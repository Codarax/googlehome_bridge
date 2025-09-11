#!/usr/bin/env bash
set -euo pipefail
# Home Assistant style entrypoint
cd /app || exit 1
exec python server.py
