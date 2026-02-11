# Claude Swarm

Multi-agent orchestration for Claude Code built on the Agent SDK.

## Architecture

```
src/claude_swarm/
  cli.py          - Click CLI entry point (main group + sessions/replay subcommands)
  types.py        - Core dataclasses: SwarmTask, SwarmPlan, SwarmAgent, FileConflict, SwarmResult
  decomposer.py   - Opus 4.6-powered task decomposition (prompt -> dependency graph JSON)
  orchestrator.py - Parallel agent execution with anyio task groups, file locks, cost tracking
  config.py       - YAML config loading for custom agent types and swarm topologies
  session.py      - Session recording (JSONL events) and replay for post-mortem review
  ui.py           - Rich terminal UI with htop-style agent/task dashboard
```

## Key Patterns

- **Opus for planning, Haiku for workers** — Decomposer uses Opus, worker agents use Haiku
- **File-level conflict detection** — Pessimistic locking via `_file_locks` map
- **Topological sort for parallel groups** — `SwarmPlan.parallel_groups` property
- **Session recording** — Every event saved to `~/.claude-swarm/sessions/` as JSONL

## Running Tests

```bash
python -m pytest tests/ -v -p no:pytest_ethereum -p no:web3
```

## Style

- Python 3.11+, strict typing, dataclasses over dicts
- Ruff for formatting/linting
- No mutation — create new objects
