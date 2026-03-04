#!/usr/bin/env python3
"""
orchestrate.py — Single Source of Truth for the Entire Project

Edit the CONFIG object in Section 1, then run:
    python orchestrate.py generate   # Write all project files
    python orchestrate.py up         # Generate + start the stack

Config files (Dockerfiles, docker-compose, nginx, etc.) are generated from
inline functions in this script. Application code (api/app.py, worker/app.py,
tests/, migrations/env.py) lives in templates/ as real Python files you edit
with full IDE support — config values use << marker >> syntax.

Change a config value once here, and it propagates everywhere.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


# =============================================================================
#  1. CONFIGURATION — Edit This Section to Configure Your Entire Stack
# =============================================================================

@dataclass
class PostgresConfig:
    """PostgreSQL database. The 'host' must match the docker-compose service name."""
    user: str = "taskapp"
    password: str = "changeme_use_a_strong_password"
    db: str = "taskdb"
    host: str = "postgres"
    port: int = 5432
    image: str = "postgres:16-alpine"
    volume_name: str = "postgres-data"

    @property
    def async_url(self) -> str:
        """Connection string for asyncpg (used by FastAPI)."""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"

    @property
    def sync_url(self) -> str:
        """Connection string for psycopg2 (used by Celery worker)."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


@dataclass
class RedisConfig:
    """Redis cache & message broker. Two DB numbers: app/broker and results."""
    host: str = "redis"
    port: int = 6379
    db_main: int = 0
    db_results: int = 1
    image: str = "redis:7-alpine"
    volume_name: str = "redis-data"

    @property
    def url(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.db_main}"

    @property
    def celery_broker_url(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.db_main}"

    @property
    def celery_result_backend(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.db_results}"


@dataclass
class ApiConfig:
    """FastAPI application settings."""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    python_version: str = "3.12"


@dataclass
class NginxConfig:
    """Nginx reverse proxy settings."""
    external_port: int = 80
    image_version: str = "1.27-alpine"
    worker_connections: int = 1024
    keepalive_timeout: int = 65


@dataclass
class PrometheusConfig:
    """Prometheus metrics collection."""
    port: int = 9090
    image: str = "prom/prometheus:latest"
    scrape_interval: str = "15s"
    evaluation_interval: str = "15s"
    volume_name: str = "prometheus-data"


@dataclass
class GrafanaConfig:
    """Grafana visualization."""
    port: int = 3000
    image: str = "grafana/grafana:latest"
    admin_user: str = "admin"
    admin_password: str = "changeme"
    volume_name: str = "grafana-data"


@dataclass
class ProjectConfig:
    """
    THE SINGLE SOURCE OF TRUTH.

    Every value that ends up in a generated file comes from here.
    Change a value here, run `python orchestrate.py generate`,
    and it propagates everywhere.
    """
    project_name: str = "taskapp"
    network_name: str = "app-network"
    restart_policy: str = "unless-stopped"

    postgres: PostgresConfig = field(default_factory=PostgresConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    nginx: NginxConfig = field(default_factory=NginxConfig)
    prometheus: PrometheusConfig = field(default_factory=PrometheusConfig)
    grafana: GrafanaConfig = field(default_factory=GrafanaConfig)


# ── Edit values here, then run: python orchestrate.py up ─────────────────────
CONFIG = ProjectConfig()
# ─────────────────────────────────────────────────────────────────────────────


# =============================================================================
#  2. TEMPLATE RENDERING — Application Code
# =============================================================================
#
# Application code (api/app.py, worker/app.py, tests/, migrations/env.py) lives
# in the templates/ directory as regular Python files you edit with full IDE
# support.  Config values use << marker >> syntax (Jinja2 custom delimiters).


# Templates directory:
#   templates/api/app.py            ← << postgres.user >>, << api.port >>, etc.
#   templates/worker/app.py         ← << redis.celery_broker_url >>, etc.
#   templates/tests/conftest.py     ← pure Python (no markers)
#   templates/tests/test_tasks.py   ← pure Python (no markers)
#   templates/tests/__init__.py     ← empty
#   templates/migrations/env.py     ← << postgres.async_url >> (comment only)
# =============================================================================

TEMPLATE_DIR = Path(__file__).parent / "templates"

template_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    variable_start_string="<<",
    variable_end_string=">>",
    block_start_string="<%",
    block_end_string="%>",
    comment_start_string="<#",
    comment_end_string="#>",
    keep_trailing_newline=True,
)


def render_template(template_path: str, config: ProjectConfig, header_lines: list[str] | None = None) -> str:
    """
    Render a Jinja2 template with CONFIG values.

    The template context exposes each config sub-object by name, so templates
    use << postgres.user >>, << redis.url >>, << api.port >>, etc.

    If header_lines is provided, they are prepended to the rendered output.
    """
    context = {
        "postgres": config.postgres,
        "redis": config.redis,
        "api": config.api,
        "nginx": config.nginx,
        "prometheus": config.prometheus,
        "grafana": config.grafana,
        "project": config,
    }
    template = template_env.get_template(template_path)
    rendered = template.render(**context)

    if header_lines:
        header = "\n".join(header_lines) + "\n"
        return header + rendered
    return rendered


