# Exit / Crowding Overlay — PHASE-0 PRE-REGISTRATION — **RATIFIED (scoped, §0.1)**

> ## STATUS: RATIFIED BY FABLE 2026-07-04 — REGISTERED as of this commit
> Drafted by Opus under roadmap item **P1.3** (research/LIVE_FLOW_PRODUCTION_ROADMAP_BY_FABLE.md, ruling **R3**); adjudicated same-day. The proposals below are FROZEN as amended by the §0.1 rulings (F1–F5), which are part of the registration. Opus review verdict on the draft: APPROVE (2 nits, both resolved by F4 and the F-A citation fix). The RUN (P4.4) may begin per §8.11 as amended by F3.

## §0.1 FABLE ADJUDICATION (2026-07-04) — rulings F1–F5

- **F1 (OPEN-1, power fork) — BOTH lanes, sector-ETF PRIMARY.** The gated PRIMARY conditioning universe = the 11-sector-ETF complex, 2018→, all group-days (the exhaustion leg itself is the condition) — domain-matched to the −1.24% SELL base rate and adequately powered. The board-held roster is a **watermarked SECONDARY tag lane** that can never promote alone and **never gates** — the gated FDR trial count stays **16** (§7); secondary-lane cells print as context. Placebo adaptation: PRIMARY lane placebo = same-sector leg-not-fired matched group-days (regime+duration matched, 200 draws, exclusion_zone=10); SECONDARY lane keeps §5's held-but-not-fired design verbatim.
- **F2 (OPEN-2) — ADOPTED as recommended.** L3's 2013-17 OI-only bucket is reported, never gated, stamped "pre-primary, OI-only, robustness."
- **F3 (OPEN-3) — L4 runs at ratification, PRE-FDR interim.** L4 has no thetadata dependency and runs first; its cells print labeled **PRE-FDR INTERIM** until L1–L3 complete the 16-trial sub-family, at which point BH q-values print once for the whole family. No verdict language stronger than ACCRUE/interim before the family completes.
- **F4 (long-set simplification; resolves review nit) — §2.1's long-set = membership in the `buy[]` roster, full stop.** The `state ∈ {...} AND label == "BUY ZONE"` sub-filters are DROPPED: roster membership already IS the actively-held entry set, and state/label text is schema-drift-fragile. (Secondary lane only, per F1.)
- **F5 (L2 IV source) — vendor IV, not reconstruction.** IV-rank computes from the T1 greeks store's vendor `implied_vol` directly (`source:vendor`, `reconstructed:false`); the A5 BS-inversion remains the AUDIT tool only (roadmap P2.3 / D3 benchmark-then-supersede). §8.3's reconstruction-labeling law applies to any quantity NOT vendor-supplied (e.g. group aggregation), unchanged.

**Battery:** EXIT-CROWD (LIVE_ORDER_FLOW_BRAINSTORM §5.6 "Exit overlay", roadmap F). **Phase:** Phase-0 (options-alpha program). **Branch (draft):** `w1-p13-exit-crowding-prereg`.
**Author:** Opus research agent, off the frozen SELL base-rate machinery + the live US board ledger schema. **Adjudicator:** Fable (RATIFIED 2026-07-04, rulings §0.1 F1–F5). **Runner:** roadmap **P4.4** (RUN happens *after* ratification AND after `data/thetadata_eod/_manifest.json` marks the universe pass complete, per R8).
**Constitution inherited:** OPTIONS_ALPHA_MASTERPLAN **§2 doctrine** (validate-before-score, no flow-direction claims, OI-is-sacred, dealer-sign fragility, sub-30-date backtest ban) + OPTIONS_ALPHA **A3** (no 60-date half-gates) + SETUP_SPECIES_MASTERPLAN **§1** safety-net-axis grading + O_OPT_PHASE0_PREREG placebo/FDR machinery. Verdicts: **DISPLAY-WITH-EDGE / DISPLAY-WITH-NULL / KILL / ACCRUE**. **No hard gate into any engine on pass** (China subsector-gate falsification is binding). Fail → display-with-null per house law.

