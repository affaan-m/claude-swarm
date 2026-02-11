"""Core type definitions for Claude Swarm."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TaskStatus(StrEnum):
    """Status of a swarm task."""

    PENDING = "pending"
    BLOCKED = "blocked"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentStatus(StrEnum):
    """Status of a swarm agent."""

    IDLE = "idle"
    WORKING = "working"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SwarmTask:
    """A single task in the swarm's dependency graph."""

    id: str
    description: str
    agent_type: str  # e.g., "coder", "reviewer", "tester"
    status: TaskStatus = TaskStatus.PENDING
    dependencies: list[str] = field(default_factory=list)  # task IDs this depends on
    assigned_agent: str | None = None
    files_to_modify: list[str] = field(default_factory=list)
    result: str | None = None
    error: str | None = None
    cost_usd: float = 0.0
    duration_ms: int = 0
    tools: list[str] = field(default_factory=list)
    prompt: str = ""

    @property
    def is_ready(self) -> bool:
        """Check if all dependencies are completed."""
        return self.status == TaskStatus.PENDING and len(self.dependencies) == 0

    def to_agent_definition_dict(self) -> dict[str, Any]:
        """Convert to a dict suitable for AgentDefinition kwargs."""
        return {
            "description": self.description,
            "prompt": self.prompt,
            "tools": self.tools or None,
            "model": "haiku",
        }


@dataclass
class SwarmAgent:
    """A running agent in the swarm."""

    id: str
    name: str
    task_id: str
    status: AgentStatus = AgentStatus.IDLE
    cost_usd: float = 0.0
    turns: int = 0
    files_modified: list[str] = field(default_factory=list)
    current_tool: str | None = None


@dataclass
class FileConflict:
    """Detected when multiple agents try to modify the same file."""

    file_path: str
    agent_ids: list[str]
    task_ids: list[str]
    resolved: bool = False


@dataclass
class SwarmPlan:
    """The decomposed plan for a complex task."""

    original_prompt: str
    tasks: list[SwarmTask]
    estimated_total_cost: float = 0.0
    model_used: str = "opus"

    @property
    def task_count(self) -> int:
        return len(self.tasks)

    @property
    def parallel_groups(self) -> list[list[str]]:
        """Group tasks by dependency level for parallel execution."""
        # Tasks with no dependencies can run first
        remaining = {t.id: set(t.dependencies) for t in self.tasks}
        groups: list[list[str]] = []

        while remaining:
            # Find all tasks whose dependencies are satisfied
            ready = [tid for tid, deps in remaining.items() if len(deps) == 0]
            if not ready:
                # Circular dependency — shouldn't happen with good decomposition
                ready = list(remaining.keys())[:1]
            groups.append(ready)
            for tid in ready:
                del remaining[tid]
            # Remove completed tasks from dependency lists
            for deps in remaining.values():
                deps -= set(ready)

        return groups


@dataclass
class SwarmResult:
    """Final result of a swarm execution."""

    plan: SwarmPlan
    completed_tasks: list[SwarmTask]
    failed_tasks: list[SwarmTask]
    conflicts: list[FileConflict]
    total_cost_usd: float
    total_duration_ms: int
    agents_used: int
