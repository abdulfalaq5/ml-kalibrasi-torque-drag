# TO-DO: Prototype Sistem Kalibrasi Torque & Drag ML (3 Minggu)

Dokumen kerja internal. Centang `[x]` saat selesai. Setiap hari ada baris **Selesai bila** sebagai patokan hasil.

> **Status pengerjaan (2 Okt 2026).** Semua bagian kode sudah dibuat dan diuji **di laptop dengan
> data sintetis** (`make sample`; 15 sumur + 2 sumur baru). Tes: 32 lulus (`make test`). Stack
> Docker Compose jalan lokal; alur login → impor → latih → prediksi → dashboard → ekspor, backup
> dan uji pulihkan sudah dicoba. **Belum**: semua yang butuh server/domain, data client, narasumber,
> atau client (Tahap 0, deploy, sesi narasumber, impor 15 sumur asli, demo, serah terima). Parser
> memakai pola nama sheet/kolom yang masih **asumsi** (docs/keputusan.md K-17): sesuaikan
> `backend/app/parsers/column_map.py` setelah audit file asli.

## Gambaran langkah (10 langkah)

1. **Persiapan**: kesepakatan data, persetujuan penggunaan AI, server dan domain.
2. **Fondasi dan keamanan**: repo, Docker Compose, deploy kosong ke domain di hari pertama, login satu akun admin di hari kedua.
3. **Audit data**: periksa 15 file Excel, buat matriks sumur x section x tipe.
4. **Parser dan database**: baca WellPlan dan data aktual, simpan ke PostgreSQL.
5. **Dataset**: selaraskan kedalaman, konversi satuan, bentuk fitur.
6. **Model dan validasi**: baseline WellPlan, Ridge, XGBoost, validasi per kelompok sumur.
7. **Prediksi sumur baru**: unggah WellPlan lalu keluar prediksi.
8. **Dashboard**: tiga grafik (Hookload, Torque, Selisih), filter section dan tipe, penandaan interval.
9. **Ekspor Excel**: sheet perbandingan dan prediksi beserta grafik.
10. **Demo, revisi, serah terima**.

## Daftar fitur (disamakan dengan proposal dan perjanjian paket 3 minggu)

| No | Fitur (sesuai Lampiran A perjanjian) | Dikerjakan | Selesai bila |
|---|---|---|---|
| 1 | Impor Excel (WellPlan .xlsm/.xlsx + sheet data aktual) | Hari 3-5 | Dua file contoh dan 15 sumur terpilih ter-impor |
| 2 | Validasi dan pembersihan (satuan imperial, laporan kesalahan per file) | Hari 5 | Setiap file gagal punya alasan yang jelas di UI |
| 3 | Klasifikasi section dan tipe sumur (J, S, Horizontal) | Hari 5 | Semua sumur punya section dan tipe, bisa dikoreksi manual |
| 4 | Model kalibrasi ML (Ridge baseline dan XGBoost) | Hari 6-8 | Model tersimpan, dibandingkan dengan baseline WellPlan |
| 5 | Validasi model (sumur uji, RMSE/MAPE/R² per section dan tipe) | Hari 9-10 | Laporan akurasi per kombinasi, peringatan data sedikit |
| 6 | Prediksi sumur baru dari file WellPlan | Hari 11 | Unggah file lalu keluar prediksi 5 target per kedalaman |
| 7 | Dashboard tiga profil: **tampil 3 grafik (Hookload, Torque, Selisih)** + filter + penandaan interval | Hari 12 | Tiga grafik sejajar; Selisih menunjukkan arah (kanan/kiri) dan besarnya per kedalaman |
| 8 | Ekspor Excel (.xlsx, sheet perbandingan dan prediksi ML, grafik) | Hari 13 | File terbuka di Excel tanpa peringatan |
| **9** | **Login satu akun admin (tambahan)** | **Hari 2** | Tanpa login, semua endpoint ditolak |

