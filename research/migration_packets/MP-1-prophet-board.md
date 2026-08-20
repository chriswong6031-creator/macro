# MIGRATION PACKET — us_stocks.html (Prophet Board)

**packet-id:** MP-1 · **date:** 2026-08-13 · **author:** design authority (Fable main loop), conforming to the Prophet program ruling PR #5504
**Amended:** 2026-08-19 — **Amendment 1** (C8 composition cycle over the R4 reference; condition C8-A). Executes the frozen rulings of `research/reference_integrity/prophet-board-5514-r4-composition/verdict.yml` against this packet's law. Full mapping table + citations at the bottom of this file, above the Record line. C8-A does not touch R4/R5 or re-adjudicate any ruling; where a ruling is routed to Sol for veto (b1), this packet records it effective-unless-countermanded.
**Amended:** 2026-08-19 — **Amendment 2** (post-C8-B ratifications + shell-commissioning rulings by the commissioning session). Four items: (1) §10's loading state adopts C8-B's dash law — the em dash keeps its single meaning (published-and-absent, ruling §6 fn.1) and never means "loading"; skeletons shimmer the counts instead. (2) §10's error copy adopts C8-B's shipped three-section string ("Candidates, Groups and the record below"), superseding Amendment 1's two-section draft — the reference proved the record strip is a surviving section the promise must cover. (3) New §8b: paid-boundary adaptation ownership (`_split_us_board`/`_write_us_payload`), previously unowned. (4) G-D-1 re-measurement discipline after the 2026-08-19 library partial-build incident. No composition, reference, or ruling is re-adjudicated.
**Governing documents (in precedence order):** `research/PROPHET_RULING_J9C_J10_LIFECYCLE_CELLS.md` (the ruling — on any conflict it wins) → `research/P0_REFERENCE_EXPERIENCE_DESIGN_PACKET.md` §B as amended 2026-08-13 (the frozen reference) → `research/DESIGN_MIGRATION_FACTORY_V1.md` §0 gates → `research/reference_integrity/prophet-board-5514-r4-composition/verdict.yml` (C8 composition-cycle rulings, binding on the items Amendment 1 touches) → this packet's specifics.
**A builder that believes this packet is wrong stops and escalates to the design authority; the packet is amended or a dissent recorded — the builder never improvises (factory §1).**

## SPAWN GATES (all three, hard — do not commission the builder before)

