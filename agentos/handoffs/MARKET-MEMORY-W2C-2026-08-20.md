---
workstream: "WS:MARKET-MEMORY-W2C"
session: claude/market-memory-m0a-proof-20260820
model: local
ended_because: complete
mission: >
  Reconcile the three registered W2C prospective windows after the outage,
  publish immutable dispositions, decide M0A pass/fail from production
  evidence, update the workstream, and stop without starting M0B.
state_before: >
  WS-MARKET-MEMORY-W2C still described #5805 as awaiting merge and the
  2026-08-18 window as future. #5805 had already merged. Canonical registration
  remained mmspyexpreg_e00ffc1d34b57ce3b011955a8662dae8f7e069b7f5f07417c428a5815c6dd6e3.
  Public regime latest.json at task start was asof=2026-08-19,
  built_at=2026-08-20T02:38:26Z, stale=false. No production dispositions had
  been authenticated through the reader primitives.
changed:
  - path: agentos/workstreams/WS-MARKET-MEMORY-W2C.md
    what: >
      Marked M0A done/proven from the three in-window abstained rows, retargeted
      M0B to the remaining exact-same-session technical capture lag, and replaced
      the stale 2026-08-16 operational claims.
  - path: agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20.md
    what: >
      Recorded the three-window production reconciliation, timer/installation
      receipts, source-generation pins, and the M0A pass with M0B named but not
      started.
