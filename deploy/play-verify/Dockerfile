# Keyless Play verifier. Build context is a staged directory that contains
# this file, requirements.txt, and play_verify/ — not the BadgeDay app image.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY play_verify ./play_verify

RUN useradd --create-home --uid 10001 appuser
USER appuser

# Cloud Run sets PORT. No JSON key is copied into the image.
CMD ["sh", "-c", "exec uvicorn play_verify.server:app --host 0.0.0.0 --port ${PORT:-8080}"]
