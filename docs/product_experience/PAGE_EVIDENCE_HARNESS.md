# Page evidence harness

`scripts/capture_page_evidence.py` — bounded browser evidence capture and UX-smell
census for the pages named in the product page registry.

It is an **evidence tool**. It loads a fixed list of routes anonymously, screenshots
a declared state matrix, and writes down facts a human could count by hand. It
produces no score, no grade, no ranking, and no "this page is bad" label. The
report's own header says it: *heuristics identify review targets; they do not
determine that a page is bad.*

---

## 1. Quick start

```bash
# constants + a canned end-to-end proof; opens no browser, touches no network
python3 scripts/capture_page_evidence.py --self-check

# capture the P0 macro pages from a local build (recommended default)
python3 scripts/capture_page_evidence.py --site-dir site

# capture one route against the live origin
python3 scripts/capture_page_evidence.py \
  --routes /index.html --base-url https://www.mastermind-x.com \
  --viewports desktop --locales en --themes light,dark --max-pages 1

# committed artifacts + a human table
python3 scripts/capture_page_evidence.py --site-dir site \
  --emit-md docs/product_experience/ux_smell_report.md
```

Requires playwright **locally** (not a repo dependency, deliberately):

```bash
python3 -m pip install playwright && python3 -m playwright install chromium
```

### CLI

| flag | default | notes |
| --- | --- | --- |
| `--registry` | `data/product_experience/page_registry.json` | schema `mastermind.page_registry.v1` |
| `--priority` / `--repo` | `P0` / `macro` | registry-row filters |
| `--base-url` \| `--site-dir` | — | exactly one is required |
| `--routes` | — | comma list; overrides registry selection |
| `--output-dir` | `data/product_experience/evidence` | gitignored, local only |
| `--manifest` | `data/product_experience/p0_evidence_manifest.json` | committed |
| `--smells` | `data/product_experience/ux_smell_report.json` | committed |
| `--emit-md` | — | markdown rendering of the smell report |
| `--viewports` / `--locales` / `--themes` | `desktop,tablet,mobile` / `en,zh` / `light,dark` | axes to attempt |
| `--max-pages` | `30` | hard cap; excess rows are recorded as excluded |
| `--delay-ms` | `500` | politeness sleep between page loads |
| `--timeout-s` | `30` | per-navigation timeout |
| `--as-of` | now (UTC) | pins `generated_at`; makes a run byte-reproducible |
| `--observer-config` | built-in | JSON overriding panel selectors, probes, caps |
| `--headed` / `--self-check` | off | |

Exit codes: `0` captured · `2` usage or registry error · `3` some page captured no
state at all · `4` `verifier_unavailable` (no browser).

### Running without a registry

`--routes` with no registry file on disk synthesizes minimal rows (`page_id` derived
from the route, no declared themes/locales), so every requested axis is attempted.
This is the smoke-test mode. If a registry *does* exist and a `--routes` entry
matches one of its rows, that row is reused — so a registry-declared dark-only page
stays dark-only even when named explicitly.

---

## 2. State matrix

Per page, only where the registry says the axis is supported:

| dimension | values | how it is set |
| --- | --- | --- |
| viewport | desktop 1440×900 · tablet 820×1180 · mobile 390×844 | browser context viewport |
| locale | `en` · `zh` | `data-lang` on `<html>` (see below) |
| theme | `light` · `dark` | `data-theme` on `<html>` (see below) |
| access | **anonymous only** | no session, ever |

A registry row that declares `themes: ["dark"]` produces **no light cell** — the
excluded axis is written into that page's `gaps` with the reason, rather than
attempted and failed. Same for `locales`.

### How the registry narrows a page

| registry field | effect |
| --- | --- |
| `priority` / `repo` | row filters; defaults `P0` / `macro` |
| `route_kind: "page"` | captured at `route` |
| `route_kind: "family"` (e.g. `/dossier/<id>.html`) | **excluded** — a family stands for many URLs and is not itself capturable. Capture one by naming a concrete URL: `--routes /dossier/nvda.html`. A row carrying an `exemplar_route` is captured at that route automatically. |
| `themes` / `locales` as a list | intersected with the requested axes; the difference becomes a gap |
| `themes` / `locales` as `"unknown"` | the registry could not resolve the axis, so it is treated as **silent**: every requested value is attempted and `applied_theme` / `applied_locale` record what the page actually did. An unresolved axis must never read as "supports nothing" — that would expand to zero cells and produce a page with no evidence at all. |

