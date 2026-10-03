# Tools dan Arsitektur: Prototype Sistem Kalibrasi Torque & Drag ML

Ketentuan utama: database **PostgreSQL**, semua komponen berjalan di **Docker**, kecuali **nginx** yang dipasang langsung di server (di luar Docker) sebagai pintu masuk ke domain.

## 1. Gambaran arsitektur

```
Pengguna (browser)
      |  HTTPS (domain)
      v
+--------------------------------+   <- di luar Docker
|  nginx (host)                  |
|  SSL (certbot), rate limit     |
|  login, batas unggah file      |
+---------------+----------------+
                | http://127.0.0.1:8000
================|===============================  <- di dalam Docker Compose
                v
        +---------------+        +------------------+
        |  app          | -----> |  db              |
        |  FastAPI +    |        |  PostgreSQL 16   |
        |  web React    |        +------------------+
        |  + ML (Python)|              |
        +-------+-------+        volume: pgdata
                |
     volume: uploads (file Excel)
     volume: models  (file model .joblib)

  (opsional) backup: dump database terjadwal -> folder ./backups
```

**Dibagi dua:**

| Di luar Docker (host) | Di dalam Docker |
|---|---|
| nginx, certbot (SSL), firewall (ufw), Docker Engine | PostgreSQL, aplikasi (API + web + ML), backup database |

Hanya `app` yang dibuka ke host, dan hanya di `127.0.0.1:8000`. Database **tidak** dibuka ke luar.

## 2. Daftar tools

### 2.1 Infrastruktur dan deployment

