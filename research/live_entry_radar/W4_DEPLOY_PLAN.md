# W4 Live Entry Radar — operator activation plan (deploy-ready, exact-SHA)

**Status:** STAGED, NOT ARMED. Everything in this plan ships in the W4 merge; nothing activates
until the operator performs step 2. This honors the W4 deployment boundary (build + validate,
no autonomous production service state) while keeping the house "go-live is a repo commit"
shape: the commit is already live on the VPS via the 3-minute pull — only the arm flag is the
operator's act.

**Exact SHA:** the W4 squash-merge commit on `main` (recorded in the Agent OS handoff at merge;
every artifact the lane writes carries `pack_hash` + spec-hash provenance, so the running code
version is auditable from any payload).

## What ships (dormant until armed)

| Piece | State at merge |
|---|---|
| `app/deploy/macro-entry-radar-pack.{service,timer}` | staged in repo; `update.sh` self-arming block installs+enables ONLY when armed |
| `app/deploy/macro-live-entry-radar.{service,timer}` | same |
| `update.sh` entry-radar block | runs on every deploy; logs `entry-radar: staged, not armed` and exits unless armed |
| `.github/workflows/entry-radar-live.yml` backstop | schedule self-disabled while `vars.VPS_LIVE_PRIMARY == 'true'`; `workflow_dispatch` available for rollback ops |
| `freshness_sentinel` SURFACES entry | active immediately; `absent_ok: true` means a not-yet-armed lane never pages |
| Caddy | zero changes — `live/entry_radar.json` inherits the auth gate by omission |

## Operator activation (one step + verification)

1. Confirm the W4 merge SHA is live on the VPS: `cd /opt/macro && git log -1 --format=%H` ≥ the merge SHA.
2. **Arm:** add `ENTRY_RADAR_LIVE_ENABLE=1` to `/etc/macro-live.env` on the VPS, then run one deploy
   pass (`app/deploy/update.sh` runs on the next pull automatically; or invoke it once by hand).
   The self-arming block then `systemd-analyze verify`s and installs+enables both timers.
3. Verify, same day:
   - `systemctl list-timers | grep entry-radar` → both timers scheduled.
   - After the next pack window: `/var/lib/macro-live/state/entry_radar/pack/current` exists;
     `entry_radar_inversion_proof.json` shows `"pass": true` with the case count.
   - Next RTH session: `live/entry_radar.json` advancing every 5 min (`health.state: "live"`,
     `pass.seq` incrementing, `content.ledger_hash` moving on transitions); spool objects under
     `live_flow/entry_radar_events/<session>/` on passes with transitions.
   - **§15 PR-4 gate close-out:** "5-min cadence measured across a full RTH session" — read
     `health.pass.prev_gap_intervals` at 16:00 ET (0 gaps = measured clean) and record it in the
     workstream. This is the one acceptance line that structurally requires activation; it
     completes here, owned by this step.
4. Rollback: remove the env line; the next `update.sh` pass disables both timers (block is
   symmetric); `ENTRY_RADAR_NO_PUBLISH=1` in the service env is the softer no-writes rehearsal
   switch; the kill-file (`/var/lib/macro-live/state/entry_radar/KILL`) stops evaluation while
   keeping the payload honest (`health.state: "killed"`).

### What the GitHub backstop can and cannot tell you

The backstop lane is a **rollback path, not a second opinion**, and reading its payload as if it
were the VPS's will mislead. Three properties, all structural:

- **Its state plane is COLD every run.** `ENTRY_RADAR_STATE_DIR` points at `$RUNNER_TEMP`, wiped
  with the job. So there is no journal to replay, no ledger history, and no warm 4H bucket cache:
  the pass sees only what it can derive from the frozen pack and this cycle's quotes. Two
  consequences to hold in mind — the §10 re-arm history is absent, so a name the VPS would refuse
  `suppressed_by_rearm` can arm here; and every C3 name pays a cold fetch inside the same budget,
  so more names defer. (Before this env was set, the lane resolved *no* state dir at all and every
  run was a `stale_pack` whole-cycle refusal, exit 5 — it could never once have evaluated a name.)
- **A quiet backstop and a broken checkout look the same.** The job's sparse cone carries
  `data/stocks`, the per-name daily parquet substrate the pack builder freezes. That cone is the
  heaviest thing this lane checks out and it is the one entry `prophet-live.yml` does not need.
  If the probe set grows past what the committed store actually holds — a new name added to the
  probe config before its parquet lands, or a cone edit that drops the path — the pack builder
  finds no substrate per name, every name comes back `no_substrate`, and the payload reads as a
  **quiet market rather than a broken checkout**. Check `health.dark.no_substrate` against
  `inputs.quotes.coverage` before believing a flat backstop pass; on the VPS the same shape is a
  real data-store gap and reads the same way.
- **Cadence is not purchasable here.** The crons ask for every 5 minutes; measured on this repo,
  frequent schedules land 90 min–3 h apart. `health.pass.prev_gap_intervals` will therefore be
  large on the backstop by design, and the §15 cadence gate above can only be closed on the VPS.

## Standing safety properties (no operator attention needed)

- Stale pack ⇒ whole-cycle refusal (`stale_pack`), zero transitions, zero spool — never a wrong-session evaluation.
- Failed inversion proof ⇒ the pack is `proof_failed` and the RTH evaluator refuses the cycle.
- Basis mismatch ⇒ per-name dark with the audit receipt on the row; never a spliced tape.
- Spool failure ⇒ transitions withheld (retried next pass); never an unspooled admission.
- The lane writes only: R2 `live_flow/entry_radar_events/**` (PRIVATE_OPERATIONAL), the live dir
  payload, and `/var/lib/macro-live/state/entry_radar/**`. Never `data/`, never git.
