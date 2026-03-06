# User Guide: Production-Ready Multi-Service Deployment

A hands-on, step-by-step guide to running, using, and developing with this project. By the end, you'll have 8 Docker containers running a task management API with caching, background workers, TLS, and full observability.

## What You'll Learn

- Docker Compose multi-service orchestration with health checks
- TLS termination with Nginx reverse proxy
- REST API development with FastAPI and async SQLAlchemy
- Cache-aside pattern with Redis
- Asynchronous task processing with Celery
- Metrics collection with Prometheus and Grafana dashboards
- Multi-stage Docker builds with non-root users

---

## Prerequisites

| Tool | Minimum Version | Check Command |
|------|----------------|---------------|
| Docker Desktop (or Docker Engine + Compose v2) | 24.0+ | `docker --version` |
| Git | 2.0+ | `git --version` |
| curl | any | `curl --version` |
| make | any | `make --version` |
| openssl | any | `openssl version` |

---

## Step 1: Clone and Configure Environment

```bash
git clone <repo-url>
cd Production-Ready-multi-service-deployment-project
```

Copy the environment template and (optionally) customize passwords:

```bash
cp .env.example .env
```

The `.env` file controls all service configuration. Key variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `POSTGRES_PASSWORD` | `changeme_use_a_strong_password` | Database password |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection string |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` | Celery message broker |
| `DEBUG` | `false` | Enables FastAPI debug mode |
| `GF_SECURITY_ADMIN_PASSWORD` | `changeme` | Grafana login password |

> For local development, the defaults work out of the box. For any shared environment, change the passwords.

---

## Step 2: Generate TLS Certificates

The project may already include self-signed certificates in `services/nginx/certs/`. If they're missing or expired, generate new ones:

```bash
mkdir -p services/nginx/certs

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout services/nginx/certs/selfsigned.key \
  -out services/nginx/certs/selfsigned.crt \
  -subj "/C=US/ST=Dev/L=Local/O=TaskApp/CN=localhost"
```

This creates a self-signed certificate valid for 365 days. Browsers will show a security warning - this is expected for local development.

---

## Step 3: Build and Launch All Services

```bash
make up
```

This runs `docker compose up -d --build`, which:

1. Builds custom images for the **API** and **Worker** (multi-stage Dockerfiles)
2. Pulls official images for PostgreSQL, Redis, Nginx, Prometheus, and Grafana
3. Starts all 8 containers in dependency order:
   - PostgreSQL and Redis start first (no dependencies)
   - API and Worker start after PostgreSQL and Redis are healthy
   - Nginx starts after the API is healthy
   - Traffic Generator starts after the API is healthy
   - Prometheus and Grafana start independently

First build takes 1-3 minutes depending on your machine. Subsequent builds are faster due to Docker layer caching.

---

## Step 4: Verify All Services Are Running

```bash
make status
```

You should see all containers with status `Up` and health state `(healthy)`:

```
NAME                 IMAGE                   STATUS                   PORTS
api                  ...                     Up (healthy)             0.0.0.0:8000->8000/tcp
postgres             postgres:16-alpine      Up (healthy)             0.0.0.0:5432->5432/tcp
redis                redis:7-alpine          Up (healthy)             0.0.0.0:6379->6379/tcp
nginx                nginx:1.27-alpine       Up                       0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
worker               ...                     Up
prometheus           prom/prometheus:latest   Up                       0.0.0.0:9090->9090/tcp
grafana              grafana/grafana:latest   Up                       3000/tcp
traffic-generator    alpine/curl:latest       Up
```

Quick health check:

```bash
# Via Nginx (HTTPS) - use -k to accept self-signed cert
curl -k https://localhost/

# Direct to API (HTTP)
curl http://localhost:8000/
```

Both should return:
```json
{"status": "ok"}
```

---

## Step 5: Explore the API — CRUD Operations

All API endpoints live under `/api/v1/tasks/`. You can access them through Nginx (HTTPS on port 443) or directly (HTTP on port 8000). The examples below use Nginx.

### Create a Task

```bash
curl -k -X POST https://localhost/api/v1/tasks/ \
  -H "Content-Type: application/json" \
  -d '{"title": "Learn Docker Compose", "description": "Multi-service orchestration", "priority": "high"}'
