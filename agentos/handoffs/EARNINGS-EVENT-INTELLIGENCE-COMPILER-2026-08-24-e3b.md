---
workstream: "WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER"
session: claude/e3b-aapl-live-qa
model: local
ended_because: ci_handoff
mission: >
  Implement unlocked E3-B: canonical qa_exchange.v1 adapter/validator,
  AAPL FY2026 Q3 publication into event_workspace.v1, Terminal
  manifest-v2 + Q&A consumer, bounded public glance count. Zero model
  calls. Hold both PRs for Sol. Do not merge, deploy, or start E3-C.
state_before: >
  E3-A2 landed as deterministic shadow reconstruction
  (1158c9a17712084c011581cd68933f09100c2e5a). E3-B was locked. Chairman
  and Sol unlocked E3-B in this commission. Live AAPL transcript SHA
  a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f
  still matches the accepted E3-A2 revision.
changed:
  - path: engine/company_intelligence/qa_exchange.py
    what: Canonical qa_exchange.v1 adapter/validator; SHA-gated AAPL publication; truthful null model provenance; nested event_source_clock.v1 omitted when system_recorded_at is absent.
  - path: engine/company_intelligence/event_workspace.py
    what: Validate every qa_exchange.v1 item and optional nested source_clock; keep parent event_workspace.v1 / manifest v2.
  - path: engine/company_intelligence/event_workspace_build.py
    what: Publish accepted exchanges for the held AAPL revision; suppress unstructured questions_count overlay when Q&A is non-empty.
  - path: app/company_intelligence.py
    what: Public glance derives analyst-question count from accepted qa_exchanges length; never overlay 14; no private provenance leak.
  - path: tests/test_company_intelligence_qa_exchange.py
    what: 7/32/36/26/68 parity, unavailable-only topics, hostile validator mutations, SHA mismatch publishes [].
  - path: agentos/workstreams/WS-EARNINGS-EVENT-INTELLIGENCE-COMPILER.md
    what: E3-B in_progress after Chairman+Sol unlock; E3-A/E3-A2 remain done; E3-C remains locked.
  - path: agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-24-e3b.md
    what: This E3-B implementation return.
prs: []
decisions:
  - DEC:E3-EVENT-INTELLIGENCE-COMPILER-NOT-SCORER
verified:
  - claim: Held AAPL transcript SHA still equals the accepted E3-A2 revision.
    command: python3 -c "import gzip,hashlib,pathlib; p=pathlib.Path('tests/fixtures/company_intelligence/aapl_fy2026_q3.json.gz'); print(hashlib.sha256(gzip.decompress(p.read_bytes())).hexdigest())"
    result: a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f
  - claim: Canonical adapter emits 7/32/36/26 exchanges/spans/turns with topics=["unavailable"] and null provider/model/prompt.
    command: python3 -c "from engine.company_intelligence.qa_exchange import accepted_qa_exchanges_for_transcript, ACCEPTED_QA_TRANSCRIPT_SHA256; import gzip,json,hashlib,pathlib; raw=gzip.decompress(pathlib.Path('tests/fixtures/company_intelligence/aapl_fy2026_q3.json.gz').read_bytes()); segs=json.loads(raw)['segments']; xs=accepted_qa_exchanges_for_transcript(event_id='evt_cik0000320193_2026q3_results', document_id='tx:AAPL/2026Q3', document_sha256=hashlib.sha256(raw).hexdigest(), segments=segs); print(len(xs), sum(len(x['question_spans']) for x in xs), sum(len(x['answer_spans']) for x in xs), sum(len(x['respondents']) for x in xs), xs[0]['topics'], xs[0]['provenance']['model'])"
    result: 7 32 36 26 ['unavailable'] None
unverified:
  - claim: Hosted Macro CI/fences and Terminal required checks have not concluded at handoff write time.
    what_would_verify: gh pr checks on both held draft PRs after push
  - claim: Authenticated production Terminal Q&A proof is deferred until Sol landing approval.
    what_would_verify: post-landing 1440 EN / 820 EN / 390 ZH production browser proof
unresolved:
  - SOURCE_CLOCK_OWNER_GAP: transcript rows have no trustworthy system_recorded_at; nested event_source_clock.v1 is omitted rather than fabricated.
  - Topics remain unavailable-only; no topic-model authority.
  - E3-A2 source-format limitations remain (operator-intro identity grammar).
  - E3-B is BUILT_NOT_PROVEN until Sol lands Terminal then Macro and production proof runs.
next_actions:
  - Sol reviews the two held draft PRs.
  - Landing order after approval: Terminal consumer, then Macro producer, then lawful AAPL workspace rebuild, then production proof.
  - Do not merge, deploy, or start E3-C in this session.
do_not_redo:
  - Do not reopen E3-A or E3-A2 reconstruction method.
  - Do not copy Pass-A topic labels or grant any model authority.
  - Do not revert event_workspace_manifest.v2 to v1.
  - Do not fabricate source_available_at from generated_at, conference time, or wall clock.
  - Do not start E3-C.
danger_areas:
  - Invalid QA must drop to [] without failing the E2 workspace or resurrecting stale v1 quarters.
  - Public glance must not leak hashes, run ids, clocks, or span machinery.
  - A diverged live transcript SHA must publish [] and surface AAPL_TRANSCRIPT_REVISION_DIVERGED, not the old seven exchanges.
---

E3-B is implemented as deterministic structural publication, not a model enrichment wave. Canonical `qa_exchange.v1` is the only producer into `qa_exchanges`. Topics are `["unavailable"]`. Terminal consumes manifest v1 and v2 and strictly normalizes Q&A. Both PRs stay draft/hold/do-not-merge. Status at best: `BUILT_NOT_PROVEN`.
