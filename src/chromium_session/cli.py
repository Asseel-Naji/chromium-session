"""
Typer CLI for Chromium Session Parser.
"""

import csv
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from .bookmarks import (
    Bookmark,
    BookmarkFolder,
    count_bookmarks,
    parse_bookmarks_file,
)
from .browsers import (
    Browser,
    BrowserProfile,
    detect_browsers,
    find_latest_session,
    get_browser_by_id,
    get_browser_choices,
    get_profile_choices,
)
from .history import parse_history
from .organizer import organize_tabs_by_domain, sort_tabs_by_title
from .parser import SessionParser, load_vivaldi_workspaces
from .writer import SessionWriter

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


def get_selected_profile(
    browser: Browser, profile_name: str | None
) -> BrowserProfile | None:
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


def export_to_csv(all_results: list[dict], show_deleted: bool = False):
    """Export session data to CSV format."""
    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=[
            "browser",
            "profile",
            "window_id",
            "tab_id",
            "title",
            "url",
            "workspace",
            "active",
            "deleted",
        ],
        lineterminator="\n",
    )
    writer.writeheader()

    for result in all_results:
        browser = result.get("_browser", "")
        profile = result.get("_profile", "")

        for window_idx, window in enumerate(result.get("windows", [])):
            if window["deleted"] and not show_deleted:
                continue

            window_id = window_idx + 1

            for tab_idx, tab in enumerate(window.get("tabs", [])):
                if tab["deleted"] and not show_deleted:
                    continue

                tab_id = tab_idx + 1
                workspace = tab.get("workspace", "")

                writer.writerow(
                    {
                        "browser": browser,
                        "profile": profile,
                        "window_id": window_id,
                        "tab_id": tab_id,
                        "title": tab.get("title", ""),
                        "url": tab.get("url", ""),
                        "workspace": workspace,
                        "active": str(tab.get("active", False)).lower(),
                        "deleted": str(tab.get("deleted", False)).lower(),
                    }
                )


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
        Optional[str],
        typer.Option(
            "--browser",
            "-b",
            help="Browser to use (auto-detected if not specified)",
            autocompletion=complete_browser,
        ),
    ] = None,
    profile: Annotated[
        Optional[str],
        typer.Option(
            "--profile", "-p", help="Profile name", autocompletion=complete_profile
        ),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help="Output as JSON")
    ] = False,
):
    """List defined workspaces (Vivaldi only)."""
    # Auto-detect browser and profile if not specified
    if browser is None:
        result = find_latest_session()
        if result is None:
            rprint("[red]No session files found in any browser profile[/red]")
            rprint("[dim]Run 'chromium-session list' to see available browsers[/dim]")
            raise typer.Exit(1)

        browser_obj, profile_obj, _ = result
        if not json_output:
            rprint(
                f"[dim]Auto-detected: {browser_obj.name} / {profile_obj.name}[/dim]\n"
            )
    else:
        browser_obj = get_browser_by_id(browser)
        if not browser_obj:
            rprint(
                f"[red]Browser '{browser}' not found. Run 'chromium-session list' to see available browsers.[/red]"
            )
            raise typer.Exit(1)

        profile_obj = get_selected_profile(browser_obj, profile)
        if not profile_obj:
            rprint(f"[red]No profiles found for {browser_obj.name}[/red]")
            raise typer.Exit(1)

    ws = load_vivaldi_workspaces(profile_obj.path)

    if not ws:
        rprint("[yellow]No workspaces found (workspaces are Vivaldi-specific)[/yellow]")
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
        Optional[str],
        typer.Option(
            "--browser",
            "-b",
            help="Browser to use (auto-detected if not specified)",
            autocompletion=complete_browser,
        ),
    ] = None,
    files: Annotated[
        Optional[list[Path]],
        typer.Argument(help="Session file(s) to parse"),
    ] = None,
    profile: Annotated[
        Optional[str],
        typer.Option(
            "--profile", "-p", help="Profile name", autocompletion=complete_profile
        ),
    ] = None,
    latest: Annotated[
        int, typer.Option("--latest", "-n", help="Parse only N most recent files")
    ] = 1,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help="Output as JSON")
    ] = False,
    csv_output: Annotated[
        bool, typer.Option("--csv", "-c", help="Output as CSV")
    ] = False,
    show_deleted: Annotated[
        bool, typer.Option("--show-deleted", help="Include deleted tabs/windows")
    ] = False,
    by_workspace: Annotated[
        bool,
        typer.Option("--by-workspace", "-W", help="Group tabs by workspace (Vivaldi)"),
    ] = False,
):
    """Parse session files and display tabs."""
    # Validate mutually exclusive flags
    if json_output and csv_output:
        rprint("[red]Error: --json and --csv flags are mutually exclusive[/red]")
        raise typer.Exit(1)

    # Auto-detect browser and profile if not specified
    if browser is None:
        result = find_latest_session()
        if result is None:
            rprint("[red]No session files found in any browser profile[/red]")
            rprint("[dim]Run 'chromium-session list' to see available browsers[/dim]")
            raise typer.Exit(1)

        browser_obj, profile_obj, _ = result
        if not json_output and not csv_output:
            rprint(
                f"[dim]Auto-detected: {browser_obj.name} / {profile_obj.name}[/dim]\n"
            )
    else:
        browser_obj = get_browser_by_id(browser)
        if not browser_obj:
            rprint(
                f"[red]Browser '{browser}' not found. Run 'chromium-session list' to see available browsers.[/red]"
            )
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

            if not json_output and not csv_output:
                rprint(
                    f"\n[bold cyan]# {browser_obj.name} / {profile_obj.name}[/bold cyan]"
                )
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
    elif csv_output:
        export_to_csv(all_results, show_deleted=show_deleted)


