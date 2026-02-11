"""Tests for the SwarmOrchestrator (non-SDK-dependent logic)."""

from claude_swarm.orchestrator import SwarmOrchestrator
from claude_swarm.types import (
    AgentStatus,
    SwarmAgent,
    SwarmPlan,
    SwarmTask,
    TaskStatus,
)


def _make_plan(tasks: list[SwarmTask]) -> SwarmPlan:
    return SwarmPlan(original_prompt="test", tasks=tasks)


def test_get_ready_tasks_no_deps() -> None:
    tasks = [
        SwarmTask(id="a", description="A", agent_type="coder"),
        SwarmTask(id="b", description="B", agent_type="coder"),
    ]
    orch = SwarmOrchestrator(plan=_make_plan(tasks), cwd="/tmp")
    ready = orch._get_ready_tasks()
    assert len(ready) == 2


def test_get_ready_tasks_with_deps() -> None:
    tasks = [
        SwarmTask(id="a", description="A", agent_type="coder"),
        SwarmTask(id="b", description="B", agent_type="reviewer", dependencies=["a"]),
    ]
    orch = SwarmOrchestrator(plan=_make_plan(tasks), cwd="/tmp")
    ready = orch._get_ready_tasks()
    assert len(ready) == 1
    assert ready[0].id == "a"


def test_get_ready_tasks_after_completion() -> None:
    tasks = [
        SwarmTask(id="a", description="A", agent_type="coder", status=TaskStatus.COMPLETED),
        SwarmTask(id="b", description="B", agent_type="reviewer", dependencies=["a"]),
    ]
    orch = SwarmOrchestrator(plan=_make_plan(tasks), cwd="/tmp")
    orch.completed_task_ids.add("a")
    ready = orch._get_ready_tasks()
    assert len(ready) == 1
    assert ready[0].id == "b"


def test_all_done_when_all_completed() -> None:
    tasks = [
        SwarmTask(id="a", description="A", agent_type="coder", status=TaskStatus.COMPLETED),
        SwarmTask(id="b", description="B", agent_type="tester", status=TaskStatus.FAILED),
    ]
    orch = SwarmOrchestrator(plan=_make_plan(tasks), cwd="/tmp")
    assert orch._all_done() is True


def test_all_done_with_pending() -> None:
    tasks = [
        SwarmTask(id="a", description="A", agent_type="coder", status=TaskStatus.COMPLETED),
        SwarmTask(id="b", description="B", agent_type="tester", status=TaskStatus.PENDING),
    ]
    orch = SwarmOrchestrator(plan=_make_plan(tasks), cwd="/tmp")
    assert orch._all_done() is False


def test_file_conflict_detection() -> None:
    tasks = [
        SwarmTask(id="a", description="A", agent_type="coder", files_to_modify=["src/auth.ts"]),
        SwarmTask(id="b", description="B", agent_type="coder", files_to_modify=["src/auth.ts"]),
    ]
    orch = SwarmOrchestrator(plan=_make_plan(tasks), cwd="/tmp")

    # Lock files for task a
    agent_a = SwarmAgent(id="agent-a", name="coder-a", task_id="a", status=AgentStatus.WORKING)
    orch.agents["agent-a"] = agent_a
    orch._file_locks["src/auth.ts"] = "agent-a"

    conflict = orch._check_file_conflict(tasks[1])
    assert conflict is not None
    assert conflict.file_path == "src/auth.ts"


def test_no_conflict_when_different_files() -> None:
    tasks = [
        SwarmTask(id="a", description="A", agent_type="coder", files_to_modify=["src/auth.ts"]),
        SwarmTask(id="b", description="B", agent_type="coder", files_to_modify=["src/user.ts"]),
    ]
    orch = SwarmOrchestrator(plan=_make_plan(tasks), cwd="/tmp")
    orch._file_locks["src/auth.ts"] = "agent-a"
    orch.agents["agent-a"] = SwarmAgent(
        id="agent-a", name="coder-a", task_id="a", status=AgentStatus.WORKING
    )

    conflict = orch._check_file_conflict(tasks[1])
    assert conflict is None


def test_cancel_pending_tasks() -> None:
    tasks = [
        SwarmTask(id="a", description="A", agent_type="coder", status=TaskStatus.COMPLETED),
        SwarmTask(id="b", description="B", agent_type="tester", status=TaskStatus.PENDING),
        SwarmTask(id="c", description="C", agent_type="reviewer", status=TaskStatus.BLOCKED),
    ]
    orch = SwarmOrchestrator(plan=_make_plan(tasks), cwd="/tmp")
    orch._cancel_pending_tasks(reason="Budget exceeded")

    assert tasks[0].status == TaskStatus.COMPLETED  # unchanged
    assert tasks[1].status == TaskStatus.CANCELLED
    assert tasks[2].status == TaskStatus.CANCELLED
    assert tasks[1].error == "Budget exceeded"


def test_active_agent_count() -> None:
    orch = SwarmOrchestrator(plan=_make_plan([]), cwd="/tmp")
    orch.agents["a1"] = SwarmAgent(
        id="a1", name="coder-1", task_id="t1", status=AgentStatus.WORKING
    )
    orch.agents["a2"] = SwarmAgent(
        id="a2", name="coder-2", task_id="t2", status=AgentStatus.COMPLETED
    )
    orch.agents["a3"] = SwarmAgent(
        id="a3", name="coder-3", task_id="t3", status=AgentStatus.WORKING
    )
    assert orch.active_agent_count == 2


def test_update_blocked_tasks() -> None:
    tasks = [
        SwarmTask(id="a", description="A", agent_type="coder"),
        SwarmTask(
            id="b", description="B", agent_type="reviewer",
            dependencies=["a"], status=TaskStatus.BLOCKED,
        ),
    ]
    orch = SwarmOrchestrator(plan=_make_plan(tasks), cwd="/tmp")
    orch.completed_task_ids.add("a")
    orch._update_blocked_tasks("a")
    assert tasks[1].status == TaskStatus.PENDING
