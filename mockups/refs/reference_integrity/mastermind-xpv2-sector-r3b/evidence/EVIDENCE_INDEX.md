# XPV2-SC-R3B — Evidence Index (commission §21 deliverable 12)

Every file in this directory, one line each: filename → what it proves →
commission §/deliverable satisfied. Candidate under test:
`proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html` (BUILD_MANIFEST.json
output sha256 `0812bf7f…8610b5ce2`).

Capture method (all screenshots): local `python3 -m http.server 8931`
serving `proposal/`, Chromium (playwright-core 1.62.1 / Chrome for Testing
151.0.7922.34), **one fresh browser context per capture** (methodology note
QA2-14 — a shared page's CDP metrics override breaks after
`page.screenshot()`), section- or element-scoped crops at
`deviceScaleFactor:2` unless noted. State changes (theme/lang/access/
fail-fetch) driven only through the candidate's own R3 REFERENCE HARNESS
drawer controls (`#ref-theme`, `#ref-lang`, `#ref-access`, `#ref-failfetch`)
or real page UI (tabs, disclosures, the filter box) — never direct DOM
mutation. The harness's own fixed-position chrome is hidden
(`display:none`) immediately before each screenshot only, after every
state change has already been applied, so it does not bleed into
multi-frame stitched crops of elements taller than the viewport.

## A. PRIMARY 30 — six views × five view/lang/theme/width combos

| file | proves | § |
|---|---|---|
| `overview-1440-dark-en.png` | Overview, desktop, dark, EN — full baseline render (also shows the stale-clock chip) | §22 / A |
| `overview-1440-light-en.png` | Overview, desktop, light theme | §22 / A |
| `overview-1440-dark-zh.png` | Overview, desktop, ZH | §22 / A |
| `overview-390-dark-en.png` | Overview, mobile 390px, dark, EN | §22 / A |
| `overview-390-dark-zh.png` | Overview, mobile 390px, ZH | §22 / A |
| `map-1440-dark-en.png` | Map, desktop, dark, EN | §22 / A |
| `map-1440-light-en.png` | Map, desktop, light | §22 / A |
| `map-1440-dark-zh.png` | Map, desktop, ZH | §22 / A |
| `map-390-dark-en.png` | Map, mobile 390px, EN | §22 / A |
| `map-390-dark-zh.png` | Map, mobile 390px, ZH | §22 / A |
| `moving-1440-dark-en.png` | What's Moving, desktop, dark, EN | §22 / A |
| `moving-1440-light-en.png` | What's Moving, desktop, light | §22 / A |
| `moving-1440-dark-zh.png` | What's Moving, desktop, ZH | §22 / A |
| `moving-390-dark-en.png` | What's Moving, mobile 390px, EN | §22 / A |
| `moving-390-dark-zh.png` | What's Moving, mobile 390px, ZH | §22 / A |
| `money-1440-dark-en.png` | Money & Breadth, desktop, dark, EN | §22 / A |
| `money-1440-light-en.png` | Money & Breadth, desktop, light | §22 / A |
| `money-1440-dark-zh.png` | Money & Breadth, desktop, ZH | §22 / A |
| `money-390-dark-en.png` | Money & Breadth, mobile 390px, EN | §22 / A |
| `money-390-dark-zh.png` | Money & Breadth, mobile 390px, ZH | §22 / A |
| `explore-1440-dark-en.png` | Explore, desktop, dark, EN | §22 / A |
| `explore-1440-light-en.png` | Explore, desktop, light | §22 / A |
| `explore-1440-dark-zh.png` | Explore, desktop, ZH | §22 / A |
| `explore-390-dark-en.png` | Explore, mobile 390px, EN | §22 / A |
| `explore-390-dark-zh.png` | Explore, mobile 390px, ZH | §22 / A |
| `confluence-1440-dark-en.png` | Confluence, desktop, dark, EN | §22 / A |
| `confluence-1440-light-en.png` | Confluence, desktop, light | §22 / A |
| `confluence-1440-dark-zh.png` | Confluence, desktop, ZH | §22 / A |
| `confluence-390-dark-en.png` | Confluence, mobile 390px, EN | §22 / A |
| `confluence-390-dark-zh.png` | Confluence, mobile 390px, ZH | §22 / A |

## B. ADDITIONAL