@app.command()
def summary(
    browser: Annotated[
        Optional[str],
        typer.Option(
            "--browser",
            "-b",
            help="Browser to use (auto-detected if not specified)",
            autocompletion=complete_browser,
        ),
    ] = None,
    profile: Annotated[
        Optional[str],
        typer.Option(
            "--profile", "-p", help="Profile name", autocompletion=complete_profile
        ),
    ] = None,
):
    """Show a quick summary of session stats."""
    # Auto-detect browser and profile if not specified
    if browser is None:
        result = find_latest_session()
        if result is None:
            rprint("[red]No session files found in any browser profile[/red]")
            rprint("[dim]Run 'chromium-session list' to see available browsers[/dim]")
            raise typer.Exit(1)

        browser_obj, profile_obj, _ = result
        rprint(f"[dim]Auto-detected: {browser_obj.name} / {profile_obj.name}[/dim]\n")
    else:
        browser_obj = get_browser_by_id(browser)
        if not browser_obj:
            rprint(
                f"[red]Browser '{browser}' not found. Run 'chromium-session list' to see available browsers.[/red]"
            )
            raise typer.Exit(1)

        profile_obj = get_selected_profile(browser_obj, profile)
        if not profile_obj:
            rprint(f"[red]No profiles found for {browser_obj.name}[/red]")
            raise typer.Exit(1)

    workspaces_map = load_vivaldi_workspaces(profile_obj.path)

    if not profile_obj.has_sessions:
        rprint("[red]No sessions directory found[/red]")
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
        rprint(
            f"[red]Browser '{browser}' not found. Run 'chromium-session list' to see available browsers.[/red]"
        )
        raise typer.Exit(1)

    table = Table(title=f"Profiles for {browser_obj.name}")
    table.add_column("Name", style="cyan")
    table.add_column("Has Sessions", style="green")
    table.add_column("Path", style="dim")

    for p in browser_obj.profiles:
        has_sessions = "✓" if p.has_sessions else "✗"
        table.add_row(p.name, has_sessions, str(p.path))

    console.print(table)


