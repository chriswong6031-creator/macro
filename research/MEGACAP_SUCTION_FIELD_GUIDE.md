# Megacap Suction — Field Guide (MLC W3)

**Compiled:** 2026-07-16 · **Charter:** `MEGACAP_LEADERSHIP_COHERENCE_MASTERPLAN_BY_FABLE.md` §W3
**Nature:** behavioral catalog + playbook. Not a signal spec, not a scorer, not a backtest report.

---

## 1. Purpose & epistemic status

This document is the **field-guide-first** deliverable required by the `understanding-before-backtest` house law before any suction organ or ladder gains authority. It catalogs how five historical megacap-concentration episodes actually behaved — index vs equal-weight, rest-of-cohort, laggard sectors, breadth — and distills a plain-word playbook. The concentration organ and suction ladder in W3 (§6 here) are **display-tier** surfaces that derive their vocabulary and rung boundaries FROM this catalog. The promotion study **S-MLC-2** (masterplan §W6) will draw its conditioning-variable ruler FROM the §5 playbook, not the reverse.

**What this document does NOT do (house law + masterplan §4):**
- No signals, no scores, no escalations, no gates. Display/context only (MLC-R2, MLC-R8).
- No backtest verdicts. No performance statistics beyond simple descriptive return/breadth series already in the local stores.
- The word "validated" is CI-banned and never appears as a claim here. Behavioral regularities are stated as **falsifiable descriptions with per-episode tallies**, not as established laws.
- Every "tended to" carries its episode count (e.g. "4 of 5"). Where the sample is one episode, it is labeled a **single precedent**, not a pattern.

**Sample caveat that governs the whole document.** The catalog is **n = 5 named episodes** (six sub-runs), all US large-cap, four of them tech/AI, spanning 1999–2026. This is a behavioral library, not a statistical sample. Tallies like "4 of 5" describe *this library*; they are not frequencies over the population of all concentration regimes. The dot-com episode (§2.5) is deliberately included as the **contrast case** that breaks several of the modern patterns — its disagreements are the most load-bearing content here.

**Two facts the catalogs agreed on and the local store confirms:**
- NVDA 2023 anchors verified in `data/yahoo/NVDA.parquet`: Jan 3 2023 = 14.28, May 24 = 30.48, May 25 gap = 37.90 (+24.4% close-to-close, 3.8× volume), Aug 31 = 49.26; 2026 ATH close 235.47 on May 14 2026.
- Breadth (`data/breadth/breadth.parquet`) covers 1962→present; RSP (`data/yahoo/RSP.parquet`) begins **2003-05-01** (so equal-weight is unavailable for the dot-com episode — a hard gap, not an oversight); the AI/non-AI breadth split (`data/breadth/breadth_split.parquet`) begins **2025-03-18** only.

---

## 2. Episode atlas

Five episodes, each: anatomy · suction-vs-broadening verdict with dates · breadth · how it ended · sources & disputes.

### 2.1 NVDA 2023 — AI ignition (Jan–Aug 2023)

**Anatomy.** NVDA +244.9% Jan 3→Aug 31 2023 (14.28→49.26, local). Same window: QQQ +43.3%, SPY +19.2%, RSP +7.2%. Three phases: (1) pre-ignition grind Jan–May 22, NVDA +117.8% while RSP was ~flat (+1.9%); (2) the **guidance gap** — Q1 FY24 reported May 24 after close, Q2 revenue guide ~$11.0B vs ~$7.2B consensus, May 25 open +23.8% on 3.3× volume, ~$187B cap added in a session; (3) post-gap extension +30% further with a *decelerating* per-earnings reaction (+23.8% Q1 gap → +3.3% next-day on the Aug 23 Q2 beat). Character: **grind punctuated by one catalytic gap**, not a parabola from the start. NVDA started 15.6% *below* its own 200dma and crossed it 8 sessions in; ended 68% above it.

**Suction vs broadening.** *Pure suction Jan 3–May 22*: 6 of 9 sectors underperformed RSP, 4 sectors negative while NVDA tripled; SPY–RSP spread widened monotonically to +8.5pp by May 22. The **SVB crisis (Mar 8–17)** was a suction *accelerant* — regional-bank stress drove flight INTO megacap "quality," inflecting the SPY–RSP gap wider. The May 25 gap day itself broadened nothing: SPY +0.1%, RSP −1.2%, 7 of 9 non-tech sectors red. *Partial broadening May 25–Aug 31*: cyclicals (XLY +15%, XLE +13%, XLI +11%) joined; defensives (XLP +0.1%, XLU −1.7%) never did; SPY still out-ran RSP. **Regime flip ~May 31–Jun 5.**

