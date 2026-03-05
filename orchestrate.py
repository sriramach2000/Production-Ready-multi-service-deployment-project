#!/usr/bin/env python3
"""
orchestrate.py — Single Source of Truth for the Entire Project

Edit the CONFIG below, then run:
    python orchestrate.py generate   # Write all project files
    python orchestrate.py up         # Generate + start the stack

Change a config value once here, and it propagates everywhere.
Application code lives in templates/ as real Python files with << marker >> syntax.
Infrastructure templates live in templates/infra/ with the same marker syntax.
Static files (.gitignore, .dockerignore, grafana dashboards) are committed directly.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


# =============================================================================
#  1. CONFIGURATION — Edit This Section to Configure Your Entire Stack
# =============================================================================

@dataclass
class Config:
    """All config values for the entire stack. Change here, regenerate, done."""
    project_name: str = "taskapp"
    network_name: str = "app-network"
    restart_policy: str = "unless-stopped"

    # PostgreSQL
    pg_user: str = "taskapp"
    pg_password: str = "changeme_use_a_strong_password"
    pg_db: str = "taskdb"
    postgres_host: str = "postgres"
    pg_port: int = 5432
    postgres_image: str = "postgres:16-alpine"
    postgres_volume: str = "postgres-data"

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db_main: int = 0
    redis_db_results: int = 1
    redis_image: str = "redis:7-alpine"
    redis_volume: str = "redis-data"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    python_version: str = "3.12"
    debug: bool = False

    # Nginx
    nginx_external_port: int = 80
    nginx_image_version: str = "1.27-alpine"
    nginx_worker_connections: int = 1024
    nginx_keepalive_timeout: int = 65

    # Prometheus
    prometheus_image: str = "prom/prometheus:latest"
    prometheus_port: int = 9090
    prometheus_volume: str = "prometheus-data"
    prometheus_scrape_interval: str = "15s"
    prometheus_evaluation_interval: str = "15s"

    # Grafana
    grafana_image: str = "grafana/grafana:latest"
    grafana_port: int = 3000
    grafana_volume: str = "grafana-data"
    grafana_admin_user: str = "admin"
    grafana_admin_password: str = "changeme"

    # Derived properties
    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db_main}"

    @property
    def celery_broker_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db_main}"

    @property
    def celery_result_backend(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db_results}"

    @property
    def postgres_async_url(self) -> str:
        return f"postgresql+asyncpg://{self.pg_user}:{self.pg_password}@{self.postgres_host}:{self.pg_port}/{self.pg_db}"

    @property
    def postgres_sync_url(self) -> str:
        return f"postgresql://{self.pg_user}:{self.pg_password}@{self.postgres_host}:{self.pg_port}/{self.pg_db}"


CONFIG = Config()


# =============================================================================
#  2. TEMPLATE RENDERING
# =============================================================================

TEMPLATE_DIR = Path(__file__).parent / "templates"
PROJECT_ROOT = Path(__file__).parent

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


def render_template(template_path: str, config: Config) -> str:
    """Render a Jinja2 template using all Config fields as context."""
    # Expose every field + property as a flat dict for templates
    context = {}
    for field_name in config.__dataclass_fields__:
        context[field_name] = getattr(config, field_name)
    # Add derived properties
    for prop_name in ["redis_url", "celery_broker_url", "celery_result_backend",
                      "postgres_async_url", "postgres_sync_url"]:
        context[prop_name] = getattr(config, prop_name)

    # Also expose nested-style names for app templates (postgres.user, redis.url, etc.)
    context["postgres"] = type("P", (), {
        "user": config.pg_user, "password": config.pg_password,
        "db": config.pg_db, "host": config.postgres_host, "port": config.pg_port,
        "async_url": config.postgres_async_url, "sync_url": config.postgres_sync_url,
    })()
    context["redis"] = type("R", (), {
        "url": config.redis_url, "celery_broker_url": config.celery_broker_url,
        "celery_result_backend": config.celery_result_backend,
    })()
    context["api"] = type("A", (), {
        "host": config.api_host, "port": config.api_port,
    })()

    template = template_env.get_template(template_path)
    return template.render(**context)


def _gen_header(template_path: str) -> str:
    """Standard GENERATED header pointing to the source template."""
    return (
        f"# GENERATED by orchestrate.py from templates/{template_path}\n"
        f"# To modify: edit templates/{template_path}, then run: python orchestrate.py generate\n"
    )


# =============================================================================
#  3. FILE MANIFEST — Every Generated File
# =============================================================================

def get_file_manifest(config: Config) -> list[tuple[Path, str, str]]:
    """Returns (file_path, content, description) for every generated file."""
    manifest = []

    def add(path: str, template: str, desc: str, header: bool = True):
        content = render_template(template, config)
        if header:
            content = _gen_header(template) + content
        manifest.append((PROJECT_ROOT / path, content, desc))

    def add_raw(path: str, template: str, desc: str):
        """For non-Python files where # comments aren't appropriate."""
        content = render_template(template, config)
        manifest.append((PROJECT_ROOT / path, content, desc))

    # Application code (from app templates)
    add("api/app.py", "api/app.py", "FastAPI application")
    add("worker/app.py", "worker/app.py", "Celery worker")

    # Tests
    add("tests/conftest.py", "tests/conftest.py", "Test fixtures")
    add("tests/test_tasks.py", "tests/test_tasks.py", "CRUD endpoint tests")
    manifest.append((PROJECT_ROOT / "tests" / "__init__.py", "", "Tests package init"))

    # Infrastructure (from infra templates)
    add_raw("docker-compose.yml", "infra/docker-compose.yml", "Docker Compose services")
    add_raw("docker-compose.override.yml", "infra/docker-compose.override.yml", "Docker Compose dev overrides")
    add_raw("api/Dockerfile", "infra/api.Dockerfile", "API Dockerfile")
    add_raw("worker/Dockerfile", "infra/worker.Dockerfile", "Worker Dockerfile")
    add_raw("services/nginx/Dockerfile", "infra/nginx.Dockerfile", "Nginx Dockerfile")
    add_raw("services/nginx/nginx.conf", "infra/nginx.conf", "Nginx main config")
    add_raw("services/nginx/conf.d/default.conf", "infra/nginx-default.conf", "Nginx reverse proxy config")
    add_raw("services/prometheus/prometheus.yml", "infra/prometheus.yml", "Prometheus scrape config")
    add_raw("services/grafana/provisioning/datasources/datasource.yml",
            "infra/grafana-datasource.yml", "Grafana Prometheus datasource")
    add_raw("api/requirements.txt", "infra/api-requirements.txt", "API dependencies")
    add_raw("worker/requirements.txt", "infra/worker-requirements.txt", "Worker dependencies")

    # Environment files
    add_raw(".env", "infra/dot-env", "Environment variables")
    add_raw(".env.example", "infra/dot-env-example", "Environment example (safe to commit)")

    return manifest


# =============================================================================
#  4. FILE WRITER
# =============================================================================

def write_generated_files(config: Config) -> None:
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
#  5. CLI — Commands & Entry Point
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
    write_generated_files(CONFIG)

def cmd_up() -> None:
    write_generated_files(CONFIG)
    run_docker_compose("up", "-d", "--build")

def cmd_down() -> None:
    run_docker_compose("down")

def cmd_restart() -> None:
    run_docker_compose("restart")

def cmd_clean() -> None:
    print("WARNING: This will delete all data (database, Redis, Grafana, Prometheus).")
    run_docker_compose("down", "-v")

def cmd_build() -> None:
    write_generated_files(CONFIG)
    run_docker_compose("build")

def cmd_status() -> None:
    run_docker_compose("ps")

def cmd_test() -> None:
    write_generated_files(CONFIG)
    run_docker_compose("up", "-d", "--build")
    print("\n  [TEST] Running pytest inside the api container...\n")
    run_docker_compose("exec", "api", "pytest", "tests/", "-v", "--override-ini=asyncio_mode=auto")

def cmd_logs(service: str | None = None) -> None:
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
