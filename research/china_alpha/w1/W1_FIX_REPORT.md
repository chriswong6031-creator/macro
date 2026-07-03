# W1 Fix Report — B1 + B2 + Minors

**Date:** 2026-07-03
**Status:** COMPLETE — 108 passed (up from 94), 0 new failures.
**Broader smoke:** 554 passed, 1 pre-existing failure (test_china_news, documented, unrelated).

---

## Blockers fixed

### B1 — Builder crash on buy_now+overextended (scripts/build_china_library.py)

**Root cause reproduced (pre-fix):** `assign_stage(gate_eligible=True, entry_status='buy_now', overextended=True)` correctly returned `STAGE_RAN_LATE` (F6 ruling: extension beats timing gauge). The builder then asserted `entry_status=buy_now must never appear on a RAN_LATE row` — a self-inflicted contradiction that crashed on 002896.SZ and 002472.SZ.

**Fix:**
1. `engine/setup_tier.py` — Rule 2 now distinguishes the muted-entry path: when `overextended=True AND entry_status in {buy_now, partial}`, emits `muted_entry=True` in the detail dict and the sublabel "entry gauge open — but extended; wait for pullback" (vs "signal live — entry passed; wait for pullback" for non-muted cases).
2. `scripts/build_china_library.py` — The old crashing `_r2_bad` assert is replaced with three render-level invariants:
   - Every rule-2 RAN_LATE row must have a sublabel.
   - Every rule-2 RAN_LATE row with `entry_status in {buy_now, partial}` must have `muted_entry=True` on the row dict.
   - After stage assignment, `muted_entry=True` is propagated from `stage_detail` to the top-level row dict (Jinja reads `n.get('muted_entry')`, not the nested detail).
   - Dead line `_cand_tickers = ...` (L~1475) removed.

**Verification:** Synthetic simulation of 002896.SZ/002472.SZ (buy_now+extended) now produces `RAN_LATE + muted_entry=True + sublabel` without any AssertionError.

### B2 — Template green banding leak on RAN_LATE cards (templates/china.html.j2)

**Root cause:** The RAN_LATE card rendered `<div class="nb-entry nbe-{{ es.status }}"...>` unconditionally. For `partial` (not caught by the old assert) this rendered `nbe-partial` = green left-border + green dot + "Buy now" tooltip — F6 verbatim.

**Fix (templates/china.html.j2, ~L1490):** The entry gauge block is now gated on `n.get('muted_entry')`:
- `muted_entry=True` → renders `nbe-wait_pullback` (amber, not green) with a neutral dual-span line: "gauge open — but extended; not actionable / 量表打开 — 但已延伸；当前不可操作". No green class, no "Buy now" text, no `a3` dot.
- `muted_entry` falsy → renders the standard gauge unchanged (for hold/extended/topping RAN_LATE rows that are not overextended+actionable).

**Invariants verified by tests:**
- `nbe-buy_now` must not appear on muted_entry RAN_LATE card.
- `nbe-partial` must not appear on muted_entry RAN_LATE card (partial case).
- "Buy now" text must not appear.
- ENTRY cards still render `nb-entry` with full green banding (no regression).
- Non-muted RAN_LATE cards (hold status) still render their gauge.

---

## Minors fixed

### Minor 1 — Dead `_cand_tickers` line

`scripts/build_china_library.py:~L1475` — the line `_cand_tickers = {r.get("ticker") for _s, r in cand}` was assigned and never read. Removed.

### Minor 2 — Hold compact line on RAN cards (launched state omitted)

**Problem:** `assign_stage` rule 3 only emitted a `basing_chip` when `hold_state.state == "intact"`. 603129.SS (launched) carried `hold_summary=None` despite having a meaningful hold context.

