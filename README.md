# chromium-session

Parse and analyze session files from Chromium-based browsers (Chrome, Vivaldi, Brave, Edge) with support for workspaces, profiles, and tab management.

## Features

- **Multi-browser support**: Chrome, Vivaldi, Brave, Edge, and other Chromium-based browsers
- **Profile detection**: Automatically detects and lists all browser profiles
- **Workspace support**: Parse Vivaldi workspaces and group tabs accordingly
- **Session analysis**: View active/deleted tabs, windows, and session statistics
- **Flexible output**: Rich terminal display or JSON export
- **Tab organization**: View tabs by window or grouped by workspace

## Installation

### From Source

```bash
git clone https://github.com/yourusername/chromium-session.git
cd chromium-session
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e .
```

### Using uv (recommended)

```bash
uv pip install chromium-session
```

## Requirements

- Python 3.12+
- Linux (primary support)
- Chromium-based browser(s) installed

## Usage

### List Detected Browsers

Show all detected Chromium-based browsers and their profiles:

```bash
chromium-session list
```

**Example output:**
```
                               Detected Browsers
┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ ID            ┃ Name           ┃ Profiles                         ┃ Sessions ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ chrome        │ Google Chrome  │ Default                          │ 1/1      │
│ vivaldi       │ Vivaldi        │ Default, Profile 2, Profile 4    │ 5/5      │
│ brave         │ Brave          │ Default                          │ 1/1      │
│ edge          │ Microsoft Edge │ Default                          │ 1/1      │
└───────────────┴────────────────┴──────────────────────────────────┴──────────┘
```

### List Browser Profiles

Show all profiles for a specific browser:

```bash
chromium-session profiles vivaldi
```

### View Session Summary

Get a quick overview of tabs and windows:

```bash
chromium-session summary vivaldi
```

**Example output:**
```
Vivaldi / Default
Session: Session_13402871234567

┏━━━━━━━━━━━━━┳━━━━━━━┓
┃ Metric      ┃ Value ┃
┡━━━━━━━━━━━━━╇━━━━━━━┩
│ Total tabs  │ 127   │
│ Active tabs │ 115   │
│ Deleted tabs│ 12    │
│ Windows     │ 3     │
└─────────────┴───────┘

                 Tabs by Workspace
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Workspace          ┃                       Tabs ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Work               │                         42 │
│ Research           │                         38 │
│ Personal           │                         35 │
│ No Workspace       │                         12 │
└────────────────────┴────────────────────────────┘
```

### Parse Session Files

Parse and display all tabs in the latest session:

```bash
# Parse latest session (default)
chromium-session parse vivaldi

# Parse specific profile
chromium-session parse vivaldi --profile "Default"

# Parse multiple recent sessions
chromium-session parse vivaldi --latest 3

# Show deleted tabs as well
chromium-session parse vivaldi --show-deleted

# Group tabs by workspace (Vivaldi)
chromium-session parse vivaldi --by-workspace
```

### List Workspaces (Vivaldi)

Show all defined workspaces:

```bash
chromium-session workspaces vivaldi
```

**Example output:**
```
        Workspaces in Vivaldi / Default
┏━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Emoji ┃ Name                 ┃ ID         ┃
┡━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ 💼    │ Work                 │ 1          │
│ 🔬    │ Research             │ 2          │
│ 🏠    │ Personal             │ 3          │
└───────┴──────────────────────┴────────────┘
```

### JSON Output

Export session data as JSON:

```bash
# Export session data
chromium-session parse vivaldi --json > session.json

# Export workspaces
chromium-session workspaces vivaldi --json > workspaces.json
```

## Command Reference

### Global Options

| Option | Description |
|--------|-------------|
| `--help` | Show help message |
| `--install-completion` | Install shell completion |

### Commands

#### `list`

List all detected Chromium-based browsers.

```bash
chromium-session list
```

#### `profiles <browser>`

List all profiles for a specific browser.

```bash
chromium-session profiles vivaldi
```

