"""Swarm Orchestrator — Manages parallel agent execution with dependency tracking."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable
from typing import Any

import anyio
from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, query
from claude_agent_sdk.types import (
    AssistantMessage,
    HookContext,
    HookInput,
    HookJSONOutput,
    HookMatcher,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

from .session import SessionRecorder
from .types import (
    AgentStatus,
    FileConflict,
    SwarmAgent,
    SwarmPlan,
    SwarmResult,
    SwarmTask,
    TaskStatus,
)

# Callback type for UI updates
OnUpdate = Callable[[], None]
OnAgentEvent = Callable[[str, str, Any], None]  # agent_id, event_type, data


class SwarmOrchestrator:
    """Orchestrates parallel Claude Code agents with dependency tracking.

    The orchestrator manages a pool of agents executing tasks from a SwarmPlan.
    It respects task dependencies, detects file conflicts, tracks costs,
    and provides real-time status updates for the TUI.
    """

    def __init__(
        self,
        plan: SwarmPlan,
        cwd: str,
        max_concurrent: int = 4,
        max_budget_usd: float = 5.0,
        on_update: OnUpdate | None = None,
        on_agent_event: OnAgentEvent | None = None,
        recorder: SessionRecorder | None = None,
    ) -> None:
        self.plan = plan
        self.cwd = cwd
        self.max_concurrent = max_concurrent
        self.max_budget_usd = max_budget_usd
        self.on_update = on_update or (lambda: None)
        self.on_agent_event = on_agent_event or (lambda *_: None)
        self.recorder = recorder

        # State tracking
        self.agents: dict[str, SwarmAgent] = {}
        self.completed_task_ids: set[str] = set()
        self.conflicts: list[FileConflict] = []
        self.total_cost: float = 0.0
        self.start_time: float = 0.0
        self._budget_exceeded: bool = False

        # Map file paths to agent IDs currently modifying them
        self._file_locks: dict[str, str] = {}

        # Task lookup
        self._tasks: dict[str, SwarmTask] = {t.id: t for t in plan.tasks}

    @property
    def active_agent_count(self) -> int:
        """Count agents currently working."""
        return sum(1 for a in self.agents.values() if a.status == AgentStatus.WORKING)

    async def run(self) -> SwarmResult:
        """Execute all tasks in the plan, respecting dependencies.

        Enforces budget limits — cancels remaining tasks if total cost exceeds max_budget_usd.

        Returns:
            SwarmResult with completed/failed tasks and statistics
        """
        self.start_time = time.monotonic()

        async with anyio.create_task_group() as tg:
            while not self._all_done():
                # Budget enforcement: cancel pending tasks if over budget
                if self.total_cost >= self.max_budget_usd and not self._budget_exceeded:
                    self._budget_exceeded = True
                    self._cancel_pending_tasks(
                        reason=f"Budget exceeded: ${self.total_cost:.4f} >= ${self.max_budget_usd:.2f}"
                    )
                    self.on_update()
                    # Wait for running agents to finish, but don't launch new ones
                    if self.active_agent_count == 0:
                        break
                    await anyio.sleep(0.5)
                    continue

                ready_tasks = self._get_ready_tasks()

                for task in ready_tasks:
                    if self.active_agent_count >= self.max_concurrent:
                        break
                    # Check for file conflicts before launching
                    conflict = self._check_file_conflict(task)
                    if conflict:
                        self.conflicts.append(conflict)
                        task.status = TaskStatus.BLOCKED
                        self.on_update()
                        continue

                    task.status = TaskStatus.RUNNING
                    self._lock_files(task)
                    tg.start_soon(self._run_agent, task)
                    self.on_update()

                # Brief pause before checking again
                await anyio.sleep(0.5)

        elapsed = int((time.monotonic() - self.start_time) * 1000)

        return SwarmResult(
            plan=self.plan,
            completed_tasks=[t for t in self.plan.tasks if t.status == TaskStatus.COMPLETED],
            failed_tasks=[t for t in self.plan.tasks if t.status == TaskStatus.FAILED],
            conflicts=self.conflicts,
            total_cost_usd=self.total_cost,
            total_duration_ms=elapsed,
            agents_used=len(self.agents),
        )

    async def _run_agent(self, task: SwarmTask) -> None:
        """Run a single agent for a task."""
        agent_id = f"agent-{uuid.uuid4().hex[:8]}"
        agent = SwarmAgent(
            id=agent_id,
            name=f"{task.agent_type}-{task.id}",
            task_id=task.id,
            status=AgentStatus.WORKING,
        )
        self.agents[agent_id] = agent
        self.on_agent_event(agent_id, "started", {"task_id": task.id})
        if self.recorder:
            self.recorder.record_agent_started(agent_id, task.id, task.description)
        self.on_update()

        try:
            # Create hooks for tracking this agent's activity
            hooks = self._create_agent_hooks(agent)

            options = ClaudeAgentOptions(
                model="haiku",
                cwd=self.cwd,
                permission_mode="acceptEdits",
                max_turns=20,
                max_budget_usd=0.50,
                hooks=hooks,
                allowed_tools=task.tools,
            )

            collected_text = ""
            task_start = time.monotonic()

            async for message in query(prompt=task.prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            collected_text += block.text
                        elif isinstance(block, ToolUseBlock):
                            agent.current_tool = block.name
                            agent.turns += 1
                            self.on_agent_event(
                                agent_id, "tool_use", {"tool": block.name, "input": block.input}
                            )
                            if self.recorder:
                                self.recorder.record_tool_use(
                                    agent_id, task.id, block.name, block.input
                                )
                            self.on_update()
                elif isinstance(message, ResultMessage):
                    task.cost_usd = message.total_cost_usd or 0.0
                    self.total_cost += task.cost_usd

            task.duration_ms = int((time.monotonic() - task_start) * 1000)
            task.result = collected_text
            task.status = TaskStatus.COMPLETED
            task.assigned_agent = agent_id
            self.completed_task_ids.add(task.id)

            agent.status = AgentStatus.COMPLETED
            agent.cost_usd = task.cost_usd
            self.on_agent_event(agent_id, "completed", {"cost": task.cost_usd})
            if self.recorder:
                self.recorder.record_agent_completed(
                    agent_id, task.id, task.cost_usd, task.duration_ms
                )

        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.error = str(exc)
            agent.status = AgentStatus.FAILED
            self.on_agent_event(agent_id, "failed", {"error": str(exc)})
            if self.recorder:
                self.recorder.record_agent_failed(agent_id, task.id, str(exc))

        finally:
            self._unlock_files(task)
            # Unblock dependent tasks
            self._update_blocked_tasks(task.id)
            self.on_update()

    def _create_agent_hooks(self, agent: SwarmAgent) -> dict[str, list[HookMatcher]]:
        """Create hooks to track an agent's file modifications."""

        async def track_file_writes(
            input_data: HookInput, tool_use_id: str | None, context: HookContext
        ) -> HookJSONOutput:
            tool_name = input_data.get("tool_name", "")
            tool_input = input_data.get("tool_input", {})

            if tool_name in ("Write", "Edit"):
                file_path = tool_input.get("file_path", "")
                if file_path and file_path not in agent.files_modified:
                    agent.files_modified.append(file_path)

            return {}

        return {
            "PostToolUse": [
                HookMatcher(matcher="Write|Edit", hooks=[track_file_writes]),
            ],
        }

    def _get_ready_tasks(self) -> list[SwarmTask]:
        """Get tasks whose dependencies are all completed."""
        ready = []
        for task in self.plan.tasks:
            if task.status != TaskStatus.PENDING:
                continue
            deps_met = all(d in self.completed_task_ids for d in task.dependencies)
            if deps_met:
                ready.append(task)
        return ready

    def _all_done(self) -> bool:
        """Check if all tasks are either completed, failed, or cancelled."""
        return all(
            t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
            for t in self.plan.tasks
        )

    def _check_file_conflict(self, task: SwarmTask) -> FileConflict | None:
        """Check if a task would conflict with currently running agents."""
        for file_path in task.files_to_modify:
            if file_path in self._file_locks:
                other_agent_id = self._file_locks[file_path]
                other_agent = self.agents.get(other_agent_id)
                if other_agent and other_agent.status == AgentStatus.WORKING:
                    return FileConflict(
                        file_path=file_path,
                        agent_ids=[other_agent_id, "pending"],
                        task_ids=[other_agent.task_id, task.id],
                    )
        return None

    def _lock_files(self, task: SwarmTask) -> None:
        """Lock files that a task will modify."""
        agent_id = task.assigned_agent or task.id
        for file_path in task.files_to_modify:
            self._file_locks[file_path] = agent_id

    def _unlock_files(self, task: SwarmTask) -> None:
        """Unlock files after a task completes."""
        for file_path in task.files_to_modify:
            if file_path in self._file_locks:
                del self._file_locks[file_path]

    def _update_blocked_tasks(self, completed_task_id: str) -> None:
        """Unblock tasks that were waiting on a completed task."""
        for task in self.plan.tasks:
            if task.status == TaskStatus.BLOCKED and completed_task_id in task.dependencies:
                # Check if all other deps are also met
                deps_met = all(d in self.completed_task_ids for d in task.dependencies)
                if deps_met:
                    task.status = TaskStatus.PENDING

    def _cancel_pending_tasks(self, reason: str) -> None:
        """Cancel all pending and blocked tasks (e.g., when budget is exceeded)."""
        for task in self.plan.tasks:
            if task.status in (TaskStatus.PENDING, TaskStatus.BLOCKED):
                task.status = TaskStatus.CANCELLED
                task.error = reason
        self.on_agent_event("orchestrator", "budget_exceeded", {"reason": reason})
