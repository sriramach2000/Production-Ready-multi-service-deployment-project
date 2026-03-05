# templates/worker/app.py — Celery Background Worker
# Config values use << marker >> syntax, filled in by orchestrate.py at generate time.
# Edit THIS file, then run: python orchestrate.py generate
#
# The worker uses synchronous SQLAlchemy (not async) because Celery is process-based.

import os
from typing import Any

from celery import Celery
from sqlalchemy import create_engine, text
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session


# =============================================================================
# 1. CELERY CONFIGURATION
# =============================================================================

celery_app = Celery("worker")
celery_app.conf.broker_url = os.getenv("CELERY_BROKER_URL", "<< redis.celery_broker_url >>")
celery_app.conf.result_backend = os.getenv("CELERY_RESULT_BACKEND", "<< redis.celery_result_backend >>")
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.timezone = "UTC"


# =============================================================================
# 2. TASK DEFINITIONS
# =============================================================================

@celery_app.task(bind=True, name="generate_report")
def generate_report(self, filters: dict | None = None) -> dict[str, Any]:
    """Generate a report of tasks matching the given filters."""
    try:
        database_url = os.getenv("DATABASE_URL", "<< postgres.sync_url >>")
        engine = create_engine(database_url)

        with Session(engine) as session:
            total = session.execute(text("SELECT COUNT(*) FROM tasks")).scalar()
            status_rows = session.execute(text("SELECT status, COUNT(*) FROM tasks GROUP BY status")).fetchall()
            by_status = {row[0]: row[1] for row in status_rows}
            priority_rows = session.execute(text("SELECT priority, COUNT(*) FROM tasks GROUP BY priority")).fetchall()
            by_priority = {row[0]: row[1] for row in priority_rows}

        engine.dispose()
        return {"total_tasks": total, "by_status": by_status, "by_priority": by_priority}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5, max_retries=3)


@celery_app.task(bind=True, name="bulk_status_update")
def bulk_status_update(self, task_ids: list[int], new_status: str) -> dict[str, Any]:
    """Update the status of multiple tasks at once."""
    try:
        database_url = os.getenv("DATABASE_URL", "<< postgres.sync_url >>")
        engine = create_engine(database_url)

        with Session(engine) as session:
            result: CursorResult = session.execute(
                text("UPDATE tasks SET status = :status WHERE id = ANY(:ids)"),
                {"status": new_status, "ids": task_ids},
            )
            session.commit()
            updated_count = result.rowcount

        engine.dispose()
        return {"updated_count": updated_count}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5, max_retries=3)
