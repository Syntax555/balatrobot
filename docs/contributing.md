# Contributing

Guide for contributing to BalatroBot development.

## Prerequisites

- **Balatro** (v1.0.1+)
- **Lovely Injector** - [Installation](https://github.com/ethangreen-dev/lovely-injector)
- **Steamodded** - [Installation](https://github.com/Steamopollys/Steamodded)
- **DebugPlus** (optional) - Required for test endpoints

## Development Setup

### 1. Clone the Repository

```bash
git clone https://github.com/your-repo/balatrobot.git
cd balatrobot
```

### 2. Symlink to Mods Folder

Instead of copying files, create a symlink for easier development:

**macOS:**
```bash
ln -s "$(pwd)" ~/Library/Application\ Support/Balatro/Mods/balatrobot
```

**Linux:**
```bash
ln -s "$(pwd)" ~/.local/share/Steam/steamapps/compatdata/2379780/pfx/drive_c/users/steamuser/AppData/Roaming/Balatro/Mods/
```

**Windows (PowerShell as Admin):**
```powershell
New-Item -ItemType SymbolicLink -Path "$env:APPDATA\Balatro\Mods\balatrobot" -Target (Get-Location)
```

### 3. Set Environment Variables

```bash
export BALATROBOT_DEBUG=1
export BALATROBOT_FAST=1
```

### 4. Launch Balatro

Start the game normally. Check logs for "BalatroBot API initialized" to confirm the mod loaded.

## Running Tests

Tests use Python + pytest to communicate with the Lua API:

```bash
# Install all dependencies
make install

# Run all tests (restarts game automatically)
make test

# Run specific test file
pytest tests/lua/endpoints/test_health.py -v

# Run tests with dev marker
make test PYTEST_MARKER=dev
```

## Code Structure

```
src/lua/
├── core/
│   ├── server.lua       # HTTP server
│   ├── dispatcher.lua   # Request routing
│   └── validator.lua    # Schema validation
├── endpoints/           # API endpoints
│   ├── health.lua
│   ├── gamestate.lua
│   ├── play.lua
│   └── ...
└── utils/
    ├── types.lua        # Type definitions
    ├── enums.lua        # Enum values
    ├── errors.lua       # Error codes
    ├── gamestate.lua    # State extraction
    └── openrpc.json     # API spec
```

## Adding a New Endpoint

1. Create `src/lua/endpoints/your_endpoint.lua`:

```lua
return {
  name = "your_endpoint",
  description = "Brief description",
  schema = {
    param_name = {
      type = "string",
      required = true,
      description = "Parameter description",
    },
  },
  requires_state = { G.STATES.SHOP },  -- Optional
  execute = function(args, send_response)
    -- Implementation
    send_response(BB_GAMESTATE.get_gamestate())
  end,
}
```

2. Add tests in `tests/lua/endpoints/test_your_endpoint.py`

3. Update `src/lua/utils/openrpc.json` with the new method

## Pull Request Guidelines

1. **One feature per PR** - Keep changes focused
2. **Add tests** - New endpoints need test coverage
3. **Update docs** - Update api.md and openrpc.json for API changes
4. **Follow conventions** - Match existing code style
5. **Test locally** - Ensure `make test` passes
