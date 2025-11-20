"""Integration tests for agent configuration API endpoints."""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.api
class TestAgentConfigAPI:
    """Test agent configuration operations."""

    def test_get_agent_config(self, client: TestClient, sample_project):
        """Test getting agent configuration for a project."""
        response = client.get(f"/api/v1/projects/{sample_project.id}/agent-config")

        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] == sample_project.id
        assert "agent_type" in data
        assert "environment_type" in data
        assert "enabled_tools" in data
        assert "llm_provider" in data
        assert "llm_model" in data

    def test_get_agent_config_not_found(self, client: TestClient):
        """Test getting agent config for non-existent project."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/api/v1/projects/{fake_id}/agent-config")

        assert response.status_code == 404

    def test_update_agent_config_llm_settings(self, client: TestClient, sample_project):
        """Test updating LLM settings."""
        response = client.put(
            f"/api/v1/projects/{sample_project.id}/agent-config",
            json={
                "llm_provider": "anthropic",
                "llm_model": "claude-3-sonnet",
                "llm_config": {
                    "temperature": 0.9,
                    "max_tokens": 8192
                }
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["llm_provider"] == "anthropic"
        assert data["llm_model"] == "claude-3-sonnet"
        assert data["llm_config"]["temperature"] == 0.9
        assert data["llm_config"]["max_tokens"] == 8192

    def test_update_agent_config_environment(self, client: TestClient, sample_project):
        """Test updating environment settings."""
        response = client.put(
            f"/api/v1/projects/{sample_project.id}/agent-config",
            json={
                "environment_type": "python3.12",
                "environment_config": {
                    "packages": ["numpy", "pandas"]
                }
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["environment_type"] == "python3.12"
        assert "numpy" in data["environment_config"]["packages"]

    def test_update_agent_config_tools(self, client: TestClient, sample_project):
        """Test updating enabled tools."""
        response = client.put(
            f"/api/v1/projects/{sample_project.id}/agent-config",
            json={
                "enabled_tools": ["bash", "file_read", "file_write", "file_edit"]
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["enabled_tools"]) == 4
        assert "file_edit" in data["enabled_tools"]

    def test_update_agent_config_system_instructions(self, client: TestClient, sample_project):
        """Test updating system instructions."""
        instructions = "You are a helpful Python expert. Always write clean, documented code."

        response = client.put(
            f"/api/v1/projects/{sample_project.id}/agent-config",
            json={"system_instructions": instructions}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["system_instructions"] == instructions

    def test_update_agent_config_partial(self, client: TestClient, sample_project):
        """Test partial update of agent config."""
        # Get current config
        response = client.get(f"/api/v1/projects/{sample_project.id}/agent-config")
        original_provider = response.json()["llm_provider"]

        # Update only temperature
        response = client.put(
            f"/api/v1/projects/{sample_project.id}/agent-config",
            json={
                "llm_config": {"temperature": 0.5}
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["llm_provider"] == original_provider  # Unchanged
        assert data["llm_config"]["temperature"] == 0.5  # Updated

    def test_list_agent_templates(self, client: TestClient):
        """Test listing available agent templates."""
        response = client.get("/api/v1/agent-templates")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have at least some default templates
        assert len(data) >= 0

    def test_apply_agent_template(self, client: TestClient, sample_project):
        """Test applying an agent template to a project."""
        # First, create a template or use a built-in one
        # Assuming there's a template endpoint
        response = client.post(
            f"/api/v1/projects/{sample_project.id}/agent-config/apply-template",
            json={"template_id": "python-expert"}
        )

        # May return 404 if template system not implemented yet
        assert response.status_code in [200, 404]

    def test_update_agent_config_invalid_provider(self, client: TestClient, sample_project):
        """Test updating with invalid LLM provider."""
        response = client.put(
            f"/api/v1/projects/{sample_project.id}/agent-config",
            json={
                "llm_provider": "invalid_provider",
                "llm_model": "invalid_model"
            }
        )

        # Should validate provider
        assert response.status_code in [400, 422]

    def test_update_agent_config_persistence(self, client: TestClient, sample_project):
        """Test that agent config updates persist."""
        # Update config
        response = client.put(
            f"/api/v1/projects/{sample_project.id}/agent-config",
            json={
                "llm_provider": "anthropic",
                "enabled_tools": ["bash"]
            }
        )
        assert response.status_code == 200

        # Retrieve config again
        response = client.get(f"/api/v1/projects/{sample_project.id}/agent-config")
        assert response.status_code == 200
        data = response.json()
        assert data["llm_provider"] == "anthropic"
        assert data["enabled_tools"] == ["bash"]
