"""CLI (FR-23): `telegraph-guard screen 0x...`

Prints a verdict table with clickable verify URLs so a judge or a miner
operator can audit every signal that produced the decision.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys

from .core import Guard
from .discovery import fetch_registry
from .engine import KEY_ENV, PaymentUnavailable, signer_address
from .types import GuardConfig, GuardVerdict

_COLOR = {"allow": "\033[32m", "block": "\033[31m", "review": "\033[33m"}
_RESET = "\033[0m"
_DIM = "\033[2m"


def _c(text: str, code: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{code}{text}{_RESET}"


def render(v: GuardVerdict, verbose: bool = False) -> str:
    lines: list[str] = []
    color = _COLOR.get(v.verdict, "")
    lines.append("")
    lines.append(
        f"  {_c(v.verdict.upper(), color)}  {v.target}  "
        f"{_c(f'[{v.target_type}]', _DIM)}"
    )
    allow_below = v.thresholds.get("allowBelow", 0.3)
    block_above = v.thresholds.get("blockAbove", 0.7)
    thresholds = f"(allow<{allow_below} block>={block_above})"
    lines.append(
        f"  risk {v.risk:.2f}  confidence {v.confidence:.2f}  {_c(thresholds, _DIM)}"
    )
    lines.append("")

    for r in v.reasons:
        lines.append(f"    · {r}")
    if v.reasons:
        lines.append("")

    if v.signals:
        lines.append(f"  {_c('SIGNALS', _DIM)}")
        for s in v.signals:
            if not s.ok:
                lines.append(f"    {s.intent:<22} {_c('error', _COLOR['block'])}  {s.error}")
                continue
            risk = f"{s.risk:.2f}" if s.risk is not None else "  — "
            conf = f"{s.confidence:.2f}" if s.confidence is not None else "  — "
            name = (s.miner_name or s.miner_id or "?")[:24]
            dur = f"{s.duration_ms}ms" if s.duration_ms else "—"
            lines.append(
                f"    {s.intent:<22} {name:<26} risk {risk}  conf {conf}  {dur:>7}"
            )
            if s.verify_url:
                lines.append(f"      {_c(s.verify_url, _DIM)}")
            if verbose and s.reasoning:
                lines.append(f"      {_c('router: ' + s.reasoning, _DIM)}")
            if verbose and s.raw is not None:
                blob = json.dumps(s.raw)[:400]
                lines.append(f"      {_c('result: ' + blob, _DIM)}")
        lines.append("")

    lines.append(
        f"  {_c(f'{len([s for s in v.signals if s.ok])} signals · {v.elapsed_ms}ms · ${v.cost_usd:.4f} · guard {v.guard_version}', _DIM)}"
    )
    lines.append("")
    return "\n".join(lines)


async def _cmd_screen(args: argparse.Namespace) -> int:
    cfg = GuardConfig(
        allow_below=args.allow_below,
        block_above=args.block_above,
        deadline_ms=args.deadline_ms,
        min_signals=args.min_signals,
        fail_closed=not args.fail_open,
        miners=args.miners.split(",") if args.miners else None,
        chain=args.chain,
        verbose=args.verbose,
    )
    guard = Guard(cfg)
    try:
        if args.warmup:
            await guard.warmup()
        verdicts = []
        for target in args.targets:
            v = await guard.screen(target, cfg)
            verdicts.append(v)
            if args.json:
                print(json.dumps(v.to_dict(), indent=2))
            else:
                print(render(v, args.verbose))
    finally:
        await guard.aclose()

    # Exit non-zero when anything was not allowed, so CI and shell
    # pipelines can gate on it.
    return 0 if all(v.verdict == "allow" for v in verdicts) else 1


async def _cmd_miners(args: argparse.Namespace) -> int:
    import httpx

    async with httpx.AsyncClient() as c:
        reg = await fetch_registry(c)
    for intent, miners in reg.by_intent.items():
        print(f"\n  {intent}  ({len(miners)} miners)")
        for m in miners:
            ep = m.endpoint_for(intent)
            path = ep.get("path") if ep else "—"
            print(f"    {m.id:<12} {m.name[:38]:<40} {path}")
    print()
    return 0


async def _cmd_warmup(args: argparse.Namespace) -> int:
    guard = Guard()
    try:
        res = await guard.warmup()
    finally:
        await guard.aclose()
    for mid, status in sorted(res.items()):
        print(f"  {mid:<12} {status}")
    return 0


def _cmd_wallet(args: argparse.Namespace) -> int:
    try:
        addr = signer_address()
    except PaymentUnavailable as exc:
        print(f"  {exc}", file=sys.stderr)
        return 1
    print(f"\n  signer   {addr}")
    print("  network  Base Sepolia (eip155:84532)")
    print("  needs    testnet USDC — the Engine charges $0.01 per call")
    print("  faucet   https://faucet.circle.com  (select Base Sepolia)\n")
    return 0


def _load_dotenv() -> None:
    """Load a local .env if present, without clobbering the real environment.

    Kept dependency-free and deliberately dumb: `KEY=value` lines only.
    An already-exported variable always wins.
    """
    path = os.path.join(os.getcwd(), ".env")
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                if key and key not in os.environ:
                    os.environ[key] = value.strip().strip("'\"")
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="telegraph-guard",
        description="Pre-transaction safety gate for AI agents, backed by Telegraph miners.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("screen", help="screen an address, tx hash, ENS name, or URL")
    s.add_argument("targets", nargs="+")
    s.add_argument("--chain", default="ethereum")
    s.add_argument("--allow-below", type=float, default=0.3)
    s.add_argument("--block-above", type=float, default=0.7)
    s.add_argument("--deadline-ms", type=int, default=8000)
    s.add_argument("--min-signals", type=int, default=2)
    s.add_argument("--miners", help="comma-separated miner ids for direct mode (FR-5)")
    s.add_argument("--fail-open", action="store_true", help="allow on failure (unsafe)")
    s.add_argument("--warmup", action="store_true", help="warm miners before screening")
    s.add_argument("--json", action="store_true")
    s.add_argument("-v", "--verbose", action="store_true")

    sub.add_parser("miners", help="list live miners per target intent")
    sub.add_parser("warmup", help="warm all target miners")
    sub.add_parser("wallet", help="show the x402 signer address to fund")

    args = p.parse_args(argv)

    _load_dotenv()
    logging.basicConfig(
        level=logging.INFO if os.environ.get("TELEGRAPH_GUARD_LOG") else logging.WARNING,
        format="%(message)s",
    )

    if args.cmd == "wallet":
        return _cmd_wallet(args)
    handler = {"screen": _cmd_screen, "miners": _cmd_miners, "warmup": _cmd_warmup}[args.cmd]
    try:
        return asyncio.run(handler(args))
    except PaymentUnavailable as exc:
        print(f"\n  {exc}\n", file=sys.stderr)
        print(f"  Run `telegraph-guard wallet` after setting {KEY_ENV}.\n", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
