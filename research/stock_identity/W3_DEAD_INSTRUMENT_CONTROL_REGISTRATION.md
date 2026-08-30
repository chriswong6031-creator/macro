# W3S — Dead Instrument Control Set: candidate-population, sampling and exclusion law

- operation_key: `SI-W3S-DEAD-CONTROL-V1`
- parent_operation: `SI-FABLE-COO-PROGRAM-20260828`
- workstream: `WS:STOCK-IDENTITY`
- commission packet: commit `0e65358a3e15707f1f769720bce195a99078c6bf`, blob `421638c488dfa7c44a36608e1e1fbf3b07c96714`,
  path `agentos/handoffs/STOCK-IDENTITY-2026-08-29-W3S-DEAD-CONTROL-RESTART.md`
- registration base: `origin/main` @ `5037814d4367` (packet `base_sha` was `07e63c5877c1`; main has advanced, see §7)
- status at write time: **PREREGISTRATION — committed before any tape-dependent inclusion decision**

## 0. Why this document exists and what it forbids

The Dead Instrument Control Set is a separately registered hard predecessor of W5/Q1 survivorship
(W2 registration). Its only scientific value is that its membership was fixed **before** anyone
looked at what the tapes do. This file is the fixing act.

Once this file is committed, the builder may only *execute* the screens below. It may not add a
name, drop a name, reorder the cohort, retune a threshold, or introduce a new screen. Any change
to this law after tapes have been read voids the cohort and requires a fresh registration with a
new operation key and an explicit Sol act.

**The specific failure this forbids:** selecting five terminated names, discovering that two of
them have awkward tapes, and quietly replacing them with two better-behaved ones. That produces a
control set whose survivorship properties are an artifact of the selector, which is exactly the
bias W5/Q1 exists to measure.

## 1. Authority and precedence

1. current Chairman end-to-end recovery intent;
2. current protected Skillpack at pickup;
3. original Stock Identity masterplan survivorship law
   (`research/stock_identity/STOCK_IDENTITY_COMPLETE_MASTERPLAN_2026-08-28.md`);
4. W1 registration's measured dead-name impossibility on the original allowed planes
   (`research/stock_identity/W1_IDENTITY_ATLAS_V0_REGISTRATION.md`);
5. W2 registration: the Dead Instrument Control Set is a separately registered hard W5/Q1
   predecessor (`research/stock_identity/W2_EXPERT_REPLAY_REGISTRATION.md`);
6. accepted W3 freeze (`research/stock_identity/W3_FINAL_ARCHITECTURE_FREEZE_2026-08-27.md`);
7. prior Sol ruling in the parent thread: a minimum preregistered terminated-ledger extension plus
   reuse of the existing dead-name collection owner to persist OHLCV it already receives is inside
   W3S authority. **No second market-data platform, no hidden cache, no new identity authority, no
   unproven AVB-tail / close-only substitute.**

## 2. Machinery contract this cohort must satisfy (read from code, not assumed)

Pinned at `origin/main` @ `5037814d4367`:

| Constraint | Value | Source |
|---|---|---|
| Registered price planes | `stocks_tr_v1` (`data/stocks`), `baskets_ohlcv_v1` (`data/baskets/ohlcv`), `stock_identity_ohlcv_v1` (`data/stock_identity/ohlcv`) | `engine/stock_identity/plane.py:47-59` |
| Plane precedence (first carrying plane wins; others shadowed) | `stocks_tr_v1` → `baskets_ohlcv_v1` → `stock_identity_ohlcv_v1` | `engine/stock_identity/plane.py:52`, `:95-105` |
| Required columns on every plane | `close`, `high`, `low`, `volume` | `engine/stock_identity/plane.py:63` |
| Planes carrying `open` | `baskets_ohlcv_v1`, `stock_identity_ohlcv_v1` only | `engine/stock_identity/plane.py:61` |
| Index type | `DatetimeIndex`, else `ValueError` | `engine/stock_identity/plane.py:140` |
| Non-positive closes | dropped at load | `engine/stock_identity/plane.py:155` |
| Minimum sessions for a non-null fingerprint | **252** | `engine/stock_identity/fingerprint.py:90` (`MIN_SESSIONS`), enforced `compute_raw` |
| Episode inputs | `high`, `low`, `close`; `sma200` needs 200, `HIGH_WIN` 126, `BREAKDOWN_LOW_WIN` 60 | `engine/stock_identity/episodes.py:67-72,127-131,357` |
| SI program-plane adjustment mode | `auto_adjust=True` (dividend/split adjusted total-return) | `data/stock_identity/ohlcv/manifest.json` |

