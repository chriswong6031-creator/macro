---
workstream: WS:FUNDAMENTAL-FORENSICS
session: claude/ff-0-freshness-truth
model: local
ended_because: complete
prs: [5794]

mission: >
  FF-0 — Freshness Truth and Visible Degradation. Add the health contract and
  authenticated GET /api/forensics/health, display current/stale/degraded/unavailable
  without presenting render time as source freshness, rename the primary CTA to
  Open signal analysis and make it open a visible desktop analysis panel. Open
  one PR after acceptance evidence, write this handoff, and stop. Do not start FF-1.

state_before: >
  Filing Forensics already composed private gzip state with generated_at taken from
  the EDGAR/source clock, served it at authenticated GET /api/forensics/state, and
  labelled the workbench "Last refreshed". The primary CTA copy was "See why it
  matters"; openEvidence() returned early on desktop, so the button only focused a
  finding in an already-visible sticky column.

changed:
  - path: engine/fundamental_forensics/health.py
    what: "Health contract (schema fundamental_forensics.health.v1) classifying
      source clocks, age_seconds, current/stale/degraded/unavailable, and stable
      reason codes. Render/evaluation time is evaluated_at only."
  - path: contracts/fundamental_forensics_health.schema.json
    what: "Draft 2020-12 schema for the health document; additionalProperties false."
  - path: engine/fundamental_forensics/private_state.py
    what: "LoadedState plus origin tracking (local/r2/last_good/missing) so a
      stale last-good blob classifies as degraded rather than silently current."
  - path: app/forensics.py
    what: "Authenticated GET /api/forensics/health returning JSON with private,
      no-store headers. 200 even when unavailable so the UI can paint the state."
  - path: templates/fundamental_forensics.html.j2
    what: "Four-cell source-freshness meta; CTA copy Open signal analysis / 打开信号分析;
      asset stamp ?v=20260816-ff0. Paired site HTML re-rendered from the shell."
  - path: templates/fundamental_forensics.js
    what: "loadHealth/applyHealth/renderRunMeta; openAnalysisDrawer on every
      viewport including desktop; __FF_WORKBENCH_TEST__ seam that skips init()."
  - path: templates/fundamental_forensics.css
    what: "Four freshness colors; desktop .ff-evidence.is-open overlay and
      ff-analysis-open animation. Run-meta stays visible when gated."
  - path: tests/test_fundamental_forensics_health.py
    what: "FF-0 acceptance: July 12 stale under August clock, current fixture,
      missing unavailable, last-good degraded, rerender does not advance source
      freshness, health endpoint leak/auth checks."
  - path: tests/fundamental_forensics_cta_contract.test.mjs
    what: "Desktop drawer transition (is-open + data-analysis-open + scrim) and
      health paint that refuses evaluated_at as the source snapshot."

verified:
  - claim: "July 12 source fixture is stale under an injected August clock; current fixture is current; missing state is unavailable; last-good fallback is degraded when stale; rerendering cannot advance source freshness; health JSON matches the schema and leaks no private rows, credentials, or storage keys."
    command: "PYTHONPATH=$PWD /Users/chriswong/Documents/Cluade/Macro\\ Dashboard/.venv/bin/python -m pytest tests/test_fundamental_forensics_health.py tests/test_fundamental_forensics_ui.py tests/test_fundamental_forensics_page.py tests/test_fundamental_forensics_private_state.py tests/test_forensics_api.py -q"
    result: "83 passed"
  - claim: "CTA opens a visible analysis drawer on desktop; health states paint current/stale/degraded/unavailable without using evaluation time as source freshness."
    command: "node --test tests/fundamental_forensics_cta_contract.test.mjs tests/fundamental_forensics_receipt_contract.test.mjs"
    result: "7 passed"
  - claim: "Template and site JS/CSS pairs match."
    command: "python3 -m scripts.check_template_site_sync"
    result: "template↔site sync OK (88 pairs checked)"

unverified:
  - claim: "Live VPS workbench at https://www.mastermind-x.com/fundamental_forensics.html shows the four freshness states and the analysis drawer after this PR merges and the 3-minute pull (JS/CSS) plus any covering render (HTML shell)."
    what_would_verify: "After merge, signed-in GET /api/forensics/health on the VPS returns the contract, the run-meta data-freshness attribute is one of current/stale/degraded/unavailable, Source snapshot is not wall-clock render time, and Open signal analysis adds is-open to #ff-evidence on a >=1100px desktop viewport."

unresolved:
  - "private_object_at is null in this wave (gzip mtime is 0; no R2 LastModified without a new collector). Hash and origin are present."
  - "This session stops at an open PR per the FF-0 stop condition and does not squash-merge or live-verify."

next_actions:
  - "Do not start FF-1."
  - "Wait for CI on the FF-0 PR to conclude, then squash-merge and delete the remote branch."
  - "Verify live: health endpoint 200 with private/no-store, run-meta data-freshness, Open signal analysis desktop drawer."

do_not_redo:
  - "Do not present render time or evaluated_at as source freshness. generated_at on the composed state is the source clock."
  - "Do not add a new SEC collector, change detectors, wire Prophet, redesign attested history, or expand the metric registry to finish FF-0."
  - "Do not restore the desktop early-return in openEvidence(); the CTA must open the analysis drawer."
  - "Do not put assert_no_private_leak on the request path."

danger_areas:
  - "A write into sparse-omitted data/ truncates the committed artifact. Health reads public_summary.json when present; tests inject clocks instead."
  - "last-good origin is an in-process cache fallback after R2 failure. A still-valid TTL returns origin r2; tests expire with cache_seconds=0."
  - "Health is 200 when unavailable so the UI can paint the state. /api/forensics/state still 503s on a missing blob."
---
