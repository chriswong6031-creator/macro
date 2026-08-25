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

## §5 US current-state overlay (pending analyst return — see following section in this commit series)

## §6 V4 / Cell H overlays (pending analyst return)

## §7 Recommended rollout + US architecture (provisional)

Written after §5/§6 land in this document.

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