**Binding history floor: 252 sessions.** A tape shorter than 252 sessions produces an all-null
fingerprint and is therefore not a control, it is a hole.

## 3. Candidate population (frame `P`)

`P` = every instrument that satisfies **all** of:

- **P1** it is a U.S.-exchange-listed instrument (NYSE, NYSE American, NASDAQ, or Cboe) as of its
  terminal listing event;
- **P2** a **terminal listing event** is asserted for it by an existing repo-canonical terminated
  instrument record — not by a vendor status flag;
- **P3** it is already carried by an existing repo price plane (§2) or by the existing dead-name
  collection owner. W3S introduces no new universe and no new identity authority.

### 3.1 Enumeration procedure (deterministic, no discretion)

The builder constructs `P` as the union of these enumerated sources, each read at the pinned
commit, each recorded with its path and SHA-256 content hash in the run receipt:

- **S-A** — `config/delisted_symbols.yml`, every row under `symbols:` (the curated exit ledger);
- **S-B** — `data/quality/reused_tickers_audit.json`, the adjudicated `delisted_printing` exit rows;
- **S-C** — the existing dead-name collection owner's terminated inventory:
  `data/edgar/dead_name_cik.json` (dead universe, derived by `collectors.edgar_deadnames` from
  `data/breadth/sp1500_pit_membership.parquet`) joined to `data/edgar/dead_name_delisting.json`
  (EDGAR-derived terminal-event evidence).

`P = S-A ∪ S-B ∪ S-C`. No name may enter `P` by any other route, including operator suggestion,
worker intuition, or "it has a long tape". Every member of `P` is carried through to the exclusion
ledger with a terminal disposition — accepted, or excluded with exactly one code.

**Owner reuse, not a new plane.** The permitted bounded source act is confined to
`collectors/edgar_deadname_prices.py`, which today calls Polygon aggregates with `adjusted=true`
and receives full `o/h/l/c/v` bars but persists **close only**
(`collectors/edgar_deadname_prices.py:132-142`, schema `ticker,date,close,source` at `:235-236`).
W3S may persist the OHLCV fields that call already returns. It may not add a provider, widen the
universe, create a second price plane, or invent an alternate corporate-action truth.

### 3.2 Deterministic ordering

`P` is ordered by `(termination_date ASC, ticker ASC)` with `termination_date` taken from the
terminal-event record. Ordering is fixed before screening and is never re-derived from results.

## 4. Screens (applied in fixed order; first failure assigns the code)

