from __future__ import annotations

from balatro_ai.policy_context import DecisionFrame, PolicyContext


class TransitionManager:
    def before_decide(self, frame: DecisionFrame, ctx: PolicyContext) -> None:
        if frame.last_state == "SHOP" and frame.state != "SHOP":
            ctx.round_memory.pop("shop", None)
