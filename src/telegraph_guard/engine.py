"""Telegraph Engine transport with x402 payment (FR-3, FR-4, FR-5, FR-6, FR-12).

All inference goes through the Engine, never to a miner's own base URL —
direct calls produce no signal and do not count as Telegraph usage (FR-3).

Payment is x402. The node currently charges $0.01 per call on both the
auto-routed and direct paths; the amount, asset and network are always
read from the 402 challenge, never hardcoded (FR-6).
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx

from .discovery import Miner
from .types import ENGINE_BASE, Signal

log = logging.getLogger("telegraph_guard.engine")

KEY_ENV = "TELEGRAPH_GUARD_KEY"


class PaymentUnavailable(RuntimeError):
    """No usable wallet key, so no paid call can be made."""


def _looks_rate_limited(payload: Any, status: int) -> bool:
    """FR-12: detect a rate-limit signal on either path."""
    if status == 429:
        return True
    blob = json.dumps(payload).lower() if payload is not None else ""
    return "rate limit" in blob or "rate_limit" in blob or "too many requests" in blob


def build_payment_client(private_key: str | None = None) -> httpx.AsyncClient:
    """An httpx client that transparently answers 402 challenges (FR-6).

    The key is read from the environment and handed straight to the x402
    signer. It is never logged and never sent anywhere else (NFR-4).
    """
    key = private_key or os.environ.get(KEY_ENV)
    if not key:
        raise PaymentUnavailable(
            f"{KEY_ENV} is not set. TelegraphGuard needs a Base Sepolia key "
            "holding testnet USDC to pay the Engine's x402 challenge. "
            "Testnet keys only — never use a mainnet key."
        )

    from eth_account import Account
    from x402.client import x402Client
    from x402.http.clients.httpx import x402HttpxClient
    from x402.mechanisms.evm.exact import register_exact_evm_client
    from x402.mechanisms.evm.signers import EthAccountSigner

    account = Account.from_key(key)
    x402 = x402Client()
    # Networks come from the challenge's accepts[]; registering the EVM
    # exact scheme lets the selector pick Base Sepolia when offered.
    register_exact_evm_client(x402, EthAccountSigner(account))
    return x402HttpxClient(x402, timeout=httpx.Timeout(60.0))


def signer_address(private_key: str | None = None) -> str:
    key = private_key or os.environ.get(KEY_ENV)
    if not key:
        raise PaymentUnavailable(f"{KEY_ENV} is not set")
    from eth_account import Account

    return Account.from_key(key).address


def _signal_from_response(intent: str, body: dict[str, Any], elapsed_ms: int) -> Signal:
    """Map an Engine response onto a Signal receipt (FR-11)."""
    return Signal(
        intent=body.get("intent") or intent,
        miner_id=str(body["miner_id"]) if body.get("miner_id") is not None else None,
        miner_name=body.get("miner_name"),
        duration_ms=body.get("duration_ms") or elapsed_ms,
        signal_hash=body.get("signal_hash"),
        reasoning=body.get("reasoning"),
        cost_usd=float(body.get("cost_usd") or 0.0),
        raw=body.get("result"),
    )


async def ask_auto(
    client: httpx.AsyncClient,
    intent: str,
    query: str,
    context: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> Signal:
    """Auto-routed ask (FR-4). Never blocked, has a fallback miner lined up,
    and returns the router's `reasoning`."""
    payload: dict[str, Any] = {"query": query}
    if context:
        payload["context"] = context

    t0 = time.monotonic()
    try:
        r = await client.post(
            f"{ENGINE_BASE}/engine/v1/ask", json=payload, timeout=timeout
        )
    except Exception as exc:  # network, payment, timeout
        return Signal(intent=intent, error=f"{type(exc).__name__}: {exc}")
    elapsed = int((time.monotonic() - t0) * 1000)

    return _finish(intent, r, elapsed)


async def ask_direct(
    client: httpx.AsyncClient,
    intent: str,
    miner: Miner,
    method: str,
    endpoint: str,
    payload: dict[str, Any],
    timeout: float = 30.0,
    acknowledge_warnings: bool = False,
) -> Signal:
    """Direct-miner ask (FR-5) for deterministic demos and consensus mode."""
    body: dict[str, Any] = {
        "method": method,
        "endpoint": endpoint,
        "payload": payload,
    }
    if acknowledge_warnings:
        body["acknowledge_warnings"] = True

    t0 = time.monotonic()
    try:
        r = await client.post(
            f"{ENGINE_BASE}/engine/v1/ask/{miner.id}", json=body, timeout=timeout
        )
    except Exception as exc:
        return Signal(
            intent=intent,
            miner_id=miner.id,
            miner_name=miner.name,
            error=f"{type(exc).__name__}: {exc}",
        )
    elapsed = int((time.monotonic() - t0) * 1000)

    sig = _finish(intent, r, elapsed)
    sig.miner_id = sig.miner_id or miner.id
    sig.miner_name = sig.miner_name or miner.name
    return sig


def _finish(intent: str, r: httpx.Response, elapsed: int) -> Signal:
    # A 402 that survives the x402 transport means the signed payment was
    # rejected at settlement. On testnet that is almost always an unfunded
    # signer, so say so rather than surfacing a bare status code.
    if r.status_code == 402:
        return Signal(
            intent=intent,
            duration_ms=elapsed,
            error=(
                "payment rejected at settlement — the signer is most likely out of "
                "Base Sepolia USDC. Check the balance of the address printed by "
                "`telegraph-guard wallet` and top it up at https://faucet.circle.com"
            ),
        )

    try:
        body = r.json()
    except Exception:
        return Signal(
            intent=intent,
            duration_ms=elapsed,
            error=f"HTTP {r.status_code}: non-JSON response",
        )

    if r.status_code >= 400 or _looks_rate_limited(body, r.status_code):
        detail = body.get("error") or body.get("detail") or json.dumps(body)[:200]
        sig = Signal(intent=intent, duration_ms=elapsed, error=f"HTTP {r.status_code}: {detail}")
        # 422 on the direct path is a predicted failure and is not charged.
        sig.rate_limited = _looks_rate_limited(body, r.status_code)  # type: ignore[attr-defined]
        return sig

    sig = _signal_from_response(intent, body, elapsed)
    warnings = body.get("warnings") or []
    if warnings and _looks_rate_limited(warnings, 200):
        sig.rate_limited = True  # type: ignore[attr-defined]
    return sig


def was_rate_limited(sig: Signal) -> bool:
    return bool(getattr(sig, "rate_limited", False))
