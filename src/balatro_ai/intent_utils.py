from __future__ import annotations

import enum
from typing import Any, TypeVar

TEnum = TypeVar("TEnum", bound=enum.Enum)


def intent_text(value: Any) -> str | None:
    """Best-effort conversion of an intent-like value into a string."""
    if isinstance(value, str):
        return value
    inner = getattr(value, "value", None)
    return inner if isinstance(inner, str) else None


def ctx_intent_value(ctx: Any) -> Any:
    """Return ctx.{round,run}_memory['intent'] with round taking precedence."""
    value = None
    if hasattr(ctx, "round_memory"):
        value = ctx.round_memory.get("intent")
    if value is None and hasattr(ctx, "run_memory"):
        value = ctx.run_memory.get("intent")
    return value


def ctx_intent_text(ctx: Any) -> str | None:
    """Return the current intent string from a PolicyContext-like object."""
    return intent_text(ctx_intent_value(ctx))


def ctx_intent_text_nonempty(ctx: Any) -> str:
    """Return the first non-empty intent string from ctx.{round,run}_memory."""
    if hasattr(ctx, "round_memory"):
        value = intent_text(ctx.round_memory.get("intent"))
        if value:
            return value
    if hasattr(ctx, "run_memory"):
        value = intent_text(ctx.run_memory.get("intent"))
        if value:
            return value
    return ""


def coerce_enum(enum_cls: type[TEnum], value: Any) -> TEnum | None:
    """Coerce a string/enum-like value into a specific Enum member."""
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str) and value:
        key = value.strip().upper()
        try:
            return enum_cls[key]
        except KeyError:
            return None
    inner = getattr(value, "value", None)
    if isinstance(inner, str) and inner:
        key = inner.strip().upper()
        try:
            return enum_cls[key]
        except KeyError:
            return None
    return None
