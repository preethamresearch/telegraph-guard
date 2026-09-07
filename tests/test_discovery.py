"""Endpoint resolution across the three description conventions real
miners use. Fixtures are trimmed copies of live /api/miners records."""

from telegraph_guard.discovery import Miner, Registry, _parse_miner

CHAINSIGHT = _parse_miner(
    {
        "id": "302",
        "name": "ChainSight",
        "capabilities": ["FRAUD_DETECTION", "URL_SCAN", "WALLET_BALANCE_CHECK"],
        "endpoints": [
            {"path": "/balance", "method": "GET",
             "description": "Native ETH balance of a wallet address (WALLET_BALANCE_CHECK)."},
            {"path": "/tx", "method": "GET",
             "description": "Details of an on-chain transaction by hash (ONCHAIN_TX_LOOKUP)."},
            {"path": "/fraud", "method": "GET",
             "description": "Malicious-activity risk assessment of an address (FRAUD_DETECTION)."},
            {"path": "/urlscan", "method": "GET",
             "description": "Phishing/scam assessment of a URL (URL_SCAN)."},
        ],
    }
)

DEGENLENS = _parse_miner(
    {
        "id": "10002",
        "name": "DegenLens",
        "capabilities": ["FRAUD_DETECTION", "ONCHAIN_TX_LOOKUP"],
        "endpoints": [
            {"path": "/transaction/lookup", "method": "GET",
             "description": "ONCHAIN_TX_LOOKUP. Look up one specific EVM transaction."},
            {"path": "/anomaly/check", "method": "GET",
             "description": "FRAUD_DETECTION. Five screens over an address."},
            {"path": "/health", "method": "GET", "description": "Liveness."},
        ],
    }
)

# Names no intent anywhere — only the route identifies it.
PREFLIGHT = _parse_miner(
    {
        "id": "20260828",
        "name": "PREFLIGHT",
        "capabilities": ["URL_SCAN", "WALLET_BALANCE_CHECK", "ONCHAIN_TX_LOOKUP"],
        "endpoints": [
            {"path": "/ssl-check", "method": "GET", "description": "Live TLS verification."},
            {"path": "/url-scan", "method": "GET", "description": "Safety scan of a URL."},
            {"path": "/wallet-balance", "method": "GET", "description": "Native token balance."},
            {"path": "/tx-lookup", "method": "GET", "description": "Status of a transaction hash."},
        ],
    }
)

# Single-purpose miner with one unnamed route.
SENTINEL = _parse_miner(
    {
        "id": "5001",
        "name": "URL Sentinel",
        "capabilities": ["URL_SCAN"],
        "endpoints": [
            {"path": "/scan", "method": "POST",
             "description": "Return a safe/suspicious/malicious verdict."},
        ],
    }
)


def test_parenthesised_intent_convention():
    assert CHAINSIGHT.endpoint_for("FRAUD_DETECTION")["path"] == "/fraud"
    assert CHAINSIGHT.endpoint_for("URL_SCAN")["path"] == "/urlscan"
    assert CHAINSIGHT.endpoint_for("WALLET_BALANCE_CHECK")["path"] == "/balance"
    assert CHAINSIGHT.endpoint_for("ONCHAIN_TX_LOOKUP")["path"] == "/tx"


def test_leading_intent_convention():
    assert DEGENLENS.endpoint_for("FRAUD_DETECTION")["path"] == "/anomaly/check"
    assert DEGENLENS.endpoint_for("ONCHAIN_TX_LOOKUP")["path"] == "/transaction/lookup"


def test_path_fallback_when_no_intent_named():
    assert PREFLIGHT.endpoint_for("URL_SCAN")["path"] == "/url-scan"
    assert PREFLIGHT.endpoint_for("WALLET_BALANCE_CHECK")["path"] == "/wallet-balance"
    # Must prefer /tx-lookup over the similarly-named /ssl-check etc.
    assert PREFLIGHT.endpoint_for("ONCHAIN_TX_LOOKUP")["path"] == "/tx-lookup"


def test_single_purpose_miner_single_route():
    assert SENTINEL.endpoint_for("URL_SCAN")["path"] == "/scan"


def test_no_match_returns_none():
    m = Miner(id="221", name="EmailRep", capabilities=["FRAUD_DETECTION"],
              endpoints=[{"path": "/{email}", "description": "Email reputation."}])
    # An email-reputation route is not an address fraud endpoint.
    assert m.endpoint_for("WALLET_BALANCE_CHECK") is None


def test_health_route_does_not_count_as_the_only_route():
    m = Miner(id="1", name="X", capabilities=["URL_SCAN"],
              endpoints=[{"path": "/health", "description": "Liveness."}])
    assert m.endpoint_for("URL_SCAN") is None


def test_registry_lookup():
    reg = Registry(by_intent={"FRAUD_DETECTION": [CHAINSIGHT, DEGENLENS]})
    assert reg.miner("302").name == "ChainSight"
    assert reg.miner("9999") is None
    assert len(reg.miners_for("FRAUD_DETECTION")) == 2
    assert reg.miners_for("URL_SCAN") == []


def test_fresh_registry_is_stale():
    # fetched_at defaults to 0, so an unpopulated registry always refreshes.
    assert Registry().stale
