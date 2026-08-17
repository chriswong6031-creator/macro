# D0R discovery and blocker appendix

Recorded 2026-08-17. **Do not fix in D0R.** D1-or-later unless noted as already-known historical.

## Bugs / degraded live behavior

1. **Entitled desk unproven / unentitled teaser is the live default.** Compact page paints 2 of 500 workspace events and a membership banner. Paid JSON and `/api/government-revenue/*` 401. D1: entitled-browser rescue.
2. **Candidate filmstrip says “Link status unavailable” instead of “Members only”.** Workspace hydration maps 401 → `locked`. Candidate radar fetch to `/api/government-revenue/candidates` returns `missing bearer token` and the ticker rail uses `unavailable`. Same access failure, two user meanings.
3. **Agency facet / event agency empty.** Compact event `agency: {}` while official award is DISA/DoD. Facet ids are stringified Python dicts (`"{'id': 1174, ...}"`). Filter UX is degraded.
4. **`dates.known_at.semantic = "official"`** on a projector first-seen clock. Mislabels ingestion time as a government field.
5. **Late-discovery inconsistency.** JSON `is_late_discovery=true` on HC101319C0006; title is “New obligation observed”. Sibling HII row titles the lateness. A May action can be read as a fresh change.
6. **Budget graph verifying forever / 0 programs.** `budget_program_graph.json` and `site/government-revenue-data/budget-program.json` are **absent from HEAD**, but `render.yml` and the API path list still name them. UI copy assumes a precomputed P-1/R-1 graph.
7. **Opportunities freshness unavailable with headline 0.** Must not be filed as EMPTY_VALID.
8. **HTML Last-Modified 2026-08-14 vs `#gov-data` generated_at 2026-08-13.** A later HTML bake did not refresh the evidence cut. Capture 2026-08-17 still shows Aug 13 clocks.
9. **`/api/health` `commit` (`a0b2aba13b5`) ≠ `checkout` (`e7cdfa25732`).** Inherited from kickoff; still unexplained.

## Stale or inert components

- `shadow_context.py`, `market_context.py`, `sbir_progression.py`, `issuer_graph_expansion.py`: tests (and shadow’s own module) without builder/runtime import from `scripts/build_government_revenue.py`.
- `prophet_annotation.py` is wired in `prophet_bridge.py` fail-open; live annotation not captured. Bridge comment still says candidate radar is empty; HEAD `candidate_count=22`.
- Compact briefcase (save/export/alerts) disabled until workspace hydrate.
- Award-detail `award_event_snapshots` row for HC101319C0006 is an older eligible=false cut (modified 2026-03-11) beside a live action P00032 (2026-05-12). Dual-read required.

## Spec vs live contradictions

- Architecture/kickoff: “Candidate Radar is a product tab.” Live unentitled: 0 + loading. Entitled: unproven.
- Status file `source_health.status=ok` vs UI “Partial or stale coverage” (client aging + opportunity unavailable + lock).
- Graph `companies` 19 tickers vs compact company strip 21 (GE, BWXT extra). `#5424` would add BWXT on defense20-v1 — still **open**, not live.
- Collection continued 2026-08-14 (new action-page sha) but published compact bundle remains 2026-08-13 / receipt `2a07ba19…`.

## Duplicate-plane hazards (do not mint)

- Company financials / backlog / GAAP / guidance / estimates / prices / options / dark pool / themes / identity Atlas / Neural Web / Prophet. V3 consumes those planes; it does not fork them.
- A second reviewed recipient graph (`DNR:LAW-REVIEWED-MANIFEST-CENSUS`). D2 must use whichever graph is on `origin/main` after `#5424` is decided — not a parallel defense21.

## D1 implications (not a D1 handoff)

- Entitled production capture with a real `site_full` session.
- Classify 401 on candidate API as locked, not unavailable, if that is the intended access meaning.
- Do not treat compact 2-row tape as the Change Tape product.
- Budget artifact: either publish the graph or stop the UI from spinning as if it exists.
- SAM opportunities: restore a source or print SOURCE_UNAVAILABLE honestly (already closer than a fake zero).
- Do not merge `#5424` from D0R.
- Do not “fix” lineage by weakening clocks or filling empty agency from inference.

## Access vs epistemics (restated)

Paid `site_full` is independent of display/context-only epistemics. Unlocking the 500-row workspace does not grant rank, gate, size, or candidate-admission authority.
