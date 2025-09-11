ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.12
FROM ${BUILD_FROM}

WORKDIR /app

# Copy and install dependencies
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY server.py /app/server.py
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 5000
ENTRYPOINT ["/run.sh"]