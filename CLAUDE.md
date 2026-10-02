# Kalibrasi Torque & Drag ML (prototype 3 minggu)

## Tujuan
Mengkalibrasi hasil simulasi torque & drag WellPlan dengan ML berdasarkan data aktual lapangan.
Masukan: laporan WellPlan (.xlsx/.xlsm) + sheet data aktual. Keluaran: prediksi 5 target per
kedalaman (pick up, slack off, rotating weight, torque off bottom, torque on bottom), dashboard
tiga grafik, dan ekspor Excel. Pembanding wajib: WellPlan apa adanya (baseline).

## Lingkup
8 fitur sesuai perjanjian (impor, validasi, klasifikasi section/tipe, model Ridge + XGBoost,
validasi model, prediksi sumur baru, dashboard 3 grafik, ekspor Excel) + **login satu akun admin**.
TIDAK dikerjakan: banyak akun/role/manajemen pengguna, Random Forest, SVR, MLP, SHAP, versi
model, pelatihan ulang otomatis, evaluasi pasca-sumur, PDF, REST API untuk sistem lain, what-if,
real-time, mobile app.

## Dashboard
Tiga grafik berdampingan dengan sumbu kedalaman bersama (terbalik, 0 di atas): Hookload, Torque,
Selisih. Warna tetap: WellPlan biru, ML oranye, Aktual hijau (titik). Grafik Selisih: A − B,
kanan = positif (lebih tinggi), kiri = negatif (lebih rendah), garis nol di tengah. Sumur latih
memakai prediksi **out-of-fold**.

## Login
Semua endpoint `/api/*` wajib sesi kecuali `/api/health` dan `/api/auth/login`
(dipasang lewat `dependencies=[Depends(require_admin)]` di `app/main.py`). Jangan menambah akun
atau role. Tes `backend/tests/test_auth.py` memeriksa setiap route.

## Stack dan perintah
- Backend: FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, pandas, scikit-learn, XGBoost.
- Frontend: React + Vite + TypeScript, Plotly.js (`web/`), di-build ke `backend/static` lewat Dockerfile.
- `make up` / `make down` / `make logs` — Docker Compose
- `make test` — pytest (SQLite sementara, tanpa Docker)
- `make lint` — ruff
- `make sample` — buat data sintetis di `data/sample/`
- `make dev-api` + `make dev-web` — pengembangan lokal (Vite proxy `/api` ke :8000)
- Migrasi baru: `cd backend && alembic revision --autogenerate -m "..."` (dengan DATABASE_URL Postgres)

## Aturan data (Pasal 11)
- JANGAN membaca atau mencetak isi folder `data/`, `uploads/`, `models/` ke chat.
- Pakai file sintetis (`scripts/make_sample_data.py`) atau salinan anonim (`scripts/anonymize_files.py`).
- Jangan commit data, `.env`, atau model. Fixture tes hanya data sintetis.
- Jangan unggah file client ke server sebelum login aktif dan HTTPS berjalan.

## Aturan satuan
Simpan nilai + satuan asli; konversi hanya di `backend/app/services/units.py`.
Satuan baku internal SI: m, kN, kN·m, deg, deg/30m. Tampilan default imperial (ft, klbf, ft-lbf).

## Aturan validasi model
Selalu validasi per kelompok sumur (leave-one-well-out / GroupKFold), bandingkan dengan baseline
WellPlan, tandai kombinasi section × tipe dengan < 3 sumur. Laporkan jujur bila ML tidak lebih baik.

## Keputusan
Semua asumsi dicatat di `docs/keputusan.md` (K-xx). Pola nama sheet/kolom di
`backend/app/parsers/column_map.py` — sesuaikan setelah audit data.
