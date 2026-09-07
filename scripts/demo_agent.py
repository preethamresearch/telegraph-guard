"""Flagship demo (FR-30, FR-31, FR-32).

A LangGraph agent with a Base Sepolia wallet is told to pay three
invoices. TelegraphGuard sits between the agent's intent and its wallet:

    invoice → guard → allow  → pay      (real Base Sepolia USDC transfer)
                    → block  → abort    (prints the signals that stopped it)
                    → review → human    (escalates, does not pay)

Nothing about the verdict is simulated. Every decision is real Telegraph
miner output with resolvable signal hashes.

    python scripts/demo_agent.py            # screen + pay
    python scripts/demo_agent.py --no-send  # screen only, never transfer
"""

from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from langgraph.graph import END, StateGraph  # noqa: E402

from telegraph_guard import Guard, GuardConfig  # noqa: E402
from telegraph_guard.cli import render  # noqa: E402
from telegraph_guard.langgraph import guard_node, route_on_verdict  # noqa: E402

BASE_SEPOLIA_RPC = os.environ.get("BASE_SEPOLIA_RPC", "https://sepolia.base.org")
USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"

DIM, RESET, BOLD = "\033[2m", "\033[0m", "\033[1m"
GREEN, RED, YELLOW = "\033[32m", "\033[31m", "\033[33m"


#: The three invoices (FR-30). Targets are pre-tested for clean separation.
INVOICES = [
    {
        "name": "Invoice 1 — settle with a known contract",
        "to": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",  # Uniswap V2 router
        "amount": "0.01",
        "chain": "ethereum",
        "expect": "allow",
    },
    {
        "name": "Invoice 2 — a sanctioned mixer address",
        "to": "0x722122dF12D4e14e13Ac3b6895a86e84145b6967",  # Tornado Cash (OFAC SDN)
        "amount": "0.01",
        "chain": "ethereum",
        "expect": "block",
    },
    {
        "name": "Invoice 3 — payment page reached from an agent's web browse",
        "to": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
        "url": "http://testsafebrowsing.appspot.com/s/phishing.html",
        "amount": "0.01",
        "chain": "ethereum",
        "expect": "block",
    },
]


# --- the payment tool the agent is gated away from --------------------------


async def send_usdc(to: str, amount: str) -> str:
    """Actually move testnet USDC on Base Sepolia (FR-31).

    Reached only from the `execute` branch — i.e. only after the guard
    returned `allow`.
    """
    from eth_account import Account
    from web3 import AsyncHTTPProvider, AsyncWeb3

    key = os.environ["TELEGRAPH_GUARD_KEY"]
    acct = Account.from_key(key)
    w3 = AsyncWeb3(AsyncHTTPProvider(BASE_SEPOLIA_RPC))

    erc20 = [
        {
            "name": "transfer",
            "type": "function",
            "stateMutability": "nonpayable",
            "inputs": [
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
            ],
            "outputs": [{"name": "", "type": "bool"}],
        }
    ]
    usdc = w3.eth.contract(address=w3.to_checksum_address(USDC_BASE_SEPOLIA), abi=erc20)
    value = int(float(amount) * 10**6)

    tx = await usdc.functions.transfer(
        w3.to_checksum_address(to), value
    ).build_transaction(
        {
            "from": acct.address,
            "nonce": await w3.eth.get_transaction_count(acct.address),
            "chainId": 84532,
        }
    )
    signed = acct.sign_transaction(tx)
    tx_hash = await w3.eth.send_raw_transaction(signed.raw_transaction)
    return tx_hash.hex()


# --- graph ------------------------------------------------------------------


