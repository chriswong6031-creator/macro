# Mastermind data contracts — 2026-08-12

Status: specification. §1–§3 are law for any new dataset; §4 contracts are the AS-BUILT
description of ten existing surfaces plus the delta each owes.
Authority: `context_only` — this is data-plane infrastructure. Nothing here ranks, gates,
sizes or escalates anything.
Implements: `DESIGN_SPEC.md` §D5 (contracts) and §D6 (null/zero/unknown), under §D1 layers,
§D2 identity, §D3 temporal profiles and §D4 price basis.
Machine form: `config/dataset_registry.yml`, loaded by `lib/dataos/registry.py::load_registry`.
Sibling specs: `research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md` (the CN plane's own
contract, which this document does not restate), `research/PERCEPTION_CONTRACTS.md` (the
machine-consumable artifact plane on the serving side).

## 0. How to read this, and what "verified" means here

Every factual claim below carries either a `path:LINE` citation or the command that produced
it. A sentence without one is a defect in this document.

Two provenance labels are used and never blurred:

- **VERIFIED** — a command was run and its output is quoted. Commands were run either in the
  code worktree `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/mastermind-data-os-arch-070441`
  (source files) or in the materialized checkout `/Users/chriswong/Documents/Cluade/Macro Dashboard`
  (`data/` contents).
- **INFERRED** — reasoned from cited evidence, not measured.

**Standing caveat on the materialized checkout.** `/Users/chriswong/Documents/Cluade/Macro Dashboard`
is in a broken git state: detached HEAD, an unresolved merge conflict in `config/dag.yml`,
4,560 dirty entries, HEAD 1,119 commits (~29 days) behind the code worktree's `origin/main`
(census PART 2, smells lane, VERIFIED). **Therefore: parquet/JSON file CONTENT read from that
checkout is used freely below — a column list and a stored float are facts about bytes. File
MTIMES and `git log` from that checkout are NOT used to support any staleness claim in this
document.** Where a freshness statement is needed it is sourced from a producer's own declared
cadence, not from an observed mtime.

Standing adjudications this document obeys, cited by key per house law:
`DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` (an adjusted price where the raw print was required
stop-shipped a whole program), `DNR:HOLD-FF-DETECTOR-PERIOD-BASIS` (a knowingly-divergent
definition is registered, not silently unified), `DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY`
(no run clock enters content identity), `DNR:KILL-INTRADAY-CHRONICLE` (nightly is the sole
advancer of forward ledgers).

---

## 1. The contract format

### 1.1 The primitive we are extending

The house already owns the right contract primitive, and it was not designed in the abstract —
it was designed by an incident.

`collectors/base.py:41-80` defines `ColumnContract`, a frozen dataclass carrying exactly one of
`max_dark_days` (the column is live and owed on a cadence) or `retired` (an ISO date on which
upstream disclosure ended), plus a free-text `note` that is appended to the alarm so "the alarm
text says what to do rather than only what broke" (`collectors/base.py:66-67`). The
`__post_init__` at `collectors/base.py:73-80` raises unless exactly one mode is set — the
contract cannot be half-declared.

Its docstring records why the contract had to move down to the column
(`collectors/base.py:43-50`):

> `detect_stale_series` is frame-grain: it asks when the frame last had ANY observation. A
> multi-column series therefore stays "fresh" forever as long as one column keeps ticking —
> which is exactly how china_connect/northbound hid the death of `net`/`buy`/`sell` for ~2 years
> behind a still-live `turnover`.

The incident itself is documented at the source. `collectors/china_connect.py:1-40` records that
the northbound leg (`MUTUAL_TYPE 005`) lost `net`, `buy` and `sell` together on **2024-08-16**
when the April-2024 CSRC rule amendment ended daily northbound flow disclosure; `turnover`
survived and kept posting daily; `hold_mktcap` degraded to quarter-end-only from 2024-09 with a
literal `0` emitted on every non-disclosure day in between — impossible for a cumulative
holdings level, so 450 fake zeros were healed out of the store on 2026-08-04 and the collector
now coerces `0 -> NaN` (`collectors/china_connect.py:23-31`). The frame never went stale. Nothing
went red. The declaration that fixes it is `collectors/china_connect.py:114-140`: five explicit
`ColumnContract` rows per leg, three of them `retired=_NB_RETIRED` so the expected all-null
steady state is **silent**, and only the opposite event — a non-null value after the retirement
date — speaks up.

Three properties of that primitive are load-bearing and are inherited verbatim by the dataset
tier:

1. **The contract is declared at the grain where the failure hides.** Frame-grain freshness
   could not see a dead column, so the declaration moved to the column.
2. **A declared-dead thing is silent, not noisy.** `retired` exists because "a warning that is
   always on is a warning nobody reads" — the same lesson `collectors/yahoo.py:41-43` records
   independently for the missing-symbol reporter (CTRA/TPH sat frozen for three months).
3. **The alarm carries the remedy.** `note` is not documentation; it is the payload of the
   annotation.

### 1.2 What per-DATASET adds that per-COLUMN cannot say

`ColumnContract` answers "is this column still alive". It cannot answer any of the questions
that actually produced the defects this program exists to close, because each of them is a
property of the dataset as a whole or of the relationship between datasets:

| Question | Why `ColumnContract` cannot answer it | Measured cost of not answering it |
|---|---|---|
| What does this number MEAN? | Column-grain freshness is meaning-blind | `data/stocks` `close`, `data/yahoo` `close`, `data/yahoo` `close_price` and `data/massive_stock_day` `close` are four different quantities under one name (§4.2) |
| Which vintage of the adjustment produced it? | Not a liveness property | HON 2025-09-25 reads four different numbers across four live stores (§4.2, VERIFIED) |
| Who WRITES this? | `ColumnContract` is attached to an adapter that already knows | The census lane that owns the storage tier could not find `data/stocks`' writer in a 60-second search and filed it as an open question; it is `collectors/sector_holdings.py:259 class StockPriceAdapter` with `group = "stocks"` at `:263` |
| Who READS this, so what breaks if it moves? | Out of scope by construction | `grep -rl 'data/stocks' engine scripts collectors lib app \| wc -l` = **135** (VERIFIED, this worktree; the census counted 133 and 132 at earlier times — the number moves, which is itself the argument for storing it) |
| Which clocks does it carry, so can it be read point-in-time? | Not a column property | `engine/basket_membership_pit.py` falls back to current membership with `pit=False` for every suite because its store is unbuilt (§4.8) |
| What is it licensed for? | Not a column property | `data/stocks` (`collectors/sector_holdings.py:264` `overwrite_overlap = True  # yfinance auto_adjust=True`), `data/yahoo` and `data/baskets/ohlcv` are all yfinance-sourced and republished to a paid product; the only place that exposure is written down is `config/dataset_registry.yml:57` `licensing: vendor_terms_personal_use` |
| Does it exist at all? | A contract on a store that was never built looks identical to one on a healthy store | `collectors/finnhub_altdata.py:19-21` records that `data/finnhub/recommendation.parquet` "has therefore NEVER existed, and seven consumers … have been reading a missing store and failing open to null the whole time" |

So the dataset tier is not a replacement for `ColumnContract`; it is the tier above it.
`ColumnContract` stays exactly as it is and remains the per-column liveness declaration; the
`DatasetContract` carries meaning, grain, identity, clocks, basis, provenance, rights, and the
DAG edge. `lib/dataos/registry.py:3-11` states this relationship in the implementation's own
words.

### 1.3 The `DatasetContract` fields

Implemented at `lib/dataos/registry.py:115-146`. Required fields are enumerated at
`lib/dataos/registry.py:105-109` and are deliberately short — the comment there
(`lib/dataos/registry.py:103-104`) gives the reason: "a required field nobody can fill honestly
gets filled dishonestly."

| Field | Required | Meaning |
|---|---|---|
| `dataset_id` | yes | Stable dotted id. The DAG node key, and the thing a receipt and a citation both point at. Never renamed; a rename is a new id plus `supersedes`. |
| `layer` | yes | `L0 SOURCE` / `L1 NORMALIZED` / `L2 CANONICAL` / `L3 DERIVED` / `L4 INTELLIGENCE` (`lib/dataos/registry.py:68-81`). The price-basis law lives at L2. |
| `status` | yes | `PRODUCED` / `PROPOSED` / `RETIRED` (`lib/dataos/registry.py:84-89`). See §1.4. |
| `owner` | yes | The accountable lane. Extends, never duplicates, `config/sector_intelligence_ownership.yml` (§1.6). |
| `producer` | yes | `path.py::Symbol` of the single writer. `one_writer_required` is already house policy in that ownership file. |
| `storage` | yes | Path template, R2 key prefix, or table. R2 and Postgres are first-class here, not an archival tier — the Wave-3A fundamentals substrate lives entirely in R2 CAS (§4.5). |
| `format` | yes | `parquet` / `json` / `jsonl` / `sqlite` / `postgres`. |
| `grain` | yes | The uniqueness key, as an ordered column tuple. A row that duplicates on `grain` is a `uniqueness` violation. |
| `identity.id_column` / `identity.id_type` | no (yes for entity-keyed sets) | The join column and its §D2 id form (`SEC`, `ISS`, `listing_key`, `symbol`, `OPT`, `fred_series_id`, `cik`, …). `id_type: symbol` is a **declaration of a known weakness**, not a solution: §D2's law is that a symbol is never an identity. |
| `temporal_profile` | yes | `BARS` / `REVISABLE_RELEASE` / `SNAPSHOT_SERIES` / `EVENT` / `DERIVED` / `INTELLIGENCE`. Determines which clocks are mandatory (§D3). |
| `timezone` | no | The tz the temporal columns are stamped in. `UTC` where the store is UTC-stamped; an exchange tz where it is session-stamped. Silence here is how a Shanghai 09:30 CST bar becomes a Monday NY midnight cross — the hazard `engine/bar_derive.py:71` documents by name. |
| `frequency` | no | `1d`, `1h`, `tick`, `mixed`, `event`, `quarterly`. |
| `adjustment` | no (yes for price sets) | The **(basis, vintage)** pair, never a boolean. See §1.5. |
| `vendor` / `endpoint` | no | Provenance. `endpoint` is the exact URL or SDK call, so a vendor-terms question has one place to start. |
| `conflict_policy` | defaulted | `PRIMARY_ONLY` / `FALLBACK` / `DOMAIN_AUTHORITY` / `CROSS_VALIDATE` / `COMPOSITE` (`lib/dataos/registry.py:92-100`). Defaulting to `PRIMARY_ONLY` is deliberate: `lib/dataos/registry.py:174-177` notes that a single-vendor row should not have to recite a decision nobody made. |
| `freshness_sla_hours` | no | Hours after which the dataset is `DEGRADED`. See §1.7 on why this is not a wrapper over `data/run_status.json`. |
| `quality_checks` | no | Which of the nine §D8 families apply. |
| `consumers` | no | Modules that read it. This is the blast radius; it is the field that makes a basis migration schedulable. |
| `inputs` | no | Upstream `dataset_id`s. This IS the lineage DAG (`lib/dataos/registry.py:15-22`) — no runtime instrumentation, no lineage service. |
| `licensing` | no | Redistribution class. See §1.6 on the three competing spellings that exist today. |
| `version` | yes | SemVer of the CONTRACT, not the data. Minor = additive column. Major = a column's meaning changed. |
| `supersedes` | no | The `dataset_id` or module path this replaces. |
| `schema.<col>` | no | Per-column `{dtype, unit, currency, basis, nullable, null_reasons, zero_is_meaningful, range, renames_to, note}`. |
| `notes` | no | Prose the next session needs and cannot derive. |

### 1.4 `status` is part of the contract

`lib/dataos/registry.py:24-26` states the rule the rest of this document is bound by:

> A registry that lists a dataset which does not exist is worse than no registry: the next
> session builds against it.

