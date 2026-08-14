# MIGRATION PACKET — us_stocks.html (Prophet Board)

**packet-id:** MP-1 · **date:** 2026-08-13 · **author:** design authority (Fable main loop), conforming to the Prophet program ruling PR #5504
**Governing documents (in precedence order):** `research/PROPHET_RULING_J9C_J10_LIFECYCLE_CELLS.md` (the ruling — on any conflict it wins) → `research/P0_REFERENCE_EXPERIENCE_DESIGN_PACKET.md` §B as amended 2026-08-13 (the frozen reference) → `research/DESIGN_MIGRATION_FACTORY_V1.md` §0 gates → this packet's specifics.
**A builder that believes this packet is wrong stops and escalates to the design authority; the packet is amended or a dissent recorded — the builder never improvises (factory §1).**

## SPAWN GATES (all three, hard — do not commission the builder before)

- **G-A:** PR-0(c) merged AND a published `site/prophet/index.json` carries per-row `lifecycle_state` + the `lifecycle_counts` block (`lifecycle_live_total`, `lifecycle_grand_total`). The ladder cannot be built against a payload that lacks its field. (`early_turn_watch` may still be absent from a given bake — the watch cell's disclosed-absence state in §10 covers that; the *field contract* may not be absent.)
- **G-B:** DS-PR-0 merged (`.mx-ladder` and sibling `.mx-*` primitives live in `theme.css`).
- **G-C:** Mockup gate satisfied — rendered board mockups (light + dark + zh, 1440 + 390w) committed under `mockups/refs/institutionalize/us_stocks/`, reviewed against tension §G.2 (three count-bearing devices: lifecycle ladder / Candidates shelves / Groups lanes — three nouns, no visual merge). The spawn prompt inlines the factory §0 gates, this packet's path, and the committed mockup paths — never prose descriptions of a look.

---

## 1 ROUTE + TEMPLATE

- Route: `/us_stocks.html` (Prophet — US board), EN + ZH variants.
- Owning template: `templates/dashboard.html.j2` — **stocks-mode region only** (`body.page-stocks` blocks). The same file renders macro.html; that region is a sibling packet (factory docket item 10) and is out of scope here. This packet lands first; item 10 rebases on it.
- Card partial: `templates/_prophet_card.html.j2` (`pv_card` macro — shared with hk/china/canada/intl; see §9).
- Table module: `templates/stocktable.js` (US stock table).
- Count plumbing: `scripts/build_site.py`.
- Groups header total: `templates/_us_act_now_board.html.j2`.

## 2 ARCHETYPE

**B (Board)** — a governed inventory with one signature counting device; registry row `us_stocks.html` (per the DS-PR-1 re-keyed registry). First-of-archetype: this migration bakes archetype B's reference page.

## 3 CANONICAL REFERENCE

- Structural contract: `research/P0_REFERENCE_EXPERIENCE_DESIGN_PACKET.md` **§B as amended 2026-08-13** (six sections; ladder; count cure; unit of account; demotion landing table).
- Visual contract: the committed mockups under `mockups/refs/institutionalize/us_stocks/` (gate G-C) + the design-system specimen `mockups/design_system/specimen.html`.
- Semantics contract: the ruling §6 (cells, derivation, unit of account, two-total law), §5 (surface ownership), §10 (migration gates).

## 4 PRIMARY QUESTION

*"Which setups matter most right now, where in their lifecycle, and which am I allowed to act on today?"*

## 4b THE CELL SET (inlined from ruling §6 — the builder renders these, verbatim; labels come from PR-0(c)'s paired constants at build time, this table is the review checksum)

| # | Key (`data-life`) | EN | ZH | Weight encoding (§0 grammar) | Counted in headline? |
|---|---|---|---|---|---|
| 1 | `watch` | Watch | 观察 | dashed hairline | yes (live) |
| 2 | `ready` | Ready | 就绪 | half-filled | yes (live) |
| 3 | `entered` | Entered | 入场 | solid | yes (live) |
| 4 | `delivering` | Delivering | 达标 | solid | yes (live) |
| 5 | `overtime` | Overtime | 超时 | solid muted | yes (live) |
| 6 | `invalidated` | Invalidated | 失效 | hollow, struck rule | yes (live) |
| 7 | `resolved` | Resolved | 已结 | neutral outline | **no — terminal cell, outside the headline sum** |

Headline = `lifecycle_live_total` (cells 1–6); grand total = `lifecycle_grand_total`. The selected-cell state is solid fill + heavier rule (never violet, never a cell identity). Funnel order above is the ladder's left→right order.

## 5 PRIMITIVES TO REUSE

`.mx-ladder` (control form: cells carry `aria-pressed`; selection = solid fill + heavier rule, never violet) · `.pvcard` + `pv_css()` · the five-lane `.actcol/.acth` idiom (Groups — untouched) · `.dtp` + `.pbs` stamp (one each) · `.mx-tier-gate--prophet` (violet = locked, its only meaning) · LENS `data-tip-en/zh` · `_icons.html.j2` · `lib/illus.py` · `.st-view-toggle` · `.mx-empty` + `.mx-empty-why` · `.mx-sec` header anatomy. **New in this packet (template-scoped, not theme.css):** `.pv-mark` — the static lane mark chip; the episode chip on multi-row names.

## 6 MODULE DISPOSITIONS (every current first-level module exactly once)

| Current module | Disposition |
|---|---|
| "Prophet Stock Signals" card grid (population: `_su.buy` candidates) | **RETAIN as §2 SETUPS — population re-sourced to the plan book** (`site/prophet/index.json.plans`): one `.pvcard` per plan row, keyed by plan `id`; `data-life` from `lifecycle_state`; `data-ticker` retained for live-quote JS. **This re-sourcing is the migration's structural act (ruling §10.4)** |
| us-standouts screener (triage shelves + lane headings) | **RETAIN as §3 CANDIDATES / 候选** — own section, own printed-once header total; shelf counts are its decomposition; `data-stage` attr renamed `data-triage` (machine name only) |
| US stock table | **RETAIN minus the "Stage / 阶段" column and its count chips — RETIRED** (ruling §7/§10.5; the `RIPENING` chip is producer-less). No replacement column; the table gains `lifecycle` nothing — lifecycle lives on cards/ladder |
| Four-dot price-stage rail + int `stage` + inline `_STAGE_BY_LANE` duplicate (`dashboard.html.j2:16016`) | **REMOVE** (same-PR law, ruling §10.1); replaced by the lifecycle fact column + `.pv-mark` chip |
| Mega-cap tape | DEMOTE → §5 Market context, *Indexes & mega-caps* tab |
| Market State strip | COMPRESS → §1 regime/posture chips + macro.html |
| Indexes board | DEMOTE → §5 *Indexes & mega-caps* tab |
| Breadth board | DEMOTE → §5 *Breadth* tab |
| Turn Setups | MERGE-INTO §2's "What changed today" strip + link to the Turn Watch deck (never an embedded panel) |
| Accumulation watch | DEMOTE → §5 *Flow* tab (darkpool link-out) |
| Real fund moves | REMOVE (link-out to `smart_money.html` from *Flow* tab) |
| Release Radar / Week ahead | REMOVE (Today §5 calendar + `news.html`; link from §5) |
| Track record teaser | DEMOTE → §6 Evidence & record |
| Rates check | DEMOTE → §5 *Rates* tab |
| Sector Intelligence teaser | COMPRESS → §4 Groups header link |

## 7 MUST NOT CHANGE (verified in review)

- **Engine judgment:** `lane` values, `phase` computation, ranking, scoring, ledger writes — untouched (the ruling §4/§8; this PR is display-tier only).
- **Payload schemas:** `site/prophet/index.json` and plan JSONs are consumed as PR-0(c) published them; this PR adds no keys and recomputes nothing client-side that `lifecycle_counts` publishes.
- **Fossils:** historical snapshots keep int `stage` and old labels as written; the `data-triage` rename touches live templates only, never `data/` history (ruling §8).
- **Canonical counts:** every rendered quantity of setups quotes `lifecycle_counts`, a published total, or a computed difference — the page must not re-derive counts from row iteration where the block exists.
- **Access boundaries:** anonymous 1 card / Free 3 / paid full; withheld rows only in `premiumdata/us_stocks.json`; max two locks (Setups, Groups).
- **URLs:** `us_stocks.html` stays; only the fragment vocabulary changes (`#life=<cell>`).
- **Other markets:** hk/china/canada/intl keep the legacy rail via the `pv_card` parameter default (ruling §10.2) — zero rendered-byte change on non-US pages, test-pinned.
- **Graded-ledger population** never merges into the board (`DNR:KILL-PROPHET-POP-MERGE`).

## 8 FILES IN SCOPE (exhaustive)

- `templates/dashboard.html.j2` — stocks-mode region only.
- `templates/_prophet_card.html.j2` — lifecycle variant behind a parameter (default = legacy rail for non-US callers); `.pv-mark`; episode chip; lifecycle fact column.
- `templates/stocktable.js` — Stage column + chips retire (**caution:** `nav_market.js` is immutable at a hand-written key — stocktable.js is a different file, but the same hand-written-key discipline applies: read before regenerating).
- `scripts/build_site.py` — count plumbing (quote `lifecycle_counts`), Candidates total, `#life=` filter wiring.
- `templates/_us_act_now_board.html.j2` — Groups header total only.
- Tests (new/updated): chip-count law, two-total reconciliation, stage-word sweep, rail-absence, non-US byte-parity, fragment vocabulary.
- Rendered `site/` copies via the render lane (never hand-edited).

## 9 FORBIDDEN SCOPE

- `templates/theme.css` (DS-PR-0 owns tokens/primitives; any needed primitive change is a DS-PR, not this packet).
- Nav partials (`_site_nav.html.j2`, `_navlinks.html.j2`, `navigation-refresh.css`, `nav_market.js`).
- `scripts/build_prophet.py`, `engine/*` — PR-0(c) owns the field; this PR consumes it. If the payload contract is wrong, STOP and escalate; do not patch the exporter here.
- `dashboard.html.j2` macro-mode region (sibling packet, docket item 10 — this packet names its owned region as the stocks-mode blocks and lands first).
- `china.html.j2`, `hk.html.j2`, canada/intl templates (their rails are their program lanes' to retire; `china.html.j2:3551`'s hardcoded `'stage': 4` is documented, not touched).
- Plan JSON schemas, `config/plans.yml`, access config (Handoff A owns), `data/` writes of any kind.
- Banned vocabulary: no "stage/阶段" in any user-facing string; no "falsifier/refuted/证伪" (#3821); no blended confidence numbers (`DNR:KILL-FUSED-COMPOSITE`).

## 10 STATES (EN + ZH, written here — the builder copies, never invents)

- **loading:** card skeletons at true grid geometry; ladder cells show dashes, never zeros; no words.
- **empty:** "No live setups today — the board refreshes after the next close." / 「今日暂无在场计划——下个收盘后刷新。」 All-zero ladder still renders (the shape teaches the page). `.mx-empty` + `.mx-empty-why`, cause = *no qualifying rows today*.
- **watch key-absence (distinct from zero — ruling §6 fn.1):** when the payload has no `early_turn_watch` key, the watch cell renders "Watch tier publishes from the next nightly." / 「观察档自下一次夜间构建起发布。」 — never a silent 0.
- **stale:** existing `.nb-stale-note`; exactly one page stamp (`.dtp` + `.pbs`, no second as-of beside the ladder — packet §G.4).
- **error:** "The board didn't load. Candidates, Groups and Market context below are current." / 「看板未能加载。下方的候选、板块与市场环境仍是最新。」 + Retry.
- **dense:** grid view caps at 40 cards with `+{cell−shown} more` quoted as a computed difference; **table view renders every row of the active filter** (the exact-agreement surface).
- **Episode chip (multi-row names):** EN "Episode 2 · opened Aug 5" / ZH 「第 2 轮 · 8月5日启动」; resolved-episode cards add "Newer plan on this name →" / 「该股最新计划 →」 when a live row exists. Final microcopy settles at the mockup gate; the constraints (neutral ink, no hue, dated, only when >1 rows, never counted) are binding. ZH strings above are drafts pending the native-speaker pass required by the zh copy law — the reviewer checks they are not English-shaped.

## 11 EVIDENCE REQUIRED (PR body; review-blocking)

- Factory §0.2 screenshot matrix: light + dark × EN + ZH × 1440×900 + 390w.
- Forced-state shots: empty · error · watch key-absence · each of the seven ladder filters active · a two-episode ticker (both cards visible, episode-chipped) · the lock at the tier boundary.
- Harness capture per DS-PR-2's checklist.
- **Reconciliation evidence:** a side-by-side of the rendered ladder numbers against the payload's `lifecycle_counts` values for the same bake (a screenshot + the JSON excerpt), plus one filtered view showing rendered-cards + quoted `+N` = cell count.
- **Retirement evidence:** `grep -rn "#stage=" templates/` and a user-facing "Stage/阶段" sweep of the rendered US page (EN+ZH) — both empty, output pasted; the stocktable shown without the Stage column (light + dark).
- **Non-US parity evidence:** byte-diff of rendered hk/china/canada/intl pages against pre-migration output — empty.

## 12 ACCEPTANCE (factory §0 gates + amended P0 §B acceptance 1–12, verbatim binding + packet-specific)

Factory §0 gates ride in full. P0 §B acceptance (as amended 2026-08-13) is the page contract — items 1–12. Packet-specific additions, each testable by a stranger:

1. `lifecycle_state` → `data-life` mapping is 1:1 with the payload; no template-side re-derivation from `phase`/`closed`.
2. The `data-triage` rename is complete in live templates (no live `data-stage` remains) and zero fossilized files changed.
3. The `pv_card` lifecycle parameter defaults to legacy: non-US templates render byte-identical.
4. The inline `_STAGE_BY_LANE` duplicate at `dashboard.html.j2:16016` is gone.
5. `.pv-mark` renders at most once per card, from `lane` ∈ {bottoming, continuation} only; no chip for any other value; LENS tip carries the fact + gloss.
6. One `.dtp` + `.pbs` pair; the ladder adds no second stamp.
7. Sort rule stated in words beside the ladder; the ⚡ chip stays presentation-tier.
8. Page weight ≤ current us_stocks −10%; inline `<style>` growth within ratchet rule 7.

## 13 COLLISIONS (checked 2026-08-13)

- PR #5500 (Prophet decision packet) — open, answered by #5504; informational only.
- The Prophet program's queued "board funnel-presentation design pass" (gated on #5370, merged) — **this packet IS that pass**; the commissioning session cites both charters so it is built once.
- `dashboard.html.j2` is the estate's most-touched template — branch off fresh `origin/main` at spawn time; **rebuild-not-rebase** on conflict (site-heavy law); re-check `gh pr list --search "dashboard.html.j2"` at spawn.
- Sequencing: lands **before** factory docket item 10 (macro migration, same file); item 10's packet names its macro-mode region and rebases on this.
- DS-PR-0 / PR-0(c): spawn gates G-A/G-B above — recheck merge state at spawn, not at packet-read time.

## 14 ROLLBACK

Template-scoped: revert the merge commit + re-render (the shared render lane's next covering run restores the previous body; `?v=` stamps re-hash). No `data/` writes, no schema changes, no engine paths — the revert story is one commit. The stocktable column retire is a removal in `stocktable.js` restored by the same revert. Non-US surfaces are untouched by construction, so rollback risk is confined to the US board.

---

*Record (factory §3.7): mark DONE with the PR number here when merged; deviations/dissents append below this line.*
