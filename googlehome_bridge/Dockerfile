ARG BUILD_FROM
FROM ${BUILD_FROM}

WORKDIR /app

# Ensure python & pip present even if BUILD_FROM ended up being a plain base image
RUN set -e; \
	if ! command -v python3 >/dev/null 2>&1; then \
		echo "Installing python3 & pip (fallback)"; \
		apk update && apk add --no-cache python3 py3-pip; \
	fi; \
	if ! command -v pip >/dev/null 2>&1; then \
		echo "Bootstrapping pip"; \
		python3 -m ensurepip || true; \
		ln -sf /usr/bin/pip3 /usr/bin/pip || true; \
	fi; \
	python3 -m pip install --no-cache --upgrade pip

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py /app/server.py
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 5000
ENTRYPOINT ["/run.sh"]