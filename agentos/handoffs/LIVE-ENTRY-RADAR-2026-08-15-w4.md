---
workstream: WS:LIVE-ENTRY-RADAR
session: live-entry-radar-w4-0f5eea
model: fable
ended_because: complete

mission: >
  W4 / PR-4: the VPS-primary 5-minute RTH live evaluator on the frozen G0/C1–C5
  substrate — bounded live cycle (Probe Set → inputs → basis audit → readings →
  episode transitions → spool → health receipt), nightly frozen-substrate pack
  with solved threshold receipts + the commission-amendment inversion PROOF
  battery, §10 re-arm wiring through exported rearm_eligible, liveness, kill
  switch, deploy units staged behind an operator arm flag. No W5 writer, no
  outcome reads, Prophet byte-identical. STOP after W4.

state_before: >
  W3 DONE at #5724 (4b9706ef) with records reconciled in #5726; detector spec
  hashes published (C1 f0bbd6cf3a6e2339 · C2 d8ba60a25cfa7400 · C3
  d54dc1e55c4261c8 · C4 dce21ac680233ee2 · C5 13dec66345a0376c · G0
  9be89a8acc8b905c); F1 refusing. W4 commissioned fresh (CEO handoff
  2026-08-15 + same-day amendment: consume final W3 return state; inversion
  proof packs in W4 scope; re-arm explicit; basis audit before the engine;
  W5 authorized as a separately-owned PARALLEL lane behind a hard firewall).
  During this session W5's code landed on main (engine/entry_radar/replay/**,
  scripts/{reconcile_entry_radar,entry_radar_vendor,entry_radar_replay,
  entry_radar_stage_terminal}.py) — reconciled by merge, zero engine-file
  collisions; W5's own records remain that session's to write.

changed:
  - path: engine/entry_radar/live_pack.py (new)
    what: "Frozen-substrate nightly pack: per-name confirmed OHLC substrate
      freeze; solved C1/C2a threshold receipts by oracle bisection with the
      four explicit degeneracies (§7.1 hardening 1) and condition_at_boundary /
      bracket_verdict; basis_audit helper (0.25% prophet-live derivation);
      pack_hash over firing-relevant content; JSON pointer + atomic dir
      persistence + 3-pack retention; the commission-amendment inversion PROOF
      battery (threshold boundaries both directions, state micro-paths through
      unmodified run_c1/c2/c3, re-arm/c2f/C3-turn/basis boundaries) — any
      failure ⇒ pack proof_failed ⇒ the RTH evaluator refuses the cycle."
  - path: engine/entry_radar/live_ledger.py (new)
    what: "Runtime episode ledger in the §13 mastermind.live_entry_episode.v1
      shape (+variant, scores structurally None): apply_run diff/dedup (stale
      terminal traces → superseded, never re-admitted), spool_then_commit —
      commit is impossible without a spool receipt; §10 clock overlay
      (CANDIDATE→RESOLVED at H=10 by session arithmetic only — no price in the
      stamping path), re-arm bookkeeping through challengers.rearm_eligible
      (measurement per (ticker,detector), firing-unit per variant, idempotent
      suppression records), terminal-mutation refusal, compaction that archives
      and never deletes (P-10)."
  - path: engine/entry_radar/live_eval.py + vendor_minutes.py + scripts/entry_radar_live.py + scripts/entry_radar_live_pack.py (new)
    what: "The 5-min pass: kill switch → session window → stale-pack/proof
      gates (whole-cycle refusal, zero transitions, zero spool) → per-name
      quote gates (carried/premarket/aged quotes excluded) → raw-quote basis
      audit BEFORE the engine (mismatch ⇒ dark + null readings + receipt) →
      journal-backed incremental observations (pack_hash-pinned, byte-parity
      pinned against W3 build_observation_path) → unmodified run_c1/run_c2/
      run_c3/c4_snapshot → ledger diff → spool-first → payload + enumerated
      health receipt (live/degraded/stale_pack/proof_failed/out_of_window/
      killed/failed) with cadence gap detection and null-reading honesty.
      vendor_minutes: bounded episode-windowed minute-agg reader (IntradayReader
      impl) with substrate-fingerprint-stamped bucket cache. G0/C5 nightly lanes
      wired behind ENTRY_RADAR_SLICE_DIR (unset ⇒ honest unavailable —
      no Terminal slice store exists in production yet)."
  - path: app/deploy/macro-{live-entry-radar,entry-radar-pack}.{service,timer} + update.sh block + .github/workflows/entry-radar-live.yml + freshness_sentinel SURFACES entry + hot_tape tap
    what: "Deploy staged NOT armed: update.sh self-arming block additionally
      gated on ENTRY_RADAR_LIVE_ENABLE=1 in /etc/macro-live.env (symmetric
      disarm); workflow backstop double-gated (ENTRY_RADAR_LIVE_DISABLED +
      VPS_LIVE_PRIMARY) and schedule-dormant while the VPS is primary;
      sentinel surface entry_radar_live (live_file, absent_ok) = the mandated
      positive liveness registration; the W1-designated 2-line hot_tape
      nomination tap (demo/dry-run gated). Caddy untouched — entry_radar.json
      inherits the auth gate by omission."
  - path: tests/test_entry_radar_w4_{pack,ledger,live,pit,liveness,c3_reader,lane}.py + .github/ci/legacy-jobs.yml
    what: "The hostile battery (design §5 PIT-W4-1..20 + named test_W4R_*
      regressions from the adversarial round), wired into the entry-radar CI
      step. Every load-bearing guard carries a mutation control."
  - path: research/live_entry_radar/{W4_LIVE_EVALUATOR_DESIGN,W4_DEPLOY_PLAN,W4_REAL_DATA_SMOKE,W4_REVIEW_DISPOSITIONS}.md
    what: "Binding design (§7.1 operationalization recorded as a mechanism
      receipt under the A5.0 correction discipline — no detector-meaning
      change); operator activation plan (arm flag, verification checklist, §15
      full-RTH-measurement close-out owned by activation); real-data receipts
      (pack+proof on real store shapes; the vendor minute smoke that closes
      W3's unverified row — 4H grid/basis/freshness verified on real
      aggregates, 0.3–2.7 bp basis agreement); adversarial dispositions."

