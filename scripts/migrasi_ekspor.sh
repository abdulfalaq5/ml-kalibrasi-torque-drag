#!/usr/bin/env bash
# Ekspor seluruh isi sistem untuk pindah server (jalankan di server LAMA, dari folder proyek).
# Hasil: folder migrasi/ berisi
#   db.dump        database Postgres (pg_dump format custom)
#   uploads.tar.gz file unggahan (volume uploads)
#   models.tar.gz  model ML + snapshot dataset (volume models)
#   MANIFEST.txt   jumlah baris per tabel, ukuran, commit, checksum
#   SHA256SUMS     checksum untuk dicek setelah transfer FTP
# Folder data/, backups/, Training/ dan .env ikut terbawa saat seluruh folder proyek dipindah.
#
# Bawaan: container app DIHENTIKAN supaya tidak ada data baru yang tertinggal setelah ekspor.
# STOP_APP=0 untuk ekspor tanpa menghentikan app (mis. uji coba).
set -euo pipefail
cd "$(dirname "$0")/.."
COMPOSE=${COMPOSE:-docker compose}
OUT=migrasi

[ -f .env ] || { echo "File .env tidak ada di $(pwd)"; exit 1; }
if [ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ]; then
  echo "Folder $OUT/ sudah berisi file. Pindahkan/hapus dulu agar ekspor lama tidak tertimpa."
  exit 1
fi
mkdir -p "$OUT"

if [ "${STOP_APP:-1}" = "1" ]; then
  echo "== 1. Menghentikan app (database tetap jalan)"
  $COMPOSE stop app
else
  echo "== 1. STOP_APP=0: app tetap jalan (hasil ekspor bisa tertinggal data terbaru)"
fi

echo "== 2. Dump database"
$COMPOSE exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$OUT/db.dump"

echo "== 3. Arsip volume uploads dan models"
# docker compose run memakai volume milik proyek ini apa pun nama foldernya
$COMPOSE run --rm --no-deps -T --user root -v "$PWD/$OUT:/migrasi" --entrypoint sh app -c \
  "tar czf /migrasi/uploads.tar.gz -C /data/uploads . && tar czf /migrasi/models.tar.gz -C /data/models . \
   && chown $(id -u):$(id -g) /migrasi/uploads.tar.gz /migrasi/models.tar.gz"

echo "== 4. Manifest dan checksum"
{
  echo "Ekspor: $(date '+%Y-%m-%d %H:%M:%S %Z') dari $(hostname)"
  echo "Commit: $(git rev-parse --short HEAD 2>/dev/null || echo '-')"
  echo
  echo "Jumlah baris per tabel:"
  $COMPOSE exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F " " -c "
    select table_name, (xpath(\$\$/row/c/text()\$\$, query_to_xml(format(\$\$select count(*) as c from %I\$\$, table_name), false, true, \$\$\$\$)))[1]::text
    from information_schema.tables where table_schema = \$\$public\$\$ order by 1"'
  echo
  echo "Ukuran:"
  du -sh "$OUT"/db.dump "$OUT"/uploads.tar.gz "$OUT"/models.tar.gz data backups Training 2>/dev/null || true
} > "$OUT/MANIFEST.txt"
(cd "$OUT" && sha256sum db.dump uploads.tar.gz models.tar.gz > SHA256SUMS)
chmod -R a+rX "$OUT"

cat "$OUT/MANIFEST.txt"
echo
echo "Selesai. Pindahkan SELURUH folder proyek (termasuk .env, migrasi/, data/) ke server baru"
echo "lewat FTP mode BINARY, lalu di server baru jalankan: make migrasi-impor"
if [ "${STOP_APP:-1}" = "1" ]; then
  echo "App di server ini masih berhenti. Untuk menyalakan lagi: $COMPOSE start app"
fi
