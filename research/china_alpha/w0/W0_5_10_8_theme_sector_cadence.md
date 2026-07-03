# W0 — Items 5, 10, 8: Theme-Join Fix · Sector First-Tick-Up · JSON Cadence Honesty

**Date:** 2026-07-03  
**Wave:** W0 (repair + honesty, display/log only — no rank changes)  
**Items:** W0.5 (THS theme-join), W0.10 (sector first-tick-up chip), W0.8 (per-stock JSON cadence banner)

---

## What changed and why

### W0.5 — Theme-join fix (`scripts/build_china_library.py:_basket_tailwind_map`)

**Problem (evidenced in exemplar-300725.md):** The TWD (tailwind) axis showed "no data" for 300725.SZ
despite the stock belonging to "Synthetic Biology" (THS concept basket) with +18.9% 20d rel.
Root cause: `_basket_tailwind_map()` only read curated baskets (`compute_china_baskets`), which
has 22 baskets and 280 unique members. Neither 300725.SZ, 603129.SS, nor 688306.SS appear in
any curated basket.

**Quantified gap (measured this session):**
- Curated members: 280; THS members: 915
- Board names (110 buy rows) with zero curated membership: 94 of 110 (85%)
- Board names THS would help: 63 of 110 (57%)
- 603129.SS, 300725.SZ, 688306.SS — all three exemplars have ZERO curated membership; all three
  have THS membership.

**Fix:** Extended `_basket_tailwind_map()` to call `compute_china_ths_baskets()` in addition to
`compute_china_baskets()`. Per-ticker winner = strongest `|rel20|` across curated+THS. THS entries
are labeled `"theme: <name> (THS)"` so the template can distinguish them. A build-time log reports
total coverage after the merge.

**Verified results (live run on real basket data):**
- `300725.SZ` → `"theme: Synthetic Biology (THS)", rel20=17.8%` (was null, the documented hole)
- `603129.SS` → `"theme: Two-Wheelers (THS)", rel20=-3.8%` (was null)
- `688306.SS` → `"theme: Solid-State Battery (THS)", rel20=31.8%` (was null; Humanoid Robots
  would also qualify at 15.1% but Solid-State Battery is the strongest THS basket for this name)
- Total coverage: 1,017 names (up from ~280 with curated only)

**Constraints respected:**
- DISPLAY-ONLY: feeds the tailwind display axis in `conviction_profile`; no change to `_cn_bonus`
  or `blend_sorted` (rank spine untouched).
- Source field added to the dict (`"source": "curated"` or `"source": "ths"`) — additive,
  backward-safe (existing consumers only read `name` and `rel20`).

---

### W0.10 — Sector first-tick-up chip (`scripts/build_china_library.py` + `engine/china_standout_track.py`)

**Problem (evidenced in rotation-machinery.md §3.2):** `data/china_sector_cycles/forward_log.parquet`
already contains `phase` and `osc_slope` for 31 Shenwan L1 sectors daily. The "first-tick-up"
signal (phase=="Trough" AND osc_slope>0) is the earliest non-confirmation-lagged inflection in the
sector-cycle stack — yet it was never pulled into the picker or the ledger.

**Today's qualifying sectors (2026-07-03, verified live):**
- Agriculture (osc_slope=0.8, signature=6.0)
- Pharma & Biotech (osc_slope=2.0, signature=30.0) — the 300725 sector
- Non-bank Financials (osc_slope=9.5, signature=41.0)

**Fix:**
1. In `main()`: load `forward_log.parquet`, filter to latest date + kind=="sector", derive
   `_sector_turn_by_sw` dict (Shenwan L1 name → `{state, osc_slope, signature, asof, approx:true}`).
2. Hand-mapped `_YAHOO_TO_SW` dict (11 Yahoo GICS-style sectors → Shenwan L1 names). The
   taxonomies differ; every entry carries `approx:True` so template and grader can label it.
3. In the standout-row enrichment loop: attach `sector_turn` to board rows where the Yahoo sector
   maps to a qualifying Shenwan sector.
4. Card chip in `templates/china.html.j2`: renders `"↑ sector: bottoming" / "↑ 板块：触底"` using
   the existing `nb-coiled` CSS class (same weight as other context chips). Title attribute shows
   the asof date and the `approx` warning.
