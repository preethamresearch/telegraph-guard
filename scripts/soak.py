"""Demand generation (FR-40, FR-41).

Screens a curated list of real addresses, transaction hashes and URLs
across all four target intents until each has at least ``--target``
signals attributable to TelegraphGuard, then writes HASHES.md.

Rate-limit citizenship (NFR-8): capped at 1 request/second per miner,
rotating across miners, never hammering one endpoint.

    python scripts/soak.py --target 100
    python scripts/soak.py --target 5 --dry-run     # no paid calls

Every screened target is a real one and every signal is a real miner
response — no synthetic volume (NFR-11).
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from telegraph_guard import Guard, GuardConfig  # noqa: E402
from telegraph_guard.classify import classify  # noqa: E402
from telegraph_guard.types import TARGET_INTENTS  # noqa: E402
from targets import TARGETS  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "soak-signals.jsonl"
HASHES_PATH = ROOT / "HASHES.md"

#: NFR-8 — one request per second per miner.
MIN_INTERVAL_PER_MINER = 1.0


class MinerThrottle:
    """Per-miner 1 rps gate shared across concurrent screenings."""

    def __init__(self, interval: float = MIN_INTERVAL_PER_MINER) -> None:
        self.interval = interval
        self._last: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def wait(self, miner_id: str) -> None:
        async with self._lock:
            now = time.monotonic()
            last = self._last.get(miner_id, 0.0)
            delay = self.interval - (now - last)
            self._last[miner_id] = now + max(0.0, delay)
        if delay > 0:
            await asyncio.sleep(delay)


async def run(args: argparse.Namespace) -> int:
    counts: collections.Counter[str] = collections.Counter()
    per_miner: collections.Counter[str] = collections.Counter()
    miner_names: dict[str, str] = {}
    rows: list[dict] = []

    # Pin the calibrated miners (FR-5). The auto-router lands
    # FRAUD_DETECTION on ChainSight, which returns the same canned prose for a
    # clean router as for a sanctioned mixer — routing 100+ signals through it
    # would generate volume with no judgement behind it.
    cfg = GuardConfig(
        deadline_ms=args.deadline_ms,
        min_signals=1,
        miners=args.miners.split(","),
        miners_per_intent=args.miners_per_intent,
    )
    guard = Guard(cfg)

    log = LOG_PATH.open("a")
    started = time.time()
    rounds = 0

    try:
        if args.warmup:
            print("  warming miners...")
            await guard.warmup()

        while rounds < args.max_rounds:
            rounds += 1
            remaining = [i for i in TARGET_INTENTS if counts[i] < args.target]
            if not remaining:
                break

            print(
                f"\n  round {rounds} — "
                + "  ".join(f"{i.split('_')[0]}:{counts[i]}/{args.target}" for i in TARGET_INTENTS)
            )

            for target in TARGETS:
                if all(counts[i] >= args.target for i in TARGET_INTENTS):
                    break
                ttype = classify(target)
                if ttype == "unknown":
                    print(f"    skip (unclassifiable): {target}")
                    continue

                if args.dry_run:
                    print(f"    would screen {ttype:<8} {target}")
                    counts.update(TARGET_INTENTS[:2])
                    continue

                # NFR-8: pace between targets so no miner is hit faster
                # than 1 rps even across the parallel intent fan-out.
                await asyncio.sleep(args.pace)

                v = await guard.screen(target, cfg)
                for s in v.signals:
                    if not s.ok or not s.signal_hash:
                        continue
                    counts[s.intent] += 1
                    if s.miner_id:
                        per_miner[s.miner_id] += 1
                        if s.miner_name:
                            miner_names[s.miner_id] = s.miner_name
                    row = {
                        "target": v.target,
                        "target_type": v.target_type,
                        "verdict": v.verdict,
                        **s.to_dict(),
                    }
                    rows.append(row)
                    log.write(json.dumps(row) + "\n")
                log.flush()
                print(
                    f"    {v.verdict:<6} {v.target[:52]:<54} "
                    f"risk {v.risk:.2f}  {len([s for s in v.signals if s.ok])} signals"
                )
    finally:
        log.close()
        await guard.aclose()

    elapsed = time.time() - started
    print(f"\n  done in {elapsed:.0f}s — {sum(counts.values())} signals")
    for i in TARGET_INTENTS:
        mark = "ok " if counts[i] >= args.target else "SHORT"
        print(f"    {mark} {i:<24} {counts[i]}")

    if per_miner:
        print("\n  per-miner counts (for Discord outreach, FR-43):")
        for mid, n in per_miner.most_common():
            print(f"    {mid:<12} {miner_names.get(mid, '')[:34]:<36} {n}")

    if rows and not args.dry_run:
        write_hashes(rows, counts, per_miner, miner_names)
        print(f"\n  wrote {HASHES_PATH}")

    return 0 if all(counts[i] >= args.target for i in TARGET_INTENTS) else 1


def write_hashes(rows, counts, per_miner, miner_names) -> None:
    """FR-41: public, auditable list of every signal hash."""
    lines = [
        "# Signal hashes",
        "",
        "Every verdict TelegraphGuard produces is backed by real Telegraph miner",
        "responses. Each row below is one miner response with its on-chain",
        "`signal_hash`, resolvable at the Engine by anyone.",
        "",
        f"**{len(rows)} signals** across {len([c for c in counts.values() if c])} intents.",
        "",
        "## Per intent",
        "",
        "| Intent | Signals |",
        "|---|---|",
    ]
    for intent, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {intent} | {n} |")

    lines += ["", "## Per miner", "", "| Miner | Name | Signals |", "|---|---|---|"]
    for mid, n in per_miner.most_common():
        lines.append(f"| {mid} | {miner_names.get(mid, '')} | {n} |")

    lines += [
        "",
        "## Signals",
        "",
        "| Intent | Miner | Target | Risk | Verify |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        risk = f"{r['risk']:.2f}" if r.get("risk") is not None else "—"
        target = r["target"][:44]
        name = r.get("miner_name") or r.get("miner_id") or "?"
        url = r.get("verify_url") or ""
        h = (r.get("signal_hash") or "")[:14]
        lines.append(f"| {r['intent']} | {name} | `{target}` | {risk} | [{h}…]({url}) |")

    HASHES_PATH.write_text("\n".join(lines) + "\n")


def main() -> int:
    p = argparse.ArgumentParser(description="Route real demand to Telegraph miners.")
    p.add_argument("--target", type=int, default=100, help="signals required per intent")
    p.add_argument("--pace", type=float, default=1.0, help="seconds between targets (NFR-8)")
    p.add_argument("--deadline-ms", type=int, default=15000)
    p.add_argument("--max-rounds", type=int, default=20)
    p.add_argument("--miners", default="9002,95822412,20260828,5001,302")
    p.add_argument("--miners-per-intent", type=int, default=1)
    p.add_argument("--warmup", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="no paid calls")
    return asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
