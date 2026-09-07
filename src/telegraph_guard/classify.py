"""Target classification (FR-1, FR-2).

Decides what a caller handed us and therefore which Telegraph intents to
fan out to. Unrecognised input yields ``unknown``, which the core turns
into a ``review`` verdict with no calls made — we never guess.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from .types import FANOUT, TargetType

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_TX_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
# ENS and other supported TLDs resolvable by the wallet miners.
_ENS_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}(\.[a-z0-9-]+)*\.(eth|base\.eth)$", re.I)


def classify(target: str) -> TargetType:
    """Classify a screening target.

    >>> classify("0x1f9090aaE28b8a3dCeaDf281B0F12828e676c326")
    'address'
    >>> classify("vitalik.eth")
    'ens'
    """
    if not isinstance(target, str):
        return "unknown"
    t = target.strip()
    if not t:
        return "unknown"

    if _ADDRESS_RE.match(t):
        return "address"
    if _TX_RE.match(t):
        return "tx"
    if _ENS_RE.match(t):
        return "ens"

    # A URL either carries an explicit scheme, or looks like a bare host
    # with a dotted TLD. Bare hosts are normalised to https:// by the caller.
    if "://" in t:
        parsed = urlparse(t)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return "url"
        return "unknown"

    # Bare host such as "evil-airdrop.example" or "site.com/path".
    host = t.split("/", 1)[0]
    if "." in host and " " not in t and _is_hostlike(host):
        return "url"

    return "unknown"


def _is_hostlike(host: str) -> bool:
    if host.startswith(".") or host.endswith("."):
        return False
    labels = host.split(".")
    if len(labels) < 2 or len(labels[-1]) < 2:
        return False
    return all(re.fullmatch(r"[a-zA-Z0-9-]+", lbl) for lbl in labels)


def normalize(target: str, target_type: TargetType) -> str:
    """Canonicalise a target for querying (lowercase hex, scheme-qualified URLs)."""
    t = target.strip()
    if target_type in ("address", "tx"):
        return t.lower()
    if target_type == "ens":
        return t.lower()
    if target_type == "url" and "://" not in t:
        return f"https://{t}"
    return t


def intents_for(target_type: TargetType) -> list[str]:
    """Intent fan-out for a target type (FR-2)."""
    return list(FANOUT.get(target_type, []))