def _template_header(template_path: str) -> list[str]:
    """Standard GENERATED header pointing to the source template."""
    return [
        f"# GENERATED by orchestrate.py from templates/{template_path}",
        f"# To modify application code: edit templates/{template_path}",
        "# To modify config values: edit CONFIG in orchestrate.py",
        "# Then run: python3 orchestrate.py generate",
    ]


# --- Convenience wrappers (called from the file manifest) ---

def generate_api_app(config: ProjectConfig) -> str:
    return render_template("api/app.py", config, _template_header("api/app.py"))


def generate_worker_app(config: ProjectConfig) -> str:
    return render_template("worker/app.py", config, _template_header("worker/app.py"))


def generate_conftest(config: ProjectConfig) -> str:
    return render_template("tests/conftest.py", config, _template_header("tests/conftest.py"))


def generate_test_tasks(config: ProjectConfig) -> str:
    return render_template("tests/test_tasks.py", config, _template_header("tests/test_tasks.py"))


def generate_tests_init(config: ProjectConfig) -> str:
    return render_template("tests/__init__.py", config, ["# GENERATED by orchestrate.py"])


def generate_alembic_env(config: ProjectConfig) -> str:
    return render_template("migrations/env.py", config, _template_header("migrations/env.py"))


# =============================================================================
#  3. GENERATORS — Dependencies
# =============================================================================

def generate_api_requirements(c: ProjectConfig) -> str:
    """Generate api/requirements.txt — pinned dependencies."""
    return textwrap.dedent("""\
        # GENERATED by orchestrate.py — do not edit manually.
        # Re-generate: python orchestrate.py generate

        # Web framework
        fastapi==0.135.1            # https://pypi.org/project/fastapi/
        uvicorn[standard]==0.41.0   # https://pypi.org/project/uvicorn/

        # Database
        sqlalchemy[asyncio]==2.0.48  # https://pypi.org/project/sqlalchemy/
        asyncpg==0.31.0              # https://pypi.org/project/asyncpg/
        alembic==1.18.4              # https://pypi.org/project/alembic/

        # Caching
        redis==7.2.1  # includes asyncio support — https://pypi.org/project/redis/

        # Task Queue (for dispatching to worker)
        celery==5.6.2  # https://pypi.org/project/celery/

        # Configuration
        pydantic-settings==2.13.1  # https://pypi.org/project/pydantic-settings/

        # Monitoring
        prometheus-client==0.24.1  # https://pypi.org/project/prometheus-client/

        # Testing
        pytest==8.3.5          # https://pypi.org/project/pytest/
        pytest-asyncio==0.25.3 # https://pypi.org/project/pytest-asyncio/
        httpx==0.28.1          # https://pypi.org/project/httpx/
        aiosqlite==0.21.0      # https://pypi.org/project/aiosqlite/
    """)


def generate_worker_requirements(c: ProjectConfig) -> str:
    """Generate worker/requirements.txt — pinned dependencies."""
    return textwrap.dedent("""\
        # GENERATED by orchestrate.py — do not edit manually.
        # Re-generate: python orchestrate.py generate
        # NOTE: Worker uses synchronous SQLAlchemy (not async) because Celery is process-based.

        celery==5.6.2           # https://pypi.org/project/celery/
        redis==7.2.1            # https://pypi.org/project/redis/
        sqlalchemy==2.0.48      # https://pypi.org/project/sqlalchemy/
        psycopg2-binary==2.9.11  # https://pypi.org/project/psycopg2-binary/
    """)


# =============================================================================
#  4. GENERATORS — Dockerfiles
# =============================================================================

def generate_api_dockerfile(c: ProjectConfig) -> str:
    """Generate api/Dockerfile — multi-stage build for FastAPI."""
    return textwrap.dedent(f"""\
        # GENERATED by orchestrate.py — do not edit manually.
        # Re-generate: python orchestrate.py generate

        # ---- Stage 1: Builder ----
        FROM python:{c.api.python_version}-slim AS builder
        WORKDIR /app
        COPY requirements.txt .
        RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

        # ---- Stage 2: Production ----
        FROM python:{c.api.python_version}-slim
        RUN addgroup --system appgroup && adduser --system --group appuser
        WORKDIR /app
        COPY --from=builder /install /usr/local
        COPY ./app.py ./app.py
        USER appuser
        EXPOSE {c.api.port}
        HEALTHCHECK --interval=30s --timeout=5s --retries=3 \\
          CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:{c.api.port}/')"
        CMD ["uvicorn", "app:app", "--host", "{c.api.host}", "--port", "{c.api.port}"]
    """)


