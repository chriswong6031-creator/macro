# Lane B evidence — XPV2-SC-R3B.1 (accessibility + token repair)

Fix packet items: **R3B1-08 · 09 · 10 · 11 · 12**.
Candidate at capture: `sha256 fec05b058fbc9dbe29744ad015b7ee9cd9baa5cb85bbbde739daa8b97644cf70`
(5,479,315 bytes), deterministic across two rebuilds, `verify_reference.py` 10/10,
`tests/test_xpv2_sector_r3_fixture.py` 59/59.

## Rerunnable gates — for Lane C

All four run headless against `proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html`,
take no screenshots (so CDP device-metrics emulation cannot be corrupted mid-run),
and exit non-zero on any failure. They need a Python environment with Playwright
plus a Chromium build.

| script | gate | result at this sha |
|---|---|---|
| `../zoom_sweep.py` | 6 views × {320, 390, 768, 820} physical × {EN, ZH} at 200%: zero document overflow, zero painted semantic clipping, zero clipped primary controls | **48/48 cells pass**, 0 / 0 / 0 |
| `../contrast_audit.py` | every reference-authored text leaf ≥ 4.5:1 on its composited surface, and none under the 10px ramp floor, at theme × language | **0 failures, 0 sub-ramp cells, 0 parser-suspects** over 15,340 scored cells |
| `../aria_id_audit.py` | document-wide unique ids; every `aria-controls` / `aria-labelledby` / `aria-describedby` / `for` IDREF resolves to exactly one element, in EN and ZH after all six views mount | **253 ids, 0 duplicated; 74 references, 0 unresolved** |
| `../lang_probe.py` | `documentElement.lang` tracks the language through the page's own control, `REF.setLang`, a bare `setAttribute`, six view activations, two hash repaints and a reload | **7/7 PASS**; ZH = `zh-CN` |

Machine output: `zoom_sweep.json`, `contrast_audit.json`, `aria_id_audit.json`,
`LANG_PROBE.txt`. Narrative: `CONTRAST_TABLE.md`.

Three method notes are load-bearing and are documented inside the scripts rather
than only here, because a future run that loses them will silently produce wrong
numbers: Chromium serialises `color-mix()` as `color(srgb …)` in 0–1 (a ratio of
exactly 1.00 means the parser broke, not the page); `overflow:auto` ancestors are
scroll ports, not clippers, and a clipping walk that ignores that charges every
wide table against the rounded card enclosing it; and content parked behind a
closed `<details>` or a `max-height:0` collapse is not clipped meaning.

## Crops

| file | shows | axis |
|---|---|---|
| `01_moving_help_open_1440_dark_en.png` | Rank-fit help control, keyboard-activated, popover open, focus ring on the 44px target | 1440 dark EN |
| `02_moving_help_open_1440_dark_zh.png` | Reliability help control, open, ZH disclosure | 1440 dark ZH |
| `03_moving_help_named_open_1440_dark_en.png` | the named "How this works" scorecard control, open | 1440 dark EN |
| `04_moving_help_open_390_dark_en.png` | the same control on a phone | 390 dark EN |
| `05_moving_help_named_open_390_dark_zh.png` | named control + full ZH disclosure on a phone | 390 dark ZH |
| `06_money_verdict_320phys_zoom200_en.png` | "Volatility: calm" wrapping inside its pill — the MAC-002 clip, closed | 320 physical / 200%, EN |
| `07_money_verdict_320phys_zoom200_zh.png` | the ZH twin | 320 physical / 200%, ZH |
| `08_overview_state_ledge_1440_dark_zh.png` | 立即买入 after the ink-rung repair | 1440 dark ZH |
| `09_confluence_state_ledge_1440_dark_zh.png` | 现可入场 / 领先 / 就绪 after the repair | 1440 dark ZH |
| `10_overview_state_ledge_1440_dark_en.png` | the EN twin, unchanged | 1440 dark EN |
| `11_moving_trackrecord_1440_light_en.png` | light "Still measuring" after the repair | 1440 light EN |
| `12_moving_trackrecord_1440_light_zh.png` | light 测量中 after the repair | 1440 light ZH |
| `13_overview_board_head_1440_light_en.png` | "20d vs market" at the ramp floor in full `--muted` | 1440 light EN |
| `14_money_treemap_820phys_zoom200_en.png` | treemap after the measured label-fit pass — "Consumer Defensive" inside the chart edge | 820 physical / 200%, EN |
| `15_money_treemap_1440_dark_en.png` | treemap at desk width, unchanged in character | 1440 dark EN |

## Pins Lane C can bind

`data-r3b1` markers were added on the repaired structures that have a discrete node:

| marker | node |
|---|---|
| `08` | each of the three Moving help controls (`button.r3-tr-help`) |
| `09` | the Money verdict's chip row (`.mny-chips`), the leaf that was being cut |
| `10` | the harness language control (`select#ref-lang`) that drives `lang` + `data-lang` |
| `11` | the track-record verdict badge (`.r3-tr-q`) and the board's figure column (`.r3-colfig`) |
| `12` | all 22 embedded data-registry blocks (`script#ref-data-<n>`) |

The one stable id the explain pattern now mints is `#r3-receipt` — the single
shared receipt popover, created eagerly at install so every `aria-controls`
pointing at it resolves before anything is opened.
