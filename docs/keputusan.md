# Keputusan dan asumsi

Format: **K-xx — keputusan**. Status: *asumsi* (konfirmasi narasumber/client), *dari data*
(diturunkan dari audit 94 file folder Training, Okt 2026), atau *teknis* (keputusan implementasi).

## Data dan format

| ID | Keputusan | Status | Di kode |
|---|---|---|---|
| K-01 | Satuan baku internal SI: m, kN, kN·m, deg, deg/30m. Nilai + satuan asli selalu disimpan. Tampilan bawaan imperial (ft, klbf, ft-lbf). | teknis | `services/units.py` |
| K-02 | Satu baris `wells` = satu sumur pada satu section (satu file). Validasi mengelompokkan per **nama sumur** (= nama folder), jadi section lain dari sumur yang sama tidak bocor ke data uji. | teknis | `db/models.py`, `services/training.py` |
| K-03 | Section dari **nama file** (`8.5in`, `8.50_in`, `12.25 HS`, `22inHS`, `17.25 HS`→17,5"). Urutan cadangan: diameter wellbore Summary (B), OD bit, `Section:` di sheet aktual. Nilai di sheet aktual **tidak andal** (3 file lateral 8,5" tertulis 12-1/4") → hanya peringatan. Section standar: 26, 22, 17,5, 12,25, 8,5, 6,125 (toleransi 0,4"). | dari data | `parsers/workbook.py`, `services/classify.py` |
| K-04 | Tipe sumur dari **folder induk** (`J/`, `S/`, `Horizontal/`), sesuai susunan Training. Tanpa folder tipe: dari survey (Horizontal ≥ 80°, S = build-hold-drop ≥ 10°, sisanya J). Survey section atas sumur horizontal terbaca J — wajar, folder yang dipakai. | dari data | `services/importer.py` |
| K-05 | Format A (roadmap): rencana mentah dari blok `Drag`/`Torque` sebelum kolom "Graph reference"; `Tripping Out`=pick up, `Tripping In`=slack off, `Rotating Off Bottom`=rotating weight; torsi `Rotating On/Off Bottom`. Aktual dari `T&D Actual Reading`. Sheet `Casing Shoe` diabaikan. **Revisi (feedback client #1):** offset **Calibrate** DD dibaca — Drag baris 1 label (`PICK UP`/`SLACK OFF`/`ROTATE`, kolom B–D atau C–E) + baris 2 nilai; Torque **menurut posisi**: baris "Calibrate On Bot Torque" kolom C = on bottom, baris tepat di bawahnya kolom C = off bottom (label baris itu tertimpa angka di 3 file). Kurva "Graph reference" Excel = mentah + offset; aplikasi menghitungnya sendiri (cocok persis di 47/48 file; 1 file memakai rumus DD non-standar dengan koreksi tambahan). Calibrate = koreksi DD, **bukan** data aktual. | dari data + client | `parsers/roadmap.py`, `services/calibration.py` |
| K-05b | Format B (laporan WellPlan): `CSG x OPH y Trip IN/Out` → FF = OPH; `Rotate Off Bottom`; `Off Bottom Torque analysis`; torque on bottom dari `Surface Torque` di `Rotary Drill Buckling Outputs` (hanya Base FF, mis. OPH rot 0,4). Aktual dari `Drilling Data` (header tanpa satuan: beban klbf; torsi kft-lbf bila nilai < 100); `Tripping  Data` hanya pengganti bila operasi itu tidak ada di Drilling Data. | dari data | `parsers/wellplan_report.py`, `services/dataset.py` |
| K-06 | Skenario FF berbeda antar file ({0,1;0,3;0,5}, {0,3;0,4;0,5}, {0,2..0,5}, satu file 0,35). FF **0,3 dan 0,5 ada di semua file** → fitur `wp_ff03`, `wp_ff05`, kemiringan `(wp_ff05-wp_ff03)/0,2`. Baseline WellPlan = FF 0,3 (torque on bottom format B = Base FF). | dari data + asumsi | `services/dataset.py`, `services/operations.py` |
| K-07 | Titik aktual non-fisik (hookload ≤ 0, torsi < 0) dibuang. Titik di luar rentang WellPlan dibuang (tanpa ekstrapolasi). Outlier residu > 5 MAD per sumur & operasi dibuang (≥ 8 titik). Semua tercatat di "Catatan dataset". | teknis | `services/dataset.py` |
| K-08 | Rencana roadmap jarang (3–28 titik, ~tiap 1000 ft): interpolasi linear ke kedalaman aktual; grid prediksi dirapatkan tiap 100 ft. Grid dimulai dari casing shoe. | dari data | `services/dataset.py` |
| K-09 | MAPE dan selisih persen memakai penyebut minimal 5% × median \|nilai\|. | teknis | `services/metrics.py` |
| K-13 | Nama sumur: folder (impor massal) > form unggah > `Well:` di file > awalan nama file. | teknis | `services/importer.py` |
| K-14 | Impor idempoten: checksum sama → tidak diimpor dua kali; file baru untuk sumur-section sama → versi baru menggantikan yang lama. | teknis | `services/importer.py` |
| K-17 | Pola nama sheet/kolom di `parsers/column_map.py` diturunkan dari audit 94 file. Varian baru: tambahkan pola di sana. | dari data | `parsers/column_map.py` |
| K-18 | Format A tidak punya kedalaman casing shoe (sheet `Casing Shoe` tidak berisi shoe): dipakai **puncak rencana section** sebagai pendekatan shoe section sebelumnya. Format B: kumulatif casing di tabel wellbore. | dari data + asumsi | `services/importer.py` |

## Gerbang kualitas data

| ID | Keputusan | Status | Di kode |
|---|---|---|---|
| K-19 | Minimal **8 titik aktual pick up di dalam rentang WellPlan** (usul TODO). Di Training, 6 section (umumnya 17,5") punya 5–7 titik → status C. Bisa diterima lewat tinjauan engineer. | asumsi — sepakati dengan client | `services/quality.py` |
| K-20 | Cek satuan: rasio median aktual/WellPlan hookload di luar 0,33–3 → kritis. Torsi: hanya faktor ~1000 (< 0,01 atau > 100) yang kritis; di luar 0,33–3 → peringatan, karena torsi section dangkal sangat kecil dan asumsi bit torque WellPlan (DTOR) berbeda dari lapangan. | dari data | `services/quality.py` |
| K-21 | Urutan slack off ≤ rotating ≤ pick up: toleransi max(2 klbf, 3%); > 25% kedalaman melanggar → kritis. `Tripping Data` tidak dihitung pada cek urutan kedalaman (tercatat dari dalam ke dangkal). | teknis | `services/quality.py` |
| K-22 | Peringatan statistik dibandingkan dengan sumur sekelas (section × tipe, ≥ 4 sumur pembanding), z robust (MAD) > 3,5. Skor = 100 − 25 × kritis − 8 × peringatan. | teknis | `services/quality.py` |
| K-23 | Tinjauan engineer: `accept` (C→B), `exclude` (X), `fix` (tetap C). Riwayat tidak dihapus; yang berlaku keputusan terakhir. | teknis | `services/quality.py` |

## Dataset, model, dan validasi

| ID | Keputusan | Status | Di kode |
|---|---|---|---|
| K-10 | Satu model per operasi (5 target). Fitur dasar: kedalaman, WellPlan FF 0,3/0,5, kemiringan FF, rencana rotating weight, section, tipe, format file. | teknis | `services/training.py` |
| K-11 | Kandidat: Ridge (α 1/10), XGBoost (2 setelan), Random Forest (2 setelan), SVR (C 10/100), MLP opsional; target langsung atau selisih terhadap WellPlan. Dipilih RMSE validasi silang terkecil (sedikit optimistis; karena itu blind test terpisah). | teknis | `services/training.py` |
| K-12 | Validasi silang **GroupKFold 5 per nama sumur**. Kombinasi section × tipe < 3 sumur → peringatan. Minimal 5 sumur latih. Dashboard sumur latih memakai prediksi out-of-fold dari model fold yang sama. | teknis | `services/training.py` |
| K-24 | Grup fitur tambahan diuji (ablation, XGBoost) dan **hanya dipakai bila skor turun ≥ 1%**. Pada data Training: hanya grup *survey* yang lolos. Format A tidak punya survey/BHA/mud → fitur kosong diisi median + indikator kosong. | dari data | `services/training.py` |
| K-25 | Model per kombinasi section × tipe hanya dicoba bila ≥ 10 sumur, dipakai bila RMSE ≥ 2% lebih baik dari model tunggal. | teknis | `services/training.py` |
| K-26 | Versi dataset: snapshot CSV gz + SHA-256 + daftar sumur (dan checksum file). Setiap model mencatat `dataset_id`. Hash berubah bila isi berubah. | teknis | `services/dataset.py` |
| K-27 | **Blind test**: ~20% sumur per tipe (seed 42), dikunci saat dataset pertama dibekukan, berlaku untuk dataset berikutnya. Hanya bisa dijalankan sekali per model. Buka kunci hanya dengan konfirmasi tertulis ("UNLOCK"; "BUKA KUNCI" lama tetap diterima). | teknis | `services/dataset.py`, `services/training.py` |
| K-28 | Model baru dibandingkan dengan model aktif memakai rasio rata-rata RMSE ML / RMSE WellPlan; lebih buruk > 1% → **ditahan**. | teknis | `services/training.py` |
| K-29 | Uncertainty band (P10–P90) = kuantil 10% dan 90% residu out-of-fold per operasi (lebar tetap). Ditampilkan sebagai dua garis putus-putus (bukan arsiran); bawaan dashboard: tidak dicentang. | teknis | `services/training.py` |
| K-30 | SHAP (TreeExplainer/LinearExplainer) untuk model pohon dan Ridge; permutation importance untuk SVR/MLP. Untuk target selisih, wajar bila fitur geometri/kedalaman dominan. Fitur `plan_format` penting di beberapa operasi → ada perbedaan sistematis roadmap vs laporan WellPlan. | dari data | `services/training.py` |

## Aplikasi

| ID | Keputusan | Status | Di kode |
|---|---|---|---|
| K-15 | Penguncian login per username (5 gagal / 15 menit) + `limit_req` nginx. | teknis | `api/auth.py` |
| K-16 | Ambang penandaan interval bawaan 5 (satuan tampilan atau %), dapat diubah. | asumsi | `web/src/pages/DashboardPage.tsx` |
| K-31 | Batas aman per sumur menimpa batas per section untuk operasi + jenis yang sama. Kedalaman "menyentuh" = perpotongan linear pertama. | teknis | `services/limits.py` |
| K-32 | Impor massal dari folder dipicu tombol (bukan pemantau otomatis); file diubah < 60 detik dilewati. Catatan lingkup: proposal menyebut "unggah" → penyesuaian kecil pada fitur 1, perlu dicatat tertulis. | teknis | `services/inbox.py` |

## Perubahan dari feedback client #1 (4 Okt 2026)

| ID | Keputusan | Status | Di kode |
|---|---|---|---|
| K-33 | Data dipisah menurut `purpose`: **training** (sumur historis, satu-satunya acuan ML) dan **monitoring** (sumur yang akan/sedang dibor; diprediksi & dievaluasi saja). Kunci unik sumur = (nama, section, purpose). Dataset, matriks, pembanding statistik kualitas, dan impor folder hanya training. Monitoring tidak pernah masuk dataset walau kualitasnya A. | client | `db/models.py`, `services/quality.py`, `services/dataset.py` |
| K-34 | **Promote to training**: salin file versi terakhir sumur monitoring sebagai sumur training baru (melewati gerbang kualitas). Sumur monitoring tetap ada. | usulan — konfirmasi GMeet | `api/wells.py` |
| K-35 | Unggah wajib memilih purpose, **Well section** dan **Well type**; pilihan pengguna didahulukan atas isi file (beda → peringatan). Impor folder tetap dari nama folder/file. | client | `api/files.py`, `services/importer.py` |
| K-36 | Kurva WellPlan dashboard/ekspor: bawaan **dengan offset Calibrate DD** bila file punya offset ≠ 0 (sama dengan crossplot Excel), bisa diganti "As modelled". Metrik dashboard memakai kurva yang ditampilkan; metrik model (training) tetap terhadap WellPlan mentah. | client | `services/profile.py` |
| K-37 | Offset Calibrate juga grup fitur `calibration` (`dd_calibration` = offset operasi baris itu; file .xlsm kosong → median + indikator). Dipakai hanya bila lolos uji manfaat ≥ 1% (K-24). **Hasil dataset v2 (4 Okt 2026):** grup ini lolos (+37,4%), model #5 rasio ML/T&D 0,714 → 0,453. **Catatan jujur:** pada sumur blind yang punya Calibrate, ML (RMSE PU 19,2 kN) belum lebih baik dari kurva *T&D model + Calibrate* saja (18,1 kN); pola sama di semua operasi. Artinya sebagian besar perbaikan berasal dari offset DD, yang kemungkinan diisi setelah melihat data aktual sumur itu. Nilai tambah ML ada pada sumur tanpa Calibrate (laporan .xlsm) dan sebelum DD mengisi Calibrate → tanyakan di GMeet kapan Calibrate diisi; pertimbangkan pembanding "T&D + Calibrate" di laporan model. | client + teknis | `services/dataset.py` |
| K-38 | Nama seri baku: `PU - OHFF : 0.3`, `SO - OHFF : 0.5`, `ROT` (satu kurva, OHFF baseline), `Torque On/Off Bottom - OHFF : x`; sumbu `Depth (ft)`. Satu warna tetap per OHFF di semua grafik (ramp biru ordinal 0,1→0,5, tervalidasi): 0,1 `#86b6ef`, 0,2 `#5598e7`, 0,3 `#2a78d6`, 0,4 `#1c5cab`, 0,5 `#104281`. ML oranye, aktual hijau, band putus-putus, batas operasi titik-titik merah. Bawaan: "All OHFF curves" dicentang. | client | `services/operations.py`, `web/src/components/chartTheme.ts` |
| K-39 | Forecast N ft: mulai dari kedalaman aktual terakhir (atau puncak rencana), langkah 30 ft, berhenti di akhir rencana WellPlan (ML butuh WellPlan sebagai input). Koreksi bias lokal opsional = median (aktual − ML) dari ≤ 10 titik aktual terakhir dalam 1.000 ft, minimal 3 titik; tampilan saja. Penjelasan: perubahan kontribusi SHAP antara awal–akhir jendela (Ridge: kontribusi linear; SVR/MLP: tukar fitur), perubahan rencana dari survey, batas yang terlewati, kalimat otomatis. | client + teknis | `services/forecast.py` |
| K-40 | Seluruh layar dan keluaran (Excel, PDF, template, pesan API) berbahasa Inggris; kode status di database juga Inggris (migrasi 0004). Glosarium: WellPlan → **T&D Model** pada label kurva/metrik; out-of-fold → **unseen-well validation**. Template baru: sheet `Instructions`/`Well Info`/`Example …`; template lama (`Info Sumur`) tetap terbaca. Dokumen internal boleh tetap Indonesia. | client | semua |
| K-41 | ROT di ekspor Excel satu kolom (tanpa OHFF). Struktur output Excel lainnya menunggu template client. | client | `services/export.py` |

## Catatan terbuka (isi setelah sesi narasumber)

- Konfirmasi minimum 8 titik aktual (K-19) dan perlakuan section 17,5" yang titiknya sedikit.
- Konfirmasi baseline FF 0,3 (K-06) dan asumsi bit torque WellPlan vs lapangan (K-20).
- Batas aman resmi per section (torsi top drive, kapasitas hookload, slack off minimum).
- Target keberhasilan relatif yang disepakati client: ____
- GMeet: tombol Promote to training (K-34), Calibrate untuk sumur monitoring, gaya garis band/batas, langkah forecast (30 ft / per stand / 100 ft), template output Excel (K-41).