def generate_worker_dockerfile(c: ProjectConfig) -> str:
    """Generate worker/Dockerfile — multi-stage build for Celery worker."""
    return textwrap.dedent(f"""\
        # GENERATED by orchestrate.py — do not edit manually.
        # Re-generate: python orchestrate.py generate

        # ---- Stage 1: Builder ----
        FROM python:{c.api.python_version}-slim AS builder
        WORKDIR /app
        COPY requirements.txt .
        RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

        # ---- Stage 2: Production ----
        FROM python:{c.api.python_version}-slim
        RUN addgroup --system appgroup && adduser --system --group appuser
        WORKDIR /app
        COPY --from=builder /install /usr/local
        COPY ./app.py ./app.py
        USER appuser
        HEALTHCHECK --interval=30s --timeout=10s --retries=3 \\
          CMD celery -A app inspect ping || exit 1
        CMD ["celery", "-A", "app", "worker", "--loglevel=info"]
    """)


def generate_nginx_dockerfile(c: ProjectConfig) -> str:
    """Generate services/nginx/Dockerfile."""
    return textwrap.dedent(f"""\
        # GENERATED by orchestrate.py — do not edit manually.
        # Re-generate: python orchestrate.py generate

        FROM nginx:{c.nginx.image_version}
        RUN rm /etc/nginx/conf.d/default.conf
        COPY nginx.conf /etc/nginx/nginx.conf
        COPY conf.d/ /etc/nginx/conf.d/
        EXPOSE 80
    """)


# =============================================================================
#  5. GENERATORS — Docker Compose & Environment
# =============================================================================

def generate_env_file(c: ProjectConfig) -> str:
    """Generate .env — all environment variables from CONFIG."""
    return textwrap.dedent(f"""\
        # GENERATED by orchestrate.py — do not edit manually.
        # Re-generate: python orchestrate.py generate
        # NEVER commit this file to git.

        # --- PostgreSQL ---
        POSTGRES_USER={c.postgres.user}
        POSTGRES_PASSWORD={c.postgres.password}
        POSTGRES_DB={c.postgres.db}
        POSTGRES_HOST={c.postgres.host}
        POSTGRES_PORT={c.postgres.port}

        # --- Redis ---
        REDIS_URL={c.redis.url}

        # --- Celery ---
        CELERY_BROKER_URL={c.redis.celery_broker_url}
        CELERY_RESULT_BACKEND={c.redis.celery_result_backend}

        # --- API ---
        API_HOST={c.api.host}
        API_PORT={c.api.port}
        DEBUG={str(c.api.debug).lower()}

        # --- Grafana ---
        GF_SECURITY_ADMIN_USER={c.grafana.admin_user}
        GF_SECURITY_ADMIN_PASSWORD={c.grafana.admin_password}
    """)


def generate_env_example(c: ProjectConfig) -> str:
    """Generate .env.example — safe-to-commit reference."""
    return textwrap.dedent(f"""\
        # GENERATED by orchestrate.py — do not edit manually.
        # Copy this file: cp .env.example .env
        # Then fill in real values. NEVER commit .env to git.

        # --- PostgreSQL ---
        POSTGRES_USER={c.postgres.user}
        POSTGRES_PASSWORD=changeme_use_a_strong_password
        POSTGRES_DB={c.postgres.db}
        POSTGRES_HOST={c.postgres.host}
        POSTGRES_PORT={c.postgres.port}

        # --- Redis ---
        REDIS_URL={c.redis.url}

        # --- Celery ---
        CELERY_BROKER_URL={c.redis.celery_broker_url}
        CELERY_RESULT_BACKEND={c.redis.celery_result_backend}

        # --- API ---
        API_HOST={c.api.host}
        API_PORT={c.api.port}
        DEBUG=false

        # --- Grafana ---
        GF_SECURITY_ADMIN_USER={c.grafana.admin_user}
        GF_SECURITY_ADMIN_PASSWORD=changeme
    """)


