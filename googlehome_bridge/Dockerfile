ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM ${BUILD_FROM}

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt /app/requirements.txt

# Robust install of python3 & pip on Alpine base with retries + mirror fallback, then install deps
RUN set -e; \
	echo "--- Installing python3 & pip (with retries) ---"; \
	for attempt in 1 2 3 4 5; do \
		if apk update && apk add --no-cache python3 py3-pip bash; then \
			echo "apk install success on attempt ${attempt}"; break; \
		else \
			echo "apk install failed (attempt ${attempt}), sleeping 6s"; sleep 6; \
			if [ "${attempt}" = "3" ]; then \
				echo "Adding fallback mirrors"; \
				printf 'https://dl-cdn.alpinelinux.org/alpine/v3.20/main\nhttps://dl-cdn.alpinelinux.org/alpine/v3.20/community\n' > /etc/apk/repositories; \
			fi; \
		fi; \
		if [ "${attempt}" = "5" ]; then echo "FATAL: apk install failed after 5 attempts"; exit 1; fi; \
	done; \
	ln -sf python3 /usr/bin/python || true; \
	python3 -m ensurepip || true; \
	python3 -m pip install --no-cache --upgrade pip; \
	python3 -m pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY server.py /app/server.py
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 5000
ENTRYPOINT ["/run.sh"]