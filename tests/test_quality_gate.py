"""Tests for the Opus quality gate module."""

import json

from claude_swarm.quality_gate import (
    QualityReport,
    TaskReview,
    _build_task_summaries,
    _extract_json,
    _parse_quality_report,
)
from claude_swarm.types import SwarmPlan, SwarmResult, SwarmTask, TaskStatus


def _make_result() -> SwarmResult:
    tasks = [
        SwarmTask(
            id="t1",
            description="Create auth routes",
            agent_type="coder",
            status=TaskStatus.COMPLETED,
            files_to_modify=["src/auth.ts"],
            result="Created login and register endpoints",
            cost_usd=0.05,
            duration_ms=5000,
        ),
        SwarmTask(
            id="t2",
            description="Write tests",
            agent_type="tester",
            status=TaskStatus.COMPLETED,
            files_to_modify=["tests/auth.test.ts"],
            result="Added 12 test cases",
            cost_usd=0.03,
            duration_ms=3000,
        ),
    ]
    plan = SwarmPlan(original_prompt="Add auth", tasks=tasks)
    return SwarmResult(
        plan=plan,
        completed_tasks=tasks,
        failed_tasks=[],
        conflicts=[],
        total_cost_usd=0.08,
        total_duration_ms=8000,
        agents_used=2,
    )


def test_build_task_summaries() -> None:
    result = _make_result()
    summaries = _build_task_summaries(result)
    assert "t1" in summaries
    assert "COMPLETED" in summaries
    assert "auth.ts" in summaries


def test_parse_quality_report_valid_json() -> None:
    json_str = json.dumps({
        "overall_score": 8,
        "verdict": "pass",
        "summary": "Good work",
        "task_reviews": [
            {"task_id": "t1", "score": 9, "issues": [], "suggestions": ["Add error handling"]},
        ],
        "integration_issues": [],
        "missing_items": [],
    })
    report = _parse_quality_report(f"```json\n{json_str}\n```", cost=0.02)
    assert report.overall_score == 8
    assert report.verdict == "pass"
    assert report.summary == "Good work"
    assert len(report.task_reviews) == 1
    assert report.task_reviews[0].score == 9
    assert report.review_cost_usd == 0.02


def test_parse_quality_report_fallback() -> None:
    report = _parse_quality_report("This is not JSON at all", cost=0.01)
    assert report.overall_score == 7  # default pass
    assert report.verdict == "pass"
    assert report.review_cost_usd == 0.01


def test_extract_json_from_markdown() -> None:
    text = 'Here is the review:\n```json\n{"score": 8}\n```\nDone.'
    result = _extract_json(text)
    assert result is not None
    assert json.loads(result)["score"] == 8


def test_extract_json_raw() -> None:
    text = 'The result is {"score": 8} end'
    result = _extract_json(text)
    assert result is not None
    assert json.loads(result)["score"] == 8


def test_extract_json_none() -> None:
    result = _extract_json("No JSON here")
    assert result is None
