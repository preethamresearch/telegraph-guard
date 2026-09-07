"""Extraction must handle the shapes real miners actually return, and must
never silently read a safety score as a risk score."""

import pytest

from telegraph_guard.extract import (
    extract_confidence,
    extract_risk,
    tx_context_bump,
    wallet_context_bump,
)


def test_explicit_risk_score():
    assert extract_risk({"risk_score": 0.88}) == 0.88
    assert extract_risk({"fraud_score": 88}) == 0.88


def test_safety_polarity_is_inverted():
    # A trust score of 0.9 means SAFE, i.e. risk 0.1.
    assert extract_risk({"trust_score": 0.9}) == pytest.approx(0.1)
    assert extract_risk({"safety_score": 100}) == pytest.approx(0.0)


def test_risk_key_wins_over_safety_key():
    assert extract_risk({"risk_score": 0.9, "trust_score": 0.9}) == 0.9


def test_boolean_flags():
    assert extract_risk({"is_malicious": True}) == 0.9
    assert extract_risk({"is_malicious": False}) == 0.1


def test_tiers():
    assert extract_risk({"risk_tier": "HIGH"}) == 0.85
    assert extract_risk({"verdict": "clean"}) == 0.05
    assert extract_risk({"classification": "phishing"}) == 0.95
    assert extract_risk({"risk_level": "low risk"}) == 0.15


def test_unknown_tier_is_none_not_safe():
    # An "unknown" rating must not be read as safe.
    assert extract_risk({"risk_tier": "unknown"}) is None


def test_nested_result():
    assert extract_risk({"data": {"analysis": {"risk_score": 0.42}}}) == 0.42


def test_uninterpretable_returns_none():
    assert extract_risk({"balance": "12.4", "symbol": "ETH"}) is None
    assert extract_risk(None) is None
    assert extract_risk([]) is None


def test_percent_strings():
    assert extract_risk({"risk_score": "85%"}) == 0.85


def test_confidence():
    assert extract_confidence({"confidence": 0.91}) == 0.91
    assert extract_confidence({"summary": "hi"}) is None


def test_wallet_zero_history_bump():
    bump, reason = wallet_context_bump({"tx_count": 0})
    assert bump == 0.15 and reason
    assert wallet_context_bump({"tx_count": 57})[0] == 0.0


def test_tx_status_bump():
    assert tx_context_bump({"status": "reverted"})[0] == 0.2
    assert tx_context_bump({"status": "pending"})[0] == 0.2
    assert tx_context_bump({"status": "confirmed"})[0] == 0.0


# --- operational status is not a safety verdict -----------------------------
#
# Verbatim from the live TxLens /wallet-balance receipt (signal
# 0xca378ca8…): `status: "ok"` means the request succeeded, but the
# extractor read it as risk 0.05 and the UI showed a safety score for a
# plain balance lookup. Spotted by a user reading the receipt against the UI.

TXLENS_BALANCE = {
    "address": "0x7a250d5630b4cf539739df2c5dacb4c659f2488d",
    "answer": "0x7a25…488d holds 0.025 ETH on Ethereum.",
    "balance_native": 0.025,
    "balance_wei": "25000000000000000",
    "chain": "ethereum",
    "confidence": 1,
    "status": "ok",
    "summary": "0x7a25…488d holds 0.025 ETH on Ethereum.",
}


def test_status_ok_is_not_a_risk_verdict():
    assert extract_risk(TXLENS_BALANCE) is None
    # Confidence is still the miner's stated confidence in its answer.
    assert extract_confidence(TXLENS_BALANCE) == 1.0


def test_operational_words_on_status_keys_never_read_as_verdicts():
    for word in ("ok", "success", "complete", "none", "error", "partial"):
        assert extract_risk({"status": word}) is None, word
        assert extract_risk({"result": word}) is None, word


def test_genuine_verdicts_on_status_keys_still_read():
    assert extract_risk({"status": "malicious"}) == 0.95
    assert extract_risk({"status": "clean"}) == 0.05


def test_ok_inside_prose_is_not_a_verdict_either():
    assert extract_risk({"answer": "Everything looks ok to me."}) is None
