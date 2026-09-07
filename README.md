# TelegraphGuard

**A pre-transaction safety gate for AI agents that hold wallets.**

Before your agent moves money, TelegraphGuard screens the destination — address, transaction hash, ENS name, or URL — across four Telegraph intents in parallel, aggregates a confidence-weighted risk score from competing miners, and **blocks, allows, or escalates** the action.

> TrustFilter reads messages. TelegraphGuard stops an agent from moving money.

Every verdict is backed by real Telegraph miner responses with on-chain `signal_hash` receipts. No mocks, no cached inference.

---

## Why

Agents with wallets are already being drained:

- **May 2026** — a prompt-injection attack on the Grok/Bankr agent drained ~$204K in DRB tokens. SlowMist called it a "Permission Chain Attack": the agent mapped natural-language output directly into financial instructions without validating the source.
- **July 2026** — Zscaler ThreatLabz showed four production LLMs completing a crypto payment after reading a poisoned web page.

Circle's Agent Wallets ship allowlists and spend limits — *policy* controls. Nobody ships the *intelligence*: is this specific address, tx, or URL actually safe, right now? x402 defines what happens when an agent needs to **pay**, and deliberately leaves unspecified what happens when it needs to **decide**.

TelegraphGuard is that decision.

---

## Install

Requires **Python ≥ 3.10**.

```bash
pip install telegraph-guard
```

### Fund a wallet

The Telegraph Engine charges **$0.01 per call** over x402 on both the auto-routed and direct-miner paths. Screening one address costs two calls (~$0.02).

```bash
export TELEGRAPH_GUARD_KEY=0x...          # Base Sepolia key — TESTNET ONLY
telegraph-guard wallet                     # prints the address to fund
```

