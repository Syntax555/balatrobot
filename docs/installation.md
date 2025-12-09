# Installation

This guide covers installing the BalatroBot mod for Balatro.

## Prerequisites

1. **Balatro** (v1.0.1+) - Purchase from [Steam](https://store.steampowered.com/app/2379780/Balatro/)
2. **Lovely Injector** - Follow the [installation guide](https://github.com/ethangreen-dev/lovely-injector#manual-installation)
3. **Steamodded** - Follow the [installation guide](https://github.com/Steamodded/smods/wiki)

## Mod Installation

### 1. Download BalatroBot

Download the latest release from the [releases page](https://github.com/your-repo/balatrobot/releases) or clone the repository.

### 2. Copy to Mods Folder

Copy the following files/folders to your Balatro Mods directory:

```
balatrobot/
├── balatrobot.json    # Mod manifest
├── balatrobot.lua     # Entry point
└── src/lua/           # API source code
```

**Mods directory location:**

| Platform | Path                                                                                                          |
| -------- | ------------------------------------------------------------------------------------------------------------- |
| Windows  | `%AppData%/Balatro/Mods/balatrobot/`                                                                          |
| macOS    | `~/Library/Application Support/Balatro/Mods/balatrobot/`                                                      |
| Linux    | `~/.local/share/Steam/steamapps/compatdata/2379780/pfx/drive_c/users/steamuser/AppData/Roaming/Balatro/Mods/` |

### 3. Launch Balatro

Use the platform-specific launcher script from the `scripts/` directory:

```bash
# macOS
python scripts/balatro-macos.py --fast --debug

# Linux (via Proton)
python scripts/balatro-linux.py --fast --debug

# Windows
python scripts/balatro-windows.py --fast --debug
```

**Available options:**

| Flag              | Description                                |
| ----------------- | ------------------------------------------ |
| `--host HOST`     | Server hostname (default: 127.0.0.1)       |
| `--port PORT`     | Server port (default: 12346)               |
| `--fast`          | Fast mode (skip animations)                |
| `--headless`      | Headless mode (no window)                  |
| `--render-on-api` | Render only on API calls                   |
| `--audio`         | Enable audio (disabled by default)         |
| `--debug`         | Debug mode (requires DebugPlus mod)        |
| `--no-shaders`    | Disable all shaders for better performance |

The scripts automatically:

- Kill any existing Balatro instances
- Kill processes using the specified port
- Set up the correct environment variables
- Log output to `logs/balatro_{port}.log`

### 4. Verify Installation

Start Balatro, then test the connection:

```bash
curl -X POST http://127.0.0.1:12346 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "health", "id": 1}'
```

Expected response:

```json
{"jsonrpc":"2.0","result":{"status":"ok"},"id":1}
```

## Troubleshooting

- **Connection refused**: Ensure Balatro is running and the mod loaded successfully
- **Mod not loading**: Check that Lovely and Steamodded are installed correctly
- **Port in use**: Change `BALATROBOT_PORT` to a different value

## Custom Launchers

If you're using a custom launcher or need to start Balatro manually, set these environment variables before launching:

| Variable                   | Default     | Description                                |
| -------------------------- | ----------- | ------------------------------------------ |
| `BALATROBOT_HOST`          | `127.0.0.1` | Server hostname                            |
| `BALATROBOT_PORT`          | `12346`     | Server port                                |
| `BALATROBOT_FAST`          | `0`         | Fast mode (1=enabled)                      |
| `BALATROBOT_HEADLESS`      | `0`         | Headless mode (1=enabled)                  |
| `BALATROBOT_RENDER_ON_API` | `0`         | Render only on API calls (1=enabled)       |
| `BALATROBOT_AUDIO`         | `0`         | Audio (1=enabled)                          |
| `BALATROBOT_DEBUG`         | `0`         | Debug mode (1=enabled, requires DebugPlus) |
| `BALATROBOT_NO_SHADERS`    | `0`         | Disable all shaders (1=enabled)            |

**Example (bash):**

```bash
export BALATROBOT_PORT=12346
export BALATROBOT_FAST=1
# Then launch Balatro with the Lovely Injector
```

**Example (Windows PowerShell):**

```powershell
$env:BALATROBOT_PORT = "12346"
$env:BALATROBOT_FAST = "1"
# Then launch Balatro.exe
```