**Breadth.** pct_above_200 finished May 22 at 54.1% — essentially no net breadth gain over 4.5 months of a massive index move (divergence #1). It cratered to 45.5% on the May 25 gap day (divergence #2 — narrowest breadth on the leader's best day). A genuine June–July broadening ran pct_above_200 44.8%→79.2%. By Aug 31 it had already retreated to 62.6% while NVDA made new highs (divergence #3), which **resolved DOWN**: Sep–Oct correction, SPY −8.1%, NVDA −18.3% (leader corrected ~2.3× the index).

**How it ended.** No blowoff. The Aug 23 muted earnings reaction signaled the market had front-loaded the guidance path. NVDA fell 18.3% into Oct 26, then recovered the whole drawdown to a new ATH by Nov 20 — institutions treated the dip as re-entry.

**Sources.** Prices/breadth locally verified. Institutional framing web-sourced: Goldman Sachs Research (June 2023) top-10-drive-all-returns + concentration warning; Aurum H1-2023 hedge-fund data (tech L/S +10.1%); RBC "Great Narrowing." NVDA's exact SPX dollar-contribution is **not** locally isolable (megacap member closes absent pre-July 2023).

### 2.2 NVDA / Mag7 2024–2026 — the long-grind regime

**Anatomy.** A multi-leg concentration run. Verified magnitudes: **Leg 1** (May 24 2023→Jul 10 2024, ~14mo) NVDA +342%, SPY +39%, XLK +55%, RSP +20%. **Leg 2** (Aug 5 2024→Feb 19 2025) NVDA +39%, SPY +19%, RSP +13%. **Tariff crash** (Feb 19–Apr 8 2025) NVDA −30.8%, SPY −18.8%, RSP −16%, QQQ −23% — broad, *not* concentrated. **Recovery** (Apr 8 2025→Jul 15 2026) NVDA +121%, XLK +103%, SPY +54%, RSP +42%. NVDA 2026 ATH close 235.47 on May 14 2026 (local); as of Jul 15 2026 NVDA −9.8% from that ATH, SPY −0.4%. Character: **grind, not parabola** — NVDA annualized vol ~53% but only 5.4% of days ≥+5%, the big up-days all earnings step-functions; 588-session run across four beats.

**Suction vs broadening.** *Leg 1 = pure suction*: bottom-5 sectors (XLP/XLU/XLRE/XLB/XLV) did 9–19% while NVDA did +342%; RSP–SPY gap = **19pp** (the suction premium). *Leg 2 = partial broadening + continued concentration*: financials/consumer-disc joined on the Nov-2024 election rotation; RSP–SPY gap narrowed to ~6pp; healthcare/energy/materials/real-estate stayed in suction. *Recovery leg = reconcentration* in megacap tech with genuine industrials/energy participation (AI-infrastructure narrative); RSP still −12pp behind SPY. **Brief broadening flip Jul 11 2024** (one CPI print): RSP +2.0%, NVDA −12.6%, QQQ −5.5% in the rotation week — the canonical suction-reversal signature — lasted ~2 weeks then megacaps resumed.

**Breadth.** The concentration fingerprint emerged Q2 2024: Mar 2024 pct_above_200 = 82.3% → Jul-10-2024 ATH = 71.4% while SPY rose ~10% (index up, breadth down). Feb-19-2025 ATH (SPY 604) carried pct_above_200 = 65.2% vs Jan-2-2024 (SPY 460) at 82.9% — market 31% higher, average stock less healthy. Jul 11 2024 rotation resolved the divergence UP for a day (pct_above_50 53.8%→65.4%) but did not stick. Tariff low Apr 8 2025 = 5.8%/18.6% (extreme destruction). Current Jul 15 2026 = 62.6%/67.5% (healthy, not euphoric). **AI/non-AI split (2025-03-18+ only):** leadership rotates every 3–6 months — Sep-2025 AI leads, Jan-2026 non-AI leads, May-2026 AI re-concentrates (spread_50 +26.6pp), Jul-2026 mixed. Neither group sustains monopoly.

**How it ended (each sub-peak differently).** Jul-2024 sub-peak: CPI-driven small-cap rotation, a *suction reversal* (RSP rose as NVDA fell). Feb-2025 sub-peak: tariff shock, a *broad* selloff (every sector fell — NOT suction). 2026 sub-peak: grind resumption, mild pullback.

**Sources.** Prices/breadth local. Web: Mag-7 ≈30% of SPX cap and ≈30% of 2022–24 SPY gains (Mellon, Russell Investments); NVDA ≈33% of SPY YTD gain June 2024 (Fortune); H1-2024 SPY +19.5% vs RSP-equivalent +4.4% (Finsyn); HF net-long Mag-7 peaked ~21% June 2024, drifted to 15.5% Jan 2025 (Resonanz) — **pros de-risked BEFORE the Jul-11 rotation, not after.**

### 2.3 AAPL 2020 — COVID melt-up (Jun–Sep 2020)

**Anatomy.** Field-guide window Jun 1→Sep 2 2020. QQQ +29.6%, XLK +30.1%, SPY +17.6%, RSP +12.3% (QQQ–RSP spread +17.3pp over 65 sessions). AAPL announced a 4:1 split Jul 30 (effective Aug 31); reached $2T cap intraday Aug 19; Sep-1 post-split closing high $134.18. Character: **PARABOLIC** — QQQ extension above 200dma ran +14.4% (Jun 1) → +33.1% (Sep 2), accelerating in the final fortnight. Suction inflected the **week of Aug 17** (split-anticipation options buying).

**Suction vs broadening (five phases).** (1) Jun 1–10 broadening, RSP leads, cyclicals front. (2) Jun 10–30 COVID-scare divergence, rotation OUT of cyclicals INTO tech. (3) Jun 30–Aug 7 broadening again — the stimulus/vaccine melt-up, breadth confirmed. (4) **Aug 7–Sep 2 suction/parabolic** — QQQ +11.5% vs RSP +4.1%, sector dispersion at episode max (std 5.6%), 6 of 18 days QQQ-up-and-RSP-down. (5) Sep 2–30 air-pocket that was **rotation not crash** — RSP outperformed QQQ by 3.5pp on the way down (classic suction unwind: leader sheds more).

**Breadth — the exception.** This episode does **NOT** show breadth-diverges-as-price-rises on the approach. pct_above_200 was *rising* into the top (67.6% Sep 1 → 72.4% Sep 2). The divergence lived at the **50dma** level (97.5% Jun 1 → 85.2% Sep 2) and in **RSP vs QQQ** (+17.3pp). NH = 113 on Sep 2 (98.7th pctile) was a **blowoff** reading, not confirmation. **Field-guide implication carried forward: for a parabolic top, RSP–QQQ spread is a better suction proxy than pct_above_200.**

**How it ended.** Single-session reversal Sep 2 (intraday $137.98 → close $127.45, −7.4% top-to-close). Twin triggers, both contemporaneous: SoftBank's ~$4B OTM megacap call position (dealer delta-hedging amplified the run, unwound on Sep 4–5 disclosure), and split-euphoria retail exhaustion (Aug-31 brokerage outages, then no fresh cohort). pct_above_50 collapsed 85.2%→55.0% in 4 sessions — abrupt.

**Sources.** ETF/breadth/NVDA local. AAPL prices web (StatMuse/CNBC, split-adjusted). SoftBank gamma: FT/WSJ Sep 4–5, SpotGamma Sep 2020 (which *disputed* the naked-long framing — likely call spreads, smaller net gamma). Split retail: Motley Fool/Vice (189k+ Robinhood AAPL buyers around split). Ives target $515→$600 on iPhone-12 "supercycle."

### 2.4 TSLA S&P-inclusion 2020–21 & META recovery 2023–24 — the two contrast runs

**TSLA inclusion (Nov 2020–Feb 2021).** Announced Nov 16 2020 (effective Dec 21), single-date rebalance requiring ~$72–94B forced passive buying; TSLA ~$408→~$900 peak Jan 8 2021 (~5 sessions post-inclusion), then −30–35% by late Feb on the reflation rotation. **Verdict: BROADENING tape, NOT suction.** RSP led SPY at *every* checkpoint (RSP +24.1% vs SPY +13.3% full window, +10.8pp) — because the Pfizer vaccine announcement (Nov 9) drove a value/cyclical broadening that dominated the mechanics: XLE +68%, XLF +35%, Russell 2000's best-ever month. TSLA sucked from **its own home sector** (XLY +8.4%, lagged despite TSLA's run) and the arb pool, but did **not** suppress the broad tape. Breadth was historically elevated and expanding (pct_above_200 peaked 93% on Dec 1, *three weeks before* inclusion), confirming throughout — no divergence at top; the rolloff was reflation exhaustion, not narrowing.

