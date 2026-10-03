# TO-DO: Lanjutan dari Prototype 3 Minggu ke Paket 6 Minggu (40 sumur atau lebih)

Dokumen kerja internal. Prototype 3 minggu menjadi **fondasi**. Enam minggu ini dipakai untuk menaikkan cakupan ke 40 sumur atau lebih, menjaga kualitas data, melengkapi model, dan menyelesaikan 16 fitur sesuai proposal.

> **Soal "menjamin kualitas hasil":** tidak ada sistem yang bisa menjamin kualitas hasil dari data yang kualitasnya tidak diketahui. Yang bisa dijamin adalah **prosesnya**: setiap file diperiksa, setiap sumur diberi status dan alasan, hanya data yang lolos yang dipakai melatih model, dan akurasi diukur pada sumur yang tidak pernah dilihat model. Bagian "Gerbang kualitas data" di bawah menjabarkannya. Kesalahan yang tidak terlihat dari datanya sendiri (misalnya pembacaan yang salah dicatat di lapangan) tidak bisa ditangkap sistem, hanya bisa dikurangi lewat tinjauan engineer.

> **Status pengerjaan (3 Okt 2026).** Semua pekerjaan kode paket 6 minggu sudah dibuat dan
> dijalankan pada **data asli folder `Training/`** (45 sumur, 94 file) di stack Docker lokal:
> pindai folder → gerbang kualitas (A 69 · B 15 · C 10 sumur-section) → dataset v1 beku
> (35 sumur latih, 9 sumur blind test) → model Ridge/XGBoost/Random Forest/SVR dibandingkan
> (rasio RMSE ML/WellPlan 0,714) → blind test sekali (ML lebih baik dari WellPlan di 5 operasi)
> → dashboard, batas aman, Excel, PDF. 44 tes lulus. **Belum** (butuh client / narasumber /
> server): konfirmasi & persetujuan client, sesi narasumber, tinjauan sumur status C, target
> akurasi, deploy server, demo, UAT, revisi, pelatihan, serah terima. Ringkasan angka:
> `data/reports/RINGKASAN_HASIL.md` (tidak di Git).

## Yang sudah ada dari prototype (dipakai ulang)

- [x] Parser WellPlan dan data aktual, impor ke PostgreSQL, validasi dasar
- [x] Klasifikasi section dan tipe sumur
- [x] Dataset builder, baseline WellPlan, Ridge, XGBoost
- [x] Validasi per kelompok sumur
- [x] Prediksi sumur baru
- [x] Dashboard 3 grafik (Hookload, Torque, Selisih)
- [x] Ekspor Excel
- [x] Login satu akun admin
- [ ] Deploy Docker + nginx + HTTPS di domain

**Hari 1 lanjutan:** kaji ulang kode prototype, catat utang teknis (bagian yang ditulis cepat), dan putuskan mana yang dirapikan dulu.

## Daftar fitur paket 6 minggu (sesuai proposal v2)

| No | Fitur | Status dari prototype | Pekerjaan lanjutan |
|---|---|---|---|
| 1 | Impor laporan WellPlan | Ada (15 sumur) | 40+ sumur, **impor massal dari folder** (lihat bawah), varian format |
| 2 | Impor data aktual | Ada | Varian sheet dan penanganan data kosong |
| 3 | Validasi dan pembersihan | Dasar | **Gerbang kualitas data** lengkap |
| 4 | Klasifikasi section dan tipe sumur | Ada | Koreksi manual dan tinjauan engineer |
| 5 | Dataset dan fitur | Ada | Fitur tambahan (lihat Minggu 2) |
| 6 | Pelatihan dan perbandingan model | Ridge, XGBoost | + Random Forest, SVR, MLP (opsional) |
| 7 | Validasi per kelompok sumur | Ada | Blind test, kurva belajar, per section dan tipe |
| 8 | Penjelasan hasil (SHAP) | Belum | Baru |
| 9 | Penyimpanan model | Dasar | Versi model, versi dataset, riwayat performa |
| 10 | Prediksi sumur baru | Ada | Penyempurnaan, peringatan data sedikit |
| 11 | Dashboard tiga profil | 3 grafik | Penyempurnaan, performa dengan 40+ sumur |
| 12 | Deteksi interval dan batas aman | Penandaan sederhana | Batas aman per kedalaman |
| 13 | Evaluasi prediksi vs aktual | Belum | Baru |
| 14 | Ekspor laporan Excel | Ada | Lengkap sesuai struktur sheet contoh |
| 15 | Ringkasan PDF | Belum | Baru |
| 16 | Login sederhana | Ada | Sudah ada, perkuat bila perlu |

