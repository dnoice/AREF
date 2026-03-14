"""
✒ Metadata
    - Title: AREF End-to-End Demo Script (v2.0)
    - File Name: demo.py
    - Relative Path: scripts/demo.py
    - Artifact Type: script
    - Version: 2.0.0
    - Date: 2026-03-13
    - Update: Thursday, March 13, 2026
    - Author: Dennis 'dnoice' Smaltz
    - A.I. Acknowledgement: Anthropic - Claude Opus 4
    - Signature: ︻デ═─── ✦ ✦ ✦ | Aim Twice, Shoot Once!

✒ Description:
    Comprehensive end-to-end demonstration of the AREF (Adaptive Resilience
    Engineering Framework) platform. Walks through the full AREF lifecycle:
    pre-flight checks, baseline traffic, chaos injection, pillar-by-pillar
    observation (Detection -> Absorption -> Adaptation -> Recovery -> Evolution),
    and post-incident analysis with rich terminal output.

✒ Key Features:
    - Feature 1:  Pre-flight health sweep of all 5 microservices + dashboard
    - Feature 2:  Baseline traffic generation with order pipeline timing
    - Feature 3:  Snapshot of CRS score, pillar scores, and service metrics
    - Feature 4:  Chaos injection via AREF chaos API (payment_provider_failure)
    - Feature 5:  Live traffic during incident with failure tracking
    - Feature 6:  Pillar-by-pillar deep inspection (circuit breakers, feature
                   flags, traffic routes, recovery tiers, timeline events)
    - Feature 7:  Chaos rollback and recovery observation
    - Feature 8:  Post-recovery traffic verification
    - Feature 9:  Side-by-side before/after CRS comparison
    - Feature 10: Full Rich terminal UI with panels, tables, progress bars,
                   and colour-coded status indicators
    - Feature 11: Multi-experiment mode (--experiment flag for any of the 5
                   pre-defined chaos experiments)
    - Feature 12: Configurable traffic volume, step delay, and base URLs via
                   CLI arguments

✒ Usage Instructions:
    $ python -m scripts.demo
    $ python -m scripts.demo --experiment cascading_failure --orders 15
    $ python -m scripts.demo --fast

✒ Other Important Information:
    - Dependencies:
        Required: httpx, rich
        Internal: None (pure HTTP client against running services)
    - Requires: All AREF services running (docker compose up)
    - Available experiments: payment_provider_failure, order_service_latency,
      inventory_degradation, notification_overload, cascading_failure
---------
"""

from __future__ import annotations

import argparse
import asyncio
import time
from typing import Any

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.box import ROUNDED, SIMPLE_HEAVY

COL_WIDTH = 72
console = Console(width=COL_WIDTH)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
API_BASE = "http://localhost:8080"
GATEWAY = "http://localhost:8000"
SERVICES = {
    "Gateway":       {"url": "http://localhost:8000", "health": "/health"},
    "Orders":        {"url": "http://localhost:8001", "health": "/health"},
    "Payments":      {"url": "http://localhost:8002", "health": "/health"},
    "Inventory":     {"url": "http://localhost:8003", "health": "/health"},
    "Notifications": {"url": "http://localhost:8004", "health": "/health"},
    "Dashboard":     {"url": "http://localhost:8080", "health": "/api/aref/status"},
}

PILLAR_COLORS = {
    "detection": "bright_cyan",
    "absorption": "bright_magenta",
    "adaptation": "bright_yellow",
    "recovery": "bright_green",
    "evolution": "bright_red",
}

EXPERIMENTS = [
    "payment_provider_failure",
    "order_service_latency",
    "inventory_degradation",
    "notification_overload",
    "cascading_failure",
]


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def score_bar(score: float, width: int = 18) -> str:
    filled = int(score * width)
    bar = "[green]" + "=" * filled + "[/][dim]" + "-" * (width - filled) + "[/]"
    return bar


def status_dot(healthy: bool) -> str:
    return "[green]OK[/]" if healthy else "[red]DOWN[/]"


