"""Confidence and risk extraction from heterogeneous miner results (FR-7).

Telegraph miners do not share a result schema. TxLens returns a 0–1
``confidence`` plus a ``summary``; DegenLens returns a bounded risk tier
with its measurements; URL scanners return verdict strings. This module
normalises whatever arrived into:

  * ``risk``       — 0.0 safe … 1.0 fraudulent, or None if nothing usable
  * ``confidence`` — 0–1 as reported by the miner, or None if absent

Polarity matters: a "trust score" of 0.9 and a "risk score" of 0.9 mean
opposite things, so keys are matched against explicit safe/unsafe
vocabularies rather than a generic "find a float" sweep. Anything we
cannot interpret returns None and is weighted 0.5 downstream (FR-7)
rather than being silently treated as safe.
"""

from __future__ import annotations

import re
from typing import Any

# Keys whose value rises with danger.
_RISK_KEYS = (
    "risk_score", "riskscore", "fraud_score", "fraudscore", "risk",
    "fraud_probability", "fraud_likelihood", "threat_score", "malicious_score",
    "scam_score", "abuse_score", "phishing_score", "severity_score",
)
# Keys whose value rises with safety — inverted on extraction.
_SAFE_KEYS = (
    "safety_score", "trust_score", "trustscore", "reputation_score",
    "reputation", "safety", "trust",
)
# Boolean flags that assert danger directly.
_BOOL_RISK_KEYS = (
    "is_malicious", "malicious", "is_fraud", "is_fraudulent", "is_scam",
    "is_phishing", "phishing", "blacklisted", "is_blacklisted", "suspicious",
    "is_suspicious", "flagged",
)
_CONFIDENCE_KEYS = ("confidence", "confidence_score", "certainty", "score_confidence")

# Categorical risk tiers / verdict strings → risk value.
_TIERS: dict[str, float] = {
    "critical": 0.95, "severe": 0.95, "malicious": 0.95, "phishing": 0.95,
    "scam": 0.95, "fraud": 0.9, "fraudulent": 0.9, "dangerous": 0.9,
    "high": 0.85, "high_risk": 0.85, "elevated": 0.65, "medium": 0.5,
    "moderate": 0.5, "unknown": None, "unrated": None, "none": 0.05,
    "low": 0.15, "low_risk": 0.15, "minimal": 0.1, "safe": 0.05,
    "clean": 0.05, "benign": 0.05, "legitimate": 0.05, "trusted": 0.02,
    "ok": 0.05, "harmless": 0.05, "no_risk": 0.02,
}
_TIER_KEYS = (
    "risk_tier", "risk_level", "tier", "level", "verdict", "classification",
    "category", "status", "rating", "label", "assessment", "result",
)


def _walk(obj: Any, depth: int = 0):
    """Yield (lowercased_key, value) pairs from a nested result, shallow-first."""
    if depth > 4:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k).lower(), v
            if isinstance(v, (dict, list)):
                yield from _walk(v, depth + 1)
    elif isinstance(obj, list):
        for item in obj[:20]:
            if isinstance(item, (dict, list)):
                yield from _walk(item, depth + 1)


def _as_unit_float(v: Any) -> float | None:
    """Coerce to 0–1. Accepts 0–1 floats, 0–100 ints, and '85%' strings."""
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        f = float(v)
    elif isinstance(v, str):
        s = v.strip().rstrip("%")
        try:
            f = float(s)
        except ValueError:
            return None
        if v.strip().endswith("%"):
            f /= 100.0
    else:
        return None
    if f != f:  # NaN
        return None
    if 0.0 <= f <= 1.0:
        return f
    if 1.0 < f <= 100.0:
        return f / 100.0
    return max(0.0, min(1.0, f))