---

## Impor massal dari folder (pertanyaan: "data 40 sumur ditaruh di folder")

Bisa, dan lebih praktis daripada mengunggah 40 file satu per satu. Rancangannya:

```
data/inbox/                  <- file baru ditaruh di sini (di server)
   BLSE26-0002/
      laporan_wellplan.xlsm
      aktual_roadmap.xlsx
   MUTI25-0010/
      ...
data/processed/              <- file yang sudah diimpor (dipindah otomatis)
data/rejected/               <- file ditolak, disertai alasan
```

- [x] Folder `data/inbox` dipasang ke container sebagai volume (bind mount), hanya ada di server
- [x] Aturan penamaan: satu subfolder per sumur, kode sumur = nama folder. Ini juga cara memasangkan laporan WellPlan dengan data aktual
- [x] Tombol **"Pindai folder"** di aplikasi (bukan pemantau otomatis terus-menerus, agar file yang masih disalin tidak terbaca setengah jadi)
- [x] Abaikan file yang baru diubah dalam 1 menit terakhir
- [x] Idempoten: file dengan checksum sama tidak diimpor dua kali, file yang berubah dibuat sebagai versi baru
- [x] Hasil pemindaian: tabel per sumur (diterima, diterima dengan peringatan, ditahan) beserta alasan
- [x] Setelah impor: file dipindah ke `processed/` atau `rejected/`
- [x] Hanya `.xlsx` dan `.xlsm`, macro tidak dijalankan, batas ukuran per file
- [ ] Hak akses folder: hanya pengguna server dan container
- [ ] Catatan lingkup: proposal menyebut "unggah". Impor folder adalah penyesuaian kecil pada fitur 1, sebaiknya dicatat tertulis

---

## Gerbang kualitas data

Tujuan: hanya data yang layak masuk training, dan setiap keputusan bisa ditelusuri.

**Status per sumur**

| Status | Arti | Masuk training? |
|---|---|---|
| **A: Layak** | Lolos semua pemeriksaan wajib | Ya |
| **B: Layak dengan peringatan** | Ada peringatan tidak kritis, tercatat | Ya, dengan tanda |
| **C: Ditahan** | Gagal pemeriksaan kritis | Tidak, menunggu tinjauan |

**Pemeriksaan wajib (kritis)**
- [x] Format sheet dikenali (WellPlan atau roadmap), kolom wajib ada
- [x] Satuan dikenali dan berhasil dikonversi
- [x] Kedalaman naik dan tidak ada duplikat
- [x] Nilai wajar secara fisik (hookload positif, torque tidak negatif)
- [x] Urutan fisik wajar dengan toleransi: slack off <= rotating weight <= pick up
- [x] Rentang kedalaman WellPlan dan data aktual saling tumpang
- [x] Jumlah titik aktual minimum (usul awal: 8 titik, disepakati di audit)
- [x] Section dan tipe sumur teridentifikasi
- [x] Bukan duplikat sumur lain (checksum dan kombinasi nama dan kedalaman)

**Pemeriksaan statistik (peringatan)**
- [x] Bandingkan rasio aktual/WellPlan dengan sumur lain di section dan tipe yang sama (outlier robust, misalnya MAD)
- [x] Lompatan tak wajar antar titik berurutan
- [x] Nilai aktual yang persis sama berulang (kemungkinan salin tempel)
- [x] Ukuran data aktual jauh lebih sedikit dari sumur sekelas

