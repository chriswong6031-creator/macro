# PILLAR D1 — The Cycle Ontology + Unified State Machine

**Design document for the solution masterplan. Keystone pillar: every other pillar imports this one.**
All paths relative to repo root (canonical main = `/tmp/macro-cycle-fable-main/`). Audit references are to
`research/CYCLE_INTELLIGENCE_PROBLEM_AUDIT_FOR_FABLE.md` (findings J1–J7, I#1–#5, Part III Phase 1).

---

## 0. Executive thesis

The audit's root disease is that "position", "phase", "turn", and "action" each have 3–5 incompatible
definitions living in five hand-mirrored files that have **already drifted** (proof: `sector_cycles.py:68`
claims its PHASES hues are "identical … to site/cycle_data.js" — they are not; Trough is `#5b9bf0` in
Python and `#e06464` in JS, Recovery and Expansion differ too). The fix is not documentation; it is a
**compiled contract**: one Python module, `engine/cycle_ontology.py`, that owns

1. the ONE canonical 0–100 position semantic (a vol-standardized detrended z mapped through a normal CDF —
   replacing the range-stochastic whose confirmed-peak readings span 17.6–99.7),
2. the master 5-phase wheel with the ladder / DC / IC / BUY-SELL vocabularies declared as **sub-reads**
   through an explicit 5×8 crosswalk matrix with a "clocks disagree" state,
3. the ONE turn primitive (ZigZag as the cycle-turn detector, `find_troughs` demoted to a declared
   timing-ladder sub-detector; confirmed-vs-provisional contract; `confirmed_at` timestamps; stable
   `turn_id`s + tolerance re-keying so narrative bindings survive re-detection — defusing N2),
4. the fused state machine `resolve_state()` inside `_record_core` so contradictory action pairs
   (Peak/SELL beside BOTTOM WATCH/GET READY) **cannot co-fire**, and
5. a build step that GENERATES `site/cycle_ontology.js` from the Python module so JS cannot drift again.

Crucially, the JS side receives **data + resolved outputs, not logic**: `resolve_state()` runs only in
Python at build; pages render `now.stance` / `now.divergence` — they never recompute it. That is the only
architecture in which "JS cannot drift" is literally true.

Migration is staged with zero flag-days: new fields ship **alongside** legacy fields, the position flip is
gated on a backfill acceptance study (registered in the admin Experiments tracker per N4), and the
narrative re-keying migrator runs automatically whenever detector params or price basis change.

---

## 1. The position semantic

### 1.1 Decision

**Canonical position = `100 · Φ(z)` where `z` is the smoothed log-detrend residual standardized by its own
EWMA volatility.** One formula, three frequency parameter sets (D/W/M), every parameter declared and
versioned in the ontology.

```
d_t     = ln(P_t) − ln( EMA(P, span=trend_span, min_periods=trend_span//2)_t )
d̃_t     = EMA(d, span=smooth_span)_t
σ_t     = EWMSTD(d, span=trend_span, min_periods=trend_span//3)_t
σ*_t    = max(σ_t, 0.25 · expanding_median(σ)_t)          # causal vol floor
z_t     = d̃_t / σ*_t
pos_t   = 100 · Φ(z_t)                                     # Φ = standard normal CDF
```

- `P` = **close_price** (split-adjusted, dividend-UNadjusted) once the dual-basis data contract (data-basis
  pillar) lands; until then `close_tr` with the basis honestly labeled (`pos_basis` field, §4.4). The
  formula is basis-agnostic; the *label* is mandatory.
- `Φ` implemented with `math.erf` lifted elementwise (`np.frompyfunc(math.erf,1,1)`) — pure
  stdlib+numpy, respecting the repo's no-scipy render-path doctrine (see `engine/grading.py` comment,
  S5 scout).
- The causal vol floor (`0.25 × expanding median of σ`) prevents the quiet-period explosion where a
  near-zero trailing σ turns a 2% wobble into z=3. Expanding median = PIT-clean.

**Frequency parameter sets** (declared as `POSITION_PARAMS` in the ontology):

| freq | trend_span | smooth_span | min_bars | intended series |
|---|---|---|---|---|
| `D` | 252 bars | 10 | 200 | ETFs, sectors, baskets, daily FRED tapes (HY OAS, BDI) |
| `W` | 52 bars | 2 | 40 | weekly resamples (rare; ladder IC uses its own machinery) |
| `M` | 36 bars | 2 | 24 | monthly macro tapes: Case-Shiller, DRAM contract ASP, ISM (N1) |

A per-series override (`trend_span`) is allowed **only via the proxy registry** (§6) — e.g. a structural
18-year housing frame may register `trend_span=60` months so the secular swing isn't detrended away. Every
override is a declared, versioned registry entry, never an inline constant.

### 1.2 Why this and not the alternatives

**Against the incumbent range-stochastic** (`sector_cycles._detrended_osc`, `sector_cycles.py:92-103`):
its 0–100 is `(dt − rolling252_min) / (rolling252_max − rolling252_min)` — the denominator is whatever
range the *last year happened to contain*. After 12 quiet months the range is tiny and noise spans 0–100;
right after a crash the range is huge and a genuine cyclical peak reads mid-range. That is exactly the
audit's finding: **confirmed peaks span 17.6–99.7** on this gauge — the number is not comparable across
assets or even across time for one asset. The z/CDF form replaces the brittle rolling min/max with a
smoothly-adapting σ: `pos ≥ 84` means "≥ +1σ above own trend" for XLU, XLK, EWZ, Case-Shiller and a
crypto basket alike. This cross-sectional comparability is also **load-bearing for T3**: the hazard model
pools age/amplitude covariates across sectors+countries+baskets, and pooling a non-comparable position
covariate would poison it. Choosing the standardized-z semantic is what makes the pooled hazard legitimate.

**Against drawdown-percentile / `92·exp(−dd/30)`** (`markets_app.js:71`): drawdown-from-ATH conflates
cycle position with secular regime. Post-1990 Nikkei (or 2000–2013 SPX) would read "washed out" for a
decade+ regardless of the intermediate cycles actually traded; a market making new ATHs is pinned at 92
whether it is early or late in its advance; and the transform has no trough symmetry. It also measures
*distance from a single historical point* (the ATH), which repaints meaning every time a new ATH prints.
Refuted as the canonical semantic. **Retained as a clearly-relabeled auxiliary stat**: markets.html may show
"% from ATH" as a labeled fact, never on the 0–100 cycle axis.

