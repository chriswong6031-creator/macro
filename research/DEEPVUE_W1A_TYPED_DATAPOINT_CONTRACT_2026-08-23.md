# Deepvue W1-A typed datapoint contract freeze

Status: implementation contract for the bounded W1-A carrier. This document does
not authorize W1-B, a query kernel, UI, a value store, or new source semantics.

## Pinned boundary

- Commission pickup observed: `fb2375441f21b94201edc4ed6ac2c40f67274cde`.
- Macro pre-modification pin after the required fast-forward: `a3b7eb6821bcaa44a8ab50bf82db391adb18c0cf`.
- Protected Sol Skillpack: `db0bac5fe3f72348262d42c8bd26b836bda9f61d`.
- Binding kill-registry fences: `DNR:KILL-LLM-ORIGINATION`,
  `DNR:KILL-FUSED-COMPOSITE`, `DNR:KILL-STAGE-WIN-GATE`,
  `DNR:KILL-PROPHET-POP-MERGE`, and `DNR:KILL-PUBLIC-INTERNALS`.
- Canonical identity remains Data OS `SEC:*`; symbols are current edge aliases only.
- W1-A is a deterministic read layer. It persists no resolved values and owns no
  source formulas, rights registry, security master, history, rank, gate, or signal.
- Returns are percentage points (`15.0` means positive fifteen percent), not
  benchmark-relative strength and not ratios.
- Resolver `generated_at` is transport time and never freshness evidence.

## Frozen manifest

| Field | Entity | Owner/source read | Unit and basis | Clocks/freshness | PIT | Rights |
|---|---|---|---|---|---|---|
| `market.price.last` | security | canonical quote resolver used by Neural Web | owner ISO quote currency; owner-native last | quote source clock and delay law | current only | subscriber allowed |
| `market.return.1m` | security | owner-published `ret_1m` from `stock_technicals` output | percent; owner current price-history basis, about 21 sessions | owner artifact clocks/health | current only | subscriber allowed |
| `market.return.3m` | security | owner-published `ret_3m` from `stock_technicals` output | percent; owner current price-history basis, about 63 sessions | owner artifact clocks/health | current only | subscriber allowed |
| `market.return.12m` | security | owner-published `ret_12m` from `stock_technicals` output | percent; owner current price-history basis, about 252 sessions | owner artifact clocks/health | current only | subscriber allowed |
| `stage.current` | security | owner-published Stage record from `stage_analysis`/`weinstein_stage` | stage code 1..4; owner classification | completed-week/owner artifact law | current only | subscriber allowed |
| `stage.weeks_in_stage` | security | same owner-published Stage record | integer weeks; owner classification | completed-week/owner artifact law | current only | subscriber allowed |
| `industry.rank.percentile` | industry | `stage_industry` industry region/comparison-set row | percentile 0..100; owner comparison set | owner build coverage/freshness | current only | subscriber allowed |
| `security.industry_member.rs_percentile` | security | `stage_industry` member-within-own-industry row | percentile 0..100; distinct from industry rank | owner build coverage/freshness | current only | subscriber allowed |
| `earnings.next_date` | security | `equity_earnings` canonical `earnings.parquet` row | ISO date, preserving date precision | row/file as-of and trading-day health | current only | subscriber allowed |
| `earnings.latest.eps_growth_pct` | security | Company Intelligence latest event `eps_growth_pct` | percent; owner event metric, never recomputed | owner context/event clocks and health | current only | subscriber allowed |
| `earnings.latest.revenue_growth_pct` | security | Company Intelligence latest event `revenue_growth_pct` | percent; owner event metric, never recomputed | owner context/event clocks and health | current only | subscriber allowed |
| `theme.local.memberships` | security | Theme Graph direct current `company/security -> local_theme MEMBER_OF` view | sorted local-theme refs; no canonical-theme composition | owner edge/build metadata | current only | dynamic owner rights |

