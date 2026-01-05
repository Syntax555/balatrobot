from __future__ import annotations

import itertools
import time
from typing import Any, Mapping

import requests
from requests import Response, Session
from requests.exceptions import ConnectionError, RequestException, Timeout

JsonObject = dict[str, Any]

DEFAULT_BASE_URL = "http://127.0.0.1:12346"


class BalatroRPCError(Exception):
    """Represents a JSON-RPC error or client-side validation failure."""

    def __init__(
        self,
        code: int,
        message: str,
        data: JsonObject | None,
        method: str | None,
        params: Mapping[str, Any] | None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data
        self.method = method
        self.params = dict(params) if params else None

    def __str__(self) -> str:
        details = f" data={self.data}" if self.data is not None else ""
        method = f" method={self.method}" if self.method else ""
        return f"{self.code}: {self.message}{method}{details}"


class BalatroRPC:
    """JSON-RPC 2.0 client for the BalatroBot API."""

    def __init__(self, base_url: str, timeout: float) -> None:
        if not base_url:
            raise BalatroRPCError(
                code=-32602,
                message="Invalid params",
                data={"reason": "base_url is required"},
                method=None,
                params=None,
            )
        if timeout <= 0:
            raise BalatroRPCError(
                code=-32602,
                message="Invalid params",
                data={"reason": "timeout must be positive"},
                method=None,
                params={"timeout": timeout},
            )
        self._base_url = base_url
        self._timeout = timeout
        self._session = requests.Session()
        self._id_counter = itertools.count(1)

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._session.close()

    def call(self, method: str, params: dict[str, Any] | None = None) -> JsonObject:
        """Call a JSON-RPC method and return its result."""
        payload: JsonObject = {
            "jsonrpc": "2.0",
            "method": method,
            "id": self._next_id(),
        }
        if params:
            payload["params"] = dict(params)
        response_data = self._post(payload)
        if "error" in response_data:
            self._raise_rpc_error(
                response_data["error"],
                method=method,
                params=params,
            )
        if "result" not in response_data:
            raise BalatroRPCError(
                code=-32000,
                message="Missing result in response",
                data={"response": response_data},
                method=method,
                params=params,
            )
        return response_data["result"]

    def health(self) -> JsonObject:
        """Call the health check endpoint."""
        return self.call("health")

    def gamestate(self) -> JsonObject:
        """Fetch the current game state."""
        return self.call("gamestate")

    def rpc_discover(self) -> JsonObject:
        """Return the OpenRPC specification document."""
        return self.call("rpc.discover")

    def start(self, deck: str, stake: str, seed: str | None = None) -> JsonObject:
        """Start a new game run."""
        if not deck:
            raise self._invalid_params("deck is required", {"deck": deck})
        if not stake:
            raise self._invalid_params("stake is required", {"stake": stake})
        if seed == "":
            raise self._invalid_params("seed cannot be empty", {"seed": seed})
        params: JsonObject = {"deck": deck, "stake": stake}
        if seed is not None:
            params["seed"] = seed
        return self.call("start", params)

    def menu(self) -> JsonObject:
        """Return to the main menu."""
        return self.call("menu")

    def select(self) -> JsonObject:
        """Select the current blind."""
        return self.call("select")

    def skip(self) -> JsonObject:
        """Skip the current blind."""
        return self.call("skip")

    def buy(
        self,
        *,
        card: int | None = None,
        voucher: int | None = None,
        pack: int | None = None,
    ) -> JsonObject:
        """Buy a card, voucher, or pack from the shop."""
        choice, value = self._single_choice(
            {"card": card, "voucher": voucher, "pack": pack},
            method="buy",
        )
        params = {choice: self._validate_index(choice, value)}
        return self.call("buy", params)

    def pack(
        self,
        *,
        card: int | None = None,
        targets: list[int] | None = None,
        skip: bool | None = None,
    ) -> JsonObject:
        """Select a card or skip from an opened booster pack."""
        if skip is True:
            if card is not None or targets is not None:
                raise self._invalid_params(
                    "skip cannot be combined with card or targets",
                    {"card": card, "targets": targets, "skip": skip},
                )
            return self.call("pack", {"skip": True})
        if skip is False:
            raise self._invalid_params(
                "skip must be true when provided",
                {"card": card, "targets": targets, "skip": skip},
            )
        if card is None:
            raise self._invalid_params(
                "card is required when not skipping",
                {"card": card, "targets": targets},
            )
        params: JsonObject = {"card": self._validate_index("card", card)}
        if targets is not None:
            params["targets"] = self._validate_indices("targets", targets)
        return self.call("pack", params)

    def sell(
        self,
        *,
        joker: int | None = None,
        consumable: int | None = None,
    ) -> JsonObject:
        """Sell a joker or consumable."""
        choice, value = self._single_choice(
            {"joker": joker, "consumable": consumable},
            method="sell",
        )
        params = {choice: self._validate_index(choice, value)}
        return self.call("sell", params)

    def reroll(self) -> JsonObject:
        """Reroll the shop items."""
        return self.call("reroll")

    def cash_out(self) -> JsonObject:
        """Cash out round rewards and transition to shop."""
        return self.call("cash_out")

    def next_round(self) -> JsonObject:
        """Leave the shop and advance to blind selection."""
        return self.call("next_round")

    def play(self, cards: list[int]) -> JsonObject:
        """Play cards from the current hand."""
        indices = self._validate_indices("cards", cards)
        if not (1 <= len(indices) <= 5):
            raise self._invalid_params(
                "play requires 1-5 card indices",
                {"cards": cards},
            )
        return self.call("play", {"cards": indices})

    def discard(self, cards: list[int]) -> JsonObject:
        """Discard cards from the current hand."""
        indices = self._validate_indices("cards", cards)
        return self.call("discard", {"cards": indices})

    def rearrange(
        self,
        *,
        hand: list[int] | None = None,
        jokers: list[int] | None = None,
        consumables: list[int] | None = None,
    ) -> JsonObject:
        """Rearrange cards in hand, jokers, or consumables."""
        choice, value = self._single_choice(
            {"hand": hand, "jokers": jokers, "consumables": consumables},
            method="rearrange",
        )
        indices = self._validate_indices(choice, value, allow_empty=True)
        return self.call("rearrange", {choice: indices})

    def use(self, *, consumable: int, cards: list[int] | None = None) -> JsonObject:
        """Use a consumable card."""
        params: JsonObject = {"consumable": self._validate_index("consumable", consumable)}
        if cards is not None:
            params["cards"] = self._validate_indices("cards", cards, allow_empty=True)
        return self.call("use", params)

    def save(self, path: str) -> JsonObject:
        """Save the current run to a file."""
        if not path:
            raise self._invalid_params("path is required", {"path": path})
        return self.call("save", {"path": path})

    def load(self, path: str) -> JsonObject:
        """Load a saved run from a file."""
        if not path:
            raise self._invalid_params("path is required", {"path": path})
        return self.call("load", {"path": path})

    def _next_id(self) -> int:
        return next(self._id_counter)

    def _post(self, payload: JsonObject) -> JsonObject:
        delays = (0.1, 0.2, 0.4)
        for attempt in range(len(delays) + 1):
            try:
                response = self._session.post(
                    self._base_url,
                    json=payload,
                    timeout=self._timeout,
                )
                return self._parse_response(response, payload)
            except (ConnectionError, Timeout) as exc:
                if attempt < len(delays):
                    time.sleep(delays[attempt])
                    continue
                raise BalatroRPCError(
                    code=-32098,
                    message="Connection error",
                    data={"error": str(exc)},
                    method=payload.get("method"),
                    params=payload.get("params"),
                ) from exc
            except RequestException as exc:
                raise BalatroRPCError(
                    code=-32097,
                    message="Request error",
                    data={"error": str(exc)},
                    method=payload.get("method"),
                    params=payload.get("params"),
                ) from exc
        raise BalatroRPCError(
            code=-32099,
            message="Unknown request failure",
            data=None,
            method=payload.get("method"),
            params=payload.get("params"),
        )

    def _parse_response(self, response: Response, payload: Mapping[str, Any]) -> JsonObject:
        if not response.ok:
            raise BalatroRPCError(
                code=-32000,
                message="HTTP error",
                data={"status": response.status_code, "body": response.text},
                method=payload.get("method"),
                params=payload.get("params"),
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise BalatroRPCError(
                code=-32700,
                message="Parse error",
                data={"body": response.text},
                method=payload.get("method"),
                params=payload.get("params"),
            ) from exc
        if not isinstance(data, dict):
            raise BalatroRPCError(
                code=-32000,
                message="Invalid response payload",
                data={"response": data},
                method=payload.get("method"),
                params=payload.get("params"),
            )
        return data

    def _raise_rpc_error(
        self,
        error: Mapping[str, Any],
        *,
        method: str,
        params: Mapping[str, Any] | None,
    ) -> None:
        code = int(error.get("code", -32000))
        message = str(error.get("message", "Unknown error"))
        data = error.get("data")
        data_payload = None
        if isinstance(data, Mapping):
            data_payload = dict(data)
        elif data is not None:
            data_payload = {"data": data}
        raise BalatroRPCError(
            code=code,
            message=message,
            data=data_payload,
            method=method,
            params=params,
        )

    def _invalid_params(self, reason: str, params: Mapping[str, Any] | None) -> BalatroRPCError:
        return BalatroRPCError(
            code=-32602,
            message="Invalid params",
            data={"reason": reason},
            method=None,
            params=params,
        )

    def _single_choice(
        self,
        values: Mapping[str, Any],
        *,
        method: str,
    ) -> tuple[str, Any]:
        present = [key for key, value in values.items() if value is not None]
        if len(present) != 1:
            raise BalatroRPCError(
                code=-32602,
                message="Invalid params",
                data={
                    "reason": "exactly one parameter must be provided",
                    "fields": list(values.keys()),
                },
                method=method,
                params={k: v for k, v in values.items() if v is not None},
            )
        key = present[0]
        return key, values[key]

    def _validate_index(self, name: str, value: Any) -> int:
        if not isinstance(value, int):
            raise self._invalid_params(f"{name} must be an integer", {name: value})
        if value < 0:
            raise self._invalid_params(f"{name} must be >= 0", {name: value})
        return value

    def _validate_indices(
        self,
        name: str,
        values: list[int],
        *,
        allow_empty: bool = False,
    ) -> list[int]:
        if not isinstance(values, list):
            raise self._invalid_params(f"{name} must be a list", {name: values})
        if not values and not allow_empty:
            raise self._invalid_params(f"{name} must be non-empty", {name: values})
        indices: list[int] = []
        seen: set[int] = set()
        for value in values:
            index = self._validate_index(name, value)
            if index in seen:
                raise self._invalid_params(
                    f"{name} must not contain duplicates",
                    {name: values},
                )
            seen.add(index)
            indices.append(index)
        return indices
