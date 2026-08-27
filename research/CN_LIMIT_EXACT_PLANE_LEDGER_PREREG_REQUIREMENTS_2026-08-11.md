# CN limit-alpha — exact-plane forward ledger + advancer: preregistration requirements (2026-08-11)

Status: **requirements charter only — creates no ledger, imports no rows, grades nothing**

Authority: `none_research_requirements_only`

Governing kill: `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`

Governing ruling: `research/CN_LIMIT_ALPHA_RECONCILIATION_LEDGER_2026-08-09.md` §6 (as amended
2026-08-10) and §8 items 2–4, 6.

Substrate contract: `research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md`.

---

## §0 What this document is, and what it is not

This is a **behavioral requirements charter** for a forward limit-alpha ledger and its
advancer that may be built **only after** the gates in §5 close and a separate
preregistration is written and registered.

Explicitly, this document:

- **creates no ledger** and defines no on-disk store as existing;
- **imports zero rows, zero grades, zero probabilities, and zero measured numbers** from
  either withdrawn forward seed (Claude's or Codex's), from the withdrawn adjusted-price
  event tape, or from any receipt derived from them;
- **grades nothing** and advances nothing;
- **is not a preregistration.** It states what a future preregistration must pin down. It
  does not pin thresholds, horizons, cushions, universe filters, or model parameters. Every
  such number is reserved for the fresh preregistration written against the authorized
  substrate.
- **confers no authority.** Nothing here ranks, sizes, gates, alerts, trades, or establishes
  numerical strategy evidence, and nothing here may be cited as evidence that an
  implementable edge exists.

Requirements below are written as constraints on a **fresh implementation**. Where a
constraint is inherited from preserved prior work, that work is cited as **design input
only** per §2.

---

## §1 Why this charter exists

`DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` is a STOP-SHIP by ruling. It withdraws the
adjusted-price (Yahoo-plane) CN limit-alpha tape, the artifacts mistakenly re-landed by
#5198, and their W2/W3 executable and result descendants. Its scope is total on the
numbers: nothing from either adjusted-price vintage, **either forward seed**, or any
derived receipt may be graded, ranked, gated, sized, alerted, traded, promoted, displayed
as a current probability, or used as numerical strategy evidence — and no withdrawn tape,
artifact, receipt, result, **reproducer, reader**, or rendered surface may be restored.

Reconciliation §6, as amended 2026-08-10, is equally explicit: **grade neither ledger**;
neither may be advanced, reconciled, copied into a new ledger, or written into the program
record. The same paragraph opens the only permitted door, and this charter walks through
exactly that door and no further:

> The preserved Codex engine may inform requirements such as stable identity, keep-first
> contradiction detection, and exact-session accounting, but it is not adopted executable
> authority. A future advancer must be implemented and pre-registered against the authorized
> exact plane, with no imported rows or grades from either withdrawn seed.

The defects that caused the kill are properties of the **input plane and the equality
rule**, not of the ledger machinery:

1. split-adjusted prices (Yahoo history requested with `auto_adjust=False` is still
   rebased), so historical nominal CNY prices and exchange limits cannot be reconstructed
   exactly;
2. ties-to-even rounding where the exchange rule is half-up; and
3. no exact vendor limit authority to compare against.

This matters for scoping: the **mechanical** invariants of the withdrawn implementation —
how identity is keyed, how partitions are installed, how a non-session is classified — were
never the thing that failed. They are recoverable as requirements. The **numbers** are not
recoverable at all.

---

## §2 Salvaged behavioral requirements (design input, not adopted code)

**Attribution.** The requirements in this section are abstracted from the preserved branch
`claude/cn-limit-alpha-forward-ledger` @ `93149e56609`, specifically its
`engine/cn_limit_alpha_ledger.py` and `scripts/advance_cn_limit_alpha_ledger.py`.

