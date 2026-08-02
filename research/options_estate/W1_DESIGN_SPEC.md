# W1 — nav front door + Ticker workbench depth (design spec)

Status: **PINNED DESIGN** for OIP wave W1. Authored by the design lane 2026-07-30.
Extends `research/options_estate/WORKSPACE_DESIGN_SPEC.md` (the pinned `.oew` system —
fill-track thesis, slate-indigo structure accent, brass record ink, closed six-stance
vocabulary, mono-for-figures type law, question-framed eyebrows). This document does not
fork that system; every new class below is namespaced `.oew-` and every new token is
declared inside the existing `.oew{}` scope. Implements
`research/options_estate/OIP_MASTERPLAN.md` §0 (gates), §3 (design language), §4 (IA),
§5.1 (S1 Ticker depth) and §11 (W1 scope).

Binding inputs, in conflict-priority order: `docs/DESIGN_DOCTRINE.md` (content law) →
this document (visual system + copy for W1) → `WORKSPACE_DESIGN_SPEC.md` (the base system
this extends) → `OIP_MASTERPLAN.md` (direction and vocabulary, not markup).

**Reference implementation:**
[`mockups/oip_w1/w1_mockup.html`](../../mockups/oip_w1/w1_mockup.html) — self-contained,
no build step, no external fetches. Working theme/lang toggles (real production markup,
not a demo-only control). Copy markup and CSS from that file verbatim; where this document
and the mockup disagree, the mockup is the source of truth for markup, this document for
why and for the copy tables. Crops: `mockups/refs/oip/w1/`.

---

## §0 THE BUILDER MUST NOT DECIDE THESE

Every item below is already decided. Changing one is a design change and returns to the
design lane, not resolved in the build (spawn-handoff law).

**Scope**
1. W1 ships: the nav regroup, Ticker-mode search, five new S1 reads (filmstrip · rich-or-
   cheap · where-positions-built · what-the-move-is-worth · expiration-pressure), the
   `wall_persistence` cross-check chip on the two existing wall rows, and declared-cap copy
   on Scanner/Leaders. It does **not** ship Brief mode's session-character shelf (W2), the
   Scanner v2 columns/presets (W3), or the Structure & Vol desk (W3). The filmstrip's Brief
   placement is pinned here (§5) so W2 does not re-open its design, but W2's own team wires
   it.
2. **The LEX six-stance vocabulary needs NO engine change.** Verified fresh against
   `engine/i18n.py:579-587` (2026-07-30): all six doctrine stances — Act, Get ready,
   Watch — don't chase, Protect gains, Stand aside, Ignore — are already present, under the
   comment *"stances (the doctrine six, complete since OEU M-CMD — the Options workspace
   uses all of them, so every stance now resolves through td() for this and every future
   surface)"*. `WORKSPACE_DESIGN_SPEC.md` §5.0's claim that three are missing is **stale** —
   it was accurate on 2026-07-25 and someone completed the set since. §5.4 below reproduces
   the current, verified table. **No `engine/i18n.py` edit ships in W1.**
3. **`summary.iv_rank` already exists** (`engine/gex_model.py:616-627`) — a real, honestly-
   qualified ~40-trading-day self-percentile (`rank_pct`, `band`, `n_days`,
   `low_confidence`), already rendered on gex.html's "mood" card
   (`site/gex.js:774-783`). This is **not** the same thing as the masterplan's "true 252-day
   IV rank," which genuinely does not exist. §5.2 ships the real short-window field, young-
   flagged, rather than empty-stating a field that already has data. This is a deliberate,
   reported deviation from the literal "design as an empty state" instruction — see the
   build-report note in the PR body.
4. **Term-slope word and skew percentile are genuinely absent** (no field anywhere computes
   them; `term[]`/`smile[]` carry only raw per-expiry/per-strike numbers, and `tilt.legs`'s
   skew leg carries a raw `rr25` with no percentile). These stay out of W1 entirely — not
   built as a template-side classification, not empty-stated as their own panel. They are
   E2(c) work (masterplan §6), not a W1 concern.

**Colour**
5. Filmstrip ink uses `--oew-accent` (structure), **never** `--up`/`--down`. The arc's sign
   (call-heavy vs put-heavy premium) is not one of the two sanctioned direction instruments
   (masterplan §0.8: tape_flow, ΔOI) — coloring it red/green would read as an unsanctioned
   direction claim. Same rule, same reasoning as the masterplan's own ΔOI bars (§3:
   "direction-neutral tint... so ZH flip never touches it").
6. The wall-persistence cross-check chip is a **calm confirm/disagree/no-data** mark, not a
   stance and not a pip. It uses `--oew-accent` (confirms), `--ink-3`/muted (disagrees —
   this is a fact about data sources, not a warning), and is silent (renders nothing) when
   `matches_board_wall` is `null`.
7. Empty-state panels (`.oew-notyet`) use a **dashed** hairline, never a solid one — dashed
   reads as "not drawn yet," solid reads as "drawn and empty," which would be dishonest
   (there is no zero to report; there is no reading at all).

**Type**
8. Filmstrip corner labels (session open / close time) and the end-of-track close mark are
   `.mono` (times are figures). Event tick hover text and the "how the day traded" sentence
   are UI face (they are sentences). `iv_rank` band words (Rich/Elevated/Normal/Cheap/Very
   cheap) are UI face, not mono — they are words, not figures, exactly per the type-role
   law already pinned in `WORKSPACE_DESIGN_SPEC.md` §0.6.

**Layout**
9. The filmstrip is exactly `height:64px` in its two client-rendered homes (Ticker mode,
   gex.html head) and `height:56px` in Brief's session-character card (smaller because it
   sits beside other chips, not alone). Do not pick a different height per occurrence.
10. The "where positions built" bars use the sector-bar idiom verbatim: **pure length
    encoding, the value lives in its own right-aligned mono column** — never inside the
    fill (`WORKSPACE_DESIGN_SPEC.md` §5.1 already found this breaks on short bars; the same
    physics applies here).
11. Spacing/radius tokens are the existing `--s1…--s8` / `--r-pill/ctl/panel` scale. Do not
    introduce new values.

**Copy**
12. All fixed labels are pinned EN+ZH in §5/§6. Do not translate, re-word, or "improve" them.
13. **Word budget is a ceiling, not a mandate — corrected 2026-07-30, design-lane ruling.**
    `WORKSPACE_DESIGN_SPEC.md` §0's "exactly one stance chip + at most one footnote + one
    as-of per panel" caps what a single panel is allowed to carry. It has never been, and is
    not, a requirement that every panel carry a stance — a panel with zero stance chips
    satisfies that ceiling exactly as well as one with a single chip. The binding rule for
    *how many stance chips appear across a page* is the masterplan's own verdict law
    (`OIP_MASTERPLAN.md` §3), reproduced here in full so this item is self-contained:
    *"Each surface keeps exactly one decision element (the stance chip row of its
    hero/footer). New shelves add facts, never verdicts — machine-checkable: one
    `data-verdict-surface` marker per page; CI greps for duplicates."* A prior draft of this
    item conflated the two laws — it read the per-panel ceiling as a per-panel mandate and
    had every new panel, including both empty states, carry its own chip. That reading is
    **superseded by this item** and was visibly wrong in the mockup: the identical chip
    "Watch — don't chase" stacked five times down one page
    (`mockups/refs/oip/w1/02_ticker_core_en_dark.png`, pre-fix crop), reading as boilerplate
    a reader learns to skip — the opposite of a decision element.

    Applied to this wave's five new reads: **exactly one stance chip survives in Ticker
    mode, on the existing verdict surface — the Name-header panel (§5.1 item 1: spot, regime
    headline, stance, expected range), the same role gex.html's own per-symbol card already
    plays as "the existing verdict hero" (§3.5).** That panel's `.oew-ic-foot` row is the
    sole element carrying the `data-verdict-surface` marker (bare boolean attribute — see
    §5.1 for the exact markup). **Every other new panel this wave ships — "How the day
    traded" (§3.5), "Rich or cheap?" and "Where positions built" (§5.2, all their coverage-
    gap/young-window variants included), and both `.oew-notyet` empty states (§5.3) — drops
    the stance chip entirely**, in every state each panel can render, and keeps only its
    footnote sentence and its as-of stamp (where it has one). This explicitly includes both
    empty states: rendering no data is not itself grounds for a second decision element on
    the page — the plain-word "not measured yet" sentence already discloses the honest
    nothing-yet, and does not need a chip to say it a second time. The wall-persistence
    cross-check chip (§4, `.oew-wcheck`) was never a candidate here in the first place —
    §0.6 already rules it "not a stance and not a pip," and "The map" panel itself is
    unchanged by this wave and carries no stance chip of its own (verified against the
    mockup: its footer is caveat + as-of only, no `.oew-stance`) — so §4 needed no edit
    beyond this cross-reference.

    Out of scope for this item, flagged not fixed: the persistent chrome's `.oew-nofuse`
    banner and the pre-existing "Today's measured flow" panel (§5.1 item 9, unchanged) also
    render a `.oew-stance` and also appear in the affected crops. Both are
    `WORKSPACE_DESIGN_SPEC.md`-owned, pre-date this wave, and sit outside every file this
    document's §12 lists — §0.13, old or new reading, has only ever governed the panels *this
    wave* introduces. A fully page-wide reading of the verdict law would eventually want
    those addressed too; that is a base-spec decision for a separate PR, not a silent
    addition to this targeted revision's scope.

    **RESOLVED — that separate PR shipped.** The base spec took the page-wide reading:
    `WORKSPACE_DESIGN_SPEC.md` §0.16 now states the ceiling-not-mandate correction in its
    own voice and drops the chip from both spots, keeping each sentence verbatim in EN and
    ZH plus the as-of stamp where there is one. Nothing above changes — this paragraph
    correctly describes what was in scope *for W1*. What it means going forward: the page
    now carries exactly one `data-verdict-surface`, the Ticker name-header row this
    document's §5.1 pins, and `tests/test_build_options_command.py` greps for duplicates
    the way `OIP_MASTERPLAN.md` §3 asks. The chips this item removed and the two that PR
    removed were the same defect at different scopes.
