"""
Typer CLI for Chromium Session Parser.
"""

import json
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from .browsers import (
    Browser,
    BrowserProfile,
    detect_browsers,
    get_browser_by_id,
    get_browser_choices,
    get_profile_choices,
)
from .parser import SessionParser, Workspace, load_vivaldi_workspaces

app = typer.Typer(
    name="chromium-session",
    help="Parse Chromium-based browser session files with workspace support.",
    no_args_is_help=True,
)
console = Console()


def complete_browser(incomplete: str) -> list[str]:
    """Autocomplete browser names."""
    choices = get_browser_choices()
    return [c for c in choices if c.startswith(incomplete)]


def complete_profile(ctx: typer.Context, incomplete: str) -> list[str]:
    """Autocomplete profile names based on selected browser."""
    browser_id = ctx.params.get("browser")
    if not browser_id:
        return []
    choices = get_profile_choices(browser_id)
    return [c for c in choices if c.startswith(incomplete)]


def get_selected_profile(browser: Browser, profile_name: str | None) -> BrowserProfile | None:
    """Get the selected profile or first available."""
    if not browser.profiles:
        return None
    
    if profile_name:
        for p in browser.profiles:
            if p.name == profile_name:
                return p
        # Try partial match
        for p in browser.profiles:
            if profile_name.lower() in p.name.lower():
                return p
    
    # Return first profile with sessions, or just first
    for p in browser.profiles:
        if p.has_sessions:
            return p
    return browser.profiles[0]


def list_session_files(sessions_dir: Path) -> list[Path]:
    """List all session files in a directory, sorted by modification time."""
    files = []
    for pattern in ["Session_*", "Tabs_*", "Current Session", "Current Tabs"]:
        files.extend(sessions_dir.glob(pattern))
    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)


@app.command("list")
def list_browsers():
    """List all detected Chromium-based browsers."""
    browsers = detect_browsers()

    if not browsers:
        rprint("[yellow]No Chromium-based browsers detected[/yellow]")
        raise typer.Exit(1)

    table = Table(title="Detected Browsers")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Profiles", style="dim")
    table.add_column("Sessions", style="yellow")

    for browser in browsers:
        profile_names = ", ".join(p.name for p in browser.profiles[:3])
        if len(browser.profiles) > 3:
            profile_names += f" (+{len(browser.profiles) - 3})"
        
        sessions_count = sum(1 for p in browser.profiles if p.has_sessions)
        sessions_str = f"{sessions_count}/{len(browser.profiles)}"
        
        table.add_row(browser.id, browser.name, profile_names, sessions_str)

    console.print(table)


