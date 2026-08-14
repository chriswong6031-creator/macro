# P0 Reference Experience Design Packet

**Program:** Operation Institutionalize, Handoff B deliverable 3 of 3
**Status:** Design packet for Sol approval, then implementation per §9. No production code rides this PR.
**Authority:** Reference architecture designed by the Opus product/UX director lane; adjudicated and amended by the Fable main loop; red-teamed by an independent Opus reviewer before ship.
**Companions:** `research/PRODUCT_EXPERIENCE_CENSUS_2026-08.md` (evidence), `research/MASTER_PRODUCT_INFORMATION_ARCHITECTURE_V1.md` (IA + decisions).
**Amended 2026-08-13** per the Prophet program ruling (PR #5504, `research/PROPHET_RULING_J9C_J10_LIFECYCLE_CELLS.md`): the six-cell stage enum this packet was drafted against is superseded by the ruled seven-cell `lifecycle_state` partition; §B is re-cut (Setups = plan rows; the candidate screener separates into Candidates / 候选); the four-dot rail and all user-facing "stage" vocabulary retire. Amendment record: §L. The §K red-team record is historical and unmodified — where it references the six-cell enum or `#stage=`, this amendment governs. The board migration packet is `research/migration_packets/MP-1-prophet-board.md`.
**How this is used:** each reference page below is the frozen contract for one implementation PR (`03` §7 migration-packet form; one reference page per PR until the pattern is stable). A builder may not redesign outside the packet without escalation.

---

## 0. System decisions binding all five pages

**No new token system, no new card system, no new header family.** Everything composes `theme.css` tokens, LENS tips (`data-tip-en/zh`), `.dtp`, `.mx-tier-*`, `.pvcard`, `_icons.html.j2`, and `lib/illus.py`.

- **Type:** adopt, do not invent — promote the 10-step ramp currently trapped in `body.page-macro` (inside `dashboard.html.j2`) into `theme.css` as the site ramp. `--font-ui` for words; `tabular-nums` on figures only, never on words. *(Caution for the implementer: theme.css edits have a four-way blast radius — template/site sync, hash re-stamp, and the line-sliced mockup harness — land the ramp promotion as its own reviewed change.)*
- **Palette:** direction on `--up/--down`-derived inks (zh flips); health on `--warn/--act/--ok`. **Lifecycle is encoded by weight, never by hue** — re-issued 2026-08-13 over the ruled seven cells (ruling §10.6): **Watch 观察 = dashed hairline** (signal fired, nothing committed) · **Ready 就绪 = half-filled** (plan armed, trigger not fired) · **Entered 入场 / Delivering 达标 = solid** (live commitment) · **Overtime 超时 = solid muted** (declared window expired, still open) · **Invalidated 失效 = hollow, struck rule** (thesis void) · **Resolved 已结 = neutral outline** (graded out; archive weight). The grammar encodes *commitment class*, not per-cell identity — the two solid cells are distinguished by label and count, which the partition law guarantees. The encoding is direction-neutral by construction: no `--up/--down` ink ever touches a lifecycle mark, so it survives the zh direction-flip unchanged; a lifecycle marker borrowing a category hue is a known contrast collision in this estate. **Violet is lock-only.** (Red-team correction: there is no `--prophet` token; the hue ships as `.mx-tier-gate--prophet{--mx-tier-accent:#7c5cff}` in `tier_preview.css:16` and today it means *locked*. It keeps that single meaning.) **The active/selected ladder cell keeps its own separate encoding — solid fill + heavier rule, never violet** — which is exactly why no *cell identity* may use the heavier rule: selection state and cell class must never collide.
- **Signature (one, spent deliberately): the count ladder.** A horizontal row of lifecycle cells — simultaneously the board's headline statistic and its filter control, echoed at detail scale as the dated lifecycle rail. **Partition law (re-cut to the ruling):** the cell set is the ruled `lifecycle_state` partition (ruling §6) — **Watch 观察 · Ready 就绪 · Entered 入场 · Delivering 达标 · Overtime 超时 · Invalidated 失效 · Resolved 已结** — exhaustive and disjoint at the declared unit of account (cells count **plan rows**; `watch` counts tickers with no open plan row); a hand-picked subset voids the invariant. **Two-total law (ruling §6, binding):** the six live cells (watch…invalidated) sum to `lifecycle_live_total`, and *that* is the page's headline — "N live setups today", printed once. `resolved` is deliberately outside the headline (a graded-out plan is record, not inventory — red-team #6 made structural); it renders as the ladder's terminal cell or an adjacent quoted count, both reading from the same `lifecycle_counts` block. The enforcement rule, restated precisely: *every integer on the page describing a quantity of setups is a `lifecycle_counts` value, one of the two published totals, or a computed difference of them* (locks and "+N more" links quote or derive, never recount). The risk taken — fusing the headline stat with the filter — is justified by exactly that enforcement property, and by the fact that a lifecycle is what distinguishes Prophet from a generic screener. ZH lexicon: **fixed by the ruling** (the seven two-character words above, native arc, shipped as paired EN/ZH constants in PR-0(c) — never re-minted downstream). Ladder geometry: at 390w the seven cells wrap to two rows (4+3), total pinned — never a horizontal scroll on a filter control (scroll hides active-filter state); explicit zh×390w acceptance check.

---

# A. TODAY — `start.html` (Archetype A)

**USER + JOB.** A returning subscriber before the US open (plus the anonymous "See it live" visitor). Job: *"What changed while I was away, and what deserves attention before the open?"*

**ABOVE-FOLD (1440×900).** `.dtp` session token + single page as-of (34px) → **Market state row** (one line per followed market: regime word + plain clause + link, 96px) → **Needs attention** (3–5 rows: name · what changed ≤14 words · stance verb · link — the primary answer, 240px) → **Prophet today** (count ladder + tier-capped preview cards, 300px). Exactly one primary CTA, tier-dependent: paid *Open the Prophet board* / Free *See all N setups* / anonymous *Create free account*.
**390w one swipe:** session token + the user's primary market line + Needs-attention rows 1–3.

**STRUCTURE (5 first-level sections):**

```
start.html
├─ [chrome] session token · one page as-of                            L1
├─ 1. MARKET STATE — row per market: word + clause + link             L1
│      (no charts, no gauge — the gauge lives on macro.html)
├─ 2. NEEDS ATTENTION — 3–5 ordered change rows + stance verbs        L1
│      per-row LENS "source · time · rule" · "See all N" → Monitor    L2
├─ 3. PROPHET TODAY — today's-changes slice + ≤3 .pvcard previews
│      + lock (see slice law below)                                   L1
├─ 4. YOUR WATCHLIST — registered: ≤5 change rows;
│      anonymous: Shape-C explanation + one-click start               L1
└─ 5. RISK & CALENDAR — plain-word conditions + next 3 events         L1/L2
```

Desktop column contract: §2 renders as the 2/3-width primary column with §4+§5 as a 1/3 rail beside it; §1 and §3 are full-width bands. Today is not a single equal-weight vertical stack.

**Needs-attention ordering law (red-team #7, `DNR:KILL-FUSED-COMPOSITE` compliance).** The ordering is a stated, non-scored precedence rule — never a composite: (1) Prophet lifecycle transitions (a plan row changing cell along the ruled funnel order) on names the user watches, (2) other watchlist triggers, (3) Prophet lifecycle transitions off-watchlist, (4) risk-condition changes — most recent first within each class, no numeric blending, no weights, no hidden inputs. Each row's LENS tip prints the rule verbatim: source class, timestamp, and which precedence slot it filled. If a scored ranker is ever wanted here, it goes through the PSI §3.1.2 display-composite law (printed legs, v0-equal weights, abstention, day-one grading) as its own adjudication — not this packet.

**Prophet-today slice law (red-team #5, re-cut to the ruling).** The module's three numbers (**new** — plan rows added to the book today · **entered** — rows whose trigger fired today · **resolved** — rows graded out today) are a *labelled slice of today's `lifecycle_state` transitions* — never a second count vocabulary, never cells re-counted. Invalidations surface through Needs-attention (precedence class 1/3), not as a fourth slice number. The module links to the board with the canonical headline in the link text ("Open the board — 118 live setups"), quoting `lifecycle_live_total`, not recounting.

**Anonymous primary market (red-team #17):** anonymous visitors have no saved state (`01` §3.1) — the primary-market row defaults to US, and to CN when the locale is zh; the chip strip covers the rest.

**COMPONENTS.** Reuse: `.dtp`, `.ms-*` verdict vocabulary compressed to a row (word + thesis clause only — not the meter), `.pvcard`, `.mx-tier-gate`, LENS, `_icons.html.j2`, `illus.py` card sparklines. **NEW (2):** `.ladder` (count ladder — total + 5 weight-encoded cells, cells are links/filters) and `.chg-row` (name · change clause · stance verb · chevron). Both compose existing tokens.

**STATES.** loading = skeleton rows at true geometry, no words; empty = full-weight sentence "Quiet tape — nothing crossed a line since Friday's close." (`.empty`+`.empty-why`); stale = `.dtp` behind-state + one line; error = "This read didn't load. The rest of the page is current." + Retry — never a bare `—`; dense = caps (5 changes / 3 cards) with counted "See all" links. **Loading ≠ empty is structural: loading has no sentence, empty has no skeleton.**

**ACCESS.** Anonymous: market state + risk/calendar full; Needs-attention top 1 + lock stating a real count; ladder totals honest + 1 card; watchlist as Shape-C explanation. Free: everything, 3 cards, real watchlist. Paid: + "since your last visit". Full change list and beyond-cap cards ship only in `premiumdata/`, never in anonymous HTML.

**RESPONSIVE (2 deliberate reductions).** (i) Market state → one row for the user's primary market + chip strip for the rest. (ii) Prophet today → ladder + one card + "See 2 more".

**ACCEPTANCE.**
1. At 1440×900 without scrolling, a cold reader names three things that changed and one thing to do.
2. Exactly one as-of stamp on the page.
3. Anonymous lock states a real count and names a plan; view-source contains zero locked rows.
4. Slow-3G load shows skeleton, never the empty sentence.
5. Forced-empty payload shows a market-facing why, never a pipeline sentence.
6. 390w first swipe = market state + 3 change rows; no horizontal page scroll.
7. zh: every Tier-1 string has a native ZH twin; no EN state names leak.
8. Both themes screenshotted; light lock teaser is ghosted (`saturate(.35)`, opacity ≤.5), not a blur smudge.

---

# B. PROPHET BOARD — `us_stocks.html` (Archetype B)

**USER + JOB.** A paying investor choosing what to work on today; secondarily the anonymous visitor judging whether the machine is real. Job: *"Which setups matter most right now, where in their lifecycle, and which am I allowed to act on today?"*

**ABOVE-FOLD (1440×900).** Page head (**Prophet — US** · one-line purpose · `.dtp` freshness · regime/posture chips) → **count ladder** (`118 live setups today` + Watch 4 · Ready 52 · Entered 57 · Delivering 2 · Overtime 1 · Invalidated 2 · **Resolved 16 as the terminal cell, visibly outside the headline sum** — the cell set is the ruled `lifecycle_state` partition, exhaustive at the declared unit) → sort-rule line + primary CTA → first card row + a slice of row two. **REPLACES** the live order (mega-cap tape → market strip → lanes → four screens → "Prophet Stock Signals") where the page named for the flagship put the flagship below four other modules.
**390w one swipe:** page head + ladder strip (two-row wrap, total pinned) + first card.

**STRUCTURE:**

```
us_stocks.html  (Prophet — US)
├─ 1. BOARD HEADER — purpose ≤14 words · COUNT LADDER (= filter) ·
│      sort rule in words · one .dtp + existing .pbs stamp            L1
│      methodology + lifecycle glossary → LENS / methodology.html     L2/L3
├─ 2. SETUPS (population: PLAN ROWS — the Prophet book,
│      site/prophet/index.json.plans) — one .pvcard per plan id ·
│      grid/table toggle · ONE contextual lock at the tier boundary   L1
│      "What changed today" strip (new/entered/resolved)              L2
├─ 3. CANDIDATES / 候选 (population: tonight's screener rows,
│      us_standouts) — triage shelves · ONE header total ·
│      no lifecycle vocabulary inside this section                    L1/L2
├─ 4. GROUPS — where money is rotating (SECTORS+THEMES) —
│      five stance lanes, unchanged idiom, ONE header total           L1
├─ 5. MARKET CONTEXT — breadth · regime · mega-cap tape · rates,
│      as tabs                                                        L2
└─ 6. EVIDENCE & RECORD — public proof · methodology · history links  L3
```

Everything else on the live page (Release Radar, Week ahead, Indexes, Turn Setups, Accumulation watch, Real fund moves, full breadth board) demotes into §5 tabs or to its own page: twelve first-level panels → six. (The count was five before the 2026-08-13 amendment; the sixth section is the ruled Candidates separation — ruling §10.4 forbids the screener merging into Setups, and a section is the smallest honest home that keeps its rows on the page.)

**THE COUNT CURE (the page's central ruling — re-cut 2026-08-13).** **Three populations, three nouns, one canonical total each, never mixed** (ruling §10.4 amends the original two): **Setups** (plan rows — the Prophet book; the ladder's live cells sum to the printed headline, `lifecycle_live_total`), **Candidates / 候选** (tonight's screener rows — one header total, printed once in its own section), and **Groups** (sectors+themes — one header total; lane counts are its decomposition). A Setups integer and a Candidates integer never render adjacent, never share a sentence, never sum; the two sections use disjoint nouns in both languages (a candidate is not a setup until a plan row exists). Every other setup integer on the page is a quote or a computed difference of `lifecycle_counts` values: overflow links are `+{cell−shown} more`; the "What changed today" strip (new/entered/resolved) is a labelled slice of today's lifecycle transitions; **the tier lock quotes the live total and names what it withholds** ("You're seeing 3 of 118 live setups — the rest are part of the live board"), and the headline never sells graded-out plans as inventory because `resolved` sits outside it *by construction* (the two-total law — red-team #6, now structural rather than copy discipline). Lifecycle is a **fact column** — one cell word + plain gloss, no blended confidence number (`DNR:KILL-FUSED-COMPOSITE`); the ⚡ trigger chip stays presentation-tier on a card whose verb remains the ruling stance (`DNR:KILL-PROPHET-POP-MERGE`).

**THE UNIT OF ACCOUNT (ruling §6, binding on rendering).** The board renders **one card per plan row, keyed by plan `id`** (`data-ticker` stays an attribute for the live-quote JS). A ticker with two commitments renders two cards — a resolved 07-13 episode and a live 08-05 plan on the same name are two separate tracked commitments, and one-card-per-row is the only rendering under which ladder counts, `data-life` filters, and visible cards agree exactly (the chip-count law). **Visual treatment of multi-episode names (defined here, not left to the builder):** (i) same-ticker cards each stand alone in the grid under the board's global sort — never stacked, merged, or grouped into a carousel; (ii) every card of a multi-row name carries a small neutral-ink **episode chip** — dated ordinal, EN "Episode 2 · opened Aug 5" / ZH "第 2 轮 · 8月5日启动" (exact microcopy settles at the mockup gate; the constraints — neutral ink, no hue, dated, present only when the ticker has >1 rows on the board — are binding); (iii) a resolved-cell card renders at the resolved weight (neutral outline, §0) and links to the newer live episode when one exists ("Newer plan on this name → / 该股最新计划 →"); (iv) the episode chip is metadata, never a count — it appears in no total. Ticker-keyed surfaces elsewhere (landing showcase, dossier chip, stock-detail chip) use the ruling's per-ticker projection (newest open row → else watch → else resolved), which is single-valued and test-pinned in PR-0(c) — the board is the only surface that shows the row-granular truth.

**Demotion landing table (red-team #13) — every current first-level panel gets a named destination; nothing vanishes:**

| Current us_stocks panel | Destination |
|---|---|
| Mega-cap tape | §5 Market context → *Indexes & mega-caps* tab |
| Market State strip | §1 regime/posture chips (compressed) + macro.html |
| Indexes board | §5 → *Indexes & mega-caps* tab |
| Breadth board | §5 → *Breadth* tab |
| Turn Setups | §2's "What changed today" strip + the Turn Watch surface (Prophet program's deck — link, not an embedded panel) |
| Accumulation watch | §5 → *Flow* tab (with darkpool link-out) |
| Real fund moves | link-out to `smart_money.html` from the *Flow* tab |
| Release Radar / Week ahead | Today §5 calendar + `news.html`; link from §5 |
| Track record teaser | §6 Evidence & record |
| Rates check | §5 → *Rates* tab |
| Sector Intelligence teaser | §4 Groups header link |
| "Prophet Stock Signals" card grid (built from `_su.buy` candidates) | **RETAINED as §2 Setups, population re-sourced to the plan book** — one card per plan row (ruling §10.4; the migration's structural act) |
| us-standouts screener (triage shelves, lane headings) | **§3 Candidates / 候选** — same shelves, own printed-once total; any shelf heading colliding with a lifecycle cell word relabels within its shipped triage lexicon (one-referent-per-page law, ruling §10.4) |
| US stock table "Stage / 阶段" column + its count chips | **RETIRED** (ruling §7/§10.5 — the naming law's directest violation; its `RIPENING` chip is producer-less). The table's other columns keep; no replacement column |
| Four-dot price-stage rail on cards (`_STAGE_BY_LANE`, int `stage`) | **RETIRED in the same PR that lands the ladder** (ruling §10.1 — two lifecycle vocabularies never co-render); the price read demotes to the lane mark chip + LENS (§G.1) |

Mobile: §5 is link-only, meaning each tab's content is reachable at its destination page in one tap — demoted, not deleted.

**COMPONENTS.** Reuse: `.pvcard` + `pv_css()` (see the card-lifecycle ruling, §G.1); the five-lane `.actcol/.acth` idiom untouched; `.dtp`; `.mx-tier-gate--prophet`; LENS; `_icons.html.j2`; `illus.py`; `.pbs` stamp; `.st-view-toggle`. **NEW:** `.mx-ladder` in control form — cells carry `aria-pressed`, the active cell uses the selection encoding (solid fill + heavier rule, never violet), cell identity uses the §0 weight grammar. **Field contract (supersedes the red-team #2 correction's minting language):** the ladder consumes **`lifecycle_state`** — the derived display-tier projection specified by the ruling and built in PR-0(c) (`scripts/build_prophet.py`; seven cell keys; per-row values plus the `lifecycle_counts` block; EN/ZH paired constants) — rendered to a **`data-life`** attribute on cards; the ladder filters on `data-life` and the URL fragment is **`#life=<cell>`**. The legacy `data-stage` triage attribute renames to **`data-triage`** in this same migration PR (machine name only — its shipped user-facing labels never said "stage"; fossilized snapshots are never rewritten, ruling §8). **NEW:** `.pv-mark` — the lane mark chip: one static neutral-ink chip per card at most ("Bottoming entry / 底部入场" · "Continuation entry / 顺势入场" — **no recovery chip**, its producer is structurally empty and a producer-less chip is the exact defect the rail died of), LENS tip carrying the lane fact + gloss. It is a *mark*, not a device: no sequence, no fill states, no ordering among chips, nothing that reads as progress (ruling §5).

**STATES.** loading = card skeletons at grid geometry, ladder shows dashes not zeros; empty = "No live setups today — the board refreshes after the next close." / 「今日暂无在场计划——下个收盘后刷新。」 with an all-zero ladder (the shape still teaches the page); **watch-cell key absence** = on a payload with no `early_turn_watch` key the watch cell renders a disclosed absence — "Watch tier publishes from the next nightly." / 「观察档自下一次夜间构建起发布。」 — never a silent 0 (ruling §6 fn.1: key-absence and zero are different facts); stale = existing `.nb-stale-note`, one stamp only; error = "The board didn't load. Candidates, Groups and Market context below are current." + Retry; dense = grid view caps at 40 cards with `+{cell−shown} more` quoted per the count law, **table view renders every row of the active filter** — the table is the surface where rendered rows equal cell counts exactly.

**ACCESS.** Ladder + totals honest for everyone. Cards: anonymous 1 / Free 3 per list/day / paid full (`01` §5, `04` §8). Card depth ladders from ticker + lifecycle + why + freshness → +zone/edge/⚠ → +complete plan. Filters visibly inert below paid with one line saying why. Withheld rows live in `premiumdata/us_stocks.json` only. Max two locks on the page (Setups, Groups — the Candidates section never grows a third).

**RESPONSIVE.** (i) Five lanes → a segmented **stance selector** showing one lane at a time (lane names are stances, so a selector is honest). (ii) Market context is link-only on mobile. (iii) Candidates collapses to its header total + counted shelf chips, rows one tap behind — the total stays printed even collapsed. (iv) The ladder wraps to two rows (4+3) at 390w per §0 — never horizontal scroll.

**ACCEPTANCE (re-issued 2026-08-13; each testable by a stranger).**
1. **Count law, two totals:** every integer on the page describing a quantity of setups is a `lifecycle_counts` value, one of the two published totals, or a computed difference of them. The six live cells sum to the printed headline and the headline equals the payload's `lifecycle_live_total`; `resolved` renders outside the headline sum; the lock's quoted numbers reconcile to the same block.
2. **Chip-count law at the unit of account:** the board renders one card per plan row, keyed by plan `id`. For any active ladder filter, rendered cards plus the quoted `+N more` difference equal that cell's count exactly; in table view, rendered rows equal it with no remainder. A ticker with two plan rows renders two cards, each episode-chipped, never merged.
3. Ladder cell click filters in place; no second board; URL gains `#life=<cell>` (e.g. `#life=entered`); the string `#stage=` appears nowhere in links, JS, or history.
4. **Three populations, no leakage:** Setups, Candidates / 候选, and Groups each print exactly one canonical total; every Candidates shelf count sums to the Candidates total; no Candidates integer renders adjacent to, in a sentence with, or summed into a Setups integer; the seven lifecycle cell words (EN or ZH) appear nowhere inside the Candidates section.
5. **Stage retirement:** the word "stage" / "阶段" appears nowhere user-facing on the page — labels, column headers, count chips, aria attributes, URL fragments, LENS copy, either language. The stocktable's Stage column and its chips are gone.
6. **Rail retirement:** the four-dot rail renders nowhere on the page; no ordered sequence of lane chips reads as progress; each card carries at most one static `.pv-mark` lane chip; no "recovery" chip exists.
7. No blended confidence number; lifecycle appears as a cell word + plain gloss.
8. Every lane's / shelf's "+N more" equals its header count minus rendered rows.
9. Anonymous view-source: exactly one card's data, zero locked rows.
10. A ⚡ card's verb still reads as its ruling stance.
11. 390w: seven ladder cells visible in a two-row wrap with the total pinned, no horizontal page scroll; one Groups lane visible via selector; Candidates collapsed but its total printed.
12. Light + dark + zh: violet never lands on a data value; direction inks flip under zh; lifecycle weight encoding identical under zh (direction-neutral). A payload with the `early_turn_watch` key absent renders the watch cell's disclosed-absence line, never a silent 0.

---

# C. PROPHET DETAIL — new surface (Archetype C)

**USER + JOB.** An investor who clicked one name off the board or an alert. Job: *"What is this setup, has it changed, is today a good entry, and what would take it off the board?"*

**URL SCHEME (reconciled with the engine's identity unit — red-team #12).** Canonical **`/prophet/<TICKER>.html`** — stable per name, statically baked, deep-linkable from cards, alerts, chat, email. The IA's Phase N2 is amended to this scheme (it previously said `/prophet/<id>`; the two docs now agree). The engine's canonical unit is the *episode* (`site/prophet/plans/<ID>.json`, `data/prophet/ledger.jsonl`) — the ticker page is a **resolver view**: a new builder (`scripts/build_prophet_pages.py`, PR-4) maps ticker → current plan ID from the board index and bakes one page per name. **Resolver rule (ruling §6, test-pinned in PR-0(c)):** a ticker-keyed page shows the cell of the newest **open** plan row (by `recorded_at`, tie-break `id`); else `watch` if the ticker is in the watch set; else `resolved` — a live fire outranks a finished episode. Other episodes on the name list under past appearances, never merged into the header. Historical episodes: `?as-of=` is client-fetch over the existing per-plan JSON (a statically served file cannot vary by query string), rendered under a "read as of" band. Rejected: per-episode URLs as canonical (setups recur on a name; yesterday's link must resolve to today's read). Namespace: `/prophet/<TICKER>.html` files coexist with the existing `/prophet/plans/` + `showcase.json` (no collision; stated so Handoff A's access lists treat them separately). **Render budget:** pages are baked only for names on the current board plus the delayed-resolved showcase set (≈50–120 pages/night, SSR illus charts only) — budget line ≤2 min of the nightly render; the builder logs its page count and duration.

**ABOVE-FOLD (1440×900).** **Decision header** (ticker + name · stance verb large · lifecycle cell word + gloss · freshness · completeness chip) → **lifecycle rail** (dated stops for the transitions this episode has actually made along the ruled funnel — watch → ready → entered → …, current stop lit; never a fixed-length track with unlit future promises) → **why now** (2 plain sentences + the 3 evidence chips that moved) → top of the **two-column quality block**. Primary CTA: *Add to watchlist* / anonymous *Create free account to track this*.
**390w one swipe:** header + rail + why-now.

**STRUCTURE:**

```
/prophet/<TICKER>.html
├─ 1. DECISION HEADER — identity · stance verb · lifecycle + gloss ·
│      one freshness stamp · completeness chip                        L1
│      links: company dossier · board · chart                         L2
├─ 2. WHY NOW & WHAT CHANGED — LIFECYCLE RAIL (dated) ·
│      two plain sentences · ≤3 what-changed rows                     L1/L2
├─ 3. QUALITY — two columns, never blended:
│      SIGNAL quality + word label | ENTRY quality + word label ·
│      the honest cross-case line ("Strong setup, poor entry —
│      wait for a pullback") · receipts behind LENS                   L1/L2
├─ 4. RISK & WHAT WE'RE WATCHING — risk reference (stop distance,
│      sizing note) · projection window in plain words ("If X for
│      two closes, we'd move it to Stand aside") · one footnote:
│      "Windows, not certainties — re-drawn nightly"                  L1
└─ 5. EVIDENCE & RECORD — evidence groups behind disclosure ·
       methodology · lifecycle definitions · past appearances + outcomes L3
```

**Language law (#3821):** *falsifier*, *refuted*, *证伪* appear nowhere, either language. §4 is "What we're watching / 我们在盯什么". Full verdicts stay on the Calibration Lab. Signal quality and entry quality are tracked and displayed separately — never summed, averaged, or blended (`04` §5 + `DNR:KILL-FUSED-COMPOSITE`); the `.qual2` layout has no total row by construction.

**COMPONENTS.** Reuse: `_prophet_card.html.j2` `--pv-*` hue tokens for the stance verb; `.dtp`; LENS for every receipt; `.pv-cau-pop` caution anatomy; `illus.py` SSR chart with the existing buy-zone band (never Plotly); `_icons.html.j2`; `.mx-tier-gate--prophet`; `_stock_decision.css.j2` header idiom as base. **NEW (2):** `.rail` (dated lifecycle rail, weight-encoded — the signature) and `.qual2` (two-column quality block, no total row).

**STATES.** loading = header+rail skeleton, verb slot is a grey pill never a default verb; empty/not-covered = "This name isn't on the Prophet board today. Here's what it looked like when it last was →" — **never "NOT IN LIBRARY"**; stale = current stop dims + "Last confirmed <date> — tonight's pass hasn't published."; error = header from cache, stance verb withheld rather than guessed; dense = cautions scroll in-popover, evidence stays collapsed. Completeness chip vocabulary (`04` §4): *Complete / Partial — N checks had no data today / Delayed — prices as of X / Rebuilt from history / Provisional — settles tonight*.

**ACCESS (rewritten after red-team #1 — the original "header+rail+why-now public" rule would have let an anonymous crawl of `/prophet/` reconstruct the complete current live board that the board page itself withholds, violating `01` §5 and `04` §7).**

- **Names on the current live board — anonymous:** Shape-B lock shell only: identity, page purpose, methodology links, the board's ladder totals (`04` §8 grants totals + lifecycle distribution), and the unified lock ("This name is on today's board. The lifecycle read, thesis, and plan are part of the live board.") — **no lifecycle state, no stance verb, no rail, no why-now.** The one-preview-card-per-board allowance (`01` §5) is spent on the board page, not multiplied across detail pages. Live-board detail pages carry `noindex` while the name is on the board.
- **Names on the current board — Free:** lifecycle + rail + why-now (Free's three-cards/day convention governs how many *full* reads a Free user opens per day; the census's sibling Handoff A owns the enforcement mechanics).
- **Delayed-resolved episodes (the public-proof set, `04` §7):** fully public and indexable — timestamped origination, the episode's dated lifecycle path, outcome, wins and losses. This is where the SEO value of `/prophet/` lives, honestly.
- **Quality/risk depth (all tiers):** quality shows word labels below paid; exact entry/stop/target numbers are the paid payload, server-enforced, absent from every non-paid page source.

**RESPONSIVE.** (i) Quality columns stack as two divided, re-labelled blocks (bare stacking would visually re-blend them). (ii) Rail collapses to current + previous + "history".

**ACCEPTANCE.**
1. Signed-in (Free+): `/prophet/NVDA.html` loads directly with no board visit; stance + lifecycle above the fold. Anonymous on a live-board name: the lock shell renders with no lifecycle/verb/rail, and the page carries `noindex`.
2. **Anonymous crawl test:** a crawl of `/prophet/` + `/stocks/` cannot reconstruct today's board — no more than one current name exposes a lifecycle state or stance to an anonymous session.
3. No occurrence of falsifier/refuted/证伪 in either language.
3. Signal and entry quality separately labelled; nothing sums or averages them.
4. A strong-signal/poor-entry name renders the honest cross-sentence.
5. Anonymous view-source contains no exact stop/target numbers; the lock names the plan.
6. Completeness chip uses one of the five sanctioned phrases.
7. One freshness stamp.
8. 390w: quality blocks divided and re-labelled, not merely stacked.

---

# D. PLANS — `plans.html` (Archetype G)

**USER + JOB.** A prospect who has seen one real output and is deciding whether to pay. Job: *"Which plan is for me, what exactly do I get, and what happens when I click?"*

**ABOVE-FOLD (1440×900).** Headline ≤10 words + one-sentence value + **the plan cards** (the archetype's primary question is answered by the cards, so the cards are above the fold; the hero compresses to two lines — replaces the live full-height hero). One primary-weight CTA (the primary card's button).
**390w one swipe:** headline + Free card top + the paid card's price.

**THE TWO VARIANTS (Chairman decision `01` §13, open):**

- **Variant (i) — Free + Essential monthly + Founding Pro annual.** Three cards, **global annual/monthly toggle removed**, one price per card (Free $0 no card · Essential $X/mo billed monthly · **Founding Pro $75/mo billed $900 yearly**, primary weight). Removing the toggle is what structurally kills the live "$900 = $900" collision: Essential-annual is never rendered, so it cannot be dominated on-screen.
- **Variant (ii) — Free + Founding Pro only.** Two cards, two-column table, no mobile selector needed; monthly demand handled by one FAQ row.

**Design recommendation (not a ruling): variant (ii)** — the only variant where the table needs no selector, mobile needs no reduction, and every visible option is undominated. Essential stays a backend entitlement and future tier per `01` §4.

**STRUCTURE:**

```
plans.html
├─ 1. VALUE — headline + one sentence + "what Free includes" line     L1
├─ 2. PLAN DECISION — cards: one price · one billing line ·
│      ONE savings/entitlement line naming its comparison ·
│      CTA + what-happens-next                                        L1
├─ 3. FEATURE COMPARISON — one table generated from the same
│      config entries as the card bullets (bullet ⇄ row, enforced) ·
│      per-row ⓘ plain description                                    L2
├─ 4. PROOF — 3 resolved public-proof rows + track-record link        L2
└─ 5. FAQ & RISK REVERSAL — cancel, refund, renewal                   L2
```

**Cures, each naming what it replaces.** *Savings math:* one savings statement per card, computed from `config/plans.yml`, naming its comparison — replaces the live triple that states three different savings for one price. *Scarcity:* the static `1,726 of 2,000` counter is replaced by the entitlement fact ("Founding rate stays locked for as long as you stay subscribed"); a counter returns only if live from billing authority. *Duplication:* the table and cards generate from one config source; a bullet with no table row is a build error.

**COMPONENTS.** Reuse: `_public_nav` family + `landing.css` card idiom — migrating `landing.css`'s competing `:root` token set onto `theme.css` tokens during this build (census §3.1); existing `.tier`/`.matrix-card`/`.mx-plan-tabs`; `_icons.html.j2` check/dash marks (never emoji). **NEW (1):** `.plan-claim` — the single savings/entitlement line slot; the template permits exactly one per card.

**STATES.** Prices are server-rendered from config (no price loading state; only the CTA has pending). A plans page with no plans **fails the build**, never renders. Offer-expired swaps the Founding card to standard Pro pricing with a plain line. Checkout error: "We couldn't start checkout. Your card was not charged." + retry + support. Table scrolls inside its own `overflow-x` container.

**ACCESS.** Anonymous: everything including exact prices (acquisition surface, Shape A). Free: "Your current plan" marker + what-you'd-gain marker. Paid: current plan marked, CTA becomes *Manage plan* → the routed account page; no upsell wall for subscribers. Every claim maps to a live entitlement flag (`01` §7); a claim with no flag is a defect.

**RESPONSIVE.** (i) *(variant i)* table always renders two columns — Free + the selected plan — with a labelled segmented selector (replaces the live mobile table that hides Free and Pro entirely). (ii) The recommended plan is first on mobile, not middle.

**ACCEPTANCE.**
1. No two visible plans share the same effective annual price.
2. Each card shows exactly one savings/entitlement claim, naming its comparison.
3. Every card bullet ⇄ table row ⇄ config key.
4. No scarcity number unless it changes between loads on different days.
5. 390w: comparison shows two columns; selector states the current plan in words.
6. Anonymous/Free/paid each render a correct current-plan marker.
7. EN and ZH prices identical; ZH copy native, not an English-shaped calque.
8. Both themes; the primary card's emphasis survives light mode (ring, not glow).

---

# E. COMPANY DOSSIER — `stocks/<TICKER>.html` + `stock.html` repair (Archetype C)

**USER + JOB.** An investor evaluating a company — from search, the board, chat, or the Terminal frame. Job: *"What's the current read, what changed, and what would change my mind?"*

**`stock.html` REPAIR RULING (route decision — Sol sign-off, §10).** `stock.html` today is a universal client-rendered shell that throws a render error for every ticker, has no per-ticker URL, and answers the board's #1 pick with "NOT IN LIBRARY". Its job is already served by two URL-bearing surfaces: the dossier and the Prophet detail. **Retire it as a destination; make it a resolver** — `stock.html?t=NVDA` → redirect to `stocks/NVDA.html`; bare `stock.html` → the ticker directory with search. Any content that genuinely lives only there moves into the dossier first. **Standing rule established:** *a page reached from a card may never deny the card's subject* — thin coverage renders what exists plus a market-facing line, never a library-membership error.

**ABOVE-FOLD (1440×900).** **Decision header** (identity · thesis in one sentence · lifecycle word · stance verb · freshness) → **Prophet chip** → **What changed** (≤3 dated rows) → evidence tab bar + first tab's top rows. CTA: *Add to watchlist*. **Prophet-chip tier rule (red-team #1):** for signed-in users the chip shows live membership via the per-ticker projection ("On the Prophet board — Entered since Aug 6 →" / 「已上先知榜——8月6日入场 →」); for anonymous sessions it shows membership only for names in the delayed-resolved public set, and for current-board names renders the neutral form "Prophet coverage available →" — otherwise the free dossier estate enumerates the live board.

**STRUCTURE:**

```
stocks/<TICKER>.html
├─ 1. DECISION HEADER — thesis · lifecycle · stance · freshness       L1
│      Prophet chip → /prophet/<TICKER>.html (presentation tier)      L1
├─ 2. WHAT CHANGED — ≤3 dated rows                                    L1
├─ 3. EVIDENCE GROUPS — tabs are tasks, not components:
│      Price & flow | Fundamentals | Filings & events | Peers         L2
│      full tables + per-metric LENS receipts                         L3
├─ 4. RISK & CATALYSTS — plain-word risks + next dated catalysts      L2
└─ 5. PROVENANCE & HISTORY — sources, per-group as-of, past reads     L3
```

**Cures.** Tier-3-at-Tier-1 receipts (`§7 take marker · display-only · W6-C`, `n=6 · cohort n=26`) are deleted from visible text and re-homed in LENS tips as translated receipts ("6 past cases in this group; 26 across the sector"). **Prophet boundary:** the dossier never renders the plan; the Prophet page never renders the fundamentals; the chip carries no merged score (`DNR:KILL-PROPHET-POP-MERGE`).

**COMPONENTS.** Reuse: `_stock_decision.css.j2` + `_decision_card.html.j2` header base; `.dtp` per-group freshness; LENS; `illus.py`; `_icons.html.j2`; `.mx-tier-gate` on paid groups; the Terminal-frame CSP contract (header must survive at frame width). **NEW (1):** `.tabset` — evidence tabs; invariant: each tab is a task name, tab state lives in the URL hash.

**STATES.** loading = instant static header + skeleton tab bodies; empty per group, market-facing ("No filings in the last 90 days." / "Not covered — we don't carry options data for this listing."); stale = per-group `.dtp` age + one page-level oldest-group line; error = the failing tab says so and names what still works, header never blanks; dense = in-container scroll, peers cap 8.

**ACCESS.** Anonymous: full company facts — **this is the free SEO estate; do not gate the shell** (flagged so Handoff A's access waves don't sweep it in). Gate only premium groups' payloads. Free: + watchlist and change summaries. Paid: + premium groups and the full Prophet plan inline.

**RESPONSIVE.** (i) Tabs become a horizontally scrolled strip, active tab pinned left — not an accordion (an accordion loses the parallel-tasks reading). (ii) Change-row source chips move into each row's LENS tip.

**ACCEPTANCE.**
1. `stock.html?t=NVDA` lands on `stocks/NVDA.html`; bare `stock.html` lands on the directory; neither throws.
2. The board's #1 pick resolves to a dossier that renders content — no membership error anywhere.
3. No Tier-3 receipt string (`§`, `W6-C`, bare `n=`) in visible text; all inside `data-tip-*`.
4. The Prophet chip links out and shows no score.
5. Each evidence group has its own as-of; one page summary stamp.
6. Deep-link `#filings` opens that tab.
7. Inside the Terminal frame at 900px the decision header is complete and unclipped.
8. Anonymous: facts render; premium payloads 403 and their locks name a plan.

---

# F. Cross-cutting components (prerequisites for all five pages)

### F.1 The unified contextual-lock component — `.mx-tier-gate` extended, not replaced

Mandatory ordered slot contract (a lock missing any slot fails review):

| Slot | Class | Content law |
|---|---|---|
| 1 | `.mx-tier-eyebrow` | what you see now, with a real count quoting the canonical block: "You're seeing 3 of 118 live setups" |
| 2 | `.mx-tier-copy b` | what is locked, ≤8 words |
| 3 | `.mx-tier-copy small` | why it matters *for this task*, ≤20 words, written per surface |
| 4 | `.mx-tier-plan` *(new slot)* | which plan, with price: "Included with Pro — $75/mo billed yearly" |
| 5 | `.mx-tier-primary` + `.mx-tier-signin` | CTA + the existing-member path |

Rules: one lock per meaningful task, max two per page, never above the free content it describes. Seeded from the two working artifacts: the us_stocks teaser and the `.obm-sheet` tier ladder's three-plain-benefits discipline. **Ships with:** the light-mode ghost rule promoted out of `body.page-stocks` scope into `tier_preview.css` unscoped (`blur(5px) saturate(.35) opacity ~.46`), so every locked surface inherits the ghost instead of a dirty smudge on white.

### F.2 Product-nav auth/pricing presence rule

**Every product page's header carries a plans link and an auth control** — inside the existing right-hand group of `templates/_site_nav.html.j2`; no third header family, no local geometry change. Anonymous: … · **Plans** · **Sign in** · Terminal. Free: … · **Plans** · account chip (initial + tier word) · Terminal. Paid: Plans moves inside the account menu. The account chip is the single entry to the routed `/account` page the IA calls for. Replaces the current state where product pages offer a conversion-ready reader no path to pay.

### F.3 The empty-state component

`.empty` + **mandatory** `.empty-why` (adopting Terminal's `.fin-empty`/`.fin-empty-why` "never a bare No data" law). Five sanctioned causes with fixed bilingual copy — *market closed / no qualifying rows today / source unavailable / not covered / still building* — market-facing vocabulary only. Replaces ~82 per-page empty-state variants and, by name, "It appears here after the first nightly run."

### F.4 The 404 page

None exists today; a missing URL serves an empty body to the user. **Red-team #4 correction on mechanism:** the main site's Caddy `handle_errors` block is **active and deliberate** (`app/deploy/Caddyfile:443`) — its contract is "a missing/erroring page surfaces as its real status code" and, for protected assets, fail-closed JSON that must **never** be substituted with a static file (`tests/test_regwall_json_gate.py`); the commented-out rewrites are other hosts' press-cutover blocks. The 404 page therefore ships as **a 404-status, HTML-request-only branch added inside the existing `handle_errors` block**, leaving `@reg_asset_err` and the JSON contract untouched, plus a test that a gated-asset error still returns the JSON 503 and a test that an HTML 404 response carries the page body (still with status 404).

Page spec: `_public_nav` family, both themes, bilingual; four blocks — plain statement ("That page isn't here."), the honest likely cause ("Some pages are generated per ticker, per sector, and per basket — if you typed a ticker, try the search."), the nav's search field focused, three routes back (**Today · Prophet board · Plans**). No "Oops", no mascot.

---

# G. Design-review record (adjudicated tensions)

1. **One lifecycle vocabulary per card (red-team #3 supersedes the first-draft resolution). RESOLVED 2026-08-13 — concurrence GRANTED (PR #5504, ruling §10), with a refinement this packet adopts:** the four-dot rail **retires entirely rather than being relabelled** — the ruling's §1.2 finding is that `lane` is an entry-door classification, not a progression, so *any* relabel would still be a progress bar over a category (two of whose four steps are structurally unreachable). What replaces it: the **lifecycle cell word as a fact column** on cards (board scale) and the **dated lifecycle rail** (detail scale, §C — dated actual transitions, never a fixed track); the price/entry read demotes to the static `.pv-mark` lane chip + LENS receipt (§B COMPONENTS; no recovery chip). Binding conditions carried from the ruling: **same-PR retire** (a surface gaining ladder or lifecycle labels retires the old rail in that same PR — 就绪 is reused by the new lexicon, so a split rollout would render one word with two meanings); **US-scope with a parameter** (`pv_card` grows a lifecycle variant behind a parameter; hk/china/canada/intl keep the legacy rail until their program lanes adopt the cell set). The one-vocabulary-per-card rule stands.
2. **Count-bearing devices on one page** (stance lanes vs lifecycle cells, now plus the Candidates shelves). Resolved by different nouns (Groups vs Setups vs Candidates / 候选), different forms (columns-with-icons vs counted hairline ladder vs triage shelves under one header total), and non-adjacency — plus the one-referent-per-page word law (a lifecycle cell word appears only as lifecycle vocabulary; a colliding shelf heading relabels). **This is the packet's most fragile decision — the first thing the implementation reviewer must check in a rendered mockup.**
3. **Dossier shell stays free** — gating it would be a traffic decision disguised as a paywall decision (flagged to Handoff A).
4. **One as-of per panel:** the count ladder must not add a second stamp beside `.pbs` — an easy implementer regression, now an acceptance check.
5. **Hover-demotion boundary** (census §5.3 ruling, ratified here): demotion is for mechanics, never for a caveat that changes how the headline number should be read — the macro dial-cap caveat moves into the panel.
6. **Anti-sameness contract (red-team #15).** Each archetype keeps one identity device that the others may not borrow: A = the two-column command layout with `.chg-row` stance rows; B = the count ladder; C = the dated lifecycle rail as the hero's second line; D = single-claim plan cards; E = the thesis-first decision header + task tabset. The mockup gate is where rhythm and column contracts are judged as designs, not asserted in prose.

---

# H. Escalation ruling (model routing for implementation)

Adjudicated with the Opus director's recommendation: **no blanket Fable escalation.** All five reference pages are structural work over ratified idioms — the draft-and-review test passes; Opus `builder` + independent review lands them. Two narrow exceptions put to the gate:

- **Prophet detail hero** (decision header + lifecycle rail as one composed moment) — *if* Sol designates this the launch's marketing-grade signature surface, its hero is taste-as-deliverable → main loop or `FABLE-WHY: creative:` via the orchestrator gate.
- **Landing hero/proof belt** (outside this packet's five pages; census §5.3 tension 2): replacing mock-ups with one live dated product output is a signature moment → same gate when commissioned.

---

# I. Execution handoff — implementation PRs

Per `03` §11 (one reference page per PR until the pattern is stable) and the model-routing law (Opus builds; design choices frozen here). Red-team #9/#10/#11 restructured this section: a foundations PR now owns every shared primitive, and **no builder is spawned before the mockup gate**.

**MOCKUP GATE (blocking, spawn-handoff law).** Before any page PR below is commissioned, the commissioning session produces rendered mockups of that page (light + dark + zh, desktop + 390w) and commits them under `mockups/refs/institutionalize/<page>/`. This packet is the *structural* contract; the mockups are the *visual* contract; builders receive both — never prose alone. The first mockup check for the board is tension G.2 (stance lanes vs lifecycle ladder vs Candidates shelves on one page — three count-bearing devices, three nouns, no visual merge).

**PR-0 — Foundations (shared primitives + type ramp).**
Scope: (a) promote the `--fs-*` ramp from `dashboard.html.j2:1641` (`body.page-macro` block) into `theme.css` — extraction boundary is `--fs-*` **only** (the block's page-scoped surface-token overrides stay page-scoped); delete/reconcile the shadowing page-local `--fs-*` declarations (`seo_base.html.j2`, `leader_radar.html.j2`, `intraday_flow.html.j2`, and any others a grep finds) in the same PR; name the governed body classes (note: the Prophet board is `body.page-stocks`, which inherits only via `:root`). (b) `.ladder`, `.chg-row`, `.empty`+`.empty-why` primitives in `theme.css` so both `build_site.py` and `build_vector.py` templates can consume them. (c) **Superseded by the ruling's §9 spec, which is the binding contract:** `lifecycle_state` emitted per plan row as a **derived display-tier projection** (the ruling's §6 precedence order verbatim; unknown-phase arm → `ready` + a `::warning` line, bare `print(..., flush=True)` at line start) — no new enum is minted; `early_turn_watch` added to the intake exporter's whitelist (sourcing the bridge's `list[str]`, never `basket_score`'s same-named `list[dict]`); the `lifecycle_counts` block + `lifecycle_live_total` + `lifecycle_grand_total` on the index (optional-fields path + schema version bump + manifest regen); the EN/ZH lexicon as paired constants (ruling §6 table verbatim, all-or-nothing); `STAGE_CONFIRMING`/`STAGE_CONFIRMED` deleted; the two stale domain comments healed; the ruling's six test families (partition + totals mutation-checked, no-dead-cell, watch key-absence vs zero, lexicon pairing, per-ticker projection single-valued). Display-tier per the epistemics law — no gauntlet needed for a derived fact column. **The field ships dark: no template/rail change, no `data-stage` rename, no lane change rides PR-0** — surfaces adopt at migration (PR-2 / MP-1). (d) F.1 lock-slot extension + light-ghost promotion in `tier_preview.css`.
Owner: Opus `builder`; independent Opus `reviewer`. **Caution:** theme.css edits have the known four-way blast radius (template/site sync → hash → stamps → line-sliced mockup harness) — this PR is deliberately small and reviewed alone.
Files: `templates/theme.css`, `templates/dashboard.html.j2` (ramp extraction only), the shadowing templates above, `templates/tier_preview.css`, `scripts/build_prophet.py`, `engine/us_early_turn.py` (dead-constant deletion), `engine/grade_us_board.py` + `templates/_prophet_card.html.j2` (comment heals only, non-rendering), tests (ramp presence, lifecycle-field contract per ruling §9, empty-why lint seed, ghost rule).
Collision risks: Handoff A access waves (`tier_preview.css`); the Prophet program lane (`build_prophet.py` — coordinate; the field is additive display-tier).

**PR-1 — Funnel enablement (chrome + wayfinding).**
Scope: F.2 nav auth/pricing right-rail states; F.4 404 page **via a 404-only, HTML-only branch inside the existing `handle_errors` block at `Caddyfile:443`** — `@reg_asset_err` and the fail-closed JSON contract untouched (red-team #4).
Owner: Opus `builder`; independent Opus `reviewer`.
Files: `templates/_site_nav.html.j2`, `templates/navigation-refresh.css` (right-rail states only), new `templates/404.html` (+ builder registration + site copy pairing), `app/deploy/Caddyfile` (the one branch), tests (nav-state render; 404 HTML body with status 404; gated-asset error still returns JSON 503).
Collision risks: open nav PRs; `nav_market.js` untouched (immutable-list caution).
Rollback: additive; revert commit.

**PR-2 — Prophet board reference (`us_stocks.html`, packet §B as amended). Migration packet: `research/migration_packets/MP-1-prophet-board.md` (binding; authored 2026-08-13).** *After PR-0(c)'s field is live in a published payload, DS-PR-0, and the mockup gate. The §J.10 concurrence is GRANTED (PR #5504, ruling §10) — no longer a wait.*
Scope (the ruling's §10 gates are the spec): count ladder over the seven `lifecycle_state` cells (two-total law) + **card grid re-sourced from the plan book — one card per plan row, the migration's structural act (§10.4)** + Candidates / 候选 separation with its own total + count cure + demotion landing table + section regroup (12 panels → 6) + four-dot rail retired same-PR with the lifecycle fact column + `.pv-mark` lane chip replacing it (§G.1 as resolved) + stocktable "Stage / 阶段" column retired (§10.5) + `data-stage` → `data-triage` rename (machine name only; fossils untouched) + `#life=` fragment (never `#stage=`) + `pv_card` lifecycle variant behind a parameter (other markets keep the legacy rail, §10.2).
Owner: Opus `builder` from MP-1 + the committed board mockups; `designer` review against amended §B acceptance.
Files: `templates/dashboard.html.j2` (stocks-mode region), `templates/_prophet_card.html.j2` (lifecycle variant behind parameter), `templates/stocktable.js` (Stage column retire), `scripts/build_site.py` (canonical count plumbing), `_us_act_now_board.html.j2` (header total only), tests.
Collision risks: **HIGH** — the Prophet program has its own queued "board funnel-presentation design pass" gated on PR #5370's merge; this PR IS that pass — coordinate with the Prophet program session so it is built once, citing both charters. `dashboard.html.j2` is the estate's most-touched template; branch fresh; rebuild-not-rebase on conflict (site-heavy law). Sequencing: lands before the macro.html migration (factory docket items 6 → 10, same file).
Rollback: template-scoped; revert + re-render.

**PR-3 — Today reference (`start.html`, packet §A).** *After PR-0.*
Scope: the five-section Today contract + column contract; consumes `.ladder`/`.chg-row`/`.empty-why` from PR-0.
Owner: Opus `builder`; `designer` review against §A acceptance.
Files: `scripts/build_vector.py` (hub renderer), new partials (`_today_*.html.j2`), tests.
Collision risks: low (no active lane on start.html).
Rollback: template-scoped.

Then: **PR-4** Prophet detail (`/prophet/<TICKER>.html` + `scripts/build_prophet_pages.py`, packet §C — after Sol's decisions and coordination with Handoff D's launch review; render-budget line enforced in the builder), **PR-5** plans (packet §D — **blocked on the Chairman's Founding-Pro presentation decision**), **PR-6** dossier reference + `stock.html` resolver (packet §E — after Sol signs the route ruling; the production render-failure bug is already chipped separately and does not wait for this).

### I.5 Per-page packet fields (files / forbidden scope / data / performance)

| Page | Files owned | Files forbidden | Data requirements | Perf budget |
|---|---|---|---|---|
| A Today | `scripts/build_vector.py`, `_today_*.html.j2` | `theme.css` (PR-0 owns), nav partials, any engine | existing: market_state, board index (`lifecycle_state` + `lifecycle_counts` per PR-0(c)), watchlist API, risk_state, calendar; **no new engine outputs** | HTML ≤ 400KB; zero blocking third-party; first useful paint < 1.5s local |
| B Prophet board | `dashboard.html.j2` (stocks region), `_prophet_card.html.j2`, `stocktable.js`, `build_site.py`, `_us_act_now_board.html.j2` | `build_prophet.py` + engine paths (PR-0(c) owns the field; this PR consumes), graded-ledger population (`DNR:KILL-PROPHET-POP-MERGE`), non-US market templates | plan book (`site/prophet/index.json.plans` + `lifecycle_state` + `lifecycle_counts`) for Setups; `us_standouts` for Candidates; premiumdata split (existing) | page ≤ current us_stocks weight −10%; grid view ≤ 40 cards + quoted `+N`; table view renders the active filter in full |
| C Prophet detail | `scripts/build_prophet_pages.py` (new), `prophet_detail.html.j2` (new) | Prophet scoring, ledger writes, plan JSON schemas | plan JSON (existing), `lifecycle_state` + per-ticker projection, delayed-resolved showcase set | ≤2 min nightly bake for ~50–120 pages; page ≤ 250KB |
| D Plans | `plans.html.j2`, `build_public_pages.py`, `landing.css` (token migration) | Stripe objects, `config/plans.yml` **prices** (presentation only), billing spine | `config/plans.yml` as the single claim source | page ≤ 300KB; zero JS beyond toggle/selector |
| E Dossier | `ticker.html.j2`, `build_ticker_pages.py`, `stock.html` (resolver only) | Prophet plan rendering inline (chip links out), access config (Handoff A owns) | existing dossier payloads + delayed-resolved membership set | template weight flat vs current; header renders without JS |

---

# J. Approval decisions required (Sol / Chairman) — consolidated

1–6: as listed in the IA doc §10 (six-job nav regroup; Neural Web naming; Mastermind Bot naming; watchlist.html identity; **Founding-Pro presentation variant (i) vs (ii) — blocks PR-5**; Prophet named-entry placement).
7. **`stock.html` retirement to a resolver** (packet §E) — route decision.
8. **Prophet detail hero Fable-gate** (packet §H) — only if it is designated the launch signature surface.
9. **Count-ladder ratification** (packet §0/§B) — the signature device and its enforcement rule (the only sanctioned home for a setup count). *Status 2026-08-13:* clause 3 (the cell set + the field) is **answered by the Prophet lane ruling** (PR #5504 §6: the seven-cell `lifecycle_state` partition, two-total count law, PR-0(c) spec); what remains for Sol is ratifying the ladder as the signature device itself.
10. **Card lifecycle vocabulary** (§G.1) — *Status 2026-08-13:* Prophet-program concurrence **GRANTED** (PR #5504, ruling §10), refined: the rail retires rather than relabels; conditions (same-PR retire, US-scope parameter, book-sourced grid, stocktable column retire, weight re-map) recorded in §G.1 and MP-1. PR-2 is unblocked on this item.
11. **Anonymous Prophet-detail lock shell** (§C ACCESS) — ratify that current-board names expose no lifecycle/verb/rail anonymously and carry `noindex` while on the board (the red team's board-leak cure; it is the direct application of `01` §5 + `04` §7, recorded here because it materially changes §C's SEO posture).

---

# K. Red-team record

Independent Opus red-team pass, 2026-08-11/12. Initial verdict: **REWORK — scoped** (census strongest of the three; packet not builder-ready). Seventeen findings; every blocker and major was accepted and integrated before ship:

- **#1 (BLOCKER, board leak):** the first-draft §C/§E anonymous rules would have published the complete current live board via crawlable detail shells. Fixed: §C ACCESS rewritten (lock shell + `noindex` for current-board names; full public detail only for delayed-resolved episodes), §E chip tier rule, new crawl acceptance test. §J.11 records the ratification ask.
- **#2 (BLOCKER, missing stage field):** the ladder was spec'd against a `data-stage` attribute that carries a different triage vocabulary; no EARLY/CONFIRMING/CONFIRMED field exists in `build_prophet.py`. Fixed: PR-0(c) mints the stage as a display-tier field with a stated contract; ladder consumes new `data-life`.
- **#3 (BLOCKER, two lifecycles on one card):** the card already ships a ratified 4-stage lifecycle rail (筑底/转向/就绪/趋势); `.pv-stage` would have added a second. Fixed: §G.1 binding one-vocabulary rule; default = stage lexicon re-cuts the rail; Prophet-program concurrence + §J.10 gate; PR-2 scope enlarged accordingly.
- **#4 (BLOCKER, Caddy wrong-cause):** the 404 spec misread the active, deliberate `handle_errors` contract and would have broken fail-closed gated-asset JSON. Fixed: F.4 rewritten (HTML-only 404 branch inside the existing block; JSON-503 regression test).
- **#5–#6 (count invariant):** EXTENDED was missing from the cell set; the lock sold non-actionable states. Fixed: partition law (§0), enum-derived cells, actionable-subtotal lock, acceptance B.1 restated.
- **#7 (Needs-attention composite risk):** ordering respecified as a stated non-scored precedence rule with per-row printed provenance; any future scored ranker routed through PSI §3.1.2.
- **#8 (Research as new mega-menu):** per-menu budget + "All research →" index + macro.html demotion reconciliation added to the IA.
- **#9–#10 (no home for shared components; ramp risk):** PR-0 created (theme.css ramp with stated extraction boundary + shadowing-declaration cleanup + primitives); PR-2/PR-3 became consumers.
- **#11 (missing packet fields + mockups):** §I.5 per-page files/forbidden/data/perf table added; blocking MOCKUP GATE added per the spawn-handoff law.
- **#12 (URL contradictions):** IA Phase N2 amended to `/prophet/<TICKER>.html`; resolver builder named; `?as-of` respecified as client-fetch; namespace coexistence and render-budget line added.
- **#13 (demotion orphans):** demotion landing table added to §B; mobile path clarified as demoted-not-deleted.
- **#14 (violet collision):** violet is lock-only; active ladder cell uses weight.
- **#15–#17 (minors):** anti-sameness contract (§G.6); census number-hygiene fixes (denominators, destination-count bases, template counts); zh ladder lexicon + zh×390w geometry test + anonymous primary-market default.

Standing dissent preserved: none — no finding was rejected. The reviewer's overall judgment that "nothing here requires abandoning the six-job model or the count ladder" stands as the review's conclusion on the architecture itself.

---

# L. Amendment record

**2026-08-13 — Prophet ruling conformance (PR #5504, `research/PROPHET_RULING_J9C_J10_LIFECYCLE_CELLS.md`).** Amended by the design authority to make this packet conform exactly to the Prophet program lane's §J.9(c)+§J.10 ruling. The §K record above is history and untouched. What changed:

1. **Cell set re-cut (§0, §B):** the six-cell EARLY/CONFIRMING/CONFIRMED/AGING/EXTENDED/INVALIDATED enum (refused — two producer-less cells, two live axes fused) is replaced by the ruled seven-cell `lifecycle_state` partition: **Watch 观察 · Ready 就绪 · Entered 入场 · Delivering 达标 · Overtime 超时 · Invalidated 失效 · Resolved 已结**, with the ruled EN/ZH labels fixed (PR-0(c) paired constants) and the two-total count law (`lifecycle_live_total` binds the headline; `resolved` outside it).
2. **Weight grammar re-issued (§0)** over the seven cells: dashed → half → solid (entered/delivering) → solid muted (overtime) → hollow/struck (invalidated) → neutral outline (resolved); direction-neutral; selection encoding (solid + heavier rule) reserved, never a cell identity.
3. **Setups population re-based (§B):** the governed Setups grid renders the plan book — **one card per plan row, keyed by plan `id`** — not screener candidates; multi-episode names get the episode-chip treatment (defined in §B), never collapsed.
4. **Candidates separated (§B):** the candidate screener becomes its own **Candidates / 候选** section with one canonical total, disjoint nouns, no lifecycle vocabulary inside it (one-referent-per-page word law).
5. **Stage retirement (§B, §C, §E):** the four-dot price-stage rail retires wherever the lifecycle appears (same-PR law); the stocktable "Stage / 阶段" column retires; `#stage=` → `#life=`; the word "stage/阶段" leaves all user-facing Prophet copy. Superseded in place: old §B acceptance 1/3, the red-team #2 minting language, "stage" vocabulary throughout §A/§C/§E.
6. **Lane preserved as a mark (§B, §G.1):** `lane` survives in the engine untouched; on surfaces it is only the static `.pv-mark` entry chip (no recovery chip) + LENS fact — never a progress device.
7. **§G.1 resolved:** concurrence granted; rail retires rather than relabels (ruling §1.2); §G.2 restated over three count-bearing devices.
8. **Execution re-scoped (§I):** PR-0(c) now carries the ruling's §9 spec verbatim (field ships dark); PR-2 is governed by the migration packet `research/migration_packets/MP-1-prophet-board.md` (authored with this amendment) and is gated on PR-0(c)-in-payload + DS-PR-0 + the mockup gate — no longer on §J.10.
9. **§J statuses:** item 9 clause-3 answered; item 10 granted.
10. **Companion touch-ups:** the IA doc's §"Prophet stage vocabulary" and Today-hub slice lines re-cut to the ruled cells; factory docket item 6 dependency updated.
