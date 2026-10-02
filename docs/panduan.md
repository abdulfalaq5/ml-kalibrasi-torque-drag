# Panduan singkat

## A. Penggunaan (untuk engineer)

### 1. Masuk
Buka domain aplikasi, masukkan username dan password admin. Sesi berlaku 8 jam. Setelah 5 kali
salah, login terkunci 15 menit.

### 2. Impor data (menu **Data sumur**)
1. Tarik file `.xlsx` / `.xlsm` ke kotak **Impor file Excel** (bisa banyak sekaligus). Macro tidak
   pernah dijalankan.
2. File yang tidak memuat nama sumur/ukuran lubang (mis. roadmap Drag/Torque) → isi **Nama sumur**
   dan **Section** sebelum menarik file.
3. Hasil tiap file: `ok`, `peringatan` (terimpor, ada catatan), atau `gagal` (tidak terimpor; alasan
   tampil di bawah nama file dan di **Riwayat impor** — klik baris untuk detail).
4. Periksa kolom **Section** dan **Tipe** di daftar sumur. Bila salah, pilih nilai yang benar;
   sumbernya berubah menjadi `manual` dan tidak ditimpa impor berikutnya.
5. **Matriks section × tipe** menandai kombinasi dengan < 3 sumur ber-data aktual (⚠).

Format yang dikenali (lihat `backend/app/parsers/column_map.py`):

| Jenis | Sheet | Isi |
|---|---|---|
| Laporan WellPlan | Summary | Well Name, Hole Size, Casing Shoe |
| | Tripping Load Analysis | MD + Pick Up / Slack Off per FF + Rotating |
| | Off Bottom Torque | MD + Off/On Bottom Torque per FF |
| | Survey Outputs | MD, Inc, Azi, TVD, DLS |
| | BHA | komponen + OD (bit = ukuran lubang) |
| Roadmap | Drag, Torque | sama seperti di atas |
| Data aktual | T&D Actual Reading | Depth + Pick Up, Slack Off, Rotating Weight, Torque Off/On Bottom |
| | Drilling Data | Depth + Torque (on bottom) |
| | Tripping Data | Depth + Hookload + Direction (POOH/RIH) |

Satuan dibaca dari header dalam kurung, mis. `Pick Up FF 0.30 (kip)`. Satuan tidak dikenal →
kolom ditolak dengan pesan error.

### 3. Latih model (menu **Model**)
1. Klik **Latih model** (pilihan algoritma: terbaik per operasi / XGBoost / Ridge). Proses berjalan
   di latar belakang; status diperbarui otomatis.
2. **Laporan evaluasi**: RMSE/MAPE/R² WellPlan vs ML per operasi, per section, per tipe,
   section × tipe, dan per sumur. Baris kuning = data sedikit atau ML lebih buruk dari WellPlan.
   Semua angka adalah hasil validasi leave-one-well-out (sumur dinilai oleh model yang tidak
   melihatnya).
3. **Unduh laporan (.xlsx)** untuk dikirim ke client. **Unduh dataset (CSV)** untuk pemeriksaan
   manual (satuan SI).
4. Model baru otomatis aktif; model lama bisa diaktifkan kembali.

### 4. Prediksi sumur baru
Di **Data sumur → Prediksi sumur baru**, tarik satu laporan WellPlan. Sistem mengimpor, memprediksi
dengan model aktif, lalu membuka dashboard. Peringatan muncul bila section/tipe jarang di data latih.

### 5. Dashboard
- Filter **Section**, **Tipe sumur**, pilih **Sumur**, dan **Satuan** (imperial / SI).
- **Hookload** dan **Torque**: WellPlan (biru), ML (oranye), Aktual (titik hijau). Kotak centang
  menyalakan/mematikan operasi; "Kurva FF" menampilkan skenario FF lain.
- **Selisih**: pilih target dan mode absolut/persen. Konvensi **A − B: kanan (+) = A lebih tinggi,
  kiri (−) = A lebih rendah**.
  - WellPlan − Aktual dan ML − Aktual: titik, hanya di kedalaman yang punya data aktual.
  - ML − WellPlan: kurva, koreksi yang diberikan ML.
- **Penandaan interval**: pilih seri dan ambang |selisih|; interval yang melewati ambang diarsir
  di ketiga grafik dan didaftar di bawah.
- Zoom/geser kedalaman berlaku untuk ketiga grafik. Kursor memunculkan garis penuntun di ketiga
  grafik dan pembacaan nilai di bawahnya.
- Sumur latih memakai prediksi **out-of-fold**; sumur tanpa data aktual hanya menampilkan
  ML − WellPlan.
- **Ekspor Excel**: sheet Info, Perbandingan (kedalaman aktual + selisih), Prediksi ML (grid
  WellPlan), Grafik (Hookload, Torque, Selisih untuk target terpilih), Metrik.

## B. Operasional (Docker)

```bash
docker compose up -d --build                    # deploy / perbarui
docker compose logs -f app                      # log
docker compose exec db psql -U tdml -d tdml     # periksa database
docker compose exec app alembic upgrade head    # migrasi manual (otomatis saat start)
docker compose exec app python -m app.cli set-admin-password   # ganti password admin
docker compose down                             # hentikan (data aman di volume)
```

**Jangan** `docker compose down -v` di server: menghapus database dan file.

### Pemasangan server baru
`DOMAIN=td.domain.com EMAIL=... bash deploy/setup_server.sh` — paket, firewall, Docker, nginx,
sertifikat, `.env` (password DB dan SECRET_KEY acak). Lalu isi `ADMIN_USERNAME` /
`ADMIN_PASSWORD` di `.env`, `docker compose up -d --build`, login, **hapus `ADMIN_PASSWORD`** dari
`.env`, dan setelah login lolos uji hapus baris `auth_basic` di nginx.

### Memperbarui aplikasi
```bash
git pull && docker compose up -d --build
```

### Backup dan pemulihan
- Service `backup` membuat dump harian di `./backups` (7 hari).
- Salin `uploads` dan `models` berkala:
  `docker run --rm -v td-ml_uploads:/u -v $PWD/backups:/b alpine tar czf /b/uploads.tgz -C /u .`
- Uji pulihkan (sekali sebelum serah terima) ke database kosong:
  ```bash
  gunzip -c backups/last/tdml-latest.sql.gz | docker compose exec -T db psql -U tdml -d tdml
  ```
  (sesuaikan nama file dengan isi folder `backups`). Backup manual: `make backup`.

### Serah terima
1. `docker compose exec app python -m app.cli set-admin-password` → password baru, serahkan lewat
   pengelola password / jalur aman (bukan chat).
2. Pastikan `.env` tidak memuat `ADMIN_PASSWORD`.
3. Uji alur penuh di server: login → impor → latih → prediksi → dashboard → ekspor.
