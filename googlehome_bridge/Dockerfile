FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Copy requirements from subfolder explicitly (since build context is repo root)
COPY googlehome_bridge/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application files
COPY googlehome_bridge/server.py /app/server.py
COPY googlehome_bridge/run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 5000
ENTRYPOINT ["/run.sh"]