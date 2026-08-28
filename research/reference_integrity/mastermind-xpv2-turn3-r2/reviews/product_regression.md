# XPV2 Turn-3 R2 — Independent Product Regression Critic

- Reviewer: `codex-xpv2-product-regression-20260820`
- Frozen artifact: `da83976ece01c54d5ab07307e68118693e100a58`
- First pass frozen: `2026-08-20 07:17:40 PDT`
- First-pass verdict: `BLOCK`
- Final verdict after rationale quarantine: `BLOCK`

The reviewer used production source and payload contracts, the frozen candidates,
current rendered/payload artifacts, tests, and only the Turn-3 §9 capability ledger
before freezing the first pass. The full Turn-3 packet was read only after the first-pass
blocker set was fixed.

## Blockers

### PRC-001 — Broken row/detail and method destinations

Operational links are rendered as `href="#"` throughout the Sector Central candidate:
selected-action “View all” (`:438`), Early turns (`:463-465`), Map (`:548`), Moving
(`:578-579`), Crosscurrents (`:593`), Explore history tools (`:689-691`), Confluence
focus/queue/late rows (`:741`, `:746-749`, `:754`, `:756-759`), generated state rows
(`:882`), and generated Explore rows (`:909`). LENS exposes `Open methodology` as
`href="#method"` at `:269`, but the candidate has no `id="method"`.

Production action rows preserve real `x.href` destinations and row-pop behavior in
`templates/_us_act_now_board.html.j2:459,482`; `templates/sector_central.html.j2:3096-3112`
and `templates/si_workspace.js:258-268,310-315` preserve trace navigation. Confluence owns
real group and stock destinations in `templates/subsectors.js:65-66,267-280,325-328`.
This is a broken user journey and silent capability loss.

### PRC-002 — Tier withholding/access behavior is not preserved

The current shared board defines “same counts, withheld rows” at
`templates/_us_act_now_board.html.j2:26-31,43-65`; full counts come from canonical arrays
at `:524-548`, while gated preview slicing occurs at `:529-541`. Production hydrates
`premiumdata/sector_central.json` only after validating `tier_payload.v1` and page identity
at `templates/sector_central.html.j2:3533-3612`.

The candidate hardcodes a local state list and counts at `:424-429,838-879` and updates
only View-all text at `:889`. It has no access-aware destination or payload-backed lane.
The §9 ledger requires tier withholding to be retained exactly.

### PRC-003 — Legacy hash and trace routing is incomplete

The current router maps live inbound anchors in `templates/si_workspace.js:32-64,310-318`,
including `#theme-*`, `#read-*`, canonical views, legacy anchors, and unknown hashes.
`tests/test_si_workspace_shell.py:188-216,241-256` guards those contracts.

The candidate maps only a subset at `:773-780`; omits anchors including `rotmap-section`,
`sc-app`, and `sc-top`; collapses `#read-*` to Overview without opening a trace at
`:782-786`; and has no `#theme-*` exemption before rewriting. The ledger requires exact
legacy-hash preservation.

### PRC-004 — Static reference data leaves producer ownership unproven

The candidate hardcodes clocks and facts at `:421`, `:487`, `:572`, and `:704`; state rows
and counts at `:838-879`; and Explore to seven hardcoded rows at `:895-912`. Its current
snapshot numbers happen to match the freeze commit: action-board lanes `4/5/5/3/27`, and
Confluence counts S&P `65`, Nasdaq `12`, Russell `93`, baskets `49`. But the reference
contains no producer path or correction behavior. `templates/subsectors.js:39-43,560-579`
fetches the four canonical Confluence universes dynamically.

Second-pass amendment: upheld but narrowed. A static reference has not itself changed
production authority, but it cannot establish product-capability preservation unless each
hardcoded value is explicitly a placeholder and the producer contract is carried into the
migration.

### PRC-005 — Explore/history workflow is silently collapsed

