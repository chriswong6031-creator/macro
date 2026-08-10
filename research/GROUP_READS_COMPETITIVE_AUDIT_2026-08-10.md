# Group Reads — §7 competitive + production-quality audit (2026-08-10)

**What this is.** The post-build audit `research/GROUP_READS_MASTERPLAN_BY_FABLE.md` §7 deferred to audit time: "does this beat Jodie/Struct/Quartr/EarningsCall.ai/EquityDesk *individually*", graded on the operator's six axes. The build-out it waited on shipped and live-verified 2026-08-10 (`research/GROUP_READS_SESSION3_HANDOFF_2026-08-10.md`). Evidence: fresh competitor recon walks (2026-08-10) + a production-quality audit of our shipped surfaces against the masterplan §0 gates.

**Honesty rule for this doc.** The house null discipline applies to self-assessment: where a competitor's core job is one we do not do, the verdict says so plainly ("orthogonal — we don't compete on X") instead of inflating an adjacent capability into a win. "Beat individually" is graded as two separable claims: (1) **home turf** — for the core job that product sells, would our surface do that job well enough that a subscriber wouldn't miss them; (2) **moats** — the axes we hold that they lack. A win on (2) never silently substitutes for a loss on (1).

## §A Rubric (frozen — reuse for future re-audits)

Six dimensions, from the operator's §7 grading axes. Scale per dimension per competitor: **BEAT** (we are materially better) / **PARITY** (comparable job done) / **BEHIND** (they are materially better) / **N/A** (they do not play this axis — noted, not scored). Every grade carries one-line evidence with a source (URL or file:line). Composite scores across dimensions are deliberately not computed (house law: disclosed rules over named legs, no fused ranks — the per-competitor verdict is a written judgment, not an average).

| # | Dimension | Question it grades | BEAT looks like |
|---|---|---|---|
| R1 | Read assembly quality | Does the surface deliver an assembled *read* — plain-word stance, evidence tiles, "what strengthens/weakens this" — or raw metrics the user must assemble themselves? | Stance line answering "so what do I do" (even when the answer is "watch — don't chase"), receipts one hover away, conditions named |
| R2 | Membership hygiene | Is group membership curated, point-in-time, and free of junk (preferred shares, misfiled tickers), or noisy auto-discovery? | Curated PIT baskets + discovered candidates kept separate; zero junk members in shipped baskets |
| R3 | Arc answers | Does it answer "is the washout done / where in the cycle is this group" at group grain? | A group-grain arc/washout state with disclosure of its evidence and its nulls |
| R4 | Earnings integration | Per-group earnings clock, beat/surprise rollup, guidance, revision breadth, sympathy — integrated into the group read? | Group-grain earnings pulse joined to the same surface as participation/flow |
| R5 | Honest-null discipline | Coverage counts declared, floors enforced, nulls printed with plain-word reasons — or silent fills and survivor stats? | n_members/n_covered on every cross-sectional stat; thin baskets render null with a reason |
| R6 | Bilingual reach | EN/ZH at glance tier, meaning-equivalent (not English-shaped) | Full zh READ band; no translated `title=` attrs; zh in builders and templates |

## §B Competitor dossiers

*(filled from 2026-08-10 recon; each dossier: identification + confidence, core job, feature inventory with URLs, pricing, the six-dimension read, what they conspicuously lack)*

### B1 Jodie.ai (walked live 2026-08-10; diffed vs the 2026-08-08 teardown)

**Core job:** evidence-auditable co-movement detection joined to SEC-filing-sourced business relationships — "Connected-market intelligence with filing receipts." Explicit non-claims repeated site-wide: "No forecasts. No buy or sell calls. No price targets."

**Engine (methodology page, self-described):** residualize returns vs market proxy → nightly Ledoit–Wolf shrinkage covariance + Louvain clustering over ~1,900 US stocks → new-formation detection "calibrated to ~1 false signal / 2 trading weeks" → 15-min refresh of participation breadth / volume / flow / dispersion. They publish their own validation stats (52% forward co-movement precision; 42.9% vs 30% baseline filing-similarity co-movement; 1.25–1.33× near-term realized movement "concentration, not direction").

