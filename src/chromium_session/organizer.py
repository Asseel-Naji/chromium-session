"""
Tab organization utilities for session files.

Provides functionality to reorganize tabs by various criteria (domain, etc.)
while maintaining window structure.
"""

from urllib.parse import urlparse

from .parser import Tab, Window


def extract_domain(url: str) -> str:
    """
    Extract the domain from a URL.

    Args:
        url: URL string

    Returns:
        Domain string (e.g., "github.com"), or "local" for local URLs,
        or "unknown" for invalid URLs.
    """
    if not url:
        return "unknown"

    # Handle special cases
    if url.startswith("about:") or url.startswith("chrome://"):
        return "browser"
    if url.startswith("file://"):
        return "local"

    try:
        parsed = urlparse(url)
        domain = parsed.netloc

        # Remove port if present
        if ":" in domain:
            domain = domain.split(":")[0]

        # Remove www. prefix for cleaner grouping
        if domain.startswith("www."):
            domain = domain[4:]

        return domain if domain else "unknown"
    except Exception:
        return "unknown"


def get_tab_current_url(tab: Tab) -> str:
    """
    Get the current URL of a tab.

    Args:
        tab: Tab object

    Returns:
        Current URL string
    """
    for hist in tab.history:
        if hist.idx == tab.current_history_idx:
            return hist.url
    return ""


def organize_tabs_by_domain(windows: list[Window]) -> list[Window]:
    """
    Organize tabs within each window by domain.

    This function groups tabs by their domain while preserving:
    - Window structure (tabs stay in their original window)
    - Tab groups (maintained)
    - Active tab status
    - Deleted status

    Args:
        windows: List of Window objects

    Returns:
        New list of Window objects with reorganized tabs
    """
    new_windows = []

    for window in windows:
        if not window.tabs:
            new_windows.append(window)
            continue

        # Group tabs by domain
        domain_groups: dict[str, list[Tab]] = {}

        for tab in window.tabs:
            url = get_tab_current_url(tab)
            domain = extract_domain(url)

            if domain not in domain_groups:
                domain_groups[domain] = []
            domain_groups[domain].append(tab)

        # Sort domains alphabetically
        sorted_domains = sorted(domain_groups.keys())

        # Flatten tabs in domain order
        organized_tabs = []
        for domain in sorted_domains:
            # Within each domain, maintain original relative order
            tabs_in_domain = domain_groups[domain]
            tabs_in_domain.sort(key=lambda t: t.idx)
            organized_tabs.extend(tabs_in_domain)

        # Update tab indices
        for new_idx, tab in enumerate(organized_tabs):
            tab.idx = new_idx

        # Update active tab index if needed
        new_active_tab_idx = window.active_tab_idx
        if window.active_tab_idx >= 0 and window.active_tab_idx < len(window.tabs):
            original_active_tab = window.tabs[window.active_tab_idx]
            try:
                new_active_tab_idx = organized_tabs.index(original_active_tab)
            except ValueError:
                # Tab not found, keep original index
                pass

        # Create new window with organized tabs
        new_window = Window(
            id=window.id,
            active_tab_idx=new_active_tab_idx,
            deleted=window.deleted,
            tabs=organized_tabs,
        )

        new_windows.append(new_window)

    return new_windows


def sort_tabs_by_title(windows: list[Window]) -> list[Window]:
    """
    Sort tabs within each window alphabetically by title.

    Args:
        windows: List of Window objects

    Returns:
        New list of Window objects with sorted tabs
    """
    new_windows = []

    for window in windows:
        if not window.tabs:
            new_windows.append(window)
            continue

        # Sort tabs by title
        sorted_tabs = sorted(
            window.tabs,
            key=lambda t: next(
                (h.title.lower() for h in t.history if h.idx == t.current_history_idx),
                "",
            ),
        )

        # Update tab indices
        for new_idx, tab in enumerate(sorted_tabs):
            tab.idx = new_idx

        # Update active tab index
        new_active_tab_idx = window.active_tab_idx
        if window.active_tab_idx >= 0 and window.active_tab_idx < len(window.tabs):
            original_active_tab = window.tabs[window.active_tab_idx]
            try:
                new_active_tab_idx = sorted_tabs.index(original_active_tab)
            except ValueError:
                pass

        new_window = Window(
            id=window.id,
            active_tab_idx=new_active_tab_idx,
            deleted=window.deleted,
            tabs=sorted_tabs,
        )

        new_windows.append(new_window)

    return new_windows
