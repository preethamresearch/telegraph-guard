"""Canonical data types for TelegraphGuard (PRD §9.1)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

GUARD_VERSION = "0.1.0"

ENGINE_BASE = "https://devnode.telegraphprotocol.com"

TargetType = Literal["address", "ens", "tx", "url", "unknown"]
Verdict = Literal["allow", "block", "review"]

# The four intents TelegraphGuard routes demand to (PRD §6).
INTENT_FRAUD = "FRAUD_DETECTION"
INTENT_URL = "URL_SCAN"
INTENT_WALLET = "WALLET_BALANCE_CHECK"
INTENT_TX = "ONCHAIN_TX_LOOKUP"

TARGET_INTENTS = [INTENT_FRAUD, INTENT_URL, INTENT_WALLET, INTENT_TX]

#: Intent fan-out per target type (FR-2).
FANOUT: dict[str, list[str]] = {
    "address": [INTENT_FRAUD, INTENT_WALLET],
    "ens": [INTENT_FRAUD, INTENT_WALLET],
    "tx": [INTENT_TX, INTENT_FRAUD],
    "url": [INTENT_URL, INTENT_FRAUD],
    "unknown": [],
}


def verify_url(signal_hash: str | None) -> str | None:
    """Public receipt URL for a signal hash (FR-11)."""
    if not signal_hash:
        return None
    return f"{ENGINE_BASE}/engine/v1/signal/{signal_hash}"


@dataclass
class GuardConfig:
    """Per-call options. Safe defaults per NFR-5 — a developer who changes
    nothing gets a conservative, fail-closed guard."""

    allow_below: float = 0.3
    block_above: float = 0.7
    deadline_ms: int = 8000
    min_signals: int = 2
    fail_closed: bool = True
    #: Direct-miner mode (FR-5). When set, calls POST /engine/v1/ask/{id}
    #: instead of the auto-routed path.
    miners: list[str] | None = None
    #: How many miners to query concurrently for each risk-bearing intent
    #: (FRAUD_DETECTION, URL_SCAN). Miner coverage is partial and uptime is
    #: uneven: a single miner failing over left the gate with no judgement at
    #: all in roughly one run in four. Redundancy costs one extra call per
    #: primary intent and removes that class of flake. Context intents
    #: (wallet, tx) stay single — they inform a verdict, never carry one.
    miners_per_intent: int = 1
    chain: str = "ethereum"
    verbose: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.allow_below <= 1.0:
            raise ValueError("allow_below must be in [0,1]")
        if not 0.0 <= self.block_above <= 1.0:
            raise ValueError("block_above must be in [0,1]")
        if self.allow_below > self.block_above:
            raise ValueError("allow_below must be <= block_above")
        if self.min_signals < 1:
            raise ValueError("min_signals must be >= 1")
        if self.miners_per_intent < 1:
            raise ValueError("miners_per_intent must be >= 1")


@dataclass
class Signal:
    """One miner response, with its on-chain receipt (FR-11)."""

    intent: str
    miner_id: str | None = None
    miner_name: str | None = None
    #: Normalised 0 = safe … 1 = fraud. None when the miner returned no
    #: usable risk information.
    risk: float | None = None
    #: Miner-reported confidence 0–1, or None when absent (FR-7).
    confidence: float | None = None
    duration_ms: int | None = None
    signal_hash: str | None = None
    reasoning: str | None = None
    cost_usd: float = 0.0
    #: Set when the call failed rather than returned a judgement.
    error: str | None = None
    #: Raw miner `result`, retained for --verbose and debugging.
    raw: Any = None

    @property
    def verify_url(self) -> str | None:
        return verify_url(self.signal_hash)

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("raw", None)
        d["verify_url"] = self.verify_url
        return d


@dataclass
class GuardVerdict:
    """Canonical output (PRD §9.1)."""

    target: str
    target_type: TargetType
    verdict: Verdict
    risk: float
    confidence: float
    reasons: list[str] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    cost_usd: float = 0.0
    elapsed_ms: int = 0
    thresholds: dict[str, float] = field(default_factory=dict)
    guard_version: str = GUARD_VERSION

    @property
    def allowed(self) -> bool:
        return self.verdict == "allow"

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "target_type": self.target_type,
            "verdict": self.verdict,
            "risk": round(self.risk, 4),
            "confidence": round(self.confidence, 4),
            "reasons": self.reasons,
            "signals": [s.to_dict() for s in self.signals],
            "cost_usd": round(self.cost_usd, 6),
            "elapsed_ms": self.elapsed_ms,
            "thresholds": self.thresholds,
            "guard_version": self.guard_version,
        }


class PaymentBlocked(Exception):
    """Raised by helpers that turn a non-allow verdict into a hard stop."""

    def __init__(self, verdict: GuardVerdict) -> None:
        self.verdict = verdict
        super().__init__(
            f"TelegraphGuard {verdict.verdict} for {verdict.target} "
            f"(risk={verdict.risk:.2f}): {'; '.join(verdict.reasons) or 'no reasons'}"
        )