**Surfaces:** Today/"MY RADAR" feed (delayed for free, real-time Pro); themes index — **40 named groups** with per-group status tags **"Strengthening / Cooling / Steady"**; per-theme pages (sections: THE TRADER READ / WHAT CHANGES THE READ / EVIDENCE CLOCK / THEME CONSTRUCTION / WHO IS IN IT / HAS THIS HAPPENED BEFORE); per-ticker situation reports with relationship graphs; EOD wrap with a **numbered-Cluster leaderboard** (e.g. "Cluster 388 ($ARW)") hinting at a looser auto-clustered substrate beyond the 40 curated names (relationship unverified). Watchlist alerts (free tier: 3 names).

**Pricing:** Free $0 / Pro **$29/mo "founding rate — locked for life"** (struck $39 regular) / **$290/yr**. Pro = live-forming events, unlimited monitoring, alerts, portfolio connected-exposure, full change history with filing evidence.

**Diff findings vs 08-08 (the four flagged absences):**
1. **Earnings — partial and ADJACENT, not integrated.** Core theme/ticker pages verified free of earnings fields (no dates/EPS/surprise/guidance; the Diversified Financials theme even prints "No verified recent catalyst is attached to this move"). BUT the Jodie brand now spans **struct.news** ("Powered by jodie.ai"), publishing per-company earnings briefs (60+ over Aug 7–10). Positioning splits the jobs: "Struct explains the story once. Jodie keeps watching what changes next." No group page surfaces a Struct brief inline — **no group-grain earnings read anywhere** (see B2).
2. **Cycle state — a lifecycle layer EXISTS** (missed in the 08-08 teardown): "Setting up → Activating → Expanding → Weakening," surfaced as the Strengthening/Cooling/Steady tags. This is a **co-movement trajectory** state — it answers "is this theme's co-movement building or fading," NOT "is the washout done" (no drawdown/capitulation/reclaim construct; "washout"/"arc" verified absent site-wide). Adjacent, not equivalent — the verdict in §D grades this precisely.
3. **Chinese — verified absent** (no /zh route, no hreflang, no zh content findable).
4. **Membership noise — still live.** Fresh example: "Regional Banks & Industrials" (market-discovered, 14 members) contains **zero industrials** — all 14 are banks/financials/insurers — and the page itself concedes "Capital-flow agreement is 0%, so the basket is not yet clean." (Preferred-share pattern from 08-08 not re-sampled — only 2/40 member lists pulled.)

**Personas (use-cases page):** self-directed investor (hidden concentration), active trader (catch rotation pre-consensus), time-pressed trader (one screen replaces 40 charts).

**Unverified/open:** sitemap carries `?market=europe/asia/crypto` params and ~800+ non-US ticker routes, but the asia param renders the US landing — multi-market coverage COULD NOT VERIFY (JS routing). No social presence findable at all (no X/LinkedIn/blog/changelog — all 404 or absent).
### B2 Struct — PENDING RECON (identification itself part of the task)
### B3 Quartr — PENDING RECON
### B4 EarningsCall.ai (earningscall.ai, walked 2026-08-10)

**Identification note:** distinct from EarningsCall LLC / earningscall.io/.biz (a transcript/audio data-API vendor, 5,256 companies) — secondary sources blend the two; coverage counts for the .ai product are unverified.

**Core job:** AI earnings-call summarization for individuals — "save hours reading transcripts." Single tier **$25/mo** (7-day trial; annual toggle "24% off", amount unrendered). Features: AI summaries, tweet-style digests, chat over earnings data, "Guidance & Q&A Insights," sentiment/tone detection, **peer benchmarking capped at 4 manually-picked companies**, watchlist alerts, earnings calendar, Weekly Intelligence + Tariff Impact Tracker (nav items; content login-gated, unverified).

**Absences (per public pages):** no basket/theme construction (peer compare is ad hoc, max 4); no co-movement; no group-grain rollup of any kind; no surprise-vs-consensus tracking found; no estimate revisions; no cycle/arc state; no read-through/counterparty logic; no zh (NOT FOUND — app screens unauditable anonymously).

### B5 EquityDesk (equitydesk.ai — identification MEDIUM-HIGH, plausible but uncorroborated by third parties)