---

## 0. In plain English

We already have a *price-only* verdict on what happens after a group flips to the SELL/exhaustion state: the sector-signal state machine, calibrated on the 11 SPDR sector ETFs 1998–2026, says a SELL state earns **−1.24% excess vs SPY over 63 days, hitting only 40% of the time (n=169)** — a real, measured avoid-edge (`engine/sector_signals.py:78`). That number is the **outcome currency** of this battery: any options-derived exhaustion leg has to beat, or at least meaningfully sharpen, that price-only SELL base rate before it earns anything but a display tile.

This pre-reg asks four narrow questions of the **options tape** (unsigned legs only — no directional flow claim), conditioned on **the groups we are currently long** (defined operationally in §2.1 from the live US board ledger):

1. **(L1)** When short-dated OTM **call-share** spikes in a group we hold — retail/chase crowding — do forward returns decay toward (or below) the SELL base rate?
2. **(L2)** When **IV-rank blows out** but price barely responds (a vol bid with no follow-through) — does that mark exhaustion?
3. **(L3)** When the **put/call open-interest ratio collapses into strength** (protection lifted as price rises) — the complacency tell?
4. **(L4)** When **ETF-flow rolls off** (institutions trimming while price holds — the "A4 divergence tell") — does that lead the drawdown, at a 1–5 day lag?

The **falsifiable house prediction, written before we look:** the **SELL / exhaustion side validates before any BUY-side flow signal does.** Exit evidence is cheaper to find than entry evidence because crowding leaves a louder options footprint than accumulation. If the gauntlet returns "exit yes, entry no," that verdict is printed, not hidden. Everything ships display-only until it clears the same gauntlet the price claims cleared.

---

## 1. Data-state STAMP (exact local state, DRAFT authored 2026-07-04)

- **`engine/sector_signals.py :: STATE_BASE_RATES["SELL"]`** — the **outcome-currency base rate**: `{"exc63": -1.24, "hit": 40, "abs63": -0.05, "abs_hit": 59, "n": 169}` (line 78). Calibrated on the full state machine, weekly-sampled across the 11 sector ETFs 1998–2026 (lines 60–70). The neighboring avoid states are also stamped and are the comparison ladder: `TOPPING exc63 −0.11 / hit 48 / n 2335`, `EXTENDED exc63 +0.06 / hit 50 / n 2185`. The negative avoid-edge **concentrates in TOPPING/SELL** — the doc's own honesty nuance (lines 63–65). **These are refreshed live by `calibrate` (SECTOR_CONFLUENCE.md), so the harness reads the LIVE dict at run time, not the static fallback**, and stamps the exact values it used.
- **`scripts/oracle_gauntlet_p3.py:1365-1379`** — the **B2 benchmark machinery** that already compares an exit-side forward spread against this exact baseline: `b2_baseline = {"mean_pct": -1.24, "hit_rate": 0.40, "n": 169, "source": "sector_signals SELL"}`, compared to `ep_out_undeniable_63d` direction-adjusted mean, labeled **"informative only — different universe granularities."** This battery **reuses B2 verbatim** as its benchmark-exceedance gate (the G6-analog), inheriting its honest cross-granularity caveat.
- **`data/us_board_ledger/snapshots.jsonl`** — the **live US board state** that defines "groups we are long." Row schema (verified): `{as_of, rank_by, dispersion_regime, buy[], watch[], laggards[]}`. Latest row `as_of=2026-07-02` (`buy` n=24); a fuller row `2026-06-30` carries `buy` n=34. Each `buy[]` element carries `ticker, name, sector, state, label, urgency, align_tier, conviction{...}, signal{...}, entry_signal{...}`. `rank_by="bottoming-alignment"`. **This is the operational long-set source (see §2.1).**
- **`data/us_board_ledger/retro_grades.parquet`** (85 KB) + **`studies.json`** — the forward-graded board ledger (the Stage-B PIT-stamp target, OPTIONS_ALPHA A6). `studies.json.powered=false`, `power_note` = "UNPOWERED shallow run (no deep panel / no PIT membership) — survivorship-INFLATED, DIRECTIONAL ONLY." **Survivorship caveat carried forward: any board-conditioned n is survivorship-inflated until the deep+PIT panel (reports/stock-conviction-phase0.md) backs it.**
- **`engine/theme_flow_rollup.py`** — the **L4 (ETF-flow rolloff) source**. `theme_flow(region='us') -> {theme_id: ThemeFlowResult}`; `ThemeFlowResult = {flow_score, accumulating_pct, divergence, n_covered, n_members, flow_label}`. **Module header explicitly stamps `directional=False`, DISPLAY-ONLY**, trailing-truth snapshots of reported fund holdings at **1–5 day lag** (header lines 1–11), `_MIN_COVERED_FRAC = 0.10`. The **`divergence` flag = flow_score<0 while basket rel-price flat/up = the "A4 tell"** — this is the L4 leg's exact primitive. **L4 carries a hard 1–5d lag label on every surface (R3).**
- **`data/thetadata_eod/_manifest.json`** — **`{"store":"thetadata_eod","n_roots":0,"per_root":{},"updated_at":null}`** as of this draft — the universe pass has **NOT** completed. Every L1/L2/L3 feature is defined *against this planned store*. Per **R8**, no harness reads `data/thetadata_eod/` until this manifest marks the universe pass complete (`n_roots` at the full ~360-root target, `updated_at` non-null). `_backfill_state.json` also present (29 bytes).
- **`engine/options_universe.py :: gex_symbols()`** — the optionable universe resolver (roadmap R1: returns **360** roots at `max_underlyings=360`). Options features exist only for members in this set → the coverage law §2.4 binds.