def generate_docker_compose(c: ProjectConfig) -> str:
    """Generate docker-compose.yml — all 7 services."""
    return textwrap.dedent(f"""\
        # GENERATED by orchestrate.py — do not edit manually.
        # Re-generate: python orchestrate.py generate

        services:
          {c.postgres.host}:
            image: {c.postgres.image}
            env_file: .env      # reads: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
            volumes:
              - {c.postgres.volume_name}:/var/lib/postgresql/data
            networks:
              - {c.network_name}
            restart: {c.restart_policy}
            healthcheck:
              test: ["CMD-SHELL", "pg_isready -U {c.postgres.user}"]
              interval: 10s
              timeout: 5s
              retries: 5

          {c.redis.host}:
            image: {c.redis.image}
            volumes:
              - {c.redis.volume_name}:/data
            networks:
              - {c.network_name}
            restart: {c.restart_policy}
            healthcheck:
              test: ["CMD", "redis-cli", "ping"]
              interval: 10s
              timeout: 5s
              retries: 5

          api:
            build: ./api
            env_file: .env      # reads: POSTGRES_*, REDIS_URL, CELERY_*, API_*, DEBUG
            depends_on:
              {c.postgres.host}:
                condition: service_healthy
              {c.redis.host}:
                condition: service_healthy
            networks:
              - {c.network_name}
            restart: {c.restart_policy}
            healthcheck:
              test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:{c.api.port}/')"]
              interval: 30s
              timeout: 5s
              retries: 3

          worker:
            build: ./worker
            env_file: .env      # reads: CELERY_*, POSTGRES_*
            depends_on:
              {c.postgres.host}:
                condition: service_healthy
              {c.redis.host}:
                condition: service_healthy
            networks:
              - {c.network_name}
            restart: {c.restart_policy}

          nginx:
            build: ./services/nginx
            ports:
              - "{c.nginx.external_port}:80"
            depends_on:
              api:
                condition: service_healthy
            networks:
              - {c.network_name}
            restart: {c.restart_policy}

          prometheus:
            image: {c.prometheus.image}
            volumes:
              - ./services/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
              - {c.prometheus.volume_name}:/prometheus
            ports:
              - "{c.prometheus.port}:9090"
            networks:
              - {c.network_name}
            restart: {c.restart_policy}

          grafana:
            image: {c.grafana.image}
            env_file: .env      # reads: GF_SECURITY_ADMIN_USER, GF_SECURITY_ADMIN_PASSWORD
            volumes:
              - {c.grafana.volume_name}:/var/lib/grafana
              - ./services/grafana/provisioning:/etc/grafana/provisioning:ro
              - ./services/grafana/dashboards:/var/lib/grafana/dashboards:ro
            ports:
              - "{c.grafana.port}:3000"
            networks:
              - {c.network_name}
            restart: {c.restart_policy}

        networks:
          {c.network_name}:
            driver: bridge

        volumes:
          {c.postgres.volume_name}:
          {c.redis.volume_name}:
          {c.prometheus.volume_name}:
          {c.grafana.volume_name}:
    """)


def generate_docker_compose_override(c: ProjectConfig) -> str:
    """Generate docker-compose.override.yml — dev overrides."""
    return textwrap.dedent(f"""\
        # GENERATED by orchestrate.py — do not edit manually.
        # Re-generate: python orchestrate.py generate
        #
        # Dev overrides — automatically merged with docker-compose.yml.
        # Adds hot-reload, debug mode, and exposes internal ports.
        # Production only: docker compose -f docker-compose.yml up

        services:
          api:
            volumes:
              - ./api/app.py:/app/app.py
              - ./tests:/app/tests
            command: ["uvicorn", "app:app", "--host", "{c.api.host}", "--port", "{c.api.port}", "--reload"]
            ports:
              - "{c.api.port}:{c.api.port}"
            environment:
              - DEBUG=true

          {c.postgres.host}:
            ports:
              - "{c.postgres.port}:{c.postgres.port}"

          {c.redis.host}:
            ports:
              - "{c.redis.port}:{c.redis.port}"
    """)


# =============================================================================
#  6. GENERATORS — Nginx
# =============================================================================

def generate_nginx_conf(c: ProjectConfig) -> str:
    """Generate services/nginx/nginx.conf — main nginx configuration."""
    return textwrap.dedent(f"""\
        # GENERATED by orchestrate.py — do not edit manually.
        # Re-generate: python orchestrate.py generate

        worker_processes auto;

        events {{
            worker_connections {c.nginx.worker_connections};
        }}

        http {{
            include       /etc/nginx/mime.types;
            default_type  application/octet-stream;

            access_log /var/log/nginx/access.log;
            error_log  /var/log/nginx/error.log;

            gzip on;
            gzip_types text/plain application/json application/javascript text/css;

            sendfile    on;
            tcp_nopush  on;
            tcp_nodelay on;

            keepalive_timeout {c.nginx.keepalive_timeout};

            include /etc/nginx/conf.d/*.conf;
        }}
    """)


