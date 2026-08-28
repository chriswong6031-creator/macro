# Stock Dashboard V3.7 — HK follower production acceptance record (2026-08-26)

Session: Fable COO, `WS:PROPHET-HK-CA-REVAMP` presentation lane
(continuation of the Canada V3.7 wave —
`research/STOCK_DASHBOARD_V37_CANADA_ACCEPTANCE_2026-08-25.md`). Review law:
`research/SOL_HK_V37_FOLLOWER_ARCHITECTURE.md` (§14 rejection triggers +
§13 fixtures) + `research/SOL_V37_REFERENCE_ARTIFACT_PRODUCTION_ADDENDUM.md`.

## Implementation identity

| Item | Value |
|---|---|
| PR | #6433 `claude/hk-v37-follower` |
| Reviewed head | `3a1487fd75a0e31e3080a12bd4901324c47bccf0` |
| Squash merge | `cbf615eaa89399ae2a1b40de9db94f583d6c37c2` (merged on concluded green, head re-read pre-merge) |
| CI | ci.yml run 32920264252 SUCCESS on the reviewed head |
| Files | `site/hk-stock-v36.js` (new composer), `templates/dashboard-icons.js` + `site/dashboard-icons.js` (HK loader block, byte-paired), `tests/test_hk_v37_composer.py` (new), `.github/ci/legacy-jobs.yml` (wiring) |
| Adversarial review | Opus reviewer round 1: 1 BLOCKER + 2 MAJOR + 4 NONBLOCKING — all adjudicated and repaired; verdict PASS on `3a1487fd` |
| Delivery | covering render re-stamped `dashboard-icons.js?v=010b4a01` (page built 2026-08-26 03:01 UTC); VPS byte-verified |

Market-native deltas vs Canada (per the frozen follower architecture — shared
grammar, not a clone): Top Picks = the owner's **Featured cohort**
(`pv-featured`, emitted on `featured and stage=='live'` — never positional);
**no LIVE treatment anywhere** (HK has no per-ticker live quote plane —
`live/quotes.json` carries zero `.HK` stock symbols; the single header chip is
the owner's `Board <as_of>`); **zero fetches** (every input harvested from
served owner DOM); sector-only Leadership (no canonical HK theme artifact —
none fabricated) joining the Act-Now lanes (verbatim owner labels, same anv2
family as Canada) with `#sector-rotation`'s owner rank + cycle state;
Southbound INTEGRATE_COMPRESS ladder — conditional Leading-Now cue gated on
the **owner's own materiality marker** (`.sbah-sig`: `sig-in/sig-out/sig-neu`;
`sig-neu` suppresses), modal subband with the three owner `.sbah-read`
sentences, full Mainland Money panel as an on-demand Research tool; Evidence &
Record moves the HK trd chip+dialog (`factordata/hk_track_ledger.json`);
Research tools = HK Macro link + one-at-a-time disclosure toggles revealing
the owner's own panels (#hk-velocity-desk, #washout-watch, #mainland-money,
#hk-screener) below the composer — real destinations, no dead anchors, no
competing shelf at rest.

