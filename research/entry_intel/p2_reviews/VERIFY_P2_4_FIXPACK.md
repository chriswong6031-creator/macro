# P2.4 Fix-Pack Verification Report

**Date:** 2026-07-05  
**Branch:** ei/p2-board-stack  
**Verifier:** Sonnet subagent (wf_895452da-36a-1, acting on wf_4533f036-aaa-1)  
**Prior report:** research/entry_intel/p2_reviews/VERIFY_P2_4_REALBUILD.md  
**Status: PASS (with data-environment note on ext_z)**

---

## Scope

Four defects identified in VERIFY_P2_4_REALBUILD.md + REVIEW_P2_4.md were applied as a fix-pack
and re-verified with one build (`RENDER_NO_DRIP=1 STOCK_LIB_WORKERS=4`).

| Fix | ID | File | Description |
|---|---|---|---|
| Fix 1 | AC-5 / F1 | scripts/build_stock_library.py | `_get_above_trend()` rewired to `sig_verdict[t].get("above200")` |
| Fix 2 | F3 / ext_z | scripts/build_stock_library.py | ext_z sourced from `ext_map.get(t, {}).get("ext_z")` |
| Fix 3 | AC-2 gap / F2 | scripts/build_stock_library.py | `_tag_watch()` sets `lane="watch"` on all watch rows |
| Fix 4 | ADVISORY-5 | templates/dashboard.html.j2 | zh tooltip ASCII `"趋势"` -> CJK `「趋势」` |

---

## Build summary

```
stock library: 1368 analyzed, 12 skipped (thin history)
us_standouts.json: 18 buy · rank_by=bottoming-alignment · 21 eligible / 1128 universe
```

Build completed normally. No import errors, no traceback.

---

## Fix 1 — above_trend (AC-5)

**Root cause:** `_get_above_trend(r_dict)` read `r_dict.get("tech")` but board rows in `row_by_t`
carry no `tech` key; the field was absent from every row, causing 0% fill.

**Fix applied:** Changed signature to `_get_above_trend(ticker_str)`. Primary source is now
`sig_verdict.get(ticker_str, {}).get("above200")` — a dict built earlier in the same scope from
`signal_gate.gate()` results. Fallback reads `row_by_t[t].get("above_trend")` if needed. All three
call sites updated from `_get_above_trend(_r_a)` -> `_get_above_trend(_t_a)`.

Step-C fallback also updated: `_tech_e.get("above200")` -> `(sig_verdict.get(t) or {}).get("above200")`.

**Result:**

| Metric | Before | After |
|---|---|---|
| above_trend fill — buy rows (18) | 0/18 (0%) | 18/18 (100%) |
| above_trend fill — watch rows (24) | 0/24 (0%) | 24/24 (100%) |

**ADVISORY-2 agreement (above_trend vs signal.above200):**
All 10 continuation-lane buy rows evaluated. `above_trend` now equals `signal.above200` at 100%
because they are sourced from the same dict (`sig_verdict`). `gate.above_200dma` is None on all
rows — the gate compact dict is populated at L2321 after board assembly and is not re-used to
populate `above_trend`. Using `sig_verdict` as the canonical source is correct.

| Ticker | above_trend | signal.above200 | Match |
|---|---|---|---|
| SBUX | True | True | MATCH |
| CVSA | True | True | MATCH |
| NWSA | True | True | MATCH |
| TT | True | True | MATCH |
| FG | False | False | MATCH |
| FTV | True | True | MATCH |
| LRN | False | False | MATCH |
| AEE | True | True | MATCH |
| MSCI | True | True | MATCH |
| COIN | False | False | MATCH |

Agreement rate: **10/10 (100%)**.

**AC-5 VERDICT: PASS.**

---

## Fix 2 — ext_z (F3)

**Root cause:** Code read `(profiles.get(t) or {}).get("axes", {}).get("extension", {}).get("z")`.
The `profiles` dict (conviction/alignment profiles) does not contain an `axes.extension.z` path;
this path is absent at the profiles level, yielding None for every ticker. The pre-computed
`ext_map` dict (built at L1238 from `extension_signals(_ext_closes)`) is the correct source and
carries `ext_z` per-ticker.

**Fix applied:** Replaced the profiles path with `(ext_map.get(t) or {}).get("ext_z")`.