```

Response (HTTP 201):
```json
{
  "title": "Learn Docker Compose",
  "description": "Multi-service orchestration",
  "status": "todos",
  "priority": "high",
  "id": 11,
  "created_at": "2026-03-06T12:00:00",
  "updated_at": null
}
```

> Note: The `id` will vary. The traffic generator seeds 10 tasks on startup, so your first manual task may be id 11+.

### List All Tasks

```bash
curl -k https://localhost/api/v1/tasks/
```

Response (HTTP 200):
```json
{
  "tasks": [ ... ],
  "total": 11
}
```

### Filter Tasks

Filter by status (`todos`, `in_progress`, `done`) and/or priority (`low`, `medium`, `high`):

```bash
# Only high-priority tasks
curl -k "https://localhost/api/v1/tasks/?priority_filter=high"

# Only in-progress tasks
curl -k "https://localhost/api/v1/tasks/?status_filter=in_progress"

# Combine filters
curl -k "https://localhost/api/v1/tasks/?status_filter=todos&priority_filter=high"

# Pagination
curl -k "https://localhost/api/v1/tasks/?skip=0&limit=5"
```

### Get a Single Task

```bash
curl -k https://localhost/api/v1/tasks/1
```

Response (HTTP 200):
```json
{
  "title": "Task 1",
  "description": "Auto-generated task 1",
  "status": "todos",
  "priority": "low",
  "id": 1,
  "created_at": "2026-03-06T12:00:00",
  "updated_at": null
}
```

### Update a Task

Use PATCH with only the fields you want to change:

```bash
curl -k -X PATCH https://localhost/api/v1/tasks/1 \
  -H "Content-Type: application/json" \
  -d '{"status": "in_progress", "priority": "high"}'
```

Response (HTTP 200) — returns the full updated task with `updated_at` now populated.

### Delete a Task

```bash
curl -k -X DELETE https://localhost/api/v1/tasks/1
```

Response: HTTP 204 (no body). Requesting the same task again returns HTTP 404.

### Error Handling

```bash
# Task not found
curl -k https://localhost/api/v1/tasks/99999
# → 404: {"detail": "Task not found"}

# Missing required field
curl -k -X POST https://localhost/api/v1/tasks/ \
  -H "Content-Type: application/json" \
  -d '{"description": "no title"}'
# → 422: Validation error
```

---

## Step 6: Observe Caching Behavior

The API uses a **cache-aside pattern** with Redis for individual task lookups (GET by ID).

**How it works:**

1. `GET /api/v1/tasks/{id}` checks Redis first (key: `task:{id}`)
2. On cache miss: queries PostgreSQL, stores result in Redis with 300s TTL
3. On cache hit: returns cached data without touching the database
4. `PATCH` and `DELETE` invalidate the cache for that task

**Try it yourself:**

```bash
# First request — cache miss, hits the database
curl -k https://localhost/api/v1/tasks/2

# Second request — cache hit, served from Redis (faster)
curl -k https://localhost/api/v1/tasks/2

# Update the task — invalidates cache
curl -k -X PATCH https://localhost/api/v1/tasks/2 \
  -H "Content-Type: application/json" \
  -d '{"status": "done"}'

