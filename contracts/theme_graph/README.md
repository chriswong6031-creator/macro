# `contracts/theme_graph/` — the semantic spine, and how to read it

Row contracts for `data/theme_graph/{nodes,edges,evidence,capability}.parquet`, the
probation-proposal queue, plus the CN price-limit regime registry. Producer: `scripts/build_theme_graph.py` (engine:
`engine/theme_graph/`). Guard: `scripts/check_theme_graph_contracts.py`
(law `theme_graph.edge_contract`). Program: GMI W1b —
`research/GLOBAL_MARKET_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` §4.1–§4.4.

This file is the **consumer contract**. The first named consumer is Group Reads'
regional twins (masterplan §5.1): GMI's CN membership spine is a necessary input for
GR's CN/HK twins, and GR's own gate ("after US proves") is unchanged by that — GMI
supplies membership and evidence, GR computes participation. Read the five rules
below before joining anything to this store.

## 1. Read semantics — latest belief, never latest row

The edge store is **append-only and bitemporal**. One `edge_id` may have many rows,
each with its own `belief_time`. The current view is

> **for each `edge_id`, the row with the maximum `belief_time`** (ties break on the
> later `computed_at`, then on `edge_id` — deterministic, never on a magnitude).

`engine/theme_graph/store.py::read_edges(latest_belief=True)` is that view; use it
rather than reading the parquet raw, or you will double-count every fact that has
ever been re-believed.

Two consequences that bite:

- **A closed edge never vanishes.** Closing a membership appends a NEW row carrying
  `valid_to`; the row that opened it stays on disk as what was believed then. If a
  closed edge disappears from your join, your join dropped it — the store did not.
  Dead members stay in every denominator (gap-refusal survivorship law); a delisted
  or removed constituent is an edge with a `valid_to`, never an absence.
- **Contradictory evidence coexists.** Two receipts disagreeing about the same fact
  are two `evidence` rows and two `evidence_refs`; nothing nets, nothing is
  superseded in place. A consumer that wants one answer must say which receipt it
  trusts and why — the store will not choose for it.

Point-in-time membership at date *D* = edges where `valid_from <= D` and
(`valid_to` is null or `valid_to > D`), evaluated on the latest-belief view — and,
for a genuinely as-of-*D* answer, restricted to `belief_time <= D` as well. Those
are different questions; the second is the one that is not look-ahead.

## 2. `era` and `date_provenance` — what the dates actually mean

Every W1b row is `era="reconstruction"`: assembled after the fact from curated
membership documents, with `belief_time` = the backfill's own run date. **Reconstructed
history is never promotion evidence** (G0.2). From the first nightly on, genuine
changes append with `era="observed"`.

`date_provenance` says how `valid_from` was obtained, and one value is a warning:

| value | meaning |
|---|---|
| `curated_changelog` | the membership document recorded a real dated add/remove |
| `seed_constant` | **the date is a CONVENTION, not an observation** |
| `raw_snapshot` | first observed in a dated vendor snapshot |
| `crosswalk` | derived from `config/theme_crosswalk.yml`, dated at the crosswalk's own date |

**`seed_constant` in detail.** The CN basket families seed every first-run member at
the fixed price-cache start `2021-06-15`. That constant is not when those companies
joined those themes — it is where the series begins. An edge stamped `seed_constant`
therefore supports "this membership is descriptive of the window" and never "this
membership was known on that date". Filtering it out is legitimate; treating it as an
observation is the exact error G0.2 exists to prevent: **do not make present knowledge
look historically known.**

## 3. Ordering, tier, and what this store may not do

- **G0.11 ordering law.** Query results order by **recency or canonical id only**.
  Sorting members by an exposure attribute makes the query a ranker, which is
  forbidden. The three exposure axes (`economic_share`, `trading_beta`,
  `attention_share`), their `*_formula_id`s and their `*_display` enums are
  **reserved-null in v1** — W2's exposure-decomposition probe measures them; until
  then they are columns, not numbers.
- **Display tier, zero authority.** The synapse entries `theme-graph-{nodes,edges,evidence}`
  carry all six authority booleans literal `false`. This store ranks nothing, sizes
  nothing, gates nothing, originates nothing, adds no candidate, escalates nothing.
