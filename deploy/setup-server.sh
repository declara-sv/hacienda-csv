#!/usr/bin/env bash
# One-time server setup for the HaciendaCSV API. Runs ON the server (Ubuntu) as a sudo-capable user.
# Usage (from your machine):  ssh hacienda-vps 'bash -s' < deploy/setup-server.sh api.example.com
# Safe to re-run. It only touches /opt/hacienda-api, the `hacienda` user, one systemd unit and one
# nginx site; other sites on the server are left alone.
set -euo pipefail

DOMAIN="${1:?usage: setup-server.sh <api-domain>}"
APP_DIR=/opt/hacienda-api
APP_USER=hacienda
PORT=8010

if ss -tlnH | awk '{print $4}' | grep -q ":${PORT}$" && ! systemctl is-active -q hacienda-api; then
  echo "Port ${PORT} is already used by something else. Pick another port." >&2; exit 1
fi

id "$APP_USER" >/dev/null 2>&1 || sudo useradd --system --create-home --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
sudo mkdir -p "$APP_DIR/releases" "$APP_DIR/shared/files"
sudo touch "$APP_DIR/shared/.env"
sudo chmod 600 "$APP_DIR/shared/.env"
sudo chown -R "$APP_USER:$APP_USER" "$APP_DIR"
sudo chmod 750 "$APP_DIR"

# uv manages Python 3.13 and the virtualenv for the app user.
if ! sudo -u "$APP_USER" test -x "$APP_DIR/.local/bin/uv"; then
  curl -LsSf https://astral.sh/uv/install.sh | sudo -u "$APP_USER" env HOME="$APP_DIR" UV_NO_MODIFY_PATH=1 sh
fi

sudo tee /etc/systemd/system/hacienda-api.service >/dev/null <<UNIT
[Unit]
Description=HaciendaCSV API (FastAPI)
After=network-online.target
Wants=network-online.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR/current
Environment=HOME=$APP_DIR
ExecStart=$APP_DIR/current/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port $PORT --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=$APP_DIR

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable hacienda-api >/dev/null

if [ ! -f "/etc/nginx/sites-available/$DOMAIN" ]; then
  sudo tee "/etc/nginx/sites-available/$DOMAIN" >/dev/null <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;

    client_max_body_size 25m;

    location / {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }
}
NGINX
  sudo ln -sf "/etc/nginx/sites-available/$DOMAIN" "/etc/nginx/sites-enabled/$DOMAIN"
  sudo nginx -t
  sudo systemctl reload nginx
fi

echo "Server ready. Next:"
echo "  1. Fill $APP_DIR/shared/.env (deploy/push-env.sh)."
echo "  2. Point DNS A record for $DOMAIN at this server, then: sudo certbot --nginx -d $DOMAIN"
echo "  3. Deploy: deploy/deploy-api.sh"