This is not hypothetical here. The completeness critic spot-checked the census and found five
dataset rows whose `producer`, `identifier`, `cadence` or `consumers` fields were asserted from
a filename or an unopened file — `data/options_flow` ("not deep-inspected; inferred from
filename convention"), `data/options_entry`/`data/options_exit` (four fields "not
deep-inspected"), the Canada/HK fundamentals rows ("producer: unexplored collector names"), and
`data/china_stocks_raw`'s producer given as an OR of two modules. **Those rows enter the
registry as `PROPOSED` or not at all.** Below, every `PRODUCED` contract was checked against the
bytes; anything not checked says so.

There is a third state the census surfaced repeatedly and that `status` alone cannot express:
**coded, wired to consumers, and empty.** `collectors/china_block_tape.py:73-81` *documents* the
wiring it never received — the module docstring reads "Or via the adapter pattern:
`Adapter("china_block_tape", refresh, hosts=["akshare"], serial=True)`", but that is prose, not
code (`ast.parse` puts the module docstring at lines 1-92; the file defines zero classes and
`scripts/collect.py` never mentions it — VERIFIED here 2026-08-12);
`collectors/finnhub_altdata.py:19-21` records seven consumers reading a
store that never had a row. From the filesystem, a never-wired producer and a wired producer that
broke last night are indistinguishable. `status: PROPOSED` covers "declared, not produced";
`RETIRED` covers "was produced". The wiring state is carried by `producer` plus `notes` today;
promoting it to its own enum is §5 work, not something to invent here.

### 1.5 `adjustment` is a pair, never a boolean — and the boolean already misled a module

The single highest-value correction the adversarial verifier forced on this program:
**`adjusted` is a `(basis, as-of-vintage)` pair.**

`engine/price_ladder.py` is the best prior art in the repo and encodes the boolean form. Its
premise (`engine/price_ladder.py:5-8`) is correct — "An excess return is `name_return −
benchmark_return`. That subtraction is only meaningful when both legs are priced on the SAME
adjustment basis" — and it groups the per-name stores into one family at
`engine/price_ladder.py:104`:

```
ADJUSTED_SOURCES = ("baskets_ohlcv", "yahoo", "data_stocks", "baskets_extras")
```

with `is_adjusted()` at `engine/price_ladder.py:129-133` returning `True` for all four. The
verifier measured that the three per-name rungs are **not the same basis**: on 2024-06-03,
31/223 tickers present in both `data/stocks` and `data/baskets/ohlcv` disagree by >0.01%, 18 by
>0.5%, worst 4.877% (HON); and there is no consistent precedence — for HON, `yahoo == baskets`
and `stocks` is the outlier, while for PEP `stocks == yahoo` and `baskets` is the outlier.
`r.adjusted` returns `True` for all of them, so the divergence is invisible to every consumer.

That module also already documents the exact mechanism, one layer down, for its cache rung
(`engine/price_ladder.py:35-44`): a rebuild re-bases the cache in place, so `PNC` at 2026-06-22
read `234.71` in the 2026-07-01 commit and `232.85` on 2026-08-06, and re-running
`scripts/grade_us_board.py` against the shipped ledger "would have moved 75 already-published
rows, 19 of them materially (worst −1.94pp on `LPG` 2026-06-18 H5)". Its remedy — callers stamp
the basis on the row and an already-graded row is never re-priced — is correct and is exactly
what the `adjustment` field generalizes, with one extension: **it must cover the adjusted family
too, not just the cache fallback.**

Therefore the contract's `adjustment` field is a mapping, not a string:

```yaml
adjustment:
  basis: tradj            # raw | sadj | tradj | dual_basis | none
  vintage: unrecorded     # an ISO date, or `unrecorded`
  vintage_column: null    # the column carrying adjustment_asof, once one exists
```

`vintage: unrecorded` is a legal and currently very common value. It is the honest statement
that the store's adjustment is a point-in-time quantity whose as-of is not written down, and it
is what makes the gap countable. The seeded rows carry the scalar form today
(`config/dataset_registry.yml:52`, `:92`, `:143`); widening them to the mapping is a §5 item.

### 1.6 Fields where a vocabulary already exists and must be picked, not invented

Three contract fields name a fact the repo already records under competing spellings. The
contract must choose one and say which; adding a fourth is the failure mode.

- **`licensing`.** Two spellings exist in collectors sitting in the same tree:
  `collectors/sec_capital_structure.py:1474-1476` writes
  `{"redistribution_class": "public_source_link", …, "license_note": "United States SEC EDGAR public filing"}`
  and `collectors/sec_capital_structure_companyfacts.py:5393` the same shape, while
  `collectors/biocatalyst/drugs_at_fda.py:957` and `collectors/biocatalyst/clinicaltrials_v2.py:925,980`
  write `"license_class": "us_government_source_facts"`. `lib/dataos/registry.py:147`'s
  `licensing: str` is a third name.
  **Ruling: `licensing` is the registry field; its VALUES come from the
  `redistribution_class` vocabulary** (`public_source_link`, `us_government_source_facts`,
  `vendor_terms_personal_use`, `vendor_licensed_redistributable`,
  `vendor_licensed_internal_only`). The per-artifact `rights` block in the SEC collectors stays
  as it is; the biocatalyst `license_class` key is a rename candidate, not a rewrite target.
- **`owner`.** A formal, tracked, test-enforced ownership registry already exists:
  `config/sector_intelligence_ownership.yml` (477 lines, `schema: sector_intelligence_ownership.v1`,
  policy block lines 6-13 with `one_writer_required: true`, `duplicate_writer_behavior: hard_fail`,
  `user_state_owner: terminal_supabase`), enforced by `tests/test_sector_intelligence_ownership.py`
  and pinned by SHA from `config/biocatalyst_closed_beta_source_manifest.yml:17-18`.
  **Ruling: `owner` values must resolve against that file.** Its scope today is the
  sector-intelligence / biocatalyst / corporate-intelligence / capital-structure domains — no
  price, macro, options, news or CN store has a `canonical_owner` row, and that is the actual
  gap. Creating a second ownership registry would violate that file's own
  `duplicate_writer_behavior: hard_fail` spirit and the CLAUDE.md prohibition on duplicate
  control planes.
- **`freshness_sla_hours`.** Five independent staleness mechanisms exist with no shared
  constant: `app/main.py`'s per-artifact `age_min`, `admin/health.py:15 _STALE_HOURS=96.0`,
  `scripts/freshness_sentinel.py`'s per-artifact budgets, `lib/project_runtime_state.py:69-79`'s
  `_CADENCE_SPECS`, and `engine/neuralweb/market_packet.py:173 QUOTES_STALE_MIN=45.0`.
  **Ruling: the registry field is the DECLARATION; the five detectors keep their own
  implementations for now and are reconciled against it in §5.** Building the field as a wrapper
  over `data/run_status.json` is explicitly rejected: that file tracks 149 of 332 top-level
  `data/` dirs, and ~19 "additive, never fatal" bolt-on collector calls in `scripts/collect.py`
  (e.g. `sec_ftd` at `scripts/collect.py:1188-1196` — a bare `try: from collectors.sec_ftd
  import incremental` with a `noqa: BLE001 — additive, never fatal` except; intraday at
  `scripts/collect.py:857-859`)
  bypass the Adapter-registry loop that populates it, so they can run nightly and never register
  an entry (census smells lane, VERIFIED).

### 1.7 A freshness SLA needs an expected-cadence field, or it will cry wolf

`collectors/sec_ftd.py:5-16` publishes on a semi-monthly vendor cadence with a documented
30-calendar-day PIT lag, so a ~37-day-old file is CORRECT, not broken — and a naive mtime sort
ranked it 4th-stalest in the estate (census smells lane, VERIFIED). The existing per-adapter
primitive is `Adapter.stale_after_days` (`collectors/base.py:88`, default 5, consumed at
`collectors/base.py:460-494`), already overridden per source — `collectors/bis.py:74` sets 120
for a quarterly series with a one-quarter publication lag.
**Ruling: `freshness_sla_hours` in a dataset contract means "hours since the last EXPECTED
observation", where expected is derived from `frequency` plus the producer's declared lag —
never "hours since file mtime".** `collectors/massive_stock_day.py:22-25` already states the
correct shape for an R2-backed store: "a dead feed, a failed restore, or a skipped publish turns
the engine job red within 26h."

### 1.8 Where the format lives, and one thing a reader must know about it

The machine form is `config/dataset_registry.yml` (`schema: dataset_registry.v1`, line 32),
loaded and validated by `lib/dataos/registry.py`. Seven rows exist today: three US equity-bar
stores, two FRED stores, and two `PROPOSED` reference rows
(`config/dataset_registry.yml:38,78,129,163,200,240,273`).

**Caveat, stated because omitting it would make this document unfalsifiable:** at the time of
writing, `config/dataset_registry.yml`, `lib/dataos/` and the six `tests/test_dataos_*.py`
files are UNTRACKED in this worktree (`git status --porcelain` → `?? config/dataset_registry.yml`,
`?? lib/dataos/`, `?? tests/test_dataos_{identity,nulls,price,quality,registry,temporal}.py`,
VERIFIED).
CI has therefore never run those tests and no reviewer has seen the registry. This document is
written against files that exist and were read; it is not written against files that have been
proven to compile and pass. Committing them is a §5 precondition, not a follow-up.

---

## 2. Null, zero and unknown (§D6)

### 2.1 The vocabulary

Nine closed values, implemented at `lib/dataos/nulls.py:39-58`:

| Reason | Means | Consumer action |
|---|---|---|
| `OK` | present and meaningful | use it |
| `NOT_YET_AVAILABLE` | exists upstream later; the release has not landed | wait |
| `NOT_APPLICABLE` | the field cannot apply to this entity | never ask |
| `NO_COVERAGE` | we do not carry this entity/field at all | do not infer |
| `VENDOR_FAILED` | we asked and the source did not answer | retry, alarm |
| `SUPPRESSED_LICENSE` | we have it and may not serve it | licensing incident, not a data gap (`lib/dataos/nulls.py:48`) |
| `HALTED` | no print exists because trading was halted | see §2.4 |
| `PRE_INCEPTION` | before the security/series existed | truncate the window |
| `POST_DELISTING` | after the security stopped existing | stop asking |

The set is closed on purpose (`lib/dataos/nulls.py:21-25`): a consumer must be able to act
differently on `NOT_YET_AVAILABLE` (wait) than on `POST_DELISTING` (stop asking) than on
`VENDOR_FAILED` (retry and alarm), which is impossible when all three arrive as the same `NaN`.

Per-column policy is `NullPolicy` (`lib/dataos/nulls.py:61-80`): `zero_is_meaningful`,
`allowed_reasons`, `nan_permitted`. `validate_value` (`lib/dataos/nulls.py:87-121`) returns the
reason a stored value is unlawfully masquerading as, or `None`. Its fail-closed choice is
documented in place: an absence whose reason was never recorded returns `NO_COVERAGE`, the
weakest reading, because the reader genuinely cannot tell "we never had it" from "the vendor
failed tonight" (`lib/dataos/nulls.py:112-119`).

The `HALTED` value has no producer today. `ls data | grep -iE 'halt|luld|auction|suspend'`
returns only `treasury_auctions`, an unrelated Treasury issuance store (census PART 1, VERIFIED).
Halts are inferred and then silently dropped: `engine/theme_crowding.py:47` and
`engine/group_flow.py:91` both drop "zero-variance (halted / constant-price) members" so one
constant column cannot NaN the matrix, and `engine/synthetic_control.py:454` restricts to donors
that "actually printed on that day". A halted name and a genuinely flat name are
indistinguishable in every store, and the resolution is exclusion — an unmeasured,
daily-grain survivorship mechanism inside every cross-sectional statistic the site publishes.
`HALTED` is declared here so the vocabulary is complete when a producer exists; today every
column that could carry it is honestly `NO_COVERAGE`.

### 2.2 What NOT to write a rule about

`lib/dataos/nulls.py:2-4` cites "635 `fillna(0)` sites across 266 files, and 1,426
`get(...) or 0` coercions" as the measured surface. **Both numbers are regex artifacts and
neither reproduces; do not quote them.** The adversarial verifier re-measured: the strict form
`grep -rnE 'fillna\((0|0\.0)\)'` over `engine|scripts|lib|collectors|app` returns 622, and 14 of
the loose-regex hits are `fillna(0.5)`/`fillna(0.05)` and are not zero-fills at all; the `or 0`
count with `\.get\([^)]*\)\s+or\s+0` is 1,582, not 1,426.

Worse, the framing is wrong. On a deterministic 15-site stride sample of the 636:

| Verdict | Count | Examples |
|---|---|---|
| genuine null-as-zero defect | 2 (13%) | `engine/volume_flow_signals.py:200` (unknown OBV slope becomes a definite "not trending up" fed to a persistence counter); `scripts/build_factor_panel.py:1369` (a missing factor day compounded as a flat day) |
| the zero is the true value | 8 (53%) | `engine/theme_clinical.py:515` (a count); `engine/masterminds.py:258` (day-0 return); `scripts/insider_phase0.py:192`, proven by `scripts/insider_phase0.py:195` `act = s[s != 0.0].dropna()  # conditional on insider activity` |
| arithmetically inert | 3 (20%) | `engine/china_conditions.py:334-336` and `engine/axes.py:78-80` both pair the fill with an availability-weighted denominator on the adjacent line; `engine/insider_power.py:404` calls `.sum()`, which already skips NaN |
| grep false positive | 1 (7%) | `engine/active_commodity.py:119` is `fillna(0.5)` |

**A spec clause targeting `fillna(0)` as a class would be ~87% false positives and would train
every future session to ignore it.** The two clauses below are targeted instead.

### 2.3 Clause D6-A — the compounding idiom

**Law.** `(1 + <returns>.fillna(0)).cumprod()` is forbidden without an aliveness mask on the
same expression.

**Why this one.** A missing return is compounded as a *flat day*, so an index level continues
through a period in which the constituent did not trade — halted, suspended, not yet listed, or
delisted. The survivor is the dead entity. This is mechanically detectable and the guarded form
already exists in-repo twice.

**Measured surface (VERIFIED, this worktree):**

```
$ grep -rnE '\(1(\.0)? ?\+ ?[a-z_]*ret[a-z_]*\.fillna\((0|0\.0)\)\)\.cumprod\(\)' \
       --include='*.py' engine scripts lib | wc -l
22
```

Two of the 22 carry the guard:

- `engine/indicators.py:55` — `return (1 + rets.fillna(0)).cumprod().where(closes[cols].notna().any(axis=1))`
- `engine/oracle/timemachine.py:247` — `lvl = (1.0 + ret_w.fillna(0.0)).cumprod().where(alive)`

The remaining 20 are unguarded: `engine/baskets_intl.py:100`, `engine/china_narrative_tags.py:181`,
`engine/commodity_index.py:182`, `engine/china_narrative_radar.py:81`, `engine/china_sector_index.py:98`,
`engine/china_sector_index.py:215`, `engine/momentum_crash_gate.py:108`, `scripts/build_intl.py:675`,
`scripts/oracle_nightly.py:763`, `scripts/oracle_screen.py:139`, `scripts/study_hk_narrow_leadership_turn.py:297`,
`scripts/oracle_reversion_screen.py:323`, `:668`, `:785`, `scripts/backtest_vol_overlay.py:124`,
`scripts/cbf_regime_study.py:751`, `scripts/research/oracle_reversion_base10_tc_sweep.py:141`,
`scripts/research/net_liq_regime_gate.py:96`, `scripts/research/oracle_seq_tc_recheck.py:242`,
`scripts/research/oracle_compound_tc_recheck.py:89`.

**Detector.** The grep above, as a test that asserts the site set is a subset of a declared
allowlist; a new unguarded site fails. Registered as a `tests/` case, not a new
`scripts/check_*.py` — `config/house_law_checks.yml` hard-fails on any unregistered
`check_*.py`.

**Not a mass rewrite.** Several of the 20 are research scripts operating on a survivorship-clean
frame where the mask is a no-op. The clause's job is to force each one to say which.

### 2.4 Clause D6-B — the volume cluster

**Law.** On a volume column, `zero_is_meaningful: false` unless the contract says otherwise, and
a missing bar may not be filled with `0`.

**Why this one.** "No trades" and "no data" are different market states, and both flow straight
into OBV / CMF / accumulation reads that treat zero as a real observation. The sites:
`engine/stock_technicals.py:345` `vol = volume.fillna(0.0)`; `engine/stock_technicals.py:258`
`has_vol = bool((volume.fillna(0) > 0).sum() > 20)`; `engine/volume_signature.py:89`
`volume = volume.fillna(0.0)`; `engine/leader_lifecycle.py:547` `obv = signed_vol.fillna(0).cumsum()`;
`engine/basket_tape.py:184` `dt.signals(close, high, low, dvol.fillna(0.0))` (census smells lane).

**And in one store the fill is not even representable as a fix.** VERIFIED, materialized
checkout:

```
$ python3 -c "
import pyarrow.parquet as pq
for p in ['data/stocks/AAPL.parquet','data/yahoo/AAPL.parquet',
          'data/baskets/ohlcv/AAPL.parquet','data/massive_stock_day/AAPL.parquet']:
    s=pq.read_schema(p); print(p,'->',[(n,str(t)) for n,t in zip(s.names,s.types)])"
data/stocks/AAPL.parquet          -> close double, high double, low double, volume double,  Date timestamp[ms]
data/yahoo/AAPL.parquet           -> close_price double, close double, volume int64,        Date timestamp[ms]
data/baskets/ohlcv/AAPL.parquet   -> open, high, low, close double, volume int64,           Date timestamp[ms]
data/massive_stock_day/AAPL.parquet -> open, high, low, close double, volume int64, transactions int64, date timestamp[ms]
```

