############################
# Frontend build stage
############################
FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json ./
# If a lock file exists copy it for better caching
COPY frontend/package-lock.json ./ 2>/dev/null || true
RUN npm install --no-audit --no-fund
COPY frontend/ .
RUN npm run build

############################
# Backend stage
############################
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install backend dependencies
COPY googlehome_bridge/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy backend application (root server.py) and entrypoint
COPY server.py /app/server.py
COPY googlehome_bridge/run.sh /run.sh
RUN chmod +x /run.sh

# Copy built frontend assets
COPY --from=frontend /frontend/dist /app/frontend-dist

ENV FRONTEND_DIST=/app/frontend-dist
EXPOSE 5000
ENTRYPOINT ["/run.sh"]