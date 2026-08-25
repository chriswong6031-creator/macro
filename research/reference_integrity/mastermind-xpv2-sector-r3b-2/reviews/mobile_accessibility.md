# XPV2-SC-R3B.2 — Final Mobile / Accessibility Critic

## Verdict

**PASS_WITH_CONDITIONS**

No candidate-owned blocker or major finding survives. The exact R3B.2 closure mechanics tested in this seat pass. The conditions are honest evidence/measurement limits: the heatmap colour-field remains UNMEASURED, and the declared production-before screenshot set never existed. Neither is converted into a candidate failure or a false PASS.

## Binding identity

- Repo: `mastermindx-market-intelligence/macro`
- Canonical carrier: PR #6337 / `claude/xpv2-sc-r3b2-build`
- Dispatch head: `0e542f3eda09721f8a255a08bb9db09070090871`
- Frozen SHA: `d0830a374795925ee1e55b66c0cc42e329ac172d`
- Candidate SHA-256: `4adb4b6245e8e4aa5b68c850a615461327c0a5d2e672e4c203d6ba32a3b8d53c`
- Candidate size: `5,506,871`
- Manifest: `in_review`
- Exact-head CI: `32702450784`, completed/success
- Excluded carrier: PR #6336 / `codex/xpv2-sc-r3b2-final-continuation`; different head `d4863b6cdfcc279da347abc111b1d43fc0646415`, never reviewed
- Skillpack dispatch pin acknowledged: `Mastermind@9b55edccc3f7f7973f73b85c34ba38107b577e33`, `mastermind.sol_skillpack.v1` / `1.0.0`

Freshness: PASS. I did not participate in Sector Central R3/R3B/R3B.1/R3B.2 design, build, QA, orchestration, adjudication, correction, or prior criticism. No sibling result was read. No substantive finding was preloaded.

Material-drift gate: PASS. After `git fetch origin`, current `origin/main` was `263e7719c640517ca88504f1161d5abb75ccb1c4`; the diff from dispatch contained no change in the baseline's seven material Sector Central producer paths, Design Doctrine, Product Design System, RIG/reference paths, or this reference family. No `POST_FREEZE_MATERIAL_DRIFT` stop applies.

## Method and independent evidence

Rationale quarantine was honored. Before reveal I independently verified identity, candidate bytes, PR/CI/exclusion, baseline capability/task inventory, and the limited available production-before product-map captures; then rendered 320/390/768/820 × EN/ZH × dark/light with reduced-motion and coarse/touch emulation, plus 200% stress. The first pass was frozen at `2026-08-24T10:13:11Z` in `critic_return/first_pass_mobile_accessibility.md`.

Independent raw receipts:

- `critic_return/scratch/mobile_first_pass.json` — SHA-256 `ff22196babd5820a40ce1c86ab06db749078db5b3e1e0cd984eaa52e9d32fa94`
- `critic_return/scratch/mobile_post_reveal.json` — SHA-256 `102b36b24c4aaa76ed43dff67f8a699f7bf87b1b35cf6fa92af029a787a2f888`
- `critic_return/scratch/mobile_targeted.json` — SHA-256 `a19e882981f6022d874e59b687431b8a49be544e363dc26aa2eb96cbc6a0c52d`
- Independent full-page captures: `critic_return/scratch/first_pass_shots/`

After freeze I revealed the controlling handoff, continuity, orchestrator adjudications, build/evidence receipts, R3B.1 verdict/reviews, R3A authority pack, Design Doctrine, Product Design System, and RIG law. No sibling R3B.2 critic result was opened.

## Findings

### MA2-001 — minor — evidence provenance — UPHELD CONDITION

The baseline's six named production screenshots are explicitly marked PLANNED/not captured. The available generic product-map captures provide a before-state impression, not the promised route/view/theme/locale evidence set.

- Attribution: upstream RIG evidence, not candidate bytes
- Evidence: `baseline.yml:evidence.screenshots` and `evidence.gaps`
- Smallest remedy: preserve the comparison limit in Sol/R3C accounting; do not claim a captured production-before matrix exists.

### MA2-002 — minor — measurement limit — UPHELD CONDITION

Heatmap colour-field text is **UNMEASURED** in this seat. I used no valid blended/substrate colour-field method and therefore issue neither PASS nor FAIL for that axis.

- Attribution: R3C/design-system verification residue; no candidate defect established
- Evidence: governing handoff §4/§10 and verifier disclosure; this seat intentionally performed no invalid flat-surface substitution
- Smallest remedy: evaluate with a valid painted-substrate method or human legibility review in the authorized next stage; retain UNMEASURED until then.

### MA2-003 — cosmetic observation — severe-zoom reference chrome

At the harsh 320-physical/200% model (160 CSS px), the trailing `· XPV2-SC-R3B` portion of the reference-only top marker is clipped while `Reference` remains. No user signal, action, navigation, or data meaning is clipped; document width remains equal to the layout viewport.

- Attribution: candidate reference chrome
- Severity: cosmetic; not a verdict condition
- Smallest remedy: none required for this reference cycle; if polished later, allow the reference id to wrap or disappear as a whole at 160 CSS px.

## Mandatory B2 verification

