# F0 — Canonical Grader Reuse Map

**Commission:** MASTERMIND GROK-F0  
**As-of:** 2026-08-18  
**Tree:** `origin/main` @ `3d12412e561e`

**Verdict:** Path Survival has a named owner already — `engine/grading.py`. The build extends that module (and the ledgers that already call it). It must not mint `engine/path_survival/` as a second grader. Two siblings already compute path numbers under different laws: `engine/track_scoring.py` (forced-H=10 `capture`) and Radar `replay/outcomes.py` (OHLC + ATR). Both should become *callers* of extended spine primitives, not permanent twins.

---

## 1. The one grader (target state, already law)

`research/SETUP_SPECIES_MASTERPLAN_BY_FABLE.md` §1.2 **PRIMARY SOURCE VERIFIED**:

> One grader (target state, not current fact). … **W0.1 makes `engine/grading.py` the one grader** via explicit per-ledger migrations … market-native fill conventions preserved (CN T+1 HL2 + locked-limit exclusion; HK suspension rule; US next-bar close). The spine does not flatten markets; it centralizes primitives.

W0.1a shipped the primitives (`fwd_mfe`, `terminal_state`, `cushion_incidence`, PIT membership) as PR #1100. W0 Stage B-b deleted `grade_us_board`'s private `_fwd_ret` / `_close_path_mae` and routed through `forward_metrics` (PR #1142). Stage B-a threaded the spine onto `track_record` (PR #1139). Stage B-d added CN-native spine axes on T+1 HL2, **explicitly not** via `grading.fill_index` (PR #1151).

That is the reuse contract Path Survival inherits. Creating a new truth store or a new `terminal_state2` would violate it.

---

## 2. What to reuse unchanged

| Primitive | Reuse as | Do not change |
|---|---|---|
| `fill_index` | US (and default) fill | next-bar close; `same_bar` stays shadow-only |
| `forward_metrics` | close-path MFE/MAE/return | window `(fill, fill+H]`; `fwd_mdd` stays ≤0; `fwd_mfe` stays ≥0 |
| `terminal_state` / `TerminalState` | % barrier race, close basis | STOP / DEAD_MONEY / CUSHIONED / CLEAN_LIFTOFF; stop-wins on same close |
| `terminal_state_short` | short-side mirror | do not call long `terminal_state` with `liftoff_mult<1` |
| `cushion_incidence` / `post_cushion_breach` / `_cushion_stop_scan` | competing-risk cushion | one scan definition; never median-over-reachers |
| `STOP_BARRIER` `CUSHION_BARRIER` `LIFTOFF_*` `SPINE_HORIZONS` | named % parameterizations | freeze; new barriers = new named parameterization |
| `GradeBasis` | TR vs price stamp | never silently swap |
| `resolve_series` / `load_dead_prices` / `as_of_panel` | survivorship + delist | keep degrade-and-stamp |
| `REJECTION_TAXONOMY` | near-miss reasons | append-only via §8 |

Callers that already route through the spine (**CODE VERIFIED** import/use):

- `scripts/grade_us_board.py` — writes `fwd_mfe_*`, both terminal states, `post_cushion_breach`
- `engine/track_record.py` — W0.1a spine columns
- `engine/etf_board_ledger.py` — `forward_metrics`
- `engine/us_entry_status_remeasure.py` — `forward_metrics`
- `engine/name_score_grader.py`, `engine/sector_central_grader.py`
- `engine/provisional_replay.py`, `scripts/oracle_asymmetry_regrade.py`
- `engine/prophet_stage_fusion.py` — `terminal_state` clean15_126 & clean8_21
- `tests/test_grading_spine_v2.py`

Nightly **PRODUCTION VERIFIED** (workflow): `daily.yml` runs `grade_us_board --nightly` and `build_track_record`.

---

## 3. What to reuse as *semantics*, not as a second library

### 3.0 `engine/track_scoring.py` (already a second close-path scorer)

Reuse `capture` (realised / MFE, `MFE_FLOOR`, `n_capture_undefined`) and the forced-verdict-at-H law. Do **not** copy `score_from_fill` into a Path Survival package. If the spine grows a `capture` column it must match this definition (percent units vs ratio is a named choice — see open questions).

