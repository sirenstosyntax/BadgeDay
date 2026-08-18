#!/usr/bin/env bash
# BadgeDay — Cloud Agent install.
#
# Prepares both halves of the repo for local development: the Python/FastAPI API (plus the
# ingestion CLI and the queue worker) and the React/Vite SPA. It is idempotent — safe to
# re-run against a cached or partially prepared tree — and needs no credentials. Every
# external service (Supabase, Anthropic, Azure, Stripe) is optional; the test suite and the
# ingestion pipeline run against synthetic fixtures with nothing configured.
set -euo pipefail

cd "$(dirname "$0")/.."

# The default image ships Python 3.12 but not the stdlib venv module. Install it once; the
# dpkg check keeps re-runs (and snapshot boots that already have it) from paying for apt.
if ! dpkg -s python3.12-venv >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3.12-venv
fi

# Backend. An editable install is deliberate: it keeps the source tree in place so
# app/spa.py resolves web/dist by walking up from its own location, while still installing
# the dependencies and the console scripts (badgeday-ingest, badgeday-worker) from
# pyproject. `python3 -m venv` reuses an existing .venv rather than clobbering it.
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"

# Frontend dependencies, from the lockfile.
npm --prefix web ci

# The SPA throws at module load when the Supabase variables are unset, so without these the
# dev server cannot even render the sign-in screen. They are public-by-design values (they
# identify the project and grant nothing; access is the candidate's token plus RLS), and
# these are obvious placeholders — real magic-link auth needs real values supplied as
# secrets. Written only when absent so a real local file is never overwritten.
if [ ! -f web/.env.local ]; then
  cat > web/.env.local <<'EOF'
VITE_SUPABASE_URL=https://placeholder.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_placeholder
VITE_API_URL=http://localhost:8000
EOF
fi