# Next GET will be a cache miss again (re-fetches from DB)
curl -k https://localhost/api/v1/tasks/2
```

You can verify cache entries directly in Redis:

```bash
docker compose exec redis redis-cli GET task:2
```

---

## Step 7: Trigger Background Tasks with Celery

The API can dispatch work to the Celery worker for async processing.

### Generate a Report

```bash
curl -k -X POST https://localhost/api/v1/tasks/report
```

Response (HTTP 202):
```json
{
  "task_id": "abc123-some-uuid",
  "status": "accepted"
}
```

The report runs asynchronously in the Celery worker. Check the worker logs to see the result:

```bash
make logs service=worker
```

You'll see output like:
```
worker  | Task generate_report succeeded in 0.05s: {'total_tasks': 10, 'by_status': {'todos': 5, 'in_progress': 3, 'done': 2}, 'by_priority': {'low': 3, 'medium': 4, 'high': 3}}
```

---

## Step 8: Monitor with Prometheus

Prometheus scrapes metrics from the FastAPI application every 15 seconds.

Open in your browser: **http://localhost:9090**

### Example PromQL Queries

Try these in the Prometheus query box:

| Query | What It Shows |
|-------|--------------|
| `http_requests_total` | Total request count by method, endpoint, status code |
| `rate(http_requests_total[5m])` | Request rate over the last 5 minutes |
| `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))` | 95th percentile latency |
| `http_requests_total{status_code="404"}` | All 404 responses |
| `http_requests_total{method="POST"}` | All POST requests |

The traffic generator is continuously sending requests, so you should see data immediately.

---

## Step 9: Explore Grafana Dashboards

Open in your browser: **https://localhost/grafana/**

> Accept the self-signed certificate warning in your browser.

**Login credentials** (from `.env`):
- Username: `admin`
- Password: `changeme` (or whatever you set in `.env`)

### Find the Pre-Built Dashboard

1. Click the hamburger menu (top-left)
2. Go to **Dashboards**
3. Open **FastAPI API Dashboard**

The dashboard has 4 panels:

| Panel | Metric | Description |
|-------|--------|-------------|
| Request Rate | `rate(http_requests_total[5m])` | Requests per second over time |
| Request Duration (p95) | `histogram_quantile(0.95, ...)` | 95th percentile response time |
| Error Rate | `http_requests_total{status_code=~"4..\|5.."}` | 4xx and 5xx error rate |
| Active Requests | `http_requests_total` | Total request count gauge |

The traffic generator sends continuous requests, so all panels should show live data. Use the time range picker (top-right) to zoom into the last 5 or 15 minutes.

---

## Step 10: Understand the Traffic Generator

The traffic generator (`services/traffic-generator/seed.sh`) runs automatically on startup and:

1. **Waits** for the API to be healthy
2. **Seeds** 10 tasks with random priorities
3. **Exercises** all endpoints (list, get, update, filter, 404s)
4. **Runs a continuous load loop** — mix of GET requests every 0.3 seconds

This generates the metrics data visible in Prometheus and Grafana. You can customize its behavior via environment variables in `docker-compose.yml`:

| Variable | Default | Description |
|----------|---------|-------------|
| `SEED_COUNT` | `10` | Number of tasks to create |
| `LOOP_DELAY` | `0.3` | Seconds between load loop iterations |
| `LOOP_DURATION` | `0` | Duration in seconds (0 = infinite) |

To stop the traffic generator without affecting other services:

```bash
docker compose stop traffic-generator
```

---

## Step 11: Run the Test Suite

```bash
make test
```

This builds the API container and runs pytest inside it:

```bash
docker compose exec api pytest tests/ -v --override-ini=asyncio_mode=auto
```

The test suite uses **SQLite in-memory** (not PostgreSQL) for speed and isolation. It covers:

- **Create**: valid task, missing title, default values
- **List**: empty list, multiple tasks, filter by status, filter by priority
- **Get**: valid task, 404 not found
- **Update**: full update, partial update, 404 not found
- **Delete**: success, 404 not found, idempotency (delete twice)

Expected output: **21 tests passed**.

---

## Step 12: Development Workflow

### Hot Reload

The `docker-compose.override.yml` file (automatically applied in development) enables:

- **Volume mount**: `api/app.py` is mounted into the container
- **Auto-reload**: Uvicorn watches for file changes with `--reload`
- **Debug mode**: `DEBUG=true`

Edit `api/app.py` on your host machine and the API restarts automatically — no rebuild needed.

### View Logs

```bash
# All services
make logs

# Specific service
make logs service=api
make logs service=worker
make logs service=nginx
make logs service=postgres
```

### Direct Database Access

With the dev override, PostgreSQL and Redis are exposed on your host:

```bash
# Connect to PostgreSQL
docker compose exec postgres psql -U taskapp -d taskdb

# Useful SQL queries
SELECT * FROM tasks;
SELECT status, COUNT(*) FROM tasks GROUP BY status;
SELECT priority, COUNT(*) FROM tasks GROUP BY priority;
```

```bash
# Connect to Redis
docker compose exec redis redis-cli

