# Site performance remediation — continuation handoff, 2026-08-19

Program: the 7-PR performance/efficiency remediation commissioned 2026-08-19 against
audited baseline `e6815775d2e3`.

**Status: PRs 1 and 2 delivered, merged, and live. PRs 3–7 not started.**

| # | scope | state |
|---|---|---|
| 1 | correct, idempotent, on-demand assistant loader | **MERGED `7688e47df893`** (#5976) |
| 2 | remove direct assistant tags from canonical estate templates | **MERGED `351be097b51e`** (#5993) + `418c583754a6` (#6000) |
| 3 | close content-hash cache-policy gaps (`Caddyfile`) | **MERGED `4ec6887610c6`** (#6033) |
| 4 | incremental list-overlay mutation handling | not started ← **next** (scouted, see below) |
| 5 | Smart Money progressive disclosure | not started |
| 6 | scatter-capable Plotly distribution | not started |
| 7 | deployment instrumentation (optional, separate) | not started |

PR 1's full record is in this file's previous revision (git history). Its one durable
correction is repeated under §"Corrections" below.

---

## PR 2 — the acquisition estate stops eager-loading the assistant · #5993 merged `351be097b51e` 16:33:33Z

### What it fixes

`templates/seo_base.html.j2:495` emitted `<script src="{{ rel }}mm_brain.js">` beside
`theme.js`. Every acquisition page therefore downloaded, parsed, executed, and mounted
the largest script in the estate on page load, to render a launcher pill most visitors
never click. These are anonymous SEO landing surfaces: first load *is* the product.

Measured in-browser, `/stocks/earnings/a-2026q2-call-record.html`:

| | before | after |
|---|---|---|
| `mm_brain.js` requests before interaction | 1 (232,097 B) | **0** |
| total JS transferred | 611,225 B | **379,128 B** (−38%) |
| DOM nodes at rest | 960 | **807** (−153) |
| launcher at rest | real widget | `#mmb-boot` stub (`role=button`, `aria-label`) |
| first click | opens | opens — 1 × root-resolved `/mm_brain.js?v=…` 200 |

3,476 pages: 3,419 earnings wire + 57 free estate.

### Browser proof

Every affected page type, at rest → `eagerTags: 0`, `brainRequests: []`, stub present;
after one click → exactly **1** root-resolved request, 200, `mounted`, panel open, stub
retired, `#mmb-launch` present. Depths 0/1/2/3 covered: `about-research.html`,
`blog/…`, `products/index.html`, `stocks/earnings/{article,index}`, `learn/technical/…`,
`tools/calculators/cagr.html`, `stocks/earnings/weekly/…`.

390×844 → bare 56×56 orb at `right/bottom:16px`, `position:fixed`, hit-tests on top,
`tabindex=0`. Light theme on a clean load → stub vs. real `#mmb-launch` computed
`backgroundColor`/`boxShadow`/`borderRadius`/geometry **identical, no diffs**.
`langchange` relabels `aria-label` EN → 问操盘大脑, no `title=`. Zero console errors.

> Measuring the stub by toggling `data-theme` at runtime produces a **false** boxShadow
> mismatch — the stub's styles were already computed. Load the page with
> `localStorage.theme` set instead. There is no light-theme defect.

### Dependency discoveries — none of these were in the audit

1. **Three pages must KEEP the eager tag.** `lib.pages.HAND_AUTHORED_PAGES` —
   `products/{mastermind-ai,market-terminal,market-dashboards}.html` — ship the landing
   tail and carry **no `theme.js`**. No theme.js ⇒ no stub ⇒ no loader, so their tag is
   the only assistant they have. A blanket sweep would have removed the assistant from
   them entirely. `tests/test_free_content.py` now asserts the exemption *positively*
   and fails if one of them ever gains `theme.js` while keeping the tag.

2. **The earnings wire's builder cannot re-render.** Its ingest lane
   (`earnings-evidence-graph`) has been dead since **2026-07-29**;
   `build_earnings_public_wire` fails closed on `existing earnings-wire publication is
   older than 48 hours`, and `audit_earnings_wire_freshness --strict` reports
   `published=2026-07-29 upstream=2026-08-18 lag=20d backlog=2008 bodies`. Its 3,419
   published pages are frozen bytes; the hourly lane fails every run. Waiting would have
   left **97.6 % of the eager cost in place indefinitely**, so those pages carry the same
   single-line deletion the template produces. *Convergent, not divergent*:
   `publish_public_wire` → `_render_pages(manifest)` renders the **whole catalog** from
   this template and rewrites every destination, so the lane emits these exact bytes when
   it recovers. The deletion's shape was pinned by the canonical builder, not guessed —
   `build_free_content --fix` produced exactly `0+/1-` on all 57 of its own pages, and
   the transform refused any page not carrying exactly one matching line.
   **The ingest outage itself is untouched — separate lane, separate owner.**

3. **`scripts/ci_authority.py` caps a PR at `MAX_CHANGED_FILES = 3000`** (`:59`,
   GitHub's pull-files API ceiling). A 3,478-file head is rejected
   `current_pull_identity_rejected` with `authority_hit_count: 0` — which *reads* like an
   authority objection and is not one. **Any generated-estate PR must be split below
   3,000 files.** PR 2 shipped as 2,959 + 519.

4. **`ci-plan` takes ~9 minutes on a 2,959-file head** (it enumerates the changed-file
   list before scheduling). Budget for it; it is not wedged.

### Corrections to earlier records

- **`MM_BRAIN_CFG` was a false alarm.** The PR 1 handoff recorded
  `window.MM_BRAIN_CFG === undefined` on direct-tag pages as a real defect PR 2 would
  fix. Re-read against `mm_brain.js`: `ANCHOR = CFG.anchor || 'br'` already defaults to
  the same anchor, and the symbol read at `:3373` falls through to
  `window.MDXActiveSymbol || window.MMBrainSymbol || window.ACTIVE_SYMBOL` — a
  **superset** of what theme.js's `CFG.symbol` returns. `CFG = {}` was behaviourally
  identical. PR 2's justification is the 232 KB, nothing else.
- **Committed `site/**` bytes need no workflow to go live.** `pages.yml` is
  `workflow_dispatch`-only and deploys the separate GitHub Pages *mirror*.
  mastermind-x.com is Tencent EdgeOne in front of the VPS Caddy, which **pulls main
  every ~3 min**. PR 2 therefore required no render dispatch at all. (A render is still
  what re-stamps `?v=` across the estate — that part of the PR 1 note stands.)

### Traps hit — do not repeat

- **`git checkout <path>` to undo a scratch experiment reverts your own uncommitted
  work.** Restoring `templates/seo_base.html.j2` after a negative-test experiment
  silently wiped the real template edit. Re-check `git diff` after any such restore.
- **Do not edit PR metadata right after a force-push.** `ci-authority.yml` triggers on
  `pull_request_target: [opened, synchronize, reopened, edited]` under a per-PR
  concurrency group with `cancel-in-progress: true`. A title edit fired an `edited` event
  whose payload still carried the **pre-push** head; it cancelled the force-push's own
  `synchronize` run and published a `failure` against the stale sha. Fix: fire one more
  `edited` (a body edit) once the push has settled. The `cancelled` check-run stays
  attached to the head forever and keeps tripping `ship_loop_guard`, even after a later
  run for the same name succeeds — merge by hand rather than churning the head.

---

## PR 3 — every content-hashed public asset gets the immutable year · #6033 merged `4ec6887610c6`

### What it fixes

`scripts/optimize_assets.py` stamps `?v=<sha256[:8]>` on **every** local `.js`/`.css`
ref in `site/**/*.html` — not a curated set. The Caddyfile splits cache policy on
that stamp: `@public_static` carries `not query v=*`, so a stamped request can only
be caught by `@public_versioned`. That list held **24** paths against **81**
reviewed-public ones, so a stamped asset missing from it matched **nothing** and was
served with **no `Cache-Control` at all** — EdgeOne's long default TTL, the exact
2026-07-03 white-page incident class the section exists to prevent.

Measured live before the change:

```
GET /navigation-refresh.css?v=c299c324   200   Cache-Control: (absent)
GET /theme.css?v=6d906bba                200   public, immutable, max-age=31536000
```

| | before | after |
|---|---|---|
| stamped refs served `immutable` | 59,299 | **79,824** |
| stamped refs with NO `Cache-Control` | 34,483 | 14,025 (all 401-gated or 60s) |
| `@public_versioned` paths | 24 | **64** |

38 reviewed-public assets / 20,525 page-refs were in the hole.
`/navigation-refresh.css` alone is on 9,644 pages and had no `Cache-Control` in
*either* form, stamped or bare.

### The trap — why this is a reviewed list and not an extension matcher

A blanket `*.js`/`*.css` matcher is the obvious fix and is a **security bug**.
Checked against production, not assumed:

```
wh_banner.js?v=…          401  no-store    (7,107 page-refs — 2nd largest in the gap)
mm_charts.js  sector_cycles.js  forming_narratives.js
baskets_desk.js  ai_desk_thematic.js        401  no-store
```

Caching any of them publicly turns the CDN into an authentication bypass. Every
path added was already reviewed public — 35 already in `@public_static`, plus
`/navigation-refresh.css`, `/stock-logos.js`, `/logo_config.js` which
`config/site_access.yml` declares `public.exact` but which were never added to
either cache list. **No access was widened**, and a guard now enforces that.

`/mtf.js` and `/mm_brain.js` LEFT the hand-stamp carve-out: it exists for
hand-authored `?v=N` integers, and both now serve content hashes equal to their own
file bodies (`b62aea2f`, `f74045d8`), so 300s was costing a revalidation per
navigation. The four genuine integers stay (`watchlist.js?v=9`, `watchstore.js?v=5`,
`market_books.js?v=2`, `portfolio.js?v=6`).

### Guards (in the already-wired `tests/test_site_access_boundary.py`)

Each verified to FAIL on the pre-fix tree, not merely pass on the fixed one:

| guard | caught |
|---|---|
| every `@public_versioned` entry is already reviewed public | a planted `/wh_banner.js` |
| every reviewed-public asset served `?v=`-stamped is on the immutable matcher | all 35 |
| carve-out holds only paths whose served stamp is NOT their own `sha256[:8]` | `mtf.js`, `mm_brain.js` |

`caddy validate --adapter caddyfile` → **Valid configuration**. 299 tests green
across every suite that reads these matchers.

### Left open, deliberately

`/stocks/earnings/assets/earnings-wire.{css,js}` — 6,816 page-refs, content-hash
stamped, currently served `public, must-revalidate, max-age=60` by a different rule
(not "no header", so no safety exposure). They are **not** in `public.exact`, so
promoting them needs an explicit access review, not a drive-by. That review is the
cheapest remaining cache win in the estate.

---

## Next single action — PR 4 (scouted while PR 3 sat in CI; NOT started)

**Replace the body-wide list-overlay rescan with incremental handling.**
`templates/theme.js` `initListOverlay()` (~:4448) ends with:

```js
mo.observe(document.body, { childList: true, subtree: true });
```

Every DOM mutation anywhere on the page schedules a rAF that runs `upgrade()`,
whose first act is `document.querySelectorAll('.lst-wrap')`.

**Measured 2026-08-20: only 11 pages in the estate contain a `.lst-wrap` at all**
(`hk_stocks`, `china_stocks`, `canada_stocks` at 4 each; `sector_central`,
`allocation`, `allocation_hk` and 5 more at 1). `initListOverlay` is called
unconditionally, so on the other **~8,324 pages** the observer fires on every
mutation and the selector always returns empty — permanent per-frame cost for
zero work, worst on live-tape pages where `live.js` mutates continuously.

Two mitigations already exist and must be preserved: rAF coalescing (one pass per
frame) and the per-wrap `dataset.ovlN` idempotence early-return.

**Do NOT "fix" it by early-returning when no `.lst-wrap` exists at boot** — the
function's own comment records that lists are injected after boot (`renderActNow`,
`langchange` rebuilds), so a boot-time check would silently break those pages.
The safe shape is to inspect the MutationRecords (do any `addedNodes` contain or
sit inside a `.lst-wrap`?) before scheduling the rAF, or to scope `observe()` to
the list containers once one appears.


## Superseded — next single action (PR 3, now merged)

**PR 3 — close the content-hash cache-policy gaps in `app/deploy/Caddyfile`.**

Its precondition is now fully satisfied: `mm_brain.js` is content-addressed from **both**
sides — the three hand-authored tags carry `?v=<hash>` from `optimize_assets`, and the
theme.js loader resolves `?v=<baked sha256(mm_brain.js)[:8]>` from `lib/site_assets.py`.
Moving it onto the edge's immutable matcher can no longer pin an unversioned URL.

Read `app/deploy/Caddyfile` around the three `path` lists at `:343`, `:469`, `:513` and
the `:547` group; the immutable list is the one that must gain the content-hashed assets.

## Notes for whoever picks this up

- `templates/theme.js` is a **paired asset with a bake**. Edit it → run
  `python3 -m scripts.check_template_site_sync --fix` → commit both copies. Any new
  placeholder must join `_THEME_TOKENS` in the same commit and be valid JS unbaked
  (`/*__X__*/''`) — an unbaked theme.js is a supported local-build mode.
- A `scripts/**` edit sets `authority_changed=true`, removing the base-inherited-red
  excuse. **Check main is green before merging.** PR 2 touched no `scripts/**`.
- `ci-authority/codex/merge-queue-pilot` fails on **every** PR based on `main`
  (`inactive_base_context`). Excluded by `merge_on_green.py`. Not a red you own.
- The audit's "Technical Lab 7.4 MB screener" item is correctly out of scope —
  production 404s `/tech_lab.html` by design.


---

## Verifying an edge-cache change — read before re-checking PR 3

A plain `curl -I` against a promoted asset can keep showing the OLD header long
after the reload, and that is not a failed deploy. Measured 2026-08-20, ~10 min
after #6033 merged:

```
GET /navigation-refresh.css?v=c299c324            server: TencentEdgeOne  age: 2648   (no Cache-Control)
GET /navigation-refresh.css?v=c299c324&cb=<rand>  cache-control: public, immutable, max-age=31536000
```

The pathology PR 3 fixed is its own verification obstacle: the header-less
responses were already pinned at EdgeOne under its long default TTL, so the edge
keeps serving them. **Always append a cache-busting param to force origin** — the
`@public_versioned` matcher only requires `query v=*`, so `&cb=…` does not change
which matcher fires. The stale cohort is bounded and self-clearing: any content
change mints a new `?v=` hash, hence a new URL.

`app/deploy/update.sh:373` installs the Caddyfile only when it differs, gated on
`caddy validate`, then `systemctl reload caddy`. Cron runs it every ~3 min under a
flock. A Caddyfile change therefore needs **no render lane at all** — it is not a
rendered artifact, so `render.yml`/`pages.yml` are irrelevant to it.
