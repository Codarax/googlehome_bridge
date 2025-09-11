#!/usr/bin/env bash
set -euo pipefail
cd /app || exit 1
exec python server.py
