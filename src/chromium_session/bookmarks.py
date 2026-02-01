"""
Parser for Chromium Bookmarks JSON files.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Bookmark:
    """A single bookmark entry."""

    name: str
    url: str
    date_added: int = 0
    guid: str = ""
    id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return {
            "name": self.name,
            "url": self.url,
            "date_added": self.date_added,
            "guid": self.guid,
            "id": self.id,
        }


@dataclass
class BookmarkFolder:
    """A bookmark folder that can contain bookmarks and subfolders."""

    name: str
    children: list["Bookmark | BookmarkFolder"] = field(default_factory=list)
    date_added: int = 0
    date_modified: int = 0
    guid: str = ""
    id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return {
            "name": self.name,
            "children": [child.to_dict() for child in self.children],
            "date_added": self.date_added,
            "date_modified": self.date_modified,
            "guid": self.guid,
            "id": self.id,
            "type": "folder",
        }


@dataclass
class BookmarksData:
    """Complete bookmarks data structure."""

    bookmark_bar: BookmarkFolder | None = None
    other: BookmarkFolder | None = None
    synced: BookmarkFolder | None = None
    mobile: BookmarkFolder | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON export."""
        result: dict[str, Any] = {}
        if self.bookmark_bar:
            result["bookmark_bar"] = self.bookmark_bar.to_dict()
        if self.other:
            result["other"] = self.other.to_dict()
        if self.synced:
            result["synced"] = self.synced.to_dict()
        if self.mobile:
            result["mobile"] = self.mobile.to_dict()
        return result


def parse_bookmark_node(node: dict[str, Any]) -> Bookmark | BookmarkFolder:
    """Parse a single bookmark node (either a bookmark or folder)."""
    node_type = node.get("type", "")

    if node_type == "url":
        return Bookmark(
            name=node.get("name", ""),
            url=node.get("url", ""),
            date_added=int(node.get("date_added", 0)),
            guid=node.get("guid", ""),
            id=node.get("id", ""),
        )
    elif node_type == "folder":
        folder = BookmarkFolder(
            name=node.get("name", ""),
            date_added=int(node.get("date_added", 0)),
            date_modified=int(node.get("date_modified", 0)),
            guid=node.get("guid", ""),
            id=node.get("id", ""),
        )

        # Parse children
        children = node.get("children", [])
        for child in children:
            folder.children.append(parse_bookmark_node(child))

        return folder
    else:
        # Unknown type, treat as empty folder
        return BookmarkFolder(name=node.get("name", "Unknown"))


def parse_bookmarks_file(bookmarks_path: Path) -> BookmarksData:
    """Parse a Chromium Bookmarks JSON file."""
    if not bookmarks_path.exists():
        raise FileNotFoundError(f"Bookmarks file not found: {bookmarks_path}")

    with open(bookmarks_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    roots = data.get("roots", {})

    bookmarks_data = BookmarksData()

    # Parse bookmark bar
    if "bookmark_bar" in roots:
        node = roots["bookmark_bar"]
        bookmarks_data.bookmark_bar = parse_bookmark_node(node)  # type: ignore

    # Parse other bookmarks
    if "other" in roots:
        node = roots["other"]
        bookmarks_data.other = parse_bookmark_node(node)  # type: ignore

    # Parse synced bookmarks
    if "synced" in roots:
        node = roots["synced"]
        bookmarks_data.synced = parse_bookmark_node(node)  # type: ignore

    # Parse mobile bookmarks (some browsers have this)
    if "mobile" in roots:
        node = roots["mobile"]
        bookmarks_data.mobile = parse_bookmark_node(node)  # type: ignore

    return bookmarks_data


def count_bookmarks(folder: BookmarkFolder) -> tuple[int, int]:
    """
    Count bookmarks and folders in a folder.

    Returns:
        (bookmark_count, folder_count)
    """
    bookmark_count = 0
    folder_count = 0

    for child in folder.children:
        if isinstance(child, Bookmark):
            bookmark_count += 1
        elif isinstance(child, BookmarkFolder):
            folder_count += 1
            sub_bookmarks, sub_folders = count_bookmarks(child)
            bookmark_count += sub_bookmarks
            folder_count += sub_folders

    return bookmark_count, folder_count
