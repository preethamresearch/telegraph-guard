"""CrewAI integration (FR-21).

    from telegraph_guard.crewai import TelegraphGuardTool
    agent = Agent(role="Treasurer", tools=[TelegraphGuardTool(), PayTool()], ...)

The description is written at the LLM, not at the developer: it states the
precondition ("before any payment tool") explicitly, because that sentence
is the only thing standing between a socially-engineered agent and a
transfer.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from .core import Guard
from .types import GuardConfig, GuardVerdict

DESCRIPTION = (
    "Screen a payment destination for fraud BEFORE sending any funds. "
    "You MUST call this tool and receive an 'ALLOW' verdict before using any "
    "payment, transfer, or wallet tool. Accepts a blockchain address, ENS "
    "name, transaction hash, or URL. Returns ALLOW, REVIEW, or BLOCK with a "
    "risk score and the Telegraph miner signals behind it. If the verdict is "
    "BLOCK, do not send funds under any circumstances and report the reasons. "
    "If REVIEW, stop and ask a human before proceeding."
)


def format_verdict(v: GuardVerdict) -> str:
    """Compact string an LLM can act on, plus the JSON receipt (FR-21)."""
    head = (
        f"{v.verdict.upper()} — {v.target} ({v.target_type}) "
        f"risk={v.risk:.2f} confidence={v.confidence:.2f}"
    )
    reasons = "\n".join(f"  - {r}" for r in v.reasons) or "  - no reasons recorded"
    guidance = {
        "allow": "Safe to proceed with the payment.",
        "block": "DO NOT send funds. Report these reasons to the user.",
        "review": "Do not send funds without explicit human approval.",
    }[v.verdict]
    return f"{head}\n{reasons}\n{guidance}\n\nJSON:\n{json.dumps(v.to_dict())}"


def _run_sync(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # CrewAI may call tools from inside a loop; run on a private one.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _build_tool_class() -> Any:
    from crewai.tools import BaseTool  # type: ignore[import-not-found]
    from pydantic import BaseModel, Field  # type: ignore[import-not-found]

    class _Args(BaseModel):
        target: str = Field(
            ...,
            description="Address, ENS name, transaction hash, or URL to screen.",
        )

    class TelegraphGuardTool(BaseTool):  # type: ignore[misc]
        name: str = "telegraph_guard"
        description: str = DESCRIPTION
        args_schema: type[BaseModel] = _Args

        guard_config: GuardConfig = GuardConfig()

        def _run(self, target: str) -> str:
            guard = Guard(self.guard_config)

            async def go() -> GuardVerdict:
                try:
                    return await guard.screen(target, self.guard_config)
                finally:
                    await guard.aclose()

            return format_verdict(_run_sync(go()))

    return TelegraphGuardTool


def __getattr__(name: str) -> Any:
    """Import crewai lazily so `telegraph_guard` stays installable without it."""
    if name == "TelegraphGuardTool":
        try:
            return _build_tool_class()
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "TelegraphGuardTool requires crewai — install with "
                "`pip install 'telegraph-guard[crewai]'`"
            ) from exc
    raise AttributeError(name)


__all__ = ["TelegraphGuardTool", "format_verdict", "DESCRIPTION"]
