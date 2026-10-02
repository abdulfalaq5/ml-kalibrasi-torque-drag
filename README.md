# Prototype Sistem Kalibrasi Torque & Drag ML

Aplikasi web untuk mengimpor laporan WellPlan + data aktual, melatih model kalibrasi
(Ridge / XGBoost, divalidasi per sumur), memprediksi sumur baru, menampilkan dashboard tiga
grafik (Hookload, Torque, Selisih), dan mengekspor Excel. Satu akun admin.

- Rencana kerja: `TODO_Prototype_3_Minggu.md`
- Tools & arsitektur: `TOOLS_dan_Arsitektur.md`
- Keputusan & asumsi: `docs/keputusan.md`
- Panduan pengguna & operasional: `docs/panduan.md`
- Konteks untuk Claude Code: `CLAUDE.md`

## Mulai cepat (laptop)

```bash
cp .env.example .env            # isi password, SECRET_KEY, ADMIN_*; set APP_ENV=development dan COOKIE_SECURE=false untuk http lokal
docker compose up -d --build
# buka http://127.0.0.1:8000, login dengan ADMIN_USERNAME / ADMIN_PASSWORD
```

Data contoh sintetis (bukan data client):

```bash
uv venv .venv -p 3.12 && uv pip install -p .venv/bin/python -r backend/requirements-dev.txt
make sample                     # -> data/sample/*.xlsx (15 sumur + 2 sumur baru + 2 roadmap)
make test
```

## Struktur

```
backend/app/        api/ core/ db/ parsers/ services/ main.py cli.py
backend/alembic/    migrasi
backend/tests/      tes + fixtures sintetis
web/                React + Vite + Plotly
scripts/            audit_files.py, anonymize_files.py, make_sample_data.py
deploy/             konfigurasi nginx host + skrip pemasangan server
docs/               keputusan.md, panduan.md
```