> **Perhatian:** fitur 9 **belum ada** di proposal dan perjanjian. Di sana tertulis "tanpa login dan manajemen pengguna" (perjanjian Pasal 9 ayat 1 dan Lampiran A, proposal Bagian 7 dan daftar "tidak termasuk"). Catat perubahan ini secara tertulis (revisi dokumen atau addendum) supaya dokumen dan pekerjaan sama. Yang tetap tidak dikerjakan: banyak akun, role, dan manajemen pengguna.

**Tidak dikerjakan (sesuai perjanjian):** Random Forest, SVR, MLP, SHAP, penyimpanan versi model, pelatihan ulang otomatis, evaluasi pasca-sumur, ringkasan PDF, REST API untuk sistem lain, what-if, real-time, mobile.

---

## Aturan kerja (berlaku sepanjang proyek)

- **Data client dan AI (Pasal 11 perjanjian).** Sebelum data client dipakai di Claude Code atau alat AI lain, pastikan ada persetujuan tertulis client, atau data sudah dianonimkan (nama sumur, lapangan, koordinat diganti kode). Jangan menempelkan data asli ke chat.
- **Data tidak masuk Git.** Folder `data/`, `uploads/`, `models/`, `.env` masuk `.gitignore`.
- **Jangan unggah file client ke server sebelum login aktif dan HTTPS berjalan.** Sebelum itu, audit data dikerjakan di laptop saja.
- **Deploy sejak Hari 1** dan perbarui setiap hari, supaya masalah server ketahuan sejak awal.
- **Satu fitur = satu cabang Git.** Uji dengan dua file contoh dulu, baru 15 file.
- **Catat keputusan dan asumsi** di `docs/keputusan.md` (misalnya cara menentukan tipe sumur).
- **Jadwal tanpa cadangan.** Kalau terlambat lebih dari 1 hari, pakai *Daftar pemotongan* di bagian bawah.
- **Hasil model dicek manusia.** Jangan menerima grafik yang tampak bagus tanpa memeriksa angka dan satuannya.

---

## Tahap 0: Persiapan (sebelum Hari 1)

- [ ] Perjanjian ditandatangani, Lampiran B (bukti pembayaran) terpasang
- [ ] Tanggal Mulai disepakati dan tertulis di perjanjian
- [ ] Persetujuan tertulis penggunaan alat AI atas data client, atau kesepakatan anonimisasi
- [ ] File untuk 15 sumur terpilih diterima (target paling lambat hari kerja ke-2)
- [ ] Narasumber drilling engineer ditetapkan, beserta cara dan jam menghubunginya
- [ ] Username admin ditentukan, password dibuat acak dan panjang, disimpan di pengelola password (tidak lewat chat)
- [ ] Server: VPS Ubuntu LTS (2 vCPU, 4 GB RAM, 40 GB disk) disediakan client atau disepakati siapa yang membeli
- [ ] Domain atau subdomain disiapkan, DNS A record mengarah ke IP server
- [ ] Laptop: Docker Desktop, Git, Python 3.12, Node 20, VS Code, Claude Code terpasang
- [ ] Daftar sumur terpilih mencakup variasi section (17,5", 12,25", 8,5", 6,125") dan tipe (J, S, Horizontal)

**Selesai bila:** semua yang dibutuhkan ada sebelum kerja dimulai. Data belum datang = jadwal bergeser (Pasal 3 ayat 3).

---

## MINGGU 1: Audit data dan impor Excel

### Hari 1: Fondasi dan deploy kosong
- [x] Buat repo Git privat, struktur folder (lihat dokumen Tools), `.gitignore`, `.env.example`
- [x] Tulis `CLAUDE.md` di root repo: konteks proyek, konvensi kode, perintah umum, aturan data
- [x] `docker-compose.yml`: service `db` (PostgreSQL) dan `app` (FastAPI + halaman React kosong)
- [x] Endpoint `/api/health` yang mengecek koneksi database
- [x] Alembic terpasang, migrasi pertama berjalan di container
- [ ] Server: Docker Engine, firewall (22/80/443), nginx di host, certbot, basic auth **sementara** (dicabut di Hari 2 setelah login aktif)
- [ ] Deploy pertama ke server

