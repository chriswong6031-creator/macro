# Wave-6 pre-registration v2 — donor promotion + blocked-population DISCOVERY + HOLD tracker

> Fable, 2026-07-02 (v1) → v2 same evening after a 4-reviewer adversarial panel (2 FLAWED verdicts;
> findings + resolutions in §8; ZERO runs occurred under v1). DURABLE_BOTTOM_FRAMEWORK §2/§4 bind.
> v1's central error, on the record: the READMIT gate was INVERTED on its own fixtures — it opened
> on Tencent twice during the 2021 knife (index-level bear context lags the name by ~9 months) and
> was shut on MCD by late June (2W-turn recency expired; worse, MCD/KO's dips NEVER reach monthly
> oversold — dwell=0 — so the "fresh washout" leg did no work on the cases it existed to admit).
> Consequence: W6-B is DEMOTED from gate-confirmation to a wave-1-style STRATIFICATION DISCOVERY
> study. No W6-B board ship this wave; only feature promotions to a wave-7 gate candidate.

---

## 0. Corrected object model (from the panel's fixture computations)

- **MCD/KO-class (the owner's buys):** shallow dips (−5..−15% below the 200MA) in names whose
  MONTHLY momentum never registers the dip (completed-month StochRSI D stays ≥ ~25-50). These are
  "unbroken-cycle dips," NOT washout states.
- **Tencent-class (the knife):** a progressive decline that drives monthly D into oversold and
  pins it (dwell 1→16 months), goes entrenched below its own 200MA, and keeps manufacturing
  daily/3D crossovers all the way down.
- **The hard limit:** at the fire bar, an EARLY knife (Tencent 2021-05: dwell 0, index healthy,
  2W turn fresh) is near-indistinguishable from a shallow dip. Therefore the design goal is NOT
  first-sight clairvoyance — it is (a) discovering which bar-t features separate the two classes
  *as well as possible*, and (b) a **SERIAL-LOCKOUT ratchet** that admits at most the first fire
  of a knife and then shuts until a full washout-reclaim cycle completes. The −5% stop prices the
  first fire; the ratchet prevents fires 2..N (the actual Tencent capital destruction).

## 1. W6-A — donor-unwind promotion (recalibrated per statistics panel)

- Inference unit: the **donor-unwind EPISODE** (a maximal run of consecutive cracking days),
  cluster-bootstrapped at the episode level (the wave-5b name×63d clustering understates market-
  wide dependence; effective n ≈ episodes, expected O(15-40) over 2012-2026 — count reported).
- **G6a (recalibrated):** on E_FRESH entries (the product-relevant policy — the chip rides on all
  confluence entries): clean15(cracking) − clean15(intact) ≥ +2pp POINT on BOTH panels AND
  episode-clustered 90% LB > 0 on the deep panel AND per-name majority ≥ 52% (deep, names with
  ≥3 fires per cell) AND direction holds excl-2025 and both time halves AND ≥ 12 distinct
  cracking episodes contribute. (v1's P2×both-panels-at-+2pp-LB conjunction was unpassable-by-
  construction — baskets P2 point was +1.73pp; struck.)
- Ship if pass: market-wide context chip ("rotation: leader cracking/intact") + ledger fields,
  display-only; the SOLE statistical ship decision of this wave (family accounted: one).

## 2. W6-B — blocked-population discovery (stratification, wave-1 protocol)

**Population (honest replication of the live blocker — causality panel):** confluence fires where
`engine.signal_quality._buy_filter`'s below∧weekly-down path blocks: ¬above200 ∧ ¬w_bull (both on
the **3D grid exactly as signal_quality computes them**) ∧ NOT bearish-div-vetoed ∧ NOT saved by
the held∧reclaim escape (replicated at the next two 3D bars). Report the count under this honest
screen AND the naive daily `close<MA200` screen so the gap is visible. (The live gate does NOT
block sub-200 wholesale — a sub-200 fire in a weekly uptrend passes today; v1's population was
factually wrong.)

**Feature battery (each with a mechanism story; stratifiers, evaluated count-fair per wave-1 §4.3):**
- F1 distance-below-200MA bands (<8% / 8-18% / >18%, the BOTTOM_CONFIDENCE bands) + 200MA slope sign.
- F2 sigma-scaled decline speed: (252d-high drawdown) ÷ (ATR63% × √126) — "multi-sigma trend vs
  normal oscillation."
- F3 monthly registration: completed-month StochRSI D level (≥25 = cycle unbroken) and 3-month ΔD
  (freefall vs drift). STRICTLY-COMPLETED convention: monthly features are computed on the
  ME-native series, mapped by known-date (index.max), then shifted one bar so a month completing
  ON bar i is NOT visible at i; anti-repaint assertion carried from wave-5 §7.3 verbatim.
- F4 dwell_m as a MONOTONE CURVE (clean15/stop5 by dwell run-length; no hand bands — v1's ≤2/≥4
  cut sat on a smooth run-length distribution and was struck). Native-ME run-length, same
  completedness convention.
