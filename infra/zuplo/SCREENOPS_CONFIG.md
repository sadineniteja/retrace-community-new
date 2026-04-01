# ScreenOps on Zuplo (Cloudflare edge only)

Coordinate-finding HTTP calls **only** go to:

`POST https://<GATEWAY_BASE_URL>/v1/chat/completions`

(Same Cloudflare Worker → Zuplo path as the main chat LLM. ReTrace does **not** use DB `screenops_api_url` / `screenops_api_key` / `screenops_model` for coordinates.)

## Config route (Zuplo)

**GET** `https://<GATEWAY_BASE_URL>/retrace/screenops-config`  
(Path is fixed in ReTrace: `SCREENOPS_GATEWAY_CONFIG_PATH`.)

Return JSON built from **Zuplo environment variables**, for example:

| JSON field | Typical Zuplo env source | Purpose |
|------------|---------------------------|---------|
| `coord_model` | e.g. `$env(SCREENOPS_COORD_MODEL)` | First attempt: ScreenOps-specific model id upstream. |
| `coord_api_key` | optional | Bearer when the user has **no** Supabase JWT (e.g. HMAC-only). If users use JWT, omit — ReTrace sends the Supabase access token. |

`coord_api_url` in JSON is **ignored**; routing to a different upstream is done inside Zuplo policies, not by changing the host ReTrace calls.

## Behaviour

1. ReTrace reads the config GET (authenticated like other gateway calls).
2. **First** coordinate attempt: `coord_model` from Zuplo **if** set and **different** from the main chat model; otherwise only the main model.
3. **Second** attempt (if the first fails or returns no coordinates): **main chat model**, same URL and same auth (`/v1` + JWT or `coord_api_key`).
4. If that still fails, the coordinate step fails (workflow handles it).

Without a managed gateway (`GATEWAY_BASE_URL` + chat using that gateway), the coordinate finder is **off** (keyboard-only mode); vision still uses the configured chat model.

## Sanity check

```bash
curl -sS -H "Authorization: Bearer <supabase_access_token>" \
  "https://<GATEWAY_BASE_URL>/retrace/screenops-config"
```

Legacy HMAC: send `X-Gateway-Sig` like other gateway calls.
