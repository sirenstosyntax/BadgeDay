#!/usr/bin/env bash
#
# Deploy BadgeDay to Azure Container Apps: one image, two apps (web + worker).
#
# What it does, idempotently — safe to re-run to ship a new version:
#   1. builds the image in ACR's cloud (no local Docker needed)
#   2. pushes the runtime config from .env as Container Apps secrets
#   3. creates/updates the web app (public) and the worker app (no ingress)
#
# Prerequisites (see deploy/README.md): the Azure CLI installed and `az login` done, with
# the containerapp extension. This script never logs you in and never picks a subscription
# for you — run `az account set --subscription ...` first if you have more than one.
#
# Config is overridable by environment variable; the defaults align with the existing sts
# infrastructure named in CLAUDE.md.
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-sts-examgen-rg}"
LOCATION="${LOCATION:-eastus}"
ACR_NAME="${ACR_NAME:-stsbadgeday}"          # must be globally unique, alphanumeric only
ENVIRONMENT_NAME="${ENVIRONMENT_NAME:-badgeday-env}"
WEB_APP="${WEB_APP:-badgeday-web}"
WORKER_APP="${WORKER_APP:-badgeday-worker}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || echo latest)}"
DEPLOY_ENVIRONMENT="${DEPLOY_ENVIRONMENT:-production}"  # ENVIRONMENT label for the hosted app
ENV_FILE="${ENV_FILE:-.env}"                 # runtime secrets (backend)
WEB_ENV_FILE="${WEB_ENV_FILE:-web/.env.local}"  # VITE_* build args (public)
IMAGE="${ACR_NAME}.azurecr.io/badgeday:${IMAGE_TAG}"

cd "$(dirname "$0")/.."   # repo root, regardless of where this is called from

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

