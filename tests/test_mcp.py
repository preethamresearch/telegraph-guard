"""MCP surface (FR-24).

Two layers: the registered tools are driven through the server's own
call_tool path (so schema generation and result serialisation are real),
and the tool contract itself is asserted — an MCP client's only defence
against a socially-engineered payment is what the description says.
"""

from __future__ import annotations

import json

import pytest

from telegraph_guard.mcp_server import SCREEN_DESCRIPTION, _summary, build_server
from telegraph_guard.types import GuardConfig, GuardVerdict, Signal

mcp = pytest.importorskip("mcp")


def verdict(kind="block", risk=0.88):
    return GuardVerdict(
        target="0xabc",
        target_type="address",
        verdict=kind,
        risk=risk,
        confidence=0.9,
        reasons=["FRAUD_DETECTION: TxLens risk 0.88 (0.90)"],
        signals=[
            Signal(
                intent="FRAUD_DETECTION",
                miner_id="9002",
                miner_name="TxLens",
                risk=risk,
                confidence=0.9,
                signal_hash="0xfeed",
            )
        ],
        thresholds={"allowBelow": 0.3, "blockAbove": 0.7},
    )


class StubGuard:
    def __init__(self, kind="block"):
        self.kind = kind
        self.seen: list[str] = []

    async def screen(self, target, config=None):
        self.seen.append(target)
        return verdict(self.kind)

    async def aclose(self):
        pass


def server_with(kind="block"):
    stub = StubGuard(kind)
    return build_server(GuardConfig(), guard=stub), stub


# --- tool registration ------------------------------------------------------


async def test_screen_tool_is_registered():
    server, _ = server_with()
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert "screen" in names
    assert "list_miners" in names


async def test_screen_tool_schema_takes_a_target_string():
    server, _ = server_with()
    tool = next(t for t in await server.list_tools() if t.name == "screen")
    props = tool.input_schema["properties"]
    assert "target" in props
    assert props["target"]["type"] == "string"
    assert tool.input_schema.get("required") == ["target"]


# --- invocation -------------------------------------------------------------


def _payload(result):
    """Pull the structured dict back out of a CallToolResult."""
    assert not result.is_error, result
    if result.structured_content is not None:
        return result.structured_content
    # Fall back to the text block, which must carry the same JSON.
    for block in result.content:
        if getattr(block, "text", None):
            return json.loads(block.text)
    raise AssertionError(f"no payload in {result!r}")


async def test_screen_returns_the_verdict_and_receipts():
    server, stub = server_with("block")
    payload = _payload(await server.call_tool("screen", {"target": "0xabc"}))

    assert stub.seen == ["0xabc"]
    assert payload["verdict"] == "block"
    assert payload["risk"] == pytest.approx(0.88)
    assert payload["signals"][0]["verify_url"].endswith("/engine/v1/signal/0xfeed")
    assert payload["guard_version"]


async def test_screen_summary_tells_the_model_what_to_do():
    server, _ = server_with("block")
    payload = _payload(await server.call_tool("screen", {"target": "0xabc"}))
    assert "DO NOT send funds" in payload["summary"]

    server, _ = server_with("allow")
    payload = _payload(await server.call_tool("screen", {"target": "0xabc"}))
    assert "Safe to proceed" in payload["summary"]


async def test_review_summary_is_not_a_soft_allow():
    server, _ = server_with("review")
    payload = _payload(await server.call_tool("screen", {"target": "0xabc"}))
    summary = payload["summary"]
    assert "human approval" in summary
    assert "Safe to proceed" not in summary


# --- the contract the calling model actually reads --------------------------


def test_description_states_the_precondition():
    d = SCREEN_DESCRIPTION.lower()
    assert "before" in d and "must" in d
    # Every verdict must be explained, or a model will improvise on the ones
    # that are not.
    for word in ("allow", "review", "block"):
        assert word in d
    assert "not a soft allow" in d


def test_summary_includes_verify_urls():
    text = _summary(verdict())
    assert "/engine/v1/signal/0xfeed" in text
    assert "TxLens" in text
