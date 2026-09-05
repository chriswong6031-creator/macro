# MO-DELTA-029 — Commodity Coverage Matrix (2026-09-02)

Companion to `MARKET_ONTOLOGY_F09_COMMODITY_COVERAGE_MATRIX_2026-09-02.csv`. Code-verified
only (12 `engine/commodity_*.py` modules + `engine/strategic_reserves.py`, cross-checked
against `config.yml` `commodities:` and `scripts/build_commodities.py`).

## What the matrix shows

43 rows across 5 families. All 5 families have at least one row; every module appears at
least once. The 17-member roster comes from `config.yml:4211-4238` (`assets` = core four
gold/silver/copper/oil; `complex_members` = core four + platinum/palladium/natgas/gasoline/
heating_oil/corn/wheat/soybeans/live_cattle/coffee/sugar/cocoa/cotton).

- **metals (precious: gold/silver/platinum/palladium):** price+signal+MTF+index+confluence+
  cycle (pgms) run for all four (`commodity_inputs`/`signals`/`mtf`/`index`/`confluence`/
  `cycle_state`). `conviction`/`alerts`/`news`/`strategies` are gold+silver only —
  platinum/palladium are excluded by name from `ORDER`/`LABEL`/`COMMODITY_QUERY`
  (`scripts/build_commodities.py:60-73`, `engine/commodity_alerts.py:35-36`,
  `engine/commodity_news.py:35-41`).
- **industrial (copper):** full stack — copper is in the core four, so every module that
  covers gold/silver also covers it in full (no partial cells).
- **energy (oil/natgas/gasoline/heating_oil):** price+signal+MTF+index+confluence run for
  all four; cycle state covers oil+natgas only; `conviction`/`alerts`/`news`/`strategies`
  are oil-only (core four); `commodity_carry_context.py` (WTI term structure) and
  `strategic_reserves.py` (US SPR + JODI) are oil-only context.
- **agriculture (corn/wheat/soybeans/livestock/softs):** price+signal+MTF+index+confluence
  run for all 8 members; cycle state covers corn/wheat/soybeans only (`engine/
  commodity_cycle_state.py:14` names softs/cattle as absent). NO conviction, alerts, news,
  strategies, carry, supply, or reserve module ever names an agriculture member.
- **semiconductors/critical-tech:** zero coverage. No `commodity_*.py` module or
  `config.yml commodities:` entry names any semiconductor/critical-tech material
  (checked: semiconductor, lithium, rare earth, uranium, silicon, cobalt, nickel — 0
  matches in `engine/commodity_*.py` + `engine/strategic_reserves.py`).

## Honest gaps

- **No physical supply-chain layer anywhere except oil.** `commodity_supply_context.py`'s
  EIA WPSR seasonal-anomaly read (crude/gasoline/distillate stocks vs 5y norm) is the ONLY
  module in this inventory that models a physical-balance/supply-chain layer. Metals,
  industrial (copper), agriculture, and semiconductors have `NONE` on that axis with no
  exception. `strategic_reserves.py` is government-reserve levels (SPR/JODI), not a
  modeled supply-chain layer, and is scored `NONE` per this matrix's stricter definition —
  a looser reading could count it; flagged, not resolved here.
- **`commodity_signals.py`'s own docstring says "core four," but `scripts/
  build_commodities.py:1247-1250` reuses `compute_asset()` for all 17 members** via
  `member_results` — the code footprint is broader than the module's stated scope. Treat
  the docstring as stale, not authoritative.
- **Industrial-metals coverage is copper only.** No aluminum/zinc/tin/steel/iron-ore
  futures are tracked in any `commodity_*.py` module (equity proxies for those exist
  elsewhere in the repo, e.g. `VALE` iron-ore, but that is a different engine family and
  out of scope for this matrix).
- **`commodity_mtf.py`'s applied scope is inferred from the caller** (`scripts/
  build_commodities.py:1041-1048`, "MTF ladder for all 17 members"), not from the module
  file itself, which is asset-agnostic and takes no member list.

## Acceptance-test answer

"Matrix names file+source per family" — answered: every row names its covering module file
(`covering_module`) and the code-cited data source (`data_source_cited_in_code`), grouped
by the 5 required family rows, with explicit `NO-COVERAGE` rows printed wherever a family
has no module on an axis (never silently omitted).
