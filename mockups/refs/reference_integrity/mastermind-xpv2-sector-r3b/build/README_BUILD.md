# XPV2-SC-R3B — build harness

Deterministic assembly harness for the Sector Central six-view reference
artifact. This directory is the **R3B build harness** (ROUTE: build,
commissioned to implement plumbing, not design). It owns the fixture
supplement, the assembler, the runtime shim, and a throwaway placeholder
shell/six view partials that prove the pipeline runs end to end today. A
Principal Design Lead's real shell/views replace the placeholders in a later
wave **without touching the harness** — see "Lane contract" below.

## Rebuild

```
cd mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/build
python3 build_reference.py    # writes ../proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html + BUILD_MANIFEST.json
python3 verify_reference.py   # standalone checks (not pytest — see below)
```

Both scripts are stdlib-only Python 3, no dependencies, no network access.

## Determinism contract

`build_reference.py` never writes a wall-clock timestamp of its own. Every
date/time visible in the artifact comes from embedded fixture data (e.g. the
`generated_utc` fields inside the JSON blocks). Two runs against the same
inputs produce **byte-identical** output — `verify_reference.py` check (a)
runs the build twice and diffs the SHA-256. Ordering is deterministic
everywhere it is not already fixed by the assembly sequence: fixture/
supplement entries are embedded in sorted-path order, and `BUILD_MANIFEST.json`
is written with `sort_keys=True`.

## Assembly order

`build/shell.html` carries five literal HTML-comment slot markers, substituted
in this fixed order by `build_reference.py`:

1. `REF:NAV` — six `<a class="si-view-btn" data-view="…" href="#…">` links,
   generated from a hardcoded EN/ZH title table (verbatim from
   `templates/si_workspace.js:17-20` / `routing_contract.md` §1 — structural
   chrome, not fixture data, so hardcoding it is not a recompute).
2. `REF:VIEWS` — the six `build/views/*.html` partials, concatenated in
   canonical view order (overview → confluence).
3. `REF:DATA` — the embedded data registry: one `<script type="application/json"
   id="ref-data" data-path="…">` block per R3A fixture file (17, sorted) and
   per supplement JSON file (4, sorted), one `<script type="text/x-ref-fragment"
   data-path="fragments/sc_flows.html">` for the extracted flow-board fragment,
   one plain **executed** `<script>` for `sector_cycles_data.js` (it assigns
   `window.SECTOR_CYCLES`), and one plain executed `<script>` baking
   `window.SECTOR_CENTRAL` from the verbatim `sectordata/sector_central.json`
   bytes (mirrors `scripts/build_sector_central.py`'s own
   `site/sector_central_data.js` write — a build-time embed, never a client
   fetch, matching production).
4. `REF:RUNTIME` — `build/runtime_shim.js`, inlined verbatim (escaped only at
   the `</script>` boundary).
5. `REF:ROUTER` — `templates/si_workspace.js`, inlined **verbatim** (byte
   compared at build time; the build aborts if the embedded copy would differ
   from the template), escaped only at the `</script>` boundary.

This order matters: the shim's registry-building code (step 4) runs after the
data blocks exist (step 3) and before the router (step 5) calls its own
`route()` at the bottom of its IIFE, so by the time the router's boot-time
dispatch runs, `REF.registry`/`REF.fragments`/`window.fetch` are already
wired. View partials (step 2) register their own logic on
`document.addEventListener('DOMContentLoaded', …)`, which fires only after
every synchronous `<script>` in the document — including the DATA and RUNTIME
blocks — has executed, so a view's proof-of-data script can always assume the
registry exists regardless of the VIEWS-before-DATA slot ordering in the raw
HTML.

## `</script>` escaping rule

Every embedded blob (data-registry JSON, the extracted fragment, the plain
executed scripts, the runtime shim, and the router) is passed through
`escape_script_close()`: a regex substitution of `</script` (case-insensitive)
to `<\/script` (same case). This is a **textual** escape, not a
re-serialization — `\/` is a recognized escape for `/` in both JSON strings
and JS strings, so parsed/executed semantics never change. It exists purely so
a literal `</script` sequence anywhere in fixture bytes (or in the router/shim
source) can never close the surrounding `<script>` element early.
`verify_reference.py` check (d) re-derives the same escape and confirms it as
a substring of the emitted HTML, so this is exercised by the test suite, not
just asserted in prose.

## The `NaN`/`Infinity` JSON quirk

