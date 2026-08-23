# Deepvue W1-A typed datapoint validation receipt

Status: pre-PR implementation receipt for the bounded W1-A carrier. This receipt is
evidence, not authorization for W1-B or any adjacent product surface.

## Identity and source pins

- Commission pickup observed: `fb2375441f21b94201edc4ed6ac2c40f67274cde`.
- Macro pre-modification pin: `a3b7eb6821bcaa44a8ab50bf82db391adb18c0cf`.
- Protected Sol Skillpack `origin/master`: `db0bac5fe3f72348262d42c8bd26b836bda9f61d`.
- Registry schema/version: `datapoint_registry.v1` / `1.0.0`.
- Frozen semantic registry digest:
  `7dff09b790f9f789dfeed80781a7fb62bc138ad4bf801d81664d471c4508d4cf`.
- Value envelope schema: `datapoint_value.v1`.
- Branch: `claude/deepvue-w1a-datapoint-resolver`.

Current Macro `origin/main`, the exact-head PR map, final head, PR, checks, merge,
deployment, and live-machine proof are volatile delivery receipts and must be added
to the PR/final return after they exist. They are not inferred here.

## Frozen field and owner matrix

| Field | Exact owner read | Unit/basis | PIT | Subscriber policy |
|---|---|---|---|---|
| `market.price.last` | neutral extraction of the current Neural Web quote waterfall | owner ISO currency; owner-native last | current only | allowed |
| `market.return.1m` | `stock_technicals` published `ret_1m` | percent points; about 21 sessions | current only | allowed |
| `market.return.3m` | `stock_technicals` published `ret_3m` | percent points; about 63 sessions | current only | allowed |
| `market.return.12m` | `stock_technicals` published `ret_12m` | percent points; about 252 sessions | current only | allowed |
| `stage.current` | `stage_analysis`/`weinstein_stage` published classification | integer enum 1..4 | current only | allowed |
| `stage.weeks_in_stage` | same Stage record | integer weeks | current only | allowed |
| `industry.rank.percentile` | `stage_industry` `industry_ranks` USA/industry row | percentile 0..100; industry comparison set | current only | allowed |
| `security.industry_member.rs_percentile` | `stage_industry` `industry_name_pctile` ticker row | percentile 0..100; member within own industry | current only | allowed |
| `earnings.next_date` | `equity_earnings` canonical row | ISO date, date precision | current only | allowed |
| `earnings.latest.eps_growth_pct` | Company Intelligence latest event `eps_growth_pct` | percent points; exact owner event lineage | current only | allowed |
| `earnings.latest.revenue_growth_pct` | Company Intelligence latest event `revenue_growth_pct` | percent points; exact owner event lineage | current only | allowed |
| `theme.local.memberships` | Theme Graph current direct security/company `MEMBER_OF` local-theme edges | sorted entity-ref set; no canonical-theme composition | current only | dynamic owner rights |

All current-only fields return typed `history_not_supported` without owner adapter
reads for a past cutoff. Symbols normalize through the current Data OS `store` alias
edge into a stable `SEC:*` identity; the envelope never represents that current alias
as historical naming evidence. An explicit superseded security fails closed rather
than redirecting silently.

## Capability proof

- `DatapointResolver` validates the complete request, cost and cell limits before
  identity or owner I/O, batches adapters by owner, validates every owner result and
  value envelope, then applies audience projection.
- `scripts/resolve_datapoints.py` is a read-only, canonical-JSON machine consumer
  with no import, path, formula, persistence, retry or vendor-fetch escape hatch.
- The query fixture consumes `stage.current` and `market.return.3m` as registered
  percent points. It does not create a generalized query kernel.
- The Brain fixture passes the same resolved fact packet through the existing
  model-visible-result boundary. It does not add routing or promote observations.
- Direct, query and Brain fixtures retain the same fact fingerprint; duplicate
  facts are rejected.
- The only existing-file behavior change extracts the exact four-step quote
  waterfall into a neutral helper and makes Brain delegate to it mechanically.

## State and negative proof

The focused suite covers available, unavailable/missing, stale, not-applicable,
rights-blocked and historical-cutoff behavior across the frozen manifest. On the
current production-shaped repository data:

- `AAPL` normalizes to `SEC:US-XNAS-AAPL`.
- Stage is available as Stage 2, 46 weeks, owner as-of `2026-08-23`.
- security-within-industry percentile is available as `40.0`.
- Company Intelligence EPS and revenue growth are available as `29.0` and `16.0`
  with their exact per-field lineage and owner event clock.
- current direct local-theme membership resolves internally to 22 source-native
  local-theme references.
- `Software` resolves as the exact industry entity with industry percentile `95.9`.
- locally absent quote/technical artifacts and stale earnings-calendar state remain
  typed absence; the resolver does not invent numbers or freshness.

Exact negative commands and results:

```text
python3 scripts/resolve_datapoints.py --symbol DEFINITELY_NOT_A_REAL_SYMBOL_8F4A \
  --field market.price.last --audience internal --consumer-use query
=> exit 2; RequestValidationError; unknown current Data OS store alias

python3 scripts/resolve_datapoints.py --symbol AAPL --field market.price.last \
  --audience internal --consumer-use query \
  --requested-as-of 2025-01-02T00:00:00Z
=> exit 0; unavailable/history_not_supported; value null; owner disposition only

python3 scripts/resolve_datapoints.py --symbol AAPL \
  --field theme.local.memberships --audience subscriber --consumer-use query
=> exit 0; rights_blocked; value null; no internal artifact path or relation payload
```

## Mandatory mutation proof

Every test applies a test-local mutant, asserts that the intended contract invariant
fails, and exits through pytest teardown with production code unchanged.

