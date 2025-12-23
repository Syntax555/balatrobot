"""Shared test fixtures for CLI tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from balatrobot.config import ENV_MAP


@pytest.fixture
def clean_env(monkeypatch):
    """Clear all BALATROBOT_* env vars for clean tests."""
    for env_var in ENV_MAP.values():
        monkeypatch.delenv(env_var, raising=False)
    yield


@pytest.fixture
def mock_popen(monkeypatch):
    """Mock subprocess.Popen for lifecycle tests."""
    mock_process = MagicMock()
    mock_process.pid = 12345
    mock_process.terminate = MagicMock()
    mock_process.kill = MagicMock()
    mock_process.wait = MagicMock(return_value=0)

    mock_popen_cls = MagicMock(return_value=mock_process)
    monkeypatch.setattr("subprocess.Popen", mock_popen_cls)

    return mock_process


@pytest.fixture
def mock_httpx_success(monkeypatch):
    """Mock httpx.AsyncClient returning successful health response."""

    async def mock_post(*args, **kwargs):
        response = MagicMock()
        response.json.return_value = {"result": {"status": "ok"}}
        return response

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = mock_post

    mock_async_client = MagicMock(return_value=mock_client)
    monkeypatch.setattr("httpx.AsyncClient", mock_async_client)

    return mock_client


@pytest.fixture
def mock_httpx_fail(monkeypatch):
    """Mock httpx.AsyncClient always raising ConnectionError."""
    import httpx

    async def mock_post(*args, **kwargs):
        raise httpx.ConnectError("Connection refused")

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = mock_post

    mock_async_client = MagicMock(return_value=mock_client)
    monkeypatch.setattr("httpx.AsyncClient", mock_async_client)

    return mock_client
