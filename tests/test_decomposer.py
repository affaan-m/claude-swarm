"""Tests for the task decomposer."""

from claude_swarm.decomposer import _extract_json_block, _parse_decomposition


def test_extract_json_block_fenced() -> None:
    text = '''Here is the plan:

```json
{"tasks": [{"id": "task-1", "description": "Do something"}]}
```

Done.'''
    result = _extract_json_block(text)
    assert result is not None
    assert '"task-1"' in result


def test_extract_json_block_raw() -> None:
    text = 'The decomposition is {"tasks": [{"id": "t1"}]} and that is all.'
    result = _extract_json_block(text)
    assert result is not None
    assert '"t1"' in result


def test_extract_json_block_none() -> None:
    text = "No JSON here at all"
    result = _extract_json_block(text)
    assert result is None


def test_parse_decomposition_valid() -> None:
    text = '''```json
{
  "tasks": [
    {
      "id": "task-1",
      "description": "Implement auth",
      "agent_type": "coder",
      "dependencies": [],
      "files_to_modify": ["src/auth.ts"],
      "tools": ["Read", "Write"],
      "prompt": "Implement authentication"
    },
    {
      "id": "task-2",
      "description": "Test auth",
      "agent_type": "tester",
      "dependencies": ["task-1"],
      "files_to_modify": ["tests/auth.test.ts"],
      "tools": ["Read", "Write", "Bash"],
      "prompt": "Write tests for auth"
    }
  ]
}
```'''
    tasks = _parse_decomposition(text)
    assert len(tasks) == 2
    assert tasks[0].id == "task-1"
    assert tasks[0].agent_type == "coder"
    assert tasks[1].dependencies == ["task-1"]


def test_parse_decomposition_fallback() -> None:
    text = "This is not valid JSON at all, just plain text instructions."
    tasks = _parse_decomposition(text)
    # Should create a single fallback task
    assert len(tasks) == 1
    assert "fallback" in tasks[0].description.lower() or tasks[0].agent_type == "coder"