def ms(seconds: float) -> str:
    return f"{seconds * 1000:.1f}ms"


# ---------------------------------------------------------------------------
# Step helpers
# ---------------------------------------------------------------------------
async def preflight(client: httpx.AsyncClient) -> bool:
    """Step 1: Check all services are running."""
    table = Table(box=ROUNDED, title="Service Health", show_header=True, header_style="bold", width=COL_WIDTH)
    table.add_column("Service", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Uptime", justify="right")
    table.add_column("Requests", justify="right")
    table.add_column("Memory", justify="right")

    all_ok = True
    for name, svc in SERVICES.items():
        try:
            resp = await client.get(f"{svc['url']}{svc['health']}", timeout=3.0)
            if resp.status_code == 200:
                d = resp.json()
                table.add_row(
                    name,
                    status_dot(True),
                    f"{d.get('uptime_seconds', 0):.0f}s",
                    str(d.get("total_requests", "-")),
                    f"{d.get('memory_mb', 0):.0f}MB",
                )
            else:
                table.add_row(name, status_dot(False), "-", "-", "-")
                all_ok = False
        except Exception:
            table.add_row(name, status_dot(False), "-", "-", "-")
            all_ok = False

    console.print(table)
    return all_ok


async def snapshot_crs(client: httpx.AsyncClient) -> dict[str, Any]:
    """Fetch CRS and pillar scores."""
    try:
        resp = await client.get(f"{API_BASE}/api/aref/status", timeout=5.0)
        return resp.json()
    except Exception:
        return {}


def render_crs(data: dict[str, Any], title: str = "Platform Status") -> Panel:
    """Render CRS + pillar scores as a Rich panel."""
    crs = data.get("crs", 0)
    pillars = data.get("pillars", {})

    table = Table(box=SIMPLE_HEAVY, show_header=True, header_style="bold", width=COL_WIDTH - 4)
    table.add_column("Pillar", style="bold")
    table.add_column("Score", justify="center", width=8)
    table.add_column("Bar", width=22)

    for name in ["detection", "absorption", "adaptation", "recovery", "evolution"]:
        score = pillars.get(name, 0)
        color = PILLAR_COLORS.get(name, "white")
        table.add_row(
            f"[{color}]{name.capitalize()}[/]",
            f"{score:.3f}",
            score_bar(score),
        )

    return Panel(
        table,
        title=f"[bold]{title}[/]  |  CRS: [bold cyan]{crs:.4f}[/]",
        box=ROUNDED,
        width=COL_WIDTH,
    )


async def generate_traffic(
    client: httpx.AsyncClient, count: int, label: str = "Traffic"
) -> dict[str, Any]:
    """Generate order traffic and return stats."""
    successes = 0
    failures = 0
    latencies: list[float] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"[cyan]{label}...", total=count)

        for i in range(count):
            start = time.perf_counter()
            try:
                resp = await client.post(f"{GATEWAY}/api/orders", json={
                    "customer_email": f"demo{i}@aref.test",
                    "items": [
                        {"sku": "WIDGET-001", "quantity": 2},
                        {"sku": "GADGET-001", "quantity": 1},
                    ],
                    "total": 44.97,
                    "payment_method": "card",
                }, timeout=12.0)
                elapsed = time.perf_counter() - start
                latencies.append(elapsed)

                if resp.status_code == 200:
                    d = resp.json()
                    order_id = d.get("order", {}).get("order_id", "?")
                    pipe = d.get("pipeline", {})
                    console.print(
                        f"  [green]OK[/] {order_id}  "
                        f"pipeline={pipe.get('total_ms', 0):.0f}ms  "
                        f"provider={d.get('payment', {}).get('provider', '?')}"
                    )
                    successes += 1
                else:
                    console.print(f"  [red]FAIL[/] HTTP {resp.status_code}: {resp.text[:60]}")
                    failures += 1
            except Exception as e:
                elapsed = time.perf_counter() - start
                latencies.append(elapsed)
                console.print(f"  [red]ERR[/]  {str(e)[:70]}")
                failures += 1

            progress.advance(task)
            await asyncio.sleep(0.25)

    avg_lat = sum(latencies) / max(len(latencies), 1)
    p99_lat = sorted(latencies)[int(len(latencies) * 0.99)] if len(latencies) > 1 else (latencies[0] if latencies else 0)

    stats = {
        "total": count,
        "successes": successes,
        "failures": failures,
        "avg_latency": avg_lat,
        "p99_latency": p99_lat,
    }

    table = Table(box=SIMPLE_HEAVY, show_header=False, width=COL_WIDTH - 4)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Total Requests", str(count))
    table.add_row("Successes", f"[green]{successes}[/]")
    table.add_row("Failures", f"[red]{failures}[/]" if failures else f"[green]{failures}[/]")
    table.add_row("Success Rate", f"{successes / max(count, 1) * 100:.1f}%")
    table.add_row("Avg Latency", ms(avg_lat))
    table.add_row("P99 Latency", ms(p99_lat))
    console.print(Panel(table, title=f"{label} Results", box=ROUNDED, width=COL_WIDTH))

    return stats


async def inspect_pillars(client: httpx.AsyncClient) -> None:
    """Deep-dive into each pillar's current state."""

    # Detection
    try:
        det = (await client.get(f"{API_BASE}/api/aref/detection", timeout=5.0)).json()
        alerts = det.get("active_alerts", det.get("alerts", []))
        alert_count = len(alerts) if isinstance(alerts, list) else alerts
        anomaly = det.get("anomaly", {})
        sli = det.get("sli_tracker", {})
        threshold = det.get("threshold", {})
        rules_count = threshold.get("rules_count", "?") if isinstance(threshold, dict) else threshold
        console.print(Panel(
            f"  Active alerts: [bold]{alert_count}[/]\n"
            f"  Anomaly metrics tracked: [bold]{len(anomaly)}[/]\n"
            f"  SLI services: [bold]{len(sli)}[/]  |  "
            f"Threshold rules: [bold]{rules_count}[/]",
            title="[bright_cyan]Detection[/]",
            box=ROUNDED, width=COL_WIDTH,
        ))
    except Exception as e:
        console.print(f"[dim]  Detection data unavailable: {e}[/]")

    # Absorption — circuit_breakers is {total, open, breakers: {name: {...}}}
    try:
        ab = (await client.get(f"{API_BASE}/api/aref/absorption", timeout=5.0)).json()
        cb_data = ab.get("circuit_breakers", {})
        cb_total = cb_data.get("total", 0) if isinstance(cb_data, dict) else len(cb_data)
        cb_open = cb_data.get("open", 0) if isinstance(cb_data, dict) else 0
        breakers = cb_data.get("breakers", {}) if isinstance(cb_data, dict) else {}
        open_names = [n for n, b in breakers.items() if b.get("state") == "OPEN"]
        rl_data = ab.get("rate_limiters", {})
        rl_count = rl_data.get("total", len(rl_data)) if isinstance(rl_data, dict) else len(rl_data)
        bh_data = ab.get("bulkheads", {})
        bh_count = bh_data.get("total", len(bh_data)) if isinstance(bh_data, dict) else len(bh_data)
        deg = ab.get("degradation", {})
        deg_count = len(deg) if isinstance(deg, (list, dict)) else 0
        console.print(Panel(
            f"  Circuit breakers: [bold]{cb_total}[/] total, "
            f"[{'red' if cb_open else 'green'}]{cb_open} OPEN[/]\n"
            f"  Rate limiters: [bold]{rl_count}[/]  |  Bulkheads: [bold]{bh_count}[/]\n"
            f"  Degradation: [bold]{deg_count}[/] services tracked"
            + (f"\n  [red]Open: {', '.join(open_names)}[/]" if open_names else ""),
            title="[bright_magenta]Absorption[/]",
            box=ROUNDED, width=COL_WIDTH,
        ))
    except Exception as e:
        console.print(f"[dim]  Absorption data unavailable: {e}[/]")

    # Adaptation — feature_flags is dict of {svc: [flags]}, scaler is {instances, limits, ...}
    try:
        ad = (await client.get(f"{API_BASE}/api/aref/adaptation", timeout=5.0)).json()
        flags_data = ad.get("feature_flags", {})
        # Flags can be dict {svc: [flags]} or list
        if isinstance(flags_data, dict):
            all_flags = [f for svc_flags in flags_data.values() for f in (svc_flags if isinstance(svc_flags, list) else [svc_flags])]
        else:
            all_flags = flags_data
        disabled = [f for f in all_flags if isinstance(f, dict) and not f.get("enabled")]
        shifter = ad.get("traffic_shifter", {})
        route_count = len(shifter.get("services", {})) if isinstance(shifter, dict) else 0
        scaler = ad.get("scaler", {})
        instances = scaler.get("instances", {}) if isinstance(scaler, dict) else {}
        total_inst = sum(instances.values()) if isinstance(instances, dict) else "?"
        console.print(Panel(
            f"  Feature flags: [bold]{len(all_flags)}[/] total, "
            f"[{'yellow' if disabled else 'green'}]{len(disabled)} disabled[/]\n"
            f"  Traffic routes: [bold]{route_count}[/] services  |  "
            f"Instances: [bold]{total_inst}[/]\n"
            f"  Active adaptations: [bold]{ad.get('active_adaptations', 0)}[/]  |  "
            f"Total: [bold]{ad.get('total_adaptations', 0)}[/]",
            title="[bright_yellow]Adaptation[/]",
            box=ROUNDED, width=COL_WIDTH,
        ))
    except Exception as e:
        console.print(f"[dim]  Adaptation data unavailable: {e}[/]")

    # Recovery
    try:
        rec = (await client.get(f"{API_BASE}/api/aref/recovery", timeout=5.0)).json()
        console.print(Panel(
            f"  Active recoveries: [bold]{rec.get('active_recoveries', 0)}[/]\n"
            f"  Total recovered: [bold]{rec.get('total_recovered', 0)}[/]\n"
            f"  Runbooks available: [bold]{len(rec.get('runbooks', []))}[/]",
            title="[bright_green]Recovery[/]",
            box=ROUNDED, width=COL_WIDTH,
        ))
    except Exception:
        console.print("[dim]  Recovery data unavailable[/]")

    # Evolution
    try:
        ev = (await client.get(f"{API_BASE}/api/aref/evolution", timeout=5.0)).json()
        console.print(Panel(
            f"  Reviews generated: [bold]{ev.get('reviews_generated', 0)}[/]\n"
            f"  Patterns detected: [bold]{ev.get('patterns_detected', 0)}[/]\n"
            f"  Knowledge entries: [bold]{ev.get('knowledge_entries', 0)}[/]",
            title="[bright_red]Evolution[/]",
            box=ROUNDED, width=COL_WIDTH,
        ))
    except Exception:
        console.print("[dim]  Evolution data unavailable[/]")


