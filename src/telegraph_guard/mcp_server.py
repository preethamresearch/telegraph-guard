"""MCP server (FR-24).

Exposes TelegraphGuard to any MCP client — Claude, Cursor, the Nasiko
gateway — so an agent that reaches for a payment tool can be made to
screen the destination first.

    telegraph-guard-mcp                    # stdio (Claude Desktop, Cursor)
    telegraph-guard-mcp --transport streamable-http --port 8402

Claude Desktop config:

    {
      "mcpServers": {
        "telegraph-guard": {
          "command": "telegraph-guard-mcp",
          "env": { "TELEGRAPH_GUARD_KEY": "0x..." }
        }
      }
    }

The tool description is written at the calling model, not at the
developer: it states the precondition explicitly, because in an MCP
setting that sentence is the only thing sequencing the guard before the
payment.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from .core import Guard
from .discovery import fetch_registry
from .types import GUARD_VERSION, TARGET_INTENTS, GuardConfig, GuardVerdict

INSTRUCTIONS = """\
TelegraphGuard screens payment destinations for fraud before an agent moves money.

Call `screen` with any blockchain address, ENS name, transaction hash, or URL
BEFORE using any payment, transfer, or wallet tool. Treat a `block` verdict as
final and a `review` verdict as requiring human approval.

Verdicts are backed by live Telegraph miner responses, each carrying an
on-chain signal hash that can be independently verified.
"""

SCREEN_DESCRIPTION = """\
Screen a payment destination for fraud BEFORE sending any funds.

You MUST call this and receive an "allow" verdict before using any payment,
transfer, or wallet tool. Accepts a blockchain address, ENS name, transaction
hash, or URL.

Returns a verdict of "allow", "review", or "block" with a 0-1 risk score and
the individual Telegraph miner signals behind it, each with a verifiable
signal hash.

- allow  -> safe to proceed with the payment.
- review -> STOP. Ask a human before proceeding. Do not send funds.
- block  -> STOP. Do not send funds under any circumstances. Report the reasons.

A "review" verdict is not a soft allow. If the guard cannot get enough
evidence, it returns "review" rather than guessing, and you must not proceed.
"""


def _summary(v: GuardVerdict) -> str:
    """Compact human/model-readable rendering placed alongside the JSON."""
    guidance = {
        "allow": "Safe to proceed with the payment.",
        "block": "DO NOT send funds. Report these reasons to the user.",
        "review": "Do not send funds without explicit human approval.",
    }[v.verdict]

    lines = [
        f"{v.verdict.upper()} — {v.target} ({v.target_type})",
        f"risk {v.risk:.2f} of 1.00 · confidence {v.confidence:.2f} · {v.elapsed_ms}ms",
        "",
    ]
    lines += [f"  - {r}" for r in v.reasons] or ["  - no reasons recorded"]
    lines.append("")

    ok = [s for s in v.signals if s.ok]
    if ok:
        lines.append("Signals:")
        for s in ok:
            risk = f"{s.risk:.2f}" if s.risk is not None else "—"
            lines.append(
                f"  {s.intent} · {s.miner_name or s.miner_id or '?'} · risk {risk}"
                + (f" · {s.verify_url}" if s.verify_url else "")
            )
        lines.append("")
    lines.append(guidance)
    return "\n".join(lines)


def build_server(config: GuardConfig | None = None, guard: Guard | None = None) -> Any:
    """Construct the MCP server. Kept importable so tests can drive the
    registered tools directly without spawning a transport."""
    from mcp.server.mcpserver import MCPServer

    cfg = config or GuardConfig()
    _guard = guard or Guard(cfg)

    server = MCPServer(
        name="telegraph-guard",
        title="TelegraphGuard",
        version=GUARD_VERSION,
        instructions=INSTRUCTIONS,
    )

    @server.tool(name="screen", description=SCREEN_DESCRIPTION)
    async def screen(target: str) -> dict[str, Any]:
        """Screen a payment destination for fraud."""
        verdict = await _guard.screen(target, cfg)
        payload = verdict.to_dict()
        # Lead with the instruction the model must act on, then the receipt.
        payload["summary"] = _summary(verdict)
        return payload

    @server.tool(
        name="list_miners",
        description=(
            "List the live Telegraph miners backing each screening intent. "
            "Useful for auditing which sources produced a verdict."
        ),
    )
    async def list_miners() -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as c:
            reg = await fetch_registry(c)
        return {
            intent: [
                {
                    "miner_id": m.id,
                    "name": m.name,
                    "endpoint": (m.endpoint_for(intent) or {}).get("path"),
                }
                for m in reg.miners_for(intent)
            ]
            for intent in TARGET_INTENTS
        }

    @server.resource(
        "telegraph-guard://config",
        name="Guard configuration",
        description="Active thresholds and safety defaults.",
        mime_type="application/json",
    )
    def config_resource() -> str:
        return json.dumps(
            {
                "allow_below": cfg.allow_below,
                "block_above": cfg.block_above,
                "deadline_ms": cfg.deadline_ms,
                "min_signals": cfg.min_signals,
                "fail_closed": cfg.fail_closed,
                "chain": cfg.chain,
                "guard_version": GUARD_VERSION,
            },
            indent=2,
        )

    return server


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="telegraph-guard-mcp",
        description="Expose TelegraphGuard screening over MCP.",
    )
    p.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "sse", "streamable-http"],
        help="stdio for Claude Desktop/Cursor; http for a shared gateway",
    )
    p.add_argument("--port", type=int, default=8402)
    p.add_argument("--chain", default="ethereum")
    p.add_argument("--allow-below", type=float, default=0.3)
    p.add_argument("--block-above", type=float, default=0.7)
    p.add_argument("--deadline-ms", type=int, default=8000)
    p.add_argument("--min-signals", type=int, default=2)
    p.add_argument("--fail-open", action="store_true", help="allow on failure (unsafe)")
    args = p.parse_args(argv)

    from .cli import _load_dotenv

    _load_dotenv()

    cfg = GuardConfig(
        allow_below=args.allow_below,
        block_above=args.block_above,
        deadline_ms=args.deadline_ms,
        min_signals=args.min_signals,
        fail_closed=not args.fail_open,
        chain=args.chain,
    )
    server = build_server(cfg)

    if args.transport == "stdio":
        server.run("stdio")
    else:
        os.environ.setdefault("FASTMCP_PORT", str(args.port))
        server.run(args.transport, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
