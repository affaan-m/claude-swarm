"""Tests for core type definitions."""

from claude_swarm.types import SwarmPlan, SwarmTask, TaskStatus


def test_swarm_task_is_ready() -> None:
    task = SwarmTask(
        id="task-1",
        description="Test task",
        agent_type="coder",
        status=TaskStatus.PENDING,
        dependencies=[],
    )
    assert task.is_ready is True


def test_swarm_task_not_ready_with_deps() -> None:
    task = SwarmTask(
        id="task-2",
        description="Test task",
        agent_type="coder",
        status=TaskStatus.PENDING,
        dependencies=["task-1"],
    )
    assert task.is_ready is False


def test_swarm_task_not_ready_if_running() -> None:
    task = SwarmTask(
        id="task-1",
        description="Test task",
        agent_type="coder",
        status=TaskStatus.RUNNING,
        dependencies=[],
    )
    assert task.is_ready is False


def test_swarm_plan_parallel_groups() -> None:
    tasks = [
        SwarmTask(id="a", description="A", agent_type="coder", dependencies=[]),
        SwarmTask(id="b", description="B", agent_type="coder", dependencies=[]),
        SwarmTask(id="c", description="C", agent_type="reviewer", dependencies=["a", "b"]),
    ]
    plan = SwarmPlan(original_prompt="test", tasks=tasks)

    groups = plan.parallel_groups
    assert len(groups) == 2
    assert set(groups[0]) == {"a", "b"}
    assert groups[1] == ["c"]


def test_swarm_plan_task_count() -> None:
    tasks = [
        SwarmTask(id="1", description="First", agent_type="coder"),
        SwarmTask(id="2", description="Second", agent_type="tester"),
    ]
    plan = SwarmPlan(original_prompt="test", tasks=tasks)
    assert plan.task_count == 2


def test_swarm_plan_serial_dependencies() -> None:
    tasks = [
        SwarmTask(id="a", description="A", agent_type="coder", dependencies=[]),
        SwarmTask(id="b", description="B", agent_type="coder", dependencies=["a"]),
        SwarmTask(id="c", description="C", agent_type="reviewer", dependencies=["b"]),
    ]
    plan = SwarmPlan(original_prompt="test", tasks=tasks)

    groups = plan.parallel_groups
    assert len(groups) == 3
    assert groups[0] == ["a"]
    assert groups[1] == ["b"]
    assert groups[2] == ["c"]