- **G-A:** PR-0(c) merged AND a published `site/prophet/index.json` carries per-row `lifecycle_state` + the `lifecycle_counts` block (`lifecycle_live_total`, `lifecycle_grand_total`). The ladder cannot be built against a payload that lacks its field. (`early_turn_watch` may still be absent from a given bake — the watch cell's disclosed-absence state in §10 covers that; the *field contract* may not be absent.)
- **G-B:** DS-PR-0 merged (`.mx-ladder` and sibling `.mx-*` primitives live in `theme.css`).
- **G-C:** Mockup gate satisfied — rendered board mockups (light + dark + zh, 1440 + 390w) committed under `mockups/refs/institutionalize/us_stocks/`, reviewed against tension §G.2 (three count-bearing devices: lifecycle ladder / Candidates shelves / Groups lanes — three nouns, no visual merge). The spawn prompt inlines the factory §0 gates, this packet's path, and the committed mockup paths — never prose descriptions of a look.
- **G-D-1 (Amendment 1, b1 ruling):** the display-tier actionability axis is publishable estate-wide — **MET**. Under the b1 ruling (`verdict.yml` `rulings.b1_actionability_axis`), stance sources `entry_status` when present, else `board_read.fields.status`, and the fallback field is published at `board_read.fields.status` availability **225/225**, `blocked_data: 0`, `site/prophet/index.json` `asof` **2026-08-18** (product_regression.yml decisive_receipt). This re-opens no population/blend/rank/gate (`DNR:KILL-PROPHET-POP-MERGE`, confronted at §8a below) and re-closes the sequencing item the product receipt raised ("RULE B1... Opens or re-closes G-D-1"). Effective unless Sol countermands b1. **[Amendment 2 — re-measurement discipline]** The MET verdict above was measured at the 2026-08-18 payload. On 2026-08-19 `site/prophet/index.json` collapsed to 43/250 healthy (`ticker_absent_from_library: 207`, `source_as_of` null) — a same-day **partial build** triggered by #5980's i18n guard, healed by #6006 (squash `0de8b86`, merged 2026-08-19T20:07:23Z), not a data regression. Standing rule: G-D-1 is re-measured against the **current** nightly payload at every (re-)commissioning of this packet, and a MET verdict older than the newest nightly is stale evidence — a collapse whose root cause is a build-lane defect HOLDS commissioning until the heal's next nightly proves recovery, but does not un-MET the gate's underlying availability claim. **[Day-3 receipt, 2026-08-20T05:17Z — PASS, and the binding reading is ADJUDICATED.]** Measured at the post-#6006 publication `0b0c296f85f3` (blob `251b935155d8bd584347d7c924f9cb7acd945851`, byte-identical at tip): **frozen Reading A** — `available / (available + blocked_data)`, with the producer-law exclusion `not_applicable: plan_closed` (25 rows, `closed:true` in both directions, structurally stable across every healthy snapshot) — = **237/237 = 100.0000%**, `blocked_data: 0`, `read_errors: {}`, `status_unmapped: {}`; gross-row Reading B = 237/262 = 90.46%; every plausible reading clears ≥90%. Both #5980 failure signatures (`ticker_absent_from_library`, null `source_as_of`) are **absent at zero**. **Reading A is hereby adjudicated the binding G-D-1 reading**: it uniquely reproduces this gate's own literal "225/225" (on snapshot `9d73eaa2c93b`), and it is stable where Reading B has 1-row slack near 90% on ordinary nights (the 08-18 229-row snapshot reads 89.08% under B while 100% under A). Erratum recorded for the cited decisive_receipt: `product_regression.yml` `second_pass.decisive_receipt` labels its 250-row/225-available figures "at e8b54f057f58 (2026-08-18)" — those figures belong to `9d73eaa2c93b` (2026-08-19T06:57Z); `e8b54f057f58` carries 229 rows / 204 available. Numbers right, commit label off by one publication; substance unaffected.

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
| 5 | `overtime` | Overtime | 超时 | solid muted | yes (live) [fn.2] |
| 6 | `invalidated` | Invalidated | 失效 | hollow, struck rule | yes (live) |
| 7 | `resolved` | Resolved | 已结 | neutral outline | **no — terminal cell, outside the headline sum** |

Headline = `lifecycle_live_total` (cells 1–6); grand total = `lifecycle_grand_total`. The selected-cell state is solid fill + heavier rule (never violet, never a cell identity). Funnel order above is the ladder's left→right order.

**[fn.2, Amendment 1, b8 ruling — CLOSED BY CITATION]** The Overtime cell's clock is not the retired `age_days`/horizon anchor (35 live rows show `age_days>horizon_days` while `lifecycle_counts.overtime=0`) — `plan_clock_date()` is the authoritative plan clock, already ruled (SEA #4684, commit `242aafda0dc7`); the #5540 overtime contradiction was healed and its closure verified in the D-LAB-R5 blocker re-census (commit `444f80d62774`: 0 rows past horizon on the plan's own clock, 0 `phase=overtime`). The C8 product-regression receipt corroborates on the current payload: `clock_age_days>horizon` on 0 rows. No change to this table's Overtime row or to `lifecycle_counts` derivation — the cell was already correct; this note exists so a builder does not re-open the age_days/horizon question the reference's own DESIGN_NOTES Q2 recorded UNRESOLVED (2026-08-13, before the ruling landed).

## 5 PRIMITIVES TO REUSE

`.mx-ladder` (control form: cells carry `aria-pressed`; selection = solid fill + heavier rule, never violet) · `.pvcard` + `pv_css()` · the five-lane `.actcol/.acth` idiom (Groups — untouched) · `.dtp` + `.pbs` stamp (one each) · `.mx-tier-gate--prophet` (violet = locked, its only meaning) · LENS `data-tip-en/zh` · `_icons.html.j2` · `lib/illus.py` · `.st-view-toggle` · `.mx-empty` + `.mx-empty-why` · `.mx-sec` header anatomy. **New in this packet (template-scoped, not theme.css):** `.pv-mark` — the static lane mark chip; the episode chip on multi-row names.

**[Amendment 1] Vocabulary resolution — `.pv-mark` / `.mx-mark` / `.pv-cau` (P-B5, pv_cau_classification ruling):**

