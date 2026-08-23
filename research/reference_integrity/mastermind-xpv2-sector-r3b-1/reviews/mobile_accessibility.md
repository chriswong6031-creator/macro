# XPV2 Sector Central R3B.1 — Fresh Mobile / Accessibility Critic (re-run seat)

## Review identity and scope

- Reviewer: Claude (Opus 5), independent Mobile / Accessibility critic seat.
- **This is a RE-RUN seat.** A prior Mobile/Accessibility receipt for this SHA existed only in chat and was not recoverable. Under the governing commission's rule *"rerun only that missing critic; do not fabricate provenance"*, this document is a fresh, independent re-derivation. I did not read, receive, or reconstruct the lost receipt; nothing below is inherited from it. Any agreement with it is coincidental convergence, not provenance.
- Freshness: I did not participate in R3B.1 design, build, QA, orchestration, or adjudication.
- Role: Mobile / Accessibility critic only. This is a critic verdict, not an authority approval, not a production-migration authorization, and not permission to start R3C.
- Reference ID: `mastermind-xpv2-sector-r3b-1`.
- Predecessor: `mastermind-xpv2-sector-r3b` @ `dc84f78cddf04d9be90e9249126f9767de5725a6` (verdict `REVISE`). The predecessor receipt at `research/reference_integrity/mastermind-xpv2-sector-r3b/reviews/mobile_accessibility.md` binds that older SHA; **this receipt binds `0667f800`** and supersedes nothing in the predecessor's own record.
- Governing standard: `research/reference_integrity/mastermind-xpv2-sector-r3b-1/COMMISSION.md`.

## Frozen-byte verification (performed by me, before reviewing)

Both required identities verified independently:

```
$ shasum -a 256 mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b-1/proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html
fec05b058fbc9dbe29744ad015b7ee9cd9baa5cb85bbbde739daa8b97644cf70   [MATCHES required]

$ git cat-file -t 0667f800764bf210af6c1237ccf0b5f0a71b4af2
commit                                                            [freeze commit EXISTS]

$ git show 0667f800764bf210af6c1237ccf0b5f0a71b4af2:mockups/refs/.../MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html | shasum -a 256
fec05b058fbc9dbe29744ad015b7ee9cd9baa5cb85bbbde739daa8b97644cf70   [blob at freeze commit MATCHES]
```

Disclosed provenance nuance, recorded rather than treated as a mismatch: `0667f800` is a merge commit on the build branch `claude/xpv2-sc-r3b1-build` and is **not an ancestor of the review checkout's HEAD** (`git merge-base --is-ancestor 0667f800 HEAD` → false). The bytes reached main through squash-merge `780cbcf6d2d2c7b32b87a4674929e1732e5ad036` (PR #6248), whose blob hashes to the same `fec05b05…`. Reviewed bytes are therefore byte-identical at the freeze commit, at the squash-merge, and in the working tree. No stop condition: the commission's requirement is that the SHAs match, and they do at all three points.

## Method

Rendered and measured; nothing below is read off source. Harness: Playwright + Chromium `151.0.7922.34`, headless, against a `file://` load of the exact frozen bytes. No candidate, `build/`, fixture, manifest, baseline, continuity, production, or `approval.yml` byte was modified. Browser-side state changes (viewport, `data-theme`, `REF.setLang`, `has_touch`, `reduced_motion`, device scale factor) were applied to the test page only.

Independent probes were written to my own scratch directory. I ran the supplied `build/` harness first as a baseline, then wrote my own measurement passes that deliberately differ from it on three axes, so that a shared blind spot could surface:

| Axis | Supplied harness | My independent pass |
|---|---|---|
| Scope of walk | active `.si-view` root only | **whole `document.body`** (catches sticky chrome, workspace nav, header, footer) |
| Theme dimension | `zoom_sweep.py` runs dark only | **dark AND light** |
| Contrast viewport | `contrast_audit.py` at 1440×1000 only | **also 390 mobile**, all four theme×lang |
| DOM state | boot/gated state | **boot AND fully-expanded** (269 disclosure/show-all activations) |
| Cell count | 48 zoom cells | **96 standard + 96 severe-zoom + 36 expanded** |