prs: [PENDING_AT_WRITE — filled at merge]

verified:
  - claim: "Full entry-radar CI line green (W1–W5 union post-merge, 22 suites)."
    command: "python3 -m pytest <the legacy-jobs entry-radar step's 22 files> -q"
    result: "1370 passed, 2 skipped (W4's own seven suites: 480; 67 named test_W4R_* adversarial regressions)"
  - claim: "Prophet firewall byte-clean."
    command: "git diff --stat origin/main..HEAD -- engine/entry_signal.py engine/signal_gate.py engine/confluence_tiers.py engine/signal_quality.py 'engine/prophet_*.py' engine/washout_turn.py engine/mtf_upturn.py engine/technicals.py"
    result: "empty"
  - claim: "Frozen identities untouched; F1 refuses."
    command: "get_spec × 6 + registry-vs-implementation assert"
    result: "all six hashes match the published literals"
  - claim: "Real-vendor bounded smoke receipted (basis/session/timestamps/freshness)."
    command: "research/live_entry_radar/W4_REAL_DATA_SMOKE.md"
    result: "pack+proof 47/47 on real shapes; 4H grid exact on real minutes; basis gap 0.32–2.66 bp; W3 unverified row CLOSED"

unresolved:
  - "vendor_minutes treats a reader returning zero rows for a session as a
    missing session (fail-closed into c3_incomplete_window) — conflating
    fetch-fault with fetched-and-empty. Reachable only via synthetic readers
    today (real vendor sessions return rows); documented in the dispositions,
    refusal direction is the safe one."
  - "W5's workstream row/handoff were still unwritten on main when this session
    ended — their code merged mid-session (replay/**, reconciler, vendor,
    stage-terminal scripts) and this PR's merge reconciled the shared files
    (producers guard union, one W1..W5 CI step, sentinel SURFACES union,
    update.sh sibling blocks). Their records are theirs to write."

unverified:
  - claim: "5-min cadence across a full RTH session (§15 PR-4 gate line)."
    what_would_verify: "Operator activation per W4_DEPLOY_PLAN.md (arm flag) +
      reading health.pass.prev_gap_intervals at 16:00 ET — activation is
      operator authority by commissioning; the deploy plan owns the close-out."
  - claim: "G0/C5 lanes against a production Terminal slice store."
    what_would_verify: "A slice store landing on the VPS (none exists anywhere
      in production today — census receipt in the design §3b); the lanes
      publish honest unavailable until then."

next_actions:
  - "Operator: arm per W4_DEPLOY_PLAN.md when ready (ENTRY_RADAR_LIVE_ENABLE=1
    + one deploy pass), then close the §15 full-RTH measurement line."
  - "W5's session owns its own records (code merged during this session;
    workstream row/handoff still todo on their side)."
  - "Follow-ups chipped, not owed: snapshot-lane coverage union with the probe
    set; pack-build parallelization if the pre-open window ever tightens;
    intraday (sub-session) external watchdog beyond the session-grain sentinel
    surface; W5↔W4 vendor-reader consolidation candidate
    (vendor_minutes vs entry_radar_vendor — two lawful lanes today)."

do_not_redo:
  - "Do not re-run the W4 adversarial round — findings C1..C3, H1..H4, M1..M10,
    LOW batch adjudicated/fixed/regression-pinned; receipts in
    research/live_entry_radar/W4_REVIEW_DISPOSITIONS.md."
  - "Do not 'optimize' the journal-backed incremental observation path back to
    an in-memory memo — the lane is a oneshot process per pass; the journal IS
    the memo (M1 ruling)."
  - "Do not treat pack `never_true` C1 thresholds as defects — K=SMA(3) floors
    at (rawk₋₁+rawk₋₂)/3; high-K names lawfully cannot arm in one tick
    (real-data receipts in W4_REAL_DATA_SMOKE.md)."
  - "Do not strip the whole-cycle stale-pack/proof_failed refusals down to
    per-name handling — §5's stale-pack row is a fabrication risk, not a
    freshness nicety."

danger_areas:
  - "The W4/W5 firewall is now two-sided IN TREE: live lane writes runtime
    state + R2 spool only; W5's reconcile_entry_radar.py is the sole durable
    writer. Neither imports the other (guard-tested my side). Keep it so."
  - "The bucket cache is only lawful because it is fingerprint-stamped —
    adjusted aggregates are NOT immutable across corporate actions (H4). Any
    new cache must carry the same vintage stamp."
  - "update.sh's entry-radar block is ARM-GATED — copying the block pattern
    without the gate silently activates a production lane on the next pull."
---
