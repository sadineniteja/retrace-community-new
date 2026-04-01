# Deploy checklist (run on your machine)

Cloudflare **blocks Worker creation** until the account email is verified and you use an API token (or `wrangler login`).

## 1. Verify account email

[Verify your Cloudflare account email](https://developers.cloudflare.com/fundamentals/setup/account/verify-email-address/). Without this, the API returns **10034**.

## 2. API token for Wrangler (or use `wrangler login`)

Create a token with **Workers Scripts:Edit** (and **Account Settings:Read** if prompted). Export:

```bash
export CLOUDFLARE_API_TOKEN='...'
```

## 3. Install & deploy

```bash
cd infra/cloudflare/retrace-llm-edge
npm install
npm run deploy
npm run secret
# paste upstream origin, e.g. https://your-project-main-xxxxx.d2.zuplo.dev (no trailing slash)
```

## 4. Custom domain

Dashboard: **Workers & Pages** → **retrace-llm-edge** → **Settings** → **Triggers** → **Custom Domains** → add **llm.lumenatech.ai**.

## 5. Remove conflicting DNS

Dashboard: **DNS** → delete the **CNAME** `llm` → `cname.zuplo.app` (the Worker’s custom domain will replace it).  
If you skip step 4, keep the CNAME until the Worker is live.

## 6. ReTrace

```env
GATEWAY_BASE_URL=https://llm.lumenatech.ai
```
