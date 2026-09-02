---
workstream: "WS:PROPHET-CANDIDATE-ADDED-DATE"
session: claude/prophet-candidate-added-date-e2e-20260901 (Fable principal 053db3b7-bfca-42e9-95e5-23971b8bb26d)
model: fable
ended_because: complete
mission: >
  Operation prophet-candidate-added-date-fable-e2e-20260901-sol-001: restore the
  truthful Prophet candidate "Added date" chip across all five boards end-to-end —
  implementation, two adversarial review rounds with repairs, dual-theme visual
  evidence, Sol CONTINUE-HOLD compliance, Chairman-approved release, merge, covering
  render, and live five-surface production verification.
state_before: >
  Capability NOT_BUILT on canonical main; predecessor Grok child terminal with draft
  #6687 preserved as read-only prior art (resolver fabricated dates under
  left-censoring; Intl loader used git subprocesses dead on the render lane); HK/CA
  candidate cards still shipped a misleading signal.asof/setups.as_of date; HK, CA
  and Intl had no board-level "Data through" freshness disclosure.
changed:
  - path: engine/prophet_board_since.py
    what: "New pure resolver: (date, basis) provenance, left-censoring guard, membership-vs-display lane law, per-market coverage floor, Intl artifact carry-forward. No subprocesses, no new store."
  - path: templates/_prophet_card.html.j2
    what: "Distinct added_date pv_card param; .pv-added chip (EN Added <Mon D> / ZH 入榜 <MM-DD>), strict-ISO gate, null renders nothing, data-tip-en/zh tooltip; zone value never clips (chip degrades first)."
  - path: scripts/build_site.py + build_china.py + build_hk.py + build_canada.py + build_intl.py + build_intl_library.py + build_china_library.py
    what: "Once-per-board fail-open enrichment on all five markets; CN more_actionable forward persistence under a distinct board_definition with a zero-featured-night guard."
  - path: templates/hk.html.j2 + canada.html.j2 + intl.html.j2 + _us_board_cards.html.j2 + china.html.j2
    what: "All candidate cards pass added_date with date:none (misleading as-of removed from HK/CA/Intl); HK/CA/Intl gained Data-through freshness lines."
  - path: tests/ (4 suites) + .github/ci/legacy-jobs.yml + tests/test_p_mp1_shell_nonus_byte_parity.py
    what: "95 RED-first tests; contract-delta path widenings; parity guards converted to merge-safe SHA-256 byte pins (incl. the inherited stocktablejs red)."
  - path: mockups/refs/prophet-candidate-added-date-e2e/
    what: "Committed dual-theme evidence matrix from real page builds (40 cells + refresh), EVIDENCE.md with measured ink/subordination packet."
verified:
  - claim: "Feature is live on production for all five boards with the accepted semantics."
    command: "curl -sL https://www.mastermind-x.com/{us,china,hk,canada,intl}_stocks.html | grep -c 'data-added=\"20' / 'pv-added' / 'Data through' (2026-09-02T02:4xZ, post render 33573672885 success at merge SHA 4327fcd6242037)"
    result: "PASS — US 3 chips with data-added=2026-08-31 + tooltip; CN/HK/CA/Intl 0 chips (truthful nulls) with a freshness disclosure on every page; no candidate-card as-of leakage (pv-dt hits are plan cards)."
  - claim: "All binding CI concluded green on the immutable release candidate."
    command: "gh pr checks 6719 (head fce4f69804c8): 35 passes — contract-delta, hosted-plan, main-admission, 12 trusted-executor packs, fences/self-mod/grader, ci-gate."
    result: "PASS — sole non-green was the documented non-binding merge-queue-pilot status context."
  - claim: "Resolver truth-table and repairs independently confirmed."
    command: "Opus reviewer (non-author), three passes: full adversarial review (FAIL -> repaired), repair-delta review (FAIL -> repaired), round-3 delta review on becf409188ce (PASS; merge-base==HEAD simulation clean; live-fossil stamps HK/CA all-None, US 40/40; pv_css SHA re-derived byte-identical)."
    result: "PASS with disclosures D1 (day-one chips are US-only), D2 (CN hijack guard suite tests the predicate, mechanism verified by source reading)."
  - claim: "Dual-theme experience judged as designs, not just rendered."
    command: "Opus designer, two passes: 40-cell matrix (5 boards x dark/light x EN/ZH x 1440/390) from real builds + refresh after round-3; zone clipping 0/40 (was 3/3 US, 22/24 CN); measured subordination dark 1.99x / light 1.64x."
    result: "PASS — with finding F9 (pre-existing token architecture: light-theme US zone shelf paints above the card; judge any future chip emphasis light-first)."
unverified:
  - "Nightly persistence: continuing US names retaining their Added dates across the
    next real nightly advance (one-shot check scheduled by the closing session;
    contract behavior is unit-proven, live receipt pending the next daily run)."
  - "CN date accrual in production (structurally begins only after the first
    post-merge nightly writes more_actionable fossil rows)."
  - "Intl chips remain null until the upstream intl_setups.json as_of null is
    repaired (separate defect, pre-existing)."
do_not_redo:
  - "Do not re-attempt HK/CA date coverage by writing display-tier lanes into
    board_ledger under the live definitions — it corrupts Spearman rank-IC grading;
    a coverage extension needs its own rank-authority-safe program and authorization."
  - "Do not 'fix' CN launch nulls by trusting pre-floor absence-proofs — that is the
    exact fabrication class this program exists to prevent
    (DSC:PROPHET-BOARD-TENURE-COVERAGE-FLOOR)."
danger_areas:
  - "tests/test_p_mp1_shell_nonus_byte_parity.py byte pins must be updated (never
    weakened) by any PR touching the pinned templates/pv_css."
  - ".github/ci/legacy-jobs.yml curated exclusive scopes: new imports reaching
    build/serving closures require contract-delta path widenings (widen, never
    narrow)."
unresolved:
  - "Intl upstream as_of is null (pre-existing defect outside this program's scope);
    Intl chips stay null until it is repaired."
  - "HK/CA ledger coverage extension is wanted-but-unauthorized; without it their
    chips remain null by design."
next_actions:
  - "Confirm the nightly-persistence receipt: US live cards retain their Added dates
    after the next real daily run, and a more_actionable row appears in CN's fossil
    (starting its floor)."
  - "Flip WS:PROPHET-CANDIDATE-ADDED-DATE status to done once that receipt lands."
  - "If HK/CA coverage is ever wanted, commission the rank-authority-safe ledger
    coverage extension as a NEW authorized program (see do_not_redo)."
links:
  - "PR #6719 (merged 4327fcd6242037, 2026-09-02T00:02:59Z, Chairman-approved release over the Sol hold)"
  - "PR #6687 (closed as superseded, branch preserved as evidence)"
  - "Program carrier: Slack #agent-dispatch C0BSBM78V1N/1788258398.440699"
  - "DSC:PROPHET-BOARD-TENURE-COVERAGE-FLOOR"
---

# Prophet candidate Added date — end-to-end closeout

Cold-stranger summary: the chip is live and truthful. US shows real dates today;
CN/HK/CA/Intl show none because their histories cannot yet prove any — CN accrues
automatically from the first post-merge nightly, HK/CA need a separately authorized
ledger coverage extension, Intl needs its upstream as_of repaired. Every semantics
decision, review receipt, and Sol/Chairman authority edge is on the program carrier.