def generate_nginx_default_conf(c: ProjectConfig) -> str:
    """Generate services/nginx/conf.d/default.conf — reverse proxy config."""
    # Note: $host, $remote_addr etc. are nginx variables, not Python
    return (
        "# GENERATED by orchestrate.py — do not edit manually.\n"
        "# Re-generate: python orchestrate.py generate\n"
        "\n"
        "upstream api {\n"
        f"    server api:{c.api.port};\n"
        "}\n"
        "\n"
        "server {\n"
        "    listen 80;\n"
        "    server_name _;\n"
        "\n"
        "    add_header X-Frame-Options DENY always;\n"
        "    add_header X-Content-Type-Options nosniff always;\n"
        '    add_header X-XSS-Protection "1; mode=block" always;\n'
        "    add_header Referrer-Policy strict-origin-when-cross-origin always;\n"
        "\n"
        "    location / {\n"
        "        proxy_pass http://api;\n"
        "        proxy_set_header Host $host;\n"
        "        proxy_set_header X-Real-IP $remote_addr;\n"
        "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
        "        proxy_set_header X-Forwarded-Proto $scheme;\n"
        "    }\n"
        "\n"
        "    location /metrics {\n"
        "        proxy_pass http://api/metrics;\n"
        "    }\n"
        "}\n"
    )


# =============================================================================
#  7. GENERATORS — Monitoring (Prometheus & Grafana)
# =============================================================================

def generate_prometheus_yml(c: ProjectConfig) -> str:
    """Generate services/prometheus/prometheus.yml — scrape configuration."""
    return textwrap.dedent(f"""\
        # GENERATED by orchestrate.py — do not edit manually.
        # Re-generate: python orchestrate.py generate

        global:
          scrape_interval: {c.prometheus.scrape_interval}
          evaluation_interval: {c.prometheus.evaluation_interval}

        scrape_configs:
          - job_name: "fastapi"
            static_configs:
              - targets: ["api:{c.api.port}"]
            metrics_path: "/metrics"

          - job_name: "prometheus"
            static_configs:
              - targets: ["localhost:9090"]
    """)


def generate_grafana_datasource(c: ProjectConfig) -> str:
    """Generate services/grafana/provisioning/datasources/datasource.yml."""
    return textwrap.dedent(f"""\
        # GENERATED by orchestrate.py — do not edit manually.
        # Re-generate: python orchestrate.py generate

        apiVersion: 1
        datasources:
          - name: Prometheus
            type: prometheus
            access: proxy
            url: http://prometheus:{c.prometheus.port}
            isDefault: true
            editable: false
    """)


def generate_grafana_dashboard_provider(c: ProjectConfig) -> str:
    """Generate services/grafana/provisioning/dashboards/dashboard.yml."""
    return textwrap.dedent("""\
        # GENERATED by orchestrate.py — do not edit manually.
        # Re-generate: python orchestrate.py generate

        apiVersion: 1
        providers:
          - name: "default"
            orgId: 1
            folder: ""
            type: file
            disableDeletion: false
            editable: true
            options:
              path: /var/lib/grafana/dashboards
              foldersFromFilesStructure: false
    """)


def generate_grafana_dashboard_json(c: ProjectConfig) -> str:
    """Generate services/grafana/dashboards/api_dashboard.json — starter dashboard."""
    dashboard = {
        "__comment": "GENERATED by orchestrate.py — do not edit manually.",
        "annotations": {"list": []},
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 0,
        "id": None,
        "links": [],
        "panels": [
            {
                "title": "Request Rate (req/sec)",
                "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
                "targets": [
                    {
                        "expr": "rate(http_requests_total[5m])",
                        "legendFormat": "{{method}} {{endpoint}}",
                        "refId": "A",
                    }
                ],
                "datasource": {"type": "prometheus", "uid": "prometheus"},
            },
            {
                "title": "Request Duration (p95)",
                "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
                "targets": [
                    {
                        "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))",
                        "legendFormat": "p95 {{endpoint}}",
                        "refId": "A",
                    }
                ],
                "datasource": {"type": "prometheus", "uid": "prometheus"},
            },
            {
                "title": "Error Rate (4xx + 5xx)",
                "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
                "targets": [
                    {
                        "expr": 'rate(http_requests_total{status_code=~"[45].."}[5m])',
                        "legendFormat": "{{status_code}} {{endpoint}}",
                        "refId": "A",
                    }
                ],
                "datasource": {"type": "prometheus", "uid": "prometheus"},
            },
            {
                "title": "Active Requests",
                "type": "gauge",
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
                "targets": [
                    {
                        "expr": "http_requests_total",
                        "legendFormat": "total",
                        "refId": "A",
                    }
                ],
                "datasource": {"type": "prometheus", "uid": "prometheus"},
            },
        ],
        "schemaVersion": 39,
        "tags": ["fastapi", "api"],
        "templating": {"list": []},
        "time": {"from": "now-1h", "to": "now"},
        "title": "FastAPI API Dashboard",
        "uid": "fastapi-api-dashboard",
        "version": 1,
    }
    return json.dumps(dashboard, indent=2) + "\n"


# =============================================================================
#  8. GENERATORS — Database Migrations (Alembic)
# =============================================================================

