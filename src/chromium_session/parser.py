"""
Core parser for Vivaldi/Chrome SNSS session files.

Based on: https://github.com/lachlanallison/chrome-session-viewer
"""

import json
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Command constants from Chrome source
class Commands:
    SET_TAB_WINDOW = 0
    SET_TAB_INDEX_IN_WINDOW = 2
    UPDATE_TAB_NAVIGATION = 6
    SET_SELECTED_NAVIGATION_INDEX = 7
    SET_SELECTED_TAB_IN_INDEX = 8
    TAB_CLOSED = 16
    WINDOW_CLOSED = 17
    SET_ACTIVE_WINDOW = 20
    LAST_ACTIVE_TIME = 21
    SET_TAB_GROUP = 25
    SET_TAB_GROUP_METADATA2 = 27


@dataclass
class Workspace:
    id: int
    name: str
    emoji: str = ""


@dataclass
class HistoryItem:
    idx: int
    url: str = ""
    title: str = ""


@dataclass
class TabGroup:
    high: int
    low: int
    name: str = ""

    @property
    def key(self) -> str:
        return f"{self.high:x}{self.low:x}"


@dataclass
class Tab:
    id: int
    history: list[HistoryItem] = field(default_factory=list)
    idx: int = 0
    win: int = 0
    deleted: bool = False
    current_history_idx: int = 0
    group: Optional[TabGroup] = None
    workspace_id: Optional[int] = None


@dataclass
class Window:
    id: int
    active_tab_idx: int = -1
    deleted: bool = False
    tabs: list[Tab] = field(default_factory=list)


def load_vivaldi_workspaces(
    profile_path: str | Path | None = None,
) -> dict[int, Workspace]:
    """Load workspace definitions from Vivaldi Preferences file."""
    if profile_path is None:
        profile_path = Path.home() / ".config/vivaldi/Profile 2"
    else:
        profile_path = Path(profile_path)

    prefs_file = profile_path / "Preferences"
    if not prefs_file.exists():
        return {}

    try:
        with open(prefs_file, "r", encoding="utf-8") as f:
            prefs = json.load(f)

        workspaces = {}
        ws_list = prefs.get("vivaldi", {}).get("workspaces", {}).get("list", [])

        for ws in ws_list:
            ws_id = int(ws.get("id", 0))
            workspaces[ws_id] = Workspace(
                id=ws_id,
                name=ws.get("name", ""),
                emoji=ws.get("emoji", ""),
            )

        return workspaces
    except Exception:
        return {}


def extract_workspace_ids_from_session(session_data: bytes) -> dict[str, int]:
    """Extract URL to workspace ID mappings from Vivaldi session data."""
    url_workspace_map = {}

    try:
        text = session_data.decode("latin-1")

        # Pattern: "urlForThumbnail":"<url>","workspaceId":<id>
        pattern = r'"urlForThumbnail":"([^"]+)","workspaceId":([0-9.e+]+)'
        matches = re.findall(pattern, text)

        for url, ws_id in matches:
            try:
                ws_id_int = int(float(ws_id))
                url_workspace_map[url] = ws_id_int
            except ValueError:
                pass

        # Also try reverse pattern
        ext_pattern = r'"workspaceId":([0-9.e+]+)[^}]*"url":"([^"]+)"'
        matches2 = re.findall(ext_pattern, text)
        for ws_id, url in matches2:
            try:
                ws_id_int = int(float(ws_id))
                url_workspace_map[url] = ws_id_int
            except ValueError:
                pass

    except Exception:
        pass

    return url_workspace_map


