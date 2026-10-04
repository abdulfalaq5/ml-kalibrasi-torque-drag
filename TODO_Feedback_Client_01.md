# TO-DO: Perbaikan dari Feedback Client #1 (4 Okt 2026)

Dokumen kerja internal. Centang `[x]` saat selesai. Setiap butir punya **Selesai bila** sebagai
patokan hasil. Urutan pengerjaan: **P1** dulu (integritas data & memblokir review client), lalu **P2**.

## Ringkasan

| Kode | Pekerjaan | Asal | Prioritas | Status |
|---|---|---|---|---|
| G | **Pisahkan upload Training vs Monitoring** (data monitoring tidak pernah jadi acuan ML) | jawaban #1 | P1 | belum |
| A | Crossplot Model T&D vs Actual = Excel (kurva model terkalibrasi DD) | feedback 2, 5 | P1 | penyebab ditemukan |
| B | Plot standar baku (`Depth`, `PU - OHFF : 0.3`, …) + warna konsisten per OHFF | feedback 1, jawaban #2, #5 | P1 | belum |
| J | Upload: pilih Section & Type dulu; menu Data sumur dengan grouping & filter | jawaban #8 | P1 | belum |
| I | Dashboard: "Semua kurva FF" default ✔, "Uncertainty band" default ✘ | jawaban #7 | P1 | belum |
| C | Teks "What This System Does" di Panduan | feedback 3 | P1 | belum |
| D | **Seluruh aplikasi & keluaran dalam bahasa Inggris** (tanpa pilihan bahasa) | jawaban #3 | P2 | keputusan final |
| H | **Forecast N ft ke depan** (input user, mis. 300 ft) + info sebab-akibat | jawaban #6 | P2 | belum |
| E | Struktur output Excel hasil ML | feedback 4, jawaban #4 | P2 | **menunggu template dari client** |
| F | Sesi GMeet dengan Mas Wahyu + tutorial lebih jelas | feedback 6 | P2 | perlu dijadwalkan |

## Jawaban client (4 Okt 2026)

| No | Pertanyaan | Jawaban | Dampak |
|---|---|---|---|
| 1 | Calibrate ditentukan sebelum/setelah melihat actual? | *Calibrate* adalah koreksi yang ditentukan DD (bukan data actual). File yang diinput adalah sumur yang sudah selesai sampai kedalaman akhir; model pasti tidak sama dengan actual. Yang jadi acuan ML adalah **fitur upload Training sendiri**. Buat **upload Training** (acuan ML) dan **upload Monitoring** (hanya dihitung/diprediksi), **jangan digabung**. | butir G, A |
| 2 | `SO - OHFF : 0.55` = 0.5? | **Ya, 0.5** | butir B |
| 3 | Bahasa | **Bahasa Inggris saja** | butir D |
| 4 | Struktur output Excel ML | **Menunggu template dari client** | butir E ditunda |
| 5 | Standar warna plot | Tidak ada standar perusahaan; **warna per OHFF (0.2/0.3/0.4/0.5) disamakan dan konsisten** | butir B |
| 6 | Prediksi ke depan | **User menginput berapa ft ke depan** (mis. 300 ft), model memprediksi dan memberi **info sebab-akibat** | butir H |
| 7 | Default checkbox dashboard | **"Semua kurva FF" default tercentang, "Pita ketidakpastian" default tidak** | butir I |
| 8 | Alur upload | **User memilih Section dan Type dulu, baru upload**; menu Data sumur ada **grouping & filter** Section dan Type | butir J |

---

## Temuan teknis (file AMPUH0034 (O-O-55B) 8.5", Halliburton)

File: `P_AMPU25_0001 (O-O-55B)_8.50in TnD Roadmap.xlsx` (format A / roadmap).

1. Grafik Excel memplot kolom **"Graph reference"** = WellPlan + offset *Calibrate* dari DD:
   - Drag: `AF = Tripping Out (C) + $C$2` (PU), `AE = Tripping In (B) + $D$2` (SO), `AG = Rotating Off Bottom (G) + $E$2` (ROT); sama untuk OHFF 0.4 (AI/AJ) dan 0.5 (AL/AM).
   - Torque: `W = Rotating On Bottom + $C$2`, `X = Rotating Off Bottom + $C$3` (per OHFF: W/X, Z/AA, AC/AD).
   - Offset sumur ini: **PU +23 klbf, SO 0, ROT +7.5 klbf, Torque On +2650 ft-lbf, Torque Off +2700 ft-lbf.**
