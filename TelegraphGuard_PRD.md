# TelegraphGuard — Product Requirements Document

**Version:** 1.1 · **Date:** 7 Sep 2026 · **Status:** Build-in-progress
**Target:** Telegraph Hackathon Season I, Track 3 (Applications)
**Submission deadline:** 7 Sep 2026, 23:59 UTC (8 Sep, 05:29 IST)

---

## 1. One-line summary

TelegraphGuard is a pre-transaction safety gate for AI agents that hold wallets. Before an agent moves money, the guard screens the destination (address, transaction, or URL) across four Telegraph intents in parallel, aggregates a confidence score from competing miners, and **blocks, allows, or escalates** the action. It ships as a LangGraph node and a CrewAI tool over one shared client.

**Tagline:** *TrustFilter reads messages. TelegraphGuard stops an agent from moving money.*

---

## 2. Problem

Agents with wallets are the x402 thesis, and they are already being drained:

- May 2026: a prompt-injection attack on the Grok/Bankr agent drained ~$204K in DRB tokens. MetaMask called it the first documented exploit of its kind; SlowMist called it a "Permission Chain Attack" — the agent mapped natural-language output directly into financial instructions without validating the source.
- July 2026: Zscaler ThreatLabz showed four production LLMs completing a crypto payment after reading a poisoned web page.
- Circle's Agent Wallets (May 2026) shipped allowlists and spend limits — *policy* controls. Nobody ships the *intelligence*: is this specific address, tx, or URL actually safe, right now?
- x402 itself defines what happens when an agent needs to *pay*, and intentionally leaves unspecified what happens when it needs to *decide*.

Frameworks (LangGraph, CrewAI, LangChain) give developers `try/except` around a tool call. Nothing gives the agent a trust signal before an irreversible action.

---

## 3. Goals and non-goals

### Goals
1. G1 — A developer adds one node/tool and their agent cannot pay a flagged destination.
2. G2 — Every decision is backed by real Telegraph miner responses with on-chain `signal_hash` receipts (no mocks — hard hackathon requirement).
3. G3 — Route ≥100 real requests through each of the four target intents before deadline (Track 1 eligibility threshold; makes the FRAUD_DETECTION miners our allies).
4. G4 — Win on the judged criteria: real users, real usage, creativity/usefulness, deep (not surface) Telegraph integration, X engagement.

### Non-goals
- Not a wallet, not a key manager, not a policy engine (Circle/Bankr do that).
- Not a consumer web app. A minimal web demo page is optional; the product is the SDK.
- Not a scam-message classifier (that is TrustFilter).
- Not multi-chain beyond what live miners support (Ethereum + Base primary; Arbitrum/Polygon/OP where miners cover them).
- No mainnet money. Base Sepolia / Solana Devnet only.

---

## 4. Users

| Persona | Situation | What they need |
|---|---|---|
| **Agent developer** (primary) | Building a LangGraph/CrewAI agent that pays for services via x402 or sends USDC | A drop-in gate so the agent can't be socially engineered into paying a scammer |
| **Telegraph miner operator** (secondary, strategic) | Runs a FRAUD_DETECTION / URL_SCAN / wallet miner; needs Track 3 request volume to be prize-eligible | An app that routes real demand to them and credits them publicly |
| **Hackathon judge** | Evaluating 30-hour builds | A working live demo, verifiable signal hashes, evidence of adoption |

---

## 5. Verified platform facts the design depends on

All confirmed from live endpoints on 6–7 Sep 2026.

