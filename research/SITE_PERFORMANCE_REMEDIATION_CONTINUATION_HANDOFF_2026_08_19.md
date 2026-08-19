# Site performance remediation — continuation handoff, 2026-08-19

Program: the 7-PR performance/efficiency remediation commissioned 2026-08-19 against
audited baseline `e6815775d2e3`. This session started from `a8b50d964b3a` (that
baseline plus a day of nightly traffic).

**Status: PR 1 of 7 delivered, merged, and live. PRs 2–7 not started.**

The commissioned order is unchanged:

| # | scope | state |
|---|---|---|
| 1 | correct, idempotent, on-demand assistant loader | **MERGED `7688e47df893`** |
| 2 | remove direct assistant tags from canonical estate templates | not started ← **next** |
| 3 | close content-hash cache-policy gaps (`Caddyfile`) | not started |
| 4 | incremental list-overlay mutation handling | not started |
| 5 | Smart Money progressive disclosure | not started |
| 6 | scatter-capable Plotly distribution | not started |
| 7 | deployment instrumentation (optional, separate) | not started |

---

## PR 1 — lazy, correctly-resolved assistant loader · [#5976](https://github.com/mastermindx-market-intelligence/macro/pull/5976) · merged `7688e47df893` 12:09:50Z

### The defect, re-verified on production before any edit

`initChatLauncher` set `s.src = 'mm_brain.js'`. A dynamically created `<script>`
resolves a relative URL against the **document**, not the injecting script. There is
exactly one `mm_brain.js` (site root) and no `<base>` anywhere in the estate.

Measured live at `theme.js?v=948020b9`, 2026-08-19:

| route | request | outcome |
|---|---|---|
| `/stocks/AAPL.html` | `GET /stocks/mm_brain.js` | **404** `net::ERR_ABORTED`; `window.MMBrain` false, `#mmb-root` absent |
| `/macro.html` | `GET /mm_brain.js` | 200 — eager at `DOMContentLoaded`, unversioned |

`account.js` hit this same nested-estate trap and was fixed by resolving from
`_mmSharedAssetRoot` (derived from theme.js's own script URL, so it carries the
correct depth). This does the same.

### Corrections to the audit's figures (measured at `a8b50d964b3a`)

The audit's shape was right. Three counts were stale and **one claim was wrong**:

| audit | measured | note |
|---|---|---|
| 8,276 docs load `theme.js` | **8,335** (all of them) | estate grows nightly |
| 8,035 nested | **8,075** — 4,614 @d1 · 3,439 @d2 · 22 @d3 · 260 root | |
| 3,472 nested carry a direct tag | **3,475** nested + 4 root = 3,479 | |
| 237 root pages load eagerly | **256** root pages carry no direct tag | |
| "`theme.js` still makes an unnecessary nested 404 request" on direct-tag pages | **FALSE** | both scripts are `defer`, so `mm_brain.js` executes and sets `window.MMBrain` before `DOMContentLoaded`; `initChatLauncher` early-returns. Verified in-browser: one script tag, one request, no stub. |

### Found during the work, not in the audit, still open

On all ~3,479 direct-tag pages `window.MM_BRAIN_CFG` is **`undefined`** at runtime.
Two compounding causes:

1. the tag is emitted *before* `theme.js` (both `defer`), so the bundle executes
   first and reads `window.MM_BRAIN_CFG || {}` while unset; and
2. `initChatLauncher` early-returns on `window.MMBrain` *before* the config
   assignment, so it is never written at all.

The widget therefore runs with `CFG = {}`: no symbol accessor, no page label,
default anchor. Moving the assignment above the early return does not help — the
bundle has already read it. **PR 2 is what fixes this**, and it is the strongest
argument for doing PR 2 next.

### Shipped

- `templates/theme.js` + `site/theme.js` — `initChatLauncher` mounts an accessible
  `#mmb-boot` stub mirroring `#mmb-launch`, and loads the bundle on activation
  (click / Enter / Space), coalesced to one request and one mount. Hover/focus warms
  with `rel=preload`, never a `<script>` (a `<script>` would *mount*, and hovering is
  not activating).
- `lib/site_assets.py` — `mm_brain_version()` + `MM_BRAIN_VER_TOKEN`; `emit_theme_js`
  bakes `sha256(mm_brain.js)[:8]`, the same hash `optimize_assets` stamps into HTML,
  so page-authored and on-demand loads share one cache key.
- `scripts/check_template_site_sync.py` — stdlib fallback generalized from
  `str.partition` (one token) to an N-token split. **Load-bearing:** with the old
  form the second token lands inside `head` or `tail`, so a *healthy* tree fails the
  compare and the `pages.yml` publish refuses. `ci.yml` never sees it — it takes the
  exact-compare branch.
- Tests: `tests/test_chat_launcher_stub.py` (16), `tests/test_template_site_sync_tokens.py` (6),
  `tests/test_site_assets.py` (+4). Both new guards are fed the pre-fix input so they
  cannot rot into tests that only pass.

### Proof

Local, `site/` at the merged head:

| depth | page | before | after one activation |
|---|---|---|---|
| 0 | `/us_stocks.html` | stub · 0 requests · no `#mmb-root` | 1 × root-resolved 200 · mounted · panel open |
| 1 | `/stocks/AAPL.html` | stub · 0 requests | 1 × root-resolved 200 (Enter) · open |
| 2 | synthetic | stub · 0 requests | 1 × root-resolved 304 · open |
| 3 | synthetic | stub · 0 requests | 1 × root-resolved 200 (Space) · open |
| 2 | `/stocks/earnings/aa-…` | real widget already mounted | no stub, **no second request** |

Hover→click: `performance` reports **1** fetch, `initiatorType: link`, script
`transferSize=0`. Three rapid clicks: **1** request. Unreachable bundle: retryable
launcher, no console errors, next click refetches. `langchange` relabels EN↔ZH
including `aria-label`, no `title=`. 1440×900 → labelled pill at `right/bottom:22px`;
390×844 → bare 56×56 orb at `right:16px` — matching `#mmb-launch` exactly.

CI: all 12 packs + `ci-gate` green; run `32248294639` `completed success`.

Production, 12:14Z (VPS `last-modified: 12:12:03 GMT`):

```
site/theme.js @ origin/main   sha256[:8] = b1128870
GET /theme.js                 sha256[:8] = b1128870   public, must-revalidate, max-age=300
GET /theme.js?v=948020b9      sha256[:8] = b1128870   public, immutable, max-age=31536000
GET /theme.js?v=b1128870      sha256[:8] = b1128870   public, immutable, max-age=31536000
```

The origin serves the fix on every query key — the edge is **not** pinned.

### Residual risk on PR 1 — read this before re-verifying

`theme.js`'s content hash moved `948020b9 → b1128870`, but the 8,335 HTML pages were
stamped `?v=948020b9` by the `scope=all` render that landed at ~11:00Z, *before* the
merge. Consequences:

- **Cold clients** (no cache entry for `theme.js?v=948020b9`) get the fix immediately.
- **Clients holding that entry** under `immutable, max-age=1y` will not revalidate —
  they keep the old body until the HTML is re-stamped. This was reproduced in-browser
  after the deploy: a profile that had loaded the page pre-merge still ran the old
  code and still requested `/stocks/mm_brain.js`.

**The re-stamp did not need a manual dispatch.** The merge triggered
`public-render` (run `32251225693`, 12:09:53Z) on the `templates/*.js` path, and
`scripts/ci/public_render.sh` runs `python -m scripts.optimize_assets`, which
refreshes asset stamps **site-wide**. Confirm that run concluded `success` and that
`site/*.html` now references `theme.js?v=b1128870`; if it did not land, dispatch
`render.yml` (`scope=all`, 40–85 min) — checking the pool for an in-flight render
first, and never cancelling one.

> Caveat when reading that lane's commits: `public-render` fully rebuilds only the
> three public pages; for product pages it re-stamps `?v=` and nothing else. A
> `render-public` commit touching `site/<page>.html` is **not** evidence the body is
> fresh. Here only the stamp is needed, so that limitation does not matter — but do
> not generalize it.

---

## Next single action

**PR 2 — remove the page-authored `mm_brain.js` tags from the canonical base
templates.** `templates/seo_base.html.j2:495` emits
`<script src="{{ rel }}mm_brain.js"></script>`; `scripts/optimize_assets` adds the
`?v=` and `defer` afterwards. Removing it routes every page through the loader PR 1
shipped, which also fixes the `MM_BRAIN_CFG` undefined defect above.

It is a generated-estate change: large diff, needs a full render. It cannot regress
the pages it does not reach — the loader is already proven to stand down when a tag
is present.

## Notes for whoever picks this up

- `templates/theme.js` is a **paired asset with a bake**. Edit it → run
  `python3 -m scripts.check_template_site_sync --fix` → commit both copies. Any new
  placeholder must be added to `_THEME_TOKENS` in the same commit and must be valid
  JS unbaked (`/*__X__*/''`), because an unbaked theme.js is a supported local-build
  mode and a broken token takes the whole shared script down.
- A `scripts/**` edit sets `authority_changed=true`, which removes the
  base-inherited-red excuse. **Check main is actually green before merging** —
  merging an authority-changing PR onto a red main creates a stop gate that cannot be
  cleared afterwards. Main's `ci.yml` was red all morning (`ci-pack-2/5/8/9/10`) and
  went green at 11:00Z once #5969 landed; PR 1 was merged into that green window.
- `ci-authority/codex/merge-queue-pilot` fails on **every** PR based on `main`
  (`inactive_base_context`, `allowed: true`). It is explicitly excluded by
  `merge_on_green.py` (`CI_AUTHORITY_INACTIVE_CONTEXT`). Not a red you own.
- The audit's "Technical Lab 7.4 MB screener" item is correctly out of scope —
  production 404s `/tech_lab.html` by design.
- PR 3 (cache policy) has a new precondition satisfied: `mm_brain.js` is now
  content-addressed from **both** the page-authored tags and the dynamic loader, so
  moving it onto the immutable matcher no longer risks pinning an unversioned URL.