5. Ledger column in `engine/china_standout_track.py:append_board`: adds `"sector_turn"` column
   (schema-union safe via `pd.concat` — old rows read as NaN). Also added to `grade()` recs and
   `by_sector_turn` stratification slice.

**Constraints respected:**
- DISPLAY/LEDGER ONLY — `_cn_bonus` and `blend_sorted` untouched.
- `approx:True` propagated at every layer so the approximate join is never hidden.
- No Jinja `.key` access on a possibly-missing key: used `.get('sector_turn')` and guarded with
  `{% if n.get('sector_turn') and n.get('sector_turn').get('state') == 'bottoming' %}`.

---

### W0.8 — Per-stock JSON cadence honesty (`templates/china_lookup.html.j2`)

**Problem (evidenced in exemplar-300725.md §0):** Per-stock JSONs in `site/chinastockdata/` can
trail the board (`china_standouts.json`) by multiple sessions. The exemplar showed: board as_of
2026-07-02, per-stock JSON asof 2026-06-26 for 603129.SS (6 days stale). The lookup page showed
score 77/"constructive" while the board card said 26/"Watch" — a user navigating the board saw an
actively contradictory signal on click-through.

**Fix (display-only, cheapest honest path per spec):** Added a staleness banner
(`#r_stale_banner`, CSS class `stale-banner`) to `china_lookup.html.j2`:
- Banner appears when `d.asof` trails today's date by >1 calendar day (a gap of 1 day is normal;
  >1 indicates a missed build cycle).
- Copy: `"Detail data as of <date> — the board may be fresher. Score and signals on the board
  could differ."` with dual-span bilingual pattern (`l-en`/`l-zh`).
- Uses the existing `L('stale_prefix')` / `L('stale_suffix')` i18n key pattern (added to both
  `T.en` and `T.zh`).
- Banner is hidden (`display:none`) when data is current.
- Also changed `asof:` label from `"data through"` to `"data as of"` to match the precise semantic
  (these JSONs carry the build date, not a data-through date).

**Root cause of the cadence gap (carry-over):** The render pipeline (`nightly daily` vs `nightly
render` lane) only commits `data/` from the asia build; the per-stock JSONs in `site/chinastockdata/`
are regenerated by `build_china_library.py` in every nightly build, but if a build is skipped or
the china lane fails, the JSONs age. The honest fix for the cadence itself (ensuring every build
regenerates all per-stock JSONs) is larger than W0 — carry-over to W1 infra planning.

---

## Evidence

| Item | Claim | Verified by |
|------|-------|-------------|
| W0.5 | 300725.SZ was TWD=null before fix | exemplar-300725.md §4 item 6 |
| W0.5 | THS "Synthetic Biology" has +18.9% rel20 | `baskets_ths.json` live read |
| W0.5 | 300725 now gets rel20=17.8% from THS | live run `_basket_tailwind_map()` with real data |
| W0.5 | 63 of 110 board names gain THS coverage | live board membership scan |
| W0.10 | Pharma & Biotech has osc_slope=2.0 as of 07-03 | forward_log.parquet live read |
| W0.10 | Healthcare → "Pharma & Biotech" map produces sector_turn for 300725 | live simulation |
| W0.10 | sector_turn column added to ledger schema | `china_standout_track.py` edit |
| W0.8 | Banner triggers when diffDays > 1 | JS logic + test coverage |
| W0.8 | Dual-span bilingual pattern used | template inspection + test |

---

## Tests

File: `tests/test_w0_5_10_8.py` — 22 tests, all pass.