- F5 name-entrenched, H5-faithful: name's own close < its 200MA on ≥ 70% of the trailing 252d.
- F6 RS-vs-index 126d new-low flag (two-sided: may hurt MCD-class in rotation regimes — measured,
  not assumed).
- F7 turn evidence, two speeds: weekly stoch cross-up (fast) vs 2W cross (context; 2W grid on a
  FIXED GLOBAL fortnight phase — weeks since 1990-01-05 grouped in pairs — never per-name
  resample anchors). Lead + premium-over-trough REPORTED for every turn cell (the 2W leg measured
  ~1 month late on KO-2025; lateness is a named failure mode).
- F8 context: index bear_ctx (126d, ≥70% below index 200MA — a NEW feature, provenance honest,
  not "H5-style") and donor_unwind (wave-5b definition verbatim incl. min-members/top-rank guards).

**Pre-named composite candidates (evaluated after the singles, fixtures binding):**
- C-SHALLOW: F1-shallow ∧ 200MA-rising ∧ F3-unbroken (monthly D ≥ 25).
- C-LOCKOUT (the ratchet): state machine — OPEN until (F4 dwell ≥ 4 ∨ F5 entrenched ∨ F1-deep),
  then SHUT until monthly D exits oversold AND the name reclaims its 200MA (full cycle reset).
  Evaluated on SERIAL economics: per-name cumulative admitted-fire outcomes through knife windows.

**Fixtures (§4-style, run pre-panel as unit tests, REFRAMED):**
- Tencent 0700.HK 2021-01..2022-10: C-LOCKOUT admits ≤ 1 fire across the window AND is SHUT for
  ≥ 80% of it (including 2021-09-30, the mid-knife date v1 admitted). C-SHALLOW's admissions
  across the window are printed with dates and forward outcomes — honesty table, no hiding.
- MCD 2026-04-21..06-30 + KO 2024-12, 2025-09-08..2025-12: state tables printed per candidate
  with open/shut dates, premium-over-trough and lead where gradable. A candidate that never opens
  for ANY positive fixture is dead regardless of pooled stats; one that opens late gets its
  lateness printed (premium/lead), not excused.

**Promotion rules (to a wave-7 gate candidate; NOTHING from W6-B ships to a board this wave):**
favorable-vs-unfavorable stratum ≥ +5pp clean15 POINT with n ≥ 300 panel-wide per stratum side,
sign-stable on both time halves and ticker halves, stop5 not worse by > 2pp, ≥ 25 distinct 63d
blocks contributing; composites additionally pass their fixtures. Ties/near-ties resolve to the
SIMPLER leg (CHARTER §3). HK panel is adversarial context for every promoted feature (must not
invert sign there; it need not show the edge).

## 3. W6-C — HOLD tracker (product; owner-gated; corrected touch list)

- `hold_state` requires a NEW `engine/coiled.py` port of the wave-5 LAUNCHED/BROKEN/OBP state
  test (they exist ONLY in research/entry_timing/wave5.py — v1's "state fns exist" claim was
  false) + fixture tests (JNJ excluded, KO intact through its base).
- Surfaces: per-name library record (`site/stockdata/<T>.json` → stock.html) for ALL names incl.
  blocked ones, PLUS the standout-card chip for surfaced names. (v1's chip had NO surface for
  blocked names — the standout loop is alignment+entry_ok-gated upstream.)
- Live-anchor discipline carried from wave-5: computed on completed buckets; `provisional` flag
  (reuse sig.provisional pattern) when the current month/2W bucket is incomplete; anchor on
  signal_gate take_date; the wave-5 anchor-divergence ship-block rule applies.
- Fields: `hold_state`, `invalidation` (cycle trough ×0.97), `days_basing`, `donor_state`.
  grade_us_board `_extract` allowlist patch REQUIRED for gradeability. i18n dual-span chips.
  NOTHING touches BUYABLE_TIERS / setups.json / discovery / signal_quality.

## 4. Panels, inference, deliverables

Panels: deep US (211) + baskets (2,335) + HK adversarial (157, HSI context; CSI300 for any CN
follow-up — deferred). Axes/inference: wave-5 §4 verbatim (ATR co-primary, 90% clustered LBs,
name/block floors) with the W6-A episode-clustering addition. Deliverables: `wave6.py`
(`--selftest` = ALL fixtures incl. the Tencent lockout scan + completedness/anti-repaint
assertions), `WAVE6_REPORT.md`, gates/strata JSONs, ledger rows.

## 5. Degeneracy checks (symbolic + empirical, pre-compute)

- W6-B strata: every feature is computed from objects with NO shared predicate with the
  population screen (which fixes ¬above200-3D ∧ ¬w_bull); F1 shares the 200MA object but on
  bands/slope orthogonal to the binary screen — the population is a FIXED set, features partition
  it; no candidate equals the population or the empty set (fixtures prove both sides non-empty,
  and the statistics panel's ¬bear_ctx trap is addressed: bear_ctx is now a STRATIFIER whose
  within-¬bear_ctx decomposition is a required table, not a silent admit leg).
