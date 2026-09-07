"""End-to-end tests of the orchestrator with a stubbed Engine.

core.py is the module that decides whether money moves, so it is exercised
against canned Engine responses rather than left to live testing. Uses a
real httpx client over a MockTransport, so URL construction, JSON encoding
and status handling are all genuinely exercised.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from telegraph_guard.core import Guard, build_query
from telegraph_guard.discovery import Registry, _parse_miner
from telegraph_guard.types import (
    INTENT_FRAUD,
    INTENT_TX,
    INTENT_URL,
    INTENT_WALLET,
    GuardConfig,
)

ADDR = "0x1f9090aae28b8a3dceadf281b0f12828e676c326"
URL = "https://evil-airdrop.example"
TX = "0x" + "ab" * 32

CHAINSIGHT = _parse_miner({
    "id": "302", "name": "ChainSight",
    "capabilities": ["FRAUD_DETECTION", "WALLET_BALANCE_CHECK"],
    "endpoints": [
        {"path": "/fraud", "method": "GET", "description": "Risk (FRAUD_DETECTION)."},
        {"path": "/balance", "method": "GET", "description": "Balance (WALLET_BALANCE_CHECK)."},
    ],
})
TXLENS = _parse_miner({
    "id": "9002", "name": "TxLens",
    "capabilities": ["FRAUD_DETECTION", "WALLET_BALANCE_CHECK"],
    "endpoints": [
        {"path": "/fraud-query", "method": "POST", "description": "FRAUD_DETECTION. Risk."},
        {"path": "/wallet-balance", "method": "GET", "description": "WALLET_BALANCE_CHECK."},
    ],
})

REGISTRY = Registry(
    by_intent={
        INTENT_FRAUD: [CHAINSIGHT, TXLENS],
        INTENT_WALLET: [CHAINSIGHT, TXLENS],
        INTENT_URL: [CHAINSIGHT],
        INTENT_TX: [CHAINSIGHT],
    },
    fetched_at=float("inf"),  # never stale, so no network discovery
)


def engine_reply(intent, miner_id, miner_name, result, hash_="0xfeed"):
    return {
        "miner_id": miner_id, "miner_name": miner_name, "intent": intent,
        "result": result, "cost_usd": 0.01, "duration_ms": 900,
        "signal_hash": hash_, "reasoning": f"routed to {miner_name}", "warnings": [],
    }


class FakeEngine:
    """Records every request and replies from a per-intent script."""

    def __init__(self, replies: dict, delay: dict | None = None):
        self.replies = replies
        self.delay = delay or {}
        self.requests: list[tuple[str, dict]] = []

    def client(self) -> httpx.AsyncClient:
        async def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content or b"{}")
            path = request.url.path
            self.requests.append((path, body))

            # Infer the intent from the auto-route query or the direct route.
            intent = self._intent_of(path, body)
            if intent in self.delay:
                await asyncio.sleep(self.delay[intent])

            reply = self.replies.get(intent)
            if reply is None:
                return httpx.Response(500, json={"error": f"no script for {intent}"})
            if isinstance(reply, int):
                return httpx.Response(reply, json={"error": "boom"})
            return httpx.Response(200, json=reply)

        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    @staticmethod
    def _intent_of(path: str, body: dict) -> str:
        if "/ask/" in path:
            ep = body.get("endpoint", "")
            if "fraud" in ep:
                return INTENT_FRAUD
            if "balance" in ep:
                return INTENT_WALLET
            if "url" in ep or "scan" in ep:
                return INTENT_URL
            return INTENT_TX
        q = (body.get("query") or "").lower()
        if "fraudulent" in q or "scam" in q or "phishing" in q:
            return INTENT_FRAUD
        if "balance" in q:
            return INTENT_WALLET
        if "safe to click" in q:
            return INTENT_URL
        return INTENT_TX


def guard_with(fake: FakeEngine, cfg: GuardConfig | None = None) -> Guard:
    return Guard(cfg or GuardConfig(), registry=REGISTRY, client=fake.client())


# --- happy paths ------------------------------------------------------------


async def test_clean_address_is_allowed():
    fake = FakeEngine({
        INTENT_FRAUD: engine_reply(INTENT_FRAUD, "9002", "TxLens",
                                   {"risk_score": 0.04, "confidence": 0.93}),
        INTENT_WALLET: engine_reply(INTENT_WALLET, "302", "ChainSight",
                                    {"balance": "812.4", "tx_count": 4211}),
    })
    g = guard_with(fake)
    v = await g.screen(ADDR)

    assert v.verdict == "allow"
    assert v.risk == pytest.approx(0.04)
    assert len(v.signals) == 2
    assert all(s.ok for s in v.signals)
    # Receipts must survive the whole pipeline.
    assert v.signals[0].verify_url.endswith("/engine/v1/signal/0xfeed")
    assert v.cost_usd == pytest.approx(0.02)


async def test_flagged_address_is_blocked():
    fake = FakeEngine({
        INTENT_FRAUD: engine_reply(INTENT_FRAUD, "9002", "TxLens",
                                   {"risk_score": 0.91, "confidence": 0.88}),
        INTENT_WALLET: engine_reply(INTENT_WALLET, "302", "ChainSight",
                                    {"balance": "0.0", "tx_count": 0}),
    })
    v = await guard_with(fake).screen(ADDR)

    assert v.verdict == "block"
    assert v.risk == 1.0  # 0.91 + 0.15 zero-history bump, clamped
    assert any("no transaction history" in r for r in v.reasons)


async def test_url_target_fans_out_to_url_scan():
    fake = FakeEngine({
        INTENT_URL: engine_reply(INTENT_URL, "302", "ChainSight",
                                 {"verdict": "phishing", "confidence": 0.97}),
        INTENT_FRAUD: engine_reply(INTENT_FRAUD, "9002", "TxLens",
                                   {"risk_score": 0.2, "confidence": 0.5}),
    })
    fake_g = guard_with(fake)
    v = await fake_g.screen(URL)

    assert v.target_type == "url"
    assert v.verdict == "block"
    # Max of URL_SCAN and FRAUD, not the mean.
    assert v.risk == pytest.approx(0.95)


async def test_tx_target_fans_out_to_tx_lookup():
    fake = FakeEngine({
        INTENT_TX: engine_reply(INTENT_TX, "302", "ChainSight", {"status": "reverted"}),
        INTENT_FRAUD: engine_reply(INTENT_FRAUD, "9002", "TxLens",
                                   {"risk_score": 0.55, "confidence": 0.9}),
    })
    v = await guard_with(fake).screen(TX)

    assert v.target_type == "tx"
    assert v.risk == pytest.approx(0.75)  # 0.55 + 0.2 reverted
    assert v.verdict == "block"


async def test_real_chainsight_prose_payload_scores_low_but_cannot_allow():
    """Regression: the shapes miner 302 actually returned on the live node.

    Prose extraction reads this as low risk (0.15), which is what lets a
    clean address avoid a needless `review`. But ChainSight states no
    confidence, and live calibration showed it returns this same text for
    an OFAC-sanctioned mixer as for a clean router — so it must not be able
    to authorise a payment on its own. Low risk, but still `review`.
    """
    fake = FakeEngine({
        INTENT_FRAUD: engine_reply(INTENT_FRAUD, "302", "ChainSight", {
            "address": ADDR,
            "answer": (
                "Based on publicly available blockchain analytics and "
                "fraud-intelligence sources, the address does not appear in any "
                "known scam, phishing, or fraud database, and no reports of "
                "malicious activity are associated with it."
            ),
        }),
        INTENT_WALLET: engine_reply(INTENT_WALLET, "302", "ChainSight", {
            "address": ADDR,
            "balance_eth": 812.4,
            "chain": "ethereum",
            "signal": "The Ethereum account holds 812.4 ETH.",
        }),
    })
    v = await guard_with(fake).screen(ADDR)

    assert v.risk == pytest.approx(0.15)
    assert v.verdict == "review"
    assert any("confidence" in r for r in v.reasons)


async def test_prose_fraud_report_blocks():
    fake = FakeEngine({
        INTENT_FRAUD: engine_reply(INTENT_FRAUD, "302", "ChainSight", {
            "answer": "This address is sanctioned and appears on the OFAC SDN list.",
        }),
        INTENT_WALLET: engine_reply(INTENT_WALLET, "302", "ChainSight",
                                    {"balance_eth": 0.0, "tx_count": 400}),
    })
    v = await guard_with(fake).screen(ADDR)
    assert v.verdict == "block"


# --- failure handling -------------------------------------------------------


async def test_unknown_target_makes_zero_http_calls():
    fake = FakeEngine({})
    v = await guard_with(fake).screen("not a real target")

    assert v.verdict == "review"
    assert fake.requests == []  # FR-2: no calls, no spend


async def test_one_intent_failing_still_produces_a_verdict():
    fake = FakeEngine({
        INTENT_FRAUD: engine_reply(INTENT_FRAUD, "9002", "TxLens",
                                   {"risk_score": 0.92, "confidence": 0.9}),
        INTENT_WALLET: 500,
    })
    v = await guard_with(fake, GuardConfig(min_signals=1)).screen(ADDR)

    assert v.verdict == "block"
    assert any(not s.ok for s in v.signals)


async def test_total_failure_fails_closed():
    fake = FakeEngine({INTENT_FRAUD: 500, INTENT_WALLET: 500})
    v = await guard_with(fake).screen(ADDR)

    assert v.verdict == "block"
    assert "insufficient_signals" in v.reasons[0]


async def test_402_reports_funding_not_a_bare_status():
    fake = FakeEngine({INTENT_FRAUD: 402, INTENT_WALLET: 402})
    v = await guard_with(fake).screen(ADDR)

    assert v.verdict == "block"
    joined = " ".join(v.reasons).lower()
    assert "usdc" in joined or "faucet" in joined


async def test_deadline_drops_slow_signals():
    fake = FakeEngine(
        {
            INTENT_FRAUD: engine_reply(INTENT_FRAUD, "9002", "TxLens",
                                       {"risk_score": 0.02, "confidence": 0.9}),
            INTENT_WALLET: engine_reply(INTENT_WALLET, "302", "ChainSight",
                                        {"tx_count": 900}),
        },
        delay={INTENT_WALLET: 2.0},
    )
    cfg = GuardConfig(deadline_ms=300, min_signals=1)
    v = await guard_with(fake, cfg).screen(ADDR)

    # The fast signal decides; the slow one is dropped, not awaited.
    assert v.verdict == "allow"
    assert v.elapsed_ms < 1500
    assert any("deadline" in (s.error or "") for s in v.signals)


async def test_deadline_miss_below_min_signals_is_not_allow():
    fake = FakeEngine(
        {
            INTENT_FRAUD: engine_reply(INTENT_FRAUD, "9002", "TxLens",
                                       {"risk_score": 0.01, "confidence": 0.99}),
            INTENT_WALLET: engine_reply(INTENT_WALLET, "302", "ChainSight",
                                        {"tx_count": 900}),
        },
        delay={INTENT_WALLET: 2.0},
    )
    v = await guard_with(fake, GuardConfig(deadline_ms=300, min_signals=2)).screen(ADDR)
    assert v.verdict == "review"


async def test_uninterpretable_results_do_not_allow():
    """Miners answered, nothing was a risk judgement — must not be an allow."""
    fake = FakeEngine({
        INTENT_FRAUD: engine_reply(INTENT_FRAUD, "9002", "TxLens", {"summary": "hello"}),
        INTENT_WALLET: engine_reply(INTENT_WALLET, "302", "ChainSight", {"balance": "1.0"}),
    })
    v = await guard_with(fake).screen(ADDR)
    assert v.verdict == "review"


# --- routing / transport ----------------------------------------------------


async def test_auto_route_is_the_default_path():
    fake = FakeEngine({
        INTENT_FRAUD: engine_reply(INTENT_FRAUD, "9002", "TxLens", {"risk_score": 0.1}),
        INTENT_WALLET: engine_reply(INTENT_WALLET, "302", "ChainSight", {"tx_count": 10}),
    })
    await guard_with(fake).screen(ADDR)

    assert all(p == "/engine/v1/ask" for p, _ in fake.requests)
    assert all("query" in b for _, b in fake.requests)


async def test_direct_miner_mode_targets_the_requested_miner():
    fake = FakeEngine({
        INTENT_FRAUD: engine_reply(INTENT_FRAUD, "9002", "TxLens", {"risk_score": 0.1}),
        INTENT_WALLET: engine_reply(INTENT_WALLET, "9002", "TxLens", {"tx_count": 10}),
    })
    cfg = GuardConfig(miners=["9002"])
    await guard_with(fake, cfg).screen(ADDR)

    assert fake.requests
    for path, body in fake.requests:
        assert path == "/engine/v1/ask/9002"
        assert "endpoint" in body and "method" in body


async def test_rate_limit_warning_retries_on_another_miner():
    """FR-12: a rate-limit warning on the auto path retries directly."""
    limited = engine_reply(INTENT_FRAUD, "9002", "TxLens", {"risk_score": 0.5})
    limited["warnings"] = ["rate limit exceeded for miner 9002"]

    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        calls.append(request.url.path)
        intent = FakeEngine._intent_of(request.url.path, body)
        if intent == INTENT_WALLET:
            return httpx.Response(200, json=engine_reply(
                INTENT_WALLET, "302", "ChainSight", {"tx_count": 50}))
        if request.url.path == "/engine/v1/ask":
            return httpx.Response(200, json=limited)
        return httpx.Response(200, json=engine_reply(
            INTENT_FRAUD, "302", "ChainSight", {"risk_score": 0.9, "confidence": 0.9}))

    g = Guard(GuardConfig(), registry=REGISTRY,
              client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    v = await g.screen(ADDR)

    assert any(p.startswith("/engine/v1/ask/") for p in calls), "expected a direct retry"
    fraud = [s for s in v.signals if s.intent == INTENT_FRAUD][0]
    assert fraud.miner_id == "302"  # retried away from the limited miner


# --- query construction -----------------------------------------------------


def test_queries_match_engine_intent_descriptions():
    """Phrasing is what keeps the auto-router on the intended intent."""
    assert "fraudulent" in build_query(INTENT_FRAUD, ADDR, "address", "ethereum")
    assert "balance" in build_query(INTENT_WALLET, ADDR, "address", "ethereum")
    assert "safe to click" in build_query(INTENT_URL, URL, "url", "ethereum")
    assert "status and gas used" in build_query(INTENT_TX, TX, "tx", "ethereum")
    # The chain must reach the miner, not be silently dropped.
    assert "base" in build_query(INTENT_WALLET, ADDR, "address", "base")


def test_url_fraud_query_does_not_ask_about_an_address():
    q = build_query(INTENT_FRAUD, URL, "url", "ethereum")
    assert "address" not in q.lower()


# --- redundancy on risk-bearing intents -------------------------------------
#
# Live, TxLens intermittently failed over and the replacement returned nothing
# usable, so roughly one run in four lost the fraud verdict entirely. Querying
# a second miner concurrently removes that class of flake.


async def test_second_miner_covers_a_failing_first():
    """The preferred fraud miner dies; the redundant one still decides."""
    calls: list[str] = []

    async def handler(request):
        body = json.loads(request.content or b"{}")
        calls.append(request.url.path)
        intent = FakeEngine._intent_of(request.url.path, body)
        if intent == INTENT_WALLET:
            return httpx.Response(200, json=engine_reply(
                INTENT_WALLET, "302", "ChainSight", {"tx_count": 500}))
        # miner 302 (slot 0) is down; 9002 (slot 1) answers.
        if request.url.path.endswith("/302"):
            return httpx.Response(503, json={"error": "upstream down"})
        return httpx.Response(200, json=engine_reply(
            INTENT_FRAUD, "9002", "TxLens", {"risk_score": 0.93, "confidence": 0.9}))

    g = Guard(
        GuardConfig(miners=["302", "9002"], miners_per_intent=2, min_signals=1),
        registry=REGISTRY,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    v = await g.screen(ADDR)

    assert v.verdict == "block"
    assert any(s.ok and s.risk == pytest.approx(0.93) for s in v.signals)


async def test_redundancy_only_applies_to_risk_bearing_intents():
    """Wallet/tx inform a verdict, they never carry one — no extra spend."""
    fake = FakeEngine({
        INTENT_FRAUD: engine_reply(INTENT_FRAUD, "9002", "TxLens",
                                   {"risk_score": 0.1, "confidence": 0.8}),
        INTENT_WALLET: engine_reply(INTENT_WALLET, "302", "ChainSight",
                                    {"tx_count": 900}),
    })
    cfg = GuardConfig(miners=["9002", "302"], miners_per_intent=2, min_signals=1)
    await guard_with(fake, cfg).screen(ADDR)

    wallet_calls = [
        b for _, b in fake.requests
        if FakeEngine._intent_of("/engine/v1/ask/x", b) == INTENT_WALLET
    ]
    assert len(wallet_calls) == 1, "wallet intent must not be duplicated"
    assert len(fake.requests) == 3, "2 fraud + 1 wallet"


def test_miners_per_intent_defaults_to_one():
    """Redundancy costs an extra call, so it is opt-in."""
    assert GuardConfig().miners_per_intent == 1
    with pytest.raises(ValueError):
        GuardConfig(miners_per_intent=0)


async def test_direct_payload_query_matches_the_intent():
    """Receipts are public: a balance call must not carry the fraud question.
    Observed in live signal 0xca378ca8… and spotted by a user auditing it."""
    fake = FakeEngine({
        INTENT_FRAUD: engine_reply(INTENT_FRAUD, "9002", "TxLens",
                                   {"risk_score": 0.1, "confidence": 0.8}),
        INTENT_WALLET: engine_reply(INTENT_WALLET, "9002", "TxLens",
                                    {"balance_native": 1.0, "status": "ok"}),
    })
    cfg = GuardConfig(miners=["9002"], min_signals=1)
    await guard_with(fake, cfg).screen(ADDR)

    for path, body in fake.requests:
        q = (body.get("payload") or {}).get("query", "")
        if "balance" in body.get("endpoint", ""):
            assert "balance" in q and "fraudulent" not in q
        elif "fraud" in body.get("endpoint", ""):
            assert "fraudulent" in q
