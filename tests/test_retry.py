"""Tests for retry logic in the orchestrator."""

from claude_swarm.orchestrator import SwarmOrchestrator
from claude_swarm.types import (
    SwarmPlan,
    SwarmTask,
)


def _make_plan(tasks: list[SwarmTask]) -> SwarmPlan:
    return SwarmPlan(original_prompt="test", tasks=tasks)


def test_retry_count_tracking() -> None:
    tasks = [SwarmTask(id="a", description="A", agent_type="coder")]
    orch = SwarmOrchestrator(plan=_make_plan(tasks), cwd="/tmp", max_retries=3)
    assert orch.max_retries == 3
    assert len(orch._retry_counts) == 0


def test_retry_count_default() -> None:
    tasks = [SwarmTask(id="a", description="A", agent_type="coder")]
    orch = SwarmOrchestrator(plan=_make_plan(tasks), cwd="/tmp")
    assert orch.max_retries == 1  # default: 1 attempt (no retries)
