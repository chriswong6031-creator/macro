# F01 — FX & Commodity Source Rights + Depth Parity (2026-09)

Scope: MO-PAID-003 (FX monitoring), MO-PAID-004 (Commodities monitoring) rights half.
Authority ceiling: context_only. This document records; it changes no surface and no code.
Verified in: /Users/chriswong/Documents/Cluade/macro-main @ 16b3734c9d87, 2026-09-05.
Checkout state: SPARSE in the builder's own worktree (`python3 scripts/worktree_sparse.py status`); `data/` was not inspected. Every finding in this document is sourced from `engine/`, `scripts/`, `templates/`, `docs/`, and `agentos/` file:line citations that ARE tracked in a sparse checkout, plus the verified-substrate grep results already recorded (2026-09-05) in the frozen packet spec for this document. No claim here required reading `data/` bytes directly, so none is marked UNVERIFIED on that ground — but a builder resuming this document with `data/` access should re-run the negative-search greps in §4 independently rather than trusting this restatement alone.

## 0. Null taxonomy used in this document

| state | means | must NOT be written as |
|---|---|---|
| `unknown` | we have not established it either way | "none", "no restriction", "clear" |
| `not_yet_available` | the thing is expected to exist later; it does not exist now | "unknown", "zero" |
| `stale` | a real value exists but is older than its freshness contract | "missing" |
| `source_failed` | the fetch was attempted and errored | "not_yet_available" |
| `rights_blocked` | terms forbid the storage/use we would need | "unknown" |
| `measured-zero` | we measured, and the honest answer is zero | any of the above |

## 1. Headline verdict

The FX price spine (`forex.html`) and the commodity price spine (`commodities.html`, `commodity_strategies.html`) both enter through the same `store.read("yahoo", …)` path (`engine/forex_inputs.py:66-67,157`; `engine/commodity_inputs.py:49-53`), fed by the `collectors.intl_prices.IntlPriceAdapter` registered at `scripts/collect.py:298`. The repository holds **no rights ruling** for that vendor: `docs/QUAL_DATA_COMPLIANCE.md` contains no Yahoo/yfinance clause, and neither `agentos/decisions/` nor `agentos/discoveries/` carries a matching `DEC-*`/`DSC-*` record. This is stated as **UNVERIFIED / rights-posture-unrecorded** — we have not established permission either way. The sentence "no restriction was found" is banned; the correct statement is that the posture has never been recorded.

## 2. Source inventory — FX (forex.html)

| series family | store group | collector / adapter (file:line) | consumer (file:line) | rights state | what would verify |
|---|---|---|---|---|---|
| FX spot & DXY (`DX-Y.NYB`, pair closes) | `yahoo` | `collectors.intl_prices.IntlPriceAdapter` — `scripts/collect.py:298` ("yfinance indices + vol + FX") | `engine/forex_inputs.py:66-67`, `:157`; rendered `templates/forex.html.j2:301` | `unknown (rights-posture-unrecorded)` | a written Yahoo/yfinance ToS reading + a `DEC-*` ruling, or migration to a licensed FX vendor |
| policy/short rates | `fred` group `fx_rates_short` | `collectors.fred.FredAdapter` — `scripts/collect.py:150` | `engine/forex_inputs.py:45`, `:139` | VERIFIED permissive — FRED-published series, public-domain transport, same posture as R-1/R-2 of the 2026-09-04 census | contradicting FRED terms or a source-agency restriction on a specific series id |
| long rates | `fred` group `fx_rates_long` | same | `engine/forex_inputs.py:147` | VERIFIED permissive (same basis) | same |
| REER | `fred` group `fx_reer` | same | `engine/forex_inputs.py:148` | VERIFIED permissive (same basis) with sub-flag `unknown (attribution terms unread)` — BIS-origin REER republished via FRED; attribution obligation not read | reading the BIS REER terms and the FRED series notes |
| FX positioning | `cot` | CFTC Commitments of Traders | `engine/forex_inputs.py:89` | VERIFIED permissive — US federal government publication | a CFTC redistribution notice |

## 3. Source inventory — Commodities (commodities.html / commodity_strategies.html / spr.html)

