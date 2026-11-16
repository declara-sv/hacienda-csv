#!/usr/bin/env bash
# Deploy the API to the VPS over SSH. Runs on YOUR machine from the repo root.
#   deploy/deploy-api.sh            deploy the current commit (HEAD)
#   deploy/deploy-api.sh <git-ref>  deploy a tag/commit
#   deploy/deploy-api.sh --rollback switch back to the previous release (no migrations)
# Each deploy is a new folder under /opt/hacienda-api/releases; `current` is a symlink to it.
set -euo pipefail

HOST="${DEPLOY_HOST:-hacienda-vps}"
APP_DIR=/opt/hacienda-api
KEEP=5
cd "$(git rev-parse --show-toplevel)"

remote() { ssh -o BatchMode=yes "$HOST" "$@"; }

if [ "${1:-}" = "--rollback" ]; then
  remote "set -euo pipefail
    cur=\$(sudo readlink $APP_DIR/current)
    prev=\$(sudo ls -1d $APP_DIR/releases/* | grep -vx \"\$cur\" | tail -1)
    [ -n \"\$prev\" ] || { echo 'No previous release.' >&2; exit 1; }
    sudo -u hacienda ln -sfn \"\$prev\" $APP_DIR/current
    sudo systemctl restart hacienda-api
    echo \"Rolled back to \$prev\""
  exit 0
fi

REF="${1:-HEAD}"
SHA=$(git rev-parse --short "$REF")
if [ "$REF" = "HEAD" ] && [ -n "$(git status --porcelain -- apps/api)" ]; then
  echo "apps/api has uncommitted changes; commit them first (deploys ship a commit)." >&2; exit 1
fi
RELEASE="$APP_DIR/releases/$(date -u +%Y%m%d%H%M%S)-$SHA"
echo "Deploying $SHA to $HOST:$RELEASE"

git archive "$REF" apps/api | remote "set -euo pipefail
  sudo -u hacienda mkdir -p '$RELEASE'
  sudo -u hacienda tar -x -C '$RELEASE' --strip-components=2
"

remote "set -euo pipefail
  run() { sudo -u hacienda env HOME=$APP_DIR bash -c \"cd '$RELEASE' && \$1\"; }
  run '$APP_DIR/.local/bin/uv sync --frozen --no-dev --quiet'
  # The app reads ./.env itself (dotenv parsing), so link the shared file into the release.
  run 'ln -sfn $APP_DIR/shared/.env .env && .venv/bin/alembic upgrade head'
  sudo -u hacienda ln -sfn '$RELEASE' $APP_DIR/current
  sudo systemctl restart hacienda-api
  for i in \$(seq 1 20); do
    curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1 && { echo 'Health check OK'; break; }
    sleep 1
    [ \$i -eq 20 ] && { echo 'Health check FAILED; see: sudo journalctl -u hacienda-api -n 50' >&2; exit 1; }
  done
  sudo ls -1d $APP_DIR/releases/* | head -n -$KEEP | xargs -r sudo rm -rf
"
echo "Done. Release $SHA is live."
