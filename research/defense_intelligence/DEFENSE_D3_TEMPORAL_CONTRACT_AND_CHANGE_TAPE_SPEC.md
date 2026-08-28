# D3 — Temporal Contract v3 + Change Tape (FROZEN SPEC, 2026-08-20)

Authorized by Sol (D3 directive, 2026-08-20). Scope: make temporal truth
impossible to misread on the EXISTING Change Tape. Display/context authority
only. No source acquisition, no collector recovery, no SAM parser, no P-1/R-1
parser, no cap change, no #5424, no Atlas expansion, no Prophet/Neural Web.

## §0 Acceptance gates (not done unless)

1. **P00032 (IRDM, HC101319C0006)** reads on the TAPE ROW — not only the
   inspector — as: took effect 2026-05-12, first known 2026-08-12, late
   discovery. Amount 18,416,666.66 exact. No copy anywhere presents it as an
   August catalyst or new August award.
2. **Balance-change row (N0002418C2406, HII)** shows exact before/after from
   `changed_fields` verbatim (4,722,995,757.0 → 4,724,822,663.0 and
   4,724,822,663.0 → 4,725,472,612.5 for the two committed events) plus a
   visible successor line sourced from `prior_source_identity`. Its title and
   type copy never read as a second "new award".
3. **Deobligation (N0002415C2114/AZ0010)** keeps its negative sign
   (−5,937,624) end to end and renders with NO ticker link (its
   `listed_company_impacts` is `[]`). The LDOS deobligation
   (47QFCA21C0002, −41,000,000) keeps its sign AND its reviewed ticker —
   unlinking applies only when the event itself carries no reviewed impact.
4. **Opportunities mode** shows typed `SOURCE_UNAVAILABLE` sourced from the
   read-model (not recomputed frontend truth), and an absent/malformed rail
   block fails CLOSED to unavailable — never to "no opportunities this week".