**That code is NOT adopted.** It is not cherry-picked, not copied, not vendored, and not
imported. It reads the back-adjusted `data/china_stocks_raw` store and defaults to
withdrawn Wave-1 seed and receipt paths; as an executable it is a withdrawn reproducer and
restoring it would itself violate the kill. What follows are **behavioral requirements a
fresh implementation must satisfy** — stated so that a clean-room implementation against
the authorized substrate can be checked against them. No constant, threshold, or default
from that branch is inherited.

### §2.1 Attested exchange calendar (`cn_exchange_calendar.v1` semantics)

No weekday heuristics anywhere in the advancer. Session arithmetic resolves against an
attested calendar artifact carrying, at minimum, the attested year, the ordered session
tuple, its source URLs, and a content hash.

Required behaviors:

- **Membership, not inference.** "Is this a session?" is a lookup against the attested
  tuple. Weekend and holiday dates are non-sessions because they are absent from the tuple,
  never because of day-of-week arithmetic.
- **Session-count offsets.** Forward window arithmetic advances by *positions in the session
  tuple*, not by calendar days.
- **Fail closed at the attestation boundary.** A date outside the attested year, or a date
  absent from the tuple, raises rather than extrapolating. An offset that would run past the
  end of the attested calendar raises rather than guessing the next year's sessions. A
  window that cannot yet be resolved stays OPEN; it is never silently truncated or
  extrapolated to a nearby date.
- **Provenance.** The calendar's hash and sources are recorded in the run receipt, so any
  grade can be re-derived against the exact calendar that produced it.

Under the exact plane the calendar must additionally reconcile with the substrate contract's
canonical market clock (frozen definition-versioned epoch `mainland-joint-complete-v1` at
`1992-01-01`, exact SSE/SZSE calendar-day and open-session equality, `pretrade_date`
adjacency, one immutable `market_session_position` counted from that epoch),
with BSE inheriting the documented consensus from launch. Where the attested artifact and
the spine clock disagree, the run fails; it does not pick a winner.

The epoch supersedes the previous fixed 1991-01-01 anchor; history before it is typed
`PRE_EPOCH_SOURCE_UNSUPPORTED` and carries no session position. This costs the frozen
evaluation nothing: the adopted split begins at train 2011, whose deepest lookback is the
21-session reset window reaching late 2010 — nineteen years after the epoch — so no frozen
construction requires an authority-grade outcome dated before it. Because re-anchoring
shifts every ordinal by a constant, window and horizon boundaries must be expressed as
session-position DIFFERENCES; no construction may attach economic or target meaning to an
absolute ordinal magnitude.

### §2.2 Monthly-partitioned Parquet with atomic installation

- Rows live in Parquet partitions under a monthly directory layout, with immutable daily
  parts inside each month — never one monolithic JSONL, and never a rewritten whole-history
  file.
- Probability rows and grade rows are **separate partition kinds** with separate schemas.
- **Exact schema equality on read.** A partition whose schema differs from the declared
  schema is an integrity failure, not a coercion opportunity.
- **Atomic install.** A partition is written to a temporary location and moved into place, so
  a crashed or killed run leaves either the previous state or the complete new partition —
  never a half-written part.
- **All-or-nothing per run.** Every planned partition for a run is validated before any of
  them is installed (see §2.4).

### §2.3 Stable prediction identity

- A prediction's identity is a fixed tuple of signal date, instrument, model version, limit
  definition, and entry rule. A grade's identity is that tuple plus grade kind and horizon.
- **Identity excludes the entry session.** This is the load-bearing choice: if a calendar
  correction moves the entry session, that is a *mutation of an existing prediction*, not a
  new prediction. Including the entry session in the key would let a calendar fix
  silently mint a second, contradictory row for the same forecast.
- The limit definition and entry rule are **inside** the key, so an exact-cent grade and any
  separately preregistered tolerant twin (§4) can never collide or overwrite each other.
- Identity is stable across re-runs, re-collections, and store repairs. It is never derived
  from row order, file position, or ingestion time.

### §2.4 Keep-first contradiction detection

- The ledger is **append-only**. An already-written row for a given identity is authoritative
  and is kept.