Coverage actually executed:

- **Standard sweep, 96 cells**: 6 views × {320, 390, 768, 820} × {dark, light} × {EN, ZH}. 24,276 text leaves and 3,624 focusable controls measured.
- **Severe-zoom sweep, 96 cells**: same matrix at 200%, modelled as a half-width CSS layout viewport at `device_scale_factor=2` (320→160, 390→195, 768→384, 820→410 CSS px), `is_mobile`/`has_touch` set below 768.
- **Expanded-state sweep, 36 cells**: {320, 390, 820} × {EN, ZH} × 6 views, after driving every `aria-expanded="false"`, every closed `<details>`, and every show-all/更多 control to open (269 total activations).
- **Contrast**: harness matrix at 1440 (16,140 cells) plus my own 390-wide re-run (15,940 collected / 15,528 scored) across dark/light × EN/ZH.
- Help-control semantics, keyboard (Enter/Space/Escape), real coarse-pointer `tap()`, focus retention, document language across boot/toggle/six-view/hash-repaint/reload, duplicate-ID and ARIA-IDREF audits in boot and expanded state.

Clipping was measured the way R3B1-09 demands — **not by `scrollWidth`**. For every text node I took `Range.getClientRects()` (painted runs, not element boxes) and compared each run against every ancestor that genuinely hides overflow, resolved per axis, with the walk terminating on an axis at the first `overflow:auto|scroll` scroll port (content inside a scroll port is reachable, so an outer radius-clipping `overflow:hidden` never hides it). Content parked behind an operable control (closed `<details>`, `content-visibility`, `max-height:0`) is not charged as lost meaning. `.r3-vh` is excluded by name as the artifact's visually-hidden utility.

## Commissioned fix-packet items in my scope — independently verified

### R3B1-08 — Moving help controls: **PASS**

All three `.r3-tr-help` controls verified in EN and ZH at 1440 and at 390 with `pointer:coarse` / `hover:none` / five touch points.

| Control | Size (EN) | Size (ZH @390) | Accessible name EN | Accessible name ZH |
|---|---|---|---|---|
| Rank fit | 44.0 × 44.0 | 44.0 × 44.0 | `Rank fit — how this works` | `排序吻合 — 原理说明` |
| Reliability | 44.0 × 44.0 | 44.0 × 44.0 | `Reliability — how this works` | `可靠度 — 原理说明` |
| Scorecard method | 110.5 × 44.0 | 69.2 × 44.0 | `Scorecard method — how this works` | `记分卡方法 — 原理说明` |

- Effective target ≥44×44: met on both axes for all three, both languages.
- Unique localized accessible name naming the concept: met; three distinct names per language, each naming its concept.
- Real DOM explanation with a stable id: met. `#r3-receipt` is a real `div.r3-tipbox` with `role="status"`, toggled via the `hidden` attribute (`display:none` → `block`), carrying real prose — e.g. EN `"Rank fit is how closely the ranking matched what happened next."`, ZH `"排序吻合是指排序与后续实际走势的接近程度。"`.
- Valid expanded/controls relationship: met and **mutually exclusive**, which I attacked specifically. Activating control B while A is open flips A back to `aria-expanded="false"` and B to `"true"`; the shared `aria-controls="r3-receipt"` target resolves to exactly one element (audit below). A shared disclosure panel driven by three buttons is a lawful pattern *only* if stale `aria-expanded="true"` cannot persist on a non-owning control; it cannot here.
- Keyboard: `Enter` and `Space` both activate; focus is retained on the activating button after repaint.
- Coarse pointer: real Playwright `tap()` at 390 with touch enabled opens the receipt and moves focus to the button.
- Dismiss: `Escape` closes the disclosure, sets `aria-expanded="false"`, and leaves focus on the button rather than dropping it to `body`.

### R3B1-09 — severe zoom: **PASS**, and it survives a harsher method than the harness used

96 severe-zoom cells (the harness runs 48; I added the light-theme half) measured whole-document rather than active-view-only:

```
cells=96 zoom=200%
 docOverflow cells: 0   max=0
 clippedText: 0
 clippedControls: 0
 smallType: 0
```

The commissioned 320-physical / 200% axis (160 CSS px layout viewport) is clean in all four theme×language combinations across all six views, including Money — the predecessor's `.mny-verdict` painted-leaf defect (`Volatility: calm` overrunning an `overflow:hidden` edge by 3.3 px) does **not** reproduce. Zero document overflow, zero painted semantic clipping, zero clipped primary controls, at 320/390/768/820. The explicit "do not rely only on scrollWidth" warning is satisfied: my gate is painted-run geometry, and it independently reproduces zero.

### R3B1-10 — document language: **PASS**

Verified through the page's own control and through repaint/navigation, at 390 and 1440:

- Boot: `<html lang="en" data-lang="en">`, nav `aria-label="Sector Intelligence views"`.
- After `REF.setLang('zh')`: `lang="zh-CN"`, `data-lang="zh"`, nav `aria-label="板块情报视图"` — both attributes move together, and localized ARIA moves with them.
- Survives: activation of all six views, two legacy/canonical hash repaints, and a bare external `setAttribute('data-lang','zh')` (the runtime re-syncs `lang`).
- A full reload returns to the `en` default, as specified.

`zh-CN` is the house-approved precise tag (production parity: `templates/theme.js:600,:614`).

### R3B1-11 — contrast and live type: **PASS**, extended to mobile

Harness matrix at 1440: 16,140 cells, 15,340 scored reference-authored, **0 AA failures, 0 sub-10px cells, 0 parser-suspect (`ratio == 1.00`) rows**. The zero suspect count is the meaningful control here: it confirms the `color(srgb …)` 0..1 serialisation trap documented in `contrast_audit.py` was parsed correctly rather than silently collapsing foreground onto background.

I did not accept a desktop-only measurement for a mobile/accessibility verdict, so I re-ran the same collector at **390 wide** across dark/light × EN/ZH: 15,940 collected, 15,528 scored, **0 AA failures, 0 sub-10px cells**. Separately, my 96-cell standard sweep and 96-cell zoom sweep each report `smallType: 0` — no live text renders below 10px at 320/390/768/820 in any theme or language, at 100% or 200%.

Every commissioned named cell clears, at actual rendered size, in all four theme×language combinations:

| Named cell | dark/EN | dark/ZH | light/EN | light/ZH |
|---|---|---|---|---|
| action state — Buy now / 立即买入 (11px w700) | 5.58 | 4.79 | 4.98 | 4.59 |
| action state — Entry now / 现可入场 (11px w700) | 5.58 | 4.79 | 4.98 | 4.59 |
| risk state — Risk appetite / 风险偏好 (10px w700) | 5.39 | 5.39 | 5.14 | 5.14 |
| track record — Still measuring / 测量中 (10px w700) | 7.59 | 7.59 | 6.33 | 6.33 |
| board column — 20d vs market / 20日对比市场 (10px w600) | 5.57 | 5.57 | 5.43 | 5.43 |

The three predecessor defects are closed with margin: ZH-dark action/risk labels 4.26–4.45 → 4.79/5.39; light `Still measuring` 3.61 → 6.33; `20d vs market` 3.91 dark / 3.43 light → 5.57 / 5.43. The ZH margins are the thinnest in the matrix (4.59:1 light/ZH on the action states, 0.09 above floor) — noted as fragile, not charged.

### R3B1-12 — duplicate IDs and ARIA reference integrity: **PASS**, including in expanded state

The predecessor's 22 repeated `id="ref-data"` values are gone.

| State | EN | ZH |
|---|---|---|
| Boot, all six views touched | 253 ids, 0 duplicated, 74 IDREFs resolved, 0 unresolved | 253 / 0 / 74 / 0 |
| **Fully expanded** (269 activations), 320/390/820 | 258 ids, 0 duplicated, 0 broken | 258 / 0 / 0 |

