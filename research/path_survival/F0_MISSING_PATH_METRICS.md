# F0 — Missing Path Metrics

**Commission:** MASTERMIND GROK-F0  
**As-of:** 2026-08-18

This list is relative to the *commissioned* metric set and to an honest first-passage holdability grader. "Missing" means: not implemented on the canonical spine, or implemented only on a sibling under a different definition that must not be silently aliased.

Absence bounds are the searches listed in the capability census.

---

## 1. Missing on the canonical spine (`engine/grading.py`)

| Metric | Sibling that already has a definition | Why the sibling cannot just be "the spine" |
|---|---|---|
| High/low first-passage MFE/MAE | Radar `outcomes.attach` | Different P0, different window, vendor plane |
| ATR-scaled target / invalidation race | Radar `target_before_invalidation` | 1.00× / 1.25× A0, not ±5% |
| Same-bar **high/low** straddle tie | pre-registered in Setup-Species §1.1; **not coded** | Spine stop-wins is close-only |
| Gap-through-stop / gap-through-invalidation | Radar `gap_through_invalidation` | Needs `open`; stocks/yahoo cannot feed it |
| False-start (MAE-before-MFE in ATR units) | Radar `_false_start` clause A | Requires A0 + true-range OHLC |
| False-start clause B (K re-entry + washout low) | Radar `_false_start` | Detector-specific; not a house primitive |
| Time-to-failure (ATR) | Radar `time_to_failure` | Different clock than `stopped_at_bar` |
| Time-to-positive (close > P0) | Radar `time_to_positive` | Not the same as `cushion_at_bar` (+5%) |
| Time-to-MFE (argmax high) | Radar `time_to_mfe` | Spine has no argmax-bar of MFE |
| Path efficiency under the *name* `path_efficiency` | **nowhere** | `track_scoring.capture` = realised/MFE already exists — reuse that name/definition |
| Close-location inside the bar (close−low)/(high−low) post-entry | **nowhere** as a path stat | `donchian_pos` / entry_quality are pre-entry |
| Post-entry time underwater (bars close < fill) | **nowhere** | `time_underwater_series` is bars-since-252-high |
| Overnight vs RTH contribution | **nowhere** as a graded split | Radar day-0 is LIVE-only remainder |
| Reversal frequency along the trade | **nowhere** as a count | SI catalogs reversal *episodes*, not trades |
| Minute first-passage | **no store** | vendor fetch is C3-only |
| Opening-auction P0 | **no US store** | Radar live event, not a historical tape |

---

## 2. Present on the spine but easy to misuse

These are *not* missing. They are named so a later builder does not reimplement them under a prettier name.

- `fwd_mfe_{H}` / `fwd_mdd_{H}` — close excursions.
- `terminal_state` (+ short mirror).
- `cushion_incidence` (all-fires denominator).
- `post_cushion_breach`.
- `stopped_at_bar` / `cushion_at_bar` / `liftoff_at_bar`.

Misuse patterns already visible in the estate **CODE VERIFIED**:

- Calling close-min `MAE` and high/low-min `MAE` as if they were one number.
- Using `time_underwater_series` as if it were time-below-fill.
- Using Mastermind `giveback_pct_of_mfe` as if it were `post_cushion_breach`.
- Using Mastermind `brain/outcomes` TARGET/STOP (+15/−10, target-wins, same-bar-ish) as if it were `terminal_state`.

---

## 3. Present as law, not as code

| Law | Where written | Code status |
|---|---|---|
| High/low straddle: stop wins | Setup-Species masterplan §1.1 | comment only |
| Full-universe high/low history wired into the spine | same | not wired; yahoo is close-only |
| One grader; market-native fills | masterplan §1.2 | US migrated; CN native; QLedger next-bar but **not** `forward_metrics` |
| Species ledgers graded on the spine | masterplan + GRADE_CLOSURE | **GRADER-STARVED** (0 graded / 21 logged) |
| Radar W5 forward ledger accruing live | `daily.yml` + W5 prereg | local state `WAITING_FOR_LIVE_SOURCE`, 0 rows |
| SI W3 episode ruler | `WS-STOCK-IDENTITY` | `todo` |

---

## 4. Missing *joins*, not missing formulas

Even where two systems compute a related number, there is no shared row key that Path Survival can hang a single holdability record on.

| Join | Status |
|---|---|
| Spine fire ↔ Radar episode | no shared `episode_id`; different P0/fill |
| Spine fire ↔ SI episode | SI is expert-independent; join would be by `(symbol, date∈[start,end], type)` after `resolution_known_date` |
| Spine fire ↔ QLedger claim | QLedger is desk-claim not per-fire path |
| Spine fire ↔ Mastermind thesis | different entry convention; different barriers |
| Board row `species_id` | masterplan required emit-time stamp; Stage B notes said `species_id` null because many species bind | **INFERRED** still often null — not re-audited row-by-row this session |

---

## 5. What is *not* missing (do not rebuild)

- Persisted `stopped_at_bar` / `cushion_at_bar` / `liftoff_at_bar` on live board/track_record rows (computed, then dropped).
- Radar `day0_samples` producer (declared, not written).
- Radar secondary minute-path outcome table (named, not built).
- SI W3 localization ruler (constants sealed, compute banned in W2).

- A close-path honesty grader. Exists.
- A 4-state terminal partition. Exists.
- Competing-risk cushion incidence. Exists.
- A research-grade OHLC first-passage attach for Radar detectors. Exists (`outcomes.py`).
- A live giveback flag for the bot. Exists (`held_risk`).
- An episode catalog of declines/reclaims. Exists (SI W1).
- A claim scoreboard. Exists (QLedger).

Rebuilding any of those under a Path Survival name is the second-grader failure the commission forbids.

---

## 6. Priority holes for a later Path Survival *measurement* wave

Not a build order. Not a model. The holes that actually block an honest holdability read:

1. **OHLC first-passage on the spine**, optional, named, stop-wins-on-straddle, refusing yahoo-close-only inputs instead of pretending highs exist.
2. **Plane + basis stamp** on every path row (`price_plane_id`, `GradeBasis`, fill convention, P0 definition).
3. **Gap-through** only where `open` exists; ex-div flag required.
4. **Post-entry time-underwater** (bars close < fill) as a new primitive — do not reuse `time_underwater_series`.
5. **Close-location** — genuinely absent; define before coding. Path efficiency: reuse `track_scoring.capture`, do not mint a synonym.
6. **Do not** start a minute plane or an auction tape to unblock (1)–(5). Daily OHLC is enough for the first measurement contract.

---

## NO-BUILD / DO-NOT-INFER

- Missing ≠ "does not exist as a concept." Radar already answered several items for *its* episodes.
- Missing on the spine ≠ license to copy `outcomes.py` into a new package.
- Species GRADER-STARVED ≠ "species have no path law." The law is the spine; the registry is not feeding it.
- 0 Radar forward rows locally ≠ "Radar outcomes are unimplemented." The attach function is implemented; the live source is not.