**Arguments:**
- `browser`: Browser ID (e.g., `chrome`, `vivaldi`, `brave`, `edge`)

#### `summary <browser>`

Show quick summary statistics for the latest session.

```bash
chromium-session summary vivaldi [OPTIONS]
```

**Arguments:**
- `browser`: Browser ID

**Options:**
- `--profile`, `-p`: Specific profile name

#### `parse <browser>`

Parse and display session files.

```bash
chromium-session parse vivaldi [OPTIONS]
```

**Arguments:**
- `browser`: Browser ID

**Options:**
- `--profile`, `-p`: Specific profile name
- `--latest`, `-n`: Number of recent sessions to parse (default: 1)
- `--json`, `-j`: Output as JSON
- `--show-deleted`: Include deleted tabs and windows
- `--by-workspace`, `-W`: Group tabs by workspace (Vivaldi only)

#### `workspaces <browser>`

List defined workspaces (Vivaldi only).

```bash
chromium-session workspaces vivaldi [OPTIONS]
```

**Arguments:**
- `browser`: Browser ID

**Options:**
- `--profile`, `-p`: Specific profile name
- `--json`, `-j`: Output as JSON

## Use Cases

### Session Recovery

Recover tabs after a browser crash:

```bash
# View all tabs from the latest session
chromium-session parse vivaldi --show-deleted

# Export to JSON for processing
chromium-session parse vivaldi --json > crashed-session.json
```

### Tab Management

Analyze your browsing habits:

```bash
# See how many tabs you have per workspace
chromium-session summary vivaldi

# Find specific tabs
chromium-session parse vivaldi --json | jq '.windows[].tabs[] | select(.title | contains("Python"))'
```

### Multi-Profile Management

Work with multiple browser profiles:

```bash
# List all profiles
chromium-session profiles vivaldi

# Parse specific profile
chromium-session parse vivaldi --profile "Work"
```

## Browser Support

| Browser | ID | Session Support | Workspace Support |
|---------|-----|-----------------|-------------------|
| Google Chrome | `chrome` | ✅ | ❌ |
| Vivaldi | `vivaldi` | ✅ | ✅ |
| Brave | `brave` | ✅ | ❌ |
| Brave Nightly | `brave-nightly` | ✅ | ❌ |
| Microsoft Edge | `edge` | ✅ | ❌ |

## Running as a Module

You can also run the package as a Python module:

```bash
python -m chromium_session list
```

## Development

### Setup Development Environment

```bash
git clone https://github.com/yourusername/chromium-session.git
cd chromium-session
uv venv
source .venv/bin/activate
uv pip install -e .
```

### Project Structure

```
chromium-session/
├── src/
│   └── chromium_session/
│       ├── __init__.py
│       ├── __main__.py      # Module entry point
│       ├── cli.py           # Typer CLI interface
│       ├── parser.py        # Session file parser
│       └── browsers.py      # Browser detection logic
├── pyproject.toml
└── README.md
```

## Troubleshooting

### No browsers detected

**Problem**: `chromium-session list` shows no browsers.

**Solution**: Ensure you have at least one Chromium-based browser installed in the default location:
- Chrome: `~/.config/google-chrome/`
- Vivaldi: `~/.config/vivaldi/`
- Brave: `~/.config/BraveSoftware/Brave-Browser/`
- Edge: `~/.config/microsoft-edge/`

### Session files not found

**Problem**: Browser is detected but sessions show `0/N`.

**Solution**: The browser must have been run at least once. Session files are created in:
```
<browser-config-dir>/<profile>/Sessions/
```

### Import errors after moving project

**Problem**: `python -m chromium_session` fails with import errors.

**Solution**: Reinstall the package in the new location:
```bash
uv pip install -e .
```

## License

MIT License - See LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Author

Asseel Naji

## Acknowledgments

- Built with [Typer](https://typer.tiangolo.com/) for the CLI
- [Rich](https://rich.readthedocs.io/) for beautiful terminal output
