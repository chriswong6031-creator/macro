# DeepVue W2-A — `workspace_layout.v1` Architecture Freeze (2026-08-26)

Status: **FROZEN** for wave W2-A of `WS:DEEPVUE-INTELLIGENCE-WORKSPACE`, under the
explicit Sol commission of 2026-08-26 (Skillpack pin
`7d160ff47df1bca0ac6312141e6e1134bbce6539`; Macro pickup
`a0b92f9e01c0`, Terminal pickup `580de03e7a75`). Amendments during the wave
require a ruling recorded in this file. W2-B semantic propagation is OUT of this
contract; its boundary is §12.

Authority: Sol W2-A commission → current `WS-DEEPVUE-INTELLIGENCE-WORKSPACE` →
`research/DEEPVUE_W1C_VALIDATION_RECEIPT_2026-08-26.md` →
`research/DEEPVUE_CLEAN_ROOM_REMAINING_WAVES_HANDOFF_FOR_CLAUDE.md` §5.4 + W2-A
(lines 352–378, 653–676) → current Terminal implementation (archaeology packet
2026-08-26, `origin/master` 580de03e7a75).

## 0. Archaeology rulings that shape everything below

1. **Production `chart_layouts` is EMPTY** (re-censused 2026-08-26 via PostgREST:
   `content-range: */0`; columns `id uuid, user_id uuid, name text, config jsonb,
   updated_at timestamptz, created_at timestamptz`). There is no customer data at
   migration risk today; migration law is still built and fixture-proven because
   rows can appear at any moment and legacy *local* formats exist.
2. **No DDL in W2-A.** Optimistic concurrency is achieved with the existing
   table: the workspace `revision` lives inside the canonical payload
   (`config.revision`) and writes use an **atomic conditional UPDATE**
   (`UPDATE … WHERE user_id = ? AND name = ? AND config->>'revision' = ?` via
   supabase-js `.update().eq('config->>revision', …)`), which is a single SQL
   statement — not a read-then-write check. Creates are plain INSERTs fenced by
   the existing `chart_layouts_user_name (user_id, name)` unique index. The
   commission's "smallest additive evolution" is therefore **none**; the
   production-DDL gate (§23 of the commission) is not entered.
3. **`chart_layouts` stays the one canonical named-workspace store.** No second
   table, no parallel store, no migration-tracking store.
4. **The existing chart-layout code is reused, not rebuilt**: `layoutConfig.ts`
   (`LAYOUT_SCHEMA_VERSION = 2`, `normalizeLayoutConfig`, `captureLayoutConfig`,
   `applyLayoutConfig`), `layouts.ts` service semantics
   (create-vs-overwrite, `unavailable ≠ empty ≠ unauthenticated`,
   `nextLayoutName`), `/api/layouts` status contract, RLS owner policy.
5. **Second proof widget = `brain`** (§7). Chart + Brain prove the graph is
   generic without new domain engines and give W1-C regression proof for free.
6. **Collision fence**: no open PR in either repo touches layout persistence.
   Terminal PRs #444/#445/#446 share one entitlement hunk in
   `TerminalShell.tsx` (~line 1062–1077) and #467 touches the ChartFrameBar
   region; W2-A's Terminal edits (regions ~1647/1695, ~4106–4204, ~4567, ~4672,
   ~4730–4780, ~5427) must not touch those hunks. Re-census before every push.

### Amendment A1 (2026-08-26, pre-merge, ruled by the commissioning session)

Terminal-runtime verification during the core build falsified two chart-config
field types as originally frozen, both of which would have made the canonical
validator REJECT real Terminal v2 layouts (migration loss, the exact failure
W2-A exists to prevent):

- `lockedVLine` is `string | null` in the real runtime (TerminalShell/
  ChartPanel own it as a string key), never a number. Amended: string 1..64
  chars, no control characters, or null.
- `split` is Terminal's discrete pane-split selector with runtime domain
  `VALID_SPLITS = {1, 2, 4}`, not a 0–100 percentage. Amended: integer enum
  {1, 2, 4}. (The `50` in the original §1 example was an authoring error in
  this document, propagated into the first vector set.)

The Macro schema/validator/vectors and the Terminal mirror are both bound to
the amended law; the golden-vector digest changes accordingly and the old
digest is void. No other field law changed.

### Amendment A2 (2026-08-26, pre-merge, ruled by the commissioning session after the Phase 6 adversarial review of head 8b4d326514f6)

