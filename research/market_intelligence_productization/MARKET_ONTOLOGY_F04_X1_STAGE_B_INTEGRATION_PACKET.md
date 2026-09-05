# F04-X1 WTI Live Trace — Stage B integration packet

**Status:** PREPARED, NOT APPLIED. Every hunk below is documented so it can be
applied in one pass once ownership clears. This branch applies **none** of them.

**Why prepared and not applied.** Each insertion point is a file an open sibling
carrier is editing right now. Applying them here would either conflict on merge
or silently revert a sibling's better version — the failure mode that closed
#4850. The point of the packet is that the next session does not have to redo
this census; the line numbers are current as of `origin/main` at the head this
branch is based on, and every one carries the churn evidence that says how fast
it is moving.

Scope note: Stage B is discoverability and CI selection. It changes **no**
product behaviour, no transport law, and no owner data. The page already works
at its direct URL with the private-transport guarantees Stage A proved.

---

## B-1 · Register the builder in the normal site build

**File:** `scripts/build_site.py` — **CONTENDED** (`#6836` [F01][R1B] added a page
here recently; churn is high).

The house pattern is a plain function call inside `main()`, each wrapped in its
own additive `try/except` that logs and continues. Definition neighbourhood is
`build_alerts_page` at `scripts/build_site.py:3551`; the call chain is at
`:5709-5713`.

Insert after the `build_alerts_page` block (currently `:5714`). **This is the
whole hunk** — there is nothing to define locally, because the feature-owned
builder already exposes the entry point (`scripts/build_ontology_explorer.py`,
`build_shell`, shipped in this PR and covered by
`tests/test_ontology_explorer_shell.py`):

```python
    try:
        from scripts.build_ontology_explorer import build_shell
        build_shell(env, site)
        _tmark("ontology_page")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("ontology page failed: %s", e)
```

`build_shell` deliberately takes the site build's **own** `env` rather than
making its own: one page rendered by two differently-configured Jinja
environments is how autoescape drifts between the nightly build and a manual
one. It raises on a missing paired asset rather than returning a code, which is
what the additive `try/except` pattern above expects. It takes no `generated`
argument because this template has no generated-at stamp to fill — the page
carries no build-time value at all, by transport design.

**Until this lands** the page is built by running
`python3 scripts/build_ontology_explorer.py` directly. That is why Stage A is
`BUILT_NOT_PROVEN` on discoverability and says so.

## B-2 · The nav entry

**File:** `templates/_navlinks.html.j2` — **the family is already decided.**
Amendment 3 §2 assigns this product the `_site_nav` / `_navlinks` family plus a
toolbar below the global nav. There is no open question about which family; only
the hunk is outstanding.

`templates/_site_nav.html.j2` needs **no** change — it is a shell that
`{% include "_navlinks.html.j2" %}` at `:13` and enumerates nothing itself.

Insert after the Alert Center row (`templates/_navlinks.html.j2:89`), inside the
US submenu block:

```jinja
        <a href="{{ NP }}ontology.html"><span class="submenu-icon submenu-icon-alert" aria-hidden="true"></span>{{ t('WTI Live Trace', 'WTI 实时追踪') }}<span class="d">{{ t('Which step in the oil-to-duration path is actually met', '油价至久期路径中，哪一环节当前真正成立') }}</span></a>
```

The established rollout convention is a feature flag on the `<a>` itself —
`{% if ontology_enabled is not defined or ontology_enabled %}…{% endif %}` —
matching `leader_radar_enabled` (`:108`), `intraday_flow_enabled` (`:72`) and
`darkpool_enabled` (`:104`). Use it if the entry should stay dark during rollout.

The icon above reuses an existing sprite class deliberately. `submenu-icon-*`
classes are styled in `templates/product-nav-icons.css` (`submenu-icon-alert` at
`:198`), **not** in `navigation-refresh.css` — and that file is on the
Caddyfile's `immutable` list, so minting a new icon means a second shared-file
edit whose `?v=` re-stamp only lands on a render. Reusing an existing class
avoids both. Pick a dedicated icon in a later pass if the nav owner wants one.

Worth flagging to whoever owns the nav: `/transmission.html` — the canonical
surface this page links to as its continuation — is itself **not** in
`_navlinks.html.j2` today. That is out of scope here, but a reader who follows
the continuation lands on a page with no nav entry of its own.

