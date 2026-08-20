# Mastermind-X XPV2 — E0A

## Current Estate Truth, Registry Freshness, Family Exemplars, and V2 Schema Delta

**Wave ID:** `XPV2-E0A`
**Program:** Mastermind-X Institutional Product Experience V2
**Date:** 2026-08-20
**Repository:** `mastermindx-market-intelligence/macro`
**State:** `RESEARCH_COMPLETE — NO PRODUCT CHANGE PROPOSED`

---

# 0. Scope and method

## 0.1 What this wave is

A research/registry measurement wave. It establishes what the product estate
actually is today, how far the committed page registry has drifted from it, what
guards do and do not protect that registry, which surfaces exemplify each
archetype family, and what a Registry V2 schema would have to change.

## 0.2 What this wave deliberately did NOT do

Per the governing instruction, none of the following was performed and none is
proposed here as an action:

- No page, template, CSS, JS, or navigation was modified.
- Registry V2 was not implemented. No schema was written.
- No route was deleted, redirected, renamed, or consolidated.
- No design-system surface was flipped compliant.
- No owner was inferred for any route.
- No rejected R2 design reference was consumed. This wave is independent of the
  Sector Central R3 and LENS R3 reference programs.

The working tree carries exactly one added file — this document — plus the two
continuation handoffs in §11 and §12.

## 0.3 A note on the governing handoff, and on prior E0A work

The `XPV2-E0A` handoff was not present on `origin/main`, in `research/`, or
attached to the commissioning session. It was eventually located **outside the
canonical tree**, in an unpushed sibling worktree (§14). This wave was executed
against the scope as stated in the commissioning instruction — estate truth,
registry freshness, family exemplars, V2 schema delta — and every finding is
independently derived from the repository at pin `92d1754b`.

**A prior Codex session already executed an E0A wave.** Its output is unpushed,
unmerged, and has no PR; it does not exist on `origin/main`. This document is an
independent re-derivation, as instructed, and §14 reconciles the two — including
one substantive disagreement resolved on evidence.

## 0.4 Method

Four parallel censuses (registry/source archaeology, navigation and
canonical-surface, PR collision and ownership, family exemplar selection), with
the orchestrator re-deriving every load-bearing number directly. Two subagent
conclusions were overturned on evidence and are recorded as such in §5.1 and
§4.4 — they are kept visible rather than silently corrected.

---

# 1. Baseline pins

Every number in this document is measured against these pins. Refs move
constantly in this repository (sibling sessions fetch the shared clone during a
session), so all counts are pinned to a SHA, never to a moving ref.

| Pin | Value |
|---|---|
| `origin/main` at measurement | `92d1754b77e64056f7c2e1a54f86f06c111f15cc` (2026-08-20 19:36Z) |
| Registry artifact | `data/product_experience/page_registry.json` |
| Registry schema | `mastermind.page_registry.v1` |
| Registry `generated_at` | `2026-08-11T00:00:00Z` |
| Registry `sources.macro.sha` | `eb37499065ca189bd33a9dd53ca50c3d3a45d894` |
| **Registry's true main-reachable base** | `21b99fac0e2608638ddcf286e460d60f962cd7f8` |
| Rows in registry | 309 (287 macro, 15 terminal, 7 mastermind) |

---

# 2. Current estate truth

## 2.1 Headline counts

Measured at pin `92d1754b`:

| Measure | Count | Command |
|---|---|---|
| Tracked HTML pages, whole site | **8,439** | `git ls-files 'site/*.html' \| wc -l` |
| Top-level routes (`site/*.html`, depth 2) | **260** | `git ls-files -- ':(glob)site/*.html' \| wc -l` |
| Registry rows, all repos | 309 | artifact |
| Registry rows, macro | 287 (269 `page`, 18 `family`) | artifact |

## 2.2 Top-level route inventory is STABLE

Between the registry's base commit `21b99fac` and pin `92d1754b` — a span of
**1,984 commits** — the top-level route inventory did not move at all:

```
git diff --name-status 21b99fac..92d1754b -- ':(glob)site/*.html'
  → 253 M, 0 A, 0 D
```

**Zero top-level routes added. Zero deleted. 253 modified.** Every registry
page-row still resolves to a tracked file (0 dangling rows), and every `site/`
subdirectory that the registry models has a family row.

This is the single most reassuring finding of the wave: the registry's *route
list* is still accurate. What has drifted is everything about *scale* and
*coverage below the top level*.

## 2.3 Where the estate actually grew

The estate nearly doubled in tracked pages while the route list stood still. All
of that growth is inside families:

| Family | Registry `notes` | Actual today | Delta |
|---|---:|---:|---:|
| `research` | 1,016 | 1,485 | **+469** |
| `stocks` (direct) | 2,180 | 2,069 | **−111** |
| `products` | 1 | 5 | +4 |
| `blog` | 6 | 7 | +1 |
| `learn` | 15 | 16 | +1 |
| `tools` | 27 | 28 | +1 |
| 12 other families | — | — | 0 |
| **Covered total** | **4,395** | **4,760** | **+365** |
| **`stocks/earnings` (UNCOVERED)** | **0 rows** | **3,419** | **entire family** |