---

## 2. Constructions (proposed — frozen on ratification)

### 2.1 The long-set (operational definition — the conditioning set)

The claims condition on **"groups we are long."** Operationalized from the live board ledger, PIT-honestly:

- **Primary long-set unit = the board `buy[]` roster on each snapshot `as_of` date.** A name is "long" on date *t* if it appears in `snapshots.jsonl`'s `buy[]` array for the snapshot whose `as_of == t` (or the most recent `as_of ≤ t` if no same-day snapshot), with `state ∈ {FRESH BUY, BUY ZONE, BUY}` and `label == "BUY ZONE"` — i.e. the actively-held entry roster, NOT `watch` or `laggards`.
- **Group aggregation = by `sector`** (the `buy[]` element's `sector` field, e.g. "Industrials"), mapped to the sector-ETF complex the SELL base rate is calibrated on (XLB…XLY). This makes the outcome currency (§1, sector-ETF SELL base rate) **domain-matched** to the conditioning group. A per-name overlay is reported as context only (the species precedent: per-name overlays stay falsified; the SLEEVE/group is the unit — SETUP_SPECIES §8 W1-S13 row).
- **PIT hygiene on the roster:** the board snapshot for date *t* is read from the `as_of ≤ t` row only — never a future snapshot. The ledger is append-only JSONL; the harness reads the line whose `as_of` satisfies the rule and never a later line. **Survivorship stamp:** `studies.json.powered=false` → every long-set-conditioned n is **survivorship-inflated**; positives are optimistic and carry the caveat until the deep+PIT panel confirms (§8).
- **Placebo counterpart (§5):** matched **non-event group-days** = sector-group-days where the group is *held* (in `buy[]`) but the exhaustion leg did **not** fire, regime- and duration-matched.

### 2.2 The four unsigned exhaustion legs (proposed feature definitions)

All L1–L3 features compute **per held-group per session** from the planned `data/thetadata_eod/` T1 store, aggregated to the group via §2.1. Each carries `signing_source` (must be **unsigned** — total/share/absolute, never net-signed; signed legs enter by amendment only, R3) and `reconstructed` provenance stamps (§8). **Per-leg data windows are stated because the join surface differs by leg** (roadmap R3 requires per-leg windows).

- **L1 — Short-dated OTM call-share spike** (`crowd_call_share_z`).
  Definition: within a held group, the **share of daily options volume in short-dated (≤ 21 DTE) OTM calls** (strike > underlying_price × 1.02), member-mean, standardized to a 252-session rolling z. **Requires the EOD-volume ⋈ greeks join for `underlying_price`** (moneyness needs spot at the greeks timestamp). **Leg window: 2018→** (after the greeks-bearing warm-up: greeks coverage begins 2017 per roadmap F-A; a full 252-session z baseline needs ≥1 year → first usable z ≈ 2018). Fires when `crowd_call_share_z ≥ +1.5` with 2-session persistence.
- **L2 — IV-rank blowout × weak price response** (`iv_blowout_weak_px`).
  Definition: group-mean **IV-rank (252-session percentile of ATM-IV30)** in its top decile (`iv_rank ≥ 90`) **AND** the group's realized 5-session return magnitude in its bottom tercile (a vol bid with no follow-through). IV-rank recomputed per OPTIONS_ALPHA A5 (OTM/near-ATM BS inversion; NOT "match vendor IV30"). **Leg window: 2018→** (IV-rank needs a 252-session ATM-IV30 baseline; the recomputed IV series begins with the greeks era). Fires when both conditions hold on the same session.
- **L3 — P/C-OI collapse-into-strength** (`pcoi_collapse_strength`).
  Definition: the group-mean **put/call open-interest ratio** falling ≥ 1 z (252-session) over a 5-session window **while** the group's 5-session return is positive (protection lifted into a rally = complacency). **OI uses `oi[t-1]` — the OI timing law; same-day OI is a build-breaking bug** (OPTIONS_ALPHA §2.4, O_OPT §8.1). **Leg window: OI history begins 2012 → first usable 5-session-slope-on-252-baseline z ≈ 2013→**; but this battery's **primary window is 2018→** (§3) so L3's pre-2018 span is reported only as an era-robustness read, never as primary. Fires when the z-drop threshold is met with positive concurrent return.
- **L4 — ETF-flow rolloff** (`etf_flow_rolloff`).
  Definition: `engine/theme_flow_rollup.theme_flow(region='us')`'s **`divergence == True`** for the held group's theme (`flow_score < 0` while basket rel-price flat/up), OR `flow_score` crossing below 0 with `n_covered/n_members ≥ _MIN_COVERED_FRAC` (0.10). **Explicitly labeled 1–5 day lag on every surface** (module header; R3) — this leg CANNOT claim lead tighter than its own reporting cadence. **No thetadata dependency**: L4 reads the holdings-flow store, so it can run **independently of `data/thetadata_eod/` manifest completion** — but it still waits for ratification. **Leg window: bounded by ETF-holdings history**, stamped at run time.

### 2.3 The outcome currency (frozen — the SELL base-rate machinery)

- **Label:** forward **63-day excess-vs-SPY** of the held group (sector-ETF), direction consistent with the SELL/avoid frame (a *negative* excess is the exhaustion payoff). Secondary horizons **21d** (rotational class) and **5d** for robustness. Absolute-63d reported beside excess (the sector_signals dual, lines 66–70).
- **Benchmark (the outcome currency):** the fire-conditioned forward-63d excess is compared against the **live `STATE_BASE_RATES["SELL"]` dict** (`exc63=−1.24, hit=40, n=169`), reusing the **`oracle_gauntlet_p3.py` B2 machinery verbatim** (§1) with its "informative only — different universe granularities" caveat. **An exhaustion leg earns DISPLAY-WITH-EDGE only if its fire-conditioned forward excess is *more negative* than the SELL base rate at adequate power AND clears the placebo/FDR gauntlet.** Matching the base rate is not an edge; the leg must sharpen it.
- **Safety-net axes (SETUP_SPECIES §1, the species grading currency):** every leg additionally prints the terminal-state partition on the **held names** — **stop-out rate**, **dead-money rate**, **cushion incidence** (cumulative-incidence with stop-out as competing risk — NEVER a median over reachers, §1 lines 114–121), on the **`clean8_21`** (rotational) grid, with **`clean15_126`** (positional) printed as context. Framing: an exhaustion fire that *raises stop-out / dead-money incidence* on held names is the exit-side payoff. These are **context beside the base-rate verdict, never the gate by themselves** (banned-verdict-metrics list, §1 lines 141–145).

### 2.4 Coverage & concentration handling (binding)

- **`coverage_g(t) = |M_g(t) ∩ gex_symbols()| / |M_g(t)|`** per held group per session. Group-sessions with `coverage_g < 0.40` are nulled and excluded, counted in a **"coverage-dropped" tally reported alongside n** (O_OPT §2.4 precedent).
- **Sector-ETF confirmer:** the group's own sector ETF is a single liquid instrument with full options coverage — its L1/L2/L3 legs are always available at sector tier even when member breadth is thin. **The sector tier is therefore the primary tier.**
- **Concentration penalty:** any group-session where one member supplies > 60% of options notional is down-weighted toward 0 (O_OPT §2.2 feature 4 precedent).

---

## 3. Eras & primary window (proposed — frozen on ratification)

**Primary window = 2018→** (roadmap R3: exit-overlay Phase-0 is registered 2018→; the L1/L2 greeks-⋈-volume join is only available after the 2017 greeks warm-up). L3's OI history extends to 2013 but is used pre-2018 only as an era-robustness read, never primary.

**Mandatory era splits** (reported for every gated cell; matching OPTIONS_ALPHA R2 IV/greeks-dependent partition):
- **2018-19** (pre-COVID) — **2020-22** (COVID + rate shock) — **2023→** (modern).

A claim alive only in a single era is dead (era-consistency G4). L3's OI-only extension may additionally report **2013-17** as a fourth, non-primary era bucket (stamped "pre-primary, OI-only, robustness").

**n-honesty (pre-stated):** the long-set is the board `buy[]` roster, and the board ledger's dated history is short (`snapshots.jsonl` runs ~2024-06→2026-07 in the current file). **This is the binding power constraint:** board-conditioned fire counts are expected small-n, and **the primary conditioning may need to fall back to the sector-ETF SELL/avoid-state universe** (the 1998–2026 calibration domain) with a board-membership *tag* rather than a hard board filter — a fork Fable must rule (see §6, OPEN-1). Any cell below its power floor (§4) is **ACCRUE, not KILL**.

---

## 4. Claims, statistics & kill criteria (proposed — CI-includes-0 style)

Each leg declares a PRIMARY pre-declared statistic; the G1–G4 + BH-FDR battery follows O_OPT/P3 exactly. Thresholds below are the **proposed gated primaries**; per the O_OPT R1 precedent, **±0.25 (or ±10-percentile for rank thresholds) neighbors are REPORTED as ungated sensitivity curves** — a primary passing while both neighbors fail is flagged **fragile** and capped at DISPLAY-WITH-NULL.

### EXIT-CROWD-L1 — Short-dated OTM call-share spike (crowding)
**Claim.** In held groups, sessions where `crowd_call_share_z ≥ +1.5` are followed by forward-63d excess **more negative than the SELL base rate** (−1.24%).
**PRIMARY statistic:** fire-conditioned direction-adjusted forward-63d excess mean, with block-bootstrap 90% CI, compared to −1.24% via the B2 machinery; G1 placebo-p95 + G2 bootstrap-CI + G3 regime strata (VIX high/low, SPY-200d) + G4 era-consistency (3/3 era means same sign) + BH-FDR.
**KILL if:** the fire-conditioned-minus-base-rate delta bootstrap 90% CI **includes 0 at n ≥ 60 fires** (adequately powered and no sharpening over the price-only base rate). **n < 60 → ACCRUE** (register + `come_back_on`).

### EXIT-CROWD-L2 — IV-rank blowout × weak price response
**Claim.** Sessions with `iv_rank ≥ 90` AND bottom-tercile 5-session return, in held groups, precede forward-63d excess more negative than the SELL base rate.
**PRIMARY statistic:** as L1, on the joint-condition fire set.
**KILL if:** delta-vs-base-rate CI includes 0 at **n ≥ 60**; else ACCRUE.

### EXIT-CROWD-L3 — P/C-OI collapse-into-strength (complacency)
**Claim.** Sessions where the group P/C-OI ratio drops ≥ 1 z over 5 sessions **into** positive concurrent return precede forward-63d excess more negative than the SELL base rate. **`oi[t-1]` throughout.**
**PRIMARY statistic:** as L1.
**KILL if:** delta-vs-base-rate CI includes 0 at **n ≥ 60**; else ACCRUE. (OI-only 2013-17 era reported as robustness, never a gate.)

### EXIT-CROWD-L4 — ETF-flow rolloff (institutional trim, 1–5d lag)
**Claim.** Held groups whose `theme_flow.divergence == True` (or `flow_score` crossing < 0) precede forward-21d **and** 63d excess more negative than the SELL base rate, **at a labeled 1–5 day lag** (the leg cannot claim lead tighter than its reporting cadence).
**PRIMARY statistic:** fire-conditioned direction-adjusted forward-21d excess (PRIMARY, matching the flow cadence) + 63d, delta-vs-base-rate, G1–G4 + BH-FDR. **The lag label is printed on every cell; no "L4 leads" claim below 1 session is permitted** (O_OPT O6-v coincident-labeling law).
**KILL if:** delta-vs-base-rate CI includes 0 at **n ≥ 60**; else ACCRUE.

**Min-n floors (pre-stated):** every leg's gate needs **n ≥ 60 fires** (the house ~60 floor). Two-way-conditioned cells (leg × era) inherit the ACCRUE-not-KILL rule below their per-era floor (≥ 20/era to report an era mean; a cell < 20 prints as context only).

---

## 5. Placebo (proposed — reuses O6/P3b machinery)

Every leg runs against **matched non-event group-days**: sector-group-days where the group **is held** (in `buy[]`) but the leg did **not** fire, **regime-matched** (same VIX/SPY-200d strata) and **duration-matched**, drawing **200 pseudo-fires** with **`exclusion_zone = 10` sessions** (a placebo day may not fall within 10 sessions of a real fire), exactly the `data/oracle/gauntlet/p3b_routing_placebo.json` spec. Cells with fewer real fires than the placebo can support are flagged **`insufficient_placebo:true`** and stay pre-FDR candidates. The placebo furnishes each leg's **`placebo_p95`** — the G1 threshold. **The held-but-not-fired matched set is the correct null: it isolates the leg's marginal signal over merely being long the group.**

---

## 6. What this pre-reg does NOT do (pre-committed rejections) + OPEN forks

**Pre-committed rejections:**
1. **No signed legs.** Only unsigned/share/absolute legs (L1–L4). Net-signed premium, aggressor-signed flow, and any `direction_reliable` claim enter **by amendment only, after T2a exists** (R3; OPTIONS_ALPHA §2.2 signing gate). Tone stays neutral/`~`.
2. **No hard gate into any engine on pass.** DISPLAY-WITH-EDGE → board exit-side annotations + a crowding/exhaustion display board (roadmap P3.3) only. Never a hard sell-gate (China falsification).
3. **No same-day OI.** L3 uses `oi[t-1]` always; same-day OI = a build-breaking bug.
4. **No sub-30-date / 60-date half-gates** (OPTIONS_ALPHA A3). A leg either clears at the primary window's real power or ACCRUEs; no provisional light verdict.
5. **No invented composite.** L1–L4 are reported as **separate legs**; any fusion into a single "exhaustion score" must beat the equal-weight-of-legs baseline in a *separate* registered trial (O_OPT §6.1 no-laundering law).
6. **No per-name promotion.** The group/sleeve is the unit; per-name overlays stay context (SETUP_SPECIES W1-S13 precedent).
7. **No BUY-side claim.** This battery is exit-side only; any entry/accumulation flow claim is its own future prereg (this is the substance of the house prediction, §0).

**OPEN forks for Fable (must be ruled before freeze):**
- **OPEN-1 (power fork).** The board `buy[]` history is short (~2024-06→). Does the long-set stay a **hard board filter** (small-n, ACCRUE-likely), or fall back to the **sector-ETF SELL/avoid-state universe** (1998–2026, powered) with board membership as a *tag*? Recommended default: **run BOTH** — sector-ETF universe as the powered PRIMARY (domain-matched to the −1.24% base rate), board-filtered as a watermarked secondary that can never promote alone. Fable rules.
- **OPEN-2 (era count).** Adopt L3's 2013-17 OI-only bucket as a reported fourth era, or drop it? Recommended: **report, never gate.**
- **OPEN-3 (L4 independence).** L4 has no thetadata dependency — may it run at ratification while L1–L3 wait for manifest-complete (R8)? Recommended: **yes, L4 runs first** (it is the cheapest exit evidence and the house prediction's front-runner).

---

## 7. FDR family & trial ledger (proposed — frozen on ratification)

**EXIT-CROWD joins the OPTIONS_ALPHA registered family** (the options-alpha program's multiplicity accounting; OPTIONS_ALPHA_MASTERPLAN §2 doctrine — "reliable family… no wave may depend on flow direction," §1 lines 71-73). BH-FDR (q ≤ 0.10) is applied **within the EXIT-CROWD gated sub-family**, mirroring P3's within-section FDR, and the count adds to the program-level accounting.

**Proposed registered gated-trial count** (every leg × era cell that gates):
- **L1** — primary-63d: 1 pooled + 3 era = **4**.
- **L2** — 1 pooled + 3 era = **4**.
- **L3** — 1 pooled + 3 era = **4** (2013-17 bucket = display-only, NOT counted).
- **L4** — 21d PRIMARY: 1 pooled + 3 era = **4** (63d = 4 robustness cells, NOT gated).

**Gated FDR family total = 4 + 4 + 4 + 4 = 16 gated trials.** 5d/63d-secondary and sensitivity-curve neighbors (R1) are explicitly outside the family and cannot gate. **The exact count is fixed by THIS document on ratification — no result-dependent trial-count choices remain.** The count is stamped into the ledger at run end (pure append; seed inherited from the options-alpha family).

---

## 8. Validation constitution (binding on ratification)

1. **OI timing law.** L3 uses `oi[t-1]`; same-day OI = bug (OPTIONS_ALPHA §2.4).
2. **Signing provenance.** Every leg carries `signing_source`; only unsigned legs run in Phase-0. Mixed-source aggregates forbidden. Signed legs enter by amendment.
3. **Reconstruction labeling.** IV-rank / any chain-derived quantity is `reconstructed:true`, recomputed per OPTIONS_ALPHA A5; live-vs-reconstructed divergence on any overlap is a blocking audit finding.
4. **Era discipline.** 2018-19 / 2020-22 / 2023→ era means printed for every gated cell; a claim alive in one era is dead.
5. **FDR family.** §7 — joins the options-alpha registered family; BH q ≤ 0.10 within the EXIT-CROWD sub-family.
6. **Placebo law.** §5 — held-but-not-fired matched non-event group-days, 200 draws, exclusion_zone=10, regime+duration matched.
7. **Survivorship stamps.** The board ledger is `powered=false` / survivorship-INFLATED (`studies.json`); every board-conditioned n carries the caveat that positives are optimistic until the deep+PIT panel confirms (§2.1, §3). L4's ETF-holdings coverage is sparse-by-design (`_MIN_COVERED_FRAC=0.10`) and stamped.
8. **Detection-lag honesty (O6-v).** L4's 1–5d lag is printed on every surface; no leg claims a lead tighter than its reporting cadence; k≈0 findings labeled *coincident*, never "leading."
9. **Outcome-currency honesty.** The −1.24% SELL base rate is a **cross-granularity** benchmark (sector-ETF domain vs board/group domain); the B2 "informative only — different universe granularities" caveat is carried on every base-rate comparison. Matching the base rate is NOT an edge.
10. **CI-enforced language.** "validated" stays CI-guarded and is claimed nowhere in this draft; new UI strings ship EN+ZH; no title-attr translations (`data-tip-en/zh` popovers; `check_title_i18n`); zh up/down color token flip applies; jinja new keys guarded with `is not none`.
11. **Data-dependency law (R8).** The RUN (roadmap P4.4) begins ONLY after (a) Fable ratifies this document, AND (b) `data/thetadata_eod/_manifest.json` marks the universe pass complete (`n_roots` at target, `updated_at` non-null) for L1–L3. **L4 may run at ratification** (no thetadata dependency), pending OPEN-3. No harness reads `data/thetadata_eod/` mid-backfill.

---

## 9. What passing / failing means (proposed)

- **DISPLAY-WITH-EDGE** (a leg clears G1–G4 + BH-FDR AND sharpens the SELL base rate on the primary window) → board exit-side annotations + the crowding/exhaustion display board (P3.3). Never a hard gate; wiring into any score path requires a subsequent pass under the engine's own gauntlet.
- **DISPLAY-WITH-NULL** (fails FDR but not KILL) → the null is printed on the page.
- **KILL** (meets a §4 kill criterion at adequate power) → leg dead; recorded; not displayed as an exhaustion candidate.
- **ACCRUE** (right direction, n below floor) → registered with a `come_back_on` date tied to board-ledger accrual + (for signed legs) the T2a/signing-gate re-pass.

**Honest prior (pre-stated, falsifiable — the house prediction):** **the SELL / exhaustion side (L1–L4) validates before any BUY-side / accumulation flow signal does.** Within the exit side, the cheapest evidence — **L4 (ETF-flow rolloff) and L1 (call-share crowding)** — is expected to sharpen the SELL base rate before L2/L3. If the gauntlet returns "exit no," that null is printed, not hidden, and the house prediction is recorded as refuted.

---

## 10. Registry & wiring

Proposed experiment id **`exit_crowding_phase0`**. Per the O_OPT R2 precedent, the `data/experiments/registry_seed.json` append lands with the **runner PR (P4.4)**, not this doc-only draft — prereg validity will derive from the **ratified** document's commit timestamp, not from this DRAFT. **No wiring into any live engine or board in Phase-0** — reports + display-only annotations only. No result-dependent choices remain once Fable ratifies and the DRAFT banner is removed.

---

## 11. Status log

| Date | Event |
|---|---|
| 2026-07-04 | **RATIFIED by Fable** (rulings F1–F5 in §0.1): sector-ETF PRIMARY lane / board-tag SECONDARY (F1); 2013-17 robustness-only (F2); L4 runs now PRE-FDR-interim (F3); long-set = buy[] roster membership (F4); L2 IV-rank from vendor implied_vol (F5). Registration effective this commit. |
| 2026-07-04 | **DRAFT authored** (Opus, roadmap P1.3 / ruling R3). Census off `engine/sector_signals.py` SELL base rate, `data/us_board_ledger/snapshots.jsonl` long-set schema, `engine/theme_flow_rollup.py` L4 source, `scripts/oracle_gauntlet_p3.py` B2 machinery, `data/thetadata_eod/_manifest.json` (n_roots=0, pass NOT complete). **NOT registered — awaits Fable ratification.** Open forks OPEN-1/2/3 flagged for adjudication. Blocked on: Fable ratify → then P4.4 RUN after `_manifest.json` universe-pass-complete (L1–L3) / at ratification (L4, pending OPEN-3). |
