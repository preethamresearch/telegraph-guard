"""The routing contract is what actually stops the payment, so it is
tested independently of the network."""

from telegraph_guard.langgraph import ROUTES, _target_from, guard_node, route_on_verdict
from telegraph_guard.types import GuardConfig, GuardVerdict


def verdict(kind):
    return GuardVerdict(
        target="0xabc", target_type="address", verdict=kind, risk=0.9, confidence=0.9
    )


def test_routes_match_prd():
    assert ROUTES == {"allow": "execute", "block": "abort", "review": "human"}


def test_route_on_verdict():
    assert route_on_verdict({"guard_verdict": verdict("allow")}) == "execute"
    assert route_on_verdict({"guard_verdict": verdict("block")}) == "abort"
    assert route_on_verdict({"guard_verdict": verdict("review")}) == "human"


def test_route_accepts_serialized_verdict():
    assert route_on_verdict({"guard_verdict": {"verdict": "allow"}}) == "execute"


def test_missing_verdict_never_executes():
    assert route_on_verdict({}) == "human"
    assert route_on_verdict({"guard_verdict": None}) == "human"
    assert route_on_verdict({"guard_verdict": "nonsense"}) == "human"


def test_target_selection_prefers_url():
    assert _target_from({"to": "0xabc", "url": "https://evil.xyz"}) == "https://evil.xyz"
    assert _target_from({"to": "0xabc"}) == "0xabc"
    assert _target_from({}) is None


async def test_node_reviews_when_no_destination():
    node = guard_node(GuardConfig())
    out = await node({"pending_payment": {}})
    assert out["guard_verdict"].verdict == "review"
    assert route_on_verdict(out) == "human"


async def test_node_screens_via_injected_guard():
    class FakeGuard:
        def __init__(self):
            self.seen = []

        async def screen(self, target, config=None):
            self.seen.append((target, config.chain))
            return verdict("block")

    fake = FakeGuard()
    node = guard_node(GuardConfig(), guard=fake)
    out = await node({"pending_payment": {"to": "0xabc", "chain": "base"}})

    assert fake.seen == [("0xabc", "base")]
    assert route_on_verdict(out) == "abort"
    # State must be preserved, not replaced.
    assert out["pending_payment"]["to"] == "0xabc"