def build_graph(guard: Guard, cfg: GuardConfig, send: bool):
    async def pay(state: dict) -> dict:
        p = state["pending_payment"]
        if not send:
            print(f"    {GREEN}would send{RESET} {p['amount']} USDC → {p['to']}")
            return {**state, "result": "allowed (send skipped)"}
        try:
            h = await send_usdc(p["to"], p["amount"])
            h = h if h.startswith("0x") else "0x" + h
            print(f"    {GREEN}sent{RESET} {p['amount']} USDC → {p['to']}")
            print(f"    {DIM}https://sepolia.basescan.org/tx/{h}{RESET}")
            return {**state, "result": f"sent {h}"}
        except Exception as exc:
            # A failed transfer is a wallet problem, not a guard problem —
            # the screening above it was still real.
            print(f"    {YELLOW}transfer failed{RESET}: {type(exc).__name__}: {exc}")
            return {**state, "result": f"transfer failed: {exc}"}

    async def abort(state: dict) -> dict:
        print(f"    {RED}BLOCKED — no funds moved.{RESET}")
        return {**state, "result": "blocked"}

    async def hitl(state: dict) -> dict:
        print(f"    {YELLOW}ESCALATED to a human — no funds moved.{RESET}")
        return {**state, "result": "escalated"}

    g = StateGraph(dict)
    g.add_node("guard", guard_node(cfg, guard=guard))
    g.add_node("pay", pay)
    g.add_node("abort", abort)
    g.add_node("hitl", hitl)
    g.set_entry_point("guard")
    g.add_conditional_edges(
        "guard", route_on_verdict, {"execute": "pay", "abort": "abort", "human": "hitl"}
    )
    for n in ("pay", "abort", "hitl"):
        g.add_edge(n, END)
    return g.compile()


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--no-send", action="store_true", help="screen only, never transfer")
    p.add_argument("--no-warmup", action="store_true")
    p.add_argument("--deadline-ms", type=int, default=15000)
    args = p.parse_args()

    cfg = GuardConfig(deadline_ms=args.deadline_ms)
    guard = Guard(cfg)
    app = build_graph(guard, cfg, send=not args.no_send)

    print(f"\n{BOLD}  TelegraphGuard — agent invoice run{RESET}")
    print(f"{DIM}  guard between the agent's intent and its wallet{RESET}")

    results = []
    try:
        if not args.no_warmup:
            print(f"\n{DIM}  warming miners...{RESET}")
            await guard.warmup()

        for inv in INVOICES:
            print(f"\n{BOLD}  {inv['name']}{RESET}")
            payment = {k: v for k, v in inv.items() if k not in ("name", "expect")}
            out = await app.ainvoke({"pending_payment": payment})
            v = out["guard_verdict"]
            print(render(v))

            outcome = classify_outcome(v, inv["expect"])
            colour = {PASS: GREEN, FAIL: RED, INCONCLUSIVE: YELLOW}[outcome]
            print(
                f"    {DIM}expected {inv['expect']}, got {v.verdict}{RESET}  "
                f"{colour}[{outcome}]{RESET}"
            )
            if outcome == INCONCLUSIVE:
                print(f"    {YELLOW}{DESCRIPTIONS[INCONCLUSIVE]}{RESET}")
            results.append((inv["name"], inv["expect"], v, outcome))
    finally:
        await guard.aclose()

    return report(results)


# --- outcome classification -------------------------------------------------
#
# A verdict that matches for the wrong reason is not a passing demo. If the
# guard never obtained a usable miner signal — an unfunded wallet, a dead
# node, a blown deadline — then every target blocks identically and two of
# three "expected block" cases match by accident. Reporting that as 2/3
# passing would be actively misleading in a recorded demo, so evidence is
# required before a match counts.

PASS = "PASS"
FAIL = "FAIL"
INCONCLUSIVE = "INCONCLUSIVE"

DESCRIPTIONS = {
    INCONCLUSIVE: (
        "^ no miner evidence — this blocked because screening never ran, "
        "not because anything was flagged."
    ),
}


def has_evidence(v) -> bool:
    """Whether a verdict rests on real miner output.

    A signal counts only if it came back without error AND carries a
    signal_hash, which is what makes it independently verifiable.
    """
    return any(s.ok and s.signal_hash for s in v.signals)


def classify_outcome(v, expected: str) -> str:
    """PASS only when the verdict matches *and* real signals produced it."""
    if not has_evidence(v):
        return INCONCLUSIVE
    return PASS if v.verdict == expected else FAIL


def report(results) -> int:
    """Print the summary and return a shell exit code.

    Non-zero unless every case passed on real evidence, so a recorded run
    or a CI job cannot quietly present an inconclusive result as a success.
    """
    print(f"\n{BOLD}  Summary{RESET}")
    counts = {PASS: 0, FAIL: 0, INCONCLUSIVE: 0}
    for name, expect, v, outcome in results:
        counts[outcome] += 1
        colour = {PASS: GREEN, FAIL: RED, INCONCLUSIVE: YELLOW}[outcome]
        n_sig = len([s for s in v.signals if s.ok and s.signal_hash])
        print(
            f"    {colour}{outcome:<12}{RESET} {v.verdict:<6} "
            f"(expected {expect:<6}) {DIM}{n_sig} signals{RESET}  {name}"
        )

    total = len(results)
    print()
    if counts[INCONCLUSIVE] == total:
        print(f"  {YELLOW}{BOLD}THIS RUN PROVED NOTHING.{RESET}")
        print(
            f"  {YELLOW}No target produced a single verifiable miner signal, so "
            f"every invoice{RESET}"
        )
        print(
            f"  {YELLOW}blocked for the same reason. The guard failed closed "
            f"correctly — but no{RESET}"
        )
        print(f"  {YELLOW}screening happened. Do not present this as a demo.{RESET}")
        print(f"\n  {DIM}Fund the signer, then re-run:  telegraph-guard wallet{RESET}\n")
        return 2
    if counts[INCONCLUSIVE]:
        print(
            f"  {YELLOW}{counts[INCONCLUSIVE]} of {total} inconclusive — "
            f"those cases had no miner evidence.{RESET}\n"
        )
        return 2
    if counts[FAIL]:
        print(f"  {RED}{counts[FAIL]} of {total} did not match expectations.{RESET}\n")
        return 1
    print(f"  {GREEN}{total} of {total} passed on real miner evidence.{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