2. Sistem saat ini memakai WellPlan mentah (K-05) → kurva model bergeser sebesar offset → crossplot tidak sama.
3. Berlaku luas: **44/48 file roadmap** punya offset hookload ≠ 0 (PU −15 s.d. +33 klbf), **43/48** offset torsi ≠ 0 (−4950 s.d. +3000 ft-lbf). File .xlsm tidak punya offset.
4. **Bug parser**: offset *Torque Off Bottom* tidak terbaca bila label sel A3 tertimpa angka (di file ini A3 = 1650, nilai 2700 di C3).
5. **Risiko pencampuran data (butir G)**: saat ini file dari "Prediksi sumur baru" masuk tabel sumur yang sama dengan data latih. Bila kemudian berisi data actual dan lolos gerbang kualitas, file itu **ikut masuk dataset berikutnya**. Harus dipisah.

---

## P1

### G. Pisahkan upload Training vs Monitoring (jawaban #1) — **paling penting**

Prinsip: **Training** = sumur historis yang sudah selesai dibor, satu-satunya acuan ML.
**Monitoring** = sumur yang sedang/akan dibor; hanya dihitung dan diprediksi, **tidak pernah** dipakai
melatih model, tidak ikut dataset, tidak ikut statistik pembanding "sumur sekelas".

Data & backend
- [x] Kolom `purpose` (`training` | `monitoring`) di tabel `wells` dan `uploaded_files` + migrasi Alembic
      (`server_default 'training'` untuk data lama — semua 94 file Training sekarang = training)
- [x] Unik per (nama, section, **purpose**): sumur yang sama boleh ada di kedua kelompok tanpa saling menimpa
- [x] `POST /api/files` wajib parameter `purpose`; impor tidak pernah memindahkan file antar kelompok
- [x] Pindai folder (`data/inbox`) = **training saja** *(folder `data/inbox-monitoring` opsional belum dibuat)*
- [x] `services/dataset.py` (`build_dataset`, `freeze_dataset`), `services/quality.py`
      (`eligible_well_ids`, `recompute_all`, banding sesama kelas) hanya memakai `purpose = training`
- [x] Gerbang kualitas tetap dijalankan untuk monitoring (sebagai informasi), tapi status-nya tidak
      membuat sumur masuk training
- [x] Monitoring: upload ulang file yang sama (mis. data actual bertambah saat pengeboran) = versi baru
      sumur monitoring itu → evaluasi prediksi vs actual otomatis (menu Evaluation), tetap di monitoring
- [x] (Konfirmasi client) Tombol eksplisit **"Promote to training"** setelah sumur monitoring selesai dibor:
      menyalin data ke kelompok training (lewat gerbang kualitas), hanya oleh admin, tercatat siapa/kapan.
      *(Selesai: `POST /api/wells/{id}/promote`, sumber file `promote` + waktu; tetap dikonfirmasi di GMeet)*
      Tanpa tombol ini, data monitoring tidak pernah masuk training
- [x] Tes: unggah file monitoring berisi data actual berstatus A → bekukan dataset → sumur itu **tidak**
      ada di dataset; jumlah baris dan hash dataset tidak berubah

UI
- [x] Menu Data sumur dibagi dua tab/halaman: **Training Data** (upload training, pindai folder, daftar sumur
      training, kualitas) dan **Monitoring** (upload monitoring, daftar sumur monitoring, forecast)
- [x] Label jelas di setiap upload: "Files uploaded here become the ML reference" vs
      "Files uploaded here are only calculated/forecast; they never change the ML reference"
- [x] Dashboard, Evaluation, export: tanda kelompok (Training / Monitoring) pada setiap sumur
- [x] Panduan: jelaskan perbedaan kedua upload

**Selesai bila:** data monitoring terbukti tidak pernah masuk dataset/training (tes otomatis), kedua upload
terpisah di UI, dan client menyetujui alurnya.

### A. Crossplot Model T&D vs Actual = Excel (feedback 2, 5; jawaban #1)
- [x] Perbaiki pembacaan baris *Calibrate* Torque per posisi (baris 2 = On, baris 3 = Off, kolom C), tidak
      bergantung label kolom A (`parsers/roadmap.py` → `_parse_torque_calibration()`)
- [x] Simpan kurva **Model T&D calibrated** per OHFF (= rumus Excel: WellPlan + Calibrate) di samping WellPlan
      mentah; pastikan hasil identik dengan kolom "Graph reference"
