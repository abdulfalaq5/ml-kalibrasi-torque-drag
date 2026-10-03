# Pasang nginx untuk dev-ml-kalibrasi-torque-rag.lokatali.my.id

Hasil akhir:

| Siapa | Alamat | Jalur |
|---|---|---|
| Orang lain (internet) | `https://dev-ml-kalibrasi-torque-rag.lokatali.my.id` | browser → nginx (443, HTTPS) → `127.0.0.1:8401` (aplikasi Docker) |
| Anda di mesin itu sendiri | `http://localhost:8401` | browser → langsung aplikasi Docker |

```
Internet ──HTTPS 443──► nginx (host) ──► 127.0.0.1:8401 ──► container app ──► db
                                              ▲
Mesin ini: http://localhost:8401 ─────────────┘
```

Port 8401 hanya terbuka untuk `127.0.0.1` (lihat `docker-compose.yml`), jadi **tidak bisa diakses
langsung dari internet**. Akses dari luar hanya lewat nginx + HTTPS.

File di folder ini:

| File | Kapan dipakai |
|---|---|
| `dev-ml-kalibrasi-torque-rag.lokatali.my.id.awal.conf` | Tahap 1: HTTP saja, untuk mengambil sertifikat |
| `dev-ml-kalibrasi-torque-rag.lokatali.my.id.conf` | Tahap 2 (final): HTTPS + proxy ke 8401 |

Kedua file sudah dicek `nginx -t` (nginx 1.30) dan diuji fungsional: redirect HTTP→HTTPS,
halaman, API, login, dan pembatas login (429).

---

## 0. Prasyarat

1. **DNS**: buat record **A** `dev-ml-kalibrasi-torque-rag` di zona `lokatali.my.id` → IP publik
   server. Cek: `dig +short dev-ml-kalibrasi-torque-rag.lokatali.my.id` harus menampilkan IP server.
2. **Port 80 dan 443** terbuka ke server (firewall server dan firewall/security group penyedia).
   Bila server adalah laptop di jaringan rumah/kantor, router harus meneruskan (port forward)
   80 dan 443 ke laptop dan IP publiknya harus tetap; lebih disarankan memakai VPS.
3. **Aplikasi sudah berjalan** di server itu: `make up`, lalu `curl http://127.0.0.1:8401/api/health`
   → `{"status":"ok","database":"OK"}`.
4. Di `.env` server:
   ```ini
   COOKIE_SECURE=true
   APP_ENV=production
   ```
   lalu `docker compose up -d`. Dengan `COOKIE_SECURE=true`, login lewat `http://localhost:8401`
   **tetap bisa** di Chrome/Edge/Firefox (localhost dianggap aman oleh browser; sudah diuji di
   Chrome). Safari lama mungkin menolak — pakai subdomain bila begitu.

---

## 1. Pasang nginx dan certbot

```bash
sudo apt update
sudo apt install -y nginx certbot
sudo mkdir -p /var/www/certbot
sudo ufw allow 'Nginx Full'     # buka 80 dan 443 (jangan buka 8401)
```

## 2. Tahap 1 — konfigurasi HTTP sementara

```bash
cd ~/td-ml        # folder repo di server
sudo cp deploy/nginx/dev-ml-kalibrasi-torque-rag.lokatali.my.id.awal.conf \
        /etc/nginx/sites-available/dev-ml-kalibrasi-torque-rag.lokatali.my.id
sudo ln -sf /etc/nginx/sites-available/dev-ml-kalibrasi-torque-rag.lokatali.my.id \
            /etc/nginx/sites-enabled/dev-ml-kalibrasi-torque-rag.lokatali.my.id
sudo nginx -t && sudo systemctl reload nginx
```

## 3. Ambil sertifikat HTTPS (Let's Encrypt)

```bash
sudo certbot certonly --webroot -w /var/www/certbot \
  -d dev-ml-kalibrasi-torque-rag.lokatali.my.id \
  --email <email-anda> --agree-tos --no-eff-email
```

Berhasil bila muncul `Successfully received certificate` dan file ada di
`/etc/letsencrypt/live/dev-ml-kalibrasi-torque-rag.lokatali.my.id/`.

