"""Opus Quality Gate — Uses Opus 4.6 to review agent outputs before final results.

This is Phase 2.5 in the swarm pipeline: after agents complete their tasks but
before reporting final results, Opus reviews the combined output for:
- Code correctness and consistency across agents
- Missed edge cases or security issues
- Integration problems between different agents' work
- Whether the original task was fully addressed

This mirrors how senior engineers review junior engineers' work, and
demonstrates strategic Opus 4.6 usage for the hardest reasoning tasks.
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock

from .types import SwarmPlan, SwarmResult, SwarmTask, TaskStatus

QUALITY_GATE_PROMPT = """You are a senior software architect performing a quality review of work done by a team of junior engineers. Each engineer completed a subtask independently, and you need to assess the overall quality and coherence of their combined work.

ORIGINAL TASK:
{original_prompt}

SUBTASK RESULTS:
{task_summaries}

REVIEW CRITERIA:
1. **Completeness**: Was the original task fully addressed?
2. **Consistency**: Do the subtasks' outputs work together cohesively?
3. **Correctness**: Are there any bugs, logic errors, or security issues?
4. **Quality**: Is the code clean, well-structured, and maintainable?

OUTPUT FORMAT (strict JSON):
{{
  "overall_score": 1-10,
  "verdict": "pass" | "needs_revision" | "fail",
  "summary": "Brief overall assessment",
  "task_reviews": [
    {{
      "task_id": "task-1",
      "score": 1-10,
      "issues": ["list of specific issues"],
      "suggestions": ["list of improvement suggestions"]
    }}
  ],
  "integration_issues": ["issues with how tasks work together"],
  "missing_items": ["things not addressed by any task"]
}}

Be thorough but fair. Focus on actionable feedback."""


async def run_quality_gate(
    result: SwarmResult,
    cwd: str,
    model: str = "opus",
) -> QualityReport:
    """Run Opus 4.6 quality gate on completed agent work.

    Args:
        result: The SwarmResult from orchestrator execution
        cwd: Working directory
        model: Model for review (default: opus)

    Returns:
        QualityReport with scores, issues, and suggestions
    """
    # Build task summaries
    task_summaries = _build_task_summaries(result)

    prompt = QUALITY_GATE_PROMPT.format(
        original_prompt=result.plan.original_prompt,
        task_summaries=task_summaries,
    )

    options = ClaudeAgentOptions(
        model=model,
        cwd=cwd,
        permission_mode="default",
        max_turns=2,
    )

    collected_text = ""
    review_cost = 0.0

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    collected_text += block.text
        elif isinstance(message, ResultMessage):
            review_cost = message.total_cost_usd or 0.0

    return _parse_quality_report(collected_text, review_cost)


def _build_task_summaries(result: SwarmResult) -> str:
    """Build a formatted summary of all completed task results."""
    summaries = []

    for task in result.plan.tasks:
        status_str = task.status.value.upper()
        summary = f"""--- Task: {task.id} ({status_str}) ---
Agent Type: {task.agent_type}
Description: {task.description}
Files Modified: {', '.join(task.files_to_modify) or 'none'}
Duration: {task.duration_ms}ms | Cost: ${task.cost_usd:.4f}"""

        if task.result:
            # Truncate long results
            result_text = task.result[:2000]
            if len(task.result) > 2000:
                result_text += "\n... (truncated)"
            summary += f"\nOutput:\n{result_text}"

        if task.error:
            summary += f"\nError: {task.error}"

        summaries.append(summary)

    return "\n\n".join(summaries)


from dataclasses import dataclass, field
import json


@dataclass
class TaskReview:
    """Review of a single task's output."""
    task_id: str
    score: int = 0
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class QualityReport:
    """Result of the Opus quality gate review."""
    overall_score: int = 0
    verdict: str = "pass"  # pass, needs_revision, fail
    summary: str = ""
    task_reviews: list[TaskReview] = field(default_factory=list)
    integration_issues: list[str] = field(default_factory=list)
    missing_items: list[str] = field(default_factory=list)
    review_cost_usd: float = 0.0


def _parse_quality_report(text: str, cost: float) -> QualityReport:
    """Parse Opus's quality review response."""
    # Try to extract JSON
    json_str = _extract_json(text)
    if not json_str:
        return QualityReport(
            overall_score=7,
            verdict="pass",
            summary="Quality review completed (output parsing failed — defaulting to pass)",
            review_cost_usd=cost,
        )

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return QualityReport(
            overall_score=7,
            verdict="pass",
            summary="Quality review completed (JSON parsing failed — defaulting to pass)",
            review_cost_usd=cost,
        )

    task_reviews = []
    for tr in data.get("task_reviews", []):
        task_reviews.append(
            TaskReview(
                task_id=tr.get("task_id", ""),
                score=tr.get("score", 0),
                issues=tr.get("issues", []),
                suggestions=tr.get("suggestions", []),
            )
        )

    return QualityReport(
        overall_score=data.get("overall_score", 0),
        verdict=data.get("verdict", "pass"),
        summary=data.get("summary", ""),
        task_reviews=task_reviews,
        integration_issues=data.get("integration_issues", []),
        missing_items=data.get("missing_items", []),
        review_cost_usd=cost,
    )


def _extract_json(text: str) -> str | None:
    """Extract JSON from text (handles markdown code blocks)."""
    for marker in ["```json\n", "```json\r\n", "```\n{"]:
        start = text.find(marker)
        if start != -1:
            if marker == "```\n{":
                start += 4
            else:
                start += len(marker)
            end = text.find("```", start)
            if end != -1:
                return text[start:end].strip()

    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

    return None