async def inspect_services(client: httpx.AsyncClient) -> None:
    """Show service-level detail from gateway deep health."""
    try:
        resp = await client.get(f"{GATEWAY}/api/services/deep-health", timeout=5.0)
        data = resp.json()

        table = Table(box=ROUNDED, title="Service Deep Health", show_header=True, header_style="bold", width=COL_WIDTH)
        table.add_column("Service", style="bold")
        table.add_column("Status", justify="center")
        table.add_column("Latency", justify="right")
        table.add_column("Circuit", justify="center")
        table.add_column("Failures", justify="right")

        for name, svc in data.get("services", {}).items():
            st = svc.get("status", "?")
            color = "green" if st == "healthy" else ("yellow" if st == "degraded" else "red")
            lat = f"{svc.get('latency_ms', 0):.1f}ms" if svc.get("latency_ms") else "-"
            circ = "[red]OPEN[/]" if svc.get("circuit_open") else "[green]CLOSED[/]"
            table.add_row(name, f"[{color}]{st.upper()}[/]", lat, circ, str(svc.get("recent_failures", 0)))

        console.print(table)
    except Exception:
        console.print("[dim]  Deep health unavailable[/]")


async def show_timeline(client: httpx.AsyncClient, limit: int = 10) -> None:
    """Show recent timeline events."""
    try:
        resp = await client.get(f"{API_BASE}/api/aref/timeline", timeout=5.0)
        data = resp.json()
        events = data.get("events", [])[-limit:]
        summary = data.get("summary", {})

        table = Table(box=ROUNDED, title=f"Event Timeline (last {limit})", show_header=True, header_style="bold", width=COL_WIDTH)
        table.add_column("Time", style="dim", width=10)
        table.add_column("Category")
        table.add_column("Event")
        table.add_column("Severity")
        table.add_column("Source", style="dim")

        for e in reversed(events):
            ts = time.strftime("%H:%M:%S", time.localtime(e.get("timestamp", 0)))
            cat = e.get("category", "?")
            color = PILLAR_COLORS.get(cat, "white")
            sev = e.get("severity", "info")
            sev_color = {"warning": "yellow", "critical": "red", "emergency": "red"}.get(sev, "dim")
            table.add_row(
                ts,
                f"[{color}]{cat}[/]",
                e.get("event_type", "?"),
                f"[{sev_color}]{sev.upper()}[/]",
                e.get("source", "?"),
            )

        cats = summary.get("by_category", {})
        subtitle = "  ".join(f"{k}:{v}" for k, v in cats.items())
        console.print(table)
        if subtitle:
            console.print(f"  [dim]Categories: {subtitle}[/]")
    except Exception:
        console.print("[dim]  Timeline unavailable[/]")


