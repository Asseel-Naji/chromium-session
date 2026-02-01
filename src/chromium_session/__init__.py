"""Chromium-based browser session parser with workspace support."""

from .parser import SessionParser, load_vivaldi_workspaces, Workspace, Tab, Window
from .browsers import detect_browsers, detect_browser_profiles, Browser, BrowserProfile

__version__ = "0.1.0"
__all__ = [
    "SessionParser",
    "load_vivaldi_workspaces",
    "Workspace",
    "Tab",
    "Window",
    "detect_browsers",
    "detect_browser_profiles",
    "Browser",
    "BrowserProfile",
]
