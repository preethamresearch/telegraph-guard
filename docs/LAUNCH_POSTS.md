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

# X posts

**6 posts, each verified ≤280 chars (URLs count as 23 on X). Each stands alone —
post any one, several, or all as a thread. Every post tags @Telegraphprotoc
(rule 03). Add the video link to post 1 when it exists.**

### Post 1 — hook + live demo

AI agents have wallets now — and prompt injections are draining them.

I built TelegraphGuard: a safety gate that screens every payment destination through live @Telegraphprotoc miners before money moves.

Try it live: https://preethamresearch.github.io/telegraph-guard/

### Post 2 — the demo story

Gave a shopping agent $150 and three merchants. The cheapest settles to an OFAC-sanctioned mixer.

@Telegraphprotoc miners flagged it — risk 0.80, payment blocked, receipt on-chain. The agent fell back and bought safely.

https://preethamresearch.github.io/telegraph-guard/

### Post 3 — receipts

Every TelegraphGuard verdict carries an on-chain signal_hash from @Telegraphprotoc. You don't trust my API — you open the receipt and see which miner answered.

590 verified signals published:
https://github.com/preethamresearch/telegraph-guard/blob/main/HASHES.md

### Post 4 — numbers, honestly

TelegraphGuard by the numbers on @Telegraphprotoc: 590 verified signals · 4 intents · 6/6 live demo runs · 37/39 on a labelled corpus.

The 2 misses were miner coverage gaps — published in the repo, not hidden.

https://github.com/preethamresearch/telegraph-guard

### Post 5 — flywheel evidence

Flywheel evidence @Telegraphprotoc asked for: miner quality differs (one scored a mixer & a clean router identically; another split them 0.80 vs 0.10). Our demand followed quality — 435 calls to the better miner, published so it feeds their rankings.

### Post 6 — the ask to miners

If you run a FRAUD_DETECTION miner on @Telegraphprotoc: TelegraphGuard routes real demand from agents about to move money.

What's missing: more miners that take a bare address and return a 0-1 risk score + confidence. Build it and I'll route to you.

---

# Discord — miner operator outreach (FR-43)

Post in the hackathon channel. Two messages (Discord free tier caps at 2000
chars each; tables don't render — these are formatted for Discord). Post
message 1, then message 2 as a reply/thread. Tag the operators if their
handles are known.

--- MESSAGE 1 ---

**TelegraphGuard — 590 real signals routed to your miners** :shield:

Built for Track 3: a pre-transaction safety gate for AI agents with wallets. Before an agent pays, it screens the destination across four intents and returns **allow / review / block**. Every verdict is backed by your signals, with resolvable hashes.

**Try it live:** https://preethamresearch.github.io/telegraph-guard/
**Repo:** https://github.com/preethamresearch/telegraph-guard
**All 590 hashes:** https://github.com/preethamresearch/telegraph-guard/blob/main/HASHES.md

**Demand routed per miner (~30 min soak):**
`9002` TxLens — **435**
`20260828` PREFLIGHT Infrastructure Signals — **145**
`5001` URL Sentinel — **10**

Per intent: FRAUD_DETECTION 265 · URL_SCAN 125 · WALLET_BALANCE_CHECK 100 · ONCHAIN_TX_LOOKUP 100

These counts are yours to cite — application demand feeds the miner track's ranking. Feedback from screening 64 real targets in the next message :thread:

--- MESSAGE 2 ---

**Miner feedback from 64 real targets** (offered constructively — this made your endpoints part of a live product)

**TxLens (9002)** — `/assess-wallet` is the best address-fraud endpoint on the network right now. The 2,600-entity registry caught Tornado Cash as a known mixer. Two notes:
• it returns `probability 0` with `assessment_status: NOT_APPLICABLE` for a mixer — a naive integration reads that as "safe" and pays a sanctioned address. I special-cased it, but the polarity is a footgun.
• the Uniswap V3 router scored 0.9 — I suspect circular-funding fires on contracts that legitimately return funds to funders.

**PREFLIGHT (20260828)** — `/url-scan` was the most reliable scorer in the run: 9/9 on live URLhaus malware URLs, 14/14 on known-good domains, stated confidence every time. Nothing to fix.

**ChainSight (302)** — heads up: `/fraud` returned byte-identical prose ("does not appear in any known scam, phishing, or fraud database") for the Uniswap router *and* an OFAC-sanctioned Tornado Cash address. Since the auto-router prefers you for FRAUD_DETECTION, integrations that trust it will allow payments to sanctioned addresses. I had to pin miners to work around it.

**What would help every consumer most:** a second FRAUD_DETECTION endpoint that takes a bare address and returns a 0-1 risk score with stated confidence. TxLens is the only one today — a single point of failure for everyone screening addresses. Build it and TelegraphGuard routes to you.

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
