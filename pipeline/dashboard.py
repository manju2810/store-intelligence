
## Architecture
import requests
import time
import os
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.live import Live
from rich.text import Text
from datetime import datetime

console = Console()

API_URL  = os.getenv("API_URL", "http://localhost:8000")
STORE_ID = os.getenv("STORE_ID", "ST1008")
REFRESH  = int(os.getenv("REFRESH_SECONDS", "5"))

def fetch_metrics():
    try:
        r = requests.get(
            f"{API_URL}/stores/{STORE_ID}/metrics",
            timeout=5
        )
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

def fetch_funnel():
    try:
        r = requests.get(
            f"{API_URL}/stores/{STORE_ID}/funnel",
            timeout=5
        )
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

def fetch_anomalies():
    try:
        r = requests.get(
            f"{API_URL}/stores/{STORE_ID}/anomalies",
            timeout=5
        )
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

def fetch_health():
    try:
        r = requests.get(
            f"{API_URL}/health",
            timeout=5
        )
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

def build_dashboard():
    metrics   = fetch_metrics()
    funnel    = fetch_funnel()
    anomalies = fetch_anomalies()
    health    = fetch_health()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Header ───────────────────────────────────────────
    header = Panel(
        Text(
            f"🏪 Store Intelligence Dashboard — {STORE_ID}\n"
            f"Last updated: {now}",
            justify="center"
        ),
        style="bold blue"
    )

    # ── Metrics Table ────────────────────────────────────
    metrics_table = Table(
        title="📊 Live Metrics",
        show_header=True,
        header_style="bold cyan"
    )
    metrics_table.add_column("Metric", style="bold")
    metrics_table.add_column("Value", justify="right")

    if metrics:
        metrics_table.add_row(
            "Unique Visitors",
            str(metrics.get("unique_visitors", 0))
        )
        metrics_table.add_row(
            "Conversion Rate",
            f"{metrics.get('conversion_rate', 0)}%"
        )
        metrics_table.add_row(
            "Queue Depth",
            str(metrics.get("queue_depth", 0))
        )
        metrics_table.add_row(
            "Abandonment Rate",
            f"{metrics.get('abandonment_rate', 0)}%"
        )
    else:
        metrics_table.add_row("Status", "No data yet")

    # ── Funnel Table ─────────────────────────────────────
    funnel_table = Table(
        title="🔄 Conversion Funnel",
        show_header=True,
        header_style="bold magenta"
    )
    funnel_table.add_column("Stage", style="bold")
    funnel_table.add_column("Count", justify="right")
    funnel_table.add_column("Drop Off", justify="right")

    if funnel:
        for stage in funnel.get("stages", []):
            funnel_table.add_row(
                stage["stage"],
                str(stage["count"]),
                f"{stage['drop_off_pct']}%"
            )
    else:
        funnel_table.add_row("Status", "No data", "")

    # ── Anomalies Table ──────────────────────────────────
    anomaly_table = Table(
        title="⚠️  Active Anomalies",
        show_header=True,
        header_style="bold red"
    )
    anomaly_table.add_column("Type", style="bold")
    anomaly_table.add_column("Severity")
    anomaly_table.add_column("Description")

    severity_colors = {
        "CRITICAL": "red",
        "WARN"    : "yellow",
        "INFO"    : "blue"
    }

    if anomalies and anomalies.get("anomalies"):
        for a in anomalies["anomalies"]:
            color = severity_colors.get(
                a["severity"], "white"
            )
            anomaly_table.add_row(
                a["anomaly_type"],
                Text(a["severity"], style=color),
                a["description"][:50] + "..."
                if len(a["description"]) > 50
                else a["description"]
            )
    else:
        anomaly_table.add_row(
            "✅ No anomalies", "", ""
        )

    # ── Health Status ────────────────────────────────────
    health_status = "🟢 OK"
    if health:
        status = health.get("status", "UNKNOWN")
        if status == "OK":
            health_status = "🟢 OK"
        elif status == "DEGRADED":
            health_status = "🟡 DEGRADED"
        else:
            health_status = "🔴 ERROR"

    health_panel = Panel(
        Text(
            f"System Health: {health_status}",
            justify="center"
        ),
        style="bold green"
    )

    return (
        header,
        Columns([metrics_table, funnel_table]),
        anomaly_table,
        health_panel
    )

def main():
    console.print(
        "\n[bold blue]Starting Store Intelligence Dashboard[/]"
    )
    console.print(
        f"[dim]Connecting to {API_URL}...[/]\n"
    )

    with Live(
        console=console,
        refresh_per_second=1,
        screen=True
    ) as live:
        while True:
            try:
                components = build_dashboard()
                from rich.console import Group
                live.update(Group(*components))
                time.sleep(REFRESH)
            except KeyboardInterrupt:
                break

    console.print(
        "\n[bold]Dashboard stopped.[/]"
    )

if __name__ == "__main__":
    main()