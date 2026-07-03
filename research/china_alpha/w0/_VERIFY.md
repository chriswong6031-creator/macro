# W0 Verification + Adversarial Review — VERDICT: fix-needed

**Date:** 2026-07-03 · **Reviewer:** Opus (verification gate) · **Worktree:** `lucid-knuth-523979`

One blocker. Everything else (grading fix, HOLD port, theme-join, sector chip, gate diagnosis,
freshness stamp, board-width guard, copy rewrite) is correct, scope-clean, and tested. The blocker
is a shipping HTML defect in `templates/china.html.j2` that the W0.9 executor report claims was
fixed but was NOT — the file still contains Unicode curly-quote characters used as HTML attribute
delimiters.

---

## BLOCKER (must fix before ship)

### B1 — Curly-quote attribute delimiters in `templates/china.html.j2` (lines 1205, 1208, 1252)

Three edited lines use U+201C/U+201D (`"` / `"`) as HTML attribute and Jinja-string delimiters
instead of ASCII `"`:

- **L1205:** `<span class="note" style="text-transform:none">` — standout h2 subtitle
- **L1208:** `<p class="note" style="margin:0 0 2px;text-transform:none">` — standfirst paragraph
- **L1252:** `<span class="nb-cscore band-{{ c.band }}" title="…"><span class="nb-crank">` — the
  per-card buy-readiness SCORE chip (renders on **every** board card)

Impact:
- Browser parses `class="note"` as a literal class named `"note"` (curly quotes included) →
  does not match CSS `.note` → the standout subtitle and standfirst lose their styling.
- L1252 is worse: the score chip's `class="nb-cscore band-…"` and `title="…"` and the inner
  `<span class="nb-crank">` all break → the score badge loses all styling on every card, and the
  `{{ c.band }}` band color is dead. This is the loudest per-card field.

Evidence (grep confirms characters are live in the file, not just the diff):
```
$ grep -nP '[\x{201C}\x{201D}]' templates/china.html.j2
1205: <span class="note" style="text-transform:none">
1208: <p class="note" style="margin:0 0 2px;…">
1252: <span class="nb-cscore band-{{ c.band }}" title="…"><span class="nb-crank">
```
(Curly quotes elsewhere — L1214/1357/1508 — are inside help() STRING CONTENT and are fine.)

**Why the executor's test missed it:** `tests/test_china_stocks_copy_w09.py:75` verifies only
`env.parse(SRC)` (Jinja syntax). Curly quotes outside `{{ }}` are raw text to Jinja, so
`env.parse` returns OK (verified) while the rendered HTML is broken. The test has zero power
against this defect — verification theater.

**Report contradiction:** `W0.9-copy-rewrite.md` §"Template-compile smoke / Quote fix" explicitly
claims "converted the four curly-quote delimiter characters to straight ASCII." The file proves
the conversion was not applied (or was reverted). Do not ship on the report's word.

**Fix:** replace the curly quotes at L1205, L1208, L1252 with ASCII `"`. Trivial, but must be done
and re-grepped before ship.

---

## Tests run (honest pass/fail)

| File | Result |
|---|---|
| tests/test_china_alpha_w0.py + test_w0_5_10_8.py + test_china_stocks_copy_w09.py | 53 passed |
| tests/test_china_name_score.py, test_china_sector_central.py, test_china_standout_track.py, test_grade_us_board.py | 48 passed, 1 skipped |
| Smoke: `pytest tests -q -k "china or hold or standout or sector_central"` | **573 passed, 1 failed**, 1 skipped |

The one smoke failure is `test_china_news.py::test_adapter_is_registered_without_akshare`:
`ImportError: cannot import name 'all_adapters' from 'scripts.collect'`. **Pre-existing, NOT a W0
regression** — no executor touched `scripts/collect.py` or `engine/china_news`; it is the known
akshare/collect CI dependency issue. Not a W0 blocker.

Note: no test in the wave catches B1. A rendered-HTML assertion (e.g. render the standout block
and assert `class="nb-cscore"` appears with ASCII quotes) would give the test power.

---

## Fixture checks

| Check | Result | Evidence |
|---|---|---|
| (a) `_basket_tailwind_map` (THS ext), 300725.SZ non-null theme | PASS | live run: 300725.SZ → `Synthetic Biology (THS)`, rel20=17.8%; 1017 names covered |
| (b) `hold.hold_state` on 603129.SS closes → dict/clean None | PASS | returns dict `{state:'launched', anchor:'2026-06-26', days_basing:5, …}` |
| (c) `append_board` extended row schema (dry-run, restored) | PASS | 7 new cols present (ticks/provisional/ext_score/washout_2w/hold_state/entry_status/sector_turn); board.parquet restored, `git status` clean |
| (d) `regime_state()` + sector-gate diagnosis bannered | PASS | `_regime_anchor()`: gate=0.2, `gate_caps_tier='Accumulate'`, `any_stale=False` — genuine risk-off, template banners the structural cap |
| (e) touched templates compile (repo idiom) | PASS (weak) | all 3 `env.parse` OK — but this idiom does NOT catch B1 (curly-quote HTML), see B1 |
| (f) copy no longer claims board ranks by reversal | PASS | board subtitle/help/legend/footer now say washout→base→turn + "reversal … is a separate product, not what drives this board"; remaining `mean-revers` hits (L1318/1506/1534) are the SEPARATE residual-alpha panel, correctly untouched per F5 |

---

## Ship-shape (F3) audit — CLEAN

- No `_cn_bonus` changes. No `blend_sorted` usage changes. No board-ordering changes.
- Only comment references to those symbols ("never fed into `_cn_bonus`/`blend_sorted`").
- All new fields are display/ledger only. HOLD, sector_turn, tailwind, freshness stamp, width
  guard, copy — all additive. Confirmed by full diff read.

## i18n / Jinja audit

- New chips (HOLD, sector_turn, freshness, outage banner) use dual-span `l-en`/`l-zh`. Correct.
- No `t()` inside HTML attributes in new code (titles are English-only per the MEMORY gotcha).
- No missing-key `{% if d.key is not none %}` crash patterns introduced — new accesses use
  `.get()` guards (`n.get('hold')`, `n.get('sector_turn') and …`). Safe.

---

## Hygiene — dirtied tracked DATA files

Four tracked data files were dirtied by test/import side-effects (live-data drift, none in any
executor report, none touched by W0 code): `data/demand_chain/alerts_state.json`,
`site/altdata/track_record.json`, `site/demand.html`, `site/live/overlay.json` (overlay had rebuilt
with `quote_ts_max: null`). **Restored** via `git checkout --`. `git status` now shows only the
intentional W0 code/test files.

One untracked artifact remains: `data/vector/regime_calibration.json` — a BTC-vector calibration
side-effect of an import during tests, unrelated to W0, NOT gitignored. Left in place (untracked,
harmless) but **must not be `git add`ed** into the W0 commit.

---

## Minor (non-blocking) observations

- `build_china_library._basket_tailwind_map` W0.5 honesty log (`_n_zero`) always reports `0 with
  zero membership` because it counts entries already IN `out` (which all have a name), not board
  names absent from `out`. The log line is misleading but harmless — it does not affect output or
  ranking. Consider fixing the log to count board tickers not in the map. W1 cleanup, not a blocker.

---

## VERDICT: fix-needed

Single blocker B1 (curly-quote attribute delimiters, china.html.j2 L1205/L1208/L1252). Everything
else ships. After B1 is fixed and re-grepped clean, this wave is shippable.
