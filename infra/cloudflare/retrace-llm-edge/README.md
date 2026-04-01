# ReTrace LLM edge (Cloudflare Worker)

**Stable hostname** (e.g. `https://llm.lumenatech.ai`) proxies to your upstream LLM API URL. Change upstream later by updating one secret (`UPSTREAM_ORIGIN`), not every ReTrace install.

**Prerequisites:** Cloudflare account email [verified](https://developers.cloudflare.com/fundamentals/setup/account/verify-email-address/) for Workers. See **[DEPLOY.md](./DEPLOY.md)** for the full checklist.

## Deploy

```bash
cd infra/cloudflare/retrace-llm-edge
npm install
export CLOUDFLARE_API_TOKEN=...   # or: npx wrangler login
npm run deploy
npm run secret   # UPSTREAM_ORIGIN = https://YOUR-GATEWAY.d2.zuplo.dev (no trailing slash)
```

## Custom domain

1. Workers & Pages → **retrace-llm-edge** → Settings → Triggers → **Custom Domains** → add `llm.lumenatech.ai` (or your host).
2. **Delete** any DNS record that points `llm` straight to `cname.zuplo.app` if it conflicts with the Worker.

## ReTrace backend

```env
GATEWAY_BASE_URL=https://llm.lumenatech.ai
```

ScreenOps coordinate calls use the same Worker → Zuplo `/v1` as chat; Zuplo config: **[../zuplo/SCREENOPS_CONFIG.md](../zuplo/SCREENOPS_CONFIG.md)**.