def generate_alembic_ini(c: ProjectConfig) -> str:
    """Generate alembic.ini — Alembic migration configuration."""
    return textwrap.dedent(f"""\
        # GENERATED by orchestrate.py — do not edit manually.
        # Re-generate: python orchestrate.py generate
        #
        # Alembic Configuration
        # Docs: https://alembic.sqlalchemy.org/en/latest/tutorial.html

        [alembic]
        script_location = migrations
        sqlalchemy.url = {c.postgres.async_url}

        [loggers]
        keys = root,sqlalchemy,alembic

        [handlers]
        keys = console

        [formatters]
        keys = generic

        [logger_root]
        level = WARN
        handlers = console

        [logger_sqlalchemy]
        level = WARN
        handlers =
        qualname = sqlalchemy.engine

        [logger_alembic]
        level = INFO
        handlers =
        qualname = alembic

        [handler_console]
        class = StreamHandler
        args = (sys.stderr,)
        level = NOTSET
        formatter = generic

        [formatter_generic]
        format = %(levelname)-5.5s [%(name)s] %(message)s
        datefmt = %H:%M:%S
    """)


def generate_alembic_script_mako(c: ProjectConfig) -> str:
    """Generate migrations/script.py.mako — template for new migration files."""
    # Using raw string + replace to avoid mako template conflicts
    return (
        '# GENERATED by orchestrate.py — do not edit manually.\n'
        '"""${message}\n'
        '\n'
        'Revision ID: ${up_revision}\n'
        'Revises: ${down_revision | comma,n}\n'
        'Create Date: ${create_date}\n'
        '"""\n'
        'from typing import Sequence, Union\n'
        '\n'
        'from alembic import op\n'
        'import sqlalchemy as sa\n'
        '${imports if imports else ""}\n'
        '\n'
        '# revision identifiers, used by Alembic.\n'
        'revision: str = ${repr(up_revision)}\n'
        'down_revision: Union[str, None] = ${repr(down_revision)}\n'
        'branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}\n'
        'depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}\n'
        '\n'
        '\n'
        'def upgrade() -> None:\n'
        '    ${upgrades if upgrades else "pass"}\n'
        '\n'
        '\n'
        'def downgrade() -> None:\n'
        '    ${downgrades if downgrades else "pass"}\n'
    )


def generate_migrations_readme(c: ProjectConfig) -> str:
    """Generate migrations/README."""
    return textwrap.dedent("""\
        # GENERATED by orchestrate.py — do not edit manually.
        #
        # migrations/ — Alembic Database Migrations Directory
        #
        # Common commands:
        #   alembic revision --autogenerate -m "create tasks table"
        #   alembic upgrade head
        #   alembic downgrade -1
        #   alembic history
        #
        # Docs: https://alembic.sqlalchemy.org/en/latest/tutorial.html
    """)


def generate_migrations_versions_gitkeep(c: ProjectConfig) -> str:
    """Generate migrations/versions/.gitkeep — ensures the directory exists in git."""
    return ""


# =============================================================================
# 10. GENERATORS — Build Tools & Project Files
# =============================================================================

def generate_makefile(c: ProjectConfig) -> str:
    """Generate Makefile — common development commands."""
    return textwrap.dedent("""\
        # GENERATED by orchestrate.py — do not edit manually.
        # Re-generate: python orchestrate.py generate

        .PHONY: help generate build up down restart logs ps clean migrate test shell

        help: ## Show this help message
        \t@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\\033[36m%-15s\\033[0m %s\\n", $$1, $$2}'

        generate: ## Generate all project files from orchestrate.py
        \tpython orchestrate.py generate

        build: ## Generate files and build all Docker images
        \tpython orchestrate.py build

        up: ## Generate files, build, and start all services
        \tpython orchestrate.py up

        down: ## Stop and remove all containers
        \tpython orchestrate.py down

        restart: ## Restart all services
        \tpython orchestrate.py restart

        logs: ## Follow logs from all services
        \tpython orchestrate.py logs

        ps: ## Show status of all services
        \tpython orchestrate.py status

        clean: ## Stop services and remove ALL data volumes
        \tpython orchestrate.py clean

        migrate: ## Run database migrations
        \tdocker compose exec api alembic upgrade head

        test: ## Run tests inside the API container
        \tdocker compose exec api pytest

        shell: ## Open a shell in the API container
        \tdocker compose exec api /bin/sh
    """)


def generate_healthcheck_sh(c: ProjectConfig) -> str:
    """Generate scripts/healthcheck.sh — container health check script."""
    return textwrap.dedent(f"""\
        #!/bin/bash
        # GENERATED by orchestrate.py — do not edit manually.
        # Re-generate: python orchestrate.py generate
        #
        # Health check script for Docker HEALTHCHECK directive.
        # Exit code 0 = healthy, exit code 1 = unhealthy.
        # Docs: https://docs.docker.com/reference/dockerfile/#healthcheck

        curl -f http://localhost:{c.api.port}/ || exit 1
    """)


