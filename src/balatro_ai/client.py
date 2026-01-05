from __future__ import annotations

import itertools
import logging
import time
from typing import Any, Mapping

import requests
from requests import Response, Session
from requests.exceptions import ConnectionError, RequestException, Timeout

JsonObject = dict[str, Any]


class BalatroRpcError(Exception):
    """Represents a JSON-RPC error from BalatroBot or transport failures."""

    def __init__(self, code: int, message: str, data: JsonObject | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def __str__(self) -> str:
        details = f" data={self.data}" if self.data is not None else ""
        return f"{self.code}: {self.message}{details}"


class RpcClient:
    """JSON-RPC client for the BalatroBot API."""

    def __init__(
        self,
        base_url: str,
        timeout: float,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
        session: Session | None = None,
    ) -> None:
        self._base_url = base_url
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
        self._session = session or requests.Session()
        self._id_counter = itertools.count(1)
        self._logger = logging.getLogger(__name__)

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._session.close()

    def call(self, method: str, params: Mapping[str, Any] | None = None) -> JsonObject:
        """Call a JSON-RPC method and return its result."""
        payload: JsonObject = {
            "jsonrpc": "2.0",
            "method": method,
            "id": self._next_id(),
        }
        if params is not None:
            payload["params"] = dict(params)
        data = self._post(payload)
        if "error" in data:
            self._raise_rpc_error(data["error"])
        if "result" not in data:
            raise BalatroRpcError(
                code=-32000,
                message="Missing result in response",
                data={"response": data},
            )
        return data["result"]

    def gamestate(self) -> JsonObject:
        """Fetch the current game state."""
        return self.call("gamestate")

    def menu(self) -> JsonObject:
        """Return to the main menu."""
        return self.call("menu")

    def start(self, deck: str, stake: str, seed: str | None) -> JsonObject:
        """Start a new run."""
        params: JsonObject = {"deck": deck, "stake": stake}
        if seed:
            params["seed"] = seed
        return self.call("start", params)

    def select(self) -> JsonObject:
        """Select the current blind."""
        return self.call("select")

    def play(self, cards: list[int]) -> JsonObject:
        """Play cards from the current hand."""
        return self.call("play", {"cards": cards})

    def cash_out(self) -> JsonObject:
        """Cash out the round rewards."""
        return self.call("cash_out")

    def next_round(self) -> JsonObject:
        """Advance to the next round from the shop."""
        return self.call("next_round")

    def pack(self, card_index: int) -> JsonObject:
        """Select the card at the provided index from an opened pack."""
        return self.call("pack", {"card": card_index})

    def _next_id(self) -> int:
        return next(self._id_counter)

    def _post(self, payload: JsonObject) -> JsonObject:
        for attempt in range(self._max_retries + 1):
            try:
                response = self._session.post(
                    self._base_url,
                    json=payload,
                    timeout=self._timeout,
                )
                return self._parse_response(response)
            except (ConnectionError, Timeout) as exc:
                if attempt < self._max_retries:
                    self._sleep_before_retry(attempt, exc)
                    continue
                raise BalatroRpcError(
                    code=-32098,
                    message="Connection error",
                    data={"error": str(exc)},
                ) from exc
            except RequestException as exc:
                raise BalatroRpcError(
                    code=-32097,
                    message="Request error",
                    data={"error": str(exc)},
                ) from exc
        raise BalatroRpcError(code=-32099, message="Unknown request failure", data=None)

    def _parse_response(self, response: Response) -> JsonObject:
        if not response.ok:
            raise BalatroRpcError(
                code=-32000,
                message="HTTP error",
                data={"status": response.status_code, "body": response.text},
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise BalatroRpcError(
                code=-32700,
                message="Parse error",
                data={"body": response.text},
            ) from exc
        if not isinstance(data, dict):
            raise BalatroRpcError(
                code=-32000,
                message="Invalid response payload",
                data={"response": data},
            )
        return data

    def _raise_rpc_error(self, error: Mapping[str, Any]) -> None:
        code = int(error.get("code", -32000))
        message = str(error.get("message", "Unknown error"))
        data = error.get("data")
        data_payload = None
        if isinstance(data, Mapping):
            data_payload = dict(data)
        elif data is not None:
            data_payload = {"data": data}
        raise BalatroRpcError(code=code, message=message, data=data_payload)

    def _sleep_before_retry(self, attempt: int, exc: Exception) -> None:
        delay = self._backoff_seconds * (2**attempt)
        self._logger.warning(
            "Connection error (%s). Retrying in %.2fs.",
            exc,
            delay,
        )
        time.sleep(delay)
