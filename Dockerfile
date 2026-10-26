# Production Container Image for Vellakshya PDF Workstation
FROM python:3.12-slim

# System dependencies for PyMuPDF, fonts, and networking
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    libmupdf-dev \
    fonts-dejavu-core \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source and assets
COPY app/ ./app/
COPY README.md .

# Expose server port (configurable via PORT env var, defaults to 7860 for Hugging Face Spaces)
ENV PORT=7860
EXPOSE 7860

# Non-root security user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://127.0.0.1:${PORT:-7860}/api/health || exit 1

# Start FastAPI via Uvicorn
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
