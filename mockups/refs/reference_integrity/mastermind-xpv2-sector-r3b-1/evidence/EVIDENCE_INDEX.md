# Evidence index — XPV2-SC-R3B.1 (Lane D recapture)

**Candidate:** `proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html`
**Candidate sha256:** `fec05b058fbc9dbe29744ad015b7ee9cd9baa5cb85bbbde739daa8b97644cf70`
(5,479,315 bytes — from `proposal/BUILD_MANIFEST.json`, byte-verified against
the tree at capture time with `shasum -a 256`.)

All captures are headless Playwright/Chromium against the exact candidate
file above (`file://` URL, no rebuild). Naming convention follows the R3B
predecessor evidence set: `<view>-<width>-<theme>-<lang>.png`, with a
descriptive prefix for cross-cutting proofs (`contrast-*`, `overview-access-*`,
`confluence-universe-*`, `moving-help-open-*`, `money-*`). Every file below is
committed under this directory; nothing here is orphaned and every file in the
directory is listed.

Capture method notes: (1) regular (non-zoom) screenshots reuse one browser
context, changing view/theme/lang via `REF.setLang`/`data-theme`/hash
navigation; (2) the severe-zoom cell (item 4) uses a **fresh browser context**
per the KNOWN TRAP — `page.screenshot()` permanently breaks CDP
`Emulation.setDeviceMetricsOverride` for that browser session; (3) the
reference harness drawer (`#ref-harness`, "R3 REFERENCE HARNESS — not product
UI") is explicitly non-product chrome; it is left visible in ordinary
screenshots (matches predecessor practice) and hidden only for the item-4 zoom
crop, where its fixed position otherwise overlaps a scroll-stitched element
screenshot — a capture artifact, not a candidate defect.

---

## 1 — Overview: sizing / caveat / migration / playbook / enrichment

Full-page captures (single crop each; all five required elements — sizing
directive, "How this works" caveat, migration note, playbook link, enrichment
metas — fall within the view's natural scroll height, verified via
`[data-r3b1]` marker presence before each shot: markers `01,02,03,04,05a,05b,05c`
all present in every cell).

| file | shows |
|---|---|
| `overview-1440-dark-en.png` | 1440 dark EN — "positions sized to 81%", "How this works" caveat, "Money is rotating" migration note, "Open the playbook →", "49 themes · 15 categories" + 20d/CLIMBING FAST enrichment |
| `overview-1440-light-zh.png` | 1440 light ZH — 仓位缩至 81%、原理说明、迁移说明、进入攻略、49 themes/15 categories 富化元信息 twins |
| `overview-390-dark-en.png` | 390 dark EN — same five elements, mobile width (also indexed under item 8) |
| `overview-390-dark-zh.png` | 390 dark ZH — same five elements, ZH, mobile width (also indexed under item 8) |

## 2 — Moving help controls

| file | shows |
|---|---|
| `moving-help-open-1440-dark-en.png` | desktop OPEN state — the named "How this works" scorecard control (`button.r3-tr-help--named`) clicked, `aria-expanded=true`, disclosure popover text visible ("An accountable scorecard of the rotation read's own calls...") |
| `moving-help-open-390-dark-en.png` | 390 OPEN state, EN, same control |
| `moving-help-open-1440-dark-zh.png` | ZH at one width (1440) — the ZH disclosure open |

## 3 — Chinese document-language probe

| file | shows |
|---|---|
| `lang_probe.txt` | `build/lang_probe.py` run verbatim against this candidate (not rewritten) — 7/7 PASS: boot EN, the page's own `#ref-lang` control → zh-CN, six view activations, two hash repaints, `REF.setLang`, a bare `setAttribute`, and a full reload all hold `lang`/`data-lang` correctly |

## 4 — Money severe-zoom proof

| file | shows |
|---|---|
| `money-verdict-320phys-zoom200-en.png` | `.mny-verdict` element crop at 320-physical/200% (160 CSS × device_scale_factor 2) — "VOLATILITY: CALM" wraps to two lines fully inside its pill, unclipped; harness drawer hidden for this crop only (see method note above) |
| `money-320phys-zoom200-en-full.png` | full-page context for the same cell — confirms zero document overflow (`scrollWidth <= clientWidth`) at this viewport |

## 5 — Contrast proofs

| file | shows |
|---|---|
| `contrast-action-labels-overview-1440-dark-zh.png` | (a) ZH-dark action labels — Overview `#actnow` ledge: 立即买入/接近就绪/看好-勿追高/止盈/观望 |
| `contrast-action-labels-confluence-1440-dark-zh.png` | (a) ZH-dark state labels — Confluence `#cf-ledge`: 现可入场/领先/就绪 |
| `contrast-action-labels-money-1440-dark-zh.png` | (a) ZH-dark risk label — Money `.mny-verdict`: 风险偏好 (Risk-on) |
| `contrast-still-measuring-moving-1440-light-en.png` | (b) light "Still measuring" — Moving track-record badge, EN |
| `contrast-still-measuring-moving-1440-light-zh.png` | (b) light "测量中" — ZH twin |
| `contrast-20d-vs-market-overview-1440-light-en.png` | (c) 20d-vs-market label — Overview board-head column figure, light EN |
| `CONTRAST_TABLE.md` | copied verbatim from `build/lane_crops_b/CONTRAST_TABLE.md` — the measured-ratio table (15,340 cells scored, 0 AA failures, 0 sub-ramp, 0 parser-suspects at this candidate sha; includes the three commissioned rows: ZH-dark 4.79–4.97:1, light "Still measuring/测量中" 6.33:1, "20d vs market" 5.43/5.57:1) |

## 6 — Confluence labeled stock-picks

| file | shows |
|---|---|
| `confluence-picks-1440-dark-en.png` | "Stock picks" / "Conviction" header over the COIN 0.60 / NSC 0.54 figures, EN |
| `confluence-picks-1440-dark-zh.png` | "个股" / "综合把握" header over the same 0.60 / 0.54 figures, ZH |

## 7 — Duplicate-ID / ARIA report

| file | shows |
|---|---|
| `aria_id_audit.txt` | `build/aria_id_audit.py` run verbatim against this candidate — EN: 253 ids, 0 duplicated, 74 refs resolved, 0 unresolved; ZH: same |
| `aria_id_audit.json` | machine output backing the txt summary |

## 8 — All six views, three width/theme/lang combinations (18 cells)

Files marked "(=item 1)" are the same capture already listed under item 1 —
one file, two index entries, no duplicate bytes.

| file | shows |
|---|---|
| `overview-1440-dark-en.png` | (=item 1) |
| `map-1440-dark-en.png` | Map, 1440 dark EN |
| `moving-1440-dark-en.png` | Moving, 1440 dark EN |
| `money-1440-dark-en.png` | Money, 1440 dark EN |
| `explore-1440-dark-en.png` | Explore, 1440 dark EN |
| `confluence-1440-dark-en.png` | Confluence, 1440 dark EN |
| `overview-390-dark-en.png` | (=item 1) |
| `map-390-dark-en.png` | Map, 390 dark EN |
| `moving-390-dark-en.png` | Moving, 390 dark EN |
| `money-390-dark-en.png` | Money, 390 dark EN |
| `explore-390-dark-en.png` | Explore, 390 dark EN |
| `confluence-390-dark-en.png` | Confluence, 390 dark EN |
| `overview-390-dark-zh.png` | (=item 1) |
| `map-390-dark-zh.png` | Map, 390 dark ZH |
| `moving-390-dark-zh.png` | Moving, 390 dark ZH |
| `money-390-dark-zh.png` | Money, 390 dark ZH |
| `explore-390-dark-zh.png` | Explore, 390 dark ZH |
| `confluence-390-dark-zh.png` | Confluence, 390 dark ZH |

## 9 — Severe-zoom matrix (all commissioned cells, programmatic)

| file | shows |
|---|---|
| `zoom_matrix.txt` | `build/zoom_sweep.py` run verbatim against this candidate (not reimplemented) — 48/48 cells (6 views × {320,390,768,820} physical × {EN,ZH} at 200%): 0 document overflow, 0 painted semantic clipping, 0 clipped primary controls |
| `zoom_matrix.json` | machine output backing the txt summary |

## 10 — Canonical / legacy hash smoke

| file | shows |
|---|---|
| `hash_smoke.txt` | every canonical view hash (`#overview #map #moving #money #explore #confluence` — the router's own `VIEWS` list, `si_workspace.js:17`, matched by `VIEWS.indexOf(h)>=0` ahead of the legacy table) resolves to its own view; all 21 `LEGACY_ANCHORS` entries (`si_workspace.js:39-63`) resolve to the expected view (21/21 match) and to the expected scroll-target DOM id (20/21 present — the one absence, `#sc-top`, is the documented recorded seam in `build/README_BUILD.md` "Recorded seam preserved, not repaired", not a new defect) |

## 11 — Gating / hydrate smoke

| file | shows |
|---|---|
| `overview-access-gated.png` | default `gated` access state — Overview `#actnow` board, preview rows capped at 3/lane with "N more — sign in..." disclosures |
| `overview-access-hydrated.png` | `REF.setAccessState('hydrated')` — real production `.actitem` rows inserted (29), disclosures cleared |
| `overview-access-reffail.png` | fresh load with `?reffail=1` armed at parse time — the action-board fetch itself genuinely rejects (`REF.simulateFetchFail`), and `#actnow-section` correctly fails open to a single "Data failed to load — please refresh." placeholder while the surrounding sizing/caveat/migration/playbook/enrichment content (sourced from the synchronous embedded registry, not a live fetch) renders normally |
| `access_counts.txt` | counts line for each of the three states above, plus the boot-resolved `simulated-fail` fetch-log tally (8) under reffail |

## 12 — All four Confluence universes

| file | shows |
|---|---|
| `confluence-universe-sp.png` | S&P 500 (subsectors) tab active — tab strip shows S&P 500 65 / Nasdaq-100 12 / Russell-2000 93 / Thematic Baskets 49 |
| `confluence-universe-nasdaq.png` | Nasdaq-100 tab active, same counts |
| `confluence-universe-russell.png` | Russell-2000 tab active, same counts |
| `confluence-universe-baskets.png` | Thematic Baskets tab active, same counts |
| `confluence_universe_counts.json` | machine-readable per-tab-click count readout backing the four screenshots above |

## Supplementary

| file | shows |
|---|---|
| `_capture_run_notes.txt` | full console log of the capture script's own assertions (marker presence, aria-expanded states, text-content checks, overflow checks, per-cell counts) for every item above — the run-time trail behind this index |
