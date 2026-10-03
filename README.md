# Sistem Kalibrasi Torque & Drag ML (paket 6 minggu)

Aplikasi web untuk mengimpor file WellPlan + data aktual sumur (Excel), memeriksa kualitas data,
melatih dan membandingkan model kalibrasi (Ridge, XGBoost, Random Forest, SVR, MLP opsional),
menguji model pada sumur yang tidak pernah dilihat (validasi per sumur + blind test), memprediksi
sumur baru, dan menampilkan hasilnya dalam dashboard tiga grafik (Hookload, Torque, Selisih),
ekspor Excel, dan ringkasan PDF. Aplikasi memakai satu akun admin.

| Dokumen | Isi |
|---|---|
| `docs/panduan.md` | **Panduan pengguna** langkah demi langkah + panduan operasional (versi interaktif: menu **Panduan** di aplikasi) |
| `docs/ALUR_DAN_KODE.md` | **Alur sistem dan peta kode**: setiap alur → endpoint → fungsi → file/folder (untuk developer & client) |
| `docs/keputusan.md` | Keputusan dan asumsi (K-01 … K-30) |
| `TODO_Lanjutan_6_Minggu.md` | Rencana kerja paket 6 minggu dan status |
| `TOOLS_dan_Arsitektur_6_Minggu.md` | Tools dan arsitektur |
| `CLAUDE.md` | Konteks untuk Claude Code |

---

## Ringkasan cepat

| | Laptop (lokal) | Server (production) |
|---|---|---|
| **Link** | http://127.0.0.1:8401 | `https://<domain-anda>` |
| **Username** | nilai `ADMIN_USERNAME` di `.env` (bawaan `admin`) | sama |
| **Password** | nilai `ADMIN_PASSWORD` di `.env` saat aplikasi **pertama kali** dijalankan | sama, diganti saat serah terima |

> Tidak ada password bawaan. Akun dibuat sekali dari `.env` saat start pertama. Setelah itu mengubah
> `.env` tidak mengubah password. Ganti/lupa password: `make password`.

Format file yang diterima (hasil audit 94 file folder `Training/`):

| Format | Ekstensi | Sheet yang dibaca | Data aktual |
|---|---|---|---|
| **A. Roadmap** | `.xlsx` | `Drag`, `Torque` (blok per friction factor) | `T&D Actual Reading` |
| **B. Laporan WellPlan** | `.xlsm` (macro tidak dijalankan) | `Summary`, `Tripping Load Analysis`, `Off Bottom Torque analysis`, `Rotary Drill Buckling Outputs`, `Survey Outputs` | `Drilling Data`, `Tripping  Data` |

Satu file = satu section. Section dibaca dari nama file (`_8.5in`, `12.25 HS`, `22inHS`, …).
Selain dua format itu, pengguna bisa mengunduh **template** dari aplikasi (format A + sheet
`Info Sumur` berisi nama, section, tipe, block weight; `Survey` opsional), mengisinya, dan
mengunggahnya kembali.
Susunan folder: `<tipe J|S|Horizontal>/<nama sumur>/<file>`. Nama folder = kode sumur.

---

## A. Setup dari awal di laptop (Docker)

### 1. Perangkat
Pasang **Docker** (Docker Desktop di Windows/Mac, atau Docker Engine + plugin Compose di Linux)
dan **Git**. Python dan Node tidak perlu dipasang.

```bash
docker --version
docker compose version     # harus "Docker Compose version v2..."
```

### 2. Ambil kode
```bash
git clone <url-repo> td-ml
cd td-ml
```

### 3. Buat `.env`
```bash
cp .env.example .env
```
Isi:
```ini
POSTGRES_PASSWORD=<openssl rand -hex 16>
SECRET_KEY=<openssl rand -hex 32>      # minimal 32 karakter
COOKIE_SECURE=false                    # laptop (http) = false; server (https) = true
ADMIN_USERNAME=admin
ADMIN_PASSWORD=GantiDenganPasswordAnda123
```

### 4. Jalankan
```bash
make up            # = buat folder data/inbox, processed, rejected, backups + docker compose up -d --build
```
Build pertama 5–10 menit (pustaka ML, SHAP, PDF). Container yang berjalan:

| Container | Fungsi |
|---|---|
| `db` | PostgreSQL 16 (volume `pgdata`) |
| `app` | API + web + ML di `127.0.0.1:8401`; membaca folder `data/inbox` |
| `backup` | Dump database harian ke `./backups` |

Migrasi database berjalan otomatis saat start.

### 5. Cek
```bash
docker compose ps                              # app, db (healthy), backup
curl http://127.0.0.1:8401/api/health          # {"status":"ok","database":"OK"}
```

### 6. Login
Buka **http://127.0.0.1:8401**, masuk dengan `ADMIN_USERNAME` / `ADMIN_PASSWORD`. Lalu hapus baris
`ADMIN_PASSWORD` dari `.env` dan jalankan `docker compose up -d`.

### 7. Masukkan data sumur
**Data client (folder `Training/`):**
```bash
make inbox-training      # salin Training/<tipe>/<sumur>/* ke data/inbox (file asli tidak diubah)
```
**Atau data contoh sintetis (bukan data client):**
```bash
make inbox-sample
```
Lalu di web: **Data sumur → Pindai folder**. Lanjutkan sesuai `docs/panduan.md`
(Kualitas data → Model → Latih → Blind test → Dashboard → Ekspor).

> Aturan data (Pasal 11): data client hanya dipakai di laptop/server yang disepakati, tidak ke Git
> (`Training/`, `data/` ada di `.gitignore`), dan salinannya dihapus 14 hari setelah proyek selesai.

---

## B. Keluaran yang dihasilkan sistem

