#!/usr/bin/env bash
#
# One-time setup so BadgeDay can be deployed from GitHub with one button
# (.github/workflows/deploy.yml) instead of from this laptop.
#
# Run it once, from the repo root, on the laptop that already deploys — the one with
# .env, web/.env.local, `az login` and `gh auth login` done:
#
#   ./deploy/setup_github_deploy.sh
#
# It stores three repository secrets on GitHub, passing each value from here to GitHub
# without printing it:
#   BADGEDAY_ENV       — this .env (with SUPABASE_DB_URL swapped for the IPv4 session
#                        pooler if the direct host is IPv6-only; see
#                        scripts/github_deploy_env.py). This laptop's .env is not changed.
#   BADGEDAY_WEB_ENV   — web/.env.local (public VITE_* values).
#   AZURE_CREDENTIALS  — a new Azure service principal, Contributor on the BadgeDay
#                        resource group only, for azure/login in the workflow.
#
# Safe to re-run: secrets are overwritten, and re-running create-for-rbac with the same name
# rotates the service principal's secret. Do that after changing .env, so GitHub deploys
# the new values. The service principal's secret expires after a year by default; re-run
# this then too.
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-sts-examgen-rg}"
SP_NAME="${SP_NAME:-badgeday-github-deploy}"
ENV_FILE="${ENV_FILE:-.env}"
WEB_ENV_FILE="${WEB_ENV_FILE:-web/.env.local}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."   # repo root, regardless of where this is called from

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

# --- Preflight -------------------------------------------------------------------------
command -v gh >/dev/null || { echo "GitHub CLI (gh) not found. Install it, then run: gh auth login"; exit 1; }
command -v az >/dev/null || { echo "Azure CLI not found. See deploy/README.md."; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE. Run this from the BadgeDay folder that has it."; exit 1; }
[[ -f "$WEB_ENV_FILE" ]] || { echo "Missing $WEB_ENV_FILE."; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "Not signed in to GitHub. Run: gh auth login"; exit 1; }
az account show >/dev/null 2>&1 || { echo "Not signed in to Azure. Run: az login"; exit 1; }

if [[ -x .venv/bin/python ]]; then PYTHON=.venv/bin/python; else PYTHON=python3; fi
"$PYTHON" -c "import psycopg" 2>/dev/null || {
  echo "psycopg is missing. Run: source .venv/bin/activate && pip install -e ."; exit 1; }

REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
SUB_ID="$(az account show --query id -o tsv)"
SUB_NAME="$(az account show --query name -o tsv)"
az group show --name "$RESOURCE_GROUP" -o none 2>/dev/null || {
  echo "Resource group $RESOURCE_GROUP not found in subscription '$SUB_NAME'."
  echo "Run: az account set --subscription <the one BadgeDay is in>, then re-run."; exit 1; }

say "Setting up GitHub deploys for $REPO"
echo "    Azure subscription: $SUB_NAME"
echo "    Resource group:     $RESOURCE_GROUP"

# --- Secrets ---------------------------------------------------------------------------
say "Storing BADGEDAY_ENV (your .env)"
# Captured first, so a failure stops here instead of storing an empty secret.
ENV_COPY="$("$PYTHON" scripts/github_deploy_env.py "$ENV_FILE")"
printf '%s\n' "$ENV_COPY" | gh secret set BADGEDAY_ENV --repo "$REPO"
unset ENV_COPY

say "Storing BADGEDAY_WEB_ENV (web/.env.local)"
gh secret set BADGEDAY_WEB_ENV --repo "$REPO" < "$WEB_ENV_FILE"

say "Creating the deploy identity ($SP_NAME) and storing AZURE_CREDENTIALS"
AZURE_CREDS="$(az ad sp create-for-rbac \
  --name "$SP_NAME" \
  --role Contributor \
  --scopes "/subscriptions/${SUB_ID}/resourceGroups/${RESOURCE_GROUP}" \
  --json-auth \
  --only-show-errors)"
printf '%s\n' "$AZURE_CREDS" | gh secret set AZURE_CREDENTIALS --repo "$REPO"
unset AZURE_CREDS

say "Done."
echo "    GitHub can now deploy BadgeDay: Actions -> Deploy -> Run workflow."