- [x] Dashboard: pilihan kurva **"T&D Model (calibrated, as Excel)"** dan **"T&D Model (raw WellPlan)"**;
      bawaan roadmap = calibrated
- [x] Difference dan metrik "Model vs Actual" bisa terhadap model calibrated
- [x] Peran *Calibrate* di ML (sesuai jawaban #1: koreksi dari DD, dicatat sebagai **fitur tersendiri**):
  - [x] Simpan offset *Calibrate* sebagai fitur terpisah (`cal_pu`, `cal_so`, `cal_rot`, `cal_ton`, `cal_toff`)
  - [x] Uji manfaatnya lewat uji fitur yang sudah ada (dipakai hanya bila error turun ≥ 1%) dan bandingkan pada blind test
  - [x] File .xlsm (tanpa *Calibrate*) dan sumur monitoring tanpa *Calibrate* → fitur kosong ditangani (imputasi + indikator)
  - [ ] Konfirmasi di GMeet: untuk sumur **monitoring**, apakah *Calibrate* sudah diisi DD sebelum/selama
        pengeboran? Bila tidak tersedia saat forecast, fitur ini tidak dipakai
- [x] Tes: fixture sintetis bertata letak sama (termasuk A3 berisi angka) → nilai calibrated di 5 kedalaman
      sama persis dengan kolom AF/AJ/AM dan W/X/Z/AA/AC/AD
- [ ] Cek visual berdampingan dengan grafik Excel client *(cek angka sudah: 618/624 kolom Graph reference dari 48 file
      cocok persis, AMPUH0034 13/13 kolom selisih 0,000; 1 file memakai rumus DD non-standar; review visual oleh client)*: AMPUH0034 8.5" (Drag Pick Up, Slack Off, Combined,
      Torque On/Off Bottom) + 2 sumur roadmap lain
- [x] Revisi keputusan K-05 di `docs/keputusan.md`

**Selesai bila:** untuk AMPUH0034 8.5", kurva model dan titik actual di dashboard tumpang tepat dengan
grafik Excel client untuk hookload dan torque.

### B. Plot standar baku + warna konsisten (feedback 1; jawaban #2, #5)
- [x] Sumbu kedalaman: **`Depth (ft)`**
- [x] Nama seri hookload: **`PU - OHFF : 0.3`, `PU - OHFF : 0.4`, `PU - OHFF : 0.5`, `SO - OHFF : 0.3`,
      `SO - OHFF : 0.4`, `SO - OHFF : 0.5`**, `ROT` (satu kurva), `PU Actual`, `SO Actual`, `ROT Actual`,
      `PU - ML`, `SO - ML`, `ROT - ML`
- [x] Nama seri torsi: `Torque On Bottom - OHFF : x`, `Torque Off Bottom - OHFF : x`, `… Actual`, `… - ML`
- [x] Nilai OHFF dari file (0.1/0.3/0.5, 0.3/0.4/0.5, 0.2–0.5), tidak dipaksa
- [x] **Satu warna tetap per nilai OHFF** di semua grafik dan semua sumur (mis. 0.1, 0.2, 0.3, 0.4, 0.5 masing-
      masing satu warna), PU/SO dibedakan gaya garis; Actual = titik; ML = garis tebal satu warna
      *(PU/SO dibedakan nama + posisi seperti Excel client; garis putus-putus dipakai untuk band P10–P90)*
- [x] Validasi palet warna (pembeda untuk buta warna) sebelum dipakai
- [x] (Konfirmasi tampilan) batas atas/bawah ML ditampilkan sebagai **garis putus-putus** (bukan arsiran);
      batas manual (Operating limits) atas/bawah sebagai **garis titik-titik**
- [x] Terapkan sama di grafik ekspor Excel dan PDF

**Selesai bila:** dashboard, Excel, dan PDF memakai label, nama seri, dan warna per OHFF yang sama, dan
client menyetujui tampilan satu sumur contoh.

### J. Upload dengan Section & Type wajib + grouping/filter Data sumur (jawaban #8)
- [x] Form upload (Training dan Monitoring): **Section** dan **Well type** wajib dipilih dulu; tombol/area
      upload aktif setelah keduanya dipilih
- [x] Nilai pilihan user menjadi sumber utama; bila berbeda dengan isi file/nama file → peringatan di hasil impor
- [x] Pindai folder tetap memakai struktur folder (`<J|S|Horizontal>/<well>/`) dan nama file untuk section
- [x] Menu Data sumur: **grouping** per Section dan per Type (bisa dilipat, jumlah sumur per grup) + **filter**
      Section, Type, Data quality, Purpose; berlaku juga di Riwayat impor

