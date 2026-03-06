# Architecture


## Services (7 containers)

| Service    | Image / Build       | Purpose                          | Port  |
|------------|---------------------|----------------------------------|-------|
| postgres   | postgres:16-alpine  | Primary database                 | 5432  |
| redis      | redis:7-alpine      | Cache + Celery broker            | 6379  |
| api        | Custom (FastAPI)    | REST API, async SQLAlchemy       | 8000  |
| worker     | Custom (Celery)     | Background task processing       | —     |
| nginx      | Custom (Alpine)     | Reverse proxy, security headers  | 80    |
| prometheus | prom/prometheus     | Metrics collection               | 9090  |
| grafana    | grafana/grafana     | Metrics dashboards               | 3000  |

## Data Flow

```
HTTP Request -> Nginx -> FastAPI
                           |
                    +------+------+
                    |             |
                 PostgreSQL    Redis (cache-aside)
                    |
               Celery Worker (async tasks via Redis broker)
                    |
               Prometheus scrapes /metrics -> Grafana displays
```

## Key Patterns

- **Cache-aside**: GET reads Redis first, falls back to DB, then populates cache. UPDATE/DELETE invalidates cache.
- **Multi-stage Docker builds**: Builder stage installs deps, production stage copies only what's needed. Non-root user.
- **Health checks**: All services have Docker health checks. `depends_on: service_healthy` ensures correct startup order.
- **Async API, sync worker**: FastAPI uses asyncpg; Celery uses psycopg2 (process-based, no event loop).

## Project Structure

```
simplified_deployment/
+-- orchestrate.py              Config + template renderer + CLI (~250 lines)
+-- .gitignore, .dockerignore   Static, committed directly
+-- templates/
|   +-- api/app.py              FastAPI application template
|   +-- worker/app.py           Celery worker template
|   +-- tests/                  Test fixtures and test cases
|   +-- infra/                  Docker, nginx, prometheus, env templates
+-- services/grafana/           Static Grafana dashboard + provisioning
```
