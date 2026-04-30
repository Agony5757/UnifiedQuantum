"""Chip characterization subcommand."""

from __future__ import annotations

import os

import rich.box
import typer
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from .output import (
    AI_HINTS_OPTION,
    build_ref_str,
    print_ai_hints,
    print_error,
    print_info,
    print_json,
    print_success,
    print_warning,
)

HELP = (
    "Inspect per-qubit chip calibration data from cloud platforms\n"
    f"  {build_ref_str('chip')}"
)

console = Console()

app = typer.Typer(help=HELP)


@app.command("list")
def list_chips(
    platform: str | None = typer.Option(
        None, "--platform", "-p", help="Filter by platform: originq/quafu/ibm"
    ),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format: table (default) or json"
    ),
    ai_hints: bool = AI_HINTS_OPTION,
):
    """List all cached chip characterization data.

    Workflow:
      - No chips shown? Run uniqc chip update --platform originq to fetch calibration data.
      - View a specific chip: uniqc chip show originq:wuyuan:d5
      - Update stale data: uniqc chip update --platform ibm
    """
    if ai_hints or os.environ.get("UNIQC_AI_HINTS"):
        print_ai_hints("chip")

    from uniqc.backend_info import Platform
    from uniqc.chip_cache import chip_cache_info

    target_platform: Platform | None = None
    if platform:
        try:
            target_platform = Platform(platform.lower())
        except ValueError:
            print_error(f"Unknown platform '{platform}'. Valid: originq, quafu, ibm")
            raise typer.Exit(1) from None

    info = chip_cache_info()
    if not info:
        print_info("No chip data cached. Run 'uniqc chip update --platform <name>' to fetch.")
        return

    # Filter
    if target_platform:
        info = {k: v for k, v in info.items() if v["platform"] == target_platform.value}

    if not info:
        print_info(f"No cached chips for platform '{platform}'.")
        return

    rows = []
    json_data = []
    for key, meta in sorted(info.items()):
        age_str = _format_age(meta["age_seconds"])
        stale = "[yellow](stale)[/yellow]" if meta["is_stale"] else ""
        rows.append(
            [
                meta["platform"],
                meta["chip_name"],
                str(meta["num_qubits"]),
                str(meta["num_pairs"]),
                age_str + stale,
                meta["calibrated_at"] or "N/A",
            ]
        )
        json_data.append({**meta, "full_id": key})

    if format == "json":
        print_json(json_data)
        return

    table = Table(
        title="Cached Chips",
        box=rich.box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Platform", style="cyan", width=10)
    table.add_column("Chip Name", style="bold white")
    table.add_column("Qubits", justify="right", width=8)
    table.add_column("Pairs", justify="right", width=6)
    table.add_column("Cached", width=12)
    table.add_column("Calibrated At", width=20)
    for row in rows:
        table.add_row(*row)
    console.print(table)


@app.command()
def show(
    identifier: str = typer.Argument(..., help="Backend identifier (platform:name or bare name)"),
    format: str = typer.Option("rich", "--format", "-f", help="Output format: rich (default) or json"),
    ai_hints: bool = AI_HINTS_OPTION,
):
    """Show full chip characterization for a backend.

    Fetches from the cloud API if not cached locally. Shows per-qubit T1/T2,
    gate fidelities, readout errors, connectivity, and global chip properties.

    Workflow:
      - Pick a chip from: uniqc chip list
      - Update stale data: uniqc chip update --chip-name <NAME> --platform <PLATFORM>
      - Use this data for qubit selection: see analyzer module for optimal qubit picking.
    """
    if ai_hints or os.environ.get("UNIQC_AI_HINTS"):
        print_ai_hints("chip")

    from uniqc.backend_info import Platform, parse_backend_id
    from uniqc.chip_service import fetch_chip_characterization

    # Try to resolve identifier
    try:
        plat, name = parse_backend_id(identifier)
    except ValueError:
        # Try as bare name — search all platforms
        plat, name = None, identifier
        if ":" in identifier:
            print_error(f"Ambiguous identifier '{identifier}'. Use 'platform:name' format.")
            raise typer.Exit(1) from None

    if plat is not None:
        chip = fetch_chip_characterization(name, plat)
    else:
        # Bare name: try each platform
        chip = None
        for p in Platform:
            chip = fetch_chip_characterization(name, p)
            if chip is not None:
                break

    if chip is None:
        print_error(f"Chip '{identifier}' not found or platform unavailable.")
        print_info("Run 'uniqc chip update --platform <name>' to fetch chip data.")
        raise typer.Exit(1)

    if format == "json":
        print_json(chip.to_dict())
        return

    _print_chip_detail(chip)


@app.command("update")
def update(
    platform: str | None = typer.Option(
        None, "--platform", "-p", help="Only update chips for this platform: originq/quafu/ibm"
    ),
    chip_name: str | None = typer.Option(
        None, "--chip-name", "-c", help="Update a specific chip by name (requires --platform)"
    ),
    ai_hints: bool = AI_HINTS_OPTION,
):
    """Force-refresh chip characterization data from cloud APIs.

    Bypasses the cache and re-fetches calibration data from all configured
    platforms (or only the specified platform). Run this when chip calibration
    has been updated on the cloud side.

    Workflow:
      - After calibration update on the cloud: uniqc chip update
      - List to confirm: uniqc chip list
      - Inspect specific chip: uniqc chip show <NAME>
    """
    if ai_hints or os.environ.get("UNIQC_AI_HINTS"):
        print_ai_hints("chip")

    from uniqc.backend_info import Platform
    from uniqc.chip_service import fetch_all_chips, fetch_chip_characterization

    target: Platform | None = None
    if platform:
        try:
            target = Platform(platform.lower())
        except ValueError:
            print_error(f"Unknown platform '{platform}'. Valid: originq, quafu, ibm")
            raise typer.Exit(1) from None

    if chip_name:
        if not platform:
            print_error("--chip-name requires --platform to be specified.")
            raise typer.Exit(1) from None
        chip = fetch_chip_characterization(chip_name, target, force_refresh=True)
        if chip:
            print_success(f"Updated: {chip.full_id}")
        else:
            print_warning(f"Could not fetch {chip_name} from {platform}.")
        return

    # Update all (or one platform)
    chips = fetch_all_chips(platform=target, force_refresh=True)
    if not chips:
        print_warning("No chips updated. Check credentials: uniqc config validate")
    else:
        names = [f"{c.platform.value}:{c.chip_name}" for c in chips]
        print_success(f"Updated {len(chips)} chip(s): {', '.join(names)}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_chip_detail(chip) -> None:
    """Print chip characterization details using Rich formatting."""

    console.print(Rule(f"[bold cyan]Chip: {chip.full_id}[/bold cyan]"))

    # Overview panel
    overview = [
        f"[bold]Platform:[/bold]  {chip.platform.value}",
        f"[bold]Chip:[/bold]      {chip.chip_name}",
        f"[bold]Qubits:[/bold]    {len(chip.available_qubits)} available / {len(chip.connectivity)} pairs",
        f"[bold]Calibrated:[/bold] {chip.calibrated_at or 'N/A'}",
    ]
    console.print(
        Panel("\n".join(overview), title="Overview", box=rich.box.ROUNDED)
    )

    # Global info
    gi = chip.global_info
    if gi.single_qubit_gates or gi.two_qubit_gates or gi.single_qubit_gate_time:
        gi_lines = []
        if gi.single_qubit_gates:
            gi_lines.append(f"[bold]1Q Gates:[/bold]     {', '.join(gi.single_qubit_gates)}")
        if gi.two_qubit_gates:
            gi_lines.append(f"[bold]2Q Gates:[/bold]     {', '.join(gi.two_qubit_gates)}")
        if gi.single_qubit_gate_time:
            gi_lines.append(f"[bold]1Q Gate Time:[/bold] {gi.single_qubit_gate_time} ns")
        if gi.two_qubit_gate_time:
            gi_lines.append(f"[bold]2Q Gate Time:[/bold] {gi.two_qubit_gate_time} ns")
        console.print(
            Panel("\n".join(gi_lines), title="Global Info", box=rich.box.ROUNDED)
        )

    # Per-qubit table
    if chip.single_qubit_data:
        q_table = Table(
            title="Per-Qubit Data",
            box=rich.box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
        )
        q_table.add_column("ID", justify="right", width=5)
        q_table.add_column("T1 (μs)", justify="right", width=9)
        q_table.add_column("T2 (μs)", justify="right", width=9)
        q_table.add_column("1Q Fid.", justify="right", width=9)
        q_table.add_column("R0", justify="right", width=7)
        q_table.add_column("R1", justify="right", width=7)
        q_table.add_column("Avg R", justify="right", width=9)

        for sq in sorted(chip.single_qubit_data, key=lambda x: x.qubit_id):
            q_table.add_row(
                str(sq.qubit_id),
                _fmt(sq.t1, ".2f"),
                _fmt(sq.t2, ".2f"),
                _fmt(sq.single_gate_fidelity, ".4f"),
                _fmt(sq.readout_fidelity_0, ".4f"),
                _fmt(sq.readout_fidelity_1, ".4f"),
                _fmt(sq.avg_readout_fidelity, ".4f"),
            )
        console.print(q_table)

    # Per-pair table
    if chip.two_qubit_data:
        p_table = Table(
            title="Per-Pair 2Q Gate Data",
            box=rich.box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
        )
        p_table.add_column("Qubit U", justify="right", width=8)
        p_table.add_column("Qubit V", justify="right", width=8)
        p_table.add_column("Gate", width=8)
        p_table.add_column("Fidelity", justify="right", width=10)

        for tp in sorted(chip.two_qubit_data, key=lambda x: (x.qubit_u, x.qubit_v)):
            for gate in tp.gates:
                p_table.add_row(
                    str(tp.qubit_u),
                    str(tp.qubit_v),
                    gate.gate,
                    _fmt(gate.fidelity, ".4f"),
                )
        console.print(p_table)


def _fmt(val: float | None, pattern: str) -> str:
    """Format a float or return '-' if None."""
    if val is None:
        return "-"
    return f"{val:{pattern}}"


def _format_age(seconds: float) -> str:
    """Return a human-readable age string."""
    if seconds < 60:
        return f"{seconds:.0f}s ago"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.0f}m ago"
    hours = minutes / 60
    if hours < 24:
        return f"{hours:.0f}h ago"
    days = hours / 24
    return f"{days:.0f}d ago"
