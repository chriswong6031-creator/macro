# XPV2-SC-R3B — Visual / Taste Critic · FIRST-PASS FREEZE

**Frozen (UTC):** 2026-08-22T13:08:11Z
**Seat:** fresh Visual/Taste critic (Claude Opus 5, `claude-opus-5`), no prior R3B participation.
**Artifact:** `dc84f78cddf04d9be90e9249126f9767de5725a6`
**Candidate SHA-256 (independently computed):** `19553267d3f51659503fc836da6b6bdaa06afc9cdd607aafb1bb795e46c47dca` — MATCHES handoff.

This file is written BEFORE reading any quarantined rationale
(design_notes.md, ORCHESTRATOR_ADJUDICATIONS.md, FIX_VERIFICATION.md,
capability_crosscheck.md, QA_ATTACK_REPORT.md, DESIGN_SYSTEM_SPEC.md,
responsive/accessibility/copy-ledger contracts, evidence/EVIDENCE_INDEX.md,
PR #6197 prose, R3C_HANDOFF_DRAFT.md).

## First-pass verdict: **BLOCK**

Blocking set: VTC-001, VTC-002. Conditions-capable: VTC-003, VTC-004.

## Findings (priority order)

| ID | Sev | Defect |
|----|-----|--------|
| VTC-001 | HIGH | The Map encodes nothing in colour: 37/39 markers share one grey fill. `--q1..--q4` declared 12x (incl. ZH inversion) and referenced 0x, while production uses those tokens ~118x. |
| VTC-002 | HIGH | Explore first viewport is 75% chrome @1440 and 79% @390 with ZERO data rows fully visible on mobile. Category chips default EXPANDED on desktop, collapsed on mobile — wrong default on the larger surface. Headline claims "49 baskets — every member, every record"; default renders 16 of 49. |
| VTC-003 | HIGH | ZH-only WCAG AA regression on the primary state vocabulary at 11px dark: `立即买入`/`现可入场` cr=4.26, `风险偏好` cr=4.45 (AA needs 4.5). EN counterparts pass at 5.58/5.76. Inherited locale inversion was never contrast-retuned. |
| VTC-004 | HIGH | 15 Explore category chips carry no `.l-zh` span at all (16 of 19 visible chips have no CJK) while the same concepts are translated elsewhere in the same artifact (`医疗保健` appears 9x). |
| VTC-005 | MED-HIGH | Overview "WHY IT IS HERE" is a constant string within the Buy Now lane — identical sentence for all 5 buyable groups. The column justifying the action carries zero differentiating information exactly where action is taken. |
| VTC-006 | MED-HIGH | Confluence "Stock picks": largest/boldest element per row is a bare unlabeled decimal (`0.60`/`0.54`, class `r3-fig tnum`) with no column header, no unit, no `title`, no `aria-label`. |
| VTC-007 | MED | Money style/risk ETF block: red/green encodes the SIGN of a descriptive ratio, not desirability, inside a block captioned "Descriptive, never a buy list." Four red / one green reads as "mostly bad." |
| VTC-008 | MED | What's Moving "CHANGED THIS WEEK" 10-cell grid has no magnitude encoding and is not sorted by magnitude. A view named "What's Moving" gives the eye no ranking. |
| VTC-009 | MED | Templated rationale copy: the two rotation rows repeat one sentence frame with swapped nouns. With VTC-005 this is the artifact's dominant vibe-coded tell. |
| VTC-010 | MED-LOW | 9px micro tier used 134x (production `sector_central.html.j2`: 15) below the ramp floor `--fs-micro:10px`; it carries the build's only both-theme AA failure ("20d vs market" 3.91 dark / 3.43 light). |
| VTC-011 | LOW | @320 the universe tabs stack as centre-aligned rows whose selected state is a hairline colour change only; centring breaks the page's left-aligned rhythm. |
| VTC-012 | LOW | @195 (200% page zoom) the answer headline holds 22px and eats ~30% of the viewport at 1–2 words per line; no narrow-width step-down. |
| VTC-013 | LOW | Money style/risk grid: 5 items in a 3-column grid leaves a visible empty cell. |
| VTC-014 | ADVISORY — NOT an R3B defect | Type ramp is 100% px, zero rem/em; text-only zoom is inert (root 16->32px changes no rendered size). Inherited VERBATIM from production `theme.css`. Must NOT block R3B; flagged only because adopting this reference silently re-ratifies it as site-wide law. |

## Genuine strengths (verified, not conceded)

- Confluence spread bar segments are **exactly proportional to the counts** (18.1/290/380.6/326.2/163.1 px vs 1/16/21/18/9 of 65) beneath equal-width tiles. Sophisticated; I initially misread this as a defect and the measurement overturned me.
- Locale-aware 红涨绿跌 inversion implemented completely, including light variants and `--ink-mix-*` rungs — faithful to `theme.css:217-233`.
- Mobile Map **drops the scatter** for a labelled 2x2 quadrant grid with named members — better information design than the desktop chart it replaces.
- **Zero horizontal overflow** at every width 1440 -> 160 across all six views (the author's earlier GATE4 overflow bugs are genuinely fixed).
- **Zero clipped text and zero sub-24px tap targets** across 96 audited cells.
- Light mode is a designed light theme (tinted rail, white panels, hairline separation), not an inverted dark one.
- Mobile Explore rows restructure into labelled stacked cards rather than squeezed columns.
- Glance-tier plain-word annotations on Money stat tiles ("healthy majority", "more highs than lows").

## Named judgements the handoff requires

- **Strongest viewport:** 1440 dark EN Confluence (state ledge + proportional spread bar + green-emphasised headline verb).
- **Weakest viewport:** 390 Explore — zero data rows fully visible in the first screen.
- **Still looks vibe-coded:** Explore's filter block (78 buttons, expanded by default) and its "60D TREND" sparkline column (baseline-less grey squiggles, uniform, decorative).
- **Should NOT become site-wide law:** the 9px x134 micro tier; a monochrome quadrant chart while quadrant tokens sit unused; per-row rationale strings that repeat within a lane; bare unlabeled figures as the heaviest element in a row.

## Method / limitations

- Rendered independently via headless Chromium 151 over the frozen bytes; author crops and QA report NOT used as proof.
- Full 96-cell instrumented sweep (4 widths x 2 themes x 2 langs x 6 views) for contrast/tap-target/clipping/overflow.
- Eyes-on inspection: 1440 dark EN all 6; 1440 light EN overview/map/money; 1440 dark ZH overview/explore; 390 dark EN explore/map; 320 dark EN confluence; 195 zoom200 money. Remaining matrix cells were captured and instrumented but not individually eyeballed — recorded as a limitation, not a claim of full visual coverage.
- Two self-corrections during the pass: an early SHA mismatch was MY error (`2>&1` folded git's stderr into the hash input, plus a typo'd `sc-r3b` path); and a first contrast sweep reporting ~70 failures was MY parser mishandling Chromium `color(srgb ...)` output — corrected to 10 real failures across 48 cells.
