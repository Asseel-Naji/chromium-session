"""
Session file writer for Chromium SNSS format.

This module provides functionality to write session data back to SNSS binary files,
maintaining the same format as Chromium-based browsers use.
"""

import struct
from pathlib import Path

from .parser import Commands, Tab, TabGroup, Window


class SessionWriter:
    """Writer for Chromium SNSS session files."""

    def __init__(self, version: int = 1):
        """
        Initialize the session writer.

        Args:
            version: SNSS file format version (default: 1)
        """
        self.version = version
        self._buffer = bytearray()

    def _write_string(self, value: str) -> bytes:
        """
        Encode a string in pickled UTF-8 format.

        Format: uint32 size + UTF-8 bytes + padding to 4-byte alignment

        Args:
            value: String to encode

        Returns:
            Encoded bytes
        """
        encoded = value.encode("utf-8")
        size = len(encoded)
        real_size = size

        # Pad to 4-byte alignment
        if real_size % 4 != 0:
            real_size += 4 - (real_size % 4)

        result = struct.pack("<I", size)
        result += encoded
        result += b"\x00" * (real_size - size)

        return result

    def _write_string16(self, value: str) -> bytes:
        """
        Encode a string in pickled UTF-16LE format.

        Format: uint32 char_count + UTF-16LE bytes + padding to 4-byte alignment

        Args:
            value: String to encode

        Returns:
            Encoded bytes
        """
        encoded = value.encode("utf-16-le")
        char_count = len(value)
        real_size = len(encoded)

        # Pad to 4-byte alignment
        if real_size % 4 != 0:
            real_size += 4 - (real_size % 4)

        result = struct.pack("<I", char_count)
        result += encoded
        result += b"\x00" * (real_size - len(encoded))

        return result

    def _write_command(self, cmd_type: int, data: bytes):
        """
        Write a command to the buffer.

        Format: uint16 size + uint8 type + data

        Args:
            cmd_type: Command type constant
            data: Command payload
        """
        # Size includes the type byte
        size = len(data) + 1
        self._buffer.extend(struct.pack("<H", size))
        self._buffer.extend(struct.pack("<B", cmd_type))
        self._buffer.extend(data)

    def write_set_tab_window(self, window_id: int, tab_id: int):
        """
        Write SET_TAB_WINDOW command.

        Args:
            window_id: Window ID
            tab_id: Tab ID
        """
        data = struct.pack("<I", window_id)
        data += struct.pack("<I", tab_id)
        self._write_command(Commands.SET_TAB_WINDOW, data)

    def write_set_tab_index_in_window(self, tab_id: int, index: int):
        """
        Write SET_TAB_INDEX_IN_WINDOW command.

        Args:
            tab_id: Tab ID
            index: Tab index within window
        """
        data = struct.pack("<I", tab_id)
        data += struct.pack("<I", index)
        self._write_command(Commands.SET_TAB_INDEX_IN_WINDOW, data)

    def write_update_tab_navigation(
        self, tab_id: int, history_index: int, url: str, title: str
    ):
        """
        Write UPDATE_TAB_NAVIGATION command.

        Args:
            tab_id: Tab ID
            history_index: History item index
            url: URL string
            title: Title string
        """
        data = struct.pack("<I", 0)  # Unknown field
        data += struct.pack("<I", tab_id)
        data += struct.pack("<I", history_index)
        data += self._write_string(url)
        data += self._write_string16(title)
        self._write_command(Commands.UPDATE_TAB_NAVIGATION, data)

    def write_set_selected_navigation_index(self, tab_id: int, index: int):
        """
        Write SET_SELECTED_NAVIGATION_INDEX command.

        Args:
            tab_id: Tab ID
            index: Current history index
        """
        data = struct.pack("<I", tab_id)
        data += struct.pack("<I", index)
        self._write_command(Commands.SET_SELECTED_NAVIGATION_INDEX, data)

    def write_set_selected_tab_in_index(self, window_id: int, index: int):
        """
        Write SET_SELECTED_TAB_IN_INDEX command.

        Args:
            window_id: Window ID
            index: Active tab index
        """
        data = struct.pack("<I", window_id)
        data += struct.pack("<I", index)
        self._write_command(Commands.SET_SELECTED_TAB_IN_INDEX, data)

    def write_set_active_window(self, window_id: int):
        """
        Write SET_ACTIVE_WINDOW command.

        Args:
            window_id: Window ID
        """
        data = struct.pack("<I", window_id)
        self._write_command(Commands.SET_ACTIVE_WINDOW, data)

    def write_tab_closed(self, tab_id: int):
        """
        Write TAB_CLOSED command.

        Args:
            tab_id: Tab ID
        """
        data = struct.pack("<I", tab_id)
        self._write_command(Commands.TAB_CLOSED, data)

    def write_window_closed(self, window_id: int):
        """
        Write WINDOW_CLOSED command.

        Args:
            window_id: Window ID
        """
        data = struct.pack("<I", window_id)
        self._write_command(Commands.WINDOW_CLOSED, data)

    def write_set_tab_group(self, tab_id: int, group: TabGroup):
        """
        Write SET_TAB_GROUP command.

        Args:
            tab_id: Tab ID
            group: TabGroup object
        """
        data = struct.pack("<I", tab_id)
        data += struct.pack("<I", 0)  # Padding
        data += struct.pack("<Q", group.high)
        data += struct.pack("<Q", group.low)
        self._write_command(Commands.SET_TAB_GROUP, data)

    def write_set_tab_group_metadata2(self, group: TabGroup):
        """
        Write SET_TAB_GROUP_METADATA2 command.

        Args:
            group: TabGroup object with name
        """
        data = struct.pack("<I", 0)  # Unknown field
        data += struct.pack("<Q", group.high)
        data += struct.pack("<Q", group.low)
        data += self._write_string16(group.name)
        self._write_command(Commands.SET_TAB_GROUP_METADATA2, data)

    def write_tab(self, tab: Tab):
        """
        Write all commands for a tab.

        Args:
            tab: Tab object to write
        """
        # Write tab to window association
        self.write_set_tab_window(tab.win, tab.id)

        # Write tab index within window
        self.write_set_tab_index_in_window(tab.id, tab.idx)

        # Write all history items
        for hist in tab.history:
            self.write_update_tab_navigation(
                tab.id, hist.idx, hist.url, hist.title
            )

        # Write current navigation index
        self.write_set_selected_navigation_index(tab.id, tab.current_history_idx)

        # Write tab group if present
        if tab.group:
            self.write_set_tab_group(tab.id, tab.group)

        # Write deleted status
        if tab.deleted:
            self.write_tab_closed(tab.id)

    def write_window(self, window: Window):
        """
        Write all commands for a window.

        Args:
            window: Window object to write
        """
        # Write all tabs in the window
        for tab in window.tabs:
            self.write_tab(tab)

        # Write active tab index
        if window.active_tab_idx >= 0:
            self.write_set_selected_tab_in_index(window.id, window.active_tab_idx)

        # Write deleted status
        if window.deleted:
            self.write_window_closed(window.id)

    def write_session(
        self,
        windows: list[Window],
        groups: dict[str, TabGroup],
        active_window: Window | None = None,
    ):
        """
        Write complete session data.

        Args:
            windows: List of Window objects
            groups: Dictionary of TabGroup objects (keyed by group.key)
            active_window: Currently active window
        """
        # Clear buffer
        self._buffer.clear()

        # Write SNSS header
        self._buffer.extend(b"SNSS")
        self._buffer.extend(struct.pack("<I", self.version))

        # Write tab group metadata
        for group in groups.values():
            if group.name:
                self.write_set_tab_group_metadata2(group)

        # Write all windows
        for window in windows:
            self.write_window(window)

        # Write active window
        if active_window:
            self.write_set_active_window(active_window.id)

    def save(self, filepath: str | Path):
        """
        Save the session buffer to a file.

        Args:
            filepath: Path to save the session file
        """
        filepath = Path(filepath)
        with open(filepath, "wb") as f:
            f.write(self._buffer)

    def get_buffer(self) -> bytes:
        """
        Get the current session buffer.

        Returns:
            Session data as bytes
        """
        return bytes(self._buffer)
