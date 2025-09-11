############################
# Frontend build stage
############################
FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi
COPY frontend/ .
RUN npm run build

############################
# Backend stage
############################
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
ARG BUILD_VERSION=dev
ENV BUILD_VERSION=${BUILD_VERSION}

# Install backend dependencies (use root requirements if present, fallback to addon requirements)
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt || echo "Root requirements failed, trying addon requirements" \
 && if [ -f googlehome_bridge/requirements.txt ]; then pip install --no-cache-dir -r googlehome_bridge/requirements.txt; fi || true

# Copy backend application (root server.py) and entrypoint
COPY server.py /app/server.py
COPY googlehome_bridge/run.sh /run.sh
RUN chmod +x /run.sh

# Copy built frontend assets
COPY --from=frontend /frontend/dist /app/frontend-dist

ENV FRONTEND_DIST=/app/frontend-dist
EXPOSE 5000
ENTRYPOINT ["/run.sh"]