`data/yahoo`, `data/baskets/ohlcv` and `data/massive_stock_day` store `volume` as `int64`, which
**cannot represent null at all** — a missing bar in those stores is already a zero by dtype, before
any `fillna` runs. `data/stocks` stores it as `double` and can. The same read also shows the index
column is named `Date` in three stores and `date` in the fourth — a second, smaller instance of the
same class of unlegislated naming.

**Contract consequence.** Every volume column below declares `nullable` honestly against its
dtype, and where the dtype forbids null the contract says so rather than pretending.

---

## 3. Worked case: `volume` = shares or lots?

The brief asks for this case worked against real evidence. Here is what the evidence supports and
what it does not.

### 3.1 What is actually true today

**There is no live shares-vs-lots incident to report, and the reason is that there is no lot-size
data anywhere in the product to be wrong with.** VERIFIED by me across all three repos:

```
$ grep -rlnE "lot_size|board_lot|round_lot|每手|最小交易单位" collectors lib engine scripts   # Macro
(no output)
$ grep -rlnE "lot_size|board_lot|boardLot|lotSize|round_lot" /Users/chriswong/Documents/Cluade/charting-app
(no output, excluding node_modules/.git)
$ grep -rlnE "lot_size|board_lot|round_lot|lotSize" /Users/chriswong/Documents/Cluade/Mastermind
(no output, excluding node_modules/.git)
```

