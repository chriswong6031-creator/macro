# Product page census — 2026-08

Operation Institutionalize, HANDOFF C deliverable. Internal research document.

Sources: `data/product_experience/page_registry.json` (309 rows, schema
`mastermind.page_registry.v1`, `generated_at 2026-08-11T00:00:00Z`),
`data/product_experience/p0_evidence_manifest.json` (+ `_terminal`),
`data/product_experience/ux_smell_report.json` (+ `_terminal`),
`config/product_experience/page_registry_overrides.yml`.

**Nothing in this document is a verdict on a page.** Heuristics identify review
targets; they do not label a page bad. That is the harness's own stance
(`data/product_experience/ux_smell_report.json` → `disclaimer`) and it is this
report's stance. Section 6 is a review queue, not a defect list.

---

## Executive summary

1. **The console errors on 12 of 13 macro P0 pages have one systemic cause, not
   twelve page bugs — and the cause is the registration wall, not a content-type
   defect.** 36 of the 37 macro error entries are the anonymous tier hitting the
   asset regwall: `app/regwall.py:177-199` `_deny()` answers a non-allowlisted
   asset request with `401` + `application/json` (`{"locked":true,…}`), Caddy
   streams that denial in place of the file (`app/deploy/Caddyfile:346-352`), and
   under the global `nosniff` header Chrome reports it as a refused-MIME script
   error (24 entries: `mm_brain.js` on **12 of 12** pages that request it, plus
   `wh_banner.js` 5, `illus.js`/`illus.css` 2/2, `mtf.js` 2,
   `china_risk_state_live.js` 1) or as a bare 401 (12 entries). The split is
   exact: all six failing assets sit outside the `PUBLIC-BOUNDARY` allowlist
   (`app/deploy/Caddyfile:343`); all eight passing scripts sit inside it — and
   `templates/theme.js:5029`, which injects `mm_brain.js` from the same origin
   and directory, executed everywhere. Consequence: the customer chat AI never
   ran on any measured macro page **for anonymous visitors**, which is either
   intended tiering or a defect — `scripts/check_hub_a11y.py:45` asserts the
   Brain launcher mounts "on EVERY page", so the intent question goes to the
   HANDOFF A access census / operator. This census records the fact and
   prescribes nothing (fixing it would be an access-policy change, out of
   HANDOFF C scope). These entries are 24 of 37 macro console-error entries as
   MIME-refusals (63% *of console-error entries*, not of everything measured;
   census-wide the terminal capture adds one 403, making 38).
2. **Ownership is 309/309 `unowned`, and 180 of 274 live macro rows sit in no nav
   family — but the number to act on is 63.** The other 117 are 52 `fund_*` and
   46 `strategy_*` detail pages reachable from their index pages, 13 family rows,
   and 6 `report_*` one-offs. At least 5 more (`about`, `about-research`,
   `disclaimer`, `privacy`, `terms`) are footer-linked and read `none` only
   because the derivation never opens `templates/_public_footer.html.j2`.
3. **Evidence covers 17 of 309 rows (5.5%), anonymous only.** 4,316 URLs sit
   behind 18 macro family rows that the harness structurally cannot capture (no
   row carries an `exemplar_route`); Free/Essential/Pro are declared gaps on
   every captured page. Any HANDOFF B decision outside the P0 set is being made
   without measurement, and should say so.
4. Mobile horizontal overflow exists on **5 of 13** macro P0 pages
   (`macro:index`, `research_vault`, and all three long product pages) — invisible
   in the committed markdown table, which prints only the desktop reference state.
5. Terminal `/discover`, `/options`, `/portfolio` measured **76–81 visible words
   at 900px**: the anonymous capture measured the `SignupGate`/paywall, not the
   product surface. Those three rows carry no evidence about the page itself.
6. `mastermind:portfolio_desk` is documented as session-auth-gated
   (`app/web.py:2303`) while `app/auth.py:11-13` states the browser login was
   removed entirely — the page is anonymous to anyone with the URL.
7. Five geography board pairs render **two live routes from one template at
   adjacent write sites in one builder** (§3.A) — the strongest duplicate signal
   in the census.
8. **4 of 13** macro P0 pages render zero `h1` (`macro`, `plans`, `china`, `hk`);
   `source_present` is `false` on all 13, which is either a site-wide provenance
   gap or a probe that does not match this site's markup — it discriminates
   nothing and is excluded from the §6 composite.
9. The registry reconciles exactly against the repo: 269 individual macro rows +
   4,316 URLs behind 18 family rows = **4,585** = `git ls-files site/*.html`.
10. `data_sources` is `[]` on all 309 rows and `owner` is `unowned` on all 309 —
    both by v1 design, not by omission.

---

## 1. Scope & method

**What was censused.** Every user-visible route across three repos, one row per
route or per route FAMILY where one builder renders thousands of pages from one
template.

| repo | rows | read from | SHA |
|---|---:|---|---|
| macro | 287 | this worktree, `git ls-files site/*.html` | `6560d5a809bf75bd925eae08037e9118daff44c9` |
| terminal (charting-app) | 15 | git ref `origin/master` (never the working tree) | `32f4254f11d3abc26ad891bbb14e4395b0ec6e82` |
| mastermind | 7 | **working tree**, recorded `tracked_worktree_clean: true` | `17c40884de5bfbf9309f523e6787e4fd82dae266` |

