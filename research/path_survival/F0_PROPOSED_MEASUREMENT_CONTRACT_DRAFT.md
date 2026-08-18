# F0 — Proposed Measurement Contract (draft)

**Commission:** MASTERMIND GROK-F0  
**Status:** DRAFT. Not ratified. Not a build packet. No model. No gate.

This is the smallest contract that lets Path Survival *extend* `engine/grading.py` without creating a second grader. It is written so a later wave can implement it mechanically or reject named clauses.

---

## 0. Non-negotiables (inherited)

1. `engine/grading.py` remains the one grader. New path functions land in that module (or a submodule it re-exports). Callers do not grow private first-passage loops.
2. Market-native fills stay native. US default = next-bar close. CN = T+1 HL2 + locked-limit, not `fill_index`. HK suspension rule stays with HK ledgers.
3. Missing data stays missing. No fill-forward of highs/lows. No imputed opens. No "close as high."
4. Same-bar fill stays shadow-only.
5. Medians-over-reachers stay banned for any first-passage rate. Denominator = all gradable fires.
6. Do not change live rank / gate / size / execution. Display/research rows only until a later gauntlet.
7. Do not fit a holdability model. This contract measures paths.

---

## 1. Identity of a path row

Every graded path row carries:

| Field | Meaning |
|---|---|
| `symbol` | instrument |
| `signal_date` | the bar the signal was known (not the fill) |
| `fill_date` | actual entry bar |
| `fill_convention` | `next_bar_close` \| `t1_hl2` \| `t1_open` \| `t1_close` \| `sampled_last_trade` \| `first_trade_after_known_at` \| `next_session_close` |
| `entry_price` / `p0` | price implied by that convention |
| `price_plane_id` | `stocks_tr_v1` \| `yahoo_tr_v1` \| `baskets_ohlcv_v1` \| `stock_identity_ohlcv_v1` \| (CN/HK ids) |
| `return_basis` | `total_return` \| `price_return` \| `vendor_unadjusted` |
| `path_basis` | `close_only` \| `ohlc` |
| `parameterization` | named barrier set (below) |
| `horizon` | trading sessions in the window |
| `censored` | true if fewer than `horizon` forward sessions |
| `substrate_fingerprint` | optional hash of the fill-bar close (and open if used) so retro-adjust is visible |

A row that cannot populate `price_plane_id`, `fill_convention`, `path_basis`, and `parameterization` is refused, not graded.

---

## 2. Two legal path bases

### 2.1 `close_only` (already shipped)

- Window: `(fill, fill+H]`.
- MFE = max close / entry − 1 (≥ 0).
- MAE = min close / entry − 1 (≤ 0). Spine name remains `fwd_mdd` for compatibility; a new alias `fwd_mae_close` may be added **as an alias**, not a second computation.
- Barrier race: sequential closes; stop checked before cushion/liftoff on the same close.
- Legal on `data/yahoo` and `data/stocks`.

### 2.2 `ohlc` (to be added on the spine; already exists in Radar)

- Requires columns `high` and `low`. `open` required only for gap-through.
- MFE = max(high, optional day-0 max) / P0 − 1.
- MAE = min(low, optional day-0 min) / P0 − 1.
- First-touch position = `(segment, index)` with LIVE day-0 = segment 0, daily sessions = segment 1.
- Straddle / same-position tie: **adverse / stop wins** (Setup-Species §1.1 + Radar frozen law).
- If `high`/`low` are absent: refuse `ohlc`, do not degrade to close silently.
- Legal on `data/baskets/ohlcv` (2014+) and `data/stocks` (H/L, no gap-through). Illegal on `data/yahoo`. Illegal on `massive_stock_day`.

Both bases may be written on the same fire as *sibling columns*, never pooled into one MFE number.

---

## 3. Named parameterizations (append-only)

A parameterization is a frozen tuple. New economics = new name.

| Name | Path basis | Stop / adverse | Cushion / target | Liftoff / favorable | Horizon | Already exists? |
|---|---|---|---|---|---|---|
| `clean15_126` | close_only | 0.95× | 1.05× | 1.15× | 126 | yes |
| `clean8_21` | close_only | 0.95× | 1.05× | 1.08× | 21 | yes |
| `short_adv105_fav92_21` | close_only | 1.05× up | — | 0.92× | 21 | yes (`terminal_state_short`) |
| `radar_atr_1.25_1.00_H10` | ohlc | P0 − 1.25 A0 | — | P0 + 1.00 A0 | 10 | yes in Radar, not on spine |
| `radar_tgt_1.00_inv_1.25_H10` | ohlc | P0 − 1.25 A0 | P0 + 1.00 A0 | — | 10 | yes in Radar, not on spine |

A0, when used, is Wilder ATR(14) at the **prior confirmed close**, `atr_basis=true_range_daily_ohlc`. Close-proxy ATR ⇒ false-start / ATR races are `None` (unevaluable), never computed.

Do not add a "default ATR holdability" parameterization that is not on this table.

---

## 4. Metric definitions Path Survival may emit

Each metric names its parameterization and path basis.