The `stocks` family *shrank* by 111 pages, consistent with the dossier-identity
repair work (#5984 / #6041) removing wrong-company pages.

---

# 3. The coverage defect: an entire nav-linked family is invisible

This is the most consequential finding of the wave, and it is **not** staleness.

`site/stocks/earnings/` holds **3,419 tracked pages — 40.5% of the entire
tracked HTML estate — and has ZERO registry rows of any kind.**

```
python3: rows mentioning "earning" anywhere in the artifact
  (route, page_id, source_template, builder, notes)  →  0
```

## 3.1 It is not drift — it predates the registry

The Earnings Wire index was added **2026-08-02**:

```
git log --diff-filter=A --format='%h %ci %s' -1 -- site/stocks/earnings/index.html
  → 7013f9edcd51  2026-08-02  Launch the Earnings Wire and Company Intelligence teaser (#4298)
```

The registry's base commit is `21b99fac`, dated **2026-08-12** — ten days later.
At that base commit the family already held **444 pages** and a nav-linked index.
The registry was generated with this family already on disk and recorded nothing
for it. **The generator never saw it.**

## 3.2 The mechanism: the family model is single-level

At the registry base, `site/stocks/` held 2,181 HTML files: 1,737 directly plus
444 under `earnings/`. The registry recorded `"2180 committed pages under
site/stocks/"`.

The generator collapsed the whole subtree into one family row and **absorbed the
nested family's pages into the stock-dossier count**. The consequences compound:

- The earnings family has no row, so no `archetype`, no `nav_family`, no
  `payload_tier`, no `lifecycle`, no `access_shell`.
- Its pages are attributed to `macro:stocks_family`, whose route pattern
  `/stocks/<id>.html` **cannot structurally match** `/stocks/earnings/<slug>.html`
  — a different path depth.
- That row's page count is now wrong by **3,308** (claims 2,180; the subtree
  holds 5,488; the family it actually describes holds 2,069).

Six other nested subtrees are invisible the same way, though all are small:
`tools/calculators` (26), `learn/options` (7), `learn/technical` (5),
`learn/risk` (2), `tools/spreadsheets` (1), `learn/ownership` (1).

## 3.3 It is reachable — from both nav families

The earnings index is linked from the product nav (`templates/_navlinks.html.j2:271`)
**and** the public nav (`templates/_public_nav.html.j2:37`). This is not an
orphan nobody can reach. It is a first-class, doubly-linked destination that the
census designed to answer "what surfaces do we ship" does not know exists.

---

# 4. Registry freshness

## 4.1 Verdict

**The artifact is internally valid and 1,984 commits behind its own base.** Both
statements are true simultaneously, and §5 explains why nothing catches it.

## 4.2 The provenance pointer is dangling

`sources.macro.sha` records `eb37499065ca…`, which is **not reachable from
`main`**:

```
git merge-base --is-ancestor eb37499065ca 92d1754b   → NO
git merge-base            eb37499065ca 92d1754b     → 21b99fac0e26
git rev-list --count      21b99fac..92d1754b        → 1984
```

