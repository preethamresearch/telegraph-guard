"""The demo's pass/fail rule.

A verdict that matches for the wrong reason is not a passing demo. With an
unfunded wallet every target blocks identically, and two of the three
invoices ("expect block") match by accident — which would read as 2/3
passing in a recorded video. These tests pin the rule that prevents that.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

from demo_agent import (  # noqa: E402
    FAIL,
    INCONCLUSIVE,
    PASS,
    classify_outcome,
    has_evidence,
    report,
)

from telegraph_guard.types import GuardVerdict, Signal  # noqa: E402


def verdict(kind, signals):
    return GuardVerdict(
        target="0xabc", target_type="address", verdict=kind,
        risk=0.9 if kind == "block" else 0.05, confidence=0.9, signals=signals,
    )


def real_signal(hash_="0xfeed"):
    return Signal(intent="FRAUD_DETECTION", miner_id="302", miner_name="ChainSight",
                  risk=0.9, signal_hash=hash_)


def failed_signal(error="payment rejected at settlement"):
    return Signal(intent="FRAUD_DETECTION", error=error)


# --- evidence ---------------------------------------------------------------


def test_errored_signals_are_not_evidence():
    assert not has_evidence(verdict("block", [failed_signal(), failed_signal()]))


def test_no_signals_at_all_is_not_evidence():
    assert not has_evidence(verdict("review", []))


def test_a_signal_without_a_hash_is_not_evidence():
    """Unverifiable output cannot back a demo claim."""
    unverifiable = Signal(intent="FRAUD_DETECTION", miner_id="302", risk=0.9)
    assert not has_evidence(verdict("block", [unverifiable]))


def test_one_real_signal_is_evidence():
    assert has_evidence(verdict("block", [real_signal(), failed_signal()]))


# --- the accidental-match case that motivated this --------------------------


def test_unfunded_block_does_not_pass_even_when_block_was_expected():
    v = verdict("block", [failed_signal(), failed_signal()])
    assert classify_outcome(v, "block") == INCONCLUSIVE
    assert classify_outcome(v, "block") != PASS


def test_matching_verdict_on_real_signals_passes():
    assert classify_outcome(verdict("block", [real_signal()]), "block") == PASS


def test_mismatch_on_real_signals_fails():
    assert classify_outcome(verdict("allow", [real_signal()]), "block") == FAIL


# --- the reported result ----------------------------------------------------


def _results(outcomes):
    out = []
    for i, (kind, expect, sigs) in enumerate(outcomes):
        v = verdict(kind, sigs)
        out.append((f"invoice {i}", expect, v, classify_outcome(v, expect)))
    return out


def test_all_inconclusive_exits_nonzero_and_says_so(capsys):
    """The exact shape of an unfunded run: 3 blocks, 2 'expected'."""
    code = report(_results([
        ("block", "allow", [failed_signal(), failed_signal()]),
        ("block", "block", [failed_signal(), failed_signal()]),
        ("block", "block", [failed_signal(), failed_signal()]),
    ]))
    out = capsys.readouterr().out

    assert code == 2
    assert "PROVED NOTHING" in out
    # It must never report the two accidental matches as passes.
    assert "2 of 3 passed" not in out
    assert PASS not in out.replace("PROVED NOTHING", "")


def test_partial_evidence_still_exits_nonzero(capsys):
    code = report(_results([
        ("allow", "allow", [real_signal()]),
        ("block", "block", [failed_signal()]),
    ]))
    assert code == 2
    assert "inconclusive" in capsys.readouterr().out


def test_a_genuine_mismatch_exits_one(capsys):
    code = report(_results([
        ("allow", "block", [real_signal()]),
        ("block", "block", [real_signal()]),
    ]))
    assert code == 1
    assert "did not match" in capsys.readouterr().out


def test_a_fully_real_run_exits_zero(capsys):
    code = report(_results([
        ("allow", "allow", [real_signal()]),
        ("block", "block", [real_signal()]),
        ("block", "block", [real_signal()]),
    ]))
    out = capsys.readouterr().out
    assert code == 0
    assert "3 of 3 passed on real miner evidence" in out


# --- replay must never look like a live pass --------------------------------


def test_replay_never_claims_miner_evidence(capsys):
    """Replay drives the same pipeline, so every case legitimately has
    signals — but the payloads are stored, and the summary must say so."""
    code = report(_results([
        ("allow", "allow", [real_signal()]),
        ("block", "block", [real_signal()]),
        ("block", "block", [real_signal()]),
    ]), replay=True)
    out = capsys.readouterr().out

    assert "passed on real miner evidence" not in out
    assert "STORED PAYLOADS" in out
    # A replay must be distinguishable from a live pass by exit code alone,
    # or CI and recording scripts cannot tell them apart.
    assert code == 3
    assert code != 0


def test_replay_still_reports_a_genuine_mismatch(capsys):
    """A pipeline regression must surface even in replay."""
    code = report(_results([
        ("allow", "block", [real_signal()]),
        ("block", "block", [real_signal()]),
    ]), replay=True)
    assert code == 1
    assert "did not match" in capsys.readouterr().out