def _tier_value(v: Any) -> float | None:
    if not isinstance(v, str):
        return None
    key = v.strip().lower().replace(" ", "_").replace("-", "_")
    if key in _TIERS:
        return _TIERS[key]
    # "high risk", "likely phishing", "no threats detected"
    for word, val in _TIERS.items():
        if val is None:
            continue
        if re.search(rf"\b{re.escape(word)}\b", key):
            return val
    return None


def extract_confidence(result: Any) -> float | None:
    """Miner-reported confidence 0–1, or None when the miner gives none."""
    for key, val in _walk(result):
        if key in _CONFIDENCE_KEYS:
            f = _as_unit_float(val)
            if f is not None:
                return f
    return None


# --- Prose fallback ---------------------------------------------------------
#
# Several miners answer in natural language with no numeric score at all.
# Observed live from ChainSight (302) on FRAUD_DETECTION:
#
#   {"address": "0xabab…", "answer": "Based on publicly available blockchain
#    analytics and fraud-intelligence sources, the address … does not appear
#    in any known scam, phishing, or fraud database, and no …"}
#
# Without this fallback such a miner contributes nothing, and a clean address
# degrades to `review` — safe, but useless as a gate.
#
# Prose is weaker evidence than a number, so the values below are pulled in
# from the extremes: a prose "safe" is 0.15, not 0.05, and a prose "risky" is
# 0.8, not 0.95. Both still clear the default thresholds, but a single
# contradicting numeric signal outweighs them.

_PROSE_KEYS = (
    "answer", "summary", "signal", "explanation", "reasoning", "analysis",
    "conclusion", "assessment", "message", "description", "details", "text",
)

PROSE_SAFE_RISK = 0.15
PROSE_UNSAFE_RISK = 0.8

_SAFE_PATTERNS = (
    r"do(?:es)?\s+not\s+appear",
    r"\bno\s+(?:known\s+)?(?:evidence|indication|indications|reports?|records?|"
    r"history|signs?|association)\b",
    r"\bnot\s+(?:been\s+)?(?:flagged|blacklisted|reported|sanctioned|associated|linked)\b",
    r"\bappears?\s+(?:to\s+be\s+)?(?:legitimate|safe|clean|benign|normal|unremarkable)\b",
    r"\bis\s+(?:a\s+)?(?:well[-\s]known|legitimate|verified|official|reputable)\b",
    r"\blow[-\s]risk\b",
    r"\bno\s+(?:known\s+)?(?:scam|phishing|fraud|malicious|suspicious)\b",
)

_UNSAFE_PATTERNS = (
    r"\b(?:is|was|has\s+been)\s+(?:flagged|blacklisted|reported|sanctioned)\b",
    r"\bknown\s+(?:scam|phishing|fraud|malicious|phishing\s+site)\b",
    r"\bconfirmed\s+(?:scam|phishing|fraud|malicious)\b",
    r"\bhigh(?:ly)?[-\s](?:risk|suspicious)\b",
    r"\bappears?\s+(?:to\s+be\s+)?(?:fraudulent|malicious|suspicious|a\s+scam)\b",
    r"\bassociated\s+with\b[^.]{0,60}?\b(?:theft|hack|exploit|scam|launder\w*|"
    r"stolen|ransom\w*)\b",
    r"\b(?:ofac|sanction(?:ed|s)|tornado\s+cash|lazarus)\b",
    r"\bstolen\s+funds\b",
    r"\bphishing\s+(?:site|page|domain|campaign)\b",
    r"\bdo\s+not\s+(?:send|interact|proceed)\b",
)

#: Words that flip the meaning of a following risk phrase. "no known scam"
#: must not read as "known scam".
_NEGATORS = (
    "no", "not", "never", "without", "free of", "absent", "n't", "none",
    "nothing", "neither", "nor", "lacks", "lacking",
)
_NEGATION_WINDOW = 45


def _is_negated(text: str, start: int) -> bool:
    """Whether a risk phrase at ``start`` sits inside a negation."""
    window = text[max(0, start - _NEGATION_WINDOW) : start]
    # Do not read across a sentence boundary — a new sentence resets polarity.
    window = re.split(r"[.;]", window)[-1]
    return any(re.search(rf"\b{re.escape(n)}\b", window) for n in _NEGATORS)


