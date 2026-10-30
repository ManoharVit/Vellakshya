# Production Container Image for Vellakshya PDF Workstation
FROM python:3.12-slim

# Minimal system dependencies (fonts and curl for healthcheck)
# build-essential and libmupdf-dev are excluded because PyMuPDF binary wheels bundle MuPDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    fonts-dejavu-core \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python production dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source and assets
COPY app/ ./app/
COPY README.md .

# Configurable port (defaults to 8080 for Google Cloud Run compatibility)
ENV PORT=8080
EXPOSE 8080

# Non-root security user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://127.0.0.1:${PORT}/api/health || exit 1

# Start FastAPI via Uvicorn with dynamic PORT binding
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
