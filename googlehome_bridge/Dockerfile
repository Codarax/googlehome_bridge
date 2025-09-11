ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM ${BUILD_FROM}

WORKDIR /app

# Switch to Debian slim approach if base image provides apt (some ha base images are debian). Try apk first; if it fails, use apt.
RUN set -e; \
	if command -v apk >/dev/null 2>&1; then \
		echo 'Using Alpine package manager'; \
		for i in 1 2 3; do \
			apk update && apk add --no-cache python3 py3-pip bash && break || { echo 'apk attempt failed, retrying...'; sleep 3; }; \
		done; \
		ln -sf python3 /usr/bin/python; \
		python3 -m ensurepip || true; \
		pip3 install --no-cache --upgrade pip; \
	elif command -v apt-get >/dev/null 2>&1; then \
		echo 'Using Debian apt-get'; \
		apt-get update && apt-get install -y --no-install-recommends python3 python3-pip bash && \
		ln -sf python3 /usr/bin/python && \
		python3 -m pip install --no-cache --upgrade pip && \
		rm -rf /var/lib/apt/lists/*; \
	else \
		echo 'ERROR: No supported package manager found (apk or apt-get)'; exit 1; \
	fi

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