**Pelaporan dan keputusan**
- [x] Skor kualitas sederhana per sumur (berbasis aturan, bukan model)
- [x] **Laporan kualitas data**: tabel semua sumur dengan status, skor, dan alasan, bisa diunduh sebagai Excel
- [ ] Tinjauan bersama narasumber untuk sumur status C dan outlier: **perbaiki** (minta file baru dari client), **kecualikan** (dengan alasan tertulis), atau **terima** (dengan catatan)
- [x] Setiap keputusan tinjauan dicatat (siapa, kapan, alasan)
- [x] **Pembekuan data**: dataset diberi versi (daftar sumur dan hash isinya). Setiap model mencatat versi dataset yang dipakai sehingga hasilnya bisa diulang

---

## MINGGU 1: Kaji ulang, audit 40 sumur, impor massal

### Hari 1: Kaji ulang prototype
- [x] Tinjau kode, tes, dan catatan keputusan prototype
- [x] Daftar utang teknis dan urutan perapihan
- [x] Update `CLAUDE.md` dengan lingkup 16 fitur
- [ ] Konfirmasi dengan client: file 40 sumur sudah di server atau kapan tiba, persetujuan penggunaan AI atas data tetap berlaku

### Hari 2-3: Audit penuh 40 file
- [x] Jalankan skrip audit pada seluruh file (format, sheet, satuan, jumlah titik)
- [x] Matriks sumur x section x tipe (berapa sumur per kombinasi)
- [x] Daftar file yang menyimpang dan jenis penyimpangannya
- [ ] Sesi dengan narasumber: varian format, definisi, ambang
- [ ] **Laporan audit** ke client (milestone Minggu 1)

### Hari 4-5: Impor massal dan gerbang kualitas v1
- [x] Impor massal dari folder (rancangan di atas)
- [x] Gerbang kualitas data: pemeriksaan wajib dan status A/B/C
- [x] Perluas parser untuk varian format yang ditemukan di audit (dalam batas lingkup, sisanya dicatat sebagai pekerjaan tambahan)
- [x] Laporan kualitas data v1

**Selesai bila:** 40 file sudah dipindai, setiap sumur punya status dan alasan, dan client punya daftar sumur yang perlu diperbaiki atau dikonfirmasi.

---

## MINGGU 2: Kualitas data dan dataset

### Hari 6-7: Tinjauan kualitas
- [x] Pemeriksaan statistik dan skor kualitas
- [ ] Tinjauan bersama narasumber untuk sumur status C dan outlier
- [x] Putuskan perlakuan data kosong dan outlier, catat di `docs/keputusan.md`
- [ ] Minta client memperbaiki atau mengganti file yang bermasalah (kirim daftar tertulis)

### Hari 8: Dataset dan fitur
- [x] Fitur dasar dari prototype dirapikan
- [x] Fitur tambahan yang masuk akal secara fisik:
  - posisi terhadap casing shoe (casing atau open hole), bila datanya tersedia
  - profil dogleg dan tortuosity
  - properti BHA yang relevan dan mud weight
  - kedalaman relatif terhadap titik KOP dan tipe interval (vertikal, build, tangent, horizontal)
- [x] Setiap fitur baru dicek manfaatnya sebelum dipertahankan (jangan menambah fitur tanpa bukti)

### Hari 9-10: Pembekuan data dan pembagian uji
- [x] **Bekukan dataset v1** (versi dan hash)
- [x] Pisahkan **blind test**: sekitar 20% sumur (misalnya 8 dari 40), dipilih proporsional per section dan tipe, **dikunci sebelum eksperimen apa pun**. Tidak dipakai untuk tuning, hanya dipakai sekali di akhir
- [x] Sumur sisanya dipakai untuk validasi silang per kelompok sumur
- [ ] Sepakati target keberhasilan relatif dengan client, misalnya "ML lebih baik dari WellPlan pada sekian persen titik uji" (angka ditetapkan setelah audit, tanpa janji muluk)