@app.command()
def bookmarks(
    browser: Annotated[
        Optional[str],
        typer.Option(
            "--browser",
            "-b",
            help="Browser to use (auto-detected if not specified)",
            autocompletion=complete_browser,
        ),
    ] = None,
    profile: Annotated[
        Optional[str],
        typer.Option(
            "--profile", "-p", help="Profile name", autocompletion=complete_profile
        ),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help="Output as JSON")
    ] = False,
):
    """Display bookmarks with folder structure."""
    # Auto-detect browser and profile if not specified
    if browser is None:
        result = find_latest_session()
        if result is None:
            rprint("[red]No session files found in any browser profile[/red]")
            rprint("[dim]Run 'chromium-session list' to see available browsers[/dim]")
            raise typer.Exit(1)

        browser_obj, profile_obj, _ = result
        if not json_output:
            rprint(
                f"[dim]Auto-detected: {browser_obj.name} / {profile_obj.name}[/dim]\n"
            )
    else:
        browser_obj = get_browser_by_id(browser)
        if not browser_obj:
            rprint(
                f"[red]Browser '{browser}' not found. Run 'chromium-session list' to see available browsers.[/red]"
            )
            raise typer.Exit(1)

        profile_obj = get_selected_profile(browser_obj, profile)
        if not profile_obj:
            rprint(f"[red]No profiles found for {browser_obj.name}[/red]")
            raise typer.Exit(1)

    bookmarks_path = profile_obj.path / "Bookmarks"

    if not bookmarks_path.exists():
        rprint(f"[red]Bookmarks file not found: {bookmarks_path}[/red]")
        raise typer.Exit(1)

    try:
        bookmarks_data = parse_bookmarks_file(bookmarks_path)

        if json_output:
            print(json.dumps(bookmarks_data.to_dict(), indent=2))
            return

        # Display bookmarks with Rich Tree
        rprint(f"\n[bold cyan]# {browser_obj.name} / {profile_obj.name}[/bold cyan]")
        rprint(f"[dim]# Bookmarks from: {bookmarks_path}[/dim]\n")

        # Display bookmark bar
        if bookmarks_data.bookmark_bar and bookmarks_data.bookmark_bar.children:
            bookmark_count, folder_count = count_bookmarks(bookmarks_data.bookmark_bar)
            display_bookmark_folder(
                bookmarks_data.bookmark_bar,
                "Bookmarks Bar",
                bookmark_count,
                folder_count,
            )

        # Display other bookmarks
        if bookmarks_data.other and bookmarks_data.other.children:
            bookmark_count, folder_count = count_bookmarks(bookmarks_data.other)
            display_bookmark_folder(
                bookmarks_data.other, "Other Bookmarks", bookmark_count, folder_count
            )

        # Display synced bookmarks
        if bookmarks_data.synced and bookmarks_data.synced.children:
            bookmark_count, folder_count = count_bookmarks(bookmarks_data.synced)
            display_bookmark_folder(
                bookmarks_data.synced, "Synced Bookmarks", bookmark_count, folder_count
            )

        # Display mobile bookmarks
        if bookmarks_data.mobile and bookmarks_data.mobile.children:
            bookmark_count, folder_count = count_bookmarks(bookmarks_data.mobile)
            display_bookmark_folder(
                bookmarks_data.mobile, "Mobile Bookmarks", bookmark_count, folder_count
            )

    except Exception as e:
        rprint(f"[red]Error parsing bookmarks: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def history(
    browser: Annotated[
        Optional[str],
        typer.Option(
            "--browser",
            "-b",
            help="Browser to use (auto-detected if not specified)",
            autocompletion=complete_browser,
        ),
    ] = None,
    profile: Annotated[
        Optional[str],
        typer.Option(
            "--profile", "-p", help="Profile name", autocompletion=complete_profile
        ),
    ] = None,
    limit: Annotated[
        Optional[int],
        typer.Option("--limit", "-n", help="Maximum number of entries to show"),
    ] = 50,
    search: Annotated[
        Optional[str],
        typer.Option("--search", "-s", help="Search term to filter URLs and titles"),
    ] = None,
    domain: Annotated[
        Optional[str],
        typer.Option("--domain", "-d", help="Filter by domain"),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", "-j", help="Output as JSON")
    ] = False,
):
    """Display browsing history."""
    # Auto-detect browser and profile if not specified
    if browser is None:
        result = find_latest_session()
        if result is None:
            rprint("[red]No session files found in any browser profile[/red]")
            rprint("[dim]Run 'chromium-session list' to see available browsers[/dim]")
            raise typer.Exit(1)

        browser_obj, profile_obj, _ = result
        if not json_output:
            rprint(
                f"[dim]Auto-detected: {browser_obj.name} / {profile_obj.name}[/dim]\n"
            )
    else:
        browser_obj = get_browser_by_id(browser)
        if not browser_obj:
            rprint(
                f"[red]Browser '{browser}' not found. Run 'chromium-session list' to see available browsers.[/red]"
            )
            raise typer.Exit(1)

        profile_obj = get_selected_profile(browser_obj, profile)
        if not profile_obj:
            rprint(f"[red]No profiles found for {browser_obj.name}[/red]")
            raise typer.Exit(1)

    try:
        entries = parse_history(
            profile_obj.path,
            limit=limit,
            search=search,
            domain=domain,
        )

        if not entries:
            rprint("[yellow]No history entries found[/yellow]")
            raise typer.Exit(0)

        if json_output:
            output = [entry.to_dict() for entry in entries]
            print(json.dumps(output, indent=2))
            return

        # Display as table
        rprint(f"\n[bold cyan]{browser_obj.name} / {profile_obj.name}[/bold cyan]")
        if search:
            rprint(f"[dim]Search: {search}[/dim]")
        if domain:
            rprint(f"[dim]Domain: {domain}[/dim]")

        table = Table(title="Browsing History")
        table.add_column("Title", style="green", no_wrap=False, max_width=50)
        table.add_column("URL", style="cyan", no_wrap=False, max_width=60)
        table.add_column("Domain", style="yellow", max_width=25)
        table.add_column("Visits", style="magenta", justify="right")
        table.add_column("Last Visit", style="dim")

        for entry in entries:
            # Truncate title if too long
            title = entry.title[:47] + "..." if len(entry.title) > 50 else entry.title

            # Truncate URL if too long
            url = entry.url[:57] + "..." if len(entry.url) > 60 else entry.url

            # Format datetime
            last_visit = entry.last_visit_time.strftime("%Y-%m-%d %H:%M")

            table.add_row(
                title,
                url,
                entry.domain,
                str(entry.visit_count),
                last_visit,
            )

        console.print(table)
        rprint(f"\n[dim]Showing {len(entries)} entries[/dim]")

    except FileNotFoundError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except RuntimeError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1)


