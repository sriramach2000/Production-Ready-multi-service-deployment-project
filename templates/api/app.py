# templates/api/app.py — FastAPI Task Management API
# Config values use << marker >> syntax, filled in by orchestrate.py at generate time.
# Edit THIS file, then run: python orchestrate.py generate
#
# Sections: 1.Configuration  2.Models  3.Session  4.Schemas  5.Services
#           6.Cache  7.Metrics  8.Routes  9.App
#
# References:
#   FastAPI:      https://fastapi.tiangolo.com/
#   SQLAlchemy:   https://docs.sqlalchemy.org/en/20/
#   Pydantic:     https://docs.pydantic.dev/latest/
#   Redis-py:     https://redis.io/docs/latest/develop/clients/redis-py/
#   Celery:       https://docs.celeryq.dev/en/stable/
#   Prometheus:   https://prometheus.github.io/client_python/


import enum
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from typing import Any, AsyncGenerator, Optional

import redis.asyncio as aioredis
from celery import Celery
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, make_asgi_app
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import String, Text, DateTime, Enum as SAEnum, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# =============================================================================
# 1. CONFIGURATION
# =============================================================================

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    POSTGRES_USER: str = "<< postgres.user >>"
    POSTGRES_PASSWORD: str = "<< postgres.password >>"
    POSTGRES_DB: str = "<< postgres.db >>"
    POSTGRES_HOST: str = "<< postgres.host >>"
    POSTGRES_PORT: int = << postgres.port >>

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    REDIS_URL: str = "<< redis.url >>"
    CELERY_BROKER_URL: str = "<< redis.celery_broker_url >>"
    CELERY_RESULT_BACKEND: str = "<< redis.celery_result_backend >>"

    API_HOST: str = "<< api.host >>"
    API_PORT: int = << api.port >>
    DEBUG: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


# =============================================================================
# 2. DATABASE MODELS
# =============================================================================

class Base(DeclarativeBase):
    pass


class TaskStatus(str, enum.Enum):
    todos = "todos"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), default=TaskStatus.todos)
    priority: Mapped[TaskPriority] = mapped_column(SAEnum(TaskPriority), default=TaskPriority.MEDIUM)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now(), nullable=True)

    def __repr__(self) -> str:
        return f"Task(id={self.id}, title='{self.title}', status='{self.status.value}')"


# =============================================================================
# 3. DATABASE SESSION
# =============================================================================

engine: AsyncEngine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


# =============================================================================
# 4. SCHEMAS
# =============================================================================

class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None)
    status: TaskStatus = Field(default=TaskStatus.todos)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None)
    status: Optional[TaskStatus] = Field(default=None)
    priority: Optional[TaskPriority] = Field(default=None)