- **B2-05 PASS.** 18 `.r3-fig` nodes were present in every cell. Populated Strength, 20d-vs-market, Entry-tier and Conviction figures carry the localized single-node `.r3-figlab` name mechanism; active mobile figures paint the inline labels when the shared column legend disappears. No duplicate speech carrier was found. Empty/unpainted placeholders were not misreported as unnamed values.
- **B2-06 PASS.** Independent painted rectangles at 320/390 found zero surviving header↔header or header↔ticker overlap. Primary section identity survives; secondary labels drop where necessary. The browse/list equivalent remains present. Heatmap colour-field contrast is still UNMEASURED.
- **B2-10 PASS.** `.r3-spread` is `display:none`/unpainted at 320 and 390, and `display:flex`/painted at 768 and 820. No decorative mobile replacement appeared.
- **B2-11 PASS.** The `.r3-ov-season` receipt is in the same text-flow container as the full wrapped seasonal headline at 320/390 EN/ZH. At severe zoom the meaningful text remains readable and document width does not overflow.
- **B2-13 PASS.** The named `[data-r3b1="02"]` receipt button resolves `aria-controls="r3-receipt"`; Moving controls share the same target. Enter changes `aria-expanded` false→true, Escape true→false, and focus stays on the activating control.
- **B2-14 PASS.** After expanding Map, ZH `收起` measures exactly 44×44 CSS px at 320, 390, and 820.
- Decoded emoji: **PASS.** No Extended_Pictographic character was found in visible rendered DOM leaves, computed accessibility snapshot/names, or observable `::before`/`::after` generated content. Script/data/comment text was excluded from the rendered-DOM claim.

## Other accessibility results

- No duplicate IDs or unresolved `aria-controls` / `aria-labelledby` / `aria-describedby` references in the independent rendered matrix.
- `html[lang]` follows locale (`en`; ZH uses a precise Chinese tag through the runtime).
- The ≤359 navigation is a visible 2×3 grid; at 320 each destination is ~159.5×53.4 px and keyboard focus has a visible solid outline.
- Keyboard Tab reaches the six rail destinations and view controls; Moving receipt controls are 44px high, Enter/Escape operate them, and focus is retained.
- Reduced-motion media and coarse/touch modes did not hide an interaction path.
- At 100%, document width equals viewport at 320/390/768/820 across EN/ZH and both themes.
- The 200% physical-pixel model (half-width CSS layout with DPR 2) keeps document width equal to viewport in Overview, Confluence, and Money at all four requested physical widths. The first pass's CSS-`zoom` 1002px signal is therefore withdrawn as a method artifact.
- No VTC1-003 resurrection: 17px browse-link box height is not charged. The prior SC 2.5.8 spacing measurement (~40.6px pitch, one target per row) satisfies the spacing exception.

## First-pass amendment accounting

- `FP-MA-001` baseline provenance gap: **upheld** as MA2-001, still non-candidate.
- `FP-MA-002` 200% CSS-zoom stress: **withdrawn as a candidate concern**. The corrected severe-zoom/reflow model is clean for document width and meaningful content; only MA2-003 cosmetic reference-marker clipping remains at 160 CSS px.
- First-pass clean observations on IDs/IDREFs, document width, 2×3 navigation, figure naming mechanism, language, and 320 Overview readability: **upheld**.

## Strengths not to disturb

- Six task destinations remain immediately discoverable on the smallest viewport.
- The figure-label fix uses one semantic carrier with responsive visual presentation, avoiding duplicate announcements.
- Treemap collision handling is painted-width based and prioritizes identity rather than guessing from character count.
- The ramp is removed exactly when its spatial reference disappears, while fixed state cells remain.
- The shared receipt panel has coherent `aria-expanded`/`aria-controls` wiring and keyboard behavior.
- ZH target geometry, dark/light art direction, and direction/health token separation survive.
- The context-only/5d disclosure is adjacent to its badge and visibly separate from the explicitly labelled 21d figures.

## Upstream / R3C residue

- Heatmap colour-field: UNMEASURED.
- Byte-verbatim `sc_flows` contrast/magnitude debt remains upstream/R3C; it was not laundered into a candidate PASS.
- Production `Validated`/21d semantics beyond the reference-local context-only/5d qualification.
- Producer-owned English-only grader/category strings and language-of-parts work.
- Production Conviction naming collision, `REGIME BUY`, producer `reco_why`, `category_zh`, live Time Machine, real auth settlement/`premiumdata`, production router, correction/revision authority, Baskets thin/gateable, and relative-unit typography debt, as enumerated by the controlling handoff.
- The superseded #6336 carrier must be closed or explicitly marked superseded before any eventual merge; this critic made no GitHub mutation.

## NOT_EVALUABLE limits

- Real VoiceOver/NVDA speech cadence and rotor behavior were not available; Chromium accessibility snapshots and programmatic names were used.
- Real OS browser zoom UI was not automated; the established physical-pixel equivalent (half CSS viewport, DPR 2) plus a separate CSS-zoom stress pass were used.
- Heatmap colour-field legibility is UNMEASURED.
- Live authentication/hydration, production router, and production data clocks are outside this frozen standalone reference and were not evaluated as live services.
- The absent promised production-before matrix limits exact before/after visual regression claims.

## Strongest argument against this verdict

The strongest argument for a stricter `BLOCK` is that a mobile/accessibility critic should refuse any positive verdict while the heatmap's colour-field text remains unmeasured and the production-before evidence matrix is absent. I reject `BLOCK` because neither gap demonstrates a candidate-owned accessibility regression, while every commissioned candidate mechanism independently tested here passes. The strongest argument for plain `PASS` is the converse: the two conditions are upstream/evidence limits, not defects. I retain `PASS_WITH_CONDITIONS` because calling the entire accessibility surface PASS would erase a deliberately unresolved legibility axis.

## Scope compliance

Review-only. No governed candidate/build/fixture/baseline/proposal/continuity/manifest/production/R3C/approval byte was edited; no branch change, commit, push, PR mutation, approval, R3C, merge, or production action occurred. Writes are confined to `critic_return/` review/scratch.