Provenance is asymmetric and the artifact says so: terminal rows come from a ref,
mastermind rows from a clean worktree (`sources.mastermind.read_from`). Macro's
inventory is `git ls-files`, so a sparse checkout (this worktree has no `site/`
directory materialised) does not change the count.

**Reconciliation.** 287 macro rows = 269 individual pages + 18 families. The 18
families cover 4,316 committed pages (per-row notes, e.g. `macro:stocks_family`
"2180 committed pages under site/stocks/"). 269 + 4,316 = 4,585 =
`sources.macro.tracked_html_pages`. The census loses no page.

**What the harness can see.** `scripts/capture_page_evidence.py` loaded a fixed
route list anonymously against live origins and recorded facts a human could
count: heights, headings, word counts, panel counts, console errors, request and
byte counts, two contract probes. No link following, no queue, no discovery —
only the routes it was handed.

| capture | target | pages | states | axes |
|---|---|---:|---:|---|
| macro P0 | `https://www.mastermind-x.com` | 13 | 156/156 | 3 viewports × en/zh × light/dark |
| terminal P0 | `https://app.mastermind-x.com` | 4 | 12/12 | 3 viewports, en + dark only |

Viewports: desktop 1440×900, tablet 820×1180, mobile 390×844. Screenshots are
content-addressed under `data/product_experience/evidence/` (gitignored); the
manifests carry each shot's full sha256, so a shot is citable without the bytes.

**What it structurally cannot see.**

- **Any authenticated state.** No credential is ever entered, so Free / Essential
  / Pro are recorded as gaps on every page, not attempted and failed.
- **Family rows.** A family stands for many URLs and is excluded from capture.
  The harness reads an `exemplar_route` field if a row carries one; **no row
  carries one today**, so all 19 families are uncaptured.
- **Loading / empty / stale / error states** — "not synthesizable against static
  output" in v1.
- **Terminal zh.** Terminal lexicons are React-side; a `data-lang` attribute
  toggle would not honestly produce a zh render, so terminal captured `en` only.
- **Mastermind.** No public base URL is recorded for the FastAPI app, so all 7
  rows are uncaptured — including the P0 `portfolio_desk`.
- **The commit being served.** `target.resolved_sha_or_none` is `null` for both
  captures: a live origin does not disclose its commit, and guessing would be
  fabricated provenance. The registry SHAs above therefore describe the *source*,
  not necessarily the *bytes measured*.

**Judgment vs derivation.** Only `priority`, `archetype`,
`primary_user_question`, `owner`, lifecycle rulings and access facts a static
reader cannot honestly see live in
`config/product_experience/page_registry_overrides.yml`. Everything else is
re-derived on every run. The overlay can never invent a route, builder, or
template. `"unknown"` is a recorded value, never `null` and never a guess.

---

## 2. P0 route set (18 rows)

Priority is assigned only in the overrides overlay; v1 seeds P0 only, and P1–P3
assignment is a separate work item. Questions marked **(overlay)** are the
overrides file verbatim; **(proposal)** are this report's, and are not in any
artifact.

| # | page_id | route | access_shell / payload_tier | nav_family | primary user question |
|---|---|---|---|---|---|
| 1 | `macro:index` | `/` | anonymous / public | public_nav.public | What is this product and why should I trust it? (overlay) |
| 2 | `macro:start` | `/start.html` | anonymous / public | product_nav.brand | Where do I start today? (overlay) |
| 3 | `macro:macro` | `/macro.html` | anonymous / public_shell_premium_payload | product_nav.brand | What is the macro regime right now? (overlay) |
| 4 | `macro:us_stocks` | `/us_stocks.html` | anonymous / public_shell_premium_payload | product_nav.united_states | Which US stocks are set up right now? (overlay) |
| 5 | `macro:china` | `/china.html` | anonymous / public_shell_premium_payload | product_nav.china | What is the China regime right now? (overlay) |
| 6 | `macro:hk` | `/hk.html` | anonymous / public_shell_premium_payload | product_nav.hong_kong | What is the Hong Kong regime right now? (overlay) |
| 7 | `macro:confluence_screener` | `/confluence_screener.html` | anonymous / public_shell_premium_payload | product_nav.research | Which names line up across the signal stack today? (overlay) |
| 8 | `macro:research_vault` | `/research_vault.html` | anonymous / public | product_nav.research | What has the research desk published? (overlay) |
| 9 | `macro:plans` | `/plans.html` | anonymous / public | public_nav.public | What do I get, and what does it cost? (overlay) |
| 10 | `macro:products_index` | `/products/index.html` | anonymous / public | public_nav.public | What products are there? (overlay) |
| 11 | `macro:products_market_terminal` | `/products/market-terminal.html` | anonymous / public | public_nav.public | What is the Market Terminal and should I sign up? (overlay) |
| 12 | `macro:products_mastermind_ai` | `/products/mastermind-ai.html` | anonymous / public | public_nav.public | What does the AI actually do for me? (overlay) |
| 13 | `macro:products_market_dashboards` | `/products/market-dashboards.html` | anonymous / public | public_nav.public | What do the dashboards cover? (overlay) |
| 14 | `terminal:terminal` | `/terminal` | anonymous / public_shell_premium_payload | app_nav.rail | What is this instrument doing? (overlay) |
| 15 | `terminal:discover` | `/discover` | signed_in / unknown | app_nav.rail | What is worth looking at right now? (overlay) |
| 16 | `terminal:options` | `/options` | paid / premium | app_nav.rail | Where is the options market positioned? (overlay) |
| 17 | `terminal:portfolio` | `/portfolio` | signed_in / unknown | app_nav.rail | How is my book doing? (overlay) |
| 18 | `mastermind:portfolio_desk` | `/portfolio_desk` | anonymous / public | unknown | What is the desk holding and why? (overlay) |