The expanded-state audit is mine and is the load-bearing addition: the supplied `aria_id_audit.py` audits the boot DOM only, so an id minted when a disclosure opens or a "show all" fires would be invisible to it. Driving 269 expansions raises the id count 253 → 258 and still yields zero duplicates and zero unresolved `aria-controls` / `aria-labelledby` / `aria-describedby` / `aria-owns` / `aria-activedescendant` references. The gate holds under the harder state.

### Do-not-reopen items — respected, confirmed not disturbed

The mobile workspace nav honours the protected `2 columns × 3 rows` rule at ≤359 and recomposes above it. Measured `.si-view-btn` geometry:

| Width | Columns | Rows | x positions | y positions | Cell size |
|---|---|---|---|---|---|
| 320 | 2 | 3 | 0, 161 | 84, 138, 192 | 159.5 × 53.4 |
| 359 | 2 | 3 | 0, 180 | 84, 138, 192 | 179.0 × 53.4 |
| 390 | 3 | 2 | 0, 130, 261 | 84, 138 | 129.3 × 53.4 |

Six links, `nav` landmark with a localized `aria-label`, exactly one `aria-current`, 53.4px height (≥44), visible 2px focus outline (`2px solid color(srgb 0.478431 0.654902 0.878431 / 0.7)`). I did not reopen the 3×2-versus-2×3 authority question the predecessor raised; the do-not-reopen list settles it as 2×3 and the candidate complies.

## Findings

### MAC1-001 — MAJOR — candidate-owned — two numeric board columns have no accessible label at any width, and no visible label at all below 641px

The card-list "table" headers are `div.r3-cols`. Every one of them is `aria-hidden="true"` at every width, and `display:none` at ≤640px (`display:grid` at ≥641px — breakpoint bisected at 640/641). So the words in those headers reach **no** user below 641px and reach **no assistive-technology user at any width**. Whether that is acceptable depends entirely on whether each data cell carries its own label. Two of the three numeric columns do not.

Measured at 320, 390, 640, 641, 768 and 820, in EN and ZH, dark and light — the defect is width-, theme- and language-invariant on the AT axis:

| Group | Header (aria-hidden, hidden ≤640) | Value cell | Per-cell `.r3-vh` label? |
|---|---|---|---|
| Overview action board | `Score / 评分` + `20d vs market / 20日对比市场` | `span.r3-fig.tnum` = `76+27.2%` | **NO** |
| Confluence subsector list | `Entry tier / 入场层级` | `span.r3-fig.tnum` = `T1` | **NO** |
| Confluence stock picks | `Conviction / 综合把握` | `span.r3-fig.tnum` = `0.60` | **YES** |

Resulting accessible names, read from the rendered DOM:

```
Overview row  : "Gold Miners THEME · AEM · EQX · AU 76+27.2% Leading and still broad — room to add on the trend."
Confluence sub: "Auto Manufacturers Thin data — read with caution EXTENDED · CONSUMER CYCLICAL · 3 NAMES T1 Fresh T1 entry — just crossed"
Confluence stk: "COIN CAPITAL MARKETS Conviction 0.60 Its tier T2 · vs sub 20d -1.6"      <- the correct pattern
```

`76` and `+27.2%` are announced as bare numbers on the flagship Overview action board. Nothing in the accessible name says one is a strength score and the other is 20-day relative performance.

This is not a design choice, and that is what makes it chargeable: the artifact already ships the exact remedy in the same view. The Confluence stock row wraps its figure as
`<span class="r3-fig tnum"><span class="r3-vh"><span class="l-en">Conviction</span><span class="l-zh">综合把握</span> </span>0.60</span>`,
and `.r3-vh` is verified genuinely AT-exposed rather than removed from the tree (`position:absolute; width:1px; height:1px; clip:rect(0,0,0,0); clip-path:inset(50%); overflow:hidden; visibility:visible` — clipped, not `display:none`). The same wrapper is simply absent on the other two `.r3-fig` cells. This is an inconsistent application of the artifact's own established pattern.

