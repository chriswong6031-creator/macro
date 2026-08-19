# P-LAB commissioning prep — operator runbook

**Wave:** LAB-0 §6 step 3 ("Radar live commissioning"), commissioning-prep round, per
`research/prophet_v4/LAB0_B5_RECUT_OPERATOR_LAB_2026-08-18.md` §4/§6 and the day-2 Chairman
directive. **Status:** three build pieces shipped this PR (R2-first spool transport, baseline
provisioning CLI, e2e chain test); **arming W4 itself is explicitly NOT done here** — that stays
the operator's own act, gated on this PR's merge AND `#5929` (R-LAB-1, the sibling PR that fixes
the Radar W4.1 transport correctness this Lab reader depends on) merging first.

## What this PR shipped (build-only, zero runtime bytes armed)

1. **R2-first spool transport** — `engine.prophet_lab.sources.resolve_radar_spool` now tries R2
   first (via `engine.entry_radar.spool`'s exact credential ladder — the SAME backend the Radar
   spool WRITER uses), falling back to a local directory only when R2 is unconfigured or fails.
   `health.radar_spool_source` in `GET /api/prophet/lab/v1` now names the actual backend
   (`"r2"`/`"local"`/`"unconfigured"`); an R2 credential/permission/network failure surfaces as
   `health.radar_spool_error`, never a silent empty board.
2. **Baseline provisioning** — `scripts/prophet_lab_baseline.py`, an operator CLI that mints the
   `PROPHET_LAB_OBSERVATION_BASELINE_PATH` marker. Refuses unless it can read at least one real
   spooled pass with a tz-aware, parseable `pass_ts`; the minted `baseline_started_at` is always
   "now" — strictly after both the earliest and latest observed pass, so the very first API read
   afterward already has verifiable coverage (`baseline_coverage_verified`). `--dry-run` is the
   default; `--write` is required to actually mint.
3. **E2E commissioning chain test** — `tests/test_prophet_lab_commissioning.py` proves the whole
   chain end to end with fixtures: a pass spooled BEFORE the baseline stays `retrospective_seed`
   forever; a genuinely new event first spooled AFTER the baseline mint classifies
   `live_forward`; a CLI run with no spooled pass refuses; a naive timestamp anywhere is rejected;
   R2-vs-local backend disclosure and an R2 credential-failure both surface as named health
   states.

## Ordered operator sequence for step 3 (Radar live commissioning)

Perform these ON THE VPS, in order, only after BOTH this PR and `#5929` (R-LAB-1) are merged and
live (`cd /opt/macro && git log -1 --format=%H` at or past both merge SHAs — the 3-minute pull
already applied it; nothing below needs a deploy of its own). Do not skip ahead — each step's
output is the precondition for the next.

### 1. Verify the slice source

The confirmed-bar G0/C5 lanes only evaluate when `ENTRY_RADAR_SLICE_DIR` points at a real Terminal
slice tree; absent, they publish honestly `unavailable` (never a silent zero). Confirm the mount
before touching anything else:

```bash
echo "$ENTRY_RADAR_SLICE_DIR"                      # must be non-empty
ls "$ENTRY_RADAR_SLICE_DIR" | head                 # must list per-ticker slice files
```

If empty or absent: **stop here.** The deployment boundary in LAB-0 §6 names the likely path
(`/opt/terminal/terminal/public/data`) as UNVERIFIED until checked live — verify it against the
actual Terminal deploy on this host before proceeding; do not guess a path into
`ENTRY_RADAR_SLICE_DIR` and continue.

### 2. Build the pack with Radar still disabled

Build (or dry-run) the nightly/pre-open pack WITHOUT arming the live 5-min evaluator —
`ENTRY_RADAR_LIVE_ENABLE` stays unset for this step, so nothing goes live yet, only the pack
artifact + inversion proof are produced for inspection:

```bash
python3 scripts/entry_radar_live_pack.py --dry-run --verbose
# once satisfied, drop --dry-run to actually publish the pack + run the proof battery:
python3 scripts/entry_radar_live_pack.py --verbose
```

Confirm the proof passed and the pack is current:

```bash
cat /var/lib/macro-live/state/entry_radar/pack/current/entry_radar_inversion_proof.json | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print('pass:', d.get('pass'), 'cases:', d.get('n_cases'))"
```