| # | Screen | Passes only if | Failure code |
|---|---|---|---|
| S1 | **Terminated, not stale** | Two-source primary evidence per the #4622 protocol: (a) EDGAR filing-history evidence of the terminal event — Form 25 / 25-NSE accession, **or** a completed-transaction 8-K carrying Item 5.01 / 1.02 / 2.01 / 3.01, **or** a recorded bankruptcy accession — **and** (b) absence from the current NASDAQ symbol directory. A vendor "possibly delisted" flag is a hint, never evidence. Index-exit, halt, or a stale feed is not termination. | `E1_NOT_TERMINATED` |
| S2 | **Not a key migration** | No successor symbol carries the same series (`successor_ticker` null). A rename/uplisting is a key migration and the tape continues elsewhere. | `E2_KEY_MIGRATION` |
| S3 | **U.S. listed** | Listed on NYSE / NYSE American / NASDAQ / Cboe at termination. | `E3_NOT_US_LISTED` |
| S4 | **Identity resolved** | Stable issuer identity (CIK) present, and the symbol is not reassigned to a different issuer inside the tape window (ticker-reuse hygiene). | `E9_IDENTITY_UNRESOLVED` |
| S5 | **On a registered plane with required fields** | Present on ≥1 plane of §2 carrying all of `close, high, low, volume`, `DatetimeIndex`. | `E6_NO_LAWFUL_ADJUSTED_OHLCV` |
| S6 | **Adjusted** | The carrying plane's declared adjustment mode is split **and** dividend adjusted (total-return). Raw/unadjusted, or close-only, fails. | `E6_NO_LAWFUL_ADJUSTED_OHLCV` |
| S7 | **History horizon** | ≥ **252** sessions at or before the terminal date. | `E5_INSUFFICIENT_HISTORY` |
| S8 | **Terminal tape integrity** | The tape ends at the terminal date. Post-termination bars are permitted **only** as the documented zero-volume flat-forward padding tell and must be truncated to `last_session`. Any successor-series splice or basis rebase that cannot be provably restored to the true pre-termination basis fails. | `E8_TAPE_CONTAMINATED` |
| S9 | **Rights** | The source entitlement permits persisting and using this tape in-repo for this purpose. | `E7_RIGHTS_UNRESOLVED` |
| S10 | **Real, provably-adjusted source leg** | Every retained bar comes from a source leg whose split+dividend adjustment the repo asserts in code. `imputed_*` / synthetic rows are never a control. A leg whose adjustment semantics are not asserted anywhere (Stooq) may not supply an accepted tape. | `ADJUSTMENT_UNPROVEN` |

### 4.1 Blinding rule (the core of the preregistration)

No screen S1–S9 may read, and no accepted/excluded decision may depend on:

returns, cumulative or otherwise · drawdown depth or duration · volatility · Sharpe or any
performance statistic · fingerprint metric values · episode catalogs or episode counts · expert
fires · rank, size or gate outputs · localization · "how interesting the chart looks".

S7 reads **row counts and dates only**. S8 reads the tape's **terminal boundary and basis
continuity only** — it is a data-integrity test with a mechanical pass/fail tell (zero-volume
flat-forward; successor splice), never a preference between names, and it may not be relaxed or
tightened per name.

### 4.2 No hand-picking

**Every** member of `P` that passes S1–S9 is accepted. There is no cap, no top-five truncation, no
discretionary drop, and no substitution. If more than five names qualify, all of them are the
control set. The number five is a **floor for success**, never a target to select down to.

## 5. Required receipt per accepted instrument

Each accepted control carries, in the cohort manifest:

- stable instrument identity (symbol, issuer name, CIK) and ticker-history/reuse hygiene note;
- terminal reason and terminal date, each with its primary source (accession or directory receipt);
- price source/owner and rights note;
- `price_plane_id`, adjustment mode, and corporate-action semantics;
- first observation, last observation, row count, and coverage counts;
- known-at / correction behavior;
- immutable content hash of the persisted tape;
- explicit proof the tape is **terminated** rather than stale or index-exited;
- compatibility evidence against `engine.stock_identity.fingerprint` and
  `engine.stock_identity.episodes`.

**Missing is not zero.** A candidate without lawful full adjusted OHLCV is an *exclusion*, never a
partial control.

## 6. Terminal states

- `RESULT` — ≥5 accepted instruments, all receipts complete, compatibility smoke real and passing;
- `BLOCKED_NO_LAWFUL_DATA` — <5 accepted after the screens above. Providers are **not** widened and
  adjustment/history/identity requirements are **not** relaxed without an explicit Sol act;