This also closes an open question the completeness critic raised and could not answer ("Is there
a lot-size/board-lot, tick-size, or minimum-price-increment source anywhere in the bot repo? …a
trading bot is the most likely place for exchange microstructure constants"). There is not.

**What DOES exist is the collision, latent, one step from live.** Exactly one module in the
estate declares volume units, and it declares them as lots:

- `collectors/china_tushare_spine.py:2543-2551` reads TuShare `daily.vol` and stores it as
  `row["volume_lots"]`, alongside `row["amount_cny_thousands"]` and
  `row["positive_volume"] = bool(float(volume) > 0.0)`.
- Its manifest block at `collectors/china_tushare_spine.py:4627-4636` pins the fact in
  machine-readable form: `{"source_field": "daily.vol", "stored_field": "volume_lots",
  "unit": "lots (手)", "rule": "positive_volume = volume_lots > 0", "consumer_law": "a
  traded/listing-session claim must filter daily.positive_volume; …"}`.

Every other CN price store carries a bare, unit-free `volume`. VERIFIED:
`data/china_stocks_raw/600519.SS.parquet` has columns `open, close, high, low, volume, Date`
(6,118 rows) — a yfinance-plane store in **shares**, keyed `600519.SS`, with 1,592 files present.
`data/hk_stocks/0700.HK.parquet` is the same shape (159 files).

So the estate contains two conventions for one column name — `volume_lots`, declared in 手 by
`collectors/china_tushare_spine.py:4630`, and bare `volume` in shares — and the conversion factor
between them **is written down nowhere in any of the three repos** (§3.1's three greps). That is
the whole hazard: a reader who knows the two columns differ still has nothing in the estate to
convert with. The only reason no join has crossed them is that the spine has never written a row:
`collectors/china_tushare_spine.py:38-41` states "the immutable operational gate is false and
every collection path remains disabled in this foundation commit", and the census verified its
declared store root `~/.local/share/macro-dashboard/` does not exist on disk.

**Honest verdict: the collision is LATENT, not live. Do not narrate it as an incident.** What
makes it worth a clause is that it is a scheduled one — the CN spine's reopen path is the named
prerequisite for `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`, so when the spine turns on, a store
whose `volume` means lots lands beside 1,592 files whose `volume` means shares, both feeding the
same CN engines. And there is a precedent for exactly this failing quietly: the census's smells
lane found 23 of 150 sampled `data/` parquets carrying unit-free `price`/`value`/`score`/`level`
columns, including `data/canada_insider/transactions.parquet` where `value` sits beside a
`value_key` of materially different magnitude with nothing distinguishing them.

### 3.2 The clause that prevents it

**Clause U-1 — a quantity column declares its unit, and the unit is part of the name when two
units are in circulation for that quantity in the estate.**

```yaml
schema:
  volume:
    dtype: int64
    unit: shares               # REQUIRED on any quantity column. Closed set:
                               # shares | lots | contracts | usd | cny | cny_thousands |
                               # cny_cents | bp | pct | ratio | count | index_points
    currency: null             # REQUIRED and non-null when unit is a money unit
    zero_is_meaningful: false
    nullable: false            # int64 cannot carry null; see §2.4
    null_reasons: []
    range: {min: 0}
```

Three enforcement points, in increasing cost:

1. **Registry validation (cheap, now).** A `PRODUCED` row whose schema contains a column named
   `volume`, `amount`, `price`, `value`, `size`, `qty`, `notional`, `level` or `score` and no
   `unit` is a contract violation. This is a pure-registry check with no data access.
2. **Name disambiguation (cheap, at write time).** When two units for one quantity coexist in
   the estate, the column name carries the unit — `volume_lots` vs `volume_shares`. The CN spine
   already does this unprompted (`collectors/china_tushare_spine.py:2549`) and is the model. This
   is the same law §D4 applies to price: no stored price column may be named `close`, `price` or
   `value` without a basis suffix.
3. **Join-time refusal (the one that would have caught it).** A reader that joins or unions two
   datasets compares `schema.<col>.unit` for every shared column name and RAISES on a mismatch
   rather than converting. Silent conversion is the wrong remedy precisely because the repo has
   no lot-size table to convert with (§3.1) — any multiplier a reader hardcodes would be an
   uncited constant of exactly the kind `engine/gex_engine.py:28`'s `contract_multiplier=100.0`
   already is (§4.9, delta 4). RAISE, and let a human supply the missing reference data.

Note what clause U-1 is not: it is not a request to build a lot-size dataset. No consumer needs
one today, and `DNR`-style discipline says a dataset nobody reads is cost. The clause makes the
absence *visible at the join* instead of *silent in the number*.

---

## 4. The contracts

Notation for each: a header block, a schema table, then a **Delta** paragraph stating precisely
what today's shape is not. Every `PRODUCED` schema table was read from the bytes. Freshness SLAs
marked `(PROPOSED)` are declarations nothing enforces yet.

---

### 4.1 `reference.security_master` — the master

```
dataset_id        reference.security_master
layer             L2 CANONICAL
status            PROPOSED — nothing writes this today
owner             macro-dashboard
producer          (none yet — §D12 phase 1)
storage           (not yet produced)
format            parquet
grain             [security_id]
identity          security_id : SEC
temporal_profile  SNAPSHOT_SERIES
timezone          UTC
frequency         daily
adjustment        n/a
conflict_policy   DOMAIN_AUTHORITY
freshness_sla     24h after a session close (PROPOSED)
quality_checks    uniqueness, referential, completeness
licensing         derived_internal
version           0.1.0
consumers         (every entity-keyed dataset below, once it exists)
```

| column | dtype | unit | nullable | null_reasons | notes |
|---|---|---|---|---|---|
| `security_id` | string | — | no | — | `SEC:<inception listing key>`, minted once and stored |
| `issuer_id` | string | — | no | — | `ISS:<inception listing key>` |
| `listing_key` | string | — | no | — | `<CC>-<MIC>-<CODE>[.N]` — the code at INCEPTION, never today's symbol |
| `country` | string | ISO 3166-1 α-2 | no | — | |
| `mic` | string | ISO 10383 | no | — | XNYS, XNAS, XASE, XSHG, XSHE, XBSE, XHKG, XTSE, XTSX |
| `inception_code` | string | — | no | — | |
| `effective_at` | datetime64[ns] | — | no | — | |
| `ingested_at` | datetime64[ns] | — | no | — | |

Seeded at `config/dataset_registry.yml:240-271`. `lib/dataos/identity.py` is the **allocator**
(mint-once, deterministic, no counter — so two concurrent worktrees minting the same security
produce the same id); this dataset is the **authority** (the stored value).

**Delta — the whole thing.** There is no security master. The identity surface today is at least
**ten** independently-governed seams that demonstrably disagree, not one small seam:
`lib/ticker_aliases.py` (53 lines, 2 entries `{'FI':'FISV','MMC':'MRSH'}`, Yahoo-fetch only, 17
importers, self-scoped by its docstring as "NOT a display map"); `lib/delisted_symbols.py` +
`config/delisted_symbols.yml`; `lib/symbol_directory_receipts.py` (833 lines);
`engine/entity_resolver.py` (a five-layer text→ticker ladder with its own CN code-adjacency,
~280 Chinese basket names, and a CUSIP→ticker layer); `engine/name_resolver.py`;
`engine/ledger_identity.py`, whose header (`:3`, "the EchoStar double count") and measurement
(`:12-22`: 58,660 rows / 247 tickers, "EchoStar Corporation renamed SATS->ECHO effective
2026-06-24", "SATS 128 rows, ECHO 128 rows … zero SATS-only keys, zero ECHO-only keys") record a
rename this repo double-counted, and which states at `:28-29` that "SATS is absent from the
dead-name registry" — a fact `lib/ticker_aliases.py`, the other rename registry, does not have;
`collectors/edgar_deadnames.py`;
`config/theme_graph_identity_breaks.yml` (a THIRD id convention, `co:<market>:<SYMBOL>` retired
and re-minted as `co:<market>:<SYMBOL>#2`); `config/biocatalyst_sponsor_ticker_map.yml`;
`config/us_search_aliases_zh.json`.

Three incompatible collision-suffix conventions are live simultaneously: `CN-XSHG-600519` (CN
spine), `co:<market>:<SYMBOL>#2` (theme graph), and the `.2` form §D2 pins. The measured cost of
the fragmentation is in `lib/ticker_aliases.py`'s own docstring: MMC→MRSH (2026-01-14) was
carried by `scripts/fetch_basket_extras` but not by `scripts/fetch_basket_ohlcv`, so
`data/baskets/ohlcv/MMC.parquet` never existed and the `insurance` basket silently rendered
18/19 members and `us_sector_financials` 75/76 for **seven months**.

And the seam does not exist at all outside this repo: `charting-app/supabase/migrations/0001_init.sql`
keys `watchlist_symbols.symbol`, `alerts.symbol` and `favorites.value` as bare `text` with no
market qualifier and no FK; `scripts/deploy/0008_trade_memory.sql:16` keys
`ticker text not null check (ticker ~ '^[A-Z0-9][A-Z0-9._-]{0,19}$')`; and a grep for
`ticker_aliases|alias` across Mastermind's `brain/`, `portfolio/`, `data_layer/`, `bridge/`
returns zero hits for the identity mapper (census cross_repo lane).

---

### 4.2 `equity.bars.daily.*` — the flagship

There is not one contract here. There are **four US stores**, plus a CN store and an HK store,
and the whole point of writing them out is that they are not interchangeable.

#### Store sizes, VERIFIED

Re-run 2026-08-12 in the materialized checkout `/Users/chriswong/Documents/Cluade/Macro Dashboard`
(a file COUNT is a fact about the filesystem, not an mtime claim — see §0):

```
$ for d in stocks yahoo baskets/ohlcv massive_stock_day; do \
    printf "%-20s %6s  " "$d" "$(ls data/$d | grep -c '\.parquet$')"; du -sh data/$d | cut -f1; done
stocks                  229   76M
yahoo                   824   68M
baskets/ohlcv          2519  272M
massive_stock_day     20476  617M
```

| store | files | size |
|---|---|---|
| `data/stocks` | 229 | 76 M |
| `data/yahoo` | 824 | 68 M |
| `data/baskets/ohlcv` | 2,519 | 272 M |
| `data/massive_stock_day` | 20,476 | 617 M |

**Counts move, and this document pins the re-run above, not the census.** The 2026-08-12 census
lanes counted `data/yahoo` 825 and `data/massive_stock_day` 20,478; the command above returns 824
and 20,476. The store is append-per-ticker and the checkout is dirty (§0), so a two-file drift is
expected, not a contradiction. Any later measurement quoted against these stores must re-run the
command rather than carry a number forward — including the manifest comparison in §4.2.4.

Coverage is asymmetric by two orders of magnitude and history depth is inverted against it: the
census measured `data/stocks/WMT` reaching 1972-08-25 (13,577 rows) and `AAPL` 1980-12-12 (11,483
rows), while `massive_stock_day` starts 2021-07-06 for every name and `baskets/ohlcv` starts
2014-01-02 for every name. `CMG` has no `data/stocks` file at all, so a US large-cap resolves
through a different ladder rung than its peers.

#### The measurement that forces this section

VERIFIED, materialized checkout, HON on 2025-09-25:

```
$ python3 -c "import pandas as pd; ..."
data/stocks/HON.parquet        close        192.57351684570312
data/yahoo/HON.parquet         close        192.4190673828125
data/yahoo/HON.parquet         close_price  195.7587127685547
data/baskets/ohlcv/HON.parquet close        201.96490478515625
```

Four numbers, one ticker, one date, three of them nominally in the same "adjusted" family. By the
tape tip they converge (`data/stocks` reads 227.80 at its last bar 2026-06-29; the other three
read 223.90 at their last bar 2026-06-30 — note also that the four stores do not even end on the
same date). The prior headline case, NVDA 2024-06-03, is the semantic version of the same defect:
`data/stocks.close` 114.80 / `data/yahoo.close` 114.80 / `data/yahoo.close_price` 115.00 /
`data/massive_stock_day.close` 1150.00 (census, VERIFIED, ratio-confirmed by AMZN 2151.82/107.59 =
20.0000 exactly for a no-dividend name vs GOOGL 20.177 with dividend drag).

`collectors/yahoo.py:6-13` documents the semantics correctly — and only in a docstring, with
names that invert intuition:

> `close` — total-return (split+dividend adjusted) = Adj Close from yfinance auto_adjust=False.
> `close_price` — split-adjusted, dividend-UNadjusted … The correct basis for all structure math
> (ZigZag, detrended osc, DCL/failed-cycle, drawdown-from-ATH).

So the basis the house itself calls correct for structure math is **absent from the store 135
files read** (§1.2). And `collectors/yahoo.py:15-19` records the vintage problem explicitly:
"both stored bases are re-adjusted by Yahoo at every fetch, so a 1mo window pulled after an
ex-div/split disagrees with stored history on every overlap date" — handled by
`store.basis_shifted` and a `period='max'` re-pull, which is the correct remedy for the *seam*
and does nothing about the *vintage not being recorded*.

#### 4.2.1 `equity.bars.daily.stocks`

```
layer L1 · status PRODUCED · owner macro-dashboard
producer          collectors/sector_holdings.py::StockPriceAdapter  (group = "stocks", :263)
storage           data/stocks/{ticker}.parquet          (229 files)
format parquet · grain [ticker, date] · identity ticker : symbol
temporal_profile  BARS · timezone America/New_York · frequency 1d
adjustment        {basis: tradj, vintage: unrecorded}
vendor            yahoo (yfinance, auto_adjust=True splice)
conflict_policy   PRIMARY_ONLY
freshness_sla     24h after an NYSE session close (PROPOSED)
quality_checks    uniqueness, validity, freshness, continuity
licensing         vendor_terms_personal_use
version           1.0.0
consumers         135 files under engine|scripts|collectors|lib|app (VERIFIED)
```

| column | dtype | unit | currency | basis | nullable | null_reasons | range |
|---|---|---|---|---|---|---|---|
| `close` | double | quote_currency | USD | `tradj` → `close_tradj` | no | — | >0 |
| `high` | double | quote_currency | USD | `tradj` | no | — | ≥ close |
| `low` | double | quote_currency | USD | `tradj` | no | — | ≤ close, >0 |
| `volume` | double | shares | — | — | yes | `HALTED`, `NO_COVERAGE` | ≥0 |
| `Date` | timestamp[ms] | — | — | — | no | — | session dates |

VERIFIED schema (`pq.read_schema`, above). The census read all 229 files and found exactly ONE
schema, 229/229 = `('close','high','low','volume','Date')` — zero heterogeneity, no `open`
anywhere.

**Delta.** (a) `close` is the total-return series under a name that says nothing; the V1 reader
shim must expose `close_tradj` and a guard must forbid new unqualified `close`.
(b) `open` is absent — but the consequence half of the old claim is wrong and must not be
restated: opens ARE obtainable. `data/baskets/ohlcv` carries a real `open` for 2,519 names
(VERIFIED above, and known in-repo at `engine/marketing/chart_render.py:254` and
`engine/marketing/hot_tape_pack.py:13`), and `engine/ohlc_reconstruct.py` synthesizes
`open := prior close` with `high`/`low` = close ± ATR/2 for four named consumers
(`engine/signal_quality.py`, `scripts/build_signal_quality.py`, `scripts/build_chart_data.py`,
`scripts/build_hk_library.py`), documenting that its `RANGE_MULT=2.0` prior is deliberately wider
than the data-implied 1.65 and that the reconstructed high/low "should NOT be trusted for
tail-risk stop sizing". Two engines decline both routes and say so in the output:
`scripts/build_stock_personality.py:152` and `scripts/personality_compat_phase0.py:873` emit the
literal disclosure `gap-features-unavailable: data/stocks has no open column`.
**The real defect is undisclosed MIXTURE**: a gap feature built from a `baskets/ohlcv` open
against a `stocks` close crosses two adjustment vintages, and nothing stamps which open a caller
got. The contract closes this by requiring that a frame assembled from more than one
`dataset_id` carry the id per column.
(c) `adjustment.vintage` is `unrecorded`. `config/dataset_registry.yml:73-76` records the concrete
cost: the producer splices short `auto_adjust=True` windows onto deep history, which is how 30/231
names came to be stranded on a stale adjustment basis (healed by `scripts/heal_stocks_basis.py`).
(d) `volume` is `double` here and `int64` in the three sibling stores (§2.4) — a union across
them silently upcasts and loses the ability to represent a missing bar.

#### 4.2.2 `equity.bars.daily.yahoo`

```
layer L1 · status PRODUCED · producer collectors/yahoo.py
storage data/yahoo/{ticker}.parquet  (824 entries) · grain [ticker, date] · identity ticker : symbol
temporal_profile BARS · timezone America/New_York · frequency 1d
adjustment {basis: dual_basis, vintage: unrecorded}   # per-column basis below
vendor yahoo · endpoint yfinance (auto_adjust=False)
conflict_policy PRIMARY_ONLY · licensing vendor_terms_personal_use · version 1.0.0
consumers 157 files (VERIFIED)
```

| column | dtype | unit | currency | basis | nullable | notes |
|---|---|---|---|---|---|---|
| `close` | double | quote_currency | USD | `tradj` → `close_tradj` | no | Adj Close. NVDA 2024-06-03 = 114.80 |
| `close_price` | double | quote_currency | USD | `sadj` → `close_sadj` | no | Close. NVDA 2024-06-03 = 115.00. The house's own "correct basis for structure math" |
| `volume` | int64 | shares | — | — | **no (dtype)** | int64 cannot carry null; see §2.4 |
| `Date` | timestamp[ms] | — | — | — | no | |

VERIFIED schema. **Delta.** The two bases are correctly separated and correctly named nowhere —
`close` is the derived one and `close_price` is the traded one, which is backwards from every
reader's intuition. `adjustment_asof` is owed and absent (`config/dataset_registry.yml:123-127`).
Per-ticker history depth is inconsistent *within the store*: the census measured `yahoo/NVDA` at
6,906 rows back to 1999-01-22 and `yahoo/AAPL` at 756 rows back only to 2023-07-03, so any
"deepest history wins" resolution rule silently changes adjustment basis with lookback length.

#### 4.2.3 `equity.bars.daily.baskets_ohlcv`

```
layer L1 · status PRODUCED · producer scripts/fetch_basket_ohlcv.py (invoked from scripts/collect.py:789-806)
storage data/baskets/ohlcv/{ticker}.parquet  (2,519 files, ~272 MB) · grain [ticker, date]
temporal_profile BARS · timezone America/New_York · frequency 1d
adjustment {basis: tradj, vintage: unrecorded}    # measured; NOT identical to .stocks
vendor yahoo · endpoint yfinance (auto_adjust=True, batched)
conflict_policy PRIMARY_ONLY · licensing vendor_terms_personal_use · version 1.0.0
```

| column | dtype | unit | currency | basis | nullable |
|---|---|---|---|---|---|
| `open` | double | quote_currency | USD | `tradj` | no |
| `high` / `low` / `close` | double | quote_currency | USD | `tradj` | no |
| `volume` | int64 | shares | — | — | no (dtype) |
| `Date` | timestamp[ms] | — | — | — | no |

VERIFIED schema. **Delta.** This store exists because of a schema gap, not a vendor gap:
`scripts/collect.py:789-793` justifies the duplicate fetch on the grounds that "the close-only
extras store above can't feed volume", and `scripts/fetch_basket_ohlcv.py:174` falls back to
reading the `yahoo` store for names it lacks. So the same vendor is fetched by two code paths on
two schedules for overlapping tickers. **Contract law going forward: one store per
`(vendor, universe)`, never one store per `(vendor, universe, missing-column)`.** Its `tradj`
basis is a DIFFERENT vintage from `.stocks`' `tradj` — that is the HON 4.877% measurement — so
`ADJUSTED_SOURCES` grouping them as interchangeable (`engine/price_ladder.py:104`) is the live
defect this contract exists to name.

#### 4.2.4 `equity.bars.daily.massive` — the only raw print

```
layer L1 · status PRODUCED · producer collectors/massive_stock_day.py
storage R2 key prefix massive_stock_day/ (CANONICAL, ~617 MB, ~20k parquets);
        data/massive_stock_day/{ticker}.parquet is the restored local copy (20,476 files);
        only _manifest.json and _backfill_state.json are committed
grain [ticker, date] · identity ticker : symbol
temporal_profile BARS · timezone America/New_York · frequency 1d
adjustment {basis: raw, vintage: n/a}     # a printed price has no vintage — this is the point
vendor massive.com · endpoint us_stocks_sip/day_aggs_v1 flat files
conflict_policy PRIMARY_ONLY · version 1.0.0
freshness_sla 26h — DECLARED AND ENFORCED (collectors/massive_stock_day.py:22-25)
```

| column | dtype | unit | currency | basis | nullable |
|---|---|---|---|---|---|
| `open`/`high`/`low`/`close` | double | quote_currency | USD | `raw` → `*_raw` | no |
| `volume` | int64 | shares | — | — | no (dtype) |
| `transactions` | int64 | count | — | — | yes |
| `date` | timestamp[ms] | — | — | — | no | ← lowercase, unlike the three siblings |

VERIFIED schema. This is the **only lawful input for limit-price, tick-size, exchange-rule and
execution work**, per the reasoning that produced `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`.

**Delta, and it is a serious one.** Its own manifest declares it structurally incomplete: the
census read `data/massive_stock_day/_manifest.json` and found `n_tickers: 19133` against the
files on disk — 20,476 today (the census counted 20,478), a 1,343-file mismatch either way —
`coverage.first_day 2021-07-06`,
`n_processed_days: 471` against a window containing ~1,255 sessions, and
`max_missing_run_weekdays: 832`, with the SPY anchor at `n_rows 454` and
`max_gap_calendar_days 1165`. **A spec clause mandating "use the raw basis for structure math"
without a completeness contract on this store would move every structure calculation onto a
~37%-populated store with multi-year holes.** The contract therefore carries
`quality_checks: [completeness, continuity, freshness]` as BLOCK-severity and requires the
manifest's own coverage numbers to be validated against the file count — a check the manifest
already has the inputs for and does not run.

#### 4.2.5 `equity.bars.daily.china_raw` and `equity.bars.daily.hk`

```
china_raw: producer collectors/_stock_ohlc.py yfinance path (INFERRED — the census gave this as
           an OR of two modules and never opened either; status PRODUCED for the store,
           producer field carries the uncertainty rather than a guess)
           storage data/china_stocks_raw/{code}.{SS|SZ}.parquet   (1,592 files, VERIFIED)
           adjustment {basis: tradj, vintage: unrecorded}   (yfinance auto_adjust=True)
           timezone Asia/Shanghai · currency CNY
hk:        producer collectors/hk_stock_prices.py via collectors/_stock_ohlc.py
           storage data/hk_stocks/{code}.HK.parquet          (159 files, VERIFIED)
           timezone Asia/Hong_Kong · currency HKD
```

Both VERIFIED: `data/china_stocks_raw/600519.SS.parquet` = `open, close, high, low, volume(double), Date`,
6,118 rows; `data/hk_stocks/0700.HK.parquet` = `close, high, low, volume(double), open, Date`,
5,441 rows — note the two stores order their columns differently, which matters to any
positional read.

**Delta — and this one is a standing legal boundary, not a cleanup.** `data/china_stocks_raw`
is the Yahoo-plane **adjusted** CN tape. `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` forbids it for
any limit-band/legal-limit math, and its reopen path requires authorized unadjusted TuShare
`daily` × same-key vendor `stk_limit` with integer-cent equality. The sanctioned plane is
`collectors/china_tushare_spine.py`, which declares `daily` as "unadjusted nominal price
authority" and `stk_limit` as "exact legal-band authority" with canonical event prices as integer
CNY cents (`collectors/china_tushare_spine.py:47-50`) — and which has **never written a row**
(`:38-41`, operational gate false). TuShare's own `adj_factor`/`pro_bar` path is not used
anywhere and is listed under the manifest's `not_tested` array. So the three CN adjustment
planes are: Yahoo TR-adjusted (live), TuShare unadjusted nominal (dormant), and no qfq/hfq plane
at all. **Do not write a CN contract that assumes qfq/hfq exist as options.**

The CN identity delta is separate and larger: `grep -rc '"[0-9]{6}\.(SS|SZ)"' engine/*.py`
returns 26 files hardcoding yfinance-suffix CN tickers as first-class dict keys, e.g.
`engine/china_market_drivers.py:263` `extra['semis_rs'] = f['512760.SS'] / f['510300.SS']` and
`engine/china_allocation.py:45-59` keying an entire allocation-role table off `510300.SS` /
`510880.SS` / `518880.SS` (census smells lane). At least six independent CN symbol-suffix
converters exist and two genuinely disagree on Beijing Stock Exchange ranges
(`collectors/china_universe.py:113` returns `None` for 8xxxxx/4xxxxx;
`collectors/china_ths_concepts.py:97-109` maps the same ranges plus 920xxx to `.BJ`) — a code
landing in one converter's blind spot silently drops out of that pipeline while surviving in a
sibling.

#### 4.2.6 The corporate-action factor table the whole section depends on

**`reference.corporate_actions` — PROPOSED. No such store exists, and the absence is DECLARED by
the repo's own contract.**

`contracts/market_memory/spy_daily_price_source_observation.v1.schema.json:246-247` pins, as
required limitations, `"point_in_time_corporate_actions": {"const": false}` alongside
`"total_return": {"const": false}`. The census's searches found no `data/` directory for
splits/dividends, zero production `adj_factor` sites, and `yfinance` called with
`auto_adjust=True|False` across 20+ collectors but **never** with `actions=True` and never
touching `.splits`/`.dividends`.

Anchor points that already exist and should be extended rather than greenfielded:
`contracts/capital_structure_event.schema.json` carries the literal enum value `"corporate_action"`
in its event-family list; `corporate_action_basis` exists in
`contracts/cn_tushare_minutes_manifest.v1.schema.json`; `corporate_action_adjusted` exists in
`contracts/market_memory/spy_experience_{registration,outcome_revision}.v1.schema.json`; and CN
has one derivable detector — `collectors/china_tushare_spine.py:4684` documents `pre_close` as an
"ex-rights adjusted vendor field", so `pre_close != prior close` IS a corporate-action signal,
currently consumed only by `scripts/research/cn_limit_band_progress_w2.py` for limit-band
arithmetic and by nothing for adjustment.

Until this dataset exists, `adjustment.vintage: unrecorded` is the only honest value any adjusted
store can carry, and §D4's V2 target (store `_raw` + factors, derive `_sadj`/`_tradj` on read) is
unreachable. **This is the single highest-leverage PROPOSED dataset in the document.**

---

### 4.3 `equity.bars.intraday` — hourly US

```
layer L1 · status PRODUCED (on the runner; ABSENT from both git checkouts by design)
producer  scripts/build_polygon_intraday.py::accrue
          wired two ways: .github/workflows/intraday.yml:60 and the bolt-on at
          scripts/collect.py:857-859 (which is why it never registers in run_status.json — §1.6)
storage   data/intraday/{ticker}.parquet + _meta.json sidecar + {ticker}.parquet.receipt.json
          gitignored at .gitignore:66; published to R2 (scripts/publish_r2.py:79)
grain     [ticker, ts] · identity ticker : symbol
temporal_profile BARS · timezone UTC · frequency 1h (config polygon.intraday.multiplier/timespan,
          scripts/build_polygon_intraday.py:225-226)
adjustment {basis: sadj, vintage: unrecorded}   — INFERRED, see delta (e)
vendor polygon / massive.com · endpoint /v2/aggs/ticker/{sym}/range/{mult}/{span}/{from}/{to}
conflict_policy PRIMARY_ONLY · version 1.0.0
freshness_sla vendor delay floor 15 min, DECLARED (DELAYED_MIN = 15, :63)
```

| column | dtype | unit | currency | basis | nullable |
|---|---|---|---|---|---|
| `open`/`high`/`low`/`close` | double | quote_currency | USD | `sadj` | no |
| `volume` | double | shares | — | — | yes |
| `ts` (index) | datetime64[ns, UTC] | — | — | — | no — aggregate WINDOW START |

Schema read from the producer (`scripts/build_polygon_intraday.py:261-268`), not from disk:
`ls data/intraday` returns 0 entries in the materialized checkout (VERIFIED), which is correct —
the store is gitignored and lives on the runner and in R2.

**This contract is the best-behaved one in the estate and is the model for the rest.** It already
does four things nothing else does:

1. **Declares its own delay in the data.** `DELAYED_MIN = 15` with the comment "NOT real-time.
   Stamped onto the store's `_meta.json` so consumers label honestly"
   (`scripts/build_polygon_intraday.py:61-63`), written by `_write_meta` at `:193-207` with
   `{store, bar, delayed_min, source, realtime, adjusted, price_basis, timestamp_basis, universe,
   updated}`. The reason the sidecar exists rather than `DataFrame.attrs` is stated at
   `:189-191`: "pandas drops DataFrame.attrs on the parquet round-trip, so this JSON is the
   durable label."
2. **Writes a per-ticker receipt** (`:126-146`) carrying `schema`, `source_file`,
   `source_file_sha256`, `source_available_at`, `bar_seconds`, `vendor_delay_minutes`,
   `adjusted`, `price_basis`, `timestamp_basis`, `row_count`, `first_time`, `last_time`.
3. **Names its basis in a constant, not prose**: `PRICE_BASIS = "split_adjusted_polygon_aggregate_ohlc"`
   and `TIMESTAMP_BASIS = "aggregate_window_start_utc"` (`engine/options_signal_episode.py:76-77`).
   A bar timestamped by window START and one timestamped by window END are different data; this
   is the only store that says which.
4. **Refuses an ambient clock.** `_iso_utc` raises on a naive datetime (`:120-121`),
   and the receipt writer raises on an empty/invalid frame (`:133-134`).

**Delta.** (a) The receipt is not registered anywhere, so nothing joins it to the parquet it
describes; the registry `inputs`/receipt pairing of §D9 is what closes that.
(b) `adjustment.vintage` is still unrecorded — `adjusted: True` in the receipt is the boolean
form §1.5 rejects. (c) US-only by entitlement (`scripts/build_polygon_intraday.py:8-9`), so any
non-US intraday request must return `NO_COVERAGE`, not an empty frame.
(d) It bypasses `run_status.json` (§1.6), so its freshness is invisible to the one registry that
exists.
(e) **The `sadj` basis is INFERRED, not cited.** The producer calls the endpoint with
`{"adjusted": "true"}` (`scripts/build_polygon_intraday.py:259`) and the constant reads
`PRICE_BASIS = "split_adjusted_polygon_aggregate_ohlc"` (`engine/options_signal_episode.py:76`).
That the vendor's `adjusted` parameter means split-only and not dividend-adjusted is Polygon's
documentation, and **it is asserted nowhere in any of the three repos** — no code comment in Macro
or in charting-app states it. The same unstated assumption underlies the Terminal's per-symbol
adjustment seam, where a daily-bar file seeded from Macro's TR-adjusted parquet
(`charting-app/ingest/build_universe.py:49`) is then appended to from Polygon grouped-daily
(`charting-app/ingest/refresh_ohlc.py:40-41`), so one symbol's own series changes basis partway
through. Pinning this belongs in the contract's `endpoint` note, sourced from the vendor, not
inherited from a session's general knowledge.

---

### 4.4 `quotes.live` — live prices

```
layer L1 · status PRODUCED
producer  scripts/build_live_quotes.py (universe assembly) over engine/live_quotes.py (fetch)
storage   site/live/quotes.json (repo dev fallback); $MACRO_LIVE_DIR/quotes.json on the VPS
          (prod: /var/lib/macro-live/public/live, app/main.py:98); also force-pushed to a
          single-commit `live-data` branch for the keyless static path
          (scripts/build_live_quotes.py:12-20)
format json · grain [symbol] (whole-file replace, no history) · identity symbol : symbol
temporal_profile  EVENT (per-quote event_at = quote_ts) · timezone UTC · frequency ~3-5 min in session
adjustment {basis: raw, vintage: n/a}   — a live print is a raw print
vendor polygon (US equities/ETFs when keyed) | yahoo spark (everything else)
conflict_policy FALLBACK — Polygon first for plain US symbols, Yahoo otherwise and as the
          no-key US fallback (engine/live_quotes.py:7-14)
freshness_sla 45 min (the one number that IS enforced downstream:
          engine/neuralweb/market_packet.py:173 QUOTES_STALE_MIN = 45.0)
licensing vendor_terms_personal_use · version 1.0.0
consumers templates/live.js, app/main.py /api/status + /api/overlay,
          engine/neuralweb/market_packet.py, the basket-pulse builders
```

Envelope VERIFIED by reading `site/live/quotes.json`: top-level keys
`['ts','asof','source','quotes','meta']`; `meta` =
`{'requested','resolved','polygon_status','offline','delayed_min','feed','realtime'}` with
`delayed_min: 15`, `feed: '≈15-min delayed (Polygon Standard / Yahoo)'`, `realtime: False`.

**The wire names are NOT the engine names, and the contract must carry both.**
`engine/live_quotes.py:125-129` emits `{price, quote_ts, source, price_basis, delay_min,
prev_close, currency, …}`; `scripts/build_live_quotes.py:255-259` renames them into the wire
envelope as `{basis, prevClose, changePct, delayMin}`. The table below is the WIRE shape (what a
consumer actually parses); the engine shape is the producer's. A contract that records only one
of the two is a contract a consumer cannot use.

| field | dtype | unit | currency | nullable | notes |
|---|---|---|---|---|---|
| `quotes.<sym>.price` | float | quote_currency | per-quote `currency` | no | rounded to 4dp (`engine/live_quotes.py:126`) |
| `quotes.<sym>.ts` | int (ms) | — | — | no | the TRADE/MINUTE time, not the vendor's `updated` |
| `quotes.<sym>.source` | string | — | — | no | `polygon` \| `yahoo` |
| `quotes.<sym>.basis` | string | — | — | no | `trade` \| `minute` \| `day` \| `prev` \| `regular` |
| `quotes.<sym>.prevClose` | float | quote_currency | as above | yes (`NO_COVERAGE`) | |
| `quotes.<sym>.changePct` | float | pct | — | yes | |
| `quotes.<sym>.currency` | string | ISO 4217 | — | no | |
| `quotes.<sym>.delayMin` | float | minutes | — | no | measured against the trade ts |
| `asof` | ISO8601 | — | — | no | |

**What this contract gets right and must not lose.** `price_basis` is a five-value enum, and the
staleness timestamp is deliberately taken from the trade/minute time rather than the vendor's
`updated` field — `engine/live_quotes.py:88-96` states why: "`updated` … refreshes even with no
trade — on a delayed plan or an illiquid name that would falsely look fresh. A day/prev-close
basis is stamped not-live so the consumer falls back." That is exactly the distinction §D4
demands between a consolidated last print and an official close, expressed one layer up.

**Delta.** (a) §D4 requires `session ∈ {pre, regular, post, overnight, auction_open, auction_close}`
and `venue_scope ∈ {primary, consolidated}` as part of price identity. `basis: regular` conflates
"Yahoo's regularMarketPrice" with "the official closing auction price"; nothing in the schema
distinguishes them. (b) Currency is per-quote and correct, but there is no FX dataset contract to
convert with — `engine/hk_ah.py:73` derives `cny_per_hkd = usdcny / usdhkd`, a cross-rate through
two USD legs, and its docstring (`engine/hk_ah.py:1-16`) already disclaims that "the ABSOLUTE
level differs slightly from the official Hang Seng AH Premium index". (c) There is no history: the
file is replaced whole, so no `quotes.live` observation is ever recoverable point-in-time. That is
correct for its purpose and must be stated so nobody backtests against it.

---

### 4.5 `fundamentals.*`

Four surfaces, three generations of the same lesson, and one of them is not on the filesystem at
all.

#### 4.5.1 `fundamentals.us.panel` — the PIT one

```
layer L1 · status PRODUCED · producer collectors/edgar.py (panel section)
storage data/edgar/fundamentals_panel.parquet · format parquet
grain [ticker, fy] · identity ticker : symbol (cik also carried)
temporal_profile REVISABLE_RELEASE · timezone UTC · frequency annual cross-section back to ~FY2009
vendor SEC · endpoint XBRL frames API
conflict_policy PRIMARY_ONLY · licensing public_source_link · version 1.0.0
freshness_sla quarterly + 120d (PROPOSED — see the proxy caveat below)
```

VERIFIED: 22,014 rows, columns `ticker, cik, fy, assets, equity, debt_lt, shares, ni,
gross_profit, cfo, dividends, repurchases, revenue, op_income, interest_exp, assets_prior,
ni_prior, period_end, asof_date, capex`.

| column | dtype | unit | currency | nullable | null_reasons |
|---|---|---|---|---|---|
| `ticker` | large_string | — | — | no | — |
| `cik` | int64 | — | — | no | — |
| `fy` | int64 | fiscal year | — | no | — |
| `assets`…`interest_exp`, `capex` | double | usd | USD | yes | `NOT_YET_AVAILABLE`, `NO_COVERAGE` |
| `period_end` | timestamp[us] | — | — | yes | the fiscal-year end |
| `asof_date` | timestamp[us] | — | — | no | **= period_end + 120d**, a PROXY, not a filing date |

**Delta.** `asof_date` is a conservative reporting-lag proxy because the frames API supplies no
true SEC `filed` timestamp (`collectors/edgar.py:469-471`). `known_at` for this dataset is
therefore modelled, not observed, and the contract must say so — a PIT read against it is
correct-by-construction only to within the proxy. Survivorship is partially fixed and
partially not: historical frames include delisted filers, but `company_tickers.json` cannot map
their CIK back to a ticker, so the panel is current-universe tickers carrying their own history
(`collectors/edgar.py:474-478`), and `collectors/edgar_deadnames.py:7` documents the downstream
consequence: of the 1,083 dead-only tickers in `data/breadth/sp1500_pit_membership.parquet`, zero
carry fundamentals, because `company_tickers.json` cannot map a delisted CIK back to its old
ticker.

#### 4.5.2 `fundamentals.us.statements_quarterly` — the only true filing clock

VERIFIED: 62,253 rows, columns include `period_end`, **`filed`**, `as_of`, plus
`fiscal_year, fiscal_quarter, revenue, cogs, gross_profit, op_income, ni, cfo, capex, shares,
repurchases, long_term_debt, current_debt, cash, net_debt, receivables, inventory, payables,
contract_liabilities`. `period_end`, `filed` and `as_of` are all `large_string`, not timestamps.

```
grain [ticker, fiscal_year, fiscal_quarter] · producer collectors/edgar_facts.py
temporal_profile REVISABLE_RELEASE · known_at = filed   ← the ONE store where this is observed
```

**This is the only per-row acceptance-adjacent timestamp in the entire US fundamentals surface**,
and it is what `engine/capital_allocation.py:57` builds TTM from ("trailing 4 quarters with
period_end in the last 12 months, counting only filed rows"; `_TTM_QUARTERS=4`, `_TTM_MONTHS=12`
at `:134-136`). **Delta:** the three clock columns are strings; they should be typed. TTM is
computed at read time and never stored, which is correct and should stay that way — but the
contract must record that `fundamentals.us.ttm` is a DERIVED view with `computed_at`, not a
store.

#### 4.5.3 `fundamentals.us.statements_annual` — restatement-collapsing

`data/edgar/statements.parquet`, 8,784 rows, producer `collectors/edgar_facts.py`, whose
`_annual()` docstring at `collectors/edgar_facts.py:154` states "latest-filed wins on restatement" — prior vintages
are discarded, and the store has **no `filed` column at all**. `period_end` can be null: 30/8,784
rows, 12 of them inside the 120d gate window (`DNR:HOLD-FF-DETECTOR-PERIOD-BASIS`).

**Delta.** This is a `REVISABLE_RELEASE` dataset with no revision chain — it cannot answer
`known_at`, so under §D3's PIT law **it is FORBIDDEN from point-in-time reads and must RAISE**.
Today it silently returns latest-restated values, which is the leak. `engine/moat_falsifiers.py`
gates it with `_REPORTING_LAG_DAYS = 120` (`:144`) and `_pit_filter()` (`engine/moat_falsifiers.py:162`) — which
explicitly KEEPS rows with a missing `period_end` (fail-open), so the 30 null rows pass the gate.

#### 4.5.4 `fundamentals.us.companyfacts` — R2-native, bitemporal, not scheduled

```
status PRODUCED-CAPABILITY / NOT-SCHEDULED
producer collectors/sec_capital_structure_companyfacts.py (~5,000 lines) +
         engine/fundamental_forensics/* (21 modules)
storage  R2 CAS: capital_structure/companyfacts/generations/<sha256>/{source_manifest,coverage}.parquet
         plus a SEPARATE attested-history bucket read via FF_ATTESTED_R2_READONLY_* env vars
         (engine/fundamental_forensics/attested_history_store.py:1-8), which deliberately
         never imports engine.research_vault.r2_store.build_store
temporal_profile REVISABLE_RELEASE with FIVE clocks: accepted_at, recorded_at,
         mapping_available_at, computed_at, published_at
```

`data_dir()/capital_structure` does not exist anywhere in the 332-dir materialized `data/` tree
(census fundamentals lane, VERIFIED by `find`). **A registry that assumes "parquet under `data/`
is the store" is wrong for the entire Wave-3 fundamentals substrate.** The contract's `storage`
field is therefore typed to accept an R2 key prefix as a first-class location.

This lane also holds the one **non-destructive** restatement model in the repo:
`engine/fundamental_forensics/raw_ledger.py:117-122` defines an immutable append-only typed event
vocabulary — `AMENDMENT, COMPARATIVE_RECAST, RESTATEMENT, SOURCE_CORRECTION, PARSER_CORRECTION,
MAPPING_CORRECTION`. **That vocabulary is the target shape for every `REVISABLE_RELEASE` dataset
in this document**; it is not new work, it is one lane's work generalized.

**A standing divergence this contract must REGISTER, not resolve.** The same `detector_id` pairs
periods on three different bases: `scripts/build_fundamental_forensics.py:644-647` does a pure
fiscal-label match with no PIT gate at all; `engine/moat_falsifiers.py:144,162` does annual YoY
with a 120d gate that fails open on null `period_end`; `engine/fundamental_forensics/detectors.py:19-20,183-196`
requires the last two ANNUAL vintages with `MIN_PERIOD_GAP_DAYS=300`/`MAX_PERIOD_GAP_DAYS=430`
and returns `not_evaluable` otherwise. This is `DNR:HOLD-FF-DETECTOR-PERIOD-BASIS`, pinned by
`tests/test_forensic_detector_crosspin.py` §7 — **deliberately held**, because unifying them
silently republishes a live user-facing surface. Per §D10, the registry must be able to express
"these two are knowingly different" as a first-class state. Registering a divergence is
mandatory; resolving one is a product decision.

#### 4.5.5 Non-US fundamentals — one shape, six stores, no history

`data/china_fundamentals/fundamentals.parquet` (801 rows), `data/china_analyst/forecast.parquet`
(2,787 rows), `data/canada_fundamentals/fundamentals.parquet` (240),
`data/canada_earnings/earnings.parquet` (224), `data/hk_fundamentals/fundamentals.parquet` (75)
all share the `{ticker, payload, asof}` shape: one row per ticker, a JSON blob, and a single
mutable `asof` overwritten on every run (census fundamentals lane, VERIFIED by schema read).

**Delta.** `status: PRODUCED` for the stores; **`producer` for the Canada/HK three is UNVERIFIED**
— the census read their schemas but never opened the producing collector, so per §1.4 those rows
carry the uncertainty rather than a guessed module name. `temporal_profile` is `SNAPSHOT_SERIES`
with a retention of exactly one snapshot, i.e. no history at all — these datasets cannot answer
`known_at` and are FORBIDDEN from PIT reads. Identity: they key on `'000001.SZ'` / `'600519.SS'`
vendor-suffix tickers, not on the `CN-XSHE-000001` / `CN-XSHG-600519` stable IDs the CN spine
contract defines, so a join between CN fundamentals and CN price/spine data needs a mapping that
does not exist.

---

### 4.6 `earnings.*` — calendar and estimates

```
dataset_id  earnings.us.calendar
layer L1 · status PRODUCED · producer collectors/equity_earnings.py::fetch_earnings
storage data/earnings/earnings.parquet · format parquet
grain [ticker]  ← ONE row per ticker; this is the defect, see Delta
identity ticker : symbol
temporal_profile SNAPSHOT_SERIES (retention: one snapshot) · timezone UTC (as_of) / US market
        dates for next_date · frequency nightly
vendor nasdaq (unofficial public JSON) · endpoints
        api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD and
        api.nasdaq.com/api/company/{sym}/earnings-surprise (collectors/equity_earnings.py:4-7)
conflict_policy PRIMARY_ONLY · licensing vendor_terms_unofficial_scrape · version 1.0.0
freshness_sla 48h on a full-universe sweep (PROPOSED)
consumers engine/stock_fundamentals (Earnings panel), scripts/build_release_forecast.py
```

VERIFIED: 1,364 rows, columns `next_date, next_time, eps_forecast, surprises_json, as_of, ticker`
— all `large_string` except `eps_forecast` (`double`).

| column | dtype | unit | currency | nullable | null_reasons | notes |
|---|---|---|---|---|---|---|
| `next_date` | large_string | date | — | yes | `NOT_YET_AVAILABLE`, `NO_COVERAGE` | ESTIMATED, can move — disclosed on the page (`collectors/equity_earnings.py:19-21`) |
| `next_time` | large_string | enum | — | yes | | before/after market |
| `eps_forecast` | double | eps | USD | yes | `NO_COVERAGE` | **overwritten wholesale every sweep** |
| `surprises_json` | large_string | json | USD | yes | `NO_COVERAGE` | list of `{qtr, eps, consensus, surprise_pct}` |
| `as_of` | large_string | ISO8601 | — | no | | one sweep, one stamp |
| `ticker` | large_string | — | — | no | | |

**Delta — this is the leakage answer, and it is the largest unaddressed one in the estate.**

There is **no append-only, locally-timestamped consensus-before-earnings store anywhere in the
codebase.** `eps_forecast` is rebuilt fresh from the calendar dict on every run
(`collectors/equity_earnings.py:399-406`), keyed only on ticker. The census measured just 2
distinct `as_of` values across all 1,364 rows. So **any backtest joining `eps_forecast` to a past
earnings date is using today's most-recently-fetched estimate** — structurally identical to the
pre-panel `data/edgar/fundamentals.parquet` leak the codebase already diagnosed and fixed once
with `fundamentals_panel.parquet`, and never generalized to estimates.

The one place a pre-print consensus is retained historically is `surprises_json`
(`collectors/equity_earnings.py:184-194 _surprises()`), e.g. JPM `{'qtr':'Mar 2026','eps':5.94,
'consensus':5.49,'surprise_pct':8.2}` — sourced from Nasdaq's own **retrospective** surprise
table. It carries **no independently captured `known_at`**: we trust the vendor's post-hoc
labelling by fiscal quarter, not a timestamp proving we saw that consensus before the print.

Two further contract facts:

- **The collector's own docstring records the failure mode a contract would have caught.**
  `collectors/equity_earnings.py:23-30`: the no-arg path used to fall through to a 3-name demo
  default, "which pinned the nightly to a 3-ticker universe for six weeks (1361 of 1364 rows
  frozen at as_of 2026-06-19) while the store-level freshness tripwire read green off the 3 fresh
  rows." That is a `completeness` check masquerading as a `freshness` check — the exact reason
  §D8 separates the two families.
- **Producer/store schema drift, VERIFIED.** The producer writes a `surprises_as_of` column
  (`collectors/equity_earnings.py:404`) and the materialized store has no such column. Under the
  standing caveat (§0) I do not claim this proves the store is stale; I claim only that the
  producer and the store disagree, which is itself a `validity` violation the registry makes
  checkable.

`earnings.consensus.pit` is therefore declared **PROPOSED**: grain `[ticker, fiscal_period,
observed_at]`, `temporal_profile REVISABLE_RELEASE`, append-only, keep-FIRST on
`(ticker, fiscal_period, observed_at)`, `known_at := observed_at` stamped by US, not by the
vendor. The house already has the exact primitive to build it with — `engine/qbus.py`'s
keep-FIRST append and `collectors/cleveland_nowcast.py:15-16`, whose store is "keyed
(target_period, series, obs_date) with keep=\"first\" — a previously recorded observation is
never" overwritten. That store is genuinely PIT by construction, and it is the smallest working
example of the shape `earnings.consensus.pit` needs.

---

### 4.7 `macro.*` — observations with vintages

#### 4.7.1 `macro.fred.observations`

```
layer L1 · status PRODUCED · producer collectors/fred.py::FredAdapter.fetch
storage data/fred/{series}.parquet (166 files, VERIFIED) · grain [series, date]
identity series : fred_series_id
temporal_profile REVISABLE_RELEASE · timezone UTC · frequency mixed
vendor fred · endpoint https://api.stlouisfed.org/fred/series/observations
conflict_policy PRIMARY_ONLY · licensing public_domain · version 1.0.0
freshness_sla per-series, from frequency + release lag (see 4.7.3)
```

VERIFIED: `data/fred/CPIAUCSL.parquet` = 952 rows, columns `headline_cpi (double), date
(timestamp[us])` — note the column is renamed to the house alias at write time, so the FRED series
id lives in the FILENAME and the house name lives in the column.

| column | dtype | unit | nullable | null_reasons |
|---|---|---|---|---|
| `<house_alias>` | double | series-native (index/pct/level — declared per series) | yes | `NOT_YET_AVAILABLE`, `VENDOR_FAILED` |
| `date` | timestamp[us] | — | no | — |

**Delta.** `date` is the **reference period** the observation describes, in FRED's native
stamping. There is no release-date column, so this store carries the value but not the clock:
`temporal_profile: REVISABLE_RELEASE` declares `published_at` as owed and the store does not
carry it (`config/dataset_registry.yml:188-192`). Under §D3 this dataset therefore cannot answer
`known_at` and must RAISE on a PIT read; `macro.fred.vintages` is the PIT reader.

Second delta, upstream: `config.yml`'s `fred.vintage_series` **REPLACES** (does not extend)
`collectors/fred.py:42-62 DEFAULT_VINTAGE_SERIES`, so a one-line deletion there silently drops
series from the vintage store on the next keyed collect — it has happened twice (IC4WSA/CCSA
restored in #3710, then PPIFES/ECIALLCIV/ECIWAG in #3735; `config/dataset_registry.yml:193-198`).

#### 4.7.2 `macro.fred.vintages` — the PIT reader

VERIFIED: 10,103 rows, columns `series (large_string), period (timestamp[us]), value (double),
realtime_start (timestamp[us]), realtime_end (timestamp[us])`.

```
grain [series, period, realtime_start] · producer collectors/fred.py::fetch_vintages
endpoint ALFRED realtime (output_type=4, initial-release-only)
inputs [] · code_consumers collectors/fred.py::as_of_series, ::initial_release
```

**NO `inputs` EDGE, and the correction matters.** An earlier draft of this row (and of
`config/dataset_registry.yml`) declared `inputs: [macro.fred.observations]`. That edge is
FALSE: `fetch_vintages` never reads the observations store — `_vintage_series`
(`collectors/fred.py:153-174`) takes its series list from `config.yml` /
`DEFAULT_VINTAGE_SERIES`, and `_fetch_vintage_one` (`:177-195`) calls the ALFRED realtime
endpoint directly. The two are L1 **siblings** off one vendor API. A false edge is worse
than a missing one here, because §D9's entire lineage claim is "walk the registry DAG": an
operator chasing a bad row in `data/fred/CPIAUCSL.parquet` would have been pointed at a
point-in-time store that never touched that file, and a rebuild plan would have reported
the vintage refresh as "covered" by an observations backfill that did nothing for it.
`code_consumers` is likewise a rename, not a typo — `consumers` collided with
`Registry.consumers_of()`, which answers in dataset_ids off the `inputs` graph, and one
name for two different answers is how a lineage answer stops being trustworthy.

| column | dtype | meaning | nullable |
|---|---|---|---|
| `series` | large_string | FRED series id | no |
| `period` | timestamp[us] | the interval the observation DESCRIBES | no |
| `value` | double | the value in that vintage | yes |
| `realtime_start` | timestamp[us] | **`published_at` in ALFRED's vocabulary** — the date this vintage became knowable | no |
| `realtime_end` | timestamp[us] | | yes |

`known_at := realtime_start`. This is one of the six independent, locally-correct PIT
implementations §D0 names: it is correct, and it is unregistered and shares no vocabulary with
the other five.

**Delta, three parts.**
(a) **Coverage.** `collectors/fred.py:42-62` lists 26 ids; `config.yml:124` opens a
`vintage_series` list of 54. VERIFIED by me that the store carries exactly the smaller set —
`pd.read_parquet('data/fred_vintage/vintages.parquet')['series'].nunique()` = **26**, and
`'UNRATE' in set(...)` = **False**. The census's set-diff named the 28 configured-but-absent
series, including UNRATE, RSAFS, JTSJOL, ADPMNUSNERSA, USPRIV, USGOVT, CES0500000003, AWHAETP. A caller
asking `as_of_series('UNRATE', …)` gets an empty Series and `engine/pit.py` falls back to the
latest-revised reference value — a second, quieter leak layered under the first. Per §1.7, this
is a `completeness` check against the CONFIG, and it is exactly the kind a guard on
config-vs-code (rather than config-vs-disk) cannot see.
(b) **`fetch_vintages()` rewrites the parquet wholesale** (`config/dataset_registry.yml:236-237`),
so the append-only revision chain lives in ALFRED, not here. `SNAPSHOT_SERIES` semantics would be
a lie; the contract says `REVISABLE_RELEASE` with the chain held upstream.
(c) **Deliberate exclusions are correct and must be recorded as `NOT_APPLICABLE`, not as gaps.**
`collectors/fred.py:36-41`: "Market data (rates, OAS, VIX, FX, dollar) is never revised, so it is
deliberately excluded." DGS10/DGS2/DFF are therefore `NOT_APPLICABLE` for vintages. GDP/GDPC1 is a
genuine collection gap. VERIFIED:
`ls data/fred | grep -iE "^GDP|^UNRATE|^DGS(10|2)|^FEDFUNDS|^DFF"` returns exactly
`DFF.parquet, DGS10.parquet, DGS2.parquet, GDPNOW.parquet, UNRATE.parquet` — no quarterly GDP
level series and no monthly FEDFUNDS is collected at all, only the GDPNow nowcast and daily DFF.

#### 4.7.3 The release-lag model, and one census smell that must be dropped

For non-vintaged series, `engine/pit.py:110-140 DEFAULT_RELEASE_LAGS` carries a per-column
modelled business-day lag with the vendor provenance in a `note` — e.g. `headline_cpi`
`lag_bd: 8, lag_bd_measured: 32` with the note "#809 ALFRED median 45 cal d (~32 bd), the old ~8
bd prior was optimistic" (`engine/pit.py:114`).

**The census macro lane filed a smell claiming the optimistic prior wins at runtime. It is
wrong and must not enter the spec.** `engine/pit.py:181-191`:

```python
def _effective_lag_bd(spec: dict) -> int:
    lag = spec.get("lag_bd", 0)
    if spec.get("lag_bd_measured") is not None:
        lag = spec["lag_bd_measured"]
    if spec.get("lag_bd_learned") is not None:
        lag = spec["lag_bd_learned"]
    return int(round(float(lag)))
```

Precedence is documented at `engine/pit.py:106-107` — config override > learned > measured >
prior — and consumed at `:230` and `:323`. The measured lag wins. The residual PIT risk in this
lane is the two real findings: the live path defaults to `pit_basis=None`, and 28 config-declared
vintage series have no rows.

That first one is the section's real headline. `engine/inputs.py:137-151` documents
`pit_basis=None` as the byte-identical live default, and every live scored consumer calls
`build_features()` with zero arguments — `scripts/build_site.py:4664`, `engine/equity_alloc.py`
(5 sites), `engine/strategies.py:72`, `engine/masterminds.py:196`, `scripts/build_bonds.py:1381`,
`scripts/build_transmission.py:42`, the `calibrate_spvector*` family,
`scripts/refresh_regime_if_stale.py:163`, and ~10 more (census macro lane). The leak-free frame
exists — `engine/pit.py:1-40` describes itself as "the SHADOW accessor… It never touches the live
path" — and `pit_basis='release'` appears only in `scripts/build_regime_v2_pit.py:376`,
`scripts/validate_drawdown_risk_pit.py:172` and `scripts/shadow_pit_regime.py:199-200`.
**This is an adoption gap, not a capability gap.** A spec that proposes building PIT
infrastructure for macro would be rebuilding a thing that works.

---

### 4.8 `membership.*` — sector and theme

#### 4.8.1 `reference.ticker_sectors`

```
layer L1 · status PRODUCED · producer scripts/build_sector_map.py
storage data/breadth/ticker_sectors.parquet · grain [ticker] · identity ticker : symbol
temporal_profile SNAPSHOT_SERIES with retention 1  ← no as_of column at all
conflict_policy DOMAIN_AUTHORITY (GICS constituents > SIC text > SIC range,
        scripts/build_sector_map.py:3-13)
licensing derived_internal · version 1.0.0
AUTHORITY  display-only. scripts/build_sector_map.py:31-32 declares
        "FIREWALL: display-only, horizon_role=context, scored_path_surfaces=[]. MUST NOT feed
        board ordering / alert triage / entry-stack z-scores."
```

VERIFIED: 1,516 rows, columns `ticker, sector, source` — all `large_string`.

| column | dtype | domain | nullable |
|---|---|---|---|
| `ticker` | large_string | — | no |
| `sector` | large_string | 11 GICS-style strings, enumerated at `scripts/build_sector_map.py:24-26` | no |
| `source` | large_string | `gics_sp500` \| `gics_sp400` \| `gics_sp600` \| `sic_mapped` | no |

`source` is a per-row provenance column, which is the right shape and is rare in this estate.

**Delta.** (a) No `as_of` / `effective_at`. A sector reclassification overwrites history, so any
historical sector attribution is applied backward — look-ahead by construction. (b) A **second,
unpersisted** resolver exists: `engine/neuralweb/sector_map.py:56-140 build_sector_map(root)`,
with different source priority (it trusts `data/sector_holdings/{ETF}.parquet` as a coverage
extender where `build_sector_map.py` trusts SIC text). The census ran both and found 1,606 vs
1,516 tickers, 1,502 in common, exactly **1** true disagreement (`POOL`). They agree because both
lean on the same S&P constituents files, and **nothing enforces that** — neither imports the
other. (c) `DNR:KILL-PSS-F3-RESIDUAL`'s deviation note cites this map's coverage as
"`data/sector_holdings` resolved only 164/1300 → `data/breadth/ticker_sectors.parquet` 799/1300",
dated to the 2026-07-26 prereg. Those numbers are stale against the current build — the store now
resolves 1,516/1,516 by construction and `sector_holdings` is no longer a source at all
(`scripts/build_sector_map.py:3-13`). Cite the row count, not those figures. (The registry row is
cited by key, per house law; row numbers in `research/DO_NOT_REBUILD.md` shift on every append.)

#### 4.8.2 `membership.baskets.*` — and the PIT store that does not exist

```
dataset_id  membership.baskets.us | .hk | .canada | .intl | .china | .china_ths |
            .nasdaq | .russell
status PRODUCED (the CURRENT membership files) · format json
storage data/<suite>/membership.json
temporal_profile SNAPSHOT_SERIES with retention 1
```

The US file (`data/baskets/membership.json`, 46 baskets) carries per-member `added` / `removed` /
`rationale`, including exit rationale on all 15 removed rows (census taxonomy lane, VERIFIED).
HK/Canada/Intl share the construction via `engine/baskets_region.py:92-109`
(`eff_start = max(first_tape, added)`, `removed <= last_d` exclusion). `engine/basket_index.py:33`
states the honest limit itself: "like the baskets themselves the membership is ~hindsight-curated
… a descriptive consolidated tape, not an out-of-sample backtest."

**Nasdaq and Russell are structurally worse and must be contracted separately.** Their member
objects are bare `{ticker, name}` with no `added`/`removed`/`rationale` and only a single
top-level `as_of` (census taxonomy lane, VERIFIED). Any historical use of
`data/baskets_nasdaq` / `data/baskets_russell` — consumed by `engine/cycle_pattern/registry.py`
and `engine/nasdaq_internals.py` — applies today's composition uniformly across all history with
**zero** windowing. This is the clearest unconditional look-ahead in the taxonomy layer, and the
contract's job is to make a uniform cross-suite reader impossible: a reader that treats all eight
suites alike silently gets full look-ahead on two of them.

**`membership.baskets.history` — the PIT dataset — is PROPOSED, not produced.**
`engine/basket_membership_pit.py` is fully implemented: `ALL_SUITES` at `:97-99`
(`baskets_china_ths`, `baskets_china`, `baskets`), append-only keep-FIRST on
`(snapshot_date, basket_id, ticker)`, content-dedup by `members_sha` over normalized
`(basket_id, ticker, added, removed)` tuples so a cosmetic re-serialization is not mistaken for a
change, fail-closed per-suite lane gating, and a reader contract that "ALWAYS reports which basis
it answered on". Its target parquet does not exist for ANY suite: the census ran
`find data -iname '*membership_history*'` across the whole 5.3 GB tree and got zero results, and
checked all eight suites individually — all MISSING. The only raw evidence is two dated JSON
snapshots under `data/baskets_china_ths/snapshots/`.

**So `members_asof()` falls back to current membership with `pit=False` for every suite on every
date, today** — the exact look-ahead the module was built to prevent is the live behaviour.
`engine/basket_membership_pit.py:76-85` anticipates precisely this: "A consumer that silently
treats a fallback answer as point-in-time is exactly the look-ahead bug this store was built to
end, so the flag is not optional metadata: it is the answer."

**Contract consequence, and it is the general rule this document takes from the case:** a
`SNAPSHOT_SERIES` dataset whose history store is empty must return its fallback flag *in band* —
`pit=False` alongside the value — and a consumer that ignores it is the violation. `status` alone
cannot express "the code is shipped and the store is empty", which is why §1.4 keeps the wiring
state in `producer` + `notes` until it earns its own enum.

#### 4.8.3 `membership.themes` — binary, unweighted, and the weighted design is unbuilt

`data/themes_heatmap/themes_tree.json` is the shipping surface: each subsector's `members` is a
flat list of ticker strings — no weight, no confidence, no per-member date, no rationale. The
census scanned the full tree: 941 unique tickers, 434 (46.1%) in more than one subsector, MSFT in
66, AMZN in 56, GOOGL in 55, NVDA in 38. `engine/company_theme_exposure/contracts.py:33`'s closed
`_EXPOSURE_ITEM_KEYS` is `{theme_id, name_en, name_zh, basket_id, mapping_qualifier}` — no weight
field — and the module declares itself "a membership projection, not a thematic score".

The correctly-designed alternative exists in code and has **zero rows**:
`engine/theme_graph/store.py:47-63` defines `NODE_COLUMNS`/`EDGE_COLUMNS`/`EVIDENCE_COLUMNS`
including `valid_from`/`valid_to`, `evidence_time`, `belief_time`, `confidence_basis`,
`source_class`, `evidence_refs`, and three weight axes `economic_share`/`trading_beta`/
`attention_share` with `*_formula_id` and `*_display` siblings — all declared NULL by W1b design,
to be measured in W2. `data/theme_graph/` does not exist in the materialized tree.

**Delta.** `membership.themes.graph` is `PROPOSED` and is the target schema for weighted
exposure. Do not cite it as an existing source. Note also that `config/theme_graph_identity_breaks.yml`
introduces the third id convention (§4.1) — reconciling it to `SEC:`/`listing_key` is §D12
phase-1 work, not theme work.

---

### 4.9 `options.*` — chains and contracts

```
dataset_id  options.chains.polygon
layer L1 · status PRODUCED
producer  collectors/polygon_options.py::PolygonOptions.snapshot, driven by
          scripts/build_polygon_gex.py::accrue — explicitly NOT in the collect.py adapter
          registry (collectors/polygon_options.py:93-96)
storage   data/polygon_gex/chains/{session_date}.parquet (raw per-strike, all underlyings)
          + data/polygon_gex/summary_{TICKER}.parquet (1 row/day)
grain     [asof, strike_ticker]
identity  strike_ticker : polygon_occ  (underlying : symbol as the join to equities)
temporal_profile BARS (one EOD chain snapshot per session)
timezone  America/New_York (asof = NYSE session date) · frequency 1d, gated by
          nyse_calendar.is_session() (scripts/build_polygon_gex.py:141)
adjustment {basis: raw, vintage: n/a}
vendor polygon / massive.com · endpoint options snapshot (per-contract OI + IV)
conflict_policy PRIMARY_ONLY · version 1.0.0
AUTHORITY  display/research only — collectors/polygon_options.py:13-16 states the dealer
          long-call/short-put SIGN is an assumption and this is "a VOL-REGIME + LEVELS MAP,
          not alpha"
consumers engine/gex_engine.py, engine/options_skew.py, engine/options_ivspread.py,
          engine/options_hub.py, scripts/build_index_gex_history.py
```

VERIFIED (`data/polygon_gex/chains/2026-07-09.parquet`, 180,309 rows):

| column | dtype | unit | currency | nullable | null_reasons | notes |
|---|---|---|---|---|---|---|
| `underlying` | dictionary<string> | — | — | no | — | the input symbol, straight passthrough |
| `strike_ticker` | large_string | — | — | no | — | Polygon `O:`-prefixed variable-root OCC, e.g. `O:SPY260710C00525000` |
| `expiry` | timestamp[us] | — | — | no | — | |
| `K` | float | strike | USD | no | — | |
| `T` | float | years | — | no | — | `(expiry − asof).days / 365.0` (`collectors/polygon_options.py:71`) |
| `is_call` | bool | — | — | no | — | |
| `oi` | float | contracts | — | no | — | filtered to `> 0` at ingest (`:64`) |
| `iv` | float | ratio | — | yes | `VENDOR_FAILED`, `NO_COVERAGE` | |
| `gamma` / `delta` | float | per-contract greek | — | yes | `NO_COVERAGE` | **vendor-supplied**, see delta |
| `volume` | float | contracts | — | yes | `NO_COVERAGE` | |
| `spot` | float | quote_currency | USD | no | — | 15-min-delayed stock snapshot (`:66-68`) |
| `asof` | timestamp[ms] | — | — | no | — | **NYSE session date** — see delta |

**Delta, five items.**

1. **Contract identity has four mutually-incompatible encodings with no crosswalk.**
   `engine/options_focused_quote.py:641-646` builds fixed-width OCC-21
   (`f"{root:<6}{expiration:%y%m%d}{right}{strike_millis:08d}"`); this store persists Polygon's
   raw variable-root `O:` ticker; `engine/options_focused_quote.py:636-638` mints a synthetic
   `contract:uchain:<sha256>` over `root|expiration|right|strike`; and
   `engine/options_structure.py:249-261` keys on a bare `(root, strike, exp, right)` tuple with a
   display-only symbol synthesized afterwards at `:351`. §D2's `OPT:<listing key>:<YYYYMMDD>:<C|P>:<strike×1000,8 digits>`
   is the canonical form and all four become aliases.
2. **Field-name drift occurs INSIDE single files**, not just across them: `options_hub.py` 47×
   `expiration` + 5× `expiry`; `options_nbbo_cohort.py` 20/16; `options_structure.py` 3/14;
   `options_stamp.py` 2/15 (census options lane). And the right/type fact has four encodings —
   `"C"/"P"`, `"CALL"/"PUT"`, `is_call` bool, `option_type` string — while the standard OPRA
   `cp_flag` appears **zero** times anywhere.
3. **Two greeks exist per contract and nothing reconciles them.** `collectors/polygon_options.py:83-88`
   persists Polygon's own gamma/delta; `engine/gex_engine.py:62-70` recomputes gamma from scratch
   via `engine/greeks.py::bs_greeks` using only `iv/oi/K/T/is_call`, ignoring the stored columns.
   The contract must name which column is authoritative per consumer, or a future reader gets a
   different number depending on which door it came in.
4. **The model inputs are hardcoded constants.** `r` defaults to 0.043
   (`collectors/cboe.py:230`, `scripts/build_polygon_gex.py:109`) regardless of tenor or date;
   `q` comes from a four-name dict (`collectors/cboe.py:142
   GEX_Q = {'_SPX': 0.013, 'SPY': 0.013, 'QQQ': 0.006, 'IWM': 0.013}`) and is 0.0 for every
   single name. Meanwhile `data/massive_options_day/_effr_dff.parquet` sits inside the same store
   and is not wired in. `engine/gex_engine.py:28` also fixes `contract_multiplier=100.0` with no
   per-contract override anywhere, so post-merger non-standard OCC series are silently mispriced.
   These belong in the contract as declared `assumption` fields, not as defaults buried in three
   modules.
5. **The `asof` column is the reason this contract exists.**
   `scripts/migrate_polygon_gex_session_stamps.py:1-20` records that `build_polygon_gex.accrue`
   stamped `datetime.now(timezone.utc).date()` — the RUN date, not the session — so the write-side
   `is_session` gate refused every Saturday-UTC run, i.e. every Friday-evening ET accrual, which
   is why Fridays were missing from the store. The migration reclassified 42 files → 29 sessions:
   24 redated clean, 13 collision duplicates removed, 5 quarantined because their `spot` column
   was a live intraday/pre-market tape contaminating every spot-derived field
   (`net_gex_bn`, `gamma_flip`, `dist_to_flip_pct`, `magnets`, `max_pain`);
   `scripts/quarantine_polygon_gex_20260807_preopen.py:1-18` separately quarantines 2026-08-07 as
   an unrecoverable gap. **The contract clause: a bar/snapshot's `asof` is the SESSION it
   describes, resolved through the exchange calendar, never the writer's wall clock** — the same
   law `DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY` states for identity, applied to time. The
   verification method is also worth pinning: "SPY alone called the 08-06 file 0.175% fine while
   59% of its names disagreed" — a single-name spot check cannot validate a whole-chain snapshot's
   timestamp.

Two sibling stores need rows and cannot honestly get `PRODUCED` ones yet: `data/options_flow` and
`data/options_entry`/`data/options_exit` were never opened by the census (§1.4), and
`data/thetadata_eod` contains only `_backfill_state.json` + `_manifest.json` with zero ticker
parquets — it is produced out-of-band from a separate ops worktree per
`research/THETADATA_OPS_RUNBOOK.md`, and no reader module was found. All three are `PROPOSED`.

---

### 4.10 `news.items` — the event store

```
dataset_id  news.items
layer L1 · status PRODUCED · producer engine/qbus.py::ingest_batch
        (written from engine/financial_news.py, engine/macro_news.py, engine/china_news_intel.py,
         engine/news_vector.py, engine/news_events.py, engine/communique_diff.py,
         engine/missing_tape_attention.py)
storage data/qbus/items.parquet · format parquet · SCHEMA = "qbus.v1" (engine/qbus.py:38)
grain   [item_id]  — append-only, keep-FIRST (engine/qbus.py:11-14)
identity item_id : qbus_item_hash;  event_key : qbus_event_cluster
temporal_profile EVENT · timezone UTC · frequency continuous
conflict_policy PRIMARY_ONLY · version 1.0.0
AUTHORITY  "LEAF · CONTEXT-ONLY · DETERMINISTIC… nothing in the scoring path imports it"
        (engine/qbus.py:3-4)
consumers engine/news_events.py:711, engine/financial_news.py:798, +6 desks
```

VERIFIED: 3,986 rows; columns exactly as declared at `engine/qbus.py:60-76`.

| column | dtype | unit | nullable | null_reasons | notes |
|---|---|---|---|---|---|
| `item_id` | large_string | — | no | — | `qkernel.item_id(source,url,title)` — keep-FIRST key |
| `event_key` | large_string | — | yes | `NOT_YET_AVAILABLE` | assigned by clustering, may be unset before a pass |
| `desk` | large_string | — | no | — | emitting desk |
| `source` | large_string | — | no | — | |
| `source_tier` | int64 | ordinal 0–3 | no | — | `qkernel.source_tier` |
| `lang` | large_string | enum | no | — | `en`\|`zh`\|`auto` — drives the norm/shingle branch |
| `url` / `title` | large_string | — | no | — | |
| `body_sha256` | large_string | hex | yes | `NO_COVERAGE` | `""` when there is no body |
| `seendate` | large_string | ISO8601 | no | — | publisher/crawl timestamp, PIT-cleaned by the desk = **`published_at`** |
| `_crawled_at` | large_string | ISO8601 | no | — | when WE first crawled = **`ingested_at`** |
| `timestamp_quality` | large_string | enum | no | — | see below |
| `entities` / `themes` | large_string | comma-joined | yes | `NO_COVERAGE` | lists flattened for parquet, re-split on read |
| `importance_raw` | double | unitless | yes | `NO_COVERAGE` | pre-calibration, display/context |

**`timestamp_quality` is a sixth temporal dimension the rest of the estate lacks, and the
contract format should adopt it.** `engine/qbus.py:45-55` enumerates:
`CRAWL_BOUNDED` (no publisher stamp — no embargo) · `PUBLISHER_STATED` (+15 min, reject
`pubDate < crawl−48h`) · `DISCLOSURE_DATE` (EDGAR, +1 business day) · `EVENT_DATE`
("NEVER an entry anchor") · `SNAPSHOT_DATE` (display-only) · `CORRUPTED` (blocked + alert). §D3
says which clock a value is; this says **how much to believe it**. Every `EVENT`-profile dataset
should carry it.

`engine/qbus.py:5-6` also states a discipline the whole Data OS should inherit: "NO ambient-time
calls in library code — every `asof` is passed in by the caller."

**Delta.** (a) **Three non-interoperating event-identity primitives coexist.**
`engine/qkernel.py:193-204 event_id()` is per-`(title, domain)` **by design** — "Two mirrors of
the same story on different hosts get DIFFERENT ids (cross-host collapse is the job of
qbus.event_key, not of event_id)". `engine/news_common.py:108-113` delegates to the same basis.
So `data/news/event_log.parquet` (`engine/news_event_ledger.py`),
`data/news_vector/events.parquet` and `data/china_news_vector/events.parquet` all carry
**per-article** identity, and only `qbus.event_key` clusters cross-source (union-find on shared
entity/theme + a 3-day window + title-shingle Jaccard ≥ 0.6, `engine/qbus.py:176-236`). A spec
that says "event_id exists" without that distinction overstates what most of the news surface
has. (b) There is **no embedding store anywhere.** VERIFIED by me:
`data/news_vector/events.parquet` (60 rows) is
`event_id, first_seen_utc, seendate, title, url, domain, theme, source_tier, scheduled_ref` and
`data/china_news_vector/events.parquet` (1,333 rows) adds
`summary, source, baskets, tickers, score, sentiment` — **neither has a float-array column**, and
`engine/news_vector.py:45-47` stubs LLM extraction off (`enabled:false AND llm_extract:false`). `vector` is a naming collision across four unrelated `data/`
directories (`vector`, `spvector`, `news_vector`, `china_news_vector`), none of which contains
embeddings; the contract format reserves `*vector*` for literal embedding stores. (c)
`collectors/china_news.py:24-29` and `collectors/china_news_wire.py:14-16` persist **only**
aggregate daily tone numbers — the article-level China rows exist solely in
`data/china_news_vector/events.parquet`, built at build time by `engine/china_news_intel.py`, not
by the nightly collector. A registry that assumes "collectors write the canonical store" misses
this pattern; `producer` must name the build-time module.

The related credibility artifact, `data/narrative_flare/source_registry.json`
(`engine/source_registry.py`), is the cleanest reusable template in the repo for derived
intelligence: an id, a versioned Beta-Bernoulli score `(hits+2)/(calls+7)`
(`engine/source_registry.py:134`), a claim-register-then-resolve lifecycle at D+20 NYSE
trading days, and an explicit authority block at `:54-60` with `tier='display'`,
`may_rank=False`, `may_gate=False`, `may_size=False`, `may_escalate=False`. Any new
`INTELLIGENCE`-profile dataset should copy that block verbatim.

---

## 5. The migration ledger

What each contract above says is owed, ordered by §D12 phase. Nothing here is scheduled by this
document; it is the delta made countable.

| # | Owed | Datasets | Phase | Precondition |
|---|---|---|---|---|
| M0 | Commit `lib/dataos/`, `config/dataset_registry.yml`, `tests/test_dataos_*.py` | all | 0 | Resolve ownership with the sibling lane first (§1.8) |
| M1 | Widen `adjustment:` from scalar to `{basis, vintage, vintage_column}` in the 3 seeded rows | `equity.bars.daily.*` | 0 | none |
| M2 | Registry validation: quantity column without `unit`; `PRODUCED` row whose `storage` path does not exist | all | 0 | M0 |
| M3 | `reference.security_master` + `reference.vendor_aliases` produced; the ten identity seams resolved against them | all entity-keyed | 1 | none |
| M4 | Basis-suffixed reader shim + guard forbidding new unqualified `close` | 6 bar datasets, 135+157 readers | 2 | M1 |
| M5 | `reference.corporate_actions` (ex-date, type, factor) — unblocks `adjustment.vintage` and §D4's V2 | all adjusted price sets | 2 | M3 |
| M6 | `completeness` check on `data/massive_stock_day` manifest-vs-disk (19,133 vs 20,476 today, 20,478 at census; 471 of ~1,255 sessions) | `.massive` | 2 | M0 |
| M7 | Session/venue enum on `quotes.live`; separate the closing auction from the consolidated last print | `quotes.live` | 3 | calendar service |
| M8 | Contract + validators on the ten datasets here; the `(1+ret.fillna(0)).cumprod()` detector; the volume-unit detector | all | 4 | M0 |
| M9 | Fail-closed PIT readers: `macro.fred.observations`, `fundamentals.us.statements_annual`, the six `{ticker,payload,asof}` stores | 9 datasets | 5 | none |
| M10 | `earnings.consensus.pit` produced (append-only, our own `observed_at`) | `earnings.*` | 5 | none |
| M11 | `membership.baskets.history` backfilled so `members_asof()` stops answering `pit=False` | 8 suites | 5 | none |
| M12 | Receipts joined to their datasets via `dataset_id`; generalize the intraday receipt and the R2 GitHub-provenance block | all | 6 | M0 |

On M12: `engine/capital_structure/share_count_r2_conformance.py:750,766-767` already REQUIRES a
provenance block `{repository, workflow_ref, run_id, run_attempt, commit_sha, event_name, actor}`
with a 40-hex commit-SHA regex. That is the house pattern; it stops at one subsystem. Meanwhile
`data/massive_stock_day/_manifest.json` carries a store name and a wall clock and no producing-code
version, and `data/index_gex_history/_manifest.json` names `"engine": "engine.gex_engine.compute_gex"`
with no version of it — so for those stores "the number changed" cannot be distinguished from
"the code changed" (census PART 1, VERIFIED).

---

## 6. What this document deliberately does not contract

- **The user-data plane.** `public.portfolio_positions`, `watchlists`, `watchlist_symbols`,
  `alerts`, `favorites` live in Supabase under RLS, owned by the Terminal
  (`charting-app/supabase/migrations/0001_init.sql:2-6`: "The USER-DATA plane only… Market data,
  signals, regime, and backtests are NOT stored here"). The ownership registry already assigns
  `user_state_owner: terminal_supabase`. Market-data patterns (filesystem parquet, R2 CAS,
  append-only receipts) do not apply to it, and this document must not pretend otherwise. The
  completeness critic found that `portfolio_positions`' `CREATE TABLE` exists in no merged branch
  of either repo — that is a real finding and it belongs to the Terminal's lane, not to this one.
- **A second control plane, authority map or strategic state.** Prohibited cross-repo
  (`duplicate_control_planes`, Mastermind `AGENTS.md`) and restated in this repo's CLAUDE.md.
- **A migration runner.** There isn't one, and saying "add a migration" would be fiction:
  `scripts/deploy/0007_support_email.sql:5-6` records "APPLIED MANUALLY via the Supabase SQL
  editor (the 0005/0006 precedent — there is no migration runner on the render path)". The three
  evolution mechanisms actually in use are manual SQL apply with the repo file as the replay
  record, a new `_vN` schema file with the old one retained live, and a bespoke one-shot Python
  migration per store (`scripts/migrate_narrative_ttl.py`,
  `scripts/migrate_polygon_gex_session_stamps.py`, `scripts/migrate_source_manifest_to_jsonl.py`,
  `scripts/migrate_track_record_keys.py`). The `version:` field is the declaration; nothing yet
  enforces that a bump accompanies a meaning change.
- **A feature store.** One already exists, scoped to the market-memory replay subsystem:
  `engine/neuralweb/market_memory.py:147,151` pins `FEATURE_REGISTRY_VERSION`,
  `SOURCE_REGISTRY_VERSION` and a `FeatureSpec` NamedTuple ("Frozen dependency and value contract
  for one decision-time feature") with `domain, unit, value_schema, required_source_roles,
  allowed_source_roles, allowed_availability_classes, transform_version`, frozen into
  `_FEATURE_REGISTRY_V1` at `:185` and exported as `CANONICAL_FEATURE_REGISTRY` at `:335-339`.
  Its `availability_classes {intraday, session_close, scheduled_release, revision}` vocabulary is
  something the rest of the repo lacks. §D10's verdict stands — no new feature store — and the
  extension work is promoting that vocabulary, not building beside it.
- **A caching or queueing tier.** Redis is not used anywhere: `grep -rl 'import redis|redis.Redis(|REDIS_URL|from redis' --include='*.py' .`
  returns 0 files, and the ~50-file substring hit set resolves to `redistribution` /
  `redistribution_class` (census storage lane, VERIFIED). The masterplans reject it by name
  (`research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md:44` "Postgres/TimescaleDB/Redis/… a decade of ops
  debt… Boring wins"; `research/BREATHING_PLATFORM_MASTERPLAN_BY_FABLE.md:151` "no
  DuckDB/Postgres/Redis anywhere"). Any spec section written against a Redis footprint would be
  building on a phantom.
- **Metric/indicator definitions.** That is §D10 and `engine/canon.py`'s lane, and the census's
  headline count there does not survive scrutiny: `engine/canon.py` (522 lines, 22 top-level
  defs) defines **no `atr` and no `realized_vol` at all** — VERIFIED,
  `grep -cE "^def (atr|realized_vol)" engine/canon.py` = **0** — so ~23 of the cited "duplicates"
  (13 `atr` defs in 11 files, 10 `realized_vol` defs in 10 files) are canon GAPS with no
  canonical referent to violate, not violations of it,
  and on an 8-site sample 5 definers computed a genuinely different quantity
  (`engine/rank_momentum_signals.py:143 _connors_rsi` is a composite; `engine/ohlc_reconstruct.py:82
  atr_proxy` is a deliberately close-only, deliberately-wide proxy; `engine/neuralweb/chart_perception.py:487
  _atr_word` maps a number to a word). Corrected counts: 103 files import canon (55 in production
  trees), 56 production files define an `rsi`/`atr`/`realized_vol`-named function, 6 do both. Do
  not call a legitimate difference a violation.
- **The cross-repo ingestion boundary.** 17 files under `charting-app/ingest/` hardcode
  `Path("/Users/chriswong/Documents/Cluade/Macro Dashboard")` and write results back into Macro's
  `data/` tree (`charting-app/ingest/collect_us_deep.py:37-39`), bypassing `collectors/base.py`'s
  Adapter/ColumnContract contract entirely. That is a real boundary to formalize or deprecate,
  and it is a cross-repo product decision, not a data-contract one.

---

## 7. Citation census

**224 distinct `file:line` citations across 137 distinct files** (a range such as `:644-647`
counts once), spanning `collectors/`, `engine/`, `scripts/`, `lib/`, `config/`, `contracts/`,
`app/`, `admin/`, `research/`, `tests/`, `.github/workflows/`, and the two sister repos. Counted,
not asserted:

```
$ python3 -c "
import re
t=open('research/MASTERMIND_DATA_CONTRACTS.md').read()
p=re.compile(r'(?<![\w/.-])((?:[\w./-]+/)?[\w.-]+\.(?:py|yml|yaml|json|md|sql|ts|tsx|js))\s*:\s*(\d+(?:\s*[-,]\s*\d+)*)')
pairs={(f,l) for f,l in p.findall(t)}
print(len(pairs), 'citations /', len({f for f,_ in pairs}), 'files')"
224 citations / 137 files
```

The ten most-cited files are `lib/dataos/registry.py` (11), `config/dataset_registry.yml` (9),
`lib/dataos/nulls.py` (7), `engine/qbus.py` (7), `collectors/china_tushare_spine.py` (7),
`collectors/equity_earnings.py` (6), `collectors/base.py` (6), `engine/pit.py` (5),
`collectors/polygon_options.py` (4), `scripts/build_polygon_intraday.py` (4).

In addition the document quotes **fifteen commands with their output**: five `pq.read_schema`
batches (the four US bar stores; eight further stores; the CN and HK stores; the two `*_vector`
news stores), three cross-repo `grep -rlnE` lot-size sweeps, the 22-site `cumprod` grep, the HON
four-store price read, the `git status --porcelain` untracked listing, the two reader-count
greps, the `ls | wc -l` / `du -sh` store-size table, the `vintages.parquet` series-count read, and
the `ls data/fred | grep` rate-series listing.

Every quantitative claim is one of three kinds, and each is labelled where it appears:

1. **Measured by me in this session** — the four-store schema read, the HON 2025-09-25 four-value
   read, the 22-site `cumprod` count and its 2 guarded sites, the 135/157 reader counts, the
   three-repo lot-size absence, the CN/HK store schemas and file counts, and the eight parquet
   schema/row-count reads in §4.
2. **Measured by a census lane and cited to the lane plus its own `file:line`** — the four-store
   coverage asymmetry, the `massive_stock_day` manifest numbers, the 28 missing FRED vintage
   series, the 46.1% multi-theme membership scan, the `fillna(0)` 15-site adjudication, the
   `membership_history.parquet` absence across all eight suites.
3. **Explicitly corrected against an earlier draft** — the four-vs-three price stores, the
   `(basis, vintage)` pair, the `data/stocks` open consequence, the ten identity seams, the canon
   gaps-vs-violations distinction, the `fillna(0)` class clause, the Redis footprint, and the
   `engine/pit.py` lag-key smell. Each of these says so in place.

Two claims in this document are marked INFERRED at the point of use and are not measured:

- the producer attribution for `data/china_stocks_raw` (§4.2.5) — the census gave it as an OR of
  two modules and opened neither, so the contract carries the uncertainty rather than a guess;
- that Polygon's `adjusted=true` aggregates parameter is split-only rather than total-return
  (§4.3 delta (e)) — vendor documentation, asserted nowhere in any of the three repos.

One claim that a reader may expect and will not find: this document does **not** attribute the
HON divergence to any specific corporate action. Naming one would require an ex-date and a
factor to check against, and §4.2.6 is the finding that no such store exists. The measurement
stands on its own; the mechanism is deliberately left unclaimed.
