# Prototype Sistem Kalibrasi Torque & Drag ML

Aplikasi web untuk mengimpor laporan WellPlan + data aktual (Excel), melatih model kalibrasi
(Ridge / XGBoost, divalidasi per sumur), memprediksi sumur baru, menampilkan dashboard tiga
grafik (Hookload, Torque, Selisih), dan mengekspor hasil ke Excel. Aplikasi memakai satu akun admin.

Dokumen lain:

| Dokumen | Isi |
|---|---|
| `TODO_Prototype_3_Minggu.md` | Rencana kerja dan status |
| `TOOLS_dan_Arsitektur.md` | Tools dan arsitektur |
| `docs/panduan.md` | Panduan pemakaian dan operasional lengkap |
| `docs/keputusan.md` | Keputusan dan asumsi (K-01 … K-17) |
| `CLAUDE.md` | Konteks untuk Claude Code |

---

## Ringkasan cepat

| | Laptop (lokal) | Server (production) |
|---|---|---|
| **Link** | http://127.0.0.1:8000 | `https://<domain-anda>` (mis. `https://td.contoh.com`) |
| **Username** | nilai `ADMIN_USERNAME` di `.env` (bawaan: `admin`) | sama |
| **Password** | nilai `ADMIN_PASSWORD` di `.env` saat aplikasi **pertama kali** dijalankan | sama, lalu diganti saat serah terima |

