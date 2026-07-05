# P2.4 — Board Contract v2: One Board, Explicit Lanes

**STATUS: APPROVED — Fable 2026-07-05 (red-team P2_REDTEAM.md blocking fixes applied; Fable rulings R-P2.1 flip-floor=100 clusters+2 quarters, R-P2.2 single concordance authority = P2.1b §3.3)**

**Document type:** Engineering design (NOT a PREREG). Carries falsifiable acceptance criteria.
**Program:** Entry Intelligence (EI)
**Masterplan:** `research/ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` §6/P2.4
**Date:** 2026-07-05
**Author:** Sonnet subagent under Fable orchestration
**Constitution:** EI masterplan §3 (inherited law); R7 (additive-lanes); R10 (liquidity = display only); t-macro law (no translated text in title= attributes)

---

## 0. Plain-English summary

> The board today runs two separate pipelines that produce two separate JSON files. `us_standouts.json` ranks by bottoming-alignment and shows PRIME/aligned names as "trend" or "recovery" lanes. `setups.json` ranks by alpha and shows confluence-gated setups — with no lane, no alignment tier, no liquidity fields. A user looking at both sees the same ticker in different positions with no explanation of why. Behind the scenes, continuation names (ARMED-tier fires with a rising weekly phase) enter the bottoming-aligned board but carry no label distinguishing them from fresh-bottom PRIME entries.
>
> This document designs a unification: ONE board product, ONE contract, three explicit lanes — bottoming, continuation, watch. Every row carries a lane field that honestly describes what kind of setup it is. ARMED-continuation names get a "continuation" lane badge so users see they are a structurally different entry type. No name is hidden or removed (additive-lanes law R7). The `setups.json` pipeline is preserved because it serves a separate presentation context (the setups desk), but the two pipelines share the same lane taxonomy and row contract going forward.
>
> This is a labeling and contract change. Ranking logic is NOT changed in this wave — that is P3's job.

---

## 1. Evidence basis (three independent P1 effects)

This design is authorized by the following verified P1 results. Exact numbers are cited; "22/30" is NOT cited (reviewer ADVISORY-2: this overstates independent findings; the correct characterization is ~3 independent forward-return tests).

### Effect 1 — H-MISLABEL: ARMED-continuation fires are immaterially different from PRIME

**Source:** `research/entry_intel/p1_runs/p1_5_continuation/RESULTS.md` (v2, round 2, defect-corrected). Reviewer verdict: CONFORMANT (`REVIEW_v2.md`).

- **Δ(ARMED-continuation − PRIME)** at P(clean8_21): **−2.79pp** (ARMED-cont 30.65% vs PRIME 33.44%).
- BH q(T1) = 0.1225 — not significant. Both-halves sign stable (H1 Δ = −1.46pp, H2 Δ = −5.39pp, both negative — STABLE). Per-name majority: 410/642 = 63.9% agree — PASS.
- PREREG §6 decision rule: |Δ| = 2.79pp < 5pp materiality bar → **H-MISLABEL** (first disjunct). Registered action: relabel ARMED-continuation fires into an explicit continuation lane. No gate change. No rank change.
- n: ARMED-continuation 1,752 fires / 1,322 episode clusters; PRIME 5,448 fires / 3,846 episode clusters. Verdict window: 2022-06-30 → 2025-12-29 (Massive-sourced, survivor_bias=False, n_clusters well above 25 floor).

**Design implication:** ARMED-continuation names must enter the board in a "continuation" lane, not silently mixed into the same tier as PRIME. The label distinguishes structural type; the outcome distribution is similar enough that no filter or rank penalty is authorized.

### Effect 2 — T4 below-200DMA continuation fires materially outperform above-200DMA

**Source:** `research/entry_intel/p1_runs/p1_5_continuation/RESULTS.md` T4 sub-partition (diagnostic context — does NOT override T1 verdict per PREREG §6 sub-partition clause, but IS significant evidence for the below-200DMA context field).