Review repairs (round 1): **BLOCKER** — Canada's `.sm-hidden` neutralizer was
dropped in the port; legacy theme.js show-more holds live references to the
moved cards and re-hides them on resize (§14 "non-Featured actionable names
disappear from All Candidates"); repaired with
`.hk-v37-card-grid .sm-hidden{display:flex!important}` + test pin. **MAJOR** —
flow cue was unconditional (would have pinned "Flow roughly balanced — no
strong tilt" to L1); gated on the owner's `sig-*` marker. **MAJOR** —
Leading-Now printed rank-1's name stance-stripped while the owner files that
sector under Reduce / Avoid; the owner stance chip now rides the button.
Plus: lane labels pinned cross-file to the template (drift turns CI red),
comment-satisfiable test pins hardened (8/8 in-memory mutations killed),
closeModal overflow-reset guarded.

## Production matrix (entitled Claude-in-Chrome session, www.mastermind-x.com/hk_stocks.html, 2026-08-26)

| Cell | Result |
|---|---|
| Frozen hierarchy header→Leading Now→Prophet→Sector Leadership→Evidence & Record→Research Tools | **PASS** (DOM section list) |
| NO LIVE fabrication | **PASS** — zero "LIVE" text in composer output; single `Board Aug 25, 2026 / 榜单 2026年8月25日` chip; card change chips stay the owner's baked "—"; no direction-color pin |
| Featured-cohort Top Picks | **PASS** — 3 `pv-featured` of 10; `3 shown · 10 on board` truthful; All = 10/10; selection halo neutral; owner BUY action badges untouched |
| Grid XOR Table | **PASS** both directions; StockTable (HK-native columns) sole surface under Table; population mode preserved |
| Sol-gate population law | **PASS end-to-end** — Internet & Tech filter under Top Picks: population stayed `top`, 0 cards, exact `No Top Picks in this group.该组别中暂无首选。` + `View All Candidates`; deliberate click → All showing exactly 0268.HK |
| Leading Now | **PASS** — rank-1 sector Healthcare & Pharma WITH its owner `Reduce / Avoid` stance chip (honesty repair live); flow cue ABSENT with owner marker `sig-neu` (materiality gate proven on live data) |
| Sector Leadership + rotation integration | **PASS** — ranked 01-08 with verbatim native stances (Buy Now / In Favour / Bottoming Watch / Reduce–Avoid), cycle-state suffixes (NEARING A HIGH, BUY ZONE, BOTTOMING), leaders + board counts |
| Expand modal | **PASS** — four-lane group-action band (verbatim EN+ZH), 26 activation rows, Southbound subband (`内地资金`) text rows present |
| Evidence & Record | **PASS** — moved chip `Track record · building · 556 calls logged`, dialog opens with 26 real ledger rows, `Methodology →` live |
| Research tool toggles | **PASS** — one-at-a-time reveal/re-hide verified (#hk-velocity-desk → #washout-watch → none) |
| BLOCKER repair under production | **PASS, mechanism observed** — resize events made theme.js re-add `sm-hidden` to 2 moved cards; all 10 stayed visible (rescue rule holds) |
| Entitlement boundary | **PASS** — entitled `GET /hk-stock-v36.js?v=20260825` → 200 `private, no-store` with V3.7 body; anonymous (credentials omitted) → **401** |
| Dark + Light | **PASS** (screenshots) |
| EN + ZH | **PASS** — fully native ZH (港股, 首选/全部候选, 精选 chips, native stances); card sparkline hue rides the site-wide ZH swap exactly as the owner's own art does |
| Console errors | **NONE** |
| Horizontal overflow | **NONE** (scrollWidth == clientWidth) |
| 390 px | **Residual (local-real-browser + bytes proven)** — builder verified the exact shipped bytes at 390px locally (single column, no overflow); the OS ignores window resize on the automation tab's hidden Space, so the exact-390 PRODUCTION pixel pass remains unexecuted (same residual class as Canada V3.7) |

§13 fixture coverage: 1 (Featured+actionable: 3968.HK BUY), 3 (non-Featured
actionable present in All), 4 (setting-up records via stage groups), 5 (no
live plane → no LIVE), 9 (XOR), 10 (leadership filter without semantics
change) — observed live; 6 (Southbound non-material) — observed live
(`sig-neu` suppression); 2/7 (Featured+wait, A/H missing) — not present in
current data; behavior is code-guarded (owner verbs untouched; A/H fields
omitted when absent) and covered by the abort/degradation tests.

## Classification

**HK Stock Dashboard V3.7 is `PROVEN_LIVE` as of 2026-08-26** — merged exact
reviewed head, production deployment descends from the merge (VPS HEAD
`0c80d5c8` at proof time; covering render stamp 03:01 UTC), signed-in real
production browser proof on production bytes, matrix passing, no
product-authority regression (nothing moved ranking, signal, lifecycle,
availability, entitlement, quote, or persistence semantics; Featured stayed
selection-not-action; no LIVE fabricated). One residual: the exact-390
production pixel pass (local-real-browser + bytes proven).

This completes the Canada→HK regional V3.7 rollout. US remains decoupled
(`DEC:V36-REGIONAL-PILOT-RATIFIED-US-DECOUPLED` unchanged); the China
follower architecture remains outside this carrier.