`basketdata/action_board.json` (and potentially other producer artifacts in a
future capture) is serialized by Python's `json` module with its default
`allow_nan=True`, which emits **bare** `NaN`/`Infinity`/`-Infinity` tokens —
valid Python-JSON, invalid strict JSON (RFC 8259). The embedded `<script
type="application/json">` block still carries those bytes **verbatim** (no
re-serialization — the frozen spec's hard line). `runtime_shim.js` exposes
`REF.parseJSON(text)`, which regex-replaces `: NaN` / `: Infinity` /
`: -Infinity` with `: null` **before** calling `JSON.parse` — every view
partial that needs to parse a registry entry calls `REF.parseJSON(...)`
instead of bare `JSON.parse(...)`. A NaN/Infinity field becomes `null`
("no value"), never a fabricated number or a sign flip. This is the identical
failure a real browser's `r.json()` would hit on the identical bytes over a
real fetch — the helper changes what THIS artifact's own display code can
parse, never what production ships.

## Lane contract (harness files vs design-lane files)

| Owned by | Files | May the design lane touch it? |
|---|---|---|
| **R3B build harness** (this PR) | `build/build_reference.py`, `build/runtime_shim.js`, `build/verify_reference.py`, `build/fixture_supplement/**`, `build/README_BUILD.md` | No — a design lane that needs new shim behavior files a scope change, it does not edit the shim directly. |
| **R3B build harness, throwaway** | `build/shell.html`, `build/views/*.html` | **Yes, freely** — these are explicitly placeholder/proof-of-pipeline only. A design lane replaces them wholesale, as long as the five slot markers stay literal in `shell.html` and each `build/views/<id>.html` still emits a `<section class="si-view" data-view="<id>">…</section>` (the router requires this structure — see "Router contract" below). |
| **Principal Design Lead** (separate, later PR) | `DESIGN_SYSTEM_SPEC.md`, `shell_specimen.html`, `lead_crops/` (not created by this PR) | This PR does not create or touch these paths. |
| **Assembled output** | `proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html`, `proposal/BUILD_MANIFEST.json` | Generated — never hand-edited; regenerate via `build_reference.py`. |

## Router contract (what a replacement shell/views MUST preserve)

`templates/si_workspace.js` (embedded verbatim) requires, at minimum:

- Six `<section class="si-view" data-view="overview|map|moving|money|explore|confluence">`
  elements somewhere in the document (order does not matter to the router).
  `.si-view{display:none}` / `.si-view.on{display:block}` is CSS the shell
  owns, not the router.
- Nav elements carrying `class="si-view-btn" data-view="<id>"` (any tag) — the
  router toggles `.on` and `aria-current` on every element matching
  `.si-view-btn`, but does not require any specific count or container.
- No `href="#"` anywhere (frozen spec, CI-checked by `verify_reference.py`
  check (c2)) — every in-page hash must be a real canonical/legacy hash, and
  every off-page link must carry `data-ref-nav` with its real destination
  (see "Shim API surface" below).

Everything else (the `#si-read-<view>` narrative slots, the `#actnow` board
structure, per-legacy-anchor target ids) is optional to the router itself —
it degrades gracefully (`if(el) …` guards throughout `si_workspace.js`) when
an element is absent. The placeholder partials in `build/views/` include them
for fidelity/proof purposes, not because the router demands them.

**Recorded seam preserved, not repaired**: `build/views/confluence.html`
deliberately does **not** reproduce `id="sc-top"` — `routing_contract.md` §2
confirms this id does not exist as a literal DOM id in production either
(only an unrelated `<div class="sc-top">`), so the `#sc-top` legacy hash
already only-partially resolves in production (correct VIEW, silently
no-op scroll). This is recorded seam (c) in `routing_contract.md` §8 and the
commission's OUT-OF-SCOPE line forbids repairing it without a new ruling.

## Shim API surface (for the design lane)

`runtime_shim.js` exposes on `window.REF`:

- `REF.registry` — `{production-relative-path: raw embedded text}` for every
  `<script type="application/json" data-path="…">` block.
- `REF.fragments` — same shape, for `<script type="text/x-ref-fragment"
  data-path="…">` blocks (currently just `fragments/sc_flows.html`).
- `REF.parseJSON(text)` — `JSON.parse` with the NaN/Infinity tolerance above.
  Use this, not bare `JSON.parse`, on any `REF.registry[...]` value.
- `window.fetch` is overridden — any `fetch(path)` the page issues resolves
  against `REF.registry` by production-relative path (query string and
  leading `/`/`./` stripped before lookup). A hit resolves with a real
  `Response` wrapping the embedded text; a miss or
  `REF.simulateFetchFail=true` genuinely rejects, so production's own
  catch-branch/error-state code runs for real. `REF.fetchJSON(path)` is a
  `fetch(path).then(r=>r.json())` convenience wrapper.
- `REF.nav(href)` — records a would-be navigation instead of performing it.
  Wired automatically to any `<a data-ref-nav href="…">` click (capture-phase
  listener, `preventDefault()`s). **Do not** add `data-ref-nav` to in-page
  hash links (`#overview`, legacy anchors, `#theme-*`, `#read-*`) — those must
  reach the verbatim router untouched.
- `REF.themeById(id)` — mirrors `templates/sector_central.html.j2:2877`
  `themeById()` exactly, against the embedded `basketdata/baskets.json`'s
  `theme_intel.themes` list (synchronously parsed at first use via
  `REF.parseJSON`, cached).
- `REF.accessState` / `REF.setAccessState(state)` — `'gated'|'hydrated'|
  'ungated'`, wired to the drawer's selector. Calls
  `window.REF.renderActNow(state)` if a view has registered one (currently
  `build/views/overview.html`, which owns the `#actnow` board DOM).
- `REF.simulateFetchFail` — boolean, wired to the drawer's toggle.
- `REF.log` / `REF.recordFetch(path, result)` / `REF.recordNav(path, result)`
  / `REF.renderLog()` — the recorder. Every log entry is `{seq, type, path,
  result}` — deliberately no wall-clock timestamp (determinism note in the
  commission: the drawer omits timestamps).

## Time Machine — recorded-not-executed ruling

Per the orchestrator's ruling (frozen for this wave): the Explore view's Time
Machine mount renders **manifest-driven** from the in-fixture
`oracledata/tm_manifest.json` only (`build/views/explore.html`'s `#tm-mount`
proof element reads `schema_version`/`tiers`/`registry` directly from that
file). No `tm_episodes.json` or per-year chunk file was captured — R3A's own
`PROVENANCE.md` names these as an explicit GAP, and the R3B commission
explicitly forbids capturing them. Any code path that would fetch a
per-episode or per-chunk artifact (a future design-lane Time Machine
implementation, if it fetches at all) resolves against `REF.registry`, finds
no entry, and gets a genuine rejection logged as `recorded-not-executed` —
never a faked success, never an invented episode.

## Access-state mechanics (Overview Act-Now board)

`build/views/overview.html` owns `#actnow` and all three states:

- **gated** (default) — `ab[<lane>].slice(0, preview)` per lane, where
  `preview` is read from the embedded `premiumdata/sector_central.json`'s
  `panels.actnow.preview` field (currently 3) — the SAME slice rule
  `scripts/build_sector_central.py::split_actnow()` applies server-side
  (hold spends the preview budget first, avoid gets the remainder, mirrored
  exactly — not a new construction). A "N more — sign in to see the full
  lane" disclosure line appears per lane with withheld rows.
- **hydrated** — additionally parses `premiumdata/sector_central.json`'s
  `actnow_html` field, finds every `.ab-locked[data-ab-lane]` block (the
  SAME shape `templates/_us_act_now_board.html.j2`'s rows-only render emits),
  and `insertAdjacentHTML('beforeend', …)`s each block's `innerHTML` into the
  matching fold id — the identical insert-by-lane mechanic
  `access_hydration_contract.md` §3 describes for production's tier-hydration
  script. The disclosure lines are then cleared (a simplified stand-in for
  production's `restoreFold()` "Show more (N)" control — this placeholder
  just reveals everything rather than rebuilding a collapse/expand affordance;
  a real `restoreFold()` is design-lane work). **Known cosmetic artifact**:
  the hydrated rows are genuine production markup (SVG icons, `.act-row-top`,
  `.ai-bdg`, etc. from `_us_act_now_board.html.j2`), which this harness's
  minimal placeholder CSS does not style — verified working via DOM inspection
  (the row genuinely lands in the fold with its real `href` and content), just
  visually rough until the design lane's real CSS is in the shell.
- **ungated** — ignores `preview` entirely, renders every row from
  `basketdata/action_board.json` per lane, no disclosure line.

## What this harness explicitly does NOT do

- No recompute of rank, lane assignment, count (other than the
  production-mirrored `.length` over a full list, and the production-mirrored
  preview-slice budget rule above), state classification, or producer
  ordering.
- No re-serialization of embedded JSON (`REF.parseJSON`'s NaN/Infinity
  substitution operates on a **copy** used only for `JSON.parse` — the
  embedded `<script>` text itself is never touched).
- No external network requests of any kind. The single Google Fonts
  exception the commission anticipates for the design lane is left as an
  HTML comment slot in `shell.html`'s `<head>`, not wired by this harness.
- No repair of any recorded-not-repaired defect (A3/A6/A7 in
  `ADJUDICATIONS.md`, or the routing seams in `routing_contract.md` §8).
