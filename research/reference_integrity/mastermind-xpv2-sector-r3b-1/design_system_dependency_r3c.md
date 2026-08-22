# XPV2-SC-R3B.1 — bounded Design-System dependency for R3C

**Opened by:** Lane B (accessibility + token repair), 2026-08-22
**Authority:** none. This file RECORDS work that belongs upstream. It authorises
nothing, starts nothing, and is not an R3C plan.
**Scope rule it exists to honour:** COMMISSION.md R3B1-11 — *"If production later
requires a shared token amendment, record a separate bounded Design-System
dependency for R3C. Do not edit production `theme.css` here."*

Everything below was **measured in the repaired R3B.1 candidate** by
`build/contrast_audit.py` (16,140 text leaves, six views × dark/light ×
EN/ZH). Nothing here is a hypothesis. Nothing here was repaired in Lane B,
and each entry says why not.

---

## D-1 — dark EN has no red text rung (`--ink-mix-down: 100%`)

**What.** The `--ink-mix-*` block grades each state hue for text on its theme's
canvas. Both light rungs are tuned per hue (`--ink-mix-up: 62%`,
`--ink-mix-down: 84%`) and the ZH block swaps the two values because 红涨绿跌
swaps the two hues. **Dark is not tuned per hue at all** — both rungs sit at the
100% default — so the ZH swap moved 100% onto 100% and the red channel reached
the dark canvas with no rung of its own. That is the root cause of VTC-003, and
Lane B closed the half of it that was failing by completing the matrix with
`html[data-theme="dark"][data-lang="zh"]{ --ink-mix-up: 84% }` — the same 84%
rung the system already gives red in both light cells.

**What is left.** The fourth combination, **dark + EN + red** (`--ink-mix-down`),
is still at 100%. In this artifact it is not a defect: red text in dark EN renders
only on plain `--panel`, where it measures **5.07:1**, comfortably over the floor.
It fails only on a graded lane's own 8–11% tinted cell — the surface the ZH twin
sits on, and the reason the ZH twin failed at 4.26:1.

**Why Lane B did not move it.** Moving `--ink-mix-down` in dark EN would change
what EN readers see, on a cell that passes, inside a correction cycle whose
architecture is frozen and whose commission says EN must remain passing and
unchanged. That is an uncommissioned visual change, not a repair.

**The R3C question, precisely stated.** Should `templates/theme.css` carry a dark
red text rung so that the law reads "red takes the 84% rung" in all four cells
rather than three, making the artifact safe against any FUTURE dark-EN surface
that puts red text on a tinted lane? The reference's own answer is recorded and
measurable; the production change is one declaration.

**Blast radius if adopted.** Every dark-theme surface in production that binds
`--ink-down` for text. Not the fills (`--fill-*`), not the chart hues, not any
`--up`/`--down` hex.

---

## D-2 — the `sc_flows` verbatim fragment fails AA in 75 cells

**What.** `fixture_supplement/fragments/sc_flows.html` — the sector-ETF flow
table, embedded byte-verbatim under a sha256 receipt — paints its value cells on
inline tints written by the producer:
`style="background:color-mix(in srgb, var(--down) 52%, transparent)"`, with the
text left at inherited `--text`. Measured across dark/light × EN/ZH:

| | value |
|---|---|
| cells below 4.5:1 | **75** |
| range | **2.24:1 – 4.45:1** |
| worst | the 52%-tint cells (`−$703M`, `−$1.3B`, `−$2.9B`, `+$1.5B`, …) |
| view | Money, "Where sector-ETF money is flowing" |

Both languages fail, and they fail on *different* cells, because the ZH hue
inversion swaps which sign gets which tint.

**Why Lane B did not repair it.** Two independent bars. (1) The fragment is
production's own bytes carried under a receipt: rewriting the inline styles
breaks the receipt and `verify_reference.py`, and the RIG verbatim-render law
forbids the reference restyling producer output. (2) Overriding it from the
reference's own CSS layer would make the reference *correct* producer output —
the same move Lane A's cycle refused for VTC-004 and VTC-005, both of which were
reattributed to the producer for exactly this reason.

**The R3C question.** The remedy is upstream and small: the tint is a background,
so either the tint ceiling drops (52% is the only rung that fails badly in both
themes) or the cell text takes a rung chosen against the tint rather than the
panel. Owner is the producer of `sc_flows`, not this reference.

---

## D-3 — heatmap tile text is not measurable by any flat-surface method

**What.** `.hm-t > .sym` and `.hm-t > .pc` paint white glyphs with
`text-shadow: 0 1px 2px rgba(0,0,0,.42)` over a nine-bin data-driven colour
field. 440 such cells exist across the matrix.

**Why no ratio is reported.** WCAG's contrast ratio describes ONE foreground
over ONE flat surface, and this satisfies neither half: the shadow is part of the
painted foreground and the field is a datum. Reporting a flat-surface number here
would be a fabricated measurement, which is precisely why the fresh
Mobile/Accessibility critic declined to claim these cells (MAC-005: *"Heatmap text
over color fields requires a separate human/automated contrast verification during
repair; the flat-background probe deliberately does not claim those
gradient/color-field cases"*).

**What Lane B did instead.** Performed the verification MAC-005 asked for, to the
limit the method allows: every tile is now measured for *containment* rather than
contrast (`build/views/money.html`, `fitHeatLabels()`), so no ticker is ever
painted cut — the documented "drop rather than truncate" rule is now enforced
with the width the browser actually painted instead of a character-count
estimate. Legibility of white-on-bin remains an R3C item.

**The R3C question.** Whether the bin palette needs a luminance-aware text
treatment (per-bin ink rather than one white plus a shadow), evaluated with a
method appropriate to text on colour fields — not the flat-surface formula.

---

## D-4 — the type ramp has no relative units (inherited, already recorded)

Recorded here only so R3C sees the whole token surface in one place. Not new,
not this cycle's: `visual_taste.yml` VTC-014 upheld it as advisory and
explicitly not charged against R3B, because production `theme.css` carries the
identical px ramp with zero relative units and `DESIGN_SYSTEM_SPEC.md` §3
mandates that the reference's token block be a verbatim mirror of it.

Lane B removed the artifact's **sub-ramp** tiers — the 9.5px receipt glyph in six
declarations, the 9px board unit line and the 9px Explore popover eyebrow are all
back on the declared `--fs-micro:10px` floor — so the ramp is now honoured
everywhere it is declared. Whether the ramp itself should be relative is
untouched and stays a platform-level ticket.

---

## What is NOT in this file

- No production file was edited by Lane B. `templates/theme.css` is byte-clean.
- No R3C work is started, scheduled or authorised here.
- No entry claims a verdict. Each is a measurement plus the reason the repair
  does not belong to a bounded reference-correction cycle.