verified:
  - claim: >
      Capture UTC was 2026-08-20T07:58:41Z. /opt/macro HEAD was
      49f26569d547d29e3a260406e75bde5dccbf23f0 and was not modified.
    command: >
      date -u +%Y-%m-%dT%H:%M:%SZ; git -C /opt/macro rev-parse HEAD;
      git -C /opt/macro log -1 --format='%H %cI %s'
    result: >
      2026-08-20T07:58:41Z
      49f26569d547d29e3a260406e75bde5dccbf23f0
      2026-08-20T00:56:53-07:00 whitehouse: alert update 2026-08-20T07:56Z
  - claim: >
      Experience timer is enabled and genuinely armed: active/waiting, last
      trigger 2026-08-20 04:30:00 UTC, next fire 2026-08-21 04:30:00 UTC.
    command: >
      systemctl is-enabled macro-market-memory-experience.timer;
      systemctl is-active macro-market-memory-experience.timer;
      systemctl show macro-market-memory-experience.timer
      -p UnitFileState -p ActiveState -p SubState -p NextElapseUSecRealtime
      -p LastTriggerUSec
    result: >
      enabled / active; UnitFileState=enabled; ActiveState=active;
      SubState=waiting; NextElapseUSecRealtime=Fri 2026-08-21 04:30:00 UTC;
      LastTriggerUSec=Thu 2026-08-20 04:30:00 UTC
  - claim: >
      The last experience service run succeeded inside the 2026-08-19 window
      at 04:30:02–04:30:18 UTC and wrote opportunity
      mmspyexpopp_55d0d26480172ac7198fdb6831b678f34b2ea548237f9966f9166d9b2c95429a.
    command: >
      systemctl show macro-market-memory-experience.service
      -p Result -p ExecMainStartTimestamp -p ExecMainExitTimestamp
      -p ExecMainStatus; journalctl -u macro-market-memory-experience.service
      --since '2026-08-20 04:30:00 UTC' --until '2026-08-20 04:31:00 UTC'
    result: >
      Result=success ExecMainStatus=0 start 04:30:02Z exit 04:30:18Z;
      JSON schema market_memory.spy_experience_accrual_run.v1,
      deployed_commit=cdf99c6203b6bd964d7fb5564452289ecfde90e8,
      registration_id matches the canonical registration
  - claim: >
      Installation authentication succeeded against the private store without
      invoking the writer.
    command: >
      /opt/macro-api/.venv/bin/python -m scripts.accrue_market_memory_spy_experience
      --repository-root /opt/macro
      --experience-root /var/lib/macro-market-memory/state/experience-v1
      --verify-installation
    result: >
      schema market_memory.spy_experience_installation_attestation.v1;
      verified=true; registration_id matches canonical;
      installation_id=mmspyexpinstall_b9af7ddafab5a3e25ac850a07483f8b6cfcd97ad9e5bd15345f4d09605ec8525;
      store_id=mmspyexpstore_87fc719d471fe1f1eb6dd2d6fcee21290f17ea4a77d8a36807c4223f1c24f725;
      deployed_commit at verify time=49f26569d547d29e3a260406e75bde5dccbf23f0
  - claim: >
      All three expected sessions have sealed opportunity files, no pending
      publications, and validate_opportunity accepts each row.
    command: >
      read-only _read_json_path + validate_opportunity for
      opportunities/2026-08-17.json, 2026-08-18.json, 2026-08-19.json
    result: >
      2026-08-17 abstained technical_session_absent sealed 2026-08-18T04:30:24.906623Z;
      2026-08-18 abstained trusted_macro_and_technical_session_absent sealed 2026-08-19T04:30:09.298633Z;
      2026-08-19 abstained technical_session_absent sealed 2026-08-20T04:30:16.759598Z;
      each owner_attempt and seal inside its registered 04:30–04:45 UTC window;
      pending=[]
  - claim: >
      Population receipt through 2026-08-19 records 3 expected, 3 recorded,
      3 abstained, 0 admitted, 0 missed, 0 missing_sessions, timely=3,
      opportunity_completeness_q18=1.0, terminal status=open.
    command: >
      _read_json_path on
      population_receipts/mmspyexppop_c4ca803f7c397b4377c680068740c641b491cb99a7054fdff4756a0a5a926b42.json
    result: >
      population_receipt_id=mmspyexppop_c4ca803f7c397b4377c680068740c641b491cb99a7054fdff4756a0a5a926b42;
      observed_at=2026-08-20T04:30:17.211237Z;
      writer_commit=cdf99c6203b6bd964d7fb5564452289ecfde90e8;
      expected_sessions=[2026-08-17, 2026-08-18, 2026-08-19]
  - claim: >
      Experience service fired inside all three windows. Timer was started
      2026-08-18T01:30:33Z, stopped 2026-08-19T15:00:06Z, restarted
      2026-08-19T22:57:24Z, after the 2026-08-19 04:30 fire.
    command: >
      journalctl -u macro-market-memory-experience.service
      --since '2026-08-17 00:00:00 UTC' --until '2026-08-20 06:00:00 UTC';
      journalctl -u macro-market-memory-experience.timer
      --since '2026-08-17 00:00:00 UTC' --until '2026-08-20 06:00:00 UTC'
    result: >
      2026-08-18T04:30:16Z success opp mmspyexpopp_b7f75ace...;
      2026-08-19T04:30:00Z success opp mmspyexpopp_a4471315...;
      2026-08-20T04:30:02Z success opp mmspyexpopp_55d0d264...
  - claim: >
      Source and context owners succeeded in the hour before each 04:30 window.
      The old nested-filename exception did not recur. Technicals captured
      session=2026-08-14 before the first two windows, failed 2026-08-19 on
      ticker-count/publish-last, then succeeded with session=2026-08-18
      before and after the third window, still lagged versus 2026-08-19.
    command: >
      journalctl -u macro-market-memory-source.service
      -u macro-market-memory-context.service
      -u macro-market-memory-technicals.service
      --since '2026-08-18 03:00:00 UTC' --until '2026-08-20 05:00:00 UTC'
    result: >
      source already_present each pre-window fire; context Result=success each
      pre-window fire; technicals 08-18 session=2026-08-14 success; 08-19
      'store ticker count does not match the publish manifest' then
      'publish-last manifest predates the SPY parquet'; 08-20 session=2026-08-18
      success at 03:54Z and still session=2026-08-18 at 07:54Z
unverified:
  - claim: >
      Whether the 2026-08-21 04:30 window will admit if Massive publishes the
      2026-08-20 SPY daily bar in time.
    what_would_verify: >
      Authenticate opportunities/2026-08-20.json after 2026-08-21T04:45:00Z
      through validate_opportunity. Do not start the service by hand.
