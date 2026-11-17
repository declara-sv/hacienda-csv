#!/usr/bin/env bash
# Copy a local production env file to the server (never committed). Runs on YOUR machine.
#   deploy/push-env.sh [path-to-env-file]     default: apps/api/.env.production
set -euo pipefail
HOST="${DEPLOY_HOST:-hacienda-vps}"
FILE="${1:-apps/api/.env.production}"
[ -f "$FILE" ] || { echo "Missing $FILE" >&2; exit 1; }
ssh -o BatchMode=yes "$HOST" "sudo -u hacienda tee /opt/hacienda-api/shared/.env >/dev/null && sudo chmod 600 /opt/hacienda-api/shared/.env" < "$FILE"
echo "Env file updated on $HOST. Restart to apply: ssh $HOST sudo systemctl restart hacienda-api"