US fill here is next-bar close; CN fill is T+1 open with `include_fill_bar=True`. That market-native split is the same law as the spine, implemented a second time. Path Survival should not add a third.

### 3.1 Radar `engine/entry_radar/replay/outcomes.py`

This is the only production-quality high/low first-passage implementation in the estate.

Reuse these *laws*, by lifting them into `engine/grading.py` as an **optional OHLC plane** (new functions, same module):

- First-touch on highs (favorable) / lows (adverse), not closes.
- Day-0 sampled remainder as position `(0, i)` ahead of daily sessions `(1, s)` for LIVE rows.
- Adverse-first tie when both touch in the same position.
- ATR-scaled barriers as a **named parameterization** (`radar_fs_1.25_1.00_H10`), not as a replacement for `STOP_BARRIER=0.95`.
- `gap_through_invalidation` = `open < invalid AND prior_close >= invalid`.
- Censor, never drop, short windows (`censored`, `terminated_reason`).
- Exclude close-proxy ATR from false-start primary (`atr_basis != true_range_daily_ohlc` → `None`).
- Daily primary never consults minutes (`outcomes.py` 8–10).
- Vendor plane is **split-only** (`entry_radar_vendor.py`), not Yahoo TR. Do not pool Radar MFE with spine `fwd_mfe`.
- `day0_samples` is declared and unread by any producer in-tree. Do not treat LIVE day-0 remainder as live until a producer exists.

Do **not** import `engine.entry_radar.replay` from `engine.grading`. Direction of reuse is spine ← Radar laws, then Radar becomes a caller.

Do **not** change Radar W4 live eval. It is outcome-blind by contract (`live_eval.FORBIDDEN_KEY_TOKENS` includes `mfe`, `mae`, `forward`, `outcome`) **CODE VERIFIED**.

### 3.2 Radar `replay/prereg.py`

Frozen numbers to cite, not to re-derive:

- `HORIZON_PRIMARY = 10`
- `FALSE_START_ADVERSE_ATR = 1.25`, `FALSE_START_FAVORABLE_ATR = 1.00`
- `TARGET_ATR = 1.00`, `INVALIDATION_ATR = 1.25`
- FIT / TEST / holdout dates
- Detector spec hashes

A Path Survival contract that silently changes these is a second grader.

### 3.3 Radar `replay/ruler.py`

Inference, not measurement: per-name-first, month-cluster bootstrap, Wilson on rates. Path Survival measurement rows should stay episode-level; any promotion read uses this *shape* (or Eval-OS) rather than inventing a pooled-fire mean.

### 3.4 Stock Identity `episodes.py` + `plane.py`

Reuse:

- `price_plane_id` stamp on every row (`stocks_tr_v1` / `baskets_ohlcv_v1` / `stock_identity_ohlcv_v1`).
- Open-column availability law: no open on `data/stocks` ⇒ gap family off, not imputed.
- Ban on raw `massive_stock_day` for MA / drawdown / gap math (`plane.py` 27–28).
- A0 = Wilder ATR(14) at prior confirmed close (LER convention).
- Censor open legs; `resolution_known_date` for PIT consumers.
- Labels use future data **by design** and must never ship as live signals (`episodes.py` 30–34).

Do **not** treat SI episodes as trades. They are expert-independent path segments. W3 "episode ruler engine" is still `todo` (`WS-STOCK-IDENTITY`). Path Survival must not implement W3 under another name.

### 3.5 QLedger / Eval-OS

Reuse:

- Next-bar fill (`_fill_entry`) and stamped `fill_convention`.
- Declared `horizon_unit` + market calendar (`claim_window`). Control leg refuse-closed if it cannot share the window.
- Forward-only registration / evidence clock.
- `do_not_redo` in `WS-EVAL-OS-MEASUREMENT-LAW`: no retrospective claims; no `backfilled` flag; no `GRADE_HORIZONS` > 63.

Do **not** add MFE/MAE columns to `grades.jsonl` as a side effect of Path Survival. QLedger's job is claim hit / signed excess / promotion legality. Path metrics belong on fire/episode rows (board, track_record, Radar forward table), which QLedger may later *cite*.