def generate_gitignore(c: ProjectConfig) -> str:
    """Generate .gitignore."""
    return textwrap.dedent("""\
        # GENERATED by orchestrate.py — do not edit manually.
        # Re-generate: python orchestrate.py generate

        # Environment files (NEVER commit secrets)
        .env
        .env.*
        !.env.example

        # Python
        __pycache__/
        *.py[cod]
        *$py.class
        *.egg-info/
        dist/
        build/
        .eggs/

        # Virtual environments
        venv/
        .venv/
        env/

        # IDE
        .vscode/
        .idea/
        *.swp
        *.swo
        .DS_Store

        # Testing
        .pytest_cache/
        .coverage
        htmlcov/

        # Type checking
        .mypy_cache/

        # Docker volumes data (if accidentally created locally)
        postgres-data/
        redis-data/
    """)


def generate_dockerignore(c: ProjectConfig) -> str:
    """Generate .dockerignore."""
    return textwrap.dedent("""\
        # GENERATED by orchestrate.py — do not edit manually.
        # Re-generate: python orchestrate.py generate

        .git
        .gitignore
        .env
        .env.*
        __pycache__
        *.pyc
        *.pyo
        .pytest_cache
        .mypy_cache
        .vscode
        .idea
        *.md
        tests/
        docker-compose*.yml
        .dockerignore
        scripts/
        templates/
        orchestrate.py
        .DS_Store
    """)


# =============================================================================
# 11. FILE WRITER — Manifest & Disk I/O
# =============================================================================

PROJECT_ROOT = Path(__file__).parent


def get_file_manifest(config: ProjectConfig) -> list[tuple[Path, str, str]]:
    """
    Returns (file_path, content, description) for every generated file.
    Adding a new file = one new entry here + one new generator function.
    """
    return [
        # Section 2 (Templates): Application Code — edit templates/ directly
        (PROJECT_ROOT / "api" / "app.py",
         generate_api_app(config), "FastAPI application"),
        (PROJECT_ROOT / "worker" / "app.py",
         generate_worker_app(config), "Celery worker"),

        # Section 3: Dependencies
        (PROJECT_ROOT / "api" / "requirements.txt",
         generate_api_requirements(config), "API dependencies"),
        (PROJECT_ROOT / "worker" / "requirements.txt",
         generate_worker_requirements(config), "Worker dependencies"),

        # Section 4: Dockerfiles
        (PROJECT_ROOT / "api" / "Dockerfile",
         generate_api_dockerfile(config), "API Dockerfile"),
        (PROJECT_ROOT / "worker" / "Dockerfile",
         generate_worker_dockerfile(config), "Worker Dockerfile"),
        (PROJECT_ROOT / "services" / "nginx" / "Dockerfile",
         generate_nginx_dockerfile(config), "Nginx Dockerfile"),

        # Section 5: Docker Compose & Environment
        (PROJECT_ROOT / ".env",
         generate_env_file(config), "Environment variables"),
        (PROJECT_ROOT / ".env.example",
         generate_env_example(config), "Environment example (safe to commit)"),
        (PROJECT_ROOT / "docker-compose.yml",
         generate_docker_compose(config), "Docker Compose services"),
        (PROJECT_ROOT / "docker-compose.override.yml",
         generate_docker_compose_override(config), "Docker Compose dev overrides"),

        # Section 6: Nginx
        (PROJECT_ROOT / "services" / "nginx" / "nginx.conf",
         generate_nginx_conf(config), "Nginx main config"),
        (PROJECT_ROOT / "services" / "nginx" / "conf.d" / "default.conf",
         generate_nginx_default_conf(config), "Nginx reverse proxy config"),

        # Section 7: Monitoring
        (PROJECT_ROOT / "services" / "prometheus" / "prometheus.yml",
         generate_prometheus_yml(config), "Prometheus scrape config"),
        (PROJECT_ROOT / "services" / "grafana" / "provisioning" / "datasources" / "datasource.yml",
         generate_grafana_datasource(config), "Grafana Prometheus datasource"),
        (PROJECT_ROOT / "services" / "grafana" / "provisioning" / "dashboards" / "dashboard.yml",
         generate_grafana_dashboard_provider(config), "Grafana dashboard provider"),
        (PROJECT_ROOT / "services" / "grafana" / "dashboards" / "api_dashboard.json",
         generate_grafana_dashboard_json(config), "Grafana starter dashboard"),

        # Section 8: Alembic
        (PROJECT_ROOT / "alembic.ini",
         generate_alembic_ini(config), "Alembic configuration"),
        (PROJECT_ROOT / "migrations" / "env.py",
         generate_alembic_env(config), "Alembic runtime environment (template)"),
        (PROJECT_ROOT / "migrations" / "script.py.mako",
         generate_alembic_script_mako(config), "Alembic migration template"),
        (PROJECT_ROOT / "migrations" / "README",
         generate_migrations_readme(config), "Migrations directory README"),
        (PROJECT_ROOT / "migrations" / "versions" / ".gitkeep",
         generate_migrations_versions_gitkeep(config), "Versions directory placeholder"),

        # Section 2 (Templates): Tests
        (PROJECT_ROOT / "tests" / "conftest.py",
         generate_conftest(config), "Test fixtures"),
        (PROJECT_ROOT / "tests" / "test_tasks.py",
         generate_test_tasks(config), "CRUD endpoint tests"),
        (PROJECT_ROOT / "tests" / "__init__.py",
         generate_tests_init(config), "Tests package init"),

        # Section 10: Build Tools & Project Files
        (PROJECT_ROOT / "Makefile",
         generate_makefile(config), "Makefile commands"),
        (PROJECT_ROOT / "scripts" / "healthcheck.sh",
         generate_healthcheck_sh(config), "Health check script"),
        (PROJECT_ROOT / ".gitignore",
         generate_gitignore(config), "Git ignore rules"),
        (PROJECT_ROOT / ".dockerignore",
         generate_dockerignore(config), "Docker ignore rules"),
    ]