**Identification note:** best category match ("Where technicals and fundamentals converge"; solo founder, ex-CIO/Partner at HQAM). Name collides with unrelated entities (India's "The Equity Desk" blog etc.). No independent press/reviews found.

**Core job:** per-stock swing screen marrying **Weinstein 4-stage analysis** (US/EU/Asia markets) with LLM earnings-call scoring on two axes (Performance = beat/growth magnitude; Sentiment = raising vs walking back outlook), plus industry relative strength, alt-data (Google Trends/TikTok/Reddit/Wikipedia), and slide decks for 3,000+ companies. Flagship "Fundamental Stage 2" screen (early Stage 2 + quality ≥85 + call-sentiment ≥24 + call-performance ≥6) with a **published backtest** (~61% hit rate, ~7.0% mean excess/trade, ~8-week hold) and a mechanical exit rule. Single tier **$25/mo**.

**Epistemically notable:** their white paper discloses what they tested and REMOVED (RS quality gate, breakout patterns, industry-strength filtering — "flattened completely", volatility thrusts) and self-flags the commodity-sector blind spot. Credible-honest for a signal vendor — but they are a signal vendor: the product's center is an authority claim (a screen with a hit rate), the opposite of our display-tier read discipline.

**Absences (vendor-confirmed in their own white paper):** "Stock Baskets or Thematic Grouping: **Not offered**. The screen produces individual stock candidates, not grouped themes or basket strategies." No co-movement, no group earnings rollup, no supply-chain/read-through (self-disclosed), no episode ledger at group grain (stock-level entry/exit rules only), no zh. Their cycle state is real but **per-stock price-technical** — not basket-grain, no washout/capitulation construct, no participation trajectory.

## §C Our shipped quality (production audit vs §0 gates)

*(filled from the repo audit: §0 gate grid G0-1..G0-10, six-dimension self-grade with file:line evidence, ranked worst gaps)*

## §D Verdict matrix

Grades are **us vs them** on each rubric dimension (BEAT = we are materially better / PARITY / BEHIND / N/A = they don't play the axis). Per-competitor verdicts below the grid answer the operator's question in two parts: home turf, then moats.

| Dim | vs Jodie.ai | vs Struct | vs Quartr | vs EarningsCall.ai | vs EquityDesk |
|---|---|---|---|---|---|
| R1 read assembly | *(pending §C)* | — | — | *(pending §C)* | *(pending §C)* |
| R2 membership hygiene | — | — | — | **BEAT** (no baskets at all — ad hoc 4-peer compare vs our 48/49 curated PIT baskets) | **BEAT** (vendor-confirmed "not offered") |
| R3 arc answers | — | — | — | **BEAT** (absent) | **BEAT at group grain** (their Weinstein stages are real but per-stock; we ship the same framework as basket stage-shares PLUS washout/turn constructs they lack; N/A at their per-stock grain — we don't sell a per-stock entry screen and don't want to) |
| R4 earnings integration | — | — | — | **BEAT at group grain** (they summarize single calls well — no rollup, no surprise-vs-consensus found; our earnings_pulse joins clock/beat/sympathy to the basket read) | **BEAT at group grain** (two-axis per-call LLM scores feed a stock screen, vendor-confirmed no group rollup) |
| R5 honest nulls | — | — | — | **BEAT** (no coverage/floor concept anywhere) | **BEAT at surface tier, with respect** (their methodology paper honestly discloses removed features and blind spots — but the product's face is an authority claim, a hit-rate screen; ours prints n_covered and refuses thin baskets at the surface itself) |
| R6 bilingual reach | — | — | — | **BEAT** (NOT FOUND any zh) | **BEAT** (NOT FOUND any zh; their "Asian markets" is listing coverage, not language) |

**vs EarningsCall.ai:** home turf = single-call consumption (summary, chat, tone). We do not compete there — our earnings layer is structured figures + group rollup, not a call reader; a user who wants "summarize this call and let me chat with it" is buying a different job ($25/mo). Their turf does not touch ours: no baskets, no co-movement, no group anything, no cycle state, no zh. **Verdict: orthogonal home turf we concede by design; every group-grain axis is ours uncontested.**

**vs EquityDesk:** home turf = a per-stock swing screen with published backtest authority. We deliberately do not sell that job (display-tier law; DNR:KILL-PSS-SR3-PARTICIPATION forbids participation-as-timing). The overlap is the Weinstein framework — theirs per-stock as an entry gate, ours as basket stage-share description — and per-call LLM reads — theirs originating scores that gate a screen, ours de-escalate-only over structured figures. **Verdict: we beat them on every group-grain axis (all vendor-confirmed absent); their authority-tier screen is a job we refuse on epistemic law, not a capability gap — the audit records it as a positioning difference, not a BEHIND.**

## §E Gaps → waves

*(every GAP/BEHIND mapped to a wave — GR4 / GR0.1 / GR3 phase-2 / new — re-prioritized by what the comparison exposed)*
