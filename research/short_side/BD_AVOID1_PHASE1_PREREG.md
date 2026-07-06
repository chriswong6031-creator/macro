# BD-AVOID-1 Phase-1 Pre-Registration

**Status:** PRE-REGISTERED 2026-07-06 BEFORE any forward ledger write.
**Program:** L1 Short-Side Lobe — forward avoid-long phase.
**Authority:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md` §6.3 (Fable-frozen spec, verbatim binding).
**Governing charter:** `research/SHORT_SIDE_MASTERPLAN_BY_FABLE.md`.
**Phase-0 basis:** `research/short_side/BD_PHASE0_PREREG.md` + `data/research/breakdown_events_summary.json` (2026-07-06T05:16:25Z vintage).
**Contamination declaration:** `derived_from_surface: bd_phase0` — BD-2 and BD-3 were selected for Phase-1 because they cleared the ≥5pp long-stop-vs-control bar in the Phase-0 descriptive run (BD-2: +9.66pp @21d, BD-3: +16.81pp @21d). This prereg carries a compensating gate (threshold raised to ≥8pp; forward OOS verdict only). Changing any frozen gate after seeing Phase-1 forward data is p-hacking.

**TrialLedger:** `log_declared_budget(2, family='short_side')` logged BEFORE first stamper write (2 trials: BD-2 and BD-3 forward avoid-long verdicts). The Phase-0 declared budget (3) is already committed to the family; this adds 2 more declared forward trials bringing the family total to 5.

---

## §1. Hypotheses (2 trials, fdr_family='short_side')

### H1 — BD-2 Forward Avoid-Long
For names where a BD-2 event fires (failed reclaim after a stopped fire), the long-side 21-bar stop rate on forward post-registration events exceeds the matched PIT random-bar control's long-side stop rate by **≥8 percentage points**, with an episode-clustered 95% CI excluding 0, and BH q ≤ 0.10 within the `short_side` family.

### H2 — BD-3 Forward Avoid-Long
For names where a BD-3 event fires (tail-flag breach with defensive bid), the long-side 21-bar stop rate on forward post-registration events exceeds the matched PIT random-bar control's long-side stop rate by **≥8 percentage points**, with an episode-clustered 95% CI excluding 0, and BH q ≤ 0.10 within the `short_side` family.

**Compensating gate rationale:** Phase-0 observed BD-2: +9.66pp and BD-3: +16.81pp (both exceeding the masterplan's ≥5pp bar). Both definitions were selected BECAUSE they cleared the Phase-0 descriptive surface. Per `derived_from_surface: bd_phase0` (RUL-3), the threshold is raised to ≥8pp — strictly above the BD-2 Phase-0 reading (+9.66pp) and well below BD-3's (+16.81pp) — to compensate for look-ahead in definition selection. The forward OOS stream must independently clear ≥8pp without any use of the Phase-0 tape.

---

## §2. Verdict basis (forward OOS only)

**The Phase-0 tape is NEVER re-used for the verdict.** Only post-registration events (event_date ≥ 2026-07-06) feed the verdict criteria. The stamper enforces this by construction: it detects only new events since the last stamp date, and the initial stamp date is the registration date.

The Phase-0 retroactive tape provides no data points toward the verdict floor (§4 n≥300/side) and no data points toward the effect size or CI computation.

---

## §3. Event definitions (frozen — inherited verbatim from Phase-0)

BD-2 and BD-3 definitions are FROZEN at the Phase-0 specification (`research/short_side/BD_PHASE0_PREREG.md §3`). The stamper script (`scripts/research/bd_avoid1_stamper.py`) imports detector functions directly from `scripts/research/dump_breakdown_events.py` — the same frozen-threshold constants. Re-implementing detectors in the stamper is explicitly prohibited; the import is the enforcement.

**BD-2 — Failed reclaim after a stopped fire (S6⁻):**
- Source: `replay_boarded` fires with `state_8_21 == 'STOPPED'`.
- Within 10 bars after the stop bar: a rally whose highest close remains BELOW the fire-day close.
- Event fires on the first down-close after that failed-rally high (the failure bar).

**BD-3 — Tail-flag breach with defensive bid (S4⁻-adjacent arming):**
- `ema8_breach`: fresh breach per canonical `engine/signal_quality.fresh_breach_mask()` (3B resample, span=8).
- `extended`: event-day close ≥ 1.15 × rolling 126-bar min close.
- `defensive_bid`: mean({XLP, XLU, XLV}) 21-bar total return minus SPY 21-bar return > 0.

**Episode collapse:** within-ticker within-definition events within 21 bars of a prior event collapse (first wins). Identical to Phase-0.

**Liquidity floor:** 21d median dollar volume ≥ $5M, price ≥ $3 at event date. Identical to Phase-0.

---

## §4. Forward control stream

Each event row in `data/research/bd_avoid1_ledger.parquet` has 3 matched PIT random-bar control rows with `is_control=True`. Controls are:

- Same ticker, same universe, same liquidity floor.
- Sampled from non-event bars in the same calendar year (year-stratified, matching Phase-0).
- **Seeded deterministically from event_id** (not a global seed) so each event's controls are stable across stamper re-runs. Seed derivation: `seed = int(hashlib.md5(event_id.encode()).hexdigest()[:8], 16) % (2**31)` where `event_id = f"{ticker}|{definition}|{event_date}"`.
- Append-only: once written, a control row is never modified or replaced.

The same single-writer stamps both event rows and their control rows atomically per run.

---

## §5. Grading protocol

**Horizons graded:** h21 (21 bars) and h126 (126 bars) — consistent with Phase-0.

**Price plane:** `massive_stock_day`, `split_adjust()` applied. Same as Phase-0.

**Long-side terminal state (verdict-feeding):**
- `terminal_state(close, event_date, liftoff_mult=LIFTOFF_8, liftoff_horizon=LIFTOFF_HORIZON_21)` → `clean8_21` state.
- Stop rate comparison: `state == 'STOPPED'` vs control `state == 'STOPPED'` at the 21-bar horizon.

**Short-side terminal state (recorded, quarantined):**
- `terminal_state_short(close, event_date, adverse_mult=SHORT_ADVERSE_MULT, favorable_mult=SHORT_FAVORABLE_MULT_21, horizon=21)` → `short21` state.
- Short-side grades are recorded in the ledger and visible to audits, but carry NO verdict criteria and do not feed the BH FDR test. BD-3's Phase-0 observation that short-favorable > adverse is quarantined as descriptive.

**Maturity trigger:** a row is graded when the price plane has ≥ horizon bars after the fill date. Unmatured rows have `long_state_clean8_21=None`, `short_state_short21=None`. Censored paths are flagged `censored=True`, never dropped.

**Grader invocation:** the Mac-side stamper runs grading in the same pass as detection, calling `engine.grading` functions directly (same imports as Phase-0 stamper). No separate grader script is needed; grading is idempotent on already-matured rows.

---

## §6. Maturity clock and come-back date

### Retrospective arrival-rate estimate (from Phase-0 tape, 2022-2026):

| Definition | Episodes in Phase-0 tape | Years covered | Approx. episodes/year |
|------------|--------------------------|---------------|----------------------|
| BD-2       | 19,891                   | ~5 yr         | ~3,978/yr             |
| BD-3       | 5,553                    | ~5 yr         | ~1,111/yr             |

*Note: Phase-0 counts include multiple episodes per ticker; forward stream may differ due to universe evolution and real-time replay_boarded construction.*

### n ≥ 300 episodes/side floor:

At ~1,111 BD-3 events/year, 300 events accrues in ≈ 99 calendar days from the registration date.

At ~3,978 BD-2 events/year, 300 events accrues in ≈ 28 calendar days.

**Registered come-back dates (no verdict read before floor):**

- **BD-2 come-back date:** 2026-10-01 (conservative — allows for universe contraction and forward rate being lower than the 5-year historical average).
- **BD-3 come-back date:** 2027-01-01 (conservative — BD-3 is rarer; the 2027-01 date aligns with the §6.3 spec come-back and provides ~180 calendar days of buffer above the ~99-day arithmetic estimate).

Until these floors are reached, the ledger appears ONLY as an accrual clock row on the evidence panel (PR-A1). No verdict, no signal claim, no board chip.

---

## §7. FDR accounting

| Family | Existing budget (Phase-0) | This prereg adds | New family total |
|--------|---------------------------|-----------------|-----------------|
| short_side | 3 (BD-1/BD-2/BD-3 descriptive) | 2 (BD-2/BD-3 forward) | 5 |

BH correction applies across ALL 5 trials at verdict time, using the `short_side` family. The Phase-0 trials are descriptive-only (no verdict gates); at verdict time the 2 forward trials are the tested hypotheses and the 3 Phase-0 descriptive trials are counted in the family denominator.

Threshold: BH q ≤ 0.10. With 2 tests and one-sided null, the BH-adjusted alpha for rank-1 = 0.10 × 1/5 = 0.02; rank-2 = 0.10 × 2/5 = 0.04. (Using family size = 5 per conservative accounting.)

---

## §8. Quarantine (RUL-3)

- **Avoid-long only:** this prereg covers the avoid-long direction exclusively. BD-3's Phase-0 observation that short-favorable rate exceeded adverse rate is quarantined — it is recorded as a descriptive fact in Phase-0, not a tested hypothesis.
- **No short-entry prereg:** any future short-entry prereg for BD-3 (or any BD definition) is out of scope for this program and requires its own `derived_from_surface` stamp and compensating gate.
- **No board chips this wave:** until the verdict floor is reached, no board chip, no site signal surface, no alert generation from BD event fires.
- **No sizing:** gross_mult and allocation logic are unchanged. Avoid-long means "do not initiate a new long" during an active BD episode, nothing more.

---

## §9. Ledger schema

**Path:** `data/research/bd_avoid1_ledger.parquet` (git-committed, append-only, Mac-side single-writer).

**Key columns:**

| Column | Type | Description |
|--------|------|-------------|
| event_id | str | `{ticker}|{definition}|{event_date}` — unique per event |
| ticker | str | Ticker symbol |
| definition | str | 'BD-2' or 'BD-3' |
| event_date | str (ISO date) | Date of the event bar |
| fill_date | str (ISO date) | Next-bar fill date |
| entry_price | float | Split-adjusted fill price |
| is_control | bool | True for matched random-bar controls |
| control_seed | int | RNG seed used (controls only) |
| stamped_at | str (ISO datetime UTC) | When this row was written |
| pit_stamp_date | str (ISO date) | As-of date of the stamper run |
| long_state_clean8_21 | str or None | Long-side terminal state at 21d (verdict-feeding) |
| long_state_clean15_126 | str or None | Long-side terminal state at 126d (recorded) |
| short_state_short21 | str or None | Short-side terminal state at 21d (quarantined) |
| short_state_short126 | str or None | Short-side terminal state at 126d (quarantined) |
| fwd_ret_21 | float or None | Forward return at 21 bars |
| fwd_mdd_21 | float or None | Max drawdown at 21 bars |
| fwd_mfe_21 | float or None | Max favorable excursion at 21 bars |
| fwd_ret_126 | float or None | Forward return at 126 bars |
| fwd_mdd_126 | float or None | Max drawdown at 126 bars |
| fwd_mfe_126 | float or None | Max favorable excursion at 126 bars |
| censored | bool | True if any forward path was unavailable |
| survivorship_biased | bool | Always True (universe = board + fire tickers) |
| vintage_stamp | str (JSON) | Serialized 8-field vintage stamp |

**Append-only enforcement:** the stamper reads existing event_ids before writing and skips any row whose event_id already exists. Existing rows are never modified.

**Single-writer declaration:** `scripts/research/bd_avoid1_stamper.py` is the ONLY writer of this ledger. No other script, engine module, or CI job writes to this path. Parallel runs are prevented by a file-lock (`data/research/.bd_avoid1_stamper.lock`).

---

## §10. Ops lane and invocation

The stamper runs on the **Mac-side off-render ops lane** — never on CI runners (which lack `massive_stock_day` and `replay_boarded`). Invocation pattern mirrors `ops/launchd/com.mastermind.optionshub.plist`.

**launchd plist:** `ops/launchd/com.macro.bd_avoid1_stamper.plist` — runs weekday post-close (17:00 ET, after the nightly oracle run that refreshes `replay_boarded`).

**Narrow commit:** after stamping, the stamper calls `git add data/research/bd_avoid1_ledger.parquet` and commits with message `data(short_side): bd_avoid1 ledger stamp {date}`. This follows the sentinel-gap law (narrow add, not `git add .`).

**Manual invocation:**
```
cd '/Users/chriswong/Documents/Cluade/Macro Dashboard'
python -m scripts.research.bd_avoid1_stamper [--dry-run] [--data-dir PATH]
```

---

## §11. What this does NOT show or claim

- No claim about short-entry alpha, borrow availability, or short execution.
- No claim about live trading size or direction change.
- No version of this document or its ledger feeds any board score, gate, alert, or NW signal until the verdict floor is reached and a verdict is read.
- No cross-definition ranking or selection within this Phase-1 (the definitions are registered independently).
- Phase-0 retrospective tape counts do not accrue toward the n≥300 floor.

---

## Amendments

*(none — amendments require a dated entry committed before the amended run)*
