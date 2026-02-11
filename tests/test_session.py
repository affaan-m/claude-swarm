"""Tests for session recording and replay."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from claude_swarm.session import SessionRecorder, load_session_events


def test_session_recorder_lifecycle() -> None:
    """Test full session recording lifecycle."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("claude_swarm.session.SESSIONS_DIR", Path(tmpdir)):
            recorder = SessionRecorder(session_id="test-session-001")
            recorder.start(prompt="Test task", cwd="/tmp/project")

            recorder.record_plan({"tasks": [{"id": "t1", "description": "Do thing"}]})
            recorder.record_agent_started("agent-1", "t1", "Do thing")
            recorder.record_tool_use("agent-1", "t1", "Read", {"file_path": "/tmp/test.py"})
            recorder.record_agent_completed("agent-1", "t1", cost=0.05, duration_ms=5000)

            recorder.finish({"completed": 1, "total_cost_usd": 0.05})

            # Verify files were created
            session_dir = Path(tmpdir) / "test-session-001"
            assert session_dir.exists()
            assert (session_dir / "metadata.json").exists()
            assert (session_dir / "events.jsonl").exists()

            # Verify metadata
            with open(session_dir / "metadata.json") as f:
                meta = json.load(f)
            assert meta["session_id"] == "test-session-001"
            assert meta["prompt"] == "Test task"
            assert meta["result"]["completed"] == 1

            # Verify events
            events = load_session_events("test-session-001")
            # session_started + plan_created + agent_started
            # + tool_use + agent_completed + session_completed
            assert len(events) == 6


def test_session_recorder_events_count() -> None:
    """Verify correct number of events are recorded."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("claude_swarm.session.SESSIONS_DIR", Path(tmpdir)):
            recorder = SessionRecorder(session_id="test-count")
            recorder.start(prompt="Count test", cwd="/tmp")
            recorder.record_agent_started("a1", "t1", "Task 1")
            recorder.record_agent_failed("a1", "t1", "Something broke")
            recorder.finish({"failed": 1})

            events = load_session_events("test-count")
            # session_started + agent_started + agent_failed + session_completed
            assert len(events) == 4
            assert events[0]["event_type"] == "session_started"
            assert events[1]["event_type"] == "agent_started"
            assert events[2]["event_type"] == "agent_failed"
            assert events[3]["event_type"] == "session_completed"


def test_load_nonexistent_session() -> None:
    """Loading a non-existent session returns empty list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("claude_swarm.session.SESSIONS_DIR", Path(tmpdir)):
            events = load_session_events("does-not-exist")
            assert events == []