**Selesai bila:** `https://domain` terbuka, minta username/password, dan menampilkan halaman kosong dengan status "database OK".

### Hari 2: Audit data
- [x] Skrip `scripts/audit_files.py`: daftar sheet tiap file, deteksi jenis file (laporan WellPlan atau roadmap), jumlah baris, satuan
- [ ] Tabel 15 sumur: section, tipe sumur, jumlah titik aktual, jumlah skenario friction factor, sheet yang ada atau hilang
- [ ] Catat semua penyimpangan format per file
- [ ] Sesi dengan narasumber: arti kolom dan satuan, definisi tipe sumur (J/S/Horizontal), ambang untuk penandaan interval
- [ ] Susun laporan audit 1-2 halaman

**Selesai bila:** laporan audit siap dikirim ke client dan menyebut file mana yang tidak sesuai format.

### Hari 2 (sore): Login satu akun admin
- [x] Tabel `admin_user` dan migrasi. Akun dibuat dari `ADMIN_USERNAME` dan `ADMIN_PASSWORD` di `.env` saat aplikasi pertama kali jalan. Password disimpan sebagai hash (argon2), bukan teks asli
- [x] Endpoint `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`
- [x] Sesi lewat cookie bertanda tangan: HttpOnly, Secure, SameSite=Lax, masa berlaku 8 jam
- [x] Semua endpoint `/api/*` wajib login (termasuk unduhan file dan ekspor), kecuali `/api/health` dan login
- [x] `/docs` dan `/openapi.json` dimatikan di production
- [x] Batas percobaan salah: 5 kali lalu kunci 15 menit (dicatat di database), ditambah `limit_req` di nginx pada endpoint login
- [x] Halaman login di web, halaman lain dialihkan ke login bila belum masuk, tombol keluar
- [x] Skrip ganti password: `docker compose exec app python -m app.cli set-admin-password`
- [x] Tes otomatis: setiap route selain health dan login mengembalikan 401 tanpa sesi
- [ ] Cabut basic auth sementara di nginx setelah login lolos tes (agar tidak login dua kali)
- [ ] Hapus `ADMIN_PASSWORD` dari `.env` setelah akun terbentuk

**Selesai bila:** membuka domain langsung menampilkan halaman login, API tanpa sesi ditolak, dan percobaan salah keenam terkunci.

### Hari 3-4: Parser Excel
- [x] Parser laporan WellPlan (.xlsm/.xlsx): Summary, Tripping Load Analysis, Off Bottom Torque, Survey Outputs, BHA
- [x] Parser roadmap (.xlsx): Drag, Torque
- [x] Parser data aktual: T&D Actual Reading, Drilling Data, Tripping Data
- [x] Baca file tanpa menjalankan macro (`keep_vba=False`), abaikan sheet grafik dan gambar
- [x] Konversi satuan imperial ke satuan baku internal, satuan asli disimpan
- [x] Format data seragam (long format): sumur, operasi, skenario/FF, kedalaman, nilai, satuan
- [x] Tes otomatis memakai dua file contoh

**Selesai bila:** dua file contoh terbaca dan angkanya sama dengan Excel aslinya pada 5 titik yang dicek manual.

### Hari 5: Database, impor, validasi
- [x] Skema tabel dan migrasi (wells, uploaded_files, survey, plan_results, actual_readings, validation_issues)
- [ ] Konfirmasi login sudah aktif sebelum file client pertama diunggah ke server
- [x] Endpoint unggah file dan proses impor
- [x] Validasi: kolom wajib, rentang nilai, kedalaman duplikat atau tidak naik, satuan tak dikenal
- [x] Laporan kesalahan per file, tersimpan di database dan tampil di UI
- [x] Klasifikasi otomatis section (dari ukuran lubang) dan tipe sumur (dari survey), bisa dikoreksi manual
- [x] Halaman UI: unggah, daftar sumur, status impor
- [ ] Impor 15 sumur terpilih

