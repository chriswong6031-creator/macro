# Stock Dashboard V3.6 — cross-market convergence packet for Sol (2026-08-25)

Author: Fable COO session, `WS:PROPHET-HK-CA-REVAMP` presentation lane.
Skillpack: `Mastermind@4d323d03e4151449a4b76abfdfefca1d56825fde` (verified pin).
Macro pickup: `origin/main = ce4a33aeeed779530942560c5b05f4df8ab0306c`.

**Standing caveat:** the HK follower has NOT been built (Canada leg-2 gate is
still open — see §0), so every "universal grammar" claim below is evidence from
ONE market plus code archaeology. Per the commission and standing law, V3.6 must
not be proclaimed the universal design until the HK follower proves the grammar
generalizes. This packet exists so Sol can adjudicate the three colliding layers
(V3.6 presentation · US V4/MP-1 semantics · Cell H experience research) BEFORE
any US visual architecture is frozen.

## §0 Current delivery state (honest classification)

| Item | State | Receipt |
|---|---|---|
| Canada V3.6 (#6315 `b14f1f4186a8`) + V3.6.1 (#6327 `5a8f6a5aa98b`) | MERGED; **BUILT_NOT_PROVEN** | `research/STOCK_DASHBOARD_V36_CANADA_ACCEPTANCE_2026-08-25.md` |
| — Leg 1: production release identity | **PROVEN** (2026-08-25) | VPS `/opt/macro` HEAD `ce4a33aeeed7` contains both merges; `api/health` checkout match; served loader chain verified |
| — Leg 2: entitled browser matrix | **BLOCKED — entitled session unavailable to an autonomous agent** | `canada-stock-v36.js` 401 anonymous (by reviewed design); Claude-in-Chrome not connected all session; credential entry prohibited |
| HK V3.6 presentation | **NOT_BUILT — lawfully unreleased** (pilot gate law) | 08-23 handoff `next_actions`; this session honored the gate |
| US V3.6 | **NOT_BUILT, NOT COMMISSIONED** | no record authorizes it (see §1) |

## §1 Recovered V3.6 design authority (Phase A archaeology)

**There is no standalone V3.6 masterplan document.** The complete design
authority is: PR #6315 body (+ its Sol closeout comment, 2026-08-23T11:55Z),
PR #6327 body, and the records-only Agent OS handoff
`agentos/handoffs/PROPHET-HK-CA-REVAMP-2026-08-23.md` (added by PR #6323,
merge `08875eee579b`). Searched exhaustively: macro `research/`, `agentos/`
(zero V3.6 DEC/DSC records), `mockups/`, `verify_shots/`, Mastermind tracked
tree at `origin/master` (zero hits for "V3.6"/"STOCK-DASH", zero hits for
either SOL operation ID).

Consequences Sol should know:

1. **Rollout sequence:** `Canada → HK` is durably recorded (pilot-gate law in
   the 08-23 handoff). **`HK → US` is NOT recorded anywhere.** The handoff's
   sentence "the regional stock-dashboard experience architecture was frozen"
   cites nothing and no DEC record backs it. If a Chairman ruling froze a
   fuller sequence, it lives outside both repos. This packet does not
   manufacture the sequence; §7 recommends one for ratification.
2. **Visual approval:** no committed mockup/screenshot documents what the
   Chairman approved. "Chairman-approved"/"Chairman-reviewed" are PR prose.
   The #6327 signed-in screenshot that exposed the hierarchy defect was never
   committed.
3. **Capability preservation:** no record inventories which old-HK/old-US page
   capabilities must survive regionalization. §4's disposition table is the
   first such inventory (HK); the US equivalent is §5.
4. **The #6327 lesson (the one recovered piece of hierarchy doctrine):** the
   regional stock page is a *Discovery Board* — the primary candidate surface
   (Prophet) must own the first decision viewport; full leadership ranking is
   secondary/exploratory and sits below; a compact "Leading Now" cue may sit
   above; zero-states stay quiet (no negative sentences).

## §2 The V3.6 grammar as shipped (evidence, not proclamation)

From the deployed composer bytes (`site/canada-stock-v36.js` @ `ce4a33aeeed7`,
341 lines) and the PR record:

**Hierarchy (V3.6.1):** Header → Leading Now (compact strip) → **Prophet**
(primary decision surface) → Theme & Sector Leadership (two-column top-5 +
expand modal) → Research tools.

**Composition law:** presentation-only progressive enhancement. The composer
*moves* the already-rendered owner DOM (existing `.pvcard` family, existing
`#stocktable-wrap` StockTable) into the new shell; it re-renders nothing it
does not own; on any missing precondition it aborts and the legacy page stands.
Entitlement boundary: the composer JS is a registered (401-anonymous) asset;
the page shell and loader stay public.

**Authority law (held everywhere in the code):** Top Picks = first five of the
canonical board order (`data-ca-v36-order`, no re-scoring); theme/sector rank
read verbatim from owner artifacts (`rank` field, "the page never re-scores");
leadership filtering = set-membership over owner-published members; counts are
derived only from the exact displayed collection.

**Clock law:** `Board <as_of>` chip (nightly decision clock) is rendered
separately from the `LIVE · <today>` chip (client clock); live prices patch
existing `.nb-px`/`.nb-chg` spans (owner: live.js quote plane) — a fresh quote
can never imply a recomputed board.

**Honesty furniture:** "Screen · evidence accruing" truth chip (no
official-pick claim; Top Picks halo is neutral); quiet zero-states; leadership
"Ranking unavailable" empty state; 2.5 s fetch race so leadership data can
never block the Prophet surface.

**Interaction set:** Top Picks | All Candidates · Grid | Table (persisted per
market in localStorage) · leadership row click → filter + scroll to Prophet ·
Expand-leadership modal · filter pill with one-tap clear.

**Mobile:** single-column decision layout ≤680 px; controls wrap; modal
full-bleed.

## §3 Market-specific deltas (what must NOT generalize blindly)

Evidence: full HK/Canada page census (this session; `templates/hk.html.j2`
mode="stocks", `templates/canada.html.j2` mode="stocks", builders).

1. **Tape convention.** The site swaps up/down colors under `data-lang="zh"`
   (Asia convention, `theme.css:207-231`). Canada V3.6 deliberately PINNED the
   Western convention even under ZH (a Canada-market truth). **HK must keep the
   native swap** — an HK follower must not import Canada's pin.
2. **Live quotes.** Canada's legacy page carries live quote patching; **HK's
   stock page has no intraday quote surface at all** (no polling/websocket code
   in the template). An HK "LIVE" chip that implies live quotes would be a
   lie; the HK header clock treatment must reflect HK's actual quote plane
   (board as-of + whatever session state HK truly publishes).
3. **HK-native intelligence context with no Canada slot:** southbound flow
   panel + per-name "Mainland buying" chips, A/H premium ("Cheap vs A-share")
   chips, 1D Velocity Desk, ripening shelf, ran/vetoed/laggards transparency
   strips, watch strip (knife/placement-dilution blocks), leadership banner,
   rotation-chain strip, richer StockTable columns (`sb_z`, `ah_z`,
   `align_tier`, `washout_2w`). These are product capabilities, not clutter;
   §4 rules on each.
4. **Track-record eras.** Both markets carry era-scoped scorecards
   (`hk_track_ledger.json` / `ca_track_ledger.json`, never-pool law from the
   ledger-era wave). Any regional composer must keep the era clock distinct
   from board/live clocks.
5. **Terminal routing** is shared mechanism (`MDXTerminal` portal with
   per-market lookup fallback) — same contract, different fallback URLs.

## §4 Canada→HK capability disposition table (pre-build, per commission)

Rulings by Fable this session; build execution remains gated on Canada leg 2.
`RETAIN` = keep as-is in HK V3.6; `ADAPT` = keep with HK-native change;
`NOT_APPLICABLE` = no HK equivalent needed; `BLOCKED_DATA` = wants data HK
does not publish today.

| Canada V3.6 capability | HK equivalent | Ruling | Canonical HK owner |
|---|---|---|---|
| Header + truth chip ("Screen · evidence accruing") | HK is a scored market (era-scoped win-rate published) | **ADAPT** — chip must state HK's actual authority tier, not copy Canada's accruing status | `track_record` VM / ledger-era law |
| `Board <date>` vs `LIVE · <today>` dual clock | HK has board as-of but NO live quote plane | **ADAPT** — keep board as-of chip; render session/live chip only from a truthful HK source; never a client-clock "LIVE" implying quotes | build_hk VM `setups.as_of` |
| Leading Now strip (top theme + top sector + fresh count) | `hkbasketdata/sector_pulse_hk.json` + `baskets.json` exist (same producers as Canada) | **RETAIN** (same artifact contract) | `engine/sector_pulse.py`, `scripts/build_baskets_hk.py` |
| Prophet card grid (existing pvcards moved, Top Picks = first 5 canonical order) | Same `_prophet_card.html.j2` family on HK page | **RETAIN** (adapt DOM selectors — HK grid is not `#standouts .cards`) | HK board order from `build_hk.py` (intelligence lane) |
| Top Picks / All Candidates toggle | Same board semantics | **RETAIN** | canonical HK board order |
| Grid / Table toggle (StockTable moved intact) | Same `stocktable.js` contract, HK columns richer | **RETAIN** — HK columns (`sb_z`, `ah_z`, `align_tier`, `washout_2w`) must survive intact | `templates/stocktable.js` + HK column spec |
| Theme & Sector Leadership two-column + expand modal | HK artifacts exist; HK also has rotation-chain strip | **RETAIN** (leadership) + **RETAIN** rotation strip as HK-extra research row | basket/sector-pulse artifacts |
| Leadership filter → membership filtering of cards+table | Same membership contract (`symbol`/`ticker` key compat) | **RETAIN** (verify HK member key shape at build time) | basket artifacts |
| Live quote patching into table cells | No HK live quote plane | **NOT_APPLICABLE today; BLOCKED_DATA if wanted** — do not fabricate | (future) HK quote plane owner |
| Western tape pin under ZH | Site-wide ZH swap is HK-native truth | **NOT_APPLICABLE — must NOT port** (keep Asia convention) | `theme.css` global law |
| Research tools row (baskets + macro links) | `baskets_hk.html`, `hk.html`, `hk_stocks_lab.html` | **RETAIN** (+ Pick Lab link) | existing pages |
| Quiet zero-states (#6327) | Same | **RETAIN** | composer |
| — HK capabilities with no Canada slot (preservation duties): | | | |
| Hero/deskhero (risk state, liquidity regime, exposure split, breadth, southbound 20d) | n/a | **RETAIN in HK V3.6** (adapted placement above/inside header band) — do not delete for cleanliness | `hk_scoreboard`/overlay VM |
| Act-Now 4-lane sector board | Canada V3.6 consumed the same lanes for its sector column | **ADAPT** — becomes the sector half of Leadership (as Canada did), keep lane semantics | `actions` VM |
| Southbound flow panel + A/H premium panel | n/a | **RETAIN** as a distinct HK intelligence section below Leadership (never deleted; owner-rendered DOM moved, not rebuilt) | `internals.southbound`, `ah_official` |
| Per-card HK chips ("Cheap vs A-share", "Mainland buying") | n/a | **RETAIN** — cards are moved DOM; chips travel with the cards automatically | `_prophet_card` inputs |
| 1D Velocity Desk | n/a | **RETAIN** (research-tier section below leadership) | `hk_1d_velocity_desk.json` |
| Ripening shelf / ran / vetoed / laggards / watch strips | n/a | **RETAIN** — progressive disclosure below the primary board; these are the transparency spine | `setups.*` VM |
| Track-record dialog (era-scoped) | Canada has the twin | **RETAIN** | `factordata/hk_track_ledger.json` |
| Leadership banner (HKRV-W3) | n/a | **RETAIN** (compact, near Leading Now band) | `setups.leadership` |
| StockTable search placeholder | Canada lacks it | **RETAIN** (HK keeps its search) | stocktable.js |

**Build-shape ruling (for the gated wave):** HK V3.6 = new `hk-stock-v36.js`
(entitled asset, path-gated to `hk_stocks.html` via the same
`dashboard-icons.js` loader pattern, Canada gate untouched) that adapts the
V3.6 shell to HK's DOM ids and preserves every RETAIN row above by *moving*
owner DOM, exactly as Canada did. No template forks, no second card family,
no writes to `hk_standouts.json`/`build_hk_library.py` (intelligence-lane
landmine), no new artifacts.

## §5 US current-state overlay (with rulings)

Inventory basis: full read of `templates/dashboard.html.j2` mode="stocks"
(50 user-facing capabilities enumerated this session, DOM order, with data
sources; detail refs: header `:2393-2412`, Act-Now include `:15626`,
`#prophet-live` `:15823`, source toggle `:15925-15928`, lifecycle ladder
`:16272`, plan grid `:16283`, candidate grid `:16459-16460`, walls
`:16344`/`:16468`, refusal shelf `:16567`, track record `:16646-16700`;
`scripts/build_site.py` `:4718-5249`, `:6951-6987`).

**Headline finding for Sol:** the US page today carries the exact inverted
hierarchy that #6327 corrected on Canada — a macro-context tier (policy lever,
regime read, week-ahead, AI brief, sector heat, sentiment, cross-asset, index
health) **plus** the five-lane Act-Now board **above** the principal Prophet
board. If the #6327 Discovery-Board doctrine (Prophet owns the first decision
viewport) is Chairman law and not a Canada-only taste call, the US page is in
violation today. That is a hierarchy question, not a V3.6-code question.

