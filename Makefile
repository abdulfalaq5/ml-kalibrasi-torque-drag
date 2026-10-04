.PHONY: up down logs migrate backup test lint sample sample-docker password dev-api dev-web audit folders inbox-training inbox-sample practice-files

# Folder impor massal (harus bisa ditulis uid 1000 = user di dalam container)
folders:
	mkdir -p data/inbox data/processed data/rejected backups

up: folders
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f app

migrate:
	docker compose exec app alembic upgrade head

backup:
	docker compose exec -T db sh -c 'pg_dump -U $$POSTGRES_USER -d $$POSTGRES_DB' | gzip > backups/manual-$$(date +%Y%m%d-%H%M).sql.gz

test:
	cd backend && ../.venv/bin/pytest -q

lint:
	.venv/bin/ruff check backend scripts && .venv/bin/ruff format --check backend scripts

# Data sintetis (anonim) untuk pengembangan: data/sample/
sample:
	.venv/bin/python scripts/make_sample_data.py --out data/sample --wells 15

# Sama seperti `sample`, tapi lewat container app (tanpa Python di laptop)
sample-docker: folders
	docker compose run --rm --no-deps -v "$$PWD/scripts:/scripts:ro" -v "$$PWD/data:/out" \
		--user "$$(id -u):$$(id -g)" app python /scripts/make_sample_data.py --out /out/sample

# File latihan sesi pengenalan (sintetis): data/practice/{training,monitoring}/ + README.txt
practice-files: folders
	docker compose run --rm --no-deps -v "$$PWD/scripts:/scripts:ro" -v "$$PWD/data:/out" \
		--user "$$(id -u):$$(id -g)" app python /scripts/make_sample_data.py --practice --out /out/practice

password:
	docker compose exec app python -m app.cli set-admin-password

# Salin data sumur client (folder Training/<tipe>/<sumur>/) ke inbox, siap "Pindai folder".
# File asli di Training/ tidak diubah. Waktu file dimundurkan 2 menit agar tidak dilewati.
inbox-training: folders
	cp -r Training/. data/inbox/
	find data/inbox -name ".DS_Store" -delete
	find data/inbox -type f -exec touch -d "2 minutes ago" {} +
	@echo "Siap: $$(find data/inbox -type f | wc -l) file di data/inbox. Buka Data sumur -> Pindai folder."

# Data sintetis (bukan data client) ke inbox, untuk demo/latihan
inbox-sample: folders
	docker compose run --rm --no-deps -v "$$PWD/scripts:/scripts:ro" -v "$$PWD/data:/out" \
		--user "$$(id -u):$$(id -g)" app python /scripts/make_sample_data.py --out /out/inbox
	find data/inbox -type f -exec touch -d "2 minutes ago" {} +

# Laporan audit file (format, sheet, satuan, matriks). Hasil berisi nama sumur client -> data/, bukan docs/
audit:
	docker compose run --rm --no-deps -v "$$PWD/scripts:/scripts:ro" -v "$$PWD/Training:/in:ro" -v "$$PWD/data:/out" \
		-e PYTHONPATH=/app --user "$$(id -u):$$(id -g)" app python /scripts/audit_files.py /in --out /out/audit

dev-api:
	cd backend && APP_ENV=development ../.venv/bin/uvicorn app.main:app --reload --port 8401

dev-web:
	cd web && npm run dev
