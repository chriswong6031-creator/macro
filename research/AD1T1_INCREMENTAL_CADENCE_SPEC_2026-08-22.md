# AD-1T1 — Full-Universe Incremental ThetaData T1 Cadence: Frozen Build Spec

**Wave:** AD-1T1 (`WS:ADVANCED-DATA-OPTIONS`)
**Authority:** `DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA`; Sol handoff
`research/ADVANCED_DATA_OPTIONS_AD1T1_THETADATA_INCREMENTAL_T1_CADENCE_HANDOFF_2026-08-22.md`
(committed copy — the binding text); prior wave spec
`research/AD1T0_THETADATA_CUTOVER_SPEC_2026-08-22.md`.
**Ruled by:** Fable (COO), 2026-08-22. Builders execute this spec; they do not redesign it.
**Merge authority:** NONE — the AD-1T1 PR returns to Sol unmerged (DRAFT + HOLD-FOR-SOL, PR #6267).
**Revision:** R3 — R2 amended for all 17 findings of the opus analyst attack
(F1–F17, adjudicated by Fable 2026-08-22 ~22:00Z; two ensure-law-adjacent
amendments — the F1 S-panel healthy split and the F5 `fetch_failed`
superset — are RETURNED TO SOL EXPLICITLY in the §18 packet), then amended
again for all 12 findings of the opus post-build adversarial review
(RF1–RF12 + one GAPS hardening, adjudicated ~23:15Z): RF1 staleness anchor
threshold 22:00→**20:00 ET** with a computed (not grep) test at both
sentinel fire points; RF2 `deadline_exceeded` FORCES `status=partial`; RF3
the historical backfill must lock-and-write the SAME resolved store as the
daily lane — `resolve_thetadata_store()` agreement asserted at startup,
refusing on mismatch (first-install exception: when NO store resolves
anywhere, `_store_dir()` creation is permitted); RF4 a real cross-writer
lock test exercising `backfill.main()`'s lock site in both orders; RF5 the
daily mode gains the advisory (warn-only) pgrep breadcrumb; RF6 the refusal
test compares CONTENT hashes, not path names; RF7 deadline default
100→**65 min** (must fit inside the 70-min minimum fire spacing so ladder
rungs are never swallowed); RF8 `s_suspect_non_session` denominator counts
only roots with actual EOD[S] vendor attempts this run (zero attempts →
flag false); RF9 the stale-tmp sweep also covers store-root `*.tmp`
(receipt tmp) and `publish_r2._uploadable` excludes `.tmp`-suffixed files;
RF10 `ops/LIVE_FLOW_RUNBOOK.md` lane rows updated (the r2sync plist's
stale prose + the ~3× nightly R2 delta estimate are REPORTED TO SOL, not
repaired here); RF11 the ops runbook marks `com.macro.thetadata-daily`
NOT_INSTALLED pending Sol; RF12 terminal-loss abort records completed
futures before stamping; GAPS-hardening: an OSError opening the lock file
is a `failed` outcome (log + exit 1), never a traceback.

Status: FROZEN except §F (`PENDING-BENCHMARK` — filled by Fable from the
quiet-window ladder before the PR leaves draft review).

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
python -m scripts.topup_thetadata_day --roots SPY,QQQ [--date YYYY-MM-DD]     # legacy bounded mode, byte-compatible behavior
python -m scripts.topup_thetadata_day --roots @universe --date YYYY-MM-DD     # explicit catch-up: same 3-tier one-day ensure over the resolved T1 universe (F10)
python -m scripts.topup_thetadata_day --daily [--workers N] [--deadline-min M] [--force-run]
```

- `--daily` is mutually exclusive with `--roots`/`--date` (argparse-enforced).
- `--roots @universe` (F10) resolves the root list via
  `scripts.backfill_thetadata_eod._resolve_universe()` and otherwise behaves
  exactly like the legacy bounded mode for the named `--date` (3-tier one-day
  ensure; same flock; same exit codes). This is the runbook's explicit
  catch-up tool for gaps of ≥2 sessions — the historical backfill is NOT the
  catch-up path. (A single missed session self-heals: the next session's
  daily run ensures the missed S cells by construction.)
- `--workers` defaults to the frozen production count (§F); values above 6
  are rejected (hard vendor-safety cap).
- `--deadline-min` (F2) defaults to 100; §B semantics.
- `--force-run` bypasses the session/time gate for diagnostics ONLY and
  stamps `forced=true` in the health receipt. Scheduled invocations never
  pass it.
- No flag may narrow the universe or the chain (no `--limit`, no DTE/strike
  filters).

### A2. Universe (Sol §7)

Reuse the existing T1 universe resolver used by `backfill_thetadata_eod.py`
(options/GEX universe ∪ ETF anchors ∪ index roots) — import it, do not fork a
list. CENSUS-CONFIRMED: `scripts.backfill_thetadata_eod._resolve_universe()`
(ETF_ANCHORS 20 ∪ INDEX_ROOTS [SPX, SPXW] ∪ `gex_symbols()`; 378 today). The
AD denominator stays `engine.options_universe.gex_symbols()` (375 today) and
both are resolved at run time — never hard-coded. Index roots (SPX/SPXW) are
in the T1 universe but NOT in `gex_symbols()`: they count toward
`complete_t1_roots` only and are excluded from `ad_coverage_pct` by
construction (analyst surface-5 note).

### A3. Session gate (Sol §7/§12; F3, F4, F12 amendments)

Calendar authority: `lib/nyse_calendar.py` (the ONE canonical trading-calendar
module). Time gate in `zoneinfo` `America/New_York` — never a hard-coded UTC
offset.

- Exact derivation (F4): today_et = current America/New_York date;
  gate requires `nyse_calendar.is_session(today_et)` AND local ET time ≥
  16:10. Then `D = today_et` and `S = nyse_calendar.session_n_back(D, 1)`;
  a `None` S aborts the run as `failed`. **`expected_last_session()` is
  FORBIDDEN on this path** — its 17:00 ET settle buffer returns S when asked
  for D at the 16:15-window fire.
- (F3) S and D are resolved EXACTLY ONCE, before the worker pool starts,
  into an immutable run context; no worker may consult the wall clock. The
  receipt's S/D are that context's values (a run crossing midnight ET keeps
  its birth clock).
- Otherwise: **clean no-op**, exit 0, no receipt mutation (a weekday holiday
  and a weekend look identical: no-op). NYSE half-days need NO special
  branch (the calendar module deliberately does not model early closes;
  `is_session` is True and the 16:10 gate is an availability floor — data
  landing earlier is strictly safer). Builders must not invent an
  early-close branch.
- (F12) `lib/nyse_calendar.py`'s `ONE_OFF_CLOSURES` is hand-maintained (last
  entry 2025-01-09). If EOD[S] returns vendor-empty for >50% of attempted
  roots, stamp `s_suspect_non_session: true` in the receipt (operator
  breadcrumb: check for an unlisted closure) and name `ONE_OFF_CLOSURES`
  maintenance in the runbook. Never auto-walk S backwards — that would be
  historical catch-up.
- The legacy `--roots` default-date path keeps `_last_weekday_before`
  unchanged (§G byte-compatibility).

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
  window beyond the one session. Year boundary is handled by keying the
  parquet on the CELL's own `day.year` (S-cells may land in a different year
  parquet than OI[D]; verified correct in the existing writer).
- (F1) **OI[D] availability at ≥16:10 ET on D is UNMEASURED** — the
  collector deliberately converts the v3 current-day-wildcard 400 into an
  empty frame, and the repo's only measurements suggest same-evening history
  pulls may return nothing. The ensure law still ATTEMPTS OI[D] every run
  (cheap; converges either way — if the vendor withholds it, the same cell
  is re-ensured tomorrow as OI[S']), but NOTHING gates on same-evening
  success: see §D's S-panel healthy split. The first post-merge scheduled
  production session (Sol §19) doubles as the measurement — its receipt's
  `oi_D_roots` count IS the answer. RETURNED TO SOL explicitly in §18.
- No EOD[D] / Greeks[D] pulls — not needed to settle S, and not reliably
  available on D evening anyway.
- No historical catch-up in `--daily`: a missed prior day is NOT swept
  (the explicit `--roots @universe --date` tool is, per A1/F10). The receipt
  (§D) + staleness anchor (F8) make gaps visible; the frozen engine already
  degrades safely (Q_skew=None across non-consecutive sessions — Sol §4.5).
- Greeks keep full T1 store semantics (`order=3`, full columns) — no AD-only
  schema downgrade.
- Reconciliation with AD-1T0 (analyst surface-7 note): the AD-1T0 spec
  describes chain_next OI[D] as "generated pre-open on D" — that describes
  the VENDOR's publication clock (~06:30 ET on D). AD-1T1 COLLECTS the same
  cell at ≥16:10 ET on D (or the next session, per F1). Same session, later
  collection clock; the AD-1T0 receipts bind content, not collection hour.

### A5. Request topology (Sol §4.3)

Per root the tier calls are SEQUENTIAL (eod → oi[S if needed] → oi[D] →
greeks), exactly one one-day request per (tier, session). Root-level
parallelism comes only from the worker pool (§F), so worker count ≈ active
request count. Never exceed 6 workers; Terminal ceiling is 8.

CENSUS-CONFIRMED: the collector windows wildcard pulls at ≤7 calendar days,
so a one-day request is exactly ONE window = one HTTP request (the internal
`ThreadPoolExecutor(WINDOW_WORKERS=6)` has a single unit of work; greeks
one-day is likewise a single required request). The collector is thread-safe
for a root-level pool: fresh `requests.Session` per call/thread, module state
read-only. Per-window retry (2 retries, 5s/15s backoff) is the collector's
own; the daily mode adds NO additional retry layer.

(F2) **Hard wall-clock deadline:** the daily mode enforces `--deadline-min`
(default 100) measured from run start: on expiry it stops dispatching new
roots, drains in-flight work, releases the flock, and writes a `partial`
receipt with `deadline_exceeded: true`. The lock is never held past the
deadline + drain. The 04:30/06:00 PT levels-seal window is a protected zone
by construction (last fire 18:00 PT + 100 min ≪ 04:30 PT).

---

## §B Writer exclusion (Sol §8; F7, F9, F14, F15 amendments)

One crash-safe advisory lock guards ALL mutating writers of the canonical T1
store:

- Mechanism: `fcntl.flock(LOCK_EX | LOCK_NB)` on `{store}/_writer.lock`
  (store is local APFS — flock is reliable there; the lock FILE persisting is
  harmless, the LOCK dies with the fd, so process death releases ownership and
  no stale file can wedge the source).
- Holders: the daily mode, the legacy/catch-up `--roots` modes, and
  `scripts/backfill_thetadata_eod.py` (historical). All acquire before the
  first parquet mutation and hold through the run (bounded by the F2
  deadline in the daily mode).
- Refusal semantics: non-blocking; on refusal the would-be writer mutates
  NOTHING — not the parquets and NOT `_manifest.json`. Refusal visibility is
  a machine-readable single-line JSON to stdout/log
  (`{"event":"writer_locked",...}`). Exit codes (F14): the `--daily` mode
  exits **0** on refusal (a lawful ladder outcome — repeated nonzero exits
  would poison `launchctl print`'s LastExitStatus as a daily false alarm);
  the legacy `--roots` modes keep their existing exit-1 shape so the
  levels-seal caller's contract is preserved. The `_manifest.json`
  `daily_refresh` section is written ONLY by a run that HOLDS the flock.
- Lock-acquisition order in the daily mode: acquire flock FIRST, then the
  Terminal reachability probe — so a lock-holding run can always write its
  `failed` receipt safely, and a refused run never needs to.
- (F7) The pgrep check is DEMOTED to advisory in the daily mode: it logs a
  warning and never refuses (the flock is the sole authority — a pgrep
  refusal writes no artifact and can be false-positived by an orphaned
  backfill child or an operator's grep for as long as the orphan lives).
  Only the legacy `--roots` mode keeps its refusing pgrep for caller-contract
  byte-compatibility.
- (F15) `data/thetadata_eod/_writer.lock` is added to `.gitignore` and to
  `scripts/publish_r2.py`'s `_uploadable` exclusion (alongside
  `_manifest.json`) so the lock file pollutes neither git nor R2.
- CENSUS-CONFIRMED: `backfill_thetadata_eod.py` mutates only inside its
  `main()` root-year loop; the flock is acquired once in `main()` before the
  first mutation. Today the ONLY cross-writer guards are the two pgrep
  checks — there is no lock file at all; the flock is new and closes the
  pgrep TOCTOU gap.
- This is local writer coordination only — no queue, no lifecycle plane.
  The 22:00 PT r2sync lane is a store READER and takes no lock: per-file
  writes stay atomic (tmp → replace), and cross-file consistency during a
  sync was never guaranteed by the retiring design either.

---

## §C Partial failure / atomicity (Sol §9; F5, F6, F9, F11 amendments)

- Keep the existing per-(tier, root, year) atomic write (tmp → `os.replace`).
  No cross-universe transaction.
- (F9) The tmp filename becomes `{YYYY}.parquet.tmp` (the current
  `{YYYY}.tmp.parquet` MATCHES the store readers' `*.parquet` glob — a
  SIGKILL between write and replace leaves a file that
  `engine/thetadata_store.py`'s unfiltered globs would concatenate,
  doubling rows). The daily mode sweeps stale `*.tmp.parquet` /
  `*.parquet.tmp` files under the flock at startup and counts them in the
  receipt (`stale_tmp_swept`).
- One root's failure never touches other roots; one tier's failure never
  marks the root complete. (F11) Every per-root unit of work runs inside a
  catch-all that maps ANY exception (vendor, parse, parquet read, disk) to
  terminal state `failed` with the exception class recorded in
  `failure_counts_by_reason`. No exception may escape a worker into the pool.
- Per-root terminal states (at least): `complete`, `partial`, `failed`,
  `already_present`, `vendor_empty`, `terminal_unreachable`,
  `fetch_failed`, `date_unresolved`, `writer_locked`.
  - (F5) `fetch_failed` replaces the planned `timeout_or_stream_failure`
    bucket AS A SUPERSET: the collector returns `None` indistinguishably for
    timeouts, stream truncation, non-200s (entitlement/429/5xx), CSV parse
    failures, and mid-run terminal loss — the writer cannot see the cause
    without collector changes (out of scope). Sol's §9 taxonomy named
    `timeout_or_stream_failure`; this rename is RETURNED TO SOL in §18.
    Mitigation for the operationally critical case: when `fetch_failed`
    exceeds 25% of attempted roots, the run re-probes `reachable()`; a False
    re-probe aborts the run as `failed` with reason `terminal_lost_mid_run`
    and stamps `terminal_health` accordingly.
  - (F6) `date_unresolved` = the collector returned ROWS but none carry the
    target date after normalization (e.g. EOD rows whose blank `last_trade`
    → NaT). `vendor_empty` means the collector returned an EMPTY frame; it
    may never absorb the date-unresolved case. Per-cell instrumentation:
    `rows_returned` vs `rows_for_target_date`.
- `complete` for the daily mode = all four ensure cells of §A4 present after
  the run (however they got there). `already_present` = all four present
  before the run touched the vendor. The S-panel/chain_next coverage split
  is §D's.
- `terminal_unreachable` at startup (probe AFTER lock, §B) aborts the whole
  run before any pull, with a `failed` receipt naming it.

---

## §D Daily source-health receipt (Sol §10; F1, F5, F8, F16 amendments)

Home: the existing T1 `_manifest.json`, new top-level `daily_refresh` section
(one object, overwritten per run; no unbounded history — the log file carries
history). CENSUS-CONFIRMED: `_write_manifest()`
(`scripts/backfill_thetadata_eod.py:200-215`) rebuilds the manifest FROM
SCRATCH and full-REPLACEs it after every completed root-year — any foreign
key is wiped today (measured live: keys are exactly
store/n_roots/per_root/updated_at, and the keepalive wrapper's
`universe_pass_complete` completion guard is INERT — that key is never
written by anything; its only reader is the retiring wrapper itself). The
build therefore makes `_write_manifest` read-modify-write: carry forward
`daily_refresh` (and unknown top-level keys generally, fail-open) while
regenerating its own four keys. (F16) On an unreadable `_manifest.json` it
logs ONE warning naming the file and the JSON error, preserves nothing, and
writes the freshly regenerated manifest — fail-open to today's behavior,
never raise. Flip-tests required for both preservation and corrupt-read.

Note: `publish_r2._manifest_doc` embeds the whole manifest, so
`daily_refresh` rides to R2 — intended (it is the store's own health record).

Logical fields (all required):

```
source=thetadata, mode=incremental_daily, S, D,
started_at, finished_at, elapsed_sec, worker_count,
t1_universe_count, ad_universe_count,
eod_S_roots, greeks_S_roots, oi_S_roots, oi_D_roots,
complete_t1_roots, complete_ad_roots, ad_coverage_pct,
chain_next_ad_roots,
status ∈ {healthy, partial, failed},
deadline_exceeded (bool), stale_tmp_swept (int),
s_suspect_non_session (bool),
failure_counts_by_reason, failure_examples (bounded ≤10),
terminal_health, forced (bool)
```

- (F1 — RETURNED TO SOL) **S-panel healthy split:** `complete_ad_roots` = AD
  roots with the S-PANEL present (EOD[S] ∧ Greeks[S] ∧ OI[S] — the three
  cells the vendor can always serve post-close-D), and `healthy` requires
  `complete_ad_roots / ad_universe_count ≥ 0.90` on that panel.
  `chain_next_ad_roots` (OI[D] present) is reported separately and does NOT
  gate `healthy` — OI[D]'s same-evening availability is the F1 unknown, its
  absence self-heals next session as OI[S'], and the AD producer's own
  settled-pair selection (frozen engine) decides which pair is buildable.
  This does not lower 0.90; it defines the numerator on the cells a lawful
  evening run can guarantee. The threshold constant is imported from the
  frozen engine's `SOURCE_COVERAGE_GATE` (`engine/options_intel_brief.py`),
  never a second literal; `ad_universe_count` is resolved, never 375.
- `complete_t1_roots` counts the full T1 universe (incl. index roots);
  `ad_coverage_pct` = S-panel AD coverage.
- `failed` = run aborted before per-root work while HOLDING the lock (gate
  pass but terminal unreachable, universe resolution failed, or
  `terminal_lost_mid_run` per §C). A lock REFUSAL writes no receipt at all
  (§B — log + exit code are its record). Everything between = `partial`.
- Receipt writes are atomic (tmp → replace) and happen even on `partial`.
  A gate no-op (non-session / pre-16:10) writes NO receipt (the absence of a
  session's receipt is itself the honest record; no fake healthy rows).
- (F8) **Staleness anchor:** `daily_refresh.D` is the lane's liveness
  record. The existing `com.macro.theta-staleness` sentinel
  (`scripts/launchd/theta_staleness_sentinel.sh`) gains a check: ALERT when
  `daily_refresh.D != nyse_calendar.session_date()` after 22:00 ET on a
  session day (a sleeping/missed host is otherwise indistinguishable from a
  healthy one, since launchd calendar fires do not wake a sleeping Mac and
  coalesce on wake). The runbook install procedure asserts the host does not
  sleep (`pmset -g`).

---

## §E Scheduler transition (Sol §11/§12; F13 amendment)

Ruling: **new clearly-named daily label; old daily keepalive retired from the
repo estate.** Exactly one scheduled daily T1 maintainer may be active on m1.

- New: `scripts/launchd/com.macro.thetadata-daily.plist` +
  `scripts/launchd/theta_daily_refresh.sh`.
  - Finite periodic: `StartCalendarInterval` fire points at host-local (PT)
    **13:20**, 14:30, 16:00, 18:00 (= 16:20 / 17:30 / 19:00 / 21:00 ET in
    the normal regime; 13:20 gives 10 min margin over the 16:10 ET gate).
    NO `KeepAlive`. `RunAtLoad=true` is permitted (covers reboot/wake)
    because every invocation is gate-checked and idempotent.
  - (F13, precise wording) PT and ET shift DST on the same dates; the PT↔ET
    offset deviates from 3 h only inside a Sunday 01:00–05:00 ET transition
    window containing no fire point and no session. Correctness rests on the
    America/New_York gate in python, not on the offset. The install
    procedure verifies the host TZ (`systemsetup -gettimezone` =
    America/Los_Angeles) — the plist hours are host-local.
  - Multiple fire points are the bounded retry ladder: a successful earlier
    run makes later fires cheap `already_present` no-ops; a failed earlier
    run gets three more bounded attempts, never a hammer loop. launchd
    facts (from-knowledge, flagged): calendar intervals elapsing during
    sleep coalesce into ONE event on wake; no punitive backoff for nonzero
    exits absent KeepAlive; `ThrottleInterval` inert without KeepAlive.
  - Carry forward `LimitLoadToSessionType Aqua` knowingly (agent loads at
    GUI login only — the runbook states the auto-login requirement).
  - The wrapper: env/log plumbing + exec the python daily mode; ALL gating
    logic lives in python (testable), not bash.
- Retired: `scripts/launchd/theta_backfill_keepalive.sh` and
  `scripts/launchd/com.macro.thetadata-backfill.plist` are DELETED from the
  repo. Historical backfill (`backfill_thetadata_eod.py`) remains as an
  explicit, manually-invoked resumable tool (for HISTORY — the daily/catch-up
  ensure tools own freshness; the current-year-unmark trick dies with the
  wrapper). (F7) The transition procedure includes `pkill -f
  backfill_thetadata_eod` AFTER `launchctl bootout` and verifies no orphaned
  python child survives the wrapper's death.
- Runbook (`research/THETADATA_OPS_RUNBOOK.md`) gains the transition
  procedure: refresh the ops-tree bytes to current main FIRST (see census
  facts below), `launchctl bootout` the old backfill label + orphan pkill +
  verify, `bootstrap` the new daily label, TZ + no-sleep assertions,
  verification steps, the `--roots @universe --date` catch-up procedure for
  ≥2-session gaps, and `ONE_OFF_CLOSURES` maintenance (F12).
- **NOT INSTALLED in this wave** (Sol §23: no unreviewed production
  scheduler). The PR ships the plist + wrapper + runbook; m1 installation is
  a post-Sol-acceptance act. `installed_live_status: NOT_INSTALLED`.

CENSUS-CONFIRMED live-m1 facts the runbook transition section must encode:

- The live lane runs from DETACHED ops worktrees, not a synced main:
  `theta-ops-wt` HEAD b9e62f5 (2026-07-30) with newer bytes hand-copied onto
  disk for the wrapper + backfill script, and `collectors/thetadata.py` at
  the OLD committed revision (511-line diff vs repo — missing the #5942
  NA-parse fixes; a live data-quality hazard worth naming in the verdict).
  `topup_thetadata_day.py` exists only in `hub-ops-wt` (HEAD ce456ab,
  2026-08-02), where the levels-seal caller cds. The install procedure MUST
  refresh the ops-tree bytes to current main (at minimum:
  `collectors/thetadata.py`, `scripts/topup_thetadata_day.py`,
  `scripts/backfill_thetadata_eod.py`, `lib/nyse_calendar.py`, the new
  wrapper + plist) before bootstrapping the new label.
- Installed `com.macro.thetadata-backfill.plist` differs from repo only in
  `EnvironmentVariables PATH` (cosmetic — every theta wrapper hardcodes
  `PYTHON=/opt/homebrew/Caskroom/miniconda/base/bin/python`, present with
  Python 3.12.13 + pandas 3.0.5 + pyarrow 25.0.0). The new daily wrapper
  keeps that hardcoded-python convention.
- `com.macro.thetadata-surface.plist` is NOT installed on m1; `theta-terminal`
  and `theta-staleness` are. The transition boots out exactly ONE label
  (`com.macro.thetadata-backfill`) and bootstraps exactly one
  (`com.macro.thetadata-daily`).

---

## §F Concurrency (PENDING-BENCHMARK)

- Production `--workers` default: `PENDING-BENCHMARK` (chosen by Fable from
  the 1/2/4/6 quiet-window ladder evidence; hard cap 6; must fit full
  ~375-root steady-state refresh comfortably inside 16:10→18:30 ET without
  Terminal degradation).
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
  log shapes relied on by `ops/launchd/levels_seal_preopen.sh`. Additive
  changes only: flock acquisition (refusal → existing exit-1 path) and the
  F9 tmp rename (invisible to the caller).
- (F17) The legacy contract is currently UNTESTED (zero repo tests reference
  the topup writer). The builder writes CHARACTERIZATION tests pinning the
  exit-code triple, `_merge_day` date-replacement semantics, and
  `_last_weekday_before` default BEFORE adding the daily mode.
- `resolve_thetadata_store()` remains the ONLY store resolution (no second
  path, no env forks).

---

## §H Hostile tests (Sol §16 — all required, mock collector + injected clock)

Characterization-first (F17): pin the legacy `--roots` contract before any
new code.

Clock: normal midweek; Friday→Monday; market holiday (calendar says
non-session on a weekday → no-op); DST boundary regimes (March/November —
gate computed in America/New_York, asserted against UTC times that would fool
a fixed-offset gate); before/after 16:10 ET; delayed invocation (22:00 ET
same-day behavior identical); the F4 trap pinned (at 16:20 ET on session D
the run targets (D, prev) — a test that FAILS if anyone swaps in
`expected_last_session`); run-context freeze (F3 — workers never re-derive
dates); same-session rerun (`already_present` everywhere, zero vendor calls —
assert the mock records no requests).

Pair: OI[S] already present; bootstrap OI[S] absent (fetched); each of
EOD[S]/Greeks[S]/OI[D] independently absent (fetched singly); absent OI[D]
(current-day-empty per F1) leaves the root S-panel-complete and
`chain_next_ad_roots` short WITHOUT degrading `healthy`; absent D EOD never
blocks (no code path may request EOD[D]/Greeks[D] — assert the mock never
sees one); Dec→Jan year boundary (S cells land in the S-year parquet, OI[D]
in the D-year parquet); stale-July + fresh-August store yields no writes
outside the S/D cells (assert no other dates touched).

Writer: two concurrent daily invocations (second gets `writer_locked`, exit
0, zero mutations — byte-compare store); daily vs historical backfill (either
order); SIGKILL death under lock → next invocation acquires cleanly; F9
sweep: a planted stale `2026.tmp.parquet` is swept under flock and counted;
tmp writes use `{YYYY}.parquet.tmp` (glob-test: no store reader glob matches
it); one-root vendor failure isolates (F11 — including a CORRUPT year parquet
raising inside the merge: root → `failed`, run continues); one-tier failure →
root `partial`; unrelated dates in the year parquet byte-preserved after a
merge.

Universe: symbol added/dropped from resolver → denominator follows; root with
no options (`vendor_empty` root outcome, run continues); `date_unresolved`
distinct from `vendor_empty` (F6 — rows returned, none on target date);
`fetch_failed` >25% triggers the reachable() re-probe and terminal-loss abort
(F5); denominator follows the canonical owner (no hard-coded 375/378 —
grep-test the new code).

Scheduler: plist parses (plutil -lint where available, else XML assert); no
KeepAlive key; StartCalendarInterval entries exactly as §E; wrapper contains
no gating logic (grep-test); successful run followed by immediate
re-invocation = cheap no-op; retired files are GONE (test asserts absence of
theta_backfill_keepalive.sh + com.macro.thetadata-backfill.plist); exactly
one scheduled daily maintainer in the repo estate.

Deadline (F2): a mock-slow collector makes the run exceed `--deadline-min` →
no new roots dispatched, lock released, `partial` receipt with
`deadline_exceeded: true`.

Compatibility: legacy `--roots --date` behavior survives (characterization
suite green, unmodified); `--roots @universe` resolves via
`_resolve_universe()` and applies the 3-tier ensure for the named date;
exit-code triple preserved.

Receipt: healthy/partial/failed classification flips on constructed inputs;
S-panel split (F1 — OI[D] absent everywhere still yields `healthy` when the
S-panel clears 0.90; S-panel short → not healthy); threshold imported from
the engine constant (flip: change the import → test fails); `forced`
stamping; `s_suspect_non_session` flip (F12); atomic write; backfill
manifest-rewrite preserves `daily_refresh` (flip: remove preservation → test
fails); corrupt manifest → warn + fail-open regenerate, never raise (F16);
staleness-anchor check in the sentinel script (F8 — grep/functional test that
the sentinel reads `daily_refresh.D`).

---

## §I Out of scope for the builder

Everything in §0 non-goals; plus: no m1 installation, no launchctl commands,
no store access (all tests mock the collector and use tmp stores), no edits
to `engine/**` (byte-frozen) or `collectors/thetadata.py` (the F5 cause-blind
`None` is accepted as a constraint this wave, not fixed), no new stores, no
receipt homes outside `_manifest.json`. Owned files beyond the writer pair:
`scripts/launchd/theta_daily_refresh.sh` + `com.macro.thetadata-daily.plist`
(new), the two retired launchd files (deleted),
`scripts/launchd/theta_staleness_sentinel.sh` (F8 staleness-anchor check
only), `scripts/publish_r2.py` (F15 `_uploadable` exclusion only),
`.gitignore` (F15 one line), `research/THETADATA_OPS_RUNBOOK.md`, tests.
