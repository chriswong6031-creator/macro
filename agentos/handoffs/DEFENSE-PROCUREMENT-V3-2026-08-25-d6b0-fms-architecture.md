---
workstream: WS:DEFENSE-PROCUREMENT-V3
session: claude/d6b0-fms-architecture
model: fable
ended_because: complete
prs: [6404]
decisions:
  - DEC:FMS-CANONICAL-OWNER-IS-GOVREV-FMS-RAIL
discoveries: []
mission: >
  Sol commission D6-B0 (authorized in the D6-A acceptance ruling, macro #6385
  comment 5404403124): freeze the FMS congressional-notification source
  migration + stage/contract architecture so the D6-B implementation worker
  decides nothing — current/historical source, cutover, identity, stage,
  amount, corrections, canonical owner, consumer, canaries, failure states,
  proof standard. Research/records only; no collectors, schemas, APIs,
  templates, or generated data. D6-B implementation NOT authorized; D6-C+ and
  D7+ unauthorized.
state_before: >
  Pickup origin/main 99af5edd762637935afa2ce75d040e3ed5bd0532
  (2026-08-25T15:05Z). D6-A just Sol-accepted / PROVEN_LIVE; WS record still
  carried the stale "acceptance pending" text. Zero FMS/DSCA footprint
  anywhere in the repo (receipted grep). D0R registry DSCA row still pointed
  at dsca.mil as the sole surface, E2 row "UNVERIFIED this close".
changed:
  - path: research/defense_intelligence/DEFENSE_D6B_FMS_SOURCE_AND_STAGE_ARCHITECTURE_FREEZE_2026-08-25.md
    what: >
      THE FREEZE. §0 implementation acceptance gates; §2 source census with 7
      sha256 receipts (DSCA landing + notice 26-13 + certification PDF +
      Library; State listing + notice 26-27 browser/CLI twins; FR 2026-14768)
      and both migration boundary statements verbatim (EO 14383 2026-02-06;
      State "prior to February 26, 2026"); §3 source-boundary law (State
      current / DSCA history / FR supplementary; CLI transport proven for
      State, browser-only for DSCA); §4 SAMM-grounded stage law (v1 proves
      only congressional_notification; time never advances); §5
      estimated_notification_value amount law; §6 transmittal identity +
      deterministic URL-path fallback with frozen collision/supersession
      properties; §7 four-clock law (State-era notification date null unless
      FR join); §8 append-only correction law grounded in first-party
      behavior (State in-place edits, DSCA CNVn version files); §9
      contract-owner adjudication (event.v2 rejected on identity-seed
      evidence; GovRev-owned FMS rail frozen); §10 read-model sketch; §11
      contractor law (no ticker minting; D2 atlas path or unresolved); §12
      program law (D5-shaped five-key pointer, all not_reviewed in v1; D5
      untouched); §13 consumer freeze (ninth fms mode on
      government_revenue.html, 303,104-byte fence, 8,192-byte shell delta,
      five-second answers); §14 failure-state token table mapped to
      canonical GovRev spellings; §15 golden canaries + hostile stage-hold;
      §16 twelve merge-binding kill tests; §17 five named unresolveds for
      Sol (U1-U5).
  - path: research/defense_intelligence/DEFENSE_D6B_FMS_IMPLEMENTATION_HANDOFF.md
    what: >
      Paste-ready D6-B commission (marked NOT YET AUTHORIZED): §0 gates
      inline, decided-matters table, owned files, order law, census traps,
      unresolveds routed to Sol.
  - path: research/defense_intelligence/evidence/fms_reference_composition_2026-08-25.json
    what: >
      Real-data reference composition: both canaries (26-13 Saudi PAC-3
      $9.0B / 26-27 Sweden HIMARS $930M) in the frozen case shape with
      receipts, contractor not_reviewed states, program_link five-key
      not_reviewed, clocks incl. the null State-era notification date, and
      the hostile-state note.
  - path: agentos/decisions/DEC-FMS-CANONICAL-OWNER-IS-GOVREV-FMS-RAIL.md
    what: >
      Canonical-owner decision with alternatives (extend event.v2 /
      new store / dossier-widening / changes-tape bridge) each rejected on
      evidence; reversibility costly-after-ship.
  - path: research/defense_intelligence/D0R_SOURCE_RIGHTS_AND_PIT_REGISTRY.md
    what: >
      DSCA 36(b) registry row rewritten to the migrated two-surface truth;
      new E2 re-census row (verified_at 2026-08-25) with all receipt shas.
  - path: agentos/workstreams/WS-DEFENSE-PROCUREMENT-V3.md
    what: >
      First commit (173922a715c2): D6-A = done / Sol accepted / PROVEN_LIVE
      with the four acceptance rulings captured; stale next-action text
      repaired; D6-B0 opened in_progress. Closing commit of this PR: D6-B0
      = done / awaiting Sol acceptance; D6-B implementation, D6-C+, D7+
      still unauthorized.
