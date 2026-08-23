---
workstream: "WS:CRYPTO-INTELLIGENCE"
session: claude/p0a-btc-decision-authority
model: codex
ended_because: blocked
mission: >
  Build only P0A BTC Decision Authority Closure on a fresh Macro branch from
  then-current origin/main. Make the final Vector action and target derive from
  one authority, preserve the override seam and provenance receipts, prove the
  rendered desktop/mobile product, and park a Draft PR for Sol. Do not start
  P0B, alerts, broader redesign, merge or deployment.
state_before: >
  Vector's final sizing already came from signals.alloc_optimal after
  btc_overrides.apply(), but S2 still rendered action, tone and a target band
  from the independent legacy btc_recommend result. The Aug 21 evidence shape
  could therefore show a 100% final model allocation beside a defensive 0-10%
  recommendation. The midterm calendar veto had already been retired by
  DEC:BTC-MIDTERM-BLACKOUT-AUTHORITY-RETIRED; no open PR touched the P0A paths
  at the start or final collision checks.
changed:
  - path: .github/ci/legacy-jobs.yml
    what: >
      Wired the new decision suite into the existing Vector organ step with its
      jsonschema dependency and widened the curated picks/boards import closure
      to include engine/btc_decision.py, closing both introduced contract-delta
      findings without creating a new job or weakening scope.
  - path: engine/btc_decision.py
    what: >
      Added the pure deterministic btc.decision/v1 builder. It derives action
      and exact target only from final alloc_optimal, exposes raw/final/override
      provenance, sanitizes advisory-only legacy fields, and fails closed on
      missing or inconsistent authority inputs.
  - path: contracts/btc_decision.schema.json
    what: >
      Added the machine contract for valid ok and unavailable decision states,
      including conditional action requirements, bounded exposures and
      integrity receipts.
  - path: tests/test_btc_decision.py
    what: >
      Added deterministic cases for the Aug 21 split-brain shape, Kelly zero,
      bearish legacy context, mismatch/override integrity, missing inputs,
      exact 10 percentage-point thresholds, JSON safety, schema validity,
      bilingual numeric parity and the Vector consumer boundary.
  - path: scripts/build_vector.py
    what: >
      Builds one DecisionState after the lawful override seam and passes only
      that object to the Vector template. The legacy recommendation remains
      available only as sanitized advisory levels/rationale and is no longer a
      template action or sizing object.
  - path: templates/vector.html.j2
    what: >
      Renders S2 action, exact target, direction and tone exclusively from
      DecisionState, with a fail-closed unavailable state and authority receipt.
      It removes the legacy target band and legacy action/tone consumers without
      changing the established Vector component language.
  - path: site/vector.html
    what: >
      Regenerated the paired product artifact from the refreshed main data and
      source. Its decision marker reports btc.decision/v1, status ok and exact
      final exposure 100 for the current stored-data render.
  - path: site/assets/css/e7978af3.css
    what: >
      Added the content-addressed stylesheet emitted by the normal Vector
      externalize-and-stamp chain after the template changed.
  - path: verify_shots/p0a_btc_decision/vector_s2_desktop_dark_zh.png
    what: "Desktop dark-theme Chinese S2 authority proof."
  - path: verify_shots/p0a_btc_decision/vector_s2_desktop_light_zh.png
    what: "Desktop light-theme Chinese S2 authority proof."
  - path: verify_shots/p0a_btc_decision/vector_s2_mobile_dark_zh.png
    what: "390px mobile dark-theme Chinese S2 authority proof."
  - path: verify_shots/p0a_btc_decision/vector_s2_mobile_light_en.png
    what: "390px mobile light-theme English S2 authority proof."
  - path: agentos/handoffs/CRYPTO-INTELLIGENCE-2026-08-23-p0a-btc-decision.md
    what: >
      Added this cold-stranger record of the exact P0A boundary, evidence,
      held state, release condition and forbidden adjacent work.
  - path: agentos/workstreams/WS-CRYPTO-INTELLIGENCE.md
    what: >
      Registered the existing crypto-intelligence program's P0A/P0B boundary in
      the canonical knowledge plane: P0A build wave complete but parked for Sol,
      P0B todo and uncommissioned, with no execution or merge authority implied.
