"""Tests for YAML configuration loading."""

from claude_swarm.config import SwarmConfig


def test_config_from_dict_minimal() -> None:
    data = {"swarm": {"name": "test"}}
    config = SwarmConfig.from_dict(data)
    assert config.name == "test"
    assert config.max_concurrent == 4
    assert config.budget_usd == 5.0


def test_config_from_dict_with_agents() -> None:
    data = {
        "swarm": {"name": "review", "max_concurrent": 2, "budget_usd": 3.0},
        "agents": {
            "security": {
                "description": "Security reviewer",
                "model": "opus",
                "tools": ["Read", "Grep"],
                "prompt": "Analyze for vulnerabilities",
            },
            "tester": {
                "description": "Test writer",
                "tools": ["Read", "Write", "Bash"],
            },
        },
    }
    config = SwarmConfig.from_dict(data)
    assert config.name == "review"
    assert config.max_concurrent == 2
    assert len(config.agents) == 2
    assert config.agents["security"].model == "opus"
    assert config.agents["tester"].model == "haiku"  # default


def test_config_from_dict_with_connections() -> None:
    data = {
        "swarm": {"name": "pipeline"},
        "connections": [
            {"from": "coder", "to": "reviewer"},
            {"from": ["reviewer", "tester"], "to": "merger"},
        ],
    }
    config = SwarmConfig.from_dict(data)
    assert len(config.connections) == 2
    assert config.connections[0].from_agents == ["coder"]
    assert config.connections[1].from_agents == ["reviewer", "tester"]


def test_get_agent_prompt_with_fallback() -> None:
    config = SwarmConfig.from_dict({
        "agents": {
            "coder": {"description": "Codes", "prompt": "Write code!"},
        },
    })
    assert config.get_agent_prompt("coder") == "Write code!"
    assert config.get_agent_prompt("unknown") == ""


def test_get_agent_tools_with_fallback() -> None:
    config = SwarmConfig.from_dict({
        "agents": {
            "reader": {"description": "Reads", "tools": ["Read", "Grep"]},
        },
    })
    assert config.get_agent_tools("reader") == ["Read", "Grep"]
    assert "Write" in config.get_agent_tools("unknown")


def test_config_defaults() -> None:
    config = SwarmConfig()
    assert config.name == "default"
    assert config.model == "opus"
    assert config.max_concurrent == 4
