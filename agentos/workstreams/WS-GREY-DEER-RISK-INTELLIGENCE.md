---
key: GREY-DEER-RISK-INTELLIGENCE
title: Grey Deer Risk Intelligence & Capital Protection System
objective: >
  Separate slow measured market state, transition hazard and capital policy;
  publish one canonical risk envelope across Macro, Prophet, Terminal and
  Mastermind Portfolio; and allow only individually promoted or explicitly
  temporary, scope-bounded, counterfactual-preserving protection rules to affect
  actionability. Done means a real market event reaches real production users and
  authorized machine consumers with PIT clocks, correction receipts and learning.
status: active
program: market-regime-risk
repos: [macro, terminal, mastermind]
owner: coo-fable
class: build
blast_radius: user_facing
ambiguity: scoped
owns_paths:
  - research/grey_deer/
  - engine/risk_envelope.py
  - scripts/build_risk_envelope.py
  - scripts/build_live_risk_envelope.py
  - site/riskdata/risk_envelope.json
  - site/live/risk_envelope.json
  - templates/risk_envelope/
  - tests/test_risk_envelope
  - agentos/handoffs/GREY-DEER-
discoveries:
  - DSC:GD1-LC-EMISSION-LOG-STARTS-BROKEN
  - DSC:GD1-EWY-IS-NOT-KOSPI-CASH
  - DSC:GD1C-PIT-MEMBERSHIP-PREHISTORY-ABSENT
decisions:
  - DEC:RISK-STATE-HAZARD-POLICY-SEPARATION
  - DEC:RISK-ENVELOPE-IS-CANONICAL-DERIVED-PROJECTION
  - DEC:RISK-EPISODES-USE-CHRONICLE-AND-REFLEXES
  - DEC:PROPHET-RANK-PRESERVED-MARKET-ELIGIBILITY-SIDECAR
  - DEC:REPAIR-IS-ORTHOGONAL-AND-FIRST-CLASS
  - DEC:PORTFOLIO-CONSUMES-NOT-RECOMPUTES-MARKET-RISK
  - DEC:SCOPED-REFLEX-CONSTRAINTS-NOT-FUSED-SHIELD
  - DEC:AUTO-EXIT-NOT-IN-GREY-DEER-V1
artifacts:
  - research/grey_deer/GREY_DEER_RISK_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-19.md
  - research/grey_deer/GREY_DEER_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md
  - research/grey_deer/GREY_DEER_WAVE_GRAPH_AND_PR_ACCEPTANCE_MATRIX_2026-08-19.md
  - research/grey_deer/GD1_GROK_SCIENTIFIC_REPLAY_HANDOFF_2026-08-19.md
landmines:
  - "Collision fence (Sol ruling 2026-08-19): #5925 entry_radar live_pack MERGED but its PRODUCTION PROOF is still outstanding — no Grey Deer edits to engine/entry_radar/** until the Radar owner accepts the proof. Fences for #5928/#5929/#5954/#5948 are RESOLVED (all merged) and removed."
  - "The CI control-plane program's operator grant does NOT extend to Grey Deer: never admin-merge a Grey Deer PR over red main on that precedent."
  - "site/riskdata/ sits under market-regime-risk's implementation roots in config/mastermind_programs.yml — Grey Deer owns only risk_envelope.json inside it; raw regime/market-state artifacts stay with market-regime-risk."
  - "Session worktrees are sparse: site/ and data/ writes require scripts/worktree_sparse.py opt-in before any GD-2+ build touches them."
do_not_redo:
  - "No universal fused risk score in scored/authority paths (see DEC:RISK-STATE-HAZARD-POLICY-SEPARATION; legacy engine/risk_state.py is frozen compatibility, not a template)."
  - "No new event store / forward ledger for risk episodes — Chronicle + Reflex Registry + QLedger own durable history (DEC:RISK-EPISODES-USE-CHRONICLE-AND-REFLEXES)."
  - "No Prophet rank/population mutation, ever — actionability sidecar only (DEC:PROPHET-RANK-PRESERVED-MARKET-ELIGIBILITY-SIDECAR)."
  - "No arming Portfolio brain/posture_decider.py as a shortcut; no LLM probability_rolldown in any authoritative consumer."
  - "No automatic held-position exits in v1 (DEC:AUTO-EXIT-NOT-IN-GREY-DEER-V1)."
waves:
  - id: GD-0A
    title: Durable program landing — freeze, workstream, 8 decisions, handoff, registry, system map
    status: done
    pr: 5963
    # MERGED 2026-08-19T12:24:34Z, squash 705a0ceaa157; proof run 32250586821
    # 14/14 green on the refreshed head after the fleet-wide qledger T9 heal
    # (#5970, 2e13b9a51761). Discoverability verified from origin/main
    # (files + registry key + compile-context bundle).
  - id: GD-1A
    title: PIT prereg + source-clock census (Grok; hash-pinned before outcomes)
    status: done
    pr: 5961
    # MERGED 2026-08-19T14:02:46Z, squash 7676a89d370c. Sol acceptance ruling
    # 2026-08-19 closed GD-1A DONE. Prereg-first commit-verified: 663fb02b500c
    # precedes every outcome-bearing dossier commit AND predates the landed
    # freeze (#5963) — it remains GD-1's operative GD-H freeze; GD-H changes
    # under the landed freeze need a new prereg version.
  - id: GD-1B
    title: Existing-organ replay + Prophet counterfactual (Grok)
    status: done
    pr: 5961
    depends_on: [GD-1A]
    # Sol acceptance ruling 2026-08-19: ACCEPTED_NO_PROMOTION — dossier
    # accepted as research; NO construction cleared the preregistered
    # design-era gate (prereg §10), so ZERO GD-5 promotions issue from GD-1.
    # See DEC:GD1-ACCEPTED-NO-PROMOTION.
  - id: GD-1C
    title: leadership_crack.v1 design-era reconstruction + GD-H1/GD-H2 interaction test (research-only prerequisite for GD-5)
    status: done
    pr: 6038
    # CLOSED 2026-08-20: #6038 MERGED (583b5a27f714), verdict
    # DONE / BLOCKED_NO_PROMOTION (Fable-accepted). GD-5A/B/C remain CLOSED.
    # Relayed to the Grok operator 2026-08-19 (Sol: "relay now"; operator
    # carried GROK_GD1C_DESIGN_ERA_RECONSTRUCTION_PACKET_2026-08-19.md into
    # the AionUI session; canonical commission is the in-repo file below).
    depends_on: [GD-1B]
    # Sol-commissioned 2026-08-19; packet:
    # research/grey_deer/commissions/GD-1C_LEADERSHIP_CRACK_DESIGN_ERA_COMMISSION_2026-08-19.md
    # (fresh prereg; already-frozen GD-H1/GD-H2 only; episode-level effective N;
    # current-membership reconstruction labeled def_current_cf; BLOCKED if PIT
    # membership cannot be reconstructed for the primary test; August 2026 may
    # not choose thresholds).
    # Research package completed 2026-08-19 under prereg freeze fce7bfeb8c92:
    # PRIMARY GD-H1=BLOCKED and GD-H2=BLOCKED because PIT cohort membership
    # cannot be reconstructed across 2016-01-04..2026-07-31. The separate
    # def_current_cf lane produced no secondary PASS. ZERO GD-5 promotions.
    # FABLE ACCEPTANCE 2026-08-19 (this PR): verdict DONE / BLOCKED_NO_PROMOTION.
    # Verified: prereg topology (fce7bfeb = first branch commit, prereg only;
    # outcomes first at 722ddaf/9d6acde); PIT blocker real (membership first
    # tracked 2026-06-14, retrospective added-fields rejected, no rate
    # vintages) and not substituted away; def_current_cf labeling throughout;
    # thresholds frozen on <=2026-07-31 rows only; effective-N episode
    # collapse + frozen S12 gates applied (the one adequately-powered cell
    # fails discrimination/Brier/calibration/sign/baseline; the tempting
    # H1 3pct/1s row adjudicated small-N noise under the frozen rule).
    # GD-5A/B/C stay CLOSED. Only lawful continuation (NOT commissioned):
    # recover date-effective first-known cohort membership + first-available
    # nominal-rate vintages, then freeze a NEW prereg version before outcome
    # access, only if Fable judges the recovery worth pursuing.
  - id: GD-2
    title: Settled Risk Envelope + three-answer Macro hero
    status: done
    pr: 6026
    depends_on: [GD-0A]
    # PR #6026 MERGED 2026-08-19T23:15:52Z (e6a3fcd6e094) on a fully green
    # full-manifest re-run; Fable design review PASS. Sol post-merge review
    # 2026-08-19: Gate 8 (production acceptance) BLOCKED until GD-2R1.
    # GATE 8 PASSED 2026-08-20 (Fable, owning session): first production
    # publish of the repaired band = fae690766555 (dashboard-bot regime-update
    # lane 09:33:43Z, descendant of GD-2R1 merge e23fdcdceae3; the 07:27Z
    # scope=all render predates the merge and the 08:46Z render-public restamp
    # rebuilds no bodies). Live https://www.mastermind-x.com/macro.html
    # byte-identical to origin/main site/macro.html (sha256 4d90cb2c88c6);
    # DOM bundle fd9ccdbe47f7f008 binds page to the committed artifact whose
    # bytes prove stage FRAGILE, stage_since null, coherence
    # {scope: market_reads, state: CONTRADICTORY} on the RISK_ON-81-vs-BROKEN
    # dual-read (policy_summary excluded), policies [] / policy_count 0 /
    # posture NORMAL, authority rank/gate/size/execute ALL false. Live DOM
    # verified at 390/768/1440: markers present, zero page-level horizontal
    # overflow (evidence table scrolls in its own tbl-scroll container),
    # EN/ZH, no falsifier language. /riskdata/risk_envelope.json anonymous
    # 401 is the intended default-deny payload gate, not a defect.
  - id: GD-2R1
    title: Semantic-correctness repair of the settled envelope (pre-acceptance)
    status: done
    pr: 6037
    depends_on: [GD-2]
    # PR #6037 MERGED 2026-08-20T06:25:58Z (e23fdcdceae3); the two derived
    # envelope artifacts were regenerated on the merged tree. Gate 8 receipts
    # live on the GD-2 wave above.
    # Sol post-merge commission 2026-08-19; packet:
    # research/grey_deer/commissions/GD-2R1_SEMANTIC_CORRECTNESS_REPAIR_2026-08-19.md.
    # (1) LC BROKEN alone -> FRAGILE never TRANSMITTING (transmission needs an
    # independent settled source); (2) stage_since null until a lawful
    # first-observed episode transition — source onset stays in provenance;
    # (3) required-unmappable source nulls the hazard, optional calm can never
    # yield NONE; (4) behavioral stance copy removed while zero policies —
    # descriptive language + "no Grey Deer policy active"; (5) coherence
    # describes market reads only, posture excluded from agreement encoding;
    # (6) 08-18 fixture expectation -> FRAGILE / CONTRADICTORY, stage_since
    # null, raw source states unchanged.
  - id: GD-3
    title: Live provisional envelope + pending escalation
    status: in_progress
    pr: 6144
    depends_on: [GD-2]
    # Sol rulings 2026-08-19 (x2): do NOT start GD-3 until Gate 8 passes on
    # the GD-2R1-REPAIRED production render. Gate 8 PASSED 2026-08-20 —
    # GD-3 commissioned (packet + §0b Sol clarifications 2026-08-20:
    # research/grey_deer/commissions/GD-3_LIVE_PROVISIONAL_ENVELOPE_COMMISSION_2026-08-20.md).
    # BUILT + MERGED + DEPLOYED 2026-08-21: PR #6144 (sonnet builder; opus
    # adversarial review DO-NOT-MERGE round found 2 blockers — empty-live-block
    # laundered to FRESH/CALM, dwell de-escalating to calm during outage — plus
    # future-clock half-refusal, sticky degraded chip, 2-observation dwell;
    # all repaired + regression-tested, 111 tests green) merged 55d7ea02ce3e
    # on concluded green. Deployed: live macro.html carries the overlay hooks
    # (#gde-live-chip/#gde-pending-chip/#gde-live-receipt), data-bundle-id +
    # data-settled-session, risk_envelope_live.js ?v=bbe5e528; the consumer
    # script + live payload are tier-gated (anonymous 401 — deliberate; the
    # public-boundary decision was NOT taken).
    # GD-3R1 CLOCK-TRUTH REPAIR merged 2026-08-22T05:16Z (PR #6210,
    # e667ec39d176): Sol found a §0b.5 violation in the shipped bytes —
    # risk_state["built"] was published as clocks.event_time and
    # produced_at == observed_at. Repaired: event_time now comes from the real
    # contributing quote clocks (build_risk_state emits
    # live.source_event_time / source_quote_clocks; synthesized wall-clock
    # quote_ts is flagged and excluded), null when unestablishable and NEVER
    # substituted with built; upstream_built kept as separate lineage;
    # observed_at/produced_at are two real ms-precision clocks.
    # PRODUCTION ACCEPTANCE: WAITING_FOR_PRODUCTION_EVENT (Sol fallback,
    # 2026-08-21). The Gate-8-equivalent four-clock receipt requires an
    # AUTHENTICATED browser witness (regwall = Supabase session cookie only,
    # no ops bypass — verified app/regwall.py). The operator's Chrome never
    # connected during the full 2026-08-21 11:00-22:00Z window (14 retries);
    # a 2026-08-22 retry DID connect and sign in, but 2026-08-22 was a
    # SATURDAY, so no US session and no lawful event existed.
    # CORRECTION (2026-08-27): the 2026-08-21 record's claim that "no VPS
    # shell exists from the fleet host" is FALSE. app/deploy/README.md:29
    # documents `ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17`
    # (raw IP — the CDN-fronted hostname refuses port 22). It is read-only
    # diagnosis, NOT a receipt substitute: the acceptance measures the browser
    # paint leg.
    # PRE-VERIFIED IN PRODUCTION 2026-08-27 over that shell: the box runs the
    # GD-3R1 bytes; risk_envelope_live executes ok on EVERY fast-lane fire
    # (~0.9-2.2s, risk_state on odd minutes) — closing the 2026-08-21
    # unverified item; and the served 2026-08-26T22:59Z envelope proves the
    # closed-market clock laws in real bytes (event_time null while built was
    # 22:59:46; observed_at 22:59:46.623Z vs produced_at 22:59:47.538Z, ms
    # precision, 915ms apart; clocks.upstream_built 22:57:42.000Z separate;
    # revision live_provisional; all four authority booleans false).
    # STILL UNPROVEN and the whole remaining gate: event_time from a REAL
    # quote clock during an OPEN session, <=2-fast-fire propagation, browser
    # paint, and the interval-scoped data/-unchanged proof.
    # Executable acceptance packet:
    # agentos/handoffs/GREY-DEER-RISK-INTELLIGENCE-2026-08-27.md.
  - id: GD-4A
    title: CN/HK forward-ledger liveness repair
    status: done
    pr: 6022
    # PRODUCTION PROOF PASSED 2026-08-20: real settled run 32348780228
    # (asia job 13:29->15:20Z SUCCESS) advanced each ledger EXACTLY once —
    # one CN row asof 2026-08-20 (caution) + one HK row (calm), commit
    # baf4cf7c9291; no July-August backfill (tails ..07-16, 08-20); zero
    # intraday advancement all day. Duplicate-session idempotence proven on
    # production substrate: full rerun 32372312243 (16:15->17:54Z SUCCESS)
    # appended NOTHING — census identical, no new ledger commit.
    depends_on: [GD-0A]
    # PR #6022 MERGED (7d203ee2862f); Sol post-merge review 2026-08-19:
    # implementation ACCEPTED pending the real Asia-close production proof
    # (one current CN row + one current HK row, idempotent, zero intraday).
    # 2026-08-20 proof-day incident: the settled asia job could not run ALL
    # DAY — the gate's real-run classifier (run-level duration >= 10m)
    # counted QUEUE LATENCY as execution during a ~4h macstudio runner
    # starvation, classified two gate-skip runs (#287/#288, asia SKIPPED) as
    # real successes, and every later fire skipped with "a real run already
    # succeeded today" (receipt: run 32346400300 gate log 12:06:48Z). Failing
    # real path REPAIRED per the closeout mandate: PR #6089 moves the
    # classifier to job-level truth (asia job conclusion via the jobs API).
    # Proof event = the next real settled run after #6089.
    # Sol-commissioned 2026-08-19 as its own PR; packet:
    # research/grey_deer/commissions/GD-4A_CNHK_LEDGER_REPAIR_COMMISSION_2026-08-19.md.
    # COLLECT_LANE=nightly ONLY on the exact settled forward-ledger advancement
    # steps of the canonical Asia-close lane, never job-wide. Prospective
    # resume only — the July–August gap is NOT backfilled into the canonical
    # forward log. Done needs a real Asia-close production proof: exactly one
    # current CN row + one current HK row, duplicate-date idempotence, zero
    # intraday advancement.
  - id: GD-4A1
    title: CN/HK forward-ledger freshness in the existing liveness lane
    status: done
    pr: 6140
    depends_on: [GD-4A]
    # Sol-commissioned 2026-08-20 (parallel to GD-3); packet:
    # research/grey_deer/commissions/GD-4A1_LEDGER_FRESHNESS_LIVENESS_COMMISSION_2026-08-20.md.
    # Extends check_nightly_liveness.py MARKET_BOARDS with cn_ledger/hk_ledger
    # (kind: ledger, max_sessions_behind: 1 after adversarial review — budget 0
    # deterministically false-paged on weekend-anchored un-encoded CN holidays,
    # late-fire tail, and measured healthy-era misses; sustained stall alarms at
    # D+1 20:00Z = "within the next expected market session"). Review also
    # forced: UnicodeDecodeError crash fix (one bad byte killed the whole
    # watchdog), max(asof)-over-tail not last-line, board-path laziness
    # restored. MERGED e4f18b53e9d0 on concluded green; LIVE-VERIFIED same
    # hour: dispatch run 32435846087 on main SUCCESS with
    # "cn_ledger=2026-08-20(0) hk_ledger=2026-08-20(0)"; next-day organic
    # confirmation: ledgers advanced to asof 2026-08-21 (CN 14 / HK 13 rows,
    # one new row each, zero dups, commit 927fb6a78046).
  - id: GD-4B
    title: China Prophet board-health observation (display only)
    status: todo
    depends_on: [GD-0A]
  - id: GD-4C
    title: PBOC liquidity-composition read (display/context)
    status: todo
    depends_on: [GD-0A]
  - id: GD-5A
    title: Long-end duration shock expert (shadow)
    status: todo
    depends_on: [GD-1C]
    # Sol ruling 2026-08-19: GD-5A/B/C may not begin unless the applicable
    # hypothesis clears the promotion gate (GD-1 promoted nothing; GD-1C is
    # the prerequisite).
  - id: GD-5B
    title: Crowded-winner liquidation expert (shadow)
    status: todo
    depends_on: [GD-1C]
  - id: GD-5C
    title: Repair/re-entry expert (shadow)
    status: todo
    depends_on: [GD-1C]
  - id: GD-6A
    title: US Prophet market-eligibility sidecar (shadow)
    status: todo
    depends_on: [GD-2]
  - id: GD-6B
    title: China Prophet market-eligibility sidecar (shadow)
    status: todo
    depends_on: [GD-2, GD-4B]
  - id: GD-7A
    title: Temporary China new-entry protection (Chairman activation required)
    status: todo
    depends_on: [GD-6B]
  - id: GD-8A
    title: Macro alert integration (existing Alert Command Center)
    status: todo
    depends_on: [GD-3]
  - id: GD-8B
    title: Terminal envelope mirror (no local recompute)
    status: todo
    depends_on: [GD-3]
  - id: GD-9A
    title: Portfolio envelope shadow adapter (zero book mutation)
    status: todo
    depends_on: [GD-3]
  - id: GD-10
    title: Portfolio market-truth cutover (Sol + Chairman)
    status: todo
    depends_on: [GD-9A]
  - id: GD-11
    title: Promotion scorecard and learning loop
    status: todo
    depends_on: [GD-5A, GD-6A, GD-8A]
