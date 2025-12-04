# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

BalatroBot is a framework for Balatro bot development. This repository contains a Lua-based API that communicates with the Balatro game via a TCP server. The API allows external clients (primarily Python-based bots) to control the game, query game state, and execute actions.

**Important**: Focus on the Lua API code in `src/lua/` and `tests/lua/`. Ignore the Python package `src/balatrobot/` and `tests/balatrobot/`.

### Testing

```bash
# Start Balatro game instance (if you need to restart the game)
python balatro.py start --fast --debug

# Run all Lua tests (it automatically restarts the game)
make test

# Run tests with specific marker (it automatically restarts the game)
make test PYTEST_MARKER=dev

# Run a single test file (we need to restart the game with `python balatro.py start --fast --debug` if the lua code was changed before running the test)
pytest tests/lua/endpoints/test_health.py -v

# Run a specific test (we need to restart the game with `python balatro.py start --fast --debug` if the lua code was changed before running the test)
pytest tests/lua/endpoints/test_health.py::TestHealthEndpoint::test_health_from_MENU -v
```

**Tip**: When we are focused on a specific test/group of tests (e.g. implementation of tests, understand why a test fails, etc.), we can mark the tests with `@pytest.mark.dev` and run them with `make test PYTEST_MARKER=dev` (so the game is restarted and relevant tests are run). So te `dev` pytest tag is reserved for test we are actually working on.

## Architecture

### Core Components

The Lua API is structured around three core layers:

1. **TCP Server** (`src/lua/core/server.lua`)

    - Single-client TCP server on port 12346 (default)
    - Non-blocking socket I/O
    - JSON-only protocol: `{"name": "endpoint", "arguments": {...}}\n`
    - Max message size: 256 bytes
    - Ultra-simple: JSON object + newline delimiter

2. **Dispatcher** (`src/lua/core/dispatcher.lua`)

    - Routes requests to endpoints with 4-tier validation:
        1. Protocol validation (has name, arguments)
        2. Schema validation (via Validator)
        3. Game state validation (requires_state check)
        4. Endpoint execution (with error handling)
    - Auto-discovers and registers endpoints at startup (fail-fast)
    - Converts numeric state values to human-readable names for error messages

3. **Validator** (`src/lua/core/validator.lua`)

    - Schema-based validation for endpoint arguments
    - Fail-fast: returns first error encountered
    - Type-strict: no implicit conversions
    - Supported types: string, integer, boolean, array, table
    - **Important**: No automatic defaults or range validation (endpoints handle this)

### Endpoint Structure

All endpoints follow this pattern (`src/lua/endpoints/*.lua`):

```lua
return {
  name = "endpoint_name",
  description = "Brief description",
  schema = {
    field_name = {
      type = "string" | "integer" | "boolean" | "array" | "table",
      required = true | false,
      items = "integer",  -- For array types only
      description = "Field description",
    },
  },
  requires_state = { G.STATES.SELECTING_HAND },  -- Optional state requirement
  execute = function(args, send_response)
    -- Endpoint implementation
    -- Call send_response() with result or error
  end,
}
```

**Key patterns**:

- Endpoints are stateless modules that return a table
- Use `send_response()` callback to send results (synchronous or async)
- For async operations, use `G.E_MANAGER:add_event()` to wait for state transitions
- Card indices are **0-based** in the API (but Lua uses 1-based indexing internally)
- Always convert between API (0-based) and internal (1-based) indexing

### Error Handling

Error codes are defined in `src/lua/utils/errors.lua`:

- `BAD_REQUEST`: Client sent invalid data (protocol/parameter errors)
- `INVALID_STATE`: Action not allowed in current game state
- `NOT_ALLOWED`: Game rules prevent this action
- `INTERNAL_ERROR`: Server-side failure (runtime/execution errors)

Endpoints send errors via:

```lua
send_response({
  error = "Human-readable message",
  error_code = BB_ERROR_NAMES.BAD_REQUEST,
})
```

### Game State Management

The `src/lua/utils/gamestate.lua` module provides:

- `BB_GAMESTATE.get_gamestate()`: Extract complete game state
- State conversion utilities (deck names, stake names, card data)
- Special GAME_OVER callback support for async endpoints

## Key Files

- `balatrobot.lua`: Entry point that loads all modules and initializes the API
- `src/lua/core/`: Core infrastructure (server, dispatcher, validator)
- `src/lua/endpoints/`: API endpoint implementations
- `src/lua/utils/`: Utilities (gamestate extraction, error definitions, types)
- `tests/lua/conftest.py`: Test fixtures and helpers
- `Makefile`: Common development commands
- `balatro.py`: Game launcher with environment variable setup