14. No panel claims "validated." `iv_rank`'s `low_confidence` state is disclosed as "history
    building — Nd," never softened, never hidden.

**House-contract traps (re-verified against the current build, 2026-07-30, not assumed
from the base spec)**
15. `options.html.j2`'s `<section id="mode-ticker">` ships **empty** in the static HTML —
    `renderTicker()` fills it entirely via `innerHTML` on activation. The search toolbar
    (§2) must therefore be written to persist across ticker changes: `renderTicker()`'s
    target changes from `#mode-ticker` itself to a new nested `#oew-tk-body` div, with the
    search toolbar as a sibling static node the render function never touches. Getting this
    wrong recreates (and re-triggers `/`-focus races on) the search box every time the user
    picks a new name.
16. `options.html.j2` already ships a **sitewide** `.nav-search` box in its topbar (line
    ~514) with no `/` binding (`site/theme.js` has zero `key === '/'` handlers — verified by
    grep). The new Ticker-mode `/` shortcut therefore cannot collide with it; no
    coordination needed. It must still be scoped to fire **only while Ticker mode's panel
    is active** (§2) — unconditional sitewide binding would silently focus an off-screen,
    inactive tab's input.
17. `illus.js`'s reveal is `IntersectionObserver`-driven and keyed on `.ilx-in`, added once
    per element on first scroll-into-view. Client-injected filmstrips (Ticker mode, gex.html
    detail) are inserted via `innerHTML` **after** that observer has already scanned the
    page, so the render function must call `window.ilxReveal(host)` after insertion (the
    exact pattern dialogs already use — `illus.js:65`, `window.ilxReveal = reveal`) or the
    ink never draws.
