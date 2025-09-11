ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM ${BUILD_FROM}

WORKDIR /app

# Base images already contain Python. Just install deps.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy full application (root server.py lives one level up in repo, so include it explicitly)
COPY server.py /app/server.py
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 5000
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENTRYPOINT ["/run.sh"]
