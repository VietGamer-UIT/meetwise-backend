# ============================================================
# Dockerfile — MeetWise Backend v4 (Cloud Run Ready)
# ============================================================
# Cloud Run yêu cầu:
#   1. Listen PORT env var (default 8080)
#   2. Không baked-in secrets
#   3. Start fast (cold start < 5s)
# ============================================================

FROM python:3.11-slim

WORKDIR /app

# System deps (z3-solver needs gcc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install deps (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Remove secrets nếu vô tình có trong context
RUN rm -f .env credentials.json service-account*.json *.key *.pem

# Non-root security
RUN useradd -m -u 1000 meetwise && chown -R meetwise:meetwise /app
USER meetwise

# Cloud Run injects PORT env var (usually 8080)
# docker-compose dùng 8000 locally
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8080}/health')" || exit 1

# ⚠️ CLOUD RUN: PORT env var được inject tự động
# Locally: PORT=8000 (via docker-compose env)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
