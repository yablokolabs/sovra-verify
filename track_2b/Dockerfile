# Sovra Verify container image.
#
# Build from the repository root so the build context can see track_2b/:
#     docker build -f track_2b/Dockerfile -t sovra-verify:local .
#
# Credentials are NEVER part of this image. They are injected at run time as
# named environment variables by scripts/launch.sh, which reads only the two
# named application entries out of the host credential file. The credential file
# is never copied, mounted or referenced below, and a build-time guard fails the
# build if anything credential-shaped ends up under /app.

# syntax=docker/dockerfile:1

# ---------------------------------------------------------------- frontend
FROM node:22-slim AS frontend

WORKDIR /build/frontend

# Copy the manifests first so dependency layers cache independently of source.
COPY track_2b/frontend/package.json track_2b/frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then \
        npm ci --no-audit --no-fund; \
    else \
        echo "no package-lock.json present; falling back to npm install"; \
        npm install --no-audit --no-fund; \
    fi

COPY track_2b/frontend/ ./

# The build must succeed without any environment variable, because the compiled
# frontend must not depend on build-time secrets.
RUN npm run build \
    && test -f dist/index.html \
    && echo "frontend build produced dist/index.html"

# ----------------------------------------------------------------- runtime
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/track_2b/backend \
    SOVRA_WORK_DIR=/app/.sovra_work

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY track_2b/backend/requirements.txt /app/track_2b/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/track_2b/backend/requirements.txt

COPY track_2b/backend/ /app/track_2b/backend/
# api.py serves the frontend from <repo>/track_2b/frontend/dist, so the built
# assets must land at exactly this path.
COPY --from=frontend /build/frontend/dist /app/track_2b/frontend/dist

COPY track_2b/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh

# Guard: fail the build if a credential file or a credential-shaped string is
# present anywhere in the application tree. This is a real check, not a comment.
RUN set -eu; \
    for forbidden in /app/.env /app/.hermes /app/.env.local /app/credentials.json; do \
        if [ -e "$forbidden" ]; then \
            echo "SECURITY: refusing to build with $forbidden present in the image" >&2; \
            exit 1; \
        fi; \
    done; \
    if grep -rInE 'sk-[A-Za-z0-9]{16,}|hf_[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{12,}' \
         --include='*.py' --include='*.ts' --include='*.tsx' --include='*.js' \
         --include='*.json' --include='*.txt' --include='*.md' /app/track_2b 2>/dev/null; then \
        echo "SECURITY: a credential-shaped string was found in the application tree" >&2; \
        exit 1; \
    fi; \
    echo "build-time secret guard passed: no credential material in the image"

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin sovra \
    && mkdir -p /app/.sovra_work \
    && chown -R sovra:sovra /app

USER sovra

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:8080/health" >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD []
