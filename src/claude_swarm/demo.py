"""Demo mode — simulates a full swarm run with animated TUI for presentations.

This allows judges, users, and demos to see the full Claude Swarm experience
without requiring an API key or incurring costs. The simulation uses realistic
task decomposition, timing, and cost estimates.
"""

from __future__ import annotations

import asyncio
import random
import time

from .types import (
    AgentStatus,
    FileConflict,
    SwarmAgent,
    SwarmPlan,
    SwarmResult,
    SwarmTask,
    TaskStatus,
)
from .ui import SwarmUI

# Realistic demo scenarios
DEMO_SCENARIOS = {
    "auth": {
        "prompt": "Refactor auth module from Express middleware to Next.js API routes",
        "tasks": [
            {
                "id": "task-1",
                "description": "Create Next.js API route handlers for login/logout/register",
                "agent_type": "coder",
                "dependencies": [],
                "files_to_modify": ["src/app/api/auth/login/route.ts", "src/app/api/auth/register/route.ts"],
                "tools": ["Read", "Write", "Edit", "Bash", "Grep", "Glob"],
            },
            {
                "id": "task-2",
                "description": "Migrate session management from Express to NextAuth.js",
                "agent_type": "coder",
                "dependencies": [],
                "files_to_modify": ["src/lib/auth.ts", "src/app/api/auth/[...nextauth]/route.ts"],
                "tools": ["Read", "Write", "Edit", "Bash"],
            },
            {
                "id": "task-3",
                "description": "Update middleware for Next.js edge runtime",
                "agent_type": "coder",
                "dependencies": ["task-1"],
                "files_to_modify": ["src/middleware.ts"],
                "tools": ["Read", "Write", "Edit"],
            },
            {
                "id": "task-4",
                "description": "Write integration tests for auth endpoints",
                "agent_type": "tester",
                "dependencies": ["task-1", "task-2"],
                "files_to_modify": ["tests/auth.test.ts"],
                "tools": ["Read", "Write", "Edit", "Bash"],
            },
            {
                "id": "task-5",
                "description": "Security review of auth implementation",
                "agent_type": "reviewer",
                "dependencies": ["task-1", "task-2", "task-3"],
                "files_to_modify": [],
                "tools": ["Read", "Grep", "Glob"],
            },
        ],
    },
    "api": {
        "prompt": "Build a REST API for user management with CRUD operations",
        "tasks": [
            {
                "id": "task-1",
                "description": "Create user model and database schema",
                "agent_type": "coder",
                "dependencies": [],
                "files_to_modify": ["src/models/user.ts", "prisma/schema.prisma"],
                "tools": ["Read", "Write", "Edit", "Bash"],
            },
            {
                "id": "task-2",
                "description": "Implement CRUD API endpoints",
                "agent_type": "coder",
                "dependencies": ["task-1"],
                "files_to_modify": ["src/app/api/users/route.ts", "src/app/api/users/[id]/route.ts"],
                "tools": ["Read", "Write", "Edit", "Bash"],
            },
            {
                "id": "task-3",
                "description": "Add input validation with Zod schemas",
                "agent_type": "coder",
                "dependencies": ["task-1"],
                "files_to_modify": ["src/lib/validators.ts"],
                "tools": ["Read", "Write", "Edit"],
            },
            {
                "id": "task-4",
                "description": "Write comprehensive tests for all endpoints",
                "agent_type": "tester",
                "dependencies": ["task-2", "task-3"],
                "files_to_modify": ["tests/users.test.ts"],
                "tools": ["Read", "Write", "Edit", "Bash"],
            },
        ],
    },
}

# Simulated tool sequences for different agent types
TOOL_SEQUENCES = {
    "coder": ["Read", "Grep", "Glob", "Read", "Write", "Edit", "Read", "Edit", "Bash"],
    "tester": ["Read", "Glob", "Write", "Bash", "Edit", "Bash"],
    "reviewer": ["Read", "Grep", "Glob", "Read", "Grep", "Read"],
    "refactorer": ["Read", "Grep", "Read", "Edit", "Edit", "Bash"],
    "documenter": ["Read", "Glob", "Write", "Edit"],
}


def _build_demo_plan(scenario_key: str | None = None) -> SwarmPlan:
    """Build a demo plan from a scenario or default."""
    if scenario_key and scenario_key in DEMO_SCENARIOS:
        scenario = DEMO_SCENARIOS[scenario_key]
    else:
        scenario = DEMO_SCENARIOS["auth"]

    tasks = []
    for t in scenario["tasks"]:
        tasks.append(
            SwarmTask(
                id=t["id"],
                description=t["description"],
                agent_type=t["agent_type"],
                dependencies=t.get("dependencies", []),
                files_to_modify=t.get("files_to_modify", []),
                tools=t.get("tools", []),
                prompt=f"Demo prompt for {t['description']}",
            )
        )

    return SwarmPlan(
        original_prompt=scenario["prompt"],
        tasks=tasks,
        model_used="opus",
    )


async def run_demo(
    prompt: str | None = None,
    scenario: str | None = None,
    speed: float = 1.0,
) -> None:
    """Run a demo simulation with animated TUI.

    Args:
        prompt: Optional custom prompt (uses scenario default if None)
        scenario: Which demo scenario to use ("auth" or "api")
        speed: Speed multiplier (1.0 = normal, 2.0 = 2x faster, 0.5 = slower)
    """
    ui = SwarmUI()

    # Determine scenario
    if scenario is None:
        scenario = "auth"

    plan = _build_demo_plan(scenario)
    if prompt:
        plan.original_prompt = prompt

    # Phase 1: Show the plan
    ui.console.print("\n[bold blue]Phase 1:[/bold blue] Decomposing task with Opus 4.6...")
    await asyncio.sleep(1.5 / speed)
    ui.print_plan(plan)
    await asyncio.sleep(1.0 / speed)

    # Phase 2: Animated execution
    ui.console.print("[bold blue]Phase 2:[/bold blue] Executing swarm...\n")
    await asyncio.sleep(0.5 / speed)

    agents: dict[str, SwarmAgent] = {}
    conflicts: list[FileConflict] = []
    total_cost = 0.0
    completed_ids: set[str] = set()

    live = ui.start_live()
    try:
        for group in plan.parallel_groups:
            # Launch agents for this wave
            wave_agents: list[tuple[SwarmTask, SwarmAgent]] = []
            for task_id in group:
                task = next(t for t in plan.tasks if t.id == task_id)
                task.status = TaskStatus.RUNNING

                agent_id = f"agent-{task.id}"
                agent = SwarmAgent(
                    id=agent_id,
                    name=f"{task.agent_type}-{task.id}",
                    task_id=task.id,
                    status=AgentStatus.WORKING,
                )
                agents[agent_id] = agent
                wave_agents.append((task, agent))

            # Simulate tool usage for each agent in this wave
            max_tools = max(
                len(TOOL_SEQUENCES.get(t.agent_type, ["Read"])) for t, _ in wave_agents
            )

            for tool_idx in range(max_tools):
                for task, agent in wave_agents:
                    tools = TOOL_SEQUENCES.get(task.agent_type, ["Read"])
                    if tool_idx < len(tools):
                        agent.current_tool = tools[tool_idx]
                        agent.turns = tool_idx + 1
                        # Simulate cost accumulation
                        agent.cost_usd += random.uniform(0.001, 0.008)
                        task.cost_usd = agent.cost_usd

                total_cost = sum(a.cost_usd for a in agents.values())
                dashboard = ui.create_dashboard(plan, agents, total_cost, conflicts)
                live.update(dashboard)
                await asyncio.sleep(0.4 / speed)

            # Complete all agents in this wave
            for task, agent in wave_agents:
                task.status = TaskStatus.COMPLETED
                task.duration_ms = random.randint(3000, 12000)
                agent.status = AgentStatus.COMPLETED
                agent.current_tool = None
                completed_ids.add(task.id)

            total_cost = sum(a.cost_usd for a in agents.values())
            dashboard = ui.create_dashboard(plan, agents, total_cost, conflicts)
            live.update(dashboard)
            await asyncio.sleep(0.8 / speed)

    finally:
        ui.stop_live()

    # Phase 3: Results
    elapsed = sum(t.duration_ms for t in plan.tasks)
    result = SwarmResult(
        plan=plan,
        completed_tasks=[t for t in plan.tasks if t.status == TaskStatus.COMPLETED],
        failed_tasks=[],
        conflicts=conflicts,
        total_cost_usd=total_cost,
        total_duration_ms=elapsed,
        agents_used=len(agents),
    )

    ui.console.print("\n[bold blue]Phase 3:[/bold blue] Results")
    ui.print_results(result)
    ui.console.print("[dim italic]This was a demo simulation — no API calls were made.[/dim italic]\n")
