---
workstream: "WS:CRYPTO-INTELLIGENCE"
session: claude/p0a-btc-decision-authority
model: codex
ended_because: ci_handoff
mission: >
  Build and repair only P0A BTC Decision Authority Closure on the existing Macro
  branch and PR #6294. After Sol accepted exact source head 9ce6ce711602, merge
  current main normally, relinquish feature ownership of generated Vector bytes,
  preserve the accepted source blobs exactly, prove the reconciliation head, and
  release only through the repository's normal merge and canonical render lanes.
  Do not start P0B, alerts or broader redesign.
state_before: >
  Vector's final sizing already came from signals.alloc_optimal after
  btc_overrides.apply(), but S2 still rendered action, tone and a target band
  from the independent legacy btc_recommend result. The Aug 21 evidence shape
  could therefore show a 100% final model allocation beside a defensive 0-10%
  recommendation. The initial P0A implementation closed that display split but
  Sol returned two integrity defects: a 0.4 percentage-point raw/final mismatch
  could pass without an override, and a corrupt most-recent prior allocation
  could be skipped in favor of an older valid row. The held branch also needed
  a current-main reconciliation. The midterm calendar veto had already been
  retired by DEC:BTC-MIDTERM-BLACKOUT-AUTHORITY-RETIRED.
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
      missing or inconsistent authority inputs. Sol-return repair
      667ea437021e removes the economically meaningful raw/final tolerance
      (retaining only 1e-12 representation jitter in allocation fractions) and
      refuses an invalid or out-of-range most-recent non-null prior allocation
      without searching farther back.
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
      bilingual numeric parity and the Vector consumer boundary. The Sol-return
      matrix adds 0.4 percentage-point mismatch with and without an active named
      override, floating-point representation jitter, and latest-prior values
      1.20, -0.10, infinity and non-numeric corruption with schema-valid
      unavailable receipts.
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
      Removed from the P0A feature delta during Sol's release reconciliation.
      Normal merge 78b07d80b9f7 resolves the generated page to exact current-main
      bytes at pickup 5ad13e2ed335. Canonical post-merge render.yml, not the
      feature branch, owns publication of the accepted template/source changes.
  - path: site/assets/css/e7978af3.css
    what: >
      Removed as an orphaned feature-render artifact after current main was
      verified to neither contain nor reference it. No main-owned asset was
      deleted.
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
      Updated this cold-stranger record with Sol's exact-source acceptance and
      release reconciliation: old accepted head 9ce6ce711602, current-main
      pickup 5ad13e2ed335, and normal merge 78b07d80b9f7. The record now makes
      canonical render ownership explicit and retains the P0B boundary. The
      final self-containing handoff commit is identified by the exact PR-head
      receipt because a tracked file cannot contain its own commit hash.
  - path: agentos/workstreams/WS-CRYPTO-INTELLIGENCE.md
    what: >
      Updated the existing crypto-intelligence program boundary for Sol's P0A
      release: reconciliation is active, canonical render/live proof remains
      pending, and P0B remains todo and uncommissioned.