**META recovery (Feb 2023–Apr 2024).** Trough ~$88 Nov 2022 → "Year of Efficiency" pivot (Jan 2023) → Feb-1-2023 +23% single-day on $40B buyback+layoffs; best Mag-7 name of 2023 (+178%). Catalogued via XLC proxy (META closes absent from local store pre-2023-07). A **recovery/re-rating** run (a fallen leader climbing back), distinct in kind from a fresh ignition (NVDA) or a milestone melt-up (AAPL). *(The fifth catalog's META section is truncated in source material — treat META specifics as thinner-evidenced than the other episodes; see §7.)*

**Sources.** ETF/breadth local. TSLA/META prices web/public-record (both absent from local yahoo pre-2023-07). Research Affiliates "Revisiting Tesla's Addition to the S&P 500" (2021): each $100k index fund lost ~$410 to rebalance mechanics; new-inclusion names tend to underperform 12mo post.

### 2.5 Dot-com endgame 1999–2000 — the contrast case (MSFT/CSCO/tech)

**Anatomy.** Terminal acceleration of the 1990s bubble. Local anchors: Oct 1 1999 SPY 80.51/XLK 15.25/QQQ 50.79 → peaks within 3 days late Mar 2000 (XLK 24.00 & QQQ 99.33 Mar 27; SPY 96.72 Mar 24). Oct 1→Mar 27: XLK +57.3%, QQQ +95.6%, SPY +18.9%. Final leg Dec 31→Mar 27: XLK +19.7% vs SPY +3.7%. Two-phase: grinding Oct–Nov recovery, then parabolic Dec–Mar (XLK mom20 +8.9% while SPY mom20 was −4.9% on Feb 25 — a 13.9pp spread). Public record: CSCO ~$80 Mar 27 2000, briefly world's largest company ~$555B; top-5 SPX weight ~18%, top-10 ~27%, tech ~33% of SPX by mid-2000.

**Suction vs broadening.** Suction without ambiguity. Oct 1→Mar 27: XLK +57.3% while XLB −5.2%, XLU −9.9%, XLP −11.6% — money actively left defensives/materials to fund tech. **RSP unavailable (inception May 2003)** — the equal-weight rung simply cannot be computed for this episode. Estimated leader-share: tech at ~30% weight × +57.3% ≈ 17.2pp of SPY's 18.9% — roughly **91% of the index gain from tech alone**.

**Breadth — the deepest divergence in the local store.** The NYSE advance-decline line peaked **Apr 2 1998** and fell for ~23 months into the Mar-2000 top — by then 35% below its 1998 high while SPY made new ATHs. Longest sustained price/breadth divergence visible back to 1962. pct_above_200 hit **27% on Feb 25 2000** with QQQ within 10% of ATHs; new-lows ran 22–83/day *while QQQ advanced* (a clean locally-verified suction signal). BofA (public record): only ~20 stocks made new highs at the very top.

**How it ended (differs from every modern episode).** No single-day blowoff. Nasdaq Composite intraday peaked Mar 10; XLK/QQQ peaked Mar 27 — **17 days later**. Crash was gradual then accelerated on the Apr-3 MSFT DOJ antitrust ruling; XLK −23.3% by Apr 14, −52.7% by Dec 2000. **Breadth resolved DOWN and then improved AFTER the crash** (pct_above_200 45%→68% Apr–May) as money returned to bled defensives — the suction reversal.

**The top-anomaly worth freezing in memory.** Breadth *improved* Mar 10→27 (pct_above_200 to 45.3%, pct_above_50 to 66.7%, new-lows to 1) — a brief last-gasp rotation, NOT durable broadening. The lowest breadth readings **preceded** the price peak by 3–5 weeks. **Sub-35% pct_above_200 while cap-weight makes new highs did not mark the terminal top — the run had weeks left.**

**Sources.** ETF/breadth/AD-line/NVDA local. MSFT/CSCO absent pre-2023 (web/public record). Institutional practice below is documented.

---

## 3. Cross-episode patterns

Tallies are over the **five named episodes** (dot-com, NVDA-2023, NVDA/Mag7-2024-26, AAPL-2020, TSLA/META-2020-24). "Modern four" = all but dot-com.

### What repeats

- **P1 — Earnings/catalyst step-functions, not smooth acceleration, do the heavy lifting in the AI episodes. (2 of 2 NVDA episodes; partial in AAPL/META.)** NVDA's biggest days were all earnings gaps (May-25-2023 +24%, Feb-22-2024 +16%); META and TSLA each had a single defining +23%/+inclusion catalyst. Grind-between, gap-on-news.

- **P2 — The leader sheds more than the index on the way down; the suction reverses. (4 of 5.)** NVDA −18.3% vs SPY −8.1% (Sep-2023); NVDA −12.6% vs RSP +2.0% (Jul-2024 rotation week); QQQ underperformed RSP by 3.5pp in the AAPL Sep-2020 air-pocket; dot-com XLK −52.7% vs SPY far less. *Exception: the Feb-2025 tariff crash was broad (leader fell most in %, but everything fell) — a macro shock, not a suction unwind.*

- **P3 — Defensives (XLP/XLU) bleed or stagnate through the suction phase in every episode, and lead on the reversal. (5 of 5.)** Utilities/staples negative or near-zero in dot-com, NVDA-2023 phase 1, Mag7 leg 1, AAPL phase 4, and the TSLA window (XLP/XLU −1.0%/−1.9%). They are the reliable "capital left here" tell.

- **P4 — Index-up-while-breadth-down appears in the grind episodes. (3 of 5: dot-com, NVDA-2023, Mag7-2024-26.)** pct_above_200 fell or stalled while cap-weight rose (dot-com 23-month AD-line divergence; NVDA-2023 flat 54% over 4.5 months; Mag7 82%→71% into Jul-2024). This is the classic suction fingerprint — but see the anti-patterns for where it fails.

- **P5 — Passive indexing is the unintentional chase. (4 of 4 modern.)** As the leader's SPX weight rises (AAPL ~5%→7%, NVDA ~0.9%→~2.8% in 2023 then ~7–8% by 2026, TSLA forced-in at ~1.5%), every index dollar mechanically buys more of it. Documented as a structural cost (Research Affiliates: ~$410/$100k on the TSLA rebalance).

- **P6 — Pros de-risk the leader before the amateur rotation. (2 of 2 where measurable.)** HF Mag-7 net-long peaked June 2024 and fell to Jan-2025 lows *before* the Jul-2024 rotation; dot-com HFs skillfully rotated WITHIN tech near individual-name peaks rather than out. The crowd chases; the desks trim early.

### What does NOT repeat (anti-patterns — the dot-com contrast matters most)

- **A1 — "Breadth diverges before the top" is NOT universal.** The AAPL-2020 parabolic top had pct_above_200 *rising* into it (67.6→72.4%); the divergence lived at the 50dma and in RSP–QQQ. **Do not treat pct_above_200 as the one true suction gauge** — for parabolic tops it can mislead. (Fails 1 of 5 at the 200dma level.)

- **A2 — Low breadth ≠ imminent top (the dot-com lesson).** pct_above_200 hit 27% weeks *before* the Mar-2000 peak; the lowest readings led price by 3–5 weeks and the run continued to new highs. Sub-35%-while-new-highs is a *suction-is-mature* state, not a *sell-now* state. This single precedent is the strongest caution in the whole guide.

- **A3 — Concentration is NOT always suction.** The TSLA-inclusion run was a **broadening tape** (RSP led SPY throughout by 5–11pp) with a mechanically-concentrated single stock riding on top. A milestone/inclusion run inside a macro broadening (vaccine reflation) looks like concentration but does not drain the tape. **The organ must be able to say "concentrated leader, broadening market" — the two axes are independent.**

- **A4 — How it ends has no single template.** Sudden single-session reversal (AAPL Sep-2), decelerating-then-correcting grind (NVDA-2023), catalyst rotation (Mag7 Jul-2024), broad macro shock (Feb-2025 tariffs), gradual-then-antitrust-accelerated (dot-com). The end is episode-specific; a terminal-narrow **watch** state is defensible, a terminal-narrow **sell signal** is not (A2).

- **A5 — Equal-weight can't always be checked.** RSP is unavailable pre-2003 (dot-com blind on the cw/ew rung); AI/non-AI breadth split exists only from 2025-03-18. Some rungs are structurally absent for older episodes — the ladder must degrade gracefully to sector-dispersion and defensive-bleed proxies.

---

## 4. Institutional practice notes

*(Contemporaneous where dated; retrospectives labeled. All web-sourced; cited inline.)*

- **The narrowing gets flagged correctly and early — and being early is career-ending.** Dot-com: Julian Robertson closed Tiger Management late-March 2000 *at the exact peak*, short speculative tech and long value, having bled ~$7.7B to redemptions; his farewell letter called it "a Ponzi pyramid" driven by "momentum and mouse clicks" (aletteraday.substack.com). Barton Biggs (Morgan Stanley) called "the biggest bubble in the history of the world" in July 1999; clients withdrew *before* the peak (Wikipedia/WealthManagement). Correct thesis, destroyed by timing — the defining institutional hazard of a suction regime.

- **What worked historically was momentum rotation WITHIN the leader complex, not defensive rotation OUT.** Dot-com HFs increased tech from <20% to ~60% by Q3 1999, cutting individual names near their peaks but rotating into other still-rising tech (Brunnermeier-Nagel, Princeton). NVDA-2023 practitioners reached for NVDA first, then worked *down the AI supply chain* (AMD/SMCI/memory/networking) 1–3 weeks later (Benzinga contemporaneous). Rotating to laggards/value during the run underperformed in every episode (dot-com XLB/XLP/XLU all fell; AAPL-2020 laggard-rotators sat in underperformance until the Nov-2020 vaccine).

- **Passive flow is the invisible amplifier.** Jan-2000: 30% of all mutual-fund net inflows went to science/tech funds vs 8.7% to S&P index funds — retail momentum at an extreme at the *start* of the final three months. Research Affiliates quantified the TSLA-inclusion rebalance drag. Nobody framed it as a signal in real time; it is a mechanical tailwind that compounds the suction.

- **Concentration-risk warnings are a coincident-to-early context read, not a timing tool.** Goldman (June 2023) warned on top-10 dominance *as the run accelerated*; RBC's "Great Narrowing" documented cumulative concentration beyond dot-com levels. These framed the regime correctly but carried no edge on *when* it turns — consistent with A2.

- **The practitioner dilemma to encode in the glance tier:** join the momentum (short-term career-safe, catastrophic at the top) vs stand aside (right in retrospect, career-threatening during the run). The honest stance for most of a suction run is **"watch — don't chase,"** which is exactly the DESIGN_DOCTRINE glance-tier vocabulary the W3 tile must speak (MLC-R9).

---

## 5. Playbook — per-regime behavior

Four regimes distilled from the atlas. Each row: **observable markers** (things the W3 ladder + breadth read can show today) · **what historically followed** (with tally) · **stance** (plain words; vocabulary: *Act / Get ready / Watch — don't chase / Protect gains / Stand aside*). Stances are display guidance for a human reading the ladder — **not** auto-signals (MLC-R2/R8).

| Regime | Observable markers | What historically followed (tally) | Trader stance |
|---|---|---|---|
| **Suction-grind** | Leader trends up on earnings step-functions; cw–ew spread widening (RSP lagging SPY by a widening margin); defensives (XLP/XLU) flat-to-negative; pct_above_200 flat/falling while index rises; NO parabolic extension | Run continued for weeks–months in every grind case (dot-com Dec-99→Mar-00; NVDA-2023 Jan→May; Mag7 leg-1 14mo). Breadth-down-while-index-up did NOT time the top (4 of 4 grind cases). Leader corrects harder when it does turn (P2). | **Watch — don't chase.** Own the leader if already in; don't add on strength. Do NOT rotate to laggards yet (they bled in 5 of 5). Do NOT short on breadth divergence alone (A2). |
| **Suction-parabolic** | Extension above 200dma accelerating into a blowoff (AAPL QQQ +14%→+33%; dot-com XLK mom20 far above SPX); sector dispersion at highs; RSP–QQQ spread the cleaner gauge than pct_above_200 (A1); a single identifiable marginal-buyer cohort (retail/options/split/gamma) | Terminal reversal was **sudden and cohort-exhaustion driven** (AAPL single session; dot-com then antitrust). The tell was velocity + disappearing buyer cohort, NOT breadth (1 of 1 parabolic top had rising pct_above_200). | **Protect gains.** Tighten on the leader; a parabolic top gives little warning. **Get ready** to stand aside. Still not a laggard-rotation cue — that paid only after the top. |
| **Broadening-run** | RSP leading or matching SPY; laggard sectors (energy/financials/industrials) participating; breadth expanding (pct_above_200 rising with price); often a macro catalyst (vaccine, election, CPI) | Broadenings were **real but often brief inside a concentration era** (NVDA-2023 Jun–Jul; Mag7 Jul-2024 ~2wk; Leg-2 election ~4–6wk) OR a genuine macro rotation (TSLA/vaccine window, months). Leader underperformed during the flip (P2). | **Act** on the broadening while it holds — laggard/equal-weight participation is confirmed here, not hoped-for. But **watch** for reversion to megacap leadership; brief flips resumed suction (2 of 3). |
| **Terminal-narrow** | Extreme narrowness (pct_above_200 <35%, or AD-line multi-month divergence) WHILE cap-weight near ATHs; new-lows rising as index rises; single-digit new-highs at the very top | Ran **weeks longer** than the narrowness suggested (dot-com 27% breadth 3–5wk before peak). Resolved DOWN eventually (dot-com, NVDA-2023 Aug). Breadth improved AFTER the crash as defensives led (suction reversal). | **Watch — don't chase**, shading to **Protect gains.** This is a *mature-suction* state, not a sell trigger (A2). **Stand aside** from fresh laggard-bounce entries — S-MLC-2 will test exactly this (masterplan §W6). |

**5 load-bearing rows** (the ones a trader watching the ladder relies on):
1. **Suction-grind → "Watch — don't chase; don't rotate to laggards yet"** (defensives bled in 5/5; breadth-down didn't time tops in 4/4 grinds).
2. **Terminal-narrow → "mature state, NOT a sell trigger"** (dot-com single precedent: 27% breadth 3–5 weeks early — the strongest caution in the guide).
3. **Broadening-run → "Act while it holds, but watch for reversion"** (brief flips resumed suction 2/3; only vaccine-scale macro made it durable).
4. **Suction-parabolic → "Protect gains; tell is velocity + vanishing buyer cohort, not breadth"** (AAPL: pct_above_200 rose into the top).
5. **Concentration ≠ suction (cross-cutting) → the ladder must separate "concentrated leader" from "draining tape"** (TSLA: RSP led SPY the whole run).

---

## 6. W3 organ design implications

Which concentration series earn a **display row** (display-tier, nulls printed; MLC-R1 routes any new pair through the Ratio Lens registry).

**Series that earn a row (and local-store status):**

| Series | Earns a row because | Computable now? |
|---|---|---|
| NVDA share of SPX market cap | P5 (passive-chase amplifier); the operator's core beast | **Needs accrual** — SPX cap weights not in local store; requires member-cap feed. Price+shares proxy possible. |
| Mag7 share of SPX market cap | Cohort concentration level (§4 ≈30%) | **Needs accrual** — same. |
| cw/ew suction ladder: NVDA vs Mag7-ex-NVDA vs SPX-ex-Mag7 vs RSP | The primary suction gauge; separates leader / cohort / rest / equal-weight (A3 demands the leader-vs-tape split) | **Partial now:** SPY, RSP, QQQ, XLK computable from `data/yahoo/` back to 2003 (RSP) / 1998 (XLK). Individual megacaps only from **2023-07-03** — Mag7-ex-NVDA and SPX-ex-Mag7 rungs need pre-2023 member closes to accrue for history; go-forward is clean. |
| RSP–SPY (cw/ew) spread | Cleanest single suction proxy in modern episodes | **Now** — both local; RSP from 2003-05-01. |
| RSP–QQQ spread | The *better* gauge for parabolic tops (A1, AAPL lesson) | **Now** — both local. |
| breadth-under-rally divergence (pct_above_200 & pct_above_50 vs index) | P4 fingerprint; the 50dma view matters for parabolas (A1) | **Now** — `data/breadth/breadth.parquet`, 1962→present. |
| AD-line vs index divergence | Dot-com's 23-month tell; longest-range breadth context | **Now** — `ad_line` column present, deep history. |
| defensive-bleed read (XLP/XLU vs SPY) | P3, the 5/5 "capital left here" tell; degrades gracefully when RSP absent (A5) | **Now** — sector ETFs local. |
| AI vs non-AI breadth split (consume VSB) | Modern intra-tech rotation (Mag7-2024-26 finding) | **Now but shallow** — `data/breadth/breadth_split.parquet` starts **2025-03-18** only; label as recent-accrual. |

**Proposed ladder-state discretization `[FREEZE-REVIEW]`** (this is the S-MLC-2 conditioning variable — the prereg adjudicator must freeze these boundaries before any study reads them; boundaries below are *proposals from this catalog*, not fitted):

`[FREEZE-REVIEW-1]` **Four ladder states**, mapped to §5 regimes:
- **suction-grind** — RSP–SPY spread widening over a trailing window AND defensives (XLP/XLU) not leading AND leader/cohort extension not parabolic.
- **suction-parabolic** — leader extension above 200dma accelerating past a high threshold AND sector dispersion elevated (RSP–QQQ spread as the primary gauge, per A1).
- **broadening-run** — RSP leading or matching SPY AND breadth (pct_above_200) rising with price.
- **terminal-narrow** — pct_above_200 below a low threshold (dot-com touched 27%; propose a **watch band, not a trigger**, per A2) WHILE cap-weight within X% of ATH.

`[FREEZE-REVIEW-2]` **The "concentration ≠ suction" two-axis requirement.** Discretization MUST carry an independent *leader-concentration* axis (is a single name/cohort dominant?) separate from the *tape* axis (is equal-weight lagging?). TSLA-2020 (A3) is concentrated-AND-broadening; collapsing to one axis would mislabel it. S-MLC-2's conditioning must respect both.

`[FREEZE-REVIEW-3]` **Threshold provenance.** All numeric cut-points (spread-widening window, extension threshold, pct_above_200 bands, ATH proximity) are **unfitted proposals** here. The prereg adjudicator sets and freezes them BEFORE S-MLC-2 conditions on the state — otherwise the conditioning variable is fitted-in-sample and the study is compromised.

`[FREEZE-REVIEW-4]` **Terminal-narrow is a WATCH state, never a sell state** (A2 — dot-com single precedent, ran 3–5 weeks past the narrowest breadth). If any later promotion tries to make terminal-narrow gate or escalate, it violates this field guide's central caution and MLC-R8.

**PIT ledger columns (masterplan §W3):** all rows above get PIT columns from day one so S-MLC-1/2/3 have honest history. A null on any as a standalone signal is **retained as confluence context** (house law), not deleted.

**Consume, don't rebuild (MLC-R1):** breadth from `data/breadth/`, AI-split from VSB, cohort state from `data/mag7_regime/`, RS from `data/rs_series/`; new ratio rungs registered through the Ratio Lens registry, not a parallel implementation.

---

## 7. Data honesty appendix

Per-series local coverage (verified this session against the stores):

| Series / store | Coverage | Gap / caveat |
|---|---|---|
| `data/yahoo/NVDA.parquet` | 1999-01-22 → 2026-07-15 (6,911 rows) | Full history; all 2023/2026 anchor prices in the catalogs verified against it. |
| `data/yahoo/{SPY,QQQ,XLK}.parquet` | SPY 1993, QQQ & XLK 1998–99 → present | Deep; covers all five episodes. |
| `data/yahoo/RSP.parquet` | **2003-05-01** → present | **Equal-weight unavailable for dot-com (A5).** cw/ew ladder is blind pre-2003. |
| `data/yahoo/{AAPL,MSFT,AMZN,GOOGL,META,TSLA}.parquet` | **2023-07-03** → present (761 rows each) | **Individual megacaps absent pre-2023-07.** AAPL-2020, TSLA-2020, dot-com MSFT/CSCO, NVDA-2023 cohort context all rely on web/public-record prices — flagged inline in §2. Mag7-ex-NVDA and SPX-ex-Mag7 ladder rungs cannot be historically reconstructed from local data; go-forward accrual is clean. |
| `data/yahoo/` sector ETFs (XLK/XLY/XLF/XLE/XLI/XLB/XLV/XLP/XLU/XLC/XLRE) | Present, deep | Sector-level suction and defensive-bleed reads computable for all episodes (the graceful-degradation path when RSP/members absent). |
| `data/breadth/breadth.parquet` | 1962-03-13 → present | pct_above_50, pct_above_200, nh, nl, adv, dec, ad_line all present. NVDA-2023 catalog notes NH/NL provider gap after 2023-07-19 — pct_50/pct_200 remain valid. |
| `data/breadth/breadth_split.parquet` (AI vs non-AI) | **2025-03-18** → present | Recent-accrual only; the "AI/non-AI rotates every 3–6 months" finding rests on ~16 months. Label as thin. |
| `data/mag7_regime/latest.json` + `ledger.jsonl` | present | Cohort state to consume (MLC-R1); not re-derived here. |
| `data/oracle/`, `data/rs_series/` | present | Consumed as context per masterplan §2; not rebuilt. |
| SPX/Mag7 **market-cap weights** | **Absent** | No member-cap feed locally; NVDA-share and Mag7-share rows in §6 are **accrual-pending** (price×shares proxy possible but not yet built). |

**Cross-catalog consistency check (flagged, not silently resolved):**
- NVDA-2023 and Mag7-2024-26 catalogs report the **May 25 2023 gap** as +23.8% and +24.4% respectively (close-to-close vs a different reference). Local close-to-close (30.48→37.90) = **+24.4%**; the +23.8% figure is a gap-open reference. Not a contradiction — different anchors — but noted.
- NVDA SPX weight in 2023 is given as "~0.9%→~2.8%" (NVDA-2023 catalog, price-derived estimate) and reaches "~7–8% by 2026" (Mag7 catalog, web). Both are **estimates**, not locally computed (no cap feed) — treated as approximate throughout.
- The META recovery sub-episode (§2.4) is **truncated in the source catalog**; its post-Feb-2023 leg detail is incomplete. META specifics carry lower evidential weight than the other four episodes and should not anchor any playbook row on their own.
- AAPL "breadth rose into the parabolic top" (catalog-3) vs the general P4 "breadth falls under rally" is a **genuine behavioral disagreement across episodes**, surfaced deliberately as anti-pattern A1 — not reconciled away.