```
tests/test_w0_5_10_8.py::TestW05TailwindMap::test_ths_only_name_gets_tailwind PASSED
tests/test_w0_5_10_8.py::TestW05TailwindMap::test_curated_beats_ths_when_stronger PASSED
tests/test_w0_5_10_8.py::TestW05TailwindMap::test_ths_beats_curated_when_stronger PASSED
tests/test_w0_5_10_8.py::TestW05TailwindMap::test_ths_label_prefixed_correctly PASSED
tests/test_w0_5_10_8.py::TestW05TailwindMap::test_curated_label_unchanged PASSED
tests/test_w0_5_10_8.py::TestW05TailwindMap::test_failure_in_ths_degrades_gracefully PASSED
tests/test_w0_5_10_8.py::TestW010SectorFirstTickUp::test_pharma_qualifies_as_first_tick_up PASSED
tests/test_w0_5_10_8.py::TestW010SectorFirstTickUp::test_sector_turn_state_is_bottoming PASSED
tests/test_w0_5_10_8.py::TestW010SectorFirstTickUp::test_approx_flag_set PASSED
tests/test_w0_5_10_8.py::TestW010SectorFirstTickUp::test_yahoo_to_sw_map_has_healthcare PASSED
tests/test_w0_5_10_8.py::TestW010SectorFirstTickUp::test_ledger_append_has_sector_turn_column PASSED
tests/test_w0_5_10_8.py::TestW010SectorFirstTickUp::test_grade_slices_by_sector_turn PASSED
tests/test_w0_5_10_8.py::TestW08StalenessBanner::test_template_parses_without_errors PASSED
tests/test_w0_5_10_8.py::TestW08StalenessBanner::test_stale_banner_element_present PASSED
tests/test_w0_5_10_8.py::TestW08StalenessBanner::test_stale_banner_has_stale_class PASSED
tests/test_w0_5_10_8.py::TestW08StalenessBanner::test_stale_prefix_key_in_en_dict PASSED
tests/test_w0_5_10_8.py::TestW08StalenessBanner::test_stale_suffix_key_in_both_dicts PASSED
tests/test_w0_5_10_8.py::TestW08StalenessBanner::test_zh_stale_copy_is_present PASSED
tests/test_w0_5_10_8.py::TestW08StalenessBanner::test_banner_shown_when_diffdays_gt_1 PASSED
tests/test_w0_5_10_8.py::TestW08StalenessBanner::test_banner_hidden_when_not_stale PASSED
tests/test_w0_5_10_8.py::TestW08StalenessBanner::test_dual_span_bilingual_pattern_in_banner PASSED
tests/test_w0_5_10_8.py::TestW08StalenessBanner::test_no_t_call_inside_attributes_in_banner PASSED
```

Regression check on sibling test suites: 48 total (22 new + 26 pre-existing), all pass.
Pre-existing `test_canada_insider` failure confirmed to pre-date these changes (fails on git stash
baseline).

---

## Files changed

| File | Change |
|------|--------|
| `scripts/build_china_library.py` | W0.5: extend `_basket_tailwind_map` to include THS; W0.10: load forward_log, build `_sector_turn_by_sw`, attach `sector_turn` to standout rows |
| `engine/china_standout_track.py` | W0.10: add `sector_turn` column to `append_board` and `grade` |
| `templates/china.html.j2` | W0.10: sector first-tick-up chip in card sub-strip |
| `templates/china_lookup.html.j2` | W0.8: staleness banner CSS, HTML element, JS logic, bilingual strings |
| `tests/test_w0_5_10_8.py` | New: 22 tests for W0.5, W0.10, W0.8 |

---

## Deferred items

- **W0.8 root cause (render cadence):** The actual fix for making per-stock JSONs regenerate on
  every nightly build (not just the asia lane) is wider than W0. Carry to W1 infrastructure.
- **W0.10 taxonomy accuracy:** The Yahoo→Shenwan map is an 11-sector approximation. A precise join
  would require a per-ticker Shenwan-L1 lookup (currently not stored in the board rows).
  `approx:True` on every entry is the honest declaration. Upgrade path: add `shenwan_sector` field
  to per-name records when the collector can source it.
- **W0.5 THS membership coverage at 0 for remaining 31 board names:** 31 of 110 board names are
  not in any curated or THS basket. These are thinly-traded or newly-listed names outside both
  taxonomies. The tailwind axis stays null (honest absence, not a false neutral) for these names.
- **chip in china_lookup.html.j2 for sector_turn:** The lookup page (`china_lookup.html.j2`) does
  not currently render `sector_turn` — it would need to be wired from the per-stock JSON (which
  gets the field only if it appears on the board row, not from the per-stock JSON write path).
  Carry to W1 when per-stock JSON cadence is addressed.
