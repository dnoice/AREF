"""
AREF CLI — Rich interactive command-line interface.

Provides a polished terminal UI using Rich for:
  - Platform status dashboard
  - Pillar inspection and management
  - Chaos experiment control
  - Maturity assessment
  - Incident timeline viewing

Uses Click for command structure and Rich for advanced rendering.
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import Any

import click
import httpx
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree
from rich.columns import Columns
from rich.progress import Progress, BarColumn, TextColumn, SpinnerColumn
from rich.style import Style
from rich.box import ROUNDED, HEAVY, DOUBLE, MINIMAL

console = Console()

API_BASE = "http://localhost:8080"

# Pillar color mapping — matches dashboard CSS
PILLAR_STYLES = {
    "detection": Style(color="bright_blue"),
    "absorption": Style(color="bright_magenta"),
    "adaptation": Style(color="yellow"),
    "recovery": Style(color="bright_green"),
    "evolution": Style(color="bright_red"),
}

SEVERITY_STYLES = {
    "healthy": Style(color="bright_green"),
    "warning": Style(color="yellow"),
    "critical": Style(color="bright_red"),
    "emergency": Style(color="red", bold=True),
}

MATURITY_NAMES = {1: "Reactive", 2: "Managed", 3: "Defined", 4: "Measured", 5: "Optimizing"}


def fetch(endpoint: str) -> dict[str, Any] | None:
    try:
        resp = httpx.get(f"{API_BASE}{endpoint}", timeout=5.0)
        return resp.json()
    except Exception:
        return None


def post(endpoint: str, body: dict | None = None) -> dict[str, Any] | None:
    try:
        resp = httpx.post(f"{API_BASE}{endpoint}", json=body or {}, timeout=10.0)
        return resp.json()
    except Exception:
        return None


def render_header() -> Panel:
    header = Text()
    header.append("  AREF  ", style="bold white on blue")
    header.append("  Adaptive Resilience Engineering Framework  ", style="dim")
    header.append("v2.0.0", style="dim cyan")
    return Panel(header, box=MINIMAL, style="dim")


def render_crs_bar(score: float, max_score: float = 5.0) -> Text:
    """Render a colored CRS progress bar in the terminal."""
    pct = min(score / max_score, 1.0)
    bar_width = 30
    filled = int(pct * bar_width)
    empty = bar_width - filled

    if score < 2.0:
        color = "red"
    elif score < 3.5:
        color = "yellow"
    else:
        color = "green"

    bar = Text()
    bar.append("[", style="dim")
    bar.append("=" * filled, style=f"bold {color}")
    bar.append("-" * empty, style="dim")
    bar.append("]", style="dim")
    bar.append(f" {score:.2f}/{max_score:.1f}", style=f"bold {color}")
    return bar


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------

@click.group()
@click.option("--api", default="http://localhost:8080", help="AREF API base URL")
def cli(api: str) -> None:
    """AREF -- Adaptive Resilience Engineering Framework CLI"""
    global API_BASE
    API_BASE = api


@cli.command()
def status():
    """Show full AREF platform status."""
    console.print(render_header())

    with console.status("[bold cyan]Fetching platform status...", spinner="dots"):
        data = fetch("/api/aref/status")
        services = fetch("/api/aref/services")
        alerts = fetch("/api/aref/alerts")

    if not data:
        console.print("[bold red]Could not connect to AREF platform.[/]")
        console.print(f"[dim]Ensure the dashboard is running at {API_BASE}[/]")
        return

    # CRS Score
    crs = data.get("crs", 0)
    console.print()
    console.print(Panel(
        render_crs_bar(crs),
        title="[bold]Composite Resilience Score",
        subtitle=f"Profile: {data.get('risk_profile', 'balanced')}",
        box=ROUNDED,
    ))

    # Pillar table
    pillar_table = Table(
        title="Five Pillars", box=ROUNDED, show_header=True, header_style="bold",
        title_style="bold cyan",
    )
    pillar_table.add_column("Pillar", style="bold", width=14)
    pillar_table.add_column("Score", justify="center", width=8)
    pillar_table.add_column("Level", width=12)
    pillar_table.add_column("Maturity Bar", width=25)

    pillars = data.get("pillars", {})
    for name in ["detection", "absorption", "adaptation", "recovery", "evolution"]:
        score = pillars.get(name, 1.0)
        level = int(score)
        style = PILLAR_STYLES.get(name, Style())

        bar_text = render_crs_bar(score)
        level_name = MATURITY_NAMES.get(level, "Unknown")

        pillar_table.add_row(
            Text(name.capitalize(), style=style),
            Text(f"{score:.1f}", style=style),
            Text(f"L{level} {level_name}", style=style),
            bar_text,
        )

    console.print(pillar_table)

    # Services
    if services and services.get("services"):
        svc_table = Table(
            title="Service Health", box=ROUNDED, show_header=True,
            title_style="bold cyan",
        )
        svc_table.add_column("Service", style="bold", width=16)
        svc_table.add_column("Status", width=14)
        svc_table.add_column("Version", width=10)

        for name, info in services["services"].items():
            status_val = info.get("status", "unknown")
            if status_val == "healthy":
                status_text = Text("* HEALTHY", style="bold green")
            elif status_val == "unreachable":
                status_text = Text("* DOWN", style="bold red")
            else:
                status_text = Text(f"* {status_val.upper()}", style="yellow")
            svc_table.add_row(name, status_text, info.get("version", "-"))

        console.print(svc_table)

    # Alerts
    if alerts and alerts.get("alerts"):
        console.print(Panel(
            f"[bold red]{len(alerts['alerts'])} active alerts[/]",
            title="Alerts",
            box=ROUNDED,
        ))
    else:
        console.print(Panel(
            "[green]No active alerts[/]",
            title="Alerts",
            box=ROUNDED,
        ))

    # Chaos status
    if data.get("chaos_active"):
        console.print(Panel(
            "[bold red]CHAOS INJECTION ACTIVE[/]",
            box=HEAVY,
            style="red",
        ))


@cli.command()
def pillars():
    """Detailed view of all five AREF pillars."""
    for pillar in ["detection", "absorption", "adaptation", "recovery", "evolution"]:
        with console.status(f"Fetching {pillar}...", spinner="dots"):
            data = fetch(f"/api/aref/{pillar}")

        if data:
            tree = Tree(f"[bold {PILLAR_STYLES[pillar].color}]{pillar.upper()}[/]")
            _add_dict_to_tree(tree, data)
            console.print(Panel(tree, box=ROUNDED))
        else:
            console.print(f"[dim]Could not fetch {pillar} status[/]")


@cli.command()
def maturity():
    """Run maturity assessment and display results."""
    with console.status("[bold cyan]Running maturity assessment...", spinner="dots"):
        data = fetch("/api/aref/maturity")

    if not data:
        console.print("[red]Could not run assessment[/]")
        return

    console.print(render_header())
    console.print()

    # Assessment results
    table = Table(title="Maturity Assessment", box=DOUBLE, title_style="bold cyan")
    table.add_column("Pillar", style="bold", width=14)
    table.add_column("Level", justify="center", width=6)
    table.add_column("Name", width=14)
    table.add_column("Gaps", width=50)

    for pillar, assessment in data.get("assessments", {}).items():
        level = assessment.get("level", 1)
        level_name = MATURITY_NAMES.get(level, "Unknown")
        gaps = "; ".join(assessment.get("gaps", [])[:2]) or "None"
        style = PILLAR_STYLES.get(pillar, Style())
        table.add_row(
            Text(pillar.capitalize(), style=style),
            Text(f"L{level}", style=style),
            level_name,
            Text(gaps, style="dim"),
        )

    console.print(table)

    # CRS scores by profile
    crs_table = Table(title="CRS by Risk Profile", box=ROUNDED, title_style="bold cyan")
    crs_table.add_column("Profile", width=25)
    crs_table.add_column("CRS", justify="center", width=10)
    crs_table.add_column("Bar", width=30)

    for profile, score in data.get("crs_scores", {}).items():
        crs_table.add_row(
            profile.replace("_", " ").title(),
            f"{score:.3f}",
            render_crs_bar(score),
        )

    console.print(crs_table)

    console.print(f"\n[dim]Overall maturity level: L{data.get('overall_level', 1)}[/]")


@cli.command()
@click.argument("experiment", required=False)
def chaos(experiment: str | None):
    """Run a chaos experiment or list available experiments."""
    if not experiment:
        # List experiments
        console.print(render_header())
        console.print("\n[bold cyan]Available Chaos Experiments:[/]\n")

        experiments = [
            ("payment_provider_failure", "Payment provider outage", "absorption"),
            ("order_service_latency", "Order service latency spike", "detection"),
            ("inventory_degradation", "Inventory graceful degradation", "adaptation"),
            ("notification_overload", "Notification queue overflow", "adaptation"),
            ("cascading_failure", "Full cascading failure (all pillars)", "all"),
        ]

        table = Table(box=ROUNDED)
        table.add_column("Name", style="bold")
        table.add_column("Description")
        table.add_column("Tests", width=12)

        for name, desc, tests in experiments:
            table.add_row(name, desc, Text(tests, style="yellow"))

        console.print(table)
        console.print("\n[dim]Usage: aref chaos <experiment_name>[/]")
        return

    console.print(f"\n[bold red]Starting chaos experiment: {experiment}[/]")

    with console.status("[bold red]Injecting fault...", spinner="dots"):
        result = post("/api/aref/chaos/start", {"experiment": experiment})

    if result and result.get("status") == "started":
        console.print(f"[green]Experiment started: {result.get('injection', '')}[/]")
        console.print("[dim]Monitor the dashboard to observe AREF's response[/]")
    else:
        console.print(f"[red]Failed to start experiment: {result}[/]")


@cli.command("chaos-stop")
def chaos_stop():
    """Emergency stop all chaos injections."""
    result = post("/api/aref/chaos/stop")
    if result:
        console.print(f"[green]Chaos stopped. Rolled back {result.get('rolled_back', 0)} injections.[/]")
    else:
        console.print("[red]Could not stop chaos[/]")


@cli.command()
def timeline():
    """Show recent event timeline."""
    with console.status("[cyan]Fetching timeline...", spinner="dots"):
        data = fetch("/api/aref/timeline")

    if not data or not data.get("events"):
        console.print("[dim]No events recorded[/]")
        return

    table = Table(title="Event Timeline", box=ROUNDED, title_style="bold cyan")
    table.add_column("Time", width=12, style="dim")
    table.add_column("Category", width=12)
    table.add_column("Event", width=25)
    table.add_column("Severity", width=10)
    table.add_column("Source", width=20, style="dim")

    for event in reversed(data["events"][-25:]):
        cat = event.get("category", "")
        sev = event.get("severity", "info")
        style = PILLAR_STYLES.get(cat, Style())
        sev_style = SEVERITY_STYLES.get(sev, Style())

        ts = time.strftime("%H:%M:%S", time.localtime(event.get("timestamp", 0)))
        table.add_row(
            ts,
            Text(cat, style=style),
            event.get("event_type", ""),
            Text(sev, style=sev_style),
            event.get("source", ""),
        )

    console.print(table)


@cli.command()
def serve():
    """Start the AREF dashboard and control plane."""
    import uvicorn
    config = get_config_safe()
    port = config.dashboard_port if config else 8080

    console.print(render_header())
    console.print(f"\n[bold cyan]Starting AREF Dashboard on port {port}[/]")
    console.print(f"[dim]Open http://localhost:{port} in your browser[/]\n")

    uvicorn.run(
        "aref.dashboard.app:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
    )


def get_config_safe():
    try:
        from aref.core.config import get_config
        return get_config()
    except Exception:
        return None


def _add_dict_to_tree(tree: Tree, data: Any, depth: int = 0) -> None:
    """Recursively add dict data to a Rich tree."""
    if depth > 3:
        return
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                branch = tree.add(f"[bold]{key}[/]")
                _add_dict_to_tree(branch, value, depth + 1)
            else:
                tree.add(f"[dim]{key}:[/] {value}")
    elif isinstance(data, list):
        for i, item in enumerate(data[:10]):
            if isinstance(item, dict):
                branch = tree.add(f"[dim][{i}][/]")
                _add_dict_to_tree(branch, item, depth + 1)
            else:
                tree.add(str(item))


if __name__ == "__main__":
    cli()