| Fact | Value |
|---|---|
| Engine base URL (testnet) | `https://devnode.telegraphprotocol.com/engine` |
| Auto-routed ask | `POST /engine/v1/ask` body `{ "query": "...", "context": {...} }` |
| Direct ask | `POST /engine/v1/ask/{minerId}` body `{ "method", "endpoint", "payload", "acknowledge_warnings?" }` |
| Discovery (free) | `GET /api/miners?intent=FRAUD_DETECTION`, `GET /engine/v1/intents`, `GET /engine/v1/intents/{INTENT}/miners` |
| Receipt lookup (free) | `GET /engine/v1/signal/{signal_hash}` |
| Response fields | `miner_id, miner_name, endpoint, result, cost_usd, duration_ms, timestamp, reasoning, intent, signal_hash, warnings` |
| Payment | x402; 402 challenge → sign → retry with `PAYMENT-SIGNATURE`. USDC on Base Sepolia (`eip155:84532`) or Solana Devnet. Charged only on 2xx. |
| Client libs | `@x402/fetch`, `@x402/evm`, `@x402/svm`; **Node ≥ 20** required (WebCrypto) |
| Live miner counts | FRAUD_DETECTION 15–16 · ONCHAIN_TX_LOOKUP 12 · WALLET_BALANCE_CHECK 10 · URL_SCAN 10 |
| Key miners | **302 ChainSight** (all 4 intents) · **9002 TxLens** (FRAUD, WALLET, TX; returns 0–1 `confidence` + `summary` + `canonical`) · **20260828 PREFLIGHT** (URL_SCAN w/ redirect + security-header + risk analysis, WALLET, TX) · **900 OnChain Intel** (WALLET, TX) · **152 Kriterion** (URL_SCAN) |
| Cost per call | `0.00` on all target miners (testnet) |
| Rate limits | Per miner, shared node-wide across all callers |
| Auto-route behaviour | Never blocked; fallback miner lined up. Direct path returns 422 (no charge) on predicted failure. |

---

## 6. System overview

```
┌──────────────── Agent framework ────────────────┐
│  LangGraph node        CrewAI tool     (CLI)     │
└───────────────┬─────────────────┬───────────────┘
                │  screen(target) │
        ┌───────▼─────────────────▼────────┐
        │        telegraph-guard core       │
        │  classify → fan-out → aggregate   │
        │  → gate → receipt                 │
        └───────┬──────────────────────────┘
                │ x402-wrapped fetch (parallel)
   ┌────────────┼────────────┬──────────────┐
FRAUD_DETECTION  URL_SCAN  WALLET_BALANCE  ONCHAIN_TX_LOOKUP
   (302, 9002)  (20260828,152,302) (302,9002,900,20260828) (302,9002,900,20260828)
                │
        Telegraph Engine (devnode) → signal_hash per call
```

---

## 7. Functional requirements

Priority: **P0** = must ship for submission · **P1** = ship if time · **P2** = post-hackathon.

### 7.1 Core client (`telegraph-guard` package)