Standard: WCAG 2.1/2.2 **1.3.1 Info and Relationships (Level A)** — information conveyed by visual column position is not programmatically determinable. Below 641px it is not conveyed visually either, so the value is unlabeled for every user.

Attribution: **candidate-owned.** `.r3-cols`, `.r3-row`, `.r3-fig` and `.r3-vh` are reference-authored classes; the fix is reference markup and touches no producer bytes and no production token.

Smallest acceptable remedy: add the existing `.r3-vh` label wrapper to the two unlabeled `.r3-fig` cells — `Score`/`评分` (or `Strength`/`强度`, per whichever wording R3B1-06 settles) and `20d vs market`/`20日对比市场` on the Overview figure, and `Entry tier`/`入场层级` on the Confluence subsector figure. No CSS change, no `.r3-cols` change, no architecture change. Then re-run the accessible-name capture on one row per group in EN and ZH.

Overlap disclosed, not adjudicated: the Visual/Taste seat's VTC1-001 concerns the *visible* half of this same `.r3-cols` element (its `display:none` below 641px). That seat owns the sighted-user question. I charge only the accessible-name half, which is independent of it and is not cured by making the header visible on mobile — the header is `aria-hidden="true"` at every width, so a purely visual fix leaves MAC1-001 fully open. Conversely my fix leaves VTC1-001 fully open. Both need closing; neither substitutes for the other.

### MAC1-002 — MINOR — candidate-owned — ZH "收起" control is 39.0px on the inline axis, below the 44px floor its EN twin clears

`button.r3-textbtn` "Show fewer / 收起" in the Map view measures **39.0 × 44.0** CSS px in ZH at 320, 390 and 820. The EN twin ("Show fewer") clears 44 on both axes and never appears in the sweep — the shorter Chinese string is what pulls the box under the floor, so this is a language-conditional target defect that an EN-only sweep cannot see. It was the only sub-44 control found in 3,624 controls across the 96-cell standard sweep other than MAC1-003 below.

Honest scoping: 39.0 × 44.0 **passes** WCAG 2.2 SC 2.5.8's 24×24 baseline. This is charged against the house 44px floor the commission applies to help controls in R3B1-08, and it is charged Minor rather than Major precisely because no WCAG conformance criterion is breached.

Attribution: **candidate-owned** (reference-authored control and reference-authored ZH string).

Smallest acceptable remedy: give `.r3-textbtn` a `min-width:44px` (or symmetric inline padding sized off the floor rather than off the glyph count) so the target does not shrink with string length. Re-measure the control in ZH at 320/390/820.

### MAC1-003 — observation, not charged — Money browse-all-names list renders 503 links at 17px height

In the fully-expanded Money view, the accessible browse-all-names table renders **503** `<a>` elements measuring **8.2–50.9 × 17.0** CSS px (`display:inline`, `font-size:14px`, `line-height:21.7px`), one per `<td>`. These appear in every expanded cell at 320, 390 and 820 and account for 1,509 of the 1,512 sub-44px hits in the expanded sweep.

I am explicitly **not** charging this, and the reason is a measurement rather than a judgement call. WCAG 2.2 SC 2.5.8 is satisfied through the **spacing exception**: consecutive links sit at y = 4007.0, 4047.7, 4088.3, 4129.0 — a **40.6px vertical pitch** — and each row contributes exactly one link at a constant x (left = 46 for all sampled rows), so a 24px-diameter circle centred on any link intersects no other target's circle. The inline exception is *not* what saves it (each link is the sole content of its `<td>`, not a target in a sentence), but the spacing exception alone is sufficient.

Recorded because a 17px-tall touch target on a 320px phone remains poor coarse-pointer ergonomics even where it conforms, and because a future seat re-running a naive 44px sweep will see 1,509 hits and should find this adjudication rather than re-litigate it.

Attribution: candidate-owned markup; no defect charged.

## Position on the two harness populations the commission asked me to judge

The commission asked me to form and state my own view on whether the harness's record-but-do-not-gate treatment of two populations is legitimate. My answers differ for the two.

**1. The `sc_flows` producer verbatim fragment (75 cells below AA, 2.24:1 – 4.45:1) — excluding from the GATE is legitimate; calling the axis closed is not.**

