# XPV2-SC-R3A fixture — PROVENANCE

Deliverable 3 provenance record. Every producer-derived file under `fixture/`
is a byte-for-byte copy of a production artifact under `site/` at the
capture commit below — no recompute, no reordering, no reformatting.
`fixture/receipts.json` carries ONE SHA-256 per entry, computed from the
`fixture/…` file; the copy was verified byte-identical to its `site/…`
source at capture time, so that single hash covers both by construction —
there are not two separate hashes to compare. Recomputation at test time
(`tests/test_xpv2_sector_r3_fixture.py`) must match the stored hash. One
entry, `correction/UNREPRESENTED.md`, is an authored doc rather than a
`site/` copy (see §"What is NOT in this fixture set" below) — its receipt
still carries a hash, just no `site/` source.

- **Capture commit**: `4c55fe433490adfd75fd901ef25f5793db2202db` (`git rev-parse HEAD`, this worktree, at capture time)
- **Capture date**: 2026-08-20
- **Total fixture size**: 4,335,880 bytes (≈4.13 MiB) — well under the 50MB size guard; no truncation was needed. (17 producer-copied JSON artifacts + 1 authored correction doc.)

## Source → fixture → producer map

| fixture path | source path | producer script | producer function / module | dossier cite |
|---|---|---|---|---|
| `sectordata/sector_central.json` | `site/sectordata/sector_central.json` | `scripts/build_sector_central.py` | `engine/sector_central.py::compute()`, written `:356-361` | lane A §6, lane C §1 row 4 |
| `premiumdata/sector_central.json` | `site/premiumdata/sector_central.json` | `scripts/build_sector_central.py` | `write_payload()` (`:136-167`), tier_payload.v1 shape | lane A §8 |
| `basketdata/action_board.json` | `site/basketdata/action_board.json` | `scripts/build_site.py` | `action_board()` (signature `:1990`, called `:6154`) | lane A §4-5 |
| `basketdata/baskets.json` | `site/basketdata/baskets.json` | `scripts/build_baskets.py` | writes `theme_intel.{themes,act_now,market_concentration}` (`:413`) | lane C §4, lane D §2 |
| `basketdata/narrative_emergence.json` | `site/basketdata/narrative_emergence.json` | `scripts/build_baskets.py` pipeline | `engine/narrative_emergence.py::compute_emergence()` | lane D §5 |
| `marketdata/subsector_confluence.json` | `site/marketdata/subsector_confluence.json` | `scripts/build_subsector_confluence.py::main()` | `engine/subsector_confluence.py::compute_subsector_confluence()` (`:364`) | lane E §1, row 1 |
| `marketdata/subsector_confluence_nasdaq.json` | `site/marketdata/subsector_confluence_nasdaq.json` | `scripts/build_subsector_confluence.py::main_index("nasdaq")` (`:377`) | `engine/subsector_confluence.py::compute_nasdaq_confluence()` → `_compute_index_desk("nasdaq","QQQ",…)` (`:618,590`) | lane E §1, row 1 |
| `marketdata/subsector_confluence_russell.json` | `site/marketdata/subsector_confluence_russell.json` | `scripts/build_subsector_confluence.py::main_index("russell")` | `engine/subsector_confluence.py::compute_russell_confluence()` (`:623`) | lane E §1, row 1 |
| `correction/UNREPRESENTED.md` | *(none — authored doc, not a `site/` copy)* | n/a | n/a — records that correction/revision has NO production representation on either surface (State 8) | lane F §State 8, ADJUDICATIONS.md §A6 |
| `marketdata/basket_confluence.json` | `site/marketdata/basket_confluence.json` | `scripts/build_subsector_confluence.py::main()` | `engine/subsector_confluence.py::compute_basket_confluence()` (`:428`), over `data/baskets/membership.json` | lane E §1, row 1 |
| `marketdata/rotation_events.json` | `site/marketdata/rotation_events.json` | `scripts/build_rotation_events.py` (`:130,173`) | `engine.rotation_events` | lane C §2 row 2, §4 |
| `marketdata/sector_fragmentation.json` | `site/marketdata/sector_fragmentation.json` | `scripts/build_rotation_events.py` (`:130,173`) | `engine.sector_fragmentation` | lane C §2 row 2, §4 |
| `marketdata/subsector_rotation.json` | `site/marketdata/subsector_rotation.json` | `scripts/build_subsector_rotation.py` (`:335-336`) | `engine.subsector_rotation` (`:20`), over committed Finviz snapshot | lane C §2 row 3, §4 |
| `basketdata/oracle_turn_desk.json` | `site/basketdata/oracle_turn_desk.json` | `scripts/oracle_nightly.py` step 15 (`:1313,1533`) | Rotation Turn Desk, W6, display-only | lane C §2 row 4, §4 |
| `basketdata/oracle_tape_onset.json` | `site/basketdata/oracle_tape_onset.json` | `scripts/oracle_nightly.py` step 19 (`:1589`) | TAPE-ONSET, FTR W7, display-only unconfirmed flag | lane C §2 row 4, §4 |
| `marketdata/index_leadership.json` | `site/marketdata/index_leadership.json` | `scripts/build_index_leadership.py` (writer citation only — GAP, not opened by any lane) | not confirmed | lane C §4 (GAP #3), lane D §6(b) |
| `basketdata/si_handoff.json` | `site/basketdata/si_handoff.json` | `scripts/build_baskets.py:590-597` | assembles `theme_context`/`factor_season`/`flow`/`basket_member_syms`/`generated_utc`, no independent compute | lane A §11, lane C §2a |
| `oracledata/tm_manifest.json` | `site/oracledata/tm_manifest.json` | `scripts/build_oracle_timemachine.py` ("Oracle P6 — Time Machine feed exporter") | `engine/oracle/timemachine.py`, reads Oracle parquet panels; runs OFF the 67-minute render path | lane D §4 |

## Locating rules applied (per the commission)

- **`basketdata/action_board.json`** — the commission asked to "confirm actual
  path via lane A dossier." Lane A §4 confirms the artifact is
  `site/basketdata/action_board.json` (`{"action_board": {...}}` top-level
  shape, written by `scripts/build_site.py::action_board()` and read
  fail-soft by `scripts/build_sector_central.py:432-439`). No `basketdata/`
  variant with a different name exists.
- **`basketdata/si_handoff.json`** — the commission asked to locate it "via
  lane C cites: written by `scripts/build_baskets.py:590-597`." Lane C §2a
  confirms the single writer at those exact lines and the single reader at
  `scripts/build_sector_central.py:379-384`; the file lands at
  `site/basketdata/si_handoff.json` (confirmed present, 19,095 bytes at
  capture).

## What is NOT in this fixture set (explicit, per SCOPE)

The commission's copy list is Overview/Map/Moving/Money/Explore/Confluence
producer artifacts. It does not include `site/allocationdata/allocation.json`
(ranks/weights enrichment for theme rows, lane A §5), `site/marketdata/sp500_heatmap.json`
(Money heat treemap, lane C §3), `basketdata/etf_pulse.json` /
`basketdata/vol_sentiment.json` (Money-flow chips, lane C §3), or
`oracledata/tm_episodes.json` / the per-year Time Machine chunk files (lane D
§4) — these are referenced in the binding matrix and design brief as GAP or
adjacent-producer rows but were not in the commission's explicit fixture
list, so they were not captured. A future wave that needs mutation coverage
on those fields must extend this fixture set with a new capture, not infer
from the files here.
