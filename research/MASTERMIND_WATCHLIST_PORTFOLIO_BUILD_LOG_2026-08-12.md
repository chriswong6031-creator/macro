# Watchlist + Portfolio CEO revamp — program build log (W1 cycle, 2026-08-12)

Commissioning session log for the wave execution phase. Product authority:
`research/MASTERMIND_PORTFOLIO_WATCHLIST_CEO_REVAMP_HANDOFF_2026-08-12.md`; plan of record:
`research/MASTERMIND_WATCHLIST_PORTFOLIO_W0_COMMISSIONING_PACKET_2026-08-12.md` (PR #5457).

**Operator directive (2026-08-12, mid-program):** the commissioning session works autonomously to
completion of ALL waves — the CI-handoff terminality that would otherwise end the session after W0
was explicitly waived by the operator. Merge mechanics are unchanged (arm `merge-on-green`, the
sweeper merges; no CI polling).

## Wave/PR state at write

| Lane | PR | State | Notes |
|---|---|---|---|
| W0 packet | macro #5457 | armed, open | docs-only; sweeper-owned |
| Regwall P0 hotfix | macro #5463 | armed, open | SIBLING session's; 6-file funnel shell; `stockdata.js` + risk trio stay walled (public-R2 shim finding) |
| W1a multi-list store | macro #5461 | round 3 in flight | reviewer verdict ARM-AFTER-FIXES; fixes + pack-10 heal riding it (below) |
| W1b terminal adapter | terminal #408 | delivered, under review | recorded `portfolio_positions` migration `0007`; batched-add parity; per-list migration marker |
| W2 mockup gate | macro #5464 | **PINNED + armed** at `5fc85e746` | `mockups/refs/psi/workspace/{workspace.html,DESIGN_NOTES.md}` are the exact-design authority for the W2 builder |

## Commissioning rulings of record (this cycle)

- **R1 — primary bind resolution (macro):** bind exact `'Watchlist'` → else first existing list by
  `(position, created_at)` with NO creation → create `'Watchlist'` only at zero lists. The fold keeps
  create-if-absent (it always has content). Rationale: no empty-page regression for Terminal-`Default`-only
  users in the W1a→W2 window; no spurious empty `Watchlist` rows polluting Terminal pickers post-W1b.
- **R1.1 — fold-under-divergence:** the one-shot fold delivers the ticker set the anonymous visitor
  accumulated locally, captured BEFORE any cloud merge mutates the blob — never the bound list's echo.
- **Mockup rulings:** page signature = the Book Seam (money rail vs risk rail, coverage drawn as a
  hatched slot); market-book chips live in the holdings toolbar and filter the TABLE VIEW ONLY (BOOK
  READ / attention / Risk Center always describe the whole portfolio); stance vocabulary on real-money
  surfaces is descriptive only — Watch / Get ready / No action ("Act"/"Protect gains" barred); dark is
  the bare `:root` plane (attribute-selector dark ships dead); entry-price footnote states the truth
  (stored in your account, never feeds signals, never shown to others).
- **PENDING at W2 spawn — anonymous-render ruling:** packet §0's funnel gate ("real risk renders for 8
  anonymous tickers") must be reconciled with #5463's boundary (risk trio = calibrated decision rule in
  code, stays walled; the data shim diverts `<market>stockdata/*` to the public R2 plane). The mockup's
  anonymous live-vs-locked split is provisional until this ruling.

## Main-side finding (fleet-relevant)

`tests/test_odometer_light_mode_surface.py` (landed via #5458) is wired to no `run:` step and absent
from `config/unrun_test_baseline.json` → `scripts/audit_unrun_tests.py` exits 1 → the `workflow-yaml`
job (pack 10) is red on any run whose scope reaches it, including every main baseline since ~09:32Z.
The sweeper's inherited-red refresh cannot clear it (main's own proof carries the red, so the
clean-names subset test at `scripts/merge_on_green.py:4154` never passes). The heal (wire the suite —
it passes — plus its `paths:` entry) rides W1a PR #5461; once merged, main inherits the fix.

## W1a reviewer verdict (mutation-verified, round-1 head)

Shipping path CONFIRMED-SOUND: list-scoped deletes, unread-list refusal, per-list debounce, the
setActive-cancel fix — all caught their mutants. Required fixes now in round 3: publish `wlId` only on
fetch resolve (probe deleted 3 sibling rows); capture ticker set at enqueue + refuse null-target flush
(probe: 5-row wipe prevented only by undocumented aliasing); per-list `queuedPush`; fix the
fold-error test that could not fail (stub threw inside `then()` before `.catch` attached — a
`_markFolded()`-on-error mutation passed 35/35); R1.1; branch-2 explicit ordering; pack-10 heal.
Known-pre-existing, deferred to W2: `visibilitychange` re-pull inside a pending push window can revert
a just-made removal.

## Next

Arm #5461 after targeted re-verification of the fix sites → W2 builder spawns (design pinned at
#5464; anonymous-render ruling first) ∥ W5 after #408 review + merge → W3 → W4 → W6. Joint
cross-product live gate (Gold Miners Macro→Terminal, Space reverse, positions both ways) after both
W1 PRs are live; needs an authenticated session — repo live-e2e credentials to be checked first.
