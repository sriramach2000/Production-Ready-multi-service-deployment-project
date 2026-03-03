# templates/tests/test_tasks.py — Tests for Task CRUD Endpoints
# To modify: edit THIS file directly, then run: python3 orchestrate.py generate
#
# PHASE 9 | Docs: https://fastapi.tiangolo.com/tutorial/testing/

import pytest
from httpx import AsyncClient

API_PREFIX = "/api/v1/tasks"


# =============================================================================
# CREATE — POST /api/v1/tasks
# =============================================================================

@pytest.mark.asyncio
async def test_create_task_success(client: AsyncClient):
    """Valid payload -> 201, returns task with ID."""
    # todos: POST to API_PREFIX with {"title": "New Task", "description": "Details"}
    # todos: Assert response.status_code == 201
    # todos: Assert response JSON has "id", "title", "status", "created_at"
    # todos: Assert default status is "todos" and priority is "medium"
    pass


@pytest.mark.asyncio
async def test_create_task_missing_title(client: AsyncClient):
    """No title -> 422 validation error."""
    # todos: POST to API_PREFIX with {"description": "No title here"}
    # todos: Assert response.status_code == 422
    pass


@pytest.mark.asyncio
async def test_create_task_default_values(client: AsyncClient):
    """Only title provided -> status defaults to 'todos', priority to 'medium'."""
    # todos: POST with only {"title": "Minimal Task"}
    # todos: Assert status == "todos" and priority == "medium"
    pass


# =============================================================================
# LIST — GET /api/v1/tasks
# =============================================================================

@pytest.mark.asyncio
async def test_list_tasks_empty(client: AsyncClient):
    """No tasks exist -> 200, empty list."""
    # todos: GET API_PREFIX
    # todos: Assert status 200, tasks list is empty, total is 0
    pass


@pytest.mark.asyncio
async def test_list_tasks_returns_all(client: AsyncClient):
    """Create 3 tasks, then list -> returns all 3."""
    # todos: POST 3 tasks
    # todos: GET API_PREFIX
    # todos: Assert total == 3 and len(tasks) == 3
    pass


@pytest.mark.asyncio
async def test_list_tasks_filter_by_status(client: AsyncClient):
    """Filter by status=done -> only done tasks returned."""
    # todos: Create tasks with different statuses
    # todos: GET API_PREFIX?status_filter=done
    # todos: Assert only done tasks are returned
    pass


@pytest.mark.asyncio
async def test_list_tasks_filter_by_priority(client: AsyncClient):
    """Filter by priority=high -> only high-priority tasks returned."""
    # todos: Create tasks with different priorities
    # todos: GET API_PREFIX?priority_filter=high
    # todos: Assert only high-priority tasks are returned
    pass


# =============================================================================
# GET — GET /api/v1/tasks/{id}
# =============================================================================

@pytest.mark.asyncio
async def test_get_task_success(client: AsyncClient, sample_task: dict):
    """Valid ID -> 200, correct data."""
    # todos: GET API_PREFIX/{sample_task["id"]}
    # todos: Assert status 200
    # todos: Assert response matches sample_task data
    pass


@pytest.mark.asyncio
async def test_get_task_not_found(client: AsyncClient):
    """Invalid ID -> 404."""
    # todos: GET API_PREFIX/99999
    # todos: Assert status 404
    pass


# =============================================================================
# UPDATE — PATCH /api/v1/tasks/{id}
# =============================================================================

@pytest.mark.asyncio
async def test_update_task_success(client: AsyncClient, sample_task: dict):
    """Valid update -> 200, fields changed."""
    # todos: PATCH API_PREFIX/{sample_task["id"]} with {"title": "Updated Title"}
    # todos: Assert status 200
    # todos: Assert title is "Updated Title"
    pass


@pytest.mark.asyncio
async def test_update_task_partial(client: AsyncClient, sample_task: dict):
    """Update only title -> other fields unchanged."""
    # todos: PATCH with only {"title": "New Title"}
    # todos: Assert title changed but status and priority stayed the same
    pass


@pytest.mark.asyncio
async def test_update_task_not_found(client: AsyncClient):
    """Invalid ID -> 404."""
    # todos: PATCH API_PREFIX/99999 with {"title": "Nope"}
    # todos: Assert status 404
    pass


# =============================================================================
# DELETE — DELETE /api/v1/tasks/{id}
# =============================================================================

@pytest.mark.asyncio
async def test_delete_task_success(client: AsyncClient, sample_task: dict):
    """Valid ID -> 204 No Content."""
    # todos: DELETE API_PREFIX/{sample_task["id"]}
    # todos: Assert status 204
    pass


@pytest.mark.asyncio
async def test_delete_task_not_found(client: AsyncClient):
    """Invalid ID -> 404."""
    # todos: DELETE API_PREFIX/99999
    # todos: Assert status 404
    pass


@pytest.mark.asyncio
async def test_delete_task_idempotent(client: AsyncClient, sample_task: dict):
    """Delete same ID twice -> second returns 404."""
    # todos: DELETE API_PREFIX/{sample_task["id"]} — assert 204
    # todos: DELETE API_PREFIX/{sample_task["id"]} again — assert 404
    pass
