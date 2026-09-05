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

The icon above reuses an existing sprite class deliberately: minting a new
`submenu-icon-*` would add a second shared-file edit
(`templates/navigation-refresh.css`) for no product gain. Pick a dedicated icon
in a later pass if the nav owner wants one.

## B-3 · Registry derivation and the one override that is hand-written

Most of this is **derived, not listed** — three of the four registry surfaces
pick the page up automatically once `site/ontology.html` is tracked:

| Surface | File | Mechanism |
|---|---|---|
| Page inventory | `scripts/build_product_page_registry.py:612-613` | `git ls-files site/*.html` — **automatic** |
| Sitemap | `lib/seo.py:293-313` (`discover_core_pages`) | globs `site_dir/*.html` — **automatic** |
| Asset access | `config/site_access.yml:7-8` | HTML shells are no longer gated here (operator 2026-08-04); only `premium.enforced_early` prefixes 403. This page ships no gated asset prefix, so **no entry needed** |
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