unresolved:
  - >
    Exact-same-session technical capture is still absent at 04:30 UTC. That is
    the first remaining causal blocker to admitted. It is not an M0A failure.
  - >
    Session 2026-08-18 also lacked a trusted same-session pin
    (trusted_macro_and_technical_session_absent). Context itself was green;
    the pinned trusted generation had no source_session=2026-08-18 capture.
  - >
    2026-08-19 technicals additionally failed closed on ticker-count mismatch
    and later publish-last-predate. Those are distinct from the #5805 nested
    path reject and were not repaired here.
next_actions:
  - Return the three-window table and M0A pass to Sol.
  - Start M0B in a later session as one causal PR for the 04:30 exact-same-session technical lag.
  - Do not start M0B, V2, UI, retrieval, Cortex, Prophet, score, or a new source in this session.
do_not_redo:
  - Do not treat in-window abstained as missed or as proof that activation failed.
  - Do not backfill, replay 04:30 by hand, or restamp built_at to manufacture admitted.
  - Do not reopen #5805 without a live noncanonical-filename reproduction.
  - Do not assume weekend context freshness is still the first cause.
  - Do not widen the 36h freshness wall or the 15-minute window.
danger_areas:
  - _load_opportunity recovers via _write_create_once. Discovery reads must use _read_json_path plus validate_opportunity, never the recovery loader.
  - Ordinary accrue_market_memory_spy_experience without --verify-installation is the sole production writer.
  - A lagged technicals success looks healthy in systemd Result=success while still producing technical_session_absent.
---

# M0A-PROOF — three-window production reconciliation

## 0. Verdict

**M0A PASSES.** W2C executed prospectively in production on all three registered
sessions. Each window produced a validated **abstained** row, sealed inside
04:30–04:45 UTC, from the real systemd timer and the registered evidence
rules. The continuing timer is enabled, active/waiting, and next fires
2026-08-21 04:30:00 UTC. Installation authentication succeeded.

None of the three rows is admitted. That does not fail M0A. The remaining
path to admitted is M0B and was not started.

Capture `/opt/macro` HEAD: `49f26569d547d29e3a260406e75bde5dccbf23f0` at
2026-08-20T07:58:41Z. This session did not alter that checkout.

## 1. Immutable dispositions

| Expected session | Window UTC | Disposition | Opportunity id | Sealed at | Reconciled at | Reason | Sealed in window |
|---|---|---|---|---|---|---|---|
| 2026-08-17 | 2026-08-18 04:30–04:45 | **abstained** | `mmspyexpopp_b7f75ace5d0eace4ad13f99d2e67c70bdee64829ad8009f07fdd5bbe88dd3f47` | 2026-08-18T04:30:24.906623Z | null | `technical_session_absent` | yes |
| 2026-08-18 | 2026-08-19 04:30–04:45 | **abstained** | `mmspyexpopp_a44713151fae1a285e0d01ca10ffd74f5c80c46e28a2fbcc1944711b47930718` | 2026-08-19T04:30:09.298633Z | null | `trusted_macro_and_technical_session_absent` | yes |
| 2026-08-19 | 2026-08-20 04:30–04:45 | **abstained** | `mmspyexpopp_55d0d26480172ac7198fdb6831b678f34b2ea548237f9966f9166d9b2c95429a` | 2026-08-20T04:30:16.759598Z | null | `technical_session_absent` | yes |

Owner attempt clocks were also inside each window:
2026-08-18T04:30:18.665574Z, 2026-08-19T04:30:04.928131Z,
2026-08-20T04:30:09.060811Z.

Writer commits at seal: `22f3f915ac5d40533f7dced3959e1281d3aeade5`,
`fe313751eeefa7e42b45214ef81eae5a151b5d99`,
`cdf99c6203b6bd964d7fb5564452289ecfde90e8`.

Population receipt
`mmspyexppop_c4ca803f7c397b4377c680068740c641b491cb99a7054fdff4756a0a5a926b42`
matches those three ids. Counts: expected 3, recorded 3, abstained 3,
admitted 0, missed 0, missing_sessions []. Terminal status remains open
until 2027-03-03T04:30Z.

## 2. Source-generation references

Selection on every row:
`earliest_distinct_owner_observation_exact_session.v1`.