| series family | store group | consumer (file:line) | rights state | what would verify |
|---|---|---|---|---|
| commodity futures/spot closes | `yahoo` | `engine/commodity_inputs.py:49-53` (`load_price`) → `scripts/build_commodities.py:1199` | `unknown (rights-posture-unrecorded)` — same vendor as FX spot | as FX spot above |
| macro drivers (real yield, us10y/us2y, breakevens) | per `config` `commodities.drivers` `(group, series)` | `engine/commodity_inputs.py:27,38` | VERIFIED permissive where the configured group resolves to `fred`; `unknown` for any driver whose configured group is not `fred` — each configured driver group must be resolved and typed individually, never blanket-cleared. This document was not able to enumerate the live `config` driver list from this sparse checkout (config resolution was not part of the file:line trace performed), so this row is left as a conditional rule rather than a per-driver table; a follow-on pass should read `config` and expand this row into one line per driver group. | reading `config` `commodities.drivers` and naming each group |
| commodity positioning | `cot` | `engine/commodity_inputs.py:66` | VERIFIED permissive (CFTC) | a CFTC redistribution notice |
| US SPR weekly stocks | `data/eia/spr_stocks` | `engine/strategic_reserves.py:6`, `:19`; rendered via `scripts/build_spr.py:35,261` | VERIFIED permissive — EIA is a US federal statistical agency, public domain | an EIA API terms clause restricting derived redistribution |

Every `VERIFIED` cell above names the file/line or the agency that proves it. Every `unknown` cell names what would verify it. No cell is blank and no cell reads "no restriction found".

### 3.1 Commodities producer chain (MO-PAID-004 deliverable)

| Page | Renderer (file:line) | Engine modules bound (file:line of the import) |
|---|---|---|
| `commodities.html` | `scripts/build_commodities.py:1391` `env.get_template("commodities.html.j2").render(` | `engine.commodity_supply_context` (`:351`), `engine.commodity_carry_context` (`:427`), `engine.commodity_mtf` (`:497`, again `:1043` as `_cmtf`), `engine.commodity_signals` (`:536`, `:1199`), `engine.commodity_inputs` (`:1199`), `engine.commodity_conviction` (`:1199`), `engine.commodity_alerts` (`:1200`), `engine.commodity_news` (`:1315`), `engine.i18n` (`:1354`); store access via `lib.store` (`:30`, `:350`) |
| `commodity_strategies.html` | `scripts/build_commodity_strategies.py:111` `env.get_template("commodity_strategies.html.j2").render(groups=groups, built=built, C=C)` | `engine.active_commodity as Ach` (`:30`), `engine.commodity_strategies as S` (`:31`), plus script-level reuse `scripts._active_render as AR` (`:34`), `scripts.build_strategies._card/_detail_vm/_evaluate` (`:35`), `scripts.build_vector.C` (`:36`) — this page's card semantics are owned by the shared strategies renderer, not by a commodity-only engine module |
| `spr.html` | `scripts/build_spr.py:261` `env.get_template("spr.html.j2").render(` | `engine.strategic_reserves as sr` (`:35`), `engine.i18n` (`:256`); `lib.store` (`:33`) |
| (comparator) `forex.html` | `scripts/build_forex.py:1175` | `engine.forex_conviction` (`:391`), `engine.forex_mtf` (`:404`), `engine.forex_inputs/forex_signals/forex_conviction` (`:904`), `engine.forex_dollar/forex_transmission/forex_scorecards` (`:931`), `engine.forex_regime` (`:987`), `engine.forex_alerts` (`:1088`), `engine.ledger_lane.nightly_advance_enabled` (`:730,830`), `engine.i18n` (`:1172`) |

This table closes MO-PAID-004's `missing_contract` ("engine-module-to-template binding trace") by naming the exact producing engine module chain per page; `correction_behavior` was literally `UNVERIFIED (producer untraced)` and the trace above is that deliverable.

## 4. Rights findings (one entry per vendor)

