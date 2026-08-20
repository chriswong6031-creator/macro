# XPV2-SC-R3A — Lane F: Sector Central (US) state census — Overview & Confluence

Route: census. Scope: `templates/sector_central.html.j2`, `scripts/build_sector_central.py`,
`templates/_us_act_now_board.html.j2`, `templates/subsectors.js`, `templates/si_workspace.js`.
Authority precedence: production code. R2 reviews
(`research/reference_integrity/mastermind-xpv2-turn3-r2/reviews/{data_authority,product_regression}.md`)
consulted for claimed gaps; every claim below is re-verified against current file:line, not
taken on the reviews' word.

Views: **Overview** = the `#overview` rail view (hero/lead, Act-Now board §2202,
bottoming watch, leadership rotation). **Confluence** = the 6th rail view, lazy-mounted
`subsectors.js` (`templates/si_workspace.js:17-19,61-66`), four datasets (S&P/baskets/
Nasdaq/Russell).

---

## State 1 — Loading (pre-hydration)

**Overview.** Server-rendered HTML ships the Act-Now board and hero already populated
from `action_board`/`data` passed into the Jinja render
(`scripts/build_sector_central.py:444-453`) — there is no client-side loading skeleton for
the board itself; it is baked. The one client-loading surface is the *tier-gate hydrate*
(state 7): while `whenAuthSettled()`/`freshSession()` resolve, the withheld rows are simply
absent — no spinner, no skeleton (`templates/sector_central.html.j2:3596-3612`). The
Leadership-rotation strip fetches client-side (`fetch('marketdata/index_leadership.json'...)`
at `templates/sector_central.html.j2:3514-3517`) with no loading placeholder — the DOM node
stays whatever the template pre-seeded (`—`/empty) until `leadershipStrip` runs.

**Confluence.** `boot()` (`templates/subsectors.js:552-579`) issues three sequential-ish
promise chains (`Promise.all` over 4 dataset URLs, then `index_leadership.json`, then
`nasdaq_internals.json`) before the first `render()` call. Until `render()` runs, `#sc-app`
holds whatever static shell markup the page shipped (no injected skeleton markup found in
`subsectors.js`; `#sc-app` is a template-owned mount point). **Fixture recipe:** to exercise
loading, freeze the fixture at the pre-`render()` DOM (no `.sec` sections mounted) — this is
a transient state, not a distinct payload shape, so a faithful fixture is a *timing* capture
(e.g. throttled network in the harness), not a JSON variant.

## State 2 — Zero (a true zero value)

**Overview.** Lane counts (`_bn_cnt`, `_bs_cnt`, ... `templates/_us_act_now_board.html.j2:523-527`)
print `0` directly (`<span class="acth-count">{{ _bn_cnt }}</span>`) — no zero-suppression.
Numeric fields use `is not none`/`is defined` guards (e.g.
`templates/_us_act_now_board.html.j2:503-505` `{%- if x.get('perf_20d_rel') is not none and ... is defined %}`),
so a `perf_20d_rel: 0.0` row renders `+0.0%`, not blank — zero is preserved, not treated as
missing.

**Confluence.** `num()`/`signed()` (`templates/subsectors.js:53-54`) both gate on
`x == null || isNaN(x)`, never on falsiness, so `0` values render `0`/`+0.0` rather than the
`–` placeholder. `universeStats` (`templates/subsectors.js:88-107`) counts by `class` bucket;
a bucket legitimately at `0` (e.g. no `entry_now` group) renders normally — see State 3, the
buy column's explicit empty copy, which is triggered by `buy.length` being `0`
(`templates/subsectors.js:298-300`).

**Distinguishing missing from zero (both surfaces):** the house idiom is `x == null` /
`is not none` / `is defined`, never `if (x)`/`{% if x %}`. This holds everywhere sampled
(`num`, `signed`, the Act-Now perf badge, `fullRowVals`). **Fixture recipe:** a row with
`perf_20d_rel: 0.0` (Overview) or a dataset where every group's `class` is something other
than `entry_now` (Confluence) exercises this distinction; pair it with a sibling fixture
where the same field is `null`/absent to prove the two render differently.

## State 3 — Empty / no-result (filter or search yields nothing)

