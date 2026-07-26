# Deploying BadgeDay to Azure

BadgeDay ships as **one image in two roles** (see the `Dockerfile`):

- **web** — serves the built SPA and the API from a single origin (`app/spa.py`), public.
- **worker** — runs the ingestion/generation queue (`app.worker.runner`), no ingress.

Both run on **Azure Container Apps**, in the resource group that holds the existing sts
infrastructure. The image is built in **ACR's cloud** (`az acr build`), so you do **not**
need Docker installed locally.

## Prerequisites (one-time)

1. **Azure CLI.** Install from https://learn.microsoft.com/cli/azure/install-azure-cli, then:
   ```bash
   az login                       # interactive — opens a browser
   az account set --subscription "<the sts subscription>"   # if you have more than one
   az extension add --name containerapp
   az provider register --namespace Microsoft.App
   az provider register --namespace Microsoft.OperationalInsights
   ```
2. **Config files present** (already are, not committed):
   - `.env` — backend runtime secrets (Supabase, Anthropic, Azure Document Intelligence, Stripe).
   - `web/.env.local` — `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` (public; baked into the SPA at build).

## Deploy

From the repo root:

```bash
./deploy/azure-deploy.sh
```

It prints the subscription, the resource names, and **which Stripe key mode** it found, then
asks before creating anything. It is idempotent — re-run it to ship a new build (the image
tag defaults to the current git short SHA). Override any name via env var, e.g.
`LOCATION=westus2 ./deploy/azure-deploy.sh`.

What it creates: an Azure Container Registry (`Basic`), a Container Apps environment, and the
two container apps. Roughly **$40–70/month** at idle for the environment + registry + one
always-on replica of each app; the real cost driver is Document Intelligence and Anthropic
usage, which are per-document and unchanged by this.

## After the first deploy

1. **Stripe webhook.** The `STRIPE_WEBHOOK_SECRET` in `.env` is only the local `stripe listen`
   secret — it does **not** work in production. In the Stripe dashboard, add a webhook
   endpoint at `https://app.badgeday.com/billing/webhook` (or, before the custom domain is
   bound, `https://<web-fqdn>/billing/webhook`), subscribe it to `checkout.session.completed`
   and `customer.subscription.created/updated/deleted`, copy its **signing secret** into
   `.env` as `STRIPE_WEBHOOK_SECRET`, and re-run the deploy script.
2. **Custom domain.** The app's canonical host is **`app.badgeday.com`**. Map it to the web
   app (`az containerapp hostname add` + a managed certificate) and re-run the deploy script:
   it checks whether that hostname is bound and, once it is, sets `PUBLIC_WEB_URL` to
   `https://app.badgeday.com` itself. Until then the app runs on the `azurecontainerapps.io`
   URL the script prints, and `PUBLIC_WEB_URL` stays pointed at that — the script says so when
   it falls back. Deploying a different set of resources? Pass `CANONICAL_WEB_URL=…` (or `""`
   to always use the ingress FQDN).

   Do **not** point `badgeday.com` at this app: `badgeday.com` is the separate
   marketing/waitlist site (Netlify, permanent apex), and `badgeday.app` 301s to it at the
   DNS/hosting layer (Hostinger) — neither belongs to the app. `CANONICAL_HOST` /
   `REDIRECT_HOSTS` stay empty because the app answers on the single host above.
3. **Going live.** Verification used Stripe **test** keys. To take real payments, put the
   `sk_live_…` secret, the live price IDs, and the live webhook signing secret in `.env`,
   then re-run. The script will warn you when it sees `sk_live`.

## Notes

- Secrets are pushed as Container Apps **secrets** and referenced by env var, so they do not
  appear in `az containerapp show` output or image layers.
- `VITE_API_URL` is built empty on purpose: the SPA and API share an origin, so the browser
  calls same-origin paths and there is no CORS to configure.
- The worker runs `min-replicas 1, max-replicas 1` — the Postgres job queue
  (`SELECT … FOR UPDATE SKIP LOCKED`) is safe with more, but one is enough for V1.
