"""
Browser detection and profile management for Chromium-based browsers.
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BrowserProfile:
    """A browser profile with its paths."""
    name: str
    path: Path
    sessions_path: Path
    preferences_path: Path

    @property
    def exists(self) -> bool:
        return self.path.exists()

    @property
    def has_sessions(self) -> bool:
        return self.sessions_path.exists()


@dataclass
class Browser:
    """A detected Chromium-based browser."""
    id: str  # Short identifier for CLI
    name: str  # Display name
    path: Path  # Base config path
    profiles: list[BrowserProfile] = field(default_factory=list)

    @property
    def exists(self) -> bool:
        return self.path.exists()


# Browser definitions: (id, name, config_dir_patterns)
BROWSER_DEFINITIONS = [
    # Google Chrome variants
    ("chrome", "Google Chrome", ["google-chrome", "Google/Chrome"]),
    ("chrome-beta", "Google Chrome Beta", ["google-chrome-beta", "Google/Chrome Beta"]),
    ("chrome-dev", "Google Chrome Dev", ["google-chrome-unstable", "Google/Chrome Dev"]),
    ("chrome-canary", "Google Chrome Canary", ["google-chrome-canary", "Google/Chrome Canary"]),
    
    # Chromium
    ("chromium", "Chromium", ["chromium", "Chromium"]),
    
    # Vivaldi
    ("vivaldi", "Vivaldi", ["vivaldi", "Vivaldi"]),
    ("vivaldi-snapshot", "Vivaldi Snapshot", ["vivaldi-snapshot", "Vivaldi Snapshot"]),
    
    # Brave
    ("brave", "Brave", ["BraveSoftware/Brave-Browser", "brave"]),
    ("brave-beta", "Brave Beta", ["BraveSoftware/Brave-Browser-Beta"]),
    ("brave-nightly", "Brave Nightly", ["BraveSoftware/Brave-Browser-Nightly"]),
    
    # Microsoft Edge
    ("edge", "Microsoft Edge", ["microsoft-edge", "Microsoft/Edge"]),
    ("edge-beta", "Microsoft Edge Beta", ["microsoft-edge-beta", "Microsoft/Edge Beta"]),
    ("edge-dev", "Microsoft Edge Dev", ["microsoft-edge-dev", "Microsoft/Edge Dev"]),
    
    # Opera
    ("opera", "Opera", ["opera", "Opera Software/Opera Stable"]),
    ("opera-beta", "Opera Beta", ["opera-beta", "Opera Software/Opera Next"]),
    ("opera-dev", "Opera Developer", ["opera-developer", "Opera Software/Opera Developer"]),
    
    # Other Chromium-based
    ("arc", "Arc", ["Arc", "arc"]),
    ("thorium", "Thorium", ["thorium", "Thorium"]),
    ("ungoogled", "Ungoogled Chromium", ["ungoogled-chromium"]),
]


def get_config_base() -> Path:
    """Get the base config directory."""
    return Path.home() / ".config"


def detect_browser_profiles(browser_path: Path) -> list[BrowserProfile]:
    """Detect all profiles in a browser directory."""
    profiles = []
    
    if not browser_path.exists():
        return profiles
    
    # Check for Default profile
    default_path = browser_path / "Default"
    if default_path.exists():
        profiles.append(BrowserProfile(
            name="Default",
            path=default_path,
            sessions_path=default_path / "Sessions",
            preferences_path=default_path / "Preferences",
        ))
    
    # Check for numbered profiles (Profile 1, Profile 2, etc.)
    for item in browser_path.iterdir():
        if item.is_dir() and item.name.startswith("Profile "):
            profiles.append(BrowserProfile(
                name=item.name,
                path=item,
                sessions_path=item / "Sessions",
                preferences_path=item / "Preferences",
            ))
    
    # Sort profiles: Default first, then by number
    def profile_sort_key(p: BrowserProfile) -> tuple[int, str]:
        if p.name == "Default":
            return (0, "")
        try:
            num = int(p.name.replace("Profile ", ""))
            return (1, f"{num:010d}")
        except ValueError:
            return (2, p.name)
    
    profiles.sort(key=profile_sort_key)
    return profiles


def detect_browsers(config_base: Path | None = None) -> list[Browser]:
    """Detect all installed Chromium-based browsers."""
    if config_base is None:
        config_base = get_config_base()
    
    browsers = []
    
    for browser_id, name, patterns in BROWSER_DEFINITIONS:
        for pattern in patterns:
            browser_path = config_base / pattern
            if browser_path.exists():
                profiles = detect_browser_profiles(browser_path)
                if profiles:  # Only add if has profiles
                    browsers.append(Browser(
                        id=browser_id,
                        name=name,
                        path=browser_path,
                        profiles=profiles,
                    ))
                break  # Found this browser, move to next
    
    return browsers


def get_browser_by_id(browser_id: str, config_base: Path | None = None) -> Browser | None:
    """Get a specific browser by its ID."""
    browsers = detect_browsers(config_base)
    for browser in browsers:
        if browser.id == browser_id:
            return browser
    return None


def get_browser_choices() -> list[str]:
    """Get list of available browser IDs for autocompletion."""
    return [b.id for b in detect_browsers()]


def get_profile_choices(browser_id: str) -> list[str]:
    """Get list of profile names for a browser."""
    browser = get_browser_by_id(browser_id)
    if browser:
        return [p.name for p in browser.profiles]
    return []
