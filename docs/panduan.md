# Panduan sistem Kalibrasi Torque & Drag ML

Bagian A untuk pengguna (engineer), bagian B untuk operator server.

## Alur kerja singkat

```
1. Taruh file sumur di data/inbox      ->  2. Data sumur: Pindai folder
3. Kualitas data: tinjau status C       ->  4. Model: Bekukan dataset + Latih model
5. Model: periksa laporan, Blind test    ->  6. Dashboard: lihat 3 grafik, batas aman, ekspor
7. Sumur baru: unggah WellPlan -> prediksi  ->  8. Evaluasi: setelah data aktualnya masuk
```

---

## A. Panduan pengguna

### 1. Masuk
Buka link aplikasi (laptop: http://127.0.0.1:8000). Isi username dan password admin.
Sesi berlaku 8 jam. Setelah 5 kali salah password, login terkunci 15 menit. Tombol mata di kolom
password menampilkan/menyembunyikan password.

### 2. Menyiapkan file sumur
Satu file Excel = satu section sumur. Dua format diterima:

| Format | Ciri | Data rencana WellPlan | Data aktual |
|---|---|---|---|
| **A. Roadmap** (`.xlsx`) | sheet `Drag`, `Torque`, `T&D Actual Reading` | blok per friction factor (mis. 0,1/0,3/0,5 atau 0,3/0,4/0,5) | `T&D Actual Reading` (Klbs, Lbs-ft) |
| **B. Laporan WellPlan** (`.xlsm`) | sheet `Summary`, `Tripping Load Analysis`, … | FF 0,2–0,5 tiap 100 ft, torque on bottom dari `Rotary Drill Buckling Outputs` (Base FF), survey, BHA, mud weight | `Drilling Data` (+ `Tripping  Data`) |

Susun folder seperti folder `Training` client:
```
data/inbox/
  Horizontal/                 <- tipe sumur (J, S, Horizontal)
    MINAS 2193 (2D-96A) HW/   <- nama folder = kode sumur
      P_MINA25_0017HW_BHA1A_17.5in_TnD.xlsm   <- section dibaca dari nama file
      P_MINA25_0017HW_BHA2A_12.25in_TnD.xlsm
```
Tanpa folder tipe (`data/inbox/<sumur>/<file>`) juga bisa; tipe sumur lalu ditebak dari survey
(format B) atau diisi manual. Section harus ada di nama file (`8.5in`, `8.50in`, `12.25 HS`,
`22inHS`); bila tidak, isi kolom Section saat unggah manual.

Cara cepat: `make inbox-training` menyalin seluruh folder `Training/` ke `data/inbox/`.

### 3. Data sumur → Impor massal dari folder
1. Panel menunjukkan jumlah file yang menunggu di inbox.
2. Klik **Pindai folder**. 94 file butuh ±30 detik.
3. Hasil **per file**: `diterima`, `diterima dengan peringatan`, `duplikat` (isi sama dengan file
   yang sudah ada, tidak diimpor dua kali), `dilewati` (baru diubah < 1 menit), `ditolak` + alasan.
   File yang sama tapi isinya berubah → diimpor sebagai **versi baru** dan menggantikan versi lama.
4. Hasil **per sumur-section**: status kualitas A/B/C dan alasannya.
5. File dipindah ke `data/processed/` (diterima) atau `data/rejected/` (ditolak, beserta file
   `.alasan.txt`).

Unggah satu-satu tetap bisa lewat **Unggah file Excel** di halaman yang sama.

### 4. Kualitas data
Setiap sumur-section mendapat status:

| Status | Arti | Masuk training? |
|---|---|---|
| **A** Layak | lolos semua pemeriksaan | ya |
| **B** Layak + peringatan | lolos pemeriksaan wajib, ada peringatan statistik | ya, ditandai |
| **C** Ditahan | gagal pemeriksaan kritis | tidak, menunggu tinjauan |
| **X** Dikecualikan | dikecualikan engineer lewat tinjauan | tidak |

**Pemeriksaan kritis:** rencana operasi inti ada, satuan wajar (rasio aktual/WellPlan hookload
0,33–3; torsi tidak beda faktor ~1000), kedalaman tanpa duplikat bertentangan, nilai fisik wajar,
urutan slack off ≤ rotating ≤ pick up, minimal **8 titik aktual pick up di dalam rentang WellPlan**,
section & tipe diketahui, bukan duplikat sumur lain.
**Peringatan statistik:** rasio aktual/WellPlan menyimpang dari sumur sekelas (MAD), lompatan tak
wajar, nilai berulang (salin tempel), titik jauh lebih sedikit dari sumur sekelas, rasio torsi jauh
dari 1, urutan kedalaman di file tidak naik.

Klik baris untuk melihat semua pemeriksaan, lalu catat keputusan tinjauan:
- **Terima**: status C menjadi B (dipakai training, dengan catatan).
- **Kecualikan**: tidak dipakai training (X).
- **Perbaiki**: tetap C, minta file baru ke client.

Alasan wajib diisi; nama peninjau dan waktu tercatat. **Unduh laporan kualitas (.xlsx)** untuk
dikirim ke client.

### 5. Model
**a. Bekukan dataset.** Dataset = semua titik aktual sumur berstatus A/B, dipasangkan dengan nilai
WellPlan di kedalaman yang sama, plus fitur (kedalaman, WellPlan FF 0,3 & 0,5, kemiringan FF,
rotating weight, section, tipe, format file, dan grup fitur tambahan). Pembekuan menyimpan snapshot
+ hash. Dataset pertama juga **mengunci ~20% sumur sebagai blind test** (proporsional per tipe);
sumur ini tidak pernah dipakai melatih atau memilih model.

**b. Latih model.** Pilih dataset (bawaan: terbaru) dan algoritma ("Bandingkan semua" =
Ridge, XGBoost, Random Forest, SVR; centang MLP bila perlu). Proses ±3–5 menit, berisi:
1. Uji manfaat grup fitur (survey, casing shoe, BHA & lumpur, KOP & tipe interval, block weight):
   grup hanya dipakai bila menurunkan error ≥ 1%.
2. Semua kandidat × target langsung/selisih terhadap WellPlan, dinilai dengan **validasi silang
   per kelompok sumur** (satu sumur tidak pernah ada di data latih dan uji sekaligus).
3. Model tunggal vs model terpisah per kombinasi section × tipe (bila ≥ 10 sumur).
4. Kurva belajar, analisis kesalahan, SHAP, pita ketidakpastian 10–90%.
5. Dibandingkan dengan model aktif: **lebih buruk → ditahan** (tidak aktif). Bisa diaktifkan manual.

**c. Baca laporan** (klik *Laporan*):
- Tabel utama: RMSE WellPlan vs ML per operasi, persen titik ketika ML lebih dekat ke aktual.
- Tab: Section × tipe, Section, Tipe, Kedalaman, Per sumur, Titik terburuk, Algoritma,
  Tunggal vs kombinasi, Kurva belajar, SHAP.
- Baris kuning = kombinasi dengan < 3 sumur (data sedikit).
- **Laporan (.xlsx)** dan **Ringkasan PDF** untuk client.

**d. Blind test.** Setelah model final dipilih, klik **Jalankan blind test** (sekali saja per model;
hasil dicatat apa adanya dan tidak bisa diulang).

### 6. Dashboard
- Filter **Section, Tipe, Kualitas**, pilih **Sumur**, **Satuan** (imperial/SI), dan **Model**
  (aktif atau versi lain).
- **Tiga panel ditumpuk ke bawah**: Hookload, Torque, Selisih. Warna: WellPlan biru, ML oranye,
  Aktual titik hijau. Garis penuh = pick up / torque off bottom, putus-putus = slack off /
  torque on bottom, titik-titik = rotating.
- **Pita ketidakpastian ML** (arsiran oranye, 10–90%) bisa dimatikan.
- **Zoom**: tarik kotak; klik dua kali = kembali; *Reset zoom* untuk semua panel. Dengan
  "Samakan kedalaman saat zoom", zoom kedalaman berlaku di ketiga panel.
- **Selisih** = A − B: kanan (+) A lebih tinggi, kiri (−) A lebih rendah. Pilih target dan mode
  absolut/persen. Interval |selisih| > ambang diarsir kuning di ketiga panel.
- Sumur latih memakai prediksi **out-of-fold** (model yang tidak pernah melihat sumur itu).
- **Batas aman**: tambahkan batas (mis. pick up maks, torque on bottom maks = batas top drive,
  slack off min) untuk sumur ini atau seluruh section. Tabel menunjukkan kedalaman pertama saat
  ML, batas pita ML, dan WellPlan menyentuh batas; garis merah di grafik dan arsiran merah di
  bawah kedalaman itu.
- **Ekspor Excel**: sheet `Info`, `Drag`, `Torque`, `T&D Actual Reading` (struktur seperti file
  roadmap + kolom ML, pita, selisih), `Selisih`, `Grafik` (3 grafik), `Batas aman`, `Metrik`.
- **PDF**: ringkasan 2 halaman (status kualitas, versi model & dataset, metrik, batas aman,
  tiga grafik).

### 7. Prediksi sumur baru
Data sumur → **Prediksi sumur baru** → tarik file WellPlan/roadmap sumur baru. Sistem mengimpor,
memprediksi dengan model aktif, lalu membuka dashboard. Peringatan muncul bila section/tipe jarang
di data latih, kedalaman di luar rentang latih, atau survey tidak ada.

### 8. Evaluasi
Saat file berisi data aktual sumur yang sudah diprediksi diimpor kemudian, prediksi lama otomatis
dibandingkan dengan aktual dan WellPlan. Hasilnya di menu **Evaluasi**.

---

## B. Operasional (Docker)

```bash
make up                       # jalankan / perbarui (migrasi otomatis)
make logs                     # log aplikasi
make down                     # hentikan (data aman di volume)
make password                 # ganti password admin + buka kunci login
make inbox-training           # salin Training/ ke data/inbox
make audit                    # laporan audit file -> data/audit/
make backup                   # dump database manual -> backups/
docker compose exec db psql -U tdml -d tdml
```
**Jangan** `docker compose down -v` di server (menghapus database, unggahan, dan model).

### Folder data
| Folder | Isi | Di Git? |
|---|---|---|
| `Training/` | data sumur asli dari client | tidak |
| `data/inbox/` | file menunggu dipindai | tidak |
| `data/processed/`, `data/rejected/` | file setelah dipindai | tidak |
| `data/audit/`, `data/reports/` | laporan berisi nama sumur | tidak |
| volume `uploads`, `models` | salinan file terimpor, model `.joblib`, dataset beku | tidak |

Folder `data/` harus bisa ditulis uid 1000 (user di dalam container) dan tertutup untuk pengguna
lain: `sudo chown -R 1000:1000 data && chmod 750 data`.

### Pemasangan server baru
`DOMAIN=td.domain.com EMAIL=... bash deploy/setup_server.sh`, isi `ADMIN_*` dan
`COOKIE_SECURE=true` di `.env`, `make up`, login, hapus `ADMIN_PASSWORD`, cabut basic auth nginx.
Salin data ke `data/inbox/` server **setelah** HTTPS dan login berjalan.

### Pelatihan ulang saat data baru datang
1. Taruh file di `data/inbox/`, Pindai folder.
2. Tinjau status C di Kualitas data.
3. Model → **Bekukan dataset baru** (blind test lama tetap terkunci).
4. **Latih model** dengan dataset baru. Bila lebih buruk dari model aktif, model ditahan.

### Backup dan pemulihan
- Service `backup`: dump harian di `./backups` (7 hari).
- Salin juga volume `uploads` dan `models`:
  `docker run --rm -v td-ml_models:/m -v $PWD/backups:/b alpine tar czf /b/models.tgz -C /m .`
- Uji pulihkan sekali sebelum serah terima:
  ```bash
  docker compose exec -T db createdb -U tdml tdml_uji
  gunzip -c backups/last/tdml-*.sql.gz | docker compose exec -T db psql -q -U tdml -d tdml_uji
  docker compose exec -T db dropdb -U tdml tdml_uji
  ```

### Serah terima
1. `make password` → password baru, serahkan lewat jalur aman.
2. Pastikan `.env` tanpa `ADMIN_PASSWORD`.
3. Uji alur penuh di server: Pindai folder → Kualitas → Latih → Blind test → Dashboard → Ekspor/PDF.
4. Hapus salinan data client di laptop dalam 14 hari (Pasal 11 ayat 4).
