# Footprint picker prereg — the second layer on early admission (2026-08-11)

**Charter, frozen before any outcome is computed.** Program:
`PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md` §6.8(d) lane 3 + the bake-off's §A6
(`EARLY_ADMISSION_BAKEOFF_2026-08-11.md`, PR #5339 — episode plane + §RT discipline are the
substrate and the law here). Cross-market seed: CN W-P0 (operator screenshots 2026-08-11)
found oracle names board at base rate as a group while accumulation footprints pick winners
inside the filter at 2.4–3×. **Concept transfers, numbers do not** (no cross-class validation
transfer): the US measures its own tape. CN's "chip distribution" is the volume-profile
family — the one footprint plane the US already has at full depth.

**Question.** On the union admission set (C1-relaxed ∪ dot-only episodes from the bake-off
plane), do (a) accumulation-footprint features at the fire instant and (b) post-trough
evidence POLICIES separate durable entries from false starts — under labels that cannot be
gamed by stop-width arithmetic and features that cannot see the future?

## §1 Labels (v3 — both §RT defects designed out)

Per episode, three stop bases: **A** = P_low×0.99 (continuity with the bake-off), **F** =
entry −8%, **X** = entry − 2×ATR14. Label per basis = STOPPED (low ≤ stop before T+42) vs
SURVIVED (through T+42 or data edge, min 30 forward sessions; truncated counted). **No
false-bounce leg** — the P_low anchor is gone from the label. **Primary basis = X**
(fully entry-anchored); A and F are the robustness axes. `r_mult_42` recomputed per basis.

## §2 Deep battery (full 12y plane; every feature PIT from daily OHLCV at close T)

- **D1 AVWAP reclaim** — close(T) vs anchored VWAP from the decline's 126d closing-high
  date (engine `indicators_m2.anchored_vwap`); binary above/below + distance tercile.
- **D2 flush-on-shelf** — |P_low / rolling_poc(126, 24 bins) − 1| tercile (did the washout
  low land on the volume point-of-control — the CN "chip peak" analog).
- **D3 POC retest-hold** — `indicators_m2.poc_retest_hold` bullish flag as of T.
- **D4 absorption share** — share of [T−20, T] total volume transacted on sessions whose
  low ≤ P_low×1.02 (volume concentrated at the low), tercile.
- **D5 quiet accumulation** — rank-corr(volume, |daily ret|) over [T−15, T], tercile
  (negative = heavy volume on flat tape — transfer without price concession).

## §3 Thin battery (PROBE tier by charter — thin windows can never mint LIVE)

- **T1/T2 dark pool** — FINRA daily off-exchange `participation_z` and streak at T
  (`panel_deep` 374 names 2023-08+ ∪ full-universe panel 2026-05+; published same evening →
  treated knowable at T+1 open; features stamped accordingly).
- **T3 options flow** — signed net premium z over [T−5, T] (`data/options_flow`, 2026-01+,
  387 names). Texture only; n will be small and is printed.
- **Excluded, named:** GEX (<2 months of history), weekly ATS table (latest-week window),
  13F (quarterly grain; future context feature), PSS-AF1 (zero accrued rows, event-scoped),
  Massive tick/minute plane (TP-1 unbuilt). **Infrastructure debt flagged:** the one true
  PIT short-interest vintage panel (2018+, settlement+10d knowability,
  `scripts/backfill_finra_short_interest.py`) is built but gitignored/undeployed and absent
  from every checkout probed — deploying it is a named prerequisite for the ΔSI footprint,
  deferred.

## §4 Post-trough evidence as POLICIES (not conditional cohorts)

Conditioning on "the low held k sessions" deletes early stop-outs and manufactures edge
(§RT). So the structural tier is measured as decision policies over the SAME fire set, all
graded on basis X, entries at real prices:
- **P0** — enter at fire close (the bake-off baseline).
- **P1 wait-k** — enter at close of the first session ≥ T+5 iff no stop touch has printed
  and close ≤ fire-close×1.05; fires never entered are counted (not dropped).
- **P2 evidence-confirm** — enter at the knowability close of the first confirmed r3 swing
  low holding above P_low×0.98 within [T, T+15]; else never enter.
Read-out per policy: entry rate, per-fire R distribution (mean/median/p25/p75), stop-out
share, per-name-year R total, entry-vs-low give-up vs P0. No scalar winner is pre-declared —
the frontier is printed; a policy "wins" only if per-name-year R ≥ P0's with materially
lower stop-out share.

## §5 Method + read criteria (pre-stated)

Univariate terciles/binaries only; per-name-first beside pooled; month-cluster bootstrap CIs
on headline spreads; half-split by each lane's median fire date. **Every feature row carries
its cell-wise median entry_vs_low and a within-entry_vs_low-quintile conditional spread**
(the stop-width tell, mandatory). PIT audit: no feature may read any window past T (T+1-open
stamping for T1/T2 as above); no feature may reference another episode's outcome. Deep
features: **LIVE** = ≥10pp false-start spread on basis X, same sign both halves AND same
sign on bases A and F; **SUGGESTIVE** = ≥5pp with the same stability; else null. Thin
battery: capped at **PROBE** (spread + CI printed, no verdict). No combination search; one
pre-permitted cross-tab = strongest non-coupled deep feature × D4. Exemplar gate: STLD and
NEM 2026 union fires printed with all feature values before any pooled table. Survivorship
tint binds (bake-off §6). Display/measurement tier throughout — no gate, rank, or engine
change; promotion only via the program's sequencing.

## §R Results

*(appended by `footprint_picker.py`; frozen numbers in `footprint_picker_results.json`)*