### 3.6 China standout track

Reuse the *pattern*: market-native fill, shared **barrier constants** from `grading`, per-row `fill_basis` / `basis_used`, never claim `t1_hl2` when the fill was open. Path Survival US work must not call `grading.fill_index` on A-shares.

### 3.7 Mastermind bot

Reuse as *operational* consumers, not as measurement law:

- `held_risk` MFE/giveback flags (heuristic v0, `PRD-R11`).
- `entry_quality` advisory pre-entry (sizes nothing).
- `brain/outcomes` thesis labels (close +15/−10, target-wins, same-bar-ish anchor).

If the bot needs Path Survival numbers, it reads Macro spine / Radar-forward artifacts. It does not grow a fourth grader.

---

## 4. What must not be reused as-is

| Item | Why |
|---|---|
| Radar `mfe`/`mae` names as drop-in for `fwd_mfe`/`fwd_mdd` | high/low vs close; different P0 |
| Mastermind `brain/outcomes` target-before-stop | +15/−10, target-wins, not next-bar |
| `entry_primitives.time_underwater_series` as "time underwater the trade" | it is bars-since-252-high, an entry feature |
| `entry_primitives.gap_hold_events` | dormant setup detector |
| `species_registry` as a grader | display-only; GRADER-STARVED |
| Yahoo `close` as high/low first-passage input | no high/low columns |
| `data/massive_stock_day` (even when restored from R2) | unadjusted; SI explicitly forbids it for this math |
| Polygon minutes cache without `vintage` | `adjusted=true` retro-rescale fabricates 4H turns |
| QLedger `_fwd_ret` calendar-day legacy path | `CLOCK_LEGACY`; do not pool with explicit-clock rows |

---

## 5. Recommended reuse topology

```
                    ┌─────────────────────────────────────┐
                    │  engine/grading.py   CANONICAL      │
                    │  fill + close-path + (NEW) ohlc-path│
                    │  named parameterizations only       │
                    └──────────────┬──────────────────────┘
           ┌───────────────────────┼───────────────────────┐
           v                       v                       v
   grade_us_board /         china_standout          entry_radar.replay
   track_record /           (native T+1 HL2;        (becomes a CALLER
   prophet fusion           shared constants)        of ohlc-path + ATR
                                                     parameterization)
           │
           v
   QLedger cites fire-level path rows
   (does not grow a path grader)
           │
           v
   Mastermind held_risk / outcomes
   (consume published artifacts)
```

Stock Identity stays a *catalog* that can *join* Path Survival rows by `(symbol, date, plane)`. It does not grade trades.

---

## 6. Authority / ownership (do not invent)

| Concern | Owner already | Path Survival may |
|---|---|---|
| Close-path honesty axes | `engine/grading.py` | extend in-module |
| Species promotion objects | Setup Species + spine states | add context metrics only |
| Radar detector identity / W5 prereg | `WS-LIVE-ENTRY-RADAR` | reuse outcomes laws; do not restamp hashes |
| Episode catalog | `WS-STOCK-IDENTITY` | join; do not build W3 |
| Claim clock / promotion | `WS-EVAL-OS-MEASUREMENT-LAW` | do not alter `grade_claim` arithmetic |
| Live hold flags | Mastermind `held_risk` | do not change thresholds |
| Minute fetch | `vendor_minutes.py` (C3 only) | do not bulk-crawl |

No Agent OS workstream named Path Survival exists at census time (`agentos/` grep empty). That is not permission to create a control plane. If a workstream is minted later, it should `owns_paths` include `engine/grading.py` extensions + `research/path_survival/`, and must list Radar / SI / Eval-OS as *neighbors*, not as territory to rewrite.

---

## 7. NO-BUILD warnings

- Do not create `engine/path_survival/grader.py`.
- Do not copy `forward_metrics` into a Radar-only helper.
- Do not promote Radar H=10 ATR false-start to a house gate.
- Do not flatten CN T+1 HL2 into US next-bar close.
- Do not fit a holdability model. This map is measurement reuse only.