All 18 questions come from the overlay; no page in the P0 set needed a proposal.
`macro:index` is P0 at route `/` but was captured at `/index.html` under the
synthesized page_id `index.html` (§8, gap G-9).

---

## 3. Duplicate / overlapping surfaces

Evidence only. "Overlap" here means two live surfaces answer a materially similar
user question, or one artifact is served at more than one route. Whether that is
a defect is a HANDOFF B question.

| # | cluster | routes | evidence | what the overlap is |
|---|---|---|---|---|
| A | **Geography board pairs** | `/china.html`+`/china_stocks.html`; `/hk.html`+`/hk_stocks.html`; `/canada.html`+`/canada_stocks.html`; `/intl.html`+`/intl_stocks.html`; `/macro.html`+`/us_stocks.html` | one template each (`templates/china.html.j2`, `hk`, `canada`, `intl`, `dashboard.html.j2`) written at adjacent sites in one builder: `build_china.py:1549`/`:1567`, `build_hk.py:1447`/`:1457`, `build_canada.py:1141`/`:1150`, `build_intl.py:910`/`:911`, `build_site.py:6287`/`:6288` | 10 live routes, 5 templates. Four of the five pairs sit in the SAME nav group. `macro:us_stocks` additionally has a second write site (`build_site.py:5892`). |
| B | **Lab / v2 variants of shipped boards** | `/us_stocks_v2.html`, `/us_stocks_lab.html`, `/china_stocks_lab.html`, `/hk_stocks_lab.html`, `/tech_lab.html`, `/quant_lab.html`, `/signal_lab.html` | `lifecycle: lab`, `nav_family: none`; 5 named in `lib/seo.py:103-107` (`us_stocks_v2` commented "staging variant of us_stocks (not the canonical)") | 7 live-built routes shadowing canonical boards. `quant_lab`/`signal_lab` are NOT in the SEO exclusion list — they are lab-lifecycle but sitemap-eligible. |
| C | **Per-ticker lookup variants** | `/stock.html`, `/intl_stock.html`, `/canada_stock.html`, `/china_lookup.html`, `/hk_lookup.html` | 3 named in `lib/seo.py:111-113` as "noncanonical query variants (D12 §10.2)"; all 5 `nav_family: none` | 5 lookup surfaces against a canonical per-ticker family `/stocks/<id>.html` (2,180 pages, `public_nav.public`). |
| D | **Screener/board ↔ Terminal** | `macro:confluence_screener`, `macro:options_screener`, `macro:watchlist` vs `terminal:discover`, `terminal:options`, `terminal:portfolio` | registry `primary_user_question`: "Which names line up…" vs "What is worth looking at right now?"; "Where is the options market positioned?" appears once, "How is my book doing?" vs `macro:watchlist` holdings ledger (`templates/watchlist.html.j2:715`) | three cross-repo pairs answering near-identical questions on two properties with different access models. |
| E | **Allocation cluster + naming collision** | `/allocation.html`, `/allocation_china.html`, `/china_allocation.html`, `/allocation_canada.html`, `/allocation_hk.html`, `/vector_allocation.html` | `macro:allocation_china` (template unknown, builder unresolved) and `macro:china_allocation` (`templates/china_allocation.html.j2`, builder unresolved) are two live routes | 6 allocation routes; two of them differ only by word order. Only `allocation_canada` and `allocation_hk` are nav-linked. |
| F | **Two entry points from one builder** | `/start.html` (P0, brand slot in both navs) and `/vector.html` (nav none) | both `builder: ["scripts/build_vector.py"]`, written at `:1382` and `:4578`; `macro:vector` resolves to `templates/vector.html.j2`, `macro:start`'s template is unresolved | the P0 entry point and an unlinked sibling come out of the same builder. |
| G | **Calibration surfaces** | `/measurement.html`, `/calibration.html` | `macro:measurement` → `templates/measurement.html.j2` + `scripts/build_measurement.py`; `macro:calibration` template AND builder unresolved, hard-coded into `lib/seo.py:97` "Hard-coded by brief" | two live calibration routes, both `nav_family: none`; one has no resolvable source at all. |
| H | **Subsector / rotation** | `/subsectors.html`, `/subsectors_china.html`, `/subsector_rotation.html`, `/subsector_rotation_china.html` + families `/subsector/`, `/subsector_china/`, `/subsector_nasdaq/`, `/subsector_russell/` (475 pages), `/rotation/`, `/rotation_china/` (502 pages) | `rotation_family` and `rotation_china_family` share `templates/subsector_rotation_detail.html.j2` | 4 hub routes + 6 families, 977 URLs, all `nav_family: none`. |
| I | **Basket cluster** | `/baskets.html`, `/baskets_china.html`, `/baskets_china_ths.html`, `/baskets_canada.html`, `/baskets_hk.html`, `/baskets_intl.html` + 5 families (121 pages) | 6 distinct builders (`build_baskets.py:609`, `build_baskets_canada.py:212`, …); `baskets` and `baskets_china` are nav-none while their canada/hk/intl/ths siblings are nav-linked | same surface per geography, inconsistent nav membership. |
| J | **Research front doors** | `/research_vault.html` (P0), `/reports.html`, `/research/index.html` + `/research/<slug>.html` (937 pages), 6 `/report_*.html` one-offs | `research_vault`+`reports` are `product_nav.research`; `research_index`, the family, and all 6 one-offs are `nav_family: none` | four ways in to published research, two of them linked. |
| K | **Mastermind SPA served at 4 paths** | `/`, `/desk`, `/research`, `/self` | all four `source_template: app/static/index.html`; note "same SPA shell as /: the client opens this view from the path" | one artifact, four routes; `/desk` is ruled `lifecycle: internal` in the overlay, `/` and `/self` are not. |
| L | **Strategy detail** | 42 rows share `templates/strategy_detail.html.j2`; 7 share `templates/mastermind_detail.html.j2` | registry `source_template` | not a duplicate — a legitimate detail family enumerated as individual rows. Listed so it is not mistaken for one in §4's orphan count. |