The hostile review proved the frozen grammar rejects real shipped-Terminal
values (2 BLOCKERs), and found 8 MAJOR defects including three in the frozen
LAW itself. Rulings, all binding on both repos:

1. **Grammar (B1)** — amended to the real runtime domain:
   indicator id `^[A-Za-z_][A-Za-z0-9_]{0,31}$` (covers `_lab`); param key
   `^[A-Za-z0-9_][A-Za-z0-9_.]{0,63}$` (covers dotted suite keys); chart type
   `^[a-z][a-z0-9_-]{0,31}$` (covers `line-markers`); symbol
   `^[\^A-Z0-9.+:_-]{1,24}$` (covers `NVDA+AMD`, `^NDX`, `BINANCE:BTCUSDT`);
   `indParams` values allow nested objects to depth 3 below the per-indicator
   object (≤64 keys per level, bounded primitives at leaves — covers `_vis`).
2. **Lossless-or-refuse (B2)** — `migrate_legacy` MUST NOT silently drop a
   present-but-invalid owned field: it returns
   `{"ok": false, "code": "invalid_widget_config"}`. Migration is lossless or
   it refuses loudly; there is no third state.
3. **Real-capture vector (M3)** — the vector set MUST include
   `chart_layout_v2_real_capture.json` built from the REAL Terminal shapes
   (real indicator keys incl. `_lab`, real ema params with `_vis`, dotted
   suite keys, `line-markers`, a composite and a caret pane symbol, real
   `CmpCfg` `{color,lineStyle,lineWidth,mode}`, a non-integral float param).
4. **Canonicalization (M4)** — canonical JSON is
   `ensure_ascii=False, allow_nan=False, sort_keys, separators(",",":")`;
   `UnicodeEncodeError` (lone surrogates) → `malformed_workspace`; NaN/Inf are
   invalid values; integral-valued floats are normalized to integers before
   serialization (closing the Python `20.0` vs JS `20` digest split);
   non-integral floats serialize by shortest-repr in both languages.
5. **Wire mode (M5)** — `validate_envelope(obj, wire=False)`: wire mode
   accepts non-null `name` (1..60, normalized-name law). Import validates in
   wire mode then strips `name` before storage. Export output is wire-valid.
6. **Projection is fail-closed (M6+M7)** — `subscriber_safe_projection` first
   validates (stored mode); ANY failure → `{"ok": false, "code": ...}` and the
   payload is never rewritten, downgraded, or partially projected. (Terminal's
   export of a blocked row exports the RAW stored bytes instead — the UX spec
   already carries this.) Projection output over a valid envelope is 1:1 plus
   `name` and is wire-valid by construction.
7. **Conversion guard (M8)** — PostgREST cannot express
   `IS DISTINCT FROM` in one predicate; the §6 guard is TWO disjoint atomic
   conditional updates (`config->>'schema' IS NULL`, then
   `config->>'schema' <> 'workspace_layout.v1'`); mutual exclusion follows
   from READ COMMITTED WHERE re-evaluation, not single-statement identity.
8. **Retry idempotency (M9)** — on 0 rows updated the caller reads the row:
   if it exists AND `revision == target` AND canonical content equals what was
   written → the write ALREADY SUCCEEDED (report success); else
   `stale_revision` (or `not_found` when absent). On the conversion path a row
   already carrying `schema == "workspace_layout.v1"` is `stale_revision`.
9. **ABA fence (M10)** — the CAS predicate includes the loaded row's `id`
   uuid (`.eq("id", loadedRowId)`) so a delete-recreate under the same name
   cannot be silently overwritten by a stale device. No DDL — the uuid is
   already returned by every read.
10. **Key deny-list (NB1)** — `__proto__`, `constructor`, `prototype` are
    invalid as widget ids, link-group names, and param keys.
11. **`requires` optional (NB2)** — absent `requires`/`requires.floor`
    defaults to floor 1; the schema marks `requires` optional.
12. **`source_revision ≥ 1` (NB3)** — validator and schema agree.
13. **Honest provenance (NB4)** — `source_revision` is null when the payload
    carried no `schemaVersion`; version comparisons use integer checks
    (booleans are not versions).
14. **Projected name is normalized (NB5)** — the projection applies the
    normalized-name law (trim, collapse whitespace, ≤60; empty → refuse) to
    `row_name` before echoing it.

The golden-vector digest re-pins again under A2; prior digests are void.

## 1. Canonical object — `workspace_layout.v1`

