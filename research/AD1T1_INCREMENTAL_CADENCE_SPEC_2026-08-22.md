# AD-1T1 — Full-Universe Incremental ThetaData T1 Cadence: Frozen Build Spec

**Wave:** AD-1T1 (`WS:ADVANCED-DATA-OPTIONS`)
**Authority:** `DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA`; Sol handoff `ADVANCED_DATA_OPTIONS_AD1T1_THETADATA_INCREMENTAL_T1_CADENCE_HANDOFF_2026-08-22.md`; prior wave spec `research/AD1T0_THETADATA_CUTOVER_SPEC_2026-08-22.md`.
**Ruled by:** Fable (COO), 2026-08-22. Builders execute this spec; they do not redesign it.
**Merge authority:** NONE — the AD-1T1 PR returns to Sol unmerged (DRAFT + HOLD-FOR-SOL).

Status of this document: FROZEN except where marked `PENDING-BENCHMARK` /
`PENDING-CENSUS`; those slots are filled by Fable from worker evidence before
the build commission fires, and the filled values are then frozen.

---

## §0 Mission (from Sol §1, binding)

Extend the existing one-session T1 writer (`scripts/topup_thetadata_day.py`)
into the canonical **full-universe daily incremental maintainer** of the single
ThetaData T1 store, so a normal market-day run maintains a lawful S/D source
pair at ≥90% AD-universe coverage without whole-year re-pulls. Retire the
whole-year DAILY refresh behavior and the unconditional-KeepAlive loop.
Source capability only — AD-1 stays `BUILT_NOT_PROVEN`; workflow routing is
AD-1T2.

Hard non-goals (Sol §20 verbatim, all binding): no engine change, no v1.2
change, no Q_flow, no GEX rebuild, no Prophet/UI change, no lowering 0.90, no
universe shrink, no cosmetic Jul/Aug backfill, no R2 repair, no M1 runner
re-pin, no store move/copy/second store, no second Terminal, no AD-2, no
DTE/strike filters.

---

## §A Daily incremental mode

### A1. CLI shape

`scripts/topup_thetadata_day.py` gains a market-wide mode. Final CLI:

```
python -m scripts.topup_thetadata_day --roots SPY,QQQ [--date YYYY-MM-DD]   # legacy bounded mode, byte-compatible behavior
python -m scripts.topup_thetadata_day --daily [--workers N] [--force-run]
```

- `--daily` is mutually exclusive with `--roots`/`--date` (argparse-enforced).
- `--workers` defaults to the frozen production count (§F); values above 6 are
  rejected (hard vendor-safety cap).
- `--force-run` bypasses the session/time gate for diagnostics ONLY and stamps
  `forced=true` in the health receipt. Scheduled invocations never pass it.
- No flag may narrow the universe or the chain (no `--limit`, no DTE/strike
  filters).

### A2. Universe (Sol §7)

Reuse the existing T1 universe resolver used by `backfill_thetadata_eod.py`
(options/GEX universe ∪ ETF anchors ∪ index roots) — import it, do not fork a
list. `PENDING-CENSUS: exact function name(s) + module.` The AD denominator
stays `gex_symbols()` (the canonical AD universe owner) and is resolved at run
time — never hard-coded 375.

### A3. Session gate (Sol §7/§12)

Calendar authority: `lib/nyse_calendar.py` (the ONE canonical trading-calendar
module — R1, SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION). Time gate in
`zoneinfo` `America/New_York` — never a hard-coded UTC offset.

Scheduled (`--daily` without `--force-run`) runs mutate the store only when:

1. today (America/New_York date) is a real NYSE session `D`, and
2. local ET time ≥ 16:10.

Otherwise: **clean no-op**, exit 0, no receipt mutation beyond an optional
`skipped` log line (a weekday holiday and a weekend look identical: no-op).
`S` = previous NYSE session before `D` (calendar-derived, never
weekday arithmetic — the existing `_last_weekday_before` helper stays only for
the legacy `--roots` default-date path).

### A4. Tier ensure law (Sol §4.4/§7, binding)

Per target root, ensure exactly these (session, tier) cells:

```
ensure EOD[S]      # settles overnight S→D; not available on S evening
ensure Greeks[S]   # same clock as EOD
ensure OI[S]       # baseline; normally already present in steady state
ensure OI[D]       # the morning-D print of EOD-S positions = chain_next evidence
```

- "Ensure" = if the exact (session, tier) rows are already present in
  `{store}/{tier}/{ROOT}/{YYYY}.parquet`, skip (`already_present`); else fetch
  that ONE session via the canonical collector and merge with the existing
  exact-date replacement semantics (`_merge_day`). Never widen the request
  window beyond the one session.
- No EOD[D] / Greeks[D] pulls — not needed to settle S, and not reliably
  available on D evening anyway.
- No historical catch-up: a missed prior day is NOT swept by the daily mode
  (historical backfill remains the explicit resumable tool). The receipt (§D)
  makes the resulting gap visible; the frozen engine already degrades safely
  (Q_skew=None across non-consecutive sessions — Sol §4.5).