`"pass": true` is required before continuing. A `false` here means: fix the underlying threshold-
inversion issue first (Radar-owned, `engine/entry_radar/live_pack.py` — outside this PR's scope)
— do not proceed to arming with a failed proof.

### 3. Inspect confirmed state (still pre-arm)

With the pack built, confirm the confirmed-bar lanes actually see data (not just "the pack built
without error"):

```bash
python3 -c "
import json
pack = json.load(open('/var/lib/macro-live/state/entry_radar/pack/current/pack.json'))
health = pack.get('health', {})
print('dark.no_substrate:', health.get('dark', {}).get('no_substrate'))
print('inputs.quotes.coverage:', health.get('inputs', {}).get('quotes', {}).get('coverage'))
"
```

A high `no_substrate` count alongside low `coverage` means the slice/substrate mount from step 1
is not actually feeding real data — go back to step 1, do not arm on top of a quiet-but-broken
state (see `research/live_entry_radar/W4_DEPLOY_PLAN.md`'s "quiet backstop and a broken checkout
look the same" note — the same failure mode applies here, pre-arm).

### 4. Arm W4 (the operator's own act — first real live pass)

Only once steps 1-3 are clean:

```bash
# on the VPS:
echo 'ENTRY_RADAR_LIVE_ENABLE=1' >> /etc/macro-live.env
# then run one deploy pass (the self-arming block in app/deploy/update.sh
# installs + enables both systemd timers, or invoke update.sh once by hand)
```

Wait for the FIRST real pass to complete and spool. Verify a spool object actually landed:

```bash
systemctl list-timers | grep entry-radar     # both timers scheduled
# after the next 5-min window:
ls /var/lib/macro-live/state/entry_radar/spool/live_flow/entry_radar_events/$(date -u +%F)/ 2>/dev/null
# (or, if R2 is the configured backend, list the same prefix in the R2 bucket instead)
```

**Do not proceed to step 5 until at least one real object is confirmed spooled.** This is the
precondition `scripts/prophet_lab_baseline.py` itself also enforces (it refuses without one), but
confirming it here first avoids a wasted round-trip.

### 5. Mint the baseline — AFTER the first real pass, never before

Run this ON THE VPS, in a shell that has actually loaded the live environment file — the CLI
resolves R2 credentials and the local-fallback spool dir from `os.environ`, same as the API
process, and a bare shell will not have them:

```bash
set -a; . /etc/macro-live.env; set +a
```

Then:

```bash
# dry run first — always:
python3 scripts/prophet_lab_baseline.py \
  --baseline-path /var/lib/macro-live/state/prophet_lab/observation_baseline.json
# read the report: backend resolved, envelopes read, earliest/latest observed pass_ts.
# only once it looks right:
python3 scripts/prophet_lab_baseline.py \
  --baseline-path /var/lib/macro-live/state/prophet_lab/observation_baseline.json --write
```

If R2 is the production backend (credentials already in the loaded environment), no `--spool-dir`
override is needed — the CLI resolves the identical R2-first ladder the API uses. If the local
spool dir differs from `$ENTRY_RADAR_SPOOL_DIR`/`$PROPHET_LAB_RADAR_SPOOL_DIR`, pass `--spool-dir`
explicitly.

**Read the printed `backend resolved:` line before trusting the report.** If production is
supposed to run on R2 and this CLI reports `backend resolved: local`, that is a WRONG-SOURCE
signal, not a quiet fallback to celebrate — it means the environment file above was not actually
loaded (credentials absent from this shell) or R2 itself failed (check for a printed `error:`
alongside the backend line). Minting against the wrong backend can still "succeed" mechanically
(the CLI only checks that SOME real pass is readable, not that it is the RIGHT spool) while
silently baselining off stale or unrelated local data. Confirm `backend resolved: r2` before
`--write` whenever R2 is the intended production transport.

Also required alongside `--write` and `--as-of` together: `--i-know-this-is-rehearsal`
(production commissioning never uses `--as-of` — this flag exists to keep a copy-pasted rehearsal
command from silently minting a fake timestamp in production). And if
`/var/lib/macro-live/state/prophet_lab/observation_baseline.json` already holds a valid marker
from a prior attempt, `--write` alone refuses — pass `--remint` only when deliberately re-minting
(this resets every event observed since the original baseline back to `retrospective_seed`, so
confirm that is actually intended before adding it).

Set the API process's own environment (so `GET /api/prophet/lab/v1` reads the same marker):

```bash
# in /etc/macro-live.env or the macro-api service env:
PROPHET_LAB_OBSERVATION_BASELINE_PATH=/var/lib/macro-live/state/prophet_lab/observation_baseline.json
```

then restart/redeploy the API process so it picks up the new env var (the standard `update.sh`
restart-trigger path already covers `engine/prophet_lab/.*\.py`; an env-var-only change still
needs a process restart to take effect since env vars are read at request time via `os.environ`,
not re-read from a file).

### 6. Verify cycles

```bash
curl -s -H "Authorization: Bearer <a site-full operator token>" \
  https://<host>/api/prophet/lab/v1 | python3 -m json.tool | head -40
```

Check, in order:

1. `health.radar_spool_source` — `"r2"` or `"local"`, never `"unconfigured"`, and no
   `health.radar_spool_error` key present.
   - When the backend is `"r2"`, also check `health.radar_spool_bucket` and
     `health.radar_spool_prefix_queried` against the writer's own R2 config — a LIST that
     succeeds with ZERO keys reads identically to "no passes yet" whether the Lab is pointed at
     the right bucket/prefix or the wrong one; these two fields are the only way to tell without
     reaching for the writer's own config directly.
2. `health.observation_baseline_present` — `true`.
3. `generation.baseline_coverage_verified` — `true`. If `false` here, the marker was minted
   before the spool actually held evidence reaching back that far (a coverage gap — retention,
   compaction, or the marker minted too early) — re-run step 5 after confirming fresh spool
   evidence, never hand-edit the marker to "fix" this. Note this can also happen if a prior
   read hit an R2 error and fell back to local (review B3): `health.radar_spool_error` set
   alongside `radar_spool_source: "local"` means coverage is FORCED unverified regardless of
   what the local fallback data alone would say — resolve the underlying R2 error first.
4. Watch `lab-g0-v1` (or whichever board fires first) across two or three real 5-min cycles: a
   ticker whose first observation postdates the baseline should show
   `observation_class: "live_forward"`; anything observed before the baseline mint stays
   `"retrospective_seed"` — this is the expected, correct behavior, not a bug.

**Non-completion reminder (LAB-0 §0 binding rule):** completing this sequence contributes evidence
toward B6 (Radar observation-only activation with full-RTH-session proof) but does **not** close
it on its own — B6 remains its own wave with its own cadence-proof gate (§15 PR-4,
`research/live_entry_radar/W4_DEPLOY_PLAN.md` step 3's cadence line).

## Why the ordering is load-bearing (not just tidy)

Minting the baseline before step 4's first real pass is the exact failure mode this PR's build
pieces exist to prevent: `engine.prophet_lab.sources.baseline_coverage_verified` fails CLOSED when
the spool's earliest surviving envelope postdates `baseline_started_at` — a baseline minted with
nothing behind it degrades every board to `retrospective_seed` **forever**, with no error anywhere
to say so, because "coverage not verified" and "genuinely nothing observed yet" read identically
from the health block alone. `scripts/prophet_lab_baseline.py` REFUSES to mint without reading at
least one real pass specifically to make this mistake unavailable to the operator, not just
discouraged in prose — but the CLI can only refuse on what it can see; running it against the
wrong (empty, stale, or misconfigured) spool root would not catch a *coverage gap* the same way
it catches *total absence*, which is why step 3's confirmed-state inspection and step 4's spool-
object confirmation both come first.

## Open dependency

Everything above assumes `#5929` (R-LAB-1) has merged: it is the sibling PR that fixes the
confirmed-lane transport correctness (`live_pack.probe_set["nightly_lanes"]` vs the unpopulated
admission-summary field) and the `entry_radar.events/v1` envelope shape this Lab reader consumes.
This PR's R2-first transport reads whatever `entry_radar.events/v1` envelopes are actually
spooled regardless of that fix's status — the transport layer built here is independent of R-LAB-1
— but the CONTENT correctness of what shows up on the confirmed lanes is not, per LAB-0 §6's own
wave ordering (R-LAB-1 and P-LAB-API run in parallel; commissioning is explicitly sequenced
AFTER both).

## Known CI gap this program should not be surprised by later (Ruling-4)

`tests/test_entry_radar_w1.py::test_branch_diff_touches_no_protected_path` (a `WS:LIVE-ENTRY-RADAR`
non-interference guard, §16) reds on any PR that touches BOTH an `engine/entry_radar/` path and an
`engine/prophet_`-prefixed path in the same diff — its `PROTECTED_PATHS` tuple uses the literal
prefix `"engine/prophet_"`, which pattern-matches `engine/prophet_lab/` even though LAB-0 §1 is
explicit that the Lab carries **zero** ranking/gating/signal-origination authority and is
therefore not the kind of "Prophet gate code" (`entry_signal.py`, `signal_gate.py`,
`confluence_tiers.py`, etc.) this guard exists to protect. This PR's own diff (touching
`engine/entry_radar/spool.py`'s read-side seam alongside `engine/prophet_lab/{response,sources}.py`)
trips it. **The guard currently lives in a `gate: data` job**, which — before this PR's B1 fix —
never ran inside a PR's own merge gate at all (`ci.yml` only invokes `run_ci_pack.py --gate code`;
`gate: data` jobs run exclusively on the nightly `data-health.yml` lane, post-merge), so this
finding was silent rather than blocking. **It stays unfixed here deliberately**: narrowing
`PROTECTED_PATHS` to exclude `engine/prophet_lab/` specifically is a judgment call about a
Radar-owned non-interference boundary, outside a commissioning-prep packet's authority to make
unilaterally — flagged for `WS:LIVE-ENTRY-RADAR` / the next wave that touches this guard to
adjudicate (either narrow the prefix, or rule that the Lab's own read-side imports from
`engine/entry_radar/` need a different mechanism than a shared-root package). **Recording this now
so a future W2-of-the-data-health-lane session does not rediscover it as a surprise**: once
`gate: data` jobs start running inside a PR's OWN merge gate (rather than only post-merge), this
exact guard will start blocking every future PR that legitimately needs to import
`engine.entry_radar.spool` from `engine/prophet_lab/**` — the prefix should be narrowed BEFORE
that happens, not reactively after the first red.