**Against a hybrid** (z-CDF blended with percentile-of-own-history): a second parameter (blend weight) with
no principled setting, and destroys the clean "pos = Φ(z)" interpretability that the UI zone bands and the
hazard covariates rely on. Rejected: simplicity is a feature of a *contract*.

**Causality & backfillability (T4):** every term is trailing (EMA, EWMSTD, expanding median). The S2 scout
confirmed `sector_cycles.compute(asof=…)` already slices the panel before all math; `canonical_position`
keeps that property, so PIT backfill is exact.

### 1.3 Zone bands & thresholds (canonical scale)

Declared once in the ontology (`ZONES`), consumed by all five pages:

| pos | z | zone word (en / zh) |
|---|---|---|
| ≥ 84 | ≥ +1.0σ | Stretched / 超涨 |
| 68–84 | +0.47…+1.0σ | Elevated / 偏高 |
| 32–68 | ±0.47σ | Mid-range / 中位 |
| 16–32 | −1.0…−0.47σ | Depressed / 偏低 |
| ≤ 16 | ≤ −1.0σ | Washed out / 超跌 |

The phase-band cuts (68/32, matching `_classify_phase`'s current cuts) are retained for v1 continuity and
become **bound calibration constants**: the calibration pillar (T4) may refit them from the backfilled
walk-forward, and any refit bumps `ONTOLOGY_VERSION`.

### 1.4 How the same semantic renders on every page

- **sector_cycles / country_cycles / china_sector_cycles**: computed in `_record_core` (§4), emitted per
  series as the `osc` point series + `now.pos`. No page-local transforms.
- **cycle.html (flagship)**: every MEASURED-tier cycle (T1) is mapped by the proxy registry (§6) to a live
  tape (daily or monthly) and gets `canonical_position` at that tape's frequency. STRUCTURAL-tier frames
  (housing 18y, gold 17y…) *also* get the canonical position on their monthly proxy — structural tier
  removes *grading/hazard claims*, not the gauge. The hand-authored `now.pos` is deleted as an input; it may
  survive only as a narrative annotation checked by the build-time tolerance assertion (T6, flagship pillar).
- **markets.html**: the 0–100 axis becomes canonical position computed from the country ETF tape via
  `country_cycles` (the audit's "canonical intl engine" direction); `posFromDrawdown` is retired from the
  axis and re-labeled "% from ATH" as a card stat.
- Zone words, hues, band edges all come from the generated `site/cycle_ontology.js` — one source.

---

## 2. The master phase wheel + crosswalk

### 2.1 Master wheel

The 5-phase wheel is the master taxonomy: **Trough, Recovery, Expansion, Peak, Downturn** (unchanged
labels; the ontology becomes their single home — labels, shorts, hues, zh — killing the drifted duplicate
in `cycle_data.js` and the copy in `sector_cycles.PHASES`).

`classify_phase` moves from `sector_cycles._classify_phase` into the ontology, same logic (level from
canonical position, direction from weekly+3D MACD votes with osc-slope tiebreak), with two contract
additions:

1. **`phase_dir`** ∈ {rising, falling} is emitted explicitly (it is currently internal).
2. **Hysteresis hook**: `confirm_persist: int = 0` parameter — when > 0, a phase change is only committed
   after `confirm_persist` consecutive stamps agree (causal; prevents Expansion↔Downturn flapping on a
   one-week MACD wobble — see New Problem NP-4). Ships OFF (0) in v1 for behavioral continuity; the
   backfill study (D1-W5) measures flap rate and the calibration pillar decides the v1.1 value.
3. **`phase_age_bars`** + `last_transition` date are emitted — the N3/T3 hook: hazard and graders get
   age-in-phase without re-deriving it.

```python
def classify_phase(pos_now: float, osc_slope: float, w: dict, t3: dict,
                   *, prev_phase: str | None = None, confirm_persist: int = 0,
                   pending: dict | None = None) -> PhaseRead
# PhaseRead = {"phase","phase_label","phase_label_zh","phase_dir","votes","pending"}
```

### 2.2 Declared sub-reads

| vocabulary | declared role | source | ontology field |
|---|---|---|---|
| 5-phase wheel | **MASTER** — the cycle read | `classify_phase` | `now.phase` |
| 8-state ladder | daily **timing** sub-read | `cycles.ladder_state` (unchanged internals; keys frozen for calibration continuity) | `now.timing_state` |
| DC-phase (new/mid/approaching/in_band/stretched) | daily-cycle **age** sub-read | `cycles.cycle_state` | `now.dc_phase` |
| IC-phase (early/mid/late/overdue) | investor-cycle **age** sub-read | `cycles.cycle_state` | `now.ic_phase` |
| BUY/SELL `signal` | **phase-transition badge** — re-derived (§2.4), no longer independent thresholds | ontology `transition_signal` | `now.signal` |
| markets.html free-text `phaseLabel` | **KILLED** — must be one of the 5 wheel labels | — | — |

The UI ranking is part of the contract: the wheel is the headline; ladder/DC/IC render as a "timing"
drill-down section, visually subordinate; the resolved `stance` (§3) is the only action-toned text.

### 2.3 The crosswalk matrix (permitted combinations)

`CROSSWALK[(phase, ladder_state)] → {stance, divergence, note}`. The **stance vocabulary** (9 values, all
with en/zh + a semantic `tone` so zh up/down color-flip works via existing root tokens, never hardcoded
colors):

| stance | zh | tone |
|---|---|---|
| AVOID | 回避 | bearish |
| WAIT | 观望 | neutral |
| GET READY | 准备 | anticipatory |
| BUY | 买入 | bullish |
| HOLD | 持有 | bullish |
| TRIM | 减仓 | caution |
| SELL | 卖出 | bearish |
| COUNTERTREND ONLY | 仅限逆势短线 | caution |
| HIGH-RISK BOUNCE | 高风险反弹 | caution |

**The full 5×8 matrix** (D = divergence flag set → the "clocks disagree" state; cells marked `pos≥55` /
`pos≤45` are the two positionally-qualified cells):

| ladder \ phase | Trough | Recovery | Expansion | Peak | Downturn |
|---|---|---|---|---|---|
| DECLINE | AVOID | AVOID **D** | WAIT **D** | TRIM | AVOID |
| BOTTOM WATCH | GET READY | GET READY | WAIT | COUNTERTREND ONLY **D** | WAIT |
| TURN SIGNALED | BUY (setup) | BUY (setup) | BUY (setup) | COUNTERTREND ONLY **D** | pos≥55: COUNTERTREND ONLY **D** · pos<55: GET READY |
| FRESH BUY | BUY | BUY | BUY | COUNTERTREND ONLY **D** | pos≥55: COUNTERTREND ONLY **D** · pos<55: BUY (partial) |
| RALLY ON | HOLD **D** | HOLD | HOLD | HOLD | HOLD **D** |
| TOP WATCH | WAIT **D** | HOLD (don't-chase) | TRIM | TRIM | TRIM |
| ROLLING OVER | WAIT **D** (base-watch) | WAIT **D** | TRIM | SELL | SELL |
| COUNTERTREND BOUNCE | HIGH-RISK BOUNCE | HIGH-RISK BOUNCE | HIGH-RISK BOUNCE | HIGH-RISK BOUNCE | HIGH-RISK BOUNCE |

Rationale for the load-bearing cells:

- **Peak × {BOTTOM WATCH, TURN SIGNALED, FRESH BUY} → COUNTERTREND ONLY + D.** This is the audit's live
  EWN/XLK/EWT pathology (finding I#5): a stretched topping market carried "GET READY"/"BUY SETUP". The
  daily-cycle low hunt is real information but at pos≥68 with falling higher-timeframe momentum it is a
  *tactical countertrend* trade, never a cycle buy. The ladder detail stays visible in the drill-down; the
  headline stance is COUNTERTREND ONLY with the divergence chip.
- **Trough × {TOP WATCH, ROLLING OVER, RALLY ON} → D.** Mirror image: sell-side daily reads inside a
  washed-out falling phase are late-downleg noise; stance WAIT ("base-watch"), SELL suppressed.
- **DECLINE overrides**: `failed_cycle` is the platform's strongest bearish tell (`cycles.py:14-15`), so
  DECLINE never softens below AVOID/WAIT/TRIM anywhere; in Recovery/Trough it keeps AVOID but sets D
  (the phase read is now suspect — the resolved record also emits `phase_conf:"low"`).
- **Peak × DECLINE → TRIM, no D**: a failed daily cycle while stretched IS the early rollover — the
  clocks *agree* on caution.

**The "clocks disagree" state** is `divergence: true` + `clocks: {phase, ladder, agree:false}` — an
explicit, first-class output. The UI contract: when set, pages render ONE amber "Clocks disagree —
tactical read differs from cycle read" chip (dual-span en/zh) instead of two contradictory action badges.

### 2.4 The transition `signal` (re-derived)

The current independent thresholds (`BUY if pos≤45 & slope>0.5`, `sector_cycles.py:329-330` — the audit's
"fifth vocabulary", finding J7) are deleted. New definition:

```
signal = "BUY"  iff  last_transition == Trough→Recovery within SIGNAL_TTL_BARS (default 10)
                     AND ladder_state ∈ {TURN SIGNALED, FRESH BUY}
signal = "SELL" iff  last_transition == Peak→Downturn within SIGNAL_TTL_BARS
                     AND ladder_state ∈ {TOP WATCH, ROLLING OVER, DECLINE}
else None
```

The badge is now *by construction* the phase-transition event confirmed by the timing sub-read — it cannot
contradict either clock. Emitted with `signal_basis: "phase-transition-v1"` so graders know what promise
they are grading.

### 2.5 Regression test

`tests/test_cycle_ontology.py` (new; runs in the normal pytest suite, no network):

1. **Completeness**: all 40 (phase, ladder) pairs resolve; no KeyError; every stance ∈ STANCES; every
   stance/note has non-empty en+zh.
2. **No contradictory pair** (the property the audit demands): for every resolved record,
   `tone(stance)` is never `bullish` while `phase ∈ {Peak, Downturn} and pos ≥ 55` unless
   `divergence==True` is impossible — concretely: assert the matrix contains **zero** cells where phase ∈
   {Peak} and stance ∈ {BUY, GET READY} (enumerated assertion, not sampled).
3. **Signal coherence**: `transition_signal` can never return BUY when phase ∈ {Peak, Downturn} nor SELL
   when phase ∈ {Trough, Recovery} (property test over the transition table).
4. **Live-output sweep**: load `site/sectordata/sector_cycles.json` (and country/china equivalents) when
   present; assert every `now` block has `stance`, and `divergence==False → direction(stance)` consistent
   with `phase_dir` per the matrix. (This is the guard that catches a future engine change that bypasses
   `resolve_state`.)
5. **Generated-JS sync**: regenerate `site/cycle_ontology.js` in-memory and diff against the committed
   file — fail if stale (the anti-drift tripwire; same pattern as `check_nav_mega`).

---

## 3. The turn primitive

### 3.1 One contract

```python
@dataclass
class TurnParams:
    pct: float                 # ZigZag reversal threshold (%)
    basis: str                 # "close_price" | "close_tr" (until data pillar lands)
    freq: str                  # "D" | "M"
    version: int = 2           # detector version — bumped on any algo/param change

def detect_turns(close: pd.Series, *, series_id: str, params: TurnParams) -> list[dict]
```

- **Detector = ZigZag** (`_detect_swings` MOVES into `engine/cycle_ontology.py`; `sector_cycles`
  re-imports for compatibility). It is the only detector allowed to produce *cycle turns* — the objects
  that charts plot, narratives bind to, projections/hazards consume, and graders score.
- **`find_troughs` is NOT killed — it is demoted and declared**: it remains the timing ladder's internal
  short-cycle low detector (dc_day/ic_week counting). The ontology documents this role split in code
  (`SUB_DETECTORS = {"find_troughs": "timing-ladder daily/investor cycle lows — NOT cycle turns"}`), and
  the kernel stops treating its outputs as "the trough" anywhere user-facing. Killing it would rewrite
  2,200 lines of ladder logic plus its calibration lineage for zero ontology gain; assigning roles fixes
  the "same instrument, two last-bottom answers" problem because only ZigZag turns are ever *called* turns.
  `_pivots` stays an RSI-divergence internal utility (never emits "turns").
- **Confirmation rule** (made explicit + extended): a pivot is CONFIRMED when price has reversed ≥ `pct`%
  from the running extreme. The detector now also records **`confirmed_at`** — the bar index/date at which
  the threshold was crossed — and `confirm_lag_bars`. This is the PIT-honest knowledge date: the hazard
  model (T3) and the turn-precision grader (T4) must key off `confirmed_at`, not the pivot date, or they
  leak. (Today this field does not exist anywhere — the backfill would silently grade turns as known
  months before they were knowable.)
- **Provisional flag surfaced**: the final running-extreme entry keeps `provisional: true` and the contract
  now requires consumers to honor it: UI renders provisional pivots hollow/dashed with a "provisional /
  暂定" label; graders and the hazard fit EXCLUDE provisional turns; `_project_next`/hazard project from
  the last CONFIRMED turn with the provisional extreme shown as context.

### 3.2 Turn JSON shape (the wire format everywhere)

```json
{"turn_id": "xlk:trough:2022-10",
 "k": "trough", "date": "2022-10-12", "t": "2022-10", "x": 2022.78,
 "px": 112.44, "basis": "close_tr",
 "mag_pct": 33.1, "major": true,
 "provisional": false,
 "confirmed_at": "2022-11-30", "confirm_lag_bars": 34,
 "detector": {"name": "zigzag", "pct": 14.0, "version": 2, "params_hash": "a1b2c3"}}
```

`turn_id = f"{series_id}:{kind}:{YYYY-MM of date}"` — **quantized to month** deliberately: month
quantization absorbs the typical few-day re-dating that a basis fix or threshold tweak causes, so most
re-detections keep the same id. Collisions (two same-kind turns in one month) get a `-b` suffix and are
rare by construction (ZigZag alternates).

### 3.3 Re-keying scheme for narrative bindings (N2 defused)

Today `data/sector_cycles/narratives.json` legs are keyed by **exact pivot date** (`"2018-12-24"` etc. —
verified) and the 14% threshold is frozen *specifically* so those dates never move
(`sector_cycles.py:283-288`). Fixing the price basis (data pillar) or any threshold re-dates every pivot
and orphans every key. The scheme:

1. **Bindings move to `turn_id`s** (month-quantized) with a recorded `bound` block:
   ```json
   "legs": {"xlk:trough:2018-12": {"title": "...", "body": "...",
            "bound": {"date": "2018-12-24", "detector_version": 1, "px": 58.6}}}
   ```
2. **`match_turns(old_bindings, new_turns, tol_days=60) -> dict[old_key, new_turn_id | None]`** in the
   ontology: for each old binding, candidate = same `kind`, nearest date within ±60 calendar days; if a
   unique candidate exists → rebind; if two candidates tie or none within tolerance → **orphan**.
3. **`scripts/migrate_narrative_keys.py`** (one command, idempotent): reads every narratives.json
   (sector, china, country, intl, cycle-flagship once it exists), runs `match_turns` against the freshly
   detected turn set, rewrites keys in place, moves unmatched entries to a top-level `"orphaned": {}`
   section with the reason, prints a migration report. Build behavior: orphans WARN (page renders without
   that leg's prose — the graceful-degrade house pattern), never fail the build.
4. **Version stamp gate**: `compute()` emits `detector.version`+`params_hash` in meta; the build asserts
   `narratives.json .meta.detector_version` matches, else instructs to run the migrator. This is what
   finally **unfreezes** the ZigZag threshold and the price basis: any re-detection is a mechanical
   `migrate → review orphans → commit` instead of a manual re-research of every leg.

---

## 4. The state machine in `_record_core`

### 4.1 New kernel flow

`engine/sector_cycles._record_core` (the ONE kernel all three engine pages delegate to) changes to:

```python
from engine import cycle_ontology as onto

def _record_core(full, win_start, last_ts, pct=_ZZ_PCT, *, freq="D",
                 series_id="", basis="close_tr", prev_phase=None) -> dict | None:
    ...
    pos_series = onto.canonical_position(full, freq=freq)           # §1
    turns      = onto.detect_turns(full, series_id=series_id,
                                   params=onto.TurnParams(pct=pct, basis=basis, freq=freq))
    res  = cycles.analyze(full, kind="equity")                      # unchanged — ladder/DC/IC
    lad, mtf = res.get("ladder", {}), res.get("mtf", {})
    ph   = onto.classify_phase(pos_now, osc_slope, mtf.get("W", {}), mtf.get("3D", {}),
                               prev_phase=prev_phase)               # §2.1
    rs   = onto.resolve_state(pos=pos_now, phase=ph["phase"], phase_dir=ph["phase_dir"],
                              ladder_state=lad.get("state") or "",
                              dc_phase=(res.get("cycle") or {}).get("dc_phase"),
                              ic_phase=(res.get("cycle") or {}).get("ic_phase"),
                              failed_cycle=bool((res.get("cycle") or {}).get("failed_cycle")))
    sig  = onto.transition_signal(prev_phase, ph["phase"], lad.get("state") or "")
```

### 4.2 `resolve_state` — exact rules (ordered; this IS the crosswalk §2.3 plus overrides)

```python
def resolve_state(*, pos, phase, phase_dir, ladder_state,
                  dc_phase=None, ic_phase=None, failed_cycle=False) -> dict:
    # 1. failed-cycle override: DECLINE + failed_cycle → stance from matrix but never
    #    softer than the matrix cell; sets phase_conf="low" in Trough/Recovery.
    # 2. matrix lookup: cell = CROSSWALK[(phase, ladder_state)]; apply pos-qualifier
    #    for the two Downturn buy cells (pos>=55 → COUNTERTREND ONLY + D).
    # 3. emit:
    return {"stance": ..., "stance_zh": ..., "tone": ...,          # §2.3 vocab
            "divergence": bool, "divergence_note": ..., "divergence_note_zh": ...,
            "clocks": {"phase": phase, "ladder": ladder_state, "agree": not divergence},
            "phase_conf": "normal" | "low"}
```

### 4.3 What the kernel STOPS emitting raw

- `now.action` is no longer `STATE_DISPLAY[ladder].action` verbatim — it becomes the resolved `stance`
  (the ladder's own action string moves into the timing drill-down object as `timing_action`).
- `now.signal` is the transition badge (§2.4), never the old independent thresholds.
- The ladder's internal state key (`timing_state`) is **kept unchanged** so `ladder_calibration.json`
  continuity and the S3-scouted calibration lineage hold (T4 requirement).

### 4.4 The `now` block — full new shape (superset of current; legacy fields kept one release)

```json
"now": {
  "phase": "Peak", "phaseLabel": "Topping", "phase_dir": "rising",
  "phase_age_bars": 63, "last_transition": "2026-04-02", "phase_conf": "normal",
  "pos": 88.7,                       // legacy range-stochastic (DEPRECATED, removed in M3)
  "pos_v2": 79.3, "pos_basis": "close_tr", "pos_params": "D/252/10",
  "stance": "TRIM", "stance_zh": "减仓", "tone": "caution",
  "divergence": true,
  "divergence_note": "Cycle read is Topping; the daily timing ladder is hunting a short-term low. Any buy here is countertrend only.",
  "divergence_note_zh": "周期读数为做顶中；日线时点阶梯正在寻找短线低点。此处任何买入仅属逆势短线。",
  "clocks": {"phase": "Peak", "ladder": "BOTTOM WATCH", "agree": false},
  "signal": null, "signal_basis": "phase-transition-v1",
  "timing_state": "BOTTOM WATCH", "timing_action": "GET READY",   // drill-down only
  "dc_phase": "in_band", "ic_phase": "late",
  "lastTrough": "2025-04", "lastPeak": "2026-05",
  "rs_63d": 4.6, "rs_rank": 3, "above200d": true,
  "ontology_version": "1.0.0",
  "read": null
}
```

i18n: every new user-visible string (stances, divergence notes, zone words) carries en+zh in the ontology
tables; pages render them dual-span (`l-en`/`l-zh`); `t()` never appears in attributes; tones map to the
existing root color tokens so the zh up/down flip continues to work with zero new color logic.

### 4.5 Projection honesty fix (NP-1, engine-side receding horizon)

`_project_next` currently projects `central = today + max(0.05, med − since)` (`sector_cycles.py:204-206`):
once a cycle is *overdue* (`since > med`), the projected turn permanently floats ~18 days ahead of today and
rolls forward every build — the engine-side twin of the audit's `cycle_app.js:63 Math.max` pathology, and it
destroys the very overdue-ness signal the hazard pillar needs. Contract change (implemented in this pillar
because it is part of the projection *semantic*; the hazard pillar later replaces the estimator wholesale):

- projection anchors at the **last confirmed turn**, not today: `central_x = last_confirmed.x + med`;
- if `today > central_x` the record emits `overdue: true` + `overdue_frac = (today − last.x)/med` instead
  of silently pushing the date;
- UI renders "overdue by N months" (dual-span) — never a fake fresh future date.

---

## 5. `engine/cycle_ontology.py` + generated `site/cycle_ontology.js`

### 5.1 Python module — full surface

```python
"""THE cycle ontology — single source of truth for position/phase/turn/stance
semantics across cycle.html, markets.html, country_cycles, sector_cycles(_china),
sector_central(_china). site/cycle_ontology.js is GENERATED from this module
(scripts/gen_ontology_js.py) — never hand-edit the JS."""

ONTOLOGY_VERSION = "1.0.0"

# ---- vocabularies (all with en/zh; hues live ONLY here) ----
PHASES: dict[str, dict]          # 5-phase master {label, short, label_zh, short_zh, hue}
ZONES: list[dict]                # §1.3 bands {lo, hi, word, word_zh}
LADDER: list[str]                # re-exported from cycles.py (keys frozen)
LADDER_DIR: dict[str, int]       # {-1,0,+1} per ladder state
STANCES: dict[str, dict]         # §2.3 {en, zh, tone}
CROSSWALK: dict[tuple[str, str], dict]   # (phase, ladder) -> {stance, div, note, note_zh, pos_gate?}
SUB_DETECTORS: dict[str, str]    # declared roles (find_troughs, _pivots)
POSITION_PARAMS: dict[str, dict] # per-freq (§1.1)
TURN_DETECTOR_DEFAULTS: dict     # {pct_sector:14.0, pct_cn:18.0, vol_scaled:…, version:2}
SIGNAL_TTL_BARS = 10

# ---- functions ----
def canonical_position(close, *, freq="D", trend_span=None, smooth_span=None) -> pd.Series
def classify_phase(pos_now, osc_slope, w, t3, *, prev_phase=None,
                   confirm_persist=0, pending=None) -> dict
def detect_turns(close, *, series_id, params: TurnParams) -> list[dict]     # absorbs _detect_swings
def resolve_state(*, pos, phase, phase_dir, ladder_state, dc_phase=None,
                  ic_phase=None, failed_cycle=False) -> dict
def transition_signal(prev_phase, phase, ladder_state) -> str | None
def match_turns(old_bindings: dict, new_turns: list[dict], tol_days=60) -> dict
def project_next(turns: list[dict], today_x: float) -> dict | None          # §4.5 semantics
def export_payload() -> dict     # everything JS needs, JSON-serializable
```

Pure pandas/numpy/stdlib; no new dependencies; `import cycles` only for the LADDER re-export (no cycle
imports the other way — `cycles.py` stays ontology-free to avoid an import loop; `sector_cycles` is the
composition point).

### 5.2 The generator — `scripts/gen_ontology_js.py`

- Called early in `scripts/build_site.py` (and importable standalone).
- Emits `site/cycle_ontology.js`:
  ```js
  /* GENERATED from engine/cycle_ontology.py vONTOLOGY_VERSION — DO NOT EDIT.
     Regenerate: python -m scripts.gen_ontology_js */
  window.CYCLE_ONTOLOGY = {…export_payload()…};
  window.CYCLE_ONTOLOGY.zoneWord = function(pos, lang){…};   // tiny lookup helpers only
  window.CYCLE_ONTOLOGY.phaseMeta = function(phase){…};
  ```
- **Design rule: data + lookup helpers only.** `resolve_state`, `classify_phase`, `canonical_position`
  never exist in JS — pages render the resolved fields the Python kernel stamped. This is what makes
  "JS cannot drift" structurally true rather than aspirational: there is no second implementation to drift.
- Anti-drift tripwire: test §2.5-(5) regenerates and diffs (mirrors the existing `check_nav_mega` pattern);
  additionally `gen_ontology_js.py --check` exits 1 on diff for use in the render pipeline.
- Note the house gotcha: theme assets source from `templates/` — this file instead follows the
  `*_data.js` pattern (engine-written straight to `site/`), which is correct for generated data. It is
  committed like all site artifacts.
- Build cost: <1s. `canonical_position`/`resolve_state` are O(n) EMA math replacing same-cost code — the
  67-minute render budget is untouched.

### 5.3 Page adoption (which literals die)

| file | literals replaced by `window.CYCLE_ONTOLOGY` |
|---|---|
| `site/cycle_data.js` / `cycle_app.js` | `CYCLE_PHASES` (drifted hues — NP-7), zone bands at `:44-47` |
| `site/markets_data.js` / `markets_app.js` | free-text phaseLabels, y-tick zone words, `posFromDrawdown` axis (§1.4) |
| `templates/sector_cycles.js` (+ country/china twins) | local PHASES copy, `zoneWord`, action-badge logic → renders `now.stance`/`divergence` |
| `engine/sector_central*.py` | consumes `now.stance`/`divergence` from the spine instead of re-deriving direction from raw ladder+phase (its confluence votes use `LADDER_DIR`) |

---

## 6. Mixed frequency + the proxy registry (N1 engagement)

The ontology owns the **schema and validation**; population/backfill of flagship cycles belongs to the
flagship-pages pillar and the monthly-kernel wave belongs to the measurement pillar.

`data/cycle_ontology/proxy_registry.json`:

```json
{"version": 1,
 "cycles": {
   "semis":   {"tier": "measured",   "proxy": {"source": "yahoo", "id": "SMH"},  "freq": "D",
               "turn_pct": 22.0, "trend_span": null},
   "memory":  {"tier": "measured",   "proxy": {"source": "manual_series", "id": "dram_asp"}, "freq": "M",
               "turn_pct": 25.0, "trend_span": null},
   "credit":  {"tier": "measured",   "proxy": {"source": "fred", "id": "BAMLH0A0HYM2", "invert": true}, "freq": "D",
               "turn_pct": null, "turn_abs_bps": 150},
   "housing": {"tier": "structural", "proxy": {"source": "fred", "id": "CSUSHPISA"}, "freq": "M",
               "turn_pct": 8.0, "trend_span": 60,
               "frame": {"period_yrs": 18, "falsifiers": ["<falsifier-DSL exprs — tripwire pillar>"]}}
 }}
```

- `tier` implements **T1**: `measured` → full kernel treatment (turns, hazard, grading); `structural` →
  canonical position + turns are still computed and drawn, but NO hazard cone, NO grader claims, and the
  card carries the "frame, not forecast / 框架，非预测" badge; falsifier exprs are machine-evaluated by the
  tripwire pillar (the alerts plumbing exists per S5: rule function + `log_and_dedup` + notify).
- `invert: true` handles risk-on semantics (credit spreads: tight = peak) — matching the flagship's
  documented convention (`cycle_data.js` header) but now mechanical.
- Ontology ships `validate_registry(reg) -> list[str]` (unknown tier/freq/source, missing turn threshold,
  structural entries lacking `frame` → build warnings) and `load_registry()`.
- HY OAS is already collected (S5); Case-Shiller/ISM are one-line `config.yml` fred.series additions (S5) —
  registry entries name them so the flagship pillar's collection wave is mechanical.

---

## 7. Migration — ordered, no flag-day

**M0 (with D1-W1).** Ship `engine/cycle_ontology.py` + generator + tests. Generated JS contains the
*current* 5-phase labels/hues (Python's PHASES wins; cycle_data.js's drifted hues die — a deliberate,
visible one-time harmonization). No page logic changes yet; pages start loading `cycle_ontology.js` for
phase meta only.

**M1 (D1-W2).** Kernel emits the superset `now` block (§4.4): `pos_v2` ALONGSIDE legacy `pos`; `stance` /
`divergence` / `clocks` / turn `turn_id`+`confirmed_at`+`provisional` fields; projection overdue semantics.
Pages still render legacy fields → zero visual change; new fields flow into forward logs immediately (the
measurement pillar's backfill stamps them retroactively — S2 confirmed `compute(asof=…)` is PIT-clean).

**M2 (D1-W3).** Pages switch action rendering to `stance` + divergence chip + provisional-turn styling +
overdue banner. The contradictory-badge pathology dies here. sector_central switches to consuming resolved
fields.

**M3 (after D1-W5 acceptance + calibration pillar sign-off).** Position axis flips to `pos_v2`
simultaneously on all five pages (one commit — the axis semantic must never be mixed across sibling pages);
legacy `pos` field removed; zone bands from ontology. markets.html axis re-labeled per §1.4.

**M4 (whenever detector params/basis change — data pillar's close_price wave, or CN threshold review).**
Run `scripts/migrate_narrative_keys.py`; review orphans; commit. The version-stamp gate (§3.3-4) makes
skipping this impossible silently.

Each step is independently shippable and reversible; every wave lands via the standing branch→PR→
squash-merge pipeline.

---

## 8. New problems discovered while designing (beyond the 89)

**NP-1 — Engine-side receding-horizon projection (HIGH).** `_project_next` anchors the projection at
TODAY: `central = base_x + max(0.05, med − since)` with `base_x = _yf(last_ts)`
(`engine/sector_cycles.py:204-206, :325`). Once `since > med` the projected turn floats permanently
~0.05yr ahead of today and re-rolls every build — the engine twin of the audited `cycle_app.js:63`
push-forward, on all three "data-driven" pages. Overdue-ness (the strongest hazard covariate) is
structurally hidden. Fixed by §4.5.

**NP-2 — Turn `confirmed_at` does not exist anywhere (HIGH, measurement-blocking).** `_detect_swings`
emits pivot dates only (`sector_cycles.py:147-157`); no consumer knows *when* a turn became knowable
(confirmation lag at 14% is typically weeks–months). Any turn-precision grading or hazard fit on the
backfill would leak knowledge backwards without it. Fixed by §3.1.

**NP-3 — The "identical hues/labels" claim is already false (MEDIUM, evidence for T2).**
`sector_cycles.py:68` comment claims PHASES hues match `site/cycle_data.js`; live values differ for 3 of 5
phases (Trough `#5b9bf0` vs `#e06464`, Recovery `#2dd4bf` vs `#45b873`, Expansion `#45b873` vs `#3da564`).
Hand-mirroring has already rotted once; the generated-JS contract is the only durable fix.

**NP-4 — Master phase wheel has zero hysteresis (MEDIUM).** `_classify_phase` direction is a live MACD
vote (`sector_cycles.py:170-189`); a one-week weekly-MACD wobble flips Expansion↔Downturn, resetting
`phase_age` and polluting phase-transition grading (N3) and the hazard age covariate. §2.1 adds the
`confirm_persist` hook; D1-W5 measures the flap rate on backfill to set it.

**NP-5 — `_classify_phase` takes `above200` and never reads it (LOW).** Dead parameter
(`sector_cycles.py:160-189`) — signature/logic drift indicator; cleaned up in the move to the ontology.

**NP-6 — ZigZag unknown-leg seeding is downward-only (LOW).** `_detect_swings` seeds the first pivot
reference only when price falls (`if p < ref_px`, `sector_cycles.py:132-133`), so a series opening on a
rally can mis-date its first pivot — relevant to deep-history backfill stamps; note added to detector move,
fix folded into detector v2 (track running max too).

---

## 9. Verdicts on Fable's theses (as touched by this pillar)

- **T1 ADOPT.** Implemented as the `tier` field in the proxy registry (§6); the ontology computes position
  and turns for structural frames too — the tier gates *claims* (hazard/grading), not gauges. Refinement:
  structural frames still get machine turns so their hand narratives can be tolerance-checked (T6).
- **T2 ADOPT (this pillar is T2), with one refinement:** the JS is generated **data + lookup helpers, not
  transpiled logic**. `resolve_state`/`classify_phase` run only in Python; pages render stamped outputs.
  A transpiled-logic variant would create a second implementation that can drift semantically even when
  byte-identical at generation time (different float/date handling). NP-3 is the empirical case that
  hand-mirroring fails.
- **T3 ADOPT interface-side.** The position semantic was *chosen partly for the hazard model*: pooled
  cross-sectional hazard needs a cross-asset-comparable position covariate, which the vol-standardized
  z/CDF provides and the range-stochastic provably does not (17.6–99.7 peaks). Ontology also feeds hazard
  its inputs: `phase_age_bars`, confirmed turns with `confirmed_at`, `overdue_frac`.
- **T4 ADOPT.** All ontology functions are causal/deterministic → exactly backfillable (S2 confirms
  `compute(asof=…)` plumbing). Ladder internal keys frozen for calibration lineage; 68/32 phase cuts and
  `Z_SCALE` declared as bindable calibration constants, versioned.
- **T5 ADOPT.** `basis` is a mandatory labeled field on positions and turns; the ontology runs on
  `close_tr` today with honest labels and flips to `close_price` when the data pillar lands (M4 re-key).
  This ordering avoids a flag-day: semantics first, basis swap second, migrator absorbs the re-dating.
- **T6 ADOPT (enabler).** The turn_id + `match_turns` re-keying (§3.3) is precisely what lets narrative
  survive as annotation while the engine owns every plotted number; N2 is defused by construction.
- **T7 NO POSITION NEEDED HERE**, but noted: the canonical confirmed-turn set with `confirmed_at` is the
  prerequisite dataset for the lead-lag phase-0 study; that study must use `confirmed_at` (not pivot dates)
  or the measured "lead" will be an artifact of confirmation-lag differences.
- **N1 ADDRESSED** (freq parameter sets + proxy registry schema, §1.1/§6). **N2 ADDRESSED** (§3.3).
  **N3 HOOKED** (`phase_age_bars`, `overdue_frac`, `expected period` in projection — graders get
  phase-appropriate clocks). **N4 ADDRESSED** (experiments registered, §10 W5).

---

## 10. Waves

**D1-W1 — The ontology module + generated JS + tests.**
*Files:* `engine/cycle_ontology.py` (new), `scripts/gen_ontology_js.py` (new), `site/cycle_ontology.js`
(generated), `tests/test_cycle_ontology.py` (new).
*Scope:* everything in §1–§3 + §5 as code: vocabularies, crosswalk matrix, `canonical_position`,
`classify_phase` (moved), `detect_turns` (absorbs `_detect_swings`, adds `confirmed_at`/`turn_id`/detector
v2 incl. NP-6 fix), `resolve_state`, `transition_signal`, `match_turns`, `project_next` (§4.5),
`validate_registry`, `export_payload`, generator with `--check`. No page/kernel behavior change yet
(sector_cycles re-imports `_detect_swings` from the ontology for byte-identical output at `version:1`
params). *Tier:* **sonnet** (fully specified above). *Depends:* nothing.
*Acceptance:* pytest suite green incl. the 5 assertions of §2.5; `gen_ontology_js.py --check` idempotent;
`python -m engine.sector_cycles` output unchanged vs main (diff of `sector_cycles.json`); no new deps.

**D1-W2 — Kernel integration (the state machine goes live in data).**
*Files:* `engine/sector_cycles.py` (`_record_core`, `build_sector`, `build_basket`),
`engine/country_cycles.py`, `engine/china_sector_cycles.py` (pass `series_id`/`freq`/`basis` through).
*Scope:* §4 — superset `now` block (`pos_v2` alongside `pos`, `stance/divergence/clocks`,
`timing_action` demotion, transition `signal`, `phase_age_bars`), turn objects in the new wire shape,
overdue projection semantics. Legacy fields preserved. *Tier:* **sonnet**. *Depends:* D1-W1.
*Acceptance:* all three page JSONs contain the new fields for every record; §2.5-(4) live-output sweep
passes; zero records with contradictory stance/phase without divergence flag; legacy fields byte-stable;
render-time delta < +2 min.

**D1-W3 — Page adoption + divergence UX.**
*Files:* `templates/sector_cycles.js`, country/china cycle JS twins, `templates/sector_cycles.html.j2`
(+ siblings), `site/cycle_data.js`/`cycle_app.js`/`markets_app.js` (phase-meta + zone reads only at this
stage), `engine/sector_central.py`/`china_sector_central.py` (consume resolved fields).
*Scope:* §5.3 + §2.3 UI contract — stance badge replaces raw ladder action, single amber "clocks disagree"
chip, provisional-pivot hollow styling, overdue banner, all dual-span en/zh, tones→existing color tokens
(zh flip safe). *Tier:* **sonnet**. *Depends:* D1-W2.
*Acceptance:* no page renders two opposite-direction action badges on one card (DOM assertion via the
preview screenshot QA flow at scroll-0 per house gotcha); i18n check passes (no `t()` in attributes);
sector_central conviction output unchanged ±0 (it consumes, not recomputes).

**D1-W4 — Narrative re-keying migrator (N2).**
*Files:* `scripts/migrate_narrative_keys.py` (new), `data/sector_cycles/narratives.json` + china/country/
intl narrative files (rewritten keys + `bound` blocks + `meta.detector_version`), build gate in
`scripts/build_sector_cycles.py` (+ siblings).
*Scope:* §3.3 — turn_id keys, orphan section, migration report, version-stamp assertion (warn-only render,
hard-fail only on version mismatch WITHOUT a migration run). *Tier:* **sonnet**. *Depends:* D1-W2.
*Acceptance:* migrator idempotent (second run = no-op); on current data with unchanged params, 100% of
existing legs rebind with zero orphans; simulated threshold change (14→16%) on XLK rebinds ≥90% of legs
and reports the rest as orphans without breaking the page.

**D1-W5 — Position-semantic acceptance study + flip decision (uses the measurement pillar's backfill).**
*Files:* `research/cycle_ontology/POSITION_V2_ACCEPTANCE.md` (report), experiment entries in
`data/experiments/registry_seed.json`.
*Scope:* on the PIT backfill (measurement pillar's monthly-stamp wave), compute for `pos` vs `pos_v2` at
every CONFIRMED turn: distribution of position-at-peak / at-trough per family (sectors, countries,
baskets); phase flap-rate at `confirm_persist ∈ {0,1,2}`; divergence-flag base rate. Register two
experiments (N4): `cycle-pos-v2-turn-coherence` (maturation: IQR(pos_v2@confirmed peaks) ≤ 25 AND
median ≥ 70 on n ≥ 100 turns, mirrored for troughs) and `cycle-phase-flap-rate` (target: ≥50% flap
reduction at chosen confirm_persist with ≤5-bar added transition lag). GO/NO-GO on M3 flip +
`confirm_persist` value. *Tier:* **opus** (judgment call on thresholds + flip). *Depends:* D1-W2 +
measurement pillar's backfill wave (their W1).
*Acceptance:* report written with the two experiments accruing in the admin tracker; explicit GO/NO-GO
recorded; if NO-GO, a concrete parameter remediation proposed (e.g. Z_SCALE or trend_span refit).

**D1-W6 — Proxy registry schema + validation (N1 enabler).**
*Files:* `data/cycle_ontology/proxy_registry.json` (schema + the ~23 flagship entries with tier/proxy/freq
declared — turn params may be placeholder pending the flagship pillar), `engine/cycle_ontology.py`
(`load_registry`/`validate_registry` already from W1), `config.yml` (add CSUSHPISA + ISM proxies to
fred.series — one line each per S5).
*Scope:* §6. Population of *live series backing* for cycle.html is the flagship pillar's work; this wave
delivers the registry contract + tier assignments so that pillar and the tripwire pillar have a stable
target. *Tier:* **sonnet** (tier assignments reviewed by fable in PR). *Depends:* D1-W1.
*Acceptance:* `validate_registry` clean; every cycle_data.js id has a registry entry with an explicit
tier; structural entries carry `frame.period_yrs` + at least one falsifier placeholder.

**Sequencing note for other pillars:** the data-basis pillar's `close_price` wave slots in *after* D1-W2
(the kernel then flips `basis="close_price"` + runs D1-W4's migrator — that is migration step M4); the
hazard pillar consumes W2's `confirmed_at`/`phase_age_bars`/`overdue_frac`; the measurement pillar's
backfill should run **after W2** so backfilled stamps carry resolved stances and turn ids from day one
(grading the reconciled call, as the audit directs).

---

## 11. Open questions (for Fable / other pillars)

1. **CN ZigZag thresholds (18%/25%)**: keep per-family constants or move to the vol-scaled rule
   everywhere? Ontology supports both via registry/params; recommend deciding after D1-W4 makes
   re-thresholding cheap. (China-engine pillar's call.)
2. **Z_SCALE / 68-32 cuts refit**: owned by the calibration pillar post-backfill; ontology just versions
   them. Confirm they accept the binding.
3. **Does sector_central's conviction formula re-weight when its direction legs switch to `LADDER_DIR`?**
   I specified consume-not-recompute (zero conviction delta) — if the central pillar wants to *use*
   divergence as a de-rating input, that is a separate, graded change.
4. **Flagship monthly kernel** (`_record_core` at freq="M") — measurement/flagship pillar owns the kernel
   variant; ontology params are ready (§1.1). Confirm DRAM ASP sourcing (manual_series) feasibility.