---

## 4. Unowned routes — the headline

**309 of 309 rows carry `owner: "unowned"`.** This is not a data gap: the
overrides law states `owner` is overlay-only and is deliberately `unowned`
everywhere in v1 rather than inventing names. There is currently no artifact in
any of the three repos that maps a route to a responsible person or program.

The second ownership signal is nav membership. Of **274 live macro rows, 94 are
nav-linked and 180 are not**:

| cluster | rows | reachable from |
|---|---:|---|
| standalone orphans | **63** | nothing the derivation can see |
| `fund_*` 13F detail (incl. `fund_index`) | 52 | `/fund_index.html` (itself nav-none); `fund_scion.html` only from `/smart_money.html` |
| `strategy_*` detail | 46 | `/strategies.html`, `/china_strategies.html`, `/masterminds.html` (itself nav-none), `/commodity_strategies.html` (the 11 `strategy_cm_*` rows) |
| family rows | 13 | their index pages |
| `report_*` one-offs | 6 | `/reports.html` |

**The number to act on is 63, not 180.** And 63 is still an overcount: nav_family
is derived from `templates/_navlinks.html.j2` and `templates/_public_nav.html.j2`
only (`scripts/build_product_page_registry.py:570-572`).
`templates/_public_footer.html.j2` is never read, yet it links 15 routes —
including `about.html`, `about-research.html`, `disclaimer.html`, `privacy.html`,
`terms.html`, all five of which appear in the 63. `nav_family: "none"` means "no
nav family links it", never "unreachable".

Three prior figures do not reproduce and should be retired: an upstream note of
"172 live macro pages with nav_family none" matches nothing in the artifact
(measured: 180 live macro rows, of which 167 are `route_kind: page` and 13 are
families; 186 across all repos; 201 including non-live).

**What ownership assignment needs**, stated as requirements rather than a plan:

1. An `owner` vocabulary. `config/mastermind_programs.yml` already names the
   owning programs; nothing yet joins a program to a route.
2. A decision rule for the 104 detail pages (§4 table rows 2-3, 5) — do they
   inherit their index page's owner, or are the families the unit of ownership?
3. `data_sources` (v2 scope, `[]` on all 309 rows). Ownership by data lineage is
   not currently derivable.
4. A footer-inclusive nav derivation, or an explicit statement that footer links
   do not count as nav membership — otherwise every ownership pass re-litigates
   the same 5+ rows.

---

## 5. Access inconsistencies

**5.1 `mastermind:portfolio_desk` — documentation contradicts the code.**
`app/web.py:2299-2303` (`master` @ `17c40884d`) docstrings the route as
"*Standalone static page; session-auth-gated by the same middleware as the rest
of the app.*" `app/auth.py:11-13` states the browser password-cookie login flow
"*has been REMOVED … there is no /login page, no /logout route, and no session
cookie. Browsing the dashboard (all GETs + read APIs + the SSE stream) requires
NO login anywhere, on both localhost and the internet-facing VPS mirror.*" The
registry follows the code (`access_shell: anonymous`) and records the fact in the
row's notes. A P0 surface described as gated is anonymous to anyone with the URL.

**5.2 `terminal:scripts` is `signed_in`, not anonymous.** An earlier document
assumed anonymous. `terminal/app/(shell)/scripts/page.tsx:27` reads
`if (!user) return <SignupGate surface="scripts" />;`. The registry is correct;
the overlay adds that `isPaidTier()` additionally gates saving beyond the locked
flagship script.

**5.3 `terminal:landing` is an anonymous landing, not a redirect.** Route `/`,
`access_shell: anonymous`, `payload_tier: public`; middleware redirects *signed-in*
users to `/terminal` (overlay note, evidence `terminal/app/page.tsx`).

**5.4 `macro:watchlist` — nav-linked but auth-empty.** `product_nav.research`
member, `access_shell: anonymous`. `lib/seo.py:114-116` excludes it from the
sitemap with the reason "*Auth-empty until sign-in — fails the index-worthiness
test (D12 §3.3)*". A page whose default anonymous state is empty is in a product
nav; it was never captured, so this census has no measurement of that state.

