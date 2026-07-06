# OPEX / Vanna / Charm — Fable adjudication of the Codex study (2026-07-06)

**Adjudicates:** `research/OPTIONS_OPEX_VANNA_CHARM_FINDINGS.md` (Codex/GPT-5.5-XH 30-minute
pass, 30 findings F-01..F-30) + `scripts/research/options_opex_vanna_charm_study.py` +
`reports/artifacts/options_opex_vanna_charm_{results.json,summary.md}` — all four ported from
the ephemeral Codex worktree into this repo by this PR (`#port from Codex` pattern).

**Adjudication apparatus:** (1) full inventory of the existing options stack (what already
exists vs what the study proposes), (2) independent Opus adversarial methodology review of the
script + JSON, (3) a Fable-commissioned robustness addendum actually run against the same
ThetaData store: `scripts/research/options_opex_vanna_charm_robustness.py` →
`reports/artifacts/options_opex_vanna_charm_robustness.{json,md}`.

---

## §0 Verdict summary

| Family | Findings | Verdict | Disposition |
|---|---|---|---|
| A — front-expiry concentration → future vol | F-05/06/10/18/23 | **SURVIVES vol/size control** (partial IC 0.06–0.13, sign-stable all eras; ~⅔ of raw IC was vol-persistence) | `front7_*_share` display-only columns + register `S-FRONT-CHARM` (§5); root-class caveat mandatory (sign flips in ETF slice by era) |
| A′ — signed charm pressure | F-03 | **REFUTED under control** (partial IC ≈ 0; 4/6 cells flip sign) | Not internalized; pure vol-proxy dressed as predictor |
| B — Greek intensity → lower vol | F-04/09/11/12 | **CONFOUNDED — charm flips sign under control**; gamma/vanna retain sign but semantics unresolved | Context-only; "depth cushions" narrative rejected; no feature, no bucket |
| C — vanna-relief vol compression | F-07/08/24 | **SOUND, strengthened** (partial ICs stronger than raw; re-confirmed inside ETF slice) | Register `S-VANNA-RELIEF` bucket (§5); build wave W-OVC |
| D — post-OPEX vol release | F-13/25 | **SUSPECT (Era3-only, ~4 roots/date)** | Watch item only; no bucket; re-look when Era4 exists |
| E — quad/roll states + calendar OPEX | F-01/02/14/26 | **REJECT as signal; keep as context** | `is_quad_cycle` stays a display flag; nothing new |
| F — ETF-vs-single-name split, pin/air-pocket | F-15/16/17/20 | **Phantom evidence → real slice run: pin real (3/3 eras) but NOT OPEX-specific (placebo ≥ pin); air-pocket dead** | Supportive prior on S-PIN_RISK root-class stratification; no S-INDEX-PIN bucket; F-16 killed |
| G — integration framing | F-21/22/27/28/29/30 | **ACCEPT (matches house law)** | Root-class metadata + total-vs-concentration doctrine adopted (§5) |

Bottom line: the study's stats hygiene is genuinely good (PIT-clean OI shift, HAC + pooled-era
BH-FDR, placebo weeks, sign-agnostic headline constructions), and its self-restraint (F-29/F-30:
display/shadow first, path-based promotion) matches house law. Its two fatal gaps: the headline
concentration→vol ICs carried **no control for current realized vol or size**, and five findings
cite an **ETF-only robustness slice that does not exist in the shipped script or JSON**. Both
gaps are closed by the robustness addendum in this PR; verdicts below reflect the corrected
evidence.

---

## §1 What already exists (redundancy map)

The Codex report proposes several things we already have. For the record, so no future agent
re-buys them:

