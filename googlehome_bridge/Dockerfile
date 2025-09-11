ARG BUILD_FROM=python:3.11-slim
FROM ${BUILD_FROM}

WORKDIR /app

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt

# Copy application
COPY server.py /app/server.py
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 5000

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENTRYPOINT ["/run.sh"]
