"""
Browser history parsing for Chromium-based browsers.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


@dataclass
class HistoryEntry:
    """A browser history entry."""

    id: int
    url: str
    title: str
    visit_count: int
    last_visit_time: datetime
    domain: str

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "visit_count": self.visit_count,
            "last_visit_time": self.last_visit_time.isoformat(),
            "domain": self.domain,
        }


def chromium_time_to_datetime(chromium_time: int) -> datetime:
    """
    Convert Chromium timestamp to Python datetime.

    Chromium timestamps are microseconds since 1601-01-01 00:00:00 UTC.
    """
    # Chromium epoch: January 1, 1601
    # Unix epoch: January 1, 1970
    # Difference in seconds: 11644473600
    CHROMIUM_EPOCH_OFFSET = 11644473600

    if chromium_time == 0:
        return datetime.fromtimestamp(0)

    # Convert microseconds to seconds and adjust for epoch difference
    unix_timestamp = (chromium_time / 1_000_000) - CHROMIUM_EPOCH_OFFSET
    return datetime.fromtimestamp(unix_timestamp)


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc or parsed.path.split("/")[0] if parsed.path else ""
    except Exception:
        return ""


class HistoryParser:
    """Parser for Chromium History SQLite database."""

    def __init__(self, history_path: Path):
        """Initialize the history parser."""
        if not history_path.exists():
            raise FileNotFoundError(f"History database not found: {history_path}")

        self.history_path = history_path

    def parse(
        self,
        limit: Optional[int] = None,
        search: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> list[HistoryEntry]:
        """
        Parse the history database and return entries.

        Args:
            limit: Maximum number of entries to return (default: all)
            search: Search term to filter URLs and titles
            domain: Domain to filter by

        Returns:
            List of HistoryEntry objects, sorted by last visit time (newest first)
        """
        # Build SQL query
        query = (
            "SELECT id, url, title, visit_count, last_visit_time FROM urls WHERE 1=1"
        )
        params: list = []

        # Add search filter
        if search:
            query += " AND (url LIKE ? OR title LIKE ?)"
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern])

        # Add domain filter
        if domain:
            query += " AND url LIKE ?"
            domain_pattern = f"%{domain}%"
            params.append(domain_pattern)

        # Order by last visit time (newest first)
        query += " ORDER BY last_visit_time DESC"

        # Add limit
        if limit:
            query += " LIMIT ?"
            params.append(limit)

        # Execute query
        entries = []
        try:
            # Connect in read-only mode to avoid locking issues
            conn = sqlite3.connect(f"file:{self.history_path}?mode=ro", uri=True)
            cursor = conn.cursor()

            cursor.execute(query, params)
            rows = cursor.fetchall()

            for row in rows:
                entry_id, url, title, visit_count, last_visit_time = row

                # Convert Chromium timestamp to datetime
                dt = chromium_time_to_datetime(last_visit_time)

                # Extract domain
                entry_domain = extract_domain(url)

                entry = HistoryEntry(
                    id=entry_id,
                    url=url,
                    title=title or "(No title)",
                    visit_count=visit_count,
                    last_visit_time=dt,
                    domain=entry_domain,
                )
                entries.append(entry)

            conn.close()

        except sqlite3.Error as e:
            raise RuntimeError(f"Failed to parse history database: {e}")

        return entries


def parse_history(
    profile_path: Path,
    limit: Optional[int] = None,
    search: Optional[str] = None,
    domain: Optional[str] = None,
) -> list[HistoryEntry]:
    """
    Parse browser history from a profile directory.

    Args:
        profile_path: Path to the browser profile directory
        limit: Maximum number of entries to return
        search: Search term to filter URLs and titles
        domain: Domain to filter by

    Returns:
        List of HistoryEntry objects
    """
    history_path = profile_path / "History"
    parser = HistoryParser(history_path)
    return parser.parse(limit=limit, search=search, domain=domain)
