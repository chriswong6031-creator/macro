# D0R discovery and blocker appendix

Recorded 2026-08-17. **Do not fix in D0R.** D1-or-later unless noted as already-known historical.

## Bugs / degraded live behavior

1. **Entitled desk is a 500-row award-change tape, not a complete product.** Cookie workspace 200 / 500 proven. Candidate Radar UI still membership-locked after candidates API 200/22. Filmstrip still “Members only.” D1: rehydrate-on-auth.
2. **Two auth planes.** Cookie JSON 200 does not make cookie-only `/api/government-revenue/*` 200. Radar uses bearer only.
3. **Candidate filmstrip membership copy after sign-in.** Unentitled used “Link status unavailable”; entitled uses “Members only” despite site_full. Same access, still wrong meaning.
4. **Agency facet / event agency empty.** Compact event `agency: {}` while official award is DISA/DoD. Facet ids are stringified Python dicts (`"{'id': 1174, ...}"`) — visible on entitled HII cards.
5. **`dates.known_at.semantic = "official"`** on a projector first-seen clock. Mislabels ingestion time as a government field.
6. **Late-discovery inconsistency.** JSON `is_late_discovery=true` on HC101319C0006; title is “New obligation observed”. Sibling HII row titles the lateness. A May action can be read as a fresh change. Entitled tape also shows `Reported obligated balance changed` on the same PIID.
7. **Budget graph 0 programs.** Entitled copy: “Budget request rail unavailable.” Files still absent from HEAD.
8. **Opportunities freshness unavailable with headline 0.** Must not be filed as EMPTY_VALID.
9. **HTML/cut clocks.** Capture 2026-08-17 still shows Aug 13 evidence; health checkout `8b5cd60f706`.
10. **`/api/health` `commit` (`a0b2aba13b5`) ≠ `checkout` (`8b5cd60f706`).** Inherited; still unexplained.
11. **Leftover compact-loading banner** after 500-row hydrate.

## Stale or inert components

- `shadow_context.py`, `market_context.py`, `sbir_progression.py`, `issuer_graph_expansion.py`: tests (and shadow’s own module) without builder/runtime import from `scripts/build_government_revenue.py`.
- `prophet_annotation.py` is wired in `prophet_bridge.py` fail-open; live annotation not captured. Bridge comment still says candidate radar is empty; HEAD `candidate_count=22`.
- Compact briefcase (save/export/alerts) disabled until workspace hydrate.
- Award-detail `award_event_snapshots` row for HC101319C0006 is an older eligible=false cut (modified 2026-03-11) beside a live action P00032 (2026-05-12). Dual-read required.

## Spec vs live contradictions

- Architecture/kickoff: “Candidate Radar is a product tab.” Live entitled: API 22, UI locked overlay. Unentitled: 0 + loading.
- Status file `source_health.status=ok` vs UI “Partial or stale coverage” (client aging + opportunity unavailable + lock).
- Graph `companies` 19 tickers vs compact company strip 21 (GE, BWXT extra). `#5424` would add BWXT on defense20-v1 — still **open**, not live.
- Collection continued 2026-08-14 (new action-page sha) but published compact bundle remains 2026-08-13 / receipt `2a07ba19…`.

## Duplicate-plane hazards (do not mint)

- Company financials / backlog / GAAP / guidance / estimates / prices / options / dark pool / themes / identity Atlas / Neural Web / Prophet. V3 consumes those planes; it does not fork them.
- A second reviewed recipient graph (`DNR:LAW-REVIEWED-MANIFEST-CENSUS`). D2 must use whichever graph is on `origin/main` after `#5424` is decided — not a parallel defense21.

## D1 implications (not a D1 handoff)

- Rehydrate Candidate Radar and filmstrip after `MDXAuth` session; do not show membership CTA to site_full.
- Classify 401 on candidate API as locked, not unavailable, if that is the intended access meaning; after 200, clear the lock.
- Do not treat compact 2-row tape as the Change Tape product.
- Attach bearer for `/api/government-revenue/*`; cookie JSON is a different plane.
- Budget artifact: either publish the graph or stop the UI from spinning as if it exists.
- SAM opportunities: restore a source or print SOURCE_UNAVAILABLE honestly (already closer than a fake zero).
- Do not merge `#5424` from D0R.
- Do not “fix” lineage by weakening clocks or filling empty agency from inference.

## Access vs epistemics (restated)

Paid `site_full` is independent of display/context-only epistemics. Unlocking the 500-row workspace does not grant rank, gate, size, or candidate-admission authority.
