# AidFlow — convenience targets.
# Each target maps to a plain docker compose / bash command (see README for the
# no-make equivalents).

.PHONY: up down reset test seed openapi logs schema preflight ci-local

up:
	docker compose up --build

down:
	docker compose down

reset:
	docker compose down -v
	docker compose up --build

test:
	docker compose exec api pytest -q

seed:
	bash client/seed_demo.sh

openapi:
	bash client/export_openapi.sh

logs:
	docker compose logs -f

schema:
	python scripts/validate_schemas.py

preflight:
	bash scripts/preflight.sh

ci-local:
	docker compose config
	docker compose up -d --build db api
	bash scripts/wait_for_api.sh
	docker compose exec -T api pytest -q
	python scripts/validate_schemas.py
	docker compose build web