| ID | Requirement | Priority |
|---|---|---|
| FR-1 | `screen(target: string, opts?) → GuardVerdict`. Accepts an EVM address (0x + 40 hex), ENS name, transaction hash (0x + 64 hex), or URL. | P0 |
| FR-2 | **Target classification** determines the intent fan-out: address/ENS → FRAUD_DETECTION + WALLET_BALANCE_CHECK; tx hash → ONCHAIN_TX_LOOKUP + FRAUD_DETECTION; URL → URL_SCAN + FRAUD_DETECTION. Unrecognised input → `review` verdict, no calls. | P0 |
| FR-3 | Calls are made **in parallel** via the Telegraph Engine only (never directly to miner base URLs — direct calls do not produce signals or count as Telegraph usage). | P0 |
| FR-4 | Default path is **auto-routed** `POST /engine/v1/ask` with a natural-language query per intent (e.g. "How likely is the address 0x… on Base to be fraudulent?"). Rationale: never blocked, fallback lined up, returns `reasoning`. | P0 |
| FR-5 | **Direct-miner mode** (`opts.miners = [302, 9002]`) via `POST /engine/v1/ask/{id}` for deterministic demos and miner-consensus mode. Endpoint/payload shapes pulled from `GET /api/miners` at startup, never hardcoded. | P0 |
| FR-6 | **x402 payment** handled transparently with `@x402/fetch`; wallet key from `TELEGRAPH_GUARD_KEY` env var; network selection from the 402 `accepts[]` array; `payTo` always read from the challenge. | P0 |
| FR-7 | **Confidence extraction**: read a numeric `confidence` (0–1) from `result` where present (TxLens, KoinMix-style miners); otherwise derive from miner agreement in consensus mode; otherwise mark the signal `confidence: null` and weight it 0.5. | P0 |
| FR-8 | **Verdict aggregation**: per-signal risk (0 = safe … 1 = fraud) weighted by confidence. Final `risk` = max of FRAUD/URL_SCAN risk, informed by wallet/tx context (e.g. zero-history address raises risk +0.15; reverted/pending tx raises +0.2). Exact weights are configurable. | P0 |
| FR-9 | **Gate**: `allow` if `risk < allowBelow` (default 0.3); `block` if `risk ≥ blockAbove` (default 0.7); else `review`. Thresholds are per-call options and env-configurable. | P0 |
| FR-10 | **Deadline**: `opts.deadlineMs` (default 8000). Signals that miss the deadline are dropped; if fewer than `opts.minSignals` (default 2) return, verdict = `review` with reason `insufficient_signals`. | P0 |
| FR-11 | **Receipt**: every verdict includes `signals[]`, each with `intent, miner_id, miner_name, confidence, risk, duration_ms, signal_hash, reasoning, verify_url` where `verify_url = https://devnode.telegraphprotocol.com/engine/v1/signal/{hash}`. | P0 |
| FR-12 | **Rate-limit handling**: on 422 rate-limit warning (direct path) or `warnings[]` mentioning rate limit (auto path), retry once on the next miner in the intent's miner list. | P0 |
| FR-13 | **Startup discovery**: on init, fetch `/engine/v1/intents` and cache miner IDs per target intent; refresh every 10 min. Fail loudly if any target intent has < 1 miner. | P0 |
| FR-14 | `warmup()` — fires one cheap request per target miner to defeat cold starts on Render/Railway free tiers. Called automatically before demos; exposed to users. | P0 |
| FR-15 | **Fail-closed option** `opts.failClosed` (default true): network/payment failure → `block` not `allow`. | P0 |
| FR-16 | Structured logging (JSON) of every call with timing, miner, and hash — used both for debugging and for the usage dashboard. | P1 |
| FR-17 | Streaming mode over the Engine WebSocket that emits routing events as they arrive (hits the "streaming" high-value area). | P2 |

### 7.2 Framework integrations

| ID | Requirement | Priority |
|---|---|---|
| FR-20 | **LangGraph**: `telegraphGuardNode(config)` — a node that reads `state.pending_payment` (`{to, amount, chain, url?}`), runs `screen`, writes `state.guard_verdict`, plus a `routeOnVerdict` conditional-edge helper mapping `allow → "execute"`, `block → "abort"`, `review → "human"`. Python first (larger LangGraph audience); TS if time. | P0 |
| FR-21 | **CrewAI**: `TelegraphGuardTool(BaseTool)` with name `telegraph_guard`, description written so an LLM calls it before any payment tool; returns the verdict as a compact string plus JSON. | P0 |
| FR-22 | **LangChain**: `StructuredTool` wrapper (thin, same client). | P1 |
| FR-23 | **CLI**: `npx telegraph-guard screen 0x…` prints verdict table with clickable verify URLs. Used in demo video and by miners testing their own coverage. | P0 |
| FR-24 | **MCP server** exposing `screen` as a tool so any MCP client (Claude, Cursor, Nasiko gateway) can call it. | P1 |

### 7.3 Flagship demo agent

| ID | Requirement | Priority |
|---|---|---|
| FR-30 | A LangGraph agent with a Base Sepolia wallet and a task "pay these three invoices". Targets: (a) a well-known exchange/contract address → expect `allow`; (b) a fresh zero-history address that just received funds → expect `review`/`block`; (c) a URL from a public phishing blocklist → expect `block`. Targets **pre-tested** for clean separation before recording. | P0 |
| FR-31 | On `allow`, the agent actually sends testnet USDC and prints the Base Sepolia tx hash. On `block`, it prints the signals and hashes that stopped it. (Real on-chain pipeline.) | P0 |
| FR-32 | 60–90 s screen recording of the above, terminal only, no slides. | P0 |

### 7.4 Demand generation and adoption evidence

