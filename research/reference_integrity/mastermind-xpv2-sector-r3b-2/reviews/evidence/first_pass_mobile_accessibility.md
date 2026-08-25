# XPV2-SC-R3B.2 Mobile / Accessibility — Independent First-Pass Freeze

- Frozen at: `2026-08-24T10:13:11Z`
- Dispatch head: `0e542f3eda09721f8a255a08bb9db09070090871`
- Frozen SHA: `d0830a374795925ee1e55b66c0cc42e329ac172d`
- Candidate SHA-256: `4adb4b6245e8e4aa5b68c850a615461327c0a5d2e672e4c203d6ba32a3b8d53c`
- Candidate size: `5,506,871`
- Independent measurement JSON SHA-256: `ff22196babd5820a40ce1c86ab06db749078db5b3e1e0cd984eaa52e9d32fa94`
- Rationale quarantine: intact at freeze. No handoff, continuity, orchestrator adjudication, build/evidence receipt, R3B.1 verdict/review, R3A authority pack, Design Doctrine, Product Design System, RIG law, or sibling result was read.

## Identity / drift gate

PASS. Detached HEAD and PR #6337 resolve to the dispatch head; exact-head CI 32702450784 is completed/success; candidate digest and byte size match. PR #6336 resolves to a different head and was excluded. Re-pinned `origin/main` introduced no diff since dispatch in the baseline's seven material Sector Central producer paths, Design Doctrine, Product Design System, RIG/reference paths, or this reference family.

## Before-state and baseline

The 92-row baseline capability/task manifest was read. Its declared R3B production screenshot paths are explicitly planned/not captured, so they cannot serve as image evidence. I inspected the repository's available product-map 390×844 and 1440×1000 Sector Central captures as the limited production-before visual record. This is a provenance limitation, not a candidate defect.

## Independent matrix and provisional result

Rendered the exact candidate in headless Chrome at 320/390/768/820, EN/ZH, dark/light, reduced-motion media, coarse/touch emulation, plus a 200%-CSS-zoom stress pass at every width in EN/ZH. Full-page screenshots and painted rectangles are under `critic_return/scratch/first_pass_shots/`; raw measurements are `critic_return/scratch/mobile_first_pass.json`.

Provisional verdict: **PASS_WITH_CONDITIONS**.

### FP-MA-001 — baseline image provenance gap

- Severity: minor
- Attribution: upstream/reference evidence, not candidate bytes
- Evidence: `baseline.yml` labels all six named production captures PLANNED/not captured; only generic product-map captures were available.
- Smallest remedy: retain this as an explicit NOT_EVALUABLE comparison limit; do not manufacture a before/after claim.

### FP-MA-002 — 200% zoom stress needs targeted adjudication

- Severity: minor / provisional
- Attribution: not yet assigned
- Evidence: the 768 and 820 CSS-zoom stress states report document widths of 1002 px; 320 and 390 retain document width but contain intentionally wide, locally clipped/scrollable tabular content. CSS `zoom` is a stress approximation, so this is not yet a WCAG reflow finding.
- Smallest remedy: after reveal, target the required receipt-flow and stacked-ramp states with browser zoom/reflow semantics and painted-container checks before deciding.

## Clean observations / strengths

- No duplicate IDs or unresolved `aria-controls`, `aria-labelledby`, or `aria-describedby` references were found in the rendered DOM matrix.
- Document width equaled viewport width at 100% for every width/locale/theme state.
- The 320 px primary rail visibly presents all six destinations as a 2×3 grid without horizontal discovery.
- The inspected figures/role-img/SVG census had no exposed unnamed item under the first-pass naming heuristic.
- `html[lang]` resolved to `en` or `zh-Hant` in the locale matrix.
- The 320 px Overview remained readable in both art directions; no primary label or board meaning was visibly clipped.

## First-pass limits

- Heatmap color-field: **UNMEASURED**; no valid color-field method was used.
- Screen-reader speech order/duplicate announcement: NOT_EVALUABLE from this first headless pass; DOM naming was measured, not an OS assistive-technology session.
- Touch target spacing: no finding frozen from raw box height. SC 2.5.8 spacing has not yet been applied, and no VTC1-003 inference is made.
- Keyboard focus, hidden-focus, disclosure state, receipt-flow, and generated-content/decoded-emoji probes remain for the post-freeze targeted pass.
