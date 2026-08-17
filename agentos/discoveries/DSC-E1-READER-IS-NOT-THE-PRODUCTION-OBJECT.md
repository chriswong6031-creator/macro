---
key: E1-READER-IS-NOT-THE-PRODUCTION-OBJECT
claim: >
  E1 (#5817) shipped a real HTTP reader and a production-shaped test harness
  for event_workspace.v1, but that does not mean the public R2 object exists.
  On 2026-08-17 the v1 Company Intelligence marker returned HTTP 200 while
  company_intelligence/event_workspaces/manifest.json returned HTTP 404, so
  read_event_workspace returned available:false / authority:context_only.
falsifier: >
  GET https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/company_intelligence/event_workspaces/manifest.json
  returns HTTP 200 with event_workspace_manifest.v1 AND
  read_event_workspace({"event_id":"evt_cik0000320193_2026q3_results"}) returns
  available:true without a publisher having written that nest.
so_what: >
  Never declare an earnings capability live because its adapter works against a
  fixture or a production-shaped test origin. Real input must travel the real
  Company Intelligence publication lane onto the frozen sibling nest before E2
  may render it. A green reader test is not a live object.
kind: landmine
verified_at: 2026-08-17
verified_by: >
  curl -sI -A Mozilla/5.0
  https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/company_intelligence/event_workspaces/manifest.json
  → HTTP 404; sibling v1 company_intelligence/manifest.json → HTTP 200;
  PR #5817 merged as 5d600641bc35 without wiring company-intelligence.yml.
scope:
  - macro
  - earnings-intelligence
  - engine/company_intelligence/**
  - engine/neuralweb/company_intelligence_reader.py
  - .github/workflows/company-intelligence.yml
confidence: verified
---

The freeze caught this: E1 implementation is accepted; E1P is the production
activation; E2 stays blocked until the public marker is 200.
