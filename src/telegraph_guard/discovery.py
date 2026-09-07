"""Startup discovery of intents and miners (FR-13, FR-5).

Discovery endpoints are free and unauthenticated, so this is the only
layer permitted to cache (NFR-3: never cache inference). Miner endpoint
and payload shapes are pulled from ``/api/miners`` at startup rather than
hardcoded, so a miner changing its route does not break us.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .types import ENGINE_BASE, TARGET_INTENTS

REFRESH_SECONDS = 600  # FR-13: refresh every 10 min.

#: Route-name fallbacks for miners that do not name the intent in their
#: endpoint description. Ordered most-specific first so that, for example,
#: ONCHAIN_TX_LOOKUP prefers "/tx-lookup" over a bare "/tx".
_PATH_HINTS: dict[str, tuple[str, ...]] = {
    # An address-shaped target must prefer an address-shaped endpoint.
    # TxLens exposes both /fraud-query (a named scheme, "was BitConnect a
    # scam") and /assess-wallet (an address, checked against a registry of
    # 2,600+ OFAC and scam entities). Matching "fraud" first picked the
    # wrong one and the miner rejected the payload outright.
    "FRAUD_DETECTION": (
        "assess-wallet", "wallet-risk", "fraud-detection", "risk-check",
        "anomaly", "fraud-query", "fraud", "risk", "assess", "analyze",
    ),
    "URL_SCAN": ("url-scan", "urlscan", "url", "scan"),
    "WALLET_BALANCE_CHECK": ("wallet-balance", "wallet/balance", "balance", "wallet"),
    "ONCHAIN_TX_LOOKUP": (
        "transaction/lookup", "tx-lookup", "check-tx", "transaction", "/tx",
    ),
}

#: Routes that exist for liveness/discovery rather than inference.
_META_PATHS = {"/", "/health", "/meta", "/healthz", "/status"}


class DiscoveryError(RuntimeError):
    """Raised when a target intent has no live miners (FR-13: fail loudly)."""


@dataclass
class Miner:
    id: str
    name: str
    slug: str = ""
    base_url: str = ""
    capabilities: list[str] = field(default_factory=list)
    endpoints: list[dict[str, Any]] = field(default_factory=list)
    cost_per_call: float = 0.0

    def endpoint_for(self, intent: str) -> dict[str, Any] | None:
        """Best endpoint for an intent (FR-5: shapes come from the registry,
        never hardcoded).

        Miners follow three conventions for naming the intent an endpoint
        serves — leading (``"FRAUD_DETECTION. ..."``), trailing and
        parenthesised (``"... (FRAUD_DETECTION)."``), or not at all. We try
        the explicit name first, then fall back to the route itself, then to
        a single-purpose miner's only route.
        """
        # 1. The endpoint names its intent. Intent ids are mutually
        #    non-overlapping, so a plain substring test is unambiguous.
        for ep in self.endpoints:
            if intent in (ep.get("description") or "").upper():
                return ep

        # 2. Match on the route path, most specific keyword first.
        for keyword in _PATH_HINTS.get(intent, ()):
            for ep in self.endpoints:
                if keyword in (ep.get("path") or "").lower():
                    return ep

        # 3. A miner registered for exactly this intent, exposing exactly one
        #    route, can only mean that route.
        real = [e for e in self.endpoints if (e.get("path") or "/") not in _META_PATHS]
        if len(real) == 1 and self.capabilities == [intent]:
            return real[0]

        return None


@dataclass
class Registry:
    """Cached view of the Telegraph miner landscape."""

    by_intent: dict[str, list[Miner]] = field(default_factory=dict)
    fetched_at: float = 0.0

    @property
    def stale(self) -> bool:
        return (time.monotonic() - self.fetched_at) > REFRESH_SECONDS

    def miners_for(self, intent: str) -> list[Miner]:
        return list(self.by_intent.get(intent, []))

    def miner(self, miner_id: str) -> Miner | None:
        for miners in self.by_intent.values():
            for m in miners:
                if m.id == str(miner_id):
                    return m
        return None


def _parse_miner(raw: dict[str, Any]) -> Miner:
    try:
        cost = float(raw.get("cost_per_call") or 0.0)
    except (TypeError, ValueError):
        cost = 0.0
    return Miner(
        id=str(raw.get("id") or raw.get("miner_id") or ""),
        name=raw.get("name") or raw.get("miner_name") or "",
        slug=raw.get("slug") or "",
        base_url=raw.get("base_url") or "",
        capabilities=list(raw.get("capabilities") or []),
        endpoints=list(raw.get("endpoints") or []),
        cost_per_call=cost,
    )


async def fetch_registry(
    client: httpx.AsyncClient,
    intents: list[str] | None = None,
    timeout: float = 20.0,
) -> Registry:
    """Fetch miners for each target intent. Raises DiscoveryError if any
    target intent has zero miners (FR-13)."""
    intents = intents or TARGET_INTENTS

    async def one(intent: str) -> tuple[str, list[Miner]]:
        r = await client.get(
            f"{ENGINE_BASE}/api/miners",
            params={"intent": intent},
            timeout=timeout,
        )
        r.raise_for_status()
        body = r.json()
        raw = body.get("miners", []) if isinstance(body, dict) else body
        return intent, [_parse_miner(m) for m in raw]

    results = await asyncio.gather(*(one(i) for i in intents), return_exceptions=True)

    by_intent: dict[str, list[Miner]] = {}
    failures: list[str] = []
    for intent, res in zip(intents, results):
        if isinstance(res, BaseException):
            failures.append(f"{intent}: {type(res).__name__}: {res}")
            continue
        _, miners = res
        if not miners:
            failures.append(f"{intent}: 0 miners")
        by_intent[intent] = miners

    if failures:
        raise DiscoveryError(
            "Telegraph discovery failed for target intents — " + "; ".join(failures)
        )

    return Registry(by_intent=by_intent, fetched_at=time.monotonic())