async def inject_chaos_experiment(client: httpx.AsyncClient, experiment: str) -> bool:
    """Inject a chaos experiment via the AREF API."""
    try:
        resp = await client.post(
            f"{API_BASE}/api/aref/chaos/start",
            json={"experiment": experiment},
            timeout=5.0,
        )
        data = resp.json()
        if "error" in data:
            console.print(f"  [red]Error:[/] {data['error']}")
            return False
        console.print(
            f"  [red]Chaos injected[/]  experiment=[bold]{experiment}[/]  "
            f"injection=[bold]{data.get('injection', '?')}[/]"
        )
        return True
    except Exception as e:
        console.print(f"  [red]Failed to inject chaos:[/] {e}")
        return False


async def stop_chaos_experiment(client: httpx.AsyncClient) -> None:
    """Stop chaos and roll back."""
    try:
        resp = await client.post(f"{API_BASE}/api/aref/chaos/stop", timeout=5.0)
        data = resp.json()
        console.print(
            f"  [green]Chaos stopped[/]  rolled_back=[bold]{data.get('rolled_back', 0)}[/]"
        )
    except Exception as e:
        console.print(f"  [yellow]Chaos stop failed:[/] {e}")


def render_comparison(before: dict, after: dict) -> None:
    """Side-by-side CRS comparison."""
    table = Table(box=ROUNDED, title="Before vs After", show_header=True, header_style="bold", width=COL_WIDTH)
    table.add_column("Pillar", style="bold")
    table.add_column("Before", justify="center")
    table.add_column("After", justify="center")
    table.add_column("Delta", justify="center")

    for name in ["detection", "absorption", "adaptation", "recovery", "evolution"]:
        b = before.get("pillars", {}).get(name, 0)
        a = after.get("pillars", {}).get(name, 0)
        delta = a - b
        d_color = "green" if delta >= 0 else "red"
        d_sign = "+" if delta >= 0 else ""
        color = PILLAR_COLORS.get(name, "white")
        table.add_row(
            f"[{color}]{name.capitalize()}[/]",
            f"{b:.3f}",
            f"{a:.3f}",
            f"[{d_color}]{d_sign}{delta:.3f}[/]",
        )

    crs_b = before.get("crs", 0)
    crs_a = after.get("crs", 0)
    crs_d = crs_a - crs_b
    crs_color = "green" if crs_d >= 0 else "red"
    crs_sign = "+" if crs_d >= 0 else ""
    table.add_row(
        "[bold]CRS[/]",
        f"[bold]{crs_b:.4f}[/]",
        f"[bold]{crs_a:.4f}[/]",
        f"[bold {crs_color}]{crs_sign}{crs_d:.4f}[/]",
    )

    console.print(table)


