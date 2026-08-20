#!/bin/bash
# terraform/scripts/launch.sh.tpl
set -euxo pipefail
exec > /var/log/calorie-tracker-launch.log 2>&1
exec < /dev/null
export DEBIAN_FRONTEND=noninteractive
umask 077

apt-get update -y
apt-get install -y git curl ca-certificates gnupg debian-keyring debian-archive-keyring apt-transport-https

# uv -- installs directly to /usr/local/bin, a path already on PATH for
# both this script and the systemd unit below, so no symlink step is needed.
curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

# Caddy -- official Cloudsmith apt repo (caddyserver.com/docs/install)
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
chmod o+r /etc/apt/sources.list.d/caddy-stable.list
apt-get update -y
apt-get install -y caddy

# Repo is public, so a plain HTTPS clone needs no credentials at all.
git clone https://github.com/tomcioslav/kalorie.git /opt/calorie-tracker
cd /opt/calorie-tracker
/usr/local/bin/uv sync --frozen

mkdir -p /var/lib/calorie-tracker

cat > /etc/calorie-tracker.env <<'ENVEOF'
USDA_API_KEY=${usda_api_key}
DATABASE_PATH=/var/lib/calorie-tracker/calorie_tracker.db
COGNITO_REGION=${cognito_region}
COGNITO_USER_POOL_ID=${cognito_user_pool_id}
COGNITO_APP_CLIENT_ID=${cognito_app_client_id}
PUBLIC_MCP_URL=${public_mcp_url}
UVICORN_HOST=127.0.0.1
UVICORN_PORT=8000
ENVEOF
chmod 600 /etc/calorie-tracker.env

cat > /etc/systemd/system/calorie-tracker.service <<'UNITEOF'
[Unit]
Description=Calorie Tracker MCP server
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/calorie-tracker
EnvironmentFile=/etc/calorie-tracker.env
ExecStart=/usr/local/bin/uv run python -m calorie_tracker.mcp_app.main
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNITEOF

systemctl daemon-reload
systemctl enable --now calorie-tracker

cat > /etc/caddy/Caddyfile <<'CADDYEOF'
${sslip_hostname} {
    reverse_proxy 127.0.0.1:8000
}
CADDYEOF
chmod 644 /etc/caddy/Caddyfile

systemctl enable --now caddy
systemctl reload caddy || systemctl restart caddy

touch /var/log/calorie-tracker-launch-complete
rm -f /tmp/launch.sh