## B-3 · Registry derivation and the one override that is hand-written

Most of this is **derived, not listed** — three of the four registry surfaces
pick the page up automatically once `site/ontology.html` is tracked:

| Surface | File | Mechanism |
|---|---|---|
| Page inventory | `scripts/build_product_page_registry.py:612-613` | `git ls-files site/*.html` — **automatic** |
| Sitemap | `lib/seo.py:293-313` (`discover_core_pages`) | globs `site_dir/*.html` — **automatic** |
| Asset access | `config/site_access.yml` `public.exact` | **LITERAL — and I got this wrong on the first pass. See B-7.** |
| Judgment fields | `config/product_experience/page_registry_overrides.yml` | **LITERAL — the only hand-maintained input** |

The one real entry, alongside `macro:alerts` (`:914-915`):

```yaml
  macro:ontology:
    archetype: "instrument_analyzer"
```

`instrument_analyzer` is the archetype this page was designed to, per
`research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md`. **This file is under heavy
concurrent edit** by the market-os workspace-expansion program (three of its
last three commits: #6852, #6851, #6848), so it is the highest-conflict line in
the packet and belongs in whichever PR is touching it anyway.

`app/deploy/Caddyfile` was **not** opened — the census hit its budget there. It
is named by `config/site_access.yml:28-29` as carrying a byte-matching
`public`/`@reg_asset` list. Anyone applying this packet must check it before
claiming the asset path is complete; that gap is stated rather than guessed.

## B-4 · CI test selection — the packet's load-bearing item

**This repo has no broad `pytest tests/` anywhere.** `.github/workflows/ci.yml`
records the measurement in its own comment (`:3016-3020`): 1135 of 1491
`tests/test_*.py` suites were named by **no** `run:` step in **any** of the 51
workflows, and "an unnamed suite is genuinely never executed". `legacy-jobs.yml`
carries 1361 literal `tests/test_*.py` paths.

Verified for this feature:

```
$ grep -rn "ontology_explorer" .github/
(no matches)
```

So the four suites — `tests/test_ontology_explorer_{contract,identity,transport,shell}.py`,
**149 tests** — do **not** run in CI today. They pass locally and they are real,
but until this hunk lands, CI green on this PR says nothing about them, and this
PR does not claim otherwise.

The hunk, in the shape every neighbouring job uses:

```yaml
  ontology-explorer:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - name: install test deps
        run: pip install pytest pyyaml jinja2 fastapi httpx
      - name: ontology explorer suites
        run: python -m pytest tests/test_ontology_explorer_contract.py tests/test_ontology_explorer_identity.py tests/test_ontology_explorer_transport.py tests/test_ontology_explorer_shell.py -q
```

**`.github/ci/legacy-jobs.yml` is the four-way contended file** (#6828, #6834,
#6842, #6514) — the real collision on this vertical, and the reason this hunk is
documented rather than applied. Note also that `run_ci_pack.py` rebalances packs
whenever any job's weight moves, so adding a job shifts pack membership; do not
hard-code a pack index anywhere.

## B-5 · Telemetry — the honest finding is that there is no per-page convention

**Owner:** `templates/theme.js:40-78`. GA4 (`G-BZTZ9W1BBB`) is injected once,
site-wide, from the one shared script every page already loads. It is **dormant
unless `window.ENABLE_GA4 === true`**, skips localhost, and defers to idle so a
GFW-blocked tag never delays paint.

```
$ grep -rn "gtag('event'" templates/*.js templates/*.j2
(no matches)
```

There is **no custom-event convention in this repo** — every page emits
`page_view` and nothing else. So this page inherits telemetry by loading
`theme.js`, and Stage B adds no event. Minting the repo's first custom event for
this feature would set a precedent that is not mine to set.

If F00 later wants one, two constraints are not negotiable:

1. It must sit behind the same `window.ENABLE_GA4` opt-in, or it will fire on
   the China mirror where the endpoint is blocked.
2. **The payload may carry the event name only — never a reading, state code,
   leg name, freshness value or digest.** Every one of those is paid current
   output, and an analytics beacon is a third-party egress. The whole transport
   design of this feature (`private, no-store`, `Vary: Authorization`, no
   browser storage) would be undone by one `gtag('event', 'ontology_state',
   {state: snapshot.state.code})`.

---

## What Stage B does not change

No transport law, no composer behaviour, no owner artifact, no `data/` write, no
entitlement logic. If every hunk above were applied and then reverted, the page
would still serve exactly the same bytes to exactly the same readers at its
direct URL. That is deliberate: discoverability is separable from correctness,
and this vertical shipped correctness first.

---

## B-6 · The gate found this before I could hand the packet over

`contract-delta` is red on this PR, and it is **my** red. It is also the repo's
own instrument for the finding in B-4, reached independently:

```
contract-delta: tests/test_ontology_explorer_{contract,identity,transport,shell}.py
  is a new pytest suite named by no run: step in any workflow — wire it into the
  job that owns its subject in .github/ci/legacy-jobs.yml, or add a reasoned row
  to config/unrun_test_waivers.yml

contract-delta: {biocatalyst-history, biocatalyst-serving, flow-surface,
  unrun-government-revenue-grader}: import closure now reaches
  engine/ontology_explorer.py, which .github/ci/legacy-jobs.yml's declared
  `paths:` for <job> does not cover — widen <job>'s `paths:` to include
  engine/ontology_explorer.py (widening is always the safe direction)
```

The closure exists because `app/main.py` includes the router, the router imports
the composer, and those four curated jobs import `app.main`. Their `paths:`
blocks already carry engine files added for precisely this reason — "this
curated job reaches that app router, so its exclusive declaration must cover the
exact transitive closure rather than silently skipping changes to these
dependencies" (`.github/ci/legacy-jobs.yml:1591-1594`). Mine is the same case.

**The hunk** — one line per job, into each existing `paths:` list
(`flow-surface` :1586, `biocatalyst-serving` :6619, `biocatalyst-history` :7202,
`unrun-government-revenue-grader` :12355):

```yaml
      # The ontology-explorer route is reached through app/main, so a change to
      # its composer must re-run this job rather than be silently skipped.
      - "engine/ontology_explorer.py"
```

plus the `ontology-explorer` job from B-4 for the four suites.

### Why this is not fixed in this PR

Both remedies land in `.github/ci/legacy-jobs.yml`, the four-way contended file
(#6828 / #6834 / #6842 / #6514), and the standing order for this operation is
"no edits to held shared files until F00's exact hunk ruling". So this is
returned as a **concrete expansion request** rather than taken unilaterally —
which is the mechanism the same order names ("unless a concrete expansion is
returned").

**Two things I deliberately did not do:**

* **I did not make the engine import lazy to break the closure.** It would not
  have worked — `scripts/audit_unrun_tests.py:513` walks the AST with
  `ast.walk`, which is scope-insensitive and also catches
  `import_module("literal")` — and anything that *did* work would have been
  evasion of a gate that is measuring something true.
* **I did not waive the four suites.** `config/unrun_test_waivers.yml` would
  clear half the red, and its own header says the default answer for a new dark
  suite is to wire it in. A waiver here would assert these suites are unrun *on
  purpose*, which is false: they are unrun pending a file I was told not to
  touch. If F00 rules that the wiring waits, a waiver row with that reason and a
  delete condition is the honest form — but that is a ruling, not my call.

Net effect: the PR carries one genuine red whose cause is diagnosed, whose fix
is written, and whose application is blocked by an ownership rule rather than by
a defect. It is not spurious and it is not disowned.


---

## B-7 · Two corrections to this packet, from Sol analytical support

A support session checked this packet against the repo and found two claims in
it that were **false**. Both are corrected here rather than quietly edited,
because the wrong versions were already delivered.

### B-7.1 · The public assets ARE gated — this was a product bug, not a doc error

The first pass said `config/site_access.yml` needs no entry, reasoning from the
file's own header that HTML page shells stopped being gated there in 2026-08-04.
That part is true and it is not the part that matters: the same header says the
`public` list decides **ASSET** reachability, and Caddy's `@reg_asset` route is
**default-deny**, compared byte-for-byte against this file.

`/ontology.css` and `/ontology.js` are not in it:

```
$ grep -n "ontology" config/site_access.yml
(no matches)
```

Every comparable page lists its assets individually — `/biocatalyst.css`,
`/biocatalyst.js` (`:103-104`), `/onboard.css`, `/onboard.js` (`:214-215`).
So today an anonymous visitor would be served the public shell **without its
stylesheet or its client**, which defeats the "public-safe discoverable shell"
the frozen mission requires. This is not a Stage B nicety; it is a real break in
Stage A's own promise, and it is only invisible because nothing links to the page
yet.

The hunk, into `public.exact`:

```yaml
    # F04-X1 WTI Live Trace. The shell is public and carries zero current values;
    # every current reading is fetched from the authenticated API instead, so the
    # presentation assets are as public as the page they paint.
    - /ontology.css
    - /ontology.js
```

`config/site_access.yml`'s own rule requires the byte-matching `app/deploy/Caddyfile`
line in the same PR. Both are in #6828's declared Caddy/public-access territory,
so this joins the expansion request in B-6 rather than being taken here.

**How the error happened, since that matters more than the correction:** I quoted
the header sentence that says the public list governs assets, and then reasoned
about the page instead of about the assets. The check that would have caught it
is the one I did not run — grepping the file for the asset names.

### B-7.2 · There IS a custom-event convention, and I said there wasn't

B-5 concluded "this repo has no per-page custom event convention" on the strength
of one search: `grep -rn "gtag('event'" templates/`. That search was correct and
the conclusion drawn from it was not. The real owner is
`mmTrack` / `mmTrackGrowth` (`templates/theme.js:197`), which beacons to
`/api/collect` alongside a growth registry — a first-party transport, not the GA4
block I was looking at.

So the honest Stage B position is the opposite of what B-5 says: there is an
existing owner to integrate with, and this page should use it rather than
inventing anything. The constraint I stated in B-5 still holds and now matters
more, because `/api/collect` is a first-party endpoint that records events: the
payload may carry the event name only — never a state code, leg name, freshness
value or digest, all of which are paid current output.

B-5's GA4 description is accurate as far as it goes; its **conclusion** is
withdrawn.

### B-7.3 · Also carried, already open in B-6

The four suites need real `ci-pack` selection plus import/dependency wiring —
which is what `contract-delta` is red about, and what B-6 returns as the
expansion request.

## B-8 · The exact patch, proven against the real gates without touching the held file

`contract-delta`'s eight findings were returned in B-6 as a request. They are now
returned as a **verified patch**. Both gates were run against a copy of the manifest
in scratch, never against the tracked file, which stayed byte-identical throughout
(`git diff -- .github/ci/legacy-jobs.yml` → 0 lines at every step).

Method: `scripts/run_ci_pack.curated_exclusive_closure_findings` takes a manifest
*path*, and `scripts.audit_unrun_tests.CI_MANIFEST` is a rebindable module global,
so both halves of the gate can be pointed at a candidate file.

| Half | Gate | Unpatched | Patched |
|---|---|---|---|
| Import closure | `curated_exclusive_closure_findings` | 4 findings, identical to CI | `NONE` |
| Unwired suites | `gated_unrun_suites` | 4 of mine gated | 0 gated, no collateral change |

**Shape of the patch: 5 hunks, +27 lines, −0.** Four single-line `paths:` insertions
(`biocatalyst-history`, `biocatalyst-serving`, `flow-surface`,
`unrun-government-revenue-grader`), each declaring `engine/ontology_explorer.py`,
which they reach through `app/main.py:2248` → `app/ontology_explorer.py:40`. Plus one
contiguous `ontology-explorer` job appended at end-of-file — a new block, so no other
lane's lines are touched in a manifest twelve open PRs are queued behind.

### The correction that only validation caught

The first draft of that job was `scope: exclusive` with a curated six-path scope, and
it was **wrong**. `load_legacy_jobs` rejected it outright — an exclusive job must
declare the test files its own commands read — and once those four test paths were
added, its inferred closure expanded to roughly **500 files**, because these suites
drive the router through the application and therefore transitively import most of
`app/`, `engine/` and `lib/`. Curating that would have produced a job re-selected by
nearly every change in the repository: the precise opposite of what exclusive scoping
is for.

The job is therefore deliberately **not** exclusive; inference derives its scope. This
is the load-bearing detail of B-8, and it is the reason the patch is worth proving
rather than proposing — the proposal in B-6 would have shipped a hunk that was both
invalid and absurd, and no amount of re-reading it would have revealed that.

### What is still not proven

Nothing here proves the job *passes* — only that it satisfies the two gates that are
currently red. The suites pass locally (185 green); their behaviour on a CI runner is
unproven until the job actually runs, which cannot happen until the manifest opens.
