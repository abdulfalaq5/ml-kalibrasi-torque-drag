.PHONY: up down logs migrate backup test lint sample sample-docker password dev-api dev-web audit

up:
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
sample-docker:
	mkdir -p data
	docker compose run --rm --no-deps -v "$$PWD/scripts:/scripts:ro" -v "$$PWD/data:/out" \
		--user "$$(id -u):$$(id -g)" app python /scripts/make_sample_data.py --out /out/sample

password:
	docker compose exec app python -m app.cli set-admin-password

audit:
	.venv/bin/python scripts/audit_files.py data/raw --out docs/audit

dev-api:
	cd backend && APP_ENV=development ../.venv/bin/uvicorn app.main:app --reload --port 8000

dev-web:
	cd web && npm run dev
