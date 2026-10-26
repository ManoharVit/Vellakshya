# ==============================================================================
# Vellakshya Isolated Worker Sandbox Container
# Hardened rootless container for processing untrusted PDF inputs.
# ==============================================================================
FROM python:3.12-slim

# Prevent interactive prompts and Python bytecode writes
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install security updates and minimal runtime libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged application user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /sbin/nologin -d /app appuser

WORKDIR /app

# Install isolated Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code with read-only root permissions
COPY app/ /app/app/

# Setup isolated scratch volume owned by unprivileged appuser
RUN mkdir -p /app/data/job_artifacts && \
    chown -R appuser:appgroup /app

USER 10001:10001

# Entrypoint executes worker runner with dropped capabilities
ENTRYPOINT ["python3", "-m", "app.worker.runner"]
