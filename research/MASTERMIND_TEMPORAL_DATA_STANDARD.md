# Mastermind Temporal Data Standard

**Status:** MANDATORY for all future quant work in this repo. Implements `DESIGN_SPEC D3` (temporal model)
and the parts of `D1`/`D9` that carry clocks.
**Date:** 2026-08-12 · **Scope:** Macro Dashboard, and by contract every artifact it publishes to
`/Users/chriswong/Documents/Cluade/charting-app` (Terminal) and `/Users/chriswong/Documents/Cluade/Mastermind`
(trading bot).
**Reference implementation:** `lib/dataos/temporal.py` (in flight in this worktree at the time of writing —
`git ls-files lib/dataos/` returns nothing, so it is untracked and owned by the concurrent `lib/` lane).
This document is the normative text; that module is the executable form of §3–§7.

Every claim below carries a `path:LINE` citation or a command plus its output. VERIFIED means the author of
this document ran it. INFERRED means it is reasoning over evidence that is itself cited. Standing
adjudications are cited as `DNR:<KEY>`.

---

## 0. Read this first: there is a live look-ahead leak in the scoring path, and the fix already exists

### 0.1 The leak

`engine/inputs.py::build_features()` is the single feature frame every macro-consuming engine reads
(`engine/inputs.py:1-6`: *"Everything downstream (axes, transition detector, sector ranks, backtest) reads
this one aligned business-day DataFrame"*). Its point-in-time control defaults to off:

```
engine/inputs.py:137     def build_features(pit_basis: str | None = None,
engine/inputs.py:142-147     pit_basis : SHADOW point-in-time control (audit #5/#14/#39, masterplan W1a).
                                 None (default) -> current live behaviour, BYTE-IDENTICAL output (the live
                                 render/collect path never passes this argument).
engine/inputs.py:179-182     if pit_basis is not None:
                                 from engine import pit as _pitmod
```

With `pit_basis=None` the router at `engine/inputs.py:190-195` is never entered, so every revision-prone FRED
column is served from the reference-stamped, latest-revised store: the value is stamped on the month it
*describes* and forward-filled, not on the day it was *published*.

**VERIFIED — the default is what production calls.** Every one of these call sites passes zero arguments:

| call site | what it fits or publishes |
|---|---|
| `scripts/build_site.py:4664` | the nightly site build |
| `scripts/build_bonds.py:1381` | bond scoring |
| `scripts/build_transmission.py:42` | rate/inflation transmission |
| `scripts/build_spvector.py:174` | the S&P vector board |
| `scripts/calibrate_spvector.py:138`, `scripts/calibrate_spvector_phase2.py:35`, `scripts/calibrate_spvector_phase3.py:69`, `scripts/calibrate_spvector_phase4.py:48` | spvector parameter fits |
| `scripts/calibrate_macro_betas.py:61` | macro beta fits |
| `scripts/calibrate_bonds.py:199` | bond model fits |
| `scripts/calibrate_rate_inflation.py:368` | rate/inflation model fits |
| `scripts/calibrate_hk.py:108`, `scripts/calibrate_china.py:103` | HK / CN regime fits |
| `scripts/tune.py:61` | parameter tuning |
| `scripts/ab_risk_gate.py:112` | risk-gate A/B |
| `scripts/regime_snap_history.py:65`, `scripts/refresh_regime_if_stale.py:163` | regime history |
| `engine/run.py:202`, `engine/china_run.py:37`, `engine/canada_run.py:39`, `engine/regime_one.py:968` | the run entrypoints |

Command: `grep -rn "build_features(" scripts engine | grep -vc "def build_features"` → **82** call sites
(VERIFIED, this worktree). Exactly **three** of them pass `pit_basis=`, and all three are shadow/audit or a
display-provenance helper (`engine/regime_one.py:215` describes `release_row` as provenance):

| non-default call site | mechanism |
|---|---|
| `scripts/validate_drawdown_risk_pit.py:172` | `pit_basis=` router (`build_features(pit_basis=basis)`, basis ∈ release/reference) |
| `scripts/shadow_pit_regime.py:199-200` | `pit_basis=` router (`"latest"` vs `"release"`) |
| `engine/regime_one.py:954` | `pit_basis=` router (`pit_basis="release", pit_as_of=pit_as_of`) |
| `scripts/build_regime_v2_pit.py:362-372, 376` | **not the router** — PIT achieved by pre-computed macro `overrides=` |

Command: `grep -rn "pit_basis" scripts/build_regime_v2_pit.py` → **no output** (VERIFIED). That script
reaches its point-in-time leg by a fourth, separately-implemented mechanism: it builds a dict of merged
vintage leg series (`scripts/build_regime_v2_pit.py:362-372`) and injects it as
`build_features(overrides=overrides)` at `:376` — the only `overrides=` caller in `scripts/` or `engine/`
(`grep -rn "overrides=" scripts engine | grep build_features` returns that one line). The injection path
**bypasses the PIT router entirely**: `engine/inputs.py:184-188` takes the `overrides` branch *before* the
`_pit_series` branch and comments that it *"skips the pit router — the caller supplied this column
explicitly."* Its sibling `scripts/build_regime_v2_pit.py:383` (`f_rev = build_features()`, zero arguments)
is a deliberate revised-latest **control** leg, not an exception to §0.1 — by the taxonomy above it is a
leaking call site, and that is what it is for.

**This injection seam is a distinct point-in-time construction** and is counted as such in §0.7: it has its
own vintage-panel merge (`pit_availability_panel` / `merged_leg_series`), its own per-leg coverage-start
bookkeeping (`:363-371`), and its own silent-degradation mode — a leg with no vintage rows logs a warning and
**stays latest-revised** (`scripts/build_regime_v2_pit.py:368-371`) while the frame is still labelled PIT.

### 0.2 The sharpening the census under-stated — and it changes the remediation

The census lane wrote "every live-scored engine leaks." That is one word too broad, and the correction
matters because it decides what to fix first.

`build_features()` returns a *history*. For the **last row** — today — reference stamping and release
stamping largely agree: a period FRED has not published is not in the store at all, so it cannot be read
early, and for "what is core PCE right now" the latest-revised value is the *correct* answer, not a leak.
The damage is in **every prior row**, which is exactly what a fit consumes. So:

- **Live current-state read** (today's row on the site): reference-stamped latest-revised is correct. Not a leak.
- **Historical read** — parameter fitting, backtests, published track records, any regime *history*:
  reference-stamped latest-revised is a genuine look-ahead on both axes named in
  `research/PIT_LEAKAGE_TAX.md:13` (timing leak #5) and `:14` (revision leak #14).

The ~14 `calibrate_*` / `tune.py` / `ab_risk_gate.py` call sites in the table above are therefore the
priority, not the render path. They fit coefficients on a frame that knew payrolls a median 34 days early
and INDPRO 45 days early (`research/PIT_LEAKAGE_TAX.md:36-44`).

**INFERRED, flagged:** this refines the census claim; it does not refute `D3`. `D3`'s PIT law is unchanged.

### 0.3 The measured cost

`research/PIT_LEAKAGE_TAX.md:50-53` reports the leak-free quad label disagreeing with the live quad on
**17.2% of the last 5 years (1,305 days) and 15.8% of the full 1999–2026 span (7,151 days)** — and
`research/PIT_LEAKAGE_TAX.md:57` records the disagreement concentrated at turning points: 2001 at 57%
agreement, 2025 at 63%, 2020 at 78%, versus 90–96% in calm trend years. A model fit on the leaked frame is
fit hardest-wrong exactly where it is asked to earn its keep.

### 0.4 The fix is built, tested, and parked

`engine/pit.py` is a complete leak-free accessor:

- `engine/pit.py:22-31` — `basis='release'` documented as *"the LEAK-FREE frame"*: an as-of join on
  ALFRED `realtime_start` for vintaged series, a modelled release-date shift for the rest.
- `engine/pit.py:63-90` — `VINTAGED_SID_TO_COL`, 26 revision-prone FRED series mapped to live-frame columns.
- `engine/pit.py:110-143` — `DEFAULT_RELEASE_LAGS`, a per-series release-lag calendar with a provenance note
  on every entry.
- `engine/pit.py:181-191` — `_effective_lag_bd()` resolves lag in ascending precedence
  `lag_bd < lag_bd_measured < lag_bd_learned`. **This closes a census open question**: the accessor prefers
  the ALFRED-*measured* lag (CPI 32 bd, core PCE 42 bd, ECI 86 bd) over the optimistic prior (8/20/20 bd).
  There is no "leak inside the leak-fix".
- `engine/pit.py:243-267` — `release_availability()`, the availability stream keyed by first-publication date.
- `engine/pit.py:335-379` — `series(name, as_of, basis, index, ffill_limit)`, the public reader.
- `collectors/fred.py:239-252` — `as_of_series(series, asof)`, the same as-of join at the collector layer.
- `tests/test_pit_accessor.py:43,53,70` — the leak-free invariants are already pinned by test.

`engine/pit.py:11-12` states plainly: *"This module is the SHADOW accessor that produces a leak-free frame.
It never touches the live path."*

**This is an adoption gap, not a capability gap.** Any proposal to "build point-in-time infrastructure" is
rejected on sight by `D0`'s corollary. The work is wiring, plus §0.5.

### 0.5 The vintage store has drifted behind its own config — fix this before promoting anything

**VERIFIED** by content read (no mtime, no git log — see the caveat in §12):

```
$ python3 -c "import pandas as pd; df=pd.read_parquet('data/fred_vintage/vintages.parquet'); \
    print(len(df), df['series'].nunique())"
10103 26

$ python3 -c "import yaml; print(len(yaml.safe_load(open('config.yml'))['fred']['vintage_series']))"
54
```

The set difference is 28 series declared PIT-tracked in `config.yml:124-169` with **zero rows on disk**:
`ADPMNUSNERSA, AMTMUO, AMTMVS, AWHAETP, AWHMAN, BUSLOANS, CAPUTLG2211S, CAPUTLG331S, CAPUTLG3344S,
CAPUTLG334S, CES0500000003, CMRMTSPL, CUSR0000SAS, IPG2211S, ISRATIO, JTSJOL, MNFCTRIRSA, NEWORDER,
PCU331110331110, PCU334413334413, PERMIT, RSAFS, UEMPMEAN, UNRATE, USGOVT, USPRIV, W875RX1, WPU0543`.

The on-disk 26 are **set-identical** to `collectors/fred.py:42-62 DEFAULT_VINTAGE_SERIES` (verified: symmetric
difference is empty). Since `collectors/fred.py:161-162` returns the config override whenever it is present,
the store's content proves the last successful `fetch_vintages()` write ran against the code default, not the
current 54-member override. **INFERRED from content alone** — deliberately not from file mtimes.

Two mechanisms make this silent:

1. `collectors/fred.py:201-203` — no `FRED_API_KEY` ⇒ log a warning and return an empty frame. Never raises.
2. `collectors/fred.py:246-252` — `as_of_series` returns an **empty Series** when the vintage frame is
   missing or the series has no rows. A caller asking for `UNRATE` as-of 2019 gets silence, not an error.

`engine/pit.py:265-267` then falls through to `_modelled_release()` — the calendar-shifted **latest-revised**
value. So promoting `basis='release'` today would move 28 series from "knowingly leaking" to
"believed leak-free while actually serving revised finals through a modelled lag." That is worse, because it
is invisible. **Fix the store first.** This is the concrete instance of the fail-closed law in §5.

### 0.6 The remediation, in order

| # | Action | Why here |
|---|---|---|
| 1 | Run a keyed `fetch_vintages()` so the 28 configured-but-absent series materialize; add a check that compares config to **on-disk** series, not config to code constants | §0.5 — everything downstream is only as leak-free as its stalest input. `config.yml:120-121` says `tests/test_mri_config_spine.py` guards this invariant; the data shows the guard cannot be checking the parquet |
| 2 | Route the ~14 `calibrate_*` / `tune.py` / `ab_risk_gate.py` sites to `build_features(pit_basis='release')` | §0.2 — these are the ones that fit coefficients on leaked history |
| 3 | Stamp `pit_basis` on every calibration receipt and on every published historical series | a number whose basis is not recorded cannot be re-derived |
| 4 | Only then consider the live default | see the warning below |

**Do NOT silently flip the default.** `tests/test_pit_accessor.py:91-98` and `:115-124` assert that
`build_features()` equals `build_features(pit_basis=None)` on both the frame and the regime table; changing
the default reds both. That is the test doing its job. Flipping the default republishes every scored macro
number on a user-facing surface in one commit — the same hazard `DNR:HOLD-FF-DETECTOR-PERIOD-BASIS` was
raised to prevent. Promotion is a product decision with a disclosure, not a cleanup.

### 0.7 The seventh and eighth implementations (why the standard exists at all)

`scripts/calibrate_spvector_pit.py` — a script whose title is *"ALFRED point-in-time validation"* — builds
the **leaky** frame at `scripts/calibrate_spvector_pit.py:73` (`f = build_features()`, no args), then
hand-swaps two legs using a locally defined 9-line as-of join, `pit_daily()` at
`scripts/calibrate_spvector_pit.py:35-43`, duplicating both `engine/pit.py:243-267` and
`collectors/fred.py:239-252`.

Two consequences, both checkable:

1. **Partial-PIT hazard, committed by the validator.** `engine/inputs.py:148-151` warns in its own docstring
   that a partial leg set is a hazard and that the shadow frame moves *"a full leg set together"*.
   `scripts/calibrate_spvector_pit.py:80-91` swaps exactly two legs (`RECPROUSM156N`, `THREEFYTP10`) and
   leaves the rest revised.
2. **The verdict can pass vacuously.** `pit_daily` returns an all-NaN Series when the series is absent
   (`scripts/calibrate_spvector_pit.py:38-39`); the caller then skips the swap
   (`:85`, `:87` guard on `.notna().any()`). If both series were missing, `f_pit` would equal `f`, both
   allocations would be identical, and the `holds` test at `scripts/calibrate_spvector_pit.py:111-112`
   would emit *"CONFIRMED — the edge holds on genuinely point-in-time data"* (`:114-116`) having compared
   the frame to itself. Both series happen to be present in today's store, so this is a latent, not an
   active, defect — but it is the exact shape of "a receipt derived from what it checks cannot fail."

That is ten independent, locally-plausible point-in-time constructions across the repo
(`lib/dataos/temporal.py:3-8` enumerates six; `scripts/calibrate_spvector_pit.py:35`,
`collectors/edgar.py:836-851`, and `engine/basket_membership_pit.py:623` are three more; the tenth is the
`overrides=` injection seam of §0.1 — `scripts/build_regime_v2_pit.py:362-372, 376`, which reaches PIT
without ever touching the `pit_basis` router that `engine/pit.py` exists to serve). The cost of ten is
not ten bugs — it is that no one can say whether the system is correct.

---

## 1. The seven times

Seven named times, six of which are instants. `period_start`/`period_end` are two columns carrying **one**
concept — an interval label, not a clock. Enumerated in code at `lib/dataos/temporal.py:95-113`.

| Name | Kind | Meaning | Calcbench name | Answers |
|---|---|---|---|---|
| `period_start` / `period_end` | interval label | the interval the observation *describes*: a bar, a fiscal quarter, a CPI reference month | — | "what is this about" |
| `event_at` | instant | when the economic event occurred: a trade, a halt, an announcement | — | "when did it happen" |
| `effective_at` | instant | when the information becomes *applicable*: a split's effective date, an index membership date | — | "from when does it bind" |
| `published_at` | instant | when the SOURCE made it knowable | `accepted_at` | "when could anyone know" |
| `ingested_at` | instant | when Mastermind received it | `recorded_at` | "when could **we** know" |
| `computed_at` | instant | when our pipeline derived it | `computed_at` | "when did we compute it" |
| `served_at` | instant | when it became visible to a consumer | `published_at` | "when did we say it" |

Plus the revision chain — `revision_seq` and `supersedes` — which is not a clock (§8).

The Calcbench five stay valid and keep their deployed names where already in production
(`research/CALCBENCH_PARITY_WAVE_3A_BITEMPORAL_QUERY_BUILD_DOCKET_2026-08-02.md:40-48` names
`accepted_at`, `recorded_at`, `mapping_available_at`, `computed_at`, `published_at`). Nothing in the
Wave-3A fundamentals estate is renamed by this document; the mapping above is how a cross-domain reader
translates.

**A period end is not a clock.** A daily bar's `period_end` of 16:00 ET is not a moment anyone learned
anything; the vendor published the bar minutes later, and we ingested it hours later. Reading `period_end`
as availability is the timing leak of §0 in its purest form.

---

## 2. `temporal_profile` — the closed vocabulary

Every dataset declares exactly one `temporal_profile` in the Data OS registry (`D5`). The profile — not the
table, not the caller — decides which clocks are mandatory and whether a point-in-time read is lawful at all.
Enumerated at `lib/dataos/temporal.py:116-128`, required clocks at `:151-166`, required non-clock fields at
`:168-177`.

| Profile | Mandatory clocks | Mandatory fields | Also required | PIT-readable |
|---|---|---|---|---|
| `BARS` | `period_start`, `period_end`, `ingested_at` | — | `session`, `venue_scope`, price basis per `D4` | yes |
| `REVISABLE_RELEASE` | `period_end`, `published_at`, `ingested_at` | `revision_seq` | append-only; `supersedes` on a correction | yes |
| `SNAPSHOT_SERIES` | `effective_at`, `ingested_at` | — | append-only, content-deduped | yes |
| `EVENT` | `event_at`, `published_at`, `ingested_at` | — | — | yes |
| `DERIVED` | `computed_at` | `code_version`, `input_cutoffs` | — | **no** |
| `INTELLIGENCE` | `computed_at`, `served_at` | `code_version`, `input_cutoffs`, `data_cutoff_at`, `expires_at` | append-only served log | yes, via `served_at` |

Notes that are load-bearing:

- **`BARS` is deliberately thin.** `D11` forbids full bitemporal modelling of datasets that never revise.
  Bars do not revise; forcing them into a bitemporal table is pure cost. A bar store needs only
  "which interval, and when did we get it".
  *Exception that proves the rule:* a bar store carrying an **adjusted** price is not a pure `BARS` dataset —
  adjustment is revisable, so it additionally carries `adjustment_asof` per `D4`. See §9.
- **`DERIVED` is NOT point-in-time readable, on purpose.** Its clocks answer "can I recompute this", which is
  a different question from "what did we know at t" (§6). `lib/dataos/temporal.py:45-50` states the reason.
- **`SNAPSHOT_SERIES` is content-deduped, not calendar-stamped.** `engine/basket_membership_pit.py:24-33`
  gives the measured reason: a full THS snapshot is ~3,500 member rows, stamping one nightly would add
  ~1.3M rows/year that say nothing, and *"the membership in force at date D is the newest snapshot ≤ D"*
  is unaffected by the dedup.

### 2.1 Profile assignment for the datasets the census enumerated

Assignments below are the *required* profile. Where a store cannot currently satisfy it, that is named.

| Dataset | Profile | Satisfies it today? |
|---|---|---|
| `data/fred/<SID>.parquet` (VERIFIED `ls data/fred \| wc -l` → 166) | `REVISABLE_RELEASE` | **no** — carries the reference index only, no `published_at`, no `revision_seq` |
| `data/fred_vintage/vintages.parquet` | `REVISABLE_RELEASE` | **yes** — `realtime_start` *is* `published_at`; verified columns `['series','period','value','realtime_start','realtime_end']` |
| `data/cleveland_nowcast/nowcast.parquet` | `REVISABLE_RELEASE` | **yes, by construction** — `collectors/cleveland_nowcast.py:15-16`, `:123-130`: keyed `(target_period, series, obs_date)` with `keep="first"`, and it carries a `first_seen_asof` column (`:58`) that *is* `ingested_at` |
| `data/stocks`, `data/yahoo`, `data/baskets/ohlcv`, `data/massive_stock_day` | `BARS` + `adjustment_asof` | **no** — see §9 |
| `data/edgar/statements_quarterly.parquet` | `REVISABLE_RELEASE` | **partly** — VERIFIED column read (§10.2) shows `filed`; the only US fundamentals store that has it |
| `data/edgar/statements.parquet` (annual) | `REVISABLE_RELEASE` | **no** — VERIFIED no `filed` column; `collectors/edgar_facts.py:154` "latest-filed wins on restatement", i.e. prior vintages discarded |
| `data/edgar/fundamentals_panel.parquet` | `REVISABLE_RELEASE` | **proxy** — `asof_date = period_end + 120d` (`collectors/edgar.py:469-471`, default at `:516`); an honest, declared approximation of `published_at` |
| `data/earnings/earnings.parquet` | `REVISABLE_RELEASE` | **no** — mutate-in-place; see §11.2 |
| `data/<suite>/membership_history.parquet` | `SNAPSHOT_SERIES` | **yes** — `engine/basket_membership_pit.py:17,141` key `(snapshot_date, basket_id, ticker)`, keep-FIRST |
| `data/polygon_gex/*` | `BARS` (EOD chain snapshot) | **now yes** — after the session re-stamp; see §7.3 |
| corporate actions | `EVENT` | **does not exist** — see §9 |
| `site/prophet/plans/*.json`, `data/prophet/ledger.jsonl` | `INTELLIGENCE` | **partly** — clocks yes, `code_version` no; see §11.5 |
| the 77 `forward_log` artifacts (`git ls-files \| grep -c forward_log` → 77) | `INTELLIGENCE` | the house's existing replay primitive |

---

## 3. `known_at` — the coalesce rule

```
known_at := coalesce(published_at, ingested_at)      -- the dataset declares which it has
```

Implemented at `lib/dataos/temporal.py:183-190` (`KNOWN_AT_CLOCKS`) and `:259-276` (`known_at()`).

Three rules, no exceptions:

1. **`published_at` wins when present.** It is the earlier and stricter clock: information becomes knowable
   to the world before it becomes knowable to us. Using `ingested_at` where `published_at` exists over-states
   our ignorance and silently degrades a backtest's realism in the *safe* direction — which is why it is
   permitted as a fallback and forbidden as a preference.
2. **`INTELLIGENCE` coalesces to `served_at`**, not to `published_at`/`ingested_at`
   (`lib/dataos/temporal.py:189`). For our own output, "when did anyone know" *is* "when did we serve it".
   That is the replay clock of §6.
3. **A row that carries none of its profile's promised clocks is an error, not a filter.**
   `lib/dataos/temporal.py:272-276` raises rather than including it (leakage) or dropping it (an invisible
   hole). Both silent options produce a number nobody can audit.

`effective_at` is deliberately **not** in the coalesce chain. Effectivity and knowability are different
questions and conflating them is a recurring bug. Illustrative, not a repo claim: an index membership change
announced two weeks before it takes effect was knowable from the announcement, so a strategy that treats the
effective date as the knowledge date is understating its own information set — and one that treats the
announcement date as the *effective* date is holding a position the index does not yet have. Carry both;
join on `known_at`; gate the position on `effective_at`.

---

## 4. Timezone law

Four rules.

1. **Storage is tz-aware UTC.** Every instant column is stored tz-aware in UTC. A naive timestamp in storage
   is a contract violation.
2. **A naive datetime RAISES. Never guess.** `lib/dataos/temporal.py:193-223`: a tz-naive datetime is refused
   with a message naming the fix, and a bare `date` is refused too, because promoting a date to an instant is
   the same guess. The reason is stated at `:52-55` — CI runs UTC while this repo's operator works US-eastern
   evenings, so the same naive stamp means two different instants depending on which machine produced it.
3. **Session logic uses the exchange timezone, resolved from the exchange calendar — never a wall clock.**
   Three calendars exist and are the authority: `lib/nyse_calendar.py` (`ET = ZoneInfo("America/New_York")` at
   `lib/nyse_calendar.py:31`), `lib/cn_calendar.py`, `lib/hk_calendar.py`.
4. **A session date is a *derived* value, not a formatted timestamp.** `nyse_calendar.session_date(now_utc)`
   (`lib/nyse_calendar.py:255-265`) and `nyse_calendar.expected_last_session(now)`
   (`lib/nyse_calendar.py:188-196`) are the two lawful ways to get one. `date.today()` and
   `datetime.utcnow().date()` are forbidden for this purpose — `lib/nyse_calendar.py:240-242` says so in
   prose, and §7.3 is the incident that put it there.

### 4.1 A conflict this standard must resolve, not paper over

`lib/nyse_calendar.py:191-192` and `:257-258` accept a naive datetime and `replace(tzinfo=timezone.utc)` it,
documented as *"the pipeline's convention"* (`lib/nyse_calendar.py:188`, `:248`). The new law
(`lib/dataos/temporal.py:212-216`) raises on exactly that input. Both cannot be right.

**Ruling:** the calendar's assume-UTC is grandfathered at its two existing call sites and is **not** a pattern
to copy. New code normalizes through `lib.dataos.temporal.utc()` before it reaches the calendar. The
grandfather exists because the calendar is stdlib-only by design (`lib/nyse_calendar.py:1-8`: *"pure rule
arithmetic, zero data dependencies, stdlib only"*) and because its failure mode is conservative — assuming
UTC on a naive stamp produces a *later* ET time, which at worst under-reports how many sessions the store is
behind. It is a documented, bounded compromise, not a licence.

### 4.2 The in-repo incident that proves rule 2

The strongest evidence for "never guess" is a bug this repo already shipped and then documented.
`engine/session_digest.py:333-336`:

> *"`engine/live_flow._minute_key` localizes NAIVE exchange timestamps as UTC before converting to ET, so the
> tide/dte minute labels run a whole timezone offset early — a real 09:30–16:00 session is labelled
> 05:30–11:59. The series itself is correct and monotone; only the labels lie."*

The vendor's naive string `"2026-07-02T14:30:00"` means 14:30 **ET**; the reader assumed UTC; the whole
session shifted by the offset. `engine/live_flow.py:1088-1099` now carries the corrected rule and states it
as a per-source declaration: *"ThetaData v3 trade timestamps arrive as NAIVE exchange-local
(America/New_York) wall-clock strings … So a naive input is localized to ET, never UTC … One rule for the
whole function: naive means exchange time."*

That fix is correct and is exactly what rule 2 asks for — but note *where* it lives. The knowledge "this
vendor's naive stamps are ET" is a **property of the source**, and it is recorded in a parsing helper deep in
one consumer. Under this standard it belongs in the `DatasetContract` (`D5`) as a declared source timezone,
and the parser calls `lib.dataos.temporal.utc()` after applying it. The rule is not "naive is UTC" or "naive
is ET" — it is **"naive is a contract violation unless the contract says what it is."**
`engine/session_digest.py:336-338` also records the tell that separates the two: the surface stamps were
unaffected *"because they come from an aware UTC datetime"*.

### 4.3 There is no session-hours service, and there should be

`grep -rlE "09:30|16:00|9:30" engine scripts lib collectors | wc -l` → **49 files** carry session-hour
literals (VERIFIED, this worktree). Sampled sites label their timezone locally —
`engine/event_calendar.py:106` `"time_et": "16:00"`, `engine/session_digest.py:270`
`"09:30–16:00 ET" / "09:30–13:00 ET"` — so most of these are not naive/aware bugs today. It is a
single-source-of-truth gap: a DST edge or an early-close rule fixed in one file does not reach the other 48,
and `lib/nyse_calendar.py:11-13` already declares early closes out of scope for the calendar of record.
**PROPOSED** (`D12` phase 3): fold the three calendars into one session service answering
`session_bounds(venue, date) -> (open_utc, close_utc, is_early_close)`, and make the 49 literals read from it.

---

## 5. The fail-closed point-in-time law

> **A dataset whose profile lacks the clock needed to answer `known_at` is FORBIDDEN from point-in-time
> reads and must RAISE — never silently return the latest value.**

Implemented at `lib/dataos/temporal.py:244-256` (`assert_pit_readable`), with the refusal reason produced
separately at `:226-241` so the caller's next move is legible. `as_of_filter()` at `:279-292` calls it before
touching a row.

The reason this is a *law* and not a preference is stated at `lib/dataos/temporal.py:9-12`: the failure mode
*"is not an exception: it is a silent latest-vintage return. A backtest reads today's revised CPI into 2019
and scores beautifully. Nothing goes red."* Three live instances of that failure mode, all cited above:

- `collectors/fred.py:246-252` — empty Series on a missing vintage series.
- `engine/pit.py:265-267` — falls through to a calendar-shifted **latest-revised** value when a vintage row is
  missing, which is precisely a leak wearing the label `basis='release'`.
- `scripts/calibrate_spvector_pit.py:38-39` + `:85-87` — all-NaN leg, swap silently skipped, verdict prints
  "genuinely point-in-time" anyway.

### 5.1 Two tiers of refusal (this is what makes the law shippable)

The house epistemics law says context/detection infrastructure ships **display-tier freely** — a null never
blocks building. A hard raise everywhere would contradict that. The reconciliation:

| Tier | On an unanswerable `known_at` | Template in repo |
|---|---|---|
| **Display / context** | serve the degraded answer **with a machine-readable basis flag and a plain-word note** | `engine/basket_membership_pit.py:623-644,699-703` |
| **Research / backtest / calibration / promotion** | **RAISE** | `lib/dataos/temporal.py:244-256` |

`members_asof()` is the model for the display side, and its docstring states the contract better than a spec
can (`engine/basket_membership_pit.py:629-635`):

> *"`pit` is the contract. `True` means the answer came from a stored snapshot dated ≤ `date`
> (point-in-time, safe to measure on). `False` means the store does not cover `date` … and the answer is the
> CURRENT membership applied backward, which is exactly the look-ahead basis §2.12 flagged. A caller that
> measures on a `pit=False` answer is contaminating its own study; the flag exists so that is a decision,
> never an accident."*

**Rule:** any research-tier caller of a display-tier PIT reader MUST check the flag and raise. A
`pit=False` result reaching a fitted coefficient, a ranked board, or a graded ledger row is a defect in the
caller, not in the reader.

### 5.2 Fail-closed also means "declare the hole"

A dataset that is wired into consumers but has never had a row written is a distinct state from healthy and
from never-wired. `data/finnhub/recommendation.parquet` is the case: `engine/analyst_revisions.py:27-34`
reads it, and `collectors/finnhub_altdata.py:19-21` records in its own docstring that the file
*"has therefore NEVER existed, and seven consumers … have been reading a missing store and failing open to
null the whole time."* The registry (`D5`) must be able to express `declared · wired · zero rows`, because
today the only evidence is a comment.

---

## 6. Reproduce ≠ replay

Adopted verbatim from the Calcbench ruling
(`research/CALCBENCH_PARITY_WAVE_3A_BITEMPORAL_QUERY_BUILD_DOCKET_2026-08-02.md:56-57`):

> *"Running a 2022 filing through a rule written in 2026 is a current-rule recomputation, not a 2022 system
> replay."*

Two distinct guarantees. Do not claim one and deliver the other.

| Guarantee | Definition | Required of | What you must store |
|---|---|---|---|
| **Recomputable** | same inputs + same code version → same output | L3 `DERIVED` | `computed_at`, `code_version` (git sha), input dataset ids **with their vintages/hashes** |
| **Replayable** | what the system *actually emitted* at time t | L4 `INTELLIGENCE` | an append-only served-artifact log carrying `served_at` |

This is why `DERIVED` is not PIT-readable (§2). Its clocks answer the recompute question and cannot answer
the knowledge question; serving an as-of read from a `DERIVED` table *is* the current-rule recomputation the
ruling names. The refusal message at `lib/dataos/temporal.py:230-237` says exactly this, and names the two
lawful exits: promote the dataset to `INTELLIGENCE` (which carries `served_at`), or read its **inputs** as-of
and recompute.

The replay primitive already exists at scale: 77 tracked `forward_log` artifacts
(`git ls-files | grep -c forward_log` → 77), including `data/prophet_miss_audit/forward_log.jsonl` and
`data/prophet_scan_tier/forward_log.jsonl`. **Do not build a new one.**

`research/CALCBENCH_PARITY_WAVE_3A_BITEMPORAL_QUERY_BUILD_DOCKET_2026-08-02.md:50-55` is also the model for
what to do when you *cannot* honour a clock: Wave 3A's formula cells leave `computed_at` and `published_at`
**empty** rather than inventing a historical artifact, and label the result an
`on_demand_cutoff_projection`. Emptiness plus a label beats a fabricated timestamp.

---

## 7. Revision handling

### 7.1 Append-only; corrections are rows, never edits

A `REVISABLE_RELEASE` dataset is append-only. A revision is a **new row** for the same
`(entity, period)` carrying `revision_seq = prior + 1`, its own `published_at`, and `supersedes` pointing at
the row it replaces. `revision_seq` is mandatory for the profile (`lib/dataos/temporal.py:170`).

Consequences:

- `as_of(t)` selects, per `(entity, period)`, the row with the greatest `known_at <= t`. Not the greatest
  `revision_seq` — that is the latest-vintage read that started this document.
- An initial-release study reads `revision_seq = 0`. `collectors/fred.py:255-262` (`initial_release`) already
  serves this; ALFRED `output_type=4` at `collectors/fred.py:183` is what makes it one row per period.
- A "correction" that overwrites is forbidden. `collectors/edgar_facts.py:154` — *"latest-filed wins on
  restatement"* — discards prior vintages and is therefore non-conforming; the Wave-3A engine models the same
  facts correctly as immutable typed events (`engine/fundamental_forensics/raw_ledger.py:113-124`:
  `AMENDMENT`, `COMPARATIVE_RECAST`, `RESTATEMENT`, `SOURCE_CORRECTION`, `PARSER_CORRECTION`,
  `MAPPING_CORRECTION`). Extend that vocabulary; do not invent a second one.

### 7.2 A poisoned row is quarantined and disclosed, never deleted

The house pattern, and it is the right one:
`data/prophet/ledger_quarantine.json` (read via `git show HEAD:data/prophet/ledger_quarantine.json`) declares

- `rule`: *"a forward-ledger row whose close_date strictly predates the plan's own origination date
  (plan.asof) — the outcome was scanned from the base formation anchor, so it was graded on bars the plan was
  never live for"*
- `effect`: *"the row STAYS in ledger.jsonl (append-only); every reader that summarises the record excludes
  these ids from both numerator and denominator"*
- `count`: 11, `quarantined_on`: 2026-08-06.

**Rule:** a discovered temporal defect in an append-only store is handled by adding a quarantine record with a
stated rule and a stated exclusion effect. Deleting the row destroys the evidence that the defect happened
and makes the record look better than it was.

### 7.3 A run clock is not a session clock

`scripts/migrate_polygon_gex_session_stamps.py:4-10` records the measured incident:
`build_polygon_gex.accrue` stamped `datetime.now(timezone.utc).date()` — *"the RUN date, not the session the
snapshot describes. A nightly run that lands at 01:24 UTC carries the PREVIOUS ET session's closing chain but
was filed under the next calendar day, so the whole store sat one session forward of the market it measures,
and the write-side `is_session` gate then REFUSED every Saturday-UTC run — which is a Friday-evening ET
accrual. That is why Fridays are missing from the store."* Re-resolving each file's accrual instant through
`nyse_calendar.expected_last_session` reproduced the data — *"30 of 42 files verify SPY spot == the yahoo
close of the resolved session to the cent"* (`scripts/migrate_polygon_gex_session_stamps.py:12-16`). The
census reports the full reclassification as 42 files → 29 sessions with 5 quarantined; that count is
census-sourced and not independently re-run here.

Two lessons, both mandatory:

1. `period_end` for a session-scoped artifact is resolved from the exchange calendar, never from the run's
   wall clock (§4 rule 4). `scripts/migrate_polygon_gex_session_stamps.py:17-19` even names which helper is
   wrong for this: `session_date()` calls the whole ET calendar day "the session", so at 02:24 ET Wednesday it
   returns Wednesday for a chain carrying Tuesday's close — `expected_last_session` is the correct helper for
   an accrual.
2. **Verify a snapshot's timestamp on the cross-section, not on one name.**
   `scripts/migrate_polygon_gex_session_stamps.py:21-24`: *"SPY alone called the 08-06 file '0.175% — fine'
   while 59% of its names disagreed: its spot column is a live pre-market tape, not 08-05 closes."*

Identity is separately protected: hashing a per-run clock into the identity of a content artifact is
forbidden by `DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY`.

---

## 8. Derived and intelligence artifacts: version-stamping

`DERIVED` requires `code_version` and `input_cutoffs`; `INTELLIGENCE` adds `data_cutoff_at`, `served_at` and
`expires_at` (`lib/dataos/temporal.py:168-177`).

The gap here is measured and large. Per the census (`[VERIFIED]` by the prophet lane), no stored Prophet
plan, ledger row, or the ledger schema doc carries an `engine_version` / `git_sha` / `feature_version` field;
the only artifacts in the entire chain that pin an exact commit plus an input content hash are **3**
`data/prophet/origination_receipts/*.json` files written by a one-off backfill tool
(`scripts/backfill_prophet_outage.py`), covering a fraction of ~162 live plans.

The cost of the missing stamp is not hypothetical. `scripts/backfill_prophet_outage.py:16-21`:

> *"the 2026-08-10 evening re-render swapped the ranker (`us_prophet_v1` -> `v2`), refreshed its options
> snapshot, and admitted ASTS/CRC/SVM through a wall-clock hole in the earnings-blackout gate (a +08:00
> render host past local midnight read their 2026-08-10 earnings as already past — one-sided lookahead).
> Board membership measurably flapped 78<->81 rows by render-host timezone on an identical `as_of`."*

That single sentence contains both failures this document exists to prevent: a **timezone guess** (§4) and an
**unversioned derivation** (§6). Same nominal `as_of`, two different boards, no artifact recording which
code produced which.

**Rule:** any artifact at L3 or L4 that is published, graded, or read by another repo carries `code_version`
(git sha) and the vintage or content hash of each input. The receipt idiom already exists —
`contracts/*_receipt.schema.json`, and the origination receipt's own shape (`run.source_checkout` = a 40-hex
git sha, `source.sha256` of the exact bytes read) is the template. Generalize the template; do not design a
new one (`D9`).

---

## 9. Adjustment vintage is a temporal quantity

This is `D4`'s territory, restated here because it is a *clock* problem, and because the standard's readers
will otherwise mis-handle it.

An adjusted price is not a fact about a day; it is a fact about a day **as computed on some later day**. A
corporate action re-scales all prior history, so the same `(ticker, date, basis)` legitimately has different
values in two copies of the series pulled at different times.

**VERIFIED** — HON, four US daily stores, one date:

```
$ python3 -c "import pandas as pd; ..."   # /Users/chriswong/Documents/Cluade/Macro Dashboard
data/stocks/HON.parquet          close        2025-09-25  192.573517   cols ['close','high','low','volume']
data/yahoo/HON.parquet           close        2025-09-25  192.419067   cols ['close_price','close','volume']
data/yahoo/HON.parquet           close_price  2025-09-25  195.758713
data/baskets/ohlcv/HON.parquet   close        2025-09-25  201.964905   cols ['open','high','low','close','volume']
data/massive_stock_day/HON.parquet close      2025-09-25  207.700000   cols ['open','high','low','close','volume','transactions']

# same four stores, 2026-06-29:
data/stocks 227.800003 · data/yahoo 227.800003 · data/baskets/ohlcv 227.800003 · data/massive_stock_day 227.7
```

The decisive pair is `data/stocks/HON.parquet::close` (192.573517) versus `data/yahoo/HON.parquet::close`
(192.419067). Both are the **same basis** — `D4` labels both `close_tradj`, and `collectors/yahoo.py:6-13`
documents `close` as the total-return series. Two identical-basis copies of one number differ by 8 bp, and
they converge to the cent at the recent end. Basis cannot explain that. **Adjustment vintage can, and nothing
else can.** VERIFIED by column read: none of the four stores carries an `adjustment_asof` column, so the
vintage is unrecoverable from the artifact.

**Law:** `adjusted` is a **(basis, as-of-vintage) pair, never a boolean.** Every adjusted dataset carries
`adjustment_asof`. The only fully reproducible storage is `_raw` plus a corporate-action factor table with
`_sadj`/`_tradj` derived on read (`D4`).

### 9.1 The house already knows this, and already has half the mechanism

This is not a novel diagnosis — it is a documented, *measured* property of the collector, and there is a
working detector for it that simply does not record what it learned.

`collectors/yahoo.py:15-18`:

> *"Adjustment-basis guard: both stored bases are re-adjusted by Yahoo at every fetch, so a 1mo window pulled
> after an ex-div/split disagrees with stored history on every overlap date. `store.basis_shifted` detects
> that and the name is re-pulled `period='max'` instead of spliced (see `_rebase_shifted`)."*

`lib/store.py:106-127` is the detector, and its docstring carries the measurement:

> *"yfinance re-adjusts the WHOLE series at every fetch, so splicing a short re-based window onto stored
> history strands every pre-window row on a stale basis: seam-crossing returns/SMAs go silently wrong and an
> unnoticed split is a 10x level step (measured: `data/yahoo/SPY.parquet` uniformly +0.2576% off a fresh
> fetch on all 8,382 rows before 2026-05-18 — exactly one dividend of drift)."*

It also records why the obvious fix does not work: *"`upsert(overwrite_overlap=True)` cannot fix this class:
it makes the fresh pull own its OWN span but never touches rows older than the window"*
(`lib/store.py:114-117`), and it fails **safe** on ambiguity — no overlap at all also returns `True`
(`lib/store.py:121-123`), which is the §5 posture applied to price basis.

So the repo can already *detect* a vintage shift and responds by discarding the window and re-pulling
`period='max'` — which makes the whole stored series carry one consistent adjustment vintage, namely
"whenever the last full refetch happened". **That value is exactly `adjustment_asof`, and it is thrown away.**
The `D4` V1 work is therefore smaller than it looks: `_rebase_shifted` (`collectors/yahoo.py:150`) is the one
place that knows the vintage, and writing it to a sidecar is the whole of the fix for `data/yahoo`.
Extend `store.basis_shifted`; do not design a new adjustment tracker.

**There is no corporate-action event store, and the repo declares its own absence.** VERIFIED:
`config/market_memory_technical_price_basis.v1.json:25` pins `"point_in_time_corporate_actions": false`
inside a `limitations` block, and the same constant is asserted in three contract schemas and two engine
modules (`contracts/market_memory/spy_daily_price_source_observation.v1.schema.json:246` pins it as a
`{"const": false}`; `engine/neuralweb/market_memory_technical_store.py:133`). The same file pins
`"split_adjusted": false` (`:16`), `"other_corporate_action_adjusted": false` (`:18`) and
`"split_detection": false` (`:26`). A corporate-action
store is therefore **PROPOSED**, on profile `EVENT`, keyed `(msec_id, action_type, ex_date)` with clocks
`event_at` (announcement), `effective_at` (ex-date), `published_at`, `ingested_at`.

Why this is not optional: `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` stop-shipped an entire CN limit-alpha
program because a vendor-*adjusted* price was used where the exchange's raw print was the only lawful input.
An undeclared adjustment vintage is the same class of error, one step quieter.

---

## 10. Worked examples

Each shows the WRONG read, why it is wrong, and the RIGHT read. All APIs cited are real and their signatures
verified.

### 10.1 A CPI print — period vs release vs revision vs vintage

Four different times for one number. The June 2026 CPI reference month is `period_end = 2026-06-30`; BLS
published it ~32 business days later (`published_at`; the repo's own ALFRED-measured CPI lag, `engine/pit.py:115`);
we fetched it that night (`ingested_at`); BLS may revise the seasonal factors months later (`revision_seq = 1`,
carrying its own `published_at`).

```python
# WRONG — the leak of §0. The store is reference-stamped and latest-revised, so the June value
# appears on 2026-06-01 and carries whatever BLS has revised it to by the time you run this.
from engine.inputs import build_features
f = build_features()                       # pit_basis defaults to None: engine/inputs.py:137
cpi = f["core_cpi_yoy"]                    # derived at engine/inputs.py:354-361
model.fit(cpi.loc["2015":"2024"], y)       # fitted on 32 business days of look-ahead per print
```

Why: `engine/pit.py:3-9` — reference stamping *"bakes a look-ahead into every historical row"*; the measured
CPI release lag is 32 business days (`engine/pit.py:115-116`, `lag_bd_measured=32`, the documented prior of 8
being *"optimistic"*).

```python
# RIGHT — route through the accessor, full leg set together.
from engine.inputs import build_features
f = build_features(pit_basis="release")    # engine/inputs.py:179-195 routes the revision-prone columns
cpi = f["core_cpi_yoy"]
model.fit(cpi.loc["2015":"2024"], y)

# RIGHT, single series, at one rebalance date:
from collectors.fred import as_of_series
s = as_of_series("CPIAUCSL", "2019-03-15")   # collectors/fred.py:239 — as-of join on realtime_start
if s.empty:
    raise RuntimeError("no CPIAUCSL vintage coverage as of 2019-03-15 — refusing a PIT read")
    # ^ MANDATORY. collectors/fred.py:246-252 returns an empty Series on a missing store; §5.
```

Do not swap "the two legs that have vintages" and call the result point-in-time — that is §0.7.

### 10.2 An earnings print — fiscal period / report timestamp / filing timestamp / vendor ingestion

Four clocks again, and they are days to weeks apart: `period_end` (fiscal quarter end), `event_at` (the press
release / call), `published_at` (SEC acceptance — the `filed` timestamp), `ingested_at` (our sweep).

```python
# WRONG — today's consensus joined to a past print.
import pandas as pd
e = pd.read_parquet("data/earnings/earnings.parquet")
est = e.loc[ticker, "eps_forecast"]         # what we last fetched, not what was knowable pre-print
surprise = actual - est
```

Why: VERIFIED — `data/earnings/earnings.parquet` has 1,364 rows and exactly **two** distinct `as_of` values
(`2026-06-14T05:02:19.950433+00:00`, `2026-06-19T02:36:58.649552+00:00`); `eps_forecast` is rebuilt wholesale
each sweep at `collectors/equity_earnings.py:399-404`. There is no retained history of the estimate, so any
join to a past earnings date is pure look-ahead. The census fundamentals lane reports five sibling stores
sharing the `{ticker, payload, asof}` mutate-in-place shape — `data/china_analyst/forecast.parquet`,
`data/china_fundamentals/fundamentals.parquet`, `data/canada_fundamentals/`, `data/canada_earnings/`,
`data/hk_fundamentals/` — verified there by parquet read, not re-verified here.

```python
# RIGHT for reported fundamentals — the only US store with a real filing clock.
import pandas as pd
q = pd.read_parquet("data/edgar/statements_quarterly.parquet")
# VERIFIED columns include: fiscal_year, fiscal_quarter, period_end, filed, as_of, revenue, ...
knowable = q[q["filed"] <= asof]            # 'filed' is published_at for this store

# RIGHT for the annual cross-section:
from collectors.edgar import as_of_cross_section
x = as_of_cross_section("2019-03-15")       # collectors/edgar.py:836-851
if x.empty:
    raise RuntimeError("panel has no rows knowable at 2019-03-15")
```

`as_of_cross_section` uses `asof_date = period_end + 120 days` (`collectors/edgar.py:469-471`, default at
`collectors/edgar.py:516`) — a **declared conservative proxy** for `published_at`, because the EDGAR frames
API does not serve the SEC `filed` timestamp. That is the lawful way to handle a missing clock: approximate,
declare the approximation, and name it in the column. It is not the lawful way to *hide* one.

**No leak-free consensus store exists.** The nearest thing is the vendor's own retrospective surprise table
(`surprises_json`, built at `collectors/equity_earnings.py:184-194`), which carries a per-quarter
`consensus` value but no independently captured `known_at` — we would be trusting the vendor's post-hoc
labelling. A pre-print consensus panel on profile `REVISABLE_RELEASE` is **PROPOSED**; until it exists,
`eps_forecast` is display-tier only and may not enter a fit.

### 10.3 An index / basket membership change

```python
# WRONG — today's membership applied backward. This is survivorship + look-ahead in one line.
import json
doc = json.load(open("data/baskets_china_ths/membership.json"))   # membership_path(SUITE_THS), :97,:152-155
members = [m["ticker"] for m in doc["baskets"][basket_id]["members"]]
returns = panel.loc["2025":, members].mean(axis=1)
```

Why: `engine/basket_membership_pit.py:5-9` — the 12-month ignition/chase study used *"a single 2026-07-08
snapshot applied BACKWARD over the entire window, and the two PIT snapshots that do exist differ by 7.7% of
member-slots across 8 days."* 7.7% of slots in 8 days is the churn rate you are pretending is zero.

```python
# RIGHT
from engine.basket_membership_pit import members_asof
res = members_asof(basket_id, "2025-11-14", suite="baskets_china_ths")   # :623
if not res["pit"]:                       # :629-635 — the flag IS the contract
    raise RuntimeError(f"membership for 2025-11-14 is not point-in-time: {res['note']}")
members = res["members"]
```

Two subtleties the reader owns:

- `members_asof` resolves to the newest snapshot ≤ date and then applies the source's own
  `added`/`removed` dates (`engine/basket_membership_pit.py:609-620`), so a read *between* snapshots is
  correct rather than nearest-neighbour.
- `res["source_shape"]` is a **second** basis (`engine/basket_membership_pit.py:637-643`): the earliest
  side-car is the raw vendor concept dump, later ones are the seeded subset. Differencing across that
  boundary measures the seeding cap, not membership churn. `res["note"]` says so when it applies. Read it.

### 10.4 A corporate action

There is no event store (§9), so the honest example is the one you can actually run — detecting that you are
holding two different adjustment vintages of the same basis.

```python
# WRONG — treat 'adjusted close' as a fact and splice two stores to fill a gap.
a = pd.read_parquet("data/stocks/HON.parquet")["close"]        # close_tradj, vintage unknown
b = pd.read_parquet("data/yahoo/HON.parquet")["close"]         # close_tradj, DIFFERENT vintage
close = a.combine_first(b)                                     # 8 bp discontinuity at the seam
ret = close.pct_change()                                       # a fake 8 bp return on splice day
```

Why: verified in §9 — 192.573517 vs 192.419067 on 2025-09-25, both `close_tradj`, converging to 227.800003 by
2026-06-29. Neither store carries an `adjustment_asof`, so the splice is undetectable after the fact.

```python
# RIGHT, today (V1 of D4 — labels only):
#   1. pick ONE store per (security, basis) and record which one in the run receipt;
#   2. never combine_first across stores for a return series;
#   3. compute returns on _raw + an explicit factor series where the question is about
#      the printed tape (limit price, tick size, execution) — DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT;
#   4. if you must splice, ratio-align at the seam AND record the seam date + ratio in the receipt.
#
# RIGHT, after D4 V2 (PROPOSED — the store does not exist yet):
#   px = prices.read(msec_id, basis="tradj", adjustment_asof=run_started_at)
```

The declared absences to design against: `config/market_memory_technical_price_basis.v1.json:16,25,26`
(`"split_adjusted": false`, `"point_in_time_corporate_actions": false`, `"split_detection": false`).
CN is in the same position by design: `research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md:13,43` pins the
spine to *"unadjusted nominal daily quotes"*, `:51` states *"`pro_bar` is not used. A calculated band is never
substituted for `stk_limit`"*, and `:294` lists adjusted `pro_bar` under **Not tested**. That is the correct
posture for limit-price work (`DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`) and it means CN return math has no
adjusted series to be vintage-confused about — the gap there is that there is no lawful total-return basis
at all, not that its vintage is unrecorded.

### 10.5 A Prophet pick

```python
# WRONG — grade the plan from its formation anchor.
outcome = scan_bars(plan["asset"], start=plan["signal_date"], horizon=plan["horizon_days"])
```

Why: `engine/prophet_bridge.py:76-86` — historical `signal_date` values were base-formation aliases and
*"could precede origination by months — 94 of 103 live plans carried a gap, PINS by 152 days"*, so anchoring
the outcome scan there *"graded every plan on bars that PREDATED it: all 9 EXPIRED ledger rows and both
winners closed before their own plan existed, and 14 plans were born already past horizon."* Eleven rows were
quarantined for exactly this: `KKR-BULL-20260318` has `close_date` 2026-05-04 against `origination_date`
2026-07-14 — graded on bars 71 days before the plan existed
(`git show HEAD:data/prophet/ledger_quarantine.json`).

```python
# RIGHT
from engine.prophet_bridge import plan_clock_date
d = plan_clock_date(plan)          # engine/prophet_bridge.py:784-800
if d is None:
    raise RuntimeError(f"plan {plan['id']} carries no resolvable price/entry clock")
outcome = scan_bars(plan["asset"], start=d, horizon=plan["horizon_days"])
```

`plan_clock_date` resolves `price_basis_date > entry_date > asof > signal_date`
(`engine/prophet_bridge.py:789-800`), and the docstring names the defect it exists to fix: *"Reading it
[`signal_date`] FIRST is the defect this function exists to fix."* The distinction it encodes is the general
one — `engine/prophet_bridge.py:67-74`: *"`price_basis_date` and `entry_date` name the NYSE session whose
close supplied `entry`. `asof` and `recorded_at` name the run/publication date."* Price clock ≠ publication
clock, on every artifact, not just this one.

And per §8: the plan carries no `code_version`, so a pick made under `us_prophet_v1` is indistinguishable
from one made under `v2` without cross-referencing the git timeline by hand.

---

## 11. RULES FOR ANY FUTURE BACKTEST IN THIS REPO

A quant session can follow this section without reading the rest of the document.

1. **Declare your as-of function before you write a feature.** Every input must be reachable through a reader
   that takes `as_of` and filters `known_at <= as_of`. If you cannot name that reader for an input, you do not
   have a backtest yet.
2. **Macro: pass `pit_basis='release'`.** `build_features()` with no argument is the leaky frame
   (`engine/inputs.py:137,142-147`). There is no "close enough" version of this.
3. **Check the vintage store covers your series before you trust `release`.** 28 config-declared series have
   zero rows on disk (§0.5) and the accessor falls back silently to calendar-shifted revised values
   (`engine/pit.py:265-267`). `engine.pit.has_vintage(col)` (`engine/pit.py:214-220`) answers this; assert on
   it.
4. **Never swap a subset of legs and call it PIT.** `engine/inputs.py:148-151` names the partial-PIT hazard;
   `scripts/calibrate_spvector_pit.py:80-91` is the in-repo example of committing it.
5. **An empty result from a PIT reader is a STOP, not a zero.** `collectors/fred.py:246-252`,
   `scripts/calibrate_spvector_pit.py:38-39`, `collectors/edgar.py:848-849` all return empty rather than
   raising. Wrap them.
6. **Fundamentals: `data/edgar/fundamentals_panel.parquet` via `as_of_cross_section`, or
   `statements_quarterly.parquet` gated on `filed`.** Never `data/edgar/fundamentals.parquet` — its own
   collector docstring says a backtest on it *"would use TODAY's restated numbers at every past date
   (look-ahead) and only TODAY's listed tickers (survivorship)"* (`collectors/edgar.py:463-466`).
   Never `data/edgar/statements.parquet` for a restatement-sensitive question (`collectors/edgar_facts.py:154`
   discards prior vintages).
7. **Estimates and analyst consensus are display-tier. They may not enter a fit.** `eps_forecast` has two
   distinct `as_of` values across the whole universe (§10.2). Same for
   `data/china_analyst/forecast.parquet` and the Canada/HK siblings.
8. **Membership: `members_asof(...)`, and raise on `pit=False`.** Today's basket applied backward is a 7.7%
   /8-day error (`engine/basket_membership_pit.py:8-9`).
9. **Prices: one store per (security, basis), named in the receipt. No `combine_first` across stores.**
   Four US daily stores disagree on the same `(ticker, date)` on both basis and adjustment vintage
   (§9). Structure math wants `close_price` (`_sadj`); return math wants `close` (`_tradj`); exchange-rule
   and execution work wants raw.
10. **All timestamps tz-aware UTC. Session dates from the exchange calendar.** Never `date.today()`, never
    `datetime.utcnow().date()` for a session (`lib/nyse_calendar.py:240-242`). Nine `datetime.utcnow()` sites
    remain (`grep -rn "datetime.utcnow()" engine scripts collectors lib` → 9); do not add a tenth.
11. **Grade on the entry clock, not the formation clock.** `plan_clock_date()`
    (`engine/prophet_bridge.py:784`). Eleven ledger rows were quarantined for getting this wrong (§10.5).
12. **Stamp the run.** Every backtest result writes `code_version` (git sha), each input dataset id with its
    vintage or content hash, `pit_basis`, the as-of range, and row counts. Without it the result is an
    anecdote. Receipt idiom: `contracts/*_receipt.schema.json`.
13. **Report the leakage tax, not just the result.** Run the same backtest on `pit_basis='reference'` and on
    `'release'` and publish both. `research/PIT_LEAKAGE_TAX.md` is the template; `engine/pit.py:15-17`
    exists specifically to be the control leg. A strategy whose edge disappears under PIT did not have an
    edge.
14. **A self-check derived from the thing it checks cannot fail.** If your PIT verification compares a frame
    to itself when an input is missing, it prints CONFIRMED forever (§0.7). Mutate an input and prove your
    check goes red.
15. **`DERIVED` tables do not answer as-of questions.** Read their *inputs* as-of and recompute, or promote
    the table to `INTELLIGENCE` with a `served_at` log (§6). Reading a `DERIVED` table as-of is the
    current-rule recomputation the Calcbench ruling names.

---

## 12. Evidence caveats and open questions

**Evidence caveat (mandatory disclosure).** The materialized-data checkout
`/Users/chriswong/Documents/Cluade/Macro Dashboard` was reported by the census completeness critic to be in a
broken git state — detached HEAD, an unresolved merge conflict in `config/dag.yml`, ~4,560 dirty entries,
~1,119 commits behind. **Every claim in this document that reads that checkout reads parquet *content*
only.** No claim here rests on a file mtime or a `git log` from it. Specifically: §0.5's 26-vs-54 drift is
derived from the *set of series present in the parquet* compared against `config.yml` and
`collectors/fred.py`, never from a timestamp. §9's HON numbers are cell values. Anyone re-deriving a
*staleness* claim (as opposed to a *content* claim) must corroborate it against a clean checkout first.

Open questions this document does not resolve:

1. Is `engine/release_target_truth.py` wired into any scored consumer, or is it display-only like
   `engine/release_provenance.py:6-8`, `engine/release_integrity.py:3-7`, and
   `engine/release_revision_model.py:3-4` (all three of which declare display-only status in their own
   docstrings, with `release_provenance` naming an authority test that enforces it)? Not verified here.
2. Why has `fetch_vintages()` not advanced the store to the 54-series config — no `FRED_API_KEY` on the
   collect host (`collectors/fred.py:201-203` warns and returns empty), or is the keyed path simply not
   scheduled? Content cannot distinguish these; an operator check on the collect job's environment can.
3. Does any consumer dereference `surprises_json`'s per-quarter `consensus` as a PIT estimate, or is it
   purely display? This determines whether §10.2's leakage risk is theoretical or currently exploited.
4. The wall-clock hole in the earnings-blackout gate named at `scripts/backfill_prophet_outage.py:16-21` was
   fixed for the one-off replay path; `scripts/backfill_prophet_outage.py:23-24` states the defect *"itself
   is a SEPARATE fix lane — this script does not touch `build_stock_library`."* Whether it is still live in
   the standing nightly pipeline is unverified here and is the highest-value open item in this list.
5. Is there a `reporting_lag_days` equivalent anywhere in the China / Canada / HK fundamentals consumption
   path, or do those reach engine layers ungated? Not verified.

---

## 13. What this document does NOT authorize

- Building a new point-in-time framework. Nine already exist (§0.7); this standard converges them.
- Flipping `build_features()`'s default (§0.6).
- Unifying the three forensic-detector period bases — `DNR:HOLD-FF-DETECTOR-PERIOD-BASIS` holds them
  deliberately apart because unifying silently republishes a live user-facing surface. The registry must be
  able to express *"these two are knowingly different"* as a first-class state (`D10`).
- Full bitemporal modelling of `BARS` (`D11`).
- A second control plane, authority map, or strategic state in this repo — prohibited cross-repo as
  `duplicate_control_planes`.