- T4: above_200=True vs False within ARMED-continuation arm.
  - above_200=True: n=890 fires, P(clean8_21) = **24.72%**
  - above_200=False (below 200DMA): n=862 fires, P(clean8_21) = **36.77%**
  - Δ = **−12.06pp** (above minus below), BH q = 0.0000 (significant at α=0.10), sign-stable.
- **Interpretation:** within continuation fires, those that enter while still below the 200DMA substantially outperform those already extended above it. This is a within-continuation context signal — not a gate (per R7 and R4), but a material context field that every continuation row must carry so users can see which sub-type they are holding.

**Design implication:** every continuation-lane row must surface the `above_trend` field (already computed in the board pipeline at L760 as `bool(gate.get("above_200dma"))`). The board row contract must expose this field. No ranking change: the below-200DMA outperformance is a context label, not yet promoted via the ladder (that would require its own PREREG).

### Effect 3 — F3 anti-chase gate (ext_z ≤ 2.0) reduces stop-outs and dead-money

**Source:** `research/entry_intel/p1_runs/P1_3/RESULTS.md` (v2, round 2). Reviewer verdict: CONFORMANT (`REVIEW_v2.md`).

- T21 (F3, HG, 21d stop-out): Δ = **−0.43pp** favorable, perm_p = 0.0026, BH-adj = 0.0060, sign-stable. r = −0.0612.
- T22 (F3, HG, 21d dead-money): Δ = **−3.63pp** favorable, same perm_p = 0.0026, BH-adj = 0.0060.
- T24 (F3, HG, 63d stop-out): Δ = **−5.00pp** favorable, perm_p = 0.0648, BH-adj = 0.0933 (survives q≤0.10), sign-stable.
- Gate fire-rate impact: **4.6%** (2,299/49,939 fires would-block). Gate passes §6.2 (<40%). Ships as hard gate.