class TaskResponse(TaskBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None


class TaskListResponse(BaseModel):
    tasks: list[TaskResponse]
    total: int


# =============================================================================
# 5. SERVICES (CRUD)
# =============================================================================

async def create_task(session: AsyncSession, task_data: TaskCreate) -> Task:
    task = Task(**task_data.model_dump())
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def get_task(session: AsyncSession, task_id: int) -> Optional[Task]:
    result = await session.execute(select(Task).where(Task.id == task_id))
    return result.scalar_one_or_none()


async def list_tasks(
    session: AsyncSession,
    status_filter: Optional[TaskStatus] = None,
    priority_filter: Optional[TaskPriority] = None,
    skip: int = 0,
    limit: int = 20,
) -> list[Task]:
    query = select(Task)
    if status_filter is not None:
        query = query.where(Task.status == status_filter)
    if priority_filter is not None:
        query = query.where(Task.priority == priority_filter)
    query = query.order_by(Task.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def count_tasks(
    session: AsyncSession,
    status_filter: Optional[TaskStatus] = None,
    priority_filter: Optional[TaskPriority] = None,
) -> int:
    query = select(func.count()).select_from(Task)
    if status_filter is not None:
        query = query.where(Task.status == status_filter)
    if priority_filter is not None:
        query = query.where(Task.priority == priority_filter)
    result = await session.execute(query)
    return result.scalar_one()


async def update_task(session: AsyncSession, task_id: int, task_data: TaskUpdate) -> Optional[Task]:
    task = await get_task(session, task_id)
    if task is None:
        return None
    for field, value in task_data.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    await session.commit()
    await session.refresh(task)
    return task


async def delete_task(session: AsyncSession, task_id: int) -> bool:
    task = await get_task(session, task_id)
    if task is None:
        return False
    await session.delete(task)
    await session.commit()
    return True


# =============================================================================
# 6. CACHE (Redis — cache-aside pattern)
# =============================================================================

CACHE_PREFIX = "task"
DEFAULT_TTL = 300


class CacheService:
    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        self.redis = await aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)

    async def close(self) -> None:
        if self.redis:
            await self.redis.close()

    def _make_key(self, task_id: int) -> str:
        return f"{CACHE_PREFIX}:{task_id}"

    async def get_cached_task(self, task_id: int) -> Optional[dict]:
        if not self.redis:
            return None
        result = await self.redis.get(self._make_key(task_id))
        if result is None:
            return None
        return json.loads(result)

    async def set_cached_task(self, task_id: int, task_data: dict, ttl: int = DEFAULT_TTL) -> None:
        if not self.redis:
            return
        await self.redis.setex(self._make_key(task_id), ttl, json.dumps(task_data, default=str))

    async def invalidate_task_cache(self, task_id: int) -> None:
        if not self.redis:
            return
        await self.redis.delete(self._make_key(task_id))


cache_service = CacheService()


# =============================================================================
# 7. METRICS (Prometheus)
# =============================================================================

REQUEST_COUNT = Counter(
    "http_requests_total", "Total number of HTTP requests",
    ["method", "endpoint", "status_code"],
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds", "HTTP request duration in seconds",
    ["method", "endpoint"],
)


def setup_metrics(fastapi_app: FastAPI) -> None:
    @fastapi_app.middleware("http")
    async def prometheus_middleware(request: Request, call_next) -> Response:
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time
        REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path, status_code=response.status_code).inc()
        REQUEST_DURATION.labels(method=request.method, endpoint=request.url.path).observe(duration)
        return response

    metrics_app = make_asgi_app()
    fastapi_app.mount("/metrics", metrics_app)


# =============================================================================
# 8. ROUTES
# =============================================================================

router = APIRouter()


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=TaskResponse)
async def create_task_endpoint(task_data: TaskCreate, session: AsyncSession = Depends(get_session)):
    return await create_task(session, task_data)


@router.get("/", response_model=TaskListResponse)
async def list_tasks_endpoint(
    status_filter: Optional[TaskStatus] = None,
    priority_filter: Optional[TaskPriority] = None,
    skip: int = 0,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
):
    tasks = await list_tasks(session, status_filter, priority_filter, skip, limit)
    total = await count_tasks(session, status_filter, priority_filter)
    return TaskListResponse(tasks=[TaskResponse.model_validate(t) for t in tasks], total=total)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_endpoint(task_id: int, session: AsyncSession = Depends(get_session)):
    cached = await cache_service.get_cached_task(task_id)
    if cached is not None:
        return cached
    task = await get_task(session, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task_response = TaskResponse.model_validate(task)
    await cache_service.set_cached_task(task_id, task_response.model_dump(mode="json"))
    return task


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task_endpoint(task_id: int, task_data: TaskUpdate, session: AsyncSession = Depends(get_session)):
    task = await update_task(session, task_id, task_data)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    await cache_service.invalidate_task_cache(task_id)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_endpoint(task_id: int, session: AsyncSession = Depends(get_session)):
    deleted = await delete_task(session, task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    await cache_service.invalidate_task_cache(task_id)
    return None


@router.post("/report", status_code=status.HTTP_202_ACCEPTED)
async def generate_report_endpoint():
    celery_app = Celery("worker", broker=settings.CELERY_BROKER_URL)
    result = celery_app.send_task("generate_report")
    return {"task_id": result.id, "status": "accepted"}


# =============================================================================
# 9. APP
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await cache_service.connect()
    print("Application starting")
    yield
    await engine.dispose()
    await cache_service.close()
    print("Application shut down")


app = FastAPI(title="Task Management API", version="1.0.0", description="Task management service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1/tasks", tags=["tasks"])

setup_metrics(app)


@app.get("/")
async def health_check():
    return {"status": "ok"}
