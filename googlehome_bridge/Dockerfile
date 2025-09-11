ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:latest
FROM ${BUILD_FROM}

WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY server.py ./
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 5000
ENTRYPOINT ["/run.sh"]
