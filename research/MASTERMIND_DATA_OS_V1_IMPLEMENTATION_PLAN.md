# Mastermind Data OS — V1 implementation plan (2026-08-12)

The executable half of the Data OS wave. The pinned architecture is `DESIGN_SPEC` §D0–§D12
(identity, temporal, price basis, contracts, nulls, conflict, quality, lineage, feature-store
verdict, non-goals, order of work). **This document does not relitigate those decisions.** It
says what has already been built, what is left, in what order, sized so one spawned session can
finish one task, and with an observable "not done unless" for every one.

Two standing conventions apply to every line below.

- **VERIFIED means someone ran it.** A claim with a command and its output, or a
  `path/to/file.py:LINE`, is verified. A claim without one is marked INFERRED and is not
  allowed to carry a task's acceptance criterion.
- **Standing adjudications are cited by key**, never by row number:
  `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` (`research/DO_NOT_REBUILD.md:130`),
  `DNR:HOLD-FF-DETECTOR-PERIOD-BASIS` (`research/DO_NOT_REBUILD.md:169`),
  `DNR:KILL-PSS-F3-RESIDUAL` (`research/DO_NOT_REBUILD.md:77`). Row numbers shift on every
  append.

### Evidence warning that binds this whole document

The materialized-data checkout at `/Users/chriswong/Documents/Cluade/Macro Dashboard` is itself
in a broken git state — detached HEAD, an unresolved merge conflict in `config/dag.yml`, 4,560
dirty entries, HEAD at `5c90bf15229` (2026-07-14) against the code worktree's `ff88ab548a9`
(2026-08-12), ~1,119 commits behind (census PART 2 / smells lane, VERIFIED). **Every staleness
claim in this plan that rests on a file mtime or a `git log` from that checkout is therefore
labelled NEEDS-CORROBORATION and may not be used as a task's acceptance criterion.** The correct
first move for any freshness task is to establish an observation point that does not depend on a
hand-maintained checkout being clean (task DOS-4.3).

A second, sharper instance of the same trap: reading `data/prophet/ledger.jsonl` from that
checkout returns a header-only stub with zero rows, while `git show HEAD:data/prophet/ledger.jsonl`
in the code worktree returns 28 real rows (VERIFIED here: `git show HEAD:data/prophet/ledger.jsonl
| grep -c '^{'` → `28`). A naive "is the ledger empty" check returns the *opposite* of the truth
depending only on which checkout you open.

---

## §0 ACCEPTANCE GATES

House law: a build plan carries its gates at the top, phrased so a reviewer can refuse the work.
These bind the **wave**, not any single task; per-task gates are in §3.

**G0 — The foundation is committed before anything else is written.**
Not done unless `git ls-files lib/dataos/ config/dataset_registry.yml tests/test_dataos_*.py`
returns all thirteen paths and `git status --porcelain` shows none of them as `??`. Today it
returns empty for `lib/dataos/` (VERIFIED, §1). An untracked implementation cannot run in CI, so
every spec written against it is unfalsifiable, and `scripts/worktree_gc.py` protects dirty trees
but nothing protects untracked-only work from a `git clean`.

