# BadgeDay — one image, two roles.
#
# The web role serves the built SPA and the API from a single origin (see app/spa.py). The
# worker role runs the ingestion/generation queue from the very same image, with a different
# command. Both are deployed from this Dockerfile; nothing about the image decides which one
# it is, the command does.

# --- Stage 1: build the single-page app ------------------------------------------------
# Vite inlines VITE_* variables at build time, so the Supabase URL and publishable key are
# baked in here. That is correct — both are public (they identify the project and grant
# nothing; access is the candidate's token plus RLS). VITE_API_URL is empty because the API
# is served from the same origin as the app in production, so requests are same-origin paths.
FROM node:20-alpine AS web
WORKDIR /web

COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_PUBLISHABLE_KEY
ARG VITE_API_URL=""
RUN VITE_SUPABASE_URL="$VITE_SUPABASE_URL" \
    VITE_SUPABASE_PUBLISHABLE_KEY="$VITE_SUPABASE_PUBLISHABLE_KEY" \
    VITE_API_URL="$VITE_API_URL" \
    npm run build

# --- Stage 2: the Python runtime -------------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

# Installed editable, deliberately: it keeps the source tree in place so app/spa.py still
# resolves web/dist by walking up from its own location, while still installing the
# dependencies and the console scripts (badgeday-worker) from pyproject.
COPY pyproject.toml ./
COPY app/ ./app/
# C2 only. The image WORKDIR is /app; rubric.load reads this next to app/, not from CWD.
# Do not copy recruit_rubric_c3_teamwork.md — C3 is not publishable.
COPY recruit_rubric_c2_motivation.md ./
RUN pip install -e .

# The built SPA from stage 1, landing where app/spa.py looks for it (../web/dist).
COPY --from=web /web/dist ./web/dist

# Run as a non-root user. Nothing here needs root, and a container that drops it is one
# fewer thing that matters if the process is ever compromised.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# Default role is the web server. The worker deployment overrides this command with
# ["python", "-m", "app.worker.runner"]. Container Apps injects PORT; default to 8000 for
# a bare `docker run`.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
