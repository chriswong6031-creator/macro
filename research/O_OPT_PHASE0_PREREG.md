# O-OPT — Options-Tape Pressure × Rotation Episodes — PHASE-0 PRE-REGISTRATION

**Battery:** O-OPT (Oracle P7 pulled forward; LIVE_ORDER_FLOW_BRAINSTORM §5.1). **Phase:** Oracle Phase-0-Options. **Branch:** `oracle-oopt-phase0`.
**Author:** Oracle research agent (Opus) off the frozen episode-catalog schema; **adjudicated + ratified by Fable 2026-07-04** (rulings R1–R3, §0.1). **Status:** PRE-REGISTERED — committed BEFORE any options↔episode join is run, and BEFORE the `data/thetadata_eod/` T1 backfill exists (STOP-D6 honored: pre-registration needs the frozen episode schema, which now exists; it must NOT wait for or peek at the joined options data).
**Constitution:** inherits **Oracle O6** (validation constitution) + **OPTIONS_ALPHA doctrine §2** + **LIVE_ORDER_FLOW §8** (tape-specific additions). Gate battery = Oracle P3's **G1–G4 + BH-FDR** on the registered trial ledger. Verdicts: **DISPLAY-WITH-EDGE / DISPLAY-WITH-NULL / KILL / ACCRUE**. **No hard gate into any engine** on pass (China falsification, brainstorm §5.1). Fail → display-with-null per house law.

This pre-reg answers the brainstorm's honest prior (§9): options context is expected to **filter and confirm** rotations (O-OPT-2, P≈0.5–0.65) more reliably than it **leads** them (O-OPT-1, P≈0.3–0.4, "days per leg not weeks"). It is written so a null result is a legitimate, printed outcome.

## 0. In plain English

Oracle already catalogs every sector rotation since 1998 from *price* alone — money leaving one group, entering another, detected in three tiers (early → confirmed → undeniable). This test asks a separate, independent data source — the **options tape** (put/call premium, open-interest builds, implied-vol shifts, aggregated across the liquid members of each group) — four questions:

1. Does options pressure show up **before** the price detector fires? (lead-lag — the weakest bet)
2. Does options pressure **separate the rotations that persist from the ones that fizzle**? (the confirmation bet — the strongest)
3. Does destination-group options pressure **improve where-does-money-go routing**?
4. Do **two-sided** rotations (puts building in the group money leaves, calls in the group it enters) persist better than one-sided ones?

Everything ships display-only until it passes the same gauntlet Oracle's own price claims passed. The honest expectation, written before we look: **confirmation and exit-side signatures validate before any "options lead price" claim does.**

### 0.1 Fable adjudication rulings (2026-07-04)

