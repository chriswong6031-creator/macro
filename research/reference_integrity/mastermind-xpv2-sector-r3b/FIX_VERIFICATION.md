# XPV2-SC-R3B — Fix-wave verification record (QA2-01..12 + F-1..F-6)

Persisted by the orchestrator from the fix lane's return packet (fix wave landed
as commit `dfe602a3aea5`), so the re-probe evidence for all 17 dispatched
findings is on disk for the fresh critics. Finding definitions:
`mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/build/QA_ATTACK_REPORT.md`
§8 and `capability_crosscheck.md` FINDINGS detail. QA2-13/14 were NOTEs
(no fix owed): QA2-13 → R3C_HANDOFF_DRAFT.md §3; QA2-14 → capture-method note.

## Build state after fixes

`build_reference.py` clean + deterministic; `verify_reference.py` **10/10**.

## Per-finding re-probe results (fix lane, headless Chromium, fresh context per cell)

| id | fix site | re-probe result |
|---|---|---|
| QA2-01 | money.html `.lead-foot .r3-tag` wrap override | css320/390 @200%: 0px overflow (was +60/+26) |
| QA2-02 | explore.html `.ne-tk` flex-wrap | css320 @200% EN/ZH: 0px (was +36/+32) |
| QA2-03 | explore.html `.exp-frow` + category summary wrap | css320 @200%: 0px |
| QA2-04 | overview.html `.si-vr-t` overflow-wrap:anywhere | css320 @200%: 0px (was +4) |
| QA2-05 | money.html `.hm-sechd` overflow:visible | sector name paints in full at css820 @200% (was clipped, invisible to scrollWidth gates) |
| QA2-06 | shell.html `@media(max-width:820px)` seg min-height | map segments 44.0px at 768/820 EN+ZH (was 40.0) |
| QA2-07 + F-3 | overview.html hydrate rewritten through `REF.fetchJSON` (window.fetch path), per access_hydration_contract §3; baked gated-look baseline renders first so failure leaves nothing to undo (§4) | drawer-switch hydrated → 4/5/5/3/27 with working Show-more; fresh-load hydrated same; fetch-fail+hydrated stays 3/3/3/3/3 + 5 disclosures; gated 3/3/3/3/3+5; ungated 4/5/5/3/27. Note: the original QA2-07 symptom did not reproduce in isolation pre-fix; the architectural F-3 rewrite covers both diagnoses and satisfies every probe. |
| QA2-08 | confluence.html aria-controls → `cf-panel` (role=tabpanel) + arrow-key handler | controls resolve to tabpanel; ArrowRight moves focus+selection |
| QA2-09 | confluence.html ledge keydown re-queries the re-painted tab before focusing | focus stays inside the widget (activeElement remains a [role=tab]) |
| QA2-10 | four aria-labels made language-aware via paint fn at boot + langchange | all four contain CJK under data-lang=zh (操作分组 / 切换轮动图的主题或板块 / 范围 / 时机状态) |
| QA2-11 | moving.html arrows → aria-hidden, no role | 10/10 spans role=null aria-hidden=true |
| QA2-12 | roving tabindex + Home/End on all 3 tablists (14 tabs) | 0/-1 swap verified; Home/End land first/last |
| F-1 | overview.html: removed extra `__siRoute()` call (production calls `__siViewReads` alone, sector_central.html.j2:3088); `stopImmediatePropagation` stops the shim's sibling capture listener | `#read-gold_miners` → trace stays open, ZERO false nav records |
| F-2 | overview.html Bottoming Watch rows as `<a data-ref-nav href>` per `_us_bottoming_watch.html.j2:95` | 3 anchors with real basket/*.html hrefs; click records exact route |
| F-4 | map.html reasoning-chain layer/tier ZH via LAYER_ZH (bound from sector_central_china.html.j2:1425) + tier labels (signal_lab tier_labels, 已验证); money.html driver-legs LEG_ZH | map: 57/57 layer + 57/57 tier leaves CJK, zero leaks; money leadership ZH line fully ZH |
| F-5 | moving.html drawTrackRecord port (subsector_rotation.js:319-345 field-for-field) | horizons table with real numbers (matured counts, hit rates, IC, t-stat), verdict "Still measuring"/"测量中", 8 recent misses |
| F-6 | runtime_shim.js: reconciled `--ref-sticky-offset` consumption (explore/money local scroll-margin redeclarations now consume it) + bounded one-shot re-scroll after 350ms settle | mechanism verified firing; residual: `#tm-mount`/`#grader` land at the page's natural scroll ceiling (`scrollY == scrollHeight − innerHeight`), a page-length property of near-bottom targets — the target is visible and NOT under sticky chrome, which is what commission §14 requires. Adjudicated accepted; recorded in design_notes.md §5 / responsive_contract.md §1. |

## New ZH strings from this wave (also in copy_ledger.md)

操作分组 · 切换轮动图的主题或板块 · 范围 · 时机状态 (aria-labels) ·
趋势把关 (map layer, authored — absent from LAYER_ZH) · 参与广泛 · 回报加速
(money driver-legs, authored) · 广度推进 (reused verbatim from
`templates/_risk_radar_card.html.j2`).

## Post-fix regression sweep

Full width sweep 6 views × 9 widths (320–1440): 54/54 cells, 0 document
overflow; 200%-zoom cells that previously failed: 7/7 now 0px.
