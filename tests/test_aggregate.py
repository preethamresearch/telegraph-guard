"""Gate behaviour: NFR-5 safe defaults, NFR-9 determinism, NFR-2 fault tolerance."""

import pytest

from telegraph_guard.aggregate import aggregate
from telegraph_guard.types import (
    INTENT_FRAUD,
    INTENT_TX,
    INTENT_URL,
    INTENT_WALLET,
    GuardConfig,
    Signal,
)

ADDR = "0xabc"


def sig(intent, risk=None, conf=None, error=None, raw=None, hash_="0xdead"):
    return Signal(
        intent=intent,
        miner_id="9002",
        miner_name="TxLens",
        risk=risk,
        confidence=conf,
        signal_hash=hash_,
        error=error,
        raw=raw,
    )


def agg(signals, config=None, ttype="address"):
    return aggregate(ADDR, ttype, signals, config or GuardConfig())


def test_allow_on_low_risk():
    v = agg([sig(INTENT_FRAUD, 0.05, 0.9), sig(INTENT_WALLET, raw={"tx_count": 900})])
    assert v.verdict == "allow"
    assert v.risk < 0.3


def test_block_on_high_risk():
    v = agg([sig(INTENT_FRAUD, 0.88, 0.91), sig(INTENT_WALLET, raw={"tx_count": 5})])
    assert v.verdict == "block"


def test_review_in_the_middle():
    v = agg([sig(INTENT_FRAUD, 0.5, 0.8), sig(INTENT_WALLET, raw={"tx_count": 5})])
    assert v.verdict == "review"


def test_zero_history_pushes_allow_to_review():
    """A 0.2-risk address with no history must not be waved through."""
    clean = agg([sig(INTENT_FRAUD, 0.2, 0.9), sig(INTENT_WALLET, raw={"tx_count": 100})])
    fresh = agg([sig(INTENT_FRAUD, 0.2, 0.9), sig(INTENT_WALLET, raw={"tx_count": 0})])
    assert clean.verdict == "allow"
    assert fresh.verdict == "review"
    assert fresh.risk == pytest.approx(0.35)


def test_reverted_tx_bump():
    v = aggregate(
        ADDR,
        "tx",
        [sig(INTENT_FRAUD, 0.55, 0.9), sig(INTENT_TX, raw={"status": "reverted"})],
        GuardConfig(),
    )
    assert v.risk == pytest.approx(0.75)
    assert v.verdict == "block"


def test_url_and_fraud_take_the_max():
    v = aggregate(
        ADDR,
        "url",
        [sig(INTENT_URL, 0.9, 1.0), sig(INTENT_FRAUD, 0.1, 1.0)],
        GuardConfig(),
    )
    assert v.risk == pytest.approx(0.9)
    assert v.verdict == "block"


def test_confidence_weighting():
    """A high-confidence safe call outweighs a low-confidence alarm."""
    v = aggregate(
        ADDR,
        "address",
        [sig(INTENT_FRAUD, 0.9, 0.1), sig(INTENT_FRAUD, 0.1, 0.9)],
        GuardConfig(min_signals=1),
    )
    assert v.risk == pytest.approx(0.18)


def test_missing_confidence_weighted_half():
    v = aggregate(
        ADDR, "address", [sig(INTENT_FRAUD, 0.8, None)], GuardConfig(min_signals=1)
    )
    assert v.risk == pytest.approx(0.8)


# --- fault tolerance (NFR-2) ------------------------------------------------


def test_one_miner_down_still_produces_a_verdict():
    v = agg(
        [sig(INTENT_FRAUD, 0.9, 0.9), sig(INTENT_WALLET, error="ReadTimeout")],
        GuardConfig(min_signals=1),
    )
    assert v.verdict == "block"


def test_all_down_fails_closed():
    v = agg([sig(INTENT_FRAUD, error="boom"), sig(INTENT_WALLET, error="boom")])
    assert v.verdict == "block"
    assert "insufficient_signals" in v.reasons[0]


def test_all_down_fails_open_when_configured():
    v = agg(
        [sig(INTENT_FRAUD, error="boom"), sig(INTENT_WALLET, error="boom")],
        GuardConfig(fail_closed=False),
    )
    assert v.verdict == "review"


def test_insufficient_signals_is_review_not_allow():
    v = agg([sig(INTENT_FRAUD, 0.01, 0.99)], GuardConfig(min_signals=2))
    assert v.verdict == "review"


def test_unknown_target_makes_no_calls():
    v = aggregate("garbage", "unknown", [], GuardConfig())
    assert v.verdict == "review"
    assert v.signals == []


def test_uninterpretable_miners_do_not_allow():
    """Miners answered, but nothing was a risk judgement — must not allow."""
    v = agg([sig(INTENT_FRAUD, None, None), sig(INTENT_WALLET, raw={"balance": "1.0"})])
    assert v.verdict == "review"


# --- determinism (NFR-9) ----------------------------------------------------


def test_deterministic():
    signals = [sig(INTENT_FRAUD, 0.61, 0.7), sig(INTENT_WALLET, raw={"tx_count": 0})]
    a = agg(list(signals))
    b = agg(list(signals))
    assert a.to_dict() == b.to_dict()


def test_risk_is_clamped():
    v = aggregate(
        ADDR,
        "tx",
        [sig(INTENT_FRAUD, 0.99, 1.0), sig(INTENT_TX, raw={"status": "reverted"})],
        GuardConfig(),
    )
    assert v.risk == 1.0


def test_receipt_carries_verify_urls():
    v = agg([sig(INTENT_FRAUD, 0.9, 0.9), sig(INTENT_WALLET, raw={"tx_count": 1})])
    d = v.to_dict()
    assert d["signals"][0]["verify_url"].endswith("/engine/v1/signal/0xdead")
    assert d["guard_version"]


def test_config_validation():
    with pytest.raises(ValueError):
        GuardConfig(allow_below=0.9, block_above=0.2)
    with pytest.raises(ValueError):
        GuardConfig(min_signals=0)