All `owner_ref.dataset_id` values are null unless an exact row exists in the Data
OS dataset registry. The current materialized owner outputs above are not Data OS
dataset IDs, so W1-A does not mint aliases for them. Technical-return provenance
may cite `equity.bars.daily.stocks` only as an underlying owner basis when the
adapter can prove that lineage; it is not the materialized return dataset.

Although Theme Graph edges have bitemporal storage, the required security-to-graph
identity bridge is current-only. Therefore the combined SEC-addressed field is
honestly `current_only`; W1-A cannot use a current identity bridge to assert an old
membership fact.

Company Intelligence `field_lineage.metrics.<field>` is preserved as
`earnings_history` or `score_overlay`. Neither semantic field claims “reported,” and
the resolver never upgrades `score_overlay` to release-native evidence.

## Exact owner reads pinned by archaeology

- Quote reads the neutral helper extracted from the existing Neural Web quote
  waterfall; the helper preserves the current live-hub, current snapshot and
  degraded-source ordering rather than introducing a W1-A quote formula or vendor
  call.
- Technical returns read owner-published `ret_1m`, `ret_3m`, and `ret_12m` from
  `site/stockdata/{safe}.json`, carrying the record `asof` and `feed_stale` state.
  Their governed basis is Data OS `equity.bars.daily.stocks` `total_return` /
  `tradj`; W1-A does not claim an adjustment vintage that the owner does not carry.
- Stage reads live rows from `data/stage_analysis/screener.json`, including the
  owner-published Stage and weeks-in-stage classification.
- Industry rank reads region/industry-ID rows from
  `data/stage_analysis/industry_ranks.json`. Member percentile reads ticker rows
  from `data/stage_analysis/industry_name_pctile.json`; the two percentile fields
  are not interchangeable.
- Next earnings date reads the current row from
  `data/earnings/earnings.parquet`, preserves its row `as_of`, and uses the
  earnings owner's `assess_staleness` result rather than resolver age arithmetic.
- Latest earnings growth calls
  `company_intelligence_reader.read_company_intelligence`, selects the latest
  canonical event, and preserves its per-field `field_lineage` as either
  `earnings_history` or `score_overlay`.
- Theme membership reads the Theme store identity sidecar's exact `SEC:*`
  zero-to-many mapping, then only current direct `MEMBER_OF` edges whose target is
  a local theme. Subscriber projection calls
  `rights.assert_public_emission_allowed` dynamically. No canonical-theme
  composition, ThemeState, or ticker-equality fallback is permitted.

Every combined SEC-addressed field above is `current_only`. A current symbol may
normalize to a canonical `SEC:*` under a historical request, but the interpretation
remains `current_alias_only`; the cell then returns `history_not_supported` without
owner I/O and never claims that the symbol was historically valid.

## Envelope and failure law

The catalog is immutable in process and has a canonical SHA-256 digest. Every value
uses `datapoint_value.v1`, canonical identity, closed status/reason/use vocabularies,
owner clocks, owner-native freshness/quality, source/provenance, audience, and a
semantic fingerprint. Scalar availability requires a finite non-null typed value;
typed absence has null. Zero is valid. An empty local-theme set is available.

The complete request is checked before owner adapter I/O: fields, duplicates, edge
shape, type/universe/use compatibility, audience, RFC3339 cutoff, 12-field limit,
250-entity limit, 2,000-cell limit, and governed request cost. Identity normalization
then produces stable entities without silent supersession. A past cutoff on every
frozen current-only field returns `history_not_supported` without reading or
retro-stamping today's owner fact.

Internal truth is resolved before subscriber projection. Subscriber output may strip
private provenance, narrow uses, or become typed `rights_blocked`; it may never change
an available number/date, advance clocks, improve health, or expose a restricted theme
structure. Dynamic theme rights are decided by the owner at projection time.

## Explicit non-capabilities

This contract does not build W1-B or W1-C, `ai_context_envelope.v1`, a full screener,
natural-language routing, saved screens, rules/alerts, ratings, ThemeState, workspace
UI, Terminal work, Market OS B1, Neural Web promotion, Prophet/Fusion input, public
API, value persistence, or any independent trading authority.
