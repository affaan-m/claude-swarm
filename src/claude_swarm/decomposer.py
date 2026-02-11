"""Task Decomposer — Uses Opus 4.6 to break complex tasks into a dependency graph."""

from __future__ import annotations

import json
import uuid
from typing import Any

from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock

from .types import SwarmPlan, SwarmTask, TaskStatus

DECOMPOSE_SYSTEM_PROMPT = """You are a task decomposition expert. Given a complex software engineering task, break it down into independent subtasks that can be executed by separate Claude Code agents in parallel.

RULES:
1. Each subtask should be as independent as possible
2. Specify dependencies between tasks (task IDs)
3. Each task should specify which files it will modify
4. Tasks should be small enough for one agent to complete in a few minutes
5. Include a "reviewer" task at the end that depends on all implementation tasks

OUTPUT FORMAT (strict JSON):
{
  "tasks": [
    {
      "id": "task-1",
      "description": "Short description of what to do",
      "agent_type": "coder|reviewer|tester|refactorer|documenter",
      "dependencies": [],
      "files_to_modify": ["src/auth.ts", "src/middleware.ts"],
      "tools": ["Read", "Write", "Edit", "Bash", "Grep", "Glob"],
      "prompt": "Detailed instructions for the agent..."
    }
  ]
}

AGENT TYPES:
- coder: Writes new code or modifies existing code
- reviewer: Reviews code changes for quality/security
- tester: Writes and runs tests
- refactorer: Refactors existing code
- documenter: Updates documentation

IMPORTANT:
- Minimize file overlap between tasks to prevent conflicts
- If two tasks MUST edit the same file, make one depend on the other
- Keep the total number of tasks between 2 and 8
- Each task's prompt should be self-contained with all context needed"""


async def decompose_task(
    prompt: str,
    cwd: str,
    model: str = "opus",
) -> SwarmPlan:
    """Use Opus 4.6 to decompose a complex task into a dependency graph.

    Args:
        prompt: The complex task description
        cwd: Working directory for the project
        model: Model to use for decomposition (default: opus for best reasoning)

    Returns:
        SwarmPlan with tasks and dependency information
    """
    options = ClaudeAgentOptions(
        model=model,
        cwd=cwd,
        permission_mode="default",
        max_turns=3,
    )

    decompose_prompt = f"""{DECOMPOSE_SYSTEM_PROMPT}

PROJECT DIRECTORY: {cwd}

TASK TO DECOMPOSE:
{prompt}

First, explore the codebase to understand the structure. Then output your decomposition as a JSON code block.
"""

    collected_text = ""
    total_cost = 0.0

    async for message in query(prompt=decompose_prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    collected_text += block.text
        elif isinstance(message, ResultMessage):
            total_cost = message.total_cost_usd or 0.0

    # Extract JSON from the response
    tasks = _parse_decomposition(collected_text)

    return SwarmPlan(
        original_prompt=prompt,
        tasks=tasks,
        estimated_total_cost=total_cost * len(tasks),  # rough estimate
        model_used=model,
    )


def _parse_decomposition(text: str) -> list[SwarmTask]:
    """Parse the JSON task decomposition from Opus's response."""
    # Find JSON block in the response
    json_str = _extract_json_block(text)
    if not json_str:
        # Fallback: try to parse the entire text as JSON
        json_str = text.strip()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # If parsing fails, create a single fallback task
        return [
            SwarmTask(
                id=f"task-{uuid.uuid4().hex[:8]}",
                description="Execute the original task (decomposition failed)",
                agent_type="coder",
                prompt=text,
                tools=["Read", "Write", "Edit", "Bash", "Grep", "Glob"],
            )
        ]

    tasks_data = data.get("tasks", data) if isinstance(data, dict) else data

    tasks: list[SwarmTask] = []
    for item in tasks_data:
        task = SwarmTask(
            id=item.get("id", f"task-{uuid.uuid4().hex[:8]}"),
            description=item.get("description", ""),
            agent_type=item.get("agent_type", "coder"),
            dependencies=item.get("dependencies", []),
            files_to_modify=item.get("files_to_modify", []),
            tools=item.get("tools", ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]),
            prompt=item.get("prompt", item.get("description", "")),
            status=TaskStatus.PENDING,
        )
        tasks.append(task)

    return tasks


def _extract_json_block(text: str) -> str | None:
    """Extract a JSON code block from markdown-formatted text."""
    # Try ```json ... ``` first
    start_markers = ["```json\n", "```json\r\n", "```\n{"]
    for marker in start_markers:
        start = text.find(marker)
        if start != -1:
            # Adjust start position
            if marker == "```\n{":
                start += 4  # skip ```\n, keep {
            else:
                start += len(marker)
            end = text.find("```", start)
            if end != -1:
                return text[start:end].strip()

    # Try finding raw JSON object
    start = text.find("{")
    if start != -1:
        # Find the matching closing brace
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

    return None