def _collect_prose(result: Any) -> str:
    parts = [result] if isinstance(result, str) else []
    for key, val in _walk(result):
        if key in _PROSE_KEYS and isinstance(val, str):
            parts.append(val)
    return "  ".join(parts).lower()


def extract_risk_from_prose(result: Any) -> float | None:
    """Read a risk judgement out of a natural-language answer.

    Returns None whenever the text is ambiguous or says nothing decisive —
    an unclear answer becomes `review`, never an allow.
    """
    text = _collect_prose(result)
    if len(text) < 12:
        return None

    safe_hits = sum(1 for p in _SAFE_PATTERNS if re.search(p, text))

    unsafe_hits = 0
    for pattern in _UNSAFE_PATTERNS:
        for m in re.finditer(pattern, text):
            if not _is_negated(text, m.start()):
                unsafe_hits += 1

    if unsafe_hits > safe_hits:
        return PROSE_UNSAFE_RISK
    if safe_hits > unsafe_hits:
        return PROSE_SAFE_RISK
    # Tie, including 0-0: the miner did not commit, so neither do we.
    return None


def extract_risk(result: Any) -> float | None:
    """Normalised 0 = safe … 1 = fraud, or None when nothing is interpretable.

    Precedence: explicit numeric risk > inverted safety score > boolean
    danger flag > categorical tier. Earlier (shallower) keys win.
    """
    pairs = list(_walk(result))

    for key, val in pairs:
        if key in _RISK_KEYS:
            f = _as_unit_float(val)
            if f is not None:
                return f

    for key, val in pairs:
        if key in _SAFE_KEYS:
            f = _as_unit_float(val)
            if f is not None:
                return 1.0 - f

    for key, val in pairs:
        if key in _BOOL_RISK_KEYS and isinstance(val, bool):
            return 0.9 if val else 0.1

    for key, val in pairs:
        if key in _TIER_KEYS:
            t = _tier_value(val)
            if t is not None:
                return t

    # A bare verdict string sitting at the top level.
    if isinstance(result, str):
        tier = _tier_value(result)
        if tier is not None:
            return tier

    # Last resort: the miner answered in prose. Weakest evidence, so it is
    # only consulted once every structured avenue is exhausted.
    return extract_risk_from_prose(result)


# --- Contextual heuristics (FR-8) -------------------------------------------

_ZERO_HISTORY_KEYS = ("tx_count", "transaction_count", "nonce", "total_txs", "num_txs")
_TX_STATUS_KEYS = ("status", "tx_status", "state")


def wallet_context_bump(result: Any) -> tuple[float, str | None]:
    """A zero-history address that just received funds is the classic
    drain destination — raise risk (PRD FR-8: +0.15)."""
    for key, val in _walk(result):
        if key in _ZERO_HISTORY_KEYS:
            n = val if isinstance(val, (int, float)) and not isinstance(val, bool) else None
            if n is not None and n == 0:
                return 0.15, "WALLET_BALANCE_CHECK: address has no transaction history"
    return 0.0, None


def tx_context_bump(result: Any) -> tuple[float, str | None]:
    """A reverted or still-pending transaction is weak ground to pay on
    (PRD FR-8: +0.2)."""
    for key, val in _walk(result):
        if key in _TX_STATUS_KEYS and isinstance(val, str):
            s = val.strip().lower()
            if s in ("reverted", "failed", "fail", "error"):
                return 0.2, "ONCHAIN_TX_LOOKUP: transaction reverted"
            if s in ("pending", "unconfirmed"):
                return 0.2, "ONCHAIN_TX_LOOKUP: transaction still pending"
            if s in ("not_found", "notfound"):
                return 0.2, "ONCHAIN_TX_LOOKUP: transaction not found on chain"
    return 0.0, None