**G1 — Every registry row is true on the day it lands.**
Not done unless every `status: PRODUCED` row's `storage:` path exists on disk *and* its `producer:`
is a real symbol resolvable by grep, verified at authoring time and re-verified in the PR body with
the command output pasted. `lib/dataos/registry.py:23-26` states the rule this enforces: a registry
listing a dataset that does not exist is worse than no registry, because the next session builds
against it. Anything unverified enters as `status: PROPOSED` or does not enter. Five census dataset
rows were written from filename inference alone (census PART 1, "Uncited / self-admittedly
unverified assertions") — those five are the exact rows this gate exists to keep out.

**G2 — No guard ships without a mutation proof.**
Not done unless the PR body shows the new check FAILING on a deliberately broken input and passing
on the fixed one, in the same run. A guard that has never been observed red is a guard nobody has
shown can see anything (house trap: *registering a guard does not prove the guard is green*).

**G3 — No unification of a knowingly-held divergence.**
Not done unless the PR states, by key, that it does not touch `DNR:HOLD-FF-DETECTOR-PERIOD-BASIS`
(three period bases under four shared `detector_id`s, deliberately HELD because unifying them
silently republishes a live user-facing surface) or any other HOLD row. §D10 requires the registry
to express "these two are knowingly different" as a first-class state; **registering a divergence
is mandatory, resolving one is a product decision**.

**G4 — No new store, no second control plane.**
Not done unless the diff introduces zero new persistent stores beyond those named PROPOSED in the
registry, and adds no `strategic_state`/`authority_map`/control-plane analogue in this repo
(`duplicate_control_planes` is a standing cross-repo prohibition; the Executive OS state lives in
the Mastermind repo, not here). §D9's lineage is "walk the registry DAG, read the receipts" — **no
new store**.

**G5 — Every claim in a delivered doc or docstring is checkable.**
Not done unless each factual sentence carries a `file:LINE`, a command with output, or an explicit
INFERRED label. This is the same property the project exists to give the data.

**G6 — Nothing user-facing changes without the design lane.**
Not done unless any task touching a rendered surface (the Terminal `ADJ` chip, a site basis
disclosure, a degradation state) routes through `docs/DESIGN_DOCTRINE.md` + the frontend-design
skill, and shows light/dark/zh crops in the PR. Falsifier and refutation language is never
front-facing.

**G7 — The wave is measured by consumption, not by existence.**
Not done unless each phase's exit criterion names a *consumer that changed behaviour*, not a module
that exists. The single most instructive in-repo failure here: `engine/canon.py:228-236` documents
its own sector-macro-beta fix as a "SHADOW artifact (wired, NOT consumed this wave)", and the
physically-impossible `XLC: 1.0` prior it was built to retire is still live at `config.yml:2994`,
still read by `engine/conditions.py:1199-1211`, still feeding the user-facing heat penalty at
`engine/playbook.py:666` (census metrics lane, VERIFIED). A correct, tested, documented fix that
nothing consumes changed nothing.

---

## §1 Phase 0 — DELIVERED (this session). Do not re-plan it.

`lib/dataos/` exists, `config/dataset_registry.yml` exists, and five pytest suites exist and pass.
This is the foundation the rest of the plan extends. It is described here as delivered work, with
one caveat that is itself gate G0: **it is untracked.**

```
$ git status --porcelain
 M .github/ci/legacy-jobs.yml
 M .github/workflows/ci.yml
?? config/dataset_registry.yml
?? lib/dataos/
?? tests/test_dataos_identity.py
?? tests/test_dataos_nulls.py
?? tests/test_dataos_price.py
?? tests/test_dataos_quality.py
?? tests/test_dataos_registry.py
?? tests/test_dataos_temporal.py
```
(VERIFIED, code worktree, 2026-08-12. `git ls-files lib/dataos/` → empty. This closes the
completeness critic's open question about `tests/test_dataos_quality.py`: it *is* present and *is*
listed by git.)

### 1.1 What each module owns

| Module | Lines | §D | Owns |
|---|---|---|---|
| `lib/dataos/__init__.py` | 146 | D0 | The thesis + the flat public surface (`__all__`, 60 names) |
| `lib/dataos/identity.py` | 726 | D2 | Listing keys, `ISS:`/`SEC:` ids, option/future/index/FX ids, CN board classification, CN/HK symbol normalization, the **time-scoped** vendor alias table |
| `lib/dataos/temporal.py` | 292 | D3 | Eight named clocks, six temporal profiles, the fail-closed PIT law |
| `lib/dataos/price.py` | 265 | D4 | The `{field}_{basis}` naming law, `AMBIGUOUS_NAMES`, the measured `KNOWN_STORE_BASES` map |
| `lib/dataos/nulls.py` | 159 | D6 | Nine-value closed `MissingReason` vocabulary, `NullPolicy`, `validate_value` (keyed on `numbers.Number`, not `(int, float)` — see §1.3) |
| `lib/dataos/registry.py` | 396 | D5/D9 | `DatasetContract`, the loader, `validate_registry`, the static DAG |
| `lib/dataos/quality.py` | 397 | D8 | Nine check families × four severities as **pure** validators + line-start GH annotations |
| `config/dataset_registry.yml` | 322 | D5 | 7 dataset rows (5 PRODUCED, 2 PROPOSED); ONE lineage edge, `reference.security_master -> reference.vendor_aliases` |
| `tests/test_dataos_*.py` | 1,729 | — | 369 tests across SIX suites |

`wc -l` over all fourteen paths totals **4,434 lines** (VERIFIED).

### 1.2 The properties that were deliberately designed in

These are load-bearing for every later phase; a task that breaks one has regressed the foundation.

- **Stdlib-only at import time.** `pandas` appears nowhere; `yaml` is imported lazily inside
  `load_registry` (`lib/dataos/registry.py:32-34`). This is what lets a collector translate a
  ticker without paying a dataframe import, and lets the suite run in a thin CI lane with only
  `pytest pyyaml`.
- **Fail closed, with the reason attached.** `assert_pit_readable` raises `PointInTimeError`
  rather than returning a degraded answer, because "the degraded answer (the latest vintage) looks
  exactly like the right one" (`lib/dataos/temporal.py:244-256`). `pit_refusal_reason` returns the
  specific reason, because the caller's next move differs per reason
  (`lib/dataos/temporal.py:226-241`).
- **`DERIVED` is deliberately NOT PIT-readable.** `KNOWN_AT_CLOCKS[DERIVED] = ()`
  (`lib/dataos/temporal.py:188`) — its mandatory clocks answer "can I recompute this"
  (recomputable) and cannot answer "what did we know at t" (replayable). Serving an as-of read
  from a DERIVED table is exactly the current-rule recomputation the Calcbench ruling names.
  `INTELLIGENCE` answers with `served_at`, which *is* the replay clock.
- **Naive datetimes raise.** `utc()` refuses a tz-naive value rather than assuming UTC or local
  (`lib/dataos/temporal.py:211-217`). This is directly motivated by the Prophet incident where a
  `+08:00` render host read 2026-08-10 earnings as already past and flapped board membership
  78↔81 rows on an identical `as_of` (`scripts/backfill_prophet_outage.py:9-19`, VERIFIED by the
  prophet lane).
- **Lenient enum coercion at load, strict at validate.** An unknown `temporal_profile` is kept as
  a raw string on the contract and surfaces as a reportable violation instead of exploding the
  whole catalog at load (`lib/dataos/registry.py:115-124`).
- **`validate_registry` returns; it never prints or exits** (`lib/dataos/registry.py:27-31`), so
  the same function serves a test that fails on any violation and a catalog builder that renders
  them.
- **Annotations are bare prints at column 0 with `flush=True`**, never through a logger
  (`lib/dataos/quality.py:27-35`). This encodes the failure that shipped dead five times
  (#3487, #3515, #3562, #3563, #3570) before #3587 swept 69 sites.
- **`KNOWN_STORE_BASES` is documentation as code**, keyed `"<store>:<column>"`, populated from a
  measurement rather than from the column name (`lib/dataos/price.py:255-260`). It is the reason
  the V1 migration can label 135 readers without touching them.

### 1.3 Verified state of the foundation

```
$ PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_dataos_identity.py \
    tests/test_dataos_temporal.py tests/test_dataos_price.py tests/test_dataos_nulls.py \
    tests/test_dataos_registry.py tests/test_dataos_quality.py -q
369 passed in 2.26s
```

The sixth suite is not a rounding error on the fifth. `tests/test_dataos_nulls.py` did not
exist in the first pass, and neither did a `run:` entry naming it, so `lib/dataos/nulls.py`
— the whole §D6 pillar — was DARK BY CONSTRUCTION: an adversarial mutation replacing its
zero-masking law with `if False:` (deleting "0 may never mean absence" outright) failed
NOTHING across all 279 tests. The same review found the guard keyed on
`isinstance(value, (int, float))`, blind to `decimal.Decimal` and to the `numpy` scalars a
parquet frame yields through `iterrows()`/`itertuples()` — i.e. blind to the types the
stores this library describes actually produce. Both are fixed and pinned.

```
$ python3 -c "from lib.dataos.registry import load_registry, validate_registry; \
r=load_registry(); print(len(r), [c.dataset_id for c in r.all()]); print(validate_registry(r))"
7 ['equity.bars.daily.stocks', 'equity.bars.daily.yahoo', 'equity.bars.daily.massive',
   'macro.fred.observations', 'macro.fred.vintages', 'reference.security_master',
   'reference.vendor_aliases']
[]
```
(both VERIFIED, 2026-08-12.)

CI wiring is present in the working tree but likewise uncommitted: a `dataos-foundation` job in
`.github/ci/legacy-jobs.yml` (deps `pytest pyyaml` only, so a pandas import creeping into
`lib/dataos/` reds *there* first) plus a trigger-closure entry in `.github/workflows/ci.yml`
naming both `lib/dataos/**` and `config/dataset_registry.yml`. Registering the trigger for the
registry file matters because that file is the *subject* of `tests/test_dataos_registry.py` — a
registry edit that cannot start `ci.yml` is unproven by construction.

### 1.4 The one honest gap in Phase 0

```
$ grep -rln 'dataos' engine lib collectors scripts app tests contracts config \
    --include='*.py' --include='*.yml' | grep -v '^lib/dataos'
tests/test_dataos_temporal.py
tests/test_dataos_registry.py
tests/test_dataos_quality.py
tests/test_dataos_price.py
tests/test_dataos_nulls.py
tests/test_dataos_identity.py
config/dataset_registry.yml
```
**Zero production importers.** (VERIFIED.) The vocabulary exists and is tested; nothing in
`engine/`, `collectors/`, `scripts/` or `app/` calls it yet. Per gate G7 that is the correct
reading of Phase 0's status: *the foundation is delivered, the consumption is Phase 1 onward*.
Every subsequent phase is measured by a consumer that changed, and the wave-level count to watch
is this grep going from 6 to a number that includes production trees.

---

## §2 Blast-radius ranking

Ordering is by measured consumer count × irreversibility of a wrong answer, not by tidiness.
This is the ranking that decides §3's phase order.

| # | Defect class | Measured blast radius | Worst realized cost |
|---|---|---|---|
| 1 | **Identity** | ≥10 independently-governed seams; 672 files match an alias/rename pattern; `lib/ticker_aliases.py` is 53 lines with 2 rows | 7-month silent basket hole (MMC), a double-counted track record (SATS→ECHO) |
| 2 | **Price basis + adjustment vintage** | 135 files read `data/stocks`; 4 physical US daily stores; 3 semantic bases + a 4th, undocumented **vintage** axis | A published-ledger re-price that would have moved 75 graded rows, 19 materially |
| 3 | **Macro PIT** | Every live-scored consumer (~20 call sites) reads `build_features()` with the leaky default | Silent look-ahead on CPI/PCE/PPI in sector, regime, bond and allocation scoring |
| 4 | **Calendars / sessions** | 62 files carry session-hour literals; 4 independent early-close models, 3 declaring it out of scope; halts have no store at all | Halted names silently dropped from every cross-sectional estimator |
| 5 | **Metric canon** | canon covers 6 concept families; `atr` and `realized_vol` have **no canonical referent at all**; `realized_vol` producers disagree by ~1587× | An impossible `XLC=1.0` beta live in a user-facing score for the whole life of its "fix" |
| 6 | **Taxonomy PIT** | `membership_history.parquet` exists for **zero** of 3 registered suites; 2 of 8 basket suites carry no per-member dating at all | Every `members_asof()` call returns `pit=False` today |
| 7 | **Catalog** | 332 top-level `data/` dirs; `run_status.json` covers 149 of them and is frozen | "Coded but never wired" is indistinguishable from "wired and broken" |

### 2.1 Identity — everything joins on it

`lib/ticker_aliases.py` is 53 lines (VERIFIED: `wc -l` → `53`) with exactly two rows,
`YAHOO_FETCH_ALIASES = {'FI':'FISV', 'MMC':'MRSH'}` (`lib/ticker_aliases.py:37`), and its own
docstring self-scopes it: *not* a display map, *not* a ledger map — it only decides what string
goes to the vendor. **It is the narrowest of at least ten identity surfaces, not the only one**
(census PART 0, CLAIM 3, REFUTED as stated):

1. `lib/ticker_aliases.py` — membership ticker → Yahoo fetch symbol, 2 rows.
2. `lib/delisted_symbols.py` (108L) + `config/delisted_symbols.yml` (95L) — "the SECURITY STOPPED
   EXISTING — it is not a rename", with three consumers acting differently on it.
3. `lib/symbol_directory_receipts.py` (833L) — prospective completion receipts.
4. `engine/entity_resolver.py` (318L) — a five-layer text→ticker ladder with its own alias
   sources, including a CUSIP→ticker map promoted from smart_money.
5. `engine/name_resolver.py` (152L) — company-name → ticker off the SEC map.
6. `engine/ledger_identity.py` (372L) — ticker-rename identity for append-only ledgers. It
   documents SATS→ECHO (2026-06-24) causing a **double count** in
   `data/signal_archive/track_record.parquet`, and states at lines 28-30 that SATS is absent from
   the dead-name registry.
7. `collectors/edgar_deadnames.py` — dead ticker → CIK bridge; documents that `edgar.py:423`
   drops delisted filers, so 0 of 1,083 dead-only tickers in
   `data/breadth/sp1500_pit_membership.parquet` carry fundamentals.
8. `config/theme_graph_identity_breaks.yml` (53L) — a third id convention, `co:<market>:<SYMBOL>`
   retired and re-minted as `#2` on ticker reuse.
9. `config/biocatalyst_sponsor_ticker_map.yml` (1,057L) — sponsor-name → ticker.
10. `config/us_search_aliases_zh.json` (776L) — zh search aliases.

**They demonstrably disagree.** `engine/ledger_identity.py` knows SATS/ECHO;
`lib/ticker_aliases.py` does not. Three incompatible collision-suffix conventions are live at
once: the CN spine's `CN-XSHG-600519`, theme_graph's `co:<market>:<SYMBOL>#2`, and
`lib/dataos/identity.py`'s `US-XNYS-MMC.2`. Add the six independent CN symbol converters, at
least two of which disagree on Beijing Stock Exchange code ranges — `collectors/china_universe.py:100-121`
returns `None` for 8xxxxx/4xxxxx while `collectors/china_ths_concepts.py:97-109` maps the same
ranges plus 920xxx to `.BJ` (census china_hk lane, VERIFIED) — and the count of *governed* identity
surfaces is well past ten.

The realized cost is written into `lib/ticker_aliases.py`'s own docstring: `scripts/fetch_basket_extras`
carried MMC→MRSH, its sibling `scripts/fetch_basket_ohlcv` did not, so
`data/baskets/ohlcv/MMC.parquet` never existed, and for seven months the `insurance` basket
rendered 18/19 members and `us_sector_financials` 75/76. Nothing went red. The site drew one fewer
line.

And no user-facing plane in any of the three repos carries a stable id: `watchlist_symbols.symbol
text`, `alerts.symbol text`, `favorites.value text`
(`charting-app/supabase/migrations/0001_init.sql:43,79,90-91`), `portfolio_positions.ticker text`,
and the bot's per-symbol parquet filenames — all bare strings with no market qualifier (census
cross_repo lane, VERIFIED).

### 2.2 Price basis + vintage — the widest measured consumer count

```
$ grep -rl 'data/stocks' engine scripts collectors lib app | wc -l
135
```
(VERIFIED here, 2026-08-12; the adversarial verifier measured 133 on 2026-08-12 in the data
checkout. The number drifts with the tree; treat "≈135 readers" as the planning figure and
re-measure in the PR.)

**Four physical per-ticker US daily stores**, not three: `data/stocks` (229 files), `data/yahoo`
(824), `data/baskets/ohlcv` (2,519), `data/massive_stock_day` (20,476) — all VERIFIED by the
adversarial verifier. Two further directories are empty husks and must not be counted as stores:
`data/us_stocks/` holds only `latest.json`, `data/thetadata_eod/` holds only two JSON sidecars and
zero ticker parquets.

Three semantic bases (`_raw`, `_sadj`, `_tradj`) plus **a fourth divergence axis nothing in the
repo models: adjustment VINTAGE.** Measured over the full 86-ticker overlap of `data/stocks` and
`data/yahoo`, 61/86 are bit-identical and 25/86 diverge despite being the *same semantic* — worst
HON 4.92%, CMCSA 1.34%, BMY 1.12%, DIS 0.76%. One store back-adjusted through a later
distribution than another.

**The witness for the entire project is HON on 2025-09-25:**

| store / column | HON 2025-09-25 | HON 2026-06-29 |
|---|---|---|
| `data/stocks/HON.parquet` `close` | 192.573517 | 227.800003 |
| `data/yahoo/HON.parquet` `close` | 192.419067 | 227.800003 |
| `data/yahoo/HON.parquet` `close_price` | 195.758713 | 227.800003 |
| `data/baskets/ohlcv/HON.parquet` `close` | 201.964905 | 227.800003 |

Four numbers for one (ticker, date), three of them nominally in the same "adjusted" family, all
converging at the tape tip (VERIFIED by the adversarial verifier). Direction and magnitude are
consistent with HON's Solstice Advanced Materials spinoff — but that mechanism is **INFERRED, and
cannot be verified in-repo, precisely because no corporate-action store exists to check the ex-date
and factor against.**

The load-bearing bug is `engine/price_ladder.py`, which is simultaneously the best prior art in the
repo and its most consequential defect:

```
engine/price_ladder.py:104
ADJUSTED_SOURCES = ("baskets_ohlcv", "yahoo", "data_stocks", "baskets_extras")
```
(VERIFIED here by grep.) The module's premise is that "an excess return is only meaningful when
both legs are priced on the SAME adjustment basis", and it returns `adjusted=True` for all four
rungs — while 31/223 co-covered tickers disagree >0.01% on a single date (18 by >0.5%, max HON
4.877%) with **no consistent precedence**: for HON, yahoo == baskets and stocks is the outlier; for
PEP, stocks == yahoo and baskets is the outlier. A study whose universe resolves some names via
rung 1 and others via rung 3 mixes two vintages into one cross-section, and the divergence is
invisible to every consumer.

`price_ladder`'s own docstring already records the non-reproducibility this causes: PNC at
2026-06-22 read 234.71 in the 2026-07-01 commit and 232.85 on 2026-08-06, and re-running
`scripts/grade_us_board.py` against the shipped ledger "would have moved 75 already-published rows,
19 of them materially (worst −1.94pp on LPG 2026-06-18 H5)". Its remedy — stamp the basis on the
row, never re-price a graded row — is the right shape and is **per-row prose, not a store-level
vintage clock**, and it covers the cache fallback but not the adjusted family.

Adjacent, and independently damaging: `data/stocks` has **no `open` column, universally** — the
pyarrow schema of all 229 files is exactly one shape, `('close','high','low','volume','Date')`
(VERIFIED, 229/229). But opens *are* obtainable, from `data/baskets/ohlcv` (2,519 real opens,
AAPL 2026-07-08 open = 311.910004) and by synthesis (`engine/ohlc_reconstruct.py`, `open := prior
close`, high/low = close ± ATR/2 with a deliberately wide RANGE_MULT=2.0 prior). **The defect is
undisclosed mixture, not absence**: a gap feature built from a baskets `open` against a stocks
`close` crosses two different adjustment vintages, and nothing stamps which open a caller got.

Cross-repo, the same defect has a *user-visible* form. A Terminal daily-OHLC file is seeded once
from Macro's TR-adjusted `data/stocks` (`charting-app/ingest/build_universe.py:49`, `MACRO =
Path(os.environ.get("MACRO_REPO", "/Users/chriswong/Documents/Cluade/Macro Dashboard"))`, VERIFIED
here) and then topped up forever by Polygon grouped-daily with `adjusted=true`
(`charting-app/ingest/refresh_ohlc.py:38-39`, VERIFIED here) — split-only per the vendor's
documented semantics (INFERRED from vendor docs; no in-repo assertion states it). So a single
symbol's series switches adjustment convention partway through its own file. And the chip that
tells the user about it is a hardcoded constant:

```
charting-app/terminal/components/ChartFrameBar.tsx:381
{/* ADJ chip — always passive (display-only; we only serve adjusted data) */}
<span className="cfb-chip cfb-chip-adj" title={t("adjTip")}>ADJ</span>
```
with `adjTip: ["Adjusted data (split & dividend adjusted)", "复权数据（除权除息调整）"]`
(`charting-app/terminal/lib/i18n.tsx:285`). Both VERIFIED here. The badge asserts split *and*
dividend adjustment unconditionally, including for segments that are split-only and for symbols
never touched by the Macro store.

### 2.3 Macro PIT — every live-scored consumer

`engine/inputs.py:137` is `def build_features(pit_basis: str | None = None, ...)` (VERIFIED here),
and the census macro lane enumerated ~20 call sites — `scripts/build_site.py:4664`,
`engine/equity_alloc.py` (5 sites), `engine/strategies.py:72`, `engine/masterminds.py:196`,
`scripts/build_bonds.py:1381`, `scripts/build_transmission.py:42`, the four
`scripts/calibrate_spvector*` variants, `scripts/refresh_regime_if_stale.py:163`,
`scripts/calibrate_macro_betas.py:61`, `scripts/calibrate_bonds.py:199` and others — **all calling
it with zero arguments**, i.e. the leaky default that reads latest-revised FRED on native
reference-period stamping. This is a self-documented look-ahead on `headline_cpi`, `core_cpi`,
`headline_pce`, `core_pce`, `ppi`, and payrolls (VERIFIED).

The fix is **already built and unused**. `engine/pit.py` is the shadow accessor with a modelled
release-lag calendar and an ALFRED vintage as-of join, and `pit_basis='release'` is used only by
`scripts/build_regime_v2_pit.py:376`, `scripts/validate_drawdown_risk_pit.py:172`, and
`scripts/shadow_pit_regime.py:199-200`. This is an **adoption gap, not a capability gap**.

One census smell about this lane is REFUTED and must not be carried forward: the claim that
callers read the too-optimistic `lag_bd` prior rather than `lag_bd_measured`.
`engine/pit.py:181-191` already prefers config override > learned > measured > prior:

```python
def _effective_lag_bd(spec: dict) -> int:
    lag = spec.get("lag_bd", 0)
    if spec.get("lag_bd_measured") is not None:
        lag = spec["lag_bd_measured"]
    if spec.get("lag_bd_learned") is not None:
        lag = spec["lag_bd_learned"]
    return int(round(float(lag)))
```

The real residual risk is different and worse: `config.yml:124-169` declares 54 PIT-tracked series
while `data/fred_vintage/vintages.parquet` contains 26, so **28 configured series — including
UNRATE, RSAFS, JTSJOL, ADPMNUSNERSA — have zero vintage rows**, and `engine/pit.py` falls back to
reference/latest for a non-vintaged series. Promoting `basis='release'` before healing that store
would move the leak rather than close it. (Store contents VERIFIED by the macro lane; the
*staleness dating* of that parquet is NEEDS-CORROBORATION per the checkout warning.)

### 2.4 Calendars / sessions

```
$ grep -rlE "09:30|16:00|time\(9, ?30\)|time\(16, ?0\)|11:30|15:00|13:00" \
    engine scripts lib collectors app --include='*.py' | wc -l
62
```
(VERIFIED here.) §D12 pins the figure at 68; my re-measurement with the pattern above returns 62.
The gap is pattern choice, not a dispute — plan against "≈60-70 files, re-measure with the exact
grep you intend to guard."

Underneath that, **four independent early-close models, three of which declare the concept out of
scope**: `lib/nyse_calendar.py:11-14` ("Early closes (13:00 ET) are NOT modeled"),
`engine/marketing/market_clock.py:77-78` (same), `engine/live_overlay.py:119,144` ("ADVISORY hint
only — no exchange holiday calendar and no half-days"), versus `engine/session_digest.py:176,199,211`
which *does* model it but is "coverage-denominator only — this never gates, filters or labels".
No consumer can obtain an authoritative answer to "was 2025-11-28 a half day."

`engine/live_overlay.py:95-104` additionally carries its own `_REGION_HOURS` table beside the
canonical `lib/nyse_calendar.py` / `cn_calendar.py` / `hk_calendar.py` — the same canon-bypass
pattern as the indicators, in the calendar domain.

**Halts have no store at all.** `ls data | grep -iE 'halt|luld|auction|suspend'` returns only
`treasury_auctions` (unrelated). Halts are inferred as zero-variance and then *dropped*:
`engine/theme_crowding.py:47` and `engine/group_flow.py:91` remove "zero-variance (halted /
constant-price) members"; `engine/synthetic_control.py:454` and `engine/bar_derive.py:365` route
around them. That is an unmeasured, daily-grain survivorship mechanism inside every cross-sectional
statistic the site publishes. The vocabulary for it exists only in Phase 0's
`lib/dataos/nulls.py:49` (`HALTED = "HALTED"`).

Calendar coverage is a scheduled failure: `lib/cn_calendar.py:76` sets
`HOLIDAY_COVERAGE_END = date(2027, 12, 31)` and degrades to weekday-only math past it;
`lib/hk_calendar.py:100-111` hardcodes Lunar New Year through 2030 (census china_hk lane,
VERIFIED). Both degrade silently in the safe direction — but *undetected*.

### 2.5 Metric canon

**`engine/canon.py` has no `atr` and no `realized_vol` at all:**
```
$ grep -c "^def atr\|^def realized_vol" engine/canon.py
0
```
(VERIFIED here; the file is 522 lines with 22 top-level defs.) This corrects the widely-repeated
"53 files violate canon" framing. The defensible counts (adversarial verifier, VERIFIED): **103
files import canon (55 in production trees); 56 production files define an rsi/atr/realized_vol-named
function; only 6 do both.** Of 8 sampled definers, **5 compute a genuinely different quantity** —
`_connors_rsi` is a composite, `atr_proxy` is a deliberately close-only proxy, `_atr_word` maps an
ATR to a natural-language word, and the event/threshold predicates are not indicator
implementations. So roughly 23 of the cited "duplicates" are canon **gaps**, not violations, and a
task that treats a legitimate difference as a violation will make the codebase worse.

What *is* a real divergence, with magnitude: `realized_vol` producers differ on three independent
axes — annualization (×√252 or not), units (fraction vs ×100), and return type (simple vs log) —
so `engine/stock_technicals.py:94-99` reads ≈1587× `engine/vol_forecast.py:22-24` on the same
input (census metrics lane, VERIFIED). `percentile_rank` has four incompatible tie conventions
that answer 0 vs 50 vs 100 on a frozen input (`engine/btc_regime_flags.py:41-45` inclusive-of-self,
`engine/risk_radar.py:411-417` midrank scoring 50, `engine/index_momentum.py:261-268` strict-less-than).
And `credit_impulse` has a **third** live formula in three more files
(`engine/china_internals.py:185-188`, `engine/china_sector_index.py:305-307`,
`engine/china_conditions.py:292-295`) that `engine/canon.py:171-179` never mentions while claiming
the collision closed — one of which feeds a weighted regime driver at
`engine/china_conditions.py:248`.

### 2.6 Taxonomy PIT

`engine/basket_membership_pit.py` is fully-coded infrastructure whose target artifact does not
exist: `find data -iname '*membership_history*'` returns nothing across the whole tree, for all
three registered suites (`SUITE_THS`/`SUITE_CURATED`/`SUITE_US`,
`engine/basket_membership_pit.py:97-99`, VERIFIED here). Every `members_asof()` call therefore
falls back to current membership with `pit=False` — the exact look-ahead its docstring says it
exists to prevent. And `data/baskets_nasdaq/membership.json` / `data/baskets_russell/membership.json`
carry bare `{ticker, name}` members with no `added`/`removed` at all, versus six sibling suites
that do — unconditional look-ahead on 2 of 8 suites, with no error or warning signal.

### 2.7 Catalog

`data/run_status.json` covers 149 of 332 top-level `data/` dirs, and ~19 "additive, never fatal"
bolt-on collector calls in `scripts/collect.py` bypass the Adapter-registry loop that populates it
entirely (`sec_ftd`, `redfin_hf`, `baskets`, `stocks` are all absent from its `sources` dict while
being invoked). `collectors/china_block_tape.py:73-81` *documents* its own intended nightly wiring
inside the module docstring — "Or via the adapter pattern:
`Adapter("china_block_tape", refresh, hosts=["akshare"], serial=True)`" — and that wiring was never
applied. The line is docstring prose, not code: `ast.parse` puts the module docstring at lines 1-92,
`grep -c '^class '` returns 0, and `grep -c 'china_block_tape' scripts/collect.py` returns 0
(VERIFIED here 2026-08-12). So the store is not a broken pipeline and not a wired-but-empty one —
it has no producer wired at all, which from the filesystem alone is indistinguishable from both. (All VERIFIED by the smells lane; the *frozen-since* dating
of `run_status.json` is NEEDS-CORROBORATION per the checkout warning.)

---

## §3 The phased plan

Every task is sized for one spawned session. Priority is `P0` (blocks the wave), `P1` (in the
critical path of a ranked defect), `P2` (valuable, parallelizable). Agent class follows §Model
routing: `builder` (Opus) for code/PR/test work, `reviewer` (Opus) for adjudication and red-teams,
`designer` (Opus) for any user-facing surface, `Explore`/`general-purpose` with `model: 'sonnet'`
for mechanical non-code census work only.

Tasks within a phase that share no `Depends` edge can run in parallel worktrees. Tasks touching the
same file must not.

---

### Phase 1 — Land the foundation, then the identity spine

Rationale (§D12): everything joins on identity, and it is the only defect class with a *measured*
seven-month silent production loss.

---

#### **DOS-1.0 — Commit and prove the Phase 0 foundation**

- **Objective.** Move `lib/dataos/` (7 modules), `config/dataset_registry.yml`, the five test
  files, and the two CI wiring edits from untracked to merged on main, with the `dataos-foundation`
  job observed green on a real PR head.
- **Priority.** P0. Every other task in this document depends on it.
- **Depends on.** Nothing. **Blocks.** Everything.
- **Systems/files.** `lib/dataos/*.py`, `config/dataset_registry.yml`, `tests/test_dataos_*.py`,
  `.github/ci/legacy-jobs.yml`, `.github/workflows/ci.yml`.
- **Expected output.** One PR. No code changes beyond what is on disk today unless a review finds a
  defect; this task is about *tracking*, not authoring.
- **Agent class.** `builder`.
- **Acceptance tests.**
  - Not done unless `git ls-files lib/dataos/ config/dataset_registry.yml tests/test_dataos_*.py`
    lists all thirteen paths on the merged commit.
  - Not done unless the `dataos-foundation` check appears on the PR and concludes **green** — an
    absence of red is not a pass, and a suite CI never ran is dead code.
  - Not done unless `validate_registry(load_registry())` returns `[]` in that CI run (it does
    today; the point is that CI, not a laptop, has now said so).
  - Not done unless the PR body pastes the `N passed` summary line from the CI log, not from a local
    run — quote whatever count that run prints rather than a number copied from this document.
- **Migration risks.** (a) **Ownership collision** — the files appeared during a live session at
  13:43–13:55 on 2026-08-12; run `git worktree list` and `gh pr list --search "lib/dataos"` before
  claiming the lane, per house law. (b) The `.github/` edits are owned by a concurrent lane in this
  same wave; coordinate rather than force. (c) A `git clean` or worktree GC before this lands
  destroys ~4,100 lines of untracked work — this is why it is P0 and first. (The tree is untracked
  and a concurrent lane is still writing it, so the figure moves; re-measure with
  `wc -l lib/dataos/*.py tests/test_dataos_*.py` before quoting it. VERIFIED 2026-08-12: 4,112.)

---

#### **DOS-1.1 — Materialize the security master and the time-scoped alias table**

- **Objective.** Turn `reference.security_master` and `reference.vendor_aliases` from
  `status: PROPOSED` into `status: PRODUCED`, seeded from the universes that already exist, with
  `lib/dataos/identity.VendorAliasTable` as the only reader.
- **Priority.** P1.
- **Depends on.** DOS-1.0.
- **Systems/files.** New `scripts/build_security_master.py`; `config/dataset_registry.yml`
  (flip two rows); seeds from `data/breadth/constituents.parquet`,
  `data/baskets/membership.json`, `lib/delisted_symbols.py`, `config/delisted_symbols.yml`,
  `engine/ledger_identity.py`, `lib/ticker_aliases.py`.
- **Expected output.** Two parquet artifacts under a registry-declared path; one alias row per
  `(vendor, vendor_symbol, listing_key, valid_from, valid_to)`; a receipt carrying `code_version`
  and input hashes.
- **Agent class.** `builder`.
- **Acceptance tests.**
  - Not done unless a test asserts the table answers **differently either side of 2026-01-14** for
    Marsh McLennan: `yahoo` symbol `MMC` before, `MRSH` after, both resolving to the same
    `US-XNYS-MMC`.
  - Not done unless the same test covers **SATS→ECHO (2026-06-24)**, the rename
    `engine/ledger_identity.py:28-30` records as absent from the dead-name registry and which
    double-counted `data/signal_archive/track_record.parquet`. A table that knows MMC and not SATS
    has reproduced the exact fragmentation being fixed.
  - Not done unless every `PRODUCED` row passes gate G1 with the existence command in the PR body.
  - Not done unless the seed's coverage is *reported as a number*, not asserted as complete —
    "N of M members resolved, K unresolved, listed by name."
- **Migration risks.** Inception-code derivation is only as good as the inception record; a wrong
  `<CODE>` mints a wrong-but-stable id. Mitigate by **mint-once-and-store**: a later correction
  appends an alias, never re-mints (§D2). Ticker reuse after a delisting is the one collision case
  and takes an explicit `.2` suffix — rare, greppable, never silent.

---

#### **DOS-1.2 — Identity seam census → a declared, tested disagreement registry**

- **Objective.** Enumerate every identity surface in the tree, classify each as
  `ADOPT | ALIAS-INTO-MASTER | KNOWINGLY-DIFFERENT | RETIRE`, and land a test that fails when two
  ADOPT-class surfaces disagree on a security.
- **Priority.** P1.
- **Depends on.** DOS-1.1.
- **Systems/files.** New `config/identity_seams.yml`; new `tests/test_identity_seam_agreement.py`;
  reads the ten surfaces listed in §2.1.
- **Expected output.** One YAML registry + one test. **No behaviour change to any seam** — this
  task declares, it does not merge.
- **Agent class.** census pass with `Explore` (`model: 'sonnet'`); the classification adjudication
  and the test with `builder`.
- **Acceptance tests.**
  - Not done unless the census is done **by content, not by filename** — a file is an identity
    surface because it maps one symbol-space onto another, not because its name contains "alias".
    The starting grep returns 672 files; the deliverable is the ≤20 that survive reading.
  - Not done unless at least one **KNOWINGLY-DIFFERENT** row exists with a stated reason (§D10
    requires the registry to express this as a first-class state), and the test does not fire on it.
  - Not done unless the test is shown red on a deliberately-introduced disagreement and green after
    (gate G2).
- **Migration risks.** The temptation is to unify on discovery. Do not: `config/theme_graph_identity_breaks.yml`'s
  `#2` convention and the CN spine's bare key are both *in production*, and a silent unification
  republishes surfaces. Declare, then schedule.

---

#### **DOS-1.3 — One CN symbol converter**

- **Objective.** Make `lib/dataos/identity.normalize_cn_symbol` / `cn_board` the single converter,
  and retire the five ad-hoc duplicates by import.
- **Priority.** P2 (P1 if any CN limit work reopens under `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`'s
  reopen path).
- **Depends on.** DOS-1.0.
- **Systems/files.** `collectors/tushare_client.py:61-68`, `collectors/china_universe.py:100-121`,
  `collectors/china_ths_concepts.py:97-109`, `scripts/d4_cn_supply_absorption_phase0.py:132-136`,
  `scripts/build_china_microstructure.py:234`; authority is
  `collectors/china_tushare_spine.py:177-179,465-480`.
- **Expected output.** Five call sites importing one function; the spine's board classifier
  reproduced (and cross-checked) in `lib/dataos/identity.cn_board`.
- **Agent class.** `builder`.
- **Acceptance tests.**
  - Not done unless a test pins the **specific disagreement**: a `920xxx` code resolves to
    `CN-XBSE-…` under the new converter, where `china_universe.py` returned `None` and
    `china_ths_concepts.py` returned `.BJ`. Assert the *new* answer, and assert that each migrated
    call site now agrees with it.
  - **CORRECTION (2026-08-12, adversarial review).** An earlier draft of this bullet demanded that
    `8xxxxx` / `4xxxxx` codes ALSO resolve to `CN-XBSE-…`, and `lib/dataos/identity.py` was built
    to do it. That is the duplicate-identity bug the identity spine exists to end: `430047` is a
    historical **alias** of a BSE security whose canonical code is `920163`, so minting
    `CN-XBSE-430047` gives one security two ids — `SEC:CN-XBSE-920163` from the canonical feed and
    `SEC:CN-XBSE-430047` from a legacy TuShare pull — which join as different securities with
    neither side visibly wrong. The spine contract says it twice ("Old BJ codes remain aliases.
    Every canonical BSE mapping target must be `920xxx`"; "other admitted A code families are main
    board"), and the authority agrees in code: `collectors/china_tushare_spine.py::_board_for`
    (`:465-480`) decides `bse` from the vendor's `source_exchange` field, NEVER from a code prefix,
    while old codes reach the canonical id only as `alias_kind = bse_old_code` rows sourced from
    `tushare.bse_mapping` (`:1933-1942`). `lib/dataos/identity.py` carries no `bse_mapping` table
    and therefore has no authority to resolve an alias; it now RAISES on the 4xxxxx/8xxxxx families
    (`is_legacy_bse_code`), including under an explicit `.BJ` suffix — the venue was never the
    doubt. Not done unless the migrated call sites route those codes through the alias table rather
    than the converter.
  - Not done unless the ChinaNext boundary comment at `collectors/china_tushare_spine.py:475-477`
    is preserved as a test: 300000–309799 shares and 309800–309999 depositary receipts are both
    ChiNext, and a future 303-309 family must not classify as main board.
  - Not done unless the diff touches **no adjusted-price path** — this task is identity only.
- **Migration risks.** `china_universe.py`'s `None` for Beijing is load-bearing *downstream* (it
  drops those names from a fetch). Changing the converter without checking what the `None` was
  protecting turns a deliberate exclusion into a silent inclusion. Read each call site's handling
  of the falsy return before migrating it.

---

### Phase 2 — Price basis and vintage

Rationale: widest measured consumer count (≈135 files on one store alone) and the one defect class
that already produced a stop-ship (`DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`).

---

#### **DOS-2.1 — Register the fourth store and re-measure `KNOWN_STORE_BASES`**

- **Objective.** Add `equity.bars.daily.baskets_ohlcv` to the registry with its measured basis, and
  extend `lib/dataos/price.KNOWN_STORE_BASES` from 4 entries to cover every column any of the four
  stores actually serves.
- **Priority.** P1.
- **Depends on.** DOS-1.0.
- **Systems/files.** `config/dataset_registry.yml`, `lib/dataos/price.py:255-265`,
  `tests/test_dataos_price.py`.
- **Expected output.** One new registry row (`producer: scripts/fetch_basket_ohlcv.py`,
  `vendor: yahoo`, real opens, 2,519 names) + an extended measured-bases map + a stored measurement
  receipt so the next session does not re-measure by guess.
- **Agent class.** `builder`.
- **Acceptance tests.**
  - Not done unless the measurement is **re-run**, not copied: the PR body carries the four HON
    2025-09-25 numbers and the four NVDA 2024-06-03 numbers reproduced from the current data
    checkout, with the reading date stated.
  - Not done unless `data/us_stocks/` and `data/thetadata_eod/` are explicitly **excluded** as
    empty husks, with the `ls` output showing why.
  - Not done unless `data/massive_stock_day` carries the honest caveat in its row: its own manifest
    reports `n_tickers 19133` against 20,476 files on disk, `n_processed_days 471` over a window of
    roughly 1,255 sessions, and `max_missing_run_weekdays 832`, with the SPY anchor at 454 rows and
    a 1,165-day max gap. **It is a ~37%-populated store with multi-year holes, not a raw mirror.**
- **Migration risks.** Declaring `massive_stock_day` "the raw basis" without a freshness SLA and a
  gap contract would move every structure calculation onto the stalest, gappiest store in the
  estate. The registry row must carry the gap facts, not just the basis.

---

#### **DOS-2.2 — Kill `price_ladder`'s false ADJUSTED equivalence**

- **Objective.** Replace the boolean `r.adjusted` with a `(basis, adjustment_asof, source_rung)`
  triple, so a consumer can see that two rungs are not the same vintage.
- **Priority.** P1. **This is the single highest-value code change in the wave.**
- **Depends on.** DOS-2.1.
- **Systems/files.** `engine/price_ladder.py` (`ADJUSTED_SOURCES` at line 104, `_FILE_RUNGS`,
  the resolver, `r.adjusted`), every consumer of `price_ladder`'s result object.
- **Expected output.** A resolver whose return object names its rung and its measured vintage; a
  study-level guard that refuses a cross-section resolved through more than one adjusted rung
  unless the caller passes an explicit `allow_mixed_vintage=True`.
- **Agent class.** `builder`, with a `reviewer` red-team before merge.
- **Acceptance tests.**
  - Not done unless a test constructs the **HON case** (stocks vs yahoo vs baskets on 2025-09-25)
    and asserts the resolver reports three different vintages rather than three `adjusted=True`.
  - Not done unless a test asserts the **no-consistent-precedence** property directly: HON's
    outlier is `data/stocks`, PEP's outlier is `data/baskets/ohlcv`, so any "prefer store X"
    rule must be rejected by the test as an incorrect fix.
  - Not done unless `price_ladder`'s existing, correct behaviour is preserved verbatim: the
    fall-through to the unadjusted cache with `r.adjusted=False` rather than dropping a name
    ("dropping an unpriced name deletes exactly the population a study exists to measure"), and the
    documented standing hole that the extras rung recovers **zero** of the 154 board-admitted names
    that fall through — 20.6% of freshly-graded `us_board` rows.
  - Not done unless no already-graded row is re-priced by this change (the module's own law).
- **Migration risks.** Highest of any task here. `price_ladder` sits under grading and study code;
  a changed return shape that silently coerces to truthy re-introduces the bug it fixes. Land the
  new field **additively** first, migrate consumers, and only then remove the boolean.

---

#### **DOS-2.3 — The V1 reader shim and the unqualified-`close` guard**

- **Objective.** Let ≈135 readers keep reading `close` while the basis stops being folklore: a
  shim that exposes basis-suffixed names from the registry's measured bases, plus a guard that
  fails a PR introducing a *new* unqualified price column.
- **Priority.** P1.
- **Depends on.** DOS-2.1.
- **Systems/files.** New `lib/dataos/price_read.py`; new `scripts/check_price_basis_naming.py`;
  `config/dataset_registry.yml`; a `dataos` CI job entry.
- **Expected output.** `read_bars(store, ticker) -> frame with close_tradj/close_raw/… plus an
  `adjustment_asof` column`; a guard over new/changed schema declarations only.
- **Agent class.** `builder`.
- **Acceptance tests.**
  - Not done unless the guard is **scoped to new and changed columns**. A guard that fires on all
    ≈135 existing readers on day one gets disabled by the next session, and a disabled guard is
    worse than none.
  - Not done unless the guard is registered in the `ci.yml` trigger closure — a guard whose edits
    cannot start CI is dark (house trap: *wiring an unrun suite reds the trigger closure guard*;
    register it in the same PR).
  - Not done unless the guard is shown red on a synthetic `close:` column added to an L2 row and
    green after renaming it `close_tradj` (gate G2).
  - Not done unless the shim raises — never silently returns — for a `(store, column)` pair absent
    from `KNOWN_STORE_BASES`. A guessed basis is the defect.
- **Migration risks.** The shim must not become a fifth store. It reads existing parquet and
  renames columns in memory; it writes nothing (gate G4).

---

#### **DOS-2.4 — Corporate-action event store (currently PROPOSED, unbuilt)**

- **Objective.** Build the `(security, ex_date, type, factor, source, ingested_at)` table that makes
  `_sadj`/`_tradj` derivable from `_raw` and makes `adjustment_asof` meaningful.
- **Priority.** P1 — it is the precondition for §D4's V2, and its absence is why the HON mechanism
  is INFERRED rather than VERIFIED.
- **Depends on.** DOS-1.1 (needs stable ids), DOS-2.1.
- **Systems/files.** New collector; anchor vocabulary that **already exists** and must be reused
  rather than re-invented: `contracts/capital_structure_event.schema.json`
  (`/properties/event/properties/family/enum` already carries the literal `"corporate_action"`),
  `corporate_action_basis` in `contracts/.../cn_tushare_minutes_manifest.v1.schema.json`,
  `corporate_action_adjusted` in the `spy_experience_*` contracts, and the CN spine's
  ex-rights `pre_close` field (`collectors/china_tushare_spine.py:4684`).
- **Expected output.** One `status: PRODUCED` dataset with `temporal_profile: EVENT`; a US leg
  (yfinance is already called in 20+ collectors but **never** with `actions=True` and never
  touching `.splits`/`.dividends` — that is the cheapest first source) and a CN detector leg
  (`pre_close != prior close` is a corporate action, and today its only consumers use it for
  limit-band arithmetic).
- **Agent class.** `builder`.
- **Acceptance tests.**
  - Not done unless HON's 2025 spinoff appears in the store with an ex-date and a factor, and a
    test **derives** `data/baskets/ohlcv`'s HON 2025-09-25 value from `data/stocks`' value and that
    factor to within a stated tolerance. That converts the census's single best witness from
    INFERRED to VERIFIED, which is the whole point of the store.
  - Not done unless `contracts/market_memory/spy_daily_price_source_observation.v1.schema.json`'s
    `"point_in_time_corporate_actions": {"const": false}` is addressed **explicitly** — either it
    stays `false` and the new store is declared out of that contract's scope, or the contract is
    versioned. The repo's own contract currently asserts this absence; silently contradicting it is
    a worse state than the absence.
  - Not done unless the CN leg is gated: nothing derived here may feed limit-band or legal-limit
    math except through `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`'s stated reopen path (authorized
    unadjusted TuShare `daily` × same-key `stk_limit`, integer-cent equality).
- **Migration risks.** A vendor's action feed is itself revisable; the store must be
  `EVENT`-profiled and append-only with `revision_seq`, not upserted. And it must not become an
  input to anything until DOS-2.2 lands, or it will paper over the vintage divergence instead of
  explaining it.

---

#### **DOS-2.5 — Terminal: make the `ADJ` chip tell the truth (cross-repo)**

- **Objective.** Replace the unconditional badge with a per-file (ideally per-segment) provenance
  read, and put a segment marker in the OHLC JSON contract.
- **Priority.** P1 — this is the only defect in the wave that is *visibly wrong to a paying user*.
- **Depends on.** DOS-2.1 (so the seed basis is declared).
- **Systems/files.** `charting-app/terminal/components/ChartFrameBar.tsx:379-381`,
  `charting-app/terminal/lib/i18n.tsx:285`, `charting-app/ingest/build_universe.py`,
  `charting-app/ingest/refresh_ohlc.py`, `charting-app/ingest/backfill_ohlc.py`.
- **Expected output.** A `basis` field per bar-segment in `terminal/public/data/<SYM>.json`; a chip
  that reads it; EN + zh copy for all three states (TR-adjusted, split-only, mixed).
- **Agent class.** `designer` (Opus) for the chip and copy; `builder` for the ingest contract.
- **Acceptance tests.**
  - Not done unless a symbol that was Macro-seeded *and* Polygon-refreshed renders a **mixed**
    state rather than "split & dividend adjusted", with a light/dark/zh crop in the PR (gate G6).
  - Not done unless the zh copy is authored as zh, not translated from the English shape.
  - Not done unless the copy avoids falsifier/refutation register entirely — this is a data-basis
    disclosure, not a verdict.
  - Not done unless the ingest change is landed **before** the UI change, so the UI never reads a
    field that does not exist.
- **Migration risks.** The `MACRO_REPO` filesystem coupling (17 files under `charting-app/ingest/`
  hardcode the absolute path into this repo, VERIFIED) means this seam has no CI. Test the ingest
  change against a fixture JSON, not against a live sibling checkout. Do not attempt to remove the
  coupling in this task — that is DOS-6.4.

---

### Phase 3 — Calendars, sessions, halts

---

#### **DOS-3.1 — One session service**

- **Objective.** Fold `engine/live_overlay.py:95-104`'s `_REGION_HOURS` and the four early-close
  models into one authoritative service that can answer `is_session(d, venue)`,
  `session_bounds(d, venue)`, and **`is_early_close(d, venue)`** — the last of which no consumer can
  authoritatively ask today.
- **Priority.** P1.
- **Depends on.** DOS-1.0.
- **Systems/files.** `lib/nyse_calendar.py`, `lib/cn_calendar.py`, `lib/hk_calendar.py`,
  `engine/session_digest.py:176,199,211`, `engine/live_overlay.py:95-104,119,144`,
  `engine/marketing/market_clock.py:77-78`.
- **Expected output.** One module; four call sites migrated; the ≈60-70 literal-bearing files
  **inventoried but not yet migrated** (that is DOS-3.2).
- **Agent class.** `builder`.
- **Acceptance tests.**
  - Not done unless `is_early_close('2025-11-28', 'us')` returns `True` from the service and every
    migrated caller agrees.
  - Not done unless `engine/session_digest.py`'s coverage-denominator semantics are **preserved**:
    it may now read the shared answer, but it still must not gate, filter or label. Changing that
    is a product decision, not a consolidation.
  - Not done unless a test asserts the service is timezone-explicit at every boundary and refuses a
    naive datetime, reusing `lib/dataos/temporal.utc`.
- **Migration risks.** `live_overlay`'s table is used for *staleness detection*; making it
  holiday-aware will change which artifacts read as stale. Land it behind a comparison run and
  report the diff, rather than flipping it.

---

#### **DOS-3.2 — Retire the session-hour literals**

- **Objective.** Migrate the ≈60-70 files carrying `09:30`/`16:00`-class literals to the DOS-3.1
  service, and add a guard against new ones.
- **Priority.** P2. Mechanical, but large.
- **Depends on.** DOS-3.1.
- **Systems/files.** the inventory produced by DOS-3.1.
- **Expected output.** Migration in **batches with a stated batch boundary**, not one PR. Each
  batch is one session.
- **Agent class.** `builder` per batch (this is code, so not sonnet); the *inventory* may be built
  by `Explore` with `model: 'sonnet'`.
- **Acceptance tests.**
  - Not done unless each batch names the exact grep it clears and shows the count going down.
  - Not done unless known false positives stay excluded by name — `engine/dispersion.py:14` and
    `engine/whitehouse_brain.py:365` match `1600` as a **ticker count**, not a time (VERIFIED by the
    smells lane). A migration that "fixes" those has broken something.
  - Not done unless the guard exempts comments and prose (`'09:30-16:00 ET'` in a docstring is
    documentation, not a duplicated constant).
- **Migration risks.** Low individually, high in aggregate: touching 60+ files invites merge
  conflicts across a 20-worktree fleet. Batch by directory, and re-fetch `origin/main` before each
  push.

---

#### **DOS-3.3 — Halt and auction state: stop dropping, start marking**

- **Objective.** Give the zero-variance-means-halted inference a name. Wire
  `lib/dataos/nulls.MissingReason.HALTED` into the four estimators that currently drop those names
  silently, and record how many names that is.
- **Priority.** P1 — this is an unmeasured survivorship mechanism operating at daily grain inside
  published statistics.
- **Depends on.** DOS-1.0.
- **Systems/files.** `engine/theme_crowding.py:47`, `engine/group_flow.py:91`,
  `engine/synthetic_control.py:454`, `engine/bar_derive.py:365`.
- **Expected output.** No behaviour change on day one — the names are still excluded — plus a
  **count and a reason** emitted per run, and a disclosure path for the display tier.
- **Agent class.** `builder`; the disclosure copy goes to `designer`.
- **Acceptance tests.**
  - Not done unless the run reports "N members excluded, reason HALTED" and N is non-zero on at
    least one historical date, demonstrated in the PR. A mechanism nobody has ever seen fire is not
    evidence of anything.
  - Not done unless the estimator's numeric output is **byte-identical** to before on a pinned
    date — this task measures, it does not change answers.
  - Not done unless the census of "how often does this fire" is reported as an *episode* count
    (distinct halted name-days), not a fire count.
- **Migration risks.** A genuinely flat name and a halted name are indistinguishable in every store
  today, so the label is `HALTED`-*suspected*, not `HALTED`-known, until an actual halt source
  exists. Say so in the field name or the reason string; do not overclaim.

---

#### **DOS-3.4 — Calendar coverage expiry becomes a monitored fact**

- **Objective.** Make `lib/cn_calendar.py:76`'s `HOLIDAY_COVERAGE_END = date(2027, 12, 31)` and
  `lib/hk_calendar.py:100-111`'s 2030 lunar tables emit a `freshness` finding as they approach
  expiry, instead of degrading silently.
- **Priority.** P2.
- **Depends on.** DOS-1.0.
- **Systems/files.** `lib/cn_calendar.py`, `lib/hk_calendar.py`, `lib/dataos/quality.py`.
- **Expected output.** A `CheckFamily.FRESHNESS` finding at `WARN` inside 12 months of expiry and
  `DEGRADED` past it, emitted through `emit_annotations`.
- **Agent class.** `builder`.
- **Acceptance tests.**
  - Not done unless the check is shown firing by injecting `now` (the validators take an injected
    clock; do not read the wall clock).
  - Not done unless the annotation is verified to start at column 0 with `flush=True` — assert via
    `capsys` and `line.startswith("::")`, never via `caplog`.
- **Migration risks.** None material. This is additive.

---

### Phase 4 — Contracts, catalog, and one freshness primitive

---

#### **DOS-4.1 — Grow the registry to the top 25 datasets**

- **Objective.** Take `config/dataset_registry.yml` from 7 rows to ~25, covering the stores every
  ranked defect touches, under gate G1's honesty rule.
- **Priority.** P1.
- **Depends on.** DOS-2.1.
- **Systems/files.** `config/dataset_registry.yml`, `tests/test_dataos_registry.py`.
- **Expected output.** ~18 new rows, each with a verified `producer` and a verified `storage` path,
  or `status: PROPOSED`.
- **Agent class.** verification sweep with `Explore` (`model: 'sonnet'`); the rows themselves with
  `builder`.
- **Acceptance tests.**
  - Not done unless each `PRODUCED` row's producer was resolved by opening a file, not inferred
    from a filename. Two worked examples of the failure mode this prevents: the census reported
    `data/stocks`' writer as "unresolved", when it is
    `collectors/sector_holdings.py:259 class StockPriceAdapter` with `group = "stocks"` at line 263
    (VERIFIED) — *and the same collector also writes `data/stock_fundamentals`*, which no lane
    noticed.
  - Not done unless known-dead stores are represented **as a distinct state**, not omitted:
    `data/finnhub/recommendation.parquet` is declared by `engine/analyst_revisions.py:27-34`, wired
    into seven consumers, and **has never had a row written to it**
    (`collectors/finnhub_altdata.py:19-21`, VERIFIED). "Declared + wired + zero bytes" must be
    queryable, or the next session assumes the signal is live.
  - Not done unless `collectors/china_block_tape.py`'s docstring-only, never-applied wiring
    (`:73-81`) is represented as `PROPOSED`, not `PRODUCED`.
  - Not done unless the five census rows written from filename inference (`data/options_flow`,
    `data/options_entry`, `data/options_exit`, the Canada/HK fundamentals rows,
    `data/china_stocks_raw`'s "collectors A *or* B" producer) either get a real producer or enter
    as `PROPOSED`.
- **Migration risks.** The only real risk is dishonesty at scale. A 25-row registry with three
  wrong rows is more dangerous than a 7-row registry, because the wrong rows are now load-bearing.

---

#### **DOS-4.2 — One status-emission path for every collector**

- **Objective.** Make it impossible to add a collector that does not register freshness. Every
  producer — Adapter-registry or bolt-on — writes through one emitter.
- **Priority.** P1.
- **Depends on.** DOS-4.1.
- **Systems/files.** `scripts/collect.py` (the ~19 "additive, never fatal" bolt-on blocks, e.g.
  `sec_ftd` at :861-868 and the basket-OHLCV refresh at :600), `collectors/base.py`,
  `data/run_status.json`'s successor.
- **Expected output.** One emitter; the bolt-ons migrated; a guard that fails CI when a new
  `collect.py` call site writes to `data/` without emitting.
- **Agent class.** `builder`.
- **Acceptance tests.**
  - Not done unless `sec_ftd`, `redfin_hf`, `baskets` and `stocks` appear in the status artifact
    after one run — those four are currently invoked and currently absent (VERIFIED).
  - Not done unless each row carries an **expected cadence**, so a correctly-lagged feed does not
    false-flag. The worked example: `data/sec_ftd`'s ~37-day mtime staleness is *expected* — the
    vendor file is semi-monthly and `collectors/sec_ftd.py:5-16` documents a 30-day PIT lag, yet a
    naive mtime sort ranked it 4th-stalest. A staleness report without cadence metadata will spend
    its life crying wolf.
  - Not done unless the guard is shown red on a synthetic un-emitting bolt-on (gate G2).
- **Migration risks.** The bolt-ons are "additive, never fatal" for a reason — a nightly must not
  die because a scraper broke. The emitter must therefore be failure-tolerant itself: emitting
  `VENDOR_FAILED` is the success path, not an exception.

---

#### **DOS-4.3 — One freshness primitive, five callers**

- **Objective.** Replace five independently-coded staleness mechanisms with one, and anchor it on
  the deepest producer's own watermark rather than a downstream render's mtime.
- **Priority.** P1.
- **Depends on.** DOS-4.2.
- **Systems/files.** `app/main.py` (`/api/status` age_min), `admin/health.py:15`
  (`_STALE_HOURS=96.0`), `scripts/freshness_sentinel.py` (per-artifact budgets),
  `lib/project_runtime_state.py:69-79` (`_CADENCE_SPECS`),
  `engine/neuralweb/market_packet.py:173` (`QUOTES_STALE_MIN=45.0`).
- **Expected output.** One primitive in `lib/dataos/`; five callers reading it; thresholds moved
  into the registry's `freshness_sla_hours`.
- **Agent class.** `builder`, `reviewer` before merge (this touches the serving tier).
- **Acceptance tests.**
  - Not done unless the primitive reproduces the **Prophet re-stamp trap**: on 2026-08-08,
    `data/us_prophet_rank/candidates/2026-08.parquet` froze at `stamp_date 2026-08-05` while
    `us_stocks.html` kept re-baking daily, and **two of the five surfaces stayed green through it**
    (`scripts/freshness_sentinel.py:33-42`, VERIFIED). A test must show the new primitive going
    non-green on that shape.
  - Not done unless `engine/neuralweb/market_packet.py`'s docstring claim — "every rendered section
    starts with its own as-of stamp" (:27-30) — becomes **true**, or the docstring is corrected.
    Today only `tape`, `regional` and `cnboard` carry per-block `as_of`; breadth, leaders, drivers,
    shock, rates, vol and crossasset carry none (VERIFIED).
  - Not done unless the primitive's observation point does not depend on a hand-maintained checkout
    being clean (the §Evidence-warning constraint).
- **Migration risks.** Changing what counts as stale changes what users see. Land it as a shadow
  reading first, diff against all five incumbents for a week's worth of artifacts, then flip.

---

### Phase 5 — Fail-closed PIT readers

---

#### **DOS-5.1 — Heal the FRED vintage store, then promote `basis='release'`**

- **Objective.** Close the 28-series vintage gap, *then* make `pit_basis='release'` the default for
  research and backtest paths — in that order.
- **Priority.** P1.
- **Depends on.** DOS-4.2.
- **Systems/files.** `collectors/fred.py:42-62` (`DEFAULT_VINTAGE_SERIES`, 26 ids),
  `config.yml:124-169` (54 declared), `data/fred_vintage/vintages.parquet`, `engine/pit.py`,
  `engine/inputs.py:137`.
- **Expected output.** Two PRs: (a) collector + store healed to the declared 54; (b) the promotion,
  behind an explicit opt-out for the live render path if the operator wants the display number
  unchanged.
- **Agent class.** `builder` for (a); `builder` + `reviewer` for (b).
- **Acceptance tests.**
  - Not done unless the set-difference command that currently prints 28 missing series prints an
    empty set, pasted in the PR.
  - Not done unless the guard that was supposed to prevent this drift is fixed or replaced: a test
    exists (`tests/test_mri_config_spine.py`) yet the drift happened, which means it checks
    config-vs-code and not config-vs-**store**. Not done unless a check compares the config list to
    the on-disk series list (house trap: *a guard existing does not mean the artifact is current*).
  - Not done unless PR (b) reports the **measured delta** on at least one scored surface between
    `pit_basis=None` and `pit_basis='release'`, rather than asserting the fix is neutral.
  - Not done unless (b) is refused if (a) has not landed — promoting first converts a known
    latest-revised leak into a silent empty-falls-back-to-reference leak for 28 series, which is
    strictly worse because it is invisible.
- **Migration risks.** `basis='release'` changes historical scores. Anything already graded and
  published must not be re-scored (the `price_ladder` law generalizes here). Scope the promotion to
  *new* computations and backtests.

---

#### **DOS-5.2 — Backfill `membership_history.parquet` for all three suites**

- **Objective.** Give `engine/basket_membership_pit.py` the data it was built for, so
  `members_asof()` stops returning `pit=False` for every call on every date.
- **Priority.** P1.
- **Depends on.** DOS-1.1.
- **Systems/files.** `engine/basket_membership_pit.py:97-99`,
  `data/baskets_china_ths/snapshots/*.json` (the only raw evidence that exists: two dated files),
  `data/baskets/membership.json`, `data/baskets_china/membership.json`.
- **Expected output.** One `SNAPSHOT_SERIES`-profiled append-only store per suite, content-deduped,
  seeded from whatever dated evidence genuinely exists.
- **Agent class.** `builder`.
- **Acceptance tests.**
  - Not done unless `members_asof()` returns `pit=True` for at least one suite and one date, proven
    in the PR.
  - Not done unless the **seeding honesty** is explicit: for THS only two dated snapshots exist
    (2026-06-30, 2026-07-08), so the backfill covers eight days and says so. Backfilling from the
    current file and dating it historically would manufacture exactly the look-ahead being fixed.
  - Not done unless the US suite's inline `added`/`removed` dates are labelled
    **hindsight-curated** in the registry row — `engine/basket_index.py:27-28` already admits this
    ("like the baskets themselves the membership is ~hindsight-curated … a descriptive consolidated
    tape, not an out-of-sample backtest"), and the store must not launder that admission away.
- **Migration risks.** The tempting shortcut — write today's membership as the earliest snapshot —
  produces a store that *looks* PIT and is not. That is worse than `pit=False`, because `pit=False`
  is at least legible to a caller.

---

#### **DOS-5.3 — Date the Nasdaq and Russell archetype groups**

- **Objective.** Close the clearest unconditional look-ahead in the taxonomy layer.
- **Priority.** P2.
- **Depends on.** DOS-5.2.
- **Systems/files.** `data/baskets_nasdaq/membership.json`, `data/baskets_russell/membership.json`,
  `engine/cycle_pattern/registry.py`, `engine/nasdaq_internals.py`.
- **Expected output.** Per-member `added`/`removed` where a date can be honestly established; an
  explicit `PRE_INCEPTION`/`NO_COVERAGE` marker where it cannot.
- **Agent class.** `builder`.
- **Acceptance tests.**
  - Not done unless a member with no establishable date carries a `MissingReason`, not an invented
    date.
  - Not done unless a cross-suite reader test asserts that a naive uniform reader now *fails*
    rather than silently getting full look-ahead on these two suites.
- **Migration risks.** Windowing these groups changes every cycle-pattern statistic computed over
  them. Report the before/after on a pinned date rather than shipping the change silently.

---

#### **DOS-5.4 — A leak-free consensus panel for earnings estimates**

- **Objective.** Do for earnings/estimates what `fundamentals_panel.parquet` already did for EDGAR
  fundamentals: retain what was knowable, instead of only what is true now.
- **Priority.** P2 (P1 if any factor work consumes `eps_forecast`).
- **Depends on.** DOS-4.1.
- **Systems/files.** `collectors/equity_earnings.py:396-403`, `data/earnings/earnings.parquet`,
  and the five sibling mutate-in-place stores (`data/china_analyst/forecast.parquet`,
  `data/china_fundamentals/fundamentals.parquet`, `data/canada_fundamentals/`,
  `data/canada_earnings/`, `data/hk_fundamentals/`).
- **Expected output.** An append-only panel with our **own** `ingested_at`, not the vendor's
  retrospective labelling.
- **Agent class.** `builder`.
- **Acceptance tests.**
  - Not done unless the store carries a locally-stamped `ingested_at` per observation. The existing
    partial exception — `surprises_json`'s per-quarter `consensus` inside
    `data/earnings/earnings.parquet` — is **vendor-retrospective with no locally captured
    `known_at`**, so it cannot answer "what did we know before the print" and must not be presented
    as if it can.
  - Not done unless the current leak is quantified before the fix: `data/earnings/earnings.parquet`
    has **1,364 rows and only 2 distinct `as_of` values** (VERIFIED) — that number is the
    before-picture.
  - Not done unless the new panel is registered `REVISABLE_RELEASE` with `revision_seq`, so the
    profile itself forbids a PIT read that the data cannot support.
- **Migration risks.** Six stores share this shape; fixing one and leaving five is acceptable and
  should be stated, not hidden. Do not attempt all six in one session.

---

### Phase 6 — Reproducibility, lineage, receipts

---

#### **DOS-6.1 — Stamp `code_version` on produced artifacts**

- **Objective.** Make "the number moved" separable from "the code moved" for the ~332 `data/`
  stores.
- **Priority.** P1.
- **Depends on.** DOS-4.2.
- **Systems/files.** The pattern to generalize already exists and works —
  `engine/capital_structure/share_count_r2_conformance.py:750,766-767` **requires** a provenance
  block `{repository, workflow_ref, run_id, run_attempt, commit_sha, event_name, actor}` validated
  against a 40-hex `_COMMIT_SHA_RE`. The two other stampers are
  `engine/context_index/ingest.py:159,415-447` (`git_sha` per document) and
  `engine/neuralweb/capability_broker.py:249`.
- **Expected output.** That block promoted into the shared receipt idiom
  (`contracts/*_receipt.schema.json`) and emitted by the top ~10 producers. **No new store** (§D9).
- **Agent class.** `builder`.
- **Acceptance tests.**
  - Not done unless a store manifest that today carries only `{store, n_tickers, latest_date,
    updated_at, coverage, anchor}` — `data/massive_stock_day/_manifest.json`, VERIFIED — carries a
    commit sha after one run.
  - Not done unless the sha is **validated**, not merely recorded (reuse the existing 40-hex regex),
    and an empty `GITHUB_SHA` is a hard failure rather than an empty string written to disk.
  - Not done unless `data/index_gex_history/_manifest.json`, which names its engine
    (`"engine": "engine.gex_engine.compute_gex"`) but carries no version of it, gets one.
- **Migration risks.** Receipts must be additive to existing manifests; a schema replacement breaks
  readers. Add fields, never rename (the `latest.json` consumers include books trading real money).

---

#### **DOS-6.2 — Origination receipts on the standing Prophet path**

- **Objective.** Move receipt-writing from a one-off outage tool onto the nightly, so a plan's
  provenance is recoverable by construction rather than by forensics.
- **Priority.** P1 — see Q2, where the verdict is *no*.
- **Depends on.** DOS-6.1.
- **Systems/files.** `scripts/build_prophet.py`, `engine/prophet_bridge.py`;
  the pattern already exists in `scripts/backfill_prophet_outage.py`, whose three receipts carry
  `run.source_checkout` (a 40-hex sha), the GHA run id, the `sha256` of the exact
  `us_standouts.json` bytes read, and per-pick `plan_sha256`/`board_row_sha256`.
- **Expected output.** One receipt per nightly origination run; a `ranker_version` field stamped on
  the **board artifact itself**, not left in a script constant.
- **Agent class.** `builder`.
- **Acceptance tests.**
  - Not done unless a receipt is produced by the *standing nightly path*, not by a replay tool, and
    `git log --diff-filter=A -- 'data/prophet/origination_receipts/*'` shows a count above the
    current 3.
  - Not done unless a normal (non-forensic) reader can detect a ranker swap. The measured incident:
    the 2026-08-10 re-render swapped `us_prophet_v1 → us_prophet_v2` and board membership flapped
    78↔81 rows on an **identical `as_of`**, purely by render-host timezone
    (`scripts/backfill_prophet_outage.py:9-19`). Not done unless a test pins that the ranker version
    is now visible on the board.
  - Not done unless the render clock is pinned to a declared timezone, using
    `lib/dataos/temporal.utc`'s refusal of naive stamps as the mechanism.
  - Not done unless `research/PROPHET_LEDGER_SCHEMA.md` is updated: it documents an 11-field row
    while real rows carry at least seven more clock fields (VERIFIED). A stale schema doc *is* a
    reproducibility defect.
- **Migration risks.** The ledger is append-only and 11 of its 28 rows are already quarantined
  (VERIFIED: `git show HEAD:data/prophet/ledger_quarantine.json` → `"count": 11`, rule = a row whose
  `close_date` strictly predates the plan's own `asof`). Nothing in this task may rewrite a row;
  corrections go through `engine/prophet_integrity.py`'s append-only projection, whose
  `CORRECTABLE_FIELDS` allowlist deliberately excludes identity and geometry.

---

#### **DOS-6.3 — Catalog generation from the registry**

- **Objective.** One generated, committed catalog page + a `dataos catalog` query so a future
  session stops paying the discovery tax by grep.
- **Priority.** P2.
- **Depends on.** DOS-4.1.
- **Systems/files.** New `scripts/build_dataset_catalog.py`; `lib/dataos/registry.Registry.dag()`.
- **Expected output.** A generated markdown/JSON catalog + the static DAG. **No new store.**
- **Agent class.** `builder`.
- **Acceptance tests.**
  - Not done unless the catalog renders `PROPOSED` and `RETIRED` rows as visibly distinct from
    `PRODUCED` — the whole value is that the reader can tell.
  - Not done unless regeneration is idempotent and drift is CI-guarded (the repo already has this
    pattern for compiled blocklists).
- **Migration risks.** None material.

---

#### **DOS-6.4 — Formalize or deprecate the Terminal↔Macro filesystem seam**

- **Objective.** Replace the 17 hardcoded absolute paths into this repo's checkout with an R2/API
  handoff, or declare the coupling and gate it.
- **Priority.** P2, but rising — it is the reason none of that ingestion works on a CI runner or a
  second machine.
- **Depends on.** DOS-2.5.
- **Systems/files.** 17 files under `charting-app/ingest/` (`collect_us_deep.py`,
  `collect_cn_deep.py`, `collect_hk_deep.py`, `build_universe.py`, `sample_from_macro.py`,
  `pull_macro_risk.py`, `gc_orphans.py`, and others), each carrying
  `Path("/Users/chriswong/Documents/Cluade/Macro Dashboard")` (VERIFIED at
  `charting-app/ingest/build_universe.py:49`).
- **Expected output.** Either a declared, registered read-contract (an R2 prefix or an API), or an
  explicit deprecation with the seam documented in the cross-repo audit —
  `research/CROSS_REPO_CONTRACT_BOUNDARY_AUDIT_2026-08-11.md`'s 9-row bridge inventory **omits this
  entire coupling class** (VERIFIED).
- **Agent class.** `builder`; a `reviewer` pass on the cross-repo boundary.
- **Acceptance tests.**
  - Not done unless at least one ingest script runs to completion with `MACRO_REPO` unset and no
    sibling checkout present.
  - Not done unless the cross-repo audit gains the missing bridge row.
- **Migration risks.** Some of these scripts write **back** into this repo's `data/` directory,
  bypassing `collectors/base.py`'s Adapter and `ColumnContract` entirely. Removing the path without
  replacing the write side silently stops data arriving — which is exactly the failure mode with no
  error.

---

### Phase 7 — Metric canon (parallel to 4–6; blast-radius rank 5)

---

#### **DOS-7.1 — Canonicalize the primitive, not the concept**

- **Objective.** Add `atr` (and `adx`) to `engine/canon.py`, **derived from the existing `rma`
  primitive**, rather than fixing concepts one at a time.
- **Priority.** P1 within this phase.
- **Depends on.** DOS-1.0.
- **Systems/files.** `engine/canon.py` (`rma` at :311-333, `rsi` at :353-357),
  `engine/stock_technicals.py:58-60,72`, `engine/strategy_signals.py:65-74`,
  `engine/adaptive_trend_signals.py:274`; the already-correct SMA-seeded implementations at
  `engine/odds_lab.py:201-212,228` are the reference.
- **Expected output.** `canon.atr` + golden vectors in `tests/golden/canon_vectors.json`; the
  bare-EWM `_wilder` sites migrated.
- **Agent class.** `builder`.
- **Acceptance tests.**
  - Not done unless the golden vector distinguishes SMA-seeded Wilder from bare EWM in the **warm-up
    window**, which is where the two diverge and where crosses flip.
  - Not done unless the misleading call-site comments are corrected in the same PR:
    `engine/coiled.py:53`, `engine/postcross.py:54`, `engine/signal_quality.py:44` all assert "faithful
    Wilder RSI (== Pine ta.rsi)" over a function `engine/canon.py:353-357` says is *not* Pine-parity.
    An automated audit that trusts those comments certifies the wrong implementation.
  - Not done unless `engine/ohlc_reconstruct.py:82`'s `atr_proxy` is **left alone** and explicitly
    registered as a knowingly-different quantity — it is a deliberately close-only, deliberately
    wide proxy, not a broken ATR. Converting it is a regression, not a fix.
- **Migration risks.** Migrating ATR call sites changes published technical levels. Diff on a pinned
  date and report, per gate G7's consumption logic.

---

#### **DOS-7.2 — Units and annualization travel with the value**

- **Objective.** Make every emitted `realized_vol` carry `(window, annualization, return_type,
  units)`, so a ≈1587× disagreement cannot be silent.
- **Priority.** P1 within this phase.
- **Depends on.** DOS-7.1.
- **Systems/files.** the ten `realized_vol` definers, headed by `engine/vol_forecast.py:22-24`
  (unannualized, daily units) and `engine/stock_technicals.py:94-99` (log returns, ×√252, ×100).
- **Expected output.** A tagged emission convention + a registry-level `unit:` per column (the
  `DatasetContract.schema` already has the field).
- **Agent class.** `builder`.
- **Acceptance tests.**
  - Not done unless a test asserts that two differently-tagged series **cannot** be combined without
    an explicit conversion, and that the conversion is exercised.
  - Not done unless the ten definitions are *classified* (same-concept-different-units vs genuinely
    different quantity) before any is touched — the adversarial verifier's 5-of-8 result is the
    standing warning that this ratio is high.
- **Migration risks.** Renaming a widely-emitted field breaks consumers. Add the tag; do not rename
  the value.

---

#### **DOS-7.3 — Retire the impossible `XLC = 1.0` sector-macro beta**

- **Objective.** Make `engine/canon.py`'s shadow fix consumed, closing the wave's clearest example
  of a correct fix that changed nothing.
- **Priority.** P1 within this phase — it is live in a user-facing score today.
- **Depends on.** DOS-7.1.
- **Systems/files.** `config.yml:2994` (`XLC: 1.0`), `engine/conditions.py:1199-1211`,
  `engine/playbook.py:666`, `engine/canon.py:228-236`.
- **Expected output.** `playbook.py`'s heat penalty reading `canon.sector_macro_beta_blend`; the
  hand-pasted table retired.
- **Agent class.** `builder` for the wiring; `designer` review because the playbook card is
  user-facing.
- **Acceptance tests.**
  - Not done unless `canon.py:228-236`'s "SHADOW artifact (wired, NOT consumed this wave)" comment
    is **deleted** because it is no longer true.
  - Not done unless the before/after heat-penalty delta is reported per sector, with XLC named.
  - Not done unless a guard exists that fails when a canon entry is marked consumed but no
    production call site imports it — otherwise the next shadow artifact repeats this exactly.
- **Migration risks.** This changes a rendered number on every ticker's playbook card. It needs the
  design lane and a stated user-visible delta, not a silent flip.

---

#### **DOS-7.4 — The one high-yield null idiom, and the volume cluster**

- **Objective.** Fix the specific defect, not the grep.
- **Priority.** P2.
- **Depends on.** DOS-1.0.
- **Systems/files.** the 22 `(1 + <returns>.fillna(0)).cumprod()` sites
  (VERIFIED here: the census's regex returns `22`), of which only two carry an aliveness guard —
  `engine/indicators.py:55` (`.where(closes[cols].notna().any(axis=1))`) and
  `engine/oracle/timemachine.py:247` (`.where(alive)`). The 20 unguarded include
  `engine/baskets_intl.py:100`, `engine/china_narrative_tags.py:181`,
  `engine/commodity_index.py:182`, `engine/china_sector_index.py:98,215`,
  `engine/momentum_crash_gate.py:108`, `scripts/build_intl.py:675`, `scripts/oracle_nightly.py:763`,
  `scripts/oracle_screen.py:139`, `scripts/oracle_reversion_screen.py:323,668`.
  Second cluster: volume — `engine/stock_technicals.py:345,258`, `engine/volume_signature.py:89`,
  `engine/leader_lifecycle.py:547`, `engine/basket_tape.py:184`.
- **Expected output.** The `.where(alive)` guard applied to the 20; a detector that flags a *new*
  unguarded occurrence; `zero_is_meaningful: false` declared on the affected columns.
- **Agent class.** `builder`.
- **Acceptance tests.**
  - **Not done if the PR contains any clause targeting `fillna(0)` as a class.** On a 15-site
    sample, only ~13% are genuine null-as-zero defects; 53% are semantically correct zeros (a
    day-0 return, a count, an insider-activity zero that *means* "no filings"); 20% are
    arithmetically inert because they sit one line above an availability-weighted denominator
    (`engine/china_conditions.py:334-336`, `engine/axes.py:78-79`); 7% are grep false positives
    (`engine/active_commodity.py:119` is `fillna(0.5)`). A blanket rule would break 8 correct sites
    to fix 2.
  - Not done unless a test constructs a series with a halted / not-yet-listed session and asserts
    the index does **not** continue through it — the compounding of a flat day for a name that did
    not trade is the actual defect.
  - Not done unless the volume cluster's note is preserved: `data/yahoo` stores volume as `int64`
    while `data/stocks` stores `float64`, so a missing bar **cannot be represented as null** in the
    yahoo store. That is a schema fix, not a `fillna` fix, and belongs in its own task.
- **Migration risks.** Adding an aliveness guard changes index levels wherever a constituent was
  previously compounded flat. That is the correction, but it must be reported as a delta.

---

## §4 The four questions

### Q1. If five Mastermind subsystems were asked for AAPL's closing price on a historical date, would they return the same semantically correct answer?

**No — and for four independent reasons, only one of which is the well-known adjustment-basis
split.**

The five subsystems, named concretely:

1. **The nightly site/engine plane** — ≈135 files reading `data/stocks/<T>.parquet`'s `close`
   (VERIFIED count, §2.2), which is a **total-return** series.
2. **`engine/price_ladder.py`**, the de-facto price-resolution contract, which resolves a name
   through the first hit in `("baskets_ohlcv", "yahoo", "data_stocks", "baskets_extras")`
   (`engine/price_ladder.py:104`) and returns `adjusted=True` for all of them.
3. **The Terminal chart** (`charting-app`), whose per-symbol daily file is Macro-TR-seeded
   (`ingest/build_universe.py:49`) and Polygon-topped-up (`ingest/refresh_ohlc.py:38-39`).
4. **The Mastermind bot's marking layer** (`portfolio/marks.py:12-19`), whose declared precedence
   is `polygon-eod (raw/split-adjusted) > yahoo-parquet (TR-adjusted) > last-good-carry`.
5. **The whole-market scan plane** — `data/massive_stock_day`, the raw unadjusted store, read by
   `engine/us_scan_universe.py`.

**Reason 1 — three semantic bases.** `close` in `data/stocks` and `data/yahoo` is total-return;
`close_price` in `data/yahoo` is split-only; `close` in `data/massive_stock_day` is the raw print.
`collectors/yahoo.py:7-10` documents this correctly — **in a docstring only** — and the names invert
intuition: `close` is the total-return series while `close_price` is the traded basis the repo
itself calls "the correct basis for all structure math". That basis is **absent from the store 135
files read**.

**Reason 2 — adjustment vintage, which nothing in the repo models.** Over the full 86-ticker overlap
of `data/stocks` and `data/yahoo` — *the same semantic basis* — 25/86 disagree (worst HON 4.92%).
HON on 2025-09-25 reads **192.573517 / 192.419067 / 195.758713 / 201.964905** across the four stores
and all four converge to 227.800003 by 2026-06-29. One store back-adjusted through a later
distribution than another. So "adjusted" is not a boolean; it is a **(basis, as-of-vintage) pair**,
and no artifact in the estate records the second half.

**Reason 3 — `price_ladder`'s false equivalence makes the divergence invisible.** Its own premise is
that both legs of an excess return must share an adjustment basis, and its own resolution treats
three demonstrably-different vintages as one interchangeable family: 31/223 co-covered tickers
disagree >0.01% on a single date, 18 by >0.5%, max 4.877% — with **no consistent precedence**
(HON: `data/stocks` is the outlier; PEP: `data/baskets/ohlcv` is). A study whose universe resolves
some names via rung 1 and others via rung 3 has silently mixed two vintages into one cross-section.
The module *did* measure one pair rigorously (extras vs baskets: bit-identical on all 400 shared
names) and never measured the other three.

**Reason 4 — coverage and staleness are asymmetric within a single answer.** Store depth is
inverted against store breadth: `data/stocks/WMT` reaches 1972-08-25 while
`data/massive_stock_day` starts 2021-07-06 for every name and `data/baskets/ohlcv` starts
2014-01-02 for every name; `data/yahoo/NVDA` has 6,906 rows to 1999 while `data/yahoo/AAPL` has 756
rows to 2023-07-03. **Any "deepest history wins" rule silently changes adjustment basis with
lookback length.** And CMG has no `data/stocks` file at all, so a US large-cap resolves through a
different rung than its peers. Per-ticker tip staleness *inside* one store is also live
(`price_ladder`'s own docstring records `data/baskets/ohlcv` stopping at different dates for
different names), so an as-of read on one date silently drops some names.

**And the user can see it.** A single Terminal daily file carries a TR-adjusted historical segment
followed by split-only appended bars, with no per-segment provenance field, under a chip hardcoded
to claim "split & dividend adjusted" (`ChartFrameBar.tsx:381` + `i18n.tsx:285`). The bot has the
same defect in a different shape: on days Polygon answers it marks a position at a raw/split-only
EOD, and on days it falls back it marks at a TR-adjusted parquet — a day-to-day convention flip
inside one book's own NAV series.

**The measured cost of not fixing this** is already recorded in the repo: `engine/price_ladder.py`'s
docstring notes PNC at 2026-06-22 reading 234.71 in one commit and 232.85 five weeks later, and that
re-running `scripts/grade_us_board.py` against the shipped ledger would have moved **75
already-published rows, 19 materially**. A published track record moved by a store re-base is not a
rounding difference.

**The one honest caveat.** The four stores are not on the same date —
`data/massive_stock_day` sits four sessions behind the adjusted planes in the checkout that was
measured — so a naive cross-store comparison mixes a staleness gap with a semantics gap. The HON and
NVDA witnesses above are drawn on dates where all four stores have a bar, so they isolate semantics.
Any *new* comparison must do the same.

---

### Q2. Can Mastermind reconstruct exactly what Prophet knew at a historical decision timestamp, without using information that became available later?

**Verdict: No, for the great majority of the live plan book. Approximately 3 receipt files cover
~25–39 of ~162 live plans; for the other ~135 the exact producing code cannot be recovered from any
routine artifact, and the decision universe itself is recoverable only by walking git history of a
single overwritten JSON file.** That is a *provenance* failure, not a feature-computation failure —
and the distinction matters, because the feature math is actually sound.

**What is genuinely strong, and must not be rebuilt.** Prophet has a real bitemporal clock design:
`formation_date` / `price_basis_date` / `entry_date` / `recorded_at`, NYSE-session-validated and
fail-closed against staleness (`engine/prophet_bridge.py:67-94,820-906`). Its geometry math does not
leak: `engine/prophet_stage_inputs.py:200-218` truncates inputs to the entry bar before
classification, and `ec_sent_at_entry()` at :169-184 enforces `call_date < entry_date` *strictly*
("a call printed on the entry day itself is NOT usable"). The ledger is append-only with a
quarantine-not-edit discipline, and `engine/prophet_integrity.py:47-60` restricts corrections to an
allowlist that deliberately excludes identity and geometry fields.

**Why the answer is still no:**

1. **The candidate universe is a rendered site artifact, not a dated store.**
   `engine/prophet_bridge.py:20` names the source as `site/factordata/us_standouts.json`'s `buy[]`
   lane, read at `:1156` — one JSON file overwritten every render. Its only point-in-time record is
   git history of that one path. The commit count for it is itself checkout-dependent: I measured
   **45** on this worktree's branch history and **606** with `--all` (the census reported 195 from a
   different checkout), and the file is not even materialized in an agent worktree. A squash, a
   force-push, or a history rewrite on that path is an unrecoverable, silent reproducibility loss.

2. **No plan, no ledger row, and not even the ledger schema doc carries a code version.** A field
   dump of a stored plan (`site/prophet/plans/BA-BULL-20260702.json`) yields schema, id, asof, asset,
   direction, thesis, source_engines, trigger, entry, invalidation, targets, horizon_days,
   min_hold_days, tranche, option_contract, management_ref, authority_tier, reliability,
   signal_date, plus underscore-prefixed internals — and **no `engine_version`, `code_version`,
   `git_sha`, or `feature_version` anywhere** (VERIFIED). A grep for those names across
   `prophet_bridge.py`, `us_prophet_grades.py`, `prophet_integrity.py`, `prophet_stage_fusion.py`,
   `prophet_miss_audit.py` and the schema doc returns exactly one hit, and it is an unrelated
   government-revenue sidecar.

3. **The one mechanism that does it right exists only as a one-off.**
   `data/prophet/origination_receipts/` contains **3 files in all of git history**, all from the
   2026-08-09/08-11 outage, written by `scripts/backfill_prophet_outage.py` — an explicitly one-off
   force-majeure replay tool. Each carries `run.source_checkout` (a 40-hex commit sha), the GHA run
   id, the `sha256` of the exact board bytes read, and per-pick `plan_sha256`/`board_row_sha256`.
   The standing nightly path (`scripts/build_prophet.py`) writes **no receipt, no commit sha, no
   input hash**.

4. **A measured, already-diagnosed non-reproducibility.** That same backfill tool's docstring
   (:9-19) records that the 2026-08-10 evening re-render of an **identical `as_of`** swapped the
   ranker (`us_prophet_v1 → us_prophet_v2`), refreshed its options snapshot, and admitted ASTS/CRC/SVM
   through a wall-clock hole in the earnings-blackout gate — a `+08:00` render host read their
   2026-08-10 earnings as already past. **Board membership flapped 78↔81 rows by render-host
   timezone on the same nominal date**, and the ranker change was visible nowhere on the board
   artifact, only as an informal constant in a script.

5. **A named leak already fired, at scale.** `data/prophet/ledger_quarantine.json` (VERIFIED here)
   quarantines **11 rows on 2026-08-06** under the rule "a forward-ledger row whose `close_date`
   strictly predates the plan's own origination date" — e.g. `KKR-BULL-20260318` graded on a
   `close_date` of 2026-05-04 against an `origination_date` of 2026-07-14, a 71-day predate. Against
   a 28-row ledger that is **39%**. The handling is exemplary (disclose and exclude, never delete),
   but it proves the formation-vs-grading clock confusion was real and widespread.

6. **One gate input is architecturally starved in production.**
   `engine/prophet_stage_inputs.py:21-26` states that the earnings-call parquet is a gitignored,
   never-committed local backfill with no fetch/publish pair, so "on every CI and deploy host the
   file is simply absent" and every EC lookup answers `None`. The module now discloses this rather
   than degrading silently — a real fix — but the starvation is unresolved, so the EC leg of every
   live pick is unmeasurable in production.

**Exactly what would have to change** (this is DOS-6.2, plus two dependencies):

- **(a)** The nightly origination path writes an origination receipt per run, carrying the git sha,
  the GHA run id, and the `sha256` of the exact board bytes — i.e. `backfill_prophet_outage.py`'s
  block moved from the replay tool into `scripts/build_prophet.py`.
- **(b)** The board artifact itself carries `ranker_version`, so a swap is detectable by a normal
  reader rather than by forensics.
- **(c)** The renderer's wall clock is pinned to a declared timezone; `lib/dataos/temporal.utc`'s
  refusal of naive stamps is the enforcement point.
- **(d)** The candidate universe becomes a dated, append-only store rather than an overwritten file
  — `data/us_prophet_rank/candidates/YYYY-MM.parquet` is the right shape and already exists, but it
  post-dates 2026-08-08 and its own accrual shows an unexplained gap (`stamp_date` values stopping
  at 2026-08-07 while later commits touch the file). Fix the accrual, then make it the source.
- **(e)** `research/PROPHET_LEDGER_SCHEMA.md` is brought back into agreement with the rows it
  documents (11 fields documented, ≥18 present).
- **(f)** The EC store gets a fetch/publish pair, or the EC leg is declared permanently
  display-tier and removed from the gate.

For the ~135 plans originated before 2026-08-09, **(a)–(c) recover nothing retroactively.** The only
possible retroactive evidence is external — GitHub Actions run history and R2 object versions
correlated against plan `asof` dates — and whether that closes is an open question, not a plan.
Do not promise it.

---

### Q3. The five highest-blast-radius weaknesses, ranked

**1 — Identity fragmentation (≥10 seams, 3 incompatible id conventions, demonstrable disagreement).**
Ranked first because every other dataset joins on it, and because it is the only class with a
*measured* seven-month silent production loss (MMC absent from the deep store; `insurance` rendered
18/19 members, `us_sector_financials` 75/76). The disagreement is not theoretical:
`engine/ledger_identity.py:28-30` knows SATS→ECHO and records that it double-counted
`data/signal_archive/track_record.parquet`, while `lib/ticker_aliases.py` — the file most sessions
reach for — does not know it exists. `collectors/edgar_deadnames.py` documents a related structural
loss: **0 of 1,083 dead-only tickers** in `data/breadth/sp1500_pit_membership.parquet` carry
fundamentals, because a delisted CIK cannot be mapped back to its old ticker. And no user-facing
plane in any of the three repos carries a stable id at all — `watchlist_symbols.symbol`,
`alerts.symbol`, `favorites.value`, `portfolio_positions.ticker` are all bare text.

**2 — Price basis × adjustment vintage (≈135 readers on one store; 4 stores; a false-equivalence
resolver).** Ranked second on consumer count and on realized cost: this is the class that already
produced a stop-ship (`DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`) and the class whose re-base would
have moved 75 published ledger rows. The vintage axis makes it *worse* than the well-known basis
split, because two stores can carry the same declared semantic and still disagree by 4.92%. It is
also the only defect on this list that is visible to a paying user, via a hardcoded `ADJ` chip.

**3 — Macro point-in-time adoption gap (every live-scored consumer, ~20 call sites; plus 28 series
with zero vintages).** Ranked third because the fix is *already built* and unadopted —
`engine/pit.py` with a modelled release-lag calendar and an ALFRED as-of join, used by three shadow
scripts and nothing that scores. The leak is admitted in `engine/inputs.py`'s own docstring, and it
touches sector ranks, regime, bonds, allocation and the nightly site build simultaneously. The
28-series vintage gap is what makes this rank 3 rather than 2: promoting the fix today would move
the leak rather than close it.

**4 — Sessions, calendars and halts (≈60-70 literal-bearing files; 4 early-close models, 3
out-of-scope; zero halt store).** Ranked fourth because it silently corrupts *cross-sectional*
statistics rather than single numbers. A halted name and a genuinely flat name are indistinguishable
in every store, and the resolution is silent exclusion in `engine/theme_crowding.py:47`,
`engine/group_flow.py:91`, `engine/synthetic_control.py:454` and `engine/bar_derive.py:365` — an
unmeasured, daily-grain survivorship mechanism inside every published cross-sectional read. Plus a
scheduled failure: CN holidays are hardcoded through 2027-12-31, HK lunar tables through 2030, both
degrading silently.

**5 — Metric canon gaps and unit drift (canon covers 6 families; `atr`/`realized_vol` have no
canonical referent; ~1587× unit divergence; a live impossible beta).** Ranked fifth, deliberately
below the four above, because the corrected counts are much smaller than the folklore: 5 of 8
sampled "duplicate" definers compute a genuinely different quantity, and ~23 of the cited duplicates
are canon **gaps** rather than violations. What keeps it on the list at all is not the count but two
specific live defects — `realized_vol` producers disagreeing by three orders of magnitude with no
unit tag, and `config.yml:2994`'s physically-impossible `XLC: 1.0` still feeding a user-facing
playbook score while `engine/canon.py:228-236` records its own fix as unconsumed.

**Named, and deliberately not in the top five:**
Taxonomy PIT (`membership_history.parquet` exists for zero suites) is severe but has a smaller
consumer set than any of the five, and the *dateless* Nasdaq/Russell suites are the acute part.
Catalog coverage (149/332 dirs, ~19 status-bypassing bolt-ons) is the enabling condition for
everything else rather than a defect in its own right. And the six mutate-in-place
earnings/fundamentals stores are a real look-ahead surface, but the same lesson was already learned
and fixed once in this repo (`fundamentals_panel.parquet` superseding the leaky
`fundamentals.parquet`), so it is a generalization task rather than a discovery.

---

### Q4. The minimum viable Data OS

**Six things. Everything else is an extension of one of them, and most of the six already exist in
some form.**

**1. One identity spine.** `lib/dataos/identity.py` (delivered) + a materialized security master and
a **time-scoped** vendor alias table (DOS-1.1). Time-scoped is the load-bearing word: a table that
answers "what does yahoo call this today" is exactly the two-row dict that lost MMC for seven
months. It must answer "what did yahoo call this on 2025-12-01".

**2. One temporal vocabulary with a fail-closed PIT reader.** `lib/dataos/temporal.py` (delivered).
The mechanism is `assert_pit_readable` raising instead of returning the latest vintage, and
`DERIVED` deliberately not being PIT-readable. This is a ~290-line module, not a platform.

**3. One price-basis law plus a vintage clock.** The naming law and the measured store-bases map are
delivered (`lib/dataos/price.py`); the missing minimum is `adjustment_asof` on every adjusted
dataset and a resolver that stops asserting three vintages are one basis (DOS-2.2). Corporate
actions (DOS-2.4) are in the minimum only because without them `adjustment_asof` cannot be *derived*
— it can only be observed.

**4. One registry.** `config/dataset_registry.yml` (delivered, 7 rows) grown to the ~25 datasets the
ranked defects touch, under the honesty rule. The registry is simultaneously the contract plane
(§D5), the lineage DAG (§D9), and the catalog — one file, three jobs, no new store.

**5. One missing-reason vocabulary.** `lib/dataos/nulls.py` (delivered). Nine closed values. A
consumer must be able to act differently on `NOT_YET_AVAILABLE` (wait), `POST_DELISTING` (stop
asking), `VENDOR_FAILED` (retry and alarm) and `HALTED` (no print exists) — which is impossible
when all four arrive as the same `NaN`.

**6. One provenance stamp.** A `code_version` (git sha) + input hashes on every produced artifact,
generalizing the block that `engine/capital_structure/share_count_r2_conformance.py:750,766-767`
already requires and validates. Without it, "the number moved" cannot be separated from "the code
moved" for any of the ~332 stores, and no backtest in the estate is attributable.

**What is deliberately excluded from the minimum, and why:**

- **A feature store.** §D10's verdict is NO, and the census makes it stronger, not weaker: one
  already exists, scoped to the market-memory replay subsystem, with `FEATURE_REGISTRY_VERSION`, a
  `FeatureSpec` carrying `transform_version`, and an `availability_class` vocabulary
  (`engine/neuralweb/market_memory.py:147-157,185,335-339`). We do not have a serving-skew problem —
  features are computed once nightly in one pipeline. Extend `engine/canon.py`; do not build a
  second store.
- **A lineage service.** §D9's lineage is registry DAG + receipts. Two of the three pieces already
  exist. A lineage platform would be a new store to answer a question a `walk + read` answers.
- **Full bitemporal modelling of everything.** Bars never revise; forcing them into a bitemporal
  table is pure cost. That is why `TemporalProfile` is a closed vocabulary of six shapes and only
  `REVISABLE_RELEASE` mandates `revision_seq`.
- **A cache tier.** Caching today is 100% in-process, and **Redis is not used anywhere** — zero real
  client sites; the earlier count was a substring match on "redistribution". The masterplans reject
  it by name: files + parquet + R2 + git, "Boring wins." Building a cache tier to fix a problem
  nobody has measured would be the definition of scope inflation.
- **Rewriting any store.** All four US price stores stay. The V1 migration is *labels*: the registry
  declares each store's measured basis and a shim exposes basis-suffixed names, so ≈135 readers keep
  working unchanged.
- **A serving-tier query engine.** `app/` and `admin/` read pre-materialized JSON and touch zero
  parquet (VERIFIED: `read_parquet` count is 0 across all 29 `app/*.py` and 58 `admin/*.py`). That
  is a *good* boundary. The Data OS should make it an explicit invariant, not retrofit a query API
  under it.
- **A second ownership registry.** `config/sector_intelligence_ownership.yml` already exists — 477
  lines, `one_writer_required: true`, `duplicate_writer_behavior: hard_fail`, test-enforced by
  `tests/test_sector_intelligence_ownership.py`, and referenced by sha from a source manifest. Its
  scope is the sector-intelligence/biocatalyst/capital-structure domains; **no price, macro, options,
  news or CN store has an owner row, and that is the gap**. Extend that file. A duplicate would
  violate its own `hard_fail` spirit and the standing `duplicate_control_planes` prohibition.
- **A migration runner.** There is none anywhere, and the three mechanisms in use (manual SQL apply
  with the repo file as the replay record; a new `_vN` schema file beside the retained old one; a
  bespoke one-shot python migration per store) are the honest inventory. A Data OS spec that says
  "add a migration" as if a runner existed is writing fiction. Adding one is out of scope for V1.

**How small is it, concretely?** Items 1, 2, 3(partial), 4(seed), 5 are **~4,100 lines already on
disk with ~370 passing tests — a moving figure; re-measure before quoting it**. (VERIFIED
2026-08-12: `wc -l lib/dataos/*.py tests/test_dataos_*.py` → 4,112 (lib/dataos 2,383 + tests 1,729);
`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_dataos_*.py --collect-only -q` → 369 tests
collected, matching the `369 passed` run quoted in §1.3. The tree is untracked and a concurrent lane
is still writing it, so both numbers drift.) The remaining minimum is roughly: one security-master builder, one
vintage field plus one resolver fix, ~18 registry rows, one corporate-action collector, and one
receipt block generalized from an existing one. That is five to seven sessions of work, not a
platform.

---

## §5 What we are not building, and why (§D11)

Restated as refusals, each with the reason it would be a mistake *here* rather than in general.

| Not building | Why not, specifically |
|---|---|
| **Kafka / any streaming bus** | There is no streaming consumer. Features are computed once nightly in one pipeline; the serving tier reads pre-materialized JSON. A bus would add an ops surface to move data between two steps of one process. |
| **Snowflake / Databricks / a warehouse** | The house pattern is files + parquet + R2 + git, stated and defended in the masterplans ("Boring wins"). The render budget is ~67 minutes on a 4-core self-hosted box; a warehouse does not fit that constraint, it replaces it. |
| **Data-mesh vocabulary** | Explicitly rejected by §D11. "Domain-oriented decentralized data ownership" is what this repo already has, and the problem is that the domains share no vocabulary — new nouns do not fix that. |
| **A lineage SaaS or lineage platform** | §D9's lineage is registry DAG + receipts, and two of three pieces already exist (`contracts/*_receipt.schema.json`, `Registry.dag()`). Runtime instrumentation would be a new store to answer a static question. |
| **Event sourcing** | Bars never revise. An append-only event log for an immutable daily bar is pure cost with no recoverable guarantee. The two places that genuinely need append-only — the Prophet forward ledger and the fundamentals raw ledger — already have it. |
| **Full bitemporal modelling of every dataset** | Same reason. `TemporalProfile` exists precisely so that `BARS` mandates three clocks and `INTELLIGENCE` mandates seven, instead of every table paying the maximum. |
| **A feature store** | §D10: the measured defect is duplicate definitions, not online/offline skew, and a versioned feature registry with PIT machinery **already exists** at `engine/neuralweb/market_memory.py:147-157`. Building a second one would create the exact duplication being fixed. |
| **A cache/Redis tier** | Zero real Redis client sites in the tree. The ~19 module-level engine caches are unkeyed *by design* because each nightly gets a fresh process. That assumption should be made explicit and guarded, not replaced with infrastructure. |
| **Rewriting or collapsing any store** | ≈135 readers on `data/stocks` alone. V1 labels; V2 derives. A rewrite would be a flag day across four stores, three repos and a live product. |
| **A second control plane, authority map, or strategic state** | Standing cross-repo prohibition (`duplicate_control_planes`). Company strategic state lives in the Mastermind repo and is read through its validated reader; a Macro-side copy read by a Mastermind runtime is exactly the authority hop that file forbids. |
| **A second data-ownership registry** | `config/sector_intelligence_ownership.yml` exists and is test-enforced. Extend it to cover the price/macro/options/news/CN domains that currently have no owner row. |
| **A migration runner** | None exists; three ad-hoc mechanisms are in use and are the honest inventory. Building one is a real project with its own risk, not a side effect of a data-contract wave. |
| **Unifying `DNR:HOLD-FF-DETECTOR-PERIOD-BASIS`** | Four shared `detector_id`s pair periods three different ways and gate PIT three different ways, deliberately HELD, because making them agree silently republishes a live user-facing surface. §D10 requires the registry to *register* the divergence. Registering is mandatory; resolving is a product decision. |
| **Deciding whether the CN spine goes live** | `collectors/china_tushare_spine.py` is 3,600+ lines of validated ingestion whose operational gate is false and whose declared store root does not exist on disk. That is an operator decision under `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`'s reopen path, not a Data OS task. This plan treats the spine as **the authority for CN identity conventions and dormant for CN data**. |
| **Collapsing the three "portfolio" concepts** | Terminal's `portfolio_positions` (manual user log), Macro's `portfolio_brief.v1` (descriptive composition) and Mastermind's autonomous paper books have different owners and different write paths, and `research/CROSS_REPO_CONTRACT_BOUNDARY_AUDIT_2026-08-11.md` F-08/F-20 explicitly forbids inferring a bridge between the first and third. |
| **A `fillna(0)`-as-a-class rule** | Measured: ~13% genuine defects, 53% semantically correct zeros, 20% arithmetically inert. A blanket clause would break eight correct sites to fix two. The high-yield target is one idiom (22 sites, 20 unguarded) plus the volume cluster. |
| **Making `data/massive_stock_day` "the raw reference"** | Its own manifest reports 19,133 tickers against 20,476 files, 471 processed days in a ~1,255-session window, and an 832-weekday maximum missing run, with the SPY anchor at 454 rows. It is a ~37%-populated store with multi-year holes. It can be *a* raw source; it cannot be the reference without a freshness SLA and a gap contract. |

---

## §6 Self-audit

Every sentence in this document was re-read against one question: *could a reader check this?*
Claims that survived carry a `file:LINE`, a command with its output, or an explicit INFERRED /
NEEDS-CORROBORATION label. Three classes were handled specially:

- **Numbers that drift with the tree** (`data/stocks` reader count, session-hour literal count,
  `us_standouts.json` commit count) are reported with *my own* command and result alongside the
  source figure, and the tasks that depend on them require a re-measurement rather than a citation.
- **Anything resting on a file mtime or `git log` from the materialized-data checkout** is labelled
  NEEDS-CORROBORATION, per the §Evidence-warning, and is not allowed to carry an acceptance
  criterion.
- **Mechanisms that cannot be verified in-repo** — most notably HON's spinoff as the cause of the
  four-way divergence, and Polygon's `adjusted=true` being split-only — are labelled INFERRED. The
  first is INFERRED *because* the corporate-action store does not exist, which is itself the
  finding, and DOS-2.4's acceptance test is written to convert it to VERIFIED.

**Citation count, measured rather than estimated.** Counted with:

```
$ python3 -c "
import re
t=open('research/MASTERMIND_DATA_OS_V1_IMPLEMENTATION_PLAN.md').read()
h=[x.replace(' ','') for x in re.findall(
   r'[A-Za-z0-9_./-]+\.(?:py|yml|yaml|json|md|tsx|ts|sql)\s*:\s*\d+(?:[-,:]\d+)*', t)]
print(len(h), len(set(h)), len({x.split(':')[0] for x in h}))"
166 133 108
```

**133 distinct `file:LINE` citations (166 occurrences) across 108 distinct source files**, plus 103
distinct file paths cited without a line anchor, plus 7 fenced command-and-output blocks and further
inline commands quoted with their results, plus 3 standing-adjudication keys
(`DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`, `DNR:HOLD-FF-DETECTOR-PERIOD-BASIS`,
`DNR:KILL-PSS-F3-RESIDUAL`) cited by key rather than by row number.

Uncited factual sentences remaining: zero by intent. Every claim not carrying a `file:LINE` carries
an explicit VERIFIED-by (naming the lane or this session), INFERRED, or NEEDS-CORROBORATION marker.