`eb37499` is the DS-PR-1 *branch tip*; the branch squash-merged onto main as a
different commit (`9e491104`, #5486). The registry therefore records a SHA that
no `main` checkout can diff against directly. The usable base is its parent,
`21b99fac`. Recovering that base requires a `merge-base` call the schema does not
hint at, and the recorded `root` path (`…/worktrees/ds-pr-1-registry`) no longer
exists on disk.

## 4.3 `generated_at` is not a freshness stamp

`generated_at` is `2026-08-11T00:00:00Z`; the source SHA it describes is dated
**2026-08-12**. The stamp **predates the code it censused by a day**, because
`--as-of` is hand-passed (the documentation instructs passing it to keep diffs
clean, which is correct for diff hygiene and wrong for freshness). Any freshness
judgment made from `generated_at` is unsound; only the SHA carries truth, and
per §4.2 that SHA is dangling.

## 4.4 Sister-repo provenance

- **terminal** (`charting-app`): recorded SHA is 27 commits behind current
  `origin/master`. The on-disk checkout is a stale feature branch, but the
  generator reads a git ref rather than the worktree, so this is a bounded,
  honest lag.
- **mastermind**: recorded SHA matches the on-disk `HEAD` exactly — but this
  repo's rows are read from the **live worktree**, not a fixed ref, and that
  worktree is currently dirty and `ahead 2, behind 87` of its own `origin/master`.
  The SHA match therefore does not prove the rows are reproducible. *(Corrected
  from the census packet, which read the SHA match as clean provenance.)*

Regeneration is structurally possible today — both sister repos are present at
the generator's default roots. It was not run; this wave is measurement only.

---

# 5. Guard truth: binding, but blind

## 5.1 The guard binds

`product-experience-registry` (`.github/ci/legacy-jobs.yml:11927`) declares
`gate: code` (`:11929`) and runs all three registry suites (`:11949`, `:11955`,
`:11957`). It is selected into **ci-pack-11**:

```
python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml \
        --pack-index 11 --pack-count 12 --validate-only   → contains the job
```

`gate: code` jobs feed the required `ci-gate`. The job therefore **binds on the
merge gate**. (The `if: ${{ false }}` on this job is boilerplate present on all
195 jobs in the manifest — the pack runner executes them, GitHub does not. An
early reading of that line as a disable was wrong and is discarded.)

## 5.2 But it cannot see estate drift

The binding suite never reads the real site tree. Its derivation units run
against an **injected fake git callable** returning a hardcoded 12-file listing
(`tests/test_build_product_page_registry.py:188-199`, `:225-240`). The
documentation states the property outright:

> `docs/product_experience/PAGE_REGISTRY.md:161-162` — "Derivation units on
> `tmp_path` fixtures with an injected `run_git` callable. No test reads a sister
> repo, shells out to git or `gh`, or touches the network."

And the artifact's own validator agrees the file is fine:

```
python3 scripts/build_product_page_registry.py --check
  → page registry OK: 309 rows, schema mastermind.page_registry.v1   (exit 0)
```

That is a clean pass on an artifact whose base is 1,984 commits old, whose
largest family count is wrong by 3,308, and which is missing 40.5% of the
estate.

**The CI step is named "committed-JSON drift guard". It is a schema guard.** It
validates field presence, enum membership, non-null-ness, and that every
override resolves to a live `page_id`. Nothing in the guarded set compares the
artifact to reality. A registry that describes an estate that no longer exists
passes every check it has.

*This overturns the archaeology census's headline, which concluded that registry
drift "goes red … and is therefore BINDING". The job binds; what it binds is
schema validity, not correspondence to the estate.*

## 5.3 The design-system ratchet is report-only, and the baseline is zero

`design_system.compliant` is `false` in **309 of 309 rows**. Only 2 rows carry
any content beyond the bare default (`macro:macro`, `macro:us_stocks`, both
listing `governed_regions` and both still non-compliant).

The ratchet runs `--mode report` and never `--mode enforce`
(`.github/ci/legacy-jobs.yml:4429-4431`); `scripts/check_design_system.py:1,7`
states "R0 SHIPS REPORT-ONLY ON PURPOSE" and `--mode report` always exits 0.
This is the intended R0 state, recorded here as the baseline a V2 wave inherits —
not as a defect.

---

# 6. Ownership truth

`owner` is `unowned` in **309 of 309 rows**. The census tested whether that is a
true absence or merely an unfilled overlay:

| Source | Exists | Granularity | Can populate a route `owner`? |
|---|---|---|---|
| `CODEOWNERS` | **No** — none anywhere | — | — |
| `agentos/workstreams/*` `owns_paths` | Yes (36 of 39 files) | Path globs → **workstream** | Names a workstream, not a person/team; not wired to the registry |
| `docs/ACTIVE_BUILD_MAP.md` | Yes | Chronological change log | No ownership field (4 grep hits, all incidental) |
| `docs/PROJECT_ACTIVE_BUILD_MAP.md` | Yes | — | No ownership field (0 hits) |
| `config/mastermind_programs.yml` | Yes | **Program** (`implementation_owner`, `state_owner`) | Coarsest; no `owner:` key |
| `docs/MASTERMIND_SYSTEM_MAP.md` | Yes (generated) | Synapse / lobe | Not route-granular |
| `config/product_experience/page_registry_overrides.yml` | Yes | **Route / page_id** | Yes — but sets `owner` on **0** entries |

**Verdict: no source in this repository assigns ownership at route granularity.**
The one file built for exactly that purpose is the overrides overlay, and it is
empty of owner values. `owner: unowned` is an honest report of a true absence,
not a data-entry backlog.

**No owner is inferred anywhere in this document.** Git blame and commit
authorship were available and were deliberately not used; per the governing
instruction, this unknown stays unknown.

## 6.1 The program has no governance record — and one cannot be filed

There is **no `WS-*` record in `agentos/workstreams/` for the XPV2 /
institutional-product-experience program**, despite the program having shipped a
Turn-3 freeze packet (#6097), declaring `WS:INSTITUTIONAL-PRODUCT-EXPERIENCE-V2`
as its Program ID, and having live sibling sessions (§7).

This wave attempted to file the required AgentOS continuation handoff and could
not, without fabricating company structure:

- `scripts/agentos.py validate` hard-errors on a handoff referencing an unknown
  workstream (`dangling-ref`), and that validator is CI-wired at
  `.github/ci/legacy-jobs.yml:4767`.
- Minting the workstream requires a `program:` key validated against
  `config/mastermind_programs.yml`. That file holds 60 program keys and **none**
  covers product experience, design system, or the site estate.

So filing the record would have meant inventing both a workstream and a company
program. Per the standing instruction that unknowns remain unknown, neither was
invented. **The E0B and E0C continuation handoffs therefore live in §11 and §12
of this document rather than in `agentos/handoffs/`**, and the missing program
record is recorded here as a finding for the operator.

The prior Codex wave hit the same wall and recorded it as unresolved
("compile-context fails closed for that named key"); its handoff was never
exposed to CI because its branch was never pushed (§13).

---

# 7. PR collision census

`gh` budget: 3 calls total; `core` remaining 4,582 → 4,563. No `--paginate`, no
`run watch`, no polling loop.

Of **26 open PRs**, four touch a collision surface or name the program:

| PR | Title | Branch | Labels | Collision |
|---|---|---|---|---|
| #6122 | XPV2-SC-R3A: Sector Central authority + capability binding pack | `claude/xpv2-sc-r3a-binding-pack` | — | `research/reference_integrity/mastermind-xpv2-sector-r3/**` |
| #6124 | fix(intel-hub): correct false "policy votes" ranking tooltip (XPV2-IH-T0) | `claude/xpv2-ih-t0-policy-nonvoting` | `merge-on-green` | Program name only |
| #6120 | fix(intel-hub): policy is context, not a voting desk — correct the ranking help | `claude/xpv2-ih-t0-policy-nonvoting-truth` | `merge-on-green` | Program name only |
| #5737 | radar(w8): Live Entry Radar reference UX + RIG | `cursor/entry-radar-w8-rig-9f9d` | `merge-on-green`, `merge-blocked` | `research/reference_integrity/entry-radar-w8/**` |

**The registry wave has a clear field.** No open PR touches
`data/product_experience/**`, `config/product_experience/**`,
`scripts/build_product_page_registry.py`, `docs/product_experience/**`, any of
the six navigation template files, `research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md`,
or `research/DESIGN_MIGRATION_FACTORY_V1.md`. The two reference-integrity PRs
touch only their own per-program subdirectories.

**Flagged for the operator, not acted on:** #6124 and #6120 carry the same task
key (`XPV2-IH-T0`), near-identical branch names, the same author, the same
surface (the Intelligence Hub policy-ranking help text), and **both are armed
`merge-on-green`**. That is the shape of two sessions independently fixing one
defect. This wave has no authority over either PR and did not touch them; the
observation is recorded because two armed PRs editing the same copy will merge
in an order nobody chose.

Three other open PRs carry title-level HOLD markers (#6051, #6021, #5898); none
is a collision PR. PR bodies and comments were not fetched, so a HOLD stated
only in a body would not be visible — recorded as an open unknown.

---

# 8. Family exemplars

Exemplars were selected by reading the rendered page or its template, never from
metadata. Every macro exemplar was verified present in git at HEAD
(`git cat-file -e HEAD:<path>`). Sizes are committed-HTML bytes and move nightly
with the data re-bake — treat them as order-of-magnitude.

## 8.0 Two cross-cutting facts that condition every family

**F1. `archetype` is a TOPIC label, not a STRUCTURE label.** The decisive
evidence: `/macro.html` (`regime_dashboard`) and `/us_stocks.html`
(`discovery_board`) are rendered from the **same template**,
`templates/dashboard.html.j2`, by the same builder. Two more templates straddle
archetypes (`strategy_detail.html.j2` → 40 `instrument_analyzer` + 2
`discovery_board`; `mastermind_detail.html.j2` → 6 + 1). **A migration wave that
treats archetype as a structural contract will be wrong by construction.** This
is the most important input to §9 from the exemplar census.

**F2. The first four `<h2>`s of every macro page are the shared nav mega-menu**
("Core Research / Find the Edge / Capital & Regimes / Explore"), not page
content. All heading counts below are net of those four.

## 8.1 The exemplar matrix

| Archetype | n | Exemplars | Coherence |
|---|---:|---|---|
| instrument_analyzer | 119 | `/stock.html` (241 KB, tpl `stock.html.j2`) · `/stocks/A.html` (127 KB, builder unknown) · `/strategy_dual_momentum.html` (285 KB, `strategy_detail.html.j2`) · `/fund_berkshire.html` (131 KB, `fund_dossier.html.j2`) | **Catch-all** — four generators, four grammars |
| intelligence_desk | 40 | `/alt_data.html` (149 KB) · `/sector_central.html` (293 KB) · `/etfs.html` (87 KB) | **Catch-all** — 40 bespoke desks, no shared skeleton |
| discovery_board | 40 | `/us_stocks.html` (542 KB, P0) · `/confluence_screener.html` (69 KB, P0) · `/china_heatmap.html` (60 KB) | **Catch-all, but four clean cohorts** |
| regime_dashboard | 32 | `/japan.html` (89 KB) · `/macro.html` (544 KB, P0) · `/bonds.html` (213 KB) | **Partially coherent** — the most tractable large family |
| editorial | 24 | `/research_vault.html` (80 KB, P0) · `/report_haven_audition.html` (151 KB) · `/learn/index.html` (33 KB) | **Catch-all** — indexes mixed with what they index, across two chromes |
| utility | 23 | `/tools/index.html` (50 KB) · `/terms.html` (51 KB) · `/support.html` (48 KB) | **Catch-all** — see §8.2 |
| monitor | 11 | `/news.html` (161 KB) · `/alerts.html` (285 KB) · `/watchlist.html` (69 KB) | **Catch-all** at only 11 members |
| marketing | 10 | `/` (179 KB) · `/products/market-terminal.html` (126 KB) · `/plans.html` (71 KB) | **COHERENT** — the only genuinely coherent family |
| chart_workspace | 9 | `/terminal` (10.8 KB src) · `/discover` (1.4 KB src) · `/portfolio` (3.5 KB src) | **Catch-all** — the name fits exactly one member |
| command_center | 1 | `/start.html` (100 KB) | **N/A** — unfalsifiable at n=1 |

Notable structural reads:

- **`/japan.html` migrates five pages.** `japan` / `india` / `south_korea` /
  `united_kingdom` / `euro_area` are metrically near-identical (all `h2=14`,
  `dialogs=12`, 87–89 KB). Studying one covers the cohort.
- **`/macro.html` has only 2 content `h2` but 438 dialog references and 50
  cards.** Its content lives in modals, not in the document outline. A packet
  built from the heading tree will see almost nothing of the site's flagship.
- **`/bonds.html` is the opposite disclosure strategy** — 24 headings, 24 cards,
  zero dialogs. Same "what regime are we in" question, everything visible.
- **`/confluence_screener.html`'s `h1` is the answer itself** ("3 setups lining
  up today"), zero tables, payload-driven. This is house glance-tier doctrine
  expressed as a whole page — the family's design reference, not `/us_stocks.html`.
- **Terminal routes are auth-gate shells.** Route file = auth gate; layout =
  chrome; mount component = the page. `/portfolio`'s own source comment records
  that it previously "rendered WATCHLIST symbols under the name 'Conviction
  Book' — a different population wearing the portfolio's name".

## 8.2 Ten `utility` routes are live tombstones

Ten macro routes render a single redirect notice and nothing else — zero tables,
zero cards, zero svg: `/btc_strategy.html` (2,738 B), `/vector_allocation.html`,
`/flow_desk.html`, `/flow_leaders.html`, `/options_screener.html`,
`/subsector_rotation.html`, `/subsector_rotation_china.html`,
`/baskets_china.html`, `/gex.html`, `/baskets.html` (6,187 B). A registry-wide
sweep returned these 10 and nothing else — the shape is confined to `utility`.

All ten are `lifecycle: live`. **That is direct evidence that `lifecycle: live`
means "the file is served", not "the page is a product."** They should receive no
design work. No deletion or redirect is proposed here — that is a product
decision.

## 8.3 Density outliers that would corrupt a family budget

`/qa_bottom_sensors.html` (1.86 MB, `utility`, internal) is the largest page in
the registry. `/smart_money.html` (1.40 MB, 117 tables) is 10× its family
median. `/china_stocks.html` (1.10 MB, 308 cards) and `/us_stocks_lab.html`
(886 KB) follow. Conversely `/us_stocks_v2.html` is **8,440 B** — 1/20th the
page it is a "v2" of, effectively empty. None should anchor a density budget.

## 8.4 Registry provenance gaps surfaced by reading the pages

- **All 51 `fund_*` rows record `source_template: unknown`** while
  `templates/fund_dossier.html.j2` exists and is referenced by exactly one
  script — `scripts/build_smart_money.py`, which those rows already record as
  their builder. The template is mechanically discoverable; the registry simply
  does not name it.
- **`/start.html` records `source_template: unknown`**; its generator is
  `scripts/build_vector.py`, which states at `:1354` that it "owns
  `site/start.html` exclusively; 2026-07-22 operator order".
- **10 of 13 family roots have `builder: []` and `source_template: unknown`**
  despite thousands of pages on disk. A migration packet cannot be written
  against those rows without first finding the writer.

## 8.5 Misclassification observations (recorded, NOT acted on)

Flagged with evidence; no row was re-classified and no file was edited:
`/biocatalyst.html` (`intelligence_desk`) reads as a workspace;
`/watchlist.html` (`monitor`) is a paste-and-analyze tool with no monitoring
loop; `/measurement.html` (`editorial`) is the Calibration Lab, an instrument
surface; `/alerts.html` (`monitor`) self-titles "Alert Command Center" while the
sole `command_center` row is `/start.html`; `/alerts`, `/analysis`,
`/portfolio`, `/scripts` (`chart_workspace`) are tabbed data surfaces, not chart
workspaces.

## 8.6 Where the exemplar census could not see

- **`site/stocks/earnings/`** — 3,419 pages, no registry row, therefore no
  archetype and no exemplar. Invisible to any wave planned from this registry.
- **`monitor` is the weakest family**: 5 of 11 rows are `mastermind:` and were
  not read; four share one source file, so that half may be one page with five
  routes. Its only P0 (`mastermind:portfolio_desk`) is not among the exemplars.
- **`chart_workspace` confidence is MEDIUM** — the route files are 1–4 KB auth
  shells; the real layout lives in mount components and `(shell)/layout.tsx`,
  which were not read.
- **Payload-tier blindness** — where a page's paid half lives in
  `site/premiumdata/*.json`, a structural read of the HTML covers the free half
  only. Not quantified across the 118 affected rows.

---

# 9. Registry V2 schema delta

This is the adjudicated delta: what V2 must change, each item grounded in a
measured V1 failure above. It is a specification of *problems and required
properties*, not an implementation.

## 9.1 Blockers — V2 is not worth building without these

**D1. Nested families must be first-class.**
*Evidence:* §3. A single-level family model made 3,419 pages (40.5% of the
estate) invisible and misattributed them to a row whose route pattern cannot
match them.
*Required property:* family derivation walks to arbitrary depth; a nested family
gets its own row with its own route pattern; a parent family's count excludes its
children. `/stocks/<id>.html` and `/stocks/earnings/<slug>.html` are two
families, not one.

**D2. Family scale must be a structured, derived field.**
*Evidence:* §2.3. Member counts exist only inside free-text `notes`
(`"2180 committed pages under site/stocks/"`). Nothing can validate a sentence.
*Required property:* a typed `member_count` (and the glob it counts), derived,
never overlay-settable — so a drift guard can assert it and a diff shows it.

**D3. The guard must compare the artifact to the estate.**
*Evidence:* §5.2. Every unit runs on an injected fake git; `--check` passes on an
artifact missing 40.5% of the estate.
*Required property:* one CI assertion that reads the **real** tracked tree and
fails when the artifact disagrees on route set or family counts. The existing
fixture-based units stay — they test derivation logic correctly and should not be
disturbed. This is an added assertion, not a replacement. It belongs in the
existing `gate: code` job, which already binds.

**D4. Provenance must be main-reachable and self-dating.**
*Evidence:* §4.2, §4.3. The recorded SHA is a dangling branch tip; `generated_at`
predates the code it censuses.
*Required property:* record a commit reachable from `main`; have `--check` verify
that ancestry and fail on a dangling pointer; derive the freshness stamp from the
commit's own date rather than a hand-passed `--as-of`. Keep `--as-of` for diff
hygiene if desired, but it must not be the freshness source.

## 9.2 Fields V1 declares but never delivers

Each of these is empty or default across the whole artifact. V2 must either fill
them from a real source or honestly retire them — a field that is 100% default is
a schema promise the data never keeps.

| Field | Empty | Disposition question for V2 |
|---|---:|---|
| `data_sources` | **309/309** | Explicitly "reserved for v2" in the docs. This is *the* named V2 work item and it has a hard prerequisite: deriving the data behind a page. |
| `owner` | **309/309** | §6 proves no route-granularity owner source exists. V2 must either stand up an owner plane first, or mark this structurally unknowable — filling it by inference is forbidden. |
| `open_prs` | **309/309** | Only populated under opt-in `--with-prs`, which is never used (correctly — it spends shared REST quota). A field that is always empty in the committed artifact is dead weight. |
| `primary_user_question` | 291/309 | The field a product-experience program most needs; 18 filled (the P0 seed). |
| `priority` | 291/309 | Same 18-row P0 seed. P1–P3 assignment is unstarted. |
| `design_system.compliant` | false 309/309 | Correct R0 baseline (§5.3), not a defect — but V2 inherits a zero baseline. |

## 9.2b The archetype field cannot carry structural authority

**D7. `archetype` is a topic label; V2 must not let a migration wave read it as
a structural contract.**
*Evidence:* §8.0 F1. `/macro.html` (`regime_dashboard`) and `/us_stocks.html`
(`discovery_board`) render from the same template and builder; two further
templates straddle archetypes. Eight of ten families are catch-alls by the
exemplar census; only `marketing` is coherent.
*Required property:* either V2 adds a separate, derived structural key (the
template/builder identity is already available and would be honest), or the
schema documents in-band that `archetype` is a topic grouping with no structural
guarantee. The prior E0A proposal's `job_family` field (§14.3) addresses the
adjacent product-job question and is complementary, not a substitute — a job
label is no more a structure label than a topic label is.

**D8. `lifecycle: live` means "served", not "a product".**
*Evidence:* §8.2 — ten `utility` routes are `live` and render nothing but a
redirect notice. *Required property:* V2 should be able to distinguish a served
route from a product surface, or `lifecycle` must be documented as a
serving-state field so nobody plans a migration around it.

## 9.3 Accuracy repairs

**D5. `nav_family` group labels drift silently.** `/macro.html` (`macro:macro`)
records `nav_family: product_nav.brand`, but `templates/_navlinks.html.j2:62,64`
places it in the United States flyout — `product_nav.brand` belongs solely to
`/start.html` (`:36`). The coarse linked/unlinked test passes (0 disagreements in
both directions across 269 page rows), so only the *group name* is wrong. A V2
guard that checks group membership, not just reachability, would catch this.

**D6. Orphan population is stable and large.** 175 of 269 macro page rows are
`nav_family: none`, independently recomputed from the templates as 175 — an exact
match, unmoved since generation. Including family rows, 188 of 287 macro rows.
This is a standing product fact for the program to decide on; it is *not* a
registry defect and no consolidation is proposed here.

## 9.4 Explicitly NOT proposed

No archetype vocabulary change. No route deletion, redirect, or consolidation. No
navigation change. No compliance flip. No owner assignment. Those are product
decisions that belong to an adjudicating authority, not to a measurement wave.

---

# 10. Unknowns held open

Recorded as unknown rather than filled:

1. **The `XPV2-E0A` handoff as commissioned.** A handoff was located in the
   unpushed sibling worktree (§13) and is reconciled here, but it is that
   session's *output* handoff, not necessarily the document the commissioning
   instruction referred to. If a separate governing handoff exists with
   acceptance criteria beyond the four named deliverables, it was not read.
2. **Route ownership** — no source exists at route granularity (§6). Deliberately
   not inferred from blame or authorship.
3. **HOLD markers in PR bodies/comments** — only titles were scanned (§7).
4. **Whether the `/macro.html` nav mislabel and the earnings coverage gap
   predate 2026-08-11** — the earnings gap is proven to predate it (§3.1); the
   `/macro.html` mislabel was not blame-traced.
5. **Whether any individual route falls under an unrelated workstream's
   `owns_paths` glob incidentally** — not checked path-by-path.
6. **`product-experience-registry`'s `paths:` scope** — the job's scope is
   analyzer-inferred and documented as "honestly broad"; whether an unrelated
   PR's diff could deselect the pack was not established.
7. **Whether regeneration would reproduce the artifact** — feasible but not run.

---

# 11. Continuation handoff — `XPV2-E0B`

## Registry V2 derivation repair: nested families, structured scale, real drift guard

**State:** `NOT STARTED — do not begin without dispatch.`

### Observable mission

`data/product_experience/page_registry.json` describes every page the site ships,
including the 3,419-page `stocks/earnings` family, with per-family member counts
that CI verifies against the real tree.

### Why it matters

The registry is the candidate source of truth for the whole V2 product-experience
program. Today it is missing 40.5% of the estate, misattributes those pages to a
family whose route pattern cannot match them, and passes every check it has
(§3, §5.2). Any program built on it inherits those errors silently.

### Authority and precedence

1. Chairman's direct instructions.
2. This E0A packet, §3 / §4 / §9.1.
3. `docs/product_experience/PAGE_REGISTRY.md` and the overrides law.
4. Repo `CLAUDE.md` (ship loop, model routing, CI quota).

### Verified current state — do not re-derive

- Registry base `21b99fac`; pin `92d1754b`; 1,984 commits apart.
- 8,439 tracked HTML pages; 260 top-level routes; 0 top-level routes added or
  deleted since base.
- `site/stocks/earnings/` = 3,419 pages, 0 registry rows, nav-linked from both
  nav families; existed (444 pages) at the registry's own base commit.
- `site/stocks/` direct = 2,069; the `stocks_family` row claims 2,180.
- Six other nested subtrees uncovered, all small (26/7/5/2/1/1).
- `--check` exits 0 today; the binding suite reads an injected fake git.
- `product-experience-registry` is `gate: code`, in ci-pack-11, and binds.

### Exact scope

1. Depth-aware family derivation (D1). A nested family gets its own row; the
   parent's count excludes its children.
2. Structured derived `member_count` + the counting glob (D2). Free-text `notes`
   counts stop being the only record.
3. A real-tree drift assertion in the existing `gate: code` job (D3). Keep the
   fixture units untouched.
4. Main-reachable provenance + ancestry check in `--check`; SHA-derived freshness
   stamp (D4).
5. Regenerate the artifact and commit it with the schema change.

### Explicit non-goals

No archetype re-keying. No `data_sources` population (that is E0C). No owner
population. No nav change, route deletion, or compliance flip. No product UI work.

### Failure states to handle honestly

- A nested family whose parent has no row of its own.
- A family directory with zero pages at HEAD.
- A route pattern that matches at two depths — must be an error, not a silent
  first-match.

### Not done unless

- The earnings family has its own row with a correct route pattern and count.
- `stocks_family` reports 2,069, not 5,488 and not 2,180.
- A deliberately corrupted count (edit one number) makes the `gate: code` job go
  red — demonstrated, with the red run cited. **A guard that has never been seen
  failing is not a proven guard.**
- `--check` fails on a dangling provenance SHA — demonstrated the same way.
- The schema version is bumped and `docs/product_experience/PAGE_REGISTRY.md`
  updated in the same PR.

### Stop condition

PR merged, CI green, artifact regenerated and committed. No product surface
touched.

---

# 12. Continuation handoff — `XPV2-E0C`

## Estate disposition: `data_sources`, the owner question, and the dead-field audit

**State:** `NOT STARTED — blocked on E0B.`
**Blocked because** every field decision below is taken against the row set E0B
produces. Deciding disposition for 309 rows while 3,419 pages are missing from
the census would have to be redone.

### Observable mission

Every field in the registry schema either carries real data for a real reason, or
has been explicitly and visibly retired. No field is 100% default by accident.

### Why it matters

Four fields are empty in 309/309 or 291/309 rows (§9.2). `data_sources` is the
named V2 work item and has never been started. `owner` cannot be filled from any
source that exists (§6). A schema whose promises the data never keeps teaches
readers to distrust the fields that *are* real.

### Verified current state — do not re-derive

- `data_sources`, `owner`, `open_prs`: empty in 309/309.
- `primary_user_question`, `priority`: default in 291/309 (18-row P0 seed).
- No `CODEOWNERS` anywhere; no route-granularity owner source in the repo; the
  overrides overlay permits `owner` and sets it on 0 entries.
- `--with-prs` spends shared REST quota and is correctly never used in the
  committed artifact.
- No `WS-*` record exists for this program.

### Exact scope

1. **`data_sources`** — determine whether page→data lineage is derivable at all
   (builders are known for ~200 of 287 macro rows; 89 have none). Deliver a
   feasibility verdict with evidence *before* any implementation. A null result is
   a valid and complete deliverable.
2. **`owner`** — decide between standing up an owner plane, binding to workstream
   `owns_paths` at workstream granularity with the coarseness stated in the field,
   or marking the field structurally unknowable. **Inferring owners from git blame
   or authorship is forbidden.**
3. **`open_prs`** — retire from the committed artifact or document it as
   query-time-only. Do not make it default-on; the REST pool is shared.
4. **`primary_user_question` / `priority`** — propose a filling process, or state
   plainly that they stay seeded-only and why. Do not bulk-fill by inference.

### Explicit non-goals

No page, template, nav, or CSS change. No design-system compliance flip. No
archetype re-classification. No route consolidation.

### Not done unless

- Each of the four fields has a written disposition: filled (with its source),
  retired (with the removal), or explicitly held unknown (with the reason).
- Any field left empty carries a one-line note in the schema docs saying why, so
  the next reader does not re-open a settled question.
- Zero inferred owners appear in the artifact or the packet.

### Stop condition

Dispositions merged into `docs/product_experience/PAGE_REGISTRY.md` and the
schema. A feasibility null on `data_sources` is a complete outcome, not a failure.

---

# 13. Reconciliation with the prior Codex E0A

## 14.1 What exists, and where

A prior Codex session executed an E0A wave on branch `claude/xpv2-e0a`, in the
worktree `/Users/chriswong/Documents/Cluade/macro-main/.claude/worktrees/xpv2-e0a`.
Its state at the time of this wave:

| Fact | Value |
|---|---|
| Branch pushed to origin? | **No** — `git ls-remote --heads origin claude/xpv2-e0a` is empty |
| Merged to main? | **No** — `7f70abc3a901` is not an ancestor of `origin/main` |
| Open PR? | **No** — the PR census found no open PR touching `data/product_experience/**` |
| Committed there | `7f70abc3a901 fix(registry): keep source provenance portable` |
| Uncommitted there | modified `page_registry.json` + 4 untracked deliverable docs |
| Its handoff says | `ended_because: complete` |

**None of it exists on `origin/main`.** Per repo law, state is verified against
`origin/main` and never against a local folder, so the canonical tree carries no
E0A deliverables. That session declared itself complete while stopping at a local
commit — the outcome the ship-loop rule exists to prevent. **This is flagged for
the operator; this session has not touched that worktree, branch, or commit.**

## 14.2 Where the two waves agree

Independently derived, and matching: 309 rows; the estate reconciles to ~8,436
tracked macro HTML files (this wave measures 8,439 two commits later); 89 rows
have no builder and 91 no template; 291 rows retain blank user-question and
unclassified priority; **no owner was inferred by either wave**; the
`WS-INSTITUTIONAL-PRODUCT-EXPERIENCE-V2` record is absent from
`agentos/workstreams/`; and named architecture/amendment documents cited by the
program do not exist at current main under those names.

The prior wave also did two things this research-only wave was forbidden from
doing, and they are real value: it removed machine-local absolute checkout paths
from source provenance (`scripts/build_product_page_registry.py`), added an
attack test proving validation fails when absolute local paths are injected, and
regenerated the artifact with `--with-prs`.

## 14.3 Where the two waves disagree — resolved on evidence

**The disagreement: is `site/stocks/earnings/` part of the stocks family?**

The prior handoff records it as correct directory-family membership and warns
that a shallow glob "silently undercounts 5,487 current members". Its V2 proposal
carries that forward into a derived, CI-validated `route_instance_count: 5487`
for `macro:stocks_family`, and selects
`/stocks/earnings/cwen-a-2026q1-call-record.html` as that row's `long_name`
exemplar.

**This wave finds that conflation is wrong, on the registry's own definition of a
family** — "per route FAMILY where a builder renders thousands of pages from one
template":

| Test | Stock dossiers | Earnings pages |
|---|---|---|
| Builder | (registry: `[]`) | `scripts/build_earnings_public_wire.py` |
| Template | (registry: `unknown`) | `templates/earnings_wire/` |
| Route shape | `/stocks/<id>.html` | `/stocks/earnings/<slug>.html` |
| Nav | via the stocks family | linked directly from **both** navs |

Different builder, different template, different route depth, separate
reachability. The row's own `route` pattern `/stocks/<id>.html` **cannot match**
`/stocks/earnings/<slug>.html`.

**Why this matters more than a counting quibble:** `macro:stocks_family` carries
`archetype: instrument_analyzer`. Folding the earnings wire into it applies an
instrument-analyzer archetype to 3,419 editorial news pages. Baking that into a
derived, validated `route_instance_count` would make the error permanent and
CI-enforced — a guard defending a misclassification.

**Adjudication: the earnings wire is a separate family (§3, D1).** The prior
proposal's `route_instance_count` field is sound and is adopted in D2; what
changes is the membership rule it counts against. Its remaining six proposed
fields are not disputed by this wave.

## 14.4 Recommended disposition — operator decision, not taken here

The two waves are complementary: the prior one shipped a code fix and a broader
seven-field V2 proposal; this one re-derived the estate at a later pin and caught
the family-membership error before it could be encoded. Neither supersedes the
other wholesale. **Whether to push, PR, or discard the unpushed
`claude/xpv2-e0a` branch is the operator's call.** It is unpushed local work that
could be lost, and it contains a genuine portability fix this research-only wave
was scoped out of making.

---

# 14. Acceptance evidence

| Claim | Evidence |
|---|---|
| 8,439 tracked HTML pages | `git ls-files 'site/*.html' \| wc -l` |
| 260 top-level routes | `git ls-files -- ':(glob)site/*.html' \| wc -l` |
| 0 top-level routes added/deleted; 253 modified | `git diff --name-status 21b99fac..92d1754b -- ':(glob)site/*.html'` |
| 1,984 commits since base | `git rev-list --count 21b99fac..92d1754b` |
| Recorded SHA not main-reachable | `git merge-base --is-ancestor eb37499065ca 92d1754b` → non-zero |
| True base is the parent | `git merge-base eb37499065ca 92d1754b` → `21b99fac` |
| earnings = 3,419 pages | `git ls-files 'site/stocks/earnings/*.html' \| wc -l` |
| earnings has 0 registry rows | JSON scan for `earning` across all 287 macro rows → `[]` |
| earnings predates registry base | `git log --diff-filter=A -1 -- site/stocks/earnings/index.html` → 2026-08-02 |
| 444 earnings pages at base | `git ls-tree -r --name-only 21b99fac -- site/stocks/earnings/` |
| stocks direct = 2,069 | `git ls-files 'site/stocks/*.html' \| awk -F/ 'NF==3' \| wc -l` |
| `--check` passes on stale artifact | `python3 scripts/build_product_page_registry.py --check` → exit 0 |
| Guard reads a fake git | `tests/test_build_product_page_registry.py:188-199`, `:225-240` |
| Docs confirm no test reads git | `docs/product_experience/PAGE_REGISTRY.md:161-162` |
| Job is `gate: code` | `.github/ci/legacy-jobs.yml:11927`, `:11929` |
| Job is in ci-pack-11 | `run_ci_pack.py --pack-index 11 --pack-count 12 --validate-only` |
| `if: false` is boilerplate | `grep -cF 'if: ${{ false }}'` → 195 = total job count |
| Ratchet is report-only | `.github/ci/legacy-jobs.yml:4429-4431`; `scripts/check_design_system.py:1,7` |
| `design_system.compliant` false 309/309 | JSON scan of all rows |
| `owner` unowned 309/309 | JSON scan; `grep -cE '^\s*owner:\s*\S'` overrides → 0 |
| No `CODEOWNERS` | `find . -iname '*codeowners*'` → none |
| `/macro.html` nav mislabel | artifact `nav_family: product_nav.brand` vs `_navlinks.html.j2:62,64` |
| 175 orphan page rows, unmoved | template-derived recount vs artifact — exact match |
| 26 open PRs, 4 collisions | one `gh pr list --json …` call; 3 `gh` calls total |
| Nav templates unchanged since base | `git log 21b99fac..92d1754b -- templates/_navlinks.html.j2` → 0 commits |
