"""CLI entry point for Claude Swarm."""

from __future__ import annotations

import asyncio
import os
import sys

import click

from . import __version__


@click.command()
@click.argument("task", required=False)
@click.option("--cwd", "-d", default=".", help="Working directory for the project")
@click.option("--max-agents", "-n", default=4, help="Maximum concurrent agents (default: 4)")
@click.option("--model", "-m", default="opus", help="Model for task decomposition (default: opus)")
@click.option("--dry-run", is_flag=True, help="Show plan without executing")
@click.option("--no-ui", is_flag=True, help="Disable rich terminal UI")
@click.option("--budget", "-b", default=5.0, help="Maximum total budget in USD (default: 5.0)")
@click.option("--version", "-v", is_flag=True, help="Show version")
def main(
    task: str | None,
    cwd: str,
    max_agents: int,
    model: str,
    dry_run: bool,
    no_ui: bool,
    budget: float,
    version: bool,
) -> None:
    """Claude Swarm — Multi-agent orchestration for Claude Code.

    Decompose complex tasks into parallel subtasks, coordinate agents,
    and visualize everything in a rich terminal UI.

    Example:
        claude-swarm "Refactor auth module from Express to Next.js API routes"
    """
    if version:
        click.echo(f"claude-swarm v{__version__}")
        return

    if not task:
        click.echo("Usage: claude-swarm <task description>")
        click.echo("       claude-swarm --help for options")
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
        )
    )


async def _run_swarm(
    task: str,
    cwd: str,
    max_agents: int,
    model: str,
    dry_run: bool,
    no_ui: bool,
    budget: float,
) -> None:
    """Main async entry point for the swarm."""
    from .decomposer import decompose_task
    from .orchestrator import SwarmOrchestrator
    from .ui import SwarmUI

    ui = SwarmUI()

    # Phase 1: Decompose
    ui.console.print("[bold blue]Phase 1:[/bold blue] Decomposing task with Opus 4.6...")
    plan = await decompose_task(prompt=task, cwd=cwd, model=model)
    ui.print_plan(plan)

    if dry_run:
        ui.console.print("[yellow]Dry run — not executing tasks[/yellow]")
        return

    # Confirm before executing
    ui.console.print(
        f"\n[bold]Ready to execute {plan.task_count} tasks "
        f"with up to {max_agents} concurrent agents.[/bold]"
    )
    ui.console.print(f"[dim]Budget limit: ${budget:.2f}[/dim]")

    # Phase 2: Execute
    ui.console.print("\n[bold blue]Phase 2:[/bold blue] Executing swarm...")

    orchestrator = SwarmOrchestrator(
        plan=plan,
        cwd=cwd,
        max_concurrent=max_agents,
    )

    if no_ui:
        # Simple text output mode
        result = await orchestrator.run()
    else:
        # Rich live dashboard
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


if __name__ == "__main__":
    main()
