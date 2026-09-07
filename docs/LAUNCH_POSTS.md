# Launch posts — drafts

Every number below is measured, not estimated. Sources are noted so anything
can be checked before posting. **Nothing here has been posted** — these are
drafts for you to send.

Fill in before posting:
- `https://github.com/preethamresearch/telegraph-guard` — the public GitHub URL
- `<VIDEO>` — the demo video link
- Live demo URL (already filled): https://preethamresearch.github.io/telegraph-guard/
  — a stable GitHub Pages redirect to the demo tunnel. If the tunnel URL
  changes, update the redirect in the gh-pages branch; posted links keep working.
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

**3 posts, each verified ≤280 chars (URLs count as 23 on X). Post as a thread,
in order. Add the video link to post 1 when it exists (a link replaces 23 chars
— it still fits).**

### Post 1 — hook + live demo

AI agents have wallets now — and prompt injections are draining them.

I built TelegraphGuard: a safety gate that screens every payment destination through live @Telegraphprotoc miners before money moves.

Try it live: https://preethamresearch.github.io/telegraph-guard/

### Post 2 — the proof

One agent, 3 merchants. The cheapest settles to an OFAC-sanctioned mixer — blocked at risk 0.80, on-chain receipt attached. The agent falls back and buys safely.

590 verified @Telegraphprotoc signals, all auditable:
https://github.com/preethamresearch/telegraph-guard

### Post 3 — flywheel evidence (what the judges say they want)

Flywheel evidence @Telegraphprotoc asked for: miner quality differs (one scored a mixer & a clean router identically; another split them 0.80 vs 0.10). Our demand followed quality — 435 calls to the better miner, published so it feeds their rankings. 37/39 on a labelled corpus.

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
