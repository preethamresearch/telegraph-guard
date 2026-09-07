from telegraph_guard.classify import classify, intents_for, normalize
from telegraph_guard.types import INTENT_FRAUD, INTENT_TX, INTENT_URL, INTENT_WALLET

ADDR = "0x1f9090aaE28b8a3dCeaDf281B0F12828e676c326"
TX = "0x" + "ab" * 32


def test_address():
    assert classify(ADDR) == "address"
    assert classify(ADDR.lower()) == "address"


def test_tx_hash():
    assert classify(TX) == "tx"


def test_ens():
    assert classify("vitalik.eth") == "ens"
    assert classify("jesse.base.eth") == "ens"


def test_urls():
    assert classify("https://example.com") == "url"
    assert classify("http://evil-airdrop.xyz/claim") == "url"
    assert classify("evil-airdrop.xyz") == "url"
    assert classify("site.com/path") == "url"


def test_unknown():
    for bad in ["", "   ", "hello world", "0x1234", "not a target", None, 42]:
        assert classify(bad) == "unknown"


def test_address_vs_tx_length_boundary():
    # 41 hex chars is neither a valid address nor a tx hash.
    assert classify("0x" + "a" * 41) == "unknown"


def test_ftp_scheme_is_not_a_url_target():
    assert classify("ftp://files.example.com") == "unknown"


def test_fanout_matches_prd():
    assert set(intents_for("address")) == {INTENT_FRAUD, INTENT_WALLET}
    assert set(intents_for("ens")) == {INTENT_FRAUD, INTENT_WALLET}
    assert set(intents_for("tx")) == {INTENT_TX, INTENT_FRAUD}
    assert set(intents_for("url")) == {INTENT_URL, INTENT_FRAUD}
    assert intents_for("unknown") == []


def test_normalize():
    assert normalize(ADDR, "address") == ADDR.lower()
    assert normalize("  VITALIK.eth ", "ens") == "vitalik.eth"
    assert normalize("evil.xyz", "url") == "https://evil.xyz"
    assert normalize("https://evil.xyz", "url") == "https://evil.xyz"
