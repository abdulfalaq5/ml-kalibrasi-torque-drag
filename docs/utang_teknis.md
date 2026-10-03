# Kaji ulang prototype dan utang teknis (Hari 1 paket 6 minggu)

| # | Temuan di prototype 3 minggu | Dampak | Tindakan di paket 6 minggu |
|---|---|---|---|
| 1 | Parser generik berbasis nama sheet asumsi (Summary/Tripping/T&D) | Tidak cocok dengan file asli (blok FF per kolom, "Graph reference", satuan di baris terpisah) | **Diganti**: parser format A (`parsers/roadmap.py`) dan B (`parsers/wellplan_report.py`) dari audit 94 file |
| 2 | Fitur FF tetap 0,1/0,3/0,5 | File asli punya set FF berbeda; FF 0,1 tidak ada di 20+46 file | **Diganti**: FF 0,3 & 0,5 (ada di semua file) + kemiringan FF |
| 3 | Leave-one-well-out untuk semua kandidat | Lambat untuk 40+ sumur × 5 algoritma | **Diganti**: GroupKFold 5 per sumur, prediksi out-of-fold dari fold yang sama |
| 4 | Model dilatih dari data live | Hasil tidak bisa diulang | **Diganti**: dataset beku (snapshot + hash), model mencatat versi dataset |
| 5 | Tidak ada pemisahan uji akhir | Risiko optimistis | **Ditambah**: blind test terkunci, sekali per model |
| 6 | Validasi data hanya per file | Data aneh tetap masuk training | **Ditambah**: gerbang kualitas A/B/C + tinjauan |
| 7 | Daftar sumur memuat hitungan per sumur (N+1 kueri) | 0,7 detik untuk 94 sumur-section | **Diperbaiki**: kueri agregat, 37 ms |
| 8 | Ekspor Excel tidak mengikuti struktur file client | Engineer harus menyesuaikan | **Diganti**: sheet Drag / Torque / T&D Actual Reading + kolom ML |
| 9 | Generator data sintetis meniru format asumsi | Tes tidak mewakili file asli | **Diganti**: generator meniru format A dan B persis, struktur folder Tipe/Sumur |

Sisa utang (belum dikerjakan, dicatat):
- Pita ketidakpastian berlebar tetap per operasi (belum bergantung kedalaman/section), K-29.
- Pemilihan kandidat model memakai skor validasi silang yang sama (sedikit optimistis); dikompensasi blind test, K-11.
- Pelatihan berjalan sebagai background task FastAPI di proses web (cukup untuk satu server; bila beban naik, pindah ke worker terpisah).
- Grafik Excel hanya diuji terbuka di LibreOffice/openpyxl; perlu dicek sekali di Microsoft Excel.