5. **Budget mode** reaches typed `PROJECTION_MISSING` honestly on every
   path. AMENDED after adversarial review (2026-08-20, PR #6048 F1-F3): the
   real module (`createGovernmentRevenueBudget` in
   `government-revenue-dossiers.js`) already maps the live HTTP receipt
   (404/503/contract) to `projection_missing` — that verdict is
   AUTHORITATIVE and must never be overridden by the read-model fallback
   (a transport `unavailable` is never laundered into a producer claim; a
   settled `ok` with zero rows is never demoted). The typed
   `freshness.budget.failure_state` fallback applies ONLY when no module
   exists at all — where the pre-D3 page sat on "Loading budget request
   graph" forever. No state may imply verification-in-progress for a
   projection that has never been produced.
6. All new copy bilingual via `tr()`; no translated text in `title=`
   attributes; no "证伪/refuted" vocabulary; no raw slugs at glance tier
   except the two established typed codes (`SOURCE_UNAVAILABLE`,
   `PROJECTION_MISSING`) which are already shipped precedent.
7. All eight hostile test families in §5 pass; full govrev suite green.
8. No rank/score/candidate/Prophet/Neural-Web/sizing authority anywhere in
   the diff.

## §1 Clock law (frozen)

Four clocks, permanently distinct, never merged or substituted:

| clock | field | semantics |
|---|---|---|
| effective time | `change.effective_at` (alias `action_date`) | when the action took effect per the official record |
| knowledge time | `change.known_at` | Mastermind's knowledge clock — when our collector verified the record. NOT a source publication clock. |
| first/last seen | `change.first_seen_at` / `last_seen_at` | observation envelope (today both equal `known_at` at creation — leave as-is) |
| packet clocks | workspace `as_of`, `generated_at` | evidence-cut date and packet build time |

- **`source_published_at` MUST NOT be invented.** The source publication
  clock is a NAMED NULL in the UI: displayed as not asserted, with copy
  saying USAspending does not expose a per-revision publication time.
- Before/after values come ONLY from receipt-bound
  `change.changed_fields[].before/.after` (and the signed `delta_*` amounts
  the payload already carries). The browser may FORMAT and SELECT
  server-provided values; it may never subtract, infer, or re-derive them.
- Corrections/successors APPEND: `award_change.prior_source_identity` names
  the predecessor source state; a successor never rewrites a predecessor's
  clocks, receipts, or event_id.
- `award_change.is_late_discovery` is measured only on a first observation
  (engine `award_events.py`); `false` means "not a first discovery", never
  "seen live" — the existing `discoveryTiming()` dual-branch discipline in
  the template is LAW and must not regress.

## §2 Typed rail states (producer/read-model — the only engine change)

Extend `procurement_workspace.freshness` (additive, schema stays
`government_procurement_workspace.v2`; add workspace-level marker
`temporal_contract: "government_procurement_temporal.v3"`):

- Each existing rail block (`award_events`, `opportunities`, `recompetes`)
  gains a nullable typed `failure_state` field, enum:
  `null` (live/ok) | `"source_unavailable"` | `"projection_missing"`.
  - `opportunities`: `failure_state = "source_unavailable"` whenever its
    status is unavailable/error/failed or `records_visible == 0` with no
    observation — derived in the workspace builder
    (`engine/government_revenue/workspace.py` family), never in JS.
- NEW `freshness.budget` block, same shape as siblings:
  `{status, failure_state, observed_at, records_visible, reason_code}`.
  On current main it must emit
  `status: "unavailable", failure_state: "projection_missing",
  reason_code: "no_request_graph_artifact"` — derived from the fact the
  budget projection artifact (`data/government_revenue/budget_program_graph
  .json`) has never been produced (Wave 8 fixture-only). If the artifact
  exists and loads, emit its real status instead. No PDF acquisition.
- Machine enums only in the artifact; bilingual display copy stays in the
  template keyed by the enum. Reason codes are snake_case machine strings.
- Fail-closed law: a consumer that cannot find or parse a rail block treats
  the rail as unavailable, never as validly empty/current.

## §3 UI spec (template `templates/government_revenue.html.j2` — inline JS)

Reuse existing helpers/idiom (`factCell`, `truthChip`, `tr`, `date`, `ago`,
`money`, `semanticLabel`, `eventTypeCopy`, `discoveryTiming`). Exact changes:

### 3a. Tape-row temporal truth (queue rows, award_change kind)
- When `award_change.is_late_discovery === true`: add a mini chip in the
  row's truth-set: `truthChip('late', tr('Late discovery','延迟发现'))` (new
  `.truth.late` style, amber-family token consistent with existing chips),
  and the row time element renders BOTH clocks:
  `tr('Took effect ','生效 ')+date(effective_at)` on the first line with the
  existing `ago(known_at)` beside/after it as
  `tr('found ','获知 ')+ago(known_at)` — exact composition may follow the
  existing row markup, but BOTH the effective date and the
  found/knowledge marker must be visible at tape level without opening the
  inspector.