**Fix:**
- `engine/setup_tier.py` rule 3: now emits `launched_chip` (alongside the existing `basing_chip`) when `hold_state.state == "launched"`. Format: "launched from {anchor}, +X.X%".
- `scripts/build_china_library.py`: `_ran_rows.append()` now includes `"launched_chip"` from the stage detail. `hold_summary` now also captures `launched` state (with `maxup_pct` + `invalidation`).
- `templates/china.html.j2`: rule-3 RAN rows now render `launched_chip` as a green-colored detail line ("↑ launched from ... / 已突破") alongside the existing `basing_chip` amber line.

### Minor 3 — Ledger log-count cosmetic

`scripts/build_china_library.py` log line: `"logged %d names (ledger=%d)"` changed to `"appended %d names this run (total ledger rows=%d)"` to distinguish the per-run count from the cumulative total.

---

## Tests updated

| File | Before | After | New tests |
|---|---|---|---|
| `tests/test_setup_tier.py` | 44 | 51 | `test_rule2_buy_now_overextended_sets_muted_entry`, `test_rule2_partial_overextended_sets_muted_entry`, `test_rule2_hold_status_does_not_set_muted_entry`, `test_rule2_muted_entry_sublabel_differs_from_standard`, `test_rule3_launched_state_adds_launched_chip`, `test_rule3_hold_invalidated_no_chip` (extended to cover launched) |
| `tests/test_china_alpha_w1b.py` | 34 | 38 | Replaced old `test_rule2_row_cannot_have_buy_now_entry_status` (wrong per F6) with 4 new tests: `test_rule2_buy_now_not_overextended_stays_entry`, `test_rule2_buy_now_overextended_routes_ran_late_with_muted`, `test_rule2_partial_overextended_routes_ran_late_with_muted`, `test_render_invariant_muted_entry_propagated_to_row` |
| `tests/test_china_stocks_w1c_render.py` | 16 | 22 | `test_b1_b2_muted_entry_ran_late_no_green_banding`, `test_b2_partial_overextended_ran_late_no_green_banding`, `test_muted_entry_does_not_suppress_non_muted_ran_entry_gauge`, `test_entry_stage_card_still_green_after_muted_fix`, `test_ran_array_launched_chip_renders`, `test_ran_array_basing_chip_renders` |

Total: 108 passed (from 94).

---

## Files changed

| File | Change |
|---|---|
| `engine/setup_tier.py` | Rule 2: `muted_entry` flag + distinct sublabel for buy_now/partial+overextended. Rule 3: `launched_chip` for launched hold_state. |
| `scripts/build_china_library.py` | Remove `_cand_tickers`; propagate `muted_entry` from stage_detail to row; replace crashing assert with render-level invariants; `hold_summary` captures launched state; `launched_chip` in ran rows; log cosmetic. |
| `templates/china.html.j2` | RAN_LATE card entry gauge gated on `muted_entry`; neutral muted line when true; `launched_chip` render in rule-3 ran rows. |
| `tests/test_setup_tier.py` | 7 new tests for muted_entry + launched_chip. |
| `tests/test_china_alpha_w1b.py` | Replaced wrong invariant test with 4 correct F6-aligned tests. |
| `tests/test_china_stocks_w1c_render.py` | 6 new B1/B2 regression tests. |

---

## Invariants now in force (post-fix)

1. `assign_stage` rule 1: `buy_now/partial + NOT overextended -> ENTRY` (unchanged).
2. `assign_stage` rule 2: `buy_now/partial + overextended -> RAN_LATE + muted_entry=True` (F6 adjudicated). `hold/extended/topping -> RAN_LATE + muted_entry absent`.
3. Builder: every rule-2 RAN_LATE row has a sublabel (assert).
4. Builder: every rule-2 buy_now/partial RAN_LATE row has `muted_entry=True` (assert).
5. Template: `muted_entry=True` rows render `nbe-wait_pullback` (amber) — no `nbe-buy_now`, no `nbe-partial`, no "Buy now".
6. Template: ENTRY-stage cards (only) render green banding and BUY-family words.
