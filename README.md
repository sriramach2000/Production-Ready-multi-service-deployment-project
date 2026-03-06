# Production-Ready Multi-Service Deployment

A containerized task management API built with FastAPI, PostgreSQL, Redis, Celery, Nginx, Prometheus, and Grafana. Clone it, configure `.env`, and run `make up`.

## Quick Start

```bash
# 1. Create your environment file
cp .env.example .env

# 2. Generate self-signed TLS certs (one-time)
mkdir -p services/nginx/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout services/nginx/certs/selfsigned.key \
  -out services/nginx/certs/selfsigned.crt \
  -subj "/C=US/ST=Dev/L=Local/O=TaskApp/CN=localhost"

# 3. Start everything
make up

# 4. Verify services are running
make status
```

**Access the app:**

| Service    | URL                              | Credentials      |
|------------|----------------------------------|-------------------|
| API        | https://localhost/               | —                 |
| API Docs   | https://localhost/docs           | —                 |
| Grafana    | https://localhost/grafana/       | admin / changeme  |
| Prometheus | http://localhost:9090            | —                 |
| Metrics    | https://localhost/metrics        | —                 |

> Your browser will warn about the self-signed certificate — accept it to proceed.

## Architecture

```
Client -> Nginx (443/SSL) -> FastAPI (8000) -> PostgreSQL (5432)
                 |                  |
                 |              Redis (6379) <- Celery Worker
                 |
                 +-> Grafana (3000)
                 |
           Prometheus (9090)
```

Nginx terminates TLS and reverse-proxies all traffic. Grafana is served at `/grafana/` behind HTTPS. HTTP on port 80 redirects to HTTPS.

## Prerequisites

- [Docker & Docker Compose](https://docs.docker.com/get-docker/)

## Commands

```bash
make up        # Build and start all services
make down      # Stop all services (keeps data)
make restart   # Restart all services
make status    # Show service health
make logs      # View all logs
make logs service=api   # View logs for a specific service
make test      # Run tests inside the API container
make clean     # Stop and delete all data (destructive)
```

## Project Structure

```
├── api/
│   ├── app.py             # FastAPI application
│   ├── Dockerfile
│   └── requirements.txt
├── worker/
│   ├── app.py             # Celery worker
│   ├── Dockerfile
│   └── requirements.txt
├── services/
│   ├── nginx/nginx.conf   # Nginx reverse proxy (TLS)
│   ├── prometheus/        # Prometheus config
│   └── grafana/           # Grafana dashboards & provisioning
├── tests/
│   ├── conftest.py
│   └── test_tasks.py
├── docker-compose.yml
├── Makefile
├── .env.example
└── .env                   # Your local config (gitignored)
```

Edit files directly — there is no code generation step.

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

## Configuration

All config is read from `.env` at runtime via Pydantic `BaseSettings` (API) and `os.getenv()` (worker). See [.env.example](.env.example) for available variables.

## Tech Stack

**Application:** FastAPI, SQLAlchemy 2.0 (async), Celery 5.6, Pydantic v2

**Infrastructure:** Docker, Nginx 1.27 (TLS), PostgreSQL 16, Redis 7

**Monitoring:** Prometheus, Grafana (pre-provisioned dashboards)
