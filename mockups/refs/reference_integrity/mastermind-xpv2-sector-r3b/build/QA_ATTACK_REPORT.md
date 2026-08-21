# XPV2-SC-R3B — QA ATTACK REPORT (v2, adversarial lane)

**Route:** review (QA attack lane, commission SS4.1 / SS17 / SS24)
**Artifact under attack:** `mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html` (5,431,707 bytes)
**Harness:** local `python3 -m http.server 8863`, Chromium via playwright-core, CDP `Emulation.setDeviceMetricsOverride` = measurement authority.
**Status:** IN PROGRESS — appended pass by pass.

## Contents
- SS1 Gate verdicts (6)
- SS2 Width sweep matrix
- SS3 ZH parity
- SS4 ARIA
- SS5 Keyboard
- SS6 Access states + fetch-fail
- SS7 Authority masquerade (SS24)
- SS8 Findings table
- SS9 Method / limits


---

## §1.4 GATE 4 — 200% zoom, all six views × 320/390/768/820 — **FAIL**

Method: CSS-width-halving emulation (200% zoom ⇒ layout viewport = CSS width / 2), CDP
`Emulation.setDeviceMetricsOverride` (`width=160/195/384/410`, `deviceScaleFactor=2`) for the
48-cell sweep; independent per-context re-measurement (`viewport.width=emu`, `deviceScaleFactor:2`)
for the screenshot captures. Metric = `documentElement.scrollWidth - documentElement.clientWidth`.
48 cells = 4 widths × 2 langs × 6 views.

**Result: 42/48 cells clean, 6 cells FAIL.** All five seeded `qa_findings/` overflows REPRODUCE
at the seeded magnitudes, plus one additional clipped-primary-content cell at css820.

| css width | emu (200%) | lang | view | clientWidth | scrollWidth | overflow | verdict |
|---|---|---|---|---|---|---|---|
| 320 | 160 | en | overview | 160 | 164 | **+4 px** | FAIL |
| 320 | 160 | en | money | 160 | 220 | **+60 px** | FAIL |
| 320 | 160 | en | explore | 160 | 196 | **+36 px** | FAIL |
| 320 | 160 | zh | explore | 160 | 192 | **+32 px** | FAIL |
| 390 | 195 | en | money | 195 | 220/221 | **+25/+26 px** | FAIL |
| 390 | 195 | en | explore | 195 | 196 | **+1 px** | FAIL |
| 820 | 410 | en | money | 410 | 410 | 0 px | FAIL (clipped primary name, below) |
| all other 41 cells | — | — | — | — | — | 0 px, 0 clipped | PASS |

### Root causes (CDP ancestor-chain measurement, not inference)

**QA2-01 · `.r3-tag { white-space:nowrap }` cannot shrink — Money & Breadth, EN only.**
`span.l-en` "Forward track record: Validated", `white-space:nowrap`, intrinsic width **174.8 px**
inside `span.r3-tag` (**191 px**, `ws:nowrap`) inside `p.lead-foot` (**134 px** wide, `scrollWidth 207`).
No ancestor has `overflow-x:auto|hidden` — the 57 px excess propagates to `div.si-stage`
(`w:160, sw:220`) and out to the document. ZH passes only because "前瞻战绩：已验证" is shorter —
i.e. the layout is one string-length away from failing in ZH too, so this is not a ZH-safe design.

**QA2-02 · Forming Narratives ticker rows do not wrap — Explore, EN *and* ZH.**
`span.ext` ("+24.6%", "+52.6%", "+17.3%", "+14.1%") right-edges at **185.1 / 176.7 / 166.2 / 164.5 px**
against `clientWidth 160`. Chain: `span.ne-tk` (`w:170`) → `div.ne-recs` (`w:108, sw:170`) →
`div#ne-c57ebeee3468.ne-card` (`w:134, sw:183`) → `section#forming-narratives.r3-band` (`w:136, sw:184`).
Every ancestor is `overflow-x:visible` — nothing clips or scrolls, so the excess reaches the document.
ZH is the same defect (`sw 192`, three offenders), so this is **not** a translation-length artifact.

**QA2-03 · Explore filter segmented control does not wrap — Explore, EN.**
`button` "Raw" / "vs S&P" inside `span#btbl-mode.r3-seg.exp-modes` (`w:56`) inside
`div.exp-frow` (`w:108, sw:156`) inside `div.exp-filters` (`w:134, sw:169`). Right edge 166.6 vs
clientWidth 160. Contributes to the same 36 px document overflow and additionally makes the mode
selector partially unreachable without horizontal document scroll.

**QA2-04 · Overview answer lede overflows its own read slot — Overview, EN.**
`span.l-en` "Memory, HBM & Storage is handing leadership to Big…" measures **99.8 px** inside
`span.si-vr-t` whose box is **57 px** (`scrollWidth 100`), inside `p#si-read-overview.si-view-read`
(`w:121, sw:137`) → `div.r3-answer` (`w:136, sw:149`) → document `sw 164`. The primary
answer sentence — the single most important string on the action view — is the overflowing element.

**QA2-05 · Clipped primary sector name at css820/200% — Money & Breadth, EN.**
`documentElement` overflow is 0, so a scrollWidth-only gate passes this cell, but the classified
off-screen walk reports `span.l-en` "Consumer Defensive", `left 292 → right 411.4`, clipped by
`div.hm-sechd` (`overflow-x:hidden`). Commission §17 forbids a *clipped primary name* independently
of document overflow; this cell therefore fails Gate 4 on the second clause. It was NOT in the seeded
set (the seeded sweep gated on overflow only).

### Seeded-findings verification

| seeded file | seeded magnitude | re-measured | status |
|---|---|---|---|
| `GATE4-zoom200-css320-en-explore-overflow36px.png` | +36 | +36 | REPRODUCES |
| `GATE4-zoom200-css320-en-money-overflow60px.png` | +60 | +60 | REPRODUCES |
| `GATE4-zoom200-css320-en-overview-overflow4px.png` | +4 | +4 | REPRODUCES |
| `GATE4-zoom200-css320-zh-explore-overflow32px.png` | +32 | +32 | REPRODUCES |
| `GATE4-zoom200-css390-en-explore-overflow1px.png` | +1 | +1 | REPRODUCES |
| `GATE4-zoom200-css390-en-money-overflow26px.png` | +26 | +25 (CDP) / +26 (context) | REPRODUCES (±1 px measurement-path rounding) |

New screenshots: `qa_findings/QA2-GATE4-zoom200-css{320,390,820}-{en,zh}-{view}-{tag}.png` (7 files, fullPage).

### Method warning for downstream lanes (measurement-integrity note, not an artifact defect)

`page.screenshot()` **clears a CDP `Emulation.setDeviceMetricsOverride`** applied on a
user-created CDP session, and a subsequent `setDeviceMetricsOverride` on that same session does not
re-take. A screenshot-in-the-loop harness therefore silently measures at the *context* viewport
(1440) from the second iteration on and reports `over=0` for genuinely-failing cells — measured here:
same seven cases returned `60,0,0,0,26,0,0` in a shared-page loop vs `60,36,4,32,25,1,0` with a fresh
context per case. Any future zoom harness must use a fresh context per capture (or CDP
`Page.captureScreenshot`). This is how a Gate-4 regression could be "proved clean" by accident.

---

## §1.1 GATE 1 — Overview phone, five action states + counts at 320 — **PASS**

CDP `Emulation.setDeviceMetricsOverride`, `width=320`, `dsf=1`, EN.

| state tab | text (label/count) | w × h | left → right | aria-selected |
|---|---|---|---|---|
| 1 | `BUY NOW / 4` | 294 × **56** | 13 → 307 | true |
| 2 | `ALMOST READY / 5` | 294 × **56** | 13 → 307 | false |
| 3 | `IN FAVOUR — DON'T CHASE / 5` | 294 × **56** | 13 → 307 | false |
| 4 | `TAKE PROFITS / 3` | 294 × **56** | 13 → 307 | false |
| 5 | `STAND ASIDE / 27` | 294 × **56** | 13 → 307 | false |

All five labels AND all five counts are rendered and visible (stacked full-bleed, `overflow-x:visible`
on the tablist — no horizontal scroller hiding a state). `documentElement.scrollWidth - clientWidth = 0`.
No state is `display:none` at any swept width (visible-control count is a constant 12 across
320/360/390/430/768/820/1024/1280/1440 in both langs — §2). Target height 56 px ≥ 44. **PASS on all four clauses.**

## §1.2 GATE 2 — Map phone composition — **PASS**

Measured DOM/paint order at 390 (document-space `top`, CDP):

| order | element | top | note |
|---|---|---|---|
| 1 | `div.r3-answer` (`THE MAP` + "14 groups sit top-right…") | 212 | concise context answer |
| 2 | `div#r3-map-quads.r3-quads` (`LEADING 14 / WEAKENING 13 / IMPROVING 2 / LAGGING 9` + exemplar names) | 536 | quadrant summary |
| 3 | `SELECTED GROUP` card (Big Pharma, rank 1, score 77, +11.5%, rank move +9) | 805 | selected object |
| 4 | `table#rvx-board` (11 rows) inside `overflow-x:auto` parent (`parentW 358`, `table 606.2`) | — | accessible ranked list |
| 5 | `button "Hide the full map"` `aria-expanded=true` `aria-controls=r3-map-plot` | 2054 | full map, same view, explicit disclosure |

The commission's phone priority order (answer → quadrant summary → selected object → accessible list)
is satisfied and the full plot is demoted below all four, behind a real disclosure, in the same view —
exactly the permitted shape. Contrast desktop 1440 where `svg#rvx-rmap` sits at top 322, *above* the
quadrants at 871: the mobile order is a genuine re-composition, not a CSS shrink of the desktop stack.

NOTE (not a gate failure): the plot behind the disclosure is still the desktop geometry —
`svg#rvx-rmap viewBox="0 0 600 400"` painted at **244 × 162.7** at css320 and **306 × 204** at css390
(linear scale 0.41 / 0.51 of the 1440 rendering at 707.7 × 471.8). Commission §9 permits this
("the full map may remain further down the same view, behind an explicit disclosure"), so it is
recorded, not filed as a finding.

## §1.3 GATE 3 — Confluence states + universes — **PASS**

| width | 5 state names + counts simultaneously visible | universe selectors visible | doc overflow |
|---|---|---|---|
| 320 | yes — `ENTRY NOW 1 / TAILWIND 16 / NEUTRAL 21 / LATE 18 / HEADWIND 9`, each 294 × 56 | 4/4 (`S&P 500 65`, `Nasdaq-100 12`, `Russell-2000 93`, `Thematic Baskets 49`), each 296 × **44** | 0 |
| 390 | yes, 178 × 56 (2-up) | 4/4, 178 × 44 | 0 |
| 768 | yes, 110.8 × 82 | 4/4, 111.2–165.6 × 44 | 0 |
| 1440 | yes, 236.4 × 82 | 4/4, 111.2–165.6 × 44 | 0 |

**All four universe selectors are present on phone** (320 and 390) at exactly 44 px height.
**No population-scaled label container:** the `.r3-state` label boxes measure 22.0–61.7 px and track
*string length only* — their widths are byte-identical at 320/390/768/1440 (`56.1, 47.0, 47.0, 34.5,
47.0, 47.0, 56.1, 49.1, 22.0, 47.0, 47.0`) while the population counts differ per state (1/16/21/18/9)
and the parent `.cf-line` box changes with viewport (133 → 143.3 → 159.3), never with population.
Font-size is a constant `10px` across all four widths — no count-driven type scaling.

## §1.5 GATE 5 — ≥44 CSS px targets, six views, ≤820 px — **FAIL (2 controls, 4 cells)**

72 cells swept (6 widths {320,360,390,430,768,820} × 2 langs × 6 views); enumerated every
`a[href] / button / select / input / [role=button] / [role=tab] / summary / [tabindex]` visible in the
active view, harness drawer excluded. **68/72 cells clean.**

| width | lang | view | control | measured | required |
|---|---|---|---|---|---|
| 768 | en | map | `button` "Themes 38" | 98.4 × **40.0** | ≥ 44 |
| 768 | en | map | `button` "Sectors 11" | 96.9 × **40.0** | ≥ 44 |
| 768 | zh | map | `button` "主题 38" | 74.2 × **40.0** | ≥ 44 |
| 768 | zh | map | `button` "板块 11" | 69.4 × **40.0** | ≥ 44 |
| 820 | en/zh | map | same two | 98.4/96.9 and 74.2/69.4 × **40.0** | ≥ 44 |

The Map universe segmented control (`.r3-seg`) is the primary universe switch on the view — a
repeated/primary target by any reading — and it is **4 px short at both tablet-portrait widths in
scope**. It is compliant at ≤430 (a breakpoint restores the taller box), so the defect is a
media-query gap at 768–820, i.e. exactly the iPad-portrait band the gate names. Severity MAJOR
(named gate, deterministic, both languages, both widths).

## §1.6 GATE 6 — Scroll-offset law / routing — **PASS (29 landings)**

Sticky chrome inventory at 390: `div.r3-frame` (`position:sticky; top:0; height 40; z 60`) and
`nav.si-side` (`position:sticky; top:40px; height 108.8; z 30`) → combined chrome bottom **148.8 px**.

- **6 canonical hashes** — all activate the correct view, `scrollY = 0`. PASS.
- **21 LEGACY_ANCHORS** (routing_contract §2, verbatim) — 21/21 activate the correct view.
  20/21 resolve a real intra-view target and land it at `getBoundingClientRect().top` of
  **159.5–160.4 px** (17 anchors) or 289 / 671.7 (`#grader`, `#tm-mount`) — every one of them
  **clear of the 148.8 px sticky chrome**, with ≈11 px of slack on the tight cluster. No target
  sits under sticky chrome. Representative: `#actnow-section` scrollY 302 / top 160.4;
  `#board` scrollY 3763 / top 159.9; `#forming-narratives` scrollY 5234 / top 159.9 (resolves —
  the R3A "target-id existence caveat" does **not** reproduce in this candidate);
  `#tm-mount` scrollY 7294 / top 671.7.
- `#sc-top` — view activates (`confluence`), target id absent, silent scroll no-op.
  **RECORDED PRODUCTION SEAM, not a finding** (per commission scope).
- **`#read-<real-id>` family** — `data-mlc-bid` ids exist and are real
  (`gold_miners, ai_agents, non_ai_software, us_sector_staples, us_sector_materials, us_sector_comm,
  big_pharma, silver_miners`). `#read-gold_miners` → view `overview`, scrollY 292, row expanded;
  `#read-ai_agents` → view `overview`, scrollY 372, row expanded. Matches
  `si_workspace.js:314` semantics.
- **Unknown `#read-` id** — `#read-nonexistent-id-999` → `overview`, scrollY 0, no error state,
  no console warning. Matches routing_contract §4 ("harmlessly re-tried").
- **Unknown hash** — `#totally-unknown-hash-xyz` → `overview`, scrollY 0. PASS.
- **Empty hash** — lands `overview` **and rewrites the URL to `#overview`**
  (`location.href` tail = `…_R3_CANDIDATE.html#overview`), matching routing_contract §5's
  `history.replaceState` clause. PASS.