| file | proves | § |
|---|---|---|
| `overview-320-stress.png` | Overview survives a 320px stress width | §22 / B |
| `confluence-320-stress.png` | Confluence survives a 320px stress width | §22 / B |
| `explore-820-dense.png` | Explore at 820px (tablet/dense) | §22 / B |
| `money-820-dense.png` | Money at 820px (tablet/dense) | §22 / B |
| `overview-bottoming-watch.png` | `#ov-watch-band` strip closeup — self-unhidden (fixture carries 3 bottoming-watch rows), full-width strip under the lanes, never a sixth lane | §22 / B, §9 |
| `overview-access-gated.png` | Access state = gated (boot default): `#actnow`, 3-row preview + 5 disclosures | §22 / B, §21 deliverable 10 |
| `overview-access-hydrated.png` | Access state = hydrated, fetch succeeds: `#actnow` reaches full 4/5/5/3/27 lanes (QA2-07 confirmed fixed) | §22 / B, §21 deliverable 10 |
| `overview-access-fetchfail.png` | Access state = hydrated + simulate-fetch-fail ON: `#actnow` keeps the baked gated shell | §22 / B, §21 deliverable 10 |
| `confluence-empty-lane.png` | Zero-population bucket empty state: Nasdaq-100 tab, Entry-now = 0, `emptyLane()` copy rendered | §22 / B |
| `map-accessible-table.png` | `.r3-cyc-tblbox` — the mandatory accessible text-table equivalent of the sector cycle clock (`window.SECTOR_CYCLES`), all 11 sectors, real rows | §22 / B, §9 |
| `money-heatmap-accessible.png` | `#hm-alt` opened — the mandatory accessible table equivalent of the heat treemap (commission §11), 11 sectors · 503 names | §22 / B, §11 |
| `confluence-universe-sp.png` | Confluence, S&P 500 tab active: 65 rows, ledge 1/16/21/18/9 | §22 / B |
| `confluence-universe-nasdaq.png` | Confluence, Nasdaq-100 tab active: 12 rows, ledge 0/4/2/3/3 | §22 / B |
| `confluence-universe-russell.png` | Confluence, Russell-2000 tab active: 93 rows, ledge 1/16/43/19/14 | §22 / B |
| `confluence-universe-baskets.png` | Confluence, Thematic Baskets tab active: 49 rows, ledge 0/11/16/9/13 | §22 / B |
| `long-name-proof.png` | Longest EN group name across all 4 universes ("Drug Manufacturers - Specialty & Generic", Russell tab) wraps unclipped at 390px | §22 / B |
| `confluence-search-zero.png` | `#cf-q` filter with no match on S&P 500 tab: count reads exactly `0 / 65` | §22 / B, F (zero/empty state) |
| `confluence-russell-showall.png` | "Show all" expanded on Russell tab: DOM-verified 93 rows | §22 / B, F (cardinality-extreme state) |
| `read-trace-open.png` | `#read-gold_miners` deep link: Gold Miners row auto-expanded into its trace card | §21 deliverable 9 (see hash_evidence.md §3) |

`loading-static-shell.png` is **not present** — attempted and not reliably
catchable; reasoning recorded in `state_matrix.md` and GAPS below, per the
frozen-spec instruction to document an unreachable capture honestly rather
than fake it.

## C. ZOOM PROOFS (§17) — 200% zoom via CSS-width-halving, fresh context each

Method: 200% zoom emulated as layout-viewport halving (the standard
browser-zoom equivalence — CSS width W ⇒ emulated viewport width W/2),
`deviceScaleFactor:2`, one fresh context per case (QA2-14 discipline).

| file | proves | § |
|---|---|---|
| `zoom200-overview-320.png` | Overview at 200% zoom / css320 (emu 160px) | §17 / C |
| `zoom200-overview-390.png` | Overview at 200% zoom / css390 (emu 195px) | §17 / C |
| `zoom200-map-390.png` | Map at 200% zoom / css390 | §17 / C |
| `zoom200-moving-390.png` | What's Moving at 200% zoom / css390 | §17 / C |
| `zoom200-money-390.png` | Money at 200% zoom / css390 — reproduces the QA_ATTACK_REPORT §1.4 documented +25/+26px overflow cell | §17 / C |
| `zoom200-explore-390.png` | Explore at 200% zoom / css390 | §17 / C |
| `zoom200-confluence-320.png` | Confluence at 200% zoom / css320 | §17 / C |
| `zoom200-confluence-390.png` | Confluence at 200% zoom / css390 | §17 / C |
| `zoom200-explore-820.png` | Explore at 200% zoom / css820 (emu 410px) | §17 / C |

## D/E/F/G. Written evidence documents

| file | proves | § |
|---|---|---|
| `hash_evidence.md` | Full 31-landing hash/deep-link table (6 canonical + 21 legacy anchors + `#read-gold_miners` + `#theme-gold_miners` + empty hash + unknown hash): resolved view, target-found, landing gap measurement, recorder excerpts | §21 deliverable 9 |
| `access_evidence.md` | The three §15 access states + fetch-fail, DOM-measured lane counts, QA2-07 fix confirmation, `tier_payload.v1` schema-check location | §21 deliverable 10, §15 |
| `state_matrix.md` | State × where-demonstrated × evidence-file table for all 10 commissioned states (loading/zero/empty/stale/partial/error/access-shell/hydrated/long-names/cardinality-extreme) | §21 deliverable 7 |
| `EVIDENCE_INDEX.md` | This file — every evidence file mapped to what it proves and which § it satisfies | §21 deliverable 12 |

## Totals

- PNG screenshots: **58** (A:30 + B:18 present of 19 commissioned + C:9 +
  D:1 `read-trace-open.png`; `loading-static-shell.png` is the one
  documented absence).
- Markdown evidence documents: **4**.
- **Total files: 62** (≥50 required).
