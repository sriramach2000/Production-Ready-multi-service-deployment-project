# Production-Ready Multi-Service Deployment Using Docker & Docker Compose

## Project Directive

Design and containerize a Python-based microservice application using Docker and
orchestrate it with Docker Compose following production best practices.

Build a Python REST API (using FastAPI) that manages a **Task Management** system
where users can create, update, delete, and list tasks. Each task includes fields
like title, description, status, priority, and created_at timestamp. The API stores
data in PostgreSQL, uses Redis for caching frequently accessed tasks, and pushes
long-running operations to a background worker using Celery.

**You will:**
- Containerize the API, PostgreSQL, Redis, background worker, and Nginx reverse proxy
- Create optimized multi-stage Dockerfiles running as non-root users
- Use Docker Compose to define services, custom networks, named volumes, and environment variables
- Implement health checks and proper service startup ordering
- Configure Nginx to route API traffic and enable basic security headers
- Add monitoring with Prometheus and Grafana
- Ensure secrets are not hardcoded and apply restart policies

---

## How This Project Works

### Single Source of Truth

Everything is driven by **one file**: `orchestrate.py`.

```
orchestrate.py                  <-- THE ONE FILE THAT GENERATES EVERYTHING
├── Section 1: CONFIG           <-- Edit config values here
├── Section 2: Templates        <-- Renders templates/api/app.py, templates/worker/app.py, etc.
├── Sections 3-10: Generators   <-- Generates Dockerfiles, docker-compose, nginx, etc.
├── Section 11: File Manifest   <-- Maps generators to output files
└── Section 12: CLI             <-- generate, up, down, clean, logs, status
```

### Two kinds of files

| Kind | Where you edit | Examples |
|------|---------------|----------|
| **Application code** (has todoss) | `templates/` directory | `templates/api/app.py`, `templates/worker/app.py`, `templates/tests/*` |
| **Infrastructure config** (already complete) | `orchestrate.py` (Sections 3-10) | Dockerfiles, docker-compose.yml, nginx, prometheus, grafana |

### Workflow

```
1. Edit templates/api/app.py        <-- implement a todos
2. python3 orchestrate.py generate  <-- renders templates, writes all 29 files
3. python3 orchestrate.py up        <-- generates + docker compose up -d --build
```

To change a config value (e.g., port, database name):
```
1. Edit CONFIG in orchestrate.py Section 1
2. python3 orchestrate.py generate  <-- new value flows to every file that uses it
```

### Config values in templates

Templates use `<< marker >>` syntax for config values. Example from `templates/api/app.py`:

```python
POSTGRES_USER: str = "<< postgres.user >>"    # becomes "taskapp" after generate
API_PORT: int = << api.port >>                # becomes 8000 after generate
```

You never need to touch these markers. Just edit CONFIG in orchestrate.py and regenerate.

---

## Architecture Overview

```
┌─────────┐     ┌─────────┐     ┌──────────────┐     ┌────────────┐
│  Client  │────>│  Nginx  │────>│  FastAPI API  │────>│ PostgreSQL │
│          │     │  :80    │     │  :8000        │     │  :5432     │
└─────────┘     └─────────┘     └──────┬───────┘     └────────────┘
                                       │
                                       ├──────────>┌─────────┐
                                       │  cache    │  Redis  │
                                       │           │  :6379  │
                                       ├──────────>└─────────┘
                                       │  dispatch        │
                                       │           ┌──────┴──────┐
                                       └──────────>│   Celery    │
                                                   │   Worker    │
                                                   └─────────────┘

┌─────────────┐     ┌─────────────┐
│ Prometheus  │────>│   Grafana   │
│ :9090       │     │   :3000     │
└─────────────┘     └─────────────┘
   scrapes /metrics from API
```

**7 Docker services:** postgres, redis, api, worker, nginx, prometheus, grafana

---

## Project File Tree