The ledger requires the Explore table, performance chart, Time Machine, Forming Narratives,
and Track Record. Production lazy-loads Explore organs via `subsector_rotation.js` and
`time_machine.js` in `templates/si_workspace.js:76-81`. The candidate supplies three dead
history links at `:689-691` and a seven-row sample at `:895-912`. “Collapsed” cannot mean a
nonfunctional placeholder.

### PRC-006 — Confluence loses dynamic universes, members, detail, and full-table behavior

The candidate shows four tabs and S&P counts at `:707-721`, but tab clicks only toggle
`aria-pressed` at `:833-836`; they do not switch data, distribution, coverage, or lists.
Focus/queue/late rows are static and dead-linked at `:724-759`.

Production defines four dataset contracts at `templates/subsectors.js:39-43`, computes
per-universe counts at `:90-108`, coverage at `:218-234`, group cards/details at `:263-287`,
buy/avoid boards at `:289-315`, stock picks/details at `:319-340`, and dynamic tab counts at
`:560-579`. Static S&P content behind four visual tabs does not retain universes exactly.

### PRC-007 — Loading/stale/partial/error states are absent from the candidate surface

The candidate provides fixed positive states and only an Explore “Nothing matches these
filters” result at `:912`; it does not distinguish no data from no results or demonstrate
stale, partial-source, access-failure, or independent-clock behavior. Production already
has fail-soft behavior in `templates/sector_central.html.j2:3090-3095,3533-3541` and
`templates/subsectors.js:560-579`. Turn-3 §§10 and 12.4 explicitly require these states.

## Major findings

- **M-001:** LENS copy is mostly authority-correct, but its methodology destination is not.
  The copy at `:241-267` matches opportunity, tie-break, governor, and policy boundaries;
  the missing target must be implemented or the link hidden. Downgraded from blocker to major
  on second pass because the packet states the lawful remedy.
- **M-002:** Leadership handoff (`Sector Central :451-457`) and What changed (`:469-474`)
  are visually present but not proven to be payload-resident rather than narrative invention.
- **M-003:** Early turns (`:460-465`) preserve Bottoming Watch conceptually but lose receipts
  and destinations.
- **M-004:** Map, Moving, and Money/Breadth are represented visually but not proven
  production-capability complete; Map scope buttons only toggle `aria-pressed`.
- **M-005:** Production uses Stand aside / `观望` at
  `templates/_us_act_now_board.html.j2:632`; the candidate changes it to `暂时回避` at
  `:429,871-872`, violating exact label parity unless explicitly approved.
- **M-006:** The standalone custom shell is acceptable as a visual reference, but would
  become a prohibited duplicate local shell/card system if copied literally into production.

## Capability-ledger delta

| Capability | Candidate delta |
|---|---|
| Rotation verdict | ALTERED/UNPROVEN — hardcoded, not proven from theme context |
| Regime/context chips | ALTERED/UNPROVEN — hardcoded clocks/regime |
| Five action lanes | RETAINED for EN labels/order; ZH Stand aside ALTERED |
| Lane counts | RETAINED for snapshot; dynamic behavior UNPROVEN |
| Composite score / relative performance | RETAINED partially in visible sample rows |
| Lane reason | ALTERED/UNPROVEN — deterministic projection absent |
| Decision trace | LOST |
| Tier withholding | LOST |
| Leadership handoff / What changed | Present visually; payload ownership UNPROVEN |
| Self-grader | LOST/UNPROVEN |
| Bottoming Watch | RELOCATED/ALTERED; receipts/destinations lost |
| Cycle map and sector/theme cards | ALTERED/UNPROVEN; static map/detail loss |
| Fast rotation lens | UNPROVEN |
| Rotation events / in-out / fragmented sectors | Concept retained; static/unproven |
| Desk Watch | LOST/UNPROVEN |
| Closed events | RELOCATED but static/unproven |
| ETF flows / internals / heatmap / leadership scorecard | UNPROVEN |
| Explore table | LOST/ALTERED — seven-row sample |
| Performance chart | LOST/UNPROVEN |
| Time Machine / Forming Narratives / Track Record | RELOCATED but dead-linked |
| Confluence universe tabs | Visual shell retained; switching lost |
| Confluence distribution | S&P snapshot retained; other universes unproven |
| Buy-ready / tailwind / late groups | Visually improved; static/dead-linked |
| Per-group member stocks | LOST |
| Coverage | S&P snapshot retained; dynamic coverage lost |
| Caveats / method | Visually relocated; destinations unproven |
| Duplicate local systems | UNPROVEN if implemented literally |
| Legacy hashes | LOST/ALTERED |