Excluding it from the *pass/fail gate* is correct. Those bytes are `build/fixture_supplement/fragments/sc_flows.html`, carried verbatim under a sha256 receipt; the reference is forbidden from rewriting producer bytes, and R3B1-11 explicitly forbids page-local literal-colour patches and production `theme.css` edits. Gating on a defect the candidate is not permitted to fix would make the gate unsatisfiable by lawful means. The attribution is also right: **upstream**, not candidate-owned.

But the disposition must not stop at "recorded". A ratio of **2.24:1** is not a rounding error — it is roughly half the AA floor, and it is painted on a customer-facing surface. If this reference becomes production migration law with that fragment intact, the product ships 75 sub-AA cells. The honest disposition is an upstream-owned blocker with a named owner and an R3C dependency record, not a footnote. I checked `COMMISSION.md` §"R3C-only conditions" and the sc_flows contrast population is **not** among the ten recorded items; the closest entries are "Upstream generic reco_why copy quality" and "Site-wide relative-unit typography debt", neither of which covers it. **Gap:** R3C should carry an explicit `sc_flows` contrast dependency naming the 2.24:1 floor. This is a completeness gap in the handoff, not a defect in the candidate.

**2. The ~440 shadowed cells over a data-driven colour field — excluding is legitimate as method, but the axis is UNMEASURED, not passing.**

The method argument is sound and I independently agree with it: WCAG's contrast ratio is defined for one foreground over one flat surface, and a shadowed glyph painted over a data-driven gradient satisfies neither half. Computing a number there would be fabricating precision. Declining to score is the correct call, and the harness's `unmeasurable_shadowed_colour_field` scope label is honest naming rather than a euphemism.

The caveat is what must not be lost downstream: "no applicable automated method" is **not** "verified accessible". These 440 cells are the artifact's heatmap/colour-field text, they carry customer meaning, and they are currently unverified by anything. The predecessor seat drew exactly the same line and required "separate human/automated contrast verification during repair"; I reach that conclusion independently and restate it as an open axis, not a cleared one. This does not weaken the candidate's R3B1-11 pass — the commissioned cells are all reference-authored and all measured — but Sol should not read "0 AA failures" as covering the colour-field population.

**A third concern I raised and then falsified against my own measurement, recorded so it is not re-raised:** I suspected `contrast_audit.py` under-reports, because it executes `continue` on any cell whose ancestor stack contains a `background-image` *before* the record is built, so such cells would vanish from the denominator entirely rather than being counted as unmeasurable. I instrumented the collector to count that branch across all six views × dark/light × EN/ZH at 390: **`dropped_background_image = 0`**. No cell in this artifact takes that path — the `.r3-vh` and `aria-hidden` filters remove them earlier. The concern is real as a latent harness property but has **zero effect on this candidate**, and I charge nothing for it.

## Strengths independently confirmed

- Zero document overflow in **192** cells (96 standard + 96 severe-zoom), whole-document scope, all four theme×language combinations at 320/390/768/820.
- Zero painted semantic clipping and zero clipped primary controls at 100% and 200%, measured by painted `Range` geometry rather than `scrollWidth`.
- Zero live text below 10px anywhere in the matrix, at either zoom.
- Zero focusable elements with a zero-size box (no invisible tab stops) in 3,624 controls across 96 cells.
- The shared-panel disclosure pattern is implemented correctly, including the mutual-exclusion case that is the usual failure mode for it.
- Document language, including `zh-CN` precision, survives view activation, hash repaint, external attribute mutation, and reload.
- Duplicate-ID and ARIA-IDREF integrity hold in the fully-expanded DOM, not just at boot.
- Protected `2×3` mobile workspace nav at ≤359 is intact and unclipped, with a `nav` landmark, localized label, single `aria-current`, 53.4px targets and a visible focus outline.
- `.r3-vh` is a correctly-built visually-hidden utility (clip-based, `visibility:visible`) rather than a `display:none` that would silently delete content from the accessibility tree.

## Verdict

