# Demo video script (FR-32)

**Target: 75–90 seconds. No slides, no voiceover required** — on-screen text
captions are enough and survive being watched muted, which is how most judges
will first see it.

**Primary cut: the web demo.** Start the server (`python webapp/server.py`),
open http://127.0.0.1:8402, and record the browser at 1280×720+:

1. (0:00–0:08) The task card — "Buy me a 4K webcam… under $150" — and the
   headline. Caption: *An agent with a wallet is told to go shopping.*
2. (0:08–0:15) Click **Let the agent shop**. Offers appear; the agent picks
   the cheapest. Caption: *$89 is the best price. It's also the trap.*
3. (0:15–0:40) First checkout: the guard screens the settlement address live.
   Red verdict lands. Caption: *That storefront settles to an OFAC-sanctioned
   address. Payment blocked — funds never left the wallet.*
4. (0:40–0:60) The agent falls back, second checkout clears green, order
   placed. Caption: *The guard is a filter, not a wall — the agent still
   completes the purchase safely.*
5. (0:60–0:75) Click a **verify ↗** link; the Engine receipt opens. Caption:
   *Every verdict carries an on-chain signal hash anyone can check.*
6. (0:75–0:85) The code snippet. Caption: *Three lines in a LangGraph app.
   Also a CrewAI tool, CLI, and MCP server.*

The terminal cut below remains as an alternative or B-roll.

Record at 1280×720 or larger. Use a light-on-dark terminal, font size ~16pt so
text is legible when the video is scaled down.

---

## Before recording

```bash
cd ~/Developer/telegraph-guard
set -a && . ./.env && set +a

# Warm the miners so cold starts don't stall the take (FR-14).
.venv/bin/telegraph-guard warmup

# Confirm the wallet still has USDC — a 402 mid-take kills the run.
.venv/bin/telegraph-guard wallet
```

Do one full rehearsal take. The demo passed 6 of 6 consecutive live runs, but
miners are live infrastructure — if a take fails, re-run rather than edit
around it.

Clear the screen. Start recording.

---

## Shot 1 — the problem (0:00–0:12)

Type slowly enough to read:

```bash
cat scripts/demo_agent.py | grep -A 6 "INVOICES = "
```

> **Caption:** An AI agent with a wallet is told to pay three invoices.
> One is a normal contract. One is an OFAC-sanctioned mixer. One is a
> malware URL. Nothing tells the agent which is which.

---

## Shot 2 — the guard runs (0:12–0:50)

```bash
.venv/bin/python scripts/demo_agent.py --no-send
```

Let it run uncut. It takes roughly 25–35 seconds and prints each verdict as it
lands. Do not speed up this section — the pauses are real miner latency, and
they are evidence the calls are real.

> **Caption at ~0:15:** Every call is paid over x402 and routed to live
> Telegraph miners. No mocks.

As the verdicts appear:

| On screen | Caption |
|---|---|
| `ALLOW  risk 0.10` | Known infrastructure. The agent pays. |
| `BLOCK  risk 0.80` | OFAC-sanctioned mixer. Payment stopped. |
| `BLOCK  risk 0.90` | Live malware URL. Payment stopped. |

> **Caption at the summary line:** 3 of 3 on real miner evidence. Exit code 0.

---

## Shot 3 — the receipts (0:50–1:08)

This is the shot that separates this from a mock. Copy any `verify_url` from
the output above and open it:

```bash
curl -s https://devnode.telegraphprotocol.com/engine/v1/signal/<PASTE_HASH> | python3 -m json.tool | head -20
```

> **Caption:** Every verdict carries an on-chain signal hash. Anyone can
> verify which miner answered.

Point at `miner_slug`, `subnet_id`, and `tx_hash` in the output.

---

## Shot 4 — the integration (1:08–1:15)

```bash
grep -A 3 "add_conditional_edges" scripts/demo_agent.py
```

> **Caption:** Three lines in a LangGraph app. Also ships as a CrewAI tool,
> a CLI, and an MCP server.

End on that frame.

---

## Optional 15s extension, if the cut runs short

```bash
.venv/bin/telegraph-guard screen vitalik.eth --miners 9002,95822412
```

> **Caption:** Works on addresses, ENS names, transaction hashes, and URLs.

---

## What NOT to show

- **Do not use `--replay`.** It exits 3 and prints a REPLAY banner precisely so
  it can never be mistaken for a live run. Recording it would be dishonest.
- Do not crop out the summary line. The pass/fail count and exit code are the
  proof, and a judge who cannot see them has to take your word for it.
- Do not edit out a failed take's error and splice in a good one.

---

## Caption copy, plain text for the editor

```
An AI agent with a wallet is told to pay three invoices.
One is a normal contract. One is an OFAC-sanctioned mixer. One is a malware URL.

TelegraphGuard screens each destination before the money moves.
Every call is paid over x402 and answered by live Telegraph miners.

ALLOW  — known infrastructure, the agent pays
BLOCK  — OFAC-sanctioned mixer, payment stopped
BLOCK  — live malware URL, payment stopped

Every verdict carries an on-chain signal hash. Anyone can verify it.

Three lines in a LangGraph app.
```
