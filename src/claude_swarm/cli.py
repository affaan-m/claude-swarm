"""CLI entry point for Claude Swarm."""

from __future__ import annotations

import asyncio
import json
import os
import sys

import click

from . import __version__


@click.group(invoke_without_command=True)
@click.argument("task", required=False)
@click.option("--cwd", "-d", default=".", help="Working directory for the project")
@click.option("--max-agents", "-n", default=4, help="Maximum concurrent agents (default: 4)")
@click.option("--model", "-m", default="opus", help="Model for task decomposition (default: opus)")
@click.option("--dry-run", is_flag=True, help="Show plan without executing")
@click.option("--no-ui", is_flag=True, help="Disable rich terminal UI")
@click.option("--budget", "-b", default=5.0, help="Maximum total budget in USD (default: 5.0)")
@click.option("--config", "-c", default=None, help="Path to swarm.yaml config file")
@click.option("--version", "-v", is_flag=True, help="Show version")
@click.pass_context
def main(
    ctx: click.Context,
    task: str | None,
    cwd: str,
    max_agents: int,
    model: str,
    dry_run: bool,
    no_ui: bool,
    budget: float,
    config: str | None,
    version: bool,
) -> None:
    """Claude Swarm — Multi-agent orchestration for Claude Code.

    Decompose complex tasks into parallel subtasks, coordinate agents,
    and visualize everything in a rich terminal UI.

    Example:
        claude-swarm "Refactor auth module from Express to Next.js API routes"
        claude-swarm --dry-run "Add user authentication"
        claude-swarm sessions  # List past sessions
    """
    # If a subcommand was invoked, let it handle things
    if ctx.invoked_subcommand is not None:
        return

    if version:
        click.echo(f"claude-swarm v{__version__}")
        return

    if not task:
        click.echo("Usage: claude-swarm <task description>")
        click.echo("       claude-swarm --help for options")
        click.echo("       claude-swarm sessions  # List past sessions")
        return

    if not os.environ.get("ANTHROPIC_API_KEY"):
        click.echo("Error: ANTHROPIC_API_KEY environment variable not set.")
        click.echo("Get your key at: https://console.anthropic.com/settings/keys")
        sys.exit(1)

    resolved_cwd = os.path.abspath(cwd)

    asyncio.run(
        _run_swarm(
            task=task,
            cwd=resolved_cwd,
            max_agents=max_agents,
            model=model,
            dry_run=dry_run,
            no_ui=no_ui,
            budget=budget,
            config_path=config,
        )
    )


@main.command()
@click.option("--limit", "-l", default=20, help="Number of sessions to show")
def sessions(limit: int) -> None:
    """List past swarm sessions."""
    from .session import list_sessions

    sessions_list = list_sessions(limit=limit)
    if not sessions_list:
        click.echo("No sessions found. Run a swarm first!")
        return

    click.echo(f"\n{'ID':<20} {'Prompt':<50} {'Duration':<10} {'Cost':<10}")
    click.echo("-" * 90)
    for s in sessions_list:
        duration = f"{s.get('duration_s', 0):.1f}s" if s.get("duration_s") else "-"
        result = s.get("result", {})
        cost = f"${result.get('total_cost_usd', 0):.4f}" if isinstance(result, dict) else "-"
        click.echo(f"{s['session_id']:<20} {s['prompt']:<50} {duration:<10} {cost:<10}")
    click.echo()


@main.command()
@click.argument("session_id")
def replay(session_id: str) -> None:
    """Replay a past swarm session's events."""
    from rich.console import Console

    from .session import load_session_events

    console = Console()
    events = load_session_events(session_id)
    if not events:
        console.print(f"[red]Session not found: {session_id}[/red]")
        return

    console.print(f"\n[bold blue]Replaying session: {session_id}[/bold blue]\n")

    for event in events:
        ts = f"[dim]{event['timestamp']:>8.2f}s[/dim]"
        etype = event["event_type"]
        agent = event.get("agent_id", "")
        task = event.get("task_id", "")
        data = event.get("data", {})

        if etype == "session_started":
            console.print(f"{ts} [bold green]SESSION START[/bold green] {data.get('prompt', '')[:60]}")
        elif etype == "plan_created":
            task_count = len(data.get("tasks", []))
            console.print(f"{ts} [bold blue]PLAN CREATED[/bold blue] {task_count} tasks")
        elif etype == "agent_started":
            console.print(f"{ts} [green]AGENT START[/green]  {agent} -> {task} ({data.get('description', '')[:40]})")
        elif etype == "tool_use":
            tool = data.get("tool", "?")
            console.print(f"{ts} [cyan]TOOL USE[/cyan]     {agent}: {tool}")
        elif etype == "agent_completed":
            cost = data.get("cost_usd", 0)
            dur = data.get("duration_ms", 0)
            console.print(f"{ts} [green]AGENT DONE[/green]   {agent} (${cost:.4f}, {dur}ms)")
        elif etype == "agent_failed":
            console.print(f"{ts} [red]AGENT FAIL[/red]   {agent}: {data.get('error', '')[:60]}")
        elif etype == "file_conflict":
            console.print(f"{ts} [yellow]CONFLICT[/yellow]     {data.get('file_path', '')} ({data.get('agent_ids', [])})")
        elif etype == "session_completed":
            console.print(f"{ts} [bold green]SESSION END[/bold green]   Total cost: ${data.get('total_cost_usd', 0):.4f}")

    console.print()


