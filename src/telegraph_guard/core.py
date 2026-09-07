"""The guard itself: classify → fan-out → aggregate → gate → receipt.

Public surface is :func:`screen` (sync) and :func:`ascreen` (async).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx

from .aggregate import aggregate
from .classify import classify, intents_for, normalize
from .discovery import Miner, Registry, fetch_registry
from .engine import (
    PaymentUnavailable,
    ask_auto,
    ask_direct,
    build_payment_client,
    was_rate_limited,
)
from .extract import extract_confidence, extract_risk
from .types import (
    INTENT_FRAUD,
    INTENT_TX,
    INTENT_URL,
    INTENT_WALLET,
    GuardConfig,
    GuardVerdict,
    Signal,
    TargetType,
)

log = logging.getLogger("telegraph_guard")


# --- Query construction (FR-4) ---------------------------------------------
#
# Phrasing is tuned against the Engine's own published intent descriptions
# (GET /engine/v1/intents) so the auto-router lands on the intent we want
# rather than drifting — e.g. FRAUD_DETECTION's description keys on "how
# likely ... to be fraudulent", WALLET_BALANCE_CHECK on "what is the
# balance of X on <chain>".

def build_query(intent: str, target: str, target_type: TargetType, chain: str) -> str:
    if intent == INTENT_FRAUD:
        if target_type == "tx":
            return f"How likely is it that transaction {target} on {chain} is fraudulent?"
        if target_type == "url":
            return (
                f"How likely is it that the website {target} is a scam or "
                "phishing operation trying to take crypto payments?"
            )
        return f"How likely is the address {target} on {chain} to be fraudulent?"
    if intent == INTENT_WALLET:
        return f"What is the balance of {target} on {chain}?"
    if intent == INTENT_TX:
        return f"What was the status and gas used of transaction {target} on {chain}?"
    if intent == INTENT_URL:
        return f"Is this URL safe to click: {target}?"
    return f"Assess {target}."


class Guard:
    """Reusable guard holding the discovery cache and payment client.

    One instance per process is the intended usage — it keeps the miner
    registry warm and reuses the x402 connection pool.
    """

    def __init__(
        self,
        config: GuardConfig | None = None,
        private_key: str | None = None,
        registry: Registry | None = None,
    ) -> None:
        self.config = config or GuardConfig()
        self._private_key = private_key
        self._registry = registry
        self._client: httpx.AsyncClient | None = None
        self._free_client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    # -- plumbing ----------------------------------------------------------

    async def _paid(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = build_payment_client(self._private_key)
        return self._client

    async def _free(self) -> httpx.AsyncClient:
        """Unpaid client for discovery and receipt lookup, which are free."""
        if self._free_client is None:
            self._free_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self._free_client

    async def registry(self) -> Registry:
        """Cached miner registry, refreshed every 10 min (FR-13)."""
        async with self._lock:
            if self._registry is None or self._registry.stale:
                self._registry = await fetch_registry(await self._free())
            return self._registry

    async def aclose(self) -> None:
        for c in (self._client, self._free_client):
            if c is not None:
                await c.aclose()
        self._client = None
        self._free_client = None

    # -- warmup (FR-14) ----------------------------------------------------

    async def warmup(self) -> dict[str, Any]:
        """Fire one cheap request per target miner to defeat cold starts on
        free-tier miner hosting (FR-14, risk table §12).

        Uses the miner's own free health/meta route via the Engine where the
        miner publishes one, so warmup does not consume x402 balance.
        """
        reg = await self.registry()
        free = await self._free()
        seen: dict[str, Miner] = {}
        for miners in reg.by_intent.values():
            for m in miners:
                seen.setdefault(m.id, m)

        async def poke(m: Miner) -> tuple[str, str]:
            if not m.base_url:
                return m.id, "no base_url"
            paths = [e.get("path") for e in m.endpoints]
            path = next((p for p in ("/health", "/meta", "/") if p in paths), None)
            if path is None:
                return m.id, "no free route"
            try:
                r = await free.get(m.base_url.rstrip("/") + path, timeout=10.0)
                return m.id, f"HTTP {r.status_code}"
            except Exception as exc:
                return m.id, f"{type(exc).__name__}"

        results = await asyncio.gather(*(poke(m) for m in seen.values()))
        out = dict(results)
        log.info(json.dumps({"event": "warmup", "miners": len(out)}))
        return out

    # -- one call, with rate-limit retry (FR-12) ---------------------------

    async def _one_signal(
        self,
        intent: str,
        target: str,
        target_type: TargetType,
        config: GuardConfig,
    ) -> Signal:
        client = await self._paid()
        query = build_query(intent, target, target_type, config.chain)
        context = {"chain": config.chain, "target_type": target_type}

        if config.miners:
            sig = await self._direct_with_retry(client, intent, target, target_type, config)
        else:
            sig = await ask_auto(client, intent, query, context)
            if was_rate_limited(sig):
                # FR-12: retry once on the next miner in this intent's list.
                sig = await self._direct_with_retry(
                    client, intent, target, target_type, config, skip=sig.miner_id
                )

        self._decorate(sig)
        self._log(sig, target)
        return sig

    async def _direct_with_retry(
        self,
        client: httpx.AsyncClient,
        intent: str,
        target: str,
        target_type: TargetType,
        config: GuardConfig,
        skip: str | None = None,
    ) -> Signal:
        reg = await self.registry()
        candidates = reg.miners_for(intent)
        if config.miners:
            wanted = {str(m) for m in config.miners}
            preferred = [m for m in candidates if m.id in wanted]
            candidates = preferred + [m for m in candidates if m.id not in wanted]
        if skip:
            candidates = [m for m in candidates if m.id != skip]

        last: Signal | None = None
        for miner in candidates[:2]:  # FR-12: one retry, not a stampede.
            ep = miner.endpoint_for(intent)
            if ep is None:
                continue
            payload = self._payload_for(intent, target, target_type, config.chain)
            sig = await ask_direct(
                client,
                intent,
                miner,
                method=ep.get("method", "GET"),
                endpoint=ep.get("path", "/"),
                payload=payload,
            )
            last = sig
            if sig.ok and not was_rate_limited(sig):
                return sig
        if last is not None:
            return last
        return Signal(intent=intent, error=f"no miner with a usable {intent} endpoint")

    @staticmethod
    def _payload_for(
        intent: str, target: str, target_type: TargetType, chain: str
    ) -> dict[str, Any]:
        """Payload for the direct path. Field names follow the conventions the
        wallet/tx/url miners publish in their endpoint descriptions."""
        if intent == INTENT_TX or target_type == "tx":
            return {"tx_hash": target, "hash": target, "chain": chain}
        if intent == INTENT_URL or target_type == "url":
            return {"url": target}
        return {"address": target, "chain": chain}

    @staticmethod
    def _decorate(sig: Signal) -> None:
        """Fill risk/confidence from the raw miner result (FR-7)."""
        if not sig.ok:
            return
        if sig.confidence is None:
            sig.confidence = extract_confidence(sig.raw)
        if sig.risk is None:
            sig.risk = extract_risk(sig.raw)

    @staticmethod
    def _log(sig: Signal, target: str) -> None:
        """Structured JSON log per call (FR-16, NFR-7)."""
        log.info(
            json.dumps(
                {
                    "event": "signal",
                    "target": target,
                    "intent": sig.intent,
                    "miner_id": sig.miner_id,
                    "miner_name": sig.miner_name,
                    "risk": sig.risk,
                    "confidence": sig.confidence,
                    "duration_ms": sig.duration_ms,
                    "signal_hash": sig.signal_hash,
                    "cost_usd": sig.cost_usd,
                    "error": sig.error,
                }
            )
        )

    # -- the gate ----------------------------------------------------------

    async def screen(self, target: str, config: GuardConfig | None = None) -> GuardVerdict:
        """Screen a target and return a gated verdict (FR-1)."""
        cfg = config or self.config
        t0 = time.monotonic()

        target_type = classify(target)
        if target_type == "unknown":
            # FR-2: no calls made, no money spent.
            return aggregate(target, target_type, [], cfg, 0)

        norm = normalize(target, target_type)
        intents = intents_for(target_type)

        tasks = [
            asyncio.create_task(self._one_signal(i, norm, target_type, cfg))
            for i in intents
        ]

        # FR-10: signals that miss the deadline are dropped, not awaited.
        done, pending = await asyncio.wait(tasks, timeout=cfg.deadline_ms / 1000.0)
        for t in pending:
            t.cancel()

        signals: list[Signal] = []
        for t in done:
            try:
                signals.append(t.result())
            except PaymentUnavailable as exc:
                signals.append(Signal(intent="?", error=str(exc)))
            except Exception as exc:
                signals.append(Signal(intent="?", error=f"{type(exc).__name__}: {exc}"))
        for t in pending:
            signals.append(
                Signal(intent="?", error=f"deadline exceeded ({cfg.deadline_ms}ms)")
            )

        elapsed = int((time.monotonic() - t0) * 1000)
        verdict = aggregate(norm, target_type, signals, cfg, elapsed)
        log.info(
            json.dumps(
                {
                    "event": "verdict",
                    "target": norm,
                    "verdict": verdict.verdict,
                    "risk": verdict.risk,
                    "signals": len(signals),
                    "elapsed_ms": elapsed,
                }
            )
        )
        return verdict


# --- module-level convenience ----------------------------------------------

_default: Guard | None = None


def _guard(config: GuardConfig | None = None) -> Guard:
    global _default
    if _default is None:
        _default = Guard(config)
    elif config is not None:
        _default.config = config
    return _default


async def ascreen(target: str, config: GuardConfig | None = None) -> GuardVerdict:
    """Async entry point (FR-1)."""
    return await _guard(config).screen(target, config)


def screen(target: str, config: GuardConfig | None = None) -> GuardVerdict:
    """Sync entry point (PRD §9.2).

    Creates and tears down its own guard so it is safe to call from
    ordinary synchronous code. For hot paths, construct a :class:`Guard`
    once and call :meth:`Guard.screen`.
    """

    async def run() -> GuardVerdict:
        g = Guard(config)
        try:
            return await g.screen(target, config)
        finally:
            await g.aclose()

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run())
    raise RuntimeError(
        "screen() called from inside a running event loop — use `await ascreen(...)`"
    )