class SessionParser:
    """Parser for Chrome/Vivaldi SNSS session files."""

    def __init__(self, workspaces: dict[int, Workspace] | None = None):
        self.tabs: dict[int, Tab] = {}
        self.windows: dict[int, Window] = {}
        self.groups: dict[str, TabGroup] = {}
        self.active_window: Optional[Window] = None
        self._buffer: bytes = b""
        self.workspaces = workspaces or {}
        self._url_workspace_map: dict[str, int] = {}

    def reset(self):
        """Reset parser state for parsing a new file."""
        self.tabs.clear()
        self.windows.clear()
        self.groups.clear()
        self.active_window = None
        self._buffer = b""
        self._url_workspace_map.clear()

    def _read_uint8(self, offset: int) -> int:
        if offset >= len(self._buffer):
            raise ValueError(f"Offset {offset} out of bounds")
        return self._buffer[offset]

    def _read_uint16(self, offset: int) -> int:
        if offset + 1 >= len(self._buffer):
            raise ValueError(f"Offset {offset} out of bounds")
        return struct.unpack_from("<H", self._buffer, offset)[0]

    def _read_uint32(self, offset: int) -> int:
        if offset + 3 >= len(self._buffer):
            raise ValueError(f"Offset {offset} out of bounds")
        return struct.unpack_from("<I", self._buffer, offset)[0]

    def _read_uint64(self, offset: int) -> int:
        if offset + 7 >= len(self._buffer):
            raise ValueError(f"Offset {offset} out of bounds")
        return struct.unpack_from("<Q", self._buffer, offset)[0]

    def _read_string(self, data: bytes, offset: int) -> tuple[str, int]:
        """Read a pickled UTF-8 string. Returns (value, bytes_read)."""
        if offset + 3 >= len(data):
            raise ValueError(f"Offset {offset} out of bounds")

        size = struct.unpack_from("<I", data, offset)[0]
        real_size = size
        if real_size % 4 != 0:
            real_size += 4 - (real_size % 4)

        if offset + 4 + size > len(data):
            raise ValueError(f"String size {size} exceeds buffer bounds")

        value = data[offset + 4 : offset + 4 + size].decode("utf-8", errors="replace")
        return value, 4 + real_size

    def _read_string16(self, data: bytes, offset: int) -> tuple[str, int]:
        """Read a pickled UTF-16 string. Returns (value, bytes_read)."""
        if offset + 3 >= len(data):
            raise ValueError(f"Offset {offset} out of bounds")

        size = struct.unpack_from("<I", data, offset)[0]
        real_size = size * 2
        if real_size % 4 != 0:
            real_size += 4 - (real_size % 4)

        if offset + 4 + real_size > len(data):
            raise ValueError(f"String16 size {real_size} exceeds buffer bounds")

        raw_bytes = data[offset + 4 : offset + 4 + size * 2]
        value = raw_bytes.decode("utf-16-le", errors="replace")
        return value, 4 + real_size

    def _get_window(self, window_id: int) -> Window:
        if window_id not in self.windows:
            self.windows[window_id] = Window(id=window_id)
        return self.windows[window_id]

    def _get_tab(self, tab_id: int) -> Tab:
        if tab_id not in self.tabs:
            self.tabs[tab_id] = Tab(id=tab_id)
        return self.tabs[tab_id]

    def _get_group(self, high: int, low: int) -> TabGroup:
        key = f"{high:x}{low:x}"
        if key not in self.groups:
            self.groups[key] = TabGroup(high=high, low=low)
        return self.groups[key]

    def _process_command(self, cmd_type: int, data: bytes):
        """Process a single SNSS command."""
        offset = 0

        try:
            if cmd_type == Commands.UPDATE_TAB_NAVIGATION:
                if len(data) < 12:
                    return
                offset += 4
                tab_id = struct.unpack_from("<I", data, offset)[0]
                offset += 4
                hist_idx = struct.unpack_from("<I", data, offset)[0]
                offset += 4
                url, bytes_read = self._read_string(data, offset)
                offset += bytes_read
                title, _ = self._read_string16(data, offset)

                tab = self._get_tab(tab_id)
                hist_item = next((h for h in tab.history if h.idx == hist_idx), None)
                if hist_item is None:
                    hist_item = HistoryItem(idx=hist_idx)
                    tab.history.append(hist_item)
                hist_item.url = url
                hist_item.title = title

            elif cmd_type == Commands.SET_SELECTED_TAB_IN_INDEX:
                if len(data) < 8:
                    return
                window_id = struct.unpack_from("<I", data, offset)[0]
                offset += 4
                idx = struct.unpack_from("<I", data, offset)[0]
                self._get_window(window_id).active_tab_idx = idx

            elif cmd_type == Commands.SET_TAB_GROUP_METADATA2:
                if len(data) < 20:
                    return
                offset += 4
                high = struct.unpack_from("<Q", data, offset)[0]
                offset += 8
                low = struct.unpack_from("<Q", data, offset)[0]
                offset += 8
                name, _ = self._read_string16(data, offset)
                self._get_group(high, low).name = name

            elif cmd_type == Commands.SET_TAB_GROUP:
                if len(data) < 24:
                    return
                tab_id = struct.unpack_from("<I", data, offset)[0]
                offset += 8
                high = struct.unpack_from("<Q", data, offset)[0]
                offset += 8
                low = struct.unpack_from("<Q", data, offset)[0]
                self._get_tab(tab_id).group = self._get_group(high, low)

            elif cmd_type == Commands.SET_TAB_WINDOW:
                if len(data) < 8:
                    return
                win = struct.unpack_from("<I", data, offset)[0]
                offset += 4
                tab_id = struct.unpack_from("<I", data, offset)[0]
                self._get_tab(tab_id).win = win

            elif cmd_type == Commands.WINDOW_CLOSED:
                if len(data) < 4:
                    return
                window_id = struct.unpack_from("<I", data, offset)[0]
                self._get_window(window_id).deleted = True

            elif cmd_type == Commands.TAB_CLOSED:
                if len(data) < 4:
                    return
                tab_id = struct.unpack_from("<I", data, offset)[0]
                self._get_tab(tab_id).deleted = True

            elif cmd_type == Commands.SET_TAB_INDEX_IN_WINDOW:
                if len(data) < 8:
                    return
                tab_id = struct.unpack_from("<I", data, offset)[0]
                offset += 4
                idx = struct.unpack_from("<I", data, offset)[0]
                self._get_tab(tab_id).idx = idx

            elif cmd_type == Commands.SET_ACTIVE_WINDOW:
                if len(data) < 4:
                    return
                window_id = struct.unpack_from("<I", data, offset)[0]
                self.active_window = self._get_window(window_id)

            elif cmd_type == Commands.SET_SELECTED_NAVIGATION_INDEX:
                if len(data) < 8:
                    return
                tab_id = struct.unpack_from("<I", data, offset)[0]
                offset += 4
                idx = struct.unpack_from("<I", data, offset)[0]
                self._get_tab(tab_id).current_history_idx = idx

        except Exception:
            pass

    def parse_file(self, filepath: str | Path) -> dict:
        """Parse an SNSS session file and return structured data."""
        self.reset()
        filepath = Path(filepath)

        with open(filepath, "rb") as f:
            self._buffer = f.read()

        if len(self._buffer) < 8:
            raise ValueError("File too small to be a valid SNSS file")

        # Extract Vivaldi workspace mappings
        self._url_workspace_map = extract_workspace_ids_from_session(self._buffer)

        # Check magic number "SNSS"
        magic = self._buffer[:4]
        if magic != b"SNSS":
            raise ValueError(f"Invalid SNSS file: expected magic 'SNSS', got {magic!r}")

        version = self._read_uint32(4)
        if version not in (1, 3):
            raise ValueError(f"Unsupported SNSS version: {version}")

        offset = 8

        while offset < len(self._buffer):
            if offset + 2 >= len(self._buffer):
                break
            try:
                cmd_size = self._read_uint16(offset) - 1
                offset += 2
                cmd_type = self._read_uint8(offset)
                offset += 1
                if offset + cmd_size > len(self._buffer):
                    break
                cmd_data = self._buffer[offset : offset + cmd_size]
                self._process_command(cmd_type, cmd_data)
                offset += cmd_size
            except Exception:
                break

        return self._build_result()

    def _build_result(self) -> dict:
        """Build the final result structure."""
        for tab in self.tabs.values():
            tab.history.sort(key=lambda h: h.idx)
            window = self._get_window(tab.win)
            window.tabs.append(tab)

        for window in self.windows.values():
            window.tabs.sort(key=lambda t: t.idx)

        windows = []

        for window in self.windows.values():
            result_window = {
                "id": window.id,
                "active": window == self.active_window and not window.deleted,
                "deleted": window.deleted,
                "tabs": [],
            }

            non_deleted_tab_idx = 0
            for tab in window.tabs:
                group_name = tab.group.name if tab.group else ""
                is_active = (
                    not tab.deleted
                    and not window.deleted
                    and window.active_tab_idx >= 0
                    and non_deleted_tab_idx == window.active_tab_idx
                )

                result_tab = {
                    "id": tab.id,
                    "active": is_active,
                    "deleted": tab.deleted,
                    "group": group_name,
                    "workspace": None,
                    "workspace_id": None,
                    "history": [],
                    "url": "",
                    "title": "",
                }

                for hist_item in tab.history:
                    result_tab["history"].append(
                        {"url": hist_item.url, "title": hist_item.title}
                    )

                    if hist_item.idx == tab.current_history_idx:
                        result_tab["url"] = hist_item.url
                        result_tab["title"] = hist_item.title

                        ws_id = self._url_workspace_map.get(hist_item.url)
                        if ws_id:
                            result_tab["workspace_id"] = ws_id
                            if ws_id in self.workspaces:
                                ws = self.workspaces[ws_id]
                                result_tab["workspace"] = (
                                    f"{ws.emoji} {ws.name}".strip()
                                )

                result_window["tabs"].append(result_tab)

                if not tab.deleted:
                    non_deleted_tab_idx += 1

            windows.append(result_window)

        return {"windows": windows}
