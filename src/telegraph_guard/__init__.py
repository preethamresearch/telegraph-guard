"""TelegraphGuard — a pre-transaction safety gate for AI agents that hold wallets.

    from telegraph_guard import screen, GuardConfig, PaymentBlocked

    v = screen("0xabc...")
    if v.verdict != "allow":
        raise PaymentBlocked(v)
"""

from .aggregate import aggregate
from .classify import classify, intents_for
from .core import Guard, ascreen, build_query, screen
from .types import (
    GUARD_VERSION,
    GuardConfig,
    GuardVerdict,
    PaymentBlocked,
    Signal,
    verify_url,
)

__version__ = GUARD_VERSION

__all__ = [
    "Guard",
    "GuardConfig",
    "GuardVerdict",
    "PaymentBlocked",
    "Signal",
    "aggregate",
    "ascreen",
    "build_query",
    "classify",
    "intents_for",
    "screen",
    "verify_url",
    "__version__",
]