**Selesai bila (milestone Minggu 2):** dataset beku, blind test terkunci, laporan kualitas data final, dan keputusan sumur mana yang dikecualikan tercatat.

> **Titik keputusan (akhir Minggu 2):** jika sebagian besar kombinasi section x tipe hanya punya sedikit sumur bersih, bicarakan dengan client sebelum melanjutkan: tambah data, gabungkan kombinasi, atau terima bahwa sebagian hanya mendapat peringatan.

---

## MINGGU 3: Model

### Hari 11-12: Perbandingan model
- [x] Baseline: WellPlan apa adanya
- [x] Ridge, XGBoost, Random Forest, SVR dengan prosedur yang sama
- [x] Tuning parameter dengan validasi silang per kelompok sumur (satu sumur tidak ada di data latih dan uji sekaligus)
- [x] MLP sebagai pembanding opsional, hanya bila ada waktu
- [x] Bandingkan model tunggal (section dan tipe sebagai fitur) dengan model terpisah per kombinasi yang datanya cukup (usul: minimal 10 sumur)

### Hari 13: Kurva belajar dan analisis kesalahan
- [x] Ukur akurasi saat memakai 5, 10, 20, 30, dan semua sumur latih. Kurva masih naik = tambah sumur membantu. Mendatar = masalah ada di data atau fitur
- [x] Telusuri titik dan sumur dengan error terbesar: karena data, fitur, atau model?
- [x] Analisis per section, tipe sumur, dan kedalaman

### Hari 14-15: SHAP dan model final
- [x] Analisis SHAP / pentingnya fitur, cek kewajaran fisika (misalnya inklinasi dan friction factor harus berpengaruh)
- [x] Pilih model final dan strategi (tunggal atau per kombinasi) berdasarkan validasi, **bukan** blind test
- [x] **Jalankan blind test sekali** dan catat hasilnya apa adanya
- [x] Laporan evaluasi model (milestone Minggu 4 di proposal, boleh lebih awal)

**Selesai bila:** model final tersimpan dengan versi model dan versi dataset, dan ada perbandingan jujur terhadap WellPlan pada sumur uji dan blind test.

---

## MINGGU 4: Penyimpanan model, prediksi, evaluasi, batas aman

### Hari 16-17: Penyimpanan model dan pelatihan ulang
- [x] Tabel model: algoritma, parameter, metrik, versi dataset, tanggal, model aktif
- [x] Pelatihan ulang dari antarmuka saat data sumur baru ditambahkan (mengikuti gerbang kualitas yang sama)
- [x] Bandingkan model baru dengan model aktif sebelum diaktifkan, dan tahan bila lebih buruk

### Hari 18-19: Prediksi dan evaluasi
- [x] Prediksi sumur baru dari file WellPlan (penyempurnaan prototype)
- [x] Peringatan jelas bila section atau tipe sumur baru jarang ada di data latih
- [x] **Evaluasi prediksi vs aktual**: setelah data aktual sumur baru diunggah, bandingkan otomatis dengan prediksi yang dibuat sebelumnya
- [x] Interval ketidakpastian prediksi (opsional, bila waktu cukup) agar pengguna tahu seberapa yakin hasilnya

### Hari 20: Batas aman dan deteksi interval
- [x] Estimasi kedalaman ketika prediksi menyentuh batas yang ditetapkan client (torque limit, ambang hookload)
- [x] Ambang diatur dari antarmuka dan disimpan per sumur atau per section
- [x] Penandaan interval pada tiga grafik

**Selesai bila (milestone Minggu 4):** model punya riwayat versi, prediksi sumur baru jalan dengan peringatan, dan batas aman tampil.

---

## MINGGU 5: Aplikasi, ekspor, PDF

### Hari 21-22: Dashboard
- [x] Tiga grafik (Hookload, Torque, Selisih) berjalan lancar dengan 40+ sumur
- [x] Filter section, tipe sumur, status kualitas data, dan versi model
- [x] Halaman Laporan kualitas data dan halaman riwayat model
- [x] Uji performa (waktu muat grafik), optimasi kueri bila lambat