## 4. Tahap 2 — konfigurasi final HTTPS

```bash
sudo cp deploy/nginx/dev-ml-kalibrasi-torque-rag.lokatali.my.id.conf \
        /etc/nginx/sites-available/dev-ml-kalibrasi-torque-rag.lokatali.my.id
sudo nginx -t && sudo systemctl reload nginx
```

Untuk nginx lebih lama dari 1.25.1 (`nginx -v`): hapus baris `http2 on;` dan ubah
`listen 443 ssl;` menjadi `listen 443 ssl http2;` (juga untuk `[::]:443`).

## 5. Perpanjangan sertifikat otomatis

certbot memasang timer perpanjangan. Tambahkan reload nginx setelah perpanjangan:

```bash
echo -e '#!/bin/sh\nsystemctl reload nginx' | sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
sudo certbot renew --dry-run
```

## 6. Uji

```bash
# dari mana saja
curl -I http://dev-ml-kalibrasi-torque-rag.lokatali.my.id          # 301 ke https
curl https://dev-ml-kalibrasi-torque-rag.lokatali.my.id/api/health # {"status":"ok","database":"OK"}

# di server/laptop itu sendiri
curl http://localhost:8401/api/health
```

Lalu buka `https://dev-ml-kalibrasi-torque-rag.lokatali.my.id` di browser dan login.

---

## Isi konfigurasi final (ringkas)

| Bagian | Fungsi |
|---|---|
| `limit_req_zone … zone=tdml_login … 5r/m` | pembatas laju login per IP (nama zona unik, aman bila ada situs lain di server) |
| `upstream tdml_app { server 127.0.0.1:8401; }` | tujuan proxy = aplikasi Docker |
| server :80 | `/.well-known/acme-challenge/` untuk certbot, sisanya 301 ke HTTPS |
| server :443 | TLS 1.2/1.3, HSTS, nosniff, X-Frame-Options, Referrer-Policy, gzip |
| `client_max_body_size 100m` | unggah file Excel besar (sama dengan `MAX_UPLOAD_MB`) |
| `location = /api/auth/login` | pembatas laju login (balasan 429) |
| `location ~ ^/api/(files|…export|report…)` | unggah/ekspor/PDF: waktu tunggu 300 detik, upload tidak di-buffer |
| `location /assets/` | aset web berhash di-cache browser 30 hari |
| `allow … / deny all` (dikomentari) | opsional: batasi ke IP kantor/VPN |
| log | `/var/log/nginx/tdml.access.log`, `tdml.error.log` |

Header `X-Forwarded-Proto/For/Host` diteruskan; aplikasi menjalankan uvicorn dengan
`--proxy-headers --forwarded-allow-ips='*'` (aman karena port 8401 hanya untuk 127.0.0.1).

---

## Masalah umum

| Gejala | Penyebab / solusi |
|---|---|
| `502 Bad Gateway` | aplikasi belum jalan: `docker compose ps`, `curl http://127.0.0.1:8401/api/health`, `make logs` |
| certbot gagal (`Timeout` / `unauthorized`) | DNS belum mengarah ke server, atau port 80 tertutup |
| `413 Request Entity Too Large` | file > 100 MB; naikkan `client_max_body_size` dan `MAX_UPLOAD_MB` |
| `429` saat login | terlalu banyak percobaan; tunggu 1 menit (nginx) / 15 menit (kunci aplikasi) atau `make password` |
| Login lewat subdomain kembali ke halaman login | `.env` belum `COOKIE_SECURE=true`, atau header `X-Forwarded-Proto` tidak diteruskan |
| Login lewat `localhost:8401` gagal setelah `COOKIE_SECURE=true` | browser Safari lama; pakai Chrome/Edge/Firefox atau subdomain |
| Ingin akses tanpa nginx dari jaringan lokal (bukan localhost) | tidak disarankan; bila perlu ubah `127.0.0.1:8401:8401` menjadi `<IP-LAN>:8401:8401` di `docker-compose.yml` dan batasi dengan firewall |
