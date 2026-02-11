"""Tests for the demo simulation module."""

import asyncio

from claude_swarm.demo import _build_demo_plan, DEMO_SCENARIOS


def test_build_demo_plan_auth() -> None:
    plan = _build_demo_plan("auth")
    assert plan.task_count == 5
    assert plan.original_prompt == DEMO_SCENARIOS["auth"]["prompt"]
    assert plan.model_used == "opus"


def test_build_demo_plan_api() -> None:
    plan = _build_demo_plan("api")
    assert plan.task_count == 4
    assert plan.original_prompt == DEMO_SCENARIOS["api"]["prompt"]


def test_build_demo_plan_default() -> None:
    plan = _build_demo_plan(None)
    assert plan.task_count == 5  # defaults to auth scenario


def test_demo_plan_has_dependencies() -> None:
    plan = _build_demo_plan("auth")
    # task-3 depends on task-1
    task_3 = next(t for t in plan.tasks if t.id == "task-3")
    assert "task-1" in task_3.dependencies


def test_demo_plan_parallel_groups() -> None:
    plan = _build_demo_plan("auth")
    groups = plan.parallel_groups
    assert len(groups) >= 2  # at least 2 waves
    # First wave should contain independent tasks
    assert "task-1" in groups[0]
    assert "task-2" in groups[0]


def test_demo_plan_has_tools() -> None:
    plan = _build_demo_plan("auth")
    for task in plan.tasks:
        assert len(task.tools) > 0
