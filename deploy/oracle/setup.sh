#!/usr/bin/env bash
# One-time server setup for Ubuntu (Oracle Cloud Always Free). Run:  sudo bash setup.sh
set -euo pipefail
REPO=https://github.com/GS944/Hi-speed-manufacturing.git
DIR=/opt/ordertrack
say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

say "Installing Docker and Git"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
apt-get install -y -qq git >/dev/null

say "Opening ports 80 and 443 in the server firewall"
# Oracle's Ubuntu images block everything except SSH in iptables
if ! iptables -C INPUT -p tcp -m multiport --dports 80,443 -j ACCEPT 2>/dev/null; then
  iptables -I INPUT 1 -p tcp -m multiport --dports 80,443 -j ACCEPT
fi
if command -v netfilter-persistent >/dev/null; then netfilter-persistent save >/dev/null 2>&1 || true; fi

say "Getting the application code"
if [ -d "$DIR/.git" ]; then git -C "$DIR" pull --ff-only; else git clone --depth 1 "$REPO" "$DIR"; fi
cd "$DIR/deploy/oracle"

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  say "Now fill in the settings, then run this script again:"
  echo "    sudo nano $DIR/deploy/oracle/.env"
  exit 0
fi
chmod 600 .env
grep -q '^DOMAIN=your-name' .env && { echo "Set DOMAIN in $DIR/deploy/oracle/.env first."; exit 1; }

say "Building and starting (first time: about 5-10 minutes)"
docker compose up -d --build

DOMAIN=$(grep '^DOMAIN=' .env | cut -d= -f2)
say "Waiting for https://$DOMAIN/api/health"
for i in $(seq 1 60); do
  if curl -fsS "https://$DOMAIN/api/health" 2>/dev/null; then echo; say "Done. Backend URL: https://$DOMAIN"; exit 0; fi
  sleep 5
done
echo "Not reachable yet. Check:  sudo docker compose -f $DIR/deploy/oracle/docker-compose.yml logs --tail 50"