prs: [6294]
verified:
  - claim: >
      The CI manifest wiring and curated import-closure repair satisfy the
      manifest planner's adversarial unit contracts.
    command: >-
      PYTHONDONTWRITEBYTECODE=1 python3 -B -m pytest -q
      tests/test_btc_decision.py tests/test_contract_delta.py
      tests/test_ci_pack.py tests/test_ci_plan_workflow.py
    result: "167 passed; only three pytest temporary-directory cleanup warnings."
  - claim: >
      The deterministic decision, BTC authority, Vector, asset and site-reference
      regression set passes in a full checkout on the refreshed branch.
    command: >-
      PYTHONDONTWRITEBYTECODE=1 python3 -B -m pytest -q
      tests/test_btc_decision.py tests/test_btc_overrides.py
      tests/test_btc_signals.py tests/test_btc_mastermind.py
      tests/test_vector_kelly.py tests/test_vector_wave1.py
      tests/test_btc_strategy_shared.py tests/test_vector_timeline_gated.py
      tests/test_externalize_css.py tests/test_optimize_assets.py
      tests/test_check_site_asset_refs.py
    result: "199 passed; only three pytest temporary-directory cleanup warnings."
  - claim: >
      A real stored-data Vector render publishes one final action and exact target,
      and does not publish the conflicting legacy action or target band.
    command: >-
      In a disposable full detached worktree, monkeypatch only
      scripts.notify.send_telegram to a no-op, wrap build_vector.write_page to
      stop immediately after writing vector.html, run build_vector.main(), then
      assert the rendered S2 marker and text with a Python invariant script.
    result: >
      P0A_VECTOR_RENDER_COMPLETE and P0A_RENDERED_INVARIANT_OK; schema
      btc.decision/v1, status ok, final exposure 100, HOLD 100% BTC and
      持有 100% BTC present; STAY DEFENSIVE and 0–10% absent. Raw and final
      exposure were both 100%, override active false, Kelly receipt 10%,
      continuous momentum +0.8821755, categorical momentum bull and risk 9.288.
  - claim: >
      The refreshed generated page carries every content-addressed dependency
      and does not break a plain-copy template/site pair.
    command: >-
      python3 scripts/check_template_site_sync.py &&
      python3 scripts/check_site_asset_refs.py site &&
      python3 -m json.tool contracts/btc_decision.schema.json >/dev/null
    result: >
      template-to-site sync OK for 91 pairs; every template-decided site href/src
      resolves with zero gaps; schema JSON parses.
  - claim: >
      The final decision surface is responsive and bilingual across both themes.
    command: >-
      Serve site/ on 127.0.0.1; use the in-app Browser viewport capability at
      1440x1000 and 390x844; inspect the S2 DOM marker/text/scroll geometry;
      exercise dark/light and EN/ZH settings; capture the four proof images;
      read page-origin warning/error logs.
    result: >
      Desktop and mobile both reported decision status ok and exposure 100;
      document scrollWidth did not exceed clientWidth at either viewport; all
      four proof images show the exact 100% action/target; browser warnings and
      errors were empty.
  - claim: >
      Legacy btc_recommend output can no longer set Vector S2 action, tone,
      target band, Kelly target, direction, basis or conviction.
    command: >-
      rg -n "rec\\.(action|tone|exposure_lo|exposure_hi|kelly|direction|basis|conviction)|alloc_pct"
      templates/vector.html.j2 scripts/build_vector.py tests/test_btc_decision.py
    result: >
      No production consumer remains; only negative/static-guard assertions in
      tests/test_btc_decision.py match the forbidden field names.
  - claim: >
      The browser evidence files are stable, named receipts in the PR.
    command: "shasum -a 256 verify_shots/p0a_btc_decision/*.png"
    result: >
      desktop dark zh 958c2bd5959c99227918a87bd733c180d82cd11d9b4d598a9b7cbd627450fc83;
      desktop light zh b5827f715916bd655bb63def4b4f57fbf7648bceb38ddfb6d0caa75dbbd295d5;
      mobile dark zh d05c610c3ba23f6036997f07a497d6f7fbd1f94dab3c85e4f636b24bf7c868fc;
      mobile light en 8a51a85732363a609c885a5538a57171af7bbb4ebeea63988802bed6443acd85.
unverified:
  - claim: "Sol accepts the exact P0A implementation and authorizes release of the hold."
    what_would_verify: >
      Sol reviews the final pushed PR #6294 head, explicitly accepts P0A and
      explicitly authorizes the PR to leave Draft / merge. CI green alone is
      not that authorization.
  - claim: "P0B Crypto H5 authority closure, alerts or broader redesign are complete."
    what_would_verify: >
      Separate Sol directives and separately bounded implementation/review
      programs. None may be inferred from P0A acceptance.