@app.command()
def workspaces(
    browser: Annotated[
        str,
        typer.Argument(
            help="Browser to use",
            autocompletion=complete_browser,
        ),
    ],
    profile: Annotated[
        Optional[str],
        typer.Option("--profile", "-p", help="Profile name", autocompletion=complete_profile),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help="Output as JSON")
    ] = False,
):
    """List defined workspaces (Vivaldi only)."""
    browser_obj = get_browser_by_id(browser)
    if not browser_obj:
        rprint(f"[red]Browser '{browser}' not found. Run 'chromium-session list' to see available browsers.[/red]")
        raise typer.Exit(1)

    profile_obj = get_selected_profile(browser_obj, profile)
    if not profile_obj:
        rprint(f"[red]No profiles found for {browser_obj.name}[/red]")
        raise typer.Exit(1)

    ws = load_vivaldi_workspaces(profile_obj.path)

    if not ws:
        rprint(f"[yellow]No workspaces found (workspaces are Vivaldi-specific)[/yellow]")
        raise typer.Exit(1)

    if json_output:
        data = {str(k): {"name": v.name, "emoji": v.emoji} for k, v in ws.items()}
        print(json.dumps(data, indent=2))
        return

    table = Table(title=f"Workspaces in {browser_obj.name} / {profile_obj.name}")
    table.add_column("Emoji", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("ID", style="dim")

    for ws_id, workspace in sorted(ws.items(), key=lambda x: x[1].name):
        table.add_row(workspace.emoji or "📁", workspace.name, str(ws_id))

    console.print(table)


@app.command()
def parse(
    browser: Annotated[
        str,
        typer.Argument(
            help="Browser to use",
            autocompletion=complete_browser,
        ),
    ],
    files: Annotated[
        Optional[list[Path]],
        typer.Argument(help="Session file(s) to parse"),
    ] = None,
    profile: Annotated[
        Optional[str],
        typer.Option("--profile", "-p", help="Profile name", autocompletion=complete_profile),
    ] = None,
    latest: Annotated[
        int, typer.Option("--latest", "-n", help="Parse only N most recent files")
    ] = 1,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help="Output as JSON")
    ] = False,
    show_deleted: Annotated[
        bool, typer.Option("--show-deleted", help="Include deleted tabs/windows")
    ] = False,
    by_workspace: Annotated[
        bool, typer.Option("--by-workspace", "-W", help="Group tabs by workspace (Vivaldi)")
    ] = False,
):
    """Parse session files and display tabs."""
    browser_obj = get_browser_by_id(browser)
    if not browser_obj:
        rprint(f"[red]Browser '{browser}' not found. Run 'chromium-session list' to see available browsers.[/red]")
        raise typer.Exit(1)

    profile_obj = get_selected_profile(browser_obj, profile)
    if not profile_obj:
        rprint(f"[red]No profiles found for {browser_obj.name}[/red]")
        raise typer.Exit(1)

    # Load workspaces (Vivaldi-specific, but harmless for others)
    workspaces_map = load_vivaldi_workspaces(profile_obj.path)

    # Determine files to parse
    files_to_parse: list[Path] = []

    if files:
        files_to_parse = files
    elif profile_obj.has_sessions:
        files_to_parse = list_session_files(profile_obj.sessions_path)[:latest]

    if not files_to_parse:
        rprint(f"[red]No session files found in {profile_obj.sessions_path}[/red]")
        raise typer.Exit(1)

    parser = SessionParser(workspaces=workspaces_map)
    all_results = []

    for filepath in files_to_parse:
        try:
            result = parser.parse_file(filepath)
            result["_file"] = str(filepath)
            result["_mtime"] = filepath.stat().st_mtime
            result["_browser"] = browser_obj.name
            result["_profile"] = profile_obj.name
            result["_workspaces"] = {
                str(ws_id): {"name": ws.name, "emoji": ws.emoji}
                for ws_id, ws in workspaces_map.items()
            }
            all_results.append(result)

            if not json_output:
                rprint(f"\n[bold cyan]# {browser_obj.name} / {profile_obj.name}[/bold cyan]")
                rprint(f"[dim]# File: {filepath.name}[/dim]")
                display_result(
                    result,
                    show_deleted=show_deleted,
                    by_workspace=by_workspace,
                )

        except Exception as e:
            rprint(f"[red]Error parsing {filepath}: {e}[/red]")

    if json_output:
        output = all_results if len(all_results) > 1 else all_results[0]
        print(json.dumps(output, indent=2))


@app.command()
def summary(
    browser: Annotated[
        str,
        typer.Argument(
            help="Browser to use",
            autocompletion=complete_browser,
        ),
    ],
    profile: Annotated[
        Optional[str],
        typer.Option("--profile", "-p", help="Profile name", autocompletion=complete_profile),
    ] = None,
):
    """Show a quick summary of session stats."""
    browser_obj = get_browser_by_id(browser)
    if not browser_obj:
        rprint(f"[red]Browser '{browser}' not found. Run 'chromium-session list' to see available browsers.[/red]")
        raise typer.Exit(1)

    profile_obj = get_selected_profile(browser_obj, profile)
    if not profile_obj:
        rprint(f"[red]No profiles found for {browser_obj.name}[/red]")
        raise typer.Exit(1)

    workspaces_map = load_vivaldi_workspaces(profile_obj.path)

    if not profile_obj.has_sessions:
        rprint(f"[red]No sessions directory found[/red]")
        raise typer.Exit(1)

    files_to_parse = list_session_files(profile_obj.sessions_path)[:1]

    if not files_to_parse:
        rprint("[red]No session files found[/red]")
        raise typer.Exit(1)

    parser = SessionParser(workspaces=workspaces_map)

    for filepath in files_to_parse:
        try:
            result = parser.parse_file(filepath)

            total_tabs = 0
            deleted_tabs = 0
            ws_counts: dict[str, int] = {}

            for window in result["windows"]:
                for tab in window["tabs"]:
                    total_tabs += 1
                    if tab["deleted"]:
                        deleted_tabs += 1
                    ws_name = tab.get("workspace") or "No Workspace"
                    ws_counts[ws_name] = ws_counts.get(ws_name, 0) + 1

            rprint(f"\n[bold cyan]{browser_obj.name} / {profile_obj.name}[/bold cyan]")
            rprint(f"[dim]Session: {filepath.name}[/dim]")

            table = Table(show_header=True)
            table.add_column("Metric", style="dim")
            table.add_column("Value", style="green")

            table.add_row("Total tabs", str(total_tabs))
            table.add_row("Active tabs", str(total_tabs - deleted_tabs))
            table.add_row("Deleted tabs", str(deleted_tabs))
            table.add_row("Windows", str(len(result["windows"])))

            console.print(table)

            # Workspace breakdown (if any)
            if ws_counts and len(ws_counts) > 1:
                ws_table = Table(title="Tabs by Workspace")
                ws_table.add_column("Workspace", style="cyan")
                ws_table.add_column("Tabs", style="green", justify="right")

                for ws_name, count in sorted(ws_counts.items(), key=lambda x: -x[1]):
                    ws_table.add_row(ws_name, str(count))

                console.print(ws_table)

        except Exception as e:
            rprint(f"[red]Error: {e}[/red]")