| Proposed | Already exists as |
|---|---|
| `opex_phase`, `td_to_opex`, `td_since_opex`, `is_quad_cycle` | `engine/opex.py` (`tag()`, `snapshot()`), exported in `site/vol/regime.json`; `opex_days` in `options_entry_state`; `opt_opex_days` stamped on 95% of fires. NOTE: `opex_days` = calendar days, `opex.tag().td_to` = trading days — harmonize in W-OVC, don't duplicate. |
| OPEX pin state | `pin_risk` column (opex_days≤5 + long gamma + wall≤2%) + **already-registered `S-PIN_RISK` gate** (masterplan §4 W-C) |
| "Calendar alone is not tradable" (F-01/02) | `engine/opex.py` doctrine ("context only, never a buy/sell") — independent confirmation, nothing new |
| "GEX is context/barrier/vol regime, not direction" (F-11) | Masterplan §2 doctrine + W-E1 GEXR verdict (6/6 survive as vol context, sign flips by era) — confirmation |
| Vanna/charm computation | `engine/greeks.py` (`bs_greeks` returns vanna/charm), `engine/gex_engine.py` (net VEX/CEX, charm_anchor, charm_net_sign), `engine/options_hub.py` (per-expiry vanna_net/charm_net) — computed but never plumbed to state/tests |
| Dealer-sign convention | `engine/gex_engine.py` long-call/short-put, documented as unobservable assumption (audit #29) |

**Genuinely absent today:** front-expiry concentration shares (`front7_*_share`), signed
vanna/charm pressure as state columns, vanna-hedge-pressure (IV-move interaction), post-OPEX
carry-forward of prior expiry loading, and a formal `root_class` column (only a binary
`is_index_product` exists).

**Non-overlap with W-E1:** the 51-cell E1 gauntlet tested gamma-regime, skew, CW IV-spread, and
ΔOI only. Charm, vanna, expiry concentration, and put/call OI were never tested. The Codex study
is the first pass over that territory — this adjudication is not re-litigating E1.

---

## §2 Methodology review findings (Opus adversarial pass, Fable-verified)

**Held up:**
- PIT: OI `shift(1)` within contract; greeks same-day quote-derived with prior-day OI; forward
  windows start at t+1; `iv_chg5` spans t−5→t. No look-ahead found.
- HAC lags `max(auto, 2·horizon)`; BH-FDR pools all eras within each family (conservative — the
  era split *triples* hypotheses inside one correction rather than escaping it).
- Placebo calendar weeks and non-OPEX placebo states included and honestly reported.
- Families A/B survivors are `|·|`-share or `abs_*` constructions — **robust to dealer-sign
  inversion**. Family C's construction is convention-dependent (`vanna_hedge5 = −net_vanna ×
  iv_chg5`, and `net_vanna` carries the long-call/short-put sign), so its *mechanism narrative*
  inherits the dealer-sign assumption — but the state is a fixed measurable function of the
  chain and its era-stable association stands as measured. The weak, FDR-boundary rel-ret
  survivors depend on the convention outright.
- Report transcribes the JSON faithfully (spot-checked three headline numbers).

**Defects:**
- **D1 (fatal for Family F): phantom ETF slice.** The script invokes the cross-section and
  state tests exactly once each, on the full panel (`main()`, single `run_cross_section_tests` /
  `run_state_tests` call); the JSON has no slice key. F-15/16/17/20 and the proposed
  `S-INDEX-PIN` bucket cite output that does not exist. Not internalized as stated; replaced by
  the real slice in §3.2.
- **D2 (major, Families A/B): no vol/size control.** The only `rolling().std()` in the script is
  the *forward* target. Cross-sectional current-RV→future-RV IC is large and positive;
  `front7_*_share` mechanically loads currently-active short-dated chains and `abs_*` intensity
  is un-normalized notional (≈ mega-cap proxy). Closed by §3.1.
- **D3 (major): thin single-era states presented as findings.** `opex_front_charm_loaded`
  (+19.6pp RV) survives **only in Era3** (Era1 adj-p 0.50, Era2 0.16) on n_dates=57;
  `post_opex_prior_gamma_loaded` (+5.7pp) is Era3-only at ~4 condition-roots/date, adj-p 0.031,
  and its "prior loading" is ffill-carried up to a week stale. The report states neither
  cross-era failure. Both downgraded accordingly.
- **D4: calendar quad survivor is a dead regime, not an edge.** +0.57% (t=4.4) exists only in
  2005-2016 and the point estimate **reverses sign in 2017-2022** (−1.15%, unadjusted p≈0.013).
  Per house OOS doctrine this is the regime-death signature. F-01 is read as "calendar-only OPEX
  effects are dead in the modern era," which is also what the study itself concluded (F-02).
- **Cleared attack vectors, for the record:** state thresholds are per-date ranks or fixed
  shares (no full-panel quantile leak); FDR scope conservative; HAC lags adequate;
  vanna_relief state/target windows don't overlap.

---

## §3 Robustness addendum (run in this repo, same store: 174 roots, 2017–2026)

Artifacts: `reports/artifacts/options_opex_vanna_charm_robustness.{json,md}`. Descriptive
robustness — not a pre-registered gate; it informs which registrations proceed.

### §3.1 Vol/size-residualized partial ICs (Families A/B)

Method: within each date, pct-rank feature/target/controls; OLS-residualize feature rank and
target rank on `trail_rv20` (trailing 20d realized vol, ends at t) + `log_oi_notional`; Pearson
on residuals = partial Spearman IC; per-date ICs → HAC t, BH-FDR 10% within the addendum family.
Interpretation thresholds were pre-committed before results: Family A survives iff sign stable
in all three eras + BH-significant + Era3 retention ≥ ⅓ of raw IC.

**Control strength — the confound is enormous.** `trail_rv20 → fwd_rv5` cross-sectional IC =
**0.50 / 0.58 / 0.59** by era (t = 54–74). The study's headline 0.335 was competing against
this. Any un-residualized chain feature "predicting vol" must be presumed a vol proxy first.

**Results (fwd_rv5 target; abs_move_5d parallel throughout):**

| feature | Era1 raw→part | Era2 raw→part | Era3 raw→part | Era3 retained | verdict |
|---|---|---|---|---|---|
| front_week_charm_concentration | 0.146→**0.059** | 0.241→**0.077** | 0.340→**0.130** (t=17.8) | 0.38 | **SURVIVES** |
| front_week_gamma_concentration | 0.110→**0.052** | 0.196→**0.064** | 0.309→**0.113** (t=15.4) | 0.37 | **SURVIVES** |
| signed_charm_pressure (F-03) | 0.051→−0.003 | 0.106→0.018 | 0.144→0.003 | 0.02 | **REFUTED** (vol proxy) |
| charm_intensity | −0.135→**+0.058** | −0.135→**+0.055** | −0.063→**+0.099** | sign FLIP | **CONFOUND CONFIRMED** — raw finding was upside-down |
| gamma_intensity | −0.204→−0.162 | −0.203→−0.148 | −0.179→−0.215 | 1.20 | sign survives; semantics unresolved → context-only |
| vanna_intensity | −0.217→−0.214 | −0.223→−0.195 | −0.220→−0.279 | 1.27 | sign survives; semantics unresolved → context-only |
| vanna_hedge_pressure_5d | −0.031→−0.053 | −0.025→−0.049 | −0.032→−0.069 | 2.14 | **STRENGTHENED** (control unmasks it) |

Readings:
- **Family A**: real incremental vol information beyond persistence+size — but ~⅔ of the raw
  IC was confound. Ship as display state with honest magnitude expectations (partial IC ~0.06–0.13),
  not the 0.335 headline.
- **F-03 (signed charm pressure)**: partial IC ≈ 0, sign flips in 4/6 cells. The "strongest
  cross-sectional volatility predictor" claim was the confound speaking. Not internalized.
- **Family B**: `charm_intensity`'s negative-vol relation **reverses sign** once size+vol are
  controlled — F-04/F-09's "total depth is stabilizing" story is a size artifact. Gamma/vanna
  intensity keep their negative sign under control (genuinely not just size), but with charm
  flipping, intensity semantics are fragile family-wide → context-only, no narrative adopted.
- **Family C**: vanna-hedge pressure is *stronger* residualized than raw in every era — the
  opposite of a confound signature. Best-supported mechanism in the study.

### §3.2 Real ETF/index/sector slice (Family F replacement)

21 roots (SPY/QQQ/IWM/DIA/SPX + 11 SPDRs + SMH/SOXX/XBI/KRE/ARKK), `MIN_ROOTS_PER_DATE=12`,
same test harness as the study, BH-FDR within slice. 49,254 root-days.

- **Pin state (F-15) — CONFIRMED, 3/3 eras**: `opex_long_gamma_high_charm_pin → fwd_rv5`
  spread −3.57pp (t=−10.9) / −2.80pp (t=−3.9) / −2.97pp (t=−5.3); abs-move suppression
  parallel. n_cond 545–818 per era. The study's un-shipped claim happened to be right.
- **…but it is NOT an OPEX mechanism**: `placebo_long_gamma_high_charm_non_opex` suppresses
  at least as strongly (Era1 −3.57pp t=−14.9; Era2 −3.16pp; **Era3 −5.60pp > pin's −2.97pp**).
  Long-gamma + high-charm ETF chains = vol suppression *whenever*, OPEX week adds nothing
  incremental in the modern era. This folds into existing doctrine (GEXR = vol-conditioning
  context) rather than a new expiry mechanism; S-PIN_RISK's wall-proximity condition remains
  the only untested OPEX-specific differentiator, and it is already registered.
- **Air-pocket (F-16) — DEAD**: Era1 +1.60pp (adj-p 0.028, lone survivor), Era2/Era3 t = 0.6 /
  −0.1. Sign-unstable, no internalization.
- **Vanna-relief re-confirms within slice** (all eras, RV spreads −1.2 to −3.9pp, survive).
  Caveat honestly noted: `vanna_drag_sell_pressure` (the opposite-sign state) ALSO shows vol
  suppression in the slice — suggesting the operative variable is |vanna|×|IV-move| magnitude
  as much as its sign. The S-VANNA-RELIEF gate tests the flag as constructed; this symmetry is
  recorded as an interpretation caveat, not a blocker.
- **Root-class necessity now has a real artifact (F-17 vindicated)**: front-week charm
  concentration → RV is **negative** in ETF Era1 (−0.076) and **positive** in ETF Era3
  (+0.134) — sign-unstable by era within ETFs and different from the single-name-dominated
  full universe. `front7_*` states must not be interpreted without `root_class`.
- Put/call OI ratio: sign flips across eras within the slice (Era1 +0.13, Era3 −0.06) —
  F-12's "not a fear gauge" conclusion reinforced; stays dead.
- ETF-slice directional (rel_ret) survivors exist at small IC (e.g. signed charm Era3
  rel_ret_10d 0.083) but are single-slice, uncontrolled, and contradict the full-universe
  partial result — not internalized (consistent with F-21).

---

## §4 Rulings

- **RUL-OVC-1 (Family C — accept).** `vanna_relief_buy_pressure` (IV falling 5d × top-tercile
  vanna-hedge pressure) is a real vol-compression state: all three eras same sign, t ≈ −7.3 to
  −7.7, 27k–40k condition-obs, PIT-clean, sign-agnostic. It is a **holdability / de-escalation /
  stop-width** state, not an entry originator (no robust rel-ret edge — F-08 honest). Register
  `S-VANNA-RELIEF` per §5.
- **RUL-OVC-2 (Family B — context only).** Un-normalized Greek intensity is a size/liquidity
  proxy. The doctrine sentence worth keeping (and it is genuinely useful): **total-Greek
  intensity and front-expiry concentration are different objects — depth cushions, concentration
  exposes** (F-27). No feature ships without normalization; no bucket.
- **RUL-OVC-3 (Family A — accept as display state + gate).** Front-week charm/gamma
  concentration carries genuine incremental future-vol information beyond vol-persistence and
  size (partial IC 0.05–0.13, sign-stable all eras, t up to 17.8, BH-clean) — but ~⅔ of the
  study's headline IC was confound, and the ETF slice shows era-level sign instability within
  root classes. Therefore: `front7_abs_charm_share` / `front7_abs_gex_share` ship as
  display-only state columns in W-OVC **with `root_class` mandatory alongside**, and
  `S-FRONT-CHARM` is registered as a caution-family gate (§5). The honest expected magnitude
  is the partial IC, not the raw one. `signed_charm_pressure` (F-03) is explicitly NOT
  internalized — it is a vol proxy that dies under residualization.
- **RUL-OVC-4 (Family D — no bucket).** Era3-only, ~4 roots/date, stale-carry construction.
  Watch item in the program doc; nothing registered. Re-look if/when a fourth era boundary or a
  historical-fire reconstruction gives it a second independent sample.
- **RUL-OVC-5 (Family E — reject).** Quad states are sign-unstable across eras (the study says
  so itself, F-14); the lone calendar survivor is a dead 2005-16 regime (§2 D4). `is_quad_cycle`
  remains a context flag; no gate, no state, no seasonal rule.
- **RUL-OVC-6 (Family F — phantom evidence replaced; pin real but not OPEX-specific).** The
  study's cited slice had no artifact; our real slice (§3.2) shows: ETF long-gamma+high-charm
  vol suppression is real in all three eras (**supportive prior** for root-class stratification
  of the existing `S-PIN_RISK` grading), but the non-OPEX placebo suppresses at least as
  strongly — so this is dealer-positioning vol context (GEXR doctrine), not an expiry
  mechanism. Air-pocket (F-16) is dead (1 weak era, sign-unstable). `S-INDEX-PIN` is **not**
  registered: no new bucket for a mechanism already covered by GEXR context + S-PIN_RISK's
  wall-proximity test. F-17's root-class recommendation is upgraded to a formal `root_class`
  column in W-OVC — now with a real artifact behind it (front-week concentration sign-flips by
  era inside the ETF class).
- **RUL-OVC-7 (Family G — accept).** F-29/F-30 are restatements of house law (display/shadow
  until earned; path-based promotion: stop-out, liftoff, MFE, RV forecast — not directional
  return). Adopted as written; they cost nothing and bind future options waves to the same
  yardstick.
- **RUL-OVC-8 (naming/plumbing).** W-OVC must harmonize `opex_days` (calendar) vs `td_to_opex`
  (trading) rather than shipping both under ambiguous names, and must not duplicate what
  `engine/opex.py` already emits.

## §5 Registrations and build docket

**Registered now (masterplan §4 amendment, this PR):** `S-VANNA-RELIEF` and `S-FRONT-CHARM` —
see `research/OPTIONS_ALPHA_MASTERPLAN.md` §4 "OPEX/vanna/charm additions" for the
pre-registered gates, primitives, and the enlarged BH-FDR family statement (22 → 28 tests).

**Build docket W-OVC (Sonnet wave, separate PR(s), NOT built in this adjudication):**
1. `options_entry_state` new raw columns (display-only, RO-2 compliant — no composites):
   `front7_charm_share`, `front7_gex_share`, `signed_vanna_pressure`, `vanna_hedge_5d`
   (needs iv30 5d history + net VEX/CEX from gex payloads),
   `root_class` ∈ {index_etf, sector_etf, industry_etf, single_name}. Budget note: compute
   from existing polygon gex payloads / options_hub per-expiry aggregates where possible; any
   ThetaData read stays off the render path per render-budget law.
2. Stamp columns via the single-writer (`scripts/stamp_options_state.py`, A9):
   `opt_vanna_relief`, `opt_front7_charm_share`, `opt_root_class`.
3. Gate cells in `scripts/validate_options_entry.py` → `data/options_entry/gate.json`,
   `scored=false, building_history`, per the amended family statement.
4. Root-class stratification note on `S-PIN_RISK` grading (no new bucket; supportive prior
   per §3.2).
5. NW display surfacing (options_weather lobe / committee context) only after stamps flow —
   caution/de-escalation phrasing only (RO-3).

## §6 House-law compliance check

- **RO-2 (no fused composites):** every proposed column is a raw field; no
  `options_entry_quality_shadow` resurrection. ✓
- **RO-3 (caution-only):** vanna-relief and any OPEX state may only inform holdability /
  de-escalation / stop-width; never a short signal, never score origination. ✓
- **RO-11 (no kernel conditioning before NW clocks 2026-10 / ~2027-05):** nothing here touches
  kernels. ✓
- **A10 (ledger primitives are the only gate currency):** S-VANNA-RELIEF gate speaks
  `post_cushion_breach` / `terminal_state_clean8_21` / `fwd_mfe_21` only. ✓
- **Validate-before-score:** all registrations `scored=false`; display/shadow first (F-29 agrees). ✓
- **LLM non-origination:** unaffected — these are computed states, not LLM outputs. ✓

## §7 What was NOT internalized (kill list)

- `signed_charm_pressure` as a predictor (F-03) — partial IC ≈ 0 under vol/size control; the
  study's "strongest volatility predictor" was the confound.
- The "total Greek depth is stabilizing" narrative (F-04/F-09) — charm_intensity's sign
  *reverses* under control; the raw relation was a size artifact.
- `S-INDEX-PIN` as a new bucket (pin suppression is real in ETFs but not OPEX-specific —
  non-OPEX placebo ≥ pin; mechanism already covered by GEXR context + S-PIN_RISK).
- The air-pocket state (F-16) — 1 weak era, sign-unstable across eras.
- `S-QUAD-ROLL` (sign-unstable; context flag already exists).
- `S-POST-OPEX-RELEASE` (Era3-only, ~4 roots/date, stale-carry; watch item, no registration).
- Put/call OI ratio as anything (sign flips across eras in the ETF slice too).
- Any directional/return use of vanna/charm states (F-21: vol >> direction — agreed; the
  ETF-slice rel-ret survivors are uncontrolled and contradict the residualized full universe).
- The calendar quad-week "edge" (dead 2005-16 regime, sign-reversed in Modern).