unresolved:
  - >
    Sol has not reviewed or accepted PR #6294. The implementation is therefore
    PARKED / HOLD-FOR-SOL even if every binding check concludes green.
next_actions:
  - >
    Sol reviews Draft PR #6294 at its final exact head. Keep the PR Draft, keep
    merge-on-green absent, keep native auto-merge null, and do not deploy while
    review is pending.
  - >
    If Sol rejects any P0A behavior, repair only the named defect on this held
    branch, rerun the focused/schema/real-render/browser matrix and return a new
    exact head for review.
  - >
    If Sol explicitly accepts and releases the hold, a new authorized session
    may move the PR out of Draft and follow the repository's then-current merge
    and live-verification rules. This session must not infer that release.
  - >
    Keep P0B Crypto H5 authority closure, alerts and broader crypto redesign
    unstarted until separately authorized.
do_not_redo:
  - >
    Do not restore a midterm-election calendar allocation veto. It was retired
    by DEC:BTC-MIDTERM-BLACKOUT-AUTHORITY-RETIRED; calendar state is context only.
  - >
    Do not replace btc_overrides.apply() with another override seam or add a
    second allocation authority. Final action and target must continue to use
    signals.alloc_optimal after that seam; alloc_optimal_raw remains a receipt.
  - >
    Do not delete btc_recommend or broaden P0A into recommendation redesign. Its
    lawful residue is advisory levels/rationale after allowlist sanitization.
  - >
    Do not commit the disposable render's override ledger, shadow, regime ledger
    or signals.parquet writes. They were isolated and intentionally excluded;
    only the normalized site/vector.html and its new CSS asset belong in P0A.
  - >
    Do not merge, deploy, arm merge-on-green, enable auto-merge or mark this work
    shipped merely because CI is green. Sol review is the release authority.
danger_areas:
  - >
    A standalone build_vector.main() mutates Vector ledgers and signal parquet
    before it writes the page. Repeat product renders in a disposable full
    worktree and copy only the normalized page/CSS output into the held branch.
  - >
    The raw/final integrity gate intentionally fails closed when the values
    differ without an active named override, or when an active override lacks
    an identifier. Do not weaken that gate to keep a page superficially green.
  - >
    Generated vector.html must pass inline CSS externalization and asset
    stamping. Committing raw write_page output inlines the full stylesheet and
    drops the content-hashed dependency contract.
  - >
    DecisionState stores precise exposure as a 0..1 fraction and change as
    percentage points; the present Vector display rounds the exact target to an
    integer for established UI parity. Do not confuse those units in new tests
    or consumers.
---

## §0 State — what is true right now

P0A is repository-built and proven on Draft PR #6294, but it is not accepted,
merged, deployed or live. Vector S2 now has one action and one exact target from
the post-override final allocation; the current stored-data render says HOLD
100% BTC in both languages and contains no legacy defensive 0–10% instruction.
The PR is intentionally PARKED / HOLD-FOR-SOL.

## §1 What is LEFT — in order

1. Let every binding check on the final PR head conclude, repairing only a real
   P0A failure. Do not release the hold based on green checks.
2. Sol reviews the exact final PR #6294 head and either rejects a named behavior
   or explicitly accepts and releases P0A.
3. Only after an explicit Sol release may a new authorized session change the
   Draft/merge state. P0B, alerts and redesign still require separate authority.

## §2 What will bite you

The Vector builder writes ledgers and parquet before the HTML, so a product
proof run in the held branch would mix unrelated data churn into the repair.
The generated page also needs the externalize-and-stamp post-pass; raw builder
HTML is not the committed artifact shape. Finally, a raw/final mismatch without
an active named override is an integrity failure, not a reason to choose whichever
number makes the page look coherent.

## §3 What was decided and found

No new Decision or Discovery record was minted. The binding prior decision is
DEC:BTC-MIDTERM-BLACKOUT-AUTHORITY-RETIRED: election-calendar state is context,
not allocation authority.

## §4 Not in scope — do not adopt

P0B Crypto H5 authority closure, alerting, recommendation redesign, broader
Vector redesign, new override mechanisms, merge and deployment were not started.
The legacy recommender remains intentionally present behind an advisory allowlist;
its removal or redesign would be a different program.