```json
{
  "schema": "workspace_layout.v1",
  "requires": { "floor": 1 },
  "revision": 3,
  "name": null,
  "link_groups": {
    "primary_security": { "entity_type": "security" }
  },
  "widgets": [
    {
      "id": "chart-main",
      "type": "chart",
      "semantic_lane": "primary",
      "grid": { "x": 0, "y": 0, "w": 16, "h": 18 },
      "context_in": ["primary_security"],
      "context_out": ["primary_security"],
      "config": {
        "panes": ["NVDA"], "paneTfs": ["1D"], "split": 1, "activePane": 0,
        "sync": true, "chartType": "candles", "inds": ["ema21"],
        "indParams": {}, "hidden": [], "compare": [], "compareCfg": {},
        "lockedVLine": null
      }
    },
    {
      "id": "brain-dock",
      "type": "brain",
      "semantic_lane": "dock",
      "context_in": ["primary_security"],
      "context_out": [],
      "config": {}
    }
  ],
  "migration": { "source": "chart_layout_v2", "source_revision": 2 }
}
```

Field law:

- `schema` — literal `"workspace_layout.v1"`. Anything else →
  `unsupported_schema` (fail-closed, recoverable, original payload untouched).
- `requires.floor` — integer ≥ 1, default 1. A reader whose supported floor is
  lower than `requires.floor` refuses with `unsupported_floor` and never
  rewrites the payload. W2-A readers support floor 1 exactly.
- `revision` — integer ≥ 1. Monotonic per named workspace. See §4.
- `name` — **stored as `null` in the database row** (§5). Non-null only in the
  wire/export projection, where it is filled from the row's `name` column.
- `link_groups` — map of group-name → `{ "entity_type": … }`. Static contract
  structure ONLY in W2-A (no propagation behavior). Allowlisted entity types:
  `security`, `industry`, `theme`, `portfolio`, `event` (docket W2-B list).
  Max 8 groups; group names `[a-z][a-z0-9_]{0,31}`.
- `widgets` — 1..12 entries. Order is render-stable but placement authority is
  `semantic_lane` (+ optional `grid` desktop intent), never array order alone.
- `migration` — provenance of the last format conversion:
  `source` ∈ `legacy_v0 | chart_layout_v1 | chart_layout_v2 | none | import`;
  `source_revision` int|null. A natively created workspace uses
  `{"source": "none", "source_revision": null}`.
- Unknown TOP-LEVEL keys, unknown widget keys, unknown `migration.source` →
  `malformed_workspace` / `invalid_widget_config` (closed shapes; fail-closed).

## 2. Widget descriptors

- `id` — string 1..64, `[A-Za-z0-9_-]+`, unique within the workspace
  (`duplicate_widget_id` otherwise). Workspace-scoped; stable across
  save/reopen. Migration mints DETERMINISTIC ids (§6); user-created widgets get
  ids minted once at creation and persisted thereafter.
- `type` — closed allowlist for W2-A: **`chart`, `brain`**. Anything else →
  `unknown_widget_type` (the workspace as a whole remains loadable ONLY in the
  read path as a recoverable error surface — the widget renders as an explicit
  "unsupported widget" tile; a WRITE/import of an unknown type is rejected
  outright with `unknown_widget_type`).
- `semantic_lane` — closed vocabulary: `primary`, `secondary`, `rail`, `dock`.
  W2-A ships consumers for `primary` (main content column) and `dock`
  (assistant overlay/dock). `secondary`/`rail` are valid-but-unconsumed until
  W2-B/W2-C; the validator accepts them, Terminal renders their widgets in the
  primary flow after primary-lane widgets (defined, deterministic fallback) —
  never drops them silently.
- `grid` — OPTIONAL `{x, y, w, h}` non-negative integers ≤ 64: durable
  desktop-intent geometry *within* a lane. Responsive realization derives from
  lane + viewport (§9); `grid` is never scaled to phone.
- `context_in` / `context_out` — arrays (≤ 8 each) of declared link-group
  names; every entry must reference a declared `link_groups` key
  (`invalid_port` otherwise). Static declarations only; NO propagation engine
  in W2-A (§12).
- `config` — bounded per-type closed schema:
  - `chart`: exactly the fields the Terminal chart-layout contract owns
    (`panes, paneTfs, split, activePane, sync, chartType, inds, indParams,
    hidden, compare, compareCfg, lockedVLine`) — every field OPTIONAL, and an
    absent field means **"no claim — leave the live value alone"** (the
    existing `NormalizedLayout` null semantics carried forward verbatim).
    Bounds: panes ≤ 4 symbols; symbols uppercase ≤ 12 chars sanity-bounded
    (same admission as current normalize); arrays ≤ 32 entries.
  - `brain`: `{}` — closed, no properties. Brain chat/run state is owned by
    the Brain plane (W1-C run buffer), never by the workspace.