@app.command()
def profiles(
    browser: Annotated[
        str,
        typer.Argument(
            help="Browser to show profiles for",
            autocompletion=complete_browser,
        ),
    ],
):
    """List profiles for a specific browser."""
    browser_obj = get_browser_by_id(browser)
    if not browser_obj:
        rprint(f"[red]Browser '{browser}' not found. Run 'chromium-session list' to see available browsers.[/red]")
        raise typer.Exit(1)

    table = Table(title=f"Profiles for {browser_obj.name}")
    table.add_column("Name", style="cyan")
    table.add_column("Has Sessions", style="green")
    table.add_column("Path", style="dim")

    for p in browser_obj.profiles:
        has_sessions = "✓" if p.has_sessions else "✗"
        table.add_row(p.name, has_sessions, str(p.path))

    console.print(table)


def display_result(result: dict, show_deleted: bool = False, by_workspace: bool = False):
    """Display parsed session result."""
    if by_workspace:
        display_by_workspace(result, show_deleted)
    else:
        display_by_window(result, show_deleted)


def display_by_workspace(result: dict, show_deleted: bool = False):
    """Display tabs grouped by workspace."""
    workspaces: dict[str, list[dict]] = {}
    no_workspace: list[dict] = []

    for window in result["windows"]:
        for tab in window["tabs"]:
            if tab["deleted"] and not show_deleted:
                continue
            ws_name = tab.get("workspace") or "No Workspace"
            if ws_name == "No Workspace":
                no_workspace.append(tab)
            else:
                if ws_name not in workspaces:
                    workspaces[ws_name] = []
                workspaces[ws_name].append(tab)

    for ws_name, tabs in sorted(workspaces.items()):
        tree = Tree(f"[bold green]📁 {ws_name}[/bold green] ({len(tabs)} tabs)")
        for tab in tabs[:50]:
            title = tab["title"][:60] + "..." if len(tab["title"]) > 60 else tab["title"]
            tree.add(f"[dim]{title}[/dim]")
        if len(tabs) > 50:
            tree.add(f"[dim]... and {len(tabs) - 50} more[/dim]")
        console.print(tree)

    if no_workspace:
        tree = Tree(f"[bold yellow]📁 No Workspace[/bold yellow] ({len(no_workspace)} tabs)")
        for tab in no_workspace[:20]:
            title = tab["title"][:60] + "..." if len(tab["title"]) > 60 else tab["title"]
            tree.add(f"[dim]{title}[/dim]")
        if len(no_workspace) > 20:
            tree.add(f"[dim]... and {len(no_workspace) - 20} more[/dim]")
        console.print(tree)


def display_by_window(result: dict, show_deleted: bool = False):
    """Display tabs by window."""
    for i, window in enumerate(result["windows"]):
        if window["deleted"] and not show_deleted:
            continue

        status = "🟢 ACTIVE" if window["active"] else ""
        if window["deleted"]:
            status = "🔴 DELETED"

        tab_count = sum(1 for t in window["tabs"] if not t["deleted"] or show_deleted)

        tree = Tree(f"[bold]Window {i + 1}[/bold] {status} ({tab_count} tabs)")

        for tab in window["tabs"]:
            if tab["deleted"] and not show_deleted:
                continue

            title = tab["title"][:60] + "..." if len(tab["title"]) > 60 else tab["title"]
            prefix = "→ " if tab["active"] else "  "
            ws = f" [cyan]📁{tab['workspace']}[/cyan]" if tab.get("workspace") else ""
            deleted = " [red][DELETED][/red]" if tab["deleted"] else ""

            tree.add(f"{prefix}[dim]{title}[/dim]{ws}{deleted}")

        console.print(tree)


if __name__ == "__main__":
    app()