Total measured landings: 6 + 21 + 2 (`#read-` real) + 1 (`#read-` unknown) + 1 (unknown) + 1 (empty)
= **32**, above the 27 required.

---

## §2 WIDTH SWEEP MATRIX (commission §17) — **PASS, 216/216 cells clean**

9 widths {320, 360, 390, 430, 768, 820, 1024, 1280, 1440} × 2 themes {dark, light} × 2 langs {en, zh}
× 6 views = **216 cells**, CDP device-metrics per width, 100% zoom.

Per cell asserted: (a) `documentElement.scrollWidth − clientWidth == 0`; (b) zero classified
off-screen leaf nodes that are neither inside a genuine `overflow-x:auto|scroll` scroller nor a
`.r3-vh` visually-hidden node; (c) zero clipped state labels
(`.r3-ov-state, .r3-state, .r3-segn` with `scrollWidth > clientWidth` or edges outside the viewport);
(d) zero clipped primary names (`.r3-ledge-name, .r3-name, .hm-sechd span, .r3-row-name`).

**Result: `CELLS 216 / FAILCELLS 0`.**

**Hidden-only capability / off-screen control:** visible interactive-control counts are constant
across the whole width range per view+lang — overview 12/12, money 2/2, explore 118/118,
confluence 37/37; map 38 at ≤430 vs 37 at ≥768; moving 27 at ≤430 vs 26 at ≥768. Set-differencing
the control *signatures* between 1440 and 390 gives **zero capabilities lost on phone** in all six
views; the phone-only extra controls are two additive disclosures
(`map`: "Hide the full map"; `moving`: "Show the whole-market map"). No capability is phone-hidden.

The 200%-zoom failures in §1.4 are therefore **zoom-specific**, not width-specific: this artifact is
clean at every named width at 100% and breaks only when the layout viewport is halved.

---

## §6 ACCESS STATES + FETCH-FAIL — **FAIL (one CRITICAL)**

Harness `#ref-access` drives `gated / hydrated / ungated`; `window.REF.log` is the route/fetch recorder.
Reference contract: `research/reference_integrity/mastermind-xpv2-sector-r3/access_hydration_contract.md` §3
step 6 — on hydrate success the client must
(a) `insertAdjacentHTML('beforeend', …)` the withheld rows into each lane fold,
(b) `restoreFold(col)` rebuild the "Show more (N)" control for any lane now over 3 rows,
(c) remove the `.pg-more` sign-in disclosure lines.

### Measured per access state — Overview Act-Now (`#ov-panel`, 1440x900, EN)

| access | DOM rows in panel | per-lane DOM rows (buy/soon/run/trim/aside) | visible rows in active lane | `.pg-more` lines | "Show more (N)" controls |
|---|---|---|---|---|---|
| `ungated` | **44** | 4 / 5 / 5 / 3 / **27** | 3 | 1 | `(1) (2) (2) (24)` |
| `gated` | **15** | 3 / 3 / 3 / 3 / **3** | 3 | **5** | none |
| `hydrated` | **15** | 3 / 3 / 3 / 3 / **3** | 3 | **0** | `(1) (2) (2) (24)` |

Gated is correct: 3 preview rows per lane, per-lane locked disclosures whose counts match the full-board
counts exactly — "1 more here — sign in to see the full lane" (BUY NOW, 4 total), "2 more" (ALMOST READY, 5),
"2 more" (IN FAVOUR, 5), none (TAKE PROFITS, 3 = 3), "24 more" (STAND ASIDE, 27). Fold rebuild is correct in
all three states: the "N of M shown" line tracks the selected lane (`3 of 4`, `3 of 5`, `3 of 5`, `3 of 3`,
`3 of 27`) rather than a stale board-level number. Full counts come from the full board in every state
(tab badges read `4 / 5 / 5 / 3 / 27` under `gated` too) — no null-to-zero collapse, no teaser-count invention.

### QA2-07 (CRITICAL) — `hydrated` performs (b) and (c) but never (a)

Direct click test on the STAND ASIDE lane (`#dash-hold-fold`), same script, three access states:

```
UNGATED   domRowsInLane=27  visBefore=3  button="Show more (24)"  visAfterClick=27
HYDRATED  domRowsInLane=3   visBefore=3  button="Show more (24)"  visAfterClick=3
GATED     domRowsInLane=3   visBefore=3  button=null              visAfterClick=3
```

The authenticated journey the reference actually renders is: sign in, the honest
"24 more here — sign in to see the full lane" disclosure is **deleted**, a
"Show more (24)" button appears, and **clicking it reveals nothing** (3 to 3). The signed-in state is
strictly *worse* than the gated state: gated tells the truth about what is withheld; hydrated
removes the truthful line and replaces it with a control that promises 24 rows the DOM does not
contain. This is §24 `access split collapse` plus `dead destination` in one defect, and it is the only
one of the three §15 evidence states that is not reproducible from this artifact.

Screenshot: `qa_findings/QA2-CRIT-hydrate-no-rows-showmore24-dead.png` (hydrated, STAND ASIDE,
after clicking "Show more (24)" — still three rows).

### Fetch-fail — **PASS**

`#ref-failfetch` then a walk of all six views. Recorder log confirms the simulated failures are real
and are recorded, not silently swallowed:

```
{"seq":10,"type":"fetch","path":"marketdata/rotation_events.json","result":"simulated-fail"}
{"seq":11,"type":"fetch","path":"marketdata/sector_fragmentation.json","result":"simulated-fail"}
{"seq":12,"type":"fetch","path":"marketdata/subsector_rotation.json","result":"simulated-fail"}
{"seq":13,"type":"fetch","path":"basketdata/oracle_turn_desk.json","result":"simulated-fail"}
{"seq":14,"type":"fetch","path":"basketdata/oracle_tape_onset.json","result":"simulated-fail"}
{"seq":15,"type":"fetch","path":"basketdata/baskets.json","result":"simulated-fail"}
```

Page survives on every view; **zero** occurrences of `undefined`, `NaN`, `null`, `[object Object]`,
`TypeError`, `Infinity` in the rendered text of any of the six views. Production-shaped strings appear
instead — EN "Rotation-event data unavailable.", "Data failed to load — please refresh."; ZH
"数据加载失败 — 请刷新。", "篮子数据未能送达，暂时无法比较。其他视图不受影响。", "暂无可绘制曲线".
Null-to-zero collapse not observed. No invented access-denied banner, no locks on non-Overview views
(`gated`/`hydrated`/`ungated` produce identical map/moving/money/explore/confluence text lengths:
5037 / 4251 / 4974 / 7143 / 1911 in all three states).

---

## §3 ZH PARITY — **PARTIAL (one MAJOR)**

Method: with `#ref-lang = zh`, per view, count (i) visible `.l-en` spans that leaked through the
language switch, (ii) `aria-label` values containing no CJK, (iii) visible button/summary/tab labels
with no CJK, (iv) `placeholder` values with no CJK, (v) visible `th` with no CJK.

| view | leaked visible `.l-en` | aria-labels with no CJK | buttons with no CJK | `th` with no CJK | placeholders |
|---|---|---|---|---|---|
| overview | **0** | 1 — `"Action lanes"` | 0 | 0 | 0 |
| map | **0** | 1 — `"Show themes or sectors on the rotation map"` | 0 | 0 | 0 |
| moving | **0** | 9 — `"moved to"` x9 | 0 | 0 | 0 |
| money | **0** | 0 | 0 | 6 — `1D 3D 1W 2W 1M` + one | 0 |
| explore | **0** | 0 | 21 (producer `category` values) | 6 — `1D 5D 20D 60D MTD YTD` | 0 |
| confluence | **0** | 2 — `"Universe"`, `"Timing states"` | 0 | 1 — `RS60` | 0 |

**Zero EN leakage in generated rows, buttons, empty/error states or state vocabulary** — the
`.l-en`/`.l-zh` twin mechanism holds everywhere, including the fetch-fail strings above and the
gated/hydrated disclosure lines. Period tokens (`1D/5D/20D/MTD/YTD/RS60`) are read as conventional
untranslatable finance tokens and are not filed.

The 21 untranslated Explore filter buttons are producer `category` values
(`Software`, `Materials & Mining`, `Artificial Intelligence`, `US Sectors (EW)`, ...) —
**recorded producer gap, NOT a finding**, per `ORCHESTRATOR_ADJUDICATIONS.md` §6
("category filter in a labelled `<details>` (summary always names the active state)") and §7
("ZH label falls back to EN instead of a raw slug — disclosed rather than silent").

### QA2-10 (MAJOR) — authored accessible labels are English-only in ZH

Unlike the producer `category` gap, these strings are **reference-authored copy** with no
producer origin, and commission §17 lists "accessible labels" as an explicit ZH-parity clause:

| view | attribute | value (identical in EN and ZH) |
|---|---|---|
| overview | `[role=tablist] aria-label` | `Action lanes` |
| map | `[role=group] aria-label` | `Show themes or sectors on the rotation map` |
| confluence | `[role=tablist] aria-label` | `Universe` |
| confluence | `[role=tablist] aria-label` | `Timing states` |
| moving | `span.r3-arrow[role=img] aria-label` x9 | `moved to` |

A ZH screen-reader user hears the tab/group structure of three of the six views in English.
Every *visible* string on the same controls is correctly twinned — only the AT layer is monolingual.

### QA2-11 (MINOR) — `aria-label="moved to"` is a meaningless fragment in **both** languages

`MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html:2821`:

```js
var ARROW='<span class="r3-arrow" role="img" aria-label="moved to"></span>';
```

A decorative connector glyph is promoted to `role="img"` with a two-word verb fragment as its
accessible name, so a nonvisual reader of What's Moving hears "moved to" nine times with no subject
and no object. Either `aria-hidden="true"` (it is decorative — the flanking names carry the meaning)
or a complete, translated label.

---

## §4 ARIA — **PARTIAL (two MAJOR)**

**Not faked.** Real `role=tablist` / `role=tab` / `role=tabpanel` on Overview (5 tabs) and Confluence
(two tablists: 4 universes + 5 timing states); real `role=group` plus `aria-pressed` on every
filter/segment set (map universe 2, explore mode 3 / category 16 / compare-mode 2 / range 5); panels
carry `aria-labelledby` pointing at the selected tab. **Zero `a[href="#"]` in all six views.
Zero `title=` attributes in all six views** (so the "no translated text in `title=`" law is
vacuously satisfied). Three customer-relevant charts all carry accessible names via
`aria-labelledby` resolving to real text, plus text equivalents with real data:

| chart | accessible name (resolved) | equivalent |
|---|---|---|
| `svg#rvx-rmap` (map) | "Rotation map — strength against the S&P ..." + "Of 38 groups: 14 leading, 13 weakening, ..." | `table#rvx-board`, 11 rows |
| `svg#r3-cyc-svg` (map) | "Sector cycle clock — every sector's 0 to..." + "The table beneath this chart lists every..." | 12-row table + 11 `<details>` |
| `svg#r3-wm-svg` (moving) | "Whole-market rotation map — relative str..." + "The groups the producer names as emergin..." | named list |

### QA2-08 (MAJOR) — Confluence Universe tablist declares the tabs pattern and honours neither half

1. **No keyboard navigation.** Focus the first universe tab, press `ArrowRight`:
   focus stays on `S&P 500/65`, `aria-selected` unchanged. Overview's tablist *does* move
   focus and selection on `ArrowRight`, so this is a per-widget omission, not a global choice.
2. **`aria-controls` targets a non-panel.** All four universe tabs declare
   `aria-controls="sc-app"`; `document.getElementById('sc-app')` resolves to
   `<div class="r3-board st-buy">` with **`role === null`**. There is exactly one
   `role=tabpanel` in the view and its id is `cf-panel`. A `role=tab` whose controlled element is
   not a tabpanel is precisely the fake tab semantics §17 forbids — the pattern is announced to
   AT and then not honoured.

### QA2-09 (MAJOR) — Confluence Timing-states tablist loses focus to the shell root on arrow key

Focus `ENTRY NOW/1`, press `ArrowRight`: selection correctly advances to `TAILWIND/16`, but
`document.activeElement` becomes the page shell root (its `innerText` begins
`REFERENCE · XPV2-SC-R3B SH...`), i.e. focus escapes the widget — the re-render replaces the focused
button without restoring focus. A keyboard user is ejected to the top of the document on every
state change.

### QA2-12 (MINOR) — no roving tabindex; `Home`/`End` unimplemented

All 14 `role=tab` elements across the three tablists carry `tabindex === null`, so every tab sits in
the sequential tab order (APG specifies `tabindex="-1"` on unselected tabs and `0` on the selected
one). `End` on the Overview tablist leaves focus on the second tab rather than the last.

---

## §5 KEYBOARD — **PARTIAL**

- **Visible focus: PASS.** A focused `role=tab` computes
  `outline: solid 2px color(srgb 0.478 0.655 0.878 / 0.7)` — a real, non-suppressed focus ring.
- **Disclosures operable: PASS.** Every disclosure is a native `<details>/<summary>` or a real
  `<button>` with `aria-expanded` (`Hide the full map` carries `aria-expanded=true`,
  `aria-controls=r3-map-plot`; 11 `<details>` on Map; 2 on Explore; 1 each on Money and Moving).
  **Zero elements carry `aria-expanded` on a non-button, non-summary, non-`role=button` host**
  in any of the six views — no faked disclosure hosts.
- **Tab order / arrow keys: FAIL on two of three tablists** — see QA2-08, QA2-09, QA2-12.

---

## §7 AUTHORITY MASQUERADE (§24) — **PASS**