- Non-late rows keep the current single `ago(known_at)` time (knowledge
  clock is the tape's arrival semantics).
- No client-side lag computation to decide the chip — the chip keys ONLY on
  the producer flag.

### 3b. Inspector explicit clock block (award_change events)
New `inspect-section` labeled `tr('Clocks','时间线')` rendered ABOVE the
"Dates & amounts" grid, four labeled rows (facts-grid cells or a compact
list, builder's choice within existing CSS):
1. `tr('Took effect','生效')` → `date(change.effective_at)` + sub-label
   `tr('Official action date','官方行动日期')`.
2. `tr('First known to Mastermind','Mastermind 首次获知')` →
   `date(change.known_at)` + sub-label
   `tr('Our knowledge clock — when the collector verified the record, not when the source published it.','我们的知识时钟——采集器核验该记录的时间，而非来源发布时间。')`.
3. `tr('Source publication time','来源发布时间')` → literal
   `tr('Not asserted','未认定')` + sub-label
   `tr('USAspending does not expose a per-revision publication time. Nothing is substituted for it.','USAspending 未提供逐修订的发布时间。系统不会以其他时间替代。')`.
4. `tr('Evidence cut','证据截点')` → workspace `as_of` + sub-label
   `tr('Packet generated ','数据包生成于 ')+date(generated_at)`.
Late-discovery events also show the existing `discoveryTiming()` verdict
inside this block (move or duplicate the existing cell here; do not delete
its factGrid usage without keeping the copy discipline comment).

### 3c. Correction / successor state (award_change events)
- When `award_change.prior_source_identity` is non-null: a line under the
  Revision diff section:
  `tr('Succeeds a prior recorded source state (','承接先前记录的来源状态（')
  + first 12 hex chars + tr('). Corrections append; earlier receipts stay on record.','）。更正以追加方式记录；先前凭证保留在案。')`.
- When `change.is_correction === true`: chip
  `truthChip('correction', tr('Correction','更正'))` in the inspector truth
  row (and tape row). Zero events carry it today — implement data-driven,
  pin with a fixture test.
- Type copy: `eventTypeCopy` already renders balance changes as obligated-
  balance movement — assert (test) that no `award_change` event whose
  `event_type != 'obligation'` ever renders the phrase "New obligation"/
  "new award".

### 3d. Typed rail states (consumer)
- `opportunityRailUnavailable()`: prefer `freshness.opportunities.
  failure_state === 'source_unavailable'` when the field exists; retain the
  current status-string logic as fallback for pre-v3 artifacts; missing
  block ⇒ unavailable (fail closed).
- Budget: replace the eternal-`loading` path. On boot, when the real
  `createGovernmentRevenueBudget` module is absent OR its load settles with
  no rows, set `budgetStatus` from `freshness.budget.failure_state`
  (`projection_missing` ⇒ `'projection_missing'`), else `'unavailable'`.
  `'loading'` may persist only while a real in-flight load exists. The
  existing PROJECTION_MISSING copy in `emptyCopy()`/`freshness()` then
  becomes reachable — do not reword it.

## §4 Explicit non-changes
- Event contract string stays `government_procurement_event.v2`; the v3 is
  the frozen temporal semantics + typed rail states (record as
  `DEC:D3-TEMPORAL-V3-IS-ADDITIVE`).
- No new event fields; no re-timing of any manifest or candidate clock
  (`DSC:GRAPH-REPUBLISH-RETIMES-EVERY-CANDIDATE-CLOCK`).
- No change to event cap, display_priority, recompete crowd-out,
  candidate/Atlas surfaces, or `latest.json` data bytes (nightly owns them).
- `first_seen_at`/`last_seen_at` semantics untouched.

## §5 Hostile tests (all required)
Producer (pytest, real fixtures mirroring committed rows):
- T1 rail typing: opportunities unavailable ⇒ `failure_state:
  source_unavailable`; budget artifact absent ⇒ `projection_missing` +
  `no_request_graph_artifact`; artifact present ⇒ no failure_state lie.
- T2 append law: rebuilding events with a successor revision present leaves
  the predecessor event's `event_id`, clocks, and receipts byte-identical.
- T3 named-null law: no emitted event or workspace block contains a
  `source_published_at` key (regression grep over builder output).
UI (existing harness pattern in `tests/test_government_revenue_ui.py` /
node-harness precedent from D2, driven by the REAL committed exemplars):
- T4 P00032: tape row contains effective date 2026-05-12 marker + late chip
  + `ago(known_at)`; inspector clock block shows all four rows; no
  "new award"/August-catalyst phrasing.
- T5 N0002418C2406: diff shows 4722995757 → 4724822663 exactly (and the
  sibling pair); successor line shows `prior_source_identity[:12]`; type
  copy is balance-change, never new-award.
- T6 AZ0010: amount renders with minus; no ticker token; LDOS deobligation
  keeps minus AND ticker.
- T7 rails: opportunities mode renders SOURCE_UNAVAILABLE from typed state;
  with the rail block deleted from fixture ⇒ still unavailable (fail
  closed); budget mode renders PROJECTION_MISSING, and `'loading'` is not
  the settled state.
- T8 no-browser-arithmetic: diff/clock/successor renderers consume artifact
  fields verbatim (assert rendered strings equal fixture values; assert no
  new `Date`-subtraction or amount arithmetic added beyond the pre-existing
  `discoveryLagDays`, which is grandfathered display-selection law §1).