- If a re-run computes a row that **contradicts** a stored row for the same identity, that is
  an **integrity failure that aborts the run** — not an overwrite, not a silent skip, and not
  a "latest wins" update.
- The contradiction check runs **before any planned partition is installed**, so a run that
  would corrupt history fails having written nothing.
- Recomputing an identical row is a no-op, which is what makes re-runs idempotent (§4).
- Corrections therefore require an explicit, receipted mutation path with its own record —
  never an in-place rewrite that erases what was originally predicted.

### §2.5 Exact-session accounting

- Every ticker-session is classified **at its exact date**. The implementation must never hop
  to a later print to fill a missing one, and must never let a name's own row sequence
  substitute for the market clock.
- The **market clock** and the **per-name session classification** are separate tests, and
  conflating them is a known defect class. A date's existence as a market session is
  established cross-sectionally; whether a *given name* traded on it is a separate,
  per-name question (§2.7).
- The signal clock must come from **broad cross-sectional support**, so a partially collected
  tail cannot become the newest session: require a high-support reference instrument to carry
  the date, an absolute floor on distinct names present, and a floor on support relative to
  recent best cross-sectional support. **The specific thresholds are not inherited** — the
  fresh preregistration sets them against the authorized universe.
- Under the exact plane, `positive_volume` is exactly `volume_lots > 0`, zero-volume source
  rows remain in the substrate, and any traded-session claim must filter that flag.

### §2.6 No-fill semantics

Fillability is a **first-class recorded field**, never folded into the outcome.

- The record distinguishes at minimum: a normally fillable session; a session where entry
  would have required queuing at the limit and therefore **cannot be assumed filled**; a
  session missing or halted for that name and therefore **no-fill** (§2.7); and a
  not-yet-resolved pending state for open windows.
- **A no-fill is not a win and not a loss.** It is a separate disposition. Any summary that
  reports hit rates must report the no-fill population beside them, and must never compute a
  hit rate that silently drops no-fills from the denominator — a resolution-conditioned
  denominator deletes exactly the cases the entry rule could not capture.
- The daily-bar fillability test is a **proxy**, and must be labelled as one. It is not
  evidence about queue position. An exact fillability claim requires the auction/minute
  plane, not the daily plane.

### §2.7 停牌 / suspension placeholders are non-sessions for that name

- A suspension (停牌) bar is a **zero-volume stale-price placeholder row**, not a traded
  session. For the affected name it classifies as missing/halted and therefore **no-fill**.
- **A placeholder must never grade as a real session for that name**, and specifically must
  never resolve as a miss. Grading a stale placeholder as a miss manufactures losers out of
  names that could not trade.
- Symmetrically, a placeholder's presence is still evidence that *the date exists* as a
  market session — so the cross-sectional market clock (§2.5) deliberately does not filter on
  volume, while eligibility and grading do. These two rules only look contradictory; keeping
  them separate is the requirement.
- A window that spans suspension sessions is extended by the calendar's session positions, so
  a halted name is not penalized by a window that ran while it could not trade. How the
  window treats a suspension straddle must be pinned explicitly in the preregistration.

### §2.8 Explicitly NOT salvaged

- **No numbers.** No probability, grade, hit rate, threshold, cushion, horizon, cost
  assumption, universe count, or tuning constant carries over from the withdrawn work.
- **The tolerant-cushion primary definition does not carry.** The withdrawn construction made
  a tolerant cushion the *primary* limit definition because its adjusted input could not
  support cent equality. On the exact plane the primary grade is exact-cent equality (§4);
  no cushion value is inherited, and any tolerant twin must be freshly preregistered.
- **No frozen model or receipt.** The withdrawn frozen scoring receipt, its coefficients, and
  its hash pins are archaeology. A fresh model requires a fresh preregistration.
- **No seeds, no readers, no rendered surface.** No withdrawn seed is copied forward; no
  reader or page may present withdrawn probabilities as current.
