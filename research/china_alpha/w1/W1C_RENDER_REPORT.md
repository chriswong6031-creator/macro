# W1-C Report — Three-shelf render in templates/china.html.j2

**Wave:** W1-C
**Date:** 2026-07-03
**Status:** COMPLETE — 142/142 tests pass (16 new + 126 pre-existing); no git write.
**Files touched:** `templates/china.html.j2` (extended), `tests/test_china_stocks_w1c_render.py` (new)

---

## 1. What was built

### Three-shelf partition (mode=stocks standout section)

The standout board (`id="standouts"`) is now partitioned into three Jinja-rendered shelves.
The buy array is split by the `stage` field added by W1-B:

| Shelf | Source | Admission rule | CSS badge |
|---|---|---|---|
| **ENTRY** | `setups.buy` where `stage == 'ENTRY'` | gate-eligible AND entry_signal actionable | `stg-entry` (green) |
| **RAN / LATE (rule 2)** | `setups.buy` where `stage == 'RAN_LATE'` | gate-eligible BUT entry timing passed | `stg-ran` (muted) |
| **RIPENING** | `setups.ripening` (new array) | rule-4 names from W1-B | amber compact card (`nb-rip-card`) |
| **RAN / LATE (rule 3)** | `setups.ran` (new array) | gate-ineligible, cross within 15 sessions | flat row with cross date |

**F3 discipline honored:** the `blend_sorted` order within the ENTRY shelf is **unchanged** — only the stage badge and why_ranked chip are added above the existing card body. `_cn_bonus` weights are untouched.

### ENTRY shelf cards

Each ENTRY card now opens with:
```html
<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
  <span class="nb-stage stg-entry">ENTRY / 入场</span>
  <span class="nb-why" title="Why ranked here: {why_ranked}">T1+washout_2w</span>
</div>
```
The existing card body (conviction, axes, entry gauge, chips) is **100% intact** — this is the only structural change to ENTRY cards.

### RAN_LATE cards (rule 2 — buy array)

- Stage badge: `stg-ran` (muted/grey, no green)
- `stage_sublabel` rendered prominently: "signal live — entry passed; wait for pullback"
- Score displayed with `opacity:0.45` (`.nb-stage-ran-card .nb-cscore`)
- Card renders a compressed version (no buy zone, minimal entry gauge display)

### RIPENING shelf (compact cards)

24-card grid using `.nb-rip-card` (amber left-border, never an nbcard). Fields:
- Ticker, name, imminence (`~4.9W` = bars to 2W MACD cross)
- Sector
- Reason chips (split by comma from the `reasons` field)
- Spot position in 2y range (`range 35%`)

**NO BUY-family language anywhere on RIPENING cards.**

### RAN array (rule 3 — non-buy universe)

Flat list row with:
- Ticker (linked to china_lookup.html), name, sector
- Cross date + sessions_since + pct_since from `sublabel`
- `basing_chip` rendered when hold_state == intact

### CSS additions (after `.nb-note-anticipation`)

- `.nb-shelf-hdr` / `.nb-shelf-tag` / `.nb-shelf-expl` — shelf separator headers
- `.nb-shelf-tag.st-entry` (green), `.st-ripe` (amber), `.st-ran` (muted)
- `.nb-stage.stg-entry`, `.nb-stage.stg-ran` — per-card stage badges
- `.nb-why` — why_ranked chip
- `.nb-ran-detail` — RAN sublabel block (red-family background)
- `.nb-stage-ran-card .nb-cscore` — mutes score on RAN cards
- `.nb-rip-grid`, `.nb-rip-card`, `.nb-rip-top`, `.nb-rip-chips`, `.nb-rip-chip`, `.nb-rip-sec` — RIPENING compact card layout

### Help text extension

One sentence added to both EN and ZH help tooltips on the standout h2:

> EN: "Three-shelf lifecycle (W1): ENTRY = fresh turn inside a live setup (the only actionable shelf); RIPENING = setup forming but entry cascade not yet fired — watching, not acting; RAN/LATE = signal passed, shown for honesty only — do not chase."

---

## 2. Invariants satisfied

All five invariants from the W1-C spec:

| Invariant | Verification method | Result |
|---|---|---|
| BUY-family words (BUY/买入/act now) on ENTRY only | `test_no_buy_family_words_on_ripening_shelf` + `test_no_green_stage_badge_on_ran_cards` | PASS |
| No green band / stg-entry styling on RAN cards | `test_no_green_stage_badge_on_ran_cards` | PASS |
| Every shelf header has dual-span (l-en + l-zh) | `test_shelf_headers_have_dual_spans` + `test_bilingual_shelf_headers_contain_zh_text` | PASS |
| Zero non-ASCII attribute delimiters | `test_no_non_ascii_attribute_delimiters` (regex scans full template) | PASS |
| Jinja parse | `test_template_parses_without_errors` | PASS |

