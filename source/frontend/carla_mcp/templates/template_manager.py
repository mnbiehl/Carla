"""
Template manager for saving and loading MCP configurations.

Templates are stored as JSON files in ~/.config/carla-mcp/templates/
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from ..state import StateManager, Chain


@dataclass
class Template:
    """A saved MCP configuration."""

    name: str
    created: str
    aliases: Dict[str, str]
    chains: Dict[str, Dict[str, Any]]
    connections: List[List[str]]


class TemplateManager:
    """Manages template save/load operations."""

    def __init__(self, template_dir: Optional[Path] = None):
        if template_dir is None:
            template_dir = Path.home() / ".config" / "carla-mcp" / "templates"

        self.template_dir = Path(template_dir)
        self.template_dir.mkdir(parents=True, exist_ok=True)

    def save(self, name: str, state: StateManager) -> Path:
        """Save current state as a template."""
        chains_data = {}
        for chain_name, chain in state.chains.items():
            chains_data[chain_name] = {
                "name": chain.name,
                "components": chain.components,
                "instance": chain.instance,
            }

        template = Template(
            name=name,
            created=datetime.now().isoformat(),
            aliases=dict(state.aliases),
            chains=chains_data,
            connections=[[src, dst] for src, dst in state.connections],
        )

        filepath = self.template_dir / f"{name}.json"
        with open(filepath, "w") as f:
            json.dump(asdict(template), f, indent=2)

        return filepath

    def load(self, name: str) -> Template:
        """Load a template by name."""
        filepath = self.template_dir / f"{name}.json"
        if not filepath.exists():
            raise FileNotFoundError(f"Template '{name}' not found at {filepath}")

        with open(filepath) as f:
            data = json.load(f)

        return Template(**data)

    def apply(self, name: str, state: StateManager, merge: bool = False) -> None:
        """Apply a template to state."""
        template = self.load(name)

        if not merge:
            state.aliases.clear()
            state.chains.clear()
            state.connections.clear()

        state.aliases.update(template.aliases)

        for chain_name, chain_data in template.chains.items():
            state.chains[chain_name] = Chain(
                name=chain_data["name"],
                components=chain_data["components"],
                instance=chain_data["instance"],
            )

        for src, dst in template.connections:
            state.connections.add((src, dst))

    def list_templates(self) -> List[str]:
        """List all saved templates."""
        templates = []
        for filepath in self.template_dir.glob("*.json"):
            templates.append(filepath.stem)
        return sorted(templates)

    def delete(self, name: str) -> bool:
        """Delete a template."""
        filepath = self.template_dir / f"{name}.json"
        if filepath.exists():
            filepath.unlink()
            return True
        return False