```
.
├── orchestrate.py                          <-- SINGLE SOURCE OF TRUTH
│
├── templates/                              <-- YOU EDIT THESE (full IDE support)
│   ├── api/app.py                          <-- FastAPI application (56 todoss)
│   ├── worker/app.py                       <-- Celery worker (2 todoss)
│   ├── tests/
│   │   ├── conftest.py                     <-- Test fixtures (6 todoss)
│   │   ├── test_tasks.py                   <-- Test cases (15 todoss)
│   │   └── __init__.py
│   └── migrations/
│       └── env.py                          <-- Alembic environment (0 todoss)
│
├── api/                                    <-- GENERATED (don't edit directly)
│   ├── app.py
│   ├── Dockerfile                          <-- Multi-stage, non-root user
│   └── requirements.txt
├── worker/
│   ├── app.py
│   ├── Dockerfile                          <-- Multi-stage, non-root user
│   └── requirements.txt
├── services/
│   ├── nginx/
│   │   ├── Dockerfile
│   │   ├── nginx.conf                      <-- 2 todoss (logging, gzip)
│   │   └── conf.d/default.conf             <-- 3 todoss (security headers, proxy headers)
│   ├── prometheus/
│   │   └── prometheus.yml
│   └── grafana/
│       ├── dashboards/api_dashboard.json
│       └── provisioning/
│           ├── datasources/datasource.yml
│           └── dashboards/dashboard.yml
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── test_tasks.py
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   ├── README
│   └── versions/.gitkeep
├── scripts/
│   └── healthcheck.sh
├── docker-compose.yml
├── docker-compose.override.yml
├── .env / .env.example
├── alembic.ini
├── Makefile
├── .gitignore
└── .dockerignore
```

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| API Framework | FastAPI + Uvicorn | Async REST API |
| ORM | SQLAlchemy 2.0 (async) | Database operations |
| Validation | Pydantic v2 + pydantic-settings | Request/response schemas, config |
| Database | PostgreSQL 16 (asyncpg driver) | Persistent storage |
| Cache / Broker | Redis 7 | Caching + Celery message broker |
| Task Queue | Celery 5 | Background job processing |
| Reverse Proxy | Nginx 1.27 | Load balancing, security headers |
| Monitoring | Prometheus + Grafana | Metrics collection + dashboards |
| Migrations | Alembic | Database schema versioning |
| Testing | pytest + httpx + pytest-asyncio | Async API testing |
| Containerization | Docker + Docker Compose | Multi-service orchestration |

---

## Implementation Phases

Work through these phases in order. Each phase builds on the one before it.

---

### Phase 1: API Core — Configuration, Models, Schemas, CRUD, Routes, App

**File:** `templates/api/app.py`
**What you're building:** A working FastAPI REST API with CRUD operations for tasks.

#### Step 1.1 — Configuration (Section 1)

Configure the Settings class to load environment variables.