| ID | Requirement | Priority |
|---|---|---|
| FR-40 | `scripts/soak.ts`: screens a curated list of ≥60 real addresses/txs/URLs across all four intents, respecting rate limits, until each intent has ≥100 signals attributable to the app. Logs every `signal_hash`. | P0 |
| FR-41 | Public `HASHES.md` in repo listing all signal hashes with verify URLs — judges and miners can audit. | P0 |
| FR-42 | Lightweight usage counter (in-repo JSON or a one-file Vercel function) recording anonymous `screen()` counts from installs, to report "N screenings by M installs" at submission. | P1 |
| FR-43 | Discord post tagging miner operators for 302, 9002, 20260828, 900, 152 with their per-miner request counts from our app. | P0 |

---

## 8. Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-1 | **Latency**: p50 verdict ≤ 4 s, p95 ≤ 8 s with warmed miners (4 parallel calls). | Measured in soak logs |
| NFR-2 | **Availability under miner failure**: any single miner down → verdict still produced from remaining signals; two intents down → `review`, never a crash. | Fault-injection test |
| NFR-3 | **Integrity**: zero mocked or cached verdicts. Every signal carries a `signal_hash` resolvable at the Engine. Caching is allowed only for discovery (`/engine/v1/intents`, `/api/miners`), never for inference. | Code review + HASHES.md |
| NFR-4 | **Security**: private key only from env; never logged; never sent anywhere but the x402 signer. Testnet keys only; README warns against mainnet. | Grep + README |
| NFR-5 | **Safe defaults**: fail-closed, `blockAbove` 0.7, `deadlineMs` 8000, `minSignals` 2. A developer who changes nothing gets a conservative guard. | Defaults doc |
| NFR-6 | **Installability**: `pip install telegraph-guard` (Python) and `npm i telegraph-guard` (Node) → working quickstart in < 5 minutes on a fresh machine. Node ≥ 20 and Python ≥ 3.10 stated up front. | Fresh-VM test |
| NFR-7 | **Observability**: JSON logs per call; `--verbose` prints router `reasoning`. | Manual |
| NFR-8 | **Rate-limit citizenship**: soak script caps at 1 req/s per miner and rotates miners; never hammers one endpoint. | Soak config |
| NFR-9 | **Determinism where possible**: same input + same miner responses → same verdict (aggregation is pure). | Unit test |
| NFR-10 | **Licensing**: MIT. Repo public from first commit. | — |
| NFR-11 | **Compliance with hackathon rules**: real miners only; no metric inflation (all volume is real screenings of real targets); X posts tag @Telegraphprotoc; Discord participation. | Checklist §13 |

---

## 9. Interfaces

### 9.1 `GuardVerdict` (canonical output)

```json
{
  "target": "0xabc…",
  "target_type": "address",
  "verdict": "block",
  "risk": 0.82,
  "confidence": 0.91,
  "reasons": ["FRAUD_DETECTION: flagged by TxLens (0.88)", "WALLET_BALANCE_CHECK: 0 prior txs, funded 2h ago"],
  "signals": [
    {
      "intent": "FRAUD_DETECTION",
      "miner_id": "9002",
      "miner_name": "TxLens",
      "risk": 0.88,
      "confidence": 0.91,
      "duration_ms": 1320,
      "signal_hash": "0x7a44…",
      "verify_url": "https://devnode.telegraphprotocol.com/engine/v1/signal/0x7a44…",
      "reasoning": "Query asks fraud likelihood of an address — routed to TxLens."
    }
  ],
  "cost_usd": 0.0,
  "elapsed_ms": 2140,
  "thresholds": { "allowBelow": 0.3, "blockAbove": 0.7 },
  "guard_version": "0.1.0"
}
```

### 9.2 Python

```python
from telegraph_guard import screen, GuardConfig
v = screen("0xabc…", GuardConfig(block_above=0.7, deadline_ms=8000))
if v.verdict != "allow": raise PaymentBlocked(v)
```

### 9.3 LangGraph

```python
from telegraph_guard.langgraph import guard_node, route_on_verdict
g.add_node("guard", guard_node())
g.add_conditional_edges("guard", route_on_verdict, {"execute": "pay", "abort": END, "human": "hitl"})
```

