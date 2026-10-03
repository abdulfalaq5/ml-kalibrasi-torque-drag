# Kalibrasi Torque & Drag ML (paket 6 minggu, 16 fitur)

## Tujuan
Mengkalibrasi hasil simulasi torque & drag WellPlan dengan ML berdasarkan data aktual lapangan
40+ sumur. Keluaran: prediksi 5 target per kedalaman (pick up, slack off, rotating weight, torque off
bottom, torque on bottom), gerbang kualitas data, laporan model jujur (validasi per sumur + blind
test), dashboard tiga grafik, batas aman, ekspor Excel dan PDF. Pembanding wajib: WellPlan apa adanya.

## Lingkup 16 fitur
1 impor WellPlan (unggah + impor massal folder) · 2 impor data aktual · 3 validasi & gerbang kualitas
A/B/C · 4 klasifikasi section & tipe + koreksi manual · 5 dataset & fitur · 6 Ridge, XGBoost, Random
Forest, SVR (+MLP opsional) · 7 validasi per kelompok sumur, blind test, kurva belajar · 8 SHAP ·
9 versi model & dataset · 10 prediksi sumur baru · 11 dashboard 3 profil · 12 batas aman & interval ·
13 evaluasi prediksi vs aktual · 14 ekspor Excel · 15 ringkasan PDF · 16 login satu akun admin.
TIDAK: banyak akun/role, REST API untuk sistem lain, what-if, real-time, mobile.

## Data client (folder `Training/`, audit Okt 2026)
- 45 sumur, 94 file, satu file per section. Susunan `Training/<J|S|Horizontal>/<sumur>/<file>`.
- Format A roadmap `.xlsx` (Drag, Torque, T&D Actual Reading) dan format B laporan WellPlan `.xlsm`
  (Summary, Tripping Load Analysis, Off Bottom Torque analysis, Rotary Drill Buckling Outputs,
  Survey Outputs, Drilling Data). Detail di `docs/keputusan.md` K-03..K-06, `parsers/column_map.py`.
- Tes TIDAK memakai data client: fixture dari `scripts/make_sample_data.py` yang meniru kedua format.

## Dashboard
Tiga panel ditumpuk (Hookload, Torque, Selisih), sumbu kedalaman bersama (zoom tersinkron).
WellPlan biru, ML oranye (+ pita 10–90%), Aktual hijau. Selisih: kanan = positif (lebih tinggi).
Sumur latih memakai prediksi out-of-fold.

## Login
Semua endpoint `/api/*` wajib sesi kecuali `/api/health` dan `/api/auth/login`
(`dependencies=[Depends(require_admin)]` di `app/main.py`). Tes `tests/test_auth.py` memeriksa setiap route.

## Perintah
- `make up` / `make down` / `make logs` / `make password`
- `make inbox-training` (Training → data/inbox) · `make inbox-sample` · `make audit`
- `make test` (44 tes) · `make lint`
- Migrasi baru: `cd backend && alembic revision --autogenerate -m "..."` dengan DATABASE_URL Postgres;
  kolom NOT NULL baru wajib `server_default`.

## Aturan data (Pasal 11)
- Jangan mencetak isi data client ke chat; analisis cukup struktur/statistik. Laporan berisi nama
  sumur disimpan di `data/` (di luar Git), bukan `docs/`.
- `Training/`, `data/`, `.env`, model tidak di-commit (`.gitignore`, pre-commit).

## Aturan model
Selalu validasi per kelompok sumur, bandingkan dengan baseline WellPlan, blind test hanya sekali,
tandai kombinasi section × tipe < 3 sumur, laporkan jujur bila ML tidak lebih baik.
Satuan: simpan asli, konversi hanya di `services/units.py`.