| # | What to implement | Where | Docs |
|---|-------------------|-------|------|
| 1 | Configure `model_config` with `SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")` | `Settings.model_config` | [pydantic-settings dotenv](https://docs.pydantic.dev/latest/concepts/pydantic_settings/#dotenv-env-support) |
| 2 | Define a property or computed field: `DATABASE_URL` that assembles `postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}` from the individual Settings fields | Below `POSTGRES_PORT` | [pydantic validators](https://docs.pydantic.dev/latest/concepts/validators/) |

**Checkpoint:** `get_settings()` returns a Settings object with all defaults populated.

#### Step 1.2 — Database Models (Section 2)

Define the Task ORM model with proper column types.

| # | What to implement | Where | Docs |
|---|-------------------|-------|------|
| 3 | `id` — autoincrement | `Task.id: mapped_column(...)` | [mapped_column](https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html#using-mapped-column) |
| 4 | `title` — `String(255)`, `nullable=False` | `Task.title` | |
| 5 | `description` — `Text`, `nullable=True` | `Task.description` | |
| 6 | `status` — `SAEnum(TaskStatus)`, default `TaskStatus.todos` | `Task.status` | |
| 7 | `priority` — `SAEnum(TaskPriority)`, default `TaskPriority.MEDIUM` | `Task.priority` | |
| 8 | `created_at` — `DateTime`, `server_default=func.now()` | `Task.created_at` | [server defaults](https://docs.sqlalchemy.org/en/20/core/defaults.html#server-invoked-ddl-explicit-default-expressions) |
| 9 | `updated_at` — `DateTime`, `onupdate=func.now()`, `nullable=True` | `Task.updated_at` | |
| 10 | `__repr__` — return readable string like `Task(id=1, title='My Task', status='todos')` | `Task.__repr__` | |

**Checkpoint:** `Task` class has all columns defined with proper types and defaults.

#### Step 1.3 — Database Session (Section 3)

Set up the async database engine and session factory.

| # | What to implement | Where | Docs |
|---|-------------------|-------|------|
| 11 | Create async engine: `create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)` | `engine` variable | [engines](https://docs.sqlalchemy.org/en/20/core/engines.html) |
| 12 | Create session factory: `async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)` | `async_session_factory` variable | [async sessions](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) |
| 13 | Implement `get_session()` — yield a session using `async with async_session_factory() as session` | `get_session()` | [FastAPI dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/) |

**Checkpoint:** `get_session()` is a working async generator that provides database sessions.

#### Step 1.4 — Schemas (Section 4)

Define Pydantic models for request/response validation.

| # | What to implement | Where | Docs |
|---|-------------------|-------|------|
| 14 | `title` field — `min_length=1, max_length=255` | `TaskBase.title` | [pydantic fields](https://docs.pydantic.dev/latest/concepts/fields/) |
| 15 | `description` — `default=None` | `TaskBase.description` | |
| 16 | `status` — `default=TaskStatus.todos` | `TaskBase.status` | |
| 17 | `priority` — `default=TaskPriority.MEDIUM` | `TaskBase.priority` | |
| 18 | `TaskUpdate` fields — all `default=None` (partial update) | `TaskUpdate.*` | |
| 19 | `model_config = ConfigDict(from_attributes=True)` — ORM mode | `TaskResponse.model_config` | [arbitrary class instances](https://docs.pydantic.dev/latest/concepts/models/#arbitrary-class-instances) |

**Checkpoint:** Schemas validate input, serialize output, and read from SQLAlchemy models.

#### Step 1.5 — Services / CRUD (Section 5)

Implement the business logic layer.

| # | What to implement | Where | Docs |
|---|-------------------|-------|------|
| 20 | `create_task` — `Task(**task_data.model_dump())`, add, commit, refresh, return | `create_task()` | [adding items](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#adding-new-or-existing-items) |
| 21 | `get_task` — `select(Task).where(Task.id == task_id)`, execute, `scalar_one_or_none()` | `get_task()` | [select guide](https://docs.sqlalchemy.org/en/20/orm/queryguide/select.html) |
| 22 | `list_tasks` — build query with optional filters, offset, limit, order by created_at desc | `list_tasks()` | |
| 23 | `count_tasks` — `select(func.count()).select_from(Task)` with same filters | `count_tasks()` | |
| 24 | `update_task` — fetch by ID, loop `model_dump(exclude_unset=True)`, setattr, commit | `update_task()` | |
| 25 | `delete_task` — fetch by ID, `session.delete(task)`, commit, return True/False | `delete_task()` | |

**Checkpoint:** All five CRUD operations work against the database.

#### Step 1.6 — Routes (Section 8)

Wire up the API endpoints to the service functions.

| # | What to implement | Where | Docs |
|---|-------------------|-------|------|
| 26 | `POST /` — call `create_task()`, return created task | `create_task_endpoint` | [request body](https://fastapi.tiangolo.com/tutorial/body/) |
| 27 | `GET /` — call `list_tasks()` + `count_tasks()`, return `TaskListResponse` | `list_tasks_endpoint` | [query params](https://fastapi.tiangolo.com/tutorial/query-params/) |
| 28 | `GET /{task_id}` — check cache, query DB, raise 404 if not found | `get_task_endpoint` | [path params](https://fastapi.tiangolo.com/tutorial/path-params/) |
| 29 | `PATCH /{task_id}` — call `update_task()`, invalidate cache, return updated | `update_task_endpoint` | [body updates](https://fastapi.tiangolo.com/tutorial/body-updates/) |
| 30 | `DELETE /{task_id}` — call `delete_task()`, invalidate cache, return 204 | `delete_task_endpoint` | |
| 31 | `POST /report` — dispatch Celery task, return 202 with task ID | `generate_report_endpoint` | [Celery calling](https://docs.celeryq.dev/en/stable/userguide/calling.html) |

**Note:** Steps 28-30 use the cache service (Phase 3). For now, you can skip the cache calls and add them in Phase 3.

**Checkpoint:** All endpoints respond correctly (test with curl or httpx).

#### Step 1.7 — App Setup (Section 9)

Configure the FastAPI application instance, lifespan, and middleware.

| # | What to implement | Where | Docs |
|---|-------------------|-------|------|
| 32 | **Lifespan startup** — create engine, create tables, connect Redis cache | `lifespan()` yield section | [lifespan events](https://fastapi.tiangolo.com/advanced/events/) |
| 33 | **Lifespan shutdown** — dispose engine, close Redis | `lifespan()` after yield | |
| 34 | **App instance** — `FastAPI(title=..., version=..., lifespan=lifespan)` | `app = FastAPI(...)` | [first steps](https://fastapi.tiangolo.com/tutorial/first-steps/) |
| 35 | **CORS middleware** — `app.add_middleware(CORSMiddleware, ...)` | Below app creation | [CORS](https://fastapi.tiangolo.com/tutorial/cors/) |
| 36 | **Include router** — `app.include_router(router, prefix="/api/v1/tasks", tags=["tasks"])` | Below CORS | [bigger apps](https://fastapi.tiangolo.com/tutorial/bigger-applications/) |
| 37 | **Health check** — return `{"status": "ok"}` | `health_check()` | |

**Checkpoint:** `python3 orchestrate.py up` starts the stack. `curl http://localhost/` returns `{"status": "ok"}`.

---

### Phase 2: Database Session Management

**File:** `templates/api/app.py`, Section 3

Already covered in Step 1.3. If you deferred it, implement the engine, session factory, and `get_session()` now.

**Checkpoint:** API can connect to PostgreSQL and execute queries.

---

### Phase 3: Redis Caching Layer

**File:** `templates/api/app.py`, Section 6
**What you're building:** Cache-aside pattern — check Redis before hitting the database.

| # | What to implement | Where | Docs |
|---|-------------------|-------|------|
| 38 | `connect()` — `aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)` | `CacheService.connect` | [redis-py connections](https://redis.readthedocs.io/en/stable/connections.html) |
| 39 | `close()` — `await self.redis.close()` | `CacheService.close` | |
| 40 | `_make_key()` — return `f"{CACHE_PREFIX}:{task_id}"` | `CacheService._make_key` | |
| 41 | `get_cached_task()` — GET key, json.loads on hit, None on miss | `CacheService.get_cached_task` | [Redis GET](https://redis.io/docs/latest/commands/get/) |
| 42 | `set_cached_task()` — json.dumps, SETEX with TTL | `CacheService.set_cached_task` | [Redis SETEX](https://redis.io/docs/latest/commands/setex/) |
| 43 | `invalidate_task_cache()` — DELETE key | `CacheService.invalidate_task_cache` | [Redis DEL](https://redis.io/docs/latest/commands/del/) |

**Then:** Go back to the route handlers (Phase 1, Step 1.6) and add the cache calls to `get_task_endpoint`, `update_task_endpoint`, and `delete_task_endpoint`.

**Checkpoint:** First `GET /api/v1/tasks/{id}` hits DB. Second request serves from Redis cache. Update/delete invalidates the cache.

---

### Phase 4: Celery Background Worker

**File:** `templates/worker/app.py`, Section 2
**What you're building:** Background tasks dispatched from the API.

| # | What to implement | Where | Docs |
|---|-------------------|-------|------|
| 44 | `generate_report` — create sync SQLAlchemy session, query tasks, build report dict, handle retries | `generate_report()` | [Celery tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html), [retrying](https://docs.celeryq.dev/en/stable/userguide/tasks.html#retrying) |
| 45 | `bulk_status_update` — query by IDs, update statuses, commit, return count | `bulk_status_update()` | |

**Important:** The worker uses **synchronous** SQLAlchemy (psycopg2), not async (asyncpg). Celery is process-based — no async event loop.

**Then:** Go back to `generate_report_endpoint` in `templates/api/app.py` and wire up the Celery dispatch.

**Checkpoint:** `POST /api/v1/tasks/report` returns 202. Check `docker compose logs worker` to see the task execute.

---

### Phase 5: Dockerfiles (Already Complete)

The Dockerfiles are already generated and fully functional:

- **`api/Dockerfile`** — Multi-stage build, non-root `appuser`, health check, exposes port 8000
- **`worker/Dockerfile`** — Multi-stage build, non-root `appuser`, Celery health check via `celery inspect ping`
- **`services/nginx/Dockerfile`** — Copies nginx config files

**What to understand:**
- Multi-stage builds: `builder` stage installs dependencies, `production` stage copies only what's needed
- Non-root user: `addgroup --system appgroup && adduser --system --group appuser`
- Health checks: Docker periodically checks if the container is healthy

**Checkpoint:** `docker compose build` succeeds for all services.

---

### Phase 6: Docker Compose & Service Orchestration (Already Complete)

`docker-compose.yml` is generated with all 7 services configured:

**What to understand:**
- **Service dependencies:** `api` depends on `postgres` and `redis` (with `condition: service_healthy`)
- **Named volumes:** `postgres-data`, `redis-data`, `prometheus-data`, `grafana-data`
- **Custom network:** `app-network` (bridge)
- **Health checks:** Every service has health check configuration
- **Restart policy:** `unless-stopped` on all services
- **Environment variables:** Loaded from `.env` file (never hardcoded)

**Checkpoint:** `docker compose config` validates. `python3 orchestrate.py up` starts all 7 services.

---

### Phase 7: Prometheus Metrics

**File:** `templates/api/app.py`, Section 7
**What you're building:** HTTP request instrumentation for monitoring.

| # | What to implement | Where | Docs |
|---|-------------------|-------|------|
| 46 | `REQUEST_COUNT` — `Counter("http_requests_total", "...", ["method", "endpoint", "status_code"])` | Section 7 globals | [prometheus counter](https://prometheus.github.io/client_python/instrumenting/counter/) |
| 47 | `REQUEST_DURATION` — `Histogram("http_request_duration_seconds", "...", ["method", "endpoint"])` | Section 7 globals | [prometheus histogram](https://prometheus.github.io/client_python/instrumenting/histogram/) |
| 48 | `prometheus_middleware` — record start time, call next, observe duration, increment count | `setup_metrics()` | [FastAPI middleware](https://fastapi.tiangolo.com/tutorial/middleware/) |
| 49 | Mount metrics app — `make_asgi_app()` at `/metrics` | `setup_metrics()` | [prometheus ASGI](https://prometheus.github.io/client_python/exporting/http/) |

**Then:** Uncomment `setup_metrics(app)` in Section 9 (Step 1.7, item 55).

**Checkpoint:** `curl http://localhost/metrics` returns Prometheus text format. Grafana dashboard at `http://localhost:3000` shows data (login: admin/changeme).

---

### Phase 8: Nginx Security & Proxy Headers

**File:** `services/nginx/nginx.conf` and `services/nginx/conf.d/default.conf`
**Note:** These are generated from `orchestrate.py` Sections 6. To edit them, modify the generator functions in `orchestrate.py`.

| # | What to implement | Where in orchestrate.py |
|---|-------------------|------------------------|
| 50 | Logging — `access_log` and `error_log` | `generate_nginx_conf()` |
| 51 | Gzip compression — `gzip on; gzip_types ...` | `generate_nginx_conf()` |
| 52 | Security headers — `X-Frame-Options`, `X-Content-Type-Options`, `X-XSS-Protection`, `Referrer-Policy` | `generate_nginx_default_conf()` |
| 53 | Proxy headers — `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto` | `generate_nginx_default_conf()` |
| 54 | Optional: Expose `/metrics` location for external scraping | `generate_nginx_default_conf()` |

**Checkpoint:** Response headers include security headers. `docker compose logs nginx` shows access logs.

---

### Phase 9: Testing

**Files:** `templates/tests/conftest.py` and `templates/tests/test_tasks.py`
**What you're building:** Async integration tests for all CRUD endpoints.

#### Step 9.1 — Test Fixtures (`templates/tests/conftest.py`)

| # | What to implement | Where | Docs |
|---|-------------------|-------|------|
| 55 | Set `TEST_DATABASE_URL` — choose SQLite (`sqlite+aiosqlite:///./test.db`) or PostgreSQL | `TEST_DATABASE_URL` | |
| 56 | Create `test_engine` and `test_session_factory` | Module-level variables | [async SQLAlchemy](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) |
| 57 | `setup_database` fixture — create all tables before each test, drop after | `setup_database()` | |
| 58 | `db_session` fixture — yield a session from `test_session_factory` | `db_session()` | [pytest fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html) |
| 59 | `client` fixture — override `get_session`, create `AsyncClient` with `ASGITransport` | `client()` | [FastAPI async tests](https://fastapi.tiangolo.com/advanced/async-tests/) |
| 60 | `sample_task` fixture — POST a task, return the response JSON | `sample_task()` | |

#### Step 9.2 — Test Cases (`templates/tests/test_tasks.py`)

Implement all 15 test functions:

**CREATE tests:**
| # | Test | What to verify |
|---|------|---------------|
| 61 | `test_create_task_success` | POST valid payload -> 201, has id/title/status/created_at |
| 62 | `test_create_task_missing_title` | POST without title -> 422 |
| 63 | `test_create_task_default_values` | POST with only title -> status="todos", priority="medium" |

**LIST tests:**
| # | Test | What to verify |
|---|------|---------------|
| 64 | `test_list_tasks_empty` | GET with no tasks -> 200, empty list, total=0 |
| 65 | `test_list_tasks_returns_all` | Create 3, GET -> total=3 |
| 66 | `test_list_tasks_filter_by_status` | Filter by status=done -> only done tasks |
| 67 | `test_list_tasks_filter_by_priority` | Filter by priority=high -> only high tasks |

**GET tests:**
| # | Test | What to verify |
|---|------|---------------|
| 68 | `test_get_task_success` | GET valid ID -> 200, correct data |
| 69 | `test_get_task_not_found` | GET invalid ID -> 404 |

**UPDATE tests:**
| # | Test | What to verify |
|---|------|---------------|
| 70 | `test_update_task_success` | PATCH valid ID -> 200, field changed |
| 71 | `test_update_task_partial` | PATCH only title -> other fields unchanged |
| 72 | `test_update_task_not_found` | PATCH invalid ID -> 404 |

**DELETE tests:**
| # | Test | What to verify |
|---|------|---------------|
| 73 | `test_delete_task_success` | DELETE valid ID -> 204 |
| 74 | `test_delete_task_not_found` | DELETE invalid ID -> 404 |
| 75 | `test_delete_task_idempotent` | DELETE twice -> 204 then 404 |

**Running tests:**
```bash
make test                                  # inside Docker
# or
docker compose exec api pytest -v          # verbose
```

**Checkpoint:** All 15 tests pass.

---

## Quick Reference

### Commands

```bash
python3 orchestrate.py generate    # Write all 29 files from CONFIG + templates
python3 orchestrate.py up          # generate + docker compose up -d --build
python3 orchestrate.py down        # docker compose down
python3 orchestrate.py clean       # docker compose down -v (removes data!)
python3 orchestrate.py logs        # docker compose logs -f
python3 orchestrate.py logs api    # logs for one service
python3 orchestrate.py status      # docker compose ps
python3 orchestrate.py build       # generate + docker compose build
python3 orchestrate.py restart     # docker compose restart
```

Or via Makefile:
```bash
make up          make down        make logs
make build       make clean       make ps
make test        make migrate     make shell
```

### Service URLs (after `python3 orchestrate.py up`)

| Service | URL | Notes |
|---------|-----|-------|
| API (via Nginx) | http://localhost | Reverse proxy |
| API (direct) | http://localhost:8000 | Dev override |
| Health check | http://localhost/ | Returns `{"status": "ok"}` |
| API endpoints | http://localhost/api/v1/tasks | CRUD operations |
| Prometheus metrics | http://localhost/metrics | Text format |
| Prometheus UI | http://localhost:9090 | Query interface |
| Grafana | http://localhost:3000 | admin / changeme |

### API Endpoints

| Method | Path | Description | Status |
|--------|------|-------------|--------|
| `GET` | `/` | Health check | 200 |
| `POST` | `/api/v1/tasks` | Create task | 201 |
| `GET` | `/api/v1/tasks` | List tasks (with filters) | 200 |
| `GET` | `/api/v1/tasks/{id}` | Get single task | 200 / 404 |
| `PATCH` | `/api/v1/tasks/{id}` | Update task | 200 / 404 |
| `DELETE` | `/api/v1/tasks/{id}` | Delete task | 204 / 404 |
| `POST` | `/api/v1/tasks/report` | Trigger async report | 202 |
| `GET` | `/metrics` | Prometheus metrics | 200 |

### Config Quick Reference (orchestrate.py Section 1)

| Config | Default | Used in |
|--------|---------|---------|
| `postgres.user` | `"taskapp"` | .env, api/app.py, docker-compose.yml, alembic.ini |
| `postgres.password` | `"changeme_use_a_strong_password"` | .env, api/app.py, docker-compose.yml |
| `postgres.db` | `"taskdb"` | .env, api/app.py, docker-compose.yml |
| `postgres.port` | `5432` | .env, docker-compose.yml |
| `redis.host` | `"redis"` | .env, worker/app.py |
| `api.port` | `8000` | .env, api/app.py, Dockerfile, docker-compose, nginx, prometheus, healthcheck |
| `api.python_version` | `"3.12"` | api/Dockerfile, worker/Dockerfile |
| `nginx.external_port` | `80` | docker-compose.yml |
| `grafana.admin_password` | `"changeme"` | .env, docker-compose.yml |

---

## Phase Completion Checklist

```
[ ] Phase 1: API Core
    [ ] 1.1 Configuration — Settings loads from .env
    [ ] 1.2 Database Models — Task table with all columns
    [ ] 1.3 Database Session — async engine + session factory
    [ ] 1.4 Schemas — Pydantic validation models
    [ ] 1.5 Services — CRUD operations
    [ ] 1.6 Routes — All endpoints wired
    [ ] 1.7 App Setup — FastAPI instance, lifespan, router
    [ ] Verify: curl http://localhost/ returns {"status": "ok"}

[ ] Phase 2: Database Session (if deferred from 1.3)
    [ ] Verify: POST /api/v1/tasks creates a task in PostgreSQL

[ ] Phase 3: Redis Caching
    [ ] CacheService methods implemented
    [ ] Route handlers use cache (get, invalidate)
    [ ] Verify: second GET serves from cache

[ ] Phase 4: Celery Worker
    [ ] generate_report task implemented
    [ ] bulk_status_update task implemented
    [ ] API dispatches tasks via .delay()
    [ ] Verify: POST /api/v1/tasks/report returns 202

[ ] Phase 5: Dockerfiles — already complete
    [ ] Understand multi-stage builds
    [ ] Understand non-root user pattern

[ ] Phase 6: Docker Compose — already complete
    [ ] Understand service dependencies
    [ ] Understand volumes and networks

[ ] Phase 7: Prometheus Metrics
    [ ] Counter and Histogram created
    [ ] Middleware records metrics
    [ ] /metrics endpoint mounted
    [ ] Verify: curl http://localhost/metrics shows data

[ ] Phase 8: Nginx Security
    [ ] Security headers added
    [ ] Proxy headers configured
    [ ] Logging enabled
    [ ] Gzip compression enabled

[ ] Phase 9: Testing
    [ ] Test fixtures set up (engine, session, client)
    [ ] All 15 test cases implemented
    [ ] Verify: make test — all pass
```