Additional structural invariant: `test_w1c_block_is_balanced` confirms the W1-C snippet has 74 balanced if/endif + 10 balanced for/endfor pairs — so any future snippet extraction works cleanly.

---

## 3. Backward compatibility

The `_entry_rows` / `_ran_late_rows` partition uses `selectattr('stage', 'equalto', ...)`. On a pre-W1 artifact where all `stage` values are `None` (or the key is absent), both lists resolve to empty, triggering the fallback:

```jinja2
{% if (_entry_rows | length == 0) and (_ran_late_rows | length == 0) and (setups.buy | length > 0) %}
  {% set _entry_rows = setups.buy %}
{% endif %}
```

This shows all buy rows on the ENTRY shelf — exactly what the board displayed before W1-C. The `ripening` and `ran` arrays render as empty (no shelves appear). **Verified by `test_backward_compat_pre_w1_artifact`.**

The live artifact (`site/factordata/china_standouts.json` as of 2026-07-03) pre-dates the W1-B build: all `stage` fields are `None`, `ripening` and `ran` are absent. The template degrades gracefully to the pre-W1 display with no visible change to end users until the builder re-runs.

---

## 4. W0 copy blocks — intact

The W0.9 copy blocks (archetype description, three caveats, h2 subtitle) are untouched. Only one sentence was appended to the existing help tooltips. All 11 W0.9 tests continue to pass.

---

## 5. Tests

**`tests/test_china_stocks_w1c_render.py`** — 16 tests:

| Test | What it pins |
|---|---|
| `test_template_parses_without_errors` | Full Jinja parse — the primary gate |
| `test_no_non_ascii_attribute_delimiters` | Zero curly-quote/guillemet attr delimiters (whole template) |
| `test_w1c_block_is_balanced` | Jinja tag balance in the W1-C snippet (74 if/endif, 10 for/endfor) |
| `test_shelf_headers_have_dual_spans` | l-en + l-zh spans + all three shelf-tag classes in SRC |
| `test_no_t_call_inside_attributes_in_w1c_section` | t() not inside HTML attributes in W1-C block |
| `test_entry_cards_render_with_stage_badge` | `stg-entry` in rendered output |
| `test_ran_cards_render_with_stage_badge_and_detail` | `stg-ran` + rule-2 sublabel visible |
| `test_ripening_shelf_renders_compact_cards` | `nb-rip-card` + ripening ticker + reason chips |
| `test_ran_array_renders_honesty_rows` | Rule-3 ticker + cross date in output |
| `test_no_buy_family_words_on_ripening_shelf` | No BUY/买入/act now in RIPENING-only render |
| `test_no_green_stage_badge_on_ran_cards` | stg-entry absent when only RAN rows |
| `test_why_ranked_chip_on_entry_cards` | `why_ranked` content + `nb-why` class |
| `test_backward_compat_pre_w1_artifact` | Pre-W1 artifact (stage=None) degrades gracefully |
| `test_ripening_shelf_absent_when_array_empty` | No nb-rip-card when ripening=[] |
| `test_bilingual_shelf_headers_contain_zh_text` | CJK + 入场/待熟/信号已过 in rendered output |
| `test_entry_shelf_may_reference_cascade` | Existing washout chip intact on ENTRY cards |

All 16 new tests pass. No regression in any of the 126 pre-existing tests across W0, W1-A, W1-B, and W0.9 copy tests.

---

## 6. Files

| Path | Description |
|---|---|
| `templates/china.html.j2` | Three-shelf partition + CSS additions + help text extension |
| `tests/test_china_stocks_w1c_render.py` | 16 template render/invariant tests |
| `research/china_alpha/w1/W1C_RENDER_REPORT.md` | This file |

---

## 7. Open items carried forward

- Live artifact update: the next builder run (with W1-B in place) will populate `stage` fields and `ripening`/`ran` arrays, making the three shelves visible on the live site.
- Click-through (china_lookup.html): W-tier setup state in the per-stock lookup — W2 or later.
- RIPENING conversion grading: when the W6 ledger matures, the `ripening.parquet` append (W1-B) enables computing the RIPENING→ENTRY conversion rate vs base rate.
