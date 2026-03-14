"""Tests for template manager."""

import pytest
from pathlib import Path
from carla_mcp.templates.template_manager import TemplateManager, Template
from carla_mcp.state import StateManager, Chain


@pytest.fixture
def temp_template_dir(tmp_path):
    """Temporary directory for templates."""
    return tmp_path / "templates"


@pytest.fixture
def template_manager(temp_template_dir):
    return TemplateManager(template_dir=temp_template_dir)


@pytest.fixture
def state_with_data():
    """State manager with some data."""
    sm = StateManager()
    sm.create_alias("Guitar", "looper:out_1")
    sm.add_connection("looper:out_1_L", "reverb:in_L")
    sm.chains["Test Chain"] = Chain(
        name="Test Chain",
        components=["looper:out_1", "reverb", "system:playback"],
        instance="main"
    )
    return sm


class TestTemplateSave:
    """Test template saving."""

    def test_save_creates_file(self, template_manager, state_with_data, temp_template_dir):
        """Saving template creates JSON file."""
        template_manager.save("my-template", state_with_data)

        assert (temp_template_dir / "my-template.json").exists()

    def test_save_includes_aliases(self, template_manager, state_with_data):
        """Saved template includes aliases."""
        template_manager.save("test", state_with_data)
        template = template_manager.load("test")

        assert template.aliases == {"Guitar": "looper:out_1"}

    def test_save_includes_chains(self, template_manager, state_with_data):
        """Saved template includes chains."""
        template_manager.save("test", state_with_data)
        template = template_manager.load("test")

        assert "Test Chain" in template.chains


class TestTemplateLoad:
    """Test template loading."""

    def test_load_restores_aliases(self, template_manager, state_with_data):
        """Loading template restores aliases to state."""
        template_manager.save("test", state_with_data)

        new_state = StateManager()
        template_manager.apply("test", new_state)

        assert new_state.aliases == {"Guitar": "looper:out_1"}

    def test_load_nonexistent_raises(self, template_manager):
        """Loading nonexistent template raises error."""
        with pytest.raises(FileNotFoundError):
            template_manager.load("nonexistent")


class TestTemplateList:
    """Test template listing."""

    def test_list_templates(self, template_manager, state_with_data):
        """Lists all saved templates."""
        template_manager.save("template-a", state_with_data)
        template_manager.save("template-b", state_with_data)

        templates = template_manager.list_templates()

        assert "template-a" in templates
        assert "template-b" in templates
