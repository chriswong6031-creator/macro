# Growth period fidelity — prerequisite for the Macro Briefing

Operation: `macro-briefing-growth-period-fidelity-20260906-sol-001`.
Authority: current live Chairman continuation of the approved US Macro Briefing upgrade; Sol owns this bounded source correction. No new workstream, runtime job, data store or control plane is created.
Protected procedure: Mastermind `c5fe346fc6ffe865232454c07fc9aefec46951fe`, compatible Skillpack 1.0.1 / bootstrap 1.
Source base: Macro `5812a58468b92c71dc5f5f92abd838059d7d3d1c`, fresh isolated SSD worktree through the installed host storage helper.
Status: local implementation and real-input consumer proof; independent review, hosted checks and production publication are separate outstanding gates.

## Outcome and exact boundary
A researcher must distinguish a current-month leading estimate from older coincident and lagging readings. The machine consumer must retain those same source periods. This correction enables trustworthy economic-backdrop cards without a second macro model.

The existing business-cycle owner deliberately chooses each tier's freshest adequately populated monthly row. Its top-level `asof` is the leading tier's month-end bucket. The growth workspace incorrectly used that one date for every tier's reference period. The real input at this base has leading September 30, coincident July 31 and lagging August 31, calculated September 4. A future month-end *period label* is not evidence of future publication; replacing it with the build day would also be false.

This change preserves each valid tier `asof` through the existing required-source rows, nine tier metrics and three source entries. Missing or malformed tier dates remain null and never borrow another tier's date. Tier metric `observed_at` stays unknown; `calculation_as_of` uses the already-known regime calculation date. No release or first-known timestamp is invented.

Numeric inputs, weights, thresholds, states, hysteresis, freshness policy, authority flags and model method are unchanged. `METHOD_VERSION` deliberately remains v1: bumping the numeric method would reset comparison/hysteresis merely to repair metadata. Normal content-digest and code-version identity bind the corrected bytes. The repair does not redesign the existing corrections engine or claim point-in-time reconstruction.

Only production source `engine/market_os/macro_workspaces/growth.py` and its already-CI-owned `tests/test_macro_workspace_growth.py` change. The business-cycle owner, shared view/labels/templates/builder, schema, acquisition, scores, permissions and publication workflow do not change.

## Evidence
- Baseline: 25 passed, one real-owner test skipped before its source directory was materialized.
- RED: 23 intended assertion failures, 27 passed, one real-owner skip. Wrong coincident/lagging dates, invented fallback periods and invented observation timestamps all fail on the original source.
- GREEN: 51 passed, no skips, after the exact same-head `data/regime/latest.json` was materialized and checked byte-for-byte against Git.
- Existing complete `market-os-macro-workspaces` job command: 929 passed, 5 other-workspace real-data skips. No CI file was edited, no new test job added and no full-estate success claimed.
- `verify_growth_period_fidelity.py` invokes the actual existing publisher with the real regime, then the actual manifest reader, validator, view and page renderer. Eight Chromium cases cover 1440/390, dark/light and EN/ZH; all nine reference periods and separate unknown observation / known calculation fields are checked in the DOM. No page errors or document overflow. This is local real-growth-owner proof, not production or a healthy fourteen-workspace claim.
- Real owner plus its actual prior snapshot: old and corrected composers differ in exactly 27 period/clock fields; every other field, including hysteresis, corrections and authority, is byte-equivalent after canonical JSON comparison. See `real-owner-semantic-delta.json`.
- Contract-delta reported 0 introduced and 0 inherited against the immutable base.
- Raw logs, source hashes, browser receipt and eight coincident-card crops are in `growth_period_evidence_2026-09-06/`. The evidence receipt binds the parent Git revision plus the actual uncommitted composer hash; it does not pretend the parent commit contains the correction.

Reproduce the browser proof with a new, non-product output directory:

```sh
PLAYWRIGHT_BROWSERS_PATH=<installed-browser-cache> python3 \
  research/macro_html_refresh/verify_growth_period_fidelity.py --out <new-evidence-directory>
```

## Integration and remaining work
The current Macro Command owner retains PRs #6873, #6930 and #6937. File/branch checks found no growth-composer or growth-test edits in those owners' trees; #6873's complete changed-file census confirms no ownership overlap on these two paths. The broader all-open-PR GraphQL census was unavailable, so exhaustive estate-wide exclusion is not claimed. Recheck current source before push/release.

Shared-consumer debt is explicit, not absorbed: `lib/macro_suite_view.py::_evidence` currently aliases each source `reference_period` to an Observed row; the corrected metric clock path does not do that. Source-period fidelity is fixed here, but that inherited source-drawer label conflation remains for the existing shared-view owner. Existing English fallback metric names in the ZH workspace also remain unchanged; these captures are not acceptance of a redesigned bilingual interface.

P2's retained-state/source-failure Read clause and its “today's data” coverage wording were separately reported on #6937 comment 5562102042. This repair does not duplicate P2's reviewed word tables or take over its source writer.

The original compact-risk feature stays on #6685, immutable head `2d5133eacf8d88b74ad9f201eaeb3917f3fba817`, independently reviewed and released from the manual design hold by comment 5562188256. It was freshly confirmed Ready and armed with the existing `merge-on-green` label at 21:40 UTC. CI 34058460541 was pending on twelve trusted packs; all three eligible Linux runners were online/busy. No healthy runner was restarted, no queue or workflow bypassed, and no production claim was made. Its stale earlier chat final is not canonical state.

Next: freeze this bounded correction, obtain independent review, pass current hosted checks, and publish through the normal owner lane. Production acceptance requires the real growth snapshot and rendered component periods to preserve the actual producer periods; a source merge is not that proof. Continue #6685's normal guarded release separately without changing its reviewed semantic head.
