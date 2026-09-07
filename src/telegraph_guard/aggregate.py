"""Verdict aggregation and gating (FR-8, FR-9, FR-10).

This module is deliberately pure: same signals in, same verdict out, no
clock and no network (NFR-9). Everything that can fail lives in engine.py.
"""

from __future__ import annotations

from .extract import tx_context_bump, wallet_context_bump
from .types import (
    INTENT_FRAUD,
    INTENT_TX,
    INTENT_URL,
    INTENT_WALLET,
    GuardConfig,
    GuardVerdict,
    Signal,
    TargetType,
    Verdict,
)

#: Weight applied to a signal whose miner reported no confidence (FR-7).
UNKNOWN_CONFIDENCE_WEIGHT = 0.5

#: Intents that determine the primary risk. Wallet/tx intents inform it.
PRIMARY_INTENTS = (INTENT_FRAUD, INTENT_URL)


def _weighted(signals: list[Signal]) -> tuple[float | None, float]:
    """Confidence-weighted mean risk over signals that carry a risk.

    Returns (risk_or_None, mean_confidence)."""
    num = 0.0
    den = 0.0
    confs: list[float] = []
    for s in signals:
        if s.risk is None:
            continue
        w = s.confidence if s.confidence is not None else UNKNOWN_CONFIDENCE_WEIGHT
        num += s.risk * w
        den += w
        if s.confidence is not None:
            confs.append(s.confidence)
    if den == 0.0:
        return None, 0.0
    mean_conf = sum(confs) / len(confs) if confs else UNKNOWN_CONFIDENCE_WEIGHT
    return num / den, mean_conf


def aggregate(
    target: str,
    target_type: TargetType,
    signals: list[Signal],
    config: GuardConfig,
    elapsed_ms: int = 0,
) -> GuardVerdict:
    """Fold signals into a single verdict (FR-8, FR-9, FR-10)."""
    thresholds = {"allowBelow": config.allow_below, "blockAbove": config.block_above}
    usable = [s for s in signals if s.ok]
    cost = sum(s.cost_usd for s in signals)

    def build(verdict: Verdict, risk: float, conf: float, reasons: list[str]) -> GuardVerdict:
        return GuardVerdict(
            target=target,
            target_type=target_type,
            verdict=verdict,
            risk=round(max(0.0, min(1.0, risk)), 4),
            confidence=round(max(0.0, min(1.0, conf)), 4),
            reasons=reasons,
            signals=signals,
            cost_usd=cost,
            elapsed_ms=elapsed_ms,
            thresholds=thresholds,
        )

    # FR-2: we never guess at an unrecognised target.
    if target_type == "unknown":
        return build("review", 0.5, 0.0, ["unrecognised target — no miners called"])

    # FR-10 / FR-15: too little evidence to allow a payment.
    if len(usable) < config.min_signals:
        errs = [s.error for s in signals if s.error][:3]
        reason = (
            f"insufficient_signals: {len(usable)} usable of {config.min_signals} required"
        )
        reasons = [reason] + [f"error: {e}" for e in errs if e]
        # Fail-closed turns a dead network into a block, not an allow.
        verdict: Verdict = "block" if config.fail_closed and not usable else "review"
        return build(verdict, 1.0 if verdict == "block" else 0.5, 0.0, reasons)

    reasons: list[str] = []

    # Primary risk: the worst of the fraud/url judgements (FR-8, "max of").
    primary_risk: float | None = None
    primary_conf = 0.0
    for intent in PRIMARY_INTENTS:
        group = [s for s in usable if s.intent == intent]
        r, c = _weighted(group)
        if r is None:
            continue
        for s in group:
            if s.risk is not None:
                label = s.miner_name or s.miner_id or "miner"
                conf_txt = f" ({s.confidence:.2f})" if s.confidence is not None else ""
                reasons.append(f"{intent}: {label} risk {s.risk:.2f}{conf_txt}")
        if primary_risk is None or r > primary_risk:
            primary_risk = r
            primary_conf = c

    # Contextual bumps from wallet/tx intents (FR-8).
    bump = 0.0
    for s in usable:
        if s.intent == INTENT_WALLET:
            b, why = wallet_context_bump(s.raw)
            if b:
                bump += b
                if why:
                    reasons.append(why)
        elif s.intent == INTENT_TX:
            b, why = tx_context_bump(s.raw)
            if b:
                bump += b
                if why:
                    reasons.append(why)

    if primary_risk is None:
        # Miners answered but none produced an interpretable judgement.
        # Context alone is not grounds to allow money to move.
        risk = min(1.0, 0.5 + bump)
        reasons.append("no interpretable risk score from fraud/url miners")
        return build("review", risk, 0.0, reasons)

    risk = min(1.0, primary_risk + bump)

    if risk >= config.block_above:
        verdict = "block"
    elif risk < config.allow_below:
        verdict = "allow"
    else:
        verdict = "review"

    # An allow requires positive evidence of safety, not merely the absence of
    # a finding. A miner that states no confidence has told us how sure it is:
    # not at all. Observed live — with PREFLIGHT unavailable, the URL_SCAN
    # fallback landed on ChainSight, which scored a live malware dropper 0.10
    # with no confidence, and that lone signal authorised the payment.
    #
    # Such a signal may still raise risk (above), but it may not clear one.
    if verdict == "allow":
        primary = [
            s for s in usable if s.intent in PRIMARY_INTENTS and s.risk is not None
        ]
        if not any(s.confidence is not None for s in primary):
            verdict = "review"
            reasons.append(
                "no miner stated a confidence — insufficient evidence to allow"
            )

    if not reasons:
        reasons.append(f"aggregate risk {risk:.2f} from {len(usable)} signals")

    return build(verdict, risk, primary_conf, reasons)
