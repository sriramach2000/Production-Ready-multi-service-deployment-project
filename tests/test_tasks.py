# tests/test_tasks.py — Tests for Task CRUD Endpoints

import pytest
from httpx import AsyncClient

API_PREFIX = "/api/v1/tasks"


# CREATE — POST /api/v1/tasks

@pytest.mark.asyncio
async def test_create_task_success(client: AsyncClient):
    response = await client.post(f"{API_PREFIX}/", json={"title": "New Task", "description": "Details"})
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["title"] == "New Task"
    assert data["status"] == "todos"
    assert data["priority"] == "medium"
    assert "created_at" in data


@pytest.mark.asyncio
async def test_create_task_missing_title(client: AsyncClient):
    response = await client.post(f"{API_PREFIX}/", json={"description": "No title here"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_task_default_values(client: AsyncClient):
    response = await client.post(f"{API_PREFIX}/", json={"title": "Minimal Task"})
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "todos"
    assert data["priority"] == "medium"


# LIST — GET /api/v1/tasks

@pytest.mark.asyncio
async def test_list_tasks_empty(client: AsyncClient):
    response = await client.get(f"{API_PREFIX}/")
    assert response.status_code == 200
    data = response.json()
    assert data["tasks"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_tasks_returns_all(client: AsyncClient):
    for i in range(3):
        await client.post(f"{API_PREFIX}/", json={"title": f"Task {i}"})
    response = await client.get(f"{API_PREFIX}/")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["tasks"]) == 3


@pytest.mark.asyncio
async def test_list_tasks_filter_by_status(client: AsyncClient):
    await client.post(f"{API_PREFIX}/", json={"title": "Task A", "status": "done"})
    await client.post(f"{API_PREFIX}/", json={"title": "Task B", "status": "todos"})
    response = await client.get(f"{API_PREFIX}/", params={"status_filter": "done"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert all(t["status"] == "done" for t in data["tasks"])


@pytest.mark.asyncio
async def test_list_tasks_filter_by_priority(client: AsyncClient):
    await client.post(f"{API_PREFIX}/", json={"title": "Task A", "priority": "high"})
    await client.post(f"{API_PREFIX}/", json={"title": "Task B", "priority": "low"})
    response = await client.get(f"{API_PREFIX}/", params={"priority_filter": "high"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert all(t["priority"] == "high" for t in data["tasks"])


# GET — GET /api/v1/tasks/{id}

@pytest.mark.asyncio
async def test_get_task_success(client: AsyncClient, sample_task: dict):
    task_id = sample_task["id"]
    response = await client.get(f"{API_PREFIX}/{task_id}")
    assert response.status_code == 200
    assert response.json()["title"] == sample_task["title"]


@pytest.mark.asyncio
async def test_get_task_not_found(client: AsyncClient):
    response = await client.get(f"{API_PREFIX}/99999")
    assert response.status_code == 404


# UPDATE — PATCH /api/v1/tasks/{id}

@pytest.mark.asyncio
async def test_update_task_success(client: AsyncClient, sample_task: dict):
    task_id = sample_task["id"]
    response = await client.patch(f"{API_PREFIX}/{task_id}", json={"title": "Updated Title"})
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"


@pytest.mark.asyncio
async def test_update_task_partial(client: AsyncClient, sample_task: dict):
    task_id = sample_task["id"]
    response = await client.patch(f"{API_PREFIX}/{task_id}", json={"title": "New Title"})
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "New Title"
    assert data["status"] == sample_task["status"]
    assert data["priority"] == sample_task["priority"]


@pytest.mark.asyncio
async def test_update_task_not_found(client: AsyncClient):
    response = await client.patch(f"{API_PREFIX}/99999", json={"title": "Nope"})
    assert response.status_code == 404


# DELETE — DELETE /api/v1/tasks/{id}

@pytest.mark.asyncio
async def test_delete_task_success(client: AsyncClient, sample_task: dict):
    task_id = sample_task["id"]
    response = await client.delete(f"{API_PREFIX}/{task_id}")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_task_not_found(client: AsyncClient):
    response = await client.delete(f"{API_PREFIX}/99999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_task_idempotent(client: AsyncClient, sample_task: dict):
    task_id = sample_task["id"]
    response = await client.delete(f"{API_PREFIX}/{task_id}")
    assert response.status_code == 204
    response = await client.delete(f"{API_PREFIX}/{task_id}")
    assert response.status_code == 404
