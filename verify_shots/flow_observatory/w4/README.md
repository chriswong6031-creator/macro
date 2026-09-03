# Flow Observatory V2 — W4 visual evidence

Official-vs-curated lenses, coverage floors, overlap disclosure, concentration and
contribution (`research/flow_observatory/W4_SPEC.md`).

Captured via Playwright Chromium (`/private/tmp/pwvenv`, headless), `reduced_motion:
"reduce"`, against the REAL rebuilt `site/flow_velocity.html` served statically
(`python3 -m http.server <port> --directory site`) — same method as the W1/W2/W3
verify_shots. A small JS pass forces `opacity:1`/`.is-in` on every `.fv-reveal` section
(the page's own IntersectionObserver reveal otherwise leaves off-screen sections at
`opacity:0` for a screenshot taken without a full scroll pass) and scrolls to `#groups`
before each capture. `theme`/`lang` are set via `localStorage` before load (the page's
own boot script reads them); the "official" shots additionally click
`#lens-tab-official` to switch the tab. Capture script: throwaway, not committed (this
README is the durable record).

Every one of the 16 captures below also had its `document.documentElement.scrollWidth`
checked against `window.innerWidth` (no horizontal page scroll) and its Chromium
console drained for `error`-level messages — both are clean across the full matrix
(printed by the capture script; zero horizontal-scroll violations, zero console errors).

## Two real bugs this evidence pass caught (fixed before the final capture)

1. **Lens switch never actually showed the official tab.** `setLens()`'s
   `panels[k].style.display = (k===name?'':'none')` set the ACTIVE panel's inline
   style to an empty string — which merely *clears* any previous inline override, so
   `#lens-official`'s own default CSS rule (`html.js #lens-official{display:none}`)
   kept it hidden even after being selected. Fixed to set a real value (`'block'`),
   added `test_lens_switch_js_sets_a_real_display_value_not_an_empty_override`
   (tests/test_flow_observatory_groups.py).
2. **Official-sector rows never carried a real ZH name.** `l1_names` was built as
   `{code: en}` (English only); `groups.aggregate_lens` set BOTH `name` and `name_zh`
   to that same English string, so the ZH UI silently showed English Shenwan L1 sector
   names. Fixed: `l1_names` is now `{code: (name_en, name_zh)}` end-to-end (
   `scripts/build_flow_velocity._official_sectors_panel`,
   `engine.flow_observatory.groups.aggregate_lens`), added
   `test_official_lens_row_carries_a_real_zh_name_not_the_english_name_twice`.

Both are caught-and-fixed defects, not open gaps — the crops below are the POST-fix
render.

## Crops (dark/light × EN/ZH × 1440 + 390 mobile, curated AND official lens per theme)

| file | shows |
|---|---|
| `lens_curated_dark_en_1440.png` | Theme flow board, dark, curated tab active: lens tabset, `overlap 2` chip (Autos & NEV Makers, shared with another theme), `16/16` coverage badge, pinned drilldown line "top name = 16% of gross flow · without it: same direction — top: …, bottom: …" |
| `lens_official_dark_en_1440.png` | Official (Shenwan L1) tab, dark: pinned lens label "Official sectors (Shenwan L1) — current membership; history accrues from 2026-09-03"; 28 of 31 sectors render `insufficient coverage` (amber pill, never dropped); **Nonferrous Metals** (62.1% coverage, clears the floor) shows a real `quiet / insufficient data` quadrant + its own concentration drilldown + the excluded/missing list (53 names, each with `(missing)`/`(unscored)`); **Banks** (bottom row, 38/42 = 90.5%) shows `real inflow, above norm` — a genuinely healthy computed read alongside the honest insufficient-coverage majority |
| `lens_curated_light_en_1440.png` | Same curated board, LIGHT theme — white/paper material, hairline borders, all W4 chips legible (governed tokens, no new palette) |
| `lens_official_light_en_1440.png` | Same official board, LIGHT theme |
| `lens_curated_dark_zh_1440.png` | Curated board, dark + ZH — theme names/labels/chips fully in Chinese, no English leakage (`in N themes`→`属N个主题`, drilldown line→`最大贡献个股占总流量…`) |
| `lens_official_dark_zh_1440.png` | Official board, dark + ZH — real Shenwan L1 Chinese names (农林牧渔/基础化工/钢铁/有色金属/…), `覆盖不足` badges, `平静 / 数据不足` quadrant, excluded list in Chinese (`（无数据）`/`（未评分）`) |
| `lens_curated_light_zh_1440.png` | Curated board, light + ZH |
| `lens_official_light_zh_1440.png` | Official board, light + ZH |
| `lens_curated_dark_en_390.png` / `lens_official_dark_en_390.png` | Mobile (390px) crops, dark EN — lens tabset stacks as pills, table collapses to its existing responsive columns, drilldown lines clip within their own cell (never a page-level horizontal scroll — verified programmatically per capture) |
| `lens_curated_light_en_390.png` / `lens_official_light_en_390.png` | Mobile crops, light EN |
| `lens_curated_dark_zh_390.png` / `lens_official_dark_zh_390.png` | Mobile crops, dark ZH |
| `lens_curated_light_zh_390.png` / `lens_official_light_zh_390.png` | Mobile crops, light ZH |

## Coverage-floor calibration (real data, 2026-09-03)

All 22 curated `baskets_china` themes sit at 100% coverage today — any floor ≤100% keeps
every one of them eligible (trivial). The SW L1 official-sector distribution is the real
"degenerate tail" the floor exists to catch (measured against the same `kmap`, 31
groups): coverage ranges 5.1%–90.5% with a natural break at 57.6%→62.1%. Only **Banks**
(90.5%), **Non-bank Financials** (77.2%), and **Nonferrous Metals** (62.1%) clear a 60%
floor; the other 28 sectors legitimately have too little of their true membership inside
the ~1,800-name Tushare moneyflow panel to publish a non-survivor-biased read. The
starting hypothesis (60%) sits inside that natural gap and is kept as-is (see
`engine/flow_observatory/groups.py` module docstring for the full receipt).

## Spike receipt (spec §1)

`ak.index_component_sw(symbol=<SW L1 code>)` — keyless, `www.swsresearch.com` JSON
endpoint, no key/token. Sampled 801780 (Banks, 42 rows) and 801080 (Electronics, 493
rows) before building the full 31-code snapshot (5,211 total constituent rows). SPIKE
SUCCEEDED → §2A implemented (never §2B, though the §2B "unavailable" designed state is
still real, reachable code — exercised by
`tests/test_flow_observatory_groups.py::test_official_lens_unavailable_state_renders_pinned_strings_no_curated_leak`
for the case a fresh checkout's membership store has not collected yet).
