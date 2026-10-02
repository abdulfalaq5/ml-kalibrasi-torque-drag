#!/usr/bin/env bash
# Pemasangan server Ubuntu 24.04 (jalankan sebagai user dengan sudo).
# Pemakaian: DOMAIN=td.contoh.com EMAIL=admin@contoh.com bash deploy/setup_server.sh
set -euo pipefail
: "${DOMAIN:?isi DOMAIN}"
: "${EMAIL:?isi EMAIL untuk certbot}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "== 1. Paket dasar"
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx apache2-utils ufw fail2ban ca-certificates curl

echo "== 2. Firewall: 22, 80, 443"
sudo ufw allow OpenSSH
sudo ufw allow 80
sudo ufw allow 443
sudo ufw --force enable

echo "== 3. Docker Engine + Compose plugin (repo resmi Docker)"
if ! command -v docker >/dev/null; then
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo usermod -aG docker "$USER"
fi

echo "== 4. nginx awal (HTTP + basic auth sementara), lalu sertifikat"
if [ ! -f /etc/nginx/.htpasswd ]; then
  read -rp "Username basic auth sementara: " BA_USER
  sudo htpasswd -c /etc/nginx/.htpasswd "$BA_USER"
fi
sed "s/td.contoh.com/$DOMAIN/g" "$REPO_DIR/deploy/nginx/td-ml-awal-http.conf" | sudo tee /etc/nginx/sites-available/td-ml >/dev/null
sudo ln -sf /etc/nginx/sites-available/td-ml /etc/nginx/sites-enabled/td-ml
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo certbot certonly --nginx -d "$DOMAIN" -m "$EMAIL" --agree-tos --non-interactive

echo "== 5. nginx final (HTTPS). Basic auth sementara diaktifkan sampai login aplikasi lolos tes."
sed -e "s/td.contoh.com/$DOMAIN/g" \
    -e 's|# auth_basic "Prototype";|auth_basic "Prototype";|' \
    -e 's|# auth_basic_user_file|auth_basic_user_file|' \
    "$REPO_DIR/deploy/nginx/td-ml.conf" | sudo tee /etc/nginx/sites-available/td-ml >/dev/null
sudo nginx -t && sudo systemctl reload nginx

echo "== 6. Aplikasi"
cd "$REPO_DIR"
if [ ! -f .env ]; then
  cp .env.example .env
  sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 24)|" .env
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$(openssl rand -hex 32)|" .env
  echo "Isi ADMIN_USERNAME/ADMIN_PASSWORD di .env, lalu jalankan: docker compose up -d --build"
else
  sudo docker compose up -d --build
fi
echo "Selesai. Setelah login aplikasi lolos tes: hapus baris auth_basic di /etc/nginx/sites-available/td-ml dan reload nginx."