**5.5 Seven rows carry `payload_tier: "unknown"`** — `terminal:admin`, `alerts`,
`analysis`, `discover`, `portfolio` (entitlement resolved at request time, not
statically readable) plus `dev_settings`, `dev_theater` (`access_shell` also
`unknown`). Two of them (`discover`, `portfolio`) are **P0**: we ship them with no
recorded statement of what the data behind them costs.

**5.6 Four macro routes are `deny` in policy** — `_mockup_ccw_credit_desk`,
`_mockup_research_vault`, `qa_bottom_sensors`, `status`: 404 even for an entitled
user, so `access_shell` is `unknown` ("nobody, in production" is not an access
value). They are still built and committed.

**5.7 `mastermind` nav membership is not derivable** — all 7 rows are
`nav_family: "unknown"` because the dashboard nav is built client-side in the SPA.
`unknown` here is honest, and means something different from macro's `none`.

---

## 6. Top 20 UX-risk pages — a REVIEW QUEUE, not a verdict

**Composite (transparent, measured signals only).** `score = E + D + U`.

- **E — user exposure (0-6):** P0 `+3`; `nav_family` not `none`/`unknown` `+2`;
  `lifecycle: live` `+1`.
- **D — measured defect signals (0-6, captured pages only):**
  `console_error_count ≥ 4` `+2` else `≥ 1` `+1`; horizontal overflow at ANY
  viewport `+1`; zero `h1` `+1`; `asof_present == false` `+1`;
  desktop `document_height_px > 6000` `+1`.
- **U — recorded unknowns (0-4):** `source_template == "unknown"` `+1`; the row's
  own note "builder unknown" `+1`; `bilingual == "unknown"` `+1`; never captured
  `+1`.
- Ties break P0-first, then higher console-error count, then page_id.

**Five properties of this composite you must know before reading the table.**

1. **Exposure dominates by design**, per the brief: a P0 page with console errors
   outranks an orphaned lab page. It works — ranks 1-17 are all P0.
2. **D is zero for 292 of 309 rows because they were never captured.** Below rank
   17 the ranking is driven entirely by exposure and unknowns. Nothing here says
   an uncaptured page is fine.
3. `source_present == false` on all 13 macro P0 pages and all 4 terminal pages —
   a constant column ranks nothing, so it is excluded. It is either a site-wide
   provenance gap or a probe that does not match this markup; §8 G-7.
4. `>6000px` fires on the four `marketing_landing` rows, where a long scroll is
   expected for the archetype. "Is 9,504px the right length for this page" is a
   legitimate review item; it is not a defect claim.
5. **`asof_present` is rank-bearing and is the same probe family as the excluded
   `source_present`** (§8 G-7/G-8): `ux_smell_report.json → metric_notes` calls it
   "a prompt to look, not a verdict". It varies across pages (unlike
   `source_present`), which is why it stays in D — but dropping it would move
   rows by several ranks (e.g. `macro:china` from 2 to ~6). Treat any rank whose
   D includes "no as-of (+1)" with that caveat.