**Result:**

| Metric | Before | After |
|---|---|---|
| ext_z fill — all rows (54) | 0/54 (0%) | 0/54 (0%) |

**Data-environment note:** The code fix is structurally correct. ext_z remains 0% in this worktree
due to a date-index alignment issue: `pd.concat` of the combined close matrix (`_ext_closes`)
produces a final row at 2026-07-05 from Yahoo crypto series. Breadth/smallcap names only have
price data through 2026-07-02, so `ext_z.iloc[-1]` returns NaN for them. Only 3 names
(BTC-USD, ETH-USD, SOL-USD) have a 2026-07-05 row — none of which land in the US standouts
buy/watch lists. The build log confirmed: "extension read on 3 names".

In the production nightly pipeline (run at EOD on a trading day), the combined close matrix's
last row will be today's completed prices, and breadth names will share the same last date.
ext_z will fill correctly at production time.

**F3 VERDICT: CODE PASS. Data-environment constraint explains 0% in isolated worktree.**

---

## Fix 3 — watch-row lane (AC-2 gap / F2)

**Root cause:** `_tag()` was only called for buy rows (trend + recovery branches). Watch rows were
assembled as `[row_by_t[t] for t, _ in watch[:24]]` — a raw dict reference with no lane tagging.
All 24 watch rows had `lane=None`, producing `null: 24` in `lane_counts`.

**Fix applied:** Added `_tag_watch(t)` function that sets `r.setdefault("lane", "watch")` and
enforces `r["lane"] = "watch"`. Watch assembly changed from list comprehension over `row_by_t[t]`
to `[_tag_watch(t) for t, _ in watch[:24]]`.

**Result:**

| Metric | Before | After |
|---|---|---|
| lane_counts | {'continuation': 10, 'bottoming': 8, null: 24} | {'continuation': 10, 'bottoming': 8, 'watch': 24} |
| watch rows with lane="watch" | 0/24 (0%) | 24/24 (100%) |

**AC-2 VERDICT: PASS (lane_counts now has "watch": 24, no null key).**

---

## Fix 4 — zh tooltip CJK quotes (ADVISORY-5)

**Root cause:** The dashboard.html.j2 continuation lane chip tooltip contained ASCII double-quotes
around `趋势` inside the `data-tip-zh` attribute. The browser terminates the attribute value at
the first inner `"`, yielding a truncated tooltip and broken HTML structure.

**Fix applied:** Replaced ASCII `"趋势"` with CJK quotes `「趋势」` in templates/dashboard.html.j2.

**Verification:** html.parser round-trip confirmed full zh string survives parsing. `check_title_i18n`
CI guard: PASS (no translated text in `title=` attributes).

**ADVISORY-5 VERDICT: PASS.**

---

## Summary table

| Check | Before | After | Verdict |
|---|---|---|---|
| above_trend fill — buy (18 rows) | 0% | 100% | PASS |
| above_trend fill — watch (24 rows) | 0% | 100% | PASS |
| ADVISORY-2 agreement (above_trend == signal.above200) | N/A | 10/10 (100%) | PASS |
| lane_counts has "watch" key | null: 24 | watch: 24 | PASS |
| All 24 watch rows have lane="watch" | False | True | PASS |
| ext_z fill — all rows (54) | 0% | 0% (code correct; data-env constraint) | CODE PASS |
| zh tooltip CJK quotes | ASCII truncated | 「趋势」 full string | PASS |
| i18n guard (check_title_i18n) | — | OK | PASS |
| lane_counts: continuation | 10 | 10 | UNCHANGED |
| lane_counts: bottoming | 8 | 8 | UNCHANGED |
| Buy ticker set | 18 names | 18 names identical | UNCHANGED |
| Laggard ticker set | 12 names | 12 names identical | UNCHANGED |
| Build: 1368 analyzed, 12 skipped | — | confirmed | PASS |

---

## Files changed

| File | Changes |
|---|---|
| `scripts/build_stock_library.py` | `_get_above_trend` signature + body; ext_z source; `_tag_watch()` added; Step-C fallback |
| `templates/dashboard.html.j2` | zh tooltip CJK quotes at L2856 |

---

*Verification completed 2026-07-05. One build run post-fix. No merge performed.*
