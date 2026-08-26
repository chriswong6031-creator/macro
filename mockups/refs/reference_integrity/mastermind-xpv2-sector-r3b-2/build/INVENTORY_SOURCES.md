# R3B1-14 — inventory source citations

`build/inventory_check.py`'s `EXPECTED_INVENTORY` (direction 1: expected
production inventory → candidate inventory) is derived from **producer bytes
and the R3A capability contracts**, never from the candidate. This document
proves that provenance, entry by entry, and answers the question a self-
enumerating crosscheck (DAC-108) cannot: *where did the "expected" side of
this comparison come from, and could it have missed the same thing the
candidate missed?*

Every numeric value below (81%, -9.6%, +11.5%, 49, 15, 65, 113, 48) is
**re-read from the fixture JSON by `build_expected_inventory()` at every run**
— nothing here is a value typed once and left to rot. If a fixture update
changes `gross_scalar` or the theme roster, the expectation changes with it
on the next run, because the script reads the same files this document cites.

## Direction 1 entries

| id | capability | source |
|---|---|---|
| `sizing_pct` | sizing_directive | `research/reference_integrity/mastermind-xpv2-sector-r3/fixture/basketdata/baskets.json` → `theme_intel.regime_sizing.gross_scalar` (= 0.81 at freeze; script computes `round(gross_scalar*100)`). Production: `sector_central.html.j2:2886-2919 renderRegimeSizing()`. Finding: DAC-101. |
| `caveat_not_forecast` | method_caveat_clause_a | Production `sector_central.html.j2:2153`, quoted verbatim in `research/reference_integrity/mastermind-xpv2-sector-r3b/reviews/data_authority.md` DAC-102: *"Shape read only — not a forecast."* Static UI copy (not a producer number), pinned literally. |
| `caveat_construction_lag` | method_caveat_clause_b | Same production line, DAC-102: *"skips the most recent ~3 weeks by construction"*. Static UI copy, pinned literally. |
| `migration_note` | migration_note | `research/reference_integrity/mastermind-xpv2-sector-r3/fixture/basketdata/si_handoff.json` → `theme_context.migration.note_en` / `.note_zh`. Production: `sector_central.html.j2:2130`. Finding: DAC-103. |
| `allocation_href` | allocation_destination | R3A `capability_disposition_ledger.md` row #86 ("per-view working-destination inventory"), Overview / "Hero leadership context" row; `research/reference_integrity/mastermind-xpv2-sector-r3/producer_binding_matrix.md`. Production: `sector_central.html.j2:2163`. Finding: DAC-104. |
| `allocation_text` | allocation_destination | Same as `allocation_href`. |
| `hero_enrichment_outgoing` | hero_enrichment_outgoing | `basketdata/si_handoff.json` → `theme_context.leadership.trailing_leader.id` (names the theme); `basketdata/baskets.json` → `theme_intel.themes[id=<trailing_leader.id>].perf['20d'].rel` and `.perf['5d'].rel`, combined with the *same* `relTxt()`/5d-negative-only formula production uses at `sector_central.html.j2:2928-2933`. Finding: DAC-106. |
| `hero_enrichment_incoming` | hero_enrichment_incoming | `basketdata/si_handoff.json` → `theme_context.leadership.strength[0].id`; `basketdata/baskets.json` → `theme_intel.themes[id=<strength[0].id>].perf['20d'].rel` and `.pulse_rank_delta_5d`, combined with the same formula (positive-delta-only "climbing fast" clause). Production: `sector_central.html.j2:2928-2933`. Finding: DAC-106. |
| `hero_counts_themes` | hero_enrichment_counts | `basketdata/baskets.json` → top-level `baskets[]` array length (49 at freeze). Production mirrors the same `.length` call at `sector_central.html.j2:2926`. Finding: DAC-106. |
| `hero_counts_categories` | hero_enrichment_counts | `basketdata/baskets.json` → top-level `categories[]` array length (15 at freeze). Same production line. Finding: DAC-106. |
| `sp_coverage_gateable` | sp_coverage_sentence | `research/reference_integrity/mastermind-xpv2-sector-r3/fixture/marketdata/subsector_confluence.json` → `coverage.n_gateable` (65 at freeze). |
| `sp_coverage_total` | sp_coverage_sentence | Same file → `coverage.n_subsectors` (113 at freeze). |
| `sp_coverage_thin` | sp_coverage_sentence | Same file → `coverage.n_thin` (48 at freeze). |
| `sp_coverage_phrase` | sp_coverage_sentence | Static UI copy from `views/confluence.html` `paintFoot()` (R3B1-07's honest-wording repair of the DAC-105 condition) — pinned literally as the surrounding sentence structure the three numbers above sit inside, not a producer-authored string. |
| `conviction_label` | conviction_picks_label | `research/reference_integrity/mastermind-xpv2-sector-r3b-1/ORCHESTRATOR_ADJUDICATIONS_R3B1.md` R3B1-13 ruling: "Conviction" is the producer-named label for the `combined_score` column (not an invented label the candidate is free to change). Checked case-insensitively because the design system renders this header in `text-transform:uppercase`. |

## Direction 2 — allowed destination families

Sourced from `research/reference_integrity/mastermind-xpv2-sector-r3/routing_contract.md`
§7 ("Working-destination inventory per view") and
`research/reference_integrity/mastermind-xpv2-sector-r3b/capability_crosscheck.md`
row #86, plus the Money view's producer-bound external terminal URL:

| family id | pattern | source |
|---|---|---|
| `basket_family` | `^basket/` | routing_contract.md §7 — Overview/Map/Explore: `basket/<id>.html` |
| `subsector_family` | `^subsector` | routing_contract.md §7 — Confluence `detailHref()`: `subsector/`, `subsector_nasdaq/`, `subsector_russell/`, `subsector/b-*` (baskets tab prefix) |
| `stock_family` | `^stock\.html#` | routing_contract.md §7 — Confluence `stockHref(tk)`: `stock.html#<TICKER>` |
| `rotation_family` | `^rotation/` | capability_crosscheck.md row #86 — Moving view: `rotation/*` |
| `sector_cycles_family` | `^sector_cycles\.html` | capability_crosscheck.md row #86 — Map view: `sector_cycles.html`, `sector_cycles.html#*` |
| `plans_family` | `^plans\.html` | routing_contract.md §7 — Overview gated tease: `plans.html` |
| `allocation_family` | `^allocation\.html` | R3A capability ledger #86, Overview hero destination: `allocation.html` (DAC-104 restoration, R3B1-04) |
| `terminal_cross_repo_family` | `^https://app\.mastermind-x\.com/terminal\?symbol=` | `build/fixture_supplement/marketdata/sp500_heatmap.json` → `stock_url` field. `views/money.html` comment: "STOCK_URL mirrors heatmap.js:826 EXACTLY (`var STOCK_URL = data.stock_url \|\| 'stock.html#';`)" — the fixture's own `stock_url` IS this external terminal URL, not the in-page fallback; both are genuine per production's own field, and Macro Dashboard / charting-app are one connected product (CLAUDE.md). |

Every `[data-ref-nav]` href in the rendered candidate (after a full traversal
of all six views and all four Confluence universe tabs) must match one of
these eight patterns — `inventory_check.py`'s
`D2 [destination_family] every data-ref-nav href matches an allowed family`
check fails and prints every unmatched href otherwise.

## Direction 2 — allowed unresolved (recorded-not-executed) fetches

`REF.log` (the runtime shim's fetch/nav recorder, `build/runtime_shim.js`)
marks a fetch `recorded-not-executed` when the requested path has no entry
in the embedded data registry. Exactly one such path exists in the current
candidate:

| path | source |
|---|---|
| `basketdata/pulse.json` | `views/explore.html:804` — the Explore "Time Machine" mount's own fetch. This is an explicit **R3C-only condition** ("Time Machine live oracledata episode/chunk fetch", `COMMISSION.md` §"R3C-only conditions — record, do not implement") and is documented in `build/README_BUILD.md` §"Time Machine — recorded-not-executed ruling". Any OTHER unresolved fetch is unauthorized and fails `D2 [fetch_destinations]`. |

The R3A premium-data access gate (`premiumdata/sector_central.json`,
`research/reference_integrity/mastermind-xpv2-sector-r3/access_hydration_contract.md`)
is the third documented out-of-registry destination named in this wave's
commission; it is not currently exercised by this candidate's default boot
path (no anonymous-vs-authenticated toggle is driven by this harness), so it
does not appear in the allow-list above — nothing in the candidate fetches it
today. If a later wave wires the harness's auth toggle to actually issue that
fetch, add its path to `ALLOWED_UNRESOLVED_FETCHES` in `inventory_check.py`
with the same citation.

## Direction 2 — data registry (`data-path`) inventory

Every `data-path="…"` attribute in the built candidate must equal the
`path` field of an entry in `research/reference_integrity/mastermind-xpv2-sector-r3/fixture/receipts.json`
(excluding the correction-only `correction/UNREPRESENTED.md` entry, which
never gets a data block — see `verify_reference.py` check (c1)) or
`build/fixture_supplement/receipts_supplement.json` (excluding
`sector_cycles_data.js`, which embeds as a plain executed script, not a
`data-path` block — see `verify_reference.py` checks (c1c)/(c1d)). Both
receipt files are themselves sha256-pinned against the fixture bytes they
describe (`verify_reference.py` checks (b1)/(b2)), so this direction chains
back to the same producer bytes every other check in this pack chains back
to. At freeze this is exactly 22 `data-path` blocks, with zero extras and
zero omissions (`inventory_check.py`'s `D2 [data_registry]` check).
