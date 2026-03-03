# templates/api/app.py — FastAPI Task Management API (Single-File Application)
# Config values use orchestrate.py markers and are filled in at generate time.
# To modify application code: edit THIS file directly, then run: python3 orchestrate.py generate
# To modify config defaults: edit CONFIG in orchestrate.py, then regenerate.
#
# Docs: https://fastapi.tiangolo.com/tutorial/first-steps/
#
# This file contains the entire API application, organized in sections:
#   1. Configuration         — Settings loaded from environment / .env
#   2. Database Models       — SQLAlchemy ORM (Base, enums, Task table)
#   3. Database Session      — Async engine, session factory, get_session()
#   4. Schemas               — Pydantic request/response validation
#   5. Services              — Business logic (CRUD operations)
#   6. Cache                 — Redis caching layer (cache-aside pattern)
#   7. Metrics               — Prometheus instrumentation
#   8. Routes                — API route handlers
#   9. App                   — FastAPI instance, lifespan, middleware, health check
#
# Implementation phases are noted in each section header.
# Work through the todoss top-to-bottom — each section only depends on sections above it.


import enum
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from typing import Any, AsyncGenerator, Optional, Sequence

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
# PHASE 1 | Docs: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
# =============================================================================

class Settings(BaseSettings):
    """
    All app configuration is loaded from environment variables / .env file.
    Docs: https://fastapi.tiangolo.com/advanced/settings/
    """

    #   Use SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    #   Docs: https://docs.pydantic.dev/latest/concepts/pydantic_settings/#dotenv-env-support
    model_config = SettingsConfigDict(
        SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    )

    # --- Database ---
    POSTGRES_USER: str = "<< postgres.user >>"
    POSTGRES_PASSWORD: str = "<< postgres.password >>"
    POSTGRES_DB: str = "<< postgres.db >>"
    POSTGRES_HOST: str = "<< postgres.host >>"
    POSTGRES_PORT: int = << postgres.port >>


    #
    #   Format: "postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"
    #   For reference, the current config produces: << postgres.async_url >>
    #   Docs: https://docs.pydantic.dev/latest/concepts/validators/
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # --- Redis ---
    REDIS_URL: str = "<< redis.url >>"

    # --- Celery ---
    CELERY_BROKER_URL: str = "<< redis.celery_broker_url >>"
    CELERY_RESULT_BACKEND: str = "<< redis.celery_result_backend >>"

    # --- API ---
    API_HOST: str = "<< api.host >>"
    API_PORT: int = 0
    DEBUG: bool = False


# @lru_cache ensures settings are only loaded once
#   Docs: https://fastapi.tiangolo.com/advanced/settings/#creating-the-settings-only-once-with-lru_cache
@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


# =============================================================================
# 2. DATABASE MODELS
# PHASE 1 | Docs: https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html
# =============================================================================

# --- Base class for all models ---
# Docs: https://docs.sqlalchemy.org/en/20/orm/mapping_styles.html
class Base(DeclarativeBase):
    pass


# --- Enums for task status and priority ---
# Docs: https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.Enum
class TaskStatus(str, enum.Enum):
    todos = "todos"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Task(Base):
    """Represents a task in the task management system."""

    __tablename__ = "tasks"

    # Docs: https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html#using-mapped-column

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    title: Mapped[str] = mapped_column(
        String(255) , nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus) , default=TaskStatus.todos,
    )

    priority: Mapped[TaskPriority] = mapped_column(
        SAEnum(TaskPriority) , default=TaskPriority.MEDIUM
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )

    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=func.now() , nullable=True,
    )

    def __repr__(self) -> str:
        return f"Task(id={self.id}, title='{self.title}', status='{self.status.value}')"


# =============================================================================
# 3. DATABASE SESSION
# PHASE 2 | Docs: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
# =============================================================================


#   Docs: https://docs.sqlalchemy.org/en/20/core/engines.html
engine: AsyncEngine | None = create_async_engine(
    settings.DATABASE_URL, echo=False, pool_pre_ping=True 
)  