Fund that address with **Base Sepolia USDC** from [faucet.circle.com](https://faucet.circle.com).

> **Never set `TELEGRAPH_GUARD_KEY` to a mainnet key.** The key is read from the environment, handed to the x402 signer, and never logged or transmitted anywhere else — but this is testnet software.

---

## Quickstart

```bash
telegraph-guard screen 0x1f9090aaE28b8a3dCeaDf281B0F12828e676c326
telegraph-guard screen https://some-airdrop-site.example --verbose
telegraph-guard screen 0xabc... --json
```

```
  BLOCK  0xabc…  [address]
  risk 0.82  confidence 0.91  (allow<0.3 block>=0.7)

    · FRAUD_DETECTION: TxLens risk 0.88 (0.91)
    · WALLET_BALANCE_CHECK: address has no transaction history

  SIGNALS
    FRAUD_DETECTION        TxLens                     risk 0.88  conf 0.91   1320ms
      https://devnode.telegraphprotocol.com/engine/v1/signal/0x7a44…
    WALLET_BALANCE_CHECK   ChainSight                 risk  —    conf  —      880ms
      https://devnode.telegraphprotocol.com/engine/v1/signal/0x3b91…

  2 signals · 2140ms · $0.0200 · guard 0.1.0
```

The CLI exits non-zero on anything other than `allow`, so you can gate a shell pipeline on it.

### Python

```python
from telegraph_guard import screen, GuardConfig, PaymentBlocked

v = screen("0xabc...", GuardConfig(block_above=0.7, deadline_ms=8000))
if v.verdict != "allow":
    raise PaymentBlocked(v)
```

### LangGraph

```python
from telegraph_guard.langgraph import guard_node, route_on_verdict

g.add_node("guard", guard_node())
g.add_conditional_edges("guard", route_on_verdict,
                        {"execute": "pay", "abort": END, "human": "hitl"})
```

The node reads `state["pending_payment"]` (`{to, amount, chain, url?}`) and writes `state["guard_verdict"]`. It never raises — a failure becomes a `block` under the default fail-closed config, so a broken guard cannot become an open gate. An absent verdict routes to `human`, never to `execute`.

### CrewAI

```python
from telegraph_guard.crewai import TelegraphGuardTool

agent = Agent(role="Treasurer", tools=[TelegraphGuardTool(), PayTool()], ...)
```

### MCP

Expose screening to any MCP client — Claude Desktop, Cursor, or a shared gateway.

```bash
pip install 'telegraph-guard[mcp]'
telegraph-guard-mcp                                    # stdio
telegraph-guard-mcp --transport streamable-http --port 8402
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "telegraph-guard": {
      "command": "telegraph-guard-mcp",
      "env": { "TELEGRAPH_GUARD_KEY": "0x..." }
    }
  }
}
```

Two tools are exposed: `screen` (returns the verdict, the reasons, and every
signal with its verify URL) and `list_miners` (which miners back each intent,
for auditing a verdict). Thresholds are set with the same flags as the CLI, so
a gateway operator can run a stricter guard than the default.

---

## How it works

```
                      screen(target)
                            │
                  ┌─────────▼──────────┐
                  │  classify target   │   address · ens · tx · url
                  └─────────┬──────────┘
                            │  intent fan-out
        ┌───────────────────┼───────────────────┐
   FRAUD_DETECTION      URL_SCAN        WALLET_BALANCE_CHECK
                                        ONCHAIN_TX_LOOKUP
        └───────────────────┼───────────────────┘
                            │  parallel, x402-paid, via the Engine only
                  ┌─────────▼──────────┐
                  │  extract risk +    │   normalise polarity across
                  │  confidence        │   heterogeneous miner schemas
                  └─────────┬──────────┘
                  ┌─────────▼──────────┐
                  │  aggregate + gate  │   allow · review · block
                  └─────────┬──────────┘
                            │
                    GuardVerdict + signal_hash receipts
```

**Fan-out (FR-2).** address/ENS → `FRAUD_DETECTION` + `WALLET_BALANCE_CHECK`; tx hash → `ONCHAIN_TX_LOOKUP` + `FRAUD_DETECTION`; URL → `URL_SCAN` + `FRAUD_DETECTION`. Unrecognised input returns `review` with **no calls made** — we never guess, and never spend.

**Aggregation (FR-8).** Primary risk is the max of the `FRAUD_DETECTION` and `URL_SCAN` judgements, each a confidence-weighted mean across its miners. Wallet and tx intents then *inform* that score: a zero-history address adds +0.15, a reverted or pending transaction adds +0.2.

**Polarity is explicit.** A "trust score" of 0.9 and a "risk score" of 0.9 mean opposite things. Miner keys are matched against separate safe/unsafe vocabularies rather than a generic float sweep, and anything uninterpretable becomes `None` — weighted 0.5, never silently read as safe.

**Gate (FR-9).** `allow` below 0.3, `block` at or above 0.7, `review` in between. All thresholds are per-call options.

**Safe defaults (NFR-5).** fail-closed, `block_above` 0.7, `deadline_ms` 8000, `min_signals` 2. A developer who changes nothing gets a conservative guard. Fewer than `min_signals` usable responses yields `review`; a total failure with `fail_closed` yields `block`, not `allow`.

**Receipts (FR-11).** Every signal carries its `signal_hash` and a `verify_url` at the Engine, so any judge or miner operator can audit the decision independently.

---

## Configuration

| Option | Default | Meaning |
|---|---|---|
| `allow_below` | `0.3` | risk strictly below this → `allow` |
| `block_above` | `0.7` | risk at or above this → `block` |
| `deadline_ms` | `8000` | signals arriving later are dropped (FR-10) |
| `min_signals` | `2` | fewer usable signals → `review` |
| `fail_closed` | `True` | network/payment failure → `block`, not `allow` |
| `miners` | `None` | direct-miner mode, e.g. `["302", "9002"]` (FR-5) |
| `chain` | `"ethereum"` | chain named in the miner query |

Set `TELEGRAPH_GUARD_LOG=1` for structured JSON logs of every call (miner, timing, hash).

---

## CLI reference

```
telegraph-guard screen <target...>   screen addresses, tx hashes, ENS names, URLs
telegraph-guard miners               list live miners per target intent
telegraph-guard warmup               warm miners against cold starts (FR-14)
telegraph-guard wallet               show the x402 signer address to fund
```

---

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q
```

The test suite runs without network access or a wallet: aggregation and classification are pure (NFR-9), and the LangGraph routing contract is tested against an injected fake guard.

---

## Status

Testnet only — Base Sepolia. Not a wallet, not a key manager, not a policy engine.

MIT licensed.