> Tidak ada password bawaan. Akun admin dibuat sekali dari `ADMIN_USERNAME` + `ADMIN_PASSWORD`
> di `.env` saat aplikasi pertama kali jalan. Setelah itu, mengubah `.env` **tidak** mengubah
> password. Untuk menggantinya, pakai `make password` (lihat [Lupa / ganti password](#lupa--ganti-password)).

---

## A. Setup dari awal di laptop (Docker)

### Langkah 1: Siapkan perangkat

Pasang:

- **Docker**: Docker Desktop (Windows/Mac) atau Docker Engine + plugin Compose (Linux)
- **Git**

Cek bahwa keduanya terpasang:

```bash
docker --version
docker compose version     # harus "Docker Compose version v2..." (bukan docker-compose lama)
git --version
```

Python dan Node **tidak perlu** dipasang, karena semuanya dibangun di dalam Docker.

### Langkah 2: Ambil kode

```bash
git clone <url-repo> td-ml
cd td-ml
```

Jika foldernya sudah ada di laptop, cukup `cd` ke folder tersebut.

### Langkah 3: Buat file `.env`

```bash
cp .env.example .env
```

Buka `.env` dengan editor dan isi seperti contoh berikut:

```ini
POSTGRES_DB=tdml
POSTGRES_USER=tdml
POSTGRES_PASSWORD=isi-acak-panjang          # password database (tidak dipakai untuk login web)
APP_ENV=production
MAX_UPLOAD_MB=100
SECRET_KEY=isi-acak-minimal-32-karakter     # kunci tanda tangan cookie sesi
SESSION_HOURS=8
COOKIE_SECURE=false                         # LOKAL (http) wajib false; server (https) true
ADMIN_USERNAME=admin                        # username untuk login web
ADMIN_PASSWORD=GantiDenganPasswordAnda123   # password untuk login web (minimal 12 karakter disarankan)
```

Membuat nilai acak untuk `POSTGRES_PASSWORD` dan `SECRET_KEY`:

```bash
openssl rand -hex 16    # untuk POSTGRES_PASSWORD
openssl rand -hex 32    # untuk SECRET_KEY
```

Hal yang perlu diperhatikan:

- **`COOKIE_SECURE=false` wajib di laptop.** Di laptop aplikasi dibuka lewat `http://`. Bila
  nilainya `true`, browser bisa menolak menyimpan cookie sesi, sehingga login tampak berhasil
  tetapi Anda langsung kembali ke halaman login.
- `SECRET_KEY` minimal 32 karakter. Bila lebih pendek, aplikasi menolak jalan saat `APP_ENV=production`.
- `.env` **jangan di-commit**. File ini sudah ada di `.gitignore`.

### Langkah 4: Jalankan

```bash
docker compose up -d --build
```

Build pertama membutuhkan sekitar 3–10 menit, karena perlu mengunduh image dan membangun frontend serta
pustaka ML. Perintah ini menjalankan tiga container:

| Container | Fungsi |
|---|---|
| `db` | PostgreSQL 16 (data di volume `pgdata`) |
| `app` | API FastAPI + web React + ML, di port `127.0.0.1:8000` |
| `backup` | Dump database harian ke folder `./backups` |

Saat start, migrasi database berjalan otomatis dan akun admin dibuat.

### Langkah 5: Pastikan berjalan

```bash
docker compose ps
```

Ketiga container harus berstatus `Up`, dan `db` berstatus `(healthy)`.

```bash
curl http://127.0.0.1:8000/api/health
# {"status":"ok","database":"OK"}

docker compose logs app | grep -i admin
# ... Akun admin 'admin' dibuat. Hapus ADMIN_PASSWORD dari .env.
```

### Langkah 6: Buka dan login

1. Buka **http://127.0.0.1:8000** di browser.
2. Isi **Username** dengan nilai `ADMIN_USERNAME` (mis. `admin`).
3. Isi **Password** dengan nilai `ADMIN_PASSWORD` dari Langkah 3.
4. Klik **Masuk**. Anda akan diarahkan ke halaman **Data sumur**.

Sesi login berlaku 8 jam. Setelah 5 kali salah password, login dikunci 15 menit.

### Langkah 7: Hapus password dari `.env`

Setelah login berhasil, akun sudah tersimpan di database dalam bentuk hash. Hapus baris
`ADMIN_PASSWORD=...` dari `.env`, lalu jalankan:

```bash
docker compose up -d
```

Simpan password tersebut di pengelola password Anda.

### Langkah 8 (opsional): Coba dengan data contoh

Data contoh **sintetis** (bukan data client): 15 sumur dengan data aktual, 2 sumur baru tanpa
data aktual, dan 2 file roadmap.

```bash
make sample-docker
# file dibuat di data/sample/*.xlsx
```

Tanpa `make`:

```bash
mkdir -p data
docker compose run --rm --no-deps -v "$PWD/scripts:/scripts:ro" -v "$PWD/data:/out" \
  --user "$(id -u):$(id -g)" app python /scripts/make_sample_data.py --out /out/sample
```

Di Windows (PowerShell), jalankan perintah ini dari WSL, atau ganti `$PWD` dengan path folder
lengkap dan hapus opsi `--user`.

Lalu coba alurnya di web:

1. **Data sumur → Impor file Excel**: tarik semua file `W01…W15_*_wellplan.xlsx`. Untuk file
   `*_roadmap.xlsx`, isi dulu **Nama sumur** (mis. `W01`) karena file roadmap tidak memuat nama sumur.
2. **Model → Latih model**: proses berjalan di latar belakang sekitar 20 detik. Statusnya berubah
   menjadi `selesai` dan `aktif`. Klik **Laporan** untuk melihat akurasi per section dan tipe sumur.
3. **Data sumur → Prediksi sumur baru**: tarik `W16_..._baru_wellplan.xlsx`. Dashboard terbuka otomatis.
4. **Dashboard**: pilih sumur. Tiga grafik tampil (Hookload, Torque, Selisih). Arahkan kursor
   untuk melihat garis penuntun di ketiga grafik. Atur ambang untuk penandaan interval.
5. **Ekspor Excel** di dashboard: file `.xlsx` berisi data perbandingan, prediksi, dan grafik.

---

## B. Perintah sehari-hari

| Tujuan | Perintah | Pintasan |
|---|---|---|
| Jalankan / perbarui setelah kode berubah | `docker compose up -d --build` | `make up` |
| Lihat log aplikasi | `docker compose logs -f app` | `make logs` |
| Status container | `docker compose ps` | |
| Hentikan (data tetap aman) | `docker compose down` | `make down` |
| Ganti password admin | `docker compose exec app python -m app.cli set-admin-password` | `make password` |
| Masuk ke database | `docker compose exec db psql -U tdml -d tdml` | |
| Backup manual | | `make backup` |

> **Jangan jalankan `docker compose down -v`** kecuali memang ingin mengosongkan semuanya. Opsi
> `-v` menghapus volume: database, file unggahan, dan model.

### Lupa / ganti password

```bash
docker compose exec app python -m app.cli set-admin-password
```

- Masukkan password baru dua kali (minimal 12 karakter). Bila dikosongkan, password acak dibuat
  dan ditampilkan.
- Perintah ini juga **membuka kunci** login yang terkunci karena terlalu banyak percobaan salah.
- Untuk mengganti username sekaligus, tambahkan `--username nama_baru`. Akun tetap satu.

### Mulai ulang dari nol (hapus semua data)

```bash
docker compose down -v      # HAPUS database, unggahan, model
# isi lagi ADMIN_PASSWORD di .env
docker compose up -d --build
```

---

## C. Masalah umum

| Gejala | Penyebab / solusi |
|---|---|
| Login "berhasil" tapi kembali ke halaman login | `COOKIE_SECURE=true` saat dibuka lewat `http://`. Ubah ke `false` di laptop, lalu `docker compose up -d`. |
| "Username atau password salah" padahal `.env` benar | Akun sudah dibuat sebelumnya dengan password lain (`.env` hanya dipakai saat pertama kali). Jalankan `make password`. |
| "Terlalu banyak percobaan salah" | Tunggu 15 menit, atau jalankan `make password`. |
| Log: "Belum ada akun admin" | `ADMIN_USERNAME`/`ADMIN_PASSWORD` kosong saat start pertama. Isi lalu `docker compose up -d`, atau buat lewat `make password`. |
| `port is already allocated` (8000) | Port 8000 dipakai program lain. Hentikan program itu, atau ganti `127.0.0.1:8000:8000` menjadi mis. `127.0.0.1:8080:8000` di `docker-compose.yml`, lalu buka http://127.0.0.1:8080. |
| Tidak bisa dibuka dari komputer lain di jaringan | Disengaja: port hanya dibuka ke `127.0.0.1`. Akses dari luar lewat nginx + HTTPS (bagian D). |
| Aplikasi menolak start: "SECRET_KEY production harus acak…" | `SECRET_KEY` kurang dari 32 karakter atau masih nilai contoh. |
| File gagal diimpor | Lihat alasannya di **Data sumur → Riwayat impor** (klik baris). Pola nama sheet/kolom bisa disesuaikan di `backend/app/parsers/column_map.py`. |

---

## D. Setup di server (production, dengan domain + HTTPS)

Kebutuhan: VPS Ubuntu 24.04 (2 vCPU, 4 GB RAM, 40 GB disk), domain atau subdomain dengan
**DNS A record** yang mengarah ke IP server, dan akses SSH.

```bash
# 1. Di server: ambil kode
git clone <url-repo> td-ml && cd td-ml

# 2. Pasang semuanya: paket, firewall (22/80/443), Docker, nginx, sertifikat HTTPS, .env dasar
DOMAIN=td.contoh.com EMAIL=admin@contoh.com bash deploy/setup_server.sh
#    - diminta membuat username/password BASIC AUTH sementara (lapisan nginx, bukan login aplikasi)
#    - .env dibuat dengan POSTGRES_PASSWORD dan SECRET_KEY acak

# 3. Isi akun admin aplikasi
nano .env        # isi ADMIN_USERNAME dan ADMIN_PASSWORD; pastikan COOKIE_SECURE=true

# 4. Jalankan
docker compose up -d --build
```

5. Buka **`https://td.contoh.com`**. Browser pertama-tama meminta basic auth sementara dari langkah 2,
   lalu halaman login aplikasi tampil. Login dengan `ADMIN_USERNAME` / `ADMIN_PASSWORD`.
6. Setelah login aplikasi berfungsi, **cabut basic auth sementara** supaya tidak login dua kali.
   Hapus dua baris `auth_basic` di `/etc/nginx/sites-available/td-ml`, lalu jalankan
   `sudo nginx -t && sudo systemctl reload nginx`.
7. **Hapus `ADMIN_PASSWORD`** dari `.env`, lalu jalankan `docker compose up -d`.
8. Memperbarui aplikasi di kemudian hari: `git pull && docker compose up -d --build`.

Aturan keamanan: jangan unggah file client ke server sebelum HTTPS dan login aplikasi berjalan.
Saat serah terima, ganti password dengan `make password` dan serahkan lewat jalur aman (bukan
chat). Detail backup, pemulihan, dan serah terima ada di `docs/panduan.md`.

---

## E. Pengembangan (opsional, tanpa Docker untuk app)

```bash
uv venv .venv -p 3.12 && uv pip install -p .venv/bin/python -r backend/requirements-dev.txt
make test          # 32 tes, memakai SQLite sementara
make lint          # ruff
make sample        # data sintetis via Python lokal
(cd backend && ../.venv/bin/alembic upgrade head)   # buat tabel (default SQLite backend/dev.db, atau set DATABASE_URL)
make dev-api       # API di :8000
make dev-web       # Vite dev server, /api diteruskan ke :8000
```

## Struktur

```
backend/app/        api/ core/ db/ parsers/ services/ main.py cli.py
backend/alembic/    migrasi database
backend/tests/      tes + fixtures sintetis
web/                React + Vite + Plotly
scripts/            audit_files.py, anonymize_files.py, make_sample_data.py
deploy/             konfigurasi nginx host + skrip pemasangan server
docs/               keputusan.md, panduan.md, catatan perubahan lingkup login
```