| # | page_id | route | score | E | D | U | console | words | desktop px | mobile px | overflow | h1 | as-of | D inputs | U inputs |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|
| 1 | `macro:products_index` | /products/index.html | **12** | 6 | 3 | 3 | 4 | 500 | 2331 | 3904 | — | 1 | no | console=4 (+2); no as-of (+1) | template unknown; builder unresolved; i18n unknown |
| 2 | `macro:china` | /china.html | **10** | 6 | 4 | 0 | 6 | 427 | 1966 | 4044 | — | 0 | no | console=6 (+2); no h1 (+1); no as-of (+1) | — |
| 3 | `macro:products_market_dashboards` | /products/market-dashboards.html | **10** | 6 | 3 | 1 | 3 | 1399 | 9504 | 13070 | mobile | 1 | yes | console=3 (+1); overflow (+1); >6000px (+1) | i18n unknown |
| 4 | `macro:products_market_terminal` | /products/market-terminal.html | **10** | 6 | 3 | 1 | 3 | 1330 | 8670 | 11574 | mobile+tablet | 1 | yes | console=3 (+1); overflow (+1); >6000px (+1) | i18n unknown |
| 5 | `macro:products_mastermind_ai` | /products/mastermind-ai.html | **10** | 6 | 3 | 1 | 3 | 1198 | 7390 | 9764 | mobile | 1 | yes | console=3 (+1); overflow (+1); >6000px (+1) | i18n unknown |
| 6 | `macro:start` | /start.html | **10** | 6 | 2 | 2 | 3 | 513 | 2416 | 2494 | — | 1 | no | console=3 (+1); no as-of (+1) | template unknown; i18n unknown |
| 7 | `macro:hk` | /hk.html | **9** | 6 | 3 | 0 | 5 | 585 | 2601 | 5332 | — | 0 | yes | console=5 (+2); no h1 (+1) | — |
| 8 | `macro:macro` | /macro.html | **9** | 6 | 3 | 0 | 2 | 513 | 2265 | 4490 | — | 0 | no | console=2 (+1); no h1 (+1); no as-of (+1) | — |
| 9 | `macro:plans` | /plans.html | **9** | 6 | 3 | 0 | 2 | 693 | 3146 | 4873 | — | 0 | no | console=2 (+1); no h1 (+1); no as-of (+1) | — |
| 10 | `macro:research_vault` | /research_vault.html | **9** | 6 | 3 | 0 | 2 | 657 | 2485 | 4140 | mobile | 1 | no | console=2 (+1); overflow (+1); no as-of (+1) | — |
| 11 | `terminal:terminal` | /terminal | **8** | 6 | 2 | 0 | 1 | 533 | 900 | 3645 | — | 0 | yes | console=1 (+1); no h1 (+1) | — |
| 12 | `macro:index` | / | **8** | 6 | 2 | 0 | 0 | 1884 | 10526 | 13463 | mobile | 1 | yes | overflow (+1); >6000px (+1) | — |
| 13 | `macro:confluence_screener` | /confluence_screener.html | **7** | 6 | 1 | 0 | 2 | 551 | 2097 | 3255 | — | 1 | yes | console=2 (+1) | — |
| 14 | `macro:us_stocks` | /us_stocks.html | **7** | 6 | 1 | 0 | 2 | 755 | 2367 | 4514 | — | 1 | yes | console=2 (+1) | — |
| 15 | `terminal:discover` | /discover | **7** | 6 | 1 | 0 | 0 | 76 | 900 | 844 | — | 1 | no | no as-of (+1) | — |
| 16 | `terminal:options` | /options | **7** | 6 | 1 | 0 | 0 | 76 | 900 | 844 | — | 1 | no | no as-of (+1) | — |
| 17 | `terminal:portfolio` | /portfolio | **7** | 6 | 1 | 0 | 0 | 81 | 900 | 844 | — | 1 | no | no as-of (+1) | — |
| 18 | `macro:allocation_canada` | /allocation_canada.html | **7** | 3 | 0 | 4 | — | — | — | — | — | — | — | never captured | template unknown; builder unresolved; i18n unknown; never captured |
| 19 | `macro:allocation_hk` | /allocation_hk.html | **7** | 3 | 0 | 4 | — | — | — | — | — | — | — | never captured | same as 18 |
| 20 | `macro:blog_family` | /blog/&lt;id&gt;.html | **7** | 3 | 0 | 4 | — | — | — | — | — | — | — | never captured | same as 18 |

**Twenty-one rows score 7; five are the P0 rows at ranks 13-17, and ranks 18-20
are three of the sixteen non-P0 rows tied at 7, ordered alphabetically — that
ordering carries no meaning.** The other thirteen are `blog_index`,
`euro_area`, `india`, `japan`, `learn_family`, `learn_index`, `products_family`,
`south_korea`, `stocks_family`, `stocks_index`, `tools_family`, `tools_index`,
`united_kingdom`. All are nav-linked, live, never captured, with template and
builder unresolved.

**P0 row outside the top 20:** `mastermind:portfolio_desk` scores **6** (E4: P0
`+3`, `nav_family: unknown` so no nav credit, live `+1`; D0 — never captured; U2 —
i18n unknown, never captured) and ranks 34. It is low ONLY because no evidence
exists for it and its nav membership is not derivable. Read it as unmeasured, not
as healthy.

**Reading the console column.** `macro:china` (6) and `macro:hk` (5) top it
because they request the most regwall-gated assets, not because they are the
worst pages: their errors are `illus.css`, `illus.js`, `mtf.js`,
`china_risk_state_live.js`, `mm_brain.js` and a 401 — all the anonymous tier
hitting the asset regwall boundary (executive bullet 1). The bare `401` entry
appears on **12 of 13** macro P0 pages, not only these two; the manifest stores
console errors as bare strings with no URL, so individual 401s cannot be
attributed to an asset (a harness improvement item). `macro:products_index` is
the one row with a distinct error, a `404`. `macro:index` is the only macro P0
page with zero console errors.

---

## 7. Recommended archetype per P0 page

Vocabulary from "doc 03" — the operator's Operation Institutionalize pack,
`03_PAGE_CENSUS_MIGRATION_FACTORY_AND_LAUNCH_GATE.md` §8 (external to this repo;
no in-repo file enforces this enum, and `scripts/build_product_page_registry.py`
validates only the default `"unclassified"`): `command_center`,
`ranked_decision_board`, `detail_page`, `macro_dashboard`, `pricing`,
`account_onboarding`, `marketing_landing`, `research_library`. **This column is
a recommendation INPUT to HANDOFF B, not a decision.** "current" is
`page_registry.json` → `archetype`.

