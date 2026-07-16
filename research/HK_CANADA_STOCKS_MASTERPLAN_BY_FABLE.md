# HK & Canada Stock + Basket Engines — Fix Masterplan (by Fable) · v2

**Program goal (owner's words):** a dashboard full of incredible stock picks that are ripe for the picking — names about to run, at great entries, surfaced by sector rotation/leadership + confluence gating + market-native signals.
**Scope:** `hk_stocks.html` · `baskets_hk.html` · `canada_stocks.html` · `baskets_canada.html` (+ engines/collectors).
**Lineage:** Problem audit #1033 → Phase-A 9-agent deep-read → masterplan v1 → **5-critic adversarial red-team (12 fatal / 26 major findings, several verified by direct fetch or in-tree replication)** → this v2.
**Author:** Fable · 2026-07-03. Execution delegated to Opus/Sonnet waves.

---

## 0. Executive thesis

**What the evidence killed (do not build):** HK residual momentum (no tradable edge on the live 157-name deep panel: mom_res LS Sharpe +0.17 full / +0.31 modern, fails DSR, IC≈0, 447 rebalances — the original −0.22/−0.35 pin was the pre-2026-06-18 73-name panel; the expansion sign-flipped a near-zero Sharpe, not the verdict) · COILED cohort-washout on HK (refuted waves 3+6) · southbound flow-vs-price divergence (NO-GO) · HK short-term reversal on the *large-cap* panel (rev_st already failed FDR: t_HAC 1.52 full / 0.49 modern, DSR 0.07–0.18) · US→TSX t+1 sector lead (red-team replication: residual +0.11/−0.06/+0.11, sign-inconsistent) · commodity→miner "catch-up lag" at the name level (red-team replication: miners are ~96% contemporaneous with their metal; t+1 residual *negative*) · cross-sectional commodity momentum (refuted in-house) · timing constructs as board order (house truth: negative forward-IC).

**What survives and what's new:** the red-team *vindicated* the Canada commodity→sector transmission tier (XEG +1.4–2.2% / XGD +2.7–3.4% excess post regime-turn, t≈2.0–2.8 on 43–50 debounced episodes — pending episode-honest statistics), and surfaced four mechanisms v1 missed: **Connect-inclusion events** (HK; dateable, deep-history, causal front-run of southbound flow), **placement/rights-issue dilution** (HK's highest-frequency run-killer → risk gate), **bank-earnings-season clustering** (CA; Financials ≈29% of board, tightly clustered calendar), and **BoC rate-decision windows** (CA conditioner).