### How locale and theme are applied

Macro pages are same-DOM bilingual: both language spans are always in the markup and
CSS shows one off `html[data-lang]`. The harness therefore applies state exactly the
way the site's own toggle does (`templates/theme.js`):

- `setTheme(tm)` sets `data-theme` on `<html>`, writes `localStorage.theme`, and
  **removes `localStorage.themeAuto`**.
- `setLang(lg)` sets `data-lang`, syncs `document.documentElement.lang`
  (`zh` → `zh-CN`), writes `localStorage.lang`, and fires `langchange`.

Two steps, both load-bearing:

1. **Pre-navigation seed** (`add_init_script`, before any page script runs) writes
   `theme`/`lang` and clears `themeAuto`. Without clearing it, theme.js's boot lift
   re-derives the theme *from the local hour* and silently overrides the attribute —
   the same trap `scripts/light_mode_sweep.py` documents.
2. **Post-load apply** calls the page's own `window.setTheme` / `window.setLang`
   when present, so the widgets that listen for `themechange` / `langchange`
   (gauges, sparklines, Plotly charts) recolour the way they do for a real user.

Whatever `<html>` actually settled on is written back per state as `applied_theme` /
`applied_locale`, and a divergence from what was requested is recorded as a
`state_application` gap.

> **`applied_theme` is the attribute, not a repaint.** Measured on the live landing
> 2026-08-11: `data-theme=dark` applied cleanly while the hero rendered identically
> to light — the hand-authored landing keeps a theme-invariant hero by design. A
> matching `applied_theme` proves the state was accepted, never that the pixels
> changed. Compare the screenshots for that.

---

## 3. Honesty rules

These are the point of the tool, not decoration.

1. **Anonymous only.** No credential is entered, stored, synthesized, or read. Free
   / Essential / Pro are recorded on every page as gaps:
   `{"dimension": "access", "value": "pro", "captured": false, "reason": "requires
   authenticated session; not automatable without approved fixtures"}`.
   A tier state will only ever be captured through approved fixtures, and until
   those exist the manifest says so out loud.
2. **Premium payload cannot leak.** Because every load is anonymous, the artifacts
   contain only what a logged-out visitor is served. Nothing gated can enter a
   screenshot, a metric, or the manifest by construction — not by policy.
3. **Loading / empty / stale / error are gaps in v1**, reason `"state not
   synthesizable against static output"`. Faking them against a static build would
   produce a screenshot of a state the product never shows.
4. **A missing capture is written down, never omitted.** A 404, a timeout, or a
   driver error is `captured: false` with the error text; the run continues. A page
   that captured nothing still carries every metric key, all null, and
   `screenshot_completion: 0.0` — a page can be blind, but it cannot be silently
   absent.
5. **No browser is never a pass.** Missing playwright or chromium exits `4` with
   outcome `verifier_unavailable`, prints the install command, and **writes no
   artifact** — a no-browser run must never overwrite committed evidence with an
   empty one.
6. **No judgment vocabulary.** No metric is named score/grade/rating/rank/severity,
   nothing is weighted or combined, and the smell report carries no verdict column.
   Both the JSON and the markdown lead with the disclaimer.
7. **Every heuristic publishes its own false-positive risk** in `metric_notes`,
   which travels inside the committed report.

---

## 4. What is measured

One injected observer script per page load returns one JSON blob; the driver adds
console and network counts. `innerText` is layout-aware, so the hidden half of the
bilingual DOM is excluded automatically for the locale that is not showing.

| metric | definition | caveat |
| --- | --- | --- |
| `document_height_px` | `documentElement.scrollHeight` at that viewport | |
| `section_count` | direct `<section>` children of `<body>` + direct element children of `<main>` | approximation of "how many blocks" |
| `heading_counts` | visible `h1`–`h6` counts | |
| `duplicate_heading_texts` | case-folded visible heading text seen more than once | repeated tab labels are legitimate |
| `panel_count` | visible matches of `.card,.panel,[class*='card']` (configurable) | class-name heuristic; over- and under-counts expected |
| `visible_word_count` | whitespace-split `body.innerText` | Chinese is not word-segmented — a zh capture reads lower than en for identical copy (measured: landing 1,886 en vs 1,201 zh) |
| `long_paragraph_count` | visible `<p>` over 120 words (configurable) | |
| `raw_slug_hits` / `_count` | visible text matching `\b[a-z][a-z0-9]+(_[a-z0-9]+){2,}\b` | 3+ segment snake_case; deliberately quoted identifiers and file names match too |
| `todo_placeholder_hits` / `_count` | `TODO\|FIXME\|PLACEHOLDER\|lorem ipsum`, case-insensitive, visible | |
| `horizontal_overflow` | `scrollWidth > clientWidth` | |
| `elements_wider_than_viewport` | visible elements wider than the viewport (+1px tolerance) | |
| `console_error_count` | distinct console `error` texts across every captured state | |
| `request_count` / `payload_bytes_total` | driver request/response listeners, reference state | bytes exclude responses the driver cannot size |
| `asof_present` / `source_present` | selector **or** case-insensitive text probe (`[data-asof]`, `.asof`, `.freshness`; "as of", "数据截至") | approximate contract probe; absence is a prompt to look, not a verdict |
| `screenshot_completion` | captured states / attempted states | registry-excluded axes are not attempted |