### Hari 23-24: Ekspor Excel dan ringkasan PDF
- [x] Ekspor `.xlsx` dengan struktur sheet mengikuti contoh (Drag, Torque, T&D Actual Reading) ditambah kolom prediksi ML, kolom selisih, dan tiga grafik
- [x] Ringkasan PDF: metrik, grafik utama, status kualitas data, versi model dan dataset
- [ ] Cek file ekspor terbuka di Excel tanpa peringatan

### Hari 25: Integrasi dan demo
- [x] Uji alur lengkap dari folder impor sampai ekspor
- [ ] Demo ke client (milestone Minggu 5)
- [ ] Kumpulkan umpan balik dalam satu daftar tertulis (revisi putaran 1)

**Selesai bila:** seluruh 16 fitur berjalan di server dan demo sudah dilakukan.

---

## MINGGU 6: UAT, revisi, serah terima

### Hari 26-27: Revisi putaran 1
- [ ] Kerjakan revisi yang berada dalam lingkup
- [ ] Permintaan di luar lingkup dicatat sebagai pekerjaan tambahan, estimasi dikirim tertulis

### Hari 28: UAT dan revisi putaran 2
- [ ] Client menguji dengan sumur baru
- [ ] Kerjakan revisi putaran 2 (batas sesuai perjanjian)

### Hari 29-30: Serah terima
- [ ] Deploy final, backup terjadwal berjalan dan uji pulihkan dilakukan sekali
- [x] Dokumentasi: panduan pengguna, panduan operasional (impor folder, pelatihan ulang, pencadangan), dokumentasi teknis
- [ ] Pelatihan pengguna (satu sesi)
- [ ] Source code, konfigurasi Docker, dan model diserahkan setelah pelunasan
- [ ] Ganti password admin dan serahkan kredensial lewat jalur aman
- [ ] Laporan akhir: akurasi pada sumur uji dan blind test, sumur yang dikecualikan beserta alasan, keterbatasan model

**Selesai bila:** semua deliverables di perjanjian paket 6 minggu terpenuhi.

---

## Daftar pemotongan (jika terlambat, potong dari atas)

1. MLP dan interval ketidakpastian
2. Ringkasan PDF disederhanakan (tabel metrik saja)
3. Model terpisah per kombinasi (cukup model tunggal)
4. Grafik di file ekspor Excel (sheet data tetap ada)

**Jangan dipotong:** gerbang kualitas data, blind test, perbandingan dengan baseline WellPlan, pencatatan versi model dan dataset, dan peringatan pada kombinasi data sedikit.

## Risiko dan tindakan

| Risiko | Tindakan |
|---|---|
| Sebagian dari 40 sumur ternyata tidak layak | Status C dan tinjauan engineer, laporan jujur ke client, mintalah file pengganti |
| Sebaran section x tipe timpang | Model tunggal dengan fitur section dan tipe, peringatan untuk kombinasi tipis |
| ML tidak lebih baik dari WellPlan di kombinasi tertentu | Laporkan apa adanya, jangan memaksa |
| Kebocoran data (sumur sama di data latih dan uji) | Validasi per kelompok sumur dan blind test terkunci sejak awal |
| Varian format banyak | Catat di laporan audit, batasi pada lingkup, sisanya pekerjaan tambahan |
| Data baru terus datang di tengah proyek | Pembekuan data di Hari 9-10, tambahan setelahnya dihitung pekerjaan tambahan |
| Jadwal tanpa cadangan | Pakai daftar pemotongan, jangan memotong pengaman kualitas |

## Checklist penutupan

- [ ] Pembayaran seluruh termin diterima, kredit pilot 3 minggu diterapkan sesuai perjanjian
- [ ] Garansi 30 hari dicatat di kalender
- [ ] Salinan data client di laptop dan lingkungan pengembangan dihapus dalam 14 hari
- [ ] Laporan akhir dan laporan kualitas data terkirim ke client