# Useful Redis commands
KEYS task:*          # List all cached tasks
GET task:1           # View cached task 1
TTL task:1           # Check remaining TTL (seconds)
DBSIZE               # Total keys in database
```

### Interactive API Docs

FastAPI auto-generates interactive documentation:

- **Swagger UI**: https://localhost/docs (via Nginx) or http://localhost:8000/docs (direct)
- **ReDoc**: https://localhost/redoc (via Nginx) or http://localhost:8000/redoc (direct)

---

## Step 13: Cleanup and Teardown

### Stop Services (Keep Data)

```bash
make down
```

Stops all containers but preserves Docker volumes (database data, Redis data, Grafana config, Prometheus metrics). Next `make up` resumes where you left off.

### Destroy Everything

```bash
make clean
```

Stops all containers **and deletes all volumes**. This is irreversible — all database records, cached data, Grafana dashboards, and Prometheus history are lost.

---

## Architecture Quick Reference

### Request Flow

```
Client (curl / browser)
        |
        v
  Nginx (ports 80/443)
  ├── HTTP :80 → 301 redirect to HTTPS
  └── HTTPS :443
      ├── /api/v1/tasks/* ──→ FastAPI API (:8000)
      │                         ├── PostgreSQL (:5432)  [persistent storage]
      │                         ├── Redis (:6379)       [cache layer]
      │                         └── Celery via Redis    [async task dispatch]
      ├── /metrics ──────────→ FastAPI /metrics endpoint
      └── /grafana/* ────────→ Grafana (:3000)
                                 └── Prometheus (:9090) [data source]
                                       └── scrapes FastAPI /metrics every 15s

  Celery Worker
  ├── Consumes tasks from Redis (broker)
  ├── Queries PostgreSQL (sync)
  └── Stores results in Redis (backend)

  Traffic Generator
  └── Sends continuous HTTP requests to API (:8000)
```

### Port Map

| Port | Service | Protocol | Access |
|------|---------|----------|--------|
| 80 | Nginx | HTTP | Redirects to 443 |
| 443 | Nginx | HTTPS | Main entry point |
| 5432 | PostgreSQL | TCP | Direct DB access (dev) |
| 6379 | Redis | TCP | Direct cache access (dev) |
| 8000 | FastAPI API | HTTP | Direct API access (dev) |
| 9090 | Prometheus | HTTP | Metrics UI |

### Docker Volumes

| Volume | Service | Contains |
|--------|---------|----------|
| `postgres-data` | PostgreSQL | Database files |
| `redis-data` | Redis | Cache and broker data |
| `prometheus-data` | Prometheus | Time-series metrics |
| `grafana-data` | Grafana | Dashboard config and state |

### Network

All services communicate over a single Docker bridge network: `app-network`. Services reference each other by container name (e.g., `postgres`, `redis`, `api`).

---

## Makefile Command Reference

| Command | Description |
|---------|-------------|
| `make up` | Build images and start all services in background |
| `make down` | Stop all services (keeps data volumes) |
| `make restart` | Restart all running services |
| `make clean` | Stop services and **delete all data volumes** |
| `make build` | Build Docker images without starting services |
| `make status` | Show container status and health |
| `make test` | Run the pytest test suite inside the API container |
| `make logs` | Tail logs for all services |
| `make logs service=api` | Tail logs for a specific service |

---

## Troubleshooting

### Port Already in Use

```
Error: bind: address already in use
```

Another process is using port 80, 443, 5432, 6379, 8000, or 9090. Find and stop it:

```bash
# Find what's using a port (e.g., 8000)
lsof -i :8000
```

### Container Not Healthy

```bash
# Check logs for the unhealthy service
make logs service=api

# Restart a specific service
docker compose restart api
```

### Database Connection Refused

The API or Worker can't reach PostgreSQL. Check that:
1. PostgreSQL is healthy: `docker compose ps postgres`
2. The `.env` file has correct `POSTGRES_HOST=postgres` (not `localhost`)
3. The `app-network` exists: `docker network ls`

### Certificate Errors

If Nginx fails to start with certificate errors:
1. Verify cert files exist: `ls services/nginx/certs/`
2. Regenerate if needed (see Step 2)
3. Check cert validity: `openssl x509 -in services/nginx/certs/selfsigned.crt -noout -dates`

### Stale Docker State

If things are broken in unexpected ways, do a full reset:

```bash
make clean          # Remove containers and volumes
docker system prune # Remove dangling images/networks
make up             # Fresh start
```
