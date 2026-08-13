# G-D — plan-book actionability + enrichment: provenance census and publication path

**Date:** 2026-08-13 · **Gate:** MP-1 spawn gate G-D (`mockups/refs/institutionalize/us_stocks/DESIGN_NOTES.md` §7, PR #5514)
**Code:** `engine/prophet_board_read.py` · `tests/test_prophet_board_read.py`
**Producers touched:** `scripts/build_prophet.py`, `scripts/build_stock_library.py`, `.github/workflows/daily.yml`

G-D blocks the Board migration builder until the plan book publishes, **for the full plan
universe rather than the candidate intersection**, (1) the entry/actionability axis and
(2) name · sector · lane · spark. Measured on the 2026-08-13 payload, the axis reached
**61/179** rows and the enrichment **45/179**.

---

## 1. Census — why each row was missing

Measured against `site/prophet/index.json` (asof 2026-08-13, 179 plan rows, 166 distinct
tickers) and `site/factordata/us_standouts.json` (as_of 2026-08-12).

| Symptom | Rows | Cause class | Evidence |
|---|---|---|---|
| `entry_status` null | 118/179 | **Wrong field read** — it is an *origination* stamp, not a live read | Present as a KEY on 174/179 but non-null on exactly the 61 rows that also carry `admission_class` + `entry_basis` + `selection_era`. `build_prophet.py` publishes `plan.get("entry_status")` — the ANTICIPATION §6.2 A1 admission stamp, deliberately `None` before `anticipation-v1-2026-08-08` ("that null IS the era boundary, and it is printed rather than back-filled"). |
| name/sector/lane/spark absent | 134/179 | **Population mismatch** | The join was `us_standouts.buy` (70 rows) — a *screener* population. The plan book is a *ledger* population. Overlap: 44 tickers → 45 rows. Even the union of all five board buckets (157 rows) covers only 53/166 tickers → 56/179 rows. |
| — | — | **Producer absence: NO** | `entry_signal` is computed by `engine/entry_signal.assess` inside `build_stock_library`'s per-name **universe** loop (`uni = universe()`, ~1600 names), and `disp_map[ticker]` (price/off-high/spark) is built in that same loop for every name. Both were published **only** where a name reached a board bucket (`build_stock_library.py` :4935 / :4940). Probing `site/stockdata/<TICKER>.json` for the 166 plan tickers found records for **162**, carrying `entry_signal.status` on 161 and name/sector on 162. |
| — | — | **Join-key mismatch: NO** | `ticker` joins cleanly; the filename mapping is `ticker.replace("=","_").replace("^","_")`. |
| 4 tickers with no library record | 4 | **Genuinely unavailable** | `BHP`, `RIO` (foreign ADRs), `DXYZ`, `EU` — outside the US library universe. |
| Vintage | — | **Declared, pre-existing** | `index.asof` 2026-08-13 vs `source_board_asof` 2026-08-12; `source_mixed_vintage: true` already on the artifact. |

**Conclusion: this was a publication gap, not an availability gap** — with one genuine
exception (`lane`, below) and one genuine population edge (4 non-universe tickers).

---

## 2. The narrowest canonical path

`build_prophet` runs **after** `build_site`/`build_stock_library` in the same nightly job
(`daily.yml`: *"Prophet nightly … AFTER build_site: reads site/factordata/us_standouts.json
(just written)"*), so the per-ticker library records are on disk when the plan book is
published. The join therefore needs **no new upstream compute** — only:

1. `build_stock_library` stamps `spark_svg` and the gauge's disclosed
   `entry_signal_null_reason` onto the per-name record it already writes (`price`/`off_high`
   deliberately excluded — see §5);
2. `engine/prophet_board_read` joins by ticker with a declared two-rung source ladder —
   `us_stock_library` (universe-wide, primary) → `us_standouts` (committed board projection
   of the same records, fallback, and the **only** source for `lane`);
3. `build_prophet` stamps `board_read` on every plan row and publishes `board_read_lineage`
   + `board_read_coverage` at index level.

`entry_status` is **untouched**. It remains the frozen admission stamp that
`us_candidate_lanes` / `prophet_arena` / the shadow ledgers read as provenance. The live
read ships beside it, separately labelled. Overwriting it would have destroyed the era
boundary and silently changed a published field's meaning.

### Three honest states, one shape per field

```json
"board_read": {
  "schema": "prophet.board_read/v1", "scope": "ticker", "ticker": "AAPL",
  "as_of": "2026-08-13",
  "fields": {
    "status": {"value": "buy_soon", "state": "available", "reason": null, "source": "us_stock_library"},
    "lane":   {"value": null, "state": "not_applicable", "reason": "not_on_board", "source": null}
  }
}
```

`available` · `blocked_data` · `not_applicable` — and for every field,
`available + blocked_data + not_applicable == rows`.

**`not_applicable` is not a softer `blocked_data`.** A closed plan has no live stance;
reporting that as missing data would make a complete answer look like a gap.

### Reason vocabulary (closed set)

`plan_closed` · `library_source_unavailable` · `ticker_absent_from_library` ·
`gauge_null:<reason>` (reusing `engine.entry_signal.null_reason`'s own words verbatim —
`no_cycle_ladder` / `short_history` / `not_assessed` / `gauge_error:<Type>`) ·
`gauge_absent_undisclosed` · `field_absent_in_record` · `not_on_board` ·
`board_bucket_carries_no_lane`.

---

## 3. Before / after, by field (179 plan rows)

| field | before | after (available) | blocked_data | not_applicable |
|---|---|---|---|---|
| `status` | **61** | **156** | 3 | 20 |
| `name` | 45 | **177** | 2 | 0 |
| `sector` | 45 | **177** | 2 | 0 |
| `lane` | 45 (33 bottoming/continuation) | **54** | 0 | 125 |
| `spark` | 45 | **177** † | 2 | 0 |

† `spark` measured **56/179** against the current on-disk library tree, which predates the
producer change. `177` is derived, not guessed: the spark stamp and `to_write.append` sit in
the same loop iteration with no `continue`/`break`/`return` between them, so spark coverage
**equals** library-record coverage by construction —
`test_producer_stamps_the_enrichment_onto_every_universe_record` pins exactly that. First
directly measured on the next nightly.

**Every one of the 179 rows now terminates in a named state on every field.**

### Remaining non-available population, with causes

| field | state | n | cause | population |
|---|---|---|---|---|
| `status` | not_applicable | 20 | `plan_closed` | resolved plans — no live stance exists |
| `status` | blocked_data | 2 | `ticker_absent_from_library` | BHP, RIO |
| `status` | blocked_data | 1 | `gauge_absent_undisclosed` | ISRG — record present, gauge silent. Becomes `gauge_null:<reason>` once the producer change lands; the placeholder exists so the failure is disclosed rather than silent. |
| `name`/`sector`/`spark` | blocked_data | 2 | `ticker_absent_from_library` | BHP, RIO |
| `lane` | not_applicable | 123 | `not_on_board` | see §4 |
| `lane` | not_applicable | 2 | `board_bucket_carries_no_lane` | on the board, in `laggards` |

---

## 4. `lane` has a real ceiling, and that is the correct answer

`lane` is a **board-membership label**, not a per-name property.
`build_stock_library._lane_for` is *total* — it returns `"bottoming"` for any input it does
not recognise — so running it over the plan universe would yield 100% lane coverage made
entirely of fabricated setup archetypes for names the board never admitted.

Off-board rows are therefore `not_applicable`, and `lane` tops out at board membership
(54/179 today). G-D's phrasing groups four fields with different availability; three reach
177/179, and `lane` answers honestly at its true ceiling. Raising it requires widening the
*board*, not the join.

---

## 5. What was kept out

- **Live quote / change.** Not in this lane. `last_price` is already on the plan row at
  174/179 from the management engine, and the live quote is the page's `data-sym` path — no
  evidence was found that it is insufficient. `disp_map`'s `price`/`off_high` are
  deliberately not stamped onto the library record either: a top-level `price` would shadow
  the existing `tech.price` for every stockdata reader.
- **`recommended_action` as a stance.** The management engine is trade-management-only; its
  action carries display/narrative authority, not order authority (operator ruling
  2026-08-13). A plan carrying one with no axis is still `blocked_data`.
- **A default stance.** Coverage is an outcome, never a target.
- **Inline spark SVGs in `index.json`.** ~2 KB each; 177 of them would have grown the
  artifact by ~448 KB (66%) nightly, for a field only the Board renders while a dozen other
  consumers (Brain, the Terminal, `radar_internal`, `prophet_governor`,
  `us_candidate_lanes`, `options_issue_desk`, the R2 mirror) pay for it. The bodies ship in
  the ticker-keyed sibling `site/prophet/board_read_sparks.json` (~323 KB projected, 166
  tickers not 179 rows) and the row carries a resolvable reference. Registered in all three
  `daily.yml` Prophet output allowlists, or it would be runner-local and die.

---

## 6. Telemetry — why 179→45 cannot regress silently

`index.json.board_read_coverage` publishes, per field, the three state counts, the reason
histogram, the source histogram, `source_available`, `source_as_of`, `read_errors`, and
`status_unmapped`. A source outage moves published numbers to zero **and** stamps
`library_source_unavailable` on every row **and** prints a `::warning` in the nightly.

`status_unmapped` is the domain tripwire: if the engine's twelve-value actionability domain
grows a thirteenth word, it is published verbatim (never dropped, never relabelled into
something renderable) and counted here.

Coverage is also *self-consistent by test*: `available + blocked_data + not_applicable ==
rows` for every field.

---

## 7. Verification

- `tests/test_prophet_board_read.py` — 35 tests: authority, three-state termination, closed
  vocabulary, lane-not-derived, episode identity, telemetry partition, lineage, vintage
  refusal, spark sibling, join key, producer contract.
- **12/12 mutations killed**, including: axis falls back to `recommended_action`; unobtainable
  axis defaults to `wait`; lane derived off-board; closed plan reports a live stance;
  whole-source outage reported as per-ticker misses; coverage drops blocked rows from the
  partition; unmapped status relabelled; block overwrites the frozen admission stamp;
  mixed-vintage tree names a date anyway; spark claims `available` with nothing banked;
  producer stops stamping; a `continue` slipped between the stamp and the write.
- Regression sweep over the prophet suites: 730 passed. Three failures
  (`test_prophet_showcase.py` ×2, `test_prophet_anticipation_intake.py` ×1) are
  sparse-agent-worktree artifacts — `FileNotFoundError` on `site/index.html`,
  `site/landing.css`, `site/anticipationdata/us_leader_pullback.json`, all present in HEAD
  and omitted from this checkout — and reproduce identically with the diff reverted.

### One bug this caught in itself

The first cut wrote the sparks sibling to `SITE_PROPHET / …`.
`tests/test_prophet_bridge.py::test_end_to_end_smoke` redirects `INDEX_PATH` to `tmp_path`
but leaves `SITE_PROPHET` alone, so the write escaped into the real `site/prophet/` (an
*omitted tree* in a sparse agent worktree). Fixed by deriving the path from
`INDEX_PATH.parent` — which is also the semantically correct coupling, since the row's
`spark` value is a reference relative to the index. Pinned by
`test_sparks_artifact_follows_index_path_not_site_prophet`. The same module-constant trap is
documented twice in that file for `write_showcase`.

---

## 8. Not cleared by this pass

- **Overtime (Q2)** remains a separate hard production blocker.
- `gauge_absent_undisclosed` on ISRG should fall to zero once the producer change lands; if
  it persists, the gauge has a null path `engine.entry_signal.null_reason` does not mirror.
- `lane` coverage is a board-width question, not a join question.
