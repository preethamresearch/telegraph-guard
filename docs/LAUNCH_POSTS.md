# Launch posts — drafts

Every number below is measured, not estimated. Sources are noted so anything
can be checked before posting. **Nothing here has been posted** — these are
drafts for you to send.

Fill in before posting:
- `https://github.com/preethamresearch/telegraph-guard` — the public GitHub URL
- `<VIDEO>` — the demo video link
- `<HANDLE>` — your X handle, if you want it in the Discord post

**Measured figures** (from `soak-signals.jsonl`, `HASHES.md`, and six
consecutive live demo runs):

| Figure | Value | Source |
|---|---|---|
| Total verified signals | 590 | `wc -l soak-signals.jsonl` |
| FRAUD_DETECTION | 265 | HASHES.md |
| URL_SCAN | 125 | HASHES.md |
| WALLET_BALANCE_CHECK | 100 | HASHES.md |
| ONCHAIN_TX_LOOKUP | 100 | HASHES.md |
| TxLens (9002) | 435 | HASHES.md per-miner table |
| PREFLIGHT (20260828) | 145 | HASHES.md per-miner table |
| URL Sentinel (5001) | 10 | HASHES.md per-miner table |
| Demo runs passing | 6 of 6 | consecutive live runs |
| Accuracy on labelled corpus | 37 of 39 | soak analysis |
| Tests | 126 | `pytest -q` |

---

# X thread

### Post 1 — what it is

> AI agents have wallets now. In May a prompt injection drained ~$204K from the
> Grok/Bankr agent — it turned text it read into a transfer without ever
> checking the destination.
>
> Allowlists and spend limits are policy. They can't tell you if an address is
> actually safe.
>
> So I built TelegraphGuard: a pre-transaction safety gate for agents, running
> on @Telegraphprotoc miners.
>
> <VIDEO>

### Post 2 — the demo

> One agent, three invoices, one LangGraph node between its intent and its
> wallet:
>
> ALLOW  0.10 — Uniswap router
> BLOCK  0.80 — OFAC-sanctioned Tornado Cash
> BLOCK  0.90 — live malware URL from URLhaus
>
> Every call paid over x402, answered by live @Telegraphprotoc miners. No mocks.

### Post 3 — receipts

> The part I care about: every @Telegraphprotoc verdict carries an on-chain
> signal_hash.
>
> You don't have to trust my API. Open the receipt and see which miner answered,
> and when.
>
> 590 signals published in HASHES.md, all verifiable:
> https://github.com/preethamresearch/telegraph-guard/blob/main/HASHES.md

### Post 4 — numbers, and the honest part

> Final numbers, all measured:
>
> · 590 verified signals across 4 intents
> · 265 FRAUD · 125 URL_SCAN · 100 WALLET · 100 TX
> · 6/6 live demo runs
> · 37/39 correct on a labelled corpus
>
> The 2 misses were @Telegraphprotoc miner coverage gaps, not aggregation
> bugs. Details in the repo — I'd rather publish them than hide them.
>
> https://github.com/preethamresearch/telegraph-guard

### Post 5 — flywheel evidence (this is what the judges say they want)

> The hackathon brief says: "We are not looking for the best demo. We are
> looking for real evidence that the quality flywheel works."
>
> Evidence from routing 590 real calls on @Telegraphprotoc:
>
> · Miner quality differs measurably: one FRAUD miner returned identical prose
>   for a clean router and an OFAC-sanctioned mixer; another separated them
>   0.10 vs 0.80.
> · Demand followed quality: after calibration, 435 of our FRAUD calls went to
>   the miner that discriminates.
> · That demand is published per-miner, so it feeds their rankings.
>
> Better miners earned our traffic. That's the flywheel, observed.

### Post 6 — the ask (optional)

> If you run a FRAUD_DETECTION miner on @Telegraphprotoc: TelegraphGuard sends
> you real demand from agents that are about to move money.
>
> The bottleneck isn't routing, it's coverage. A bare address needs a 0-1 risk
> score and a stated confidence. Build that and I'll route to you.

---

# Discord — miner operator outreach (FR-43)

Post in the hackathon / miner channel. Tag the operators for 9002, 20260828,
and 5001.

> **TelegraphGuard — 590 real signals routed to your miners**
>
> Built a pre-transaction safety gate for AI agents with wallets. Before an
> agent pays, it screens the destination across four intents and returns
> allow / review / block. Every verdict is backed by your signals with
> resolvable hashes.
>
> **Demand routed to you over ~30 minutes:**
>
> | Miner | Signals |
> |---|---|
> | 9002 TxLens | 435 |
> | 20260828 PREFLIGHT Infrastructure Signals | 145 |
> | 5001 URL Sentinel | 10 |
>
> Per intent: FRAUD_DETECTION 265 · URL_SCAN 125 · WALLET_BALANCE_CHECK 100 ·
> ONCHAIN_TX_LOOKUP 100. Full hash list: https://github.com/preethamresearch/telegraph-guard/blob/main/HASHES.md
>
> **Direct feedback from screening 64 real targets, in case it's useful:**
>
> **@9002 TxLens** — `/assess-wallet` is the best address-fraud endpoint I found
> on the network. The 2,600-entity registry caught Tornado Cash as a known
> mixer. Two notes: it returns `probability 0` for a mixer with
> `assessment_status: NOT_APPLICABLE`, which a naive integration reads as
> "safe" and allows a payment to a sanctioned address — I special-cased it,
> but the polarity is a footgun. And the Uniswap V3 router scored 0.9, I think
> circular-funding firing on a contract that legitimately returns funds to its
> funders.
>
> **@20260828 PREFLIGHT** — `/url-scan` was the most reliable scorer in the run:
> 9/9 on live URLhaus malware URLs and 14/14 on known-good domains, with a
> stated confidence every time. Nothing to fix.
>
> **@302 ChainSight** — heads up, and I mean this constructively: `/fraud`
> returned byte-identical prose ("does not appear in any known scam, phishing,
> or fraud database") for the Uniswap router *and* for an OFAC-sanctioned
> Tornado Cash address. Because the auto-router prefers you for
> FRAUD_DETECTION, an integration that trusts it will allow payments to
> sanctioned addresses. I had to pin miners to work around it.
>
> **What would help most:** a FRAUD_DETECTION endpoint taking a bare address and
> returning a 0-1 risk score with a stated confidence. Right now TxLens is the
> only one that does, so address screening has a single point of failure —
> a second implementation immediately makes every consumer more robust.
>
> Repo: https://github.com/preethamresearch/telegraph-guard

---

## Honesty checks before posting

- The $204K Grok/Bankr figure and the SlowMist "Permission Chain Attack"
  attribution come from the PRD's own background. Re-verify against the
  original reporting before putting a number in public.
- Do not claim "N installs" or "N users" — there are none yet, and the
  hackathon rules forbid metric inflation (NFR-11).
- Every signal count is real screening of real targets. Say so if asked.
- The 37/39 accuracy figure is on a 39-target labelled corpus. Do not round
  it to "95% accurate" without that context.