next_action: >
  2026-08-27: GD-3 is built, merged, deployed and REPAIRED (#6144 55d7ea02ce3e;
  GD-3R1 #6210 e667ec39d176) and verified RUNNING on the box every fast-lane
  fire, with the closed-market clock laws proven in served production bytes.
  The wave stays OPEN on WAITING_FOR_PRODUCTION_EVENT for one artifact only:
  the Gate-8-equivalent four-clock receipt, which needs an AUTHENTICATED
  browser during a US cash session (13:30-20:00Z weekday — the fast-lane gate
  is 11:00-22:00Z but the qualifying change needs a moving tape). Executable
  packet, including everything already proven so it is not re-proven:
  agentos/handoffs/GREY-DEER-RISK-INTELLIGENCE-2026-08-27.md. In short: in-page
  authenticated fetch of live/risk_envelope.json + live/risk_state.json on
  macro.html; FIRST real live-source change (rs.built advancing WITH
  live_active true) reflected in the envelope within ≤2 fast fires;
  event_time→observed_at→produced_at→browser_seen_at with event_time equal to
  the real source quote clock and never to rs.built; overlay paint screenshot;
  interval-scoped proof data/ + forward ledgers unchanged. Feed delay is
  informational and never a failure (Sol 2026-08-22). Do NOT simulate or
  manufacture the event (Sol 2026-08-21); do not modify the implementation
  unless the real witness falsifies it (Sol 2026-08-22). GD-4A.1 DONE.
  GD-8A/8B/9A remain gated on that receipt and may not be commissioned from
  the acceptance seat. GD-5A/B/C stay closed; GD-4B/4C open and
  uncommissioned; GD-6/7 and Portfolio cutover not authorized.
---

# Grey Deer Risk Intelligence & Capital Protection

The canonical architecture, laws, wave packets, acceptance matrices, collision
fences and research protocol live in `research/grey_deer/` (see its `README.md`
for precedence). This record carries program state only.

**Authority summary:** the Risk Envelope owns no rank/size/gate/execute
authority. Policy authority arrives only per-rule via the frozen promotion
gates (freeze §10) or an explicit `temporary_operator_safety` Chairman grant
(freeze §11). Automatic held-position exit is out of scope for v1.

**Ownership summary:** Macro owns market truth, hazard experts, the envelope
and Prophet eligibility sidecars; Prophet owns raw rank/admission; Terminal
mirrors; Mastermind Portfolio consumes the envelope and owns book-specific
sizing/settlement/execution; LLMs explain and de-escalate only.
