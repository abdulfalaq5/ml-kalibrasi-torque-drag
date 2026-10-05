# Tutorial: Menguji Model ML pada Satu Sumur (untuk pengguna awam)

Versi bahasa Inggris ada di aplikasi: menu **How-to Guide → Tutorial → "Tutorial: test the model on a well"**.
Tampilan aplikasi berbahasa Inggris, jadi nama tombol di bawah ditulis persis seperti di layar
(dalam **tebal**). Satu sumur butuh sekitar 10 menit.
Penjelasan rinci setiap garis dan arsiran di grafik: `docs/panduan_membaca_grafik.md`.

---

## Bagian 0 — Gagasannya dengan bahasa sederhana

| Istilah | Artinya |
|---|---|
| **T&D model (WellPlan)** | Hasil hitungan software perencanaan untuk hookload dan torsi, satu kurva per friction factor (OHFF). |
| **Actual** | Pembacaan sebenarnya di rig saat mengebor (pick up, slack off, rotating weight, torsi). |
| **ML forecast** | Perkiraan sistem. Sistem belajar dari banyak sumur yang sudah dibor: seberapa jauh T&D model biasanya meleset dari aktual. |
| **Training Data** | Sumur lama tempat ML belajar. Untuk menguji model, bagian ini **tidak perlu disentuh**. |
| **Monitoring** | Sumur yang ingin diprediksi. Unggahan di sini **tidak pernah mengubah ML**, jadi aman untuk uji. |
| **Toleransi** | Batas lulus dari client: ML dianggap tepat bila selisihnya dengan aktual **< 10 klbf** (hookload) dan **< 2 kft-lbf** (torsi). |

**Menguji model** = memberi sistem sumur yang belum pernah ia lihat, meminta forecast, lalu
membandingkannya dengan pembacaan sebenarnya di rig. Sistem menghitung perbandingannya sendiri dan
menampilkan persentase: berapa persen pembacaan aktual yang berhasil ditebak ML dalam toleransi.
**90% ke atas = bagus.**

Alur singkat:
```
1. Cek ada model aktif (Models)  →  2. Monitoring: pilih section & tipe  →  3. Unggah file
→ 4. Baca hasil  →  5. Dashboard: forecast 300 ft  →  6. Lihat "Check against actual"  →  7. Unduh Excel/PDF
```

---

## Bagian 1 — Persiapan (2 menit)

1. **Login.** Buka alamat aplikasi, isi username dan password, klik **Sign in**.
2. **Pastikan ada model aktif.** Klik menu **Models** di bar atas. Di tabel **Model history** harus ada
   satu baris berstatus **Done** dengan label hijau **active**. Bila tidak ada, model harus dilatih
   dulu (How-to Guide topik 4) atau hubungi administrator.
3. **Siapkan file sumur yang akan diuji.** Satu file Excel = satu section dari satu sumur:
   laporan WellPlan asli (.xlsm), roadmap T&D (.xlsx), atau template dari sistem.
   Untuk uji yang sesungguhnya, file harus **berisi data aktual** (sheet "T&D Actual Reading" atau
   "Drilling Data"). Tanpa data aktual, tidak ada pembanding.
