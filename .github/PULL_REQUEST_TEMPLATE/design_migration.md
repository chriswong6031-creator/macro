Workstream: REQUIRED
Linear: REQUIRED
Portfolio-Mode: REQUIRED
Wave: REQUIRED
Authority: REQUIRED
Completion: REQUIRED

<!--
NAMED template — opt-in only. It is NOT the repo default and must never become one.
MAS28-V1-CONTRACT-SHA256: 9c57ad499fa34ee32f0ffeb9f2f5928f0515dba1609f984e5a20ce6576e7f75e
MAS28-V1-RULESET-SHA256: 2e97ad7acd0aec77ef18dbd76a1b3f2bbf8b7d4585e938498615de1917aa71aa

Replace every REQUIRED value before review. Canonical values:
- Workstream: WS:<KEY> | NONE
- Linear: MAS-### | NONE
- Portfolio-Mode: tracked | maintenance_exception | creates_workstream | architecture_candidate
- Wave: a non-empty bounded identifier
- Authority: implementation | records | research | maintenance | proof | deploy | architecture_candidate
- Completion: merge-is-done | built-not-proven | proof-required | acceptance-required | records-only

`Fixes/Closes MAS-###` is permitted only for `Completion: merge-is-done`.
Use `Refs MAS-###` or the issue URL for every other completion class.

Use it for design-migration packet PRs:
  gh pr create --body-file .github/PULL_REQUEST_TEMPLATE/design_migration.md
  ...or append ?template=design_migration.md to the compare URL.
Gates below are transcribed verbatim from research/DESIGN_MIGRATION_FACTORY_V1.md §0
("Acceptance gates — not done unless"). The factory doc is the law; this is its checklist.
Do not reword a gate here — amend §0 and re-transcribe.
-->

Packet-id:
Route:
Archetype (registry id):
Reference page:

## Acceptance gates — factory §0 (binding; "not done unless")

- [ ] **1. Reference conformance:** the migrated page composes only §11 canonical components, obeys
  its archetype's L1 budget and layout, and visually matches its reference's grammar. The
  reviewer compares against the reference mockup/page, not against the old page.
- [ ] **2. Both themes, both languages, both widths:** committed screenshots (dark+light × EN+ZH ×
  1440w+390w) in the PR body, captured per the evidence harness; the light shot is judged as
  a design (master doc §12), zh judged as native copy (master doc §13).
- [ ] **3. Density law holds:** one primary question answered above the fold; L1 sections within
  budget; one-integer law (no two visible numbers disagree about one quantity); one as-of per
  panel; no Tier-3 receipts at rest; every demoted/removed module has a named landing.
- [ ] **4. States shipped:** loading / empty(+why) / stale / error rendered and screenshotted at
  least once (forced-state harness or fixture payloads) — never a bare `—`.
- [ ] **5. No horizontal page scroll at 390w**; tables scroll in-container.
- [ ] **6. Engine/data behavior unchanged:** the packet's MUST-NOT-CHANGE list verified (payload
  schemas, counts, access boundaries, ledger writes untouched); display-tier only.
- [ ] **7. Token cleanliness:** zero new hex/font/radius literals in the diff (ratchet lint §6
  passes); page-local tokens only as derivations.
- [ ] **8. Registry updated in the same PR:** the page's row gains
  `design_system: {compliant: true, archetype, migrated_pr, evidence}` — the ratchet's
  coverage grows with the migration, or the migration didn't happen.
- [ ] **9. Fresh end-to-end pass with zero manual workarounds** (spawn-handoff law): a reload-around
  race is a bug the packet owns.
- [ ] **10. No self-merge on first-pass flagship surfaces:** the commissioning session reviews the
  visual artifact before the normal ship chain proceeds.
- [ ] **11. Perf budget respected:** the packet's page-weight/perf line (packet §I.5 pattern) holds,
  and generated-family packets carry a render-budget line — render budget is repo law.

## Evidence matrix (gate §0.2) — committed files, never prose

Replace `<packet>` with this packet's slug. Paths must exist in the diff; a link to a
pasted image is not evidence. Capture per `docs/product_experience/PAGE_EVIDENCE_HARNESS.md`.

| # | Theme | Lang | Width | Shot (committed path) |
|---|---|---|---|---|
| 1 | dark  | EN | 1440 | `mockups/refs/<packet>/dark-en-1440.png` |
| 2 | dark  | EN | 390  | `mockups/refs/<packet>/dark-en-390.png` |
| 3 | dark  | ZH | 1440 | `mockups/refs/<packet>/dark-zh-1440.png` |
| 4 | dark  | ZH | 390  | `mockups/refs/<packet>/dark-zh-390.png` |
| 5 | light | EN | 1440 | `mockups/refs/<packet>/light-en-1440.png` |
| 6 | light | EN | 390  | `mockups/refs/<packet>/light-en-390.png` |
| 7 | light | ZH | 1440 | `mockups/refs/<packet>/light-zh-1440.png` |
| 8 | light | ZH | 390  | `mockups/refs/<packet>/light-zh-390.png` |
| 9 | full page (scroll capture, reviewer's overview shot) | — | — | `mockups/refs/<packet>/fullpage-dark-en-1440.png` |

### Forced-state shots (gate §0.4)

| State | Forced how | Shot (committed path) |
|---|---|---|
| loading | `--force-state "loading:<hook>"` or fixture | `mockups/refs/<packet>/state-loading.png` |
| empty (+why) | `--force-state "empty:<hook>"` or fixture | `mockups/refs/<packet>/state-empty.png` |
| stale | `--force-state "stale:<hook>"` or fixture | `mockups/refs/<packet>/state-stale.png` |
| error | `--force-state "error:<hook>"` or fixture | `mockups/refs/<packet>/state-error.png` |

<!-- A forced shot shows the state's STYLING, not data the page returned — the harness labels
     it so, and so should the reviewer. A fixture payload is the stronger evidence where one exists. -->

## Dispositions applied (packet §6)

Every current first-level module appears exactly once. RETAIN / COMPRESS / MERGE-INTO /
DEMOTE-TO / REMOVE — a removed or demoted module names where it landed.

| Module | Disposition | Landing (for DEMOTE/REMOVE) |
|---|---|---|
|  |  |  |

- [ ] Every first-level module from the packet's table appears above, exactly once.

## Must-not-change verified (packet §7, gate §0.6)

| Guarantee | How it was verified |
|---|---|
| payload schemas |  |
| canonical counts |  |
| access boundaries |  |
| URLs / routes |  |
| ledger + `data/` writes |  |

- [ ] Display-tier only: no engine path, ledger write, or payload schema touched.
- [ ] Forbidden scope (packet §9) respected — `theme.css` untouched unless this IS a DS-PR.

## Registry + ratchet

- [ ] **Registry row updated** in this PR: `design_system.compliant: true` with `archetype`,
  `migrated_pr`, `evidence`; `governed_regions` names the `(source_template, selector/region)`
  pairs this row governs (a multi-page template governs regions, never bare files).
- [ ] `python3 scripts/check_design_system.py` run on this diff; output pasted or clean.
- [ ] Collisions checked (packet §13): `gh pr list --search "<file>"` + `docs/ACTIVE_BUILD_MAP.md`.

## Rollback (packet §14)

<!-- Template-scoped by default. Name the revert story if it is anything else. -->
