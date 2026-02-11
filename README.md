# Claude Swarm

[![PyPI](https://img.shields.io/pypi/v/claude-swarm)](https://pypi.org/project/claude-swarm/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-30%20passing-brightgreen.svg)]()

**Multi-agent orchestration for Claude Code** — decompose complex tasks into parallel subtasks, coordinate agents in real-time, and visualize everything in a rich terminal UI.

Built with the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) for the [Claude Code Hackathon](https://cerebralvalley.ai/hackathons/claude-code-hackathon-aaHFuycPfjQa5dNaxZpU) (Feb 10-16, 2026).

## How It Works

```
You: "Refactor auth module from Express middleware to Next.js API routes"

Claude Swarm:
  Phase 1: Opus 4.6 decomposes task into dependency graph
  Phase 2: Parallel agents execute subtasks with live dashboard
  Phase 3: Results summary with costs and session replay
```

1. **Task Decomposition** — Describe a complex task. Opus 4.6 analyzes your codebase and breaks it into a dependency graph of subtasks
2. **Parallel Agent Spawning** — Independent subtasks run simultaneously via Claude Agent SDK. Dependent tasks wait.
3. **Real-time Coordination** — File conflict detection prevents agents from stepping on each other. Budget enforcement stops runaway costs.
4. **Rich Terminal UI** — `htop`-style dashboard showing agent progress, tool usage, costs, and file conflicts in real-time
5. **Session Replay** — Every swarm execution is recorded. Replay any session to review what each agent did.

## Quick Start

```bash
# Install from PyPI
pip install claude-swarm

# Or from source
git clone https://github.com/affaan-m/claude-swarm
cd claude-swarm
pip install -e .

# Set your API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Run a swarm
claude-swarm "Refactor auth module from Express middleware to Next.js API routes"

# Dry run (shows plan without executing)
claude-swarm --dry-run "Add user authentication with JWT"

# Custom budget and agent count
claude-swarm --budget 3.0 --max-agents 6 "Build a REST API for user management"
```

## Architecture

```
┌───────────────────────────────────────────────┐
│              Claude Swarm CLI                  │
│                                                │
│  Phase 1: Decompose                            │
│  ┌─────────────────────────────────────────┐   │
│  │  Opus 4.6 Task Decomposer              │   │
│  │  "Add auth" -> [create routes,          │   │
│  │   add middleware, write tests, review]   │   │
│  └──────────────┬──────────────────────────┘   │
│                 │ dependency graph              │
│  Phase 2: Execute                              │
│  ┌──────────────▼──────────────────────────┐   │
│  │       Swarm Orchestrator                │   │
│  │                                         │   │
│  │  Wave 1: ┌────────┐ ┌────────┐         │   │
│  │          │ Agent 1 │ │ Agent 2 │  (parallel)│
│  │          │ coder   │ │ coder   │         │  │
│  │          └────┬────┘ └────┬────┘         │  │
│  │  Wave 2:      └─────┬─────┘              │  │
│  │               ┌─────▼─────┐              │  │
│  │               │  Agent 3  │  (depends)   │  │
│  │               │  tester   │              │  │
│  │               └─────┬─────┘              │  │
│  │  Wave 3:      ┌─────▼─────┐              │  │
│  │               │  Agent 4  │  (depends)   │  │
│  │               │  reviewer │              │  │
│  │               └───────────┘              │  │
│  │                                          │  │
│  │  File Locks: {auth.ts -> Agent 1}       │  │
│  │  Budget: $0.23 / $5.00                  │  │
│  └──────────────────────────────────────────┘  │
│                                                │
│  Phase 3: Results                              │
│  ┌──────────────────────────────────────────┐  │
│  │  4/4 tasks completed | $0.45 | 32s      │  │
│  │  Session: swarm-a1b2c3d4                 │  │
│  └──────────────────────────────────────────┘  │
└────────────────────────────────────────────────┘
```

## Features

| Feature | Description |
|---------|-------------|
| **Dependency-aware scheduling** | Tasks only start when their dependencies complete |
| **File conflict detection** | Pessimistic file locking prevents agents from editing the same file simultaneously |
| **Budget enforcement** | Hard cost limit — cancels remaining tasks when budget is exceeded |
| **Cost tracking** | Real-time per-agent and total cost monitoring |
| **Smart model selection** | Opus 4.6 for planning/decomposition, Haiku for worker agents (3x cheaper) |
| **Session recording** | Every swarm execution recorded as JSONL events |
| **Session replay** | `claude-swarm replay <id>` to review what each agent did |
| **YAML config** | Declarative swarm topologies via `swarm.yaml` |
| **Progress visualization** | Live htop-style dashboard with Rich |

## CLI Reference

```bash
# Main command
claude-swarm [OPTIONS] TASK

Options:
  -d, --cwd TEXT            Working directory (default: .)
  -n, --max-agents INTEGER  Max concurrent agents (default: 4)
  -m, --model TEXT          Decomposition model (default: opus)
  -b, --budget FLOAT        Max budget in USD (default: 5.0)
  -c, --config PATH         Path to swarm.yaml
  --dry-run                 Show plan without executing
  --no-ui                   Disable rich terminal UI
  -v, --version             Show version

# Subcommands
claude-swarm sessions              # List past sessions
claude-swarm replay <session-id>   # Replay a session's events
```

## YAML Configuration

Create `swarm.yaml` in your project root to define custom agent types:

```yaml
swarm:
  name: full-stack-review
  max_concurrent: 4
  budget_usd: 5.0
  model: opus

agents:
  security-reviewer:
    description: Reviews code for OWASP vulnerabilities
    model: opus
    tools: [Read, Grep, Glob]
    prompt: |
      Analyze the code for SQL injection, XSS, CSRF...

  tester:
    description: Writes and runs tests
    model: haiku
    tools: [Read, Write, Edit, Bash]
    prompt: |
      Write comprehensive tests. Ensure 80% coverage...

connections:
  - from: coder
    to: security-reviewer
  - from: coder
    to: tester
  - from: [security-reviewer, tester]
    to: reviewer
```

Claude Swarm auto-detects `swarm.yaml` or `.claude/swarm.yaml` in your project.

## How Opus 4.6 Is Used

Claude Swarm demonstrates strategic model selection:

- **Opus 4.6** handles task decomposition — the hardest reasoning task. It analyzes your codebase, understands the architecture, identifies dependencies between subtasks, and produces a parallelizable execution plan. This is where deep reasoning matters most.
- **Haiku** handles worker agent execution — the parallelizable work. Each agent follows focused instructions from the plan. Using Haiku here is 3x cheaper while maintaining 90% of Sonnet's capability.

This mirrors real engineering team structure: a senior architect designs the plan, junior engineers execute the pieces in parallel.

## Tech Stack

- **Python 3.11+** with `anyio` for structured async concurrency
- **claude-agent-sdk** (v0.1.35+) for Claude Code subprocess control
- **Rich** for terminal UI (Live dashboard with panels and tables)
- **Click** for CLI framework
- **Pydantic** for data validation
- **NetworkX** for dependency graph topological sorting

## Development

```bash
# Clone and install
git clone https://github.com/affaan-m/claude-swarm
cd claude-swarm
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint
ruff check src/ tests/
```

## Project Structure

```
src/claude_swarm/
  cli.py          CLI entry point (Click group + subcommands)
  types.py        Core dataclasses (SwarmTask, SwarmPlan, etc.)
  decomposer.py   Opus 4.6 task decomposition
  orchestrator.py  Parallel execution with file locks + budget
  config.py       YAML swarm topology configuration
  session.py      JSONL event recording and replay
  ui.py           Rich terminal dashboard
```

## License

MIT — [Affaan Mustafa](https://x.com/affaanmustafa)

## Acknowledgments

- [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) for the subprocess control layer
- [Everything Claude Code](https://github.com/affaan-m/everything-claude-code) for agent patterns and inspiration
- Built for the [Cerebral Valley x Anthropic Claude Code Hackathon](https://cerebralvalley.ai/hackathons/claude-code-hackathon-aaHFuycPfjQa5dNaxZpU)
