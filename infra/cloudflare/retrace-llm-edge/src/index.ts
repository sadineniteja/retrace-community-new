/**
 * ReTrace LLM edge — enterprise auth gateway.
 *
 * Auth priority (first match wins):
 *   1. Supabase JWT  — Authorization: Bearer <supabase_access_token>
 *      Worker verifies via JWKS, then replaces Authorization with the real
 *      upstream API key (UPSTREAM_API_KEY secret). The key never leaves this Worker.
 *
 *   2. Legacy HMAC   — X-Gateway-Sig: <ts>.<hmac_sha256(GATEWAY_SECRET, ts)>
 *      Kept for email / enterprise logins that don't have a Supabase JWT.
 *      Still injects UPSTREAM_API_KEY before forwarding.
 *
 * Required secrets (wrangler secret put):
 *   UPSTREAM_ORIGIN   — e.g. https://api.x.ai
 *   UPSTREAM_API_KEY  — the real LLM provider API key (never exposed to backend)
 *
 * Optional secrets:
 *   GATEWAY_SECRET    — HMAC secret for legacy path (remove once all users use JWT)
 *
 * Required vars (wrangler.toml [vars]):
 *   SUPABASE_JWKS_URL — https://<project>.supabase.co/auth/v1/.well-known/jwks.json
 */

export interface Env {
  UPSTREAM_ORIGIN: string;   // Zuplo URL — it holds the real API key
  GATEWAY_SECRET: string;    // Legacy HMAC (email/enterprise logins)
  SUPABASE_JWKS_URL: string; // Public var — set in wrangler.toml [vars]
}

const SIG_HEADER = "x-gateway-sig";
const MAX_SKEW_S = 60;
const JWKS_CACHE_TTL_S = 600;

const CORS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
  "Access-Control-Allow-Headers":
    "Authorization, Content-Type, X-Requested-With, OpenAI-Beta, Anthropic-Beta, X-Gateway-Sig",
  "Access-Control-Max-Age": "86400",
};

function hopByHop(name: string): boolean {
  const h = name.toLowerCase();
  return (
    h === "connection" || h === "keep-alive" || h === "proxy-authenticate" ||
    h === "proxy-authorization" || h === "te" || h === "trailers" ||
    h === "transfer-encoding" || h === "upgrade" || h === "host" ||
    h.startsWith("cf-") || h === "cdn-loop"
  );
}

function jsonError(message: string, status: number): Response {
  return new Response(
    JSON.stringify({ error: { message, type: "auth_error" } }),
    { status, headers: { "Content-Type": "application/json", ...CORS } },
  );
}

// ── HMAC (legacy) ──────────────────────────────────────────────────────────