| Keluaran | Dari mana | Isi |
|---|---|---|
| Laporan audit file | `make audit` → `data/audit/laporan_audit.md` + CSV | Format, sheet, satuan, titik, matriks sumur × section × tipe, penyimpangan per file |
| Template isian | Data sumur → Impor file Excel / Prediksi sumur baru → Unduh template | `template_data_latih_TnD.xlsx` (rencana + aktual) dan `template_sumur_baru_TnD.xlsx` (rencana saja), dengan Petunjuk dan Contoh |
| Hasil prediksi sumur baru | Data sumur → Prediksi sumur baru → unggah template terisi | Tabel prediksi per operasi + tombol dashboard, Excel, PDF |
| Hasil pindai folder | Data sumur → Pindai folder | Per file (diterima / peringatan / duplikat / ditolak + alasan) dan per sumur-section (status A/B/C) |
| Laporan kualitas data | Kualitas data → Unduh (.xlsx) | Status A/B/C/X, skor, alasan, rasio aktual/WellPlan, riwayat tinjauan |
| Dataset beku | Model → Dataset → Unduh | Snapshot CSV + hash, daftar sumur, sumur blind test, sumur dikecualikan |
| Laporan model | Model → Laporan (.xlsx) / Ringkasan PDF | Metrik validasi silang & blind test per operasi, per section/tipe/kedalaman/sumur, perbandingan algoritma, uji fitur, kurva belajar, SHAP |
| Dashboard | Dashboard | 3 panel (Hookload, Torque, Selisih), pita ketidakpastian, batas aman, interval ditandai |
| Ekspor per sumur | Dashboard → Ekspor Excel / PDF | Sheet `Drag`, `Torque`, `T&D Actual Reading` + kolom ML & selisih + 3 grafik + batas aman; PDF 2 halaman |
| Evaluasi prediksi | Evaluasi | Prediksi sumur baru vs data aktualnya (otomatis setelah data aktual diimpor) |

Hasil pada data Training (Okt 2026) dirangkum di `data/reports/` (tidak di Git, berisi nama sumur).

---

## C. Perintah sehari-hari

| Tujuan | Perintah |
|---|---|
| Jalankan / perbarui | `make up` |
| Log aplikasi | `make logs` |
| Hentikan (data aman) | `make down` |
| Ganti password admin (juga membuka kunci login) | `make password` |
| Salin data Training ke inbox | `make inbox-training` |
| Data contoh sintetis ke inbox | `make inbox-sample` |
| Laporan audit file Training | `make audit` |
| Backup manual | `make backup` |
| Masuk database | `docker compose exec db psql -U tdml -d tdml` |

> **Jangan `docker compose down -v`** kecuali ingin menghapus semua data (database, unggahan, model).

---

## D. Masalah umum

| Gejala | Solusi |
|---|---|
| Login kembali ke halaman login | `COOKIE_SECURE=false` untuk http lokal, lalu `docker compose up -d` |
| Password `.env` tidak diterima | Akun sudah dibuat sebelumnya → `make password` |
| "Terlalu banyak percobaan salah" | Tunggu 15 menit atau `make password` |
| Tombol "Pindai folder" nonaktif | `data/inbox` kosong; jalankan `make inbox-training` |
| File di inbox "dilewati" | File baru diubah < 1 menit; tunggu lalu pindai lagi |
| Pindai gagal "Permission denied" | Folder `data/` harus bisa ditulis uid 1000: `sudo chown -R 1000:1000 data` |
| Port 8401 dipakai | Ubah port kiri `127.0.0.1:8401:8401` (mis. `127.0.0.1:8402:8401`) di `docker-compose.yml` |

---

## E. Server (production)

**Subdomain `dev-ml-kalibrasi-torque-rag.lokatali.my.id`:** konfigurasi nginx siap pakai dan
langkah pemasangan manual ada di `deploy/nginx/PASANG_SUBDOMAIN.md`
(`dev-ml-kalibrasi-torque-rag.lokatali.my.id.awal.conf` → certbot →
`dev-ml-kalibrasi-torque-rag.lokatali.my.id.conf`). Orang lain mengakses lewat
`https://dev-ml-kalibrasi-torque-rag.lokatali.my.id`, sedangkan di mesin itu sendiri tetap bisa
`http://localhost:8401`. Di `.env` server pakai `COOKIE_SECURE=true`.

Cara otomatis (domain lain):

```bash
git clone <url-repo> td-ml && cd td-ml
DOMAIN=td.contoh.com EMAIL=admin@contoh.com bash deploy/setup_server.sh   # paket, firewall, Docker, nginx, HTTPS, .env
nano .env                                    # ADMIN_USERNAME, ADMIN_PASSWORD, COOKIE_SECURE=true
make up
sudo chown -R 1000:1000 data && chmod 750 data   # folder inbox hanya untuk user server dan container
```
Buka `https://td.contoh.com`, login, cabut basic auth sementara di nginx, hapus `ADMIN_PASSWORD`.
Data sumur disalin ke `data/inbox/` di server (mis. `scp -r Training/. server:td-ml/data/inbox/`)
**setelah** HTTPS dan login berjalan. Detail di `docs/panduan.md` bagian B.

---

## F. Pengembangan

```bash
uv venv .venv -p 3.12 && uv pip install -p .venv/bin/python -r backend/requirements-dev.txt
make test        # 48 tes (parser format A/B, kualitas, alur penuh, login, selisih)
make lint
cd web && npm ci && npm run build
```

Struktur: `backend/app/{api,core,db,parsers,services}`, `backend/alembic`, `backend/tests`,
`web/` (React + Plotly), `scripts/` (audit, anonimisasi, data sintetis), `deploy/`, `docs/`.