**Selesai bila (milestone Minggu 1):** laporan audit terkirim, 15 sumur ter-impor, dan sumur yang gagal punya alasan yang jelas.

---

## MINGGU 2: Model dan validasi

### Hari 6: Dataset
- [x] Interpolasi hasil WellPlan ke kedalaman titik aktual (kedalaman WellPlan dan aktual berbeda)
- [x] Fitur: nilai WellPlan pada FF 0,1/0,3/0,5, kedalaman, inklinasi, dogleg, section, tipe sumur, jenis operasi
- [x] Target: nilai aktual per operasi (pick up, slack off, rotating weight, torque off/on bottom)
- [x] Tentukan perlakuan data kosong dan outlier, catat di `docs/keputusan.md`
- [x] Ekspor dataset untuk pemeriksaan manual

**Selesai bila:** dataset punya baris yang jumlahnya masuk akal per sumur dan tidak ada nilai aneh karena salah satuan.

### Hari 7: Baseline dan Ridge
- [x] Baseline: WellPlan apa adanya (FF terdekat) sebagai pembanding
- [x] Ridge dengan penskalaan fitur
- [x] Skrip evaluasi: RMSE, MAPE, R² per operasi

**Selesai bila:** ada angka pembanding yang harus dikalahkan XGBoost.

### Hari 8: XGBoost
- [x] XGBoost dengan parameter sederhana, pencarian parameter kecil saja (data sedikit, hindari overfitting)
- [x] Coba dua bentuk target: nilai aktual langsung dan selisih terhadap WellPlan, pilih yang lebih stabil
- [x] Simpan model dengan joblib, catat versi dan parameter

### Hari 9: Validasi per kelompok sumur
- [x] GroupKFold atau leave-one-well-out (satu sumur tidak pernah ada di data latih dan uji sekaligus)
- [x] Metrik per section dan per tipe sumur, bandingkan dengan baseline WellPlan
- [x] Tandai kombinasi section x tipe yang sumurnya sedikit sebagai "peringatan"
- [ ] Periksa kasus terburuk satu per satu: apakah karena data atau karena model

### Hari 10: Laporan model dan antarmuka pelatihan
- [x] Laporan evaluasi (tabel dan grafik) dalam format yang bisa dibaca client
- [x] Endpoint dan tombol "Latih model" (proses latar belakang, status tampil di UI)
- [x] Tabel `models` menyimpan metrik, parameter, tanggal, dan lokasi file model
- [ ] Sesi dengan narasumber untuk mengecek kewajaran hasil
- [ ] Sepakati target akurasi bersama client (sesuai Pasal 9: tidak ada jaminan angka)

**Selesai bila (milestone Minggu 2):** model terlatih tersimpan, laporan akurasi per section dan tipe sumur ada, dan perbandingan dengan baseline WellPlan jelas, termasuk jika ML tidak lebih baik di kombinasi tertentu.

---

## MINGGU 3: Aplikasi, ekspor, demo, serah terima

### Hari 11: Prediksi sumur baru
- [x] Alur unggah file WellPlan sumur baru, validasi sama seperti impor
- [x] Mesin prediksi memakai model aktif, keluaran per kedalaman untuk 5 target
- [x] Peringatan bila section/tipe sumur baru jarang ada di data latih
- [x] Hasil prediksi tersimpan (tabel `predictions` dan `prediction_points`)

### Hari 12: Dashboard (3 grafik: Hookload, Torque, Selisih)

Tiga grafik berdampingan pada satu halaman, semuanya berbagi **sumbu kedalaman** yang sama (terbalik, 0 di atas). Tiap grafik membandingkan tiga profil dengan warna tetap: **WellPlan, Prediksi ML, Aktual**.

