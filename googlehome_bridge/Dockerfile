ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM ${BUILD_FROM}

# Install python & tools then upgrade pip
RUN apk add --no-cache python3 py3-pip bash && \
    python3 -m ensurepip && \
    pip3 install --no-cache --upgrade pip

WORKDIR /app

# Copy dependency spec first for better layer caching
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r /app/requirements.txt

# Copy server wrapper (will import actual root /app/server.py if mounted/copied later)
COPY server.py /app/server.py
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 5000
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENTRYPOINT ["/run.sh"]
