#!/usr/bin/env bash
# Pull the latest code from GitHub and restart. Run:  sudo bash /opt/ordertrack/deploy/oracle/update.sh
set -euo pipefail
cd /opt/ordertrack
git pull --ff-only
cd deploy/oracle
docker compose up -d --build
docker image prune -f >/dev/null
echo "Updated to $(git -C /opt/ordertrack log --oneline -1)"