| Metric | Definition | Missing-data rule |
|---|---|---|
| `fwd_ret` | exit close / P0 − 1 | None if censored (spine) or last-available + `censored=true` (Radar). **Pick one and stamp it.** Draft default: spine (None if not matured). |
| `mfe` / `mae` | as §2 | None if path basis illegal |
| `target_before_stop` | first-touch(target) strictly before first-touch(stop); tie = stop | None if neither touched |
| `cushion_at_bar` / `stopped_at_bar` / `liftoff_at_bar` | 1-indexed sessions from fill; 0 reserved for LIVE day-0 only | None if not touched |
| `cushion_incidence[k]` | # cushioned by k and not yet stopped / n_gradable | competing risk; all-fires denom |
| `post_cushion_breach` | after cushion, any later close < P0 | None if never cushioned |
| `gap_through_stop` | `open < stop AND prior_close >= stop` | None if no open; False is allowed only when open exists and the predicate is false |
| `false_start` | only under `radar_atr_*` | None if A0 unevaluable |
| `time_to_failure` | bar of first adverse touch under the parameterization | None if no failure |
| `time_underwater_from_fill` | count of closes < P0 in the window | new; do not reuse `time_underwater_series` |
| `capture` | realised PnL / MFE when MFE > `MFE_FLOOR`; else undefined and counted | **already shipped** in `engine/track_scoring.py`; do not invent `path_efficiency` |
| `close_location` | mean or last `(close−low)/(high−low)` over the window | None without H/L; **definition not ratified** |
| `overnight_ret` / `rth_ret` | **not in v0** | no store |

Reversal frequency is **not** in v0. SI already catalogs reversal episodes.

---

## 5. Fill and gap law

- US research default remains next-bar close for `close_only`.
- `ohlc` rows may use Radar P0 conventions only when the episode already carries a stamped `p0_basis`. A board fire without a P0 stamp does not inherit `first_trade_after_known_at`.
- Gap-through is a separate boolean, not a rewrite of `stopped_at_bar`. A close-only stop the next session and a gap-through at the open are both recorded when both are evaluable.
- Ex-dividend: if the session is an ex-div session on the subject, `gap_through_*` and ATR false-start are flagged `ex_div=true` and **excluded from primary rates** (Radar W5 law). They remain on the row.

---

## 6. PIT / leakage

- Signal date is the known-at session. Fill is strictly after, except for explicitly stamped LIVE day-0 remainder.
- FIT / TEST / holdout for Radar-shaped rows: `prereg.py` dates. Path Survival must not "discover" on `decision_session > 2026-02-13`.
- SI labels may be joined only when `asof >= resolution_known_date`.
- QLedger claims stay forward-only. This contract does not register retrospective qledger claims.
- Retro-adjustment: if `substrate_fingerprint` disagrees on re-read, the row is stale, not silently updated (keep-FIRST, matching qledger/board keep laws unless a ledger already documents keep-FRESH).

---

## 7. Who writes, who cites

| Writer | What it may write |
|---|---|
| `scripts/grade_us_board.py` / `track_record` | `close_only` spine (already). Later: sibling `ohlc` columns only when the plane has H/L |
| `engine/entry_radar/replay/outcomes.py` | becomes a caller of spine `ohlc` helpers; may keep Radar-only extras (clause B, costs) |
| `engine/china_standout_track.py` | CN-native fill + shared constants (already) |
| QLedger | cites, does not compute path |
| Mastermind `held_risk` | remains operational; may later *read* published path rows |
| Species registry | still not a grader |

---

## 8. Live-forward

- Close-only spine is already nightly.
- `ohlc` live-forward is legal only on a plane that is itself nightly (baskets).
- Radar live-forward is blocked today (`WAITING_FOR_LIVE_SOURCE`). This contract does not commission a live source.
- Minute/auction live-forward is out of v0.

---

## 9. Explicitly out of contract

- Any scoring, ranking, or sizing function of these metrics.
- Any new minute plane, auction tape, or massive restore.
- Implementing SI W3.
- Changing Radar detector hashes or W4 outcome-blindness.
- Changing Mastermind giveback thresholds.
- Promoting any metric to authority.

---

## 10. Acceptance tests a later build must add (not written now)

1. Close-only `fwd_mfe`/`fwd_mdd`/`terminal_state` byte-identical to current `grading.py` on a frozen fixture.
2. `ohlc` MFE ≥ close-only MFE and `ohlc` MAE ≤ close-only MAE on every fixture with H/L (weak monotonicity).
3. Yahoo-only symbol: `ohlc` attach raises / returns unevaluable; does not emit close-as-high.
4. Same-position high *and* low through both barriers: stop/adverse wins.
5. Missing open: `gap_through_*` is None, not False.
6. Cushion incidence denominator = n_gradable, including stopped-before-cushion.
7. Radar `attach` vs spine `ohlc` + `radar_atr_*` agree on a frozen episode fixture (or a documented, tested delta).

---

## 11. Boring-baseline note

The boring solution is: keep using `grading.forward_metrics` + `terminal_state` for holdability, and keep Radar outcomes for detector research. This draft is only justified if a later wave needs **one** row that can carry *both* close-path and OHLC-path under named parameterizations. If that join is not required, do not implement §2.2 on the spine — call Radar for OHLC and the spine for close, and stop.
