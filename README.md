# Claude Swarm

**Multi-agent orchestration for Claude Code** — decompose complex tasks into parallel subtasks, coordinate agents in real-time, and visualize everything in a rich terminal UI.

Built for the [Claude Code Hackathon](https://cerebralvalley.ai/hackathons/claude-code-hackathon-aaHFuycPfjQa5dNaxZpU) (Feb 10-16, 2026).

## What it does

1. **Task Decomposition** — Describe a complex task, Opus 4.6 breaks it into a dependency graph of subtasks
2. **Parallel Agent Spawning** — Independent subtasks run simultaneously via Claude Agent SDK
3. **Real-time Coordination** — Agents communicate through a shared task board with conflict detection
4. **Rich Terminal UI** — `htop`-style dashboard showing agent progress, costs, and file conflicts
5. **Smart Model Selection** — Opus for orchestration/planning, Haiku for worker agents

## Quick Start

```bash
# Install
pip install claude-swarm

# Or from source
git clone https://github.com/affaan-m/claude-swarm
cd claude-swarm
pip install -e .

# Run
claude-swarm "Refactor auth module from Express middleware to Next.js API routes"
```

## Architecture

```
┌─────────────────────────────────────┐
│           Claude Swarm CLI          │
│  ┌───────────────────────────────┐  │
│  │      Task Decomposer         │  │
│  │    (Opus 4.6 planner)        │  │
│  └──────────┬────────────────────┘  │
│             │ dependency graph       │
│  ┌──────────▼────────────────────┐  │
│  │     Swarm Orchestrator        │  │
│  │  ┌─────┐ ┌─────┐ ┌─────┐    │  │
│  │  │Agent│ │Agent│ │Agent│    │  │
│  │  │  1  │ │  2  │ │  3  │    │  │
│  │  └──┬──┘ └──┬──┘ └──┬──┘    │  │
│  │     │       │       │        │  │
│  │  ┌──▼───────▼───────▼──┐    │  │
│  │  │   Shared Task Board  │    │  │
│  │  │  (conflict detection)│    │  │
│  │  └─────────────────────┘    │  │
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │
│  │        Rich Terminal UI       │  │
│  │  agents | tasks | files | $   │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

## Features

- **Dependency-aware scheduling** — Tasks only start when their dependencies complete
- **File conflict detection** — Warns when multiple agents edit the same file
- **Cost tracking** — Real-time per-agent and total cost monitoring
- **Progress visualization** — See which agents are working on what, live
- **Graceful interrupts** — Ctrl+C cleanly shuts down all agents
- **Session replay** — Review what each agent did after completion

## Tech Stack

- **Python 3.12+** with `anyio` for async
- **claude-agent-sdk** for Claude Code subprocess control
- **Rich** / **Textual** for terminal UI
- **NetworkX** for dependency graph management

## License

MIT