- Greeks keep full T1 store semantics (`order=3`, full columns) — no AD-only
  schema downgrade.

### A5. Request topology (Sol §4.3)

Per root the tier calls are SEQUENTIAL (eod → oi[S if needed] → oi[D] →
greeks), exactly one one-day request per (tier, session). Root-level
parallelism comes only from the worker pool (§F), so worker count ≈ active
request count. Never exceed 6 workers; Terminal ceiling is 8.

---

## §B Writer exclusion (Sol §8)

One crash-safe advisory lock guards ALL mutating writers of the canonical T1
store:

- Mechanism: `fcntl.flock(LOCK_EX | LOCK_NB)` on `{store}/_writer.lock`
  (store is local APFS — flock is reliable there; the lock FILE persisting is
  harmless, the LOCK dies with the fd, so process death releases ownership and
  no stale file can wedge the source).
- Holders: the daily mode, the legacy `--roots` mode, and
  `scripts/backfill_thetadata_eod.py` (historical). All acquire before the
  first parquet mutation and hold through the run.
- Refusal semantics: non-blocking; on refusal the would-be writer mutates
  NOTHING, emits a machine-readable `writer_locked` outcome (receipt row for
  `--daily`; log line + the existing nonzero exit for the legacy mode so the
  levels-seal caller's retry contract is preserved), and exits nonzero.
- The existing coarse `pgrep -f backfill_thetadata_eod` guard in the topup
  writer stays as belt-and-braces; the flock is the authority.
- This is local writer coordination only — no queue, no lifecycle plane.

`PENDING-CENSUS:` confirm backfill_thetadata_eod.py has a single mutation
choke-point where the flock can be acquired once.

---

## §C Partial failure / atomicity (Sol §9)

- Keep the existing per-(tier, root, year) atomic write (tmp → `os.replace`).
  No cross-universe transaction.
- One root's failure never touches other roots; one tier's failure never marks
  the root complete.
- Per-root terminal states (at least): `complete`, `partial`, `failed`,
  `already_present`, `vendor_empty`, `terminal_unreachable`,
  `timeout_or_stream_failure`, `writer_locked`.
- `complete` for the daily mode = all four ensure cells of §A4 present after
  the run (however they got there). `already_present` = all four present
  before the run touched the vendor.
- `terminal_unreachable` at startup aborts the whole run before any pull
  (existing `reachable()` probe), with a `failed` receipt naming it.

---

## §D Daily source-health receipt (Sol §10)

Home: the existing T1 `_manifest.json`, new top-level `daily_refresh` section
(one object, overwritten per run; no unbounded history — the log file carries
history). `PENDING-CENSUS:` confirm manifest write path + that
`backfill_thetadata_eod.py` rewrites preserve unknown/other keys; if not, the
build makes the historical writer read-modify-write so the `daily_refresh`
section survives (Sol §10 explicitly requires this).

Logical fields (all required):

```
source=thetadata, mode=incremental_daily, S, D,
started_at, finished_at, elapsed_sec, worker_count,
t1_universe_count, ad_universe_count,
eod_S_roots, greeks_S_roots, oi_S_roots, oi_D_roots,
complete_t1_roots, complete_ad_roots, ad_coverage_pct,
status ∈ {healthy, partial, failed},
failure_counts_by_reason, failure_examples (bounded ≤10),
terminal_health, forced (bool)
```

- `complete_ad_roots` = AD-universe roots with ALL FOUR §A4 cells present
  (the lawful-S/D-panel intersection), never "has a year parquet".
- `healthy` requires `complete_ad_roots / ad_universe_count ≥ 0.90` (the 0.90
  is the existing frozen AD gate constant — reference it, do not mint a second
  literal if importable; ad_universe_count is resolved, never 375-literal).
- `failed` = run aborted before per-root work (gate pass but terminal
  unreachable, lock refused, universe resolution failed). Everything between
  = `partial`.
- Receipt writes are atomic (tmp → replace) and happen even on `partial`.
  A gate no-op (non-session / pre-16:10) writes NO receipt (the absence of a
  session's receipt is itself the honest record; no fake healthy rows).

---

## §E Scheduler transition (Sol §11/§12)

Ruling: **new clearly-named daily label; old daily keepalive retired from the
repo estate.** Exactly one scheduled daily T1 maintainer may be active on m1.

- New: `scripts/launchd/com.macro.thetadata-daily.plist` +
  `scripts/launchd/theta_daily_refresh.sh`.
  - Finite periodic: `StartCalendarInterval` fire points at host-local (PT)
    13:15, 14:30, 16:00, 18:00 (= 16:15 / 17:30 / 19:00 / 21:00 ET — PT↔ET is
    a constant 3h across both DST regimes, so PT-local scheduling cannot drift
    across the ET gate; the wrapper still enforces the real gate in
    America/New_York). NO `KeepAlive`. `RunAtLoad=true` is permitted (covers
    reboot/wake) because every invocation is gate-checked and idempotent.
  - Multiple fire points are the bounded retry ladder: a successful earlier
    run makes later fires cheap `already_present` no-ops (skip-if-present is
    the idempotence); a failed earlier run gets three more bounded attempts,
    never a hammer loop.
  - The wrapper: env/log plumbing + exec the python daily mode; ALL gating
    logic lives in python (testable), not bash.
- Retired: `scripts/launchd/theta_backfill_keepalive.sh` and
  `scripts/launchd/com.macro.thetadata-backfill.plist` are DELETED from the
  repo. Historical backfill (`backfill_thetadata_eod.py`) remains as an
  explicit, manually-invoked resumable tool. The whole-year unmark trick dies
  with the wrapper.
- Runbook (`research/THETADATA_OPS_RUNBOOK.md`) gains the transition
  procedure: `launchctl bootout` the old backfill label, `bootstrap` the new
  daily label, verification steps, and the explicit-historical-catch-up
  procedure for missed days.
- **NOT INSTALLED in this wave** (Sol §23: no unreviewed production
  scheduler). The PR ships the plist + wrapper + runbook; m1 installation is a
  post-Sol-acceptance act. `installed_live_status: NOT_INSTALLED`.

`PENDING-CENSUS:` live m1 label inventory + hand-patch deltas decide whether
the transition procedure needs extra steps (e.g. the live wrapper differs from
repo bytes).

---

## §F Concurrency (PENDING-BENCHMARK)

- Production `--workers` default: `PENDING-BENCHMARK` (chosen by Fable from
  the 1/2/4/6 evidence; hard cap 6; must fit full ~375-root steady-state
  refresh comfortably inside 16:10→18:30 ET without Terminal degradation).
- Selection criteria, in order: (1) no Terminal stall/health degradation at
  the chosen count; (2) projected full-universe wall time ≤ ~90 min with
  headroom; (3) per-request latency knee — prefer the lowest count meeting
  (1)+(2).
- If NO count ≤6 fits the envelope, that is a measured bottleneck returned to
  Sol in the verdict — never hidden by filters or universe shrink (Sol §14).

---

## §G Compatibility (Sol §13)

- Legacy `--roots [--date]` mode: same defaults, same merge semantics, same
  exit codes (0 complete / 2 vendor-empty-all / 1 partial-or-blocked), same
  log shapes relied on by `ops/launchd/levels_seal_preopen.sh`. The only
  additive change: flock acquisition (refusal → existing exit-1 path).
- `resolve_thetadata_store()` remains the ONLY store resolution (no second
  path, no env forks).

---

## §H Hostile tests (Sol §16 — all required, mock collector + injected clock)

Clock: normal midweek; Friday→Monday; market holiday (calendar says
non-session on a weekday → no-op); DST boundary regimes (March/November —
gate computed in America/New_York, asserted against UTC times that would fool
a fixed-offset gate); before/after 16:10 ET; delayed invocation (22:00 ET
same-day behavior identical); same-session rerun (`already_present` everywhere,
zero vendor calls — assert the mock records no requests).

Pair: OI[S] already present; bootstrap OI[S] absent (fetched); each of
EOD[S]/Greeks[S]/OI[D] independently absent (fetched singly); absent D EOD
never blocks (no code path may request it — assert the mock never sees an
EOD[D] request); stale-July + fresh-August store yields no fabricated
consecutive pair (store-level: the daily mode only writes S/D cells; assert no
other dates touched).

Writer: two concurrent daily invocations (second gets `writer_locked`, zero
mutations — byte-compare store); daily vs historical backfill (either order);
SIGKILL death under lock → next invocation acquires cleanly; one-root vendor
failure isolates; one-tier failure → root `partial`, not complete; unrelated
dates in the year parquet byte-preserved after a merge.

Universe: symbol added/dropped from resolver → denominator follows; root with
no options (`vendor_empty` root outcome, run continues); denominator follows
the canonical owner (no 375 literal anywhere — grep-test the diff).

Scheduler: plist parses (plutil -lint); no KeepAlive key; StartCalendarInterval
entries as ruled; wrapper contains no gating logic (grep-test); successful run
followed by immediate re-invocation = cheap no-op (idempotence test stands in
for "does not respawn"); only one scheduled daily maintainer in the repo
estate (test asserts the retired plist/wrapper files are GONE).

Compatibility: existing levels-seal `--roots --date` behavior survives —
existing topup tests keep passing unmodified where they encode the contract;
exit-code triple preserved.

Receipt: healthy/partial/failed classification flips on constructed inputs;
0.90 threshold flip test; `forced` stamping; atomic write; backfill
manifest-rewrite preserves `daily_refresh` (flip: remove preservation →
test fails).

---

## §I Out of scope for the builder

Everything in §0 non-goals; plus: no m1 installation, no launchctl commands,
no store access (all tests mock the collector and use tmp stores), no edits to
`engine/options_intel_brief.py` or any engine file, no changes to
`collectors/thetadata.py` semantics (`PENDING-CENSUS:` unless the census
proves a thread-safety defect, in which case Fable amends this spec
explicitly), no new stores, no receipt homes outside `_manifest.json`.
