"""Rich Terminal UI for Claude Swarm — htop-style agent dashboard."""

from __future__ import annotations

import time
from typing import Any

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .types import (
    AgentStatus,
    FileConflict,
    SwarmAgent,
    SwarmPlan,
    TaskStatus,
)

# Status emoji/indicator mapping
TASK_STATUS_STYLE = {
    TaskStatus.PENDING: ("dim", "..."),
    TaskStatus.BLOCKED: ("yellow", "BLK"),
    TaskStatus.RUNNING: ("green bold", "RUN"),
    TaskStatus.COMPLETED: ("green", "OK "),
    TaskStatus.FAILED: ("red bold", "ERR"),
    TaskStatus.CANCELLED: ("dim", "CXL"),
}

AGENT_STATUS_STYLE = {
    AgentStatus.IDLE: ("dim", "idle"),
    AgentStatus.WORKING: ("green bold", "working"),
    AgentStatus.BLOCKED: ("yellow", "blocked"),
    AgentStatus.COMPLETED: ("green", "done"),
    AgentStatus.FAILED: ("red bold", "failed"),
}


class SwarmUI:
    """Rich terminal UI for displaying swarm progress."""

    def __init__(self) -> None:
        self.console = Console()
        self._live: Live | None = None
        self._start_time: float = 0.0

    def print_plan(self, plan: SwarmPlan) -> None:
        """Display the decomposed plan before execution."""
        self.console.print()
        self.console.print(
            Panel(
                f"[bold]{plan.original_prompt}[/bold]",
                title="[bold blue]Claude Swarm[/bold blue]",
                subtitle=f"{plan.task_count} tasks | model: {plan.model_used}",
            )
        )

        # Task dependency table
        table = Table(title="Task Plan", show_lines=True)
        table.add_column("ID", style="cyan", width=10)
        table.add_column("Type", style="magenta", width=12)
        table.add_column("Description", style="white")
        table.add_column("Depends On", style="yellow", width=20)
        table.add_column("Files", style="dim", width=30)

        for task in plan.tasks:
            deps = ", ".join(task.dependencies) if task.dependencies else "-"
            files = ", ".join(task.files_to_modify[:3]) if task.files_to_modify else "-"
            if len(task.files_to_modify) > 3:
                files += f" +{len(task.files_to_modify) - 3}"
            table.add_row(task.id, task.agent_type, task.description, deps, files)

        self.console.print(table)

        # Parallel groups visualization
        groups = plan.parallel_groups
        self.console.print()
        self.console.print("[bold]Execution Order:[/bold]")
        for i, group in enumerate(groups):
            prefix = "  " if i > 0 else ""
            tasks_str = " | ".join(f"[cyan]{tid}[/cyan]" for tid in group)
            self.console.print(f"{prefix}Wave {i + 1}: [{tasks_str}]")

        self.console.print()

    def create_dashboard(
        self,
        plan: SwarmPlan,
        agents: dict[str, SwarmAgent],
        total_cost: float,
        conflicts: list[FileConflict],
    ) -> Layout:
        """Create the live dashboard layout."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )

        # Header
        elapsed = time.monotonic() - self._start_time if self._start_time else 0
        completed = sum(1 for t in plan.tasks if t.status == TaskStatus.COMPLETED)
        running = sum(1 for t in plan.tasks if t.status == TaskStatus.RUNNING)
        failed = sum(1 for t in plan.tasks if t.status == TaskStatus.FAILED)

        header_text = Text()
        header_text.append("Claude Swarm", style="bold blue")
        header_text.append(f"  |  Tasks: {completed}/{plan.task_count} done")
        header_text.append(f"  |  Running: {running}")
        if failed:
            header_text.append(f"  |  Failed: {failed}", style="red")
        header_text.append(f"  |  Cost: ${total_cost:.4f}")
        header_text.append(f"  |  Time: {elapsed:.0f}s")

        layout["header"].update(Panel(header_text))

        # Body: split into tasks and agents
        layout["body"].split_row(
            Layout(name="tasks", ratio=3),
            Layout(name="agents", ratio=2),
        )

        # Tasks table
        task_table = Table(title="Tasks", show_lines=False, expand=True)
        task_table.add_column("ID", style="cyan", width=10)
        task_table.add_column("Status", width=5)
        task_table.add_column("Type", style="magenta", width=10)
        task_table.add_column("Description")
        task_table.add_column("Cost", justify="right", width=8)

        for task in plan.tasks:
            style, indicator = TASK_STATUS_STYLE[task.status]
            status_text = Text(indicator, style=style)
            cost_str = f"${task.cost_usd:.3f}" if task.cost_usd > 0 else "-"
            task_table.add_row(
                task.id, status_text, task.agent_type, task.description[:50], cost_str
            )

        layout["tasks"].update(Panel(task_table, title="[bold]Tasks[/bold]"))

        # Agents table
        agent_table = Table(title="Agents", show_lines=False, expand=True)
        agent_table.add_column("Agent", style="cyan")
        agent_table.add_column("Status", width=8)
        agent_table.add_column("Tool", width=15)
        agent_table.add_column("Turns", justify="right", width=6)
        agent_table.add_column("Cost", justify="right", width=8)

        for agent in agents.values():
            style, label = AGENT_STATUS_STYLE[agent.status]
            status_text = Text(label, style=style)
            tool = agent.current_tool or "-"
            agent_table.add_row(
                agent.name,
                status_text,
                tool,
                str(agent.turns),
                f"${agent.cost_usd:.3f}",
            )

        layout["agents"].update(Panel(agent_table, title="[bold]Agents[/bold]"))

        # Footer: conflicts
        if conflicts:
            unresolved = [c for c in conflicts if not c.resolved]
            if unresolved:
                conflict_text = Text("FILE CONFLICTS: ", style="red bold")
                for c in unresolved[:3]:
                    conflict_text.append(f"{c.file_path} ", style="yellow")
                layout["footer"].update(Panel(conflict_text))
            else:
                layout["footer"].update(Panel(Text("No active conflicts", style="green")))
        else:
            layout["footer"].update(Panel(Text("No file conflicts detected", style="green")))

        return layout

    def start_live(self) -> Live:
        """Start the live display."""
        self._start_time = time.monotonic()
        self._live = Live(console=self.console, refresh_per_second=4)
        self._live.start()
        return self._live

    def stop_live(self) -> None:
        """Stop the live display."""
        if self._live:
            self._live.stop()
            self._live = None

    def print_quality_report(self, report: Any) -> None:
        """Print the Opus quality gate report."""
        # Score color based on value
        score = report.overall_score
        if score >= 8:
            score_style = "bold green"
        elif score >= 5:
            score_style = "bold yellow"
        else:
            score_style = "bold red"

        verdict_style = {
            "pass": "bold green",
            "needs_revision": "bold yellow",
            "fail": "bold red",
        }.get(report.verdict, "bold white")

        self.console.print()
        self.console.print(
            Panel(
                f"[{score_style}]Score: {score}/10[/{score_style}]  |  "
                f"[{verdict_style}]Verdict: {report.verdict.upper()}[/{verdict_style}]  |  "
                f"[dim]Review cost: ${report.review_cost_usd:.4f}[/dim]\n\n"
                f"{report.summary}",
                title="[bold magenta]Opus 4.6 Quality Gate[/bold magenta]",
            )
        )

        if report.integration_issues:
            self.console.print("[yellow]Integration Issues:[/yellow]")
            for issue in report.integration_issues:
                self.console.print(f"  [yellow]![/yellow] {issue}")

        if report.missing_items:
            self.console.print("[red]Missing Items:[/red]")
            for item in report.missing_items:
                self.console.print(f"  [red]-[/red] {item}")

        if report.task_reviews:
            review_table = Table(title="Per-Task Reviews", show_lines=True)
            review_table.add_column("Task", style="cyan", width=10)
            review_table.add_column("Score", width=6, justify="center")
            review_table.add_column("Issues")
            review_table.add_column("Suggestions")

            for tr in report.task_reviews:
                issues = "; ".join(tr.issues[:2]) if tr.issues else "-"
                suggestions = "; ".join(tr.suggestions[:2]) if tr.suggestions else "-"
                review_table.add_row(
                    tr.task_id,
                    str(tr.score),
                    issues[:60],
                    suggestions[:60],
                )

            self.console.print(review_table)

    def print_results(self, result: Any) -> None:
        """Print final results summary."""
        self.console.print()

        # Summary panel
        completed = len(result.completed_tasks)
        failed = len(result.failed_tasks)
        cancelled = sum(
            1 for t in result.plan.tasks if t.status == TaskStatus.CANCELLED
        )
        total = result.plan.task_count
        success_rate = (completed / total * 100) if total > 0 else 0

        summary = Table(title="Swarm Results", show_lines=True)
        summary.add_column("Metric", style="bold")
        summary.add_column("Value", justify="right")

        summary.add_row("Tasks Completed", f"[green]{completed}[/green]")
        summary.add_row("Tasks Failed", f"[red]{failed}[/red]" if failed else "0")
        if cancelled:
            summary.add_row("Tasks Cancelled", f"[yellow]{cancelled}[/yellow]")
        summary.add_row("Success Rate", f"{success_rate:.0f}%")
        summary.add_row("Total Cost", f"${result.total_cost_usd:.4f}")
        summary.add_row("Duration", f"{result.total_duration_ms / 1000:.1f}s")
        summary.add_row("Agents Used", str(result.agents_used))
        summary.add_row("File Conflicts", str(len(result.conflicts)))

        self.console.print(summary)

        if result.failed_tasks:
            self.console.print()
            self.console.print("[bold red]Failed Tasks:[/bold red]")
            for task in result.failed_tasks:
                self.console.print(f"  [red]{task.id}[/red]: {task.error}")

        self.console.print()