| page_id | current | recommended | rationale |
|---|---|---|---|
| `macro:index` | marketing_landing | **marketing_landing** | keep. Hand-authored flagship landing, public chrome family, 1,884 words / 10,526px of trust-building copy. |
| `macro:start` | command_center | **command_center** | keep. Brand-slot entry in both navs; "Where do I start today?"; 43 panels measured. |
| `macro:macro` | unclassified | **macro_dashboard** | "What is the macro regime right now?"; 29 panels, no `h1`, `templates/dashboard.html.j2`. |
| `macro:us_stocks` | ranked_decision_board | **ranked_decision_board** | keep. Tiered row preview (anon=1/Free=3/paid=full) is a ranked list by construction. |
| `macro:china` | unclassified | **macro_dashboard** | same template family and question shape as `macro:macro`, scoped to China; 13 panels, no `h1`. |
| `macro:hk` | unclassified | **macro_dashboard** | as above, scoped to Hong Kong; 21 panels, no `h1`. |
| `macro:confluence_screener` | ranked_decision_board | **ranked_decision_board** | keep. "Which names line up across the signal stack today?" with rank-1 exposed and paid rows omitted server-side. |
| `macro:research_vault` | unclassified | **research_library** | "What has the research desk published?"; anonymous visitors see the latest three summaries, PDFs behind authenticated `/api/research`. |
| `macro:plans` | pricing | **pricing** | keep. |
| `macro:products_index` | marketing_landing | **marketing_landing** | keep; it is the hub of the three product pages below. |
| `macro:products_market_terminal` | marketing_landing | **marketing_landing** | keep. |
| `macro:products_mastermind_ai` | marketing_landing | **marketing_landing** | keep. |
| `macro:products_market_dashboards` | marketing_landing | **marketing_landing** | keep. |
| `terminal:terminal` | `chart_workspace` | **unclassified — vocabulary gap** | the overlay already uses `chart_workspace`, which is NOT in doc 03's vocabulary. Recommend HANDOFF B adopt the term rather than forcing this row into `command_center`. |
| `terminal:discover` | unclassified | **ranked_decision_board (proposal)** | from "What is worth looking at right now?" + app-rail membership. Caveat: the only captured state is the `SignupGate` (76 words), so this is a metadata inference, not evidence. |
| `terminal:options` | unclassified | **macro_dashboard (proposal)** | "Where is the options market positioned?" is a market-state read, not a ranked list. Same caveat — only the `OptionsPaywall` was captured. |
| `terminal:portfolio` | unclassified | **unclassified — vocabulary gap** | "How is my book doing?" is a user's own holdings ledger. No vocabulary term fits; `account_onboarding` and `detail_page` both misdescribe it. Recommend a `portfolio_ledger` term. |
| `mastermind:portfolio_desk` | unclassified | **unclassified — vocabulary gap + no evidence** | same ledger shape as above, and never captured (no public base URL). Two unknowns, not one. |

Vocabulary findings for HANDOFF B: (a) `chart_workspace` is in use in the
overrides but absent from doc 03; (b) no term covers a holdings ledger, which is
the shape of 3 P0 rows across two repos; (c) `detail_page` and
`account_onboarding` are unused across the entire P0 set — the macro site has no
account or onboarding route in the registry at all (`macro:support` is the only
public_nav row in that neighbourhood; `terminal:login` is the only login route).

---

## 8. Exact evidence gaps

Every gap, and what would close it.

| id | gap | scope | closed by |
|---|---|---|---|
| G-1 | **Free / Essential / Pro states uncaptured.** Recorded per page as `{"dimension":"access","value":"pro","captured":false,"reason":"requires authenticated session; not automatable without approved fixtures"}` | all 17 captured pages × 3 tiers | approved test fixtures + an operator ruling that a fixture session may enter the harness. Until then the honest statement stands. |
| G-2 | **loading / empty / stale / error states uncaptured**, reason "state not synthesizable against static output" | all 17 captured pages × 4 states | a fixture/mocking layer that produces the state the product actually shows; faking it against static output would screenshot a state that never ships. |
| G-3 | **No family row was captured** — a family stands for many URLs and is excluded by construction | 19 family rows / 4,316+ URLs | add `exemplar_route` to family rows; the harness already reads it (`docs/product_experience/PAGE_EVIDENCE_HARNESS.md` §2, `scripts/capture_page_evidence.py:337`) and will capture that route automatically. Cheapest high-value gap to close. |
| G-4 | **All 7 mastermind rows uncaptured** — no public base URL recorded | incl. P0 `portfolio_desk` | record the read-mirror base URL and re-run `capture_page_evidence.py --base-url`. |
| G-5 | **Terminal zh uncaptured** — React lexicons need an in-app toggle, not a `data-lang` attribute | 4 terminal P0 pages × zh | in-app locale toggle automation in the driver. An attribute toggle would produce a dishonest "zh" render. |
| G-6 | **Terminal signed-in surfaces measured their gate, not their page** — `/discover` 76 words, `/options` 76, `/portfolio` 81, all 900px | 3 of 4 terminal P0 rows | same fixture as G-1. Until then those three rows carry no evidence about the product surface. |
| G-7 | **`source_present == false` on all 17 captured pages** | site-wide | open one page and determine whether the provenance line is genuinely absent or the probe (`[data-asof]`, `.asof`, `.freshness`, "as of", "数据截至") does not match this markup. A constant metric is either a real site-wide gap or a broken probe; both need the same 10-minute check. |
| G-8 | **`asof_present == false` on 6 of 13 macro P0** (`start`, `macro`, `plans`, `research_vault`, `products_index`, `china`) | 6 rows | same probe check; the harness calls it "a prompt to look, not a verdict". |
| G-9 | **`macro:index` was captured under a synthesized page_id.** The registry row is `macro:index` at route `/`; the manifest carries `page_id: "index.html"`, `route: /index.html`, `route_kind: "explicit_override"` | 1 P0 row | capture `macro:index` through registry selection rather than `--routes`, or record `/index.html` as the row's route. §6 joins them by hand. |
| G-10 | **`data_sources: []` on all 309 rows** (declared v2 scope) | all rows | the v2 derivation. Blocks ownership-by-lineage (§4). |
| G-11 | **`owner: "unowned"` on all 309 rows** (deliberate) | all rows | §4 requirements 1-4. |
| G-12 | **33 `write_page()` call sites unresolved** of 151; 29 distinct `file: expr` pairs sampled in `sources.macro.unresolved_write_sites` (e.g. `scripts/build_site.py: out`, `scripts/build_free_content.py` ×6) | **61 rows** note "builder unknown" — 47 at route level, 14 at directory/family level | make the output path a constant or a named pattern at those call sites, or add a declarative route manifest per builder. |
| G-13 | **39 rows have neither a builder nor a resolved template** (all macro) | 39 rows | subset of G-12. |
| G-14 | **101 rows have `bilingual`/`themes`/`locales` = `"unknown"`** | 101 rows | the derivation cannot resolve i18n for hand-authored/plain-copy pages and unresolved templates; closing G-12/G-13 closes most of this. |
| G-15 | **Nav derivation reads only two nav templates**, never `templates/_public_footer.html.j2` (15 routes) | ≥5 rows misreported as orphans | either read the footer, or state explicitly that footer links are not nav membership. |
| G-16 | **The measured bytes cannot be pinned to a commit** — `target.resolved_sha_or_none: null` for both live captures | all 17 | re-run with `--site-dir` against a local build, which records the checkout's HEAD. |
| G-17 | **Mobile/tablet overflow is invisible in the committed markdown table**, which prints only the desktop reference state | 5 of 13 macro P0 pages | add a per-viewport overflow column to the `--emit-md` renderer. Data is already in `metrics.by_viewport`. |
| G-18 | **`quant_lab` and `signal_lab` are `lifecycle: lab` but not in `lib/seo.py:_EXCLUDE_NAMES`** | 2 rows | an adjudication, not a capture: either they belong in the sitemap or they belong in the exclusion list. |