4. **Ketahui Well section dan Well type.**
   - **Well section** = ukuran lubang di file ini, biasanya ada di nama file (`_8.5in` artinya 8.5").
   - **Well type**: **J** = membangun sudut lalu ditahan; **S** = membangun, ditahan, lalu turun
     lagi; **Horizontal** = berakhir mendekati inklinasi 90°. Bila ragu, tanyakan ke DD atau lihat well plan.

---

## Bagian 2 — Unggah sumur di halaman Monitoring

1. **Klik Monitoring** di bar atas. Halaman *"Upload a monitoring well (forecast only)"* terbuka,
   berisi 5 langkah bernomor.
2. **Langkah 1 di halaman: pilih Well section dan Well type.**
   - Buka daftar **Well section**, pilih ukuran lubang (mis. **8.5"**).
   - Buka daftar **Well type**, pilih **J**, **S**, atau **Horizontal**.
   - **Well name** boleh dikosongkan (diambil dari file).
   - Selama keduanya belum dipilih, kotak unggah di langkah 4 berwarna abu-abu dan bertuliskan
     *"Select the well section and well type first"*.
3. **Langkah 2 (opsional): template.** Hanya bila tidak punya file asli: klik
   **⬇ Monitoring well template (.xlsx)**, isi sesuai sheet "Instructions" dan "Example", simpan.
4. **Langkah 4: unggah.** Tarik file ke kotak, atau klik kotak lalu pilih file. Tunggu beberapa detik:
   *"Importing and checking the file…"* lalu *"Forecasting with the active model…"*.
5. **Langkah 5: baca hasil forecast.** Muncul tabel satu baris per operasi (Pick up, Slack off,
   Rotating weight, Torque off bottom, Torque on bottom) di kedalaman paling dalam:
   - **T&D Model (OHFF 0.3)** = nilai perencanaan.
   - **ML forecast** = nilai perkiraan sistem.
   - **Uncertainty band (P10–P90)** = rentang tempat pembacaan kemungkinan besar jatuh.
   - **ML − T&D Model** = seberapa besar sistem mengoreksi rencana.
   - Pesan kuning = peringatan yang perlu dibaca (mis. tipe sumur jarang di data latih).

   Klik **Open dashboard (forecast N ft ahead)** untuk lanjut.

> Bila muncul pesan merah, file tidak terbaca; alasannya tertulis per sheet. Penyebab umum: jenis
> file salah, judul kolom diubah, atau section tidak cocok dengan file. Perbaiki file lalu unggah lagi.

---

## Bagian 3 — Membaca grafik (Dashboard)

1. **Sumur sudah terpilih** di kotak **Well**, dengan tanda **[Monitoring]**. Biarkan **Units** di
   Imperial (ft, klbf, ft-lbf).
2. **Panel Hookload (atas).**
   - Garis biru = T&D model per OHFF (biru lebih muda = OHFF lebih kecil), dengan nama seperti **PU - OHFF : 0.3**.
   - Garis oranye = ML forecast (**PU - ML**).
   - Titik hijau = pembacaan aktual (**PU Actual**).
   - **Tanda bagus**: titik hijau menempel atau dekat dengan garis oranye.
3. **Panel Torque dan panel Difference.** Torsi dibaca dengan cara yang sama. Panel Difference
   menunjukkan selisih: titik dekat garis nol hitam = error kecil.
4. **Metrics for this well (kanan bawah).** Kolom **Within tol. WP → ML**, mis. "70% → **96%**",
   artinya 70% pembacaan aktual masuk toleransi bila memakai T&D model, dan 96% bila memakai ML.
   Ini hasil uji utama untuk seluruh sumur.

---

## Bagian 4 — Menguji forecast 300 ft ke depan

Pertanyaan sebenarnya saat mengebor: *seberapa tepat forecast untuk 300 ft berikutnya?* Ini bisa
diuji pada sumur yang data aktualnya sudah lengkap, dengan "berpura-pura" rig masih di kedalaman
yang lebih dangkal.

1. **Gulir ke panel Forecast ahead** (di bawah grafik).
2. **Distance: 300** (jumlah feet yang diramal).
3. **From depth: isi kedalaman lebih awal** (untuk uji). Contoh: data aktual sampai 9.500 ft, isi
   **9000**. Forecast hanya memakai data di atas 9.000 ft, persis seperti rig sedang di 9.000 ft.
   Kosongkan kolom ini untuk forecast sungguhan dari pembacaan terakhir.
4. **Local bias correction: biarkan tercentang.** Forecast digeser memakai pembacaan aktual terakhir
   di atas kedalaman awal, mirip kalibrasi yang dilakukan DD. Opsi ini aktif secara bawaan karena
   paling akurat.
5. **Klik Forecast. Grafik langsung pindah ke area forecast.** Halaman menggulir ke grafik dan
   otomatis zoom ke jendela forecast. Yang terlihat:
   - Dua garis putus-putus ungu: **Forecast start · 9,000 ft** dan **Forecast end · 9,300 ft (+300 ft)**,
     dengan arsiran tipis di antaranya.
   - **Garis ungu tebal** per operasi = **forecast-nya**, yaitu ke mana hookload/torsi diperkirakan
     bergerak dalam 300 ft berikutnya. Pita ungu berarsir di sekitarnya = rentang kemungkinan (P10–P90).
   - Di ujung setiap garis ungu tertulis **nilai prediksinya**, mis. "PU 128 klbf @ 9,300 ft".
   - Titik hijau di dalam jendela = pembacaan aktual yang menjadi pembanding.
   - Tombol **Show whole well** (di atas grafik) kembali ke seluruh kedalaman; **Zoom to forecast**
     kembali ke jendela forecast.
6. **Baca tabel:**
   - **Check against actual** = hasil uji. Contoh: "T&D 60% · ML + bias **100%** (n=10)" artinya dari
     10 pembacaan aktual di 300 ft berikutnya, T&D model tepat 60%, ML tepat 100% (dalam toleransi).
   - **Expected accuracy** = hasil model untuk jarak yang sama pada banyak sumur yang tidak pernah
     dilihatnya (mis. "99% < 10 klbf"). Hasil uji Anda sebaiknya mendekati angka ini.
   - **Cause and effect** = kalimat yang menjelaskan kenapa nilai naik atau turun (inklinasi,
     dogleg, T&D model) dan apakah batas operasi terlampaui.
7. **Ulangi di kedalaman lain** (mis. atas, tengah, bawah section) untuk melihat apakah model bagus
   di semua bagian.

---

## Bagian 5 — Mengunduh hasil

1. **Export Excel** (atas dashboard): format client "OUTPUT … Multiple T&D Road Map".
   Isinya: Summary Outputs (tabel aktual vs ML, metrik), grafik drag dan torque, sheet PU/SO/ROT MW.
2. **PDF**: ringkasan siap cetak dengan grafik.
3. **⬇ Forecast (.xlsx)**: forecast 300 ft beserta hasil cek dan kalimat sebab-akibat.

---

## Bagian 6 — Laporan uji bawaan model (opsional)

1. **Models → Report** pada model aktif.
   - Kolom **Within tolerance T&D → ML**: hasil pada semua sumur latih, masing-masing dinilai oleh
     model yang tidak pernah melihat sumur itu.
   - Kolom **Blind within tolerance**: hasil pada sumur blind test yang dikunci sejak awal.
2. **Tab Forecast backtest**: seberapa sering forecast 300 / 600 / 1.000 ft masuk toleransi pada
   sumur yang tidak dilihat model, dengan dan tanpa koreksi bias.

---

## Hal yang perlu diketahui

| Situasi | Yang dilakukan |
|---|---|
| Kotak unggah abu-abu | Pilih Well section dan Well type dulu (langkah 1). |
| "No active model yet" | Latih model di Models dulu, atau hubungi administrator. |
| Forecast berhenti sebelum 300 ft | Hasil WellPlan berakhir di situ; ML butuh WellPlan sebagai input. |
| Kolom "Check against actual" tidak muncul | Tidak ada pembacaan aktual di jendela forecast; isi From depth yang lebih dangkal. |
| Apakah uji saya mengubah ML? | Tidak. Sumur Monitoring tidak pernah dipakai untuk training. |
| Menghapus sumur uji | Monitoring → daftar sumur → **Delete**. |
| Ingin latihan tanpa data client | Pakai file latihan (Quick Start): `data/practice/monitoring` (`make practice-files`). File ini sintetis: cocok untuk mengenal layar, tapi angka akurasinya **tidak** menggambarkan kualitas model. Uji model dengan sumur sungguhan. |