- `IDENTITY_UNRESOLVED` / `ADJUSTMENT_UNPROVEN` / `RIGHTS_UNRESOLVED` / `SOURCE_OWNER_CONFLICT` /
  `WATCH_UNAVAILABLE` — as defined in the commission packet.

## 7. Deviations from the packet's stated starting truth

The packet records `config/delisted_symbols.yml` as holding **two rows and no compatible price
files**. That was true when W1 measured it. At this registration's base (`5037814d4367`) it holds
**three** resolved rows (AVB, CTRA, TPH) with a materially richer schema (`delisted_on`, `reason`,
`acquirer`, `consideration`, `receipts`), and at least one of them has a price file on a registered
plane. Open PR #6668 would add further adjudicated exit rows.

This is recorded as a deviation rather than silently absorbed: the ledger being less sparse than the
packet assumed changes the *feasibility* of W3S, and it must not be mistaken for the commission
having already been satisfied. The screens above are unchanged by it.

## 8. Determinism and audit

- A rerun of the builder at the same input commit must reproduce the accepted cohort and the
  exclusion ledger exactly, including ordering.
- Every source read is recorded with path and content hash in the run receipt.
- Hostile fixtures that must FAIL: a reused-ticker tape; a live or merely index-exited name
  relabeled dead; a raw/unadjusted plane; a close-only tape; a successor-spliced tape.


## 9. Amendment A1 — S10 scope correction (recorded BEFORE any tape was read)

**When:** immediately after §2/§3 archaeology, before the builder screened a single tape.
No price series had been loaded, no row counts compared, no candidate accepted or rejected.

**What changed:** S10 originally read "every retained bar comes from the Polygon `adjusted=true`
aggregates leg", and named yfinance as barred.

**Why it was wrong:** S10 was drafted while the presumed source was the dead-name price store
(`collectors/edgar_deadname_prices.py`), whose Polygon leg is the only adjusted leg *in that
module*. That scoping silently excluded an existing, registered, code-asserted adjusted owner:
`data/baskets/ohlcv` (`baskets_ohlcv_v1`) is built by `scripts/fetch_basket_ohlcv.py:563` with
`yf.download(..., auto_adjust=True)` and carries full `[open,high,low,close,volume]`
(`scripts/fetch_basket_ohlcv.py:1-14`, `engine/stock_identity/plane.py:47-61`). Barring it would
have excluded lawful data on a provider-name technicality rather than on adjustment provenance,
which is the property S10 exists to protect.

**What did NOT change:** the requirement itself. A bar must still come from a leg whose
split+dividend adjustment is asserted in repo code; synthetic/imputed rows are still barred; the
unasserted Stooq leg is still barred. S1-S9, the blinding rule, the ordering, the 252-session
floor, and the no-hand-picking rule are untouched.

**Why this is not law-tuning:** the amendment is provider-scope, not outcome-scope. It was made
with zero knowledge of which names would pass, because no tape had been read. It widens the set of
*owners* whose adjustment is provable; it does not widen the *universe*, relax adjustment, relax
history, or relax identity — all of which remain barred without a Sol act.

**Standing constraint this does not touch:** yfinance is the documented source of the AVB
successor-splice contamination. Being an adjusted leg does not make a yfinance tape clean; every
such tape must still pass S8 terminal-tape integrity on its own evidence.

## 10. Execution result — `BLOCKED_NO_LAWFUL_DATA`

Builder: `scripts/stock_identity_build_dead_control.py` (exit **3**), logic in
`engine/stock_identity/dead_control.py`, receipt
`data/stock_identity/control/dead_control_cohort.json`. Deterministic: two consecutive
builds hash identically.