**Design implication:** the board contract must surface `ext_z` (or the extension chip) on every row so users see whether the entry is extended. The F3 gate promotion (shadow-first, P2.1) is handled separately; this design document only concerns itself with the *display* contract that makes the field visible. The anti-chase gate is NOT wired into the board assembly in this wave (P3's jurisdiction — see §5).

---

## 2. The two-board divergence (current state, exact)

Two independent pipelines produce two artifacts read by the template:

| Artifact | Pipeline location | `rank_by` | Lanes today | Liquidity fields | align_tier |
|---|---|---|---|---|---|
| `site/factordata/us_standouts.json` | `build_stock_library.py` L2163 | `"bottoming-alignment"` | `"trend"` / `"recovery"` | `adv_dollar_21d` / `days_to_exit_at_10pct_adv` (present in code; currently null in live snapshot) | `"aligned"` / `None` (verified 2026-07-05 via live snapshot grep: `sorted({str(r.get('align_tier')) for r in rows})` → `['None', 'aligned']`; the P1.5 replay used `PRIME/ARMED/APPROACHING` but the production board emits a different vocabulary — see §3.1 and §4.1 for the defensive mapping) |
| `site/factordata/setups.json` | `build_stock_library.py` L1929 | `None` (set from `rank_setups` as `"alpha"`) | absent | absent | absent |

The us_stocks template (`templates/us_stocks_v2.html.j2`) renders `us_standouts.json` as the primary board. The `setups.json` artifact serves a separate "setups desk" presentation. The divergence manifests when a ticker ranks highly on alpha (setups.json) but does not appear on the bottoming-aligned board — or appears at a very different position — with no explanation.

The deeper labeling gap: within `us_standouts.json`, ARMED-continuation fires (ARMED tier + rising weekly phase) currently land in `lane="trend"` alongside PRIME bottoming fires. H-MISLABEL authorizes a relabel to `lane="continuation"` — the single most consequential contract change this wave enables.

---

## 3. One-board contract v2 (target state)

### 3.1 Lane taxonomy (additive labels — R7 applies)

Three lane values, exhaustive and mutually exclusive per row:

**Verified live vocabulary (2026-07-05):** `python3 -c "import json; d=json.load(open('site/factordata/us_standouts.json')); rows=(d.get('buy') or [])+(d.get('watch') or []); print(sorted({str(r.get('align_tier')) for r in rows}))"` → `['None', 'aligned']`. The production board currently emits `"aligned"` and `None` (not `PRIME`/`ARMED`/`APPROACHING` which appear in the P1.5 replay artifact). The `_lane_for()` function must handle BOTH vocabularies. A future builder migration from the live vocabulary to the replay vocabulary, or vice versa, changes only the mapping in `_lane_for()`, not the lane taxonomy.

| Lane | Admits | Source condition | Display accent |
|---|---|---|---|
| `"bottoming"` | PRIME-equivalent fires | `align_tier in {"PRIME", "aligned"}` OR `align_tier in {"near"}` (near-aligned, same as APPROACHING-equivalent) | Primary accent (current trend lane color) |
| `"continuation"` | ARMED-equivalent fires with rising weekly phase | `align_tier in {"ARMED"}` AND `weekly_phase == "rising"` OR `align_tier in {"near"}` AND `weekly_phase == "rising"` (near=APPROACHING-equivalent with rising) | Secondary accent (distinct color, e.g. --warn or a new --cont token) |
| `"watch"` | All other board-visible names (overflow, near-aligned without rising phase, positive-conviction non-buy) | Not in buy pool, positive composite_z | Muted accent (current watch strip) |

R7 enforcement: the lane assignment is ADDITIVE — it labels what a row is, never gates it out. A name that was previously silently in `lane="trend"` carrying ARMED+rising context now appears in `lane="continuation"`. It is still on the board. Count of board rows is non-decreasing relative to pre-v2 (the byte-diff harness enforces this — §6).

**Vocabulary mapping note:** as of 2026-07-05 the live snapshot has only `"aligned"` and `None` as align_tier values — no ARMED/near rows are present. AC-3 monitors whether the continuation branch ever fires (see §6, AC-3). If the builder is updated to emit `PRIME/ARMED/APPROACHING`, `_lane_for()` handles both vocabularies via the explicit mapping in §4.1.

**Lane counts logged nightly** in the build log and emitted as a `lane_counts` dict inside the JSON artifact (`{"bottoming": N, "continuation": N, "watch": N}`). This is the monitoring primitive.

### 3.2 Row contract fields (additions to current schema)

Every board row (buy + watch + laggards) in `us_standouts.json` MUST carry the following fields after v2. Fields marked (existing) are already populated in the code but may be null in the live snapshot due to data availability; this design requires them to be non-null where the underlying data exists.

| Field | Type | Existing / New | Source | Notes |
|---|---|---|---|---|
| `lane` | string | existing (currently "trend"/"recovery"/"watch") | `build_stock_library.py` `_tag()` L2136 | Value set must expand to include `"bottoming"` and `"continuation"` per §3.1 |
| `align_tier` | string | existing | `build_stock_library.py` L2138 | Live vocabulary verified 2026-07-05: `"aligned"` / `None`; replay vocabulary: `PRIME` / `ARMED` / `APPROACHING`. Both are handled by `_lane_for()`. |
| `weekly_phase` | string | **new** | `engine/cycles.py` `mtf_alignment` result | Required to assign continuation lane; frozen at signal time in replay as `weekly_phase` |
| `above_trend` | bool | existing (L760, but emitted only on basket paths; absent on standout rows) | `gate.get("above_200dma")` | **Must be propagated to standout rows.** Enables T4 context display. |
| `ext_z` | float | existing as part of conviction/axes | `engine/extension.py` | Must be surfaced as a top-level row field for display; currently nested inside `conviction.axes` |
| `adv_dollar_21d` | float | existing (L2209) | `_liq_map` | P0.3 hygiene field. Display-only per R10. Populate from Massive store where available. |
| `days_to_exit_at_10pct_adv` | float | existing (L2210) | `_liq_map` | P0.3 hygiene field. Display-only per R10. |
| `lane_counts` | dict | **new** | build-time aggregate | Top-level JSON field, not per-row. Keys: `"bottoming"`, `"continuation"`, `"watch"`. Nightly monitoring. |

Fields NOT added in v2 (deferred to P3+):
- `species_id`: not yet wired from the species registry to individual board rows (P3.1 / P4 work).
- `cell_outcome_distribution`: P3.3 work (render outcome distributions, not scores).
- Any rank-logic field: R7 + the explicit P3 boundary in §5 forbid rank changes here.

### 3.3 Ranking logic: NO CHANGE IN V2

**This is the hard scope boundary of P2.4.** The within-lane sort order (`alpha desc` inside trend/bottoming lane; `alpha desc` inside recovery/continuation lane) is unchanged. The sector cap logic is unchanged. The admission criteria (alignment gate, entry_ok, _atier) are unchanged. The `rank_by` value in the artifact header remains `"bottoming-alignment"`. P3 owns the kernel-rank redesign (Wilson lower bound of shrunk cell posterior, shadow-first per R6).

Any change to `_combine_key`, `_asort`, `_atier`, `_entry_ok`, or the BUY/WATCH admission decision is OUT OF SCOPE for this design and must not be included in the v2 implementation PR.

### 3.4 setups.json contract alignment

`setups.json` is preserved as a separate artifact for the setups desk. In v2 the following contract changes are applied to ensure shared taxonomy:

- Each row in `setups.json` that also appears in `us_standouts.json` carries the same `lane` value it would receive under §3.1.
- `setups.json` gains a `lane` field on each buy row (populated by the same `_tag()` logic, or by a post-pass lookup against the standout row map).
- `rank_by` in `setups.json` header is set to `"alpha"` explicitly (currently None in live snapshot — a latent contract gap).

This does NOT change how `setups.json` ranks its names (still alpha via `rank_setups`). It only ensures the lane label is consistent between artifacts.

---

## 4. Implementation design

### 4.1 `build_stock_library.py` — board assembly changes

All changes are in the `build_us_library()` function (the wide board path starting ~L1920).

**Step A — weekly_phase capture (new field on cand rows).** The `mtf_alignment()` call results are already computed in the alignment logic that produces `align_tier`. The `weekly_phase` value must be extracted from that result and stored on the candidate row so it is available for lane assignment and for the board row output. This is a read — not a re-computation. If `weekly_phase` is not yet a top-level column on candidate rows, it must be populated before `_tag()` is called.

**Step B — lane assignment in `_tag()`.** The `_tag()` function (L2136) currently takes `lane` as an explicit parameter defaulting to `"trend"`. Under v2, the lane is derived from the row's `align_tier` and `weekly_phase`:

```python
import logging
_log = logging.getLogger(__name__)

# Explicit vocabulary mapping: handles BOTH the P1.5 replay vocabulary
# (PRIME/ARMED/APPROACHING) AND the current live production vocabulary
# (aligned/near/None), verified 2026-07-05 against us_standouts.json.
_PRIME_EQUIV   = {"PRIME", "aligned"}        # bottoming-type
_ARMED_EQUIV   = {"ARMED"}                   # continuation-type (requires rising weekly_phase)
_NEAR_EQUIV    = {"APPROACHING", "near"}     # near-aligned (treated as bottoming unless rising)
_KNOWN_TIERS   = _PRIME_EQUIV | _ARMED_EQUIV | _NEAR_EQUIV | {None, "None"}

def _lane_for(align_tier, weekly_phase):
    # Normalize string "None" to Python None
    tier = None if align_tier in (None, "None", "") else align_tier

    if tier in _PRIME_EQUIV:
        return "bottoming"
    if tier in _ARMED_EQUIV and weekly_phase == "rising":
        return "continuation"
    if tier in _NEAR_EQUIV and weekly_phase == "rising":
        return "continuation"  # near/APPROACHING with rising phase → continuation branch
    if tier in _ARMED_EQUIV or tier in _NEAR_EQUIV:
        return "bottoming"     # non-rising ARMED or near → grouped with bottoming
    if tier is None:
        return "bottoming"     # null align_tier → default structural type
    # UNKNOWN vocabulary value: log loudly and default
    _log.warning(
        "P2.4 _lane_for: UNKNOWN align_tier value %r (weekly_phase=%r) — "
        "defaulting to 'bottoming'. Update _PRIME_EQUIV/_ARMED_EQUIV/_NEAR_EQUIV "
        "if the builder vocabulary has changed.", align_tier, weekly_phase
    )
    return "bottoming"

def _tag(t, tier, lane=None):
    r = row_by_t[t]
    r["align_tier"] = tier
    weekly_ph = r.get("weekly_phase")  # must be populated by Step A
    r["lane"] = lane if lane is not None else _lane_for(tier, weekly_ph)
    return r
```

The `lane="recovery"` explicit parameter call for recovery rows (`_tag(t, "recovery", lane="recovery")`) is preserved as-is — the recovery lane is distinct from continuation and is not renamed.

**Step C — `above_trend` propagation to standout rows.** `above_trend` is already computed per-ticker at the candidate assembly stage (L760 via `gate.get("above_200dma")`). It must be propagated to the standout row dict during the enrichment loop (L2171+), analogous to how `adv_dollar_21d` is propagated. Add:

```python
_atrd = (profiles.get(t) or {}).get("above_trend") or row_by_t[t].get("above_trend")
if _atrd is not None:
    r["above_trend"] = _atrd
```

**Step D — `ext_z` top-level field.** Currently `ext_z` is buried inside `conviction.axes.extension.z` (if present). Add a top-level alias during enrichment:

```python
_extz = ((profiles.get(t) or {}).get("axes") or {}).get("extension", {}).get("z")
if _extz is not None:
    r["ext_z"] = round(float(_extz), 2)
```

**Step E — `lane_counts` top-level field.** After the buy + watch lists are assembled, compute:

```python
from collections import Counter
_lane_ct = Counter(r.get("lane") for r in wide["buy"] + wide["watch"])
wide["lane_counts"] = dict(_lane_ct)
log.info("P2.4 lane_counts: %s", wide["lane_counts"])
```

**Step F — `setups.json` lane backfill.** After the standout wide dict is assembled, build a lookup `{ticker: lane}` from wide["buy"]. In the `setups` assembly block (L1929–1936), add a post-pass:

```python
_standout_lane = {r["ticker"]: r.get("lane") for r in wide.get("buy", [])}
for r in setups.get("buy", []):
    r["lane"] = _standout_lane.get(r["ticker"], "bottoming")  # default to bottoming if not on standout board
if "rank_by" not in setups or setups["rank_by"] is None:
    setups["rank_by"] = "alpha"
```

### 4.2 `templates/us_stocks_v2.html.j2` — display changes

**Lane header labels.** The two existing section headers ("ENTRY OPEN" and "SETTING UP") that currently label the `entry_open` and `setting_up` lane sections are in a different template than the standout board. For the standout board, add lane group headers above the card stream:

- Cards with `lane="bottoming"` are preceded by a section label: "Bottoming" / "筑底" (zh).
- Cards with `lane="continuation"` are preceded by a section label: "Continuation" / "延续" (zh).
- Cards with `lane="watch"` are preceded by a section label: "Watch" / "观察" (zh).
- Cards with `lane="recovery"` keep their existing "Recovery" / "修复" header.

These labels use the existing `t(en, zh)` macro. They are rendered as sub-headings, not as tabs or filters (additive-lanes — all lanes visible simultaneously).

**Lane accent on card border.** `data-lane` already drives `border-left-color` via CSS (L88–89). Add a rule for `continuation`:

```css
.v2-card[data-lane="continuation"] { border-left-color: var(--cont, var(--warn)); }
.v2-card[data-lane="bottoming"]    { border-left-color: var(--up); }
```

(`--cont` is a new CSS custom property; defaults to `--warn` if unset for backward compatibility.)

**above_trend context badge.** On continuation-lane cards only, if `r.above_trend` is present, render a small context badge:

```jinja2
{% if lane == 'continuation' and r.above_trend is defined %}
  {% if r.above_trend %}
  <span class="chip chip-context" data-tip-en="Above 200DMA — continuation at elevation" data-tip-zh="站上200日均线——高位延续">200DMA+</span>
  {% else %}
  <span class="chip chip-context chip-positive" data-tip-en="Below 200DMA — continuation from washout base (T4 context: +12pp vs above-200 peers)" data-tip-zh="200日均线下方——从洗盘底部延续（T4背景：较高位同类高出12pp）">200DMA−</span>
  {% endif %}
{% endif %}
```

Note: `data-tip-en` / `data-tip-zh` attributes (NOT `title=`) per t-macro law. The T4 effect size (+12pp in P(clean8_21)) is surfaced as honest context, labeled as "T4 context" to flag it as a sub-partition finding (PREREG §6 sub-partition clause — it does not override the T1 verdict).

**ext_z context chip.** If `r.ext_z` is present, render an extension context chip on every row (all lanes):

```jinja2
{% if r.ext_z is defined and r.ext_z is not none %}
<span class="chip chip-ext {% if r.ext_z > 2.0 %}chip-warn{% endif %}"
      data-tip-en="Extension z={{ r.ext_z|round(1) }}{% if r.ext_z > 2.0 %} — extended (anti-chase context){% endif %}"
      data-tip-zh="延伸z={{ r.ext_z|round(1) }}{% if r.ext_z > 2.0 %} — 过度延伸（反追涨背景）{% endif %}">
  ext {{ r.ext_z|round(1) }}
</span>
{% endif %}
```

i18n rule: text inside `data-tip-en` / `data-tip-zh` is the translation mechanism. No `title=` attributes carry translated text. The `t()` macro wraps user-visible static strings. Dynamic per-row values (ext_z, adv_dollar_21d) are numeric and do not require translation — they appear as numbers with a static label wrapper.

**lane_counts badge.** If `d.lane_counts` is present on the top-level data object, render a pill row above the board:

```jinja2
{% if d.lane_counts %}
<div class="lane-counts">
  {% for ln, ct in d.lane_counts.items() %}
  <span class="lane-count-pill" data-lane="{{ ln }}">{{ t(ln.capitalize(), ln|capitalize_zh) }}: {{ ct }}</span>
  {% endfor %}
</div>
{% endif %}
```

This gives users a visible row count per lane, making R7 transparency concrete.

**i18n parity.** Every new static string added to the template must use the `t(en, zh)` macro. New chip labels: "Bottoming"/"筑底", "Continuation"/"延续", "Watch"/"观察", "200DMA+"/"站上200日均线", "200DMA−"/"200日均线下方". No `title=` attributes for translated content (t-macro law — checked by `check_title_i18n` CI guard).

---

## 5. Explicit scope boundary: v2 is labeling only; P3 owns ranking

The following are **explicitly out of scope** for P2.4 / v2 and must NOT be included in the implementation PR:

1. Any change to the formula used to sort rows within a lane (`_combine_key`, `_asort`, `_alpha_key`).
2. Any change to the admission criteria (`_entry_ok`, `_atier`, alignment gate, sector cap).
3. Wiring of F1/F2 rank weights (P1.3 RW survivors) into the score composite — that requires its own shadow-first PREREG per R6 and is P2.1's domain.
4. Wiring of F3 anti-chase as a hard gate — also P2.1, shadow-first, own PREREG.
5. The `species_id` field and cell outcome distributions — P3.1 / P3.3.
6. The kernel-rank shadow (Wilson lower bound posterior) — P3.2.
7. Any changes to `engine/cycles.py`, `engine/signal_gate.py`, or `engine/confluence_tiers.py`.

If any of these are found in the implementation PR, the PR reviewer must reject them and request scope reduction.

---

## 6. Acceptance criteria (falsifiable)

The v2 implementation PR passes when ALL of the following hold:

### AC-1 — Byte-diff harness: no row silently dropped

**Protocol:** run `build_stock_library.py` on the same data snapshot twice — once with the v1 code and once with the v2 code. Diff the `us_standouts.json` buy + watch arrays by ticker set.

**Criterion:** every ticker present in `wide["buy"] + wide["watch"]` in the v1 run is present in the v2 run. Zero tickers may disappear. Tickers may gain new fields; existing fields may change `lane` value (from "trend"→"bottoming" or "trend"→"continuation") — but the ticker must remain.

**Failure:** any ticker drop → PR fails AC-1, stop.

### AC-2 — Lane counts logged and non-zero

**Criterion:** after the build, `wide["lane_counts"]` exists in `us_standouts.json` and contains at least one key with a positive integer value. The build log contains `"P2.4 lane_counts:"` with the dict. If both `bottoming` and `continuation` counts are zero (implying all rows defaulted to "watch"), the build is flagged as a lane-assignment bug.

### AC-3 — ARMED/near-continuation rows carry lane="continuation" AND branch fires on real render

**Criterion (set-membership):** for every row in `us_standouts.json` with `align_tier` in `{"ARMED", "near", "APPROACHING"}` AND `weekly_phase == "rising"`, the `lane` field must be `"continuation"`. Zero exceptions.

**Protocol:**
```python
import json, sys
d = json.load(open("site/factordata/us_standouts.json"))
all_rows = (d.get("buy") or []) + (d.get("watch") or [])
# Check set-membership correctness
bad = [r["ticker"] for r in all_rows
       if r.get("align_tier") in {"ARMED", "near", "APPROACHING"}
       and r.get("weekly_phase") == "rising"
       and r.get("lane") != "continuation"]
print("SET-MEMBERSHIP:", "FAIL" if bad else "PASS", bad)
# Check that the continuation branch fires on at least one row in real data
# (guards against the live vocabulary having NO ARMED/near rows, hiding a dead branch)
cont_rows = [r["ticker"] for r in all_rows if r.get("lane") == "continuation"]
if not cont_rows:
    print("AC-3 WARNING: zero continuation-lane rows in this render — "
          "the ARMED/near→continuation branch never fired. Verify live align_tier "
          "vocabulary matches _ARMED_EQUIV/_NEAR_EQUIV in _lane_for(). "
          "If the live board genuinely has no ARMED/near rows, log as expected-empty "
          "and block until vocabulary is confirmed.")
    sys.exit(1)  # Fail loudly: branch must fire on at least one row per real render
else:
    print("AC-3 BRANCH-FIRES: PASS (", len(cont_rows), "continuation rows)")
```

**Note:** as of 2026-07-05 the live snapshot has only `"aligned"` and `None` as align_tier values. If the live board builder is emitting `PRIME/ARMED` or `aligned/near`, the vocabulary sets in `_lane_for()` already handle both. The AC-3 branch-fires check catches any future state where the branch silently goes dead.

### AC-4 — i18n parity: no title= attributes carry translated text

**Criterion:** CI `check_title_i18n` guard passes on the modified template. No `title="..."` attribute in `us_stocks_v2.html.j2` contains Chinese characters or uses the `t()` macro. All translated text in new chips uses `data-tip-en` / `data-tip-zh` attributes.

### AC-5 — `above_trend` present on continuation-lane rows where data exists

**Criterion:** if the production board contains any `lane="continuation"` rows AND `above_trend` data is available in the pipeline (i.e., `gate.get("above_200dma")` is non-null for those tickers), then at least one continuation-lane buy row in `us_standouts.json` must have a non-null `above_trend` field. This is a data-propagation check, not a data-availability guarantee.

### AC-6 — `setups.json` has non-null `rank_by` and carries `lane` fields

**Criterion:** `setups.json["rank_by"]` == `"alpha"` (not None). Every row in `setups.json["buy"]` has a `lane` field with a non-null string value.

### AC-7 — Weekly-phase field on board rows

**Criterion:** at least one buy row in `us_standouts.json` has a non-null `weekly_phase` field. (If all names happen to have null weekly_phase in the current snapshot — e.g., the MTF computation did not run — this is a pre-condition failure; the PR is blocked, not failed, and a blocker report is returned.)

---

## 7. Non-goal statements (explicit)

- **Not a PREREG.** This document is an engineering design. It does not register a study. It does not claim any alpha effect from the labeling change itself. Lane labels are honest description, not a performance claim.
- **Not a ranking change.** The board's sort order within lanes is unchanged. A "continuation" row that was previously ranked 5th in the trend lane remains at the equivalent position in the continuation lane.
- **Not a gate change.** No name is newly admitted or excluded by v2. The admission criteria are frozen at v1.
- **Not a species promotion.** The ARMED-continuation relabel does not promote a new species via the ladder. Species promotion for continuation clades (P2.3) requires its own PREREGs.
- **Not a P3 feature.** Cell outcome distributions, kernel-rank, and shadow comparison are P3 deliverables. The board contract v2 is designed to be P3-compatible (rows carry the fields P3 needs), not to implement P3 logic.

---

## 8. In plain English

> Right now, the board mixes two kinds of buys without telling you which is which. One kind is a fresh-bottom setup: the stock was beaten down, the weekly trend just started turning, and it is entering from a base. The other kind is a continuation: the weekly trend already turned weeks ago, the stock has been rising, and it just triggered the entry gate again. Both appear under the same "trend" label today.
>
> The study confirmed these two kinds are not worse than each other — they are just different. A relabel fixes the display without changing who gets on the board or how they are ranked. After v2, the board has three labeled sections: "Bottoming" (fresh base setups), "Continuation" (already in motion), and "Watch" (not yet triggering). All names that were on the board before stay on the board. The label is honest information, not a filter.
>
> We also surface two new context chips. For continuation names below the 200-day moving average, a "200DMA−" badge notes that historically these names have cleared the clean-liftoff bar at +12 percentage points higher rate than continuation names already above the 200DMA (that is a sub-study finding, shown as context, not a ranking change). For every name, an "ext z" chip shows how extended the price is — a number above 2.0 is the anti-chase warning the P1.3 study validated.
>
> Nothing that changes how names are ranked or selected is in this wave. That work belongs to Phase 3.

---

## 9. Downstream routing

- **P2.1** (F1/F2 RW promotion, F3 HG promotion): reads `us_standouts.json` lane field to stratify the shadow ledger by lane. The lane field established here is the stratification key for the shadow-first evaluation.
- **P2.3** (continuation clade PREREGs): the continuation lane field is the population selector for any new species studies on Leader Reload / Compression Breakout. It must be stable before those PREREGs register.
- **P3.1–P3.3** (cell rollups, kernel-rank, card redesign): consume `lane` as a primary stratification dimension for cell posterior computation. The row contract v2 (especially `weekly_phase`, `above_trend`, `ext_z`, `adv_dollar_21d`) provides the features P3.1 needs without re-engineering the board schema.
- **P4.1** (species-desk adapter → qledger): `lane` is the entity context for board-surface entity claims. Stable lane taxonomy is a prerequisite for consistent claim routing.

---

*Design authored 2026-07-05. Acceptance criteria are falsifiable and machine-checkable. No git operations performed. This document is data for the Fable orchestrator.*

*2026-07-05 — red-team blocking fixes applied (P2_REDTEAM.md) incl. Fable rulings R-P2.1 (flip floor 100 clusters + 2 quarters) and R-P2.2 (single concordance authority).*