async function hmacSha256(secret: string, message: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function verifyHmacSig(secret: string, raw: string): Promise<boolean> {
  const dot = raw.indexOf(".");
  if (dot < 1) return false;
  const ts = raw.slice(0, dot);
  const sig = raw.slice(dot + 1);
  const now = Math.floor(Date.now() / 1000);
  const reqTime = parseInt(ts, 10);
  if (isNaN(reqTime) || Math.abs(now - reqTime) > MAX_SKEW_S) return false;
  const expected = await hmacSha256(secret, ts);
  return sig === expected;
}

// ── Supabase JWT verification ───────────────────────────────────────────────

function base64urlDecode(str: string): Uint8Array {
  const b64 = str.replace(/-/g, "+").replace(/_/g, "/");
  const padded = b64.padEnd(b64.length + (4 - (b64.length % 4)) % 4, "=");
  const binary = atob(padded);
  return new Uint8Array([...binary].map((c) => c.charCodeAt(0)));
}

interface JwkKey {
  kty: string;
  kid?: string;
  alg?: string;
  n?: string;
  e?: string;
  x?: string;
  y?: string;
  crv?: string;
  use?: string;
}

let _jwksCache: { keys: JwkKey[]; expires: number } | null = null;

async function getJwks(jwksUrl: string): Promise<JwkKey[]> {
  const now = Math.floor(Date.now() / 1000);
  if (_jwksCache && _jwksCache.expires > now) return _jwksCache.keys;

  try {
    const resp = await fetch(jwksUrl, { cf: { cacheTtl: JWKS_CACHE_TTL_S } } as RequestInit);
    if (!resp.ok) return _jwksCache?.keys ?? [];
    const data = (await resp.json()) as { keys: JwkKey[] };
    _jwksCache = { keys: data.keys ?? [], expires: now + JWKS_CACHE_TTL_S };
    return _jwksCache.keys;
  } catch {
    return _jwksCache?.keys ?? [];
  }
}

async function importJwk(key: JwkKey): Promise<CryptoKey | null> {
  try {
    if (key.kty === "RSA") {
      return crypto.subtle.importKey(
        "jwk", key as JsonWebKey,
        { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
        false, ["verify"],
      );
    }
    if (key.kty === "EC") {
      return crypto.subtle.importKey(
        "jwk", key as JsonWebKey,
        { name: "ECDSA", namedCurve: key.crv ?? "P-256" },
        false, ["verify"],
      );
    }
  } catch { /* unsupported key */ }
  return null;
}

async function verifySupabaseJwt(token: string, jwksUrl: string): Promise<boolean> {
  const parts = token.split(".");
  if (parts.length !== 3) return false;

  try {
    const headerJson = new TextDecoder().decode(base64urlDecode(parts[0]));
    const payloadJson = new TextDecoder().decode(base64urlDecode(parts[1]));
    const header = JSON.parse(headerJson) as { alg?: string; kid?: string };
    const payload = JSON.parse(payloadJson) as { exp?: number; aud?: string | string[] };

    const now = Math.floor(Date.now() / 1000);
    if (payload.exp && now > payload.exp) return false;

    const aud = payload.aud;
    const audOk = aud === "authenticated" ||
      (Array.isArray(aud) && aud.includes("authenticated"));
    if (!audOk) return false;

    const keys = await getJwks(jwksUrl);
    const candidates = header.kid
      ? keys.filter((k) => k.kid === header.kid)
      : keys;

    const sigInput = new TextEncoder().encode(`${parts[0]}.${parts[1]}`);
    const sigBytes = base64urlDecode(parts[2]);

    for (const k of candidates) {
      const cryptoKey = await importJwk(k);
      if (!cryptoKey) continue;
      const alg = k.kty === "EC"
        ? { name: "ECDSA", hash: "SHA-256" } as AlgorithmIdentifier
        : { name: "RSASSA-PKCS1-v1_5" } as AlgorithmIdentifier;
      const ok = await crypto.subtle.verify(alg, cryptoKey, sigBytes, sigInput);
      if (ok) return true;
    }
    return false;
  } catch {
    return false;
  }
}

// ── Main handler ────────────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: CORS });
    }

    const authHeader = (request.headers.get("authorization") || "").trim();
    const bearerToken = authHeader.startsWith("Bearer ") ? authHeader.slice(7).trim() : "";

    // ── 1. Supabase JWT path ─────────────────────────────────────────────────
    const jwksUrl = (env.SUPABASE_JWKS_URL || "").trim();
    const looksLikeJwt = bearerToken.split(".").length === 3;

    if (looksLikeJwt && jwksUrl) {
      const valid = await verifySupabaseJwt(bearerToken, jwksUrl);
      if (!valid) return jsonError("Invalid or expired Supabase token", 403);
      // Verified — proceed to forward with real API key injected below.

    // ── 2. Legacy HMAC path ──────────────────────────────────────────────────
    } else {
      const hmacSecret = (env.GATEWAY_SECRET || "").trim();
      if (!hmacSecret) return jsonError("No auth method configured", 403);
      const raw = (request.headers.get(SIG_HEADER) || "").trim();
      const valid = await verifyHmacSig(hmacSecret, raw);
      if (!valid) return jsonError("Invalid or expired signature", 403);
    }

    // ── Forward to upstream, injecting the real API key ─────────────────────
    const url = new URL(request.url);
    const origin = (env.UPSTREAM_ORIGIN || "").trim().replace(/\/$/, "");
    if (!origin.startsWith("https://")) {
      return new Response("UPSTREAM_ORIGIN secret not set or invalid", { status: 503 });
    }

    const target = new URL(url.pathname + url.search, new URL(origin).origin);

    const outHeaders = new Headers();
    for (const [k, v] of request.headers.entries()) {
      if (!hopByHop(k) && k.toLowerCase() !== SIG_HEADER && k.toLowerCase() !== "authorization") {
        outHeaders.set(k, v);
      }
    }
    outHeaders.set("Host", new URL(origin).host);
    // No Authorization forwarded — Zuplo injects the real API key itself

    const init: RequestInit = { method: request.method, headers: outHeaders, redirect: "manual" };
    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = request.body;
    }

    let resp: Response;
    try {
      resp = await fetch(target.toString(), init);
    } catch (e) {
      return new Response(`Upstream error: ${e instanceof Error ? e.message : "unknown"}`, { status: 502 });
    }

    const rh = new Headers(resp.headers);
    for (const [k, v] of Object.entries(CORS)) rh.set(k, v);
    return new Response(resp.body, { status: resp.status, statusText: resp.statusText, headers: rh });
  },
};
