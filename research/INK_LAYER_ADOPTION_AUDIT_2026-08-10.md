# Ink-layer adoption audit — state-palette text on a tint of its own hue

**Status: FINDING + INSTRUMENT. No mass recolour proposed.**
Date: 2026-08-10 · Instrument: `scripts/audit_ink_on_own_tint.py` (report-only)

## §0 What this is

Two WCAG AA failures shipped and were fixed on 2026-08-10, four hours apart, on
the same element:

| PR | token | combo | before | after |
|---|---|---|---|---|
| #5226 | `--ink-pv-near` | zh / light | 3.90:1 | 4.83:1 |
| #5232 | `--ink-pv-avoid` | en / dark | 4.33:1 | 4.77:1 |

Both were the same shape, and it is not specific to Prophet: **text painted with
a state hue, on a background tinted with that same hue.** `.pv-chip` is
`background: color-mix(in srgb, var(--pvh) 13%, var(--panel))` with
`color: var(--pvh-ink)`. Tinting the background *toward* the foreground makes it
a strictly harder pair than the flat `--panel` the palette was measured against.

`theme.css` already anticipates half of this. Its own comment says the state
palette is FILL-grade, not TEXT-grade — `--up` `#1f9a55` tops out at 3.61:1 on
white — and it ships an `--ink-*` layer as the text-safe form, with the
instruction that *"consumers in page templates should write
`var(--ink-up, var(--up))`"*.

**This audit asks how widely that instruction was followed. Answer: not widely.**

## §1 The measurement

`scripts/audit_ink_on_own_tint.py`, run at `dfb19df0b36`:

```
180 candidate pair(s) under floor; 177 print the RAW token where an --ink-* twin exists.
```

Worst rows are all light mode, which matches the doctrine's own note that light
is where the fill-grade palette fails as text:

| ratio | combo | token | tint | selector | file |
|---|---|---|---|---|---|
| 2.65 | en+zh / light | `--warn` | 18% | `.tr-sev-P2` | `committee.html.j2` |
| 2.69 | en / light | `--up` | 16% | `.ask-mode-live`, `.kf-armed-yes` | `committee.html.j2` |
| 2.70 | en+zh / light | `--warn` | 16% | `.ask-mode-memo`, `.contra-sev-tension` | `committee.html.j2` |
| 2.76 | en+zh / light | `--warn` | 14% | `.kf-unit-chip` | `committee.html.j2` |
| 2.81 | zh / light | `--down` | 12% | `.ask-error` | `committee.html.j2` |
| 2.81 | en / light | `--up` | 12% | `#sector-heat .sh-heat` | `dashboard.html.j2` |
| 2.82 | en+zh / light | `--warn` | 12% | `.chip.sb-chip` | `basket_detail.html.j2` |
| 2.87 | en / light | `--up` | 10% | `.deesc-chip` | `macro_context.html.j2` |

**177 of 180 print the RAW token where an `--ink-*` twin already exists.** The
fix for those is mechanical and already house-idiomatic — `var(--up)` becomes
`var(--ink-up, var(--up))` — and it is a contrast fix, not a re-palette: the ink
keeps the hue and deepens it toward `--text`.

## §2 What the number does NOT mean

These are CANDIDATES. The instrument is static CSS analysis, and it has been
wrong in both directions already:

- **False positive, caught: dead CSS.** `.cmd-hero .v-chip.tone-*` measured
  **10 of 16** combos under AA (light as low as 2.82). It is unreachable:
  nothing in the repo ever emits `cmd-hero` or `v-chip` as markup — the file is
  included by `hk`/`china`/`canada` but no element carries the classes. The
  reachability filter now drops it. **Anything this tool prints must be
  confirmed against real markup before it is called a defect.**
- **Reachability is still an over-approximation.** A rule survives when every
  class token in its selector is emitted *somewhere*, which does not prove they
  co-occur on one element.
- **State-conditional, not currently visible.** The top rows return zero hits on
  today's live `committee.html` / `macro_context.html`, because the states that
  emit them are not active. They are real markup sites all the same —
  `.tr-sev-P2` is emitted from a JS string at `committee.html.j2:3414`,
  `.deesc-chip` at `macro_context.html.j2:702` and `:808`. These are **latent**
  defects: invisible today, rendered the moment a P2 contradiction or a
  de-escalation exists. A live-page grep is therefore not a refutation.
- **Under-reports.** Component-scoped hues (`--ic-col`, `--m7-col`, `--gr`,
  `--deck-accent`, ...) are skipped, as are alpha and stacked translucency.
- Font size is read from the same rule body; a rule that inherits its size is
  assumed small text, so a few large-text rows may be over-reported.

## §3 Why this was invisible

The failing value appears in **no source file**. The ink is computed by
`color-mix` at paint time from tokens the theme and language switches re-bind
underneath it, so a wrong percentage looks like every other percentage. The
prophet family only became measurable once it had an instrument; this audit
gives the rest of the estate the same instrument.

The second reason is a generalisation in `theme.css`'s own doctrine. It claimed
raw dark inks *"pass 4.5:1 on every estate surface"*. That pass measured
`--bg`/`--panel`/`--panel2` — flat surfaces — and never an ink on a tint of its
own hue, which is darker than any of them. #5232 corrected the comment. **An ink
proven against a panel is not proven on its own tint.**

## §4 Proposed sequencing — deliberately not done here

Not folded into #5232: that PR was a token fix with pixel proof for one
component, and a 177-rule recolour is a different change with a different review
shape. Each row needs its rendered state confirmed in a browser, in both themes
and both languages, because some are large text and some are unreachable.

1. **Confirm-then-fix by surface, not by ratio.** Take one file at a time
   (`committee.html.j2` carries the worst cluster), render the states that emit
   each class, and fix the confirmed ones by routing to `var(--ink-X, var(--X))`.
2. **Dark needs more than the ink layer for the weak red.** `--down` `#e06464`
   on a 13% tint of itself measures ~4.0–4.3 even though the dark ink layer is a
   pass-through at 100%. That hue is the estate's thinnest; where it is printed
   as text on its own tint, it needs a rung the way `--ink-pv-avoid` got 88%.
3. **Do not wire `--strict` as a blocking gate until the backlog is drained** —
   it would red main on legacy debt rather than on a regression, which is the
   trap `DESIGN_DOCTRINE.md` §6 already calls out for the vocabulary lint.
4. Once drained, flip the tool to `--strict` in a pack so the class cannot
   return.

## §5 Reproducing

```bash
python3 scripts/audit_ink_on_own_tint.py            # full table
python3 scripts/audit_ink_on_own_tint.py --top 20   # worst 20
python3 scripts/audit_ink_on_own_tint.py --strict   # exit 1 if any fail
```

The Prophet family, already fixed, is pinned separately and measured two ways —
`tests/test_prophet_verb_ink_contrast.py` (pure-python, CI-wired) and
`mockups/refs/prophet_verb_ink/probe_pv_ink.py` (Chromium). They agree to the
last digit, so a divergence means the change is wrong, not the harness. That
pair is the model for how a surface should be signed off here.
