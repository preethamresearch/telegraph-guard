"""Recorded Engine responses for replay mode.

REPLAY IS NOT A DEMO OF THE PRODUCT. It exercises the real pipeline —
classification, extraction, aggregation, gating, routing — against stored
payloads instead of live miners. It produces no signal hashes and proves
nothing about miner quality. NFR-3 forbids mocked verdicts in anything
submitted; this exists so the pipeline can be inspected without a funded
wallet.

Each fixture states its provenance honestly:

    captured    — observed verbatim from the live Engine
    constructed — written by hand in the shape the miner documents,
                  because that path has not yet been observed live
"""

from __future__ import annotations

CAPTURED = "captured"
CONSTRUCTED = "constructed"


def reply(miner_id, miner_name, intent, result, source, hash_, ms=1200):
    return {
        "miner_id": miner_id,
        "miner_name": miner_name,
        "intent": intent,
        "result": result,
        "cost_usd": 0.01,
        "duration_ms": ms,
        "signal_hash": hash_,
        "reasoning": f"Query routed to {miner_name}.",
        "warnings": [],
        "_source": source,
    }


# --- Invoice 1: a well-known contract, expected to screen clean -------------
#
# The FRAUD_DETECTION payload here is the real shape ChainSight returned on
# the live node — prose, no numeric score. It is what motivated the prose
# extractor.

CLEAN_ADDRESS = {
    "FRAUD_DETECTION": reply(
        "302", "ChainSight", "FRAUD_DETECTION",
        {
            "address": "0x7a250d5630b4cf539739df2c5dacb4c659f2488d",
            "answer": (
                "Based on publicly available blockchain analytics and "
                "fraud-intelligence sources, the address "
                "0x7a250d5630b4cf539739df2c5dacb4c659f2488d on the Ethereum "
                "network does not appear in any known scam, phishing, or fraud "
                "database, and no reports of malicious activity are associated "
                "with it. It is a widely used, well-known router contract."
            ),
        },
        CAPTURED, "0x9f2c41a7e8b3d5f60c1a", 1180,
    ),
    "WALLET_BALANCE_CHECK": reply(
        "302", "ChainSight", "WALLET_BALANCE_CHECK",
        {
            "address": "0x7a250d5630b4cf539739df2c5dacb4c659f2488d",
            "balance_eth": 0.412,
            "chain": "ethereum",
            "tx_count": 8842301,
            "signal": "The Ethereum account holds 0.412 ETH across 8,842,301 txs.",
        },
        CAPTURED, "0x3b81e0d94c7a2f16be55", 840,
    ),
}

# --- Invoice 2: a sanctioned mixer, expected to be blocked ------------------

SANCTIONED_ADDRESS = {
    "FRAUD_DETECTION": reply(
        "9002", "TxLens", "FRAUD_DETECTION",
        {
            "address": "0x722122df12d4e14e13ac3b6895a86e84145b6967",
            "risk_score": 0.94,
            "confidence": 0.91,
            "summary": (
                "Address is sanctioned and appears on the OFAC SDN list as a "
                "Tornado Cash router. Associated with laundering of stolen funds."
            ),
        },
        CONSTRUCTED, "0xc4e7a120b8d3f95e1a70", 1640,
    ),
    "WALLET_BALANCE_CHECK": reply(
        "302", "ChainSight", "WALLET_BALANCE_CHECK",
        {
            "address": "0x722122df12d4e14e13ac3b6895a86e84145b6967",
            "balance_eth": 3512.9,
            "chain": "ethereum",
            "tx_count": 194883,
        },
        CONSTRUCTED, "0x77aa20e5cb91d4038e6c", 910,
    ),
}

# --- Invoice 3: a phishing URL, expected to be blocked ----------------------

PHISHING_URL = {
    "URL_SCAN": reply(
        "20260828", "PREFLIGHT Infrastructure Signals", "URL_SCAN",
        {
            "url": "http://testsafebrowsing.appspot.com/s/phishing.html",
            "risk_score": 0.97,
            "confidence": 0.95,
            "verdict": "phishing",
            "redirects": 0,
            "security_headers": {"strict_transport_security": False},
            "summary": "Confirmed phishing page. Served over plaintext HTTP.",
        },
        CONSTRUCTED, "0x1de8b3f70a25c9614477", 1520,
    ),
    "FRAUD_DETECTION": reply(
        "9002", "TxLens", "FRAUD_DETECTION",
        {
            "risk_score": 0.88,
            "confidence": 0.84,
            "summary": "Domain is a known phishing site. Do not interact.",
        },
        CONSTRUCTED, "0x50c9d1ba7e3f28460aa1", 1310,
    ),
}


#: target substring -> recorded intent map
SCENARIOS = [
    ("0x7a250d5630b4cf539739df2c5dacb4c659f2488d", CLEAN_ADDRESS),
    ("0x722122df12d4e14e13ac3b6895a86e84145b6967", SANCTIONED_ADDRESS),
    ("testsafebrowsing.appspot.com", PHISHING_URL),
]


def lookup(target: str, intent: str) -> dict | None:
    t = target.lower()
    for key, scenario in SCENARIOS:
        if key in t:
            return scenario.get(intent)
    return None


def provenance() -> dict[str, int]:
    counts = {CAPTURED: 0, CONSTRUCTED: 0}
    for _, scenario in SCENARIOS:
        for r in scenario.values():
            counts[r["_source"]] += 1
    return counts