**Selesai bila:** upload tidak bisa dilakukan tanpa memilih Section & Type, dan daftar sumur bisa
dikelompokkan serta disaring.

### I. Default checkbox dashboard (jawaban #7)
- [x] "Semua kurva FF" / *All OHFF curves* → **default tercentang**
- [x] "Pita ketidakpastian ML" / *Uncertainty band* → **default tidak tercentang**

**Selesai bila:** saat dashboard pertama dibuka, ketiga kurva OHFF tampil dan band tidak tampil.

### C. Teks "What This System Does" di Panduan (feedback 3)
- [x] Judul topik: **"What This System Does"**; ringkasan: *A brief overview of the system, the data used,
      and the workflow from historical data to Torque & Drag forecasting.*
- [x] Paragraf pembuka diganti teks client apa adanya (T&D model & actual dari DD; ML mempelajari hubungan
      model vs actual dari sumur historis dan menghasilkan forecast pada kedalaman berikutnya)
- [x] Diagram alur topik itu disesuaikan: historical data (Training) → ML → T&D forecast (Monitoring)

**Selesai bila:** topik pertama How-to Guide memuat teks client apa adanya.

---

## P2

### D. Seluruh aplikasi dan keluaran dalam bahasa Inggris (jawaban #3 — tanpa pilihan bahasa)
- [x] Glosarium istilah (dikirim ke client untuk disetujui):

| Sekarang | Bahasa Inggris |
|---|---|
| Data sumur | **Well Data** (tab *Training Data* / *Monitoring*) |
| Kualitas data: Layak / Layak + peringatan / Ditahan / Dikecualikan | **Data Quality: Accepted / Accepted with warnings / On hold / Excluded** |
| Kedalaman | **Depth** |
| WellPlan | **T&D Model** |
| Aktual | **Actual** |
| Prediksi ML | **ML Forecast** |
| Pita ketidakpastian ML (10–90%) | **Uncertainty band (P10–P90)** |
| Selisih | **Difference (Δ)** |
| Batas aman | **Operating limits** |
| Out-of-fold | **Unseen-well validation** |
| Pindai folder · Bekukan dataset · Latih model | **Scan folder · Freeze dataset · Train model** |
| Sumur-section | **Well section** |
| Evaluasi | **Evaluation** |
| Panduan | **How-to Guide** |

- [x] Terapkan di UI (`web/src/**`), How-to Guide (`web/src/help/content.tsx`), pesan API & validasi
      (`backend/app/**`), ekspor Excel (`services/export.py`), PDF (`services/pdf.py`), template
      (`services/templates.py`), nama sheet & kolom template
- [x] Format angka: titik sebagai desimal, pemisah ribuan koma
- [x] Dokumen untuk client (panduan pengguna) dalam bahasa Inggris; dokumen internal boleh tetap Indonesia

**Selesai bila:** tidak ada teks berbahasa Indonesia di layar dan keluaran.

### H. Forecast N ft ke depan + sebab-akibat (jawaban #6)
Untuk sumur **Monitoring** yang sedang dibor (sudah ada actual sampai kedalaman sekarang) atau sumur baru.
- [x] Input user: **Forecast distance (ft)** (mis. 300 ft) dan kedalaman awal (bawaan = kedalaman actual
      terakhir, atau puncak section bila belum ada actual)
- [x] Syarat: rencana T&D Model (WellPlan) harus mencakup sampai kedalaman tujuan; bila tidak → pesan jelas
- [x] Forecast per kedalaman (mis. tiap 30 ft / per stand) untuk PU, SO, ROT, Torque On/Off: ML Forecast,
      P10–P90, dan T&D Model per OHFF
- [x] (Opsional, perlu diuji) koreksi berdasarkan selisih actual terakhir sumur itu (bias lokal dari titik
      actual terdekat) — hanya untuk tampilan forecast, **tidak** mengubah model training
- [x] **Info sebab-akibat** per interval forecast:
  - [x] Faktor terbesar yang menaikkan/menurunkan forecast (kontribusi SHAP lokal per fitur: inklinasi,
        dogleg/tortuosity, panjang open hole, kedalaman, nilai model per OHFF)
  - [x] Perubahan rencana di interval itu (build/drop/tangent, kenaikan DLS, masuk open hole)
  - [x] Peringatan bila forecast atau P90 menyentuh Operating limits, dengan kedalaman perkiraannya
  - [x] Ringkasan kalimat otomatis, mis. *"PU rises 18 klbf over the next 300 ft, mainly due to inclination
        increasing from 32° to 41° (build section). P90 reaches the 250 klbf limit at 6,420 ft."*