| Mutation | Discriminating test | Intended failure |
|---|---|---|
| M1 industry swap | `test_m01_industry_rank_member_swap_is_killed` | member RS `19` cannot replace owner industry rank `72` |
| M2 generated-at freshness | `test_m02_generated_at_freshness_laundering_is_killed` | resolver time cannot turn stale owner health fresh |
| M3 percent/ratio drift | `test_m03_percent_ratio_drift_is_killed` | `0.15` cannot satisfy the `15.0` percent-point query fixture |
| M4 null to zero | `test_m04_null_to_zero_is_killed` | unavailable numeric envelopes must carry null |
| M5 Stage 0 laundering | `test_m05_stage_zero_laundering_is_killed` | available Stage value violates the registry minimum |
| M6 current identity as history | `test_m06_current_identity_as_historical_truth_is_killed` | historical current-only request must not perform owner I/O or expose a value |
| M7 rights leak | `test_m07_subscriber_rights_leak_is_killed` | subscriber projection cannot expose blocked relation or private path |
| M8 owner bypass | `test_m08_technical_owner_bypass_recomputation_is_killed` | owner-published return `15` wins over disagreeing local recomputation |
| M9 clock replacement | `test_m09_owner_clock_replaced_by_generation_clock_is_killed` | owner event clock cannot be replaced by resolver generation time |
| M10 batch-limit removal | `test_m10_cell_and_cost_limit_removal_is_killed` | oversized request must fail before identity or owner I/O |
| M11 semantic-ID mutation | `test_m11_semantic_id_type_unit_basis_mutation_is_killed` | type/unit/basis drift changes the frozen semantic manifest |
| M12 subscriber transform | `test_m12_subscriber_numeric_transform_is_killed` | subscriber available number must equal internal truth exactly |
| M13 theme composition | `test_m13_local_theme_to_canonical_composition_is_killed` | non-local/canonical theme targets violate the direct-edge field contract |
| M14 growth-lineage laundering | `test_m14_score_overlay_lineage_laundering_is_killed` | `score_overlay` cannot claim `earnings_history` provenance |

Receipt command:

```text
python3 -m pytest -q tests/test_intelligence_workspace_mutations.py
=> 14 passed
```

## Performance receipt

Measured by `tests/test_intelligence_workspace_performance.py` with the real
resolver, identity implementation and all seven adapters over deterministic owner
fixtures; no network and no mock resolver. Times are one local run and are evidence
of the access pattern, not a service-level guarantee.

| Case | Wall | CPU | Cells | Canonical JSON bytes |
|---|---:|---:|---:|---:|
| registry cold | 10.074 ms | 9.714 ms | n/a | n/a |
| registry cached | 0.052 ms | 0.054 ms | n/a | n/a |
| one field x one security | 46.730 ms | 47.627 ms | 1 | 979 |
| eleven security fields x one security | 10.264 ms | 11.910 ms | 11 | 12,287 |
| one industry field x one industry | 0.549 ms | 0.551 ms | 1 | 1,222 |
| exact 12-field manifest as applicable | 10.814 ms | 12.461 ms | 12 | 13,509 |
| twenty securities x four fields | 30.387 ms | 31.977 ms | 80 | 83,011 |

The representative 20-security batch performs one quote batch for 20 symbols, one
security-master read, one alias-table read, and one technical owner-record read per
entity—not per field. The 11-field security batch reads Stage, member-percentile and
earnings artifacts once, one Company Intelligence event, and one Theme identity/
edge/meta view. Registry and envelope schemas are cached immutably; resolved values
are never cached or persisted. Partitioned and one-shot resolution are semantically
equivalent.

Governed request limits are 12 fields, 250 entities, 2,000 cells and request cost
8,000. No concurrency, retry plane or persistent cache was added.

## Validation

Focused gate:

```text
python3 -m pytest -q \
  tests/test_datapoint_registry.py tests/test_quote_resolution.py \
  tests/test_intelligence_workspace_identity_market.py \
  tests/test_intelligence_workspace_owner_adapters.py \
  tests/test_intelligence_workspace_consumers.py \
  tests/test_intelligence_workspace_mutations.py \
  tests/test_intelligence_workspace_cli.py \
  tests/test_intelligence_workspace_performance.py
=> 138 passed, 3 non-product pytest temporary-directory cleanup warnings
```

```text
python3 -m compileall -q engine/intelligence_workspace \
  engine/quote_resolution.py scripts/resolve_datapoints.py
git diff --check
=> both clean
```

The current-main owner-suite baseline completed with `474 passed, 2 skipped, 3
failed`. The three failures pre-exist outside the W1-A file surface: two
`TestNothingGatesOnTheNewFields` cases observe the already-current
`templates/_us_prophet_plan_cards.html.j2` reads of `days_to_report` and
`reports_within_7`; one CN/HK Theme identity-count assertion expects 984 while the
current generated owner corpus contains 988. W1-A neither modifies those files nor
widens itself to heal unrelated baseline drift. Hosted exact-head CI remains the
binding repository gate.

## Architecture and completion boundary

W1-A creates no dataset/security/issuer/price/history/rights/value store, no second
financial semantic model, no formula owner, no ThemeState, no canonical-theme
inference, no trading authority, no public API/UI and no direct vendor fetch. It is
a deterministic read layer over existing owners.

W1-B, W1-C, W3, the generalized fact intent router, effective-context compiler,
full screener/query kernel, rules/alerts, ratings, workspace, Terminal changes,
Market OS B1+, Neural Web promotion and Prophet/Fusion integration are not built or
authorized. After W1-A acceptance, the only natural continuation is a separately
commissioned W1-B. This carrier stops here.
