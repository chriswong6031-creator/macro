# Lane A Archaeology — Sector Central (US) Overview / Action-Board authority contract

ROUTE: census, sub-lane A of XPV2-SC-R3A. Scope: Overview/action-board area of
`templates/sector_central.html.j2`, `scripts/build_sector_central.py`,
`scripts/build_site.py::action_board()`/`basket_action_items()`,
`templates/_us_act_now_board.html.j2`, `templates/_us_bottoming_watch.html.j2`,
their payloads, and premiumdata gating. R2 critic bundle used only to know what to
verify (per commission); production code/payloads are authority.

All file:line citations below are against this worktree's HEAD unless noted.

---

## 1. The five action lane keys

Defined in `scripts/build_site.py::action_board()` (buckets built lines 2018,
2138–2155) and mirrored in `scripts/build_sector_central.py:67-73`
(`_ACTNOW_LANES`, a deliberate non-imported copy, pinned by
`tests/test_sector_central_gate.py::test_lane_table_matches_build_site`):

```
scripts/build_sector_central.py:67-73
_ACTNOW_LANES = [
    ("buy_now", "ab-buy-fold", False),
    ("buy_soon", "ab-soon-fold", False),
    ("on_the_run", "ab-run-fold", False),
    ("take_profits", "ab-trim-fold", False),
    ("hold", "dash-hold-fold", True),
    ("avoid", "dash-hold-fold", True),
]
```

Six urgency KEYS fold into FIVE rendered `.actcol` lanes because `hold` and
`avoid` share one DOM column ("Stand aside") — see item 6. The five visible
lane labels (`templates/_us_act_now_board.html.j2`) are:

1. `act-buy` — Buy now (lines 551-568)
2. `act-soon` — Almost ready (lines 570-586)
3. `act-run` — In favour — don't chase (lines 589-605)
4. `act-trim` — Take profits (lines 608-624)
5. `act-hold` — Stand aside (hold+avoid) (lines 628-651)

Plus a non-lane full-width watch strip, Bottoming watch (line 656 include;
see item 10) — explicitly NOT a sixth action lane
(`templates/_us_act_now_board.html.j2:652-655`).

## 2. Exact EN and ZH labels (verbatim, quoted)

Source: `templates/_us_act_now_board.html.j2`.

| Lane | EN name (line) | ZH name |
|---|---|---|
| Buy now | `Buy now` (555) | `立即买入` |
| Almost ready | `Almost ready` (574) | `接近就绪` |
| In favour — don't chase | `In favour — don't chase` (593) | `看好 — 勿追高` |
| Take profits | `Take profits` (612) | `止盈` |
| Stand aside | `Stand aside` (632) | `观望` |
| Bottoming watch (watch strip, not a lane) | `Bottoming watch` (`_us_bottoming_watch.html.j2:83`) | `筑底观察` |

## 3. Exact subcopy per lane (verbatim)

`templates/_us_act_now_board.html.j2`:

- Buy now — EN `Entry confirmed today` / ZH `今日已确认入场` (558)
- Almost ready — EN `Setting up — wait for the trigger, not a buy yet` / ZH
  `构筑中 — 等待触发，尚不可买` (577)
- In favour — don't chase — EN `Uptrend intact but extended · wait for a
  pullback` / ZH `趋势完好但已延伸 · 等待回调` (596)
- Take profits — EN `Late in the cycle / topping — protect gains` / ZH
  `周期晚期／做顶 — 保护利润` (615)
- Stand aside — EN `Hold what you own · no new buying` / ZH `持有勿动 · 不新开仓`
  (635)
- Bottoming watch — EN `cycle lows forming — watch, don't chase` / ZH
  `周期底部形成中——观察，勿追` (`_us_bottoming_watch.html.j2:86`)

These are byte-identical to the R2 critic's DAC-006 "Canonical evidence"
quotes (`research/reference_integrity/mastermind-xpv2-turn3-r2/reviews/data_authority.md:147-152`),
confirming DAC-006's claim that the candidate's abbreviated copy (`Entry
confirmed`, `Near trigger`, `Trend intact`, `Late cycle`, `No new buying`, ZH
`暂时回避`) is wrong — the real ZH for Stand aside is `观望`, not `暂时回避`.

Empty-state copy per lane (fallback when a lane has zero rows), also
verbatim EN/ZH, e.g. Buy now: `None today — nothing has fully confirmed a
fresh cycle low.` / `今日无 — 尚无标的完全确认新的周期低点。` (563).

