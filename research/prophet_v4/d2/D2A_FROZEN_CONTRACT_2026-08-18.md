# V4-D2A FROZEN CONTRACT — GMI → Data OS Identity Resolution Bridge

**Frozen by:** Fable main loop, 2026-08-18, after Scout A (Data OS plane), Scout B (graph
store/guard), Scout C (hostile cases), Scout D (cohort coverage) returns. Build pin:
`9ff7bad19126` (re-pinned from the D1 merge per the D2A handoff §12.1; collision check
clean — no open PR touches any D2A path).
**Authority:** Chairman V4 outcome → Sol D2A amendment (exact identity = Data OS spine;
GMI keeps topology ids; Stock Identity is NOT the exact-identity master) →
`config/identity_seams.yml` → `research/MASTERMIND_SECURITY_MASTER_SPEC.md` →
`lib/dataos/identity.py` + committed artifacts → GMI graph laws → D1 receipts.
**The builder implements THIS document. Deviations require returning to the orchestrator.**

## 1. Schema and paths

- Contract id: `gmi.identity_resolution/v1`; JSON schema at
  `contracts/theme_graph/identity_resolution.v1.schema.json` (house filename-suffix
  versioning; see `contracts/theme_graph/README.md` siblings).
- Store: `data/theme_graph/identity_resolution.parquet` — append-only keep-first sidecar,
  KEY `(node_id, computed_at)`, current view = max `computed_at` per node — the exact
  `capability.parquet` pattern (`store.py:77-92`, `read_capability` `store.py:207-218`).
  Never a node column: node rows are keep-first write-once (`store.py:1-9`, `:244-265`).
- Reader: `engine/theme_graph/identity_resolution.py`.
- Writer: derive rule in `engine/theme_graph/materialize.py` (capability-rule pattern,
  `materialize.py:907-910`) + `store.write_identity_resolution(...)` (lane-gated via
  `lane_ok()`, `COLLECT_LANE=nightly`, fail-closed — `store.py:146-167`), wired into
  `scripts/build_theme_graph.py::run()` immediately after `write_capability`
  (`build_theme_graph.py:132`), with `counts["identity_resolution"]` folded into the same
  `meta` dict → `write_meta` (`:134-160`).
- Guard: new section in `scripts/check_theme_graph_contracts.py::audit()` modeled on the
  capability block (`:551-596`) + `selftest()` fixtures (`:702-815`). Annotations via bare
  `print("::notice/::warning ...", flush=True)` — never a logger (repo law).

## 2. Row scope and grain

One row per **company-kind node** (`kind == "company"`, 2,806 nodes at pin; the sole
company-like predicate per `NODE_ENUMS`) per materialized graph generation. `etf`/other
kinds get NO rows in v1. Every company node MUST have a row, including refusals.

## 3. Columns (all required; nullable only where stated)

| column | semantics |
|---|---|
| `schema` | const `gmi.identity_resolution/v1` |
| `node_id` | the GMI topology id, verbatim — NEVER rewritten |
| `graph_kind` | const `company` in v1 |
| `market_scope` | `us/cn/hk/ca/intl` parsed from the id (validate with `identity.COMPANY_ID_RE`; write ONE clean split — no shared parser exists, do not copy the hand-rolled ones at `check_theme_graph_contracts.py:542-544` / `capability.py:144`) |
| `graph_identity_epoch` | from the node row / id suffix; READ-ONLY (epochs come solely from `config/theme_graph_identity_breaks.yml`) |
| `source_native_symbol` | the symbol segment (epoch suffix stripped, upper-cased) |
| `resolution_asof` | the date used for alias resolution = the generation's `belief_time` |
| `resolution_state` | closed enum, §4 |
| `issuer_id` / `security_id` / `listing_key` | master conventions (`ISS:`/`SEC:`/bare `<CC>-<MIC>-<CODE>[.N]`); ALL THREE NULL unless state == RESOLVED |
| `join_method` | closed enum: `master_inception_exact` / `vendor_alias` / `refused` |
| `master_generated_at`, `master_symbol_directory_snapshot`, `master_code_version` | copied verbatim from `data/reference/_receipt.json` |
| `refusal_reason` | text, NULL iff RESOLVED; for exceptions quote the receipt status+reason |
| `source_receipts` | compact JSON string: matched master/alias rows or the conflict/absence evidence |
| `computed_at`, `engine_version` | house stamps (capability pattern) |