# --- Preflight -------------------------------------------------------------------------
command -v az >/dev/null || { echo "Azure CLI not found. See deploy/README.md."; exit 1; }
az account show >/dev/null 2>&1 || { echo "Not logged in. Run: az login"; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE (runtime secrets)."; exit 1; }
[[ -f "$WEB_ENV_FILE" ]] || { echo "Missing $WEB_ENV_FILE (VITE build vars)."; exit 1; }

SUB="$(az account show --query name -o tsv)"
STRIPE_MODE="unknown"
grep -q '^STRIPE_SECRET_KEY=sk_live' "$ENV_FILE" && STRIPE_MODE="LIVE (real charges)"
grep -q '^STRIPE_SECRET_KEY=sk_test' "$ENV_FILE" && STRIPE_MODE="test"
say "Subscription: $SUB"
echo "    Resource group: $RESOURCE_GROUP   Location: $LOCATION"
echo "    Image:          $IMAGE"
echo "    Stripe keys:    $STRIPE_MODE   (from $ENV_FILE)"
if [[ "${ASSUME_YES:-}" != "1" ]]; then
  read -r -p $'\nCreate/update these resources? This may incur Azure charges. [y/N] ' ok
  [[ "$ok" == "y" || "$ok" == "Y" ]] || { echo "Aborted."; exit 1; }
fi

# --- Build the VITE_* build-args from the web env file ---------------------------------
# shellcheck disable=SC1090
set -a; source "$WEB_ENV_FILE"; set +a
: "${VITE_SUPABASE_URL:?set in $WEB_ENV_FILE}"
: "${VITE_SUPABASE_PUBLISHABLE_KEY:?set in $WEB_ENV_FILE}"

# --- Resource group --------------------------------------------------------------------
say "Resource group"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" -o none

# --- Container registry ----------------------------------------------------------------
say "Container registry ($ACR_NAME)"
az acr show --name "$ACR_NAME" -o none 2>/dev/null || \
  az acr create --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" \
    --sku Basic --admin-enabled true -o none

# --- Build the image in the cloud (no local Docker) ------------------------------------
# VITE_API_URL is empty on purpose: the SPA and API share an origin in this deployment.
say "Building image in ACR: $IMAGE"
az acr build --registry "$ACR_NAME" --image "badgeday:${IMAGE_TAG}" \
  --build-arg VITE_SUPABASE_URL="$VITE_SUPABASE_URL" \
  --build-arg VITE_SUPABASE_PUBLISHABLE_KEY="$VITE_SUPABASE_PUBLISHABLE_KEY" \
  --build-arg VITE_API_URL="" \
  --file Dockerfile . -o none

# --- Container Apps environment --------------------------------------------------------
az extension show --name containerapp -o none 2>/dev/null || az extension add --name containerapp -o none
say "Container Apps environment ($ENVIRONMENT_NAME)"
az containerapp env show --name "$ENVIRONMENT_NAME" --resource-group "$RESOURCE_GROUP" -o none 2>/dev/null || \
  az containerapp env create --name "$ENVIRONMENT_NAME" --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" -o none

# --- Turn .env into Container Apps secrets + env references -----------------------------
# Every configured line becomes a secret (name = KEY lowercased with dashes) and an env var
# that references it, so nothing sensitive is passed as a plain value or shows in `az ... show`.
say "Reading runtime config from $ENV_FILE"
SECRETS=(); ENVREFS=()
while IFS='=' read -r key value; do
  [[ "$key" =~ ^[A-Z] ]] || continue          # skip comments and blank lines
  [[ -n "$value" ]] || continue               # skip empty values
  value="${value%$'\r'}"                        # tolerate CRLF
  secret_name="$(echo "$key" | tr 'A-Z_' 'a-z-')"
  SECRETS+=("${secret_name}=${value}")
  ENVREFS+=("${key}=secretref:${secret_name}")
done < "$ENV_FILE"

ACR_PASS="$(az acr credential show --name "$ACR_NAME" --query 'passwords[0].value' -o tsv)"

# $1 = app name; $2 = create-only args (a string, e.g. ingress config that `update` rejects);
# the rest are args valid on both create and update (scale, --command). Splitting them this
# way is the whole point: --ingress/--target-port are set once at create and are not valid on
# update, while --command and the replica counts are.
deploy_app() {
  local app="$1" create_only="$2"; shift 2
  if az containerapp show --name "$app" --resource-group "$RESOURCE_GROUP" -o none 2>/dev/null; then
    az containerapp secret set --name "$app" --resource-group "$RESOURCE_GROUP" \
      --secrets "${SECRETS[@]}" -o none
    az containerapp update --name "$app" --resource-group "$RESOURCE_GROUP" \
      --image "$IMAGE" --set-env-vars "${ENVREFS[@]}" "$@" -o none
  else
    # shellcheck disable=SC2086
    az containerapp create --name "$app" --resource-group "$RESOURCE_GROUP" \
      --environment "$ENVIRONMENT_NAME" --image "$IMAGE" \
      --registry-server "${ACR_NAME}.azurecr.io" --registry-username "$ACR_NAME" \
      --registry-password "$ACR_PASS" \
      --secrets "${SECRETS[@]}" --env-vars "${ENVREFS[@]}" $create_only "$@" -o none
  fi
}

# --- Web app (public) ------------------------------------------------------------------
say "Web app ($WEB_APP)"
deploy_app "$WEB_APP" "--ingress external --target-port 8000" --min-replicas 1 --max-replicas 3

FQDN="$(az containerapp show --name "$WEB_APP" --resource-group "$RESOURCE_GROUP" \
  --query 'properties.configuration.ingress.fqdn' -o tsv)"
WEB_URL="https://${FQDN}"

# PUBLIC_WEB_URL is where Stripe returns the candidate after checkout, so it must be the
# app's real public URL. Set it now that we know the FQDN, and update in place.
say "Setting PUBLIC_WEB_URL=$WEB_URL"
az containerapp secret set --name "$WEB_APP" --resource-group "$RESOURCE_GROUP" \
  --secrets "public-web-url=${WEB_URL}" -o none
az containerapp update --name "$WEB_APP" --resource-group "$RESOURCE_GROUP" \
  --set-env-vars "PUBLIC_WEB_URL=secretref:public-web-url" -o none

# ENVIRONMENT is a plain label, not a secret, and it belongs to the deployment rather than
# the shared .env (which stays "development" for a laptop). Override the hosted app to the
# real environment name here.
az containerapp update --name "$WEB_APP" --resource-group "$RESOURCE_GROUP" \
  --set-env-vars "ENVIRONMENT=${DEPLOY_ENVIRONMENT}" -o none

# --- Worker app (no ingress, runs the queue) -------------------------------------------
# The command is the console script pip installed from pyproject (badgeday-worker), not
# `python -m app.worker.runner`: az parses a leading-dash arg like -m as one of its own
# flags, and the entry point sidesteps that entirely.
say "Worker app ($WORKER_APP)"
deploy_app "$WORKER_APP" "" --min-replicas 1 --max-replicas 1 --command "badgeday-worker"

# --- Done ------------------------------------------------------------------------------
say "Deployed."
echo "    Web:  $WEB_URL"
echo
echo "Next (one-time), see deploy/README.md:"
echo "  • Point a Stripe webhook at ${WEB_URL}/billing/webhook and put its signing secret"
echo "    in $ENV_FILE as STRIPE_WEBHOOK_SECRET, then re-run this script."
echo "  • Map the custom domain (badgeday.app) and update PUBLIC_WEB_URL to it."