#   Docs: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-asyncsession-with-a-sessionmaker
async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides a database session per request.
    Usage in routes: session: AsyncSession = Depends(get_session)
    Docs: https://fastapi.tiangolo.com/tutorial/dependencies/
    """

    # Pattern:
    #   async with async_session_factory() as session:
    #       yield session
    
    async with async_session_factory() as session:
        yield session


# =============================================================================
# 4. SCHEMAS (Pydantic Request/Response Validation)
# PHASE 1 | Docs: https://docs.pydantic.dev/latest/concepts/models/
# =============================================================================

class TaskBase(BaseModel):
    title: str = Field(
        #   Docs: https://docs.pydantic.dev/latest/concepts/fields/
        min_length=1, max_length=255,
    
    )
    description: Optional[str] = Field(
        default=None
    )
    status: TaskStatus = Field(
        default=TaskStatus.todos
    )

    priority: TaskPriority = Field(
        default=TaskPriority.MEDIUM
    )


# --- Schema for creating a task (POST request body) ---
# Docs: https://fastapi.tiangolo.com/tutorial/body/
class TaskCreate(TaskBase):
    """Only title is required; status and priority have defaults."""
    pass  # todos: Override fields if needed (e.g., make status/priority optional with defaults)


# --- Schema for updating a task (PATCH request body) ---
class TaskUpdate(BaseModel):
    """All fields optional — partial update pattern."""
    title: Optional[str] = Field(
        default=None, min_length=1 , max_length=255
    )
    description: Optional[str] = Field(
        default=None
    )
    status: Optional[TaskStatus] = Field(
        default=None
    )
    priority: Optional[TaskPriority] = Field(
        default=None
    )


# --- Schema for task responses (returned from API) ---
# Docs: https://fastapi.tiangolo.com/tutorial/response-model/
class TaskResponse(TaskBase):
    """Includes database-generated fields: id, created_at, updated_at."""
    #   Docs: https://docs.pydantic.dev/latest/concepts/models/#arbitrary-class-instances
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None


# --- Schema for paginated list responses ---
class TaskListResponse(BaseModel):
    tasks: list[TaskResponse]
    total: int


# =============================================================================
# 5. SERVICES (Business Logic — CRUD Operations)
# PHASE 1 | Docs: https://docs.sqlalchemy.org/en/20/orm/session_basics.html
# =============================================================================

async def create_task(session: AsyncSession, task_data: TaskCreate) -> Task:
    """Insert a new task into the database and return it."""
    
    # Docs: https://docs.sqlalchemy.org/en/20/orm/session_basics.html#adding-new-or-existing-items
    task = Task(**task_data.model_dump())
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task

async def get_task(session: AsyncSession, task_id: int) -> Optional[Task]:
    """Fetch a single task by ID. Returns None if not found."""
    # Docs: https://docs.sqlalchemy.org/en/20/orm/queryguide/select.html
    result = await session.execute(select(Task).where(Task.id == task_id))
    return result.scalar_one_or_none()

async def list_tasks(
    session: AsyncSession,
    status_filter: Optional[TaskStatus] = None,
    priority_filter: Optional[TaskPriority] = None,
    skip: int = 0,
    limit: int = 20,
) -> Sequence[Task]:
    
    """Fetch tasks with optional filtering and pagination."""
    query= select(Task)
   
    if status_filter is not None:
        query = query.where(Task.status == status_filter)
   
    if priority_filter is not None:
        query = query.where(Task.priority == priority_filter)
  
    query = query.order_by(Task.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(query)
    return result.scalars().all()


async def count_tasks(
    session: AsyncSession,
    status_filter: Optional[TaskStatus] = None,
    priority_filter: Optional[TaskPriority] = None,
) -> int:
    
    """Count tasks matching filters (for pagination metadata)."""
    query = select(func.count()).select_from(Task)

    if status_filter is not None:
        query = query.where(Task.status == status_filter)

    if priority_filter is not None:
        query = query.where(Task.priority == priority_filter)
    
    result = await session.execute(query)
    return result.scalar_one()


async def update_task(
    session: AsyncSession,
    task_id: int,
    task_data: TaskUpdate,
) -> Optional[Task]:
    """Update a task with partial data. Returns None if not found."""
    task = await get_task(session, task_id)

    if task is None:
        return None 
    
    for field, value in task_data.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    
    await session.commit()
    await session.refresh(task)
    
    return task


async def delete_task(session: AsyncSession, task_id: int) -> bool:
    """Delete a task by ID. Returns True if deleted, False if not found."""

    task = await get_task(session,task_id)
    
    if task is None:
        return False
    
    await session.delete(task)
    await session.commit()

    return True 

# =============================================================================
# 6. CACHE (Redis Caching Layer)
# PHASE 3 | Docs: https://redis.io/docs/latest/develop/clients/redis-py/
# =============================================================================

CACHE_PREFIX = "task"
DEFAULT_TTL = 300  # 5 minutes in seconds


class CacheService:
    """Manages Redis cache for tasks using the cache-aside pattern."""

    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        """Initialize the Redis connection. Call during app startup (lifespan)."""
        # todos: Create a Redis connection using aioredis.from_url()
        #   Pass: settings.REDIS_URL, encoding="utf-8", decode_responses=True
        #   Docs: https://redis.readthedocs.io/en/stable/connections.html
        pass

    async def close(self) -> None:
        """Close the Redis connection. Call during app shutdown (lifespan)."""
        # todos: Close self.redis if it exists
        #   Use: await self.redis.close()
        pass

    def _make_key(self, task_id: int) -> str:
        """Build a cache key like 'task:123'."""
        # todos: Return f"{CACHE_PREFIX}:{task_id}"
        raise NotImplementedError("todos")

    async def get_cached_task(self, task_id: int) -> Optional[dict]:
        """
        Try to get a task from Redis cache.
        Returns the task as a dict on cache hit, None on cache miss.
        """
        # todos: Build the key with self._make_key(task_id)
        # todos: Call await self.redis.get(key)
        # todos: If result is None, return None (cache miss)
        # todos: Deserialize the JSON string: json.loads(result)
        # todos: Return the deserialized dict
        # Docs: https://redis.io/docs/latest/commands/get/
        pass

    async def set_cached_task(self, task_id: int, task_data: dict, ttl: int = DEFAULT_TTL) -> None:
        """Store a task in Redis cache with a TTL (time-to-live)."""
        # todos: Build the key with self._make_key(task_id)
        # todos: Serialize task_data to JSON: json.dumps(task_data)
        # todos: Call await self.redis.setex(key, ttl, json_string)
        # Docs: https://redis.io/docs/latest/commands/setex/
        pass

    async def invalidate_task_cache(self, task_id: int) -> None:
        """Remove a task from Redis cache. Call after update or delete."""
        # todos: Build the key with self._make_key(task_id)
        # todos: Call await self.redis.delete(key)
        # Docs: https://redis.io/docs/latest/commands/del/
        pass


cache_service = CacheService()


# =============================================================================
# 7. METRICS (Prometheus Instrumentation)
# PHASE 7 | Docs: https://prometheus.github.io/client_python/
# =============================================================================

# todos: Create a Counter for total HTTP requests
#   Name: "http_requests_total"
#   Description: "Total number of HTTP requests"
#   Labels: ["method", "endpoint", "status_code"]
#   Docs: https://prometheus.github.io/client_python/instrumenting/counter/
REQUEST_COUNT: Counter | None = None  # todos: Counter(...)

# todos: Create a Histogram for request duration
#   Name: "http_request_duration_seconds"
#   Description: "HTTP request duration in seconds"
#   Labels: ["method", "endpoint"]
#   Docs: https://prometheus.github.io/client_python/instrumenting/histogram/
REQUEST_DURATION: Histogram | None = None  # todos: Histogram(...)


def setup_metrics(fastapi_app: FastAPI) -> None:
    """
    Attach Prometheus middleware and mount /metrics endpoint.
    Called in the App section below after creating the app.
    """

    @fastapi_app.middleware("http")
    async def prometheus_middleware(request: Request, call_next) -> Response:
        """Record request count and duration for every HTTP request."""
        # todos: Record the start time using time.time()
        # todos: Call response = await call_next(request)
        # todos: Calculate duration = time.time() - start_time
        # todos: Increment REQUEST_COUNT with labels (method, path, status_code)
        # todos: Observe duration in REQUEST_DURATION with labels (method, path)
        # todos: Return the response
        # Docs: https://fastapi.tiangolo.com/tutorial/middleware/
        raise NotImplementedError("todos")

    # todos: Mount the Prometheus metrics ASGI app at /metrics
    #   Use: metrics_app = make_asgi_app()
    #   Then: fastapi_app.mount("/metrics", metrics_app)
    #   Docs: https://prometheus.github.io/client_python/exporting/http/
    pass


# =============================================================================
# 8. ROUTES (API Route Handlers)
# PHASE 1 | Docs: https://fastapi.tiangolo.com/tutorial/bigger-applications/
# =============================================================================

router = APIRouter()


# ---- CREATE ----
# Docs: https://fastapi.tiangolo.com/tutorial/body/
@router.post("/", status_code=status.HTTP_201_CREATED, response_model=TaskResponse)

async def create_task_endpoint(
    
    task_data: TaskCreate,
    session: AsyncSession = Depends(get_session),

):
    """Create a new task."""
    # todos: Call create_task() with session and task_data
    # todos: Return the created task

    raise NotImplementedError("todos")


# ---- LIST ----
# Docs: https://fastapi.tiangolo.com/tutorial/query-params/
@router.get("/", response_model=TaskListResponse)
async def list_tasks_endpoint(
    status_filter: Optional[TaskStatus] = None,
    priority_filter: Optional[TaskPriority] = None,
    skip: int = 0,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
):
    """List tasks with optional filtering and pagination."""
    # todos: Call list_tasks() with filters and pagination params
    # todos: Call count_tasks() to get the total count
    # todos: Return TaskListResponse with tasks list and total count
    raise NotImplementedError("todos")


# ---- GET SINGLE ----
# Docs: https://fastapi.tiangolo.com/tutorial/path-params/
@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_endpoint(
    task_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get a single task by ID. Uses Redis cache (cache-aside pattern)."""
    # todos: Check Redis cache first via cache_service.get_cached_task(task_id)
    # todos: On cache hit — return the cached data
    # todos: On cache miss — query DB via get_task()
    # todos: If not found in DB — raise HTTPException(status_code=404)
    # todos: Store result in cache via cache_service.set_cached_task()
    # todos: Return the task
    raise NotImplementedError("todos")