## 4. Resolution algorithm (deterministic; NO fallback to ticker equality, NO fuzzy, NO scores)

Inputs: `data/reference/security_master.parquet`, `vendor_aliases.parquet`,
`_receipt.json`, loaded ONCE per materialization; alias resolution ONLY through
`lib.dataos.identity.VendorAliasTable.from_records(...)` + `.resolve(vendor, symbol, on=resolution_asof)`
(D2A is the FIRST real consumer — Scout A finding 1; `lib/dataos` is read-only, unmodified).

Ordered rules — first match wins:
1. `node_id` fails `COMPANY_ID_RE` → `INVALID_SOURCE_ID`.
2. `market_scope == "intl"` → `UNSUPPORTED_MARKET` (no country/MIC mapping exists).
3. `source_native_symbol` ∈ `_receipt.json.identity_exceptions` →
   `DEFERRED_IDENTITY_EXCEPTION` (covers `B` = deferred_no_mint and `GOLD` =
   disclosed_existing_alias; refusal_reason quotes the receipt).
4. Graph entity-kind conflict: an `etf`-kind node exists in the SAME generation whose
   symbol equals `source_native_symbol` (e.g. `co:us:IBIT` vs `etf:IBIT`) →
   `ENTITY_TYPE_CONFLICT`; ids null; `source_receipts` names the etf node AND the master
   row the symbol would otherwise resolve to. Machine-visible, no kind rewrite, no pick.
5. Exact: `source_native_symbol == inception_code` in the master → `RESOLVED`,
   `join_method = master_inception_exact`, ids copied from the master row.
6. Alias: query `VendorAliasTable.resolve(vendor, symbol, on=resolution_asof)` for EVERY
   vendor present in the table; collect the set of distinct security_ids returned.
   |set| == 1 → `RESOLVED`, `join_method = vendor_alias`, `source_receipts` lists the
   matching vendors/rows; derive issuer_id/listing_key from the master row for that
   security_id. |set| > 1 → `AMBIGUOUS` (never pick by precedence/cap/name).
7. Nothing matched → `NOT_IN_MASTER` (first-class honest state; this is the D2B queue —
   expected material: Scout D measured 43.2% of us-scope company nodes unmatched, and the
   master is 100% US so ALL cn/hk/ca company nodes land here).

Two-clock law: rule 6's `on=` date makes historical-vs-current spelling resolution flow
through the DATED alias rows exactly as Data OS defines them (`AliasRow`,
`identity.py:634-645`). The current-catalog question and the historical-naming question
are never collapsed into one symbol map.

## 5. Reader API

- `read_identity_resolution(latest=True)` — bulk, `read_capability` pattern.
- `resolve_graph_node_identity(node_id, asof=None)` — returns the node's typed row from
  the latest sidecar generation when `asof` is None; for an explicit historical `asof`,
  re-runs the §4 algorithm as a PURE function over the committed inputs at that date (no
  store write, no second store). Raises `KeyError`-style typed error only for a node_id
  absent from the graph; NEVER returns an untyped/None resolution for a known node.

## 6. Hostile-case expected states (binding fixtures; from Scout C's byte receipts)