**Overview.** Every Act-Now lane has a per-lane Jinja `{% for %}...{% else %}` zero-row
copy: Buy now → "None today — nothing has fully confirmed a fresh cycle low."
(`templates/_us_act_now_board.html.j2:562-563`); Almost ready → "No imminent setups."
(`:581-582`); On the run → `:600-601` "Nothing extended right now."; Take profits →
`:619-620` "Nothing topping." This is a genuine `{% for %}/{% else %}` Jinja construct
(fires only when the list is truly length-0), not a string check — it cannot mis-fire on a
missing key the way a truthiness check could (a `None` list is not iterated the same way a
`[]` is inside a Jinja for, but `list(action_board.get(key) or [])` in
`scripts/build_sector_central.py:113` and the equivalent in-template
`action_board.buy_now`/`.get('on_the_run', [])` access coerce missing keys to `[]` before the
loop, so "key absent" and "key present but empty" both render the SAME empty copy here —
i.e. Overview's board **does not distinguish "no rows because none qualified" from "no rows
because the field is absent from the payload."** That distinction only exists one level up,
at the `{% if action_board %}` gate (State 6/whole-board-missing), not per-lane.

**Confluence.** The group boards have empty copy: Buy-ready →
`templates/subsectors.js:298-300` "No … is firing a fresh entry tier right now…"; Avoid →
`:309` "Nothing extended or in a downtrend right now…"; Stock picks →
`templates/subsectors.js:484-486` "No qualified picks right now…". **The live-search full
table (`fullTableSection`, `templates/subsectors.js:461-499`) has NO no-result message**:
filtering `FILTER[ds]` to a string matching zero rows renders a table with a header row and
zero `<tr>` body rows, plus `<span class="cnt">0 / N</span>` (`:497`) — the count is the only
signal; there is no "Nothing matches these filters" placeholder in production. **This is a
genuine production/candidate gap in the opposite direction of the R2 candidate's fabricated
placeholder**: PRC-007 notes the candidate frozen HTML *invented* a "Nothing matches these
filters" string at its own `:912` that production's `fullTableSection` does not have.
**UNREPRESENTED IN PRODUCTION: an explicit "no search results" message on the Confluence
full table.** A phase-2 fixture for this state must therefore be the *0/N count with an
empty tbody*, not an invented message — inventing the message would repeat the exact
candidate defect PRC-007 flagged. **Fixture recipe:** set `FILTER[ds]` (or the fixture's
static-HTML twin) to a query string matching none of the group `label`/`sector` fields;
capture the `0 / N` header and the header-only table.

## State 4 — Stale (old data)

**Overview.** Two independent stale mechanisms, of different character:
1. **Absolute-clock guard** — `_dtpState()` (`templates/sector_central.html.j2:1780-1815`):
   `var builtMs=Date.parse(pulse.as_of_utc||''); var stale=isFinite(builtMs)&&(Date.now()-builtMs)>12*3600e3;`
   (`:1799-1800`). This compares **now** against the payload's own absolute UTC timestamp —
   the correct shape per the house law (build-time deltas can't see a dead writer; this reads
   `Date.now()` fresh on every client render), so a genuinely dead nightly writer whose file
   simply never updates IS caught, unlike a baked `lag_min`/`source_age_min` field would be.
   When stale, mode is forced to `last_rth` and the token becomes `LAST SESSION · SETTLED`
   (`:1797`).
   - **Guard predicate literal, fail-open check:** `isFinite(builtMs) && (...)`. If
     `pulse.as_of_utc` is malformed/absent, `Date.parse('')` → `NaN`, `isFinite(NaN)` is
     `false`, so `stale` evaluates to `false` — **this guard fails OPEN on malformed/missing
     input**: a corrupt or absent `as_of_utc` is silently treated as "not stale" rather than
     flagged, and the mode-derived label (`live`/`delayed`/`eod`/etc.) is trusted as-is. This
     is the exact NaN-comparison trap named in the mission brief, confirmed present here.
2. **`freshTxt()`-style relative labels** are a Confluence mechanism (see below), not present
   verbatim on Overview's board rows; Overview's board rows carry no per-row staleness badge
   of their own — staleness is a page-level (`_dtpState`) concept only, applied to the tape
   strip/hero, not to individual Act-Now rows.

**Confluence.** `freshTxt(e)` (`templates/subsectors.js:60-64`) is a **baked-in relative
delta**, not an absolute-clock check: `if (e.ticks != null) return e.ticks === 0 ? 'just
fired' : 'fired ' + e.ticks + ' bars ago' ...`. `e.ticks` is a bar-count baked into the
payload at build time — this is precisely the class of freshness signal the house law warns
about ("a build-time freshness DELTA freezes into the artifact — a DEAD writer reads '4 min
fresh' forever"): if the nightly stops writing `subsector_confluence.json` altogether, the
LAST good file's `ticks` values stay frozen at whatever they were, and `freshTxt` will keep
reporting "fired N bars ago" as if the pipeline were alive. **There is no absolute-clock
staleness check anywhere in `subsectors.js`** — no `Date.now()` comparison against `as_of`
was found (`grep -n "Date.now\|Date.parse" templates/subsectors.js` → no hits). The only
absolute-time signal on Confluence is the plain `as of {payload.as_of}` text
(`templates/subsectors.js:508` `document.getElementById('sc-asof').innerHTML = L('as of ' +
(payload.as_of || '—'), ...)`) — a display-only stamp with **no comparison/threshold logic
at all**, so Confluence has NO enforced staleness gate; a reader must eyeball the printed
date. **Fixture recipe:** (a) Overview absolute-clock stale — `pulse.as_of_utc` >12h in the
past → expect `LAST SESSION · SETTLED` token; (b) Overview fail-open — `pulse.as_of_utc`
malformed/`""` → expect the mode-derived label to render UNCHANGED (not forced stale) —
this is the state a fixture must capture to prove the fail-open defect exists; (c) Confluence
baked-delta — a group with `entry.ticks: 40` alongside an old `payload.as_of` should still
render "fired 40 bars ago" with no visual difference from a fresh file — this null-detector
behavior itself needs no special JSON, any payload with an `entry.ticks` value demonstrates
it; (d) Confluence has no stale FIXTURE state to build beyond the as-of string itself, since
there is no code path that changes on staleness.

## State 5 — Partial (some sources present, some missing)

**Overview.** `scripts/build_sector_central.py` fail-softs every secondary source
independently and each has its OWN degraded rendering, so partial coverage is well-modeled:
- `ctx` (`si_handoff.json` — hero/theme_context/factor_season/flow) absent/corrupt →
  `ctx = {}` (`:378-384`), template falls back per-field (`theme_context`, `factor_season`,
  `flow` all become `None`/Jinja-undefined — see `templates/sector_central.html.j2:2166`
  `{% else %}` branch for the leadership-hero fallback and `:2404` `{% else %}<div ...>—</div>{% endif %}`
  for the money-flow `mkt-flow` element).
- `_action_board` absent/corrupt → `None` (`:389-395`) → whole-board "Refreshing the action
  board — check back after tonight's close." (`templates/sector_central.html.j2:2202`).
- `_bottoming` absent/corrupt → `None` (`:402-419`) → bottoming-watch strip presumably
  self-hides (per the docstring at `scripts/build_sector_central.py:398-401`, "renders the
  strip empty (or hides it), never a crash").
- `flows_html` (ETF flow board) — `_flows_section_html()` returns `None` until flow history
  exists (`scripts/build_sector_central.py:271-273`); a `None` here is a full section
  omission, display-tier, no error surfaced.
- Whole-page template render failure → last-good committed `sector_central.html` is kept,
  build returns 0 (`:454-462`) — this is a PAGE-level partial: fresh data JS/JSON still ship,
  but the HTML shell is stale-by-a-build.

**Confluence.** Each of the 3 fetches in `boot()` independently `.catch(function(){ return
null; })` (`templates/subsectors.js:562,569,573`), so DATA/LEAD/NIDATA can each be null
independently while the others are present:
- `DATA[tab]` null/`!payload.ok` for the ACTIVE tab → whole-app "No data yet — run the
  nightly build." (`:506`) — this is Confluence's UNAVAILABLE state (State 6), triggered by
  a partial per-tab failure, since the 4 datasets are fetched together but rendered one tab
  at a time.
- `LEAD` null → `backdropChips()` returns `''` (`:588`, guarded `if (!LEAD || !LEAD.ok) return
  '';`) and the rising-star badge wiring is skipped (`:571-574`, guarded inside `if (LEAD &&
  LEAD.ok && LEAD.rising_star)`) — the rest of the page renders normally minus those two
  widgets. Genuine partial-source degrade with no error text.
- `NIDATA` null/schema-mismatched → `nasdaqInternalsPanel()`
  (`templates/subsectors.js:445-450`, `try{...}catch(e){ console.debug(...); return ''; }`)
  silently omits the whole Nasdaq-internals section for the `nasdaq` tab only.
**Fixture recipe:** three independent single-field-null fixture variants —
`{DATA.subsectors: valid, LEAD: null}`, `{LEAD: valid, DATA.nasdaq: valid, NIDATA: null}` (on
the nasdaq tab), and the Overview equivalents `{action_board: valid, si_handoff.json:
absent}` / `{si_handoff.json: valid, baskets.json: absent}`.

## State 6 — Unavailable / error (fetch failed, malformed JSON)

**Overview.** Two client-side fetches with distinct error handling:
- `__siBoot()` (`templates/sector_central.html.j2:3086-3088`): `__siFetch('basketdata/baskets.json')`
  → `.catch(function(){ ... innerHTML = 'Data failed to load — please refresh.' })`. `__siFetch`
  (`:3084`) does `if(!r.ok) throw 0;` — any non-2xx or a `.json()` parse failure lands in the
  same catch, producing the identical user-facing message. Malformed JSON and a 404/500 are
  therefore INDISTINGUISHABLE to the reader — both say "Data failed to load."
- Leadership strip fetch (`:3514-3517`): `.then(r => r.ok ? r.json() : null).catch(() =>
  null).then(leadershipStrip)` — `leadershipStrip(null)` is not shown in the excerpt read,
  but the pattern (fail to `null`, then hand to the render function) matches the
  Confluence idiom; a `null` here almost certainly no-ops the strip render (consistent with
  the `if (!LEAD || !LEAD.ok) return '';` idiom seen elsewhere) rather than showing an error
  — this specific function body was not directly opened; treat as INFERENCE pending direct
  read of `leadershipStrip`'s null-guard.
- Server-side build failures are ALWAYS fail-soft-to-0 (never abort the nightly): the
  top-level `engine.sector_central.compute()` exception handler
  (`scripts/build_sector_central.py:336-341`) logs and `return 0`; a missing `data.sectors`
  key also returns 0 with a warning (`:342-344`).

**Confluence.** `boot()`'s three fetches all `.catch(() => null)`
(`templates/subsectors.js:562,569,573`); a malformed-but-200 response (JSON parse error) is
caught the same way as a network failure, because `.then(r => r.ok ? r.json() : null)` lets
`r.json()`'s own rejected promise propagate into the SAME `.catch`. The resulting UI is the
"No data yet — run the nightly build." message for the active tab (`:506`), same string
regardless of whether the failure was 404, 500, timeout, or malformed body —
**production does not distinguish fetch-failed from malformed-JSON from empty-dataset at the
UI-copy level; only at the JS-state level (`payload` is `null` vs `payload.ok === false`).**
**Fixture recipe:** (a) `fetch` rejects (simulated offline) → expect "No data yet…"; (b)
`fetch` resolves 200 with `{not json` (parse error) → same message; (c) `fetch` resolves 200
with valid JSON but `{"ok": false}` → same message via the `!payload.ok` branch — all three
need SEPARATE fixture files even though they render identically, because the R2 gap being
repaired is about *what the harness proves*, not just what pixels ship.

## State 7 — 401/403/access-locked (unauthenticated or under-tiered)

**Overview only** (Confluence carries no tier gate in the files read — `subsectors.js` fetches
public `marketdata/*.json` with no `pgate`/`PGATE` construct anywhere in the file).
Traced end-to-end:
1. **Server decides eligibility, not the client.** `pgate` is set ONLY by
   `scripts/build_sector_central.py::split_actnow()` (`:91-133`), which slices the Act-Now
   board's per-lane row lists down to `preview_rows` (config `sector_central_gate.preview_rows`,
   default 3, `_gate_cfg()` at `:77-88`) when `sector_central_gate.gated` is true. Row counts
   in the shell stay the TRUE full-board counts (`_bn_cnt` etc., `templates/_us_act_now_board.html.j2:523-527`)
   — only the row bodies are cut — so "counts are free, names are paid" (confirmed at
   `_us_act_now_board.html.j2:508-518` header comment and `:97` docstring).
2. **Withheld rows ship out-of-band** to `site/premiumdata/sector_central.json`
   (`_SC_PAYLOAD_URL = "premiumdata/sector_central.json"`, `scripts/build_sector_central.py:57`),
   written UNCONDITIONALLY every build including the ungated case (`write_payload`,
   `:136-167`) — this prevents a shrinking board from leaving yesterday's extra rows
   hydratable.
3. **`config/site_access.yml`'s `premium.enforced_early` enforces the `/premiumdata/` URL
   prefix at the SERVER/edge**, per the inline comment
   (`scripts/build_sector_central.py:51-53`) — this repo's client JS never makes an
   authorization decision; it only asks and reacts to the HTTP outcome (comment at
   `templates/sector_central.html.j2:3538-3541`: "the SERVER decides who sees the board —
   nothing below is load-bearing, we simply ask and keep the shell when the answer is
   401/403/offline").
4. **Client hydration handler**, the ACTUAL 401/403 code path
   (`templates/sector_central.html.j2:3543-3612`):
   - `PGATE = {{ pgate | tojson }}`; `SRC = PGATE && PGATE.payload`; `if (!SRC) return;` — no
     gate configured → script no-ops entirely (byte-identical to the pre-gate page).
   - `freshSession()` (`:3556-3564`) refreshes the Supabase session cookie first (long-idle
     token repair, PR #3454 per comment).
   - `whenAuthSettled()` (`:3567-3576`) waits for the first `mdx-auth` broadcast or a 3000ms
     timeout, so a slow/broken auth layer still lets the request proceed.
   - `hydrate(payload)` (`:3588-3603`) THROWS if
     `payload.schema !== 'tier_payload.v1' || payload.page !== 'sector_central'`
     (`:3589-3591`) — a schema/page mismatch is treated as a hydration failure, same bucket
     as a network 401.
   - The fetch itself: `fetch(SRC, {credentials:'same-origin', cache:'no-store'})
     .then(r => { if (!r || !r.ok) throw new Error('locked'); return r.json(); })
     .then(hydrate)
     .catch(function(){ /* Locked (or offline): the shell stays exactly as rendered,
       disclosure lines and all. Nothing to undo — the withheld rows were never here. */ })`
     (`:3605-3612`). **This is the actual 401/403 handler**: `!r.ok` covers 401/403/5xx alike,
     collapsing all of them (plus offline and schema-mismatch) into ONE no-op catch. The
     visible result on 401/403 is: the shell renders exactly as server-baked, i.e. the
     `preview_rows` rows plus the `ab_more()` disclosure line
     (`templates/_us_act_now_board.html.j2:27-28` macro, e.g. "N more here — sign in to see
     the full lane") stays visible, UNTOUCHED. There is no distinct "access denied" banner —
     the disclosure line IS the access-locked UI, baked server-side, not injected by the
     failed fetch.
   - On SUCCESS, `hydrate()` inserts each lane's HTML via `insertAdjacentHTML('beforeend', ...)`
     keyed by `data-ab-lane` id (`:3592-3596`), restores the "Show more" fold control per
     column (`restoreFold`, `:3577-3586`), and removes the now-stale `.pg-more` disclosure
     lines (`:3600-3602`).
**Fixture recipe:** 3 variants — (a) `pgate` absent (ungated/unauthenticated-untiered site) →
full board, no gate code runs; (b) `pgate` present + payload fetch 401/403/offline → shell
stays at `preview_rows` count with the "N more — sign in" line; (c) `pgate` present + payload
fetch 200 with valid `tier_payload.v1` body → full board hydrated client-side, fold buttons
restored, disclosure lines removed. Variant (b) is what the phase-2 fixture MUST prove
distinctly from a plain zero/empty state — the row list is non-empty (`preview_rows`
worth) but visibly incomplete, which is different from State 3's true zero.

## State 8 — Correction/revision (a value later corrected)

**UNREPRESENTED IN PRODUCTION on both Overview and Confluence.** No code path in any file
read (`sector_central.html.j2`, `build_sector_central.py`, `_us_act_now_board.html.j2`,
`subsectors.js`, `si_workspace.js`) renders a "this value was corrected/restated" marker, a
diff-from-yesterday callout tied to a correction (as opposed to a normal day-over-day change),
or any concept of amending a PAST printed value. Grep across those files for
`correct(ion)?|revision|restat(e|ement)|amend` returned no functional hits (only unrelated
prose uses of "correct[ly]"). The self-grader (`engine.sector_central_grader`,
`scripts/build_sector_central.py:347-354`, `data["grader"]`) grades MATURED calls after the
fact but this is a forward-looking track-record scorecard (win-rate style), not a mechanism
for correcting/republishing a specific historical value shown to a reader that day — it was
not read in full and is out of Lane F's file scope, but nothing in `sector_central.html.j2`
renders per-value correction/revision language from it. **Verdict: correction/revision has
NO production representation on this page family.** A phase-2 fixture for this state cannot
be "source-faithful" in the way the other 9 states are — there is no producer contract to
mirror. Flag to the fixture builder: either the phase-2 spec explicitly omits this state as
N/A-to-production, or Lane F requests a design/production decision before any "corrected
value" fixture is invented (inventing one would fabricate authority the reviews (DAC-001..008)
are already blocking against).

## State 9 — Long-name overflow handling

**Overview.** Consistent `overflow:hidden; text-overflow:ellipsis; white-space:nowrap`
pattern on every name-bearing element sampled:
`.tcard .nm` (`:158`), `.rotrow .rn` (`:212`), `.scm-nm` (`:254`), `.fl-nm` (`:277`),
`.anrow .rn` (`:345`), `.rvx-hocol .nm` (`:520`), `.rvx-trow .tnm .rsn` (`:550`),
`.rvx-brow .bnm` (`:590`). There is also an explicit ABBREVIATION layer for the board:
`dispshort(name)` macro (`templates/_us_act_now_board.html.j2:33-40`) maps known-long names
(`'Consumer Staples':'Cons Staples'`, `'Consumer Discretionary':'Cons Disc'`,
`'Communication Services':'Comm Services'`, `'Reshoring & Industrial Capex':'Industrial
Capex'`) plus strips `" (Equal-Weight)"` to `" (EW)"` — a curated shortlist, not a generic
truncator, so an UNLISTED long name falls through to pure CSS ellipsis only.

**Confluence.** Same CSS idiom under `#si-confluence` (`.g-nm`/`.gcard` name spans not
directly quoted above but the section is styled under the same `#si-confluence` block that
carries `.bd-chip`/`.sc-seg-t`/`.pill` `white-space:nowrap` rules at `:680,706,767`); the full
table's subsector name cell (`fullTableSection`, `templates/subsectors.js:475-476`) has no
dedicated width/ellipsis class of its own read directly in the excerpt (the `<td>` wraps in
`.sc-tbl td` styling with `white-space:nowrap` at `sector_central.html.j2:784`, which applies
because `#si-confluence` hosts the mounted table) — same ellipsis-via-CSS mechanism, no
curated abbreviation table like `dispshort`. **Fixture recipe:** one row/group per surface
whose display name is long enough to overflow its container at 1440px and again at a
narrower mobile width (e.g. a synthetic subsector label >40 chars, and one Overview theme
name NOT in the `dispshort` abbreviation dict to prove the CSS-only fallback path).

## State 10 — Cardinality extremes (one/few/many rows)

**Overview.** Fold/show-more mechanism: `.actbody.act-fold.is-collapsed > a.actitem:nth-child(n+4)
{ display:none }` (`templates/_us_act_now_board.html.j2:220-221`) collapses any lane past 3
visible rows; the "Show more (N)" button is CSS-suppressed entirely when a lane has <4 items
via the `:not(:has(...nth-child(4)))` selector at `:224` — i.e. a genuinely SHORT lane (1-3
rows) never shows a dead "Show more" control. Under the tier gate, the fold control is instead
rebuilt DOM-side by `restoreFold()` (`templates/sector_central.html.j2:3577-3586`), which
explicitly guards `if (n <= 3) return;` before creating the button — same one/few threshold,
reimplemented for the hydrate path.

**Confluence.** Multiple independent caps: `forming.slice(0, 4)` (buy column "Also forming",
`templates/subsectors.js:298`); avoid column `avoid.slice(0, 8)` with an explicit "+N more in
the full table below" note when `avoid.length > 8` (`:308-309`); stock picks
`PICKS_CAP = 12` with a `sc-collapse`/`sc-more` "Show all N picks ▾" toggle when
`buys.length > PICKS_CAP` (`templates/subsectors.js:461,479-482`); the full table itself is
uncapped (`fullTableSection`, all `groups` rendered) but is sortable/searchable rather than
paginated. **Zero/one/few/many are each reachable via distinct thresholds**: 0 → per-column
empty copy (State 3); 1-3 (Overview lanes) / 1-8 (Confluence avoid) / 1-12 (Confluence picks)
→ shown in full, no control; over-threshold → collapsed with an explicit count-labeled
control. **Fixture recipe:** for each capped surface, three row-count variants: `0`,
`threshold` (exactly the cap, no control), `threshold+1` (control appears, one row hidden) —
9 combinations across Overview lanes (cap 3) and Confluence's three capped surfaces (caps
4/8/12).

---

## Summary table

| # | State | Overview | Confluence | Unrepresented? |
|---|---|---|---|---|
| 1 | Loading | baked HTML; only tier-hydrate + leadership strip are client-async, no skeleton | `#sc-app` pre-`render()` static shell, no skeleton | no (but no skeleton UI either — transient/timing state) |
| 2 | Zero | `is not none`/`is defined` guards preserve `0` | `x == null \|\| isNaN` preserves `0` | no |
| 3 | Empty/no-result | per-lane `{% for/else %}` copy | per-board empty copy; **full-table search has NO no-result message** | **partial** — full-table search message unrepresented |
| 4 | Stale | absolute-clock `_dtpState` (fail-open on NaN) | only baked relative `ticks` delta + plain `as_of` text, **no threshold/comparison at all** | no (but Confluence has weaker coverage) |
| 5 | Partial | independently fail-soft `ctx`/`action_board`/`_bottoming`/`flows_html` | independently null `DATA`/`LEAD`/`NIDATA` | no |
| 6 | Unavailable/error | `__siBoot` catch → fixed string; fetch-fail/malformed-JSON/5xx indistinguishable | same collapse pattern in `boot()`/`render()` | no |
| 7 | 401/403/locked | full trace: `split_actnow` → `write_payload` → `premiumdata/sector_central.json` → client `hydrate()`/`catch` | **no tier gate present at all** | Confluence: N/A by design (untiered) |
| 8 | Correction/revision | none found | none found | **YES — fully unrepresented** |
| 9 | Long-name overflow | CSS ellipsis + curated `dispshort()` abbreviations | CSS ellipsis only, no abbreviation table | no |
| 10 | Cardinality extremes | fold at 3, CSS-suppressed control below threshold | caps at 4/8/12 with count-labeled controls; full table uncapped | no |

## Fail-open guards found

- `templates/sector_central.html.j2:1799-1800`: `var stale=isFinite(builtMs)&&(Date.now()-builtMs)>12*3600e3;`
  — `isFinite(NaN)` is `false`, so a malformed/absent `pulse.as_of_utc` makes `stale` evaluate
  `false` (not stale) rather than flagging the input as bad. This is the mission-named
  NaN-comparison trap, confirmed present. It differs from the canonical trap shape (`if (age >
  LIMIT) return`) only by explicitly short-circuiting on `isFinite` first — the net effect is
  identical: malformed input reads as fresh/safe, never as an error state.
- No other `Date.now()`/`Date.parse()`-based guard was found in `subsectors.js` at all
  (grep returned zero hits) — Confluence has no equivalent guard to be fail-open OR fail-closed
  about; it simply has no staleness enforcement.

## Notes on R2 review claims verified/refined

- PRC-002's "tier withholding" claim is confirmed accurate and traced further than the review
  itself did (the review cites `:26-31,43-65` and `:524-548,529-541`; this census additionally
  traces the client hydrate/catch handler at `:3543-3612`, which the review did not quote).
- PRC-007's "loading/stale/partial/error states are absent from the candidate" is about the
  FROZEN CANDIDATE, not production — verified separately here that PRODUCTION does have
  state-specific behavior for 1/2/5/6, partial behavior for 3, and materially different depth
  for 4 (Overview) vs. Confluence (none). The review's "Nothing matches these filters" mention
  is about the candidate's invented copy (`:912`), correctly flagged by the review as
  unproven — this census confirms production's `fullTableSection` has no equivalent, i.e. the
  candidate's placeholder was fabricated, not misquoted from production.

## Gaps / not directly verified

- `leadershipStrip()`'s null-input rendering (`templates/sector_central.html.j2`, function body
  not opened in this pass) — inferred consistent with the null-safe idiom seen elsewhere, not
  directly confirmed.
- `engine.sector_central_grader` internals (out of Lane F's named file scope) were not read;
  State 8's verdict rests on the ABSENCE of correction language in the render path, not on a
  full read of the grader module.
- Mobile/viewport-specific overflow behavior (State 9) was assessed from shared CSS rules,
  not from a rendered-viewport screenshot pass — out of scope for this census (browser
  rendering is explicitly out of scope; visual/screenshot lanes belong elsewhere).