prs: [6294]
verified:
  - claim: >
      The CI manifest wiring and curated import-closure repair satisfy the
      manifest planner's adversarial unit contracts.
    command: >-
      PYTHONDONTWRITEBYTECODE=1 python3 -B -m pytest -q
      tests/test_btc_decision.py tests/test_contract_delta.py
      tests/test_ci_pack.py tests/test_ci_plan_workflow.py
    result: "174 passed; only three pytest temporary-directory cleanup warnings."
  - claim: >
      The repaired manifest introduces no unowned import closure and leaves no
      new pytest suite unwired against the exact current-main pickup.
    command: >-
      python3 scripts/check_contract_delta.py --base
      5ad13e2ed335a47ecd33d73346fb23dd5d59050a
    result: "contract-delta: 0 introduced, 0 inherited (base 5ad13e2ed335)."
  - claim: >
      The current legacy CI manifest is structurally valid with the accepted P0A
      dependency, test-suite and curated-closure additions intact.
    command: >-
      PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/run_ci_pack.py --workflow
      .github/ci/legacy-jobs.yml --pack-index 0 --pack-count 12 --validate-only
    result: >
      Validated 202 legacy jobs; 202 in scope; balanced 12-pack plan produced and
      pack 0 selected successfully. The manifest retains jsonschema in the Vector
      dependency install, tests/test_btc_decision.py in the Vector step and
      engine/btc_decision.py in the curated import closure.
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
    result: "206 passed; only three pytest temporary-directory cleanup warnings."
  - claim: >
      Sol's raw/final and previous-allocation blockers fail closed while
      preserving schema validity and the lawful named-override seam.
    command: >-
      PYTHONDONTWRITEBYTECODE=1 python3 -B -m pytest -q
      tests/test_btc_decision.py
    result: >
      38 passed. Raw .500/final .504 without override is unavailable; the same
      inputs with an active named override are allowed; 0.1+0.2 versus 0.3 is
      tolerated as representation jitter; latest prior 1.20 and -0.10 are
      unavailable with PREVIOUS_ALLOCATION_OUT_OF_RANGE and null action fields;
      corrupt infinity/string priors are unavailable without older-row search.
  - claim: >
      The existing branch preserves its seven P0A commits and reconciles with
      current origin/main by normal two-parent merges.
    command: >-
      git show --no-patch --format='%H %P'
      935ec982dcffd4521074583140a7a15bb271fca3 &&
      git show --no-patch --format='%H %P'
      f792c107473dcd33b9c611db56558f29e4597600
    result: >
      Merge 935ec982dcff has parents 2a5e640ee616 and cd42b890d1df. The only
      conflict was derived site/vector.html; current-main generated truth was
      retained for the merge and Vector was regenerated afterward from repaired
      source and stored data. During the first exact-head CI run main rendered
      again; merge f792c107473d has parents 602b0a1fe33c and 0e8cd8f28edd. Its
      only conflict was again derived site/vector.html: latest-main generated
      truth was retained for the merge, then Vector was regenerated from repaired
      source and the exact latest stored data. A final pre-push main movement
      changed only White House data and Warp CI-manifest coverage; merge-tree
      proved those manifest hunks compose with P0A. A newer Market OS acceptance
      record landed before the merge without a P0A-path change; final
      reconciliation merge e3642597ece3 has parents c22788da9469 and
      e743db23c31a. No ledger or parquet mutation was carried from either
      disposable render worktree.
  - claim: >
      A pre-release disposable render of the accepted source publishes one final
      action and exact target without the conflicting legacy action or target
      band; it is evidence of source behavior, not a feature-owned publication.
    command: >-
      In a disposable full detached worktree, monkeypatch only
      scripts.notify.send_telegram to a no-op, wrap build_vector.write_page to
      stop immediately after writing vector.html, run build_vector.main(), then
      assert the rendered S2 marker and text with a Python invariant script.
    result: >
      Historical accepted-source proof: P0A_RETURN_VECTOR_RENDER_COMPLETE and
      rendered invariant OK; schema
      btc.decision/v1, status ok, final exposure 100, HOLD 100% BTC and
      持有 100% BTC present; STAY DEFENSIVE and 0–10% absent. Raw and final
      exposure were both 100%, override active false, Kelly receipt 10%,
      current stored-data S2 action and target are consistent. The rendered
      asset set references content-addressed CSS e7978af3.
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
      all four proof images show the exact 100% action/target and coherent
      desktop/mobile composition; every requested page asset returned 200;
      browser warnings and errors were empty.
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
      desktop dark zh 9e278c61aade8a78307e14c3fb0e6e9b928fb77029d3317c23913622ef396775;
      desktop light zh 75f7b000077f6aaab5f22d76ccda4c221c1697e9c04d6ee983b59f43e425abaa;
      mobile dark zh 64326755e329f4191ab9ac70155c210b3e984462858fa856d8bd166bab790bc6;
      mobile light en 9c61075ae7248cb0d0c9579f1464b49ef6ff387d6e355784065c8f40c64ba05c.
  - claim: >
      Sol's release reconciliation preserves every accepted P0A source blob,
      carries current main normally, and leaves no generated Vector artifact in
      the feature delta.
    command: >-
      Compare the six protected source blobs at accepted head
      9ce6ce711602f6bb4986ed59ea84d70b704f3eac and reconciliation merge
      78b07d80b9f72cc92629c63cbb65de44277971f7; compare site/vector.html at
      78b07d80b9f7 with current-main pickup 5ad13e2ed335; inspect
      site/assets/css/e7978af3.css existence and references on that main pickup;
      inspect the merge parents and feature diff.
    result: >
      All six accepted source blob IDs match exactly; 78b07d80b9f7 is a normal
      two-parent merge of 9ce6ce711602 and 5ad13e2ed335; site/vector.html matches
      main blob ed000bfd6750 exactly; main had neither the CSS asset nor a
      reference to it; both generated paths are absent from the feature diff.
unverified:
  - claim: >
      The exact reconciliation head passes hosted CI, merges cleanly, publishes
      through canonical render.yml, and is proven on the live Vector surface.
    what_would_verify: >
      Push the same branch; receive exact-head CI/fence/authority green; verify
      clean mergeability; record Sol's release; mark PR #6294 ready; merge by the
      normal path; observe the natural main render.yml run and its site-only
      commit; then prove the bilingual responsive decision surface in production.
  - claim: "P0B Crypto H5 authority closure, alerts or broader redesign are complete."
    what_would_verify: >
      Separate Sol directives and separately bounded implementation/review
      programs. None may be inferred from P0A acceptance.