Scalar metrics come from the **reference state** — the first captured cell in matrix
order, named in `metrics.measured_in`. One page load is one measurement; a blend of
six would describe no state that exists. Viewport-sensitive metrics additionally
appear per viewport under `metrics.by_viewport`.

Lists are capped at 25 distinct samples so a committed artifact stays bounded.

---

## 5. Outputs

| path | committed? | contents |
| --- | --- | --- |
| `data/product_experience/evidence/<sha256[:16]>.png` | **no** (gitignored) | content-addressed full-page screenshots; identical bytes collapse onto one file |
| `data/product_experience/p0_evidence_manifest.json` | yes | schema `mastermind.p0_evidence.v1` — target, axes, selection, per-page states (with each shot's full sha256, byte size, and pixel dimensions), metrics, console errors, gaps |
| `data/product_experience/ux_smell_report.json` | yes | schema `mastermind.ux_smell_report.v1` — per-page metrics, metric notes, disclaimer, zero interpretation |
| `--emit-md` target | your choice | the same report as a table sorted by route |

The screenshots are gitignored on purpose: a full P0 sweep is ~360 PNGs at ~0.5 MB,
they are re-derivable, and the manifest's digests keep them citable without the
bytes entering Git. **Cite a screenshot by its sha256**, and re-run the capture to
regenerate it.

`target.resolved_sha_or_none` carries the checkout's git HEAD in `--site-dir` mode
and is `null` for `--base-url`: a live origin does not disclose the commit it is
serving, and guessing would be a fabricated provenance claim.

Runs are deterministic — same registry, same driver, same `--as-of` produces
byte-identical JSON, so a re-run diffs cleanly.

---

## 6. Politeness — this is a census, not a crawler

- **No link following, ever.** Only registry routes (or explicit `--routes`) are
  requested. There is no queue, no frontier, no discovery.
- **Sequential**, one page load at a time, `--delay-ms` (default 500 ms) between
  loads.
- **Hard `--max-pages` cap** (default 30); rows beyond it are recorded as excluded
  rather than quietly captured.
- **Identified UA:** `mastermind-page-census/1.0 (internal product observability)`.
- **A dead route is not hammered.** One load failure on a page marks the remaining
  states of that page not-attempted with the load error, instead of retrying the
  same broken URL for every remaining cell.
- Prefer `--site-dir` (a local build served on an ephemeral loopback port, the
  `scripts/light_mode_sweep.py` pattern) over `--base-url`. The live origin is for
  spot checks.

---

## 7. CI stance

**This tool is never wired into CI or the nightly.** Render budget is law here
(~67 min, 4-core-bound); a browser sweep belongs off the render path, run locally
during product-experience work — the same stance as `scripts/light_mode_sweep.py`.

`tests/test_capture_page_evidence.py` is CI-safe and hermetic: it opens no browser,
no socket, and no file outside `tmp_path`. The driver is an injected in-memory
`FakeDriver` through the same `PageDriver` seam production uses.

> `pytest.importorskip("playwright")` is deliberately **absent**. CI installs
> minimal deps and playwright is not a repo dependency, so an importorskip would
> SKIP green forever and prove nothing. Two tests pin the boundary: an AST check
> that `playwright` is imported only inside `playwright_page_driver`, and a
> subprocess run of `--self-check` asserting `playwright` never enters
> `sys.modules`.

Run it with `TZ=UTC python3 -m pytest tests/test_capture_page_evidence.py -q`
(CI runs UTC; the suite is TZ-agnostic because every fixture pins `--as-of`).
