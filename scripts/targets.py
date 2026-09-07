"""Curated screening corpus for the soak run (FR-40).

Every entry is a real, publicly-documented target — no synthetic volume
(NFR-11). The list deliberately spans the full risk range so the soak
also doubles as calibration evidence for the aggregation weights, and
covers all four target intents.

Malicious entries are drawn from public attribution: the OFAC SDN list,
publicly attributed exploit addresses, and Google's official Safe
Browsing *test* endpoints (which exist precisely so security tools can be
exercised without touching live phishing infrastructure).
"""

# --- Addresses expected to screen clean -------------------------------------
# Well-known contracts and exchange wallets with deep history.
SAFE_ADDRESSES = [
    "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",  # vitalik.eth
    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC token contract
    "0xdAC17F958D2ee523a2206206994597C13D831ec7",  # USDT token contract
    "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",  # Uniswap V2 router
    "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",  # Uniswap V3 router 2
    "0x28C6c06298d514Db089934071355E5743bf21d60",  # Binance hot wallet 14
    "0x21a31Ee1afC51d94C2eFcCAa2092aD1028285549",  # Binance hot wallet 15
    "0x1f9090aaE28b8a3dCeaDf281B0F12828e676c326",  # beaverbuild block builder
    "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
    "0x3f5CE5FBFe3E9af3971dD833D26bA9b5C936f0bE",  # Binance cold wallet
]

# --- Addresses expected to screen dirty -------------------------------------
# Publicly attributed to sanctions listings or documented thefts.
FLAGGED_ADDRESSES = [
    "0x8589427373D6D84E98730D7795D8f6f8731FDA16",  # Tornado Cash (OFAC SDN)
    "0x722122dF12D4e14e13Ac3b6895a86e84145b6967",  # Tornado Cash router (OFAC SDN)
    "0xd90e2f925DA726b50C4Ed8D0Fb90Ad053324F31b",  # Tornado Cash (OFAC SDN)
    "0x47666Fab8bd0Ac7003bce3f5C3585383F09486E2",  # Bybit exploiter (Lazarus, Feb 2025)
    "0x098B716B8Aaf21512996dC57EB0615e2383E2f96",  # Ronin bridge exploiter (Lazarus)
    "0x7F367cC41522cE07553e823bf3be79A889DEbe1B",  # Lazarus-attributed
]

# --- ENS names ---------------------------------------------------------------
ENS_NAMES = [
    "vitalik.eth",
    "nick.eth",
    "brantly.eth",
]

# --- Transaction hashes ------------------------------------------------------
# Real Ethereum mainnet transactions, sampled from block 25924903.
TX_HASHES = [
    "0xe8adf22d99cb2231b9ebd68f1417be7af18afd833e37197b15909c4a696e84f2",
    "0xecd972d7fc6dab23810d0a98941aadba2f0f651f967359e052a8c201590901fa",
    "0xf5c6e422da959b1126377da86212f00180cef0bb8fd6eeba1d293a2d73492799",
    "0xf2ce7eb11789210b6889bc4dd3a4e5ca5c54776cea3fb721b06173e85e232ed7",
    "0x996703fc8ec69133e238c537328b5b1e178472665f83b17268903687e44b7ac3",
    "0xe36e827ebd3ad09561476c152f884f8657eb635f42d1d3d8ed1be4bd0431785b",
    "0x0514a640b0d6faa4d0d2c0d796eca6c156eba98300bca4fe14377537c14b30db",
    "0xa8f01b2d722d3b624208c7eb3a1a9536429aef9ba9810037f5184e71edf32ee6",
    # The Bybit exploit transaction (Feb 2025), publicly documented.
    "0xb61413c495fdad6114a7aa863a00b2e3c28945979a10885b12b30316ea9f072c",
]

# --- URLs expected to screen clean ------------------------------------------
SAFE_URLS = [
    "https://ethereum.org",
    "https://github.com",
    "https://www.google.com",
    "https://telegraphprotocol.com",
    "https://docs.uniswap.org",
    "https://www.circle.com",
    "https://base.org",
    "https://x402.org",
]

# --- URLs expected to screen dirty ------------------------------------------
# Google's official Safe Browsing test endpoints. These are published by
# Google for exactly this purpose: they are classified as phishing/malware
# by any working scanner but host no actual attack payload.
TEST_MALICIOUS_URLS = [
    "http://testsafebrowsing.appspot.com/s/phishing.html",
    "http://testsafebrowsing.appspot.com/s/malware.html",
    "http://testsafebrowsing.appspot.com/apiv4/ANY_PLATFORM/SOCIAL_ENGINEERING/URL/",
    "http://malware.testing.google.test/testing/malware/",
]

#: Interleaved so each round exercises all four intents and both risk poles,
#: and so consecutive calls rotate across miners rather than hammering one.
TARGETS: list[str] = []
for _group in (
    SAFE_ADDRESSES,
    FLAGGED_ADDRESSES,
    TX_HASHES,
    SAFE_URLS,
    TEST_MALICIOUS_URLS,
    ENS_NAMES,
):
    TARGETS.extend(_group)

__all__ = [
    "TARGETS",
    "SAFE_ADDRESSES",
    "FLAGGED_ADDRESSES",
    "ENS_NAMES",
    "TX_HASHES",
    "SAFE_URLS",
    "TEST_MALICIOUS_URLS",
]
