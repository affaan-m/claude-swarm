"""Session replay — records and replays swarm execution for post-mortem review.

Each swarm execution is recorded as a session with:
- Session metadata (prompt, plan, config)
- Per-agent transcripts (tool calls, responses, costs)
- Timeline of events (start, tool_use, complete, fail, conflict)
- Final results and statistics

Sessions are saved to ~/.claude-swarm/sessions/<session-id>/
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SESSIONS_DIR = Path.home() / ".claude-swarm" / "sessions"


@dataclass
class SessionEvent:
    """A single event in the session timeline."""

    timestamp: float
    event_type: str  # started, tool_use, completed, failed, conflict, plan_created
    agent_id: str | None = None
    task_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "data": self.data,
        }


class SessionRecorder:
    """Records swarm execution events for replay."""

    def __init__(self, session_id: str | None = None) -> None:
        self.session_id = session_id or f"swarm-{uuid.uuid4().hex[:12]}"
        self.session_dir = SESSIONS_DIR / self.session_id
        self.events: list[SessionEvent] = []
        self.start_time = time.time()
        self._metadata: dict[str, Any] = {}

    def start(self, prompt: str, cwd: str) -> None:
        """Initialize a new recording session."""
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.start_time = time.time()
        self._metadata = {
            "session_id": self.session_id,
            "prompt": prompt,
            "cwd": cwd,
            "start_time": self.start_time,
        }
        self._record_event("session_started", data={"prompt": prompt, "cwd": cwd})

    def record_plan(self, plan_data: dict[str, Any]) -> None:
        """Record the decomposed plan."""
        self._metadata["plan"] = plan_data
        self._record_event("plan_created", data=plan_data)

    def record_agent_started(self, agent_id: str, task_id: str, task_description: str) -> None:
        """Record an agent starting work."""
        self._record_event(
            "agent_started",
            agent_id=agent_id,
            task_id=task_id,
            data={"description": task_description},
        )

    def record_tool_use(
        self, agent_id: str, task_id: str, tool_name: str, tool_input: dict[str, Any]
    ) -> None:
        """Record a tool call by an agent."""
        self._record_event(
            "tool_use",
            agent_id=agent_id,
            task_id=task_id,
            data={"tool": tool_name, "input": _truncate_input(tool_input)},
        )

    def record_agent_completed(
        self, agent_id: str, task_id: str, cost: float, duration_ms: int
    ) -> None:
        """Record an agent completing its task."""
        self._record_event(
            "agent_completed",
            agent_id=agent_id,
            task_id=task_id,
            data={"cost_usd": cost, "duration_ms": duration_ms},
        )

    def record_agent_failed(self, agent_id: str, task_id: str, error: str) -> None:
        """Record an agent failure."""
        self._record_event(
            "agent_failed",
            agent_id=agent_id,
            task_id=task_id,
            data={"error": error[:500]},
        )

    def record_conflict(self, file_path: str, agent_ids: list[str]) -> None:
        """Record a file conflict."""
        self._record_event(
            "file_conflict",
            data={"file_path": file_path, "agent_ids": agent_ids},
        )

    def finish(self, result_data: dict[str, Any]) -> str:
        """Finalize the recording and save to disk."""
        self._metadata["end_time"] = time.time()
        self._metadata["duration_s"] = self._metadata["end_time"] - self.start_time
        self._metadata["result"] = result_data

        self._record_event("session_completed", data=result_data)

        # Save metadata
        meta_path = self.session_dir / "metadata.json"
        with open(meta_path, "w") as f:
            json.dump(self._metadata, f, indent=2, default=str)

        # Save events as JSONL for streaming replay
        events_path = self.session_dir / "events.jsonl"
        with open(events_path, "w") as f:
            for event in self.events:
                f.write(json.dumps(event.to_dict(), default=str) + "\n")

        return str(self.session_dir)

    def _record_event(
        self,
        event_type: str,
        agent_id: str | None = None,
        task_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        event = SessionEvent(
            timestamp=time.time() - self.start_time,
            event_type=event_type,
            agent_id=agent_id,
            task_id=task_id,
            data=data or {},
        )
        self.events.append(event)


def list_sessions(limit: int = 20) -> list[dict[str, Any]]:
    """List recent sessions."""
    if not SESSIONS_DIR.exists():
        return []

    sessions = []
    for session_dir in sorted(SESSIONS_DIR.iterdir(), reverse=True):
        if not session_dir.is_dir():
            continue
        meta_path = session_dir / "metadata.json"
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
            sessions.append(
                {
                    "session_id": meta.get("session_id", session_dir.name),
                    "prompt": meta.get("prompt", "")[:80],
                    "start_time": meta.get("start_time"),
                    "duration_s": meta.get("duration_s"),
                    "result": meta.get("result", {}),
                }
            )
        if len(sessions) >= limit:
            break

    return sessions


def load_session_events(session_id: str) -> list[dict[str, Any]]:
    """Load events from a session for replay."""
    events_path = SESSIONS_DIR / session_id / "events.jsonl"
    if not events_path.exists():
        return []

    events = []
    with open(events_path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def _truncate_input(tool_input: dict[str, Any], max_len: int = 200) -> dict[str, Any]:
    """Truncate long tool input values for storage."""
    truncated = {}
    for key, value in tool_input.items():
        if isinstance(value, str) and len(value) > max_len:
            truncated[key] = value[:max_len] + "..."
        else:
            truncated[key] = value
    return truncated