- **The `context_display_only` authority label does carry** as the default authority of any
  first-generation ledger built to this charter. Promotion above display tier requires the
  gauntlet, not this document.

---

## §3 Substrate contract — the reopen precondition

The ledger may be built only on the exact plane defined by
`research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md`. Required, per that contract:

1. **Unadjusted TuShare `daily` prices from the technically gated collector.** TuShare
   licensing/compliance is `CHAIRMAN_VERIFIED_PRIVATE / SATISFIED`
   (`DEC:CNLI-TUSHARE-COMPLIANCE-IS-CHAIRMAN-VERIFIED-PRIVATE`); the controlling agreement
   and its evidence are confidential and outside coding/agent scope under NDA/privacy
   constraints, and no coding session or runtime gate may request or verify them. The former
   authorization-receipt / trust-allowlist gate this section previously required is NULL and
   removed from the runtime. Collection remains gated on `BULK_HISTORICAL_BACKFILL_READY`, a
   TECHNICAL readiness gate (live canary parity, throughput, range/completeness correctness),
   plus token hygiene, the bounded request budget, and exact request/schema binding. This
   charter does not weaken, reinterpret, or provide an alternative to those technical gates.
2. **Same-key vendor `stk_limit` upper/lower limits as the event authority.** Limits are read
   from the vendor, joined one-to-one on the same key as `daily`. Limits are never
   reconstructed from a ratio: effective-dated IPO/ST/board/no-limit state must not be guessed,
   which is why the contract's `a_share_limit_price_bounds()` is validator-only.
3. **Integer-cent equality and exchange half-up validation.** All non-null prices are exact
   CNY-cent ticks. Bound checks use Decimal `ROUND_HALF_UP` with a one-tick move and one-tick
   floor, rejecting off-tick inputs. Touch/seal flags are set **only by integer-cent equality**
   on positive-volume bounded rows. Python/NumPy ties-to-even rounding is forbidden anywhere in
   the limit path — it is one of the three named causes of the kill.
4. **Event-join equality.** The contract's `event_daily` equalities must hold: one-to-one
   daily / daily-basic / limit keys; daily-vs-`stk_limit` previous-close equality;
   daily-vs-daily-basic close equality; OHLC bounded inside the exact source interval; and
   `daily_basic.limit_status` domain, direction, and one-price semantics.
5. **PIT full-universe and effective-date completeness receipts.** The contract's
   `completeness_manifest.json` must close on its own terms — the operational-backfill code
   gate separately promoted on canary/throughput/correctness evidence; reference
   generation, exact calendar, and every required source unit request-bound and complete;
   zero unknown counts, and every `namechange` source row deterministically reconciled with
   zero unresolved conflicts — NOT 100% external corroboration, since a valid namechange row
   is its own source evidence and `NAMECHANGE_ONLY` is terminal source completeness
   (`DEC:CNLI-NAMECHANGE-IS-ITS-OWN-SOURCE-AUTHORITY`); post-2016 `bak_basic` witnesses with lifecycle
   and PIT sets reconciling under the source-union law (every lifecycle-eligible security
   witnessed in PIT and no PIT row contradicting its own master lifecycle window; a PIT row
   the current `stock_basic` snapshot omits is a legal union member counted as telemetry —
   `DEC:CNLI-HISTORICAL-PIT-IS-SOURCE-UNION`); duplicate-key, dense-key, lifecycle, exact-session,
   suspension, and daily security coverage checks closing; and the canonical exact-price event
   join closing. Manifest artifacts are private and must not be committed; only the
   contract's sanitized hash/date/scope fields propagate.
6. **The eligibility overlay** (reconciliation §8 item 3, built from the handoff §5.2 frozen
   design). Its named factual gaps are the overlay's quarantine classes, not reasons to wait.
   The ledger's universe is the overlay's eligible set; the advancer does not define
   eligibility itself.

**Survivorship and universe honesty.** The universe must be point-in-time. Delisted,
suspended-to-delisting, and never-listed-yet names must be present in the PIT universe for
every date they were actually listed. Any cohort statistic computed later must name who is
missing before its means are trusted.

