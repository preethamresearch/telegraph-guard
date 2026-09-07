"""Prose extraction (the fallback for miners that answer in sentences).

The load-bearing case is negation: a fraud report and a clean bill of
health use the same vocabulary, separated only by a "no" or a "not".
Reading one as the other is the worst failure this library can have, in
either direction, so both are tested explicitly.
"""

import pytest

from telegraph_guard.extract import (
    PROSE_SAFE_RISK,
    PROSE_UNSAFE_RISK,
    extract_risk,
    extract_risk_from_prose,
)

#: Verbatim from ChainSight (miner 302) on FRAUD_DETECTION, observed live.
REAL_CHAINSIGHT_CLEAN = {
    "address": "0xabababababababababababababababababababab",
    "answer": (
        "Based on publicly available blockchain analytics and fraud-intelligence "
        "sources, the address 0xabababababababababababababababababababab on the "
        "Ethereum network does not appear in any known scam, phishing, or fraud "
        "database, and no reports of malicious activity are associated with it."
    ),
}


def test_the_real_observed_clean_answer_reads_as_safe():
    assert extract_risk_from_prose(REAL_CHAINSIGHT_CLEAN) == PROSE_SAFE_RISK


def test_the_real_observed_answer_flows_through_extract_risk():
    """This is the case that otherwise degrades a clean address to review."""
    assert extract_risk(REAL_CHAINSIGHT_CLEAN) == PROSE_SAFE_RISK


def test_safe_prose_clears_the_allow_threshold():
    # Default allow_below is 0.3 — a clean prose answer must be allowable.
    assert PROSE_SAFE_RISK < 0.3


def test_unsafe_prose_clears_the_block_threshold():
    assert PROSE_UNSAFE_RISK >= 0.7


# --- negation, the failure mode that matters --------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "The address does not appear in any known scam database.",
        "There is no evidence of fraud associated with this wallet.",
        "This address has not been flagged or blacklisted by any provider.",
        "No known phishing or malicious activity was found.",
        "The contract appears to be legitimate and is widely used.",
        "This is a well-known exchange deposit address.",
    ],
)
def test_negated_risk_words_read_as_safe(text):
    assert extract_risk_from_prose({"answer": text}) == PROSE_SAFE_RISK


@pytest.mark.parametrize(
    "text",
    [
        "This address has been flagged as a known scam.",
        "The wallet is sanctioned and appears on the OFAC SDN list.",
        "Confirmed phishing site impersonating a wallet provider.",
        "This address is associated with the theft of user funds.",
        "The domain is a known phishing site. Do not interact.",
        "Highly suspicious: the address appears to be fraudulent.",
    ],
)
def test_affirmative_risk_reads_as_unsafe(text):
    assert extract_risk_from_prose({"answer": text}) == PROSE_UNSAFE_RISK


def test_negation_does_not_leak_across_a_sentence_boundary():
    """A clean first sentence must not neutralise a warning in the next."""
    text = (
        "There is no balance held at this address. "
        "The address has been flagged as a known scam."
    )
    assert extract_risk_from_prose({"answer": text}) == PROSE_UNSAFE_RISK


def test_mixed_signals_return_none_not_a_guess():
    text = (
        "The address does not appear in our database. "
        "However, it is associated with the theft of user funds."
    )
    # One safe hit, one unsafe hit — the miner did not commit, so neither do we.
    assert extract_risk_from_prose({"answer": text}) is None


# --- must not overreach -----------------------------------------------------


def test_neutral_prose_returns_none():
    for text in [
        "The Ethereum account holds 0 ETH.",
        "Transaction confirmed in block 25924903 using 21000 gas.",
        "This is a smart contract deployed in 2021.",
    ]:
        assert extract_risk_from_prose({"answer": text}) is None


def test_short_or_absent_text_returns_none():
    assert extract_risk_from_prose({"answer": "ok"}) is None
    assert extract_risk_from_prose({}) is None
    assert extract_risk_from_prose(None) is None
    assert extract_risk_from_prose({"balance": 12}) is None


def test_numeric_score_always_outranks_prose():
    """Prose is the weakest evidence and must never override a number."""
    result = {
        "risk_score": 0.95,
        "answer": "The address does not appear in any known scam database.",
    }
    assert extract_risk(result) == 0.95

    result = {
        "trust_score": 0.95,
        "answer": "This address has been flagged as a known scam.",
    }
    assert extract_risk(result) == pytest.approx(0.05)


def test_tier_outranks_prose():
    result = {
        "risk_tier": "high",
        "answer": "The address does not appear in any known scam database.",
    }
    assert extract_risk(result) == 0.85


def test_reads_prose_from_any_of_the_known_text_fields():
    text = "This address has been flagged as a known scam."
    for key in ("answer", "summary", "signal", "explanation", "analysis"):
        assert extract_risk_from_prose({key: text}) == PROSE_UNSAFE_RISK


def test_reads_nested_prose():
    assert extract_risk_from_prose(
        {"data": {"result": {"answer": "The domain is a known phishing site."}}}
    ) == PROSE_UNSAFE_RISK
