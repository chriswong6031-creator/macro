---
workstream: WS:PROPHET-US-V4-RECOVERY
session: prophet-lab-r4-migration-day3
model: fable
ended_because: blocked

mission: >
  Sol Day-3 directive: prove the current G-D gate on the post-heal artifact,
  commission Radar live against the canonical production source, then ship
  P-MP1-SHELL through production proof — or isolate root causes, repair
  bounded pieces, leave no fake-green, and hand back the exact continuation.
  Outcome: BLOCKED path, honestly — Gate A PASSED with an audit-grade receipt;
  Gate B is BLOCKED on one 2-minute operator action (staged, specified);
  the shell's central act is BLOCKED on one Sol ruling (W-L1 collision);
  every bounded repair that could ship, shipped (#6049 prep, #6053, #6055).

state_before: >
  Day-2 end: Lab backend + API merged and live; R5.3 approved; C8 train done
  through #6011; day-2 handoff carried three statements Sol's directive
  invalidated (wait-for-nightly, HK fixture-drift diagnosis, shell->UI->
  commissioning order). Radar believed "software commissionable, W4 unarmed".
changed:
  - {path: "agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md", what: "b5a DAY-3 STATE: sequence corrected to frozen LAB-0 §6 order; G-D PASS receipt; Gate B blocker set; shell prep/OWED split"}
  - {path: "agentos/workstreams/WS-LIVE-ENTRY-RADAR.md", what: "W4.1 day-3 commissioning-attempt record: already-armed-since-08-18 finding, 215-pass refusal histogram, B2-B5 blockers, staged repairs, residual risks"}
  - {path: "research/migration_packets/MP-1-prophet-board.md", what: "G-D-1 day-3 PASS receipt + BINDING READING ADJUDICATED (Reading A) + decisive_receipt commit-label erratum; §13 W-L1 collision row OPEN routed to Sol (no disposition minted)"}
  - {path: "agentos/discoveries/DSC-ARMED-LANE-WITH-NO-SPOOL-DESTINATION-READS-HEALTHY.md", what: "minted: same-host env split-brain class + armed-is-not-producing + credential-free drop-in repair idiom"}
  - {path: "scripts/build_site.py", what: "MERGED #6049 (1ccf7fe8bdba) prep: us_stance_projection (§8a, unwired), pv_card parameter (non-US byte-parity test-proven), groundwork count plumbing, suites wired into engine-render-guards"}
  - {path: "templates/theme.css", what: "MERGED #6055 (d78121d6459c): .skel + .mx-error ported verbatim from the specimen, additive-only (171+/0-), drift-guarded, zero consumers — discharges MP-1 V-B4's primitive gap"}
  - {path: "tests/test_prophet_card_shared.py", what: "MERGED #6053: zh-rebind test re-pinned to C8-C's structural flip (was the one main red, unrun-picks-boards gate:data)"}
verified:
  - {claim: "G-D PASS at the exact artifact Sol observed: frozen Reading A 237/237=100.0000% (blocked_data 0), gross Reading B 237/262=90.46%, all readings >=90%; #5980 signatures absent at zero", command: "git cat-file blob 251b935155d8bd584347d7c924f9cb7acd945851 | python3 <Lane-A script in the receipt>  # blob verified == origin/main tip and == publication 0b0c296f85f3"}
  - {claim: "W4 armed since 08-18 yet zero envelopes ever spooled; 160 in-window passes refused no_pack; canonical events prefix empty while sibling nominations prefix holds 195 keys", command: "VPS journalctl histogram + R2 LIST receipts in /var/lib/macro-live/state/prophet_lab/commissioning_receipt_2026-08-20.json"}
  - {claim: "baseline CLI refuses on zero spooled passes (fail-closed, verbatim refusal preserved); replay/idempotence PASS (identical digest twice); API health serves r2/mastermindx/live_flow/entry_radar_events under its own env", command: "commissioning receipt items 4/11/13"}
  - {claim: "the five test_hk_board_ui reds were a sparse-CI-checkout artifact, not fixture drift", command: "gh pr view 6029 --json state,mergedAt  # MERGED 2026-08-20T02:57Z; day-2 diagnosis STRUCK, chip dismissed"}
  - {claim: "#6049/#6053/#6055 merged with own runs clean (only the by-design merge-queue-pilot X)", command: "gh pr view <n> --json state,mergeCommit"}
unresolved:
  - "GATE B OPERATOR ACTION (the one lever, ~2 min, then commissioning completes during RTH): on the VPS as root — (1) write /etc/systemd/system/macro-live-entry-radar.service.d/lab-commissioning.conf with [Service] EnvironmentFile=/etc/macro-api.env; systemctl daemon-reload; (2) append ENTRY_RADAR_SLICE_DIR=/opt/terminal/terminal/public/data to /etc/macro-live.env; (3) append PROPHET_LAB_OBSERVATION_BASELINE_PATH=/var/lib/macro-live/state/prophet_lab/observation_baseline.json to /etc/macro-api.env; systemctl restart macro-api.service; (4) with the env loaded, publish the pack (scripts/entry_radar_live_pack.py --verbose, no --dry-run) OR let the 10:20:35Z timer do it — watch its exit vs MemoryMax=512M (observed unconstrained build RSS ~857MB); THEN after the FIRST real in-window envelope (earliest 13:29Z, only on a real transition — empty deltas spool nothing): mint the baseline per the runbook (dry-run, then --write), and verify 2-3 cycles classify live_forward"
  - "Remote-route same-source proof (Sol item 11 residual): needs a site-full operator bearer token; server-side reader proof already done under the API's exact env"
  - "SHELL CENTRAL ACT: awaits the Sol ruling on the MP-1 §13 W-L1 collision row (options a/b/c recorded there); after the ruling, one bounded shell PR executes the central act + §8b hunks + §11 evidence, with the mandatory independent §8b review"
  - "Sol's veto window on the b1 stance ruling remains open (G-D-1 reverts if vetoed)"
unverified:
  - "Whether the 10:20:35Z pack-service run survives its 512M MemoryMax (the discriminating experiment; a read-only check of its exit status answers it)"
  - "Edge-served /prophet/index.json bytes for a signed-in user (regwalled 401 unauthenticated — by design; the git blob is canonical for the gate)"
next_actions:
  - "Operator: apply the four staged repairs (unresolved item 1), then re-commission the Gate B finish (baseline + live_forward cycles) — the runbook and receipts name every step"
  - "Sol: rule the W-L1 transition (MP-1 §13 Day-3 row); then commission the bounded shell central-act PR (stocks-mode only, §8b independent review, §11 evidence, browser matrix per directive §8)"
  - "Then P-LAB-UI (LAB0 §6.5) — NOT started, per directive §9"
do_not_redo:
  - "Do NOT re-measure G-D before acting on this receipt unless a newer nightly has published (Amendment 2 discipline) — and never under an unstated reading: Reading A is the adjudicated binding one"
  - "Do NOT mint the Radar baseline before the first real spooled pass lands (the CLI refuses; overriding it would seed retrospective_seed-forever)"
  - "Do NOT set ENTRY_RADAR_SPOOL_DIR (a local dir re-creates the split-brain B3); the drop-in IS the repair"
  - "Do NOT hand the pack unit macro-api.env without a separate adjudication (it would activate the supabase:watchlist producer — a probe-set behavior change)"
  - "Do NOT re-diagnose the five HK-board tests (sparse-checkout artifact, #6029) or the zh-rebind test (#6053)"
  - "Day-1/2 do_not_redo stand (LAB-0 semantics, six boards, VMRK alias rejection, R5.3 approval, C8 rulings)"
danger_areas:
  - "The harness permission boundary denies remote production config mutation (scp/ssh to /etc/**) from ANY lane including the main loop — do not route around it; it makes such repairs operator acts by construction"
  - "The shared local git store on the Studio was degraded this session (uninterruptible-I/O hangs; primary checkout missing the WorktreeCreate sparse hook → every isolation:worktree spawn failed; chip task_7cb63060 filed) — the workaround was a fresh GitHub clone in the session scratchpad; check store health before git-heavy work"
  - "An in-window Radar pass with an empty delta spools NOTHING — first-envelope timing after the repair depends on real transitions, not on the clock"
  - "gh quota: batch PR lookups into one GraphQL call; 150s+ poll cadence; metadata edits only after checks conclude (a live-run edit cancels the push authority run)"
---

# Handoff — Prophet Operator Lab (V4-B5A) day 3 · 2026-08-20

Sol's three stale-item corrections are executed in this handoff's records:
the day-2 "wait for tonight's nightly" is CLOSED (measured the current
artifact — PASS), the HK fixture-drift diagnosis is STRUCK (#6029: sparse
checkout), and the wave order is corrected to the frozen LAB-0 §6 sequence
(commissioning BEFORE shell-merge, UI last). Gate A passed with an
audit-grade receipt and a binding-reading adjudication; Gate B produced the
program's most consequential finding — W4 has been armed and silently
withholding since 08-18 because the writer had no spool destination — with
the repair staged down to file paths and the one operator lever named.
The shell banked its safe preparation and halted its central act on a real,
newly-discovered cross-program collision now recorded and routed to Sol.
