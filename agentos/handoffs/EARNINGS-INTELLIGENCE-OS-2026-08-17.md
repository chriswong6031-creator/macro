---
workstream: "WS:EARNINGS-INTELLIGENCE-OS"
session: claude/earnings-e1p-handoff
model: local
ended_because: complete
mission: >
  E1P production activation: put the merged AAPL FY2026 Q3 event_workspace.v1
  on the frozen public Company Intelligence R2 nest through the existing
  company-intelligence.yml lane, and prove the real read_event_workspace HTTP
  reader returns available:true. Do not implement E2.
state_before: >
  PR #5817 had merged the contract, builder, writer, and real HTTP reader, but
  company_intelligence/event_workspaces/manifest.json was HTTP 404 and
  read_event_workspace returned available:false. E2 was blocked on that object.
changed:
  - path: scripts/refresh_event_workspaces.py
    what: Production bridge — acquire real Exhibit 99.1 + Terminal transcript, source-stable clock, write sibling nest, publish marker-last.
  - path: scripts/publish_company_intelligence_r2.py
    what: publish_event_workspaces reuses existing R2 primitives under company_intelligence/event_workspaces/; never touches the v1 marker.
  - path: .github/workflows/company-intelligence.yml
    what: Same concurrency group and R2 credentials; workspace refresh after v1; workspace failure is explicit.
  - path: tests/test_refresh_event_workspaces.py
    what: Same-input no-op, source-SHA correction, last-good on missing SEC/transcript, four-alias reader, escaped SGML headers.
  - path: agentos/discoveries/DSC-E1-READER-IS-NOT-THE-PRODUCTION-OBJECT.md
    what: A production-shaped reader test is not a live R2 object.
  - path: agentos/discoveries/DSC-EDGAR-INDEX-HEADERS-ARE-HTML-ESCAPED.md
    what: Live EDGAR index-headers.html is HTML-escaped SGML; unescape before TYPE/FILENAME.
prs: [5835, 5841]
discoveries:
  - "DSC:E1-READER-IS-NOT-THE-PRODUCTION-OBJECT"
  - "DSC:EDGAR-INDEX-HEADERS-ARE-HTML-ESCAPED"
verified:
  - claim: Public sibling marker is HTTP 200 event_workspace_manifest.v1 on generation f709a0a6ec514282d5769e7d.
    command: >
      curl -sS -D - -o /tmp/ew-marker.json -A "Mozilla/5.0"
      https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/company_intelligence/event_workspaces/manifest.json
    result: "HTTP 200; schema event_workspace_manifest.v1; generation_id f709a0a6ec514282d5769e7d; generated_at 2026-07-30T20:30:28Z"
  - claim: Immutable generation manifest byte-agrees with the marker.
    command: >
      curl -sS -A "Mozilla/5.0"
      https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/company_intelligence/event_workspaces/generations/f709a0a6ec514282d5769e7d/manifest.json
    result: "HTTP 200; same ETag c90f5ca161de8530f45e5eedbec98df2 as the marker; generation_id matches"
  - claim: Flagship workspace is receipt-verified under that generation.
    command: >
      curl -sS -A "Mozilla/5.0"
      https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/company_intelligence/event_workspaces/generations/f709a0a6ec514282d5769e7d/workspaces/evt_cik0000320193_2026q3_results.json
    result: "HTTP 200; schema event_workspace.v1; event_id evt_cik0000320193_2026q3_results"
  - claim: All four aliases return available:true on the same generation with authority context_only.
    command: >
      python3 -c 'from engine.neuralweb.company_intelligence_reader import read_event_workspace as r;
      ids=["evt_cik0000320193_2026q3_results","cie_98e318c37ec1a2a1f83c45e1","AAPL/2026Q3","aapl-2026q3-call-record"];
      [print(r({"event_id":i})["available"], r({"event_id":i})["event_id"], r({"event_id":i})["authority"], r({"event_id":i})["receipt"]["generation_id"]) for i in ids]'
    result: "four times available True / evt_cik0000320193_2026q3_results / context_only / f709a0a6ec514282d5769e7d"
  - claim: Production payload is real SEC+transcript, not the E1 fixture, with typed absences as frozen.
    command: >
      python3 -c 'from engine.neuralweb.company_intelligence_reader import read_event_workspace as r;
      w=r({"event_id":"evt_cik0000320193_2026q3_results"})["workspace"];
      print(w["issuer"]["company_id"], w["completeness"]["filing"]["filing_key"], w["completeness"]["release"]["status"], w["completeness"]["transcript"]["status"], w["completeness"]["consensus"]["status"], w["prophet_flags"])'
    result: >
      cik:0000320193; accession 0000320193-26-000018; release present
      (sha256 070abd6a9cdb7070e546d24ffcbc41c65450d939c6f88f189cb18ec711cf5fdb);
      transcript present (sha256 a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f);
      fact_revenue_gaap 109417 usd_millions byte_replayed; 8 claims byte_replayed;
      questions_count typed absence; consensus unlicensed / basis_match false;
      no beat/miss verdict; slides absent; reaction not_joined; Prophet flags all false
  - claim: Unchanged second production run is a semantic no-op.
    command: gh run view 32042904048 --log | rg "event workspace generation"
    result: "event workspace generation f709a0a6ec514282d5769e7d already promoted; live marker still f709a0a6ec514282d5769e7d / generated_at 2026-07-30T20:30:28Z"