verified:
  - claim: DSCA→State migration and both boundary statements receipted first-party
    command: >
      Browser-pane in-page fetch + crypto.subtle sha256 on
      dsca.mil/press-media/major-arms-sales and
      state.gov/arms-sales-congressional-notifications (2026-08-25)
    result: >
      DSCA banner cites EO 14383 (signed 2026-02-06): future FMS web posts
      publish on the State website; State page states DSCA archives cases
      notified prior to 2026-02-26. Receipts: DSCA landing sha256
      33fd727f…670f92 (79,526 B); State listing 6ba951b5…5f83d85
      (194,545 B, 55 items, PM Bureau).
  - claim: Both pilot canaries fetched with sha256 receipts and source-native transmittal identity
    command: browser in-page fetch + crypto.subtle; CLI curl twin for State
    result: >
      DSCA 26-13 (Saudi PAC-3 MSE, $9.0B, Lockheed-Martin, caveat paragraph
      present, certification PDF c7e3bcad…af9c55 133,064 B %PDF); State
      26-27 (Sweden M142 HIMARS, $930M, dated 2026-03-10, NO pdf/caveat/
      certification sentence, article:modified_time 2026-08-21). State page
      CLI-deterministic: two fetches byte-identical
      (692236b0…fbd37a, 176,926 B).
  - claim: Transport matrix proven from the runner host family
    command: curl -s -o /dev/null -w "%{http_code}" against all hosts
    result: >
      state.gov 200 (CLI, deterministic); dsca.mil 403; media.defense.gov
      403; samm.dsca.mil 200; federalregister.gov 200 (API; doc 2026-14768
      carries Transmittal No. 26-74 + "Date Report Delivered to Congress:
      June 5, 2026", pub 2026-07-22, 91 FR 46080).
  - claim: government_procurement_event.v2 cannot honestly carry FMS
    command: scout census (schema + award_events.py read)
    result: >
      kind enum [opportunity, recompete, award_change]; runtime emits only
      award_change; event_id seed includes award_key
      (award_events.py:1735-1776); required fields award-shaped. Frozen
      owner = GovRev FMS rail (DEC).
  - claim: Consumer fence has measured headroom
    command: git cat-file -p origin/main:site/government_revenue.html | wc -c
    result: >
      274,214 bytes vs RAW_HTML_BUDGET_BYTES 303,104
      (build_government_revenue.py:113; test_government_revenue_ui.py:671)
      = 28,890 free; FMS shell delta frozen ≤ 8,192.
  - claim: Zero existing FMS/DSCA footprint (no duplicate risk)
    command: grep -rniIaE "foreign military|dsca|36\(b\)|\bfms\b" collectors/ engine/ app/ templates/ docs/ research/
    result: >
      Only incidental substring collisions (lan-dsca-pe identifiers,
      "landscape", an unrelated "$36B" figure); zero substantive FMS/DSCA
      content anywhere in the repo at pickup head 99af5edd7626.
  - claim: AgentOS schema clean
    command: python3 scripts/agentos.py validate
    result: 700 records, 0 errors (21 pre-existing warnings on unrelated records).
  - claim: Freeze package adversarially reviewed before Sol, verdict FAIL, repaired
    command: opus reviewer packet on freeze + handoff + composition + DEC + D0R diff
    result: >
      5 blockers / 11 mediums / 6 lows. Blockers all repaired in the
      review-repair commit: B1 programLink schema-reuse was unsatisfiable
      (event plane's not_reviewed branch requires non-null
      ontology_graph_id) → FMS-owned five-key shape frozen; B2 canary-A
      acquisition contradiction → bounded browser-transport archival path
      frozen as the v1 floor; B3 unreceipted review-period-elapsed claim
      → excised everywhere, hostile canary reframed without review-period
      arithmetic; B4 transmittal label grammar unfrozen → detection
      regex + normalization + mis-key guard frozen in §6; B5 in-plane
      aggregation unbanned → forbidden + kill test T13. Mediums/lows
      repaired (case_identity_state split, advancement catalog, two-plane
      freshness vocabulary, composition matchability law, program_links
      list + program_case_link_id, gate-7 proof standard clarified,
      canary-A web-date provenance, empty_valid predicate + T14, FR byte
      receipt added). §9/DEC contract-owner adjudication and source law
      survived attack unchanged; every repo citation in them verified true.
unverified: []
unresolved:
  - >
    U1: SAMM C5.7 body (15/30-day classes, thresholds) not verbatim-receipted
    (chapter page truncates); irrelevant to v1 law (no time-based logic) but
    required before any review-period display.
  - >
    U2: historical backfill depth (DSCA Library pre-Dec-2024 corpus is
    browser-transport-only) — Sol's scope call at D6-B authorization.
  - >
    U3: Federal Register join deferred-or-not for v1 — without it State-era
    official_notification_date stays null.
  - >
    U4: Feb-06→Feb-26-2026 boundary window not exhaustively censused for
    dual/absent-surface cases; dedup-by-transmittal makes it safe; sweep at
    implementation.
  - >
    U5: ZH glance-tier vocabulary for FMS stage/amount negatives — design
    lane at implementation.
next_actions:
  - Return the D6-B0 package to Sol; D6-B implementation starts ONLY on a new Sol authorization consuming DEFENSE_D6B_FMS_IMPLEMENTATION_HANDOFF.md.
  - At D6-B authorization, Sol rules U2 (backfill depth) and U3 (FR join in v1).
do_not_redo:
  - Do not re-census DSCA/State from scratch; verify against the 2026-08-25 receipted census (FREEZE §2). Bytes may have moved — that is a new observation, not a census error.
  - Do not re-litigate the contract owner: extending government_procurement_event.v2 for FMS was rejected on identity-seed evidence (DEC:FMS-CANONICAL-OWNER-IS-GOVREV-FMS-RAIL).
  - Do not touch D5 (budget_program_keys stays const []) or widen government_program_dossier.v1 for FMS.
  - Do not assume DSCA-era notice fields (PDF, caveat, certification sentence, notification date) exist on State-era posts — censused absent.
danger_areas:
  - Review-period arithmetic is the trap that turns honest data into a false sale — the freeze forbids even computing "review complete"; kill test T3.
  - State posts mutate in place at the same URL (modified_time only); any implementation shortcut that overwrites observations destroys the only version history that exists anywhere.
  - Browser vs CLI bytes differ on state.gov — never mix transports inside one receipt chain.
---
