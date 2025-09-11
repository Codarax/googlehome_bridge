ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM ${BUILD_FROM}

WORKDIR /app

# Install python and pip (base image is Alpine minimal)
RUN apk add --no-cache python3 py3-pip bash && \
	ln -sf python3 /usr/bin/python && \
	python3 -m ensurepip || true && \
	pip3 install --no-cache --upgrade pip

# Copy requirements and install
COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY server.py /app/server.py
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 5000
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENTRYPOINT ["/run.sh"]