### 9.4 CrewAI

```python
from telegraph_guard.crewai import TelegraphGuardTool
agent = Agent(role="Treasurer", tools=[TelegraphGuardTool(), PayTool()], ...)
```

---

## 10. Success metrics (submission-time)

| Metric | Minimum | Target |
|---|---|---|
| Real signals per target intent | 100 each | 250 each |
| Distinct external installs/users | 5 | 20 |
| Miner operators engaged (reply/RT) | 3 | 8 |
| Demo: blocked targets shown live | 2 of 3 | 2 of 3 |
| X posts tagging @Telegraphprotoc | 3 | 5 |
| Quickstart time on fresh machine | < 10 min | < 5 min |

---

## 11. Build plan (remaining time, IST)

| Window | Deliverable | Kill criterion |
|---|---|---|
| Now → +2h | One paid auto-routed ask returning `signal_hash`. Fund Base Sepolia USDC. Discovery cached. | If no paid call by +2h, switch chains (Solana Devnet) before touching anything else. |
| +2 → +7h | Core client: classify, fan-out, confidence extraction, aggregate, gate, receipt, warmup, fail-closed. CLI. | If FRAUD_DETECTION results are unusable on test targets, weight URL_SCAN + wallet heuristics higher; do not stall. |
| +7 → +11h | LangGraph node + conditional edge; CrewAI tool. README quickstarts. Publish to PyPI/npm. | — |
| +11 → +14h | Flagship demo agent on Base Sepolia; pre-test 10 targets; record video. | If real USDC send fails, show the signed tx intent and hashes — still real signals. |
| +14 → +18h | Soak script to ≥100/intent; HASHES.md; Discord miner outreach; X posts 2–3. | — |
| +18 → +20h | Submit. Final X post with numbers. **Submit ≥ 2h before 23:59 UTC.** | — |

---

## 12. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Miner cold starts (Render/Railway free tiers) blow deadlines | High | `warmup()` 10 min before demo; auto-route fallback; 8 s default deadline; retry across miners |
| Shared rate limits hit by other teams | Medium | Rotate 302 / 9002 / 20260828 / 900; 422 handling; soak capped at 1 rps/miner |
| FRAUD_DETECTION output too shallow to separate targets | Medium | Consensus across ≥2 miners; wallet/tx heuristics in aggregation; pre-tested demo targets |
| x402 signing fails (Node < 20, malformed payload) | Medium | Node 20 enforced; use `@x402/fetch` not hand-rolled; try Solana devnet as alternate rail |
| Competitor surfaces in same sector | Low–Med | Post working demo early to claim narrative; differentiate as "the demand layer for safety miners" |
| Judges see "surface-level integration" | Low | Confidence gate + multi-intent + on-chain send + receipts are all in the demo, not the README |

---

## 13. Submission checklist

- [ ] Public repo, MIT, README with 5-minute quickstart (Python + Node), architecture diagram, HASHES.md
- [ ] PyPI + npm packages published
- [ ] Demo video (60–90 s) linked in README and X
- [ ] ≥100 verifiable signals per intent; explorer/hash links
- [ ] Discord: registered, miner outreach posted with per-miner counts
- [ ] X: ≥3 posts tagging @Telegraphprotoc (first paid call; blocked-payment demo; final numbers)
- [ ] Submission form: uses real miners, lists miner IDs 302 / 9002 / 20260828 / 900 / 152, names the high-value areas hit (on-chain pipeline, autonomous agent, multi-intent, confidence thresholds)
- [ ] Submitted ≥ 2 h before 23:59 UTC

---

## 14. Open questions (resolve in hour 1)

1. Exact `result` shape for FRAUD_DETECTION from 302 vs 9002 — field name for the score and its polarity (fraud-likelihood vs safety).
2. Does auto-routing reliably classify "is 0x… fraudulent" as FRAUD_DETECTION, or does it drift to WALLET_BALANCE_CHECK? If it drifts, use direct mode for that intent.
3. Base Sepolia USDC faucet throughput — enough for ~600 soak calls at $0.00 (should be, but confirm the challenge amount is actually 0).