| case | expected |
|---|---|
| `co:us:GOOG` / `co:us:GOOGL` | BOTH `RESOLVED`, distinct security_ids `SEC:US-XNAS-GOOG` / `SEC:US-XNAS-GOOGL`, distinct per-listing issuer_ids — the master has NO cross-share-class issuer axis; the limitation is DISCLOSED (docs + receipt note), never manufactured. `config/share_class_equiv.yml` (13F collapse) is NEVER consulted. |
| `co:us:BRK-B` | `RESOLVED` → `SEC:US-XNYS-BRK.B` via alias rows (dash→dot lives in the alias table; NO new normalizer in GMI) |
| `co:us:B` | `DEFERRED_IDENTITY_EXCEPTION` (receipt: deferred_no_mint) |
| `co:us:GOLD` | `DEFERRED_IDENTITY_EXCEPTION` (receipt: disclosed_existing_alias, not issuer-safe across 2025-12-02); D2A does NOT touch its membership edge — that is D2B lineage work |
| `co:us:MMC` | `RESOLVED` → `SEC:US-XNYS-MMC`; mutation test: post-rename historical name alone cannot resolve pre-2026-01-14 dates |
| `co:us:SATS` and `co:us:ECHO` | BOTH `RESOLVED` → the SAME `SEC:US-XNAS-SATS` (two topology nodes, one security — the machine-visible duplicate the bridge exists to expose; effective date 2026-06-24 respected) |
| `co:us:FI` and `co:us:FISV` | BOTH `RESOLVED` → the SAME `SEC:US-XNAS-FISV` (undated vendor-lag rename; membership alias carries FI) |
| `co:us:IBIT` | `ENTITY_TYPE_CONFLICT` (etf:IBIT coexists; master row SEC:US-XNAS-IBIT goes in source_receipts, ids stay null) |
| ANGPY, BLD, CBOE, EA, GATO, IMPUY, MAG, RHHBY (graph nodes, zero master rows) | `NOT_IN_MASTER` |
| CTRA (delisted-receipted, in master) | `RESOLVED` — the master models identity, not lifecycle (`models_lifecycle: false`); lifecycle is out of D2A scope |
| every `co:cn:*` / `co:hk:*` / `co:ca:*` node | `NOT_IN_MASTER` (master is 100% US today; the venue grammar supports these markets, so the question is formable and the honest answer is "no row") |
| every `co:intl:*` node | `UNSUPPORTED_MARKET` |

## 7. Guard requirements (Consumer 2)

In `audit()`: (a) schema/columns/dtypes/enums checks per house helpers; (b) orphan sidecar
rows (node_id with no node row) = breach; (c) **sidecar present + any company-kind node
without a current resolution row = breach** (strict CI fails — Sol attack 17); (d) sidecar
file entirely absent = `::notice` "half-finished build" per house capability posture
(historical generations predate the plane); (e) census printed every run: total company
nodes, projection rows, count per resolution_state, entity-type conflicts, and node-sets
resolving to the same security_id (the SATS/ECHO / FI/FISV duplicates). A refusal state is
NEVER a guard failure — `NOT_IN_MASTER` is required honest state (Sol §8).

## 8. Tests (mutation tests binding, §13 of the handoff)

Extend `tests/test_theme_graph_contracts.py` + new resolver test module: the §6 fixture
table verbatim against the REAL committed stores; mutation tests — rewriting
`co:us:GOOGL` to a SEC id fails `COMPANY_ID_RE`/guard; deleting a resolution row fails the
guard; a ticker absent from the master cannot become RESOLVED (assert no equality
fallback); MMC historical-clock test; guard selftest fixtures for the new breach/notice
classes. The suite must run on the real committed parquets (planted-AAPL-only is
insufficient per handoff §14).

## 9. First materialization (real machine proof)

The PR commits the first real `identity_resolution.parquet` baked from the committed
graph + committed master (2,806 rows; the capability-plane first-bake precedent), with
`COLLECT_LANE=nightly` set for the local bake exactly as the W3A first-bakes did, and the
guard run green in strict mode on the result. Counts go into `_meta.json` and the D2A
coverage receipt (`research/prophet_v4/d2/D2A_COVERAGE_RECEIPT_2026-08-18.md`), which also
carries Scout D's pre-bridge cohort table (C0 21.3% / C1 23.3% / C2 47.0% / C3 23.4% /
C5 51.5% / us-graph 56.5% exact) as the cross-check and the D2B gap statement. Every
percentage stamps its pin.

