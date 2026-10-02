# Keputusan dan asumsi

Format: **K-xx — judul**. Status: *asumsi* (perlu dikonfirmasi narasumber/client), *disepakati*,
atau *teknis* (keputusan implementasi). Perbarui status setelah sesi narasumber (Hari 2 & 10).

| ID | Keputusan | Status | Di kode |
|---|---|---|---|
| K-01 | Satuan baku internal SI: m, kN, kN·m, deg, deg/30m. Nilai + satuan asli selalu disimpan. Tampilan default imperial (ft, klbf, ft-lbf), bisa SI. | teknis | `services/units.py` |
| K-02 | Satu baris `wells` = satu sumur pada satu section (satu run WellPlan). Unik per (nama, section). Validasi mengelompokkan per **nama** sumur, jadi section lain dari sumur yang sama tidak bocor ke data latih. | teknis | `db/models.py`, `services/training.py` |
| K-03 | Section dari ukuran lubang (Summary "Hole Size", atau OD bit di sheet BHA, atau nama file "12.25in"), dibulatkan ke 17,5 / 12,25 / 8,5 / 6,125 bila selisih ≤ 0,5 in. Bisa dikoreksi manual. | asumsi | `services/classify.py` |
| K-04 | Tipe sumur dari survey: **Horizontal** bila inklinasi maks ≥ 80°; **S** bila inklinasi maks ≥ 10° dan inklinasi akhir turun ≥ 10° dari maks; selain itu **J** (sumur hampir vertikal < 5° dicatat J dengan peringatan). Klasifikasi memakai survey yang ada di file — untuk file section atas, profil S bisa belum terlihat (terbaca J): koreksi manual. Bila Summary memuat "Well Type", nilai file dipakai. | asumsi — konfirmasi definisi ke narasumber | `services/classify.py` |
| K-05 | Sumber data: laporan WellPlan didahulukan; roadmap (Drag/Torque) hanya dipakai bila laporan tidak punya operasi itu. Data aktual: sheet **T&D Actual Reading** didahulukan; Drilling Data (torque → torque on bottom) dan Tripping Data (POOH → pick up, RIH → slack off) hanya pengganti bila operasi itu tidak ada di T&D Actual Reading. Pembacaan ganda di kedalaman sama dirata-rata. | asumsi | `services/dataset.py` |
| K-06 | Baseline WellPlan = kurva skenario **FF 0,3** (nominal), tidak memakai data aktual untuk memilih FF. Rotating weight tidak bergantung FF. | asumsi — konfirmasi FF desain ke narasumber | `services/operations.py` (`BASELINE_FF`) |
| K-07 | Data kosong: baris tanpa nilai target dibuang; fitur kosong (inklinasi/dogleg tanpa survey) diisi median data latih. Outlier: titik dengan residu (aktual − WellPlan baseline) > 5 × MAD per sumur & operasi dibuang (hanya bila ≥ 8 titik). Semua pembuangan dicatat di "Catatan dataset". Nilai di luar rentang fisik (kedalaman 0–12.000 m, beban −500–10.000 kN, torsi 0–300 kN·m) dibuang saat impor dengan peringatan. | teknis | `services/dataset.py`, `parsers/workbook.py` |
| K-08 | Interpolasi WellPlan ke kedalaman aktual: linear, **tanpa ekstrapolasi** (titik aktual di luar rentang WellPlan dibuang). Prediksi dibuat di grid kedalaman WellPlan mulai dari casing shoe (bila diketahui). FF selain 0,1/0,3/0,5 diinterpolasi linear antar-FF. | teknis | `services/dataset.py` |
| K-09 | MAPE memakai penyebut minimal 5% × median \|aktual\| supaya nilai dekat nol (slack off saat buckling) tidak membuat MAPE meledak. Selisih persen di dashboard memakai aturan yang sama. | teknis | `services/metrics.py`, `services/profile.py` |
| K-10 | Satu model per operasi (5 model). Jenis operasi tidak menjadi fitur karena modelnya terpisah. Fitur: kedalaman, inklinasi, dogleg, WellPlan FF 0,1/0,3/0,5, section, tipe sumur. | teknis | `services/training.py` |
| K-11 | Kandidat per operasi: Ridge (α = 1) dan XGBoost (2 setelan kecil: depth 2/300 pohon, depth 3/200 pohon, lr 0,05), masing-masing dengan target **langsung** atau **selisih terhadap WellPlan**. Dipilih RMSE out-of-fold terkecil. Catatan: pemilihan pada skor OOF yang sama sedikit optimistis; dengan 8 kandidat dampaknya kecil, tetapi disebutkan di laporan. | teknis | `services/training.py` |
| K-12 | Validasi leave-one-well-out (GroupKFold 10 bila > 20 sumur). Kombinasi section × tipe dengan < 3 sumur diberi peringatan. Minimal 3 sumur untuk melatih. Dashboard sumur latih memakai prediksi out-of-fold. | teknis | `services/training.py` |
| K-13 | File roadmap dan file tanpa Summary tidak memuat nama sumur → nama/section diisi di form unggah; bila kosong diambil dari awal nama file (sebelum "_") dan pola "12.25in". | teknis | `services/importer.py` |
| K-14 | Unggahan ulang: checksum sama → tidak diimpor ulang; file baru dengan jenis sama untuk sumur yang sama **menggantikan** data file lama (status "diganti"). | teknis | `services/importer.py` |
| K-15 | Penguncian login dihitung per username (5 gagal dalam 15 menit → kunci 15 menit), plus `limit_req` nginx per IP. Karena hanya satu akun, penyerang bisa mengunci admin sementara; diterima untuk prototype. Ganti password via CLI membuka kunci. | teknis | `api/auth.py`, `cli.py` |
| K-16 | Ambang penandaan interval default 5 (satuan tampilan atau %), bisa diubah di dashboard. Nilai yang disepakati narasumber: ____ | asumsi | `web/src/pages/DashboardPage.tsx` |
| K-17 | Pola nama sheet & kolom (Summary, Tripping Load Analysis, Off Bottom Torque, Survey Outputs, BHA, Drag, Torque, T&D Actual Reading, Drilling Data, Tripping Data) diturunkan dari dokumen proyek, **belum dari file asli**. Sesuaikan `parsers/column_map.py` setelah audit. | asumsi | `parsers/column_map.py` |

## Catatan terbuka (isi setelah sesi narasumber)

- Arti kolom dan satuan yang belum jelas: ____
- Target akurasi yang disepakati bersama client (Pasal 9: tidak ada jaminan angka): ____