- **`.pv-mark` and `.mx-mark` are two different primitives, not a naming variance — do not conflate or pick one.** `.pv-mark` (above) is *this packet's* template-scoped lane chip, keyed on `lane` ∈ {bottoming, continuation}, per §12 acceptance item 5. `.mx-mark` is the reference's **six-weight lifecycle glyph mirrored at inline/card scale** (`board.css:291,300-380`; used in the card's `pv-life` row and the table's `st-life` cell, `board.js:493,811`) — the same weight grammar as `.mx-cap`/`.mx-ladder`, at a smaller size, on the card and table row rather than the ladder. Because it shares the `mx-` family prefix and the `.mx-cap`/`.mx-ladder` weight-grammar contract, `.mx-mark` is an **inherited DS-PR-0 primitive** (gate G-B), not a template-scoped invention — add it to this packet's reuse list explicitly: `.mx-mark` (six-weight lifecycle glyph, card + table scale).
- **`.pv-cau`** (the risk-flag pill, `board.js:473-479`, `board.css:912-940`) is **authorized per the verdict's `pv_cau_classification` ruling, written both ways as the ruling states** (the R4.2 shipped-CSS check that resolves this branch is C8-B's lane, not this packet's):
  - **If `.pv-cau` is byte-shipped production CSS** (evidence pointing this way: `templates/_prophet_card.html.j2:308` already defines `.pv-cau{position:relative;display:inline-flex}` byte-for-byte) — the 19px touch target is **estate debt**, joins K5's DS-PR-lane sub-40px control list (C8-C), and `.pv-cau` is an **inherited primitive** here: authorized as-is, its touch-floor fix is out of this packet's scope.
  - **If `.pv-cau` is reference-minted** (not actually shipped) — R4.2 fixes its target to ≥40px effective before this packet consumes it, and MP-1 §5 authorizes it explicitly only at the corrected floor.
  - Either branch: the touch-path obligation (raising the control to MPDS §14's ≥40px floor) lands in the DS-PR lane (§13 collision below) with the other sub-floor controls, never as a page-scoped fork in this packet.

**[Amendment 1] LENS obligation — bind, don't port (P-K1):** the reference's LENS (`board.js:1300-1309`) is hover/focus-only. Production's LENS (`theme.js:5283+`) already has a full touch branch consuming the same `data-tip` attribute triple. The builder **binds every tip to production's LENS** (same `data-tip-en`/`data-tip-zh` attribute pair, same trigger element contract) and **never ports board.js's renderer** — porting would regress the touch branch production already has. Not migration-blocking (K1 upheld as known-issue, not a blocker); stated here so the reuse list above is read as "production's LENS," not "the reference's."

## 6 MODULE DISPOSITIONS (every current first-level module exactly once)

| Current module | Disposition |
|---|---|
| "Prophet Stock Signals" card grid (population: `_su.buy` candidates) | **RETAIN as §2 SETUPS — population re-sourced to the plan book** (`site/prophet/index.json.plans`): one `.pvcard` per plan row, keyed by plan `id`; `data-life` from `lifecycle_state`; `data-ticker` retained for live-quote JS. **This re-sourcing is the migration's structural act (ruling §10.4)** |
| us-standouts screener (triage shelves + lane headings) | **RETAIN as §3 CANDIDATES / 候选** — own section, own printed-once header total; shelf counts are its decomposition; `data-stage` attr renamed `data-triage` (machine name only) |
| US stock table | **RETAIN minus the "Stage / 阶段" column and its count chips — RETIRED** (ruling §7/§10.5; the `RIPENING` chip is producer-less). No replacement column; the table gains `lifecycle` nothing — lifecycle lives on cards/ladder |
| Four-dot price-stage rail + int `stage` + inline `_STAGE_BY_LANE` duplicate (`dashboard.html.j2:16016`) | **REMOVE** (same-PR law, ruling §10.1); replaced by the lifecycle fact column + `.pv-mark` chip |
| Mega-cap tape | ~~DEMOTE → §5 Market context, *Indexes & mega-caps* tab~~ **[Amendment 1, V-B2] §5 no longer exists (VTC-307/§0a.D, UPHELD deletion — producer-less tab shell). Explicit disposition: RETAIN in place, unchanged.** Production already carries the lawful, event-gated form on the stocks-mode page header itself — `{% include "_mag7_tape_strip.html.j2" %}` at `dashboard.html.j2:2286` inside `#stocks-header`, ruled `DO_NOT_REBUILD.md` §2/§4 and `POSTMORTEM_20260803_MAG7_RALLY_SILENCE_BY_FABLE.md` §6 F2. No migration action; carries forward as the page-§1 regime/posture context, alongside the Market State strip below. |
| Market State strip | COMPRESS → §1 regime/posture chips + macro.html |
| Indexes board | ~~DEMOTE → §5 *Indexes & mega-caps* tab~~ **[Amendment 1, V-B2] Explicit disposition: RETAIN in place, unchanged.** Already live, stocks-mode-gated, independent of the deleted tab: "MAJOR US INDEXES — HEALTH & RISK" panel, `dashboard.html.j2:15185-15186` (`{% if mode == 'stocks' %}`, comment notes macro-mode's index content already moved to the MARKETS tray in v2). Folds into page-§1 regime/posture context; no new tab. |
| Breadth board | ~~DEMOTE → §5 *Breadth* tab~~ **[Amendment 1, V-B2] Explicit disposition: RETAIN in place, unchanged.** Already live, stocks-mode-gated: "US EQUITY SCOREBOARD (size + breadth + internals)" / "Market breadth — S&P 1500", `dashboard.html.j2:16517-16521` (`{% if mode != 'macro' %}`). Folds into page-§1 regime/posture context; no new tab. |
| Turn Setups | MERGE-INTO §2's "What changed today" strip + link to the Turn Watch deck (never an embedded panel) |
| Accumulation watch | ~~DEMOTE → §5 *Flow* tab (darkpool link-out)~~ **[Amendment 1, V-B2] Explicit disposition: RETAIN in place, unchanged.** Already live, stocks-mode-gated with a real producer (sector-SPDR weight-vs-price residual): `dashboard.html.j2:16906-16908` (`{% if mode != 'macro' %}`, `id="accumulation"`). Folds into page-§1 regime/posture context; the darkpool link-out to `smart_money.html` stays available for full detail, but the summary panel is not removed. |
| Real fund moves | REMOVE (link-out to `smart_money.html` from *Flow* tab) |
| Release Radar / Week ahead | REMOVE (Today §5 calendar + `news.html`; link from §5) |
| Track record teaser | DEMOTE → §6 Evidence & record |
| Rates check | ~~DEMOTE → §5 *Rates* tab~~ **[Amendment 1, V-B2] Explicit disposition: RETAIN in place, unchanged.** Already live, stocks-mode-gated: "Rates, bonds & FX — cross-asset check" inside "CROSS-ASSET MACRO", `dashboard.html.j2:15104,15107,15113` (`{% if mode == 'stocks' and (_rit or _cac) %}`). Deeper rates/liquidity detail stays link-out to `macro_context.html#rates` (`macro_context.html.j2:1031`, real producer, unaffected). Folds into page-§1 regime/posture context; no new tab. |
| Sector Intelligence teaser | COMPRESS → §4 Groups header link |

**[Amendment 1, V-B2] Disposition note for the five rows above:** each was previously routed to page-§5 "Market context," a tabbed section the VTC-307/§0a.D ruling deletes as a producer-less shell (header + five tab anchors bound to no producer — `DESIGN_NOTES.md:279-284`). That deletion is UPHELD and stands. What the C8 product-regression receipt (B2) found is that these five modules are **not themselves producer-less** — each already renders live, mode-gated, on the current pre-migration `us_stocks.html` (file:line citations above), independent of the tab shell MP-1 had assumed would house them. Their disposition is therefore RETENTION as page-§1 regime/posture context (the same bucket the Market State strip already compresses into), not re-homing into a tab that no longer exists and never needs to. This closes the "MP-1 §6 still routes content to the deleted section" defect without inventing new IA.

## 7 MUST NOT CHANGE (verified in review)

- **Engine judgment:** `lane` values, `phase` computation, ranking, scoring, ledger writes — untouched (the ruling §4/§8; this PR is display-tier only).
- **Payload schemas:** `site/prophet/index.json` and plan JSONs are consumed as PR-0(c) published them; this PR adds no keys and recomputes nothing client-side that `lifecycle_counts` publishes.
- **Fossils:** historical snapshots keep int `stage` and old labels as written; the `data-triage` rename touches live templates only, never `data/` history (ruling §8).
- **Canonical counts:** every rendered quantity of setups quotes `lifecycle_counts`, a published total, or a computed difference — the page must not re-derive counts from row iteration where the block exists.
- **Access boundaries:** anonymous 1 card / Free 3 / paid full; withheld rows only in `premiumdata/us_stocks.json`; max two locks (Setups, Groups).
- **URLs [Amendment 1, P-B4 — restated]:** `us_stocks.html` stays. The filter/state contract is the **query string**, `?life=<cell>` — this restates the prior fragment-only law, which the reference does not implement: `board.js:80` reads `location.search` only, and `:1270` filters by full navigation on the query string; the `#life=` fragment is written (`:1271,:1278`) but never read, so a packet-authored `#life=` link would silently render the unfiltered board (B4). **Inbound legacy `#life=<cell>` deep-links are honored for compatibility** — on load, if the query string carries no `life` param and the fragment does, treat the fragment value as the filter (read-once, then the query string is the source of truth for all in-page state changes); never write a fragment as this migration's own output. Same-tick search+hash navigation races (B4, reference `:1270-1271`) are avoided by construction: only the query string is ever written.
- **Other markets:** hk/china/canada/intl keep the legacy rail via the `pv_card` parameter default (ruling §10.2) — zero rendered-byte change on non-US pages, test-pinned.
- **Graded-ledger population** never merges into the board (`DNR:KILL-PROPHET-POP-MERGE`).

## 8 FILES IN SCOPE (exhaustive)

- `templates/dashboard.html.j2` — stocks-mode region only.
- `templates/_prophet_card.html.j2` — lifecycle variant behind a parameter (default = legacy rail for non-US callers); `.pv-mark`; episode chip; lifecycle fact column.
- `templates/stocktable.js` — Stage column + chips retire (**caution:** `nav_market.js` is immutable at a hand-written key — stocktable.js is a different file, but the same hand-written-key discipline applies: read before regenerating).
- `scripts/build_site.py` — count plumbing (quote `lifecycle_counts`), Candidates total, `#life=` filter wiring.
- `templates/_us_act_now_board.html.j2` — Groups header total only.
- Tests (new/updated): chip-count law, two-total reconciliation, stage-word sweep, rail-absence, non-US byte-parity, fragment **and query-string** vocabulary (§7 Amendment 1).
- Rendered `site/` copies via the render lane (never hand-edited).

### 8a STANCE PROJECTION — ownership (Amendment 1, P-B7, b1 ruling)

Previously unowned (B7: "the 12-status→5-verb stance projection has no owner in MP-1 §8"). This packet now owns it, in files already in scope above (`templates/_prophet_card.html.j2`, `scripts/build_site.py`):

- **Source/fallback contract, verbatim in substance from the b1 ruling:** display-tier stance sources `entry_status` when present; **else `board_read.fields.status`** — ticker-scoped, the same twelve-value vocabulary and the same `us_stock_library` producer the board already partitions via the Q7 bucket table (`_LIVE_STATUSES`/`_SETTING_UP_STATUSES`/`_RAN_STATUSES`/`_BLOCKED_STATUSES` → Buy/Near · Wait · Hold · Avoid, `DESIGN_NOTES.md:526-538`) — the fallback field is projected through the **same** bucket table, never a second mapping.
- **Per-row disclosure:** every card/row carries a `stance_basis` value naming which source rendered (`entry_status` or `board_read.fields.status`), surfaced at minimum in the LENS tip — never silently merged into one undifferentiated verb.
- **"No read yet" (BLOCKED_DATA, no stance hue, per `DESIGN_NOTES.md:563-567`) renders only when BOTH `entry_status` and `board_read.fields.status` are absent** for a row. Neither source absent alone is sufficient.
- **DNR:KILL-PROPHET-POP-MERGE confronted by name:** this ownership changes no population, no blend, no rank, no gate — the graded board population and `us_board_ledger` are untouched; only the display verb's *source field* widens, inside the same library the board already consumes (§7's existing DNR bullet is satisfied, not contradicted).
- **Macro wait-default parameterization requirement:** the shared `pv_card` macro's verb fallback (`templates/_prophet_card.html.j2:374`, `{%- set _verb = cx.verb if cx.verb in _VEN else 'wait' -%}`) silently renders `wait` for any unrecognized/absent verb — exactly the default DESIGN_NOTES Q7 forbids for an unobtainable stance. This macro is shared estate-wide (§1: "shared with hk/china/canada/intl"); it must gain a **parameter** so the US lifecycle-variant call path can render the no-read state instead of defaulting to `wait` when both sources are absent, while **every other caller's byte output is unchanged** — the parameter defaults to the current legacy behavior. This is additive to, not a repeal of, §12 acceptance item 3 (`pv_card` lifecycle parameter defaults to legacy) and §11's non-US byte-parity evidence requirement: both must still show an empty byte-diff on hk/china/canada/intl.
- **Note:** the b1 ruling is routed to Sol for veto. This packet records the contract above as **effective unless countermanded** — if Sol vetoes, this subsection reverts to G-D-1's prior (not-MET) state and the builder stops per the packet's standing escalation rule (top of file) rather than improvising a replacement mapping.

### 8b PAID-BOUNDARY ADAPTATION — ownership (Amendment 2, commissioning-session ruling 2026-08-19)

Previously unowned: §7 freezes the access-boundary *invariant* (anon 1 card / Free 3 / paid full; the `premiumdata` split; 401 behavior byte-equivalent in effect) but no section owned the *code adaptation* those functions need when the shell's markup changes. Ruling:

- **This packet's shell PR owns the adaptation of `_split_us_board` (`scripts/build_site.py:4861`) and `_write_us_payload` (`scripts/build_site.py:4928`)** to the migrated markup — split points, preview-row counts, and payload shape may be *re-plumbed*, never *re-drawn*: the observable boundary (which rows an anonymous, Free, and paid viewer can obtain, by any channel including view-source and the JSON payloads) is frozen and must be byte-equivalent **in effect** to pre-migration production.
- **Mandatory independent review of exactly that diff:** the paid-boundary hunks of the shell PR get their own named reviewer pass (opus `reviewer`, adversarial, attacking leakage: preview rows exceeding tier, withheld rows reachable via the payload, lock states rendering the wrong tier's count). The shell PR body carries that review's verdict; self-review by the builder does not satisfy this.
- **Server-side withholding stays server-side** (§7): no client-side gating may replace a server-side split as part of the adaptation, even transiently.
- Rationale: the boundary is a revenue and trust surface shared with the charting-app product; an unowned adaptation is exactly how a silent tier leak ships inside an otherwise-lawful visual migration.

## 9 FORBIDDEN SCOPE

- `templates/theme.css` (DS-PR-0 owns tokens/primitives; any needed primitive change is a DS-PR, not this packet). **[Amendment 1, P-B3 — restated]** This law is unchanged and now explicitly covers the DA-002 `--pv-buy`/`--ink-pv-buy` retune: that retune is C8-C's DS-PR lane (§13), never a page-scoped fork inside this packet. This packet's shell must render correctly, with no visual dependency on whether the DS-PR has landed — the stance-ramp collision the retune cures is a pre-existing production defect (DA-002, live today), not something this migration may treat as already fixed. See §13 for the collision this creates against the non-US byte-parity gate.
- Nav partials (`_site_nav.html.j2`, `_navlinks.html.j2`, `navigation-refresh.css`, `nav_market.js`).
- `scripts/build_prophet.py`, `engine/*` — PR-0(c) owns the field; this PR consumes it. If the payload contract is wrong, STOP and escalate; do not patch the exporter here.
- `dashboard.html.j2` macro-mode region (sibling packet, docket item 10 — this packet names its owned region as the stocks-mode blocks and lands first).
- `china.html.j2`, `hk.html.j2`, canada/intl templates (their rails are their program lanes' to retire; `china.html.j2:3551`'s hardcoded `'stage': 4` is documented, not touched).
- Plan JSON schemas, `config/plans.yml`, access config (Handoff A owns), `data/` writes of any kind.
- Banned vocabulary: no "stage/阶段" in any user-facing string; no "falsifier/refuted/证伪" (#3821); no blended confidence numbers (`DNR:KILL-FUSED-COMPOSITE`).

## 10 STATES (EN + ZH, written here — the builder copies, never invents)

- **loading:** card skeletons at true grid geometry; **[Amendment 2 — C8-B ratified]** the ladder skeletons shimmer the **counts** only — never dashes and never zeros: the em dash already carries a single lawful meaning on this board (*published-and-absent*, ruling §6 fn.1), and a loading dash would make one glyph carry two facts. The three non-live states stay visibly distinct by mechanism: `.pv-ghost` **blurs** (exists, withheld), `.skel` **shimmers** (not yet arrived), `.mx-error` **stops moving** and names what failed. No words in the loading state.
- **empty:** "No live setups today — the board refreshes after the next close." / 「今日暂无在场计划——下个收盘后刷新。」 All-zero ladder still renders (the shape teaches the page). `.mx-empty` + `.mx-empty-why`, cause = *no qualifying rows today*.
- **watch key-absence (distinct from zero — ruling §6 fn.1):** when the payload has no `early_turn_watch` key, the watch cell renders "Watch tier publishes from the next nightly." / 「观察档自下一次夜间构建起发布。」 — never a silent 0.
- **watch present-at-zero [Amendment 1, P-K19 — new, distinct from key-absence above]:** when `early_turn_watch` is **present and empty** (`watchAbsent()` false — the current production payload state, per the C8 product-regression receipt K19), the watch cell renders its normal zero-count ladder cell like any other live cell at 0 — **not** the key-absence copy above, and not a blank. The reference itself photographs the superseded key-absent state everywhere (every canonical crop, the "five published cells" headline) even though production has already moved to present-and-empty; this packet's canonical crops must include the present-at-zero state so the builder is not working from a stale reference photograph.
- **stale:** existing `.nb-stale-note`; exactly one page stamp (`.dtp` + `.pbs`, no second as-of beside the ladder — packet §G.4).
- **error [Amendment 1, V-B2 — error copy corrected; Amendment 2 — C8-B shipped string ratified]:** "The board didn't load. Candidates, Groups and the record below are current." / 「看板未能加载。下方的候选、板块与战绩仍是最新。」 + Retry (≥40px, MPDS §14). Supersedes Amendment 1's two-section draft: the reference build proved the trading-record strip is a third surviving section the error's promise must cover for the promise to be *true*. (The original correction stands: "Market context" is never named — §6's disposition retires that tab.)
- **dense:** grid view caps at 40 cards with `+{cell−shown} more` quoted as a computed difference; **table view renders every row of the active filter** (the exact-agreement surface).
- **Episode chip (multi-row names):** EN "Episode 2 · opened Aug 5" / ZH 「第 2 轮 · 8月5日启动」; resolved-episode cards add "Newer plan on this name →" / 「该股最新计划 →」 when a live row exists. Final microcopy settles at the mockup gate; the constraints (neutral ink, no hue, dated, only when >1 rows, never counted) are binding. ZH strings above are drafts pending the native-speaker pass required by the zh copy law — the reviewer checks they are not English-shaped.

## 11 EVIDENCE REQUIRED (PR body; review-blocking)

- Factory §0.2 screenshot matrix: light + dark × EN + ZH × 1440×900 + 390w.
- Forced-state shots: empty · **loading [Amendment 1, V-B4]** · error · watch key-absence · **watch present-at-zero [Amendment 1, P-K19, §10]** · each of the seven ladder filters active · a two-episode ticker (both cards visible, episode-chipped) · **the Free-tier lock at its own boundary, distinct from the anonymous lock [Amendment 1, P-K16]** · the anonymous-tier lock.
- **[Amendment 1, V-B4]** Error and loading states must match the specimen's canonical components (`mockups/design_system/specimen.html` `.mx-error` `:109-116`, loading skeleton `:443-461`) — both exist in the specimen and were absent, undisclosed, from the reference (N1: the specimen was wrongly declared non-existent on a sparse-tree `ls` rather than checked from HEAD, per `research/WORKTREE_GC_POLICY.md`'s own sparse-checkout trap). §10's error copy above is this packet's canonical error string; the loading state is §10's existing "loading" bullet (skeleton at true grid geometry; per Amendment 2 the counts shimmer — no dashes, no zeros).
- **[Amendment 1, P-K16]** The reference has no Free-tier forced state at all (K16, `board.js:1166`) — distinct from the anonymous 1-card lock. §7's access-boundary law (anon 1 / Free 3 / paid full, max two locks) already requires both; this evidence bullet makes the Free-tier boundary shot mandatory rather than assumed-covered by "the lock."
- **[Amendment 1, N3 — named gate item, not a screenshot requirement]** Three of the seven lifecycle cells — **Watch, Delivering, Overtime** — have **no card-level visual contract anywhere in the crop set** (disclosed by the reference's own author, `DESIGN_NOTES.md` §8, PRC-319). This is not curable by re-shooting the existing reference; it closes only when the underlying producers publish rows in those states to photograph. Record as an open gate item at commissioning time — the spawn prompt must name it explicitly rather than silently omitting three of seven cells from the evidence matrix — and do not treat its absence from the crop set as a defect in the builder's evidence collection.
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

## 13 COLLISIONS (checked 2026-08-13; Amendment 1 adds the entry below, 2026-08-19; Day-3 adds the W-L1 row, 2026-08-20)

- **[Day-3, OPEN — ROUTED TO SOL, no disposition minted here] W-L1 provisional-board live-refresh vs the central-act grid re-source.** The card grid this packet re-sources (`#us-standouts .nbgrid`) is the live DOM target of the PINNED Breathing Platform W-L1 surface (`research/WL1_PROVISIONAL_BOARD_DESIGN_SPEC.md`): ~930 lines of live-refresh JS (`dashboard.html.j2:18472-19402`) inject server-rendered card fragments carrying the CURRENT `_su.buy`/stage taxonomy, plus the board-state stamp in the same header. This packet is silent on it (grep "W-L1" → zero before this row). Re-sourcing the population/markup without a W-L1 disposition either kills live intraday refresh silently (selector miss) or ships a nightly-vs-live taxonomy contradiction on one page. The ratified END state already exists — LAB-0 §6.5's `ProphetBoardController` absorbs the W-L1 poller in P-LAB-UI — so the open question is only the TRANSITION: (a) the shell also ports the W-L1 injection to the new taxonomy (scope growth, work the controller redoes); (b) the shell neutralizes W-L1's grid repaint while preserving the poller + the stamp's truth-law, full live repaint returning with the controller (bounded; one panel's intraday card refresh pauses between shell and P-LAB-UI — a cross-program concession needing Breathing-Platform sign-off); (c) re-order so the controller lands first (contradicts frozen LAB-0 §6). **The builder halts on the central act until Sol rules; discovered by the #6049 builder, 2026-08-20.**

- PR #5500 (Prophet decision packet) — open, answered by #5504; informational only.
- The Prophet program's queued "board funnel-presentation design pass" (gated on #5370, merged) — **this packet IS that pass**; the commissioning session cites both charters so it is built once.
- `dashboard.html.j2` is the estate's most-touched template — branch off fresh `origin/main` at spawn time; **rebuild-not-rebase** on conflict (site-heavy law); re-check `gh pr list --search "dashboard.html.j2"` at spawn.
- Sequencing: lands **before** factory docket item 10 (macro migration, same file); item 10's packet names its macro-mode region and rebases on this.
- DS-PR-0 / PR-0(c): spawn gates G-A/G-B above — recheck merge state at spawn, not at packet-read time.
- **[Amendment 1, P-B3] The DS-PR-lane `--pv-buy`/`--ink-pv-buy` retune (C8-C, DA-002 cure) collides with §11's non-US byte-parity gate.** DA-002 is a live-in-production-dark token collision (`theme.css:80` sets `--pv-buy == #45b873 == --up` at `:72`; `:185` aliases it; `_prophet_card.html.j2:77` routes `--pvh-ink` through it) that the C8 product-regression receipt found undocumented in this packet's gate structure (B3). Its cure is C8-C, a **separate Design-System PR — never a page-scoped fork inside MP-1** (§9, restated above): it retunes shared `theme.css` tokens consumed estate-wide, including by hk/china/canada/intl. Because §7/§11/§12 item 3 require those pages' rendered bytes to be **empty-diff** against pre-migration output, the DS-PR is a genuine collision, not a sequencing nicety: **C8-C must prove its own non-US byte-parity (or an explicitly accepted, separately-approved diff) independently of this packet**; this packet's own §11 byte-diff evidence is captured against whatever token state is live in `theme.css` at the time this packet's evidence is shot, and does not certify the DS-PR's correctness. Per §9's restated law, this packet's shell renders correctly whether or not C8-C has landed — the shell **must not silently depend on the retune** (C8-D completion condition). C8-C does not gate this packet's commissioning or merge; it only shares a byte-parity surface that both PRs must separately keep clean.

## 14 ROLLBACK

Template-scoped: revert the merge commit + re-render (the shared render lane's next covering run restores the previous body; `?v=` stamps re-hash). No `data/` writes, no schema changes, no engine paths — the revert story is one commit. The stocktable column retire is a removal in `stocktable.js` restored by the same revert. Non-US surfaces are untouched by construction, so rollback risk is confined to the US board.

---

## AMENDMENT 1 — C8 composition cycle (2026-08-19)

**Authority:** `research/reference_integrity/prophet-board-5514-r4-composition/verdict.yml` (verdict: REVISE; condition `C8-A-MP1-AMENDMENT`), executing the frozen rulings against this packet's law. Receipts: `.../reviews/product_regression.yml` (role `product_regression`), `.../reviews/visual_taste.yml` (role `visual_taste`). Nothing below re-adjudicates a ruling; every item transcribes one. C8-A is one of four sibling conditions (`C8-B-R42-REFERENCE-REPAIR` repairs the reference itself — out of this packet's scope; `C8-C-DS-PR-LANE` is the separate DS-PR at §13; `C8-D-COMPLETION` gates P-MP1-SHELL on C8-A + C8-B merging, and does not gate on C8-C).

Per-item mapping (finding id → verdict section → section(s) amended here):

| # | C8-A item | Finding id(s) | Verdict section | MP-1 section(s) amended |
|---|---|---|---|---|
| 1 | URL contract restated to query-string law, `#life=` compat | P-B4 | `product_regression.yml` finding B4 | §7 (URLs bullet) |
| 2 | Market-context module dispositions + error copy | V-B2 | `visual_taste.yml` finding B2 | §6 (5 module rows + disposition note), §10 (error copy) |
| 3 | §13 DS-PR collision (DA-002 retune) + §9 restated | P-B3 | `product_regression.yml` finding B3 | §9 (theme.css bullet), §13 (new collision entry) |
| 4 | Stance-projection ownership + b1 contract + macro wait-default parameter | P-B7; ruling `b1_actionability_axis` | `product_regression.yml` finding B7; `verdict.yml` rulings | §8 (new §8a), SPAWN GATES (G-D-1) |
| 5 | `.pv-mark`/`.mx-mark`/`.pv-cau` vocabulary | P-B5; ruling `pv_cau_classification` | `visual_taste.yml` finding B5; `verdict.yml` rulings | §5 (vocabulary resolution) |
| 6 | LENS bind-don't-port | P-K1 | `product_regression.yml` finding K1 | §5 (LENS obligation) |
| 7 | Forced states: watch-present-at-zero, error+loading, Free-tier boundary, N3 | P-K19, V-B4, P-K16, N3 | `product_regression.yml` K19; `visual_taste.yml` B4, N3; `product_regression.yml` K16 | §10 (watch present-at-zero, error copy), §11 (evidence bullets, N3 gate item) |
| 8a | G-D-1 re-measured MET | b1 receipt (`product_regression.yml` decisive_receipt) | `verdict.yml` ruling `b1_actionability_axis` | SPAWN GATES (G-D-1) |
| 8b | b8/Overtime prose corrected by citation | b8 receipt (B8) | `verdict.yml` ruling `b8_overtime_clock` | §4b (fn.2 on the Overtime row) |

**Self-check (every C8-A item maps to a visible diff hunk):** items 1–7 and 8a/8b above each name the exact MP-1 section(s) edited in this amendment; none is citation-only prose appended without a corresponding change to the section the finding is against. `git diff --stat origin/main -- research/migration_packets/MP-1-prophet-board.md` shows this single file as the entire diff.

**Not amended (explicitly out of C8-A's scope, confirmed against the verdict):** `research/P0_REFERENCE_EXPERIENCE_DESIGN_PACKET.md`, the R4/R5 packets, `mockups/refs/institutionalize/us_stocks/*` (reference repair is C8-B), any `templates/`/`.css`/`.js` file (C8-C is the DS-PR; nothing in C8-A ships code), and any ruling itself (`verdict.yml` is frozen; b1's Sol-veto routing is recorded, not resolved, above).

---

*Record (factory §3.7): mark DONE with the PR number here when merged; deviations/dissents append below this line.*
*Amendment 1 (above) is packet law as of 2026-08-19, not a deviation — it is bound by the same `A builder that believes this packet is wrong stops and escalates` rule as the rest of this file.*