This is enforced at the collector, not merely asserted here. The current `stock_basic`
snapshot is a lifecycle/reference witness, not exhaustive historical membership authority,
so historical PIT construction is **source-union, never current-snapshot intersection**
(`DEC:CNLI-HISTORICAL-PIT-IS-SOURCE-UNION`). Intersecting a current snapshot against
historical sessions is precisely the survivorship filter this section forbids, and its error
points one way: a security the vendor later stops publishing would become unclassifiable on
every past date it actually traded. A security with a complete same-session positive-volume
observation and the required exact legal-band evidence is in the historical exact universe
whether or not the current snapshot still carries it. The current-snapshot omission rate is
the "name who is missing" telemetry this section demands — it is reported, never thresholded.

The same law governs the name-history plane, where the PIT witness cannot reach: it begins
2016-01-01, so requiring corroboration for an earlier `namechange` row would restore the
current snapshot as sole authority for exactly the securities most likely to have vanished
from it. A valid `namechange` row is therefore **its own sufficient source evidence**
(`DEC:CNLI-NAMECHANGE-IS-ITS-OWN-SOURCE-AUTHORITY`). It lands as `NAMECHANGE_ONLY` with zero
PIT membership, trading, exact-event, canonical-identity, rank or score authority — existence
in the source plane and authority over the universe are granted separately. The rule is
applied row by row across the frozen epoch: pre-2016 is not special-cased and the
witness-missing percentage is not an admission threshold, because a threshold would make a
row's disposition depend on its neighbours rather than on its own evidence, which is the
survivorship filter re-entering as a tunable.

---

## §4 Grading contract requirements

- **Exact-cent primary grade.** The primary board event is integer-cent equality of the close
  against the vendor upper limit for that name and session: `close_cents == up_limit_cents`.
  No cushion, no tolerance, no float comparison. Prices are compared as integer cents, not as
  floats.
- **A tolerant twin is optional, freshly preregistered, and recorded BESIDE.** If a tolerant
  variant is wanted, it must be preregistered on its own terms — its own cushion, its own
  stated rationale — and carried as a **separate row under its own `limit_definition`** in the
  identity key (§2.3). It is never averaged, blended, substituted, or promoted into the exact
  grade, and the exact grade is never softened to make it agree. No tolerant definition is
  inherited from the withdrawn work.
- **Realized return and near-limit flag beside the binary, never blended.** Each graded row
  carries, as separate fields: the binary grade, the realized return over the window so far,
  and a near-limit flag. **No combined, weighted, or composite score may exist anywhere** in
  the ledger, the advancer, its receipts, or any surface reading them. A near-limit close is a
  near-limit close; it is not a partial hit.
- **Open is a first-class state.** Rows whose window has not elapsed are OPEN, not misses.
  Receipts print open / hit / miss / expired / no-fill counts separately, per board, and never
  collapse OPEN into a denominator to make a rate look resolved.
- **Nulls are printed, not hidden.** A window that cannot be resolved — insufficient calendar,
  missing substrate, quarantined eligibility — is reported as such with its reason code.
- **Append-only.** Grades are appended; no row is rewritten in place. Contradictions abort the
  run (§2.4).
- **Nightly is the sole advancer.** Per house law, the nightly lane is the only writer of
  forward ledgers; intraday lanes discard `data/` writes. The advancer must refuse to write
  outside that lane.
- **Idempotent re-runs.** Advancing the same session twice must be a no-op the second time:
  identical rows recompute identically and install nothing new. Idempotency is a required
  test, not an incidental property.
- **Fail open, loudly.** An advancer failure must not kill the nightly render. It emits a
  GitHub annotation as a bare `print("::warning title=<slug>::<msg>", flush=True)` starting
  the line — never through a logger, which prefixes the line and makes GitHub drop it
  silently — and exits without blocking the lane.
