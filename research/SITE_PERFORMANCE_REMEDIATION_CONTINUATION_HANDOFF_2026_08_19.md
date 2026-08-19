# Site performance remediation — continuation handoff, 2026-08-19

Program: the 7-PR performance/efficiency remediation commissioned 2026-08-19 against
audited baseline `e6815775d2e3`.

**Status: PRs 1 and 2 delivered, merged, and live. PRs 3–7 not started.**

| # | scope | state |
|---|---|---|
| 1 | correct, idempotent, on-demand assistant loader | **MERGED `7688e47df893`** (#5976) |
| 2 | remove direct assistant tags from canonical estate templates | **MERGED `351be097b51e`** (#5993) + follow-on (this PR) |
| 3 | close content-hash cache-policy gaps (`Caddyfile`) | not started ← **next** |
| 4 | incremental list-overlay mutation handling | not started |
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

## Next single action

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