- **Anti-duplication law carried forward verbatim**: the workspace never owns
  timeframe favourites, drawings, drawing prefs, watchlist state, Day Trade
  Mode, alerts, or symbol-owned live data. A workspace HOSTS widgets whose own
  state lives elsewhere; it does not become their canonical data owner.

## 3. Size and count limits (frozen)

- widgets: 1..12 (`too_many_widgets`)
- serialized canonical envelope ≤ 65,536 bytes UTF-8 (`oversized_workspace`)
- link_groups ≤ 8; ports ≤ 8 per direction; name (row) per existing
  `normalizeLayoutName` law (trim, collapse whitespace, ≤ 60 chars, non-empty)
- No executable payloads anywhere: config values are data-typed (string/number/
  boolean/null/bounded arrays/objects per schema); strings never interpreted as
  HTML/JS; renderers use text-safe injection only.

## 4. Revision law (frozen)

- `revision` starts at 1 on create (and on duplicate/import — new identity, new
  history).
- A repeated READ never changes `revision`. Rendering, migrating in memory,
  reflowing, reconnecting — none of these are mutations.
- A successful SEMANTIC MUTATION of a named workspace bumps `revision` by
  exactly 1: save-over (payload change), rename (§5), widget add/remove/
  reconfigure at save time. One user action = one logical mutation = one bump,
  regardless of how many HTTP retries transport it (a retry of the SAME logical
  write carries the same target revision and is idempotent at the store: the
  conditional UPDATE either already applied — post-state row revision equals
  the written value and content matches — or applies now; it can never apply
  twice because the WHERE clause consumes the prior revision).
- Concurrency: writer sends `expected_revision` (the revision it loaded). The
  store performs one atomic conditional UPDATE with
  `config->>'revision' = expected_revision`. 0 rows updated → the caller
  distinguishes `not_found` vs `stale_revision` by a follow-up read and MUST
  surface `stale_revision` to the user (offered: reload latest / save-as-copy).
  Under no path do two devices both receive success for conflicting writes to
  the same `(user_id, name)` revision. Last-writer-wins is forbidden for
  workspace saves; the legacy blind upsert remains ONLY on the legacy
  chart-layout save path until its callers are migrated within this wave, and
  never writes `workspace_layout.v1` payloads.

## 5. Name identity (frozen)

- The `chart_layouts.name` COLUMN is the single authoritative user-visible
  workspace name (existing uniqueness `chart_layouts_user_name`).
- The STORED `config.name` is always `null`. The read/export projection fills
  `name` from the row. A write whose payload carries non-null `name` unequal
  to the target row name is `malformed_workspace` (drift fenced at the door).
- Rename = one atomic conditional UPDATE setting `name = new` (still fenced by
  `expected_revision`, bumping revision by 1). Unique-index violation →
  `name_conflict`. The old name ceases to exist as an identity; no alias rows.
- Duplicate = read source → INSERT new row (new uuid, new name via existing
  `nextLayoutName`-style collision-free naming or user-provided name),
  payload copied, `revision` reset to 1, `migration` provenance preserved.
  Subsequent histories are fully independent.

## 6. Migration law (frozen)

Recognized inbound formats (the complete real estate, per archaeology):

| # | source tag | shape | recognizer |
|---|---|---|---|
| 0 | `legacy_v0` | `{active, tf, …}` | no `schemaVersion`, has `active` |
| 1 | `chart_layout_v1` | v1 fields | `schemaVersion` absent/1 with `panes` |
| 2 | `chart_layout_v2` | `LayoutConfigV2` | `schemaVersion === 2` |
| 3 | `workspace_layout.v1` | §1 | `schema === "workspace_layout.v1"` |
| 4 | future/unknown | anything else | fail-closed `unsupported_schema` |

- **Front half reuses `normalizeLayoutConfig`** (rows 0–2 → `NormalizedLayout`
  nullable claims). The migrated `chart` widget config carries ONLY the claimed
  (non-null) fields; unclaimed fields are ABSENT (no-claim semantics survive —
  absence is never reinterpreted as reset-to-default, and fields legacy formats
  never owned are never invented).
