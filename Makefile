.PHONY: up down restart clean build status test logs

up:
	docker compose up -d --build

down:
	docker compose down

restart:
	docker compose restart

clean:
	@echo "WARNING: This will delete all data (database, Redis, Grafana, Prometheus)."
	docker compose down -v

build:
	docker compose build

status:
	docker compose ps

test:
	docker compose up -d --build
	docker compose exec api pytest tests/ -v --override-ini=asyncio_mode=auto

logs:
	docker compose logs -f $(service)