**Grafik 1: Hookload**
- [x] Kurva pick up, slack off, dan rotating weight terhadap kedalaman
- [x] Warna menunjukkan profil (WellPlan, ML, Aktual), gaya garis menunjukkan operasi (pick up penuh, slack off putus-putus, rotating titik-titik)
- [x] Aktual ditampilkan sebagai titik (pembacaan lapangan), WellPlan dan ML sebagai garis
- [x] Kotak centang untuk menyalakan atau mematikan tiap operasi agar tidak penuh
- [x] Kurva friction factor 0,1 / 0,3 / 0,5 dari WellPlan bisa ditampilkan sebagai pilihan

**Grafik 2: Torque**
- [x] Kurva torque off bottom dan torque on bottom terhadap kedalaman
- [x] Aturan warna dan gaya garis sama seperti Grafik 1
- [x] Satuan pada sumbu mengikuti file asli (misalnya ft-lbf), dengan opsi satuan SI

**Grafik 3: Selisih (arah dan besar pergeseran)**
- [x] Sumbu horizontal berpusat di **garis nol**. Konvensi: **kanan = positif = nilai lebih tinggi**, **kiri = negatif = nilai lebih rendah**. Tulis konvensi ini di legenda grafik
- [x] Tiga garis selisih:
  - **WellPlan - Aktual**: seberapa jauh model konvensional bergeser dari kenyataan
  - **ML - Aktual**: seberapa jauh prediksi ML bergeser dari kenyataan
  - **ML - WellPlan**: koreksi yang dilakukan ML terhadap WellPlan
- [x] Selisih terhadap Aktual hanya dihitung pada kedalaman yang punya data aktual (tampil sebagai titik). "ML - WellPlan" tampil sebagai kurva kontinu
- [x] Pemilih target (pick up, slack off, rotating weight, torque off, torque on) dan pemilih mode: **absolut** (satuan asli) atau **persen**
- [x] Hover menampilkan kedalaman, selisih absolut, dan selisih persen
- [x] Tabel "5 kedalaman dengan selisih terbesar" di bawah grafik, mencantumkan arah (kanan/kiri) dan besarnya

**Fitur bersama**
- [x] Zoom, geser, dan hover tersinkron antar ketiga grafik. Satu garis vertikal penuntun memotong ketiganya di kedalaman yang sama
- [x] Penandaan interval yang |selisih| melewati ambang: arsiran pada ketiga grafik, ambang bisa diatur
- [x] Untuk sumur yang ikut training, tampilkan prediksi **out-of-fold** (model yang tidak pernah melihat sumur itu), bukan prediksi in-sample, agar perbandingan jujur
- [x] Filter section dan tipe sumur, pemilih sumur, peringatan bila kombinasinya datanya sedikit
- [x] Ringkasan metrik di bawah grafik (RMSE, MAPE, R²) untuk WellPlan dan ML
- [x] Bila sumur belum punya data aktual: Grafik 1 dan 2 tetap tampil (WellPlan dan ML), Grafik 3 hanya "ML - WellPlan", dengan keterangan "belum ada data aktual"
- [x] Judul, label sumbu, satuan, dan legenda jelas pada tiap grafik
- [x] Layar kecil: ketiga grafik menumpuk vertikal

**Backend untuk grafik ini**
- [x] Endpoint yang mengembalikan data profil per sumur (WellPlan, ML out-of-fold, Aktual) dan selisih per kedalaman, dengan satuan dan tanda positif/negatif yang konsisten
- [x] Tes: selisih dihitung benar pada 3 titik yang dicek manual (tanda dan besar)

**Selesai bila:** satu sumur uji menampilkan tiga grafik dengan kedalaman sejajar, grafik Selisih menunjukkan jelas pergeseran ke kanan atau kiri beserta besarnya di kedalaman tertentu, dan angka di grafik cocok dengan tabel datanya.

