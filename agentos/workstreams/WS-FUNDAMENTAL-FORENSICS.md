---
key: FUNDAMENTAL-FORENSICS
title: Filing Forensics — source-preserving SEC evidence workbench
objective: >
  Make Filing Forensics tell the truth about operational and source freshness,
  then keep later waves (FF-1+) from starting until FF-0 is merged and verified
  live. Done for FF-0 = authenticated health contract, four explicit freshness
  states on the workbench, render time never shown as source freshness, and
  "Open signal analysis" opening a visible desktop analysis drawer.
status: awaiting_ci
program: fundamental-forensics
repos: [macro]
owner: coo-fable
class: build
blast_radius: user_facing
ambiguity: specified
owns_paths:
  - engine/fundamental_forensics/
  - app/forensics.py
  - templates/fundamental_forensics.html.j2
  - templates/fundamental_forensics.js
  - templates/fundamental_forensics.css
  - contracts/fundamental_forensics_health.schema.json
  - tests/test_fundamental_forensics_health.py
waves:
  - id: FF-0
    title: Freshness truth and visible degradation
    status: awaiting_ci
    pr: 5794
  - id: FF-1
    title: Next forensics wave (forbidden until FF-0 is merged and live-verified)
    status: todo
    depends_on: [FF-0]
landmines:
  - "composed-state generated_at is the EDGAR/source clock, reported as broad_source_at only. It is never composed_state_at, last_successful_build_at, last_publication_at, or private_object_at."
  - "Source freshness SLA is 4 days (daily pipeline + weekend + one missed night). Do not reuse PUBLIC_SUMMARY_MAX_AGE_DAYS (30) as a freshness claim."
  - "GET /api/forensics/health must stay a clocks/status document. Putting assert_no_private_leak in the request path would 500 a paid route; leak checks belong in tests."
  - "Desktop evidence used to early-return in openEvidence(); the CTA only focused a finding. The analysis drawer (is-open + data-analysis-open + scrim) is the FF-0 visible transition."
  - "Session worktrees are sparse by default. Never write into omitted data/ — that truncates the committed artifact."
do_not_redo:
  - "Do not add a new SEC collector, change detectors, wire Prophet, redesign attested history, or expand the metric registry in FF-0's blast radius."
  - "Do not present page render time or evaluated_at as source freshness."
  - "Do not relabel generated_at or public_summary generated_at as a build, composition, or publication clock."
  - "Do not start FF-1 from this record until FF-0 is merged and the live workbench shows the four freshness states plus the analysis drawer."
next_action: After CI concludes on the FF-0 PR, squash-merge, verify live freshness states and the Open signal analysis drawer, and only then commission FF-1.
---

## Context

FF-0 is the freshness-truth wave for the existing Forensics workbench. It adds
`engine/fundamental_forensics/health.py`, `GET /api/forensics/health` (site_full,
`private, no-store`), four explicit UI states, and a desktop analysis drawer
behind the renamed CTA. No detector, collector, Prophet, or attested-history
redesign.
