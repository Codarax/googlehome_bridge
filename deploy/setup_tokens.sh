#!/bin/sh
# Helper to initialize tokens/devices files and permissions for production
# Run on the server as root (or with sudo): sudo /path/to/setup_tokens.sh

set -e

APP_DIR=/opt/oauth-server
TOKENS_FILE="$APP_DIR/tokens.json"
DEVICES_FILE="$APP_DIR/devices.json"
SERVICE_USER=haoauth

echo "Ensure app directory exists: $APP_DIR"
mkdir -p "$APP_DIR"

echo "Create service user if it doesn't exist: $SERVICE_USER"
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
  echo "Created user $SERVICE_USER"
else
  echo "User $SERVICE_USER already exists"
fi

echo "Creating tokens file if missing: $TOKENS_FILE"
if [ ! -f "$TOKENS_FILE" ]; then
  echo '{}' > "$TOKENS_FILE"
  echo "Created empty $TOKENS_FILE"
else
  echo "$TOKENS_FILE already exists"
fi

echo "Creating devices file if missing: $DEVICES_FILE"
if [ ! -f "$DEVICES_FILE" ]; then
  echo '{}' > "$DEVICES_FILE"
  echo "Created empty $DEVICES_FILE"
else
  echo "$DEVICES_FILE already exists"
fi

echo "Setting ownership to $SERVICE_USER and permissions 600"
chown "$SERVICE_USER":"$SERVICE_USER" "$TOKENS_FILE" "$DEVICES_FILE"
chmod 600 "$TOKENS_FILE" "$DEVICES_FILE"

echo "Ensure parent dir ownership"
chown -R "$SERVICE_USER":"$SERVICE_USER" "$APP_DIR"

echo "Done. Next steps:"
echo " - Ensure /etc/ha-oauth.env contains: TOKENS_FILE=$TOKENS_FILE and DEVICES_FILE=$DEVICES_FILE" 
echo "   (edit with: sudo nano /etc/ha-oauth.env)"
echo " - Reload and restart systemd service:"
echo "     sudo systemctl daemon-reload && sudo systemctl restart oauth-server && sudo systemctl status oauth-server"
echo " - Verify tokens file is writable by the service user and will be updated during runtime."

exit 0