## 10. Registry + docs amendments (same PR)

- `config/identity_seams.yml`: ONE additive ADOPT-class row for
  `engine/theme_graph/identity_resolution.py` ("bridge projection; delegates every
  resolution to the master via VendorAliasTable; no own allocation; refusals typed").
  Run `tests/test_identity_seam_agreement.py` + the completeness test — the new surface
  must be declared before the content scan finds it. Nothing else in the file changes.
- `research/prophet_v4/V4_D2_ONTOLOGY_AND_PROBATION_HANDOFF.md` Gate 1: supersession note
  (old Stock Identity wording marked SUPERSEDED by the Sol D2A ruling, not erased).
- `research/prophet_v4/CONTRACT_AND_OWNER_MAP.md`: exact identity authority row (Data OS
  spine); Stock Identity row stays for behavioral/expert-routing; GMI ids intentionally
  distinct; bridge = the integration seam; no second allocator. Note the master's receipt
  currently reads `authority: display_only` — Sol's D2A ruling is the promotion of the
  spine to exact-identity authority and D2A is its first real consumer.
- `agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md`: d2 → in_progress with D2A child
  noted; record Sol adjudications — D3/W3B ownership ACCEPTED (GMI sole ThemeState owner,
  neuralweb thematic_state = predecessor lineage), D5 ACCEPTED WITH BOUNDARY (theme family
  ACCRUING/null until D3). Do NOT mark d2 done. Handoff record update in the same PR.

## 11. Forbidden (restated from the handoff §10 — the builder must not touch)

`lib/dataos/identity.py`; `scripts/build_security_master.py`; `data/reference/**`;
`engine/stock_identity/**`; `data/stock_identity/**`; node_id generation; membership
edges; `config/theme_crosswalk.yml`; `config/theme_sources.yml`; probation; ThemeState;
neuralweb; Prophet; Radar; Earnings; ranking/fusion; workflows; public UI.
If Data OS itself must change to implement this contract: STOP and return the blocker.

## AMENDMENTS (post-adversarial-review, 2026-08-18)

An opus adversarial review confirmed the D2A implementation on 27/30 attacks and found
one BLOCKER (F2) plus four non-blocking findings (F1, F3, F4, F5). All five are
dispositioned in the same PR that lands this amendment. The rules below AMEND §4 and
§7; the original frozen text above is left verbatim (never rewritten) — this section is
the binding delta.

### F2 (BLOCKER) — two-clock collapse on the historical asof path

§4's own two-clock note ("the current-catalog question and the historical-naming
question are never collapsed into one symbol map") was violated on exactly the path
built to answer a historical question: `resolve_graph_node_identity(node_id,
asof=...)`'s rule 6 was calling `VendorAliasTable.resolve(vendor, symbol, on=asof)`
unrestricted — the SAME lookup the materialization path uses — so an explicit
historical `asof` could still be answered by a fully-open (`valid_from` and `valid_to`
both null) CURRENT-CATALOG alias row (`store`/`yahoo_fetch`), which exists to answer
"what string do I use TODAY for a bar of any date", never "what did this space call the
security on THAT historical day" (`AliasRow` docstring, `lib/dataos/identity.py`).

**Rule change (§4 amendment).** Two resolution MODES now exist:

- **CURRENT mode** — the materialization path (`derive_rows`, driven by a generation's
  `belief_time`) and `resolve_graph_node_identity(node_id, asof=None)`'s live-compute
  fallback. Rule 6 may consult every vendor alias space, exactly as originally
  specified — unchanged, and the committed bake is byte-equivalent in its state counts
  (701 RESOLVED / 1869 NOT_IN_MASTER / 233 UNSUPPORTED_MARKET / 2
  DEFERRED_IDENTITY_EXCEPTION / 1 ENTITY_TYPE_CONFLICT) because no real node's rule-6
  answer changes today.
- **HISTORICAL mode** — `resolve_graph_node_identity(node_id, asof=<explicit date>)`
  only. Rule 6 may consult ONLY DATED alias rows — at least one of `valid_from` /
  `valid_to` non-null (the ledger/membership/yahoo dated historical-naming spaces).
  Rows with BOTH bounds null (the store/yahoo_fetch current-catalog spaces) are
  structurally excluded as historical-naming evidence. A historical query answered by
  no dated row is `NOT_IN_MASTER`; when an unrestricted (current-catalog-inclusive)
  lookup WOULD have matched, `refusal_reason` discloses "no dated alias evidence at
  asof; current-catalog rows exist but are not historical-naming evidence" rather than
  the plain no-row reason, so the two kinds of "no" stay distinguishable.

Rule 5 (exact inception-code match) is UNCHANGED and asof-invariant in BOTH modes: the
master's `inception_code` is the security's own canonical symbol, minted once and
stored, so it never depends on the query date — it was never party to the collapse.

### F1 — cross-market equality hole

§4 rules 5/6 matched on symbol/alias equality alone, with no check that the master
row's own market agreed with the querying node's `market_scope`. Latent today (the
master is 100% US, so no cn/hk/ca node can currently collide) but structurally open:
nothing stopped a future non-US master row from resolving a same-spelled node in
another market.

**Rule change (§4 amendment).** After any rule 5 or rule 6 hit, the master row's
listing country (the first segment of its `listing_key`, `<CC>-<MIC>-<CODE>`) must
agree with the node's `market_scope` mapping (`us`→US, `cn`→CN, `hk`→HK, `ca`→CA).
Disagreement → `NOT_IN_MASTER`, `refusal_reason` discloses the cross-market collision —
NEVER resolved, NEVER `AMBIGUOUS` (the master row is definitively another market's
security, not a coincidental symbol collision requiring a pick). No real node's outcome
changes today for the same reason as F2 (master is 100% US).

### F3 — guard blind to artifact corruption

`scripts/check_theme_graph_contracts.py`'s identity section (§7) checked shape/enum and
graph-referential integrity but not internal row consistency or cross-artifact
integrity. Two new breach classes:

- **State↔ids biconditional.** `resolution_state == RESOLVED` ⇒ `issuer_id` +
  `security_id` + `listing_key` all non-null AND `refusal_reason` null; any other state
  ⇒ all three ids null AND `refusal_reason` non-null. The derivation code cannot
  produce a violation, but a hand-edited or truncated parquet could.
- **Master membership.** Every `RESOLVED` row's `security_id` must exist in the
  committed `data/reference/security_master.parquet`, loaded read-only by the guard.
  Absent master (sparse checkout, pre-DOS-1.1 fixture) skips the check, never breaches.

Both ship with selftest fixtures that fire the breach.

Separately (F3b — the reproducibility gate the review found missing): a new test
asserts the COMMITTED parquet's current view is frame-equal (column order/dtype
normalized, `computed_at` excluded as a wall-clock stamp) to a fresh `derive_rows()`
over the committed graph + master inputs.

### F4 — coverage gaps in the test suite

The cn/hk/ca and intl sweeps sampled 25 nodes per market rather than asserting over the
full population, and `test_every_company_node_gets_a_row` called `derive_rows` with the
company-nodes-only list, which starves rule 4 (`ENTITY_TYPE_CONFLICT`) of the etf:IBIT
node it needs to see — a bug specific to that test's own call shape, invisible to the
guard (which is fed the real full-node-list `derive_rows` call by materialize.py).
Fixed: full-population assertions over the BAKED parquet, and the coverage test now
passes the FULL node list (etf nodes included) so rule 4 is live and `co:us:IBIT`
asserts `ENTITY_TYPE_CONFLICT` in that same derivation.

### F5 — `source_native_symbol` join-key risk

Documented, sentence-level, in both the module docstring and the JSON schema
description: `source_native_symbol` is PARSE PROVENANCE ONLY, never a join key. The
only sanctioned resolution paths are `read_identity_resolution()` and
`resolve_graph_node_identity()` — nothing downstream may re-derive or re-match on this
column directly.