| §24 item | probe | result |
|---|---|---|
| context sector promoted to Buy now / State-Ledge treatment on a context view | count `.r3-ledge*`, `.r3-lane*`, `.r3-cta`, `.st-buy`, `[data-lane]`, and any class matching ledge/lane/cta/primary/action inside the active view | `overview` 7, `confluence` 3, **`map` 0, `moving` 0, `money` 0, `explore` 0** — ledge/lane vocabulary exists only on the two action views |
| action fills / primary CTAs on context views | enumerate every `button`/`a` whose background alpha exceeds 0.5 | only `rgb(30,34,42)` — the neutral segmented-control surface token, identical on action and context views; no saturated action fill anywhere |
| action lane drift / Bottoming Watch escalation | count `[role=tab]` in the Overview tablist; scan for Early Entry / Early Turn / Upgrade Watch / Entry Pipeline | exactly **5** lanes (BUY NOW, ALMOST READY, IN FAVOUR — DON'T CHASE, TAKE PROFITS, STAND ASIDE); zero forbidden renames; Bottoming Watch renders as "All 3 rows: cycle turn signal — watch only · may be bottoming" — watch-only, nonpredictive, **not a sixth lane** |
| hidden `signal` / `timing_state` field rendered raw | scan rendered text for the raw field tokens | none; only prose ("Unconfirmed — raw signal, not an episode.", "Noisy signal; many clusters fade. Watchlist only, not a buy signal.") |
| falsifier vocabulary front-facing | falsif / refut / 证伪 / invalidat / tripwire / disproven across all six views, EN and ZH | **zero matches** |
| foreign-universe Confluence row / client recomputation | switch all four universes, sum the five state counts, compare to the universe total | S&P 500 `1+16+21+18+9 = 65` = 65; Nasdaq-100 `0+4+2+3+3 = 12` = 12; Russell-2000 `1+16+43+19+14 = 93` = 93; Thematic Baskets `0+11+16+9+13 = 49` = 49 — **exact in all four**, no leakage, no client re-rank |
| fabricated Baskets coverage | look for an "N of M have enough live data" coverage line per universe | printed for S&P 500 (`65 of 113 ... 48 thin`), Nasdaq-100 (`12 of 12`), Russell-2000 (`93 of 93`); **absent for Thematic Baskets** — the correct absence, not an invented number |
| false correction state / correction affordance | scan for correct / revis / amend / restat / 更正 / 修订 across all six views | **zero matches** — no correction affordance invented |
| dead destination | `a[href="#"]` per view | **0 / 0 / 0 / 0 / 0 / 0** |
| translated text in `title=` | `[title]` per view | **0 / 0 / 0 / 0 / 0 / 0** |
| Map reco tertiary | Map view carries no `.r3-ledge*` / `.r3-cta` and its only filled control is the neutral universe segment | reco stays tertiary |

No authority-masquerade finding. This dimension is the artifact's strongest.

---

## §8 FINDINGS TABLE

| id | sev | view | width / lang / theme | symptom | measurement | suggested owner lane |
|---|---|---|---|---|---|---|
| **QA2-07** | **CRITICAL** | overview | any / en+zh / any | `hydrated` access state removes the sign-in disclosure and renders "Show more (24)" but never inserts the hydrated rows; the control is dead and the signed-in view is less honest than the gated one | `dash-hold-fold` DOM rows: ungated **27**, hydrated **3**; clicking "Show more (24)": ungated 3 to **27** visible, hydrated 3 to **3**. `.pg-more` count: gated 5, hydrated **0** | access/hydration lane |
| **QA2-01** | MAJOR | money | css320 + css390 at 200% / en / both themes | `.r3-tag{white-space:nowrap}` on the "Forward track record: Validated" tag cannot shrink; drives document overflow | span 174.8 px inside `.r3-tag` 191 px inside `p.lead-foot` 134 px; doc `sw 220` vs `cw 160` = **+60 px**; at cw 195 = **+25/26 px**. No `overflow-x` ancestor | D3 (Money) |
| **QA2-02** | MAJOR | explore | css320 at 200% / **en and zh** / both | Forming Narratives ticker rows (`span.ne-tk` to `span.ext`) do not wrap; every ancestor is `overflow-x:visible` | EN right edges 185.1 / 176.7 / 166.2 / 164.5 vs `cw 160`, doc **+36 px**; ZH 180.8 / 171.5 / 162.9, doc **+32 px**; css390 EN **+1 px** | D3 (Explore) |
| **QA2-06** | MAJOR | map | 768 and 820 / en+zh / both | Map universe segmented control ("Themes N" / "Sectors N") is below the 44 px floor at both tablet-portrait widths in Gate-5 scope | 98.4 x **40.0**, 96.9 x **40.0** (en); 74.2 x **40.0**, 69.4 x **40.0** (zh). Compliant at 430 and below: media-query gap at 768-820 | D2 (Map) |
| **QA2-08** | MAJOR | confluence | any / any / any | Universe tablist declares `role=tab` but has no arrow-key navigation, and `aria-controls="sc-app"` resolves to `div.r3-board` with `role === null` (the only `role=tabpanel` is `cf-panel`) | ArrowRight: focus and `aria-selected` both unchanged; `getElementById('sc-app').getAttribute('role') === null` | a11y lane |
| **QA2-09** | MAJOR | confluence | any / any / any | Timing-states tablist advances selection on ArrowRight but drops focus out of the widget to the shell root | after ArrowRight: `aria-selected` moves to `TAILWIND/16`, `document.activeElement.innerText` begins `REFERENCE · XPV2-SC-R3B SH...` | a11y lane |
| **QA2-10** | MAJOR | overview, map, moving, confluence | any / **zh** / any | Reference-authored accessible labels are English-only in ZH (`Action lanes`, `Show themes or sectors on the rotation map`, `Universe`, `Timing states`, `moved to` x9) | 13 `aria-label` values with zero CJK under `#ref-lang=zh`; visible twins all correct (0 leaked `.l-en`) | copy/i18n lane |
| **QA2-03** | MINOR | explore | css320 at 200% / en / both | Explore filter segmented control (`#btbl-mode.r3-seg` in `div.exp-frow`) does not wrap; "Raw"/"vs S&P" push past the viewport | button right edge 166.6 vs `cw 160`; `.exp-frow` `w 108 / sw 156`; `.exp-filters` `w 134 / sw 169` | D3 (Explore) |
| **QA2-04** | MINOR | overview | css320 at 200% / en / both | The primary answer lede overflows its own read slot | `span.l-en` 99.8 px inside `span.si-vr-t` 57 px (`sw 100`) inside `p#si-read-overview` `w 121 / sw 137`; doc **+4 px** | D1 (Overview) |
| **QA2-05** | MINOR | money | css820 at 200% / en / both | Clipped primary sector name with **zero** document overflow: invisible to a scrollWidth-only gate | `span.l-en` "Consumer Defensive" `left 292 to right 411.4`, clipped by `div.hm-sechd` (`overflow-x:hidden`), `cw 410`, doc overflow 0 | D3 (Money) |
| **QA2-11** | MINOR | moving | any / en+zh / any | Decorative arrow promoted to `role="img"` with the fragment `aria-label="moved to"`: nine content-free announcements | candidate `:2821` `var ARROW='<span class="r3-arrow" role="img" aria-label="moved to"></span>';` | a11y lane |
| **QA2-12** | MINOR | overview, confluence | any / any / any | No roving tabindex on any tablist; `Home`/`End` unimplemented | all 14 `role=tab` have `tabindex === null`; `End` on Overview leaves focus on tab 2 of 5 | a11y lane |
| **QA2-13** | NOTE | money | — | "Forward track record: **Validated**" is BC-2-governed vocabulary. It is **producer-faithful** (`templates/sector_central.html.j2:3463`) and `mockups/` is outside `check_validated_claims.py`'s scan set, so it is not a defect here; the migration wave must confirm the allowlist entry's `surfaces` list covers the new surface before this ships to `templates/` or `site/` | candidate `:4237` `vlab = tr.verdict==='validated'?['Validated','已验证']`, `:4240` `L('Forward track record: '+vlab[0], ...)` | migration handoff |
| **QA2-14** | NOTE | (harness) | — | `page.screenshot()` clears a user-CDP `Emulation.setDeviceMetricsOverride` and a later `setDeviceMetricsOverride` on that session does not re-take, so a screenshot-in-the-loop zoom harness silently measures at the context viewport and reports `over=0` for genuinely failing cells | same 7 cases: shared-page loop returns `60,0,0,0,26,0,0`; fresh context per case returns `60,36,4,32,25,1,0` | QA/verification tooling |

**Counts: 1 CRITICAL, 6 MAJOR, 5 MINOR, 2 NOTE.**

---

## §9 GATE VERDICT SUMMARY

| gate | verdict | evidence |
|---|---|---|
| 1 — Overview phone: five action-state labels + counts at 320, no h-scroll, no hidden state, targets 44 px or more | **PASS** | 5 tabs 294 x 56 px, all visible, doc overflow 0, visible-control count constant across 9 widths |
| 2 — Map phone composition, full map reachable, not a shrunken desktop SVG | **PASS** | phone order answer 212, quadrants 536, selected 805, table, disclosure 2054; desktop puts the plot at 322, above quadrants at 871 |
| 3 — Confluence: five state names + counts legible at every width, no population-scaled label containers, four universes on phone | **PASS** | 5 states visible 320 to 1440 (56/56/82/82 px); `.r3-state` widths identical across widths, font-size constant 10 px; 4/4 universe tabs at 44 px on 320 and 390 |
| 4 — 200% zoom, six views x 320/390/768/820 | **FAIL** | 6 of 48 cells: +60, +36, +32, +25/26, +4, +1 px document overflow, plus one clipped primary name at css820 (QA2-01 through QA2-05) |
| 5 — 44 CSS px repeated/primary mobile targets, six views, 820 px and below | **FAIL** | 4 of 72 cells: map universe segments 40.0 px at 768 and 820, both langs (QA2-06) |
| 6 — Scroll-offset law, six canonical + 21 legacy + `#read-<id>` + empty/unknown | **PASS** | 32 landings; every resolved target lands 159.5 to 671.7 px against a 148.8 px sticky-chrome bottom; empty hash rewrites to `#overview`; `#sc-top` no-op is the recorded production seam |

**Additional passes:** width sweep **PASS** (216/216); ZH parity **PARTIAL** (QA2-10, QA2-11);
ARIA **PARTIAL** (QA2-08, QA2-09, QA2-12); keyboard **PARTIAL** (same); access states **FAIL**
(QA2-07 CRITICAL); fetch-fail **PASS**; authority masquerade §24 **PASS**.

---

## §10 METHOD AND LIMITS

- Server: `python3 -m http.server 8863` bound to `127.0.0.1`, serving the `proposal/` directory
  (a sibling server already held 8791; a free port was taken rather than reused).
- Browser: `playwright-core` with `Google Chrome for Testing` (ms-playwright `chromium-1234`), headless.
- Widths and zoom applied with CDP `Emulation.setDeviceMetricsOverride`; screenshot captures use a
  fresh browser context per case for the reason in QA2-14. Every number in this report is a CDP/DOM
  measurement taken in-page, never an estimate read off an image.
- 200% zoom is emulated as layout-viewport halving (320 to 160, 390 to 195, 768 to 384, 820 to 410),
  the standard equivalence for browser zoom; it does not model text-only zoom, which could expose
  further failures in the same components.
- Cells measured: 48 (zoom) + 216 (width sweep) + 72 (targets) + 32 (hash landings)
  + 18 (access x view) + 12 (ZH x view) + 6 (fetch-fail views) = **404 measured cells**.
- Not covered: screen-reader runtime verification, colour-contrast ratios, prefers-reduced-motion,
  RTL, print, and the `#theme-` hash family (outside the six named gates).
- Zero uncaught page errors across every pass; the only console error is a `404` for
  `/favicon.ico`, an artifact of the static test server, not of the candidate.
