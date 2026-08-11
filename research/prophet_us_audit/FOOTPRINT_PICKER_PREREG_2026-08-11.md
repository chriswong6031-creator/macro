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

## §R Results (run 2026-08-11; frozen in `footprint_picker_results.json`, per-episode features in `footprint_picker_features.parquet`; episodes SHA 305990306ef)

**Headline: a clean pre-registered NULL, on every lane.** Union set 9,805 episodes / 240
names / 2,880.5 name-years. All gates passed; deviations: HL/UEC add-ons excluded from
pooling (bake-off law), T3 options net-premium **uncomputable** (the signed column begins
2026-07-02 — ~19 rows/name; no 252d z can exist; printed as an empty lane rather than
re-specified), P1's search bounded at T+42, thin-lane windows truncated at T−1 per the
knowability rule.

**R2 — labels.** Primary basis X (entry − 2×ATR14, median risk 4.6% of entry): stop-out
56.5%, mean R +0.36, median R −1.0 — tighter than the bake-off's P_low anchor (46.2%) and
harsher; the union book's central outcome is a stop-out, with the mean carried by the right
tail. Bases A/F: 46.2% / 37.1% stop-outs.

**R3 — the policies FAIL their pre-stated win condition.** P1 (wait 5 sessions, still
alive, ≤+5%) enters 80.6% of fires; P2 (confirmed r3 pivot holding above the reference low
within 15 sessions) enters 77.1%. Neither lowers the stop-out share (57.4% / 56.1% vs P0's
56.5%) and both LOSE per-name-year R (0.95 / 0.97 vs 1.21) by forgoing 19–23% of fires.
**Simple patience does not harvest the ex-post pre/post-trough split** (bake-off R9i): a
confirmed pivot frequently prints inside a still-falling decline (the same reason C4
carried a 42% pre-trough share), so the PIT proxies tested here do not select survivors.
The 67%-win post-trough ceiling remains ex-post only — no construction measured to date
reaches it at actionable prices.

**R4 — deep battery: every feature null under the charter's stability bar.** The two
largest spreads both run OPPOSITE to their motivating stories and fail cross-basis sign
stability: D2 flush-on-shelf — a washout low landing FAR from the volume POC stops out
LESS (50.7% vs 60.4%; −9.6pp on X, CI [−15.4,−3.5]) but flips to +12.4pp on basis F → null;
D1 AVWAP-reclaimed names stop out MORE (+6.3pp; the reclaimed cell enters at 0.080 vs
0.047 entry-vs-low — it is the already-ran cohort). D3/D4/D5 flat. The cross-tab: within
D2's better cell, MORE absorption at the low WORSENS outcomes (47.8% → 56.0%) — the
"someone absorbed the flush" daily-bar story does not measure what it hopes to.

**R5/R6 — thin lanes: PROBE nulls on 12.7% coverage** (129/240 names, darkpool z spreads
+2.4/−0.3pp, CIs straddling 0); options lane empty. **R5ref — the methodology receipt:**
`entry_vs_low`'s spread is −27.4pp on the bake-off's P_low basis and **−3.7pp on the
entry-anchored primary** (+17.8pp on F) — the v3 labels designed out the stop-width
channel that manufactured the bake-off's §8 false positives. The nulls here are nulls of
the FEATURES, not artifacts of the ruler.

## §A Adjudication

1. **The CN chip-distribution concept does not transfer to US daily bars with these
   constructions.** Five volume-profile/absorption features at full 12-year depth, two
   dark-pool features at 3-year depth, two patience policies: nothing clears the
   pre-stated bars, and the two biggest effects point away from the accumulation story.
   Per the ORE law these are construction-scoped nulls — the ledger records them; the
   space stays open where the data does not yet exist to search it.
2. **Where the picker could still live (named waits-for-data, not kills):** the PIT
   short-interest vintage panel (built 2018+, undeployed — deploying it is the single
   cheapest unlock and is now the program's flagged infrastructure debt); GEX/dealer
   positioning once it has quarters of history (currently <2 months); minute-grain
   accumulation signatures once Massive TP-1 mints the plane; 13F broadening at quarterly
   grain as slow context. The CN edge may also be genuinely mechanism-local (bands, T+1,
   retail attention — their own doc's claim), in which case the US analog is weaker by
   nature and the honest posture is what the bake-off already ships: geometry + operator
   selection, without a mechanical picker.
3. **Program consequence:** the TURN WATCH deck wiring (bake-off §A2) proceeds unchanged —
   union admission at starter grade with honest texture copy; no durability tier is
   licensed from any measured feature; the deck's context columns may DISPLAY D-features
   as texture but must not rank or imply reliability. The bake-off §A6's
   post-trough-evidence charter is now EXECUTED with a null verdict for its two simplest
   policies; richer evidence constructions (e.g. pivot-confirm + reclaim-hold sequencing)
   would need a new prereg, and this file's R3 is the baseline they must beat.
4. Display/measurement tier throughout; nothing promotes from this file.