unresolved:
  - >
    Reconciliation merge 78b07d80b9f7 is local. Exact-head local/hosted proof,
    clean mergeability, normal merge, canonical render publication and live
    desktop/mobile EN/ZH proof remain outstanding.
next_actions:
  - >
    Run the requested local proof matrix on the reconciliation head, including
    contract-delta against 5ad13e2ed335, CI-manifest validation, diff check and
    Agent OS validation; then commit the durable record and push the same branch.
  - >
    Wait for exact-head hosted CI, authority/fence checks and clean mergeability.
    If any protected P0A source blob changes or a real check fails, stop with the
    named blocker rather than widening scope.
  - >
    On green proof, record Sol's explicit release, mark PR #6294 ready and merge
    by the normal path. Observe—not manufacture—the main render.yml publication;
    stop as MERGED / PUBLICATION BLOCKED if that lane does not complete.
  - >
    After canonical render, prove production Vector schema/status/action/exposure,
    EN/ZH parity, desktop/mobile layout and browser-console health.
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
    Do not restore feature-branch ownership of site/vector.html or orphan
    e7978af3.css. Sol ruled that current-main bytes win the reconciliation and
    that canonical post-merge render.yml owns generated publication.
  - >
    Do not regenerate Vector on the feature branch, create a replacement branch
    or PR, rebase/reset/force, arm merge-on-green, or infer any P0B authority from
    P0A release.
danger_areas:
  - >
    A standalone build_vector.main() mutates Vector ledgers and signal parquet
    before it writes the page. The feature branch must not run or commit that
    generated path during release reconciliation; only canonical main render.yml
    may publish the accepted source/template changes.
  - >
    The raw/final integrity gate intentionally fails closed on economically
    meaningful drift without an active named override, or when an active
    override lacks an identifier. Only 1e-12 allocation-fraction representation
    jitter is allowed. Do not weaken that gate to keep a page superficially green.
  - >
    The prior-allocation reader skips nulls only. The most-recent non-null row
    is authoritative for continuity: invalid, non-finite or out-of-range content
    must fail closed and must never trigger a search for an older valid row.
  - >
    Generated vector.html must pass inline CSS externalization and asset
    stamping. That publication contract is why the natural main render lane,
    including its site-only commit, is mandatory production evidence.
  - >
    DecisionState stores precise exposure as a 0..1 fraction and change as
    percentage points; the present Vector display rounds the exact target to an
    integer for established UI parity. Do not confuse those units in new tests
    or consumers.
---

## §0 State — what is true right now

Sol accepted exact P0A source head 9ce6ce711602 and authorized a bounded release
reconciliation. Normal merge 78b07d80b9f7 carries current-main pickup
5ad13e2ed335 while preserving every protected P0A source blob exactly. The merge
resolves site/vector.html to exact current-main bytes and removes orphaned
e7978af3.css, so generated publication is no longer a feature delta. P0A is not
yet merged, canonically rendered or live-proven; PR #6294 remains Draft until the
new exact head passes the required local and hosted proof.

## §1 What is LEFT — in order

1. Complete and commit the requested local reconciliation proof; push only the
   existing branch and wait for exact-head hosted CI/fence/authority results.
2. Verify clean mergeability, record Sol's release, mark PR #6294 ready and merge
   by the normal path.
3. Observe the canonical main render.yml run and its site-only publication
   commit, then prove the live desktop/mobile EN/ZH decision surface. P0B, alerts
   and redesign still require separate authority.

## §2 What will bite you

The Vector builder writes ledgers and parquet before the HTML, so running it on
the feature branch would reintroduce the exact generated-artifact ownership Sol
removed. The canonical main render must publish and commit only site output.
Separately, a raw/final mismatch without an active named override is an integrity
failure, not a reason to choose whichever number makes the page look coherent.
The most-recent non-null prior allocation cannot be skipped when corrupt:
continuity fails closed instead.

## §3 What was decided and found

No new Decision or Discovery record was minted. The binding prior decision is
DEC:BTC-MIDTERM-BLACKOUT-AUTHORITY-RETIRED: election-calendar state is context,
not allocation authority.

## §4 Not in scope — do not adopt

P0B Crypto H5 authority closure, alerting, recommendation redesign, broader
Vector redesign and new override mechanisms were not started. P0A merge,
canonical publication and live proof are authorized only under this bounded
release. The legacy recommender remains intentionally present behind an advisory
allowlist; its removal or redesign would be a different program.