| Tool | Saran versi | Fungsi | Catatan |
|---|---|---|---|
| Ubuntu Server LTS | 24.04 | Sistem operasi server | VPS 2 vCPU, 4 GB RAM, 40 GB SSD sudah cukup |
| Docker Engine + Compose plugin | terbaru stabil | Menjalankan semua komponen | Pakai `docker compose` (bukan `docker-compose` lama) |
| nginx | paket bawaan Ubuntu | Reverse proxy, SSL, pembatasan laju login | **Di luar Docker** |
| certbot | paket bawaan | Sertifikat HTTPS gratis (Let's Encrypt) | Perpanjangan otomatis |
| ufw | paket bawaan | Firewall: buka 22, 80, 443 saja | |
| fail2ban (opsional) | paket bawaan | Blokir percobaan login SSH berulang | |

### 2.2 Backend

| Tool | Fungsi | Alasan |
|---|---|---|
| Python 3.12 | Bahasa utama | Seluruh pustaka ML ada di sini |
| FastAPI + Uvicorn | API dan penyaji file web | Cepat dibuat, dokumentasi API otomatis (`/docs`) |
| Pydantic v2 | Validasi data masuk dan keluar | Bawaan FastAPI |
| SQLAlchemy 2 + psycopg 3 | Akses PostgreSQL | Standar, mudah diuji |
| Alembic | Migrasi skema database | Perubahan tabel tercatat dan bisa diulang |
| pandas, numpy | Pengolahan data | Interpolasi, penggabungan, fitur |
| openpyxl | **Membaca** .xlsx/.xlsm | Dibaca tanpa menjalankan macro |
| XlsxWriter | **Menulis** file Excel hasil ekspor | Grafik Excel lebih lengkap |
| scikit-learn | Ridge, penskalaan, validasi (GroupKFold) | |
| XGBoost | Model utama | Kuat untuk data tabel yang sedikit |
| joblib | Menyimpan model | |
| python-multipart | Unggah file | Dibutuhkan FastAPI |
| argon2-cffi | Hash password admin | Password tidak pernah disimpan sebagai teks asli |
| itsdangerous (lewat `SessionMiddleware` Starlette) | Cookie sesi bertanda tangan | Login satu akun, tanpa kebutuhan Redis |

### 2.3 Frontend

| Tool | Fungsi | Alasan |
|---|---|---|
| Node 20 + Vite | Build frontend | Build cepat |
| React + TypeScript | Antarmuka | Banyak contoh, mudah dibantu AI |
| Plotly.js | Tiga grafik berdampingan (Hookload, Torque, Selisih) | Subplot dengan sumbu kedalaman bersama (`matches`), zoom tersinkron, sumbu terbalik, garis nol pada grafik Selisih |
| TanStack Query | Pengambilan data dari API | Status loading dan error rapi |
| Tailwind CSS (opsional) | Gaya tampilan | Cepat untuk prototype |
| react-dropzone | Unggah file | |

Hasil build frontend **disajikan oleh FastAPI** (folder `static`), jadi tidak butuh container web terpisah. Dengan begitu satu-satunya komponen di luar Docker tetap nginx.

### 2.4 Pengembangan dan kualitas

| Tool | Fungsi |
|---|---|
| Claude Code | Pendamping pengembangan (ikuti aturan data di dokumen To-Do) |
| Git + repositori privat (GitHub/GitLab) | Versi kode |
| VS Code | Editor |
| Docker Desktop | Menjalankan stack yang sama di laptop |
| pytest + httpx | Tes parser, model, dan API |
| ruff | Linter dan formatter Python |
| pre-commit | Cek otomatis sebelum commit (termasuk mencegah file data ikut ter-commit) |
| Bruno / Postman / curl | Uji API manual |
| DBeaver atau psql | Memeriksa isi database (akses lewat `docker compose exec`, bukan membuka port) |
| GitHub Actions (opsional) | Build image dan jalankan tes otomatis |

### 2.5 Sengaja tidak dipakai (untuk prototype)

| Tool | Alasan tidak dipakai |
|---|---|
| Redis, Celery | Pelatihan model cukup beberapa detik sampai menit, cukup dengan proses latar belakang bawaan FastAPI |
| MinIO / object storage | File Excel cukup disimpan di Docker volume |
| Kubernetes | Berlebihan untuk satu server |
| Banyak akun, role, SSO, manajemen pengguna | Di luar lingkup. Hanya satu akun admin |
| SHAP, Random Forest, SVR, MLP | Di luar lingkup paket 3 minggu |

> **Jika jadwal terlambat:** fallback antarmuka ke Streamlit (satu container Python tanpa build React) bisa menghemat 2-3 hari, dengan konsekuensi tampilan lebih sederhana, perlu konfigurasi WebSocket di nginx, dan login harus dibuat ulang dengan cara lain (misalnya `streamlit-authenticator`). Putuskan di akhir Hari 5, bukan setelahnya.

## 3. Struktur repositori

```
td-ml/
├─ backend/
│  ├─ app/
│  │  ├─ main.py              # FastAPI, menyajikan static/
│  │  ├─ api/                 # router: auth, files, wells, models, predictions, export
│  │  ├─ core/                # konfigurasi, logging, security (hash password, sesi)
│  │  ├─ cli.py               # set-admin-password
│  │  ├─ db/                  # session, model SQLAlchemy
│  │  ├─ parsers/             # wellplan_report.py, roadmap.py, actuals.py
│  │  ├─ services/            # dataset.py, training.py, predict.py, export.py, units.py
│  │  └─ schemas/             # Pydantic
│  ├─ alembic/
│  ├─ tests/                  # tes dengan file contoh
│  └─ requirements.txt
├─ web/                       # React + Vite
├─ scripts/                   # audit_files.py, dll.
├─ docs/                      # keputusan.md, panduan.md
├─ data/                      # TIDAK masuk Git (file client)
├─ Dockerfile
├─ docker-compose.yml
├─ .env.example
├─ .gitignore
├─ CLAUDE.md
└─ Makefile                   # up, down, logs, migrate, backup
```

## 4. Skema database (ringkas)

| Tabel | Isi utama |
|---|---|
| `admin_user` | id, username, password_hash (argon2), tanggal ubah |
| `login_attempts` | username, waktu, berhasil/tidak (untuk penguncian sementara) |
| `wells` | id, nama (anonim bila perlu), section (inci), tipe sumur, sumber klasifikasi (otomatis/manual), status |
| `uploaded_files` | id, well_id, nama file, jenis (WellPlan/roadmap), jalur file, checksum, status impor |
| `validation_issues` | file_id, level (error/warning), pesan, lokasi (sheet/baris) |
| `survey` | well_id, MD, inklinasi, azimuth, TVD, dogleg |
| `plan_results` | well_id, operasi, skenario/FF, kedalaman, nilai, satuan asli, nilai baku |
| `actual_readings` | well_id, operasi, kedalaman, nilai, satuan asli, nilai baku |
| `models` | id, algoritma, parameter (JSON), metrik (JSON), jalur file model, aktif/tidak, tanggal |
| `predictions` | id, well_id, model_id, tanggal |
| `prediction_points` | prediction_id, operasi, kedalaman, nilai WellPlan, nilai ML |

Operasi: pick up, slack off, rotating weight, torque off bottom, torque on bottom. Satuan asli selalu disimpan di samping nilai terkonversi.

## 5. File konfigurasi

### 5.1 `docker-compose.yml`

```yaml
services:
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks: [internal]

  app:
    build: .
    restart: unless-stopped
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
      UPLOAD_DIR: /data/uploads
      MODEL_DIR: /data/models
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - uploads:/data/uploads
      - models:/data/models
    ports:
      - "127.0.0.1:8000:8000"   # hanya bisa diakses dari server itu sendiri (nginx)
    networks: [internal]

  # Opsional: backup database terjadwal
  backup:
    image: prodrigestivill/postgres-backup-local:16
    restart: unless-stopped
    environment:
      POSTGRES_HOST: db
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      SCHEDULE: "@daily"
      BACKUP_KEEP_DAYS: 7
    volumes:
      - ./backups:/backups
    depends_on:
      db:
        condition: service_healthy
    networks: [internal]

volumes:
  pgdata:
  uploads:
  models:

networks:
  internal:
```

Cek ulang nama image dan tag backup di Docker Hub saat dipasang, karena tag bisa berubah.

### 5.2 `Dockerfile` (multi-stage: build web lalu app Python)

```dockerfile
# Tahap 1: build frontend
FROM node:20-alpine AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ .
RUN npm run build

# Tahap 2: aplikasi Python
FROM python:3.12-slim
WORKDIR /app
# libgomp1 dibutuhkan XGBoost (OpenMP)
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=web /web/dist ./static
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 --proxy-headers --forwarded-allow-ips='*'"]
```

### 5.3 `.env.example`

```
POSTGRES_DB=tdml
POSTGRES_USER=tdml
POSTGRES_PASSWORD=ganti-dengan-password-panjang-dan-acak
APP_ENV=production
MAX_UPLOAD_MB=100
SECRET_KEY=isi-string-acak-minimal-32-karakter
SESSION_HOURS=8
COOKIE_SECURE=true
ADMIN_USERNAME=admin
ADMIN_PASSWORD=isi-password-awal   # hanya untuk membuat akun, hapus setelah akun terbentuk
```

Salin menjadi `.env` di server dan **jangan commit** `.env`. Atur `docs_url=None` dan `openapi_url=None` pada FastAPI saat `APP_ENV=production`.

`--forwarded-allow-ips='*'` aman di sini karena port `app` hanya dibuka ke `127.0.0.1` (nginx di host), bukan ke internet.

### 5.4 nginx di host: `/etc/nginx/sites-available/td-ml`

```nginx
# Pembatas laju untuk endpoint login (di luar blok server, konteks http)
limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;

server {
    listen 80;
    server_name td.contoh.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name td.contoh.com;

    ssl_certificate     /etc/letsencrypt/live/td.contoh.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/td.contoh.com/privkey.pem;

    client_max_body_size 100m;          # file Excel .xlsm bisa beberapa MB

    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy same-origin always;

    # Login: dibatasi 5 permintaan per menit per IP
    location = /api/auth/login {
        limit_req zone=login burst=5 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;        # impor dan pelatihan bisa memakan waktu
        proxy_send_timeout 300s;
    }
}
```

Ganti `td.contoh.com` dengan domain sebenarnya. Pada nginx versi baru, `http2` pada baris `listen` memunculkan peringatan deprecated tetapi tetap berjalan. Login ada di aplikasi (satu akun admin), jadi basic auth nginx tidak dipakai lagi. Basic auth hanya dipakai sementara pada Hari 1 sampai login aktif di Hari 2 (tambahkan `auth_basic` dan `auth_basic_user_file` pada `location /` hanya selama masa itu).

### 5.5 Perintah pemasangan di server (urutan)

```bash
# 1. Paket dasar (apache2-utils hanya perlu untuk basic auth sementara di Hari 1)
sudo apt update && sudo apt install -y nginx certbot python3-certbot-nginx apache2-utils ufw

# 2. Firewall
sudo ufw allow OpenSSH && sudo ufw allow 80 && sudo ufw allow 443 && sudo ufw enable

# 3. Docker Engine + Compose plugin (ikuti panduan resmi docs.docker.com untuk Ubuntu)

# 4. Aktifkan konfigurasi nginx, lalu minta sertifikat
sudo ln -s /etc/nginx/sites-available/td-ml /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d td.contoh.com

# 5. Jalankan aplikasi
git clone <repo> td-ml && cd td-ml
cp .env.example .env   # isi password database, SECRET_KEY, dan akun admin
docker compose up -d --build
docker compose logs -f app

# 6. (Sementara, Hari 1) basic auth sampai login aplikasi aktif
sudo htpasswd -c /etc/nginx/.htpasswd nama_pengguna
```

Sertifikat HTTPS belum ada saat pertama kali, jadi blok `listen 443` baru bisa diaktifkan setelah certbot berhasil. Cara paling mudah: mulai dengan blok `listen 80` saja, jalankan certbot, lalu tambahkan blok 443.

## 6. Keamanan dan data client

Aplikasi memakai **login satu akun admin**, dan datanya rahasia serta dibuka lewat domain publik. Lapisan pengamannya:

**Login dan sesi**
- Satu akun admin. Password disimpan sebagai hash argon2, tidak pernah sebagai teks asli.
- Sesi lewat cookie bertanda tangan: HttpOnly, Secure, SameSite=Lax, masa berlaku 8 jam.
- Semua endpoint `/api/*` (termasuk unduhan file dan ekspor) wajib login, kecuali `/api/health` dan login.
- Percobaan salah dibatasi: kunci 15 menit setelah 5 kali gagal, dan nginx membatasi 5 permintaan per menit pada endpoint login.
- `/docs` dan `/openapi.json` dimatikan di production.
- Password diganti saat serah terima, dan kredensial diserahkan lewat jalur aman.
- Ganti password: `docker compose exec app python -m app.cli set-admin-password`.

**Jaringan dan server**
- **HTTPS wajib** sejak deploy pertama.
- PostgreSQL **tidak dibuka ke luar**: tanpa `ports:` di service `db`.
- `app` hanya mendengarkan `127.0.0.1:8000`.
- Firewall hanya membuka 22, 80, dan 443. SSH dengan kunci, nonaktifkan login password.
- Opsional: batasi nginx ke IP kantor client (`allow` / `deny`) bila client menyetujui.

**Data dan unggahan**
- Password dan rahasia di `.env`, bukan di kode atau Git.
- File `.xlsm` hanya **dibaca** dengan `openpyxl`, macro tidak pernah dijalankan.
- Batasi unggahan: ekstensi (`.xlsx`, `.xlsm`), ukuran maksimum, dan simpan hanya di direktori `uploads`.
- Data client tidak ke Git, dan salinan di laptop dihapus dalam 14 hari setelah proyek selesai (Pasal 11 ayat 4).
- Jangan mengunggah file client ke server sebelum login aktif dan HTTPS berjalan.

> Catatan lingkup: login satu akun ini **belum tercantum** di proposal dan perjanjian paket 3 minggu (di sana tertulis tanpa login). Catat perubahannya secara tertulis agar dokumen dan pekerjaan sama.

## 7. Backup dan pemulihan

- Backup harian lewat service `backup` (disimpan di `./backups`, 7 hari terakhir).
- Folder `uploads` dan `models` ikut dicadangkan (salin berkala dengan `rsync` atau snapshot VPS).
- Uji pulihkan **sekali** sebelum serah terima:

```bash
# Pulihkan dump ke database kosong
gunzip -c backups/last/tdml-latest.sql.gz | docker compose exec -T db psql -U tdml -d tdml
```

Sesuaikan nama file dump dengan hasil sebenarnya di folder `backups`.

## 8. Perintah harian

```bash
docker compose up -d --build     # deploy / perbarui
docker compose logs -f app       # lihat log
docker compose exec db psql -U tdml -d tdml   # periksa database
docker compose exec app alembic upgrade head  # migrasi manual
docker compose exec app python -m app.cli set-admin-password  # ganti password admin
docker compose down              # hentikan (data tetap aman di volume)
```

Peringatan: `docker compose down -v` **menghapus volume** (database dan file). Jangan dipakai di server kecuali memang ingin mengosongkan semua.

## 9. Isi `CLAUDE.md` (untuk Claude Code)

Letakkan di root repo agar konteks selalu terbaca:

- Tujuan proyek dalam 5 baris (kalibrasi hasil WellPlan dengan ML berdasarkan data aktual).
- Lingkup 8 fitur (sesuai perjanjian) ditambah login satu akun admin, dan daftar yang **tidak** dikerjakan.
- Dashboard menampilkan **tiga grafik** berdampingan: Hookload, Torque, dan Selisih, dengan sumbu kedalaman bersama. Tiap grafik membandingkan WellPlan, prediksi ML, dan aktual. Grafik Selisih: kanan = positif (lebih tinggi), kiri = negatif (lebih rendah), dengan garis nol di tengah.
- Login: semua endpoint `/api/*` wajib sesi kecuali `/api/health` dan login; jangan menambah akun atau role.
- Stack dan perintah (`docker compose ...`, `pytest`, `ruff`).
- Aturan data: jangan pernah membaca atau mencetak isi folder `data/` ke chat; pakai file contoh yang sudah dianonimkan; jangan commit data.
- Aturan satuan: simpan satuan asli, konversi di `services/units.py`.
- Aturan validasi model: selalu validasi per kelompok sumur dan bandingkan dengan baseline WellPlan.

## 10. Tambahan untuk paket 6 minggu

| Kebutuhan | Tool / perubahan | Catatan |
|---|---|---|
| Impor massal dari folder | Volume bind `./data/inbox:/data/inbox`, `processed/`, dan `rejected/` pada service `app` | Folder hanya ada di server, hak akses terbatas |
| Model tambahan | scikit-learn (Random Forest, SVR), MLP opsional (scikit-learn `MLPRegressor`) | Tanpa PyTorch kecuali diperlukan |
| Penjelasan model | `shap` | Pustaka bisa berat, uji di image Docker sejak awal |
| Ringkasan PDF | ReportLab atau WeasyPrint, grafik dari Plotly (`kaleido`) atau matplotlib | Pilih satu, uji pembuatan PDF di dalam container |
| Versi dataset | Tabel `datasets` (daftar sumur, hash, tanggal) dan kolom `dataset_id` pada tabel `models` | Hasil model bisa ditelusuri ke data yang dipakai |
| Kualitas data | Tabel `well_quality` (status A/B/C, skor, alasan) dan `quality_reviews` (keputusan tinjauan) | Hasilnya diekspor sebagai Excel |
| Antivirus (opsional) | ClamAV di container terpisah | Untuk memindai unggahan, bila client mensyaratkan |

Contoh tambahan pada service `app` di `docker-compose.yml`:

```yaml
    volumes:
      - uploads:/data/uploads
      - models:/data/models
      - ./data/inbox:/data/inbox
      - ./data/processed:/data/processed
      - ./data/rejected:/data/rejected
```

Pastikan folder `data/` ada di `.gitignore` dan memiliki hak akses yang membatasi pengguna lain di server.