- [x] Tampil di dashboard (zona forecast diarsir di ketiga panel) dan bisa diekspor (Excel/PDF)
- [x] Tes: forecast 300 ft pada sumur contoh menghasilkan titik sampai +300 ft dan penjelasan per interval

**Selesai bila:** user bisa memasukkan jarak forecast, melihat forecast + rentang + penjelasan sebab-akibat,
dan mengekspornya.

### E. Struktur output Excel hasil ML (feedback 4) — **ditunda, menunggu template client**
- [x] Terima template dari client *(4 Okt 2026: `OUTPUT xxx 8.5'' Multiple T&D Road Map.xls`)*
- [x] Petakan kolom template ↔ data sistem; catat kolom yang belum tersedia *(K-42: surface torque saat tripping, satu mud weight per file)*
- [x] Yang sudah disepakati: **ROT cukup 1 kolom** (tanpa OHFF); OHFF 0.5 (bukan 0.55)
- [ ] Usulan untuk didiskusikan: PU/SO per OHFF (raw & calibrated), kolom ML + P10/P90, **ML-equivalent OHFF**
      per kedalaman (friction factor yang membuat model T&D = forecast ML)
- [x] Implementasi sesuai template *(`services/output_workbook.py`; dibuka di LibreOffice tanpa galat — uji di Microsoft Excel oleh client)*

**Selesai bila:** file output sesuai template client dan disetujui tertulis.

### F. Sesi GMeet dengan Mas Wahyu + tutorial (feedback 6)
- [ ] Jadwalkan GMeet (±60–90 menit), sebaiknya setelah G, A, B, J, I selesai
- [ ] Akses: subdomain `dev-ml-kalibrasi-torque-rag.lokatali.my.id` aktif, atau demo lewat share screen
- [ ] Agenda:
  1. Alur besar: Training data → Data quality → Model → Monitoring → Forecast → Output
  2. Praktik upload **Training** dan **Monitoring** (pilih Section & Type dulu) oleh Mas Wahyu sendiri
  3. Membaca Data Quality dan alasan status
  4. Monitoring: forecast N ft + sebab-akibat, membaca dashboard (crossplot calibrated, ML, band)
  5. Ekspor Excel/PDF
  6. Konfirmasi: tombol "Promote to training", ketersediaan *Calibrate* untuk sumur monitoring, tampilan
     garis batas (putus-putus / titik-titik)
- [x] File latihan (Training + Monitoring) dan checklist 1 halaman *(`make practice-files`; checklist = topik Quick Start)*
- [ ] Rekam sesi (dengan izin) sebagai video tutorial
- [x] How-to Guide: topik **Quick Start** (login → upload → forecast → output) dan perjelas bagian upload
- [ ] Catat umpan balik sesi dalam satu daftar tertulis (feedback #2)

**Selesai bila:** Mas Wahyu bisa upload dan menghasilkan output sendiri tanpa bantuan.

---

## Setelah semua selesai
- [x] Tes otomatis + uji alur penuh di Docker (Training dan Monitoring terpisah) *(55 tes; uji HTTP di Docker 4 Okt)*
- [x] Perbarui `README.md`, `docs/panduan.md`, `docs/ALUR_DAN_KODE.md`, `docs/keputusan.md`
- [x] Bekukan dataset & latih ulang bila fitur *Calibrate* (butir A) lolos uji manfaat; jalankan blind test model baru
      *(dataset v2, model #5 aktif, Calibrate lolos +37,4%; blind test: ML belum lebih baik dari "T&D + Calibrate" — lihat K-37)*
- [ ] Kirim ringkasan perubahan ke client; minta review ulang crossplot AMPUH0034 8.5" + garis ML

## Pertanyaan terbuka (untuk GMeet)
1. Perlu tombol **"Promote to training"** (memindahkan sumur monitoring yang sudah selesai dibor ke Training secara eksplisit)?
2. Untuk sumur **monitoring**, apakah angka *Calibrate* sudah diisi DD saat forecast dibuat?
3. Tampilan batas: batas atas/bawah ML = garis putus-putus, batas manual = garis titik-titik — sudah sesuai?
4. Interval titik forecast: tiap 30 ft, per stand (~93 ft), atau 100 ft?
5. Template output Excel (butir E) — kapan dikirim?