**2026-08-17** — trusted capture present (`source_session=2026-08-17`,
`mmcapture_8936ec9206aa49f69c281fe431bc01d5d689fdecd2b1ea65860fe98b742bf005`,
`mmctx_e8e9c5a8fa496a3fce2ffd03aaa99967a315d98c7eeff359b9744f8fec6c871d`).
Trusted generation `mmgeneration_c9c6f312565c0900f798a4abc58dc74fac49cd7cae46475e13e832dcf71d122a`
sha256 `c28775c5d88a733c095e674e8b33e21684077f345fefd8553b0080521c2a2369`
capture_count 12. Technical generation
`mmactualgeneration_844ed79bc6c55c137493047e198b33d6a42cfb7e26ca2c0e77bc3726a59b61a7`
sha256 `e5007c39d905a25a1323f970edb6478f8f4d304b119b95dd2b151cd2f0a0b77d`
capture_count 9. Technical capture null.

**2026-08-18** — both captures null. Trusted generation
`mmgeneration_c1ff8e07b8db2ec62595eea3d18c05b1a66d39d8ea699eb58da473d571b27d66`
sha256 `92460ca12ea9b6360d4f9b01d23acc29a050c60ee9445e3b7bf8a4fd28af3dbf`
capture_count 15. Technical generation
`mmactualgeneration_03b14e59787486567c68ef6736ffcaf16adbf22d38019743febe42d8da32917e`
sha256 `05ca0fc9de55376ad7d7860293eab42ccf7ac3a82d1d72e9dce2eddb2ca5eb8f`
capture_count 10.

**2026-08-19** — trusted capture present (`source_session=2026-08-19`,
`mmcapture_a8106b5d90b6981e6d8d9cc9ebdb1676ce33df74438aff6036290486ba0425c0`,
`mmctx_2b58ab2002355c962e43acc5ad296ef213a66614343b512edce1a530e3cb04fa`).
Trusted generation `mmgeneration_91067e9067a9620b45abcbb51cb61dfedc7573d5dcff93017cffcad30386724b`
sha256 `181d4e754d1e37d6d780fd9f79b7c07fb5ef43dc9dbf3924f2af0c3472f51f2b`
capture_count 18. Technical generation
`mmactualgeneration_800e55e02ce6d41a8236088ba9dfefaab51e35d86988b1d307a032cc2afd2994`
sha256 `1c5f445fc7d92a2ab403746b4b6ec7d3aff6410ea602a620ab89d6ffc92ed1af`
capture_count 13. Technical capture null.

## 3. Failure attribution for missed/absent

No missed rows. No absent rows. Attribution for missed/absent is empty.

The abstentions are lawful same-session evidence misses, not infrastructure
skips of the window. Source CPI intake was `already_present` before each
04:30. Context published successfully before each 04:30. Experience ran
inside each window. The common remaining hole versus **admitted** is that
the technical generation had no capture whose session equalled the
opportunity session.

Per-window owner notes, not M0A failures:

- 2026-08-17: technicals last success before 04:30 carried `session=2026-08-14`.
- 2026-08-18: technicals were failing closed (`store ticker count does not match the publish manifest`); trusted generation also lacked `source_session=2026-08-18`. First owner in source→context→technicals order that lacked the session pin is context/trusted, concurrent with technicals red.
- 2026-08-19: technicals succeeded before 04:30 with `session=2026-08-18`, still not 2026-08-19. Trusted exact-session pin was present.

#5805's nested `__case_v1` filename reject did not recur in these journals.
Do not reopen it.

## 4. Timer and installation

- `macro-market-memory-experience.timer`: enabled, active (waiting) since
  2026-08-19T22:57:24Z, next 2026-08-21T04:30:00Z.
- `macro-market-memory-experience.service`: last Result=success, disabled as
  a unit (timer-triggered oneshot; that is the reviewed shape).
- `--verify-installation`: verified. `--verify-terminal` exited 3 because
  TERMINAL.json does not exist; the pilot is open through 2027-03-03.

## 5. What is left

M0B only: one causal repair so the technical owner exposes the opportunity
session's SPY actual-output capture before 04:30 UTC. Investigate the lagged
pinned session and the distinct 2026-08-19 ticker-count / publish-last
failures. Do not start that PR from this proof session.