# ---- UPDATE ----
# Docs: https://fastapi.tiangolo.com/tutorial/body-updates/
@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task_endpoint(
    task_id: int,
    task_data: TaskUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Partially update a task."""
    # todos: Call update_task() with session, task_id, task_data
    # todos: If task not found — raise HTTPException(status_code=404)
    # todos: Invalidate Redis cache via cache_service.invalidate_task_cache(task_id)
    # todos: Return the updated task
    raise NotImplementedError("todos")


# ---- DELETE ----
@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_endpoint(
    task_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Delete a task by ID."""
    # todos: Call delete_task() with session and task_id
    # todos: If task not found — raise HTTPException(status_code=404)
    # todos: Invalidate Redis cache via cache_service.invalidate_task_cache(task_id)
    # todos: Return None (204 No Content has no body)
    raise NotImplementedError("todos")


# ---- TRIGGER ASYNC REPORT ----
# Docs: https://docs.celeryq.dev/en/stable/userguide/calling.html
@router.post("/report", status_code=status.HTTP_202_ACCEPTED)
async def generate_report_endpoint():
    """Trigger an async report generation via Celery. Returns 202 Accepted."""
    # todos: Import the Celery task from the worker (worker/app.py)
    # todos: Call task.delay() or task.apply_async() to dispatch it
    # todos: Return {"task_id": result.id, "status": "accepted"}
    raise NotImplementedError("todos")


# =============================================================================
# 9. APP (FastAPI Instance, Lifespan, Middleware)
# PHASE 1 | Docs: https://fastapi.tiangolo.com/tutorial/first-steps/
# =============================================================================

# Docs: https://fastapi.tiangolo.com/advanced/events/
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    # todos: Initialize the database engine and create tables if needed
    # todos: Initialize the Redis connection pool via cache_service.connect()
    # todos: Log that the application has started

    yield

    # --- Shutdown ---
    # todos: Dispose of the database engine (close connection pool)
    # todos: Close the Redis connection via cache_service.close()
    # todos: Log that the application is shutting down


# todos: Create the FastAPI app instance
#   Pass: title, version, description, and the lifespan function above
#   Docs: https://fastapi.tiangolo.com/tutorial/first-steps/
app = FastAPI(
    # todos: fill in app metadata and lifespan
)


# todos: Add CORS middleware to allow cross-origin requests
#   Docs: https://fastapi.tiangolo.com/tutorial/cors/
# app.add_middleware(CORSMiddleware, ...)


# todos: Include the tasks router with prefix "/api/v1/tasks" and tags=["tasks"]
#   Docs: https://fastapi.tiangolo.com/tutorial/bigger-applications/
# app.include_router(router, prefix="/api/v1/tasks", tags=["tasks"])


# todos: Set up Prometheus metrics
#   setup_metrics(app)


@app.get("/")
async def health_check():
    """Health check endpoint — used by Docker HEALTHCHECK and load balancers."""
    # todos: Return a dict with status "ok" and any other useful info
    raise NotImplementedError("todos")