18. `oi_delta_clusters` and `wall_persistence` are **additive and omitted, not null-filled**,
    when the chain-snapshot store does not cover a name (`engine/gex_state.py`, PR #3976 —
    open, not yet merged at spec time; expected to land before W1 build starts). Payload
    checks must be `if ('oi_delta_clusters' in gx && gx.oi_delta_clusters.new_oi.length)`,
    never assume the key exists. Coverage today (PR #3976 body, measured 2026-07-30):
    clusters lit on **302 of 555** modeled names; `net_gex_pctile` present on only **10 of
    555** (it needs ≥5 rows in a store that exists for 10 roots) — treat it as a rare bonus
    fact, never a panel of its own (§5.2).
19. **Corrected post-build (adversarial review round 2 on PR #4123):** `board_a_total` /
    `board_b_total` exist in `site/flowleaders/leaders.json`, but they are **pre-cap**
    counts — `scripts/build_flow_leaders.py`'s `_BOARD_CAP = 25` slice runs AFTER they are
    captured (verified: `board_a_total: 130`, `board_b_total: 24` on 2026-07-30, while
    `board_a`/`board_b` themselves ship at most 25 rows each). The declared-cap copy for
    Leaders (§6) must NOT read these two fields — the denominator has to equal what
    `site/flow_leaders.html` actually renders, which is `L.board_a`'s own length for board A
    and the `B5_flow_inflect`-filtered length of `L.board_b` for board B (that page applies
    the identical filter, `templates/flow_leaders.html.j2:37-38`). Deriving both from the
    arrays already in hand needs **zero** new engine work either — just a different read of
    the same payload, and one that cannot drift the way a separately-tracked total can.
20. Scanner's subtitle today (`options.html.j2` client JS, `renderScanner`) reads `rows.length
    + ' names, sorted by premium'` using the **unsliced** payload length while the table
    itself renders `.slice(0, 200)` — the exact undeclared-cap defect the masterplan
    diagnosed (§2.1 row 4). Fixing the sentence to state the cap is a one-line change to an
    existing string, not new plumbing.

---

## §1 Nav regroup

### 1.1 What changes and why

Today `options.html` is linked from **no navigation** (verified: zero matches for
`options.html` in `templates/_navlinks.html.j2`). The flyout trigger is still `gex.html`.
This is the P0 the masterplan names (§2.1 row 1) and the OEU ruling that was deferred for a
file collision and never re-attempted.

The OIP masterplan (§4) revises OEU's original plan in one respect: OEU's plan (still
visible in `templates/_options_workspace_banner.html.j2`'s header comment, "the four
absorbed desks: gex, options_screener, flow_desk, flow_leaders") had **gex.html** leaving
the flyout entirely, alongside options_screener/flow_desk/flow_leaders. OIP's §4
"Division of labor inside macro" explicitly keeps gex.html linked, reasoning that it is the
*instrument bench* (interactive charts, search-first) rather than a *reading* surface like
the other three — a genuinely different job, not a thinner duplicate. **This spec follows
OIP's revision**, so gex.html's nav row moves from "leaving" to "staying, regrouped under
Options — the workspace."

Net effect: **3** pages leave the flyout (options_screener, flow_desk, flow_leaders) — their
URLs stay live forever with the existing `_options_workspace_banner.html.j2` ribbon they
already carry (verified: all three already `{% include %}` it — no banner work needed in
W1). **1** page relocates within the nav, staying visible (movers.html → United States
group). **1** new page enters the flyout as its trigger (options.html). **4** pages stay
exactly where they are (gex.html, intraday_flow.html, darkpool.html, market_structure.html)
— gex.html's row moves down one tier (from trigger to a regular item) but keeps its href,
icon and description unchanged.

### 1.2 The diff-ready block

Replace `templates/_navlinks.html.j2` lines 84–96 (the `Options & Flow` `nav-dd nav-sub`
block, currently trigger=`gex.html`) with:

```html
        {# Options & Flow flyout — OIP W1 regroup (masterplan §4). The workspace
           (options.html) is now the trigger AND the flyout's first item, mirroring the
           existing Sector Central / China Research pattern (trigger href duplicated as
           the first inner row with a fuller description). Three absorbed legacy pages
           (screener, flow desk, flow leaders) intentionally do NOT appear below — they
           stay live at their own URLs forever with the ribbon banner they already carry
           (_options_workspace_banner.html.j2), per house law (no page kills, no
           redirects). Per-page enable flags move with their pages unchanged. #}
        <div class="nav-dd nav-sub">
          <a class="nav-sub-trig" href="{{ NP }}options.html"><span class="nav-sub-text"><span class="submenu-icon submenu-icon-options" aria-hidden="true"></span>{{ t('Options & Flow', '期权与资金流') }}<span class="d">{{ t('Workspace · desk · flow tracker · dark pool', '工作台 · 期权台 · 资金流追踪 · 暗池') }}</span></span><span class="caret-r">▸</span></a>
          <div class="nav-dd-menu" role="menu">
            <a href="{{ NP }}options.html"><span class="submenu-icon submenu-icon-options" aria-hidden="true"></span>{{ t('Options — the workspace', '期权工作台') }}<span class="d">{{ t('Daily Brief · Scanner · Ticker · Leaders', '每日简报 · 筛选 · 个股 · 领头股') }}</span></a>
            <a href="{{ NP }}gex.html"><span class="submenu-icon submenu-icon-dashboard" aria-hidden="true"></span>{{ t('Options Desk', '期权台') }}<span class="d">{{ t('Instrument bench — charts, walls, vol surface', '工具台 — 图表、墙位、波动率曲面') }}</span></a>
            {% if intraday_flow_enabled is not defined or intraday_flow_enabled %}<a href="{{ NP }}intraday_flow.html"><span class="submenu-icon submenu-icon-dashboard" aria-hidden="true"></span>{{ t('Intraday Flow Tracker', '盘中资金流追踪') }}<span class="d">{{ t('Volume durability · RVOL · VWAP · ~options flow · K/7 confluence', '量持续性 · RVOL · VWAP · ~期权资金 · K/7汇聚') }}</span></a>{% endif %}
            {% if darkpool_enabled is not defined or darkpool_enabled %}<a href="{{ NP }}darkpool.html"><span class="submenu-icon submenu-icon-darkpool" aria-hidden="true"></span>{{ t('Dark Pool Desk', '场外暗池台') }}<span class="d">{{ t('Off-exchange volume · short ratio · ATS venues', '场外成交量 · 融券比率 · ATS场所') }}</span></a>{% endif %}
            <a href="{{ NP }}market_structure.html"><span class="submenu-icon submenu-icon-structure" aria-hidden="true"></span>{{ t('Market Structure', '市场结构') }}<span class="d">{{ t('GEX regime · machine flows · dispersion · weekly range', '做市商制度 · 机器资金 · 离散度 · 周度区间') }}</span></a>
          </div>
        </div>
```

Notes pinned so the builder does not re-derive them:
- Icon classes are 100% reused, zero new icon CSS: `submenu-icon-options` stays exactly
  where it was (the trigger + first-row position — only the href/label under it changes,
  from gex.html to options.html); `submenu-icon-dashboard` moves from
  options_screener.html (leaving) to gex.html (freed icon, reused, not new); every other
  icon is untouched.
- `leader_radar.html`, appearing immediately after this block in the file, is untouched.
- Do **not** touch `options_screener_enabled`/`flow_desk_enabled`/`flow_leaders_enabled`
  guard variables anywhere else in the codebase — the pages still render, they are simply
  no longer linked from this menu. If a future PR wants to also stop rendering them, that
  is a separate, unrelated decision this spec does not make.

### 1.3 Daily Movers relocation

Insert immediately after the existing `us_stocks.html` row (line 65) inside the **United
States** `nav-dd-menu` (before `stage_analysis.html`), verbatim copy and icon unchanged
from its current row (just relocated, not rewritten):

```html
        <a href="{{ NP }}movers.html"><span class="submenu-icon submenu-icon-stocks" aria-hidden="true"></span>{{ t('Daily Movers', '每日异动') }}<span class="d">{{ t('Free · biggest gainers & losers today · themes moving together', '免费 · 今日涨跌最大 · 联动主题') }}</span></a>
```

Placement reasoning (pinned, not left to the builder): Movers is stock-level content, so it
sits beside the Stock Dashboard rather than deeper in the menu near Strategies/News/Alerts.
This is the "US / markets group" placement the masterplan names, made concrete.

### 1.4 Sequencing note (do not resolve — just avoid it)

`_navlinks.html.j2` is also targeted by the crypto-cockpit program (its own W2, plan-only
as of this writing). That program adds a **new** top-level nav group; this diff only edits
the existing Options & Flow block. Semantic collision is nil; git conflict is likely if both
land the same week — whichever lands first, the other rebases. Do not pre-emptively touch
anything outside the two blocks named above.

---

## §2 Ticker search/typeahead

### 2.1 Behavior — exact parity with gex.html's `#gx-q`

Read from `site/gex.js:282-313` (`setupSearch`) and `site/gex.js:1373-1377` (the global `/`
binding). The new search reproduces this **exactly** — same match predicate, same keyboard
model, same mousedown-not-click row selection, same 150ms blur-close delay. This is not a
redesign of gex.html's search; it is the same behavior wearing `.oew-` classes.

| Behavior | Rule |
|---|---|
| Match predicate | `key.indexOf(q) === 0 \|\| key.indexOf(q) >= 0 \|\| en.toUpperCase().indexOf(q) >= 0` (prefix OR substring OR name-substring) — reproduced verbatim, including that it does **not** match against the ZH name (matching gex.html's own current behavior is parity; "improving" it is a different, out-of-scope change) |
| Result cap | 12 rows |
| Keyboard | `ArrowDown`/`ArrowUp` move a highlight index (clamped); `Enter` selects the highlighted row or the first if none highlighted; `Escape` closes the panel |
| Row selection | bound on `mousedown` with `preventDefault()`, not `click` — survives the input's own `blur` handler |
| Close timing | `blur` closes after a 150ms `setTimeout` (lets the mousedown above register first) |
| Global shortcut | `/` focuses the input, **guarded** two ways: (a) not while focus is already in an `INPUT`/`TEXTAREA`/`SELECT` (gex.html's existing guard) **and** (b) only while `#mode-ticker` carries `.active` (new — see §0.16) |
| Visible focus ring | `2px solid var(--oew-accent)`, `outline-offset:1px` (the workspace's standard, not gex.html's `--info` ring — this box lives inside `.oew`, so it inherits `.oew`'s focus-ring convention) |

### 2.2 Markup (goes inside `#mode-ticker`, as a sibling of the render target — §0.15)

```html
<section class="oew-mode" id="mode-ticker" role="tabpanel" aria-labelledby="tab-ticker">
  <div class="oew-tktoolbar">
    <div class="oew-tksearch">
      <span class="mag" aria-hidden="true">⌕</span>
      <input id="oew-tk-q" type="text" autocomplete="off"
        aria-label="Look up a ticker" aria-expanded="false" aria-controls="oew-tk-sugg" role="combobox"
        placeholder="Look up a ticker — SPY, NVDA, TSLA…" data-ph-zh="查询代码 — SPY、NVDA、TSLA…">
      <div class="oew-tksugg" id="oew-tk-sugg" role="listbox"></div>
    </div>
    <span class="oew-tkhint"><span class="l-en">press <kbd>/</kbd> to search</span><span class="l-zh">按 <kbd>/</kbd> 搜索</span></span>
  </div>
  <div id="oew-tk-body"><!-- renderTicker() targets THIS, never the section itself --></div>
</section>
```

`⌕` (U+2315) replaces gex.html's 🔎 emoji deliberately — this workspace's chrome uses no
emoji anywhere today (verified: zero emoji in the persistent chrome or any `.oew-` panel);
introducing one only in the search icon would be the one inconsistent glyph on the page.
The glyph is `aria-hidden`; the accessible name comes from the input's own `aria-label`.

### 2.3 Data source — reuse gex.html's manifest, do not build a second one

The suggestion list must search the same universe Ticker mode can actually render (every
name with a `site/gex/<T>.json`) — that is precisely `window.GEX_MANIFEST`, already baked
into `gex.html.j2` (`manifest_json` context var, built in `scripts/build_gex_board.py:168-
182`, shape `{key, en, zh, grp, regime, net_gex_bn, …}`). Rather than a second, possibly-
drifting universe, **`scripts/build_options_command.py` bakes the identical array into
`options.html.j2`** as `window.OEW_TICKER_MANIFEST`. Concretely: `build_gex_board.py`
already assembles this list in memory before writing `gex.html`; it should also write it to
a small shared JSON side-artifact (e.g. `site/gex/_manifest.json`) that
`build_options_command.py` reads and re-embeds — one producer, one array, two consumers.
This is a **data-plane wiring decision**, not a new derivation (§0.11 of the masterplan:
"no new arithmetic" is about signals, not about not duplicating an existing, already-
computed list across two pages that need the same one). Flagged here so the build lane
does not invent a second, divergent manifest.

### 2.4 CSS (new — added to `options.html.j2`'s own `<style>` block, `.oew-` prefixed)

```css
.oew-tktoolbar{display:flex;align-items:center;gap:var(--s3);flex-wrap:wrap;margin-bottom:var(--s4)}
.oew-tksearch{position:relative;flex:1 1 260px;max-width:400px}
.oew-tksearch .mag{position:absolute;left:13px;top:50%;transform:translateY(-50%);
  opacity:.55;font-size:14px;pointer-events:none;color:var(--muted)}
.oew-tksearch input{width:100%;padding:10px 13px 10px 36px;border:1px solid var(--hair);
  border-radius:var(--r-ctl);background:var(--tile);color:var(--text);
  font-size:13.5px;font-family:var(--font-ui)}
.oew-tksearch input::placeholder{color:var(--muted)}
.oew-tksearch input:focus-visible{outline:2px solid var(--oew-accent);outline-offset:1px;
  border-color:var(--oew-accent)}
.oew-tksugg{position:absolute;top:112%;left:0;right:0;min-width:300px;background:var(--panel);
  border:1px solid var(--hair);border-radius:var(--r-panel);
  box-shadow:0 10px 30px rgba(0,0,0,.25);padding:6px;display:none;z-index:20;
  max-height:340px;overflow-y:auto}
.oew-tksugg.on{display:block}
.oew-tksugg .row{display:flex;justify-content:space-between;gap:10px;padding:8px 11px;
  cursor:pointer;border-radius:8px;align-items:center}
.oew-tksugg .row:hover,.oew-tksugg .row.hl{background:var(--tile)}
.oew-tksugg .row b{font-family:var(--font-mono);font-weight:700}
.oew-tksugg .row .g{color:var(--ink-3);font-size:11.5px}
.oew-tkhint{font-size:11px;color:var(--ink-3);white-space:nowrap}
.oew-tkhint kbd{font-family:var(--font-mono);border:1px solid var(--hair);border-radius:4px;
  padding:1px 5px;background:var(--tile);font-size:10px}
@media (max-width:560px){ .oew-tkhint{display:none} }
```

---

## §3 The session filmstrip — the estate-wide signature

### 3.1 What it is, precisely

A compact SSR SVG (via a new `lib/illus.py` function, following the existing `illus()` /
`regime_tape()` construction pattern — **never Plotly**) drawing one session's net-premium
path across the session window, with tick marks where structure events fired. Appears in
exactly three homes (§3.5): Brief's session-character panel (W2 build, pinned here), Ticker
mode's "how the day traded" row (W1 build), gex.html's detail head (W1 build).

### 3.2 Real data grounding — every element below cites the exact field

Source: `site/session/<ROOT>.json` (`options_session.v1`, `engine/session_digest.py`,
merged PR #3975; data starts populating with tonight's nightly run — the schema exists
today, the files do not yet).

| Filmstrip element | Payload path | Notes |
|---|---|---|
| The plotted path | `arc[]` → each `{t, net}` (ignore `ncp`/`npp` — always `null` by design, see `session_digest.py:19-29`) | Downsampled to ≤80 points server-side already; no client resampling |
| Track denominator | `coverage.minutes` / `coverage.expected` | Full session width is the track; `arc`'s own time span is what's inked |
| Degrade sentence | `coverage.quality_en` / `.quality_zh` | Already-composed plain words: `"no intraday record for this session"` (0 minutes) / `"…covers the whole/most/only part of the session"` |
| Shape fragment | `arc_shape_en` / `arc_shape_zh` | One of 6 fixed fragments (`session_digest.py:607-614`), already written to follow "Premium " as a subject |
| Event ticks | `events[]` → each `{t, type, label_en, label_zh, …}` | 6 families: `flip_cross`, `call_wall_touch`, `put_wall_touch`, `premium_burst`, `hot_pocket`, `zero_dte_spike` — every one already carries its plain-word `label_en`/`label_zh` |
| Flip clause | `flip.crosses`, `flip.last_side` | Composed into the sentence per §3.4 |
| Session bounds | `coverage.session_window_et` | e.g. `"09:30–16:00 ET"` — used only for the corner labels, not for arithmetic |

### 3.3 Markup contract (what the SSR function must emit)

```html
<figure class="ilx oew-film" role="img" aria-label="Session premium arrival, 3 events"
  style="color:var(--oew-accent);--ilx-len:842;--ilx-h:64px">
  <svg viewBox="0 0 560 64" preserveAspectRatio="none" aria-hidden="true">
    <line class="oew-film-track" x1="0" y1="32" x2="560" y2="32"/>
    <line class="oew-film-closecap" x1="560" y1="14" x2="560" y2="50"/>
    <path class="ilx-path oew-film-ink" d="M0 40 L38 39 L… "/>
    <circle class="ilx-dot oew-film-dot" cx="560" cy="22" r="3.2"/>
    <line class="ilx-event-tick oew-film-tick" x1="211" y1="10" x2="211" y2="54"/>
    <!-- one tick per event -->
  </svg>
  <span class="oew-film-d oew-film-d0 mono"><span class="l-en">09:30</span></span>
  <span class="oew-film-d oew-film-d1 mono"><span class="l-en">16:00</span></span>
  <span class="ilx-event oew-film-ev" style="--x:37.7%" tabindex="0" role="note"
    data-tip-en="price crossed the gamma flip level" data-tip-zh="价格穿越 gamma 翻转价位"
    aria-label="price crossed the gamma flip level"><i></i></span>
  <!-- one .oew-film-ev per event -->
</figure>
```

Honest-null variant (`coverage.minutes === 0`) — **no ink, no ticks, no dot**, only the
flat track and the label, matching the `_null_fragment` idiom but with the session-specific
sentence rather than the generic "No history yet":

```html
<figure class="ilx oew-film oew-film-null" role="img" aria-label="No intraday record for this session"
  style="color:var(--oew-accent);--ilx-h:64px">
  <svg viewBox="0 0 560 64" preserveAspectRatio="none" aria-hidden="true">
    <line class="oew-film-track" x1="0" y1="32" x2="560" y2="32"/>
    <line class="oew-film-closecap" x1="560" y1="14" x2="560" y2="50"/>
  </svg>
  <span class="oew-film-empty"><span class="l-en">No intraday record for this session</span><span class="l-zh">本交易日没有盘中记录</span></span>
</figure>
```

**Geometry rules pinned for the implementer:**
- `x` position of every point/tick = `(minutes since session open) / (session length in
  minutes) * 560`, using `coverage.session_window_et`'s bounds — **not** array-index
  spacing (index spacing would silently misrepresent a mid-session gap as compressed time,
  the same class of bug `regime_tape`'s own docstring warns against for its date axis).
- `y` position of the ink = the `net` series scaled to its own min/max within `[10, 54]` of
  the 64-tall viewBox (8px inset top/bottom, matching `_PAD_T`/`_PAD_B`) — a **shape**, not
  an absolute value axis; no gridlines, no y-axis labels (ilx law: sparkline-grade, glance-
  tier).
- The track (`.oew-film-track`) spans the **full** viewBox width always, regardless of how
  much of it the ink covers — this IS the coverage disclosure; no separate hatch overlay is
  needed because a gap already reads as bare track (§0 decision, simpler than a second
  hatch pattern and equally honest, including for mid-session gaps `coverage.gaps` names).
- The close-cap (`.oew-film-closecap`) is a static vertical mark at `x=560` always present
  — it marks the session's own boundary independent of data completeness ("the close caps
  it," masterplan §3, made literal).
- Reduced motion: `.oew-film` inherits the existing `.ilx` `@media (prefers-reduced-motion:
  reduce)` rule (doctrine §5/§1.5 already law) — ink lands at final state, no draw-on-
  reveal, no dot overshoot.

### 3.4 The accompanying sentence — composed from payload fields only

Pinned assembly logic (no new signal, only string composition of already-worded fields):

```
if coverage.minutes == 0:
    sentence = coverage.quality_en / coverage.quality_zh   # verbatim, no prefix
elif coverage.minutes / coverage.expected < 0.70:
    sentence = coverage.quality_en + " — Premium " + arc_shape_en + "."
             / coverage.quality_zh + "——" + "权利金" + arc_shape_zh + "。"
else:
    sentence = "Premium " + arc_shape_en + "." + flip_clause_en
             / "权利金" + arc_shape_zh + "。" + flip_clause_zh

flip_clause (only when flip.crosses > 0; omitted entirely at 0):
    " Crossed the flip once, closed {above/below} it."       (crosses == 1)
    " Crossed the flip {N} times, closed {above/below} it."  (crosses > 1)
    zh: "，穿越翻转位{一次/N次}，收于其{上方/下方}。"
    {above/below} from flip.last_side ("above" → 上方 / "below" → 下方)
```

Worked example (matches the masterplan's own illustrative sentence, now traced to real
fields): `arc_shape_en = "built steadily in one direction and stayed"`, `flip.crosses = 2`,
`flip.last_side = "above"` → **"Premium built steadily in one direction and stayed.
Crossed the flip twice, closed above it."** ZH: **"权利金全天单向累积并维持。穿越翻转位两
次，收于其上方。"**

### 3.5 The three homes

| Home | Panel title | Placement | Build wave |
|---|---|---|---|
| Brief mode | "What kind of day" / "怎样的一天" | New shelf, directly after the posture console, before the close line — per masterplan §5.2 order | W2 (markup pinned here, not built in W1) |
| Ticker mode | "How the day traded" / "今日如何交易" | New `.oew-panel`, immediately after the name-header panel, before "The map" (§4) | **W1** |
| gex.html detail head | (no new panel title — sits directly under the existing verdict hero, above the price ladder) | **W1** |

Brief's filmstrip uses **SPY's** session record as the market proxy (pinned choice, not
left open): SPY is already this workspace's `DEFAULT_TICKER` and the most complete/liquid
name in the digest's coverage. The panel subtitle says so in plain words rather than
implying a magic whole-market composite: *"SPY's session, read as the market's" /
"以SPY的交易时段代表大盘"*. This avoids inventing a new cross-name fused series (masterplan
§12: no fused composites).

**Ticker mode markup (W1):**

```html
<div class="oew-panel">
  <div class="oew-phead">
    <h2 class="oew-ph-title">{{ t('How the day traded', '今日如何交易') }}</h2>
  </div>
  <div class="oew-pbody">
    <!-- filmstrip <figure> from §3.3, inserted then window.ilxReveal(host) called -->
  </div>
  <div class="oew-pfoot">
    <!-- NO stance chip (§0.13 ruling) — this is not the verdict surface; the
         Name-header hero above already carries the page's one data-verdict-surface -->
    <span>{{ t('A record of how today unfolded, not a forecast for tomorrow.', '记录今日走势，不预测明日。') }}</span>
    <span class="oew-asof mono"><!-- session_date --></span>
  </div>
</div>
```

**gex.html detail head placement** — one line added to `renderDetail()`
(`site/gex.js:369-386`), between `heroHTML(V)` and `ladderCardHTML()`:

```js
+ (sessionFilmstripHTML(cur.session) || '')   // '' when no site/session/<T>.json fetched yet
+ ladderCardHTML()
```

`selectSymbol()` gains a third parallel fetch, `fetch("session/" + key + ".json")`
alongside the existing gex/flow fetches (`.catch(() => null)`, same pattern as `loadFlow`)
— consistent with how Ticker mode already fetches gex+flow in parallel. No panel chrome
here (no title, no stance, no footer) — it sits as a compact strip directly under the
verdict hero, the same way the masterplan names it ("gex.html's detail head").

---

## §4 The map — wall-persistence cross-check (enhancement, not a new panel)

`wall_persistence` (PR #3976) is deliberately **not** its own panel. It is an independent,
signing-free cross-check on the SAME two levels "The map" already shows (Ceiling/Floor),
so it belongs on those rows, not in a new place a reader has to learn.

**Checked against the §0.13 verdict-law ruling and found not applicable:** the only new
markup this section adds is the `.oew-wcheck` chip below, already ruled "not a stance and
not a pip" (§0.6) — it was never a stance-chip candidate. "The map" panel itself is
unchanged by this wave and carries no stance chip of its own (its footer is one caveat
sentence — "Walls are measured from this close, so price always starts inside the band." —
plus an as-of stamp, no `.oew-stance`; verified against `mockups/oip_w1/w1_mockup.html`).
Nothing in this section changed as a result of that ruling; this note exists so a reader who
starts here does not have to re-derive that from §0.13.

### 4.1 Field grounding

`gx.wall_persistence.call_side` / `.put_side`, each `{level, sessions_at_level,
matches_board_wall, board_wall, note_en?, note_zh?}` (`engine/gex_state.py` §"wall
persistence", PR #3976). `matches_board_wall` is `true`/`false`/`null` — `null` when either
side is unreadable (§0.6: renders nothing). The whole block may be **absent** from the
payload (coverage gap) — the enhancement below simply does not render, and the existing
level rows are unaffected (§0's back-compat law already binds this — nothing here can make
a level row disappear or change its own values).

### 4.2 Markup — one small chip appended to the Ceiling and Floor `lvRow()` calls only

(Flip and Magnet have no open-interest-wall equivalent — the chip does not appear on those
two rows.)

```html
<span class="oew-wcheck oew-wcheck-yes" data-tip-en="The open-interest wall (a signing-free count of contracts, independent of the dealer-gamma model) sits at the same strike as this dealer-gamma wall — two different measurements agree." data-tip-zh="未平仓量墙位（合约数量统计，不依赖做市商模型的独立测算）与该做市商Gamma墙位落在同一行权价 — 两种独立测算结果一致。">✓ <span class="l-en">confirmed by open interest</span><span class="l-zh">未平仓量印证</span></span>

<span class="oew-wcheck oew-wcheck-no" data-tip-en="The open-interest wall sits at a different strike ($X) than this dealer-gamma wall. Two independent measurements, two different answers — worth knowing, not a contradiction to resolve." data-tip-zh="未平仓量墙位（$X）与该做市商Gamma墙位不在同一行权价 — 两种独立测算给出不同答案，值得留意，但并非需要解决的矛盾。">
  <span class="l-en">open interest disagrees</span><span class="l-zh">未平仓量不一致</span></span>
```

`matches_board_wall === null` or the block absent → **render neither span** (no chip at
all on that row — silence, not a "no data" placeholder; the row already works without it).

### 4.3 CSS

```css
.oew-wcheck{display:inline-flex;align-items:center;gap:3px;font-size:10.5px;font-weight:600;
  margin-left:var(--s2);padding:2px 7px;border-radius:var(--r-pill);white-space:nowrap}
.oew-wcheck-yes{color:var(--oew-accent);background:color-mix(in srgb, var(--oew-accent) 12%, transparent)}
.oew-wcheck-no{color:var(--ink-3);background:var(--tile)}
```

Neither variant borrows `--up`/`--down` — this is a data-source agreement fact, not a price
call, and both colors are the workspace's own neutral pair (§0.6).

### 4.4 The optional `net_gex_pctile` addendum

Present on roughly 10 of 555 names today (§0.18) — too rare for its own panel. When
present, it becomes one extra line in the **"Where positions built"** panel's footer
(§5.1), reusing its own already-composed `note_en`/`note_zh` verbatim:

```html
<div class="oew-pb-pctile"><span>{{ t('Also on file:', '另有记录：') }}</span> <!-- note_en/zh --></div>
```

When absent (the overwhelming majority of names), this line does not render — no "N/A", no
placeholder row.

---

## §5 Ticker mode — full panel order and the three empty states

### 5.1 Revised Ticker-mode order (W1)

Existing panels keep their exact current markup (unchanged, verified against
`options.html.j2:1120-1264`); new panels are marked **NEW**. Order, top to bottom:

1. Name header (spot, regime headline, stance, expected range) — unchanged markup, **plus
   one new attribute** (see below): this panel's stance-chip row is the wave's sole
   `data-verdict-surface`
2. **NEW — "How the day traded"** (the filmstrip, §3.5)
3. "The map" (walls/flip/magnet) — unchanged rows, **enhanced** with the wall-check chip
   (§4)
4. **NEW — "Rich or cheap"** (§5.2)
5. **NEW — "Where positions built"** (§5.2)
6. Three reads (tape/mood/lean) — unchanged
7. **NEW — "What the move is worth"** (§5.3, empty state)
8. **NEW — "Expiration pressure"** (§5.3, empty state)
9. "Today's measured flow" — unchanged
10. Raw structure shelf (`<details>`, closed) — unchanged
11. Terminal handoff CTA — unchanged

Reasoning pinned: settled positioning facts (map, rank, ΔOI) come before the compact reads
row (which stays exactly where doctrine already validated it); the two always-or-usually-
empty panels sit together, late, near the flow/shelf material they're conceptually closest
to (both are "what we'd tell you if the ledger existed yet") — this keeps the top of the
page dense with real information and the empty states from interrupting it.

**Where the single `data-verdict-surface` marker lives (§0.13 ruling, made concrete):** add
the bare attribute `data-verdict-surface` (boolean — no value) to the Name-header panel's
existing stance-row wrapper, i.e. its `.oew-ic-foot` div (the row already holding the
`.oew-stance` chip and the expected-range text) becomes
`<div class="oew-ic-foot" data-verdict-surface style="margin-top:12px">` — one attribute
added to one already-existing element, nothing else about this panel changes. This is the
only element in Ticker mode's five new/enhanced panels that keeps its stance chip; it is
therefore also the only element in scope for the marker. `mockups/oip_w1/w1_mockup.html`
carries this attribute verbatim (search `data-verdict-surface`).

Scoped to Ticker mode only — whether Brief mode's own hero (W2, not built yet) or gex.html's
own pre-existing verdict hero already carries this marker, or should gain it, is not decided
here: gex.html's hero is untouched by W1 (§3.5 adds only the filmstrip below it), so this
spec neither asserts its current state nor adds the attribute to it. Each surface's own
build wave owns adding its own single marker.

### 5.2 "Rich or cheap" — real panel, young-window honesty (not an empty state — §0.3)

Field grounding: `gx.summary.iv_rank` → `{rank_pct, band, n_days, low_confidence,
horizon}` (`engine/gex_model.py:616-627`). Band words reuse gex.html's own existing
mapping (`site/gex.js:76-80`) verbatim — do not invent new band words.

Copy note: the masterplan's own illustrative sentence ("cost more than 82 of the last 100
sessions") drops the `%` sign because it anchors the denominator at exactly 100 — a
convention that only reads honestly when the real sample size *is* 100. `n_days` here is
whatever the store actually holds (today, always under 40; §0.3), so this spec keeps the
`%` sign explicit and states the real `n_days` beside it rather than borrowing a "days out
of 100" phrasing the data does not support.

```html
<div class="oew-panel">
  <div class="oew-phead">
    <h2 class="oew-ph-title">{{ t('Rich or cheap?', '偏贵还是偏便宜？') }}</h2>
    <div class="oew-ph-right"><span class="oew-help" tabindex="0" role="button"
      data-tip-en="Where today's 30-day implied volatility sits versus this name's own recent daily readings. This is a SHORT window (about 40 trading days) — not a full-year IV rank. A young or thin window is flagged, not hidden."
      data-tip-zh="今日30日隐含波动率相对该标的近期每日读数的位置。这是一个较短窗口（约40个交易日）— 并非完整一年的隐波分位。窗口较短或较薄时会明确标注，而非隐藏。">?</span></div>
  </div>
  <div class="oew-pbody">
    <div class="oew-rich-track" role="img" data-tip-en="…" data-tip-zh="…">
      <i class="oew-rich-pip on"></i><i class="oew-rich-pip on"></i><i class="oew-rich-pip"></i><i class="oew-rich-pip"></i><i class="oew-rich-pip"></i>
    </div>
    <p class="oew-tk-say">
      <span class="l-en">Options on NVDA cost more than <b class="mono">43%</b> of the last <b class="mono">37</b> sessions we have on file.</span>
      <span class="l-zh">NVDA 期权价格高于我们记录的近 <b class="mono">37</b> 个交易日中的 <b class="mono">43%</b>。</span>
    </p>
  </div>
  <div class="oew-pfoot">
    <!-- NO stance chip (§0.13 ruling) — the Name-header hero above carries the page's
         one data-verdict-surface; this footer is a fact about the reading, not a verdict -->
    <span>{{ t('Still building toward a full year of history — read this as a rough placement, not a settled rank.', '仍在积累完整一年的历史 — 请视为粗略定位，而非确定分位。') }}</span>
    <span class="oew-asof mono"><!-- meta.asof --></span>
  </div>
</div>
```

Pip fill: `round(rank_pct / 100 * 5)` filled pips of 5 (same `.oew-pip`-family idiom as the
posture console — reuse `.oew-pip`/`.oew-pip.on`, renamed `.oew-rich-pip` only because it
lives outside `.oew-console` and needs its own sizing, not different behavior). When
`low_confidence` is true (`n_days < 20`), the pip track is replaced with the existing
plain-word chip gex.html already uses — **"history building — Nd" / "历史积累中 — N天"**
— never a track with too few days behind it to mean anything (matches gex.html's own
`ivrHtml` branch exactly, `site/gex.js:776-777`).

When `gx.summary.iv_rank` is absent entirely (possible for thin-chain names — `iv_rank()`
returns `None` under 5 history days), the panel falls to the `.oew-notyet` treatment
(§5.4), with copy naming the specific reason: *"Not enough price history on file yet for
this name to place today's cost against its own past."*

**"Where positions built" panel:**

```html
<div class="oew-panel">
  <div class="oew-phead">
    <h2 class="oew-ph-title">{{ t('Where positions built', '仓位在何处建立') }}</h2>
    <span class="oew-ph-sub">{{ t('open-interest change between the last two chain snapshots', '最近两次期权链快照之间的未平仓量变化') }}</span>
  </div>
  <div class="oew-pbody">
    <div class="oew-pb">
      <div class="oew-pb-col">
        <div class="oew-pb-h">{{ t('Built', '新增') }}</div>
        <!-- up to 3 rows, sorted desc by oi_delta -->
        <div class="oew-pb-row"><span class="k mono">525P</span><span class="bar" style="width:78%"></span><span class="v mono">+196,512</span></div>
      </div>
      <div class="oew-pb-col">
        <div class="oew-pb-h">{{ t('Unwound', '平仓') }}</div>
        <div class="oew-pb-row"><span class="k mono">660P</span><span class="bar unwind" style="width:41%"></span><span class="v mono">−18,624</span></div>
      </div>
    </div>
  </div>
  <div class="oew-pfoot">
    <!-- NO stance chip (§0.13 ruling) — the Name-header hero above carries the page's
         one data-verdict-surface; this footer is a fact about the reading, not a verdict -->
    <span>{{ t('A count of contracts opened or closed, not a direction call.', '合约新增或平仓的计数，并非方向判断。') }}</span>
    <span class="oew-asof mono"><!-- oi_delta_clusters.latest_snapshot --></span>
  </div>
</div>
```

- Row label = `K` + first letter of `right` (`525P`, `660C`) — mono. Bar width = `|oi_delta|
  / max(|oi_delta| across the up-to-4 rows THIS side carries)`, i.e. each side scales
  against its own max, matching the sector-bar idiom's own "shared scale" rule applied
  per-column (there is no single shared scale between builds and unwinds — they are not
  comparable magnitudes by construction). Value column = `oi_delta` signed, mono
  (`+196,512` / `−18,624`).
- **Take the first 3 of each side's up-to-4 rows** — the payload's `CLUSTER_TOP_N=4`, this
  panel shows 3 (masterplan §5.1's explicit "top-3" language; a simple `.slice(0,3)`, no
  new sorting — the arrays arrive pre-sorted).
- `spot_note_en`/`spot_note_zh` (cross-source price divergence, fires on ~21% of payloads
  per PR #3976) surfaces as the panel's `?` hover receipt, never inline prose — it is
  exactly the kind of provenance detail Tier 2 exists for.
- Per-name coverage gap (the ~46% of names without a `oi_delta_clusters` block, or one of
  its degraded states — `same_vintage`, `no_matched_contracts`, `one_snapshot`, etc.): the
  panel renders the block's own `note_en`/`note_zh` **verbatim** as the panel body (replace
  the two-column layout with a single plain sentence) — never a generic "no data" fallback,
  because the engine has already composed the exact right sentence for each of the ~7
  distinct coverage states (§0.18's PR body table). No stance chip renders in this state
  either (§0.13 ruling) — the engine's own composed sentence already says plainly that
  there is nothing here to watch; a chip would restate that as a second decision element.

### 5.3 The two full empty-state panels

Both use the identical `.oew-notyet` shell (§5.4) — the difference is only the copy and the
ghost-preview shape, since each hints at a genuinely different eventual visual.

**"What the move is worth"** (EM calibration — `site/em_calibration.json` does not exist;
verified absent):

```html
<div class="oew-panel">
  <div class="oew-phead"><h2 class="oew-ph-title">{{ t("What the move is worth", '本次波幅是否值得') }}</h2></div>
  <div class="oew-pbody">
    <div class="oew-notyet">
      <div class="oew-notyet-ghost oew-notyet-cone" aria-hidden="true"></div>
      <p class="oew-notyet-say">
        <span class="l-en">The expected move itself is in the header above. What we don't yet track is whether that number is usually <em>right</em> — we're building a nightly record that grades each session's implied move against what actually happened.</span>
        <span class="l-zh">预期波幅本身已显示在上方页头。我们尚未跟踪的是这个数字是否<em>通常准确</em> — 正在建立一份每夜记录，用以对照隐含波幅与实际结果。</span>
      </p>
    </div>
  </div>
  <div class="oew-pfoot">
    <!-- NO stance chip (§0.13 ruling) — "nothing here to act on" is already the honest
         answer in plain words; a chip does not need to say it a second time, and the
         Name-header hero above already carries the page's one data-verdict-surface -->
    <span>{{ t('Not measured yet — nothing here to act on.', '尚未测量 — 此处暂无可据以行动的内容。') }}</span>
  </div>
</div>
```

**"Expiration pressure"** (E7 / S-FRONT-CHARM display surfacing — verified zero site
consumers of `S-FRONT-CHARM`/`S-VANNA-RELIEF` anywhere in `templates/`):

```html
<div class="oew-panel">
  <div class="oew-phead"><h2 class="oew-ph-title">{{ t('Expiration pressure', '到期压力') }}</h2></div>
  <div class="oew-pbody">
    <div class="oew-notyet">
      <div class="oew-notyet-ghost oew-notyet-bar" aria-hidden="true"></div>
      <p class="oew-notyet-say">
        <span class="l-en">Not measured yet. The idea: how much of this name's open interest rolls off in the next few days, and whether that concentration tends to feed on itself into expiry.</span>
        <span class="l-zh">尚未测量。设想中的内容：该标的近几日到期的未平仓量占比，以及该集中度在到期前是否会自我强化。</span>
      </p>
    </div>
  </div>
  <div class="oew-pfoot">
    <!-- NO stance chip (§0.13 ruling) — see the note on the other empty state above -->
    <span>{{ t('Not measured yet — nothing here to act on.', '尚未测量 — 此处暂无可据以行动的内容。') }}</span>
  </div>
</div>
```

Both explicitly avoid every falsifier/refutation register word (doctrine ban) and avoid
"coming soon" marketing language — they say plainly what the panel is *for* and that it
does not exist yet, which is the honest, useful form of an empty state per the doctrine's
own worked example (Turn Watch, before/after). Neither carries a stance chip (§0.13 ruling)
— "not measured yet — nothing here to act on" already discloses the honest nothing-yet in
plain words; the `st-ignore` chip a prior draft placed here was a second, redundant decision
element saying the same thing twice.

### 5.4 `.oew-notyet` — the shared first-class empty-state shell

The instruction is explicit: make emptiness a first-class design element, not an
afterthought. A one-line `<p class="oew-empty">` (the existing generic pattern, used
correctly elsewhere for "no rows matched a filter") reads as apologetic on a panel whose
entire content is the empty state. `.oew-notyet` instead pairs the plain sentence with a
**dashed ghost preview** of the eventual shape — legible as "this is what will draw here,"
never mistakable for a real, zeroed-out reading (§0.7: dashed, never solid).

```css
.oew-notyet{display:flex;align-items:center;gap:var(--s5);padding:var(--s2) 0}
.oew-notyet-ghost{flex:none;width:96px;height:56px;border:1.5px dashed var(--hair);
  border-radius:var(--r-ctl);background:
    repeating-linear-gradient(135deg, var(--hair) 0 1px, transparent 1px 7px);
  opacity:.55}
.oew-notyet-cone{clip-path:polygon(0% 46%, 0% 54%, 100% 8%, 100% 92%)}
.oew-notyet-bar{clip-path:polygon(0% 70%,22% 70%,22% 30%,44% 30%,44% 55%,66% 55%,66% 15%,88% 15%,88% 45%,100% 45%,100% 100%,0% 100%)}
.oew-notyet-say{margin:0;font-size:12.5px;line-height:1.55;color:var(--ink-2);max-width:56ch}
.oew-notyet-say em{color:var(--text);font-style:normal;font-weight:600}
@media (max-width:560px){ .oew-notyet{flex-direction:column;align-items:flex-start;gap:var(--s3)} }
```

The two ghost shapes are silhouettes of what will eventually render there (a widening cone
for the EM calibration band; a front-loaded bar for expiration concentration) — legible as
"shape," not as fabricated data (no numbers, no axis, no scale — purely a diagonal-hatch
silhouette, distinct at a glance from any real chart on the page, including the filmstrip's
own hatch-free honest-track treatment).

---

## §6 Declared caps + LEX stances

### 6.1 Scanner — fix the undeclared-cap defect (§0.20)

Change the existing subtitle line in `renderScanner()` from:

```js
'<span class="oew-ph-sub">' + bi(rows.length + ' names, sorted by premium', rows.length + ' 个标的，按权利金排序') + '</span>'
```

to a declared-cap sentence plus a link, both driven by the live `rows.length` (never a
hardcoded number — the masterplan's own "384" is already stale at 403 today, proof that a
literal would drift):

```js
'<span class="oew-ph-sub">' + bi('Top 200 by premium, sorted', '按权利金排序，前200') + '</span>'
+ '<a class="oew-ph-more" href="options_screener.html">' + bi('Open the full screener for all ' + rows.length, '打开完整筛选台，查看全部 ' + rows.length) + ' ↗</a>'
```

`.oew-ph-more` is a new small link class for the panel-header-right area:

```css
.oew-ph-more{font-size:11px;font-weight:600;color:var(--oew-accent);text-decoration:none;
  white-space:nowrap;margin-left:auto}
.oew-ph-more:hover{text-decoration:underline}
.oew-ph-more:focus-visible{outline:2px solid var(--oew-accent);outline-offset:2px;border-radius:3px}
```

Word budget check: subtitle "Top 200 by premium, sorted" = 5 words ≤ 14; link text scales
with the live count but stays a single short clause.

### 6.2 Leaders — declare both board caps from the rendered arrays' own length (§0.19)

**Corrected post-build (adversarial review round 2 on PR #4123)** — the worked example
below originally read `L.board_a_total || A.length`, which is wrong: `board_a_total` is a
pre-cap count (verified `130` against a 25-row `board_a`) and would have told a reader the
full board held 130 names when only 25 were ever reachable at `flow_leaders.html`.

Board A subtitle changes from the current unconditional sentence to include the cap. The
denominator must equal what `flow_leaders.html` actually renders for board A —
`L.board_a`'s own length (the builder's post-`_BOARD_CAP` array), never the pre-cap
`L.board_a_total`:

```js
var boardAAll = L.board_a || [];
'<span class="oew-ph-sub">' + bi(
  'top 12 of ' + boardAAll.length + ', by recurrence',
  '按出现频率排序，前12（共 ' + boardAAll.length + '）') + '</span>'
'<a class="oew-ph-more" href="flow_leaders.html">' + bi('Open the full boards', '打开完整榜单') + ' ↗</a>'
```

Board B subtitle, same pattern — but its own numerator is already filtered by
`B5_flow_inflect` (the corrected #3496 admission rule), and `flow_leaders.html` applies the
identical filter before rendering, so the denominator must be the FILTERED length, never
`L.board_b`'s raw length and never `L.board_b_total` (which is both unfiltered AND pre-cap):

```js
var boardBFiltered = (L.board_b || []).filter(function(r){ return r.B5_flow_inflect; });
// ... 'top 12 of ' + boardBFiltered.length + ', most recent first' ...
```

The two totals coincide today (`24`/`24`) only because every `board_b` row on file
currently passes the filter — they diverge the moment it doesn't, which is exactly why the
raw `L.board_b_total` field must never be read for this sentence.

The ETF strip carries no cap (it already shows every row it has — `etf.length` is not
truncated anywhere in `renderLeaders()`), so it gets no declared-cap addendum.

### 6.3 LEX stances — current, verified state (no build action — §0.2)

| EN | ZH | LEX line (`engine/i18n.py`) |
|---|---|---|
| Act | 立即行动 | 585 |
| Get ready | 做好准备 | 583 |
| Watch — don't chase | 观察—勿追高 | 582 |
| Protect gains | 保护利润 | 584 |
| Stand aside | 暂时观望 | 586 |
| Ignore | 忽略 | 587 |

Reproduced here so this spec is self-contained and so a future reader does not re-open
`WORKSPACE_DESIGN_SPEC.md` §5.0's now-stale claim. No `engine/i18n.py` diff ships with W1.

---

## §7 Payload fetch map (additions to the base spec's §6 table)

| Mode | When | New sources this wave | Cache |
|---|---|---|---|
| Ticker | first activation + on ticker change | `site/gex/<T>.json` (unchanged) · `site/flow/<T>.json` (unchanged) · **`site/session/<T>.json`** (new, `.catch(() => null)`) | per ticker |
| chrome (baked) | render time | **`site/gex/_manifest.json`** (new side-artifact, §2.3) embedded as `window.OEW_TICKER_MANIFEST` | n/a |

`gex.html` gains the same third parallel fetch (`session/<T>.json`) inside `selectSymbol()`
(§3.5). Both new fetches are additive and `.catch(() => null)` — a 404 (a name outside the
digest's coverage, or before tonight's first nightly run populates the store) degrades the
filmstrip to its honest-null variant and changes nothing else on the page.

---

## §8 Interaction inventory (additions)

| Trigger | Element | Behaviour |
|---|---|---|
| keydown `/` | document | focus `#oew-tk-q`, only when not already in an editable field AND `#mode-ticker` is the active mode |
| input / focus | `#oew-tk-q` | render/re-render the suggestion list (§2.1) |
| keydown ArrowDown/Up/Enter/Escape | `#oew-tk-q` | move highlight / select / close (§2.1) |
| mousedown | `.oew-tksugg .row` | select that ticker, clear the input, close the list |
| blur | `#oew-tk-q` | close the list after 150ms |
| hover/focus | `.ilx-event` (filmstrip ticks) | LENS popover naming the event (`label_en`/`label_zh`) |
| hover/focus | `.oew-wcheck` | LENS popover with the full cross-check receipt |
| click | `.oew-ph-more` | navigate to the standalone full page (screener / flow_leaders), same tab |

`prefers-reduced-motion: reduce` — filmstrip inherits the existing global `.oew *` rule
(`options.html.j2:505-507`, already disables all animation/transition inside `.oew`); no
new reduced-motion rule needed, only confirmation that `.oew-film`'s draw-on-reveal (via
shared `.ilx` classes) is already covered by `docs/ILLUSTRATIONS.md`'s own reduced-motion
law (item 6) plus the page-level `.oew *` blanket rule as a second, redundant guard.

---

## §9 Responsive

| Breakpoint | Change |
|---|---|
| ≤560px | `.oew-tkhint` ("press / to search") hides — a phone keyboard has no `/` shortcut worth advertising; the search box itself stays full-width |
| ≤560px | `.oew-pb` (build/unwind columns) stack to 1 column, "Built" above "Unwound" |
| ≤560px | `.oew-notyet` stacks the ghost above the sentence instead of side-by-side |
| all widths | the filmstrip's `viewBox="0 0 560 64"` with `preserveAspectRatio="none"` already stretches correctly to any container width (the standard ilx contract) — no special mobile case needed |

---

## §10 Doctrine compliance

| Law | How this design satisfies it |
|---|---|
| Tier 1 = state + stance | Every new panel discloses its state and the reader's stance toward it in plain words — as a stance *chip* only on the one panel that is this read's decision element (the Name-header hero), and as its own caveat or nothing-yet sentence everywhere else (§0.13); the content requirement is satisfied by prose where the chip is not |
| Verdict law (`OIP_MASTERPLAN.md` §3) | Exactly one decision element survives per Ticker-mode read — the Name-header hero's stance chip, this wave's sole `data-verdict-surface` (§0.13, §5.1 marker placement). Every new shelf below it — filmstrip, rich-or-cheap, where-positions-built, both empty states — adds facts, never a second verdict |
| Plain words | Every new string is authored plain; every payload-sourced note (`note_en`, `arc_shape_en`, `coverage.quality_en`) was already written plain by its own engine module — reused, not translated a second time |
| Numbers carry meaning | IV rank rides the same 5-pip fill-track as the posture console; ΔOI bars are pure length + a labeled mono value; the filmstrip's track is the coverage denominator itself |
| Word budgets | Titles ≤4 words ("Rich or cheap?", "Where positions built", "How the day traded", "What the move is worth", "Expiration pressure" — 2–4 words each); subtitles ≤14; one footer sentence; one as-of |
| Honesty survives translation | Every new string ships as a pinned EN/ZH pair here; no English state names inside ZH copy |
| Nulls in plain words | Three distinct null registers, each honest and distinct: the filmstrip's session-absence, the positions-built per-name coverage gap (payload's own composed sentence), and the two fully-not-built panels (plain "not measured yet," no false urgency) |
| Direction claims | Filmstrip ink and ΔOI bars both deliberately avoid `--up`/`--down` — neither is a sanctioned direction instrument (§0.5, §0.8 of the masterplan) |
| No new fused scores | Every new number traces to one existing engine field; the only new "computation" in any template is string concatenation of already-composed sentence fragments (§3.4) |

**Banned-vocabulary self-check (method inherited from the base spec — strip tags/scripts/
tips, grep the same 40-term list plus this wave's own slugs).** Terms specific to this
wave's payloads that must never leak into visible copy: `oi_delta_clusters`,
`wall_persistence`, `net_gex_pctile`, `same_vintage`, `matches_board_wall`, `low_confidence`,
`arc_shape` (the tag, not its EN/ZH twin), any bare event `type` string (`flip_cross` etc.
— only `label_en`/`label_zh` may render), `GEX_MANIFEST`/`OEW_TICKER_MANIFEST` (variable
names). All of §2–§6's markup above was authored against this list; the build lane's own
§0-gate sweep (masterplan §0.5) re-verifies on the real rendered page.

---

## §11 The 5-second test (per new Tier-1 panel)

Transcribed here; reproduced in the PR body per the masterplan's §0.3 gate.

| Panel | Cold-read answer |
|---|---|
| How the day traded (filmstrip) | "This shows how today's options activity built up over the day, with marks where something notable happened — it's a record of what already happened, not a signal to act on." |
| The map, wall-check chip | "An independent open-interest count agrees (or disagrees) with the modeled wall — a confidence check on a level I'm already looking at, nothing to do differently." |
| Rich or cheap? | "Today's options are priced high/low versus the last ~40 days — worth knowing before I pay up for protection or sell premium, but the history behind it is still short." |
| Where positions built | "These are the strikes where option positions grew or shrank the most since the last snapshot — tells me where attention concentrated, not which way price will go." |
| What the move is worth (empty) | "We're not yet tracking whether the expected move is usually accurate — nothing to act on here yet." |
| Expiration pressure (empty) | "We're not yet tracking how much open interest expires soon — nothing to act on here yet." |

---

## §12 Files the build lane touches

**Edit:**
- `templates/_navlinks.html.j2` — §1 diff (Options & Flow block + Movers relocation)
- `templates/options.html.j2` — §2 (search toolbar + `#oew-tk-body` split), §3.5 (filmstrip
  panel + JS insertion + `renderTicker` signature gains a `session` param), §4 (wall-check
  chip in `lvRow()` calls), §5 (five new panel-render functions + reordering
  `renderTicker`'s concatenation), §6.1/§6.2 (Scanner/Leaders subtitle + cap link), new CSS
  in the page's own `<style>` block (§2.4, §4.3, §5.4, §6.1)
- `templates/gex.html.j2` / `site/gex.js` — §3.5 (third parallel fetch in `selectSymbol()`,
  one line in `renderDetail()`)
- `scripts/build_gex_board.py` — §2.3 (write `site/gex/_manifest.json` side-artifact)
- `scripts/build_options_command.py` — §2.3 (read and embed `OEW_TICKER_MANIFEST`); no
  other context-var changes needed (`counts`, `sess`, `posture` etc. are all unchanged)
- `lib/illus.py` — §3.3 (new SSR function producing the filmstrip markup contract exactly)
- `templates/illus.css` + `site/illus.css` (byte-paired) — new `.oew-film-*`/`.ilx-*`
  filmstrip-specific rules, if any beyond what's already generic in the shared file

**No edit needed (verified, do not touch):**
- `engine/i18n.py` — LEX already complete (§0.2, §6.3)
- `templates/_options_workspace_banner.html.j2` — already correct, already included on all
  three absorbed pages leaving the flyout
- `site/flowleaders/leaders.json` schema — `board_a_total`/`board_b_total` already exist

**Follow-up, not W1 (name so it is not lost, not so it is built now):**
- `docs/site_semantics/options.md` — new glossary entries for `iv_rank`, `oi_delta_clusters`,
  `wall_persistence`, the filmstrip's arc/events — masterplan §7 names this as belonging
  "with the surface wave"; W1 is that wave for these five stats
- `config/synapse.yml` — register `site/gex/_manifest.json` as a new artifact if it is kept
  as a persistent side-file rather than a build-time-only intermediate