### Hari 13: Ekspor Excel dan demo
- [x] Ekspor `.xlsx`: sheet perbandingan dan prediksi ML mengikuti struktur contoh, dengan kolom selisih per kedalaman dan tiga grafik yang sama seperti dashboard (Hookload, Torque, Selisih)
- [ ] Cek file ekspor terbuka di Excel tanpa peringatan
- [ ] Demo ke client (sisakan waktu untuk mencatat umpan balik)
- [ ] Minta umpan balik dalam satu daftar tertulis (revisi putaran 1, Pasal 7)

### Hari 14: Revisi
- [ ] Kerjakan hanya revisi yang berada dalam lingkup (penyesuaian fitur yang ada)
- [ ] Permintaan di luar lingkup dicatat sebagai pekerjaan tambahan, estimasi dikirim tertulis
- [ ] Perbaiki bug yang ditemukan saat demo

### Hari 15: Serah terima
- [ ] Deploy final, uji ulang alur dari awal sampai ekspor pada server
- [ ] Backup database terjadwal berjalan dan sudah diuji pulihkan sekali
- [x] Panduan singkat penggunaan, plus panduan menjalankan dan memperbarui via Docker
- [ ] Ganti password admin dengan yang baru dan serahkan kredensial ke client lewat jalur aman
- [ ] Source code, konfigurasi Docker, dan model diserahkan (setelah pelunasan sesuai Pasal 4 dan 12)
- [ ] Kirim permintaan pembayaran tahap 2 (jatuh tempo 7 hari setelah demo dan serah terima)

**Selesai bila:** semua deliverables di perjanjian Pasal 5 ayat 3 terpenuhi.

---

## Daftar pemotongan (jika terlambat, potong dari atas)

1. Grafik di file ekspor Excel (sheet data tetap ada)
2. Penandaan interval deviasi di dashboard
3. Klasifikasi tipe sumur otomatis, diganti kolom isian manual atau metadata dari client
4. Sheet Tripping Data (fokus ke Drag, Torque, dan Actual Reading)
5. Pencarian parameter XGBoost (pakai parameter bawaan yang wajar)

**Jangan dipotong:** login admin, tampilan tiga grafik di dashboard (Hookload, Torque, Selisih), validasi per kelompok sumur, perbandingan dengan baseline WellPlan, dan peringatan pada kombinasi data sedikit.

## Risiko dan tindakan

| Risiko | Tindakan |
|---|---|
| Data terlambat | Jadwal bergeser sesuai perjanjian, beri tahu client tertulis di hari yang sama |
| Format file menyimpang | Catat di laporan audit, minta client merapikan atau hitung sebagai pekerjaan tambahan |
| Data aktual terlalu sedikit | Laporkan apa adanya, jangan memaksakan model rumit |
| ML tidak lebih baik dari baseline | Laporkan jujur, tunjukkan di mana ML membantu dan di mana tidak |
| Satuan salah | Tes otomatis dengan titik cek manual, satuan asli selalu disimpan |
| Server atau domain belum siap | Deploy sementara di server sendiri, pindah ke server client sebelum serah terima |
| Terlalu mengandalkan keluaran AI | Review kode dan angka, jalankan tes sebelum merge |
| Login dan keamanan terlewat karena jadwal padat | Kerjakan di Hari 2, jangan unggah data client ke server sebelum login lolos tes |

## Checklist penutupan proyek

- [ ] Pembayaran tahap 2 diterima
- [ ] Password admin diganti dan kredensial diserahkan ke client, akun uji dihapus
- [ ] Garansi 14 hari dicatat di kalender (mulai dari tanggal serah terima)
- [ ] Salinan data client dihapus dari laptop dan lingkungan pengembangan dalam 14 hari (Pasal 11 ayat 4)
- [ ] Jika client lanjut ke paket 6 minggu dalam 60 hari, kredit sesuai Pasal 16 diterapkan