unverified: []
unresolved:
  - "edgar_collector remains unjoinable_filing_identity: the production job does not date-join the legacy parquet; (cik, accession) is still the filing key."
  - "public_wire aapl-2026q3-call-record stays typed 404 as admitted in E1."
  - "questions_count is a typed absence because the held transcript has an empty analyst role; overlay history of 14 is not a structured Q&A count."
  - "consensus stays unlicensed; slides absent; reaction not_joined. These are frozen optional sources, not E1P failures."
next_actions:
  - "Implement E2 exactly as frozen; render the now-live AAPL FY2026 Q3 event_workspace.v1 through read_event_workspace in the existing Terminal Company Intelligence workspace and Macro dossier glance. Do not re-read the v1 score overlay for the glance and do not broaden scope into E3+."
do_not_redo:
  - "Do not implement another earnings-event-workspace.yml publisher. The live nest is company-intelligence.yml + publish_event_workspaces."
  - "Do not parse EDGAR -index-headers.html without html.unescape (DSC:EDGAR-INDEX-HEADERS-ARE-HTML-ESCAPED)."
  - "Do not treat a green read_event_workspace unit test as proof the R2 object exists (DSC:E1-READER-IS-NOT-THE-PRODUCTION-OBJECT)."
  - "Do not publish E1 fixtures as production truth."
  - "Do not date-join the 8-K by filing date when the collector row lacks accession."
danger_areas:
  - "refresh() prints 'immutable generation published and sibling marker promoted' even when publish_event_workspaces returned already-promoted; the INFO line 'already promoted' is the no-op receipt."
  - "Public R2 GETs 403 without a browser User-Agent; the production reader sets one, curl -I without -A does not."
  - "GitHub collaborators-permission and check-runs POST returned HTTP 503 for ~2h on 2026-08-17; ci-authority/main and fence-pack PUBLISH can red while packs are green."
---

## §0 State — what is true right now

E1P is live. Merge SHAs: `6f223ed02916` (#5835, production bridge) and `b883d341e241` (#5841, SGML unescape). Public marker `company_intelligence/event_workspaces/manifest.json` is HTTP 200. Live generation is `f709a0a6ec514282d5769e7d`. `read_event_workspace` returns `available: true` on all four AAPL aliases with `authority: context_only`. The 15:37Z scheduled rerun kept that generation (`already promoted`). E2 is unblocked. This session did not start E2.

## §1 What is LEFT — in order

1. New session: execute `research/earnings_intelligence/E2_IMPLEMENTATION_HANDOFF.md` against this live generation. Authorizing sentence:

   Implement E2 exactly as frozen; render the now-live AAPL FY2026 Q3 event_workspace.v1 through read_event_workspace in the existing Terminal Company Intelligence workspace and Macro dossier glance. Do not re-read the v1 score overlay for the glance and do not broaden scope into E3+.

2. Do not generalize the corpus. Do not open E3+.

## §2 What will bite you

The first production dispatch of #5835 (run 32039517591) failed with `EX-99.1 is absent from the SGML document map`. The exhibit was on the filing (`a8-kex991q3202606272026.htm`). Live EDGAR `-index-headers.html` is HTML-escaped SGML. Copying `collectors.edgar_8k._parse_sgml_manifest` without `html.unescape` reports every exhibit as missing.

A green `read_event_workspace` test against a production-shaped harness is not a live object. That is why E1P existed after #5817.

## §3 What was decided and found

- `DSC:E1-READER-IS-NOT-THE-PRODUCTION-OBJECT` — adapter live ≠ object live.
- `DSC:EDGAR-INDEX-HEADERS-ARE-HTML-ESCAPED` — unescape before DOCUMENT/TYPE/FILENAME.

## §4 Not in scope — do not adopt

Terminal UI, dossier UI, Stage, Earnings Command Center, Peers, slides, Q&A ML, Qwen, global search, Group Reads, TIL, Prophet ranking/sizing/gating, public Wire redesign, render publisher, corpus generalization. Those stay out of E2 as well except the frozen Terminal workspace + Macro dossier glance.