# ---------------------------------------------------------------------------
# Main demo flow
# ---------------------------------------------------------------------------
async def run_demo(
    experiment: str = "payment_provider_failure",
    order_count: int = 8,
    step_delay: float = 2.0,
) -> None:
    console.print()
    console.print(Panel(
        Text.from_markup(
            "[bold bright_cyan]AREF End-to-End Resilience Demo[/]\n"
            "[dim]Adaptive Resilience Engineering Framework[/]\n\n"
            f"Experiment: [bold]{experiment}[/]  |  Orders: [bold]{order_count}[/]"
        ),
        subtitle="[dim]digiSpace Technical Studio[/]",
        box=ROUNDED, width=COL_WIDTH,
    ))

    async with httpx.AsyncClient(timeout=10.0) as client:

        # ---- Step 1: Pre-flight ----
        console.print("\n[bold bright_cyan]Step 1[/]  Pre-flight health check")
        console.print("[dim]" + "-" * (COL_WIDTH - 2) + "[/]")
        healthy = await preflight(client)
        if not healthy:
            console.print(Panel(
                "[bold red]Some services are unreachable.[/]\n\n"
                "Start the platform:\n"
                "  [dim]$ docker compose up -d[/]\n\n"
                "Then run the demo:\n"
                "  [dim]$ python -m scripts.demo[/]",
                title="Platform Not Ready",
                box=ROUNDED, width=COL_WIDTH,
            ))
            return
        await asyncio.sleep(step_delay)

        # ---- Step 2: Baseline CRS ----
        console.print("\n[bold bright_cyan]Step 2[/]  Baseline platform status")
        console.print("[dim]" + "-" * (COL_WIDTH - 2) + "[/]")
        baseline = await snapshot_crs(client)
        console.print(render_crs(baseline, "Baseline Status"))
        await asyncio.sleep(step_delay)

        # ---- Step 3: Normal traffic ----
        console.print("\n[bold bright_cyan]Step 3[/]  Normal traffic (baseline)")
        console.print("[dim]" + "-" * (COL_WIDTH - 2) + "[/]")
        baseline_stats = await generate_traffic(client, order_count, "Baseline Traffic")
        await asyncio.sleep(step_delay)

        # ---- Step 4: Inspect services ----
        console.print("\n[bold bright_cyan]Step 4[/]  Service deep health")
        console.print("[dim]" + "-" * (COL_WIDTH - 2) + "[/]")
        await inspect_services(client)
        await asyncio.sleep(step_delay)

        # ---- Step 5: Inject chaos ----
        console.print(f"\n[bold red]Step 5[/]  Injecting chaos: [bold]{experiment}[/]")
        console.print("[dim]" + "-" * (COL_WIDTH - 2) + "[/]")
        injected = await inject_chaos_experiment(client, experiment)
        if not injected:
            console.print("[yellow]Skipping chaos steps.[/]")
            return
        await asyncio.sleep(step_delay)

        # ---- Step 6: Traffic during failure ----
        console.print("\n[bold yellow]Step 6[/]  Traffic during incident")
        console.print("[dim]" + "-" * (COL_WIDTH - 2) + "[/]")
        incident_stats = await generate_traffic(client, order_count, "Incident Traffic")
        await asyncio.sleep(step_delay)

        # ---- Step 7: Observe platform response ----
        console.print("\n[bold bright_cyan]Step 7[/]  Platform response (during incident)")
        console.print("[dim]" + "-" * (COL_WIDTH - 2) + "[/]")
        during = await snapshot_crs(client)
        console.print(render_crs(during, "During Incident"))
        await asyncio.sleep(1.0)

        # Pillar deep-dive
        console.print("\n[bold]  Pillar Deep-Dive[/]")
        await inspect_pillars(client)
        await asyncio.sleep(1.0)

        # Service health during incident
        console.print("\n[bold]  Service Health[/]")
        await inspect_services(client)
        await asyncio.sleep(step_delay)

        # ---- Step 8: Timeline ----
        console.print("\n[bold bright_cyan]Step 8[/]  Event timeline")
        console.print("[dim]" + "-" * (COL_WIDTH - 2) + "[/]")
        await show_timeline(client, limit=12)
        await asyncio.sleep(step_delay)

        # ---- Step 9: Stop chaos ----
        console.print("\n[bold green]Step 9[/]  Rolling back chaos")
        console.print("[dim]" + "-" * (COL_WIDTH - 2) + "[/]")
        await stop_chaos_experiment(client)
        await asyncio.sleep(step_delay)

        # ---- Step 10: Recovery traffic ----
        console.print("\n[bold bright_cyan]Step 10[/]  Post-recovery traffic")
        console.print("[dim]" + "-" * (COL_WIDTH - 2) + "[/]")
        recovery_stats = await generate_traffic(client, order_count, "Recovery Traffic")
        await asyncio.sleep(step_delay)

        # ---- Step 11: Final status ----
        console.print("\n[bold bright_cyan]Step 11[/]  Final platform status")
        console.print("[dim]" + "-" * (COL_WIDTH - 2) + "[/]")
        final = await snapshot_crs(client)
        console.print(render_crs(final, "Post-Recovery Status"))
        await asyncio.sleep(1.0)

        # ---- Step 12: Before/After comparison ----
        console.print("\n[bold bright_cyan]Step 12[/]  Before vs After")
        console.print("[dim]" + "-" * (COL_WIDTH - 2) + "[/]")
        render_comparison(baseline, final)

        # ---- Summary ----
        summary_table = Table(box=ROUNDED, title="Traffic Summary", show_header=True, header_style="bold", width=COL_WIDTH)
        summary_table.add_column("Phase", style="bold")
        summary_table.add_column("Success", justify="center")
        summary_table.add_column("Failed", justify="center")
        summary_table.add_column("Avg Latency", justify="right")
        summary_table.add_column("P99 Latency", justify="right")

        for label, stats in [("Baseline", baseline_stats), ("Incident", incident_stats), ("Recovery", recovery_stats)]:
            s = stats["successes"]
            f = stats["failures"]
            s_color = "green" if f == 0 else "yellow"
            f_color = "red" if f > 0 else "green"
            summary_table.add_row(
                label,
                f"[{s_color}]{s}[/]",
                f"[{f_color}]{f}[/]",
                ms(stats["avg_latency"]),
                ms(stats["p99_latency"]),
            )

        console.print(summary_table)

        console.print(Panel(
            Text.from_markup(
                "[bold green]Demo Complete[/]\n\n"
                f"View the full dashboard at [bold underline]http://localhost:8080[/]\n"
                f"Timeline, pillar tabs, and service details are all live."
            ),
            subtitle="[dim]AREF - Adaptive Resilience Engineering Framework[/]",
            box=ROUNDED, width=COL_WIDTH,
        ))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="AREF End-to-End Demo")
    parser.add_argument(
        "--experiment", "-e",
        default="payment_provider_failure",
        choices=EXPERIMENTS,
        help="Chaos experiment to run (default: payment_provider_failure)",
    )
    parser.add_argument(
        "--orders", "-n",
        type=int, default=8,
        help="Number of orders per traffic phase (default: 8)",
    )
    parser.add_argument(
        "--delay", "-d",
        type=float, default=2.0,
        help="Delay between steps in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--fast", "-f",
        action="store_true",
        help="Fast mode: 4 orders, 0.5s delay",
    )
    args = parser.parse_args()

    orders = 4 if args.fast else args.orders
    delay = 0.5 if args.fast else args.delay

    asyncio.run(run_demo(
        experiment=args.experiment,
        order_count=orders,
        step_delay=delay,
    ))


if __name__ == "__main__":
    main()
