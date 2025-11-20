"""Integration tests for project API endpoints."""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.api
class TestProjectAPI:
    """Test project CRUD operations."""

    def test_create_project(self, client: TestClient):
        """Test creating a new project."""
        response = client.post(
            "/api/v1/projects",
            json={
                "name": "New Project",
                "description": "A brand new project"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Project"
        assert data["description"] == "A brand new project"
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_project_without_description(self, client: TestClient):
        """Test creating a project without description."""
        response = client.post(
            "/api/v1/projects",
            json={"name": "Minimal Project"}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal Project"
        assert data["description"] is None

    def test_create_project_invalid_data(self, client: TestClient):
        """Test creating a project with invalid data."""
        response = client.post(
            "/api/v1/projects",
            json={}  # Missing required 'name' field
        )

        assert response.status_code == 422  # Validation error

    def test_list_projects(self, client: TestClient, sample_project):
        """Test listing all projects."""
        response = client.get("/api/v1/projects")

        assert response.status_code == 200
        data = response.json()
        assert "projects" in data
        assert len(data["projects"]) >= 1
        assert any(p["id"] == sample_project.id for p in data["projects"])

    def test_list_projects_empty(self, client: TestClient):
        """Test listing projects when none exist."""
        response = client.get("/api/v1/projects")

        assert response.status_code == 200
        data = response.json()
        assert "projects" in data
        assert isinstance(data["projects"], list)

    def test_get_project(self, client: TestClient, sample_project):
        """Test getting a specific project."""
        response = client.get(f"/api/v1/projects/{sample_project.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_project.id
        assert data["name"] == sample_project.name
        assert data["description"] == sample_project.description

    def test_get_project_not_found(self, client: TestClient):
        """Test getting a non-existent project."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/api/v1/projects/{fake_id}")

        assert response.status_code == 404

    def test_update_project(self, client: TestClient, sample_project):
        """Test updating a project."""
        response = client.put(
            f"/api/v1/projects/{sample_project.id}",
            json={
                "name": "Updated Project Name",
                "description": "Updated description"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Project Name"
        assert data["description"] == "Updated description"

    def test_update_project_partial(self, client: TestClient, sample_project):
        """Test partial update of a project."""
        original_name = sample_project.name

        response = client.put(
            f"/api/v1/projects/{sample_project.id}",
            json={"description": "Only description updated"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == original_name  # Name unchanged
        assert data["description"] == "Only description updated"

    def test_delete_project(self, client: TestClient, sample_project):
        """Test deleting a project."""
        project_id = sample_project.id

        response = client.delete(f"/api/v1/projects/{project_id}")
        assert response.status_code == 204

        # Verify project is deleted
        response = client.get(f"/api/v1/projects/{project_id}")
        assert response.status_code == 404

    def test_delete_project_not_found(self, client: TestClient):
        """Test deleting a non-existent project."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = client.delete(f"/api/v1/projects/{fake_id}")

        assert response.status_code == 404

    def test_delete_project_cascades_to_sessions(self, client: TestClient, sample_project, sample_chat_session):
        """Test that deleting a project also deletes its chat sessions."""
        project_id = sample_project.id
        session_id = sample_chat_session.id

        # Delete project
        response = client.delete(f"/api/v1/projects/{project_id}")
        assert response.status_code == 204

        # Verify session is also deleted
        response = client.get(f"/api/v1/chat-sessions/{session_id}")
        assert response.status_code == 404