def display_bookmark_folder(
    folder: BookmarkFolder, title: str, bookmark_count: int, folder_count: int
):
    """Display a bookmark folder with its contents using Rich Tree."""
    tree = Tree(
        f"[bold green]{title}[/bold green] ({bookmark_count} bookmarks, {folder_count} folders)"
    )
    _add_children_to_tree(tree, folder.children)
    console.print(tree)


def _add_children_to_tree(
    tree: Tree,
    children: list[Bookmark | BookmarkFolder],
    depth: int = 0,
    max_depth: int = 10,
):
    """Recursively add bookmark children to tree."""
    if depth > max_depth:
        tree.add("[dim]... (max depth reached)[/dim]")
        return

    for child in children:
        if isinstance(child, Bookmark):
            # Display bookmark
            name = child.name if child.name else "[untitled]"
            url_preview = child.url[:60] + "..." if len(child.url) > 60 else child.url
            tree.add(f"[cyan]{name}[/cyan] [dim]{url_preview}[/dim]")
        elif isinstance(child, BookmarkFolder):
            # Display folder
            folder_name = child.name if child.name else "[untitled folder]"
            bookmark_count, folder_count = count_bookmarks(child)
            subtree = tree.add(
                f"[bold yellow]📁 {folder_name}[/bold yellow] ({bookmark_count} bookmarks, {folder_count} folders)"
            )
            _add_children_to_tree(subtree, child.children, depth + 1, max_depth)


def display_result(
    result: dict, show_deleted: bool = False, by_workspace: bool = False
):
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
            title = (
                tab["title"][:60] + "..." if len(tab["title"]) > 60 else tab["title"]
            )
            tree.add(f"[dim]{title}[/dim]")
        if len(tabs) > 50:
            tree.add(f"[dim]... and {len(tabs) - 50} more[/dim]")
        console.print(tree)

    if no_workspace:
        tree = Tree(
            f"[bold yellow]📁 No Workspace[/bold yellow] ({len(no_workspace)} tabs)"
        )
        for tab in no_workspace[:20]:
            title = (
                tab["title"][:60] + "..." if len(tab["title"]) > 60 else tab["title"]
            )
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

            title = (
                tab["title"][:60] + "..." if len(tab["title"]) > 60 else tab["title"]
            )
            prefix = "→ " if tab["active"] else "  "
            ws = f" [cyan]📁{tab['workspace']}[/cyan]" if tab.get("workspace") else ""
            deleted = " [red][DELETED][/red]" if tab["deleted"] else ""

            tree.add(f"{prefix}[dim]{title}[/dim]{ws}{deleted}")

        console.print(tree)


