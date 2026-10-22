# Pindah server (lewat FTP, bukan GitHub)

Tujuan: setelah folder proyek dipindah dan Docker dijalankan, server baru berisi **semua** data,
file, model, akun, dan tampilan yang sama dengan server lama.

## Yang perlu diketahui

Data sistem tersimpan di dua tempat:

| Tempat | Isi | Ikut terbawa FTP? |
|---|---|---|
| Folder proyek | kode, `.env`, `data/` (inbox, processed, rejected), `backups/`, `Training/` | Ya |
| Docker volume `pgdata`, `uploads`, `models` | database (sumur, akun, prediksi, dataset), file unggahan, model ML | **Tidak**: harus diekspor dulu |

`make migrasi-ekspor` mengemas ketiga volume ke folder `migrasi/` di dalam proyek, sehingga ikut
terbawa saat folder proyek dipindah. `make migrasi-impor` mengembalikannya di server baru.

## Langkah

### A. Server lama

```bash
cd <folder proyek>
make migrasi-ekspor          # menghentikan app, lalu membuat migrasi/
```

Hasil di `migrasi/`: `db.dump`, `uploads.tar.gz`, `models.tar.gz`, `MANIFEST.txt` (jumlah baris per
tabel), `SHA256SUMS`. App sengaja dibiarkan berhenti agar tidak ada data baru yang tertinggal.
Jangan pakai sistem lama lagi setelah langkah ini.

### B. Transfer FTP

Pindahkan **seluruh folder proyek**, terutama:

- `.env`: file tersembunyi, sering tidak tampil di klien FTP. Aktifkan "show hidden files".
  Wajib sama persis (password database, `SECRET_KEY`).
- `migrasi/`, `data/`, `backups/`, `Training/`
- Tidak perlu: `.venv/`, `web/node_modules/`, `.ruff_cache/` (dibuat ulang saat build).

Pakai mode **BINARY** (bukan ASCII/auto), jika tidak file `.dump`/`.tar.gz` rusak. Kerusakan akan
tertangkap oleh pemeriksaan checksum di langkah C.

### C. Server baru (Ubuntu 24.04)

Server baru harus punya akses internet (build image mengunduh paket npm dan pip).

**Server baru, belum ada nginx/Docker:**

```bash
cd <folder proyek>
DOMAIN=<domain> EMAIL=<email> bash deploy/setup_server.sh
```

Skrip itu memasang Docker, nginx, HTTPS, lalu otomatis menjalankan impor karena `migrasi/` ada.
Arahkan DNS domain ke IP server baru **sebelum** menjalankannya (certbot perlu domain aktif).

**Docker dan nginx sudah terpasang:**

```bash
cd <folder proyek>
make migrasi-impor           # atau: bash scripts/migrasi_impor.sh
```

Impor akan: cek checksum, build image, restore database, isi volume, perbaiki izin `data/`,
menyalakan semua layanan, lalu menampilkan jumlah baris per tabel. **Bandingkan dengan
`migrasi/MANIFEST.txt`**: angkanya harus sama.

Pengaman: impor menolak jalan bila database server baru sudah berisi tabel (mis. pernah
`make up` sebelumnya). Bila server baru memang kosong/uji coba saja, `docker compose down -v`
(menghapus database server baru) lalu ulangi.

### D. Cek

1. Login admin dan guest: akun dan password sama dengan server lama.
2. Menu Models: model aktif, riwayat, laporan, status blind test sama.
3. Dashboard salah satu sumur, unduh Excel dan PDF.
4. Data Quality dan daftar sumur Monitoring per user.

Setelah semua cocok, hapus `migrasi/` di server baru (berisi data client). Server lama biarkan
berhenti beberapa hari sebagai cadangan, lalu matikan.

## Catatan

- `COOKIE_SECURE=true` di `.env`: login hanya berjalan lewat HTTPS. Untuk uji lewat IP/HTTP
  sementara, ubah ke `false`, lalu kembalikan ke `true`.
- Backup harian tetap berjalan di server baru (`backups/`).
- Diuji 21 Okt 2026 pada salinan terpisah: 19 tabel jumlah barisnya sama, semua file model,
  dataset, dan unggahan yang dirujuk database ada di disk, health check OK.