**PASS_WITH_CONDITIONS.**

Every commissioned fix-packet item in my scope — R3B1-08, R3B1-09, R3B1-10, R3B1-11, R3B1-12 — verifies clean under independent measurement, and each survives a method deliberately harsher than the supplied harness on at least one axis (whole-document scope, both themes, mobile contrast viewport, fully-expanded DOM). All five predecessor blocking/major findings in this lane (MAC-001 through MAC-003, MAC-005, MAC-006) are closed on the exact frozen bytes. I found no defect in anything the commission asked to be fixed.

I am not returning PASS, because MAC1-001 is a Level A conformance failure on the flagship Overview action board, present in both languages at every width and in both themes, which the candidate's own established `.r3-vh` pattern would close in three markup insertions.

Conditions binding before this reference becomes production migration law:

1. **MAC1-001 (Major)** — add the existing `.r3-vh` label wrapper to the Overview `Score`/`20d vs market` figure and the Confluence subsector `Entry tier` figure, in EN and ZH; re-capture one accessible name per row group as proof.
2. **MAC1-002 (Minor)** — floor `.r3-textbtn` at 44px on the inline axis so the ZH `收起` twin stops rendering at 39.0px.
3. **Handoff completeness** — record the `sc_flows` verbatim-fragment contrast population (75 cells, floor 2.24:1) as an explicit upstream R3C dependency; it is currently absent from the ten recorded R3C-only conditions.
4. **Open axis** — state the ~440 shadowed colour-field cells as unverified rather than passing, and schedule the separate verification the method gap requires.

Conditions 1 and 2 are candidate-owned and surgical. Conditions 3 and 4 are record-keeping and upstream ownership, and neither requires a candidate byte to change. None of the four touches the frozen architecture, and none reopens a do-not-reopen item.

This is a critic verdict advisory to Sol. It is not an authority approval, not a production-migration authorization, and not permission to start R3C.

## Limitations

This receipt is a **re-run** produced after the original seat's receipt for this SHA was lost. It is an independent re-derivation from the frozen bytes; it is not a reconstruction, and it makes no claim about what the lost receipt concluded. If that receipt is ever recovered, any divergence should be adjudicated on the measurements, not on seniority.

Explicitly NOT_EVALUABLE in this session:

- **Real assistive technology.** No VoiceOver, TalkBack, NVDA or JAWS run. I measured the DOM, the accessibility-relevant attributes, and Chromium's computed semantics. Accessible names quoted above are derived from rendered DOM text and ARIA attributes, not from a platform accessibility API dump, and are not a substitute for a real screen-reader pass.
- **Real touch hardware and platform gestures.** Coarse pointer was synthesised (`has_touch`, `is_mobile`, `pointer:coarse`, `hover:none`, all three media queries confirmed matching) and activation used Playwright `tap()`. Real finger targeting, gesture conflict and platform magnification were not exercised.
- **Real mobile browser chrome**, safe-area insets, and dynamic viewport (`dvh`) behaviour. The artifact declares `viewport-fit=cover`, which was not exercised against a notched device.
- **Text-only zoom** as distinct from browser/page zoom. The commissioned 200% browser-zoom axis was evaluated; a 200% text-only resize was not.
- **The ~440 shadowed colour-field cells.** Unmeasured by design, per the position stated above. Not claimed as passing.
- **Expanded-state severe zoom.** My expanded-DOM sweep ran at 100% zoom across {320, 390, 820} × {EN, ZH}. The severe-zoom sweep ran the full 96-cell matrix but in boot state. The intersection — every disclosure open *and* 200% zoom — was not swept. Both halves are individually clean, and no clipping was observed in either, but a defect that requires both conditions simultaneously would not have been caught. Recorded as an explicit open item.
- **Light theme in the expanded-state sweep.** The expanded sweep ran dark only; the 96-cell standard and 96-cell zoom sweeps cover both themes in boot state.
- **Production behaviour.** Everything above was measured against a `file://` load of the frozen reference. Live hydration, real entitlement gating, and real network failure paths are R3C conditions and were not exercised.