@app.command()
def organize(
    browser: Annotated[
        Optional[str],
        typer.Option(
            "--browser",
            "-b",
            help="Browser to use (auto-detected if not specified)",
            autocompletion=complete_browser,
        ),
    ] = None,
    profile: Annotated[
        Optional[str],
        typer.Option(
            "--profile", "-p", help="Profile name", autocompletion=complete_profile
        ),
    ] = None,
    by_domain: Annotated[
        bool,
        typer.Option("--by-domain", "-d", help="Organize tabs by domain"),
    ] = False,
    by_title: Annotated[
        bool,
        typer.Option("--by-title", "-t", help="Sort tabs alphabetically by title"),
    ] = False,
    session_file: Annotated[
        Optional[Path],
        typer.Option("--file", "-f", help="Specific session file to organize"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview changes without writing to file"),
    ] = False,
):
    """Organize tabs in session file by domain or title."""
    # Validate flags
    if not by_domain and not by_title:
        rprint(
            "[red]Error: Must specify at least one organization method (--by-domain or --by-title)[/red]"
        )
        raise typer.Exit(1)

    if by_domain and by_title:
        rprint("[red]Error: --by-domain and --by-title are mutually exclusive[/red]")
        raise typer.Exit(1)

    # Auto-detect browser and profile if not specified
    if browser is None:
        result = find_latest_session()
        if result is None:
            rprint("[red]No session files found in any browser profile[/red]")
            rprint("[dim]Run 'chromium-session list' to see available browsers[/dim]")
            raise typer.Exit(1)

        browser_obj, profile_obj, detected_session = result
        if session_file is None:
            session_file = detected_session
        rprint(f"[dim]Auto-detected: {browser_obj.name} / {profile_obj.name}[/dim]\n")
    else:
        browser_obj = get_browser_by_id(browser)
        if not browser_obj:
            rprint(
                f"[red]Browser '{browser}' not found. Run 'chromium-session list' to see available browsers.[/red]"
            )
            raise typer.Exit(1)

        profile_obj = get_selected_profile(browser_obj, profile)
        if not profile_obj:
            rprint(f"[red]No profiles found for {browser_obj.name}[/red]")
            raise typer.Exit(1)

        # Find session file if not specified
        if session_file is None:
            if not profile_obj.has_sessions:
                rprint("[red]No sessions directory found[/red]")
                raise typer.Exit(1)

            files = list_session_files(profile_obj.sessions_path)
            if not files:
                rprint("[red]No session files found[/red]")
                raise typer.Exit(1)

            session_file = files[0]

    if not session_file.exists():
        rprint(f"[red]Session file not found: {session_file}[/red]")
        raise typer.Exit(1)

    # Parse the session file
    rprint(f"[cyan]Reading session file:[/cyan] {session_file}")
    workspaces_map = load_vivaldi_workspaces(profile_obj.path)
    parser = SessionParser(workspaces=workspaces_map)

    try:
        parser.parse_file(session_file)
    except Exception as e:
        rprint(f"[red]Error parsing session file: {e}[/red]")
        raise typer.Exit(1)

    # Get original windows
    original_windows = list(parser.windows.values())
    total_tabs = sum(len(w.tabs) for w in original_windows)

    # Organize tabs
    rprint(
        f"[cyan]Organizing {total_tabs} tabs in {len(original_windows)} windows...[/cyan]"
    )

    if by_domain:
        organized_windows = organize_tabs_by_domain(original_windows)
        method = "domain"
    else:
        organized_windows = sort_tabs_by_title(original_windows)
        method = "title"

    # Display preview
    rprint(f"\n[bold green]Preview of organized session (by {method}):[/bold green]\n")

    for i, window in enumerate(organized_windows):
        if window.deleted:
            continue

        tab_count = sum(1 for t in window.tabs if not t.deleted)
        tree = Tree(f"[bold]Window {i + 1}[/bold] ({tab_count} tabs)")

        for tab in window.tabs:
            if tab.deleted:
                continue

            # Get current URL and title
            url = ""
            title = ""
            for hist in tab.history:
                if hist.idx == tab.current_history_idx:
                    url = hist.url
                    title = hist.title
                    break

            # Extract domain for display
            from .organizer import extract_domain

            domain = extract_domain(url)

            title_display = title[:50] + "..." if len(title) > 50 else title
            tree.add(f"[dim]{title_display}[/dim] [yellow]({domain})[/yellow]")

        console.print(tree)

    if dry_run:
        rprint("\n[yellow]Dry run - no changes written[/yellow]")
        return

    # Create backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = session_file.parent / f"{session_file.name}.backup_{timestamp}"

    try:
        shutil.copy2(session_file, backup_file)
        rprint(f"\n[green]Backup created:[/green] {backup_file}")
    except Exception as e:
        rprint(f"[red]Error creating backup: {e}[/red]")
        raise typer.Exit(1)

    # Write organized session
    writer = SessionWriter(version=1)

    try:
        writer.write_session(
            windows=organized_windows,
            groups=parser.groups,
            active_window=parser.active_window,
        )
        writer.save(session_file)
        rprint("[bold green]Session file organized successfully![/bold green]")
        rprint(f"[dim]File: {session_file}[/dim]")
    except Exception as e:
        rprint(f"[red]Error writing session file: {e}[/red]")
        rprint("[yellow]Restoring from backup...[/yellow]")
        try:
            shutil.copy2(backup_file, session_file)
            rprint("[green]Backup restored successfully[/green]")
        except Exception as restore_error:
            rprint(f"[red]Error restoring backup: {restore_error}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