- C-LOCKOUT: its control is the population's serial economics; the ratchet strictly reduces
  admitted fires (proper subset; Tencent fixture proves strictness).

## 6. Multiplicity

One statistical ship decision (W6-A). W6-B produces promotions only (wave-1 precedent: promotion
≠ ship; wave-7 confirmation carries the ship burden with fresh gates). W6-C is a product decision
on already-measured objects. Family accounted.

## 7. What v2 deliberately does NOT claim

- No claim that any feature separates early-knife from shallow-dip at the fire bar (the panel
  showed Tencent-2021-05 passes every v1 leg). The lockout is the honest instrument for knives.
- No claim that MCD's June-end state stays "open" under turn-recency legs (it measured shut by
  06-19 under v1's turn2w) — turn-leg recency windows are part of what discovery must pick.
- No W6-B board surface this wave, period.

## 8. Amendment log (v1 → v2, panel 2026-07-02 late, pre-run)

| # | reviewer | severity | finding | resolution |
|---|---|---|---|---|
| 1 | causality | critical | Population factually wrong: gate blocks only ¬above200(3D)∧¬w_bull∧no-reclaim, not sub-200 wholesale | §2 honest replication on the 3D grid; naive-vs-honest counts reported |
| 2 | causality | critical | Daily-vs-3D grid mismatch between screen and blocker | Population + reclaim replicated grid-identical to signal_quality |
| 3 | causality | critical | dwell_m completedness unpinned; wave-1 ffill leaks month-end into bar i | §2 F3/F4: ME-native, known-date map, +1-bar shift = strictly-completed; assertion carried |
| 4 | causality | critical | 2W resample anchor is per-name phase + incomplete-bin label trap | Fixed global fortnight phase (weeks-since-1990 pairs); known-date + assertion |
| 5 | causality | major | bear_ctx mislabeled "H5-style" (H5 is 252d name-level) | F5 = honest H5 name-level 252d; index ctx = new feature, honest provenance |
| 6 | statistics | critical | G6a unpassable-by-construction (baskets P2 +1.73 < +2 bar) | Recalibrated on E_FRESH; P2-baskets clause struck |
| 7 | statistics | critical | Donor is market-wide → effective n = episodes, not fires | Episode-level clustering + ≥12-episode floor |
| 8 | statistics | critical | G6b +5pp-at-LB needs ~+9pp point — unpassable | W6-B demoted to stratification with wave-1 promotion rules (point +5pp, sign-stability) |
| 9 | statistics | major | ¬bear_ctx admit-leg = the bear-veto rebranded (wave-5 trap) | bear_ctx demoted to stratifier; within-¬bear_ctx decomposition a required table |
| 10 | statistics | major | Sub-200 vs above-200 parity not vol-matched | ATR axes co-primary for any parity read; parity deferred to wave-7 gates |
| 11 | statistics | major | 2³ cube undecidable at n; no tie rule | Cube replaced by singles-then-composites; ties → simpler leg (CHARTER §3) |
| 12 | statistics | major | 3 unaccounted ship decisions | §6: one statistical ship (W6-A); W6-B promotes only |
| 13 | mechanism | critical | READMIT opened on Tencent 2021-05-31 & 09-30 (index ctx lags name ~9mo) | Lockout reframing (§0/§2 C-LOCKOUT); name-level F5; fixture reframed ≤1 fire + ≥80% shut |
| 14 | mechanism | critical | fresh=dwell≤2 is a knife-catcher (fires months 1-2 of declines; 77% of episodes pass dwell 3) | dwell bands struck; F4 = monotone curve, knee picked by pre-committed rule |
| 15 | mechanism | critical | Positive fixtures pass only via dwell=0 — never monthly-washed; thesis mis-specified | §0 corrected object model: unbroken-cycle shallow dips (F3 ≥25 leg), not washouts |
| 16 | mechanism | major | MCD shut by 06-19 under turn2w recency | Turn recency windows = discovery knob; two-speed F7; fixture prints open/shut dates |
| 17 | mechanism | major | 2W oversold-visit lands ~1mo late (KO-2025 opens 10-17) | F7 lead/premium reporting mandatory; weekly fast leg added |
| 18 | mechanism | major | fresh/pinned cuts arbitrary on a smooth distribution | Same as #14 |
| 19 | engine | critical | Chip has no surface (standout loop excludes blocked names upstream) | §3: per-name stockdata record + stock.html + shelf; standout chip only for surfaced names |
| 20 | engine | major | "coiled.py state fns exist" was false | §3: NEW port + fixtures, in deliverables |
| 21 | engine | major | Live repaint on incomplete month/2W undisclosed | §3: provisional flag + completed-bucket discipline + anchor-divergence rule |
| 22 | causality | minor | donor restatement dropped min-members/top-rank guards | §2 F8: wave-5b definition verbatim |
| 23 | causality | minor | G6a rested on unclustered wave-5b points | §1: episode-clustered LB required |
