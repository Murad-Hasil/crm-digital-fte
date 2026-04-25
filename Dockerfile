# =============================================================================
# Stage 1 — dependency builder
# Installs only production packages into /install so the final image
# contains no build tools or cache.
# =============================================================================
FROM python:3.12-slim AS builder

WORKDIR /install

# System deps needed to compile asyncpg / cryptography wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Install CPU-only torch first to avoid 3GB CUDA build being pulled by sentence-transformers
RUN pip install --prefix=/install --no-cache-dir \
    torch==2.3.1+cpu --extra-index-url https://download.pytorch.org/whl/cpu \
 && pip install --prefix=/install --no-cache-dir -r requirements.txt

# =============================================================================
# Stage 2 — runtime image
# Copies only the pre-built site-packages and the app source.
# =============================================================================
FROM python:3.12-slim AS runtime

# Non-root user for security
RUN addgroup --system fte && adduser --system --ingroup fte fte

WORKDIR /app

# Pull compiled packages from builder
COPY --from=builder /install /usr/local

# Application source
COPY app/ ./app/

# Credentials directory (mounted via K8s secret at runtime)
RUN mkdir -p /app/credentials && chown fte:fte /app/credentials

USER fte

EXPOSE 7860

# Default: run the FastAPI server on 7860 (HF Spaces standard port).
# docker-compose.yml overrides CMD with --port 8000 for local dev.
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "2"]
