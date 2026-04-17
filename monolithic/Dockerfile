FROM quay.io/redhat-services-prod/obsint-processing-tenant/rules-containers/rules-containers-private:latest

ENV HOME=/app \
    REQUESTS_CA_BUNDLE=/etc/pki/tls/certs/ca-bundle.crt \
    PYTHONUNBUFFERED=1

WORKDIR $HOME

# Install additional system dependencies, create upload directory, and upgrade pip
RUN microdnf install --nodocs -y sqlite gcc postgresql-devel file tar unzip && \
    microdnf clean all && \
    mkdir -p /tmp/insights-uploads && chmod 777 /tmp/insights-uploads && \
    pip install --no-cache-dir -U pip setuptools wheel

# Copy only requirements first (for better layer caching)
COPY requirements.txt .

# Install additional Python dependencies from PyPI
# (ccx-* packages already present in base image)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Copy application code (changes here won't invalidate pip install layer)
COPY app ./app
COPY migrations ./migrations
COPY config.yml ./

EXPOSE 8000

USER 1001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