- **No fused composite.** There is no score in here and there will not be one; theme
  readings print as named legs (G0.1).
- **Evidence grain.** W1b builds `MEMBER_OF` (company→basket), `EXPRESSES`
  (basket→theme) and `TRACKS` (etf→basket) only. There is deliberately **no derived
  company→theme edge**: composing membership with expression is the consumer's join,
  made against evidence it can see, not a fact this store asserts on its own.

## 4. The source-local plane (W3A) — `kind=local_theme`

A `local_theme` node is a SOURCE's own concept at the source's own grain: a Finviz
subtheme (`ltheme:finviz:<subtheme_key>`), a 同花顺 concept board
(`ltheme:ths:<code>` — the code, because 中文 names are labels, not ids). It is
deliberately not canonical GMI vocabulary; the canonical plane stays `theme:*`, and the
two meet only through a curated `EXPRESSES` edge.

**`MEMBER_OF company→local_theme` is not the refused derived edge.** The bullet above
refuses COMPOSING "A is in basket B" with "B expresses theme T" into "A expresses T" —
a fact no receipt supports. A local-theme membership is the opposite case: the SOURCE
ITSELF asserts that this ticker sits in this subtheme, and the edge carries that claim
with its own provenance (`source_class=scrape`, `confidence_basis=finviz_tree.v1`,
`date_provenance=raw_snapshot`) at the source's own grain. The structural proof that no
laundering happens: the Finviz plane mints **zero** `ltheme→theme` edges, so there is no
path from a company to canonical vocabulary through it at all.

**The join law: canonical expression is ONE hop.** `basket→theme` is the expression
path. `ltheme→theme` (61 curated 同花顺 rows) is **vocabulary resolution** — it says a
vendor's concept and a canonical theme name the same thing — and never a second
expression path. The guard asserts the two agree over every row where both exist: a
basket and the concept it expresses cannot resolve to different themes.

**Dates come from a vintage ladder.** Snapshot sources say what is true today and
nothing about when it started, so observations are laid out as dated vintages:
`valid_from` = FIRST OBSERVED, `valid_to` = the first vintage observed WITHOUT the
member (never an invented mid-window date). Under a manual refresh cadence `valid_to` is
therefore **interval-censored** — bounded by the gap between refreshes — and reads as
"gone by then", never "left on that day". A membership that reappears after a gap opens a
SECOND interval; both survive.

**Labels are mint-time snapshots, and the graph is a join spine.** `name_en`/`name_zh`/
`source_meta` are written once with the row (node rows are keep-first), so a vendor
rename changes no bytes here and the current label resolves from the live source
artifact. Rights govern the subtheme→member STRUCTURE as a dataset; a vendor's own label
is already-public vocabulary and rides `name_*` lawfully.

**Rights: the registry is the only authority.** `config/theme_sources.yml` says what may
be emitted from each source family, read at call time by
`engine/theme_graph/rights.py::assert_public_emission_allowed`. The per-row
`licensing_*` booleans on an evidence row are **mint-time snapshots with no enforcement
power** — the store is append-only, so a row minted under last quarter's class cannot
learn that the class moved. The guard therefore WARNS on a snapshot that disagrees with
its family's current class and FAILS CLOSED on a `source_meta.rights_family` that has no
registry row at all.

**Capability is a side-car, not a column.** `data/theme_graph/capability.parquet`
(contract: `capability.v1.schema.json`) classifies local themes as `semantic_only` /
`measurement_candidate` / `measurable`, re-derived by every build with the current view =
max `computed_at` per node. It is internal, never user-facing, and never a market state.
It lives outside the node row precisely because node rows are write-once: a capability
stored there would be a one-way ratchet that outlived every later substrate improvement.

## 5. Versioning — additive only

`v1` is **additive-only**: a later wave may add columns and enum members; it may not
rename a column, repurpose one, or narrow an enum. A breaking change ships as
`v2` schemas beside these, and both stores coexist until every consumer moves.
`_meta.json` beside the parquets carries `computed_at`, the row counts, per-suite
counts, and the living `ths_unmapped_concept_count` / `unknown_ths_codes` — read it
for freshness and coverage rather than counting rows yourself.
