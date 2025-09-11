Initialization helper for production deployment

Files:
- setup_tokens.sh: create /opt/oauth-server/tokens.json and devices.json, set ownership and permissions.

Usage (on target server as root):

1. Copy repository to /opt/oauth-server (example):
   rsync -av --exclude='.git' /local/path/to/repo/ /opt/oauth-server/

2. Run the setup script:
   sudo sh /opt/oauth-server/deploy/setup_tokens.sh

3. Edit /etc/ha-oauth.env and ensure it contains:
   TOKENS_FILE=/opt/oauth-server/tokens.json
   DEVICES_FILE=/opt/oauth-server/devices.json
   CLIENT_ID=...
   CLIENT_SECRET=...
   HA_URL=...
   HA_TOKEN=...

   Ensure the env file is owned by root and mode 600:
   sudo chown root:root /etc/ha-oauth.env && sudo chmod 600 /etc/ha-oauth.env

4. Reload and restart the systemd unit (example unit name: oauth-server):
   sudo systemctl daemon-reload
   sudo systemctl restart oauth-server
   sudo systemctl status oauth-server

5. Check the logs if the service fails to start:
   sudo journalctl -u oauth-server -f

Notes:
- The setup script creates a system user 'haoauth' if missing and chowns the app dir to it.
- If you run the service under a different user, change SERVICE_USER in the script or update ownership accordingly.
Deployment steps for Debian

1) Create a system user and directories

sudo useradd --system --no-create-home --shell /usr/sbin/nologin haoauth
sudo mkdir -p /opt/ha-oauth
sudo chown haoauth:haoauth /opt/ha-oauth
sudo mkdir -p /var/lib/ha-oauth
sudo chown haoauth:haoauth /var/lib/ha-oauth

2) Copy repository to /opt/ha-oauth and create a virtualenv

sudo rsync -a --exclude='.venv' . /opt/ha-oauth/
sudo chown -R haoauth:haoauth /opt/ha-oauth
sudo -u haoauth python3 -m venv /opt/ha-oauth/venv
sudo -u haoauth /opt/ha-oauth/venv/bin/pip install -r /opt/ha-oauth/requirements.txt

3) Create env file

sudo cp /opt/ha-oauth/deploy/ha-oauth.env.example /etc/ha-oauth.env
# edit /etc/ha-oauth.env and set HA_TOKEN and any secrets
sudo chown root:root /etc/ha-oauth.env
# make file readable only by root (recommended)
sudo chmod 600 /etc/ha-oauth.env

4) Install systemd service

sudo cp /opt/ha-oauth/deploy/ha-oauth.service /etc/systemd/system/ha-oauth.service
sudo systemctl daemon-reload
sudo systemctl enable --now ha-oauth.service

5) Troubleshooting

- Check logs:
  sudo journalctl -u ha-oauth.service -f
- Ensure HA_URL is reachable from the server and HA_TOKEN is valid.
 - Ensure HA_URL is reachable from the server and HA_TOKEN is valid.
 - The `/etc/ha-oauth.env` file must contain `HA_URL` and `HA_TOKEN` (Home Assistant long-lived access token). Keep this file out of source control and restrict permissions.
- If you change `devices.json`, restart service or trigger a reload by touching the file.

Security notes
- Keep `/etc/ha-oauth.env` readable only by root.
- Consider using system secret store (Vault) for HA_TOKEN in production.