**The two market theses (revised):**
- **HK = flow & structure, delivered honestly thin.** The southbound holding-Δ literature edge is real but our backtest window is ~2 years, not 9 (Eastmoney upstream is a strict 2-year rolling window — v1's "2017→ backfill" was falsified by direct fetch). So HK's near-term visible value comes from: the ripe-list contract (§5.0), Connect-inclusion events (deep history, testable now-ish), A/H discount (matched-pair panel deeper than v1 knew — A-side per-name history 1997–2008→ exists in `china_stocks/*`), the placement-dilution risk gate, SFC short-position context, and the southbound thin-test + accrual.
- **CA = transmission at the sector tier + calendar catalysts.** Commodity regime → sector-ETF excess (vindicated, pending honest stats); names get *exposure-mapped* into flagged sectors via live factor betas (no name-level alpha claim — the catch-up-gap premise had the wrong empirical sign). Plus bank-earnings clustering, the C7 momentum keystone test, CIRO short-Δ (14y archive, depth to verify by fetch), SEDI insider as long-accrual.

**The honesty spine, corrected:** v1 over-claimed ledger maturity. Truth: the name-potential ledgers started 2026-06-28/29 (6/5 snapshots), carry no outcomes yet, and grade the *potential score*, not the board. This program therefore **builds the standout-board forward ledger in W0** so the real scoreboard accrues from day one; first single 21d grade ≈ 2026-07-27, first stable rank-IC read ≈ late-Aug, 63d ≈ Oct. Graduation (W7) is a **2026-Q4 event**. Nothing in this plan pretends otherwise.

### 0.1 Corrections owned from the red-team (v1 → v2)
1. H1 southbound backfill "2017→" **false** — Eastmoney `RPT_MUTUAL_STOCK_HOLDRANKS` is a 2-year rolling window (earliest fetchable 2024-07-03); akshare `stock_hsgt_*` holdings endpoints are **northbound-only**; HKEX mutualmarket.aspx 500s on old dates. → H1 re-scoped (§3); **the 2y window must be captured immediately** (it rolls daily).
2. H3 "2006→ via CN deep store" **false as cited** — `china_search/closes.parquet` starts 2021-06-15. But deep A-history **does** exist per-name in `data/china_stocks/*.parquet` (1997–2008→) → H3 re-specced on true matched-pair depth (§3).
3. H4 "never tested in-house" **wrong** — `rev_st` already failed FDR on this panel. → H4 becomes small/low-ADV-primary on an **expanded HSCI universe** (new W1 collector), with the large-cap run as a confirm-a-kill control and a survivorship *bound*, not a stamp (§3).
4. C7 "verbatim harness reuse" **wrong** — `residual_alpha_phase0.py` is US-hardwired (SPY/GICS/SPDR, no `--market`). → real fork, acceptance = reproduces the known HK kill before CA runs (§4).
5. Ledger maturity & which-ledger-grades-what **overstated** — fixed program-wide (§5.4); all dates re-baselined; registry alerts gated on min-IC-dates so they don't fire early.
6. "~16 trials" **undercounted** — full trial ledger published (§6.1), program-level DSR `n_trials` counts every config (~30+).
7. C1 "40–60 flips" **inflated** — independent episodes ≈ 6–12 per commodity (43–50 debounced turns pooled); episode-level effective-N + `bootstrap_effective_t` mandated.
8. `closes_deep` "cosmetic depth" **under-sold** — 67 names pre-2005 / 101 pre-2010 (survivorship-selected); usable as H4's deep control.
9. `canada_fundamentals.shortRatio` is a **snapshot**, not a history. C5's value is precisely that CIRO has the history the snapshot lacks — after a depth-verifying fetch.
10. Product hole: no deterministic pre-validation board order existed in the plan (one exists in code). → the **ripe-list contract** is now a first-class W1 deliverable (§5.0), and the zero-GO outcome is a *planned branch*, not a failure state.

---

## 1. Data reality (corrected)

**HK:** 157-name OHLCV+volume panel 2000→now (76 names ≤2005 in `hk_stocks`; `closes_deep` has 67 pre-2005 / 101 pre-2010, survivorship-selected, stale 06-18); HSI 1986→; breadth 2000→; VHSI 2003→; HIBOR/HKMA 2002→; aggregate southbound 2014→; per-name southbound **9 days** + a capture-now 2y rolling upstream; A/H 12 pairs (~3y effective; A-side deep history per-name in `china_stocks/*`; H-side 2000→ in `hk_stocks/*` — matched-pair depth is per-pair, mostly ≥2015 for breadth); **no short-sell store** (SFC weekly positions ≥0.02% free ~2012→, T+7 lag, mega-cap skew — coverage vs our panel to be quantified; sstoday = daily short-sell *turnover*, today-only, accrue); no non-hindsight HK sector taxonomy (13 breadth sectors are today's curated map — PIT caveat on any "within-sector" leg); HK thematic-basket **level series not persisted** (per-ticker `data/baskets/ohlcv/` files exist; the basket-level path doesn't); fundamentals 75 names static; SOFR exists only 2018→ (pre-2018 USD leg = 3M LIBOR/OBFR splice, discontinuity handled in regime labeling).
**CA:** 219-name close+volume panel 2021→ (all .TO, **zero TSXV**; Financials 22 names ≈29% wt); 12 TSX sector ETFs (XEG/XGD/XFN 2001→, **XBM 2012→**); US sector ETFs 1998→; commodities 2000→; GSPTSE 1979→; SEDI insider **99.6% post-2025-01** (yfinance 150-row cap; append-only accrual → real backtest ≈2028); earnings 4Q × 224 names + next_date; fundamentals 240 × 29 fields (shortRatio = snapshot); BoC-vs-Fed spread dead (DGS2/DGS10 uncollected); `canada_breadth/_closes_cache` is **gitignored rebuild-only** — must be verified populated at build or CA sector drill-downs ship hollow (HKCA-13).
**Infra:** cross-sectional IC harness (US-hardwired — forks are real builds); `engine/validation.py` (HAC/FDR/DSR/`bootstrap_effective_t`); name-potential ledgers (young, no outcomes, grade the wrong thing for boards); risk-radar forward logs live; experiments registry; pre-reg report convention; `grading.py` next-bar/PIT; **no dead-name store ex-US** → survivorship bounds required, not stamps. Suspension/halt rule required in every HK forward-return computation (HK names halt for weeks; no silent ffill through halts).

---

## 2. Design principles (binding, unchanged + additions)
1. Timing places entries; edges rank names. 2. Per-market everything. 3. Validate-before-weight; refuted legs deleted. 4. Trial-budget discipline with a **published trial ledger** and program-level `n_trials` DSR. 5. Additive to shared engines; **china_alpha collision pact** (§8.1). 6. Fail-closed data with **hard freshness gates** (an axis whose input is >3 trading days staler than the card's own price is suppressed with a visible reason — enforced in code, not cadence). 7. Primary tests run **unconditioned**; sector-neutral variants are secondary robustness trials with the taxonomy's PIT status documented. 8. Every backtest on current-constituent panels reports a survivorship **bound** (worst-case delisted-name imputation or clean sub-window), not a caveat sticker.

---

## 3. Hong Kong architecture (v2)

### Stack
```
CONDITIONERS (size, never rank):  peg-liquidity regime 2018→ (H5) · global-beta amp/cushion (validated) · VHSI · mainland-policy-window chip (display)
EDGE STACK (ranks, per tier):     A/H discount (H3) · Connect-inclusion event tilt (H-INCL) · southbound Δ (H1, thin+accrue) · SFC short-position context (H2a)
RISK GATES:                       placement/rights-issue dilution demote (H-PLC) · suspension/staleness · ADV floor
ENTRY LAYER (places entries):     bottoming-alignment (primary, unchanged) · T1-T4 badge (forward-graded per tier) · washout_2w boost + extension demote (CN ports, log-and-grade)
```

**H1 — Southbound holding-Δ.** *Corrected:* backtest ceiling ≈104 weekly cross-sections (2024-07→) **only if the rolling window is captured immediately** (W1 day-one task; hard go/no-go check at W1-end). Phase-0 (W3): Δ4w primary + Δ1w secondary, forward returns measured **from the next open after disclosure** (implementation-lag honest; the mechanism is fast-decay demand pressure — if the lag eats the edge, H1 is a context chip, never a ranker, and the card copy says so). PIT universe: names on the Connect roster **as-of each week** (HKEX effective-dated inclusion/exclusion lists — same source as H-INCL). Expected verdict: ACCRUE-lean at n≈104; full-power re-run come-back 2027-07.
**H-INCL — Connect inclusion/exclusion events (new, deep-history).** Semi-annual roster reviews 2016→ (~200–400 dateable add events): one-off demand event when the mainland crowd *becomes able* to buy. Event study, next-open fills, HAC + episode honesty. Decision-grade now. Also supplies the PIT roster H1 needs. W2-feasibility spike (roster source), W3 run.
**H2a — SFC reportable short positions.** Weekly ≥0.02% positions, T+7 lag → forward windows start T+7. First step (W1): quantify coverage against our panel; if <60 names it's a context chip only. Trials: {level, Δ4w}. **H2b — sstoday short-sell turnover:** accrue-forward only; never conflated with positions.
**H3 — A/H discount tilt.** True matched-pair panel: H-side `hk_stocks` (2000→) × A-side `china_stocks` per-name (1997–2008→), FX-adjusted; pair map expanded only by **objective listing dates** (both legs listed = pair exists — inception is PIT-safe; no hindsight pair-picking). Publish per-pair start-date table; expect usable breadth ~2015→ (~130 monthly cross-sections). Phase-0 (W3, after panel build — **no 3y-interim run**): discount own-history percentile → forward 1–3m H-vs-HSI, size-controlled, dividend-tax-cycle noted as confound. Trials: {pctile primary, 1yΔ secondary}.
**H4 — Reversal, re-scoped.** The mechanism lives in small/illiquid names; our panel is mega-cap and rev_st already failed there. Sequence: W1 builds the **expanded HSCI universe** (~500 names, deep OHLCV via the shipped yfinance deep-collector pattern — also upgrades breadth/ignition); W2/W3 phase-0: primary = small-cap/low-ADV cohort within the expanded universe; controls = large-cap panel (expected-fail confirm-a-kill) + `closes_deep` 67-name pre-2005 deep subset. Survivorship **bound**: worst-case impute delisted names at the reversal-buy point; report both bounds. Honest prior: NO-GO on large caps is near-certain; small-cap GO is genuinely open.
**H5 — Peg-liquidity conditioner.** Primary 2018→ (SOFR era); secondary = spliced USD leg (3M LIBOR pre-2018) with the splice discontinuity handled in regime labels. Conditioner only.
**H-PLC — Placement/rights-issue dilution gate (new).** HK's highest-frequency idiosyncratic run-killer. W1: collector for placement/rights announcements (HKEX headlines; fallback proxy = share-count deltas from yfinance). Ships immediately as a **demote + card warning chip** (risk gates need no alpha validation); post-placement drift event study queued once ≥1y of events accrues.
**Display-first (no rank weight):** HSI/HSCEI rebalance chips, cornerstone lock-up expiry, mainland-policy-window chip.
**Do-not-build:** residual momentum · COILED/donor · southbound divergence · QVIX port · ST/limit-up logic · margin-crowding (no data).

---

## 4. Canada architecture (v2)

### Stack
```
CONDITIONERS:  commodity/CAD regime (overlay) · BoC-vs-Fed coupling (data fix) · BoC rate-decision windows (new) · gold-CAD interaction (exploratory)
EDGE STACK:    commodity→SECTOR transmission (C1, vindicated pending honest stats) · bank-earnings-season/PEAD (C-BANK, new) · momentum per C7 verdict · CIRO short-Δ (C5, post-verify)
LONG-ACCRUAL:  SEDI insider (C2 — ACCRUE-only, no W4 wiring, real read ≈2028; W1 spike: canadianinsider.com / INK free tiers for deeper history)
ENTRY LAYER:   alignment + T1-T4 (forward-graded) + extension demote
HYGIENE:       ADV floor · generic dilution flag (share-count deltas) — TSXV branch CUT (board has zero .V names)
```

**C1 — Commodity→sector transmission.** Red-team replication supports the sector tier (XEG/XGD post-turn excess, t≈2.0–2.8 raw). Phase-0 (W2): pre-registered regime-episode definition (min-duration + hysteresis → independent episodes ≈6–12/commodity, ~20–36 pooled over CL/GC/HG), non-overlapping episode returns, HAC + `bootstrap_effective_t`, DSR at program `n_trials`; per-pair ETF inception stated (XBM 2012→). Honest prior: GO-or-ACCRUE at the episode count — borderline by construction; say so. **Name tier = exposure mapping only** (live factor betas shortlist high-|beta| names inside a flagged sector — forward-graded, no alpha claim; the catch-up-gap construction is dropped, empirical sign against).
**C-BANK — Bank-earnings-season clustering + PEAD (new).** Big-6 report within ~2 weeks each quarter; Financials = 2nd-largest sector sleeve. Phase-0 (W2, in-tree data): {season-window sector effect, post-beat PEAD drift on banks}. Decision-grade (≈100 bank-quarters on 25y ETF + 5y names).
**C7 — Momentum keystone (re-costed).** Build `canada_residual_alpha_phase0.py` as a real fork (market-parameterized benchmark ^GSPTSE, CA sector map, CA panel loaders); **acceptance gate: fork reproduces, to the digit, a same-day fresh run of `scripts/hk_residual_alpha_phase0` on the current HK panel — never a frozen numeric pin** (the 2026-06-18 panel expansion 73→157 names already sign-flipped the near-zero mom_res LS Sharpe from −0.22/−0.35 to +0.17/+0.31 while leaving the kill intact: fails DSR, IC≈0). Trials: {mom_tot, mom_res} × {names 5y, sector-ETFs 25y}. Verdict branches: (A) any GO → that leg becomes the rank basis, cited; (B) **all NO-GO and no other C-leg GO'd → the board runs the ripe-list contract (§5.0) permanently, composite suppressed, tier=screen** — a planned outcome, not a failure.
**C5 — CIRO short-Δ.** W1 spike first: fetch an actual ~2013 CSV to verify archive depth + publication lag; then collector (2012→, semi-monthly) and W3 phase-0 {Δ, level} with lag-honest windows. If archive shallow → accrue-forward.
**C4 — Earnings-streak chip.** Ships as display catalyst chip now ("2 beats · reports in 23d"); exploratory read explicitly **non-evidential** (4Q depth) — cannot be cited for promotion.
**C6 — Tax-loss seasonal.** ~25 independent Decembers can never reach the bar → **descriptive chip only, no sizing tilt, no trial slot.**
**Cut:** C3 US-lead family (replication: near-zero, sign-inconsistent residual — folded into C1 as a covariate at most) · C8 TSXV branch · C2 near-term wiring.
**Display-first:** TSX quarterly rebalance add/delete chips; gold-CAD interaction as exploratory conditioner tag.

---

## 5. Shared layers (v2)

### 5.0 The ripe-list contract (pre-validation board order — deterministic, ships W1)
The owner's product is ONE ranked list per market. Until (and unless) legs graduate, both boards run this exact order — it is also the permanent product under the zero-GO branch:
```
UNIVERSE  = names passing hygiene (ADV floor · not suspended · price fresh · not placement-flagged [HK])
INCLUDE   = HK: confluence cascade eligible (signal_gate T1-T4; owner-ratified 2026-07-16, mirroring the CN
            2026-06-29 directive) — bottoming-alignment retained as per-card context badge, not a gate
            CA: bottoming-alignment ∈ {PRIME, ARMED} (existing gate; near-aligned backfill to min 10 when thin)
GROUP     = entry-open (confluence T1-T3 buyable ∧ in/near buy-zone)  >  setting-up (aligned, awaiting trigger)
RANK      = within group, edge-stack z percentile (HK: hk_edge fused z as shipped; CA: alpha until C7 verdict, then per C7 branch)
TIEBREAK  = 63d ADV desc
CARD      = mechanism lead (§7.1) + entry window (open-now | pullback lo–hi | wait-for-weekly) + tier badge + why-now chips
```
Timing groups and gates; edges rank within groups — consistent with the house truth. This makes week-1 boards sharper than today regardless of any phase-0 outcome.

### 5.1 Sector-ignition layer
Rank groups by turn evidence: breadth thrust (% members crossing 20dma, 5d) + RS-slope change + basket-MTF confirm. **HK ships without the southbound flow leg** (it accrues; thin history) — copy says "narrow market: ignition is context." CA adds the commodity-flip flag for resource sectors. Display + forward-graded ignition ledger; no scored use before grades mature.

### 5.2 Basket desk rebuild
Persist HK/CA **thematic-basket level series** (precise gap: basket-level path, not per-ticker OHLCV which exists); port risk-radar strip / act-now / flow-lens / `_theme_addons` where data legs exist; membership: curated sets keep `curated` provenance labels + shadow rules-based membership diffed on-desk; **hard freshness gate** on the tailwind axis (suppress + "basket prices N days stale" when >3 trading days older than card price) — W0 acceptance, code-enforced; `basket_freeze` parity for CA. **Note:** `baskets_region.py` is shared with intl → any change here runs the intl basket regression too (§8.1).

### 5.3 Entry layer & gate
Unchanged mechanics; HK gains washout_2w boost + extension demote + entry trio (log-and-grade). Gate re-parameterization only from matured ledger evidence (W7/Q4); until then per-market fine-print "US-calibrated". **2026-07-16 carve-out:** the HK INCLUDE *predicate swap* (alignment → confluence cascade, §5.0 amendment) is an operator-ratified design change, not an evidence-driven re-parameterization — W7/Q4 still governs any *tuning* of cascade/entry thresholds, and the board ledger stamps `gate_ver` so pre/post-swap rows grade as separate samples.

### 5.4 Ledgers (corrected)
- **NEW standout-board forward ledger (W0):** every render logs the ranked board (position, edge-leg z's, gate tier, entry state, as-of close); grades at 5/10/21/63d with next-bar fill + suspension rule. This — not the name-potential ledger — is the board's scoreboard. First single 21d grade ≈ 07-27; stable rank-IC ≈ late-Aug; 63d ≈ Oct.
- Name-potential ledgers: keep accruing; correctly described (6/5 snapshots, no outcomes yet).
- Registry entries for every trial/accrual with **real** come_back_on dates + a min-IC-dates alert gate (no early "accruing" pings).

---

## 6. Validation constitution + trial ledger

Constitution inherited (pre-reg first; HAC; BH-FDR within family; **program-level DSR n_trials ≈ 30+ counting every config across both markets**; split-half sign-stability; effective-N = independent episodes; DSR ≥ 0.90 the only door into scored seams; suspension-honest fills; survivorship bounds; verdicts GO/NO-GO/KILL/ACCRUE).

### 6.1 Trial ledger — RESOLVED 2026-07-03 (all batteries run; reports in `reports/`)
| ID | Test | **VERDICT** | Key numbers | Disposition |
|---|---|---|---|---|
| H1 {Δ4w, Δ1w} | southbound holding-Δ | **NO-GO both** (#1073) | lag+0 blip (t 1.33) erased at lag+1 — render lag eats it | context chip only; re-run 2027-07 |
| H-INCL (+re-run) | Connect-inclusion events | **NO-GO, retired** (#1077, #1078) | K=74 on 545-name panel: +20d CAR negative; run-1's +5d seed collapsed | free 796-event roster shipped; **removal side t≈−3.9 → new battery (cause-controlled) before any use** |
| H2a {level, Δ4w} | SFC short positions | **LEVEL ACCRUE · Δ4w NO-GO** (#1076) | level Q5−Q1 −0.39%/4w, HAC-t −1.81, correct CCY sign, t_eff 189; svl variant t −2.41 (non-decision) | context chip; re-run on expanded universe |
| H3 {pctile, 1yΔ} | A/H discount | **ACCRUE — near-GO** (#1068) | IC .055 (t 2.23), top-5 tilt +2.77%/3m (t 3.08), 5/6 gates, **DSR 0.879 vs 0.90** | lead accruing HK edge; fusion re-weighted toward it (W4); come-back 2027-01 |
| H4 {small-cap primary + controls} | reversal | **KILL — wrong sign w/ power** (#1070) | deepest 3M losers −0.92%/mo (t −2.14, effN 308, both halves) | → **falling-knife DEMOTE gate** (W4); CN-reversal port dead forever |
| H5 | peg-liquidity split | **ACCRUE conditioner** (#1040) | EASY vs TIGHT maxDD −21% vs −49%; live wire = agg_balance | deskhero conditioner chip + sizing context (W4) |
| C1 {oil, gold, copper} | commodity→sector | **oil ACCRUE · gold/copper NO-GO** (#1038) | oil→XEG t 2.75, FDR-reject, DSR 0.54, builds 4→8w; gold t −0.04 | oil chip live (fires on risk-on only); come-back as history deepens |
| C-BANK {window, PEAD} | bank season | **NO-GO both** (#1039) | season contrast −0.49%/qtr (wrong sign); PEAD degenerate 18/2 | slot closed |
| C7 {tot, res} × {names, ETFs} | momentum keystone | **4× ACCRUE → BRANCH B** (#1041) | names mom_res t 3.95, FDR-stable, LS 1.06, but DSR 0.37 @ ~3 episodes | CA board = ripe-list contract permanently; composite suppressed; re-test 2027-01 |
| C5 {Δ, level} | CIRO shorts | **ACCRUE-DATA — unrunnable** (#1080) | archive ends 2019-08 vs CA panel 2021-06→: zero overlap; parser bug fixed | forward accrual; ~2028 |
| C4 | earnings streak | exploratory only | non-evidential by design | catalyst chip |
| C2 | SEDI insider | ACCRUE-only | 99.6% post-2025 | ~2028; append-only accruing |
| C6 | tax-loss seasonal | never gated | ~25 Decembers | descriptive chip only |
| COILED-CA {m2d_s3d} | durable-bottom detector port (US+CN-validated engine; **CA never tested**) | **KILL — CA joins HK on do-not-port** (`COILED_CA_PREREG`) | 215-name CA panel 2022-09→, CN wave-3 gate verbatim: COILED n=923 clean15 **−2.96pp (wrong sign)**, stop5 **+6.08pp worse**, split-half both halves neg (−1.76/−3.29), per-name **45.8% minority**, name-clustered boot 90% LB **−5.83pp**; deep TSX-ETF context (survivorship-clean, 2001→) **−9.21pp** | do-not-wire; mechanism = the HK failure (CA commodity-macro-correlated, Materials+Energy 98/219 → cohort washout is beta not selection). Reinforces Branch B: CA edge is commodity→sector *transmission*, not name selection. `reports/coiled-ca-phase0.md` |

**Program outcome: 0 GO · 4 signal-ACCRUEs (H3 near-GO 0.879, oil→XEG, CA mom_res, H2a-level) · 1 conditioner · 7 NO-GO · 2 KILL (H4 reversal→demote-gate; COILED-CA durable-bottom port) — zero results tortured.** Branch B (§4.1/§5.0) is the operative product on CA; HK runs the evidence-re-weighted screen. First forward-scoreboard read: ~late-Aug 2026 (21d), Oct (63d); graduation review W7 = Q4.

---

## 7. UX & truth plan (v2)
1. **Card lead = the mechanism, alive** (product-critic fix): lead with the named fresh state in active language + the entry window — *"Mainland crowd added 0.8% of float in 2w — heaviest in 6mo · H trades 12% under its A twin · weekly base holding · entry: pullback 41.20–42.80"*. The tier is a small honest badge; **desaturation applies to the composite score chip only, never the setup narrative**. Honest-but-exciting = "a real, named, fresh mechanism + a price to act at; scoreboard building."
2. One consolidated desk-header caveat block (kills the 6× repetition); per-card tier badge.
3. Why-now chips = edge-stack states, each tagged validated/context/accruing.
4. **Track-record panel ships in 'accruing' state** with the honest date it goes live (late-Aug 21d / Oct 63d) printed on the panel.
5. CA parity: watch strip, laggard strip, alerts, AI-brief doorway.
6. Health banners on every degraded leg (kills silent fail-open); hard freshness gates per §5.2.
7. Mechanical: localStorage `hkfw-`/`cafw-` split; CA "VALIDATED" contradiction purge; dual-mode CSS blast-radius regression (stocks-mode edits re-verified on macro pages at 375px + zh).

---

## 8. Waves (re-sequenced, honestly dated)

**W0 — Truth, safety & scoreboard (this week).**
Standout-board forward ledger (both markets) · hard freshness gate on tailwind/ignition axes · health banners + breaker · CA tooltip/trust-tier contradiction purge · closes_deep nightly refresh · `basket_freeze` CA · localStorage split · FRED DGS2/DGS10 · `canada_breadth/_closes_cache` build-time verification (HKCA-13) · survivorship/suspension stamps. *Accept: 4 pages render with health surface + gates enforced in code; ledger writing on tonight's render; zero contradictory copy.*

**W1 — Data plane + ripe-list contract (this week; collect lane ONLY — no new network in render lane).**
**Day-one: capture the Eastmoney southbound 2y rolling window** (hard go/no-go at W1-end) · expanded HSCI universe collector (~500 names deep OHLCV) · SFC weekly shorts + coverage count · sstoday accrual · A/H matched-pair panel (H×A per-name stores, listing-date PIT pairs) + per-pair depth table · CIRO depth-verifying fetch → collector · SEDI append-only + canadianinsider/INK spike · placement/rights collector (or share-count proxy) · HK basket level persistence · **ripe-list contract implemented on both boards** · per-store R2-vs-git decision table + .gitignore + `publish_r2 --dirs` + `audit_r2` anchors + sentinel git-add scope **in the same PR as each store** · named tripwire per collector. *Accept: each store lands with freshness stamp + tripwire + depth report; boards ship the contract order + entry windows.*

**W2 — Phase-0 battery A (in-tree data; pre-reg docs committed before runs).**
C7 fork (gate: matches a fresh live HK-harness run, §4) → run · C1 sector tier (episode-honest) · C-BANK · H5 (2018→) · H4 if the expanded universe landed (else W3) · C4 exploratory (labeled non-evidential). *Accept: verdict-bold reports; registry updated; NO wiring.*

**W3 — Phase-0 battery B (post-collector).**
H1 thin · H-INCL · H2a · H3 · C5 · H4 (if not W2). *Same bar.*

**W4 — Wire the verdicts (two planned branches).**
Branch A (≥1 GO): re-rank per verdicts, every scored leg cites its report, refuted legs deleted. Branch B (zero GO): **ripe-list contract becomes the permanent board**, framed as the honest screen, composite suppressed — and that is success, stated on-page. Ports (washout_2w, extension demote, entry trio) land log-and-grade either way.

**W5 — Sector-ignition + basket rebuild** (§5.1–5.2; sequenced *after* china_alpha's `baskets_region` changes land or with a single coordinated owner — §8.1; intl basket regression run in the PR).

**W6 — UX overhaul** (§7; track-record panel ships 'accruing' with honest go-live dates).

**W7 — Calibration & graduation (2026-Q4).** Gate-tier hit-rates from matured ledgers · `_WEIGHT_PRIOR` recalibration where evidence permits · promotion/demotion pass · registry + memory + status log.

### 8.1 china_alpha collision pact
File-ownership: china_alpha owns `engine/coiled.py`/washout wiring + CN builders; **`baskets_region.py` gets one owner at a time** (HK/CA basket work waits or coordinates); shared `stock_score`/`signal_gate`/`name_score` edits are market-keyed params only, with mandatory rebase-onto-latest-main before merge + cross-market test suite **including the intl basket regression** in every PR touching shared modules. Same-day merges sequenced, never racing.

### 8.2 Honest program timeline
This week: W0 + W1 + most of W2. W3 gates on collectors (≈+1 week). W4 gates on verdicts. W5/W6 follow (≈2–3 weeks out). W7 = Q4 (ledger-gated). Registry carries per-wave come-back dates.

---

## 9. Risks & kill criteria (v2)
Survivorship bounds mandatory (not stamps) · southbound capture is day-one-urgent (rolling window) · thin universes → structural/flow legs (by design) · program-level multiplicity ≈30+ trials controlled via ledger-fed DSR · shared-engine collisions governed by §8.1 · CIRO/canadianinsider archive claims verified by fetch before any collector is scoped on them · **zero-GO branch is planned product, not failure** — the desks become the sharpest honest screens we can build, with the scoreboard proving (or refuting) them in public.

## 10. End-of-program acceptance test ("goal met" — measurable)
1. Each stock page surfaces **≥5 ranked names/day**, every card carrying (a) a named fresh mechanism state, (b) an explicit entry window (open-now | pullback lo–hi | wait), (c) a tier badge.
2. The **standout-board forward ledger** exists for both markets and the on-page panel prints graded results (not "accruing") by its stated go-live dates: ≥5 matured 21d cross-sections (~late-Aug), 63d by ~Oct.
3. Target: buy-group 21d hit-rate ≥55% **and** board rank-IC>0 with same-sign split-half for **at least one market** — OR the explicit honest-screen reframe ships on-page (branch B), stated plainly.
4. **Zero contradictory copy** across panels (automated check: no card asserts validated+unvalidated; no chip implies an edge the rank ignores).
5. No card shows a tailwind/ignition axis whose input prices are >3 trading days staler than the card's own price (gate enforced in code).
Nothing weaker than 2–4 counts as "goal met."

## 11. Status log
- 2026-07-03 — v1 authored on Phase-A evidence; 5-critic red-team returned 12 fatal / 26 major; v2 authored with corrections owned in §0.1.
- 2026-07-03 — **W0+W1a SHIPPED** (#1037/42/44/46/52/57/59/65): southbound 2y window captured (464d, 6.3MB); board-ledger module; truth fixes; FRED `_fetch_fred` dropna bug found+fixed → BoC-vs-Fed coupling live; SFC collector (721wk backfill completed, 153/157 coverage); CIRO (true archive 2018-11→2019-08 only — §6.1); SEDI append-only; HSCI universe 537 (388 new names fetched, R2-destined); A/H panel 25 pairs 2001→.
- 2026-07-03 — **W1b BOARDS SHIPPED** (#1069 HK, #1072 CA): ripe-list contract §5.0 live on both boards; entry windows + bilingual mechanism leads on every card; board ledger writing (day-1: HK 9 / CA 14 rows); hard freshness gate live (suppressed the stale HK tailwind on first render — positive control); **CA Branch B implemented** (composite suppressed, rank pills, "screen — accruing" badge); C1 oil chip (risk-on-gated); health banners incl. HKCA-13 surfaced on-page.
- 2026-07-03 — **W2+W3 ALL BATTERIES RESOLVED** (#1038-41, #1068/70/73/76/77/78/80): full verdicts in §6.1. Zero GO — Branch B operative; H3 A/H = near-GO (DSR 0.879); H4 = KILL→demote gate; H1/H-INCL retired by delivery-lag/impound evidence.
- 2026-07-03 — **W4 dispatched** (HK wiring: A/H-tilted fusion re-weight, falling-knife demote, H5 conditioner chip, SFC days-to-cover chip). Remaining: W5 ignition+baskets (additive only — `baskets_region` untouched per §8.1 pact), W6 UX overhaul, W7 = Q4 graduation review (first stable scoreboard read ~late-Aug). New batteries registered: Connect-REMOVAL risk gate (cause-controlled); ext-store corporate-action tripwire follow-up.
- 2026-07-03 — HK residual-momentum pins refreshed: `closes_deep` expanded 73→157 names (06-18 stamp) sign-flips mom_res LS Sharpe to +0.17 full / +0.31 modern (still fails DSR, IC≈0 — KILL stands). §0 + §4 C7 gate re-worded to live-harness acceptance (no frozen pins); `reports/hk-residual-alpha-phase0.md` regenerated from the live fork.
- 2026-07-03 — **W1c H-PLC SHIPPED** (w1c(h-plc)): placement/rights dilution gate live end-to-end. Collector = the PRIMARY route, not the proxy — HKEX titleSearchServlet headline categories (Placing 18480 / Rights Issue 18500 / Open Offer 18460; keyless JSON; archive to 2007-06-25; verified by live fetch) → `data/hk_placements/events.parquet` (git-tracked) + coverage stamp; fail-closed named tripwire (zero-union fetch raises; stale_after_days=7); dilutive-title classifier screens the category over-capture (AT1/CB issuance, meeting notices — live false positives on 0005/0300 caught in test). Board: `_placement_demote` (falling-knife pattern) pushes flagged names out of the entry groups onto the watch strip with a bilingual chip; render-lane freshness gate degrades LOUDLY (health row + None ledger stamps, never silent fail-open); `placement_flag` persisted as a nullable-bool board-ledger column (§5.4). Registry: `h-plc-post-placement-drift` accruing, come-back 2027-07-03 (deep 2007→ archive leg available earlier via --full-history if a trial slot is granted). P0 NOTE: PR #1052's squash accidentally EMPTIED `scripts/collect.py` (711 lines → 0) — the whole collect lane was a silent no-op from 07-03 07:17. Found independently in this wave; the byte-exact restore landed on main via #1093 while this PR was in flight, so #1106 contributed only the `hk_placements` registry line.
- 2026-07-03 — **DSR multiplicity plumbing regularized**: all 8 battery scripts migrated off literal `n_trials=` to the ledger path (`TrialLedger.with_declared_budget(30, family)`; hincl2 keeps its 32) per §9 "controlled via ledger-fed DSR" — bit-identical haircuts, now audited. The PR #1073 `DELIBERATE_LITERAL` exemptions are removed (that rationale misread "≈30+" as a fixed constant; hincl2's 30→32 bump proved the count grows). Ratchet + trial-registration lint both green on main again (h4/hincl/hincl2 had silently re-redded them).
- 2026-07-16 — **HK INCLUDE gate amended (operator-ratified): alignment → confluence cascade.** Trigger: full pick-pipeline audit after hk_stocks.html rendered a 1-name buy strip for consecutive sessions. Diagnosis: the bottoming-alignment INCLUDE (a fresh-bottom detector) conjoined with the entry_z>-0.1 floor passed 1 of 74 names on the 07-16 post-thrust tape (sole aligned name 1928.HK then H4-knife-demoted; the rendered card 0027.HK was a near-aligned backfill) — the gate is regime-starved mid-trend by construction, and min-10 backfill cannot manufacture names when the near pool is empty (spec-compliant, not a bug). Amendment (§5.0): HK INCLUDE = `sig_verdict.eligible` from the owner's signal_gate T1-T4 cascade, mirroring the CN owner directive 2026-06-29 (CN: 191/1421 eligible on the same engine); bottoming-alignment demoted to per-card context badge; entry gauge stays on cards. SCOPE GUARD: inclusion-only — GROUP→RANK→TIEBREAK unchanged (hk_edge fused z), H4 falling-knife + H-PLC placement demotes intact, trust_tier='screen' + "verdict never says Buy" intact, NO COILED (do-not-port kill stands), NO washout_2w rank effect (§5.3 log-and-grade stands). Board ledger stamps `gate_ver` so W7/Q4 grades split pre/post-swap samples; the pre-swap ledger (07-03→07-16, 0 matured 21d rows) carries no verdict weight either way. Same audit: HK pick-lab producer NaN crash fixed (#2623) — 1D Velocity Desk + 20 display-only books un-dead-wired.
- 2026-07-03 — **COILED-CA battery resolved — KILL** (`hkca-ca2-coiled`): the US+CN-validated durable-bottom detector (`engine/coiled.py`) was **never tested on Canada**; this closes the "why not just port the US/CN system" question with data. Pre-reg `research/COILED_CA_PREREG.md` replicates the **exact CN wave-3 gate** (215-name CA close-only panel 2022-09→, `m2d_s3d`, COILED vs noncoiled_washout clean15 spread) — committed BEFORE the run, thresholds are the CN values verbatim. Result: COILED n=923 clean15 **−2.96pp (wrong sign)**, stop5 **+6.08pp worse**, split-half **both halves negative** (−1.76/−3.29), per-name **45.8% minority**, name-clustered bootstrap 90% LB **−5.83pp** (P(Δ>0)=0.10). Deep survivorship-clean TSX sector-ETF context (2001→, cross-ETF cohort) **corroborates −9.21pp**. **CA joins HK on the do-not-port list** with its own evidence: despite CA structurally resembling CN (developed, 11 sectors, name-level cohorts), it fails like HK because CA is commodity-macro-correlated (Materials+Energy = 98/219 names) → sector-cohort washout is a beta signal, not selection. Reinforces Branch B — CA's edge is commodity→sector *transmission* (C1), not name selection. Harness `research/entry_timing/wave3_ca.py` (fork of `wave3.py` close-only path; leak-free math reused verbatim). **NOTHING WIRED** (collision pact §8.1: china_alpha owns `engine/coiled.py`); phase-0 report only.