## 4. How counts are computed, and by whom

Lane header counts (`.acth-count`) are computed **in-template**, off the FULL
(ungated) `action_board` dict, NOT off the possibly-truncated row list that
renders:

```
templates/_us_act_now_board.html.j2:524-528
{%- set _bn_cnt = action_board.buy_now | length -%}
{%- set _bs_cnt = action_board.buy_soon | length -%}
{%- set _run_cnt = action_board.get('on_the_run', []) | length -%}
{%- set _tp_cnt = action_board.take_profits | length -%}
{%- set _hold_cnt = (action_board.hold | length) + (action_board.avoid | length) -%}
```

Comment at lines 529-534 makes this explicit: "The `_*_cnt` figures above are
counted off the FULL board and stay that way — the lane headings, and the
'+N more' links, are honest totals a Free reader keeps. Only the ROW LISTS
below are cut down." This is the mechanism behind the critic's "Premium/gated
rows are not leaked while full counts remain visible" requirement
(`data_authority.md:245`) — counts are never gated, only row bodies are.

`action_board` itself is assembled once per build by
`scripts/build_site.py::action_board()` (signature at line 1990) which is
called at `scripts/build_site.py:6154` and persisted to
`site/basketdata/action_board.json` (`{"action_board": {...}}` top-level
shape, confirmed by direct read below). `scripts/build_sector_central.py`
does NOT recompute the board — it is a **reader**, loading the persisted
JSON fail-soft (`scripts/build_sector_central.py:432-439`, "Act-Now board
(reader pattern) ... read it fail-soft so an absent/corrupt file just
renders the refreshing fallback").

Live sample, `site/basketdata/action_board.json` (this checkout, read via
`python3 -c` at census time): `buy_now=4, buy_soon=5, on_the_run=5,
take_profits=3, hold=13, avoid=14` → Stand aside = hold+avoid = 27. This
matches the critic's DAC-006 "Correct statements confirmed" figures
(`4 / 5 / 5 / 3 / 27`, `data_authority.md:138,146,218`) exactly — CONFIRMED,
not refuted.

A page-wide `total` field is also computed once in `action_board()` at
build time (`scripts/build_site.py:2229-2235`, "Groups header total ... a
single published total across every lane").

## 5. Row source and row ORDER (who orders, at build or client time)

Row source: two producers merged, both at BUILD time, in
`scripts/build_site.py::action_board()`:

- **Theme (basket) rows** — from `basket_action_items(site)`
  (`scripts/build_site.py:1670`), which reads `site/basketdata/baskets.json`
  → `theme_intel.themes` / `theme_intel.act_now` (buy/add_on_pullback/
  conflicted lists) (lines 1702-1723) and enriches with
  `site/allocationdata/allocation.json` (`ranks`, `weights`) (lines
  1742-1747).
- **Sector rows (11 GICS SPDRs)** — from `sector_timing` (an
  `action_board()` parameter, the per-sector cycle-timing dict), iterated
  at `scripts/build_site.py:2027` and routed to a lane by `entry.urgency`
  / `lane_hint` / tag rules documented at lines 1998-2006.

Merge/order rule — **themes lead, sectors follow, within each lane**:

```
scripts/build_site.py:2214-2221
# UNIFY: narrative baskets lead each lane (the resolution the user acts on), GICS
# sectors follow. on_the_run: basket rows first (same 🧩-then-🏛 pattern), then sectors.
...
_ab_buy_now = (bi.get("buy_now") or []) + buy_now
_ab_buy_soon = (bi.get("buy_soon") or []) + buy_soon
_ab_on_the_run = (bi.get("on_the_run") or []) + on_the_run
_ab_take_profits = (bi.get("take_profits") or []) + take_profits
_ab_hold = (bi.get("hold") or []) + hold
_ab_avoid = (bi.get("avoid") or []) + avoid
```

Within the sector half of `buy_soon`, an explicit sort exists:
`buy_soon.sort(key=lambda x: (x["days"] if x["days"] is not None else 99))`
(`scripts/build_site.py:2156`). No other sector sub-list (`buy_now`,
`on_the_run`, `take_profits`, `hold`, `avoid`) is explicitly sorted in
`action_board()` — order there falls out of `sector_timing.items()`
dict-iteration order (build-time, not client time). Theme-row order within
each lane is whatever order `basket_action_items()` appends them in (also
build time; not traced further — out of scope, this lane is the sector
board, not basket internals).

All ordering is **build-time, server-side**, baked into the JSON/HTML by
`scripts/build_site.py` and consumed unmodified by
`scripts/build_sector_central.py`'s reader pattern; the client-side
hydration script (`templates/sector_central.html.j2`, tier-payload script
near EOF, `hydrate()` function) only APPENDS withheld rows to the end of the
existing DOM list in whatever order they arrive in the JSON blob — it does
not re-sort ("a lane can legitimately be absent", `sector_central.html.j2:3605`).

Standout-stock (`notable`) ranking is a separate, well-documented rank at
`scripts/build_site.py:2148-2213` (α-led, with per-sector cap) — this feeds
the `notable_clean` field returned by `action_board()`, used elsewhere on
the page (Explore/standouts), not the five action lanes themselves; noted
for completeness, not traced further (adjacent surface).

## 6. Score/performance source per row

**Sector rows** carry no numeric "score" field for the action board — their
displayed metric is the `stat_en`/`stat_zh` phrase computed by
`_action_board_stat_chip()` (`scripts/build_site.py:1904-1988`), a
lane-specific qualitative string (e.g. `"clean entry · 3d ago"`,
`"late cycle · {age_short}"`) derived from `entry.tag`/`entry.urgency`/
`entry.days_hi` — NOT a blended score. This directly REFUTES the R2
candidate's DAC-001 pattern of showing a single numeric "score" +
"performance %" pair per sector row as if uniform across kinds — the
critic's own canonical evidence agrees
(`data_authority.md:28-29`, quoting `engine/sector_central.py:337-430,367-401`:
conviction is state→gate→confirm→risk-size, "not a generic heat/performance
score").

**Theme (basket) rows** DO carry a numeric score, sourced from
`theme_intel.themes[].score` in `baskets.json`:

```
scripts/build_site.py:1784
"score": th.get("score"),
```

rendered on the row via `x.score` in `ab_theme_row()`:
`templates/_us_act_now_board.html.j2:489-491`. Theme rows also carry
`perf_20d_rel` (20-day relative performance vs market), rendered at
`templates/_us_act_now_board.html.j2:503-505` (`'%+.1f'|format(x.perf_20d_rel
* 100)`), sourced from `th.get("perf",{}).get("20d",{})`
(`scripts/build_site.py:1769-1770`, full field not shown here but present in
`base_item` construction). Live sample confirms shape:
`site/basketdata/action_board.json` `buy_now[0]` = Gold Miners,
`"score": 76, "perf_20d_rel": 0.2716` (read at census time via
`python3 -c` — see EVIDENCE).

For the authoritative PER-SECTOR conviction score (a distinct number from
anything on the action board), the producer is
`site/sectordata/sector_central.json` (written by
`scripts/build_sector_central.py::main()`, `data = cc.compute()` from
`engine/sector_central.py`) — this is a SEPARATE artifact from
`action_board.json` and is the one the DAC-001/DAC-002 findings cite as
canonical (e.g. `XLV / Health Care: conviction score 23, Reduce, direction
down`, `data_authority.md:35,58`). The action board and the sector-central
conviction score are two different numbers for the same sector and must
not be conflated — confirmed by reading both artifacts' schemas in this
census; not re-verified numerically beyond the critic's own citations
(GAP: did not independently pull `site/sectordata/sector_central.json`'s
XLV row to re-confirm the 23/Reduce figure — treated as reliable because
the critic's own evidence excerpt is a direct quote of the canonical file,
which per the commission's authority precedence (production payloads first)
outranks nothing here; no conflict found).

## 7. Each row's click destination (exact href pattern)

- **Sector rows**: `href="{{ x.href }}"` (`_us_act_now_board.html.j2:459`),
  where `x.href` is set at build time:
  ```
  scripts/build_site.py:2031
  "href": US_SECTOR_PAGE.get(fund, "sectors/" + fund + ".html"),
  ```
  i.e. a per-SPDR override table `US_SECTOR_PAGE`, falling back to
  `sectors/<TICKER>.html`.
- **Theme rows**: `href="{{ x.href }}"` (`_us_act_now_board.html.j2:482`),
  set at build time as:
  ```
  scripts/build_site.py:1780
  "href": "basket/" + tid + ".html",
  ```
  i.e. always `basket/<theme_id>.html`.
- **Bottoming-watch rows**: same pattern, `href="{{ x.href }}"`
  (`_us_bottoming_watch.html.j2:95`), href pre-set on each row by the
  producer (`engine/us_act_now.py` / `scripts/build_baskets.py`, not
  re-derived in the template) — not traced further inside that engine
  module (adjacent producer, out of the named scope files); GAP: exact
  href-construction line inside the bottoming-watch producer not located
  within this census's file budget — the include only consumes `x.href`
  verbatim, so the pattern (basket/`<id>`.html or sectors/`<ticker>`.html,
  matching the two icon kinds `BASKET`/sector at line 97) is inferred from
  row shape, not independently confirmed at its origin line.
- **"+N more" links** (gated shell, all five lanes) point to
  `sector_central.html#actnow-section`
  (e.g. `_us_act_now_board.html.j2:565,584,603,622,646`) — same-page anchor
  back into the board itself, not a drill-through.
- The lane-foot "Drill to stocks →" link points to `#confluence`
  (`templates/sector_central.html.j2:2205`), the in-page Confluence view
  (SI Workspace V2 hash router), not a separate page.

## 8. Premium behavior

**Gate switch (currently ON)**: `config.yml:7204-7206`
```
sector_central_gate:
  gated: true
  preview_rows: 3
```
read by `scripts/build_sector_central.py::_gate_cfg()` (lines 78-90),
defaulting to `{"gated": False, "preview_rows": 3}` only on a missing/
malformed config block — CURRENT production state is gated, preview=3 rows
per lane.

**Split (build time)**: `scripts/build_sector_central.py::split_actnow()`
(lines 93-133) slices each of the 6 underlying lane lists to the first
`preview` (3) rows for the SHELL, and collects the remainder into `locked`
(`[{lane: <fold-id>, rows: [...], wrap: bool}]`), keyed by the SAME
`.actbody` fold ids as `_ACTNOW_LANES` (item 1). Stand-aside spends its
budget on `hold` first, `avoid` takes the remainder (lines 105-109) so the
combined visible row count still equals `preview`.

**Preview row source (shell)**: the SAME `action_board` dict, sliced
in-template again for the render itself
(`_us_act_now_board.html.j2:535-541`, `_bn_rows = action_board.buy_now[:_ab_pv]
if _ab_gate else ...`) — i.e. the split is computed twice (once in Python for
the payload, once in Jinja for the shell) from the identical source list, by
design ("Pure in `action_board`", docstring
`scripts/build_sector_central.py:99-102`) so shell and payload can never
disagree about which rows are visible vs withheld.

**Full-count source**: unchanged — lane header counts (item 4) are always
computed off the FULL `action_board` lists regardless of gate state; the
gate only cuts the row bodies, never the counts (`_us_act_now_board.html.j2:529-534`).

**Withheld rows / payload**: written UNCONDITIONALLY (even when nothing is
withheld) to `site/premiumdata/sector_central.json`
(`scripts/build_sector_central.py::write_payload()`, lines 136-165;
`_SC_PAYLOAD_URL = "premiumdata/sector_central.json"`, line 61). Payload
shape: `{"schema": "tier_payload.v1", "page": "sector_central", "gated":
bool, "required_tier": "essential", "built": <iso ts>, "panels": {"actnow":
{"preview": N, "locked": N, "total": N}}, "actnow_html": "<...>"}`. Live
sample (this checkout, read at census time):
```
site/premiumdata/sector_central.json
"gated": true, "required_tier": "essential",
"built": "2026-08-20 16:51 UTC",
"panels": {"actnow": {"preview": 3, "locked": 29, "total": 44}}
```
(`44` = the sum 4+5+5+3+13+14 from item 4, confirming preview+locked=total
holds live.) `actnow_html` is server-rendered from the SAME
`_us_act_now_board.html.j2` include in its "rows-only" shape
(`_ab_rows_only` branch, lines 514-521, `ab_locked` param), so shell and
payload literally share one template path — cannot drift by construction
(docstring intent, `write_payload()` lines 143-146).

This page's own payload file, `sector_central.json`, is DELIBERATELY
separate from `us_stocks.json` (the sibling gate on `us_stocks.html`, same
shared include) — comment at
`scripts/build_sector_central.py:32-46`: sharing one payload "would make
whichever builder ran last silently overwrite the other's rows", since the
two pages are built by different scripts at different times from a possibly
different generation of `action_board.json`.

**Gating enforcement (URL level)**: `/premiumdata/` is one of the prefixes
under `premium.enforced_early` in `config/site_access.yml:648`, 403'd for
anonymous/Free readers ahead of the site-wide paywall switch
(`config/site_access.yml:618-648`).

**Authenticated hydration path (client, end-to-end)**:
`templates/sector_central.html.j2`, tier-hydration `<script>` near EOF
(search hits around line ~3560-3637 in this file):
1. `whenAuthSettled()` waits for `window.MDXAuth`'s first `mdx-auth`
   broadcast (3s timeout fallback) so the fetch is not raced against
   `theme.js` loading.
2. `fetch(SRC, {credentials:'same-origin', cache:'no-store'})` against the
   same `premiumdata/sector_central.json` URL; a non-OK response throws
   `'locked'`, caught silently — "the shell stays exactly as rendered,
   disclosure lines and all. Nothing to undo."
3. `hydrate(payload)` validates `payload.schema === 'tier_payload.v1'` and
   `payload.page === 'sector_central'` (throws otherwise), then parses
   `payload.actnow_html` into a detached `<div>`, walks its
   `[data-ab-lane]` children, and `insertAdjacentHTML('beforeend', ...)`
   into the matching `#<fold-id>` element by id (`ab-buy-fold`,
   `ab-soon-fold`, etc.) — the SAME ids `_ACTNOW_LANES` names.
4. `restoreFold(col)` rebuilds the "Show more (N)" control for any lane
   now over 3 rows (the gated shell ships without one, since nothing was
   foldable yet).
5. Any `.pg-more` disclosure line ("+N more") is removed, since the rows it
   pointed at are now present.

Server re-decides regardless of client auth state — the code comment states
"the server re-decides regardless" (near `whenAuthSettled` definition) — the
client-side wait is purely to avoid a race, not the actual gate (the actual
gate is the 401/403 the server returns on `/premiumdata/*` for an
unentitled `fetch`).

## 9. Trace behavior (`#read-*` / trace links from rows)

No `#read-*` hash-link or "trace" affordance was found ATTACHED to
individual action-board rows in `templates/_us_act_now_board.html.j2` or
`templates/_us_bottoming_watch.html.j2` — each row's only navigation is its
own `href` (item 7); rows carry a hover popover (`data-rpop`,
`.rp-src`/`.row-pop-decision` block, e.g.
`_us_act_now_board.html.j2:459,475/506`) which is an in-place tooltip, not a
link.

The one `#read-*`-shaped element on the Overview is `id="si-read-overview"`
(`templates/sector_central.html.j2:2189`), a `<p>` element (not a link) —
part of the "view read" strip: a one-line, server-seeded + client-composed
summary sentence for the Overview view, filled by
`window.__siViewReads(BASKETS)` (`templates/sector_central.html.j2:3088`)
which is defined in `templates/si_workspace.js` (`readOverview()`, lines
~136-152: composes "`<leader>` is handing leadership to `<challenger>`." +
"`N` names sit in the Buy lane." purely from `theme_intel.act_now.buy`
length and the hero's server-seeded `data-from-en`/`data-to-en` attributes;
explicitly display-tier-only composition, "no new score, rank, threshold or
gate is computed here (A7)", `si_workspace.js` header comment). This is a
SUMMARY line, not a per-row trace link — GAP: the commission's phrase
"trace links from rows" may refer to a `#confluence`/drill-through
affordance rather than a literal `#read-` id; the only such element located
matching either literal string is `si-read-overview`, and it is not a link.
No other `#read-` pattern was found via grep across
`templates/sector_central.html.j2` and the two act-board includes.

## 10. The Bottoming Watch contract

**Producer**: engine-side computation lives in `engine/us_act_now.py`
(cycle-turn detection) and `scripts/build_baskets.py` (which writes the
lane payload into `site/basketdata/baskets.json` →
`theme_intel.act_now.bottoming_watch` / `.dual_read_ids` /
`.recovering_ids` / `.bottoming_authority`, confirmed by
`scripts/build_baskets.py:291`, `_an_ba["bottoming_authority"] = _bw["authority"]`).
`scripts/build_sector_central.py::build_bottoming_context()` (lines 170-236)
is the JOIN point — the ONLY place holding both `baskets.json` (bottoming
lane) and `action_board.json` (the board rows to stamp a "recovering" chip
onto), read at `scripts/build_sector_central.py:469-484` ("W-A bottoming
watch (reader pattern)").

**Context or action authority**: explicitly CONTEXT/display-tier, never
action authority — enforced multiple ways:
- `templates/_us_bottoming_watch.html.j2:23-28` ("COPY LAW"): "Watch
  vocabulary only, never a buy verb." Two payload fields are deliberately
  NEVER rendered — `signal` ("BUY") and `timing_state` (whose vocabulary
  includes "FRESH BUY"); instead a fixed phrase "cycle turn signal — watch
  only" is quoted, pinned by `tests/test_us_act_now.py`.
- `scripts/build_sector_central.py:170-188` docstring: both halves (lane +
  graduation-gap chip) are "display-tier" and the chip's words "ship from
  the engine (`bottoming_authority`) so the page cannot drift from the
  measured basis."
- The R2 critic's own canonical evidence agrees:
  `site/basketdata/baskets.json` bottoming payload carries `tier: display,
  may_rank: false, may_gate: false, may_size: false, may_escalate: false`
  (`data_authority.md:79`) — this CONFIRMS DAC-003's finding that the R2
  candidate's "Early turns"/"Watch until the entry state upgrades" framing
  wrongly implies an upgrade pipeline; production's actual framing is
  strictly watch-only.

**Exact wording** (verbatim, from `_us_bottoming_watch.html.j2`):
- Lane title EN `Bottoming watch` / ZH `筑底观察` (line 83)
- Subcopy EN `cycle lows forming — watch, don't chase` / ZH
  `周期底部形成中——观察，勿追` (line 86)
- Per-row chip (cycle organ's own output, quoted, never a raw signal
  field): EN `cycle turn signal — watch only` / ZH `周期转折信号——仅观察`
  (line 107)
- Gate-conflict chip: EN `below 200-day trend — gate shut` / ZH
  `低于200日趋势——闸门关闭` (line 108)
- Dual-read chip: EN `may be bottoming` / ZH `或正筑底` (line 109)
- Empty state: EN `no basing candidates tonight` / ZH `今晚无筑底候选` (line
  119)
- Null disclosure (engine-sourced, quoted by the critic too):
  `"A forming low on its own has not been shown to predict what comes
  next — watch, don't chase."` (`data_authority.md:80`; rendered from
  `bottoming_authority.null_disclosure_en/zh`,
  `_us_bottoming_watch.html.j2:127-129`).

**Layout**: full-width strip UNDER the five action lanes (`grid-column: 1 /
-1`), explicitly "NOT... a sixth action lane" — it is a "WATCH surface"
answering "what is forming" vs the five lanes' "what do I do"
(`_us_bottoming_watch.html.j2:17-21`).

## 11. Leadership/heat context sources feeding the Overview

The hero + "This week's handoff" + "What changed" strip
(`templates/sector_central.html.j2` ~2130-2230) all read from
`theme_context` (Jinja var), which is loaded from
`site/basketdata/si_handoff.json` by the builder:

```
scripts/build_sector_central.py:409-416
ctx_p = site / "basketdata" / "si_handoff.json"
if ctx_p.exists():
    ctx = json.loads(ctx_p.read_text(encoding="utf-8")) or {}
...
theme_context=ctx.get("theme_context"),
factor_season=ctx.get("factor_season"),
flow=ctx.get("flow"),
```

`si_handoff.json` is itself produced by `scripts/build_baskets.py`
(NOT by `build_sector_central.py` — reader pattern, same as the action
board):

```
scripts/build_baskets.py:558-568 (theme_context computation)
_theme_context = compute_theme_context(alloc=_alloc_payload,
    theme_intel=data["theme_intel"], region="us")
...
scripts/build_baskets.py:582-593 (si_handoff.json write)
(fdir / "si_handoff.json").write_text(json.dumps({
    "theme_context": _theme_context,
    "factor_season": factor_season,
    "flow": ...,
    "basket_member_syms": _member_syms,
    "generated_utc": built,
}, ...))
```

`compute_theme_context()` lives in `engine/theme_context.py` (imported at
`scripts/build_baskets.py:562`), fed by the SAME `allocation.json` +
`theme_intel` (from `baskets.json`) the action board itself draws from — so
the hero's leadership read and the action board's theme rows share one
upstream computation family (theme_intel), but the hero speaks through
`theme_context` while the board speaks through the raw `theme_intel.act_now`
lists (item 5), not the same object.

Clock: `si_handoff.json` (and therefore the hero/leadership context) is
regenerated once per `build_baskets.py` run — same nightly cadence as the
rest of the theme/basket engine; the file also idempotency-checks against
`context_history.jsonl` per the comment at
`scripts/build_baskets.py:557-561` ("PIT correctness ... same-day
idempotency check").

Null/stale handling: `build_sector_central.py:405-416` reads
`si_handoff.json` fail-soft (`try/except`, log a warning, leave `ctx = {}`);
the template then falls back to a DIFFERENT hero
(`templates/sector_central.html.j2:2163-2172`, the `{% else %}` branch of
`{% if theme_context is defined and theme_context is not none and
theme_context.leadership %}`) — "US Sector Intelligence" generic hero with
no leadership claim, confirming the Overview degrades to context-free
copy rather than stale-but-labeled-fresh copy when the handoff is absent.

DAC-002's finding — that a candidate wrongly converted "Health care is
taking the lead" context into "Buy now" action authority — is directly
supported by this trace: `theme_context.leadership` (hero) and
`action_board` (lanes) are two DIFFERENT reads over related-but-distinct
upstream data, and nothing in `sector_central.html.j2`'s hero rendering
path (`theme_context.leadership.trailing_leader`/`.strength[0]`) writes
into or reads from the action-board lane assignment logic in
`scripts/build_site.py::action_board()`. CONFIRMED: no code path connects
hero leadership text to lane placement.

---

## Critic-claim confirm/refute summary (this lane's scope only)

| Finding | Verdict here | Basis |
|---|---|---|
| DAC-001 (sector rows shown with one blended score/perf number) | CONFIRMED wrong pattern; production sector rows have no numeric score, only `stat_en` qualitative text (item 6) | `scripts/build_site.py:1904-1988`, `_us_act_now_board.html.j2:459-476` |
| DAC-002 (Health Care context→action conflation) | CONFIRMED no code path links hero leadership to lane assignment (item 11) | traced both paths independently |
| DAC-003 (bottoming watch retitled as upgrade pipeline) | CONFIRMED production is strictly display-tier/watch-only, `may_rank:false` etc. | item 10 |
| DAC-006 (lane order/counts correct; subcopy/ZH wrong in candidate) | CONFIRMED — production subcopy and `观望` verified verbatim (items 2-3); live counts 4/5/5/3/27 match | items 2-4 |
| Premium preview/full-count/hydration mechanism (`"Premium/gated rows are not leaked while full counts remain visible"`) | CONFIRMED live: gate ON (`config.yml:7204-7206`), payload preview=3/locked=29/total=44 matches action_board.json's 44-row sum | item 8 |

DAC-004/DAC-005/DAC-007/DAC-008 concern Confluence, Moving/handoff copy, and
Intelligence Hub — OUT OF SCOPE for this lane (sibling views per the
commission).

## GAPS

- Item 7: exact href-construction line for bottoming-watch rows inside
  their producer (`engine/us_act_now.py` / `scripts/build_baskets.py`) was
  not located within this census's file scope — the row's `href` field is
  consumed verbatim by the template but its origin line was not traced
  (adjacent-producer files not in the named SCOPE list).
- Item 6: `site/sectordata/sector_central.json`'s XLV conviction-score row
  was not independently re-pulled in this census; the 23/Reduce figure is
  taken from the R2 critic's own direct quote of that canonical file, which
  is a legitimate production artifact per the commission's authority
  precedence, but this census did not re-verify it byte-for-byte.
- Item 9: no literal `#read-*` hash-link was found on individual rows; the
  one `id="si-read-overview"` element is a summary `<p>`, not a link. If the
  commission's "trace links" phrase refers to something else (e.g. a
  drill-through the R2 candidate invented), it was not located in
  production and is treated as absent — GAP because "absent" here rests on
  a grep across the in-scope files only, not a repo-wide search.
- Row order for theme-half sub-ordering (within `basket_action_items()`)
  and for the sector-half of `buy_now`/`on_the_run`/`take_profits`/`hold`/
  `avoid` (no explicit sort found, only `buy_soon`) was characterized but
  not chased into `sector_timing`'s own construction order upstream (out of
  the named SCOPE files).