def write_generated_files(config: ProjectConfig) -> None:
    """Generate and write all files from the config object."""
    manifest = get_file_manifest(config)
    print(f"\n--- Generating {len(manifest)} files from CONFIG ---\n")

    for filepath, content, description in manifest:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content)
        rel = filepath.relative_to(PROJECT_ROOT)
        print(f"  [\u2713] {str(rel):<60s} {description}")

    print(f"\n--- All {len(manifest)} files generated ---\n")


# =============================================================================
# 12. CLI — Commands & Entry Point
# =============================================================================

def run_docker_compose(*args: str) -> int:
    """Run a docker compose command. Returns exit code."""
    if shutil.which("docker"):
        cmd = ["docker", "compose", *args]
    elif shutil.which("docker-compose"):
        cmd = ["docker-compose", *args]
    else:
        print("ERROR: Docker not found. Install: https://docs.docker.com/get-docker/")
        sys.exit(1)

    print(f"  [RUN] {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=PROJECT_ROOT).returncode


def cmd_generate() -> None:
    """Generate all project files from CONFIG."""
    write_generated_files(CONFIG)


def cmd_up() -> None:
    """Generate files, build images, and start all services."""
    write_generated_files(CONFIG)
    run_docker_compose("up", "-d", "--build")


def cmd_down() -> None:
    """Stop and remove all containers."""
    run_docker_compose("down")


def cmd_restart() -> None:
    """Restart all services."""
    run_docker_compose("restart")


def cmd_clean() -> None:
    """Stop all services and remove volumes (full data reset)."""
    print("WARNING: This will delete all data (database, Redis, Grafana, Prometheus).")
    run_docker_compose("down", "-v")


def cmd_build() -> None:
    """Generate files and build all Docker images."""
    write_generated_files(CONFIG)
    run_docker_compose("build")


def cmd_status() -> None:
    """Show container status."""
    run_docker_compose("ps")


def cmd_test() -> None:
    """Generate files, rebuild API, and run pytest inside the container."""
    write_generated_files(CONFIG)
    run_docker_compose("up", "-d", "--build")
    print("\n  [TEST] Running pytest inside the api container...\n")
    run_docker_compose("exec", "api", "pytest", "tests/", "-v", '--override-ini=asyncio_mode=auto')


def cmd_logs(service: str | None = None) -> None:
    """Follow logs from all services (or a specific one)."""
    args = ["logs", "-f"]
    if service:
        args.append(service)
    run_docker_compose(*args)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Single source of truth — generate all project files and manage the Docker stack.",
        epilog="Example: python orchestrate.py up",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("generate", help="Generate all project files from CONFIG")
    sub.add_parser("up", help="Generate + build + start all services")
    sub.add_parser("down", help="Stop and remove all containers")
    sub.add_parser("restart", help="Restart all services")
    sub.add_parser("clean", help="Stop services and remove ALL data volumes")
    sub.add_parser("build", help="Generate + build Docker images")
    sub.add_parser("status", help="Show container status")
    sub.add_parser("test", help="Generate + rebuild + run pytest inside the api container")

    logs_parser = sub.add_parser("logs", help="Follow service logs")
    logs_parser.add_argument("service", nargs="?", default=None, help="Optional service name")

    args = parser.parse_args()

    commands = {
        "generate": cmd_generate,
        "up": cmd_up,
        "down": cmd_down,
        "restart": cmd_restart,
        "clean": cmd_clean,
        "build": cmd_build,
        "status": cmd_status,
        "test": cmd_test,
    }

    if args.command == "logs":
        cmd_logs(args.service)
    elif args.command in commands:
        commands[args.command]()


if __name__ == "__main__":
    main()
