# Group Reads — §7 competitive + production-quality audit (2026-08-10)

**What this is.** The post-build audit `research/GROUP_READS_MASTERPLAN_BY_FABLE.md` §7 deferred to audit time: "does this beat Jodie/Struct/Quartr/EarningsCall.ai/EquityDesk *individually*", graded on the operator's six axes. The build-out it waited on shipped and live-verified 2026-08-10 (`research/GROUP_READS_SESSION3_HANDOFF_2026-08-10.md`). Evidence: fresh competitor recon walks (2026-08-10) + a production-quality audit of our shipped surfaces against the masterplan §0 gates.

**Audit tree:** `25fd99482d5613a074dea777c419cba46079c812` (2026-08-10). Findings and
line references describe that immutable production snapshot; later heals must close them with
their own proof rather than silently making this historical audit read as a current census.

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
### B2 Struct (struct.news, walked 2026-08-10)

**Identification:** Struct is the public editorial companion to Jodie, not a separate
portfolio product. Its own masthead says "Powered by jodie.ai" and "Filing reads, what moved
together, and the receipts behind it"; every story links back to company analysis on Jodie.
The public navigation is Latest / Filing Reads / Moving Together / Filing Trends / Supply
Chain / Daily Radar, with RSS and an archive. Source: [Struct](https://struct.news/).

**Core job:** short, evidence-led company briefs that explain one filing or one observed move.
The live front page held hundreds of filing reads and explicitly positioned the division of
labor: "Struct explains the story once. Jodie keeps watching what changes next." It is a
free public reading surface; monitoring converts to Jodie. It does not maintain a separate
group membership system, group state, earnings rollup, coverage floor, or persistent group
read. Struct therefore is useful evidence packaging and distribution, but not a home-turf
Group Reads competitor. Public pages were English-only in this walk.

### B3 Quartr (Quartr Pro + mobile + API, walked 2026-08-10)

**Core job:** institutional-grade qualitative company research over first-party IR material.
Quartr Pro joins live calls, transcripts, slides, filings, AI chat, source traceability,
historical slide comparison, event calendar, alerts, summaries, and export across 15,000+
companies and 65+ markets. Pro/API pricing is contact-sales; the mobile product remains free.
Sources: [Quartr Pro](https://quartr.com/products/quartr-pro),
[pricing/features](https://quartr.com/pricing/overview), and
[company/coverage](https://quartr.com/about).

**Group capability — real, but user-assembled.** Multiple watchlists can represent a sector,
theme, portfolio, or peer group and feed AI chat/search/calendar; users can add or remove
members. Quartr also supports peer-language and narrative-change work across years of IR
material. Sources: [watchlists](https://quartr.com/features/watchlists) and
[slide search](https://quartr.com/features/slide-search). That is materially deeper than our
source-document layer and can answer ad-hoc cross-company questions. It is not a maintained
PIT basket state product: the public product contract does not show a persistent group stance,
participation/washout arc, numeric coverage floors, sympathy ledger, or bilingual group band.

**Honest competitive read:** Quartr wins its home turf decisively — live global IR coverage,
company narrative history, source-traceable qualitative search, and peer interrogation. We
win a narrower job it does not present: an always-on, preassembled group state with explicit
market/earnings denominators and EN/ZH refusal semantics. No Chinese-language product surface
was found in the official public product/pricing/feature pages; that is a public-surface
observation, not a claim about private enterprise localization.
### B4 EarningsCall.ai (earningscall.ai, walked 2026-08-10)

**Identification note:** distinct from EarningsCall LLC / earningscall.io/.biz (a transcript/audio data-API vendor, 5,256 companies) — secondary sources blend the two; coverage counts for the .ai product are unverified.

**Core job:** AI earnings-call summarization for individuals — "save hours reading transcripts." Single tier **$25/mo** (7-day trial; annual toggle "24% off", amount unrendered). Features: AI summaries, tweet-style digests, chat over earnings data, "Guidance & Q&A Insights," sentiment/tone detection, **peer benchmarking capped at 4 manually-picked companies**, watchlist alerts, earnings calendar, Weekly Intelligence + Tariff Impact Tracker (nav items; content login-gated, unverified).

**Absences (per public pages):** no basket/theme construction (peer compare is ad hoc, max 4); no co-movement; no group-grain rollup of any kind; no surprise-vs-consensus tracking found; no estimate revisions; no cycle/arc state; no read-through/counterparty logic; no zh (NOT FOUND — app screens unauditable anonymously).

### B5 EquityDesk (equitydesk.ai — identification MEDIUM-HIGH, plausible but uncorroborated by third parties)

**Identification note:** best category match ("Where technicals and fundamentals converge"; solo founder, ex-CIO/Partner at HQAM). Name collides with unrelated entities (India's "The Equity Desk" blog etc.). No independent press/reviews found.

**Core job:** per-stock swing screen marrying **Weinstein 4-stage analysis** (US/EU/Asia markets) with LLM earnings-call scoring on two axes (Performance = beat/growth magnitude; Sentiment = raising vs walking back outlook), plus industry relative strength, alt-data (Google Trends/TikTok/Reddit/Wikipedia), and slide decks for 3,000+ companies. Flagship "Fundamental Stage 2" screen (early Stage 2 + quality ≥85 + call-sentiment ≥24 + call-performance ≥6) with a **published backtest** (~61% hit rate, ~7.0% mean excess/trade, ~8-week hold) and a mechanical exit rule. Single tier **$25/mo**.

**Epistemically notable:** their white paper discloses what they tested and REMOVED (RS quality gate, breakout patterns, industry-strength filtering — "flattened completely", volatility thrusts) and self-flags the commodity-sector blind spot. Credible-honest for a signal vendor — but they are a signal vendor: the product's center is an authority claim (a screen with a hit rate), the opposite of our display-tier read discipline.

**Absences (vendor-confirmed in their own white paper):** "Stock Baskets or Thematic Grouping: **Not offered**. The screen produces individual stock candidates, not grouped themes or basket strategies." No co-movement, no group earnings rollup, no supply-chain/read-through (self-disclosed), no episode ledger at group grain (stock-level entry/exit rules only), no zh. Their cycle state is real but **per-stock price-technical** — not basket-grain, no washout/capitulation construct, no participation trajectory.

## §C Our shipped quality (production audit vs §0 gates, 2026-08-10, opus reviewer over committed bytes)

### C1 Gate grid

| Gate | Verdict | One-line evidence |
|---|---|---|
| G0-1 contract validity | **GAP** | Validators+golden+mutant tests real for all 3 artifacts; but `participation.breadth_divergence` (§4.1) never shipped, `sympathy.n_reporters` ships un-contracted, and `episodes.json` carries no `schema`/`authority`/`generated_at` envelope |
| G0-2 no fused score | **GAP** | Artifact clean (tripwire real, `tests/test_group_pulse_tripwire.py`); but the disclosed ordering rule prints only on boards `pulse.json` doesn't cover — the US board (`templates/sector_central.html.j2:2604-2662`) implements the identical sort with the rule only as a code comment (F-1) |
| G0-3 display tier / honest nulls | **PASS** | `authority:"context_only"` 49/49 ×3 artifacts; Oracle P8 verbatim in Tier-2 (`templates/basket_detail.html.j2:717-718`); no banned vocab rendered |
| G0-4 nightly sole advancer | **PASS** | Replay-determinism tests in all three ledgers |
| G0-5 CI registration | **PASS** | 4 jobs, 7 test files, 0 dark |
| G0-6 render budget | NOT-CHECKABLE from tree (instrumented; PR-body measurement not in-branch) |
| G0-7 surfaces | **GAP** | Graceful absence exemplary; banned vocab clean; but a units error ships bilingually (F-2) |
| G0-9 bilingual | **PASS** | 94 `L()` calls, 0 EN-only, 0 `title=` in the GR1 region, `name_zh` 49/49 |
| G0-10 coverage floors | **FAIL** | Floors gate only `arc.state`; every other leg computes and publishes over survivors (F-3) |

### C2 The seven load-bearing findings

- **F-1 (MAJOR)** — ordering rule unreachable on the only board it orders: `baskets_desk.js:371-386` prints it into boards with no US ids (`grPulseCovers()` false → blank); the US board's own fork (`sector_central.html.j2:2619-2631`) keeps the rule as a comment. Also `site/baskets.html` is a dead 5.5KB non-nav page — masterplan §5's "upgrade baskets.html.j2" named a board that is no longer the live US board.
- **F-2 (MAJOR, correctness)** — `capitulation_median_age_d` is TRADING SESSIONS by contract (`engine/group_pulse.py:125-126`); `basket_detail.html.j2:736` renders "days"/"天" in both languages — understates elapsed time ~40% on every page. No test pins the unit.
- **F-3 (MAJOR, G0-10 FAIL)** — `_arc_state()` refuses below floor but `_arc()` publishes every leg anyway: both floor-failing baskets print "too few members to read this group" and a full numeric read beneath it. `agreement_pct` has no floor and no own-N — median active-denominator is **2**; 29/49 baskets print exactly 1.00; the US board sorts on it raw. Six shares ship without published denominators; `reclaimed_20d_share` has a docstring/code denominator divergence.
- **F-4 (MAJOR, correctness)** — artifact vs band washout arithmetic disagrees on 5 baskets (denominator readable-members vs `n_covered`): `space_economy` state decided on 0.9091, page prints "10 of 14" ⇒ 0.71. The true denominator isn't in the artifact, so the surface cannot render correctly.
- **F-5 (MAJOR, measurement validity)** — arc does not discriminate: `turning` 39/49; `washout_in_progress` and `distributing` fired 0 times; 11/49 ages sit at the 91-bar censoring boundary (8 of them read `turning`); and the computed arc is **never consumed by the stance matrix** (`:616` computes, no rule branches). The axis §1 calls "Jodie's biggest hole" currently reads as one word repeated 39 times over troughs a quarter old.
- **F-6 (MAJOR)** — episodes: 255/490 rows (52%) are single-day episodes rendered as "N of N stayed active throughout"; history to 2025-01-02 runs over rosters whose `added` is back-projected for 95% of members (self-documented `data/baskets/membership.json:8957-8958`) with **no on-surface disclosure**; exactly-10-rows cap undisclosed; 5 of §4.2's 11 columns missing from the projection; open episodes invisible.
- **F-7 (MAJOR)** — `linked_outsiders.json` has **no consumer** — zero fetch sites in templates/site. Engine clean, honesty ruling holds (no inferred Customer/Supplier labels, pinned by test); yield near-zero as predicted (`n_confirming`=0 on 49/49). Also stamps `as_of` 08-10 while pulse/earnings stamp 08-07.

### C3 What is genuinely at/above the bar (confirmed, not padding)

Graceful absence (distinct plain-word nulls per section; "file absent" distinguished from "empty list"); slug→plain-word translation with bilingual fallbacks; floors honest **in copy** (`n_no_data` "counted, never divided away"; beat counts withheld below n_reported≥4 on 18/49; sympathy always prints its Ns); stance-matrix architecture (first-match ladder, coverage refusal rung 1, enumerable by tests); membership hygiene (0 same-basket dupes, 0 preferred/warrant tickers in 1,038 entries, 2 dead tickers correctly stamped `delisted_before_curation`, 3 dual-class pairs confined to one basket — **materially cleaner than the Jodie profile in B1**); real mutant/tripwire batteries. Minor ledger: three inconsistent agreement thresholds (F-9a); regex-sniffing builder prose for the refusal note (F-9b); board chip inert on 92% of cards (`state_change` quiet 45/49, F-9c); one `active_now:false` row with a `current_start` (F-9d); sympathy ratio (median 1.13×) ships with no dispersion estimate (F-9e); guidance band null 47/49 — the leg effectively doesn't exist yet (F-9f); masterplan says 48 baskets, file holds 49 (F-9g); `breadth_divergence` never lit (F-9h); **0/41 new stats have `docs/site_semantics/` glossary rows** (CXI law debt).

## §D Verdict matrix

Grades are **us vs them** on each rubric dimension (BEAT = we are materially better / PARITY / BEHIND / N/A = they don't play the axis). Per-competitor verdicts below the grid answer the operator's question in two parts: home turf, then moats.

| Dim | vs Jodie.ai | vs Struct | vs Quartr | vs EarningsCall.ai | vs EquityDesk |
|---|---|---|---|---|---|
| R1 read assembly | **PARITY today** (both genuinely assemble; their episode display is currently more credible than our 52%-degenerate rows, our stance/null architecture is stronger than their 0%-agreement groups; our F-2/F-4 correctness bugs are the blockers to BEAT) | **BEAT at group grain** (Struct assembles concise company/file reads, not a persistent group stance) | **PARITY, different grain** (Quartr assembles source-traceable company/peer research on demand; we preassemble a narrower persistent group read) | **BEAT at group grain** (per-call summaries assemble nothing across companies) | **BEAT at group grain** (a screen card with two scores is not an assembled read) |
| R2 membership hygiene | **BEAT** (§C: 0 dupes / 0 preferred / dead tickers stamped, vs their live zero-industrials "Industrials" group and "not yet clean" concession; our PIT back-projection debt noted — a claim they don't even attempt) | **N/A** (no separate maintained groups) | **N/A** (user-curated watchlists/peer sets, not a maintained PIT basket claim) | **BEAT** (no baskets at all — ad hoc 4-peer compare vs our 49 curated baskets) | **BEAT** (vendor-confirmed "not offered") |
| R3 arc answers | **BEAT on design / GAP as shipped** (their lifecycle tags answer "is co-movement building or fading", never "is the washout done"; our construct answers the reversal question — but F-5: 39/49 print the same word, censored ages published as observations, arc unwired from stance. The moat claim is not yet earned on the tape) | **BEAT** (no persistent group lifecycle) | **BEAT at market arc** (Quartr tracks narrative/KPI emphasis changes, not price washout/capitulation state) | **BEAT** (absent) | **BEAT at group grain** (their Weinstein stages are real but per-stock; we ship the same framework as basket stage-shares PLUS washout/turn constructs they lack; N/A at their per-stock grain — we don't sell a per-stock entry screen and don't want to) |
| R4 earnings integration | **BEAT** (verified absent in their core product; struct.news briefs are per-company and never surface on group pages — see B2; our clock/beat/sympathy is the only group-grain earnings read between us, with yield caveats F-9e/f) | **BEAT at group grain** (filing/earnings briefs are company stories, with no group clock or rollup) | **BEHIND on qualitative depth; BEAT on persistent group pulse** (Quartr's live calls, transcripts, first-party history, and peer queries are substantially deeper; it does not publish our fixed basket clock/beat/sympathy state) | **BEAT at group grain** (they summarize single calls well — no rollup, no surprise-vs-consensus found; our earnings_pulse joins clock/beat/sympathy to the basket read) | **BEAT at group grain** (two-axis per-call LLM scores feed a stock screen, vendor-confirmed no group rollup) |
| R5 honest nulls | **BEAT** (G0-3 PASS is our strongest dimension: printed Ns, refusal copy, P8 disclosure — vs their marketing-tier validation stats; their "not yet clean" concessions are real honesty, credited — and our F-3 enforcement gap is the asterisk we must clear) | **BEAT at group grain** (underlying receipts are credited; no group denominator/floor contract exists) | **PARITY, different controls** (Quartr's first-party/page-level traceability is stronger source provenance; our explicit denominators/floors/refusals are stronger state-null controls) | **BEAT** (no coverage/floor concept anywhere) | **BEAT at surface tier, with respect** (their methodology paper honestly discloses removed features and blind spots — but the product's face is an authority claim, a hit-rate screen; ours prints n_covered and refuses thin baskets at the surface itself) |
| R6 bilingual reach | **BEAT** (zh verified absent there; our band is 0 EN-only across 94 strings) | **BEAT on public surface** (Struct walk was English-only) | **BEAT on public surface** (no zh product surface found; private localization unverified) | **BEAT** (NOT FOUND any zh) | **BEAT** (NOT FOUND any zh; their "Asian markets" is listing coverage, not language) |

**vs Jodie.ai (the direct rival):** home turf = market-discovered co-movement radar with filing receipts, $29/mo. Graded: we beat them on membership hygiene, group-grain earnings, surface-tier null discipline, and zh; parity on assembled-read quality today; arc is beat-on-design but degenerate as shipped (F-5) — the §1 claim "we exceed once assembled" is TRUE on architecture and NOT YET on the tape. Two capability edges of theirs we deliberately don't contest: **live-forming detection + alerts at 15-min refresh** (our cadence is nightly by render-budget law — real edge for their rotation-chaser persona, a positioning choice for us, and their numbered-Cluster substrate suggests discovery breadth we don't attempt) and **auto-discovery of novel groupings** (our theme_discovery generates candidates but curated-first is the hygiene trade we chose — it is WHY we win R2). **Answer to the operator: not yet, honestly — pending F-2/F-3/F-4/F-5/F-6 heals we are at parity-plus with a stronger foundation; after them, yes on every axis except intraday cadence, which we concede by design.**

**vs Struct:** home turf = public, concise, receipt-linked company/file stories that route
monitoring back to Jodie. That distribution/editorial job is useful and we do not ship an
equivalent publication stream. It is not a group-state product: no maintained roster, arc,
earnings rollup, coverage gate, or bilingual band. **Verdict: orthogonal editorial front end;
we beat it on every actual group-state axis, while conceding its public narrative-distribution
job by design.**

**vs Quartr:** home turf = global, source-traceable qualitative IR research with live events,
AI chat, peer/watchlist queries, and document history. **We do not beat that product and should
not pretend to:** its company/peer qualitative depth and timeliness are materially ahead. Our
different moat is a preassembled, persistent group-state object with market/earnings
denominators, refusal semantics, and EN/ZH delivery. **Verdict: Quartr wins qualitative IR;
we win the narrower ongoing group-state read it does not publicly offer. They are complements,
not substitutes.**

**vs EarningsCall.ai:** home turf = single-call consumption (summary, chat, tone). We do not compete there — our earnings layer is structured figures + group rollup, not a call reader; a user who wants "summarize this call and let me chat with it" is buying a different job ($25/mo). Their turf does not touch ours: no baskets, no co-movement, no group anything, no cycle state, no zh. **Verdict: orthogonal home turf we concede by design; every group-grain axis is ours uncontested.**

**vs EquityDesk:** home turf = a per-stock swing screen with published backtest authority. We deliberately do not sell that job (display-tier law; DNR:KILL-PSS-SR3-PARTICIPATION forbids participation-as-timing). The overlap is the Weinstein framework — theirs per-stock as an entry gate, ours as basket stage-share description — and per-call LLM reads — theirs originating scores that gate a screen, ours de-escalate-only over structured figures. **Verdict: we beat them on every group-grain axis (all vendor-confirmed absent); their authority-tier screen is a job we refuse on epistemic law, not a capability gap — the audit records it as a positioning difference, not a BEHIND.**

## §E Gaps → waves (re-prioritized: correctness before expansion)

The audit reorders the backlog. The previously planned sequence (GR4 → GR0.1 → GR3-2) assumed the shipped substance was sound; §C shows the credibility risk is in what is already live. **CN/HK twins are explicitly deferred until W-A/W-B/W-C land — replicating F-2..F-6 into two more regions would triple the debt.**

- **W-A — correctness heals (small, ship first).** F-2 units fix ("days"/"天" → sessions wording, both languages, + a test pinning the unit word); F-9d builder guard (null `current_start` when `active_now` false); F-1 quick half (print the ordering rule on the US board — the surface that actually orders); as_of stamp unification (F-7 tail).
- **W-B — G0-10 enforcement (the FAIL).** Publish per-share denominators in `pulse.json` (additive v1.0.1 keys — fixes F-4's impossible-to-render-correctly problem at the root); suppress numeric tiles under `insufficient_coverage` (refusal means refusal); give `agreement_pct` a floor + own-N in the artifact and make the US board sort respect it.
- **W-C — arc re-cut (the moat claim depends on it, F-5).** Publish censoring honestly (`age_censored` flag, never 90-as-observation); re-cut ladder thresholds against the observed distribution (washed_out_share median 0.875 makes the current ≥0.5 rungs fire unconditionally); wire arc into the stance matrix. Measurement-lens protocol applies: distribution study → thresholds chosen and written down → then the display flip. Display-tier, so no gauntlet — but the re-cut doc is mandatory.
- **W-D — episode credibility (F-6).** Floor or honestly label single-day episodes; disclose back-projection and the 10-row cap on-surface; add the missing §4.2 columns (`members_persisted` first — the stat currently ships without its N); render open episodes.
- **W-E — light the dark leg (F-7 + GR1.2).** Fetch + render `linked_outsiders.json` as the fourth-axis tile: at today's yield (`n_confirming` 0/49) the honest render is a null tile with plain-word copy — which is itself a read, and completes the four-axis promise vs Jodie's outside-confirmation axis. Dispose of the dead `site/baskets.html` (redirect or retire; fix the stale §5 naming).
- **W-F — GR4 (after the heals).** `docs/site_semantics/` rows for all 41 new stats (CXI debt, 0/41); Turn Desk folding (DNR:KILL-ROTATION-SCHEDULE — no parallel surface); CN/HK twins LAST.
- **Queued behind:** GR0.1 `members[]` v1.1 (member-table parity — R1 upgrade vs Jodie's per-member consistency display, worth doing with W-D since both touch episode/member rendering); GR3 phase-2 (FTS phrase dictionary, alias map, GOOGL/GOOG `ambiguous_tie`, `contract_dollar_z` aggregate-grab fix) — yield work that makes W-E's tile progressively non-null.
- **Minors ledger (fold into whichever wave touches the file):** F-9a threshold unification, F-9b regex-sniff → structured refusal key, F-9c chip inertness (re-cut with W-C), F-9e sympathy dispersion estimate, F-9f guidance-leg collector thinness (18-row debt, pre-existing), F-9g masterplan 48→49 count, F-9h `breadth_divergence` disposition (light it or strike it from §4.1).
