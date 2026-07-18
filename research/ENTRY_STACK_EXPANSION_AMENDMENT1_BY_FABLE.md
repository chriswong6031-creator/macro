# Entry-Stack Expansion — Amendment 1: Horizon Doctrine + Bottom/Rebound Integration (by Fable)

**Status:** RATIFIED 2026-07-05. Amends `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md` (PR #1356, W0 shipped #1360-1367). Adjudicates `research/NEURAL_WEB_BOTTOM_REBOUND_SIGNAL_EXPANSION_REPORT_FOR_CLAUDE.md` (Codex, 2026-07-05, rescued into repo with this PR).
**New rulings:** RUL-13 through RUL-17. Prior rulings RUL-1..12 unchanged.
**Review:** one opus adversarial pass (collisions/field-availability/legality) — SHIP-WITH-FIXES; both blockers (bind-don't-recompute vs hold.py; the two new rolling columns counted and benchmarked) and the sponsorship-scoping major are integrated below, marked ⟦RV⟧.

---

## A. RUL-13 — Horizon doctrine (operator directive, 2026-07-05; STANDING)

The objective function of every entry study in this program is **durable-bottom capture at swing horizon**:

1. **Primary horizon = ~21 trading days (20-25d band).** Primary endpoints: `stop5` (immediate post-buy stop-out), **`mae21`** (immediate post-buy drawdown — path, not endpoint), `clean8_21` (rotational liftoff 1.08/21), `days_to_10`. The rebound is usually captured — and often partially given back — inside this window.
2. **63d/126d metrics are the HOLDABILITY lane only** (S-QL quality overlay and hold-state management). They never decide an entry verdict. A signal weak at 3-6 months but strong at 2-4 weeks is DOING ITS JOB; the reverse (strong at 6m, dead money the first month) is a FAIL.
3. Bare 60d/3m/6m forward-return backtests of entry signals are **non-compliant** in this program: do not spend budget computing them except inside the holdability lane.
4. Effective immediately: `mae21` supersedes `mae63` as the hygiene-study co-primary. The in-flight W1-SEV study (registered with stop5 + mae63 primaries) is grandfathered: its `stop5` primary stands; its `mae63` is read as secondary and `mae21` is computed at adjudication.

Memory anchor: `backtest-horizon-swing-2-4-weeks` (account memory, feedback-type, STANDING).

---

## B. Adjudication of the Codex bottom/rebound report

The report is a competent synthesis that correctly read this repo's priors. Its staged taxonomy (exhaustion → stabilization → trigger → repair → sponsorship → anti-chase/veto) is ADOPTED as the program's semantic layer for display surfaces. Its build list divides cleanly:

| Codex proposal | Verdict | Where it lives |
|---|---|---|
| S-UR spring reclaim as top species | ALREADY PLANNED | Masterplan §3 F2, W2 flagship — no change |
| Earnings blackout hygiene | ALREADY IN FLIGHT | W1-SEV study running (family esx_ev_blackout) |
| Squeeze release (release-bar-only) | ALREADY PLANNED | Masterplan §3 F3, W2 |
| Quality/holdability overlay | ALREADY PLANNED | Masterplan §3 F5, W2 (holdability lane per RUL-13) |
| Liquidity/spread hygiene | ALREADY PLANNED | Masterplan §3 F4, W2 |
| Within-cohort RS repair | NOT OURS — owned by S7 (#1097/#1207) and Entry Intelligence #1302 W0.4 (within-cohort RS-rank series). We consume its fields when they exist; we do not rebuild them | Coordination §D |
| Production-trigger trio ablation | NOT OURS — #1302's pre-registration (P1_3_TRIO_ABLATION_PREREG). RECOMMENDATION forwarded: add state-label impact alongside hard-gate/rank-weight arms | Coordination §D |
| Generic OBV/CMF/RVOL, ADX-positive-filter, KST, Fib/Elliott | REJECTED (report itself concurs) | Graveyard, RUL-1 |
| Per-name options sensors | DEFERRED | RUL-6 clock (~2027-01) |
| Hand-weighted master buy score | BANNED | House law; report concurs |
| **Bottom-sensor envelope + state labels (display-only)** | **ADOPTED** | New lane B0, below |
| **Vol-scaled entry zone as co-primary metric** | **ADOPTED** | RUL-14, lane B1 |
| **Sector/subsector sponsorship connector + stratification** | **ADOPTED** | RUL-16, lane B2 |
| **Launch/hold-state anti-chase reframe** | **ADOPTED (report-only first)** | Lane B3 |

### Rulings on the report's ten review questions (RUL-17 batch)

1. **Amendment, not a new program.** Bottom/rebound work rides inside Entry-Stack Expansion; a parallel program would double-account the same fires and species.
2. **`data/neuralweb/bottom_sensors.parquet` is a NEW display-only artifact**, synapse-registered. Spine/index schemas are not mutated for descriptive fields.
3. **S-UR stays the top species candidate** (already W2 flagship). No reordering needed.
4. **Trio ablation:** recommendation to include state-label arms is forwarded to #1302; we do not execute their prereg.
5. **Sector velocity is both:** Oracle owns the artifact; Neural Web consumes it as a sponsorship sensor (display-only edges). Lane B2 tests it as a stratification family under our protocol.
6. **Rare-sensor event budget:** masterplan §7.6 stands — coarser cells (engine × horizon) when regime cells cannot reach MIN_FAMILY_N within 2 quarters.
7. **Vol-scaled zone = co-primary: YES** (RUL-14).
8. **State labels display on a QA surface FIRST, then Committee View** — zero ranking authority until a label earns its own family verdict.
9. **COILED double-counting:** RUL-11 already covers it (no fire testifies twice); envelope fields are descriptive display and never feed FDR or confluence-lift as evidence.
10. **Surface order: QA page → Committee View → US stock board chips.** Boards last, because boards imply ranking authority the labels have not earned.

---

## C. New lanes

### C1. RUL-14 — Vol-scaled entry zone (co-primary metric; lane B1)

The fixed −5% stop is one-size-fits-none for washout names (prior S7 zone addendum: typical washout entries trade 6-8% below fill before working). Adopted as a MEASUREMENT, not a signal:

- Per-fire band: `sigma20 × sqrt(20)`, clamped to [5%, 15%], computed at fill from trailing 20d close-to-close vol.
- New harness outcomes: `zone_held_21` (low over fill+1..fill+21 stayed above fill × (1 − band)) and `stop_vol_21` (stopped out of the vol-scaled band), reported as **co-primary beside stop5** in every subsequent study (W2 onward; W1 studies grandfathered, computed at adjudication).
- Purpose: distinguish real failure from normal washout noise; feed stop-guidance display later ONLY if a family earns it.
- Implementation waits until the W1 harness fix (PR #1408 chain) merges — no concurrent edits to `entry_strata_phase0.py`.

### C2. RUL-15 — Bottom-sensor envelope + frozen state labels v1 (lane B0; display-only)

**Artifact:** `engine/neuralweb/bottom_sensors.py` → `data/neuralweb/bottom_sensors.parquet` + `site/neuralwebdata/bottom_sensors.json`. Computed nightly AFTER library builds. **Bind-first, compute-second** ⟦RV⟧: every field that an existing engine already emits is BOUND read-only (never recomputed off a different anchor); exactly TWO new computed columns are permitted — `dist_21d_low_pct` (close vs `rolling(21).min()` of prior closes) and `dist_126d_high_pct` (close vs `rolling(126).max()`) — both O(1) rolling ops per name, explicitly counted here because no nightly artifact carries a 21d/126d distance (only 252-bar `off_52w_high_pct`/`above_52w_low_pct` exist, engine/technicals.py:51-54). Benchmark in the PR; ≤ +30s on the render or the whole envelope moves off-path. Synapse-registered; `is_display_only: true`; store git-added + sentinel staging determination.

**Schema (v1):** `symbol, as_of, region, trigger_tier, trigger_age_ticks, coiled, star, coiled_fire, donor_state, dist_21d_low_pct, dist_126d_high_pct, entry_quality_band, squeeze_state, earnings_next_date, earnings_days_to, rs_repair_state (stamped unavailable in v1), sponsorship_state (unavailable until B2), bottom_state, overlay_flags, labels_version, source_artifacts, is_display_only`.

**Frozen state-decision table `labels_v1`** (mechanical, versioned; thresholds frozen here; any change = new version logged in this doc). Precedence top-down; `EVENT_BLACKOUT` and `COILED/STAR` are overlay flags, not states:

| State | Rule (v1) — BIND column names the source ⟦RV⟧ |
|---|---|
| `HOLD_LAUNCHED` | **BIND: `hold["state"] == "launched"`** (engine/hold.py:188-195, take-anchored — the shipped ↑Launched chip). The envelope NEVER recomputes a fire-anchored variant (two anchors ⇒ two contradictory chips on one board) |
| `FRESH_FIRE_DURABLE_CAND` | fresh T1-T3 (ticks ≤ 2) AND COILED (bind coiled flags) AND dist_21d_low ≤ 12% |
| `FRESH_FIRE_TACTICAL` | fresh T1-T3 (ticks ≤ 2) AND NOT COILED AND dist_21d_low ≤ 12% |
| `CHASE_RISK` | T1-T3 present AND (ticks > 2 OR dist_21d_low > 12%) AND not HOLD_LAUNCHED |
| `DEAD_MONEY_RISK` | **BIND: hold state intact/basing** (hold.py) with days-basing 15-40 AND abs(ret since take) < 4%; where hold fields absent for a name, stamp `unavailable` — do not recompute |
| `EARLY_WATCH` | drawdown ≥ 15% from 126d high AND `bars_to_cross ≤ 2` (available on T3/T4 rows only — signal_gate.py:214; the 2D hist-curl arm is DEFERRED until an engine emits it as a field) AND no fresh T1-T3 |
| `KNIFE_RISK` | **BIND: the existing `_ALIGN_KNIFE_BLOCK` condition** (scripts/build_stock_library.py:~2015) where computed; else drawdown ≥ 15% from 126d high AND close < prior 21d rolling low AND no fresh tier |
| `WATCH` | default |
| overlay `EVENT_BLACKOUT` | earnings next_date within ≤ 3 trading days (per-row fresh rule of masterplan §3 F1) |

Binding law ⟦RV⟧: an input that exists as an emitted field is bound read-only with its source anchor documented; an input that does not exist is stamped `unavailable` and its label degrades gracefully (documented per label) — with the sole exception of the two counted rolling columns above. Known v1 gaps, stated: the **spring/reclaim event has no state in v1** (S-UR is a W2 species; a `RECLAIM` state arrives in labels_v2 only after S-UR earns registration — `entry_primitives.undercut_rally_events` exists but adding it to the render path is exactly the compute this lane forbids); `rs_repair_state` stays `unavailable` until #1302's W0.4 series exists — and note their trio-ablation prereg is still DRAFT/pending-approval, so no pickup guarantee. Labels are DESCRIPTIVE: they rank nothing, gate nothing, alert nothing. Promotion of any label to ranking authority requires its own pre-registered family.

**Version log — `labels_v2` (2026-07-18, operator-ratified ruling).** DEAD_MONEY_RISK now binds `hold["ret_since_anchor_pct"]` — a SIGNED additive field emitted by engine/hold.py (close[now]/Pc − 1) — as the "ret since take" input. This is a **bind repair, not a threshold change**: the decision table and the |ret| < 4% threshold above are unchanged. labels_v1 had used `maxup_pct` (max FAVORABLE excursion, always ≳ 0) as a proxy because no signed field existed (deviation #4, logged in the module); the proxy could not see underwater names — reproduced 2026-07-17: AMKR down 30.4% since its 06-18 anchor carried maxup 3.42% → |3.42| < 4 → mislabeled DEAD_MONEY_RISK, while AEIS (down 23.8%, maxup 4.20%) escaped by 0.2pp of pop noise. Where the signed field is absent (pre-v2 `us_standouts.json` bake), the gate degrades to not firing per the binding law — never proxy fallback. Contamination accounting: 16 nightly parquet snapshots (2026-07-05 → 07-17) carry labels_v1 rows (~13 DEAD_MONEY_RISK instances); the per-row `labels_version` stamp is the epoch marker — any study over the git-history label series (incl. the C4/B3 threshold parameterization) must split on it. The shadow forward-ledger (`bottom_sensors_geometry_book.jsonl`) is untouched — it accrues only the Amendment-3 close-derived descriptors. The RECLAIM state reserved above for a future version remains unshipped; it would arrive in a later version after S-UR earns registration.

**Display:** standalone QA page `site/qa_bottom_sensors.html` (reachable by URL, NO nav changes — nav chrome is shared/hand-duplicated and out of scope), bilingual EN/ZH, `data-tip-en/zh` popovers, no translated `title=` attributes, zero affirmative "validated" wording. Committee View block only as a later PR after the QA surface has run ≥1 week.

### C3. RUL-16 — Sponsorship stratification (lane B2; family `esx_sponsorship`)

**Question:** do gate fires inside sectors/subsectors with positive rotation velocity/acceleration show better 21d entry asymmetry than fires in headwind groups?

- **Scoping correction ⟦RV⟧:** the "oracle panel 2021+" memory prior applies to breadth/cohesion/turnover columns ONLY. The SECTOR panel's velocity/acceleration columns (`vel_1w/1m/3m`, `accel`, `accel_z` on `data/oracle/panel_s.parquet`, 11 sector nodes) run **1998-12 → present (~27y, >99% non-null)**; only the SUBSECTOR panel (`panel_m`, 354 nodes) is genuinely 2021+. The census confirms this split, then: sector arm runs full-history; subsector arm runs 2021+ or defers to accrual if < 3y usable.
- **Pre-registered family `esx_sponsorship`, declared budget 8:** 1 frozen sponsorship definition (velocity sign + acceleration sign at fire date → tailwind / neutral / headwind) × 2 contrasts (tailwind-vs-rest, headwind-vs-rest) × {sector-level arm on 2 panels full-history = 4} + {subsector-level arm on 2 panels 2021+ = 4}. R1 estimator; 21d primaries per RUL-13; BH q≤0.10; recall printed.
- Deploy ceiling: **priority modifier / display context only** — sponsorship never hard-blocks a bottom entry (Codex report concurs; Oracle P3 confirmed-tier NULLs are the hostile prior, ONSET-tier edge the supportive one; both cited in the report header).

### C4. Lane B3 — Launch/hold-state reframe (report-only)

Descriptive study appended to the B0 lane: distribution of post-fire trajectory states (launched / dead-money / chase / stopped) on historical fires, by tier and era, 21d window. No family, no verdict — it parameterizes the `labels_v1` thresholds empirically for a possible `labels_v2` and gives the operator the "signal fires → bases → board goes silent" visibility. Any v2 threshold change is logged here.

---

## D. Coordination and sequencing

- **In-flight W1 is untouched:** the NC-fix chain (PR #1408) → S-EV + S-TS studies continue as dispatched. Lane B1 (harness edit) queues BEHIND the W1 harness fix merge. Lanes B0/B2-census are new-file lanes and run now.
- **#1302 Entry Intelligence:** RS-repair fields and trio ablation are theirs; the envelope stamps `rs_repair_state: unavailable` until their W0.4 series exists, then binds read-only. State-label recommendation forwarded, not executed.
- **Oracle:** velocity artifacts consumed read-only; the B2 family cites P3/P8 verdicts as adjacent priors.
- **#1097 species law:** no new species in this amendment (labels are display, sponsorship is a stratum family). S-UR registration remains the W2 first act.
- Build routing per CLAUDE.md: Sonnet builds, Opus reviews, Fable adjudicates. All git law unchanged (fresh-main worktrees, same-day squash-merge, sentinel staging, no bare stash).

## E. Non-goals (this amendment)

No master score. No new oscillators. No ranking authority for any label. No HK/CA. No options acceleration. No harness edits before the W1 fix merges. No Committee View changes before the QA surface has accrued.

*Filed by Fable, 2026-07-05. Companion input: Codex report (same-PR rescue). Review: single opus collision/legality pass before merge.*
