---
key: COMMODITY-AND-FX-PRICE-SPINE-IS-AN-UNRULED-YAHOO-STORE
claim: >-
  Both the FX and the commodity price spines read the same `yahoo` store group, and
  the repository holds no rights ruling for that vendor anywhere in docs/, agentos/decisions/,
  or agentos/discoveries/ — the posture is unrecorded, not cleared.
falsifier: >-
  grep -rn "Yahoo\|yfinance" docs/QUAL_DATA_COMPLIANCE.md agentos/decisions/ agentos/discoveries/
  returns a rights ruling; or engine/forex_inputs.py:66 and engine/commodity_inputs.py:49
  no longer read store.read("yahoo", ...).
so_what: >-
  A future session must not treat FX or commodity prices as rights-cleared merely because
  they are on disk; any packet that widens, monetizes, redistributes, or exports those series
  needs a vendor ruling first, and any rights table that lists them must type them `unknown`,
  never "no restriction".
kind: constraint
verified_at: 2026-09-05
verified_by: >-
  engine/forex_inputs.py:66-67,157; engine/commodity_inputs.py:49-53; scripts/collect.py:298;
  absence confirmed by grep over docs/QUAL_DATA_COMPLIANCE.md, agentos/decisions/, agentos/discoveries/
  (2026-09-05: matches found reference Yahoo/yfinance as a data mechanism — auto_adjust behavior,
  vendor constants, fiscal-anchor payload shape, delisting probes — none is a rights/ToS ruling)
scope: [macro, F01-MACRO-MARKETS, engine/forex_inputs.py, engine/commodity_inputs.py, scripts/collect.py]
confidence: verified
---

# Commodity and FX price spine is an unruled Yahoo store

`engine/forex_inputs.py:66-67` (`ticker = meta["yahoo"]`; `df = store.read("yahoo", ticker)`) and
`engine/commodity_inputs.py:49-53` (`load_price(ticker)` → `store.read("yahoo", ticker)`) both bind
their price series through the same `yahoo` store group. That group is fed by
`collectors.intl_prices.IntlPriceAdapter`, registered at `scripts/collect.py:298` ("yfinance
indices + vol + FX").

| surface | consumer (file:line) | vendor path |
|---|---|---|
| FX spot / DXY | `engine/forex_inputs.py:66-67,157` → `templates/forex.html.j2:301` | `store.read("yahoo", …)` |
| commodity futures/spot | `engine/commodity_inputs.py:49-53` → `scripts/build_commodities.py:1199` | `store.read("yahoo", …)` |

A repo-wide grep for a rights ruling covering that vendor — `docs/QUAL_DATA_COMPLIANCE.md`,
`agentos/decisions/`, `agentos/discoveries/` — returns matches that are all about Yahoo/yfinance
as a *data mechanism* (auto_adjust non-determinism, vendor constant naming, fiscal-anchor payload
shape, delisting-probe behavior). None is a rights, ToS, or licensing ruling. There is no
`DEC-*`/`DSC-*` record answering whether commercial redistribution or paid-surface display of
this vendor's data is permitted.

This is a durable, non-obvious fact: two paid-surface families (FX monitoring, commodity
monitoring) both sit on an unrecorded vendor-rights posture, and neither the engine code nor any
existing record makes that visible without tracing both consumers back to the same store group.
Any future packet that widens exposure of these series (new export, new paid tier, bulk API,
redistribution) must treat the posture as `unknown (rights-posture-unrecorded)`, not as cleared,
and should read
`research/market_intelligence_productization/F01_FX_COMMODITY_SOURCE_RIGHTS_AND_DEPTH_2026-09.md`
§4 V-1 before proceeding.