## Strengths

- EN action-lane labels/order now match production, repairing Turn 2's largest regression.
- Candidate action counts `4/5/5/3/27` match the freeze snapshot.
- Rail order matches the current six views.
- LENS copy is materially clearer and largely matches producer authority: opportunity first,
  conviction tie-break, policy nonvoting, context-only.
- Confluence restores four universe names and current S&P coverage.
- The candidate separates action authority from context in Map/Moving copy.
- Visual compression improves scanability if hidden capability remains reachable.

## Second-pass amendment trail

All seven blockers were upheld after reading the full packet. PRC-004 was narrowed to the
reference-contract gap rather than an already-live authority change. M-001 was downgraded
from blocker to major because the packet already specifies that a missing method route hides
the link. The packet reinforced the other findings through its own requirements for complete
destinations, exact hashes, access preservation, real payloads, failure states, and production
proof.

## Required repairs

1. Replace every operational `href="#"` with a real production destination or hide it.
2. Preserve row trace/detail behavior and `#read-*` async trace opening.
3. Reuse or exactly mirror the full `si_workspace.js` routing law, including `#theme-*`.
4. Preserve tier gating, canonical full counts, preview rows, disclosures, hydration
   validation, and 401/403/offline behavior.
5. Project state distribution/resource rows from canonical action-board data; never
   recompute or locally own lane, score, order, population, or rank.
6. Add a deterministic reason mapping or use reviewed existing fields.
7. Make Confluence tabs switch all four real producer universes and recompute every read.
8. Preserve group/member/stock details and prove one group plus one stock drilldown.
9. Restore real Explore search/table, selected performance, Time Machine, Track Record,
   and analysis-labelled Forming Narratives.
10. Preserve existing Map/Moving/Money organs or explicitly scope later references; do not
    present static impostors as equivalent.
11. Add loading, empty, stale, partial, unavailable/error, cardinality, and clock states.
12. Restore `观望` unless Chairman explicitly approves the translation change.
13. Implement a lawful LENS method route or hide the link.
14. Test exact labels/order/counts, destinations, access, hashes, universes/coverage,
    EN/ZH, and static-data drift.

## Production proof required

- Settled nightly payload drives Sector Central without patched DOM.
- Action counts and future changes reconcile to `site/basketdata/action_board.json`.
- Gated readers see full counts, withheld rows, sign-in disclosure, and authenticated hydrate.
- Selected rows reconcile producer order, score, performance, reason, and destination.
- All five selectors and the full legacy-hash set work, including `#read-*` and `#theme-*`.
- Four Confluence universes update counts/distribution/coverage and open group/member details.
- LENS desktop popover/mobile sheet works while rank output remains byte-identical.
- Loading/empty/stale/partial/error fixtures are captured for Overview and Confluence.
- 1440/390/320, dark/light, EN/ZH, keyboard, console-clean, running/deployed SHA, and
  rollback receipts are recorded.

## Return packet

- **STATUS:** completed read-only independent Product Regression review.
- **RESULT:** `BLOCK`; promising direction, not a canonical product reference.
- **EVIDENCE:** candidates, production templates/JS/engine/tests, rendered site artifact,
  action-board and Confluence JSON, then full Turn-3 packet after first-pass freeze.
- **GAPS:** no live browser/auth/viewport pass; Money & Breadth was not field-by-field audited.
- **DEVIATIONS:** none; no files were edited and rationale quarantine was observed.
