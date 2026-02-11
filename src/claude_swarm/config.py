"""YAML configuration for defining swarm topologies.

Allows users to define custom agent types, tool restrictions,
and reusable swarm patterns in a declarative config file.

Example swarm.yaml:
    swarm:
      name: full-stack-review
      max_concurrent: 4
      budget_usd: 5.0

    agents:
      security-reviewer:
        description: Reviews code for OWASP vulnerabilities
        model: opus
        tools: [Read, Grep, Glob]
        prompt: |
          You are a security expert. Analyze code for...

      tester:
        description: Writes and runs tests
        model: haiku
        tools: [Read, Write, Edit, Bash]
        prompt: |
          Write comprehensive tests for all modified code...

    connections:
      - from: coder
        to: security-reviewer
      - from: coder
        to: tester
      - from: [security-reviewer, tester]
        to: reviewer
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


@dataclass
class AgentConfig:
    """Configuration for a custom agent type."""

    name: str
    description: str
    model: str = "haiku"
    tools: list[str] = field(default_factory=lambda: ["Read", "Write", "Edit", "Bash", "Grep", "Glob"])
    prompt: str = ""


@dataclass
class ConnectionConfig:
    """Defines dependency between agent types."""

    from_agents: list[str]
    to_agent: str


@dataclass
class SwarmConfig:
    """Full swarm configuration loaded from YAML."""

    name: str = "default"
    max_concurrent: int = 4
    budget_usd: float = 5.0
    model: str = "opus"  # model for task decomposition
    agents: dict[str, AgentConfig] = field(default_factory=dict)
    connections: list[ConnectionConfig] = field(default_factory=list)

    @classmethod
    def from_file(cls, path: str | Path) -> SwarmConfig:
        """Load config from a YAML file."""
        if not HAS_YAML:
            raise ImportError(
                "PyYAML is required for YAML config. Install with: pip install pyyaml"
            )

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SwarmConfig:
        """Load config from a dictionary."""
        swarm_data = data.get("swarm", {})
        config = cls(
            name=swarm_data.get("name", "default"),
            max_concurrent=swarm_data.get("max_concurrent", 4),
            budget_usd=swarm_data.get("budget_usd", 5.0),
            model=swarm_data.get("model", "opus"),
        )

        # Parse agents
        for name, agent_data in data.get("agents", {}).items():
            config.agents[name] = AgentConfig(
                name=name,
                description=agent_data.get("description", f"Agent: {name}"),
                model=agent_data.get("model", "haiku"),
                tools=agent_data.get("tools", ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]),
                prompt=agent_data.get("prompt", ""),
            )

        # Parse connections
        for conn_data in data.get("connections", []):
            from_val = conn_data.get("from", [])
            if isinstance(from_val, str):
                from_val = [from_val]
            config.connections.append(
                ConnectionConfig(
                    from_agents=from_val,
                    to_agent=conn_data.get("to", ""),
                )
            )

        return config

    def get_agent_prompt(self, agent_type: str) -> str:
        """Get the prompt for an agent type, with fallback."""
        if agent_type in self.agents:
            return self.agents[agent_type].prompt
        return ""

    def get_agent_tools(self, agent_type: str) -> list[str]:
        """Get tools for an agent type, with fallback."""
        if agent_type in self.agents:
            return self.agents[agent_type].tools
        return ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]

    def get_agent_model(self, agent_type: str) -> str:
        """Get model for an agent type, with fallback."""
        if agent_type in self.agents:
            return self.agents[agent_type].model
        return "haiku"


def find_config(cwd: str) -> SwarmConfig | None:
    """Search for swarm.yaml in the project directory."""
    search_paths = [
        Path(cwd) / "swarm.yaml",
        Path(cwd) / "swarm.yml",
        Path(cwd) / ".claude" / "swarm.yaml",
        Path(cwd) / ".claude" / "swarm.yml",
    ]

    for path in search_paths:
        if path.exists():
            return SwarmConfig.from_file(path)

    return None