| | |
|---|---|
| Population `P` | **223** |
| Accepted | **0** |
| `E1_NOT_TERMINATED` | 100 |
| `E3_NOT_US_LISTED` | 119 |
| `E6_NO_LAWFUL_ADJUSTED_OHLCV` | 2 |
| `E8_TAPE_CONTAMINATED` | 2 |

### 10.1 The blocker is the terminated-instrument LEDGER, not the OHLCV

The two halves a control needs — proven termination, and a lawful full adjusted tape —
exist in this repo but **not on the same names**:

- **Names with committed primary termination evidence have no lawful tape.**
  `CTRA`/`TPH` carry resolved ledger rows but sit on **no** registered price plane at all
  (`E6`). `AVB` carries a resolved row *and* a plane tape, but that tape prints **6 real
  bars after its own `last_session=2026-08-14`** — the documented successor splice. Because
  `plane.load_symbol` does not truncate at `last_session`, those bars would reach the
  behavioral layer as if they were AvalonBay (`E8`).
- **Names with a lawful full adjusted tape have no committed termination evidence.**
  `FBRX`, `TWO`, `LEG`, `EQR`, `ISSC`, `STRS` all sit on `baskets_ohlcv_v1` with full
  `open/high/low/close/volume`, long history, and have vanished from the exchange symbol
  directory — but at this base **no committed store records a terminal event for them**,
  so they fail `S1` on evidence, not on data.
- The 119 `E3` exclusions are the structural trap this cohort exists to avoid:
  `dead_universe()` closes on an **index exit**, not a death, and absence from an exchange
  directory is an OTC ADR's normal **live** state.

### 10.2 Quantified counterfactuals (probes — NOT cohort members, NOT evidence)

Run against the same committed ladder, changing only the ledger input:

- **With open PR #6668's exit ledger merged: 2 accepted** — `FBRX`
  (2,355 sessions, 2017-04-13→2026-08-26) and `TWO` (3,179 sessions, 2014-01-02→2026-08-24).
  `AVB` still fails `E8`; `CTRA`/`TPH` still fail `E6`. **2 of 5.**
- **Feasibility probe** (hypothetical rows for plane-resident names, explicitly *not*
  evidence and never accepted): **6** names clear the tape screens `S5`–`S10`
  (`FBRX`, `TWO`, `EQR`, `LEG`, `ISSC`, `RMAX`). `STRS` and `BBBY` still fail `S8`
  because their series is still being fed.

So the tape side is **sufficient** and the evidence side is **short**. The shortfall is
three additional *adjudications*, not three additional data fetches — and `ISSC` is a
known key migration that real evidence would reject at `S2`, so the true adjudication
target is narrower than the probe's six.

### 10.3 Compatibility smoke — the machinery is proven, not assumed

Real compute through the current inputs, using the sealed `si_constants_v1.json`:

| symbol | plane | sessions | fingerprint metrics | non-null | episodes |
|---|---|---|---|---|---|
| FBRX | `baskets_ohlcv_v1` | 2,355 | 64 | 52 | 50 |
| TWO | `baskets_ohlcv_v1` | 3,179 | 64 | 52 | 46 |

`engine.stock_identity.fingerprint.compute_raw` and `episodes.build_catalog` both run
clean on a terminated tape. Nothing about the W3S pipeline is unproven — the moment
termination evidence lands for five qualifying names, the cohort builds.

### 10.4 What was NOT done, deliberately

No provider was added, no second price plane created, no criteria relaxed, and the cohort
was **not** padded to five. The bounded source act Sol authorized — persisting the
`o/h/l/v` that `collectors/edgar_deadname_prices.py` already receives from its
`adjusted=true` Polygon call but discards (`:132-142`) — was **not executed**, because no
Polygon credential is resolvable in this environment (`POLYGON_API_KEY` absent from env and
from `lib.config`), so it could not have been verified end-to-end. It remains available and
correctly scoped for a session that holds the key; note that it would extend the
**close-only** dead-name store, which is a different plane from the one that actually
supplied the qualifying tapes here.