---

## 9. Registry maintenance contract

**Regenerate** (needs both sister repos on disk; a few seconds):

```bash
python3 scripts/build_product_page_registry.py --as-of 2026-08-11T00:00:00Z
python3 scripts/build_product_page_registry.py --check      # validate committed artifact; no repos, no network
python3 scripts/build_product_page_registry.py --with-prs   # opt-in; ONE `gh pr list` call
```

Always pass `--as-of` for a PR — without it `generated_at` is "now" and every
rebuild churns the file. `--with-prs` spends shared GitHub REST quota
(CLAUDE.md); never poll it.

**Drift guard.** `tests/test_build_product_page_registry.py` runs the schema
suite against the committed JSON — every row has every field, page_ids unique and
repo-prefixed, enums valid, nothing `null`, every row cites evidence, every
override resolves. Change the census without regenerating and the suite goes red.
Derivation units run on `tmp_path` fixtures with an injected `run_git`; no test
reads a sister repo, shells out, or touches the network.

**Overrides law** (`config/product_experience/page_registry_overrides.yml`) — the
ONLY hand-edited input:

1. Judgment fields (`priority`, `archetype`, `primary_user_question`, `owner`)
   and access facts a static reader cannot honestly see live there, nowhere else.
2. Every entry SHOULD carry `evidence: [paths]`; `note:` is appended to the row's
   notes so the reason travels with the row.
3. An override on a page_id that no longer exists is a **hard error** — non-zero
   exit plus an `::error` annotation, re-checked by `--check`. Stale overrides
   cannot accumulate.
4. Only overridable fields may be set; `route`, `builder`, `source_template`,
   `source_evidence` are derived-only, so the overlay can never invent a page the
   code does not render.

**Evidence harness.** `scripts/capture_page_evidence.py`, never wired into CI or
the nightly (render budget is law; a browser sweep belongs off the render path).
`tests/test_capture_page_evidence.py` is hermetic — no browser, no socket, no
file outside `tmp_path` — and pins that `playwright` is imported only inside
`playwright_page_driver`. Run it `TZ=UTC python3 -m pytest tests/test_capture_page_evidence.py -q`.
Prefer `--site-dir` over `--base-url`; `--site-dir` also records the checkout's
HEAD (G-16).

**How a migration PR uses this — the reusability promise.**

1. Regenerate with `--as-of` at the branch point; the `page_registry.json` diff is
   a diff of facts (rows sorted `(repo, route, page_id)`, fixed field order).
2. Capture the affected routes BEFORE the change
   (`capture_page_evidence.py --site-dir site --routes <routes> --as-of <ts>`),
   make the change, re-capture with the SAME `--as-of`. Runs are deterministic,
   so the manifest diff is the metric/visual delta; shots cite by sha256 without
   the bytes entering git.
3. If the change adds, removes, or renames a route, regenerate the registry in the
   SAME PR or the drift guard reds. If it changes a judgment field, edit the
   overrides and regenerate — never hand-edit the JSON.
4. Post the per-state crops in the PR body per CLAUDE.md §Spawn-handoff law item
   1; the manifest gives the exact state list and each shot's digest.

---

*Census only. No redesign proposal, no access-policy change, and no migration
packet appears above — those belong to HANDOFF B and later waves. Section 7's
archetype column is an input to that work, not a decision.*
