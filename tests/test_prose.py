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


# --- Real TxLens payloads, captured live from /assess-wallet ----------------
#
# The mixer case is the one that matters: TxLens reports probability 0 for a
# sanctioned Tornado Cash router, because its fraud model does not apply to a
# mixer. Reading that 0 as safe would allow a payment to an OFAC address.

TXLENS_TORNADO = {
    "status": "NOT_APPLICABLE",
    "assessment_status": "INCONCLUSIVE",
    "confidence": 0.95,
    "wallet": "0x722122dF12D4e14e13Ac3b6895a86e84145b6967",
    "answer": (
        "NOT_APPLICABLE: this address is not a standard funded wallet "
        "(burn/null or known mixer). Probability 0 (0% risk)."
    ),
}

TXLENS_BYBIT_HACKER = {
    "assessment_status": "LIMITED",
    "confidence": 0.7,
    "answer": (
        "HIGH risk: wallet sent funds directly back to its own funder "
        "(circular funding). Probability 0.9 (90% risk)."
    ),
}

TXLENS_UNISWAP = {
    "assessment_status": "LIMITED",
    "confidence": 0.35,
    "answer": (
        "INCONCLUSIVE: not enough evidence gathered to reach a confident "
        "verdict. Probability 0.1 (10% risk)."
    ),
}


def test_declined_assessment_does_not_read_probability_zero_as_safe():
    from telegraph_guard.extract import declined_to_assess

    assert declined_to_assess(TXLENS_TORNADO)
    risk = extract_risk(TXLENS_TORNADO)
    assert risk is not None and risk >= 0.7, "a known mixer must not be allowed"


def test_negation_does_not_swallow_a_parenthetical_assertion():
    """'is not a standard funded wallet (burn/null or known mixer)' —
    the 'not' negates the wallet type, not the mixer finding."""
    assert extract_risk_from_prose(TXLENS_TORNADO) == PROSE_UNSAFE_RISK


def test_stated_probability_is_read():
    assert extract_risk(TXLENS_BYBIT_HACKER) == pytest.approx(0.9)
    assert extract_risk(TXLENS_UNISWAP) == pytest.approx(0.1)


def test_real_payloads_separate_cleanly_across_the_thresholds():
    clean = extract_risk(TXLENS_UNISWAP)
    hacker = extract_risk(TXLENS_BYBIT_HACKER)
    mixer = extract_risk(TXLENS_TORNADO)
    assert clean < 0.3 <= 0.7 <= hacker
    assert mixer >= 0.7