- **V-1 (Yahoo Finance via the `yahoo` store — the price spine for BOTH FX and commodities).** Posture: `unknown (rights-posture-unrecorded)`, escalating to a flagged commercial-use question. Basis: `engine/forex_inputs.py:66-67,157` and `engine/commodity_inputs.py:49-53` both read `store.read("yahoo", …)`; the collector is registered at `scripts/collect.py:298`; `docs/QUAL_DATA_COMPLIANCE.md` contains no Yahoo/yfinance clause and no `DEC-*`/`DSC-*` record covers the vendor (searched `agentos/decisions/`, `agentos/discoveries/`, `docs/`, 2026-09-05). Risk: a paid SaaS surface is priced on a feed whose terms were never read into the repo — this is an unrecorded posture, explicitly not a finding of "no restriction". Escalation trigger: any Yahoo/Verizon-Media takedown or license contact → pull the affected surfaces same-day; any move to charge specifically for FX/commodity price display → the ruling must precede the price change. Verification path: a written ToS reading recorded as `DEC-YAHOO-PRICE-SPINE-RIGHTS`, or migration of the spot leg to a licensed vendor.
- **V-2 (FRED-published rate/REER series).** Posture: VERIFIED permissive under the same basis the 2026-09-04 census used for R-1/R-2 (derived/aggregate display with attribution, no bulk redistribution). Basis: `engine/forex_inputs.py:45,139,147,148`; census precedent at `research/market_intelligence_productization/MARKET_ONTOLOGY_F01_R5R6_SOURCE_CENSUS_AND_RIGHTS_RULINGS_2026-09-04.md:113-140`. Sub-flag: the REER leg carries a BIS-origin attribution obligation that has not been read — typed `unknown (attribution terms unread)`, not permissive.
- **V-3 (CFTC COT).** Posture: VERIFIED permissive — US federal publication. Basis: `engine/forex_inputs.py:89`, `engine/commodity_inputs.py:66`.
- **V-4 (EIA SPR weekly).** Posture: VERIFIED permissive — US federal statistical agency, public domain. Basis: `engine/strategic_reserves.py:6,19`. Note the surface already self-labels as context-not-advice (`engine/strategic_reserves.py:35,40`).

## 5. Depth parity vs the MO row

The MO row for MO-PAID-003 advertises three words — `FX monitoring` (`MARKET_ONTOLOGY_COMPLETE_PARITY_ADOPTION_LEDGER_2026-08-26.csv:4`) — so it specifies no depth. Parity is therefore graded against the label plus the F00E current-public census, and every dimension the row leaves unspecified is typed `unknown (comparator undefined)`, never `parity`.

| dimension | our depth (file:line) | MO row | verdict |
|---|---|---|---|
| pair coverage | driven by `config` FX pair meta (`engine/forex_inputs.py:66` `meta["yahoo"]` per pair); the exact resolved pair count was not enumerated in this pass (would require reading the live `config`, not performed) | unspecified | `unknown (comparator undefined)` |
| dollar regime read | `templates/forex.html.j2:299-303` hero KPI row (Broad USD, DXY, 63d move, risk mood) | unspecified | `unknown (comparator undefined)` |
| carry | `templates/forex.html.j2:728-740` carry chip, `carry_diff` + `carry_to_vol`, with a `carry_context` suppression branch | unspecified | `unknown (comparator undefined)` |
| valuation | `templates/forex.html.j2:744-746` REER-gap value chip (`value-cheap`/`value-fair`/`value-rich` at ±5) | unspecified | `unknown (comparator undefined)` |
| joint-configuration / scenario read | `engine/forex_regime.py:681 fx_stress_regime`, `:774 fx_kinematics_table`, `:603 scenario_probability` — six named scenarios with Wilson-interval past-tense base rates and `n_eff` | unspecified | our depth exceeds any three-word label; still typed `unknown (comparator undefined)` for parity purposes, and the excess is reported as capability, not as a win |
| intraday / tick depth | none — nightly-rendered (`.github/workflows/render.yml:543`) | unspecified | `not_yet_available` (our side), comparator `unknown` |

The correct MO-PAID-003 disposition after this document is `UPGRADE_EXISTING_OWNER` with the rights half now RECORDED-as-unknown and the depth half graded. A genuine parity number cannot be produced until the MO row is decomposed into depth dimensions by F00E — that dependency is a GAP, printed, not fabricated.

## 6. What this document does NOT establish

It does not establish that Yahoo/yfinance use is lawful or unlawful — only that the question has never been answered in this repository. It does not establish a numeric parity score against the MO ledger (§5's comparator dimensions are `unknown`, not scored). It does not enumerate the live `config` FX pair list or the full `commodities.drivers` group table — both are named as follow-on work in §2/§3. It does not touch, render, or change any of the four live pages it describes. It does not authorize any build, gauge, or code change.

## 7. Ledger closure statement

MO-PAID-003: rights recorded (Yahoo spine typed `unknown (rights-posture-unrecorded)`), depth parity written, comparator undefined on 6/6 dimensions — acceptance_test ("vendor rights recorded and depth-parity assessment written") satisfied by §4 V-1/V-2/V-3/V-4 and §5.
MO-PAID-004: producer chain named per page, 3/3 pages (§3.1) — acceptance_test ("the producing engine module chain is named per page") satisfied; rights half shares V-1/V-3/V-4 above.
No LLM-originated signal, score, or rank is introduced by this document. Authority ceiling `context_only` is not exceeded — no surface or code was changed.
