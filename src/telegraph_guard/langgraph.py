"""LangGraph integration (FR-20).

    from telegraph_guard.langgraph import guard_node, route_on_verdict

    g.add_node("guard", guard_node())
    g.add_conditional_edges("guard", route_on_verdict,
                            {"execute": "pay", "abort": END, "human": "hitl"})

The node reads ``state["pending_payment"]`` — ``{to, amount, chain, url?}`` —
screens the destination, and writes ``state["guard_verdict"]``. It never
raises: a failure becomes a ``block`` verdict under the default
fail-closed config, so a broken guard cannot become an open gate.

No hard dependency on langgraph: the node is a plain callable over the
state dict, which is exactly what LangGraph expects.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from .core import Guard
from .types import GuardConfig, GuardVerdict

State = dict[str, Any]

#: Verdict → conditional-edge label (FR-20).
ROUTES = {"allow": "execute", "block": "abort", "review": "human"}


def _target_from(payment: dict[str, Any]) -> str | None:
    """A payment's screenable destination. A URL, when present, is the
    riskier surface — it is what a prompt-injection attack supplies — so
    it is screened in preference to the address."""
    if not isinstance(payment, dict):
        return None
    return payment.get("url") or payment.get("to") or payment.get("address")


def guard_node(
    config: GuardConfig | None = None,
    guard: Guard | None = None,
    state_key: str = "pending_payment",
    output_key: str = "guard_verdict",
) -> Callable[[State], Awaitable[State]]:
    """Build an async LangGraph node that gates ``state[state_key]``."""
    cfg = config or GuardConfig()
    _guard = guard or Guard(cfg)

    async def node(state: State) -> State:
        payment = state.get(state_key) or {}
        target = _target_from(payment)

        if not target:
            verdict = GuardVerdict(
                target="",
                target_type="unknown",
                verdict="review",
                risk=0.5,
                confidence=0.0,
                reasons=[f"no screenable destination in state['{state_key}']"],
                thresholds={"allowBelow": cfg.allow_below, "blockAbove": cfg.block_above},
            )
        else:
            call_cfg = cfg
            chain = payment.get("chain")
            if chain and chain != cfg.chain:
                call_cfg = GuardConfig(**{**cfg.__dict__, "chain": chain})
            verdict = await _guard.screen(target, call_cfg)

        return {**state, output_key: verdict}

    return node


def route_on_verdict(state: State, output_key: str = "guard_verdict") -> str:
    """Conditional-edge function mapping a verdict to a branch (FR-20).

    Anything unexpected routes to ``human`` rather than ``execute`` — an
    absent verdict is not permission to pay.
    """
    verdict = state.get(output_key)
    if isinstance(verdict, GuardVerdict):
        return ROUTES.get(verdict.verdict, "human")
    if isinstance(verdict, dict):
        return ROUTES.get(verdict.get("verdict", ""), "human")
    return "human"
