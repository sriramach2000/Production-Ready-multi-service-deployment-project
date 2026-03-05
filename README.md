# Production-Ready Multi-Service Deployment

A containerized task management API built with FastAPI, PostgreSQL, Redis, Celery, Nginx, Prometheus, and Grafana — all orchestrated from a single Python script.

## Quick Start

```bash
# 1. Create your environment file
cp .env.example .env

# 2. Generate all project files
python orchestrate.py generate

# 3. Start everything
python orchestrate.py up

# 4. Verify services are running
python orchestrate.py status
```

**Access the app:**

| Service         | URL                       | Credentials     |
|-----------------|---------------------------|-----------------|
| API (via Nginx) | http://localhost          | —               |
| API (direct)    | http://localhost:8000     | —               |
| API Docs        | http://localhost:8000/docs| —               |
| Grafana         | http://localhost:3000     | admin / changeme|
| Prometheus      | http://localhost:9090     | —               |

## Architecture

```
Client -> Nginx (80) -> FastAPI (8000) -> PostgreSQL (5432)
                              |                |
                          Redis (6379) <- Celery Worker
                              |
                        Prometheus (9090) -> Grafana (3000)
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for details.

## Prerequisites

- [Docker & Docker Compose](https://docs.docker.com/get-docker/)
- Python 3.12+
- `pip install jinja2`

## Commands

```bash
python orchestrate.py generate    # Regenerate all files from config
python orchestrate.py up          # Build and start all services
python orchestrate.py down        # Stop all services (keeps data)
python orchestrate.py restart     # Restart all services
python orchestrate.py status      # Show service health
python orchestrate.py logs        # View all logs
python orchestrate.py logs api    # View logs for a specific service
python orchestrate.py test        # Run tests inside the API container
python orchestrate.py clean       # Stop and delete all data (destructive)
```

## Development Workflow

This project uses a **single source of truth** pattern:

1. **Edit application code** in `templates/` (e.g., `templates/api/app.py`)
2. **Edit infrastructure** in `templates/infra/` (e.g., `templates/infra/docker-compose.yml`)
3. **Edit config values** in `orchestrate.py` Section 1
4. **Regenerate** with `python orchestrate.py generate`
5. **Rebuild** with `python orchestrate.py up`

> **Do not edit generated files directly** (`api/`, `worker/`, `services/`, `tests/`). Your changes will be overwritten on the next `generate`.

## API Endpoints

| Method | Endpoint               | Description                   |
|--------|------------------------|-------------------------------|
| POST   | `/api/v1/tasks/`       | Create a task                 |
| GET    | `/api/v1/tasks/`       | List all tasks (cached)       |
| GET    | `/api/v1/tasks/{id}`   | Get a task by ID              |
| PATCH  | `/api/v1/tasks/{id}`   | Update a task (partial)       |
| DELETE | `/api/v1/tasks/{id}`   | Delete a task                 |
| POST   | `/api/v1/tasks/report` | Trigger async report (Celery) |
| GET    | `/`                    | Health check                  |
| GET    | `/metrics`             | Prometheus metrics            |

## Tech Stack

**Application:** FastAPI, SQLAlchemy 2.0 (async), Celery 5.6, Pydantic v2

**Infrastructure:** Docker, Nginx 1.27, PostgreSQL 16, Redis 7

**Monitoring:** Prometheus, Grafana