**MP-1/P0 shipped state (receipts):** MP-1 central act shipped (#6076
`31ca4971ba4a`: plan-book grid + 7-cell lifecycle ladder + W-L1 repaint
neutralization); it deleted the candidate experience (recorded regression);
P0 restored it (#6243 `fd0c0b0ece50` + heal #6249 `87e65fcdb761`) as a
two-source `Candidates | Plans` toggle — **a source switch, not a population
merge** (MP-1 Amendment 2 / `DEC:P0-PROPHET-CANDIDATE-BOARD-RESTORE`).
`P-MP1-DENSE` (plans-only dense table) is OWED, and MP-1 law forbids calling
the US redesign complete while it is open. Still-unverified production legs:
entitled 60-card hydration; intraday tick repainting a candidate card.

**Rulings per major capability cluster** (`RETAIN`=stays where it is;
`IMPROVE`=stays, needs work; `RELOCATE`=survives but moves;
`SUPERSEDE`=replaced by a named successor; `BLOCKED_DATA`=wants a plane that
is not accepted yet; nothing is REMOVE — no capability dies for cleanliness):

| US cluster | Ruling | Why |
|---|---|---|
| Header + freshness/staleness contract (fail-closed badge, `_DELAY_RE` phrase contract) | **RETAIN** | Stronger than V3.6's clocks; the V3.6 dual-clock chip is the junior sibling. Never regress to a client-clock LIVE pill |
| Macro-context tier (8 panels) | **RELOCATE** | Below the principal board (or progressively disclosed / linked to `macro.html`) per the #6327 doctrine — pending Chairman ratification that the doctrine is cross-market law |
| Act-Now five-lane sector/theme board | **RELOCATE + eventual SUPERSEDE** | Near-term: fold into the Leadership tier below Prophet (as Canada did with its lanes). At V4 B4 cutover its lane vocabulary (BUY NOW / ALMOST READY / …) must yield to availability-derived lanes — three lane vocabularies on one page is two too many |
| Prophet Live "Forming today" (W-L1 poller + stamp) | **RETAIN** | Provisional-intraday tier V3.6 lacks; repaint-neutralization ruling stands |
| `Candidates \| Plans` toggle, candidate census/shelves, plan grid + lifecycle ladder | **RETAIN** | Binding Chairman ruling; the ladder's counts come from the full unsliced book (count law). V3.6's single-population Prophet slot must NOT be imposed here |
| Grid/Table toggle + USStockTable | **RETAIN + IMPROVE** | P-MP1-DENSE owed (plans-only table); no second candidate table |
| Tier walls + hydration (server split, fail-closed plan gate / fail-open candidate gate) | **RETAIN** | US boundary architecture is server-split+hydration; V3.6's composer-gating (401 JS) is the small-market pattern and must not replace it. Note: V3.6 "first 5" Top Picks is unfillable on the anonymous shell (preview=3) — a US concentration device must be the existing Featured cohort, not a new Top Picks rule |
| Disclosure tier (refusal shelf, no-plan sample, blackout note, featured footnote, board-state note) | **RETAIN** | V4 law-9 obligations (missing ≠ zero); shipped error copy promises these sections by name |
| Track record strip + dialog, what-changed dialog | **RETAIN** | Era/cohort-honest; position is load-bearing (named in shipped copy) |
| Research/context rows (recently fired, fresh triggers, market leaders, breadth, sector setups, turn setups, accumulation, 13F, theme tape, tapes) | **RETAIN, RELOCATE below board** | Research tier of the hierarchy; leaders/theme tape feed a future Leading-Now analogue |
| Live quotes (live.js repaint contracts) | **RETAIN** | Owner plane; any recomposition must keep repaint selectors intact |
| "Leading Now" strip (V3.6 element) | **ADOPT (new)** | US has the data (sector heat, theme tape, leaders) to render the compact cue above the board — presentation-only |
| EN/ZH, mobile, stock-detail routing | **RETAIN** | House law |

## §6 V4 overlay and Cell H overlay

### V4: what a US presentation layer may read vs must never own

Frozen thesis (`research/prophet_v4/ARCHITECTURE_FREEZE.md`): *surface by
emergence, gate by the trade available now, rank by intelligence* — with law 2
(no browser-derived authority) and law 7 (availability outranks score) binding
any presentation work. Plane boundary (condensed; full table in the analyst
inventory, refs above):

- **Plan lifecycle vocabulary** (`site/prophet/index.json`, 7 cells + counts):
  LIVE — read the published counts/order verbatim; never re-count from a
  slice, never re-sort (`plans_sort_key` is the only order).
- **Availability/ENTRY_OPEN** (B4): PARTIAL — semantics in
  `engine/entry_signal.py`; presentation renders state/zone/blocker, never
  computes a second zone; `UNAVAILABLE_DATA` is never green; lanes derive from
  `availability_state` only.
- **Lifecycle 4-field state** (B3) and **candidate episode identity** (B1
  grain): NOT_BUILT — nothing may fake them meanwhile (the MP-1 episode chip
  is a display count, not the episode plane).
- **Candidate pool** (`us_candidate_pool_v1`): data plane LIVE, full UI
  NOT_BUILT — a future All-Candidates UI consumes the lossless partition; no
  rival partition client-side.
- **Suppression/retirement (D2B3)**: BUILT_NOT_PROVEN — presentation may show
  typed refusals/retired status; never overlays or undoes one.
- **Freshness/settlement**: page must announce stale/degraded before cards;
  the EN staleness phrasing is a sentinel contract.
- **Ranking/eras/outcomes**: read published order and cohort-honest stats;
  `DNR:KILL-PROPHET-POP-MERGE` and never-pool-eras stand.

V3.6 already complies with the analogous laws on Canada (no re-scoring, owner
DOM moved, counts from displayed collection); the US application of V3.6
*doctrine* is compatible with V4 **only** as a server-side hierarchy change —
a client-side composer re-owning the US board would violate law 2 at the four
collision points named in §5.

### Cell H: where its ideas belong

**Governance fact:** the Cell H handoff
(`CELL_H_FLAGSHIP_PRODUCT_EXPERIENCE_HANDOFF_2026-08-22.md`) is **not on
`origin/main`** — it exists only on `origin/sol/prophet-flagship-fanout-
hardening-20260822` (`1ba4580f0679`). It self-declares "experience research /
reference composition only, zero production authority," and its five proposed
waves are explicitly unauthorized. Sol must merge/ratify that branch (or
re-home the docs) before any of it becomes citable law.

Disposition of its idea set (per the commission's four buckets):

- **Directly in the future US board:** three-tier information law
  (glance/inspection/forensic); 5-second decision goal; four-questions card
  anatomy with "can I act" dominant; mobile 390px priority law; bilingual
  plain-language law (already house law); ten typed degraded-state designs
  (several states already real: staleness, rights gate, correction/identity
  receipts).
- **Behind progressive disclosure:** evidence-independence UX,
  price-incorporation UX, fragility/crowding panel, analogue/prior UX — all
  **BLOCKED_DATA** today (intelligence vector D5, Cell B/D, alt-data families
  not accepted); design slots may be reserved, populated only when planes land.
- **In detail/dossier surfaces:** the 9-question dossier order (inherited V4
  law); theme & propagation composition (BLOCKED_DATA on `theme_state/v1`).
- **Later (upstream not accepted):** transition-driven alerts; "why now"
  explanation contract (needs an accepted explanation primitive + theme
  evidence reaching rows — currently 73% structural-only).

Cell H's own non-goals independently reinforce §5's rulings: green means
`ENTRY_OPEN` and nothing else; no overall conviction score; no client-filter
hidden authority; do not redesign the six-view V4 shell.

## §7 One recommended US architecture (recommendation only — no implementation)

**Recommendation:** the future US Prophet page is a **server-side template
evolution of the existing `dashboard.html.j2` stocks mode** that adopts the
V3.6.1 *hierarchy doctrine* and Cell H's *information-tier doctrine*, while
keeping every US semantic device exactly where V4/MP-1 law put it:

```
Header (identity · freshness/staleness contract · board-state stamp · dual clocks)
Leading Now (compact: top theme · top sector · leaders cue — presentation-only)
PROPHET principal panel  ←— first decision viewport
  ├─ Candidates | Plans toggle (Amendment 2, unchanged)
  ├─ Plans: 7-cell ladder + plan cards (+ owed P-MP1-DENSE table)
  ├─ Candidates: census + stage shelves + cards + tier wall/hydration
  └─ Prophet Live "Forming today" (provisional tier, adjacent)
Disclosure tier (refusals · no-plan sample · blackout · footnotes · track record)
Theme & Sector Leadership (Act-Now folded here; lane vocab → availability lanes at B4)
Research tier (breadth · setups · accumulation · 13F · leaders · tapes)
Macro context (relocated below, or progressively disclosed / linked)
```

- **Delivery mechanism:** NOT a client-side composer. US keeps
  server-split+hydration tiering; the V3.6 composer pattern stays a
  small-market (CA/HK) delivery tactic.
- **Concentration device:** the existing Featured cohort (≤12, ≤4/sector,
  disclosure footnote) — no new Top Picks rule, no first-N-of-preview
  arithmetic.
- **Freeze gates (ordered):** (1) Canada leg 2 passes; (2) HK follower ships
  and proves the grammar generalizes; (3) V4 B3/B4 (lifecycle/availability
  planes) land so lanes/verbs bind to real states; (4) Cell H provenance
  ratified. Freezing the US visual architecture before (2)+(3) would bind the
  flagship to an unproven grammar and unaccepted planes — the exact failure
  mode this commission exists to prevent.
- **Kill list on ratification:** any parallel US redesign that (a) merges the
  two populations, (b) introduces a new lane vocabulary, (c) re-derives
  availability client-side, or (d) re-owns the board via a client composer.

## §8 Unresolved decisions for Sol/Chairman

1. **Canada leg 2** — the entitled browser matrix needs an operator-side
   session (connect Claude-in-Chrome, or run the matrix by hand). Until it
   passes, Canada stays `BUILT_NOT_PROVEN` and HK stays unreleased.
2. **Ratify the rollout sequence** — `Canada → HK` is law; `→ US` is not.
   Sol should either ratify `Canada → HK → US(presentation follows the frozen
   US product architecture)` or explicitly decouple US.
3. **Mint the missing durable records** — a DEC record for the regional
   experience architecture (the 08-23 "frozen" claim currently rests on prose),
   and committed reference visuals once leg 2 produces them.
4. **HK "LIVE" treatment** — accept the §4 ruling (no fabricated live chip) or
   commission an HK quote plane first.
5. **Cell H provenance** — the flagship experience research lives only on the
   unmerged `sol/prophet-flagship-fanout-hardening-20260822` branch. Merge or
   re-home it before any US freeze cites it (§6).
6. **US hierarchy doctrine** — ratify whether the #6327 "Prophet owns the
   first decision viewport" lesson is cross-market law; if yes, the US page's
   macro-tier-above-board layout is a standing violation to be corrected in
   the (later, separately commissioned) US wave (§5/§7).
7. **US freeze order** — §7's gates: Canada leg 2 → HK follower proof →
   V4 B3/B4 → then freeze US. Competing US redesign paths can be killed
   against §7's kill list at ratification time.