- **R1 — Threshold sensitivity adopted.** Every pre-declared threshold in §4 (+1.0 flow-onset composite z; +0.5 pressure / ≥0.5 breadth confirmation split; +0.5 opposed-flow) is the GATED primary. A **sensitivity curve at ±0.25 neighbors is REPORTED as unregistered robustness** — not gated, not FDR-counted. A primary that passes while BOTH neighbors fail is flagged **fragile** and capped at DISPLAY-WITH-NULL. (C1 hysteresis-rigor precedent, without inflating the trial family.)
- **R2 — Registry append deferred to the runner PR.** The `data/experiments/registry_seed.json` entry (`oracle_oopt_phase0`) lands with the runner implementation PR, not this doc-only PR (the registry file is concurrently owned by an in-flight program; prereg validity derives from THIS committed document's timestamp, not the registry row).
- **R3 — Schema corrections ratified.** Tier M begins **2022-02-08** (not "2021" as the brainstorm/masterplan said); source/sink complex identity joins through `rotation_groups.json` + `graph.py::COMPLEX_ETF_MAP` (episode rows carry no complex column); the P3 trial-ledger/placebo machinery is reused verbatim; the ≤400-name options-universe cap makes the §2.4 coverage law binding.

## 1. Data state STAMP (exact local state read for this battery, 2026-07-04)

- **`data/oracle/episodes_s.parquet`** — the FROZEN Tier-S (sector) episode catalog. **749 rows**, onset range **1999-08-04 → 2026-06-29**. Nodes = the **11 sector ETFs** (`XLB XLC XLE XLF XLI XLK XLP XLRE XLU XLV XLY`). `survivorship_flagged` all False (ETF-level, survivorship-clean). Columns frozen and enumerated in §2.1.
- **`data/oracle/episodes_m.parquet`** — the FROZEN Tier-M (subsector/theme) catalog. **5,653 rows**, onset range **2022-02-08 → 2026-07-02**, 354 nodes, `survivorship_flagged` **all True** (reconstructed from current membership; masterplan §2 Tier-M watermark). **SCHEMA STAMP: earliest onset is 2022-02-08, NOT 2021** — there are zero pre-2022 subsector episodes to test.
- **`data/oracle/rotation_groups.json`** — the hand-named complex backbone (V1). Complexes `ai_compute, software, …` each with `members` (panel_m node names) + `risk_sign` (`risk_on`/`risk_off`). **This is where source/sink COMPLEX identity lives — the episode rows carry no complex column.**
- **`engine/oracle/graph.py :: COMPLEX_ETF_MAP`** — maps Tier-S sector ETFs → complexes (per `rotation_groups.json._meta`). The Tier-S node→complex join for O-OPT uses THIS map.
- **`data/oracle/gauntlet/p3_trial_ledger.json`** — the registered trial ledger O-OPT joins. Row schema: `trial_id, type, direction, tier, horizon_d, section, p_value, bh_rejected, n, direction_adjusted_mean`. Seed `20260704`.
- **`data/oracle/gauntlet/p3_results.json`** — the gate battery: per-trial `g1_pass..g4_pass`, `placebo_p95`, `boot_ci_lo/hi`, `boot_p_value`, `era_means`, `strata_means/ns`, `bh_rejected`, `bh_q_value`.
- **`data/oracle/gauntlet/p3b_routing_placebo.json`** — the routing placebo: **200 draws**, `exclusion_zone=10`, regime-matched, `insufficient_placebo` flag; cell schema `src, dest, regime, horizon_d, n_real, real_mean, placebo_mean, placebo_p95, g1_routing_pass, was_bh_rejected`.
- **`engine/options_universe.py`** — the options universe resolver: anchors (`SPY QQQ IWM DIA NVDA AAPL TSLA AMD META MSFT`) ∪ active basket members, **capped at `max_underlyings=400`**. This defines which single names have options features → the coverage limitation §2.4 addresses.
- **`data/thetadata_eod/`** — **DOES NOT EXIST YET** (plumbing merged #1273; store pending subscription). The planned T1 EOD-chains store (brainstorm §7.2: chains + OI + IV + EOD Greeks, options_universe + sector/index ETFs + SPX, 2012→, ~30–80 GB, R2). Every options feature in §2.2 is defined *against this planned store*. This pre-reg is committed before it lands. **The single-name signed-flow features additionally require the T2a feature store with `signing_source=tape` — brainstorm §7.2 T2a, 2021→ first.**

## 2. Constructions (exact, frozen)

### 2.1 The episode catalog columns this battery reads (frozen, verbatim from the parquet)

`episode_id` (str), `node` (str), `direction` ∈ {`in`,`out`}, `onset_date`, `confirmed_date`, `undeniable_date`, `exhausted_date` (datetime64[ms]), `duration` (int), `peak_accel_z`, `breadth_at_onset`, `cohesion_at_onset`, `cohesion_chg_at_onset` (float), regime tags `regime_vix_pctile`, `regime_tlt_sign`, `regime_spy_above_200d` (float), `two_sided` (bool), `paired_episode_id`, `survivorship_flagged` (bool), `pairing_unavailable` (bool).

**Outcome / label family** (the sink-vs-source forward-RS spread, per detection tier):
- `outcome_rs_5d`, `outcome_rs_21d`, `outcome_rs_63d` — forward RS spread from **onset**.
- `outcome_rs_{H}d_confirmed`, `outcome_rs_{H}d_undeniable` — same, measured from the confirmed / undeniable detection dates.
- `outcome_mature_{H}d[_confirmed|_undeniable]` (bool) — the window **matured** (was not truncated by store end). **A label is only used where its `outcome_mature_*` mask is True.**

**Detection tiers** are the three date columns (`onset_date`, `confirmed_date`, `undeniable_date`), matching the P3 ledger's `tier ∈ {onset, confirmed, undeniable}`. `undeniable_date` is `NaT` for episodes that never reached that tier — handled by the maturity mask.

### 2.2 The daily per-group options features (frozen definitions)

All features are computed **per node-group per session** from the planned `data/thetadata_eod/` T1 store (+ T2a signed-flow features where noted), then aggregated to the episode's node/complex. Each feature carries `signing_source` and `reconstructed` provenance stamps (§8).

For a group `g` (a sector-ETF complex on Tier S, a subsector/theme on Tier M) with liquid optionable member set `M_g(t) ⊆ options_universe`:

1. **`src_put_prem_z`** (source-complex put-premium z) — cross-member mean of each member's daily **put premium** (Σ put trade notional, `signing_source=tape`, aggressor-signed, EOD) standardized to a **252-session** rolling z per member, then group-averaged. Source-side pressure = puts building where money is leaving.
2. **`snk_call_prem_z`** (sink-complex call-premium z) — identical construction on **call premium**, sink side.
3. **`src_doi_put`, `snk_doi_call`** (ΔOI builds) — group-mean of member **ΔOI** (put side for source, call side for sink) using **`oi[t-1]`** (OI timing law §8.1), 5-session persistence-weighted (sign-consistent builds over the window), z-scored to 252-session member baseline.
4. **`flow_breadth_g`** (flow breadth, concentration-penalized) — the **fraction of `M_g(t)` members confirming** the directional signature (put z > 0 source / call z > 0 sink), multiplied by a concentration penalty `(1 − HHI_notional_g(t))` where `HHI` is the Herfindahl of options notional across members. **A breadth reading where a single member supplies > 60% of group notional is down-weighted toward 0** (brainstorm concentration-penalty precedent).
5. **`etf_confirm_g`** (ETF confirmation) — the sector/theme **ETF's own** put/call-premium z and ΔOI (a single liquid instrument, no breadth needed) — the independent group-level confirm.
6. **`iv_term_z`, `iv_skew_z`** (IV term/skew shifts) — group-mean member **IV-term-structure slope** change (front-vs-back) and **25Δ risk-reversal skew** change, z-scored 252-session. Sink-side term lift (call demand) / source-side skew steepening (put demand).

**Signed features (`src_put_prem_z`, `snk_call_prem_z`, and their ΔOI mates) are EXCLUDED unless the re-calibrated signing gate has flipped `direction_reliable:true` for `signing_source=tape` (brainstorm §7.1).** Until then, O-OPT runs on the **unsigned** legs (total premium z, absolute ΔOI, IV term/skew, breadth of *activity*) and the signed legs are reported `~`-soft and NOT gated. This is stamped, not silently dropped.

### 2.3 The join window (frozen)

For each episode, join the group-options feature panel over **[−15, +15] sessions around `onset_date`** (the brainstorm's exact window). Trading-session indexed (not calendar). The window is clipped to the store span; an episode whose [−15,+15] window is not fully covered by `data/thetadata_eod/` (e.g. onset before 2012-06 + 15 sessions) is **DROPPED from the options-era sample** (no partial-window imputation). OI within the window always uses `oi[t-1]` (§8.1).

### 2.4 Coverage handling (the partial-coverage law — binding)

Options features exist only for optionable, liquid members in `options_universe.gex_symbols()` (capped at 400). Episode-group aggregation therefore covers a *subset* of each group's members. Pre-registered rules:

- **`coverage_g(t)` = |M_g(t) ∩ options_universe| / |M_g(t)|**, computed per group per session.
- **Suppression floor:** any group-session with **`coverage_g < 0.40`** is set to null and EXCLUDED from that episode's aggregation (brainstorm <40%-coverage suppression rule). An episode whose onset-window median coverage is < 0.40 is dropped from the options sample and **counted in a "coverage-dropped" tally reported alongside n**.
- **Concentration penalty** (§2.2 feature 4) applies within every retained group-session.
- **Tier-S sector ETFs are single instruments with full options coverage** — the `etf_confirm_g` leg is always available at sector tier even when member breadth coverage is thin. This is why the **sector tier is the validation tier**: its ETF leg is coverage-complete.

### 2.5 Node→complex join (frozen — no episode column exists)

- **Tier S:** `node` (an ETF) → complex via `graph.py :: COMPLEX_ETF_MAP`. Source complex = the `direction=out` episode's complex; sink = the paired `direction=in` episode's complex (via `paired_episode_id` where `two_sided`).
- **Tier M:** `node` (a subsector) → complex via `rotation_groups.json.complexes[].members`. `risk_sign` provides the risk-on/off polarity for the two-sided opposed-flow test (O-OPT-4).
- Episodes whose node maps to no complex are **single-node** studies for O-OPT-1/2 (feature aggregated over the node's own members only) and are **excluded from O-OPT-3/4** (which are complex-level).

## 3. Eras, tiers, and the primary window (frozen)

**Options era:** `onset_date ≥ 2012-06-01` (T1 backfill span).

| Tier | Catalog | Role | Options-era n (measured) | Survivorship |
|---|---|---|---|---|
| **S (sector)** | `episodes_s` | **VALIDATION tier — PRIMARY** | **435** | clean (all False) |
| **M (subsector)** | `episodes_m` | **DETECTION-RESOLUTION tier** | 5,653 (all ≥ 2022-02-08) | **FLAGGED (all True) — watermark** |

**PRIMARY window = Tier S, 2012→ (n=435).** All GO-eligible verdicts are earned here. Tier-M results ship **display-with-watermark only** and can NEVER promote a claim (masterplan §2, brainstorm §5.1).

**Mandatory era splits (reported for every Tier-S trial):** **2012-15** (n=78), **2016-19** (n=103), **2020-22** (n=124), **2023→** (n=130). A claim alive only pre-2016 is dead (§8.4). Tier-M has zero mass in 2012-15 and 2016-19; its era table is 2020-22 / 2023→ only, watermark-stamped.

**n-honesty (pre-stated):** Tier-S options-era n=435 is **above the ~60 floor** — the primary window is powered for the pooled test and every era bucket (min 78) supports an era read. But note: **O-OPT-1's lead-lag is measured per detection tier**, so the `undeniable`-tier subset is smaller (episodes that never reached undeniable are excluded — the P3 ledger shows `undeniable` n≈366 vs `onset` n≈391 pooled 1999→). **O-OPT-3/4 condition on two-sided pairs**, a further subset — those cells are expected small-n and stay **pre-FDR candidates** (§5).

## 4. Claims, statistics, and kill criteria (frozen)

Each claim declares a **PRIMARY pre-declared statistic**. Direction-adjusted means and the G1–G4/BH-FDR battery follow P3 exactly. **Per ruling R1:** every threshold below is the gated primary; ±0.25 neighbors are reported as ungated sensitivity curves; a primary passing while both neighbors fail is flagged fragile and capped at DISPLAY-WITH-NULL.

### O-OPT-1 — Flow-before-rotation (the lead-lag question)

**Claim.** In the [−15,+15] window, group-options pressure (source `src_put_prem_z` + `src_doi_put` + `iv_skew_z` steepening; sink `snk_call_prem_z` + `snk_doi_call` + `iv_term_z` lift; `flow_breadth_g`; `etf_confirm_g`) **leads** the catalog's early-tier (`onset_date`) price detection, per regime.

**Measurement.** For each episode, define the **flow-onset session** = first session in the window where the composite options-pressure z (equal-weight z-mean of the available legs — NO invented weights, §6) crosses a pre-declared threshold (**+1.0**) with 2-session persistence. **Lead = `onset_date` − flow-onset session**, in sessions (positive = flow leads price).

**PRIMARY statistic:** the **median lead** (sessions), with a bootstrap 90% CI (block bootstrap over episodes, `block=1` since episodes are near-independent), reported pooled and per regime (`regime_vix_pctile` high/low via median split). Secondary: **false-alarm discrimination** — AUC of the composite options-pressure z at [−15,0] separating *matured* episodes (`outcome_mature_21d`=True with `outcome_rs_21d`>0) from placebo pseudo-episodes (§5).

**KILL if:** median lead **≤ 0 sessions** vs the onset tier **AND** false-alarm AUC 90% CI includes 0.50 (no discrimination). (Both must fail — a coincident-but-discriminating signal is DISPLAY-WITH-EDGE labeled *coincident*, per O6-v: k≈0 lead is named for the quantity it routes, never called "leading.")

### O-OPT-2 — Confirmation quality (the false-alarm question) — HIGHEST-PROBABILITY CLAIM

**Claim.** Among early-tier (`onset_date`) detections, does flow-confirmation at onset **split persistent episodes from failures**, measured on the catalog's own forward-spread labels?

**Measurement.** Split the Tier-S options-era episodes at onset into **flow-CONFIRMED** (composite options-pressure z at [−5,+1] ≥ +0.5 with `flow_breadth_g ≥ 0.5` after concentration penalty) vs **flow-UNCONFIRMED**. Outcome = **`outcome_rs_21d`** (PRIMARY horizon; 5d/63d robustness), restricted to `outcome_mature_21d`=True and direction-adjusted (out episodes sign-flipped, per P3 `direction_adjusted_mean`).

**PRIMARY statistic:** the **confirmed-minus-unconfirmed direction-adjusted mean `outcome_rs_21d` delta**, with the P3 **G1** placebo-p95 test + **G2** bootstrap-CI (boot_p_value) + **G3** regime strata (VIX high/low, SPY-200d) + **G4** era-consistency (4/4 era means same sign), then **BH-FDR** across the O-OPT family.

**KILL if:** the confirmed-vs-unconfirmed `outcome_rs_21d` delta bootstrap 90% CI **includes 0 at n ≥ 60** confirmed episodes (i.e. adequately powered and null). If confirmed n < 60 → **ACCRUE** (underpowered, register + return), not KILL.

### O-OPT-3 — Routing-matrix conditioning

**Claim.** For source-complex outflow-onset cells (the routing matrix's "A breaks down → where does money go"), does **destination-complex call/ΔOI pressure in the first 1–5 sessions** improve routing hit rates?

**Measurement.** For each realized routing cell `(src_complex, dest_complex, regime, horizon_d)` with n_real ≥ threshold, split by destination options pressure (`snk_call_prem_z` + `snk_doi_call` z-mean over [0,+5] ≥ +0.5) and measure the **routing hit-rate delta** (dest-outperforms-source rate, high-flow minus low-flow), on the SAME `outcome_rs_{5,15}d` labels and the SAME routing-placebo machinery as `p3b_routing_placebo.json` (200 draws, exclusion_zone=10, regime-matched).

**PRIMARY statistic:** the **hit-rate delta per cell vs its regime-matched placebo p95** (`g1_routing_pass`), BH-FDR across sufficient cells. **Tiny-n cells (`n_real` below the P3 `insufficient_placebo` floor) stay pre-FDR candidates — reported, never gated** (P3b precedent: bootstrap rejections refused as small-n artifacts).

**KILL if:** across the sufficient cells, **zero cells** pass G1-routing after BH-FDR **AND** the pooled high-flow-minus-low-flow hit-rate delta CI includes 0. (A single surviving cell → DISPLAY-WITH-EDGE, watermark-capped, per P3b's outcome shape.)

### O-OPT-4 — Two-sided flow pairing

**Claim.** Two-sided episodes (`two_sided`=True, paired via `paired_episode_id`) with **opposed** flow signatures (puts building in source complex, calls in sink complex — `risk_sign`-consistent) persist better than one-sided or non-opposed pairs.

**Measurement.** Among `two_sided` Tier-S pairs, classify **opposed-flow** (source `src_put_prem_z` ≥ +0.5 AND sink `snk_call_prem_z` ≥ +0.5) vs not. Outcome = paired `outcome_rs_21d` (sink leg), matured-masked, direction-adjusted.

**PRIMARY statistic:** the **opposed-vs-not direction-adjusted `outcome_rs_21d` delta**, G1–G4 + BH-FDR.

**KILL if:** the opposed-vs-not delta CI **includes 0 at n ≥ 40** two-sided opposed pairs. n < 40 → **ACCRUE** (two-sided pairs are the scarcest cell — expected small-n).

## 5. Placebo (frozen — reuses O6 machinery)

Every episode-conditioned claim (O-OPT-1/2/4) and every routing cell (O-OPT-3) runs against **random-onset pseudo-episodes matched on regime + duration**, using the exact Oracle P3b machinery: **`data/oracle/gauntlet/p3b_routing_placebo.json`** spec — **200 draws, `exclusion_zone=10` sessions** (a placebo onset may not fall within 10 sessions of a real onset), regime-matched (same VIX/SPY-200d strata), duration-matched to the real episode's `duration`. Cells/claims with fewer real observations than the placebo can support are flagged **`insufficient_placebo:true`** and stay pre-FDR candidates. The placebo furnishes each claim's **`placebo_p95`** — the G1 threshold.

## 6. What this pre-reg does NOT do (pre-committed rejections)

1. **No invented composite weights.** The "composite options-pressure z" is an **equal-weight z-mean** of available legs (O-OPT-1). Any fusion beyond equal-weight must beat the equal-weight baseline out-of-sample in a *separate* registered trial (brainstorm §6.2 — no 0.55/0.30/0.10/0.05 laundering).
2. **No hard gate into any engine on pass.** DISPLAY-WITH-EDGE → Oracle panel columns + episode-card annotations + **confirmation-leg candidacy** only. A detection-tier confirmation input is added ONLY after passing under Oracle's O6 gauntlet, and is **never a hard gate** (China falsification).
3. **No signed-flow claim before the signing gate re-passes** for `signing_source=tape` (§2.2). Signed legs run `~`-soft and ungated until then.
4. **No same-day OI.** All OI is `oi[t-1]` (§8.1). Same-day OI in any feature = a build-breaking bug.
5. **No Tier-M promotion.** Tier-M results ship display-with-watermark; a Tier-M number NEVER earns a GO-equivalent (masterplan §2).
6. **No pre-2012 options-era episodes** (window not covered by T1). No sub-40%-coverage group aggregation (§2.4).

## 7. FDR family declaration & trial ledger (frozen)

**O-OPT joins Oracle's registered trial ledger** (`data/oracle/gauntlet/p3_trial_ledger.json`), as a new **section `O-OPT`** appended at run end (pure append, seed `20260704`). BH-FDR is applied **within the O-OPT gated family** (mirroring P3's within-section FDR), and the O-OPT trial count adds to the program-level multiplicity accounting.

**Registered trial count (every claim × era × tier cell this pre-reg commits to reading):**

- **O-OPT-1** — Tier S, PRIMARY horizon lead-lag: **1 pooled** + **4 era** + **2 regime** (VIX high/low) = **7 gated cells**. (Tier-M lead-lag: 1 pooled + 2 era, watermark, **NOT gated** — 3 display cells.)
- **O-OPT-2** — Tier S, confirmed-vs-unconfirmed at **3 horizons** (5/21/63d, 21d PRIMARY) × (**1 pooled** + **4 era**) = **15 cells, of which the 21d row gates**. Gated FDR slots = **5** (pooled + 4 era at 21d); 5d/63d = 10 robustness cells (H4/C1 nuisance-horizon precedent).
- **O-OPT-3** — routing cells: **all sufficient `(src,dest,regime,horizon)` cells** BH-FDR'd as one sub-family (count set at run time = number of cells clearing the `insufficient_placebo` floor; the count is stamped into the ledger). Pre-declared ceiling **≤ 90** (matching P3b's sufficient-cell count).
- **O-OPT-4** — Tier S two-sided opposed-vs-not, 21d PRIMARY: **1 pooled** gated + **4 era** display (era cells expected too thin to gate).

**Gated FDR family total = 7 (O1) + 5 (O2) + [≤90] (O3) + 1 (O4) = up to ~103 gated trials**, matching the order of P3's 109-trial family. The exact O3 cell count is fixed at run time by the coverage/placebo floors and stamped — **no result-dependent trial-count choices remain after this document is committed.** Sensitivity-curve neighbors (R1) are explicitly outside the family and cannot gate.

## 8. Validation constitution — tape-specific (binding, from LIVE_ORDER_FLOW §8)

1. **OI timing law.** Vendor historical OI is as-of the reporting date (published next morning); every join uses **`oi[t-1]`** for day-t signals. Same-day OI = bug.
2. **Signing provenance.** Every signed feature carries **`signing_source: tape|bar`** + the measured accuracy of its source. **Mixed-source aggregates are forbidden.** O-OPT uses `signing_source=tape` only for signed legs; bar-sourced flow is never mixed in.
3. **Reconstruction labeling.** Any GEX/wall/skew computed from vendor chains is **`reconstructed:true`** and must replicate the live collector's assumptions; live-vs-reconstructed divergence on the 2026-06-15→ overlap is a blocking audit finding.
4. **Era discipline.** All Tier-S claims report **2012-15 / 2016-19 / 2020-22 / 2023→** era means + post-publication-decay commentary. A claim alive only pre-2016 is dead.
5. **FDR family.** O-OPT-* joins the Oracle registered-trial ledger (§7).
6. **Placebo law.** Every episode-conditioned claim runs against random-onset pseudo-episodes (§5); the routing family against regime-matched random-onset cells.
7. **Survivorship stamps.** Tier-M claims carry the watermark until Tier-L confirms. Tier-S member-derived legs (breadth) honor PIT membership but are label-survivorship-bounded per `manifest.json`'s `sector_label_caveat`; the **ETF-level `etf_confirm_g` leg is survivorship-clean** and is the Tier-S primary confirm.
8. **Detection-lag honesty (O6-v).** Lag distributions per tier published; **k≈0 findings labeled *coincident*** and named for the quantity they route (drawdown/exposure/confirmation), NEVER "leading."
9. **CI-enforced language.** The word "validated" stays CI-guarded; new UI strings ship EN+ZH; no title-attr translations; direction tone stays `~` until the signing gate passes.

## 9. What passing / failing means (frozen)

- **DISPLAY-WITH-EDGE** (a claim clears G1–G4 + BH-FDR on the primary window) → new **Oracle panel columns** (O0 anticipates options columns), **episode-card annotations**, and **confirmation-leg candidacy**. Wiring into detection tiers happens ONLY after a subsequent pass under Oracle's own O6 gauntlet, and is **never a hard gate** (China falsification).
- **DISPLAY-WITH-NULL** (fails FDR but not KILL) → the null is **printed on the page** per house law (a legitimate outcome). The feature ships display-only with its null stamped.
- **KILL** (meets a §4 kill criterion at adequate power) → the leg is dead; recorded in the ledger; not displayed as a confirmation candidate.
- **ACCRUE** (right direction, underpowered — n below the claim's power floor) → registered with a `come_back_on` date tied to Tier-L accrual + the signing-gate re-pass; re-run when powered.

**Honest prior (pre-stated, falsifiable — brainstorm §9):** O-OPT-2 (confirmation) and the exit/crowding side validate before O-OPT-1 (lead) does; single-name signed-flow adds nothing after breadth/ΔOI/IV-rank are in the model; if any lead claim validates, it validates on **subsector breadth in high-VIX regimes first** (cohesion_chg stress-conditional precedent). If the gauntlet returns "confirm yes, lead no," that verdict is printed, not hidden.

## 10. Registry & wiring

Experiment id **`oracle_oopt_phase0`**, maturation = report-date (in-tree backtest over the frozen catalog once T1 lands) + forward-ledger accrual for the signed legs. `come_back_on` set for (a) the signing-gate re-pass (unlocks signed legs), (b) Tier-L maturation of the underpowered cells. **Per ruling R2, the `data/experiments/registry_seed.json` append lands with the runner PR** — prereg validity derives from this document's commit timestamp. **No wiring into any live engine or board in Phase-0** — reports + display-only panel columns only. No result-dependent choices remain after this document is committed.

## 11. Status log

| Date | Event |
|---|---|
| 2026-07-04 | Pre-registration authored (Opus research agent, census off frozen `episodes_{s,m}.parquet`) + Fable adjudication R1–R3. Committed BEFORE `data/thetadata_eod/` exists and before any options↔episode join. Blocked on: T1 backfill (subscription pending) + signing-gate re-calibration for signed legs. |
