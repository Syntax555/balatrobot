# Test Fixtures

This directory contains test fixture files (`.jkr` save files) used for testing the save and load endpoints.

Fixtures are organized hierarchically by endpoint:

```
tests/fixtures/
├── save/          # Fixtures for save endpoint tests
├── load/          # Fixtures for load endpoint tests
├── generate.py    # Script to generate all fixtures
└── README.md
```

## Generating Fixtures

### Prerequisites

1. Start Balatro with the BalatroBot mod loaded
2. Make sure you're in an appropriate game state for the fixtures you need

### Generate All Fixtures

```bash
python tests/fixtures/generate.py
```

The script will automatically connect to Balatro on localhost:12346 and generate all required fixtures.

## Adding New Fixtures

To add new fixtures:

1. Create the appropriate directory structure under the endpoint category
2. Update `generate.py` to include the new fixture generation logic
3. Add fixture descriptions to this README

## Usage in Tests

Fixtures are accessed using the `get_fixture_path()` helper function:

```python
from tests.lua.conftest import get_fixture_path

def test_example(client):
    fixture_path = get_fixture_path("load", "start.jkr")
    send_request(client, "load", {"path": str(fixture_path)})
    response = receive_response(client)
    assert response["success"] is True
```

## Current Fixtures

### Save Endpoint Tests (`save/`)

- `start.jkr` - Valid save file from initial game state

### Load Endpoint Tests (`load/`)

- `start.jkr` - Valid save file from initial game state
- `corrupted.jkr` - Intentionally corrupted save file for error testing