- **Receipts state the plane.** Every receipt names the substrate (unadjusted TuShare `daily` ×
  vendor `stk_limit`), the calendar artifact hash, the completeness-manifest identity, the
  eligibility overlay version, and the authority tier. A receipt that cannot name its plane is
  not a receipt.
- **Authority.** First-generation output is `context_display_only`. Promotion to rank, size, or
  gate requires the gauntlet with pre-registered gates and printed nulls — never this charter,
  and never accumulated forward rows alone.

---

## §5 Ordered gates before any ledger may exist

From reconciliation §8. Each gate must close **before** the next is attempted; the ledger is
item 6 and may not be started early, in parallel, or "provisionally".

| # | Gate | Closes when |
|---|---|---|
| 1 | Range shards finished (§8 item 1) | Handoff §5.1 recipe complete, its four named blockers cleared |
| 2 | **Full-A spine backfill** (§8 item 2) | `BULK_HISTORICAL_BACKFILL_READY` flipped under operator-attested authority; `daily` / `daily_basic` / `stk_limit` whole-market history collected; completeness receipts closed per §3 |
| 3 | **Eligibility overlay** (§8 item 3) | Built from the handoff §5.2 frozen design, with its factual gaps expressed as quarantine classes |
| 4 | **F3 re-measurement on the exact plane** (§8 item 4) | W1–W3 core (ladder, gap, dial, fillability, weakness, windows) re-run full-universe, integer-cent, eligibility-gated. **This is the program gate to anything beyond display tier.** |
| 5 | **Fresh preregistration** (§6) | Written and registered against the authorized plane: model, universe, horizons, thresholds, windows, grade definitions, and the evaluation split — pinned before any forward row exists |
| 6 | **Ledger + advancer implemented** (§8 item 6) | Clean-room implementation satisfying §2 and §4, on the §3 substrate, with **no imported rows or grades from either withdrawn seed** |

Evaluation-split note: per reconciliation §7, re-measurements on the exact plane use the
adopted split going forward (train 2011–2019, calibration 2020–2023, locked test
2024-01→2026-06-12, audit window, prospective thereafter, with 10-session purges), and the
vendor-rich audit window 2026-06-15→2026-08-07 joins the evaluation battery for every future
construction. The preregistration must state its split explicitly rather than inherit it by
assumption.

**Gate 2 is currently open**, and no unadjusted-daily or vendor `stk_limit` store exists in
the tree. Until it closes, this charter is the only artifact this lane produces.

---

## §6 Open questions the preregistration must answer

These are deliberately left undecided here. Deciding them silently in implementation is the
failure mode this section exists to prevent.

1. **Suspension straddle.** Exactly how a window that spans 停牌 sessions is extended, and
   whether a name suspended at entry is dropped or deferred.
2. **Board partition.** Which board/era split the grade receipts report on, and how the
   differing limit widths and their effective dates are sourced from the vendor rather than
   assumed.
3. **Entry rule.** What entry is assumed, and how the daily-plane fillability proxy is to be
   superseded once the auction/minute plane is available.
4. **Horizons and windows.** Which forward horizons are graded, and the exact open/expired
   boundary in session positions.
5. **Tolerant twin.** Whether one is wanted at all, and if so its cushion and its stated
   rationale — registered before any row is written.
6. **Near-limit flag.** Its exact definition in integer cents, and the explicit statement that
   it is diagnostic only.
7. **Cost model.** Whether net-of-cost variants are carried, and if so as separate fields
   under the no-blend rule.
8. **Universe.** The eligibility overlay version pinned, and the treatment of IPO no-limit
   sessions, ST transitions, and effective-dated board moves.

---

## §7 Compliance statement

This document imports no rows, no grades, and no measured numbers from any withdrawn
artifact. It restores no tape, seed, receipt, reproducer, reader, or rendered surface. It
cites the preserved branch `claude/cn-limit-alpha-forward-ledger` @ `93149e56609` solely as
**design input for behavioral requirements**, which reconciliation §6 permits and which this
document does not convert into executable authority. It creates no ledger and confers no
authority. It is compliant with `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`.
