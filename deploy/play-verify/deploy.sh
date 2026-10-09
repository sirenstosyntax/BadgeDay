#!/usr/bin/env bash
#
# Deploy the keyless BadgeDay Play verifier to Cloud Run.
#
# This does not create a service-account JSON key, does not call Azure, and
# does not change Stripe or Play prices. It will not run unless
# CONFIRM_PLAY_VERIFY_DEPLOY=1 is set, and it refuses to run at all if
# PLAY_SERVICE_ACCOUNT_JSON is set.
#
# Project is fixed: sirens-to-syntax-play. Package is fixed: com.badgeday.app.
# Do not point this at DrillGround's drillground-play-ack service.
set -euo pipefail

PROJECT="sirens-to-syntax-play"
REGION="us-central1"
SERVICE="badgeday-play-verify"
SA_NAME="badgeday-play"
SA_EMAIL="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
PACKAGE="com.badgeday.app"
SECRET_NAME="badgeday-play-verify-shared"
PUSH_ENDPOINT="https://app.badgeday.com/billing/store/play/notifications"
TOPIC="badgeday-rtdn"
SUBSCRIPTION="badgeday-rtdn-push"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

if [[ -n "${PLAY_SERVICE_ACCOUNT_JSON:-}" ]]; then
  echo "Refusing: unset PLAY_SERVICE_ACCOUNT_JSON. This deploy does not use a JSON key." >&2
  exit 1
fi
if [[ "${PLAY_VERIFY_PROJECT:-$PROJECT}" != "$PROJECT" ]]; then
  echo "Refusing: this deploy only targets ${PROJECT}." >&2
  exit 1
fi

if [[ "${CONFIRM_PLAY_VERIFY_DEPLOY:-}" != "1" ]]; then
  echo "Refusing to deploy. Set CONFIRM_PLAY_VERIFY_DEPLOY=1 to run." >&2
  echo "This script does not change Azure, Stripe, or Play prices, and it does not create a JSON key." >&2
  exit 1
fi

command -v gcloud >/dev/null || { echo "gcloud is not installed." >&2; exit 1; }
command -v openssl >/dev/null || { echo "openssl is not installed." >&2; exit 1; }

active="$(gcloud config get-value project 2>/dev/null || true)"
if [[ "$active" != "$PROJECT" ]]; then
  echo "Refusing: gcloud project is '${active:-unset}'. Run: gcloud config set project ${PROJECT}" >&2
  exit 1
fi

echo "Enabling APIs on ${PROJECT}"
gcloud services enable \
  androidpublisher.googleapis.com \
  secretmanager.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  pubsub.googleapis.com \
  --project="$PROJECT"

if ! gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$SA_NAME" \
    --project="$PROJECT" \
    --display-name="BadgeDay Play verify, no JSON key"
fi

secret_file="deploy/play-verify/shared-secret.txt"
if gcloud secrets describe "$SECRET_NAME" --project="$PROJECT" >/dev/null 2>&1; then
  echo "Secret ${SECRET_NAME} already exists; not rotating it."
else
  if [[ ! -f "$secret_file" ]]; then
    umask 077
    openssl rand -hex 32 > "$secret_file"
    chmod 600 "$secret_file"
  fi
  gcloud secrets create "$SECRET_NAME" \
    --project="$PROJECT" \
    --replication-policy=automatic \
    --data-file="$secret_file"
fi

gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --project="$PROJECT" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor" \
  --quiet

stage="$(mktemp -d)"
cleanup() { rm -rf "$stage"; }
trap cleanup EXIT
mkdir -p "$stage/play_verify"
cp play_verify/*.py "$stage/play_verify/"
cp deploy/play-verify/Dockerfile "$stage/Dockerfile"
cp deploy/play-verify/requirements.txt "$stage/requirements.txt"
if find "$stage" -name 'shared-secret.txt' -o -name '.env' | grep -q .; then
  echo "Refusing to build: a secret file was staged." >&2
  exit 1
fi

gcloud run deploy "$SERVICE" \
  --project="$PROJECT" \
  --region="$REGION" \
  --source="$stage" \
  --service-account="$SA_EMAIL" \
  --allow-unauthenticated \
  --set-secrets="PLAY_VERIFY_SHARED_SECRET=${SECRET_NAME}:latest" \
  --set-env-vars="PLAY_PACKAGE_NAME=${PACKAGE}" \
  --min-instances=0 \
  --max-instances=2 \
  --memory=256Mi \
  --timeout=30 \
  --quiet

url="$(gcloud run services describe "$SERVICE" \
  --project="$PROJECT" \
  --region="$REGION" \
  --format='value(status.url)')"

if ! gcloud pubsub topics describe "$TOPIC" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud pubsub topics create "$TOPIC" --project="$PROJECT"
fi
if ! gcloud pubsub subscriptions describe "$SUBSCRIPTION" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud pubsub subscriptions create "$SUBSCRIPTION" \
    --project="$PROJECT" \
    --topic="$TOPIC" \
    --push-endpoint="$PUSH_ENDPOINT" \
    --push-auth-service-account="$SA_EMAIL" \
    --push-auth-token-audience="$PUSH_ENDPOINT" \
    --ack-deadline=30
fi

project_number="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --project="$PROJECT" \
  --member="serviceAccount:service-${project_number}@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator" \
  --quiet

echo
echo "Cloud Run: ${url}"
echo "Package:   ${PACKAGE}"
echo "Runtime:   ${SA_EMAIL}"
echo "RTDN topic: projects/${PROJECT}/topics/${TOPIC}"
echo
echo "Azure setting names for the next BadgeDay deploy. This script does not set them."
echo "  PLAY_PACKAGE_NAME=${PACKAGE}"
echo "  PLAY_VERIFY_BASE_URL=${url}"
echo "  PLAY_VERIFY_SHARED_SECRET   (file ${secret_file} if this machine created it; value not printed)"
echo "  PLAY_PUBSUB_AUDIENCE=${PUSH_ENDPOINT}"
echo "  PLAY_PUBSUB_SERVICE_ACCOUNT=${SA_EMAIL}"
echo "Leave PLAY_SERVICE_ACCOUNT_JSON empty."
echo "Copy PLAY_PRODUCT_ID_* from Play Console. Do not invent product ids."
echo
echo "Grant, in Play Console, after this command succeeds:"
echo "  1. Invite ${SA_EMAIL} on com.badgeday.app only, with View financial data"
echo "     and Manage orders and subscriptions. No other app."
echo "  2. Monetisation setup → real-time developer notifications →"
echo "     projects/${PROJECT}/topics/${TOPIC}"