- Deterministic identity: the migrated chart widget id is the constant
  `"chart-main"`; migrated workspaces contain exactly
  `[chart-main (primary)]` — Brain presence is NOT invented for migrated rows
  (legacy rows never claimed it). `link_groups` = `{"primary_security":
  {"entity_type": "security"}}` with chart `context_in/out =
  ["primary_security"]` (static declarations only). Same input bytes → same
  graph, every time, forever (golden-vector-pinned).
- **Cutover rule (the ONE frozen rule): migrate-on-write.** Reading a legacy
  row converts in memory and renders; the ROW is rewritten as
  `workspace_layout.v1` only when the user performs an explicit save of that
  workspace (a semantic mutation, which also bumps revision from a base of 0 →
  1 for the first workspace-format write via CAS against the row's pre-image
  content — implemented as conditional update on the row still holding a
  non-workspace payload: `NOT (config ? 'schema')` guard expressed as
  `config->>'schema' IS DISTINCT FROM 'workspace_layout.v1'` in the same
  single-statement UPDATE, so two devices cannot both convert). Consequences:
  a failed conversion never writes; re-reading an unmigrated row re-derives
  the identical graph (idempotent, no repeated-migration drift, no
  revision-on-read); the original user bytes remain in place (exportable/
  recoverable) until the user's own save replaces them.
- `mm.ws` (device key `{panes, paneTfs, split, sync, activePane, lockedVLine}`)
  and its sibling device keys (`mm.ct`, `mm.inds`, `mm.indParams`,
  `mm.indHidden`, `mm.cmpCfg`, `mm.favTF`, `mm.dtm*`) are **NOT** workspace
  inputs and are NOT migrated into named workspaces. Ownership after W2-A:
  `mm.ws` continues to own exactly what it owns today — per-device, unnamed,
  last-session chart continuity for cold boots without a deep link. Server
  `chart_layouts` owns named workspaces. The current live (unsaved) workspace
  is a session projection, never dual-written to the server. The explicit
  bridge from local→named is the user's own Save action (existing product
  law). No perpetual server↔browser sync loop exists or is added.

## 7. The generic-graph proof pair (frozen choice + rationale)

- `chart` — hosts the ENTIRE existing multi-pane chart surface as one widget
  whose config is the existing v2 ownership verbatim. This retains 1/2/4-pane,
  MTF, sync and split behavior by construction (the pane grid stays owned by
  the chart surface, exactly as today).
- `brain` — the narrowest valid non-chart proof: it is a real, already-shipped,
  user-facing Terminal surface (`BrainWidget.tsx` mounting the shared
  `mm_brain.js`); it requires zero new domain/intelligence engines; it owns no
  workspace-persistable internal state (config `{}` — a genuinely bounded
  descriptor), so it cannot tempt the wave into state-ownership violations; its
  membership/lane in the workspace is REAL new user capability (today its
  presence is hardcoded — after W2-A a workspace declares whether the Brain
  dock is part of it); and it naturally forces the W1-C regression proof
  (`getAiContext` context flow must keep working inside the new container).
  Rejected alternatives: Portfolio/Screener/Alerts views are route-level
  composers with their own data-fetch lifecycles (bad tile abstraction, higher
  risk, no added proof value); WatchlistRail is never rendered standalone today
  and watchlist state is an excluded ownership (would invite the exact
  anti-duplication violation §2 forbids).
- Default (guest or no saved workspace): the implicit runtime workspace is
  `chart-main (primary) + brain-dock (dock)` — byte-for-byte today's product.

## 8. Failure vocabulary (frozen, subscriber-safe)

`malformed_workspace`, `unsupported_schema`, `unsupported_floor`,
`unknown_widget_type`, `invalid_widget_config`, `duplicate_widget_id`,
`invalid_lane`, `invalid_port`, `name_conflict`, `stale_revision`,
`store_unavailable`, `unauthenticated`, `not_found`, `invalid_import`,
`oversized_workspace`, `too_many_widgets`.

HTTP mapping extends the existing route contract: 401 `unauthenticated`,
503 `store_unavailable`, 409 `name_conflict` | `stale_revision`,
400 the validation family, 404 `not_found`. A failure state never renders as an
empty healthy workspace; the existing `unavailable ≠ empty` law is binding.
Receipts/errors never contain repository paths, private source locations,
credentials, or other users' identifiers.

## 9. Responsive law (frozen)

