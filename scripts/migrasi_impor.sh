#!/usr/bin/env bash
# Impor hasil migrasi_ekspor.sh (jalankan di server BARU, dari folder proyek yang sudah dipindah).
# Urutan: cek checksum -> build image -> nyalakan db saja -> restore database -> isi volume
# uploads/models -> perbaiki izin folder data/ -> nyalakan semua -> cek jumlah baris.
# Menolak jalan bila database server baru sudah berisi tabel (supaya tidak menimpa data).
set -euo pipefail
cd "$(dirname "$0")/.."
COMPOSE=${COMPOSE:-docker compose}
IN=migrasi

[ -f .env ] || { echo "File .env tidak ada. Salin .env dari server lama (file tersembunyi, sering terlewat di FTP)."; exit 1; }
for f in db.dump uploads.tar.gz models.tar.gz SHA256SUMS; do
  [ -f "$IN/$f" ] || { echo "File $IN/$f tidak ada. Jalankan make migrasi-ekspor di server lama dulu."; exit 1; }
done

echo "== 1. Cek checksum (file rusak saat FTP mode ASCII akan gagal di sini)"
(cd "$IN" && sha256sum -c SHA256SUMS)

echo "== 2. Folder data dan build image"
mkdir -p data/inbox data/processed data/rejected backups
$COMPOSE build app

echo "== 3. Nyalakan database saja"
$COMPOSE up -d --wait db

n=$($COMPOSE exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*) from information_schema.tables where table_schema = \$\$public\$\$"')
if [ "$n" != "0" ]; then
  echo "Database di server ini sudah berisi $n tabel. Impor dibatalkan agar data tidak tertimpa."
  echo "Bila memang ingin diganti: $COMPOSE down -v  (MENGHAPUS database dan volume server ini), lalu ulangi."
  exit 1
fi

echo "== 4. Restore database"
$COMPOSE exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error' < "$IN/db.dump"

echo "== 5. Isi volume uploads dan models; izin folder data/ untuk uid 1000"
$COMPOSE run --rm --no-deps -T --user root -v "$PWD/$IN:/migrasi:ro" --entrypoint sh app -c \
  'tar xzf /migrasi/uploads.tar.gz -C /data/uploads && tar xzf /migrasi/models.tar.gz -C /data/models \
   && chown -R 1000:1000 /data/uploads /data/models /data/inbox /data/processed /data/rejected'

echo "== 6. Nyalakan semua layanan"
$COMPOSE up -d --wait

echo "== 7. Jumlah baris per tabel (bandingkan dengan $IN/MANIFEST.txt)"
$COMPOSE exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F " " -c "
  select table_name, (xpath(\$\$/row/c/text()\$\$, query_to_xml(format(\$\$select count(*) as c from %I\$\$, table_name), false, true, \$\$\$\$)))[1]::text
  from information_schema.tables where table_schema = \$\$public\$\$ order by 1"'
echo
curl -fsS http://127.0.0.1:8401/api/health && echo || echo "Health check gagal; lihat: make logs"
echo "Selesai. Pasang nginx + HTTPS (deploy/setup_server.sh) bila server ini belum punya."
