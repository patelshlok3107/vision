#!/usr/bin/env bash
# VISION VPS deploy — run on Hetzner/DigitalOcean Ubuntu 22.04 (fresh)
set -e

# 1) System
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y docker.io docker-compose-plugin nginx certbot python3-certbot-nginx git curl ufw

sudo systemctl enable --now docker
sudo usermod -aG docker $USER || true

# 2) Clone — replace with your repo
# git clone https://github.com/patelshlok3107/vision.git ~/VISION
# cd ~/VISION
# If updating: git pull && docker compose -f docker-compose.prod.yml pull

# 3) Env
if [ ! -f backend/.env ]; then
  cp backend/.env.prod.example backend/.env
  echo ">> EDIT backend/.env NOW: SECRET_KEY, DB_PASSWORD, ALLOWED_HOSTS"
  echo "   nano backend/.env"
  exit 1
fi

# 4) Firewall
sudo ufw allow OpenSSH
sudo ufw allow 80
sudo ufw allow 443
sudo ufw --force enable

# 5) Build & run infra
docker compose -f docker-compose.prod.yml up -d --build
echo "Waiting 20s for DB/Redis/Ollama..."
sleep 20

# 6) Migrate + create superuser
docker compose -f docker-compose.prod.yml exec backend python manage.py migrate --noinput
docker compose -f docker-compose.prod.yml exec backend python manage.py createsuperuser --noinput || true
# If createsuperuser needs interactive, run:
# docker compose -f docker-compose.prod.yml exec backend python manage.py createsuperuser

# 7) Pull Ollama models (inside ollama container)
docker compose -f docker-compose.prod.yml exec ollama ollama pull llama3
docker compose -f docker-compose.prod.yml exec ollama ollama pull moondream
docker compose -f docker-compose.prod.yml exec ollama ollama pull nomic-embed-text
docker compose -f docker-compose.prod.yml exec ollama ollama list

# 8) Nginx + Certbot — EDIT nginx.conf first: server_name api.yourdomain.com
# Point DNS A record api.yourdomain.com -> VPS_IP before this
DOMAIN=$(grep server_name nginx.conf | head -1 | awk '{print $2}' | tr -d ';')
if [[ "$DOMAIN" != "api.yourdomain.com" && -n "$DOMAIN" ]]; then
  sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m you@yourdomain.com --redirect
  sudo systemctl reload nginx
  # Or with docker nginx: use certbot certonly --webroot -w ./certbot/www -d $DOMAIN
fi

# 9) Health checks
curl -sf http://127.0.0.1:8000/api/ai/health/ | head -c 500; echo
curl -sf http://ollama:11434/api/tags | head -c 200; echo

echo "Done. Set Vercel NEXT_PUBLIC_API_URL=https://$DOMAIN and redeploy frontend."
echo "Logs: docker compose -f docker-compose.prod.yml logs -f backend"