async def _run_swarm(
    task: str,
    cwd: str,
    max_agents: int,
    model: str,
    dry_run: bool,
    no_ui: bool,
    budget: float,
    config_path: str | None = None,
) -> None:
    """Main async entry point for the swarm."""
    from .config import SwarmConfig, find_config
    from .decomposer import decompose_task
    from .orchestrator import SwarmOrchestrator
    from .session import SessionRecorder
    from .ui import SwarmUI

    ui = SwarmUI()

    # Load config if available
    swarm_config = None
    if config_path:
        swarm_config = SwarmConfig.from_file(config_path)
        ui.console.print(f"[dim]Loaded config: {config_path}[/dim]")
    else:
        swarm_config = find_config(cwd)
        if swarm_config:
            ui.console.print(f"[dim]Auto-detected swarm config: {swarm_config.name}[/dim]")

    # Apply config overrides
    if swarm_config:
        max_agents = swarm_config.max_concurrent
        budget = swarm_config.budget_usd
        model = swarm_config.model

    # Initialize session recorder
    recorder = SessionRecorder()
    recorder.start(prompt=task, cwd=cwd)

    # Phase 1: Decompose
    ui.console.print("[bold blue]Phase 1:[/bold blue] Decomposing task with Opus 4.6...")
    plan = await decompose_task(prompt=task, cwd=cwd, model=model)
    ui.print_plan(plan)

    # Record the plan
    recorder.record_plan({
        "tasks": [
            {"id": t.id, "description": t.description, "agent_type": t.agent_type, "dependencies": t.dependencies}
            for t in plan.tasks
        ]
    })

    if dry_run:
        ui.console.print("[yellow]Dry run — not executing tasks[/yellow]")
        session_path = recorder.finish({"dry_run": True})
        ui.console.print(f"[dim]Session saved: {session_path}[/dim]")
        return

    # Confirm before executing
    ui.console.print(
        f"\n[bold]Ready to execute {plan.task_count} tasks "
        f"with up to {max_agents} concurrent agents.[/bold]"
    )
    ui.console.print(f"[dim]Budget limit: ${budget:.2f} | Session: {recorder.session_id}[/dim]")

    # Phase 2: Execute
    ui.console.print("\n[bold blue]Phase 2:[/bold blue] Executing swarm...")

    orchestrator = SwarmOrchestrator(
        plan=plan,
        cwd=cwd,
        max_concurrent=max_agents,
        recorder=recorder,
    )

    if no_ui:
        result = await orchestrator.run()
    else:
        live = ui.start_live()
        try:

            def update_dashboard() -> None:
                dashboard = ui.create_dashboard(
                    plan=plan,
                    agents=orchestrator.agents,
                    total_cost=orchestrator.total_cost,
                    conflicts=orchestrator.conflicts,
                )
                live.update(dashboard)

            orchestrator.on_update = update_dashboard
            result = await orchestrator.run()
        finally:
            ui.stop_live()

    # Phase 3: Results
    ui.console.print("\n[bold blue]Phase 3:[/bold blue] Results")
    ui.print_results(result)

    # Save session
    session_path = recorder.finish({
        "completed": len(result.completed_tasks),
        "failed": len(result.failed_tasks),
        "total_cost_usd": result.total_cost_usd,
        "total_duration_ms": result.total_duration_ms,
        "agents_used": result.agents_used,
        "conflicts": len(result.conflicts),
    })
    ui.console.print(f"[dim]Session saved: {session_path}[/dim]")
    ui.console.print(f"[dim]Replay with: claude-swarm replay {recorder.session_id}[/dim]")


if __name__ == "__main__":
    main()