Durable truth = semantic lanes (+ optional desktop grid intent). Terminal
derives concrete placement per breakpoint (contract viewports 1440×900,
820×1180, 390×844 — the repo's existing responsive gate):

- `primary`: the main content column; desktop uses grid intent where present;
  tablet/phone stack primary widgets full-width in stable order.
- `dock`: assistant surfaces docked/floating per the existing product pattern
  (Brain's current placement law is preserved as-is at all breakpoints).
- `secondary`/`rail`: accepted, rendered after primary in W2-A (§2).

Never persisted: breakpoint, viewport, hover/focus/loading state, live network
state, current link-group VALUES (those are `workspace_session.v1` territory,
out of W2-A's durable contract). Zero-usable-height widgets are a failure state
(§15 of the commission) — the lane realizer guarantees a minimum usable height
per widget or overflows into scroll, and the e2e proof measures real geometry.

## 10. Ownership split (frozen)

- **Macro owns**: this contract; `contracts/intelligence_workspace/
  workspace_layout.v1.schema.json` (JSON Schema, closed); the pure validator +
  canonical vocabularies + subscriber-safe projection in
  `engine/intelligence_workspace/workspace_layout.py`; the golden migration
  vectors `contracts/intelligence_workspace/fixtures/workspace_migration/
  *.json` (input → expected canonical envelope, plus invalid-input → expected
  failure code); focused tests; the freeze/validation records. Macro does NOT
  store Terminal user workspaces, does not serve workspace APIs, and gains no
  runtime coupling.
- **Terminal owns**: the persistence adapter over `chart_layouts`
  (`layouts.ts` evolution: CAS save, rename, duplicate), `/api/layouts`
  evolution, the TS validator/migrator (`terminal/lib/workspaceLayout.ts`,
  `terminal/lib/workspaceMigrate.ts`) proven equivalent by running the SAME
  golden vectors (fixtures copied byte-identical, pinned by SHA-256 digest
  recorded in both repos' tests — the W1-C parity mechanism), the workspace
  renderer in `TerminalShell.tsx`, and the management UX.
- Cross-repo landing order: **Macro first** (freeze + schema + vectors),
  **Terminal second** (implementation against the frozen vectors), records
  closeout last. Both PR bodies record the order.

## 11. Import/export (frozen)

- Export: the canonical envelope with `name` filled from the row, current
  `revision`, provenance intact — a versioned, bounded, self-describing JSON
  file. Never includes user ids, row uuids, or any credential/path.
- Import: full validation (schema → vocabulary → limits → per-widget config);
  any failure → `invalid_import` with the specific inner code surfaced
  visibly; NEVER silently drops widgets and reports success; never executes
  payload content; creates a NEW workspace (new identity, revision 1,
  `migration.source = "import"`), with name-conflict handling via explicit
  user choice (suggested free name offered).

## 12. W2-B boundary (binding non-goals)

W2-A ships the STATIC `link_groups` / `context_in` / `context_out` vocabulary
because the schema shape must be durable, and NOTHING that acts on it: no
cross-widget symbol propagation, no transition engine, no origin/revision
propagation protocol, no unlink/freeze semantics, no fetch dedupe, no MTF link
behavior, no group color/name UI. W1-C's Brain effective-context behavior
continues UNCHANGED (BrainWidget keeps consuming the live chart-bus context via
`getAiContext` exactly as today; the workspace graph only decides whether the
Brain dock is present). Also out: W2-C, screener AST, ratings, alerts,
saved-investigation service, Neural Web/Prophet/Fusion, W1-B latency, lexer
widening, any second store/identity/registry/control plane.

## 13. Acceptance gates (§0-style, binding on every builder PR in this wave)

1. Golden vectors: every supported legacy fixture round-trips
   `legacy → envelope → Terminal runtime → capture` preserving every field the
   legacy contract owned; digest-pinned in both repos.
2. Revision: no-op read bumps nothing; one semantic mutation bumps exactly
   once; same-logical-write retry cannot double-apply; stale write loses
   loudly (`stale_revision`); concurrent create cannot mint duplicate
   `(user, name)`.
3. Failure states of §8 all reachable in tests and none renders as an empty
   healthy workspace.
4. Isolation: guest 401 law intact; cross-account access (including guessed
   ids/names) denied by RLS and by application behavior, both tested.
5. Mixed-widget journey: clean account create → configure non-default chart →
   save → leave → reopen → identical semantic workspace, through the REAL
   production path.
6. Responsive: measured geometry proof at 1440×900 / 820×1180 / 390×844.
7. W1-C regression: context receipts still stream and render correctly with
   the workspace renderer active.
8. No second state store, no DDL, no `mm.ws` scope change, no W2-B behavior.
