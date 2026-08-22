---
workstream: WS:DEFENSE-PROCUREMENT-V3
session: claude/d4-1-receipt-fail-closed
model: fable
ended_because: blocked
prs: [6173]
decisions: []
discoveries: []

mission: >
  Sol D4 closeout directive (2026-08-21): final D4 acceptance withheld on
  exactly two gates. Gate 1 (D4.1): remove the last fail-open receipt
  substitution in receiptUrl() and pin it with hostile regressions +
  mutation discipline. Gate 2 (D4P): prove the real successful
  company-packet state inside the real entitled production IRDM dossier.
  No product broadening, no D5, no D4 architecture reopen.

state_before: >
  D4 merged and live (#6123 merge b5548ece927d, #6134 seal). Shipped
  receiptUrl() did `exact-sha match || rows[0]` — if
  award_change.source_identity.content_sha256 existed with no matching
  evidence receipt, an unrelated first receipt could render as "Open
  official receipt" (the award-snapshot-vs-transaction class R4 was meant
  to kill). No entitled production proof existed (Chrome extension not
  connected in the D4 session either).

changed:
  - path: templates/government-revenue-dossiers.js
    what: >
      receiptUrl() rewritten fail-closed per Sol's frozen rule: no
      wantSha => no link; no exact content_sha256 match => no link;
      safeUrl-rejected URL => no link. No positional / URL-shape /
      nearest-receipt fallback. Government facts still render; only the
      link disappears. R14 comment block records the law. Site twin
      byte-identical (site/government-revenue-dossiers.js).
  - path: tests/test_government_revenue_company_bridge.py
    what: >
      Four hostile regressions in the merge-binding gate:code suite
      govrev-company-bridge: R14a (sha present, no receipt carries it,
      decoys present => no source-link, no decoy URL), R14b (three
      variants: source_identity absent / content_sha256 key missing /
      empty => no link, no substitution), R14c (exact match but
      javascript: URL => safeUrl rejects => no link), R14d (static pin:
      shipped receiptUrl() source must contain no `rows[0]` and no
      `|| rows` fallback). Existing R4 case-A test stays green.
  - path: research/defense_intelligence/DEFENSE_D4_COMPANY_FINANCIAL_TRUTH_BRIDGE_SPEC.md
    what: >
      §4 "D4.1 amendment (2026-08-21, Sol closeout)" records the
      fail-closed receipt link law.
  - path: agentos/workstreams/WS-DEFENSE-PROCUREMENT-V3.md
    what: >
      D4 wave records the Sol re-review, the D4.1 close, and the D4P
      blocked state; root next_action = D4P entitled proof then Sol final
      acceptance (this PR).

verified:
  - claim: D4.1 merged on concluded green and live at the serving checkout.
    command: >
      gh pr view 6173 --json state,mergeCommit (MERGED, merge
      8f10699e118b8b9c4f127985fe6333bd8f6944e2, 2026-08-21T09:39:37Z; sole
      red = red-by-design ci-authority/codex/merge-queue-pilot); curl
      /api/health => checkout 6590e678c60; git merge-base --is-ancestor
      8f10699e 6590e678c60 => live; git show
      6590e678c60:site/government-revenue-dossiers.js => fail-closed body,
      zero `|| rows[0]` remnant.
  - claim: Mutation discipline holds.
    command: >
      Builder reintroduced `|| rows[0]` in the worktree => pytest -k r14 =>
      5 failed (R14a, R14b x3, R14d); reverted => 33 passed. Full suites:
      bridge 33 passed, UI 46 passed; check_template_site_sync OK (91
      pairs).
  - claim: Page fence not ratcheted.
    command: >
      Standalone _write_site_projection bake => 296,729 bytes;
      RAW_HTML_BUDGET_BYTES 303,104 unchanged; headroom 6,375.
  - claim: Anonymous negative controls intact post-D4.1.
    command: >
      curl anon: government-revenue-dossiers.js => 401; workspace.json =>
      {"locked":true,"reason":"authentication_required"};
      government_revenue.html => 200, bridge host present as hidden markup
      only.
  - claim: Live owner packet state at block time.
    command: >
      curl /api/company-intelligence/IRDM =>
      company_intelligence_context.v1, available true, generated_at
      2026-08-21T06:53:16Z, latest_event cie_77ff210df9c064c3b2fe4aa1,
      FY2026 Q1 / call 2026-04-23, claim_citations_pending true.

unverified:
  - >
    D4P (Gate 2) — the entitled happy-path production proof. NO entitled
    browser mechanism existed: claude-in-chrome list_connected_browsers
    returned [] on repeated checks 2026-08-21; agent credential entry is
    prohibited; workspace.json is auth-locked so receipt-sha equivalence
    has no anonymous shortcut. Honest state per Sol's protocol: D4.1
    merged; D4 = BUILT_NOT_PROVEN; BLOCKED_ON_ENTITLED_PRODUCTION_PROOF.
    No fixture substitute was performed.

unresolved:
  - >
    D4P entitled production proof (the only remaining D4 gate) — see
    next_actions. Separate standing follow-ups NOT part of this closeout:
    publisher-vintage alarm; fixture-freezing the D2/D3 law suites out of
    the unrun-government-revenue advisory holding pen.

next_actions:
  - >
    When an entitled site_full browser session exists (operator connects
    the Claude Chrome extension in a signed-in Chrome, or another
    authorized mechanism): run Sol's D4P journey on
    government_revenue.html?mode=companies&item=company:IRDM — success
    company-packet state beside P00032, live receipt sha ==
    award_change.source_identity.content_sha256 (prove the sha, not the
    URL shape), record LIVE generated_at/latest_event (do NOT pin old
    values), 1280 EN / 768 EN / 375 ZH, LMT negative (no bridge node,
    zero /api/company-intelligence/LMT fetches), anon control, no
    console errors, no fetch storm. Then set D4 to done / SOL ACCEPTANCE
    PENDING and return to Sol.

do_not_redo:
  - "Do not reopen D4 architecture or the gate:code CI home (suite stays in govrev-company-bridge; unrun-government-revenue is the advisory holding pen)."
  - "Do not substitute a local fixture proof for D4P."
  - "Do not weaken receiptUrl() fail-closed law: no positional, URL-shape, or nearest-receipt fallback, ever."
  - "Do not start D5, mark it in_progress, or pre-build any of it."
  - "Do not ratchet RAW_HTML_BUDGET_BYTES (303,104)."

danger_areas:
  - "amountValue() also uses rows[0] — that is an id-keyed amounts-row picker, NOT receipt provenance; leave it unless Sol rules otherwise."
  - "The merge-on-green sweeper base-refreshed the PR branch mid-wait (merge of main by the shared account); the refreshed head reruns all packs — wait for the NEW run, the old green does not cover the new head."
  - "Anon-served government_revenue.html body size differs from the local bake (271,056 vs 296,729 observed) — anon variant/live-lane data movement; fence applies to the built artifact, not the anon-served body."
---
