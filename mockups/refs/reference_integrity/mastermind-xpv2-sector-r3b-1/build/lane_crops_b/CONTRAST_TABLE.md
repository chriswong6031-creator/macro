# R3B1-11 — contrast matrix, measured pre and post

Lane B (accessibility + token repair), XPV2-SC-R3B.1.
Candidate: `proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html`,
`sha256 fec05b058fbc9dbe29744ad015b7ee9cd9baa5cb85bbbde739daa8b97644cf70`.
Floor: **4.5:1** for text under 18px (or under 14pt bold) — `build/DESIGN_SYSTEM_SPEC.md` §366.

Reproduce with:

```
<playwright-python> build/contrast_audit.py
```

## Method, and the two traps it is built around

Every cell is the WCAG 2.x ratio of the painted foreground against the
**composited** surface behind it — the whole ancestor background stack,
alpha-composited bottom-up onto the canvas — not merely the nearest opaque
ancestor. 16,140 text leaves were measured across six views × two themes × two
languages; the table below reports the commissioned vocabulary by its visible
text, so a class rename cannot quietly drop a cell from the matrix.

Two traps have fabricated results in prior audits of this artifact, and the
script handles both by construction:

1. **Chromium serialises every `color-mix()` as `color(srgb r g b / a)` with
   components in 0–1.** A parser reading those as 0–255 saturates all channels,
   makes foreground and background identical and reports a ratio of exactly
   1.00. In this codebase a computed 1.00 means the parser broke, not the page:
   both spellings are parsed, and an exact 1.00 is flagged `SUSPECT` rather than
   counted as a failure. This audit reports **0 suspects**.
2. **`html[data-lang="zh"]` inverts `--up`/`--down` site-wide (红涨绿跌), and the
   swap is not contrast-neutral.** An EN-only sweep is structurally blind to the
   entire ZH half — which is exactly how the defect below reached a frozen
   reference with the EN twins of the same components passing at 5.58:1. Every
   cell is therefore measured at theme × language.

## Gate result

| gate | result |
|---|---|
| reference-authored text cells scored | **15,340** |
| AA failures | **0** |
| cells below the declared ramp floor (10px) | **0** (was 44) |
| parser-suspect cells (ratio exactly 1.00) | **0** |

## The commissioned cells, pre → post

Each row reports the WORST measured instance of that string in that
view/theme/language. `PRE` is the frozen-candidate measurement that reproduces
the critic receipts exactly (`mobile_accessibility.md` MAC-005, `visual_taste.yml`
VTC-003 and VTC-010); `POST` is the same probe against the repaired build.

| surface (view) | text | theme | lang | size/weight | PRE | POST | floor | verdict |
|---|---|---|---|---|---|---|---|---|
| overview | `20d vs market` | dark | en | 9px → 10px / 600 | 3.91:1 | 5.57:1 | 4.5 | **repaired** |
| overview | `20d vs market` | light | en | 9px → 10px / 600 | 3.43:1 | 5.43:1 | 4.5 | **repaired** |
| overview | `20日对比市场` | dark | zh | 9px → 10px / 600 | 3.91:1 | 5.57:1 | 4.5 | **repaired** |
| overview | `20日对比市场` | light | zh | 9px → 10px / 600 | 3.43:1 | 5.43:1 | 4.5 | **repaired** |
| overview | `Buy now` | dark | en | 11px/700 | 5.58:1 | 5.58:1 | 4.5 | unchanged, passing |
| overview | `Buy now` | light | en | 11px/700 | 4.98:1 | 4.98:1 | 4.5 | unchanged, passing |
| confluence | `Entry now` | dark | en | 11px/700 | 5.58:1 | 5.58:1 | 4.5 | unchanged, passing |
| confluence | `Entry now` | light | en | 11px/700 | 4.98:1 | 4.98:1 | 4.5 | unchanged, passing |
| confluence | `Leading` | dark | en | 11px/700 | 5.76:1 | 5.76:1 | 4.5 | unchanged, passing |
| map | `Leading` | dark | en | 11px/600 | 5.57:1 | 5.57:1 | 4.5 | unchanged, passing |
| moving | `Leading` | dark | en | 11px/700 | 7.05:1 | 7.05:1 | 4.5 | unchanged, passing |
| confluence | `Leading` | light | en | 11px/700 | 5.36:1 | 5.36:1 | 4.5 | unchanged, passing |
| map | `Leading` | light | en | 11px/600 | 5.43:1 | 5.43:1 | 4.5 | unchanged, passing |
| moving | `Leading` | light | en | 11px/700 | 6.21:1 | 6.21:1 | 4.5 | unchanged, passing |
| money | `Risk-on` | dark | en | 10px/700 | 5.39:1 | 5.39:1 | 4.5 | unchanged, passing |
| money | `Risk-on` | light | en | 10px/700 | 5.14:1 | 5.14:1 | 4.5 | unchanged, passing |
| moving | `Still measuring` | dark | en | 10px/700 | 7.59:1 | 7.59:1 | 4.5 | unchanged, passing |
| moving | `Still measuring` | light | en | 10px/700 | 3.61:1 | 6.33:1 | 4.5 | **repaired** |
| confluence | `就绪` | dark | zh | 11px/700 | 4.45:1 | 4.97:1 | 4.5 | **repaired** |
| confluence | `就绪` | light | zh | 11px/700 | 4.95:1 | 4.95:1 | 4.5 | unchanged, passing |
| moving | `测量中` | dark | zh | 10px/700 | 7.59:1 | 7.59:1 | 4.5 | unchanged, passing |
| moving | `测量中` | light | zh | 10px/700 | 3.61:1 | 6.33:1 | 4.5 | **repaired** |
| confluence | `现可入场` | dark | zh | 11px/700 | 4.26:1 | 4.79:1 | 4.5 | **repaired** |
| confluence | `现可入场` | light | zh | 11px/700 | 4.59:1 | 4.59:1 | 4.5 | unchanged, passing |
| overview | `立即买入` | dark | zh | 11px/700 | 4.26:1 | 4.79:1 | 4.5 | **repaired** |
| overview | `立即买入` | light | zh | 11px/700 | 4.59:1 | 4.59:1 | 4.5 | unchanged, passing |
| confluence | `领先` | dark | zh | 11px/700 | 4.45:1 | 4.97:1 | 4.5 | **repaired** |
| map | `领先` | dark | zh | 11px/700 | 5.57:1 | 5.57:1 | 4.5 | unchanged, passing |
| moving | `领先` | dark | zh | 11px/700 | 7.05:1 | 7.05:1 | 4.5 | unchanged, passing |
| confluence | `领先` | light | zh | 11px/700 | 4.95:1 | 4.95:1 | 4.5 | unchanged, passing |
| map | `领先` | light | zh | 11px/700 | 5.43:1 | 5.43:1 | 4.5 | unchanged, passing |
| moving | `领先` | light | zh | 11px/700 | 6.21:1 | 6.21:1 | 4.5 | unchanged, passing |
| money | `风险偏好` | dark | zh | 11px/700 | 4.45:1 | 4.97:1 | 4.5 | **repaired** |
| money | `风险偏好` | light | zh | 11px/700 | 4.95:1 | 4.95:1 | 4.5 | unchanged, passing |

**EN is unregressed.** Every EN cell holds its pre-repair value to the second
decimal, because the token rung added for this repair is scoped to dark + ZH and
no `--up` / `--down` hex was touched. The only EN cells that moved are the two
that were failing — `20d vs market` and light `Still measuring` — and both moved
upward.

## Lane A's restored nodes — unregressed

Measured through Lane A's own probe (the `data-r3b1="01"`…`"07"`, `"13"` markers),
dark/light × EN/ZH, 44 cells:

| node | worst measured, all four cells |
|---|---|
| `01` sizing directive text | 13.71:1 |
| `02` caveat control | 5.11:1 |
| `03` migration note | 13.71:1 |
| `04` playbook destination | 5.46:1 |
| `05a/05b/05c` hero enrichment | 5.11:1 |
| `05a/05b` relative-performance figures | 13.71:1 |
| `07` S&P coverage sentence | 11.56:1 |
| `13` Conviction figure label | 5.43:1 |

Minimum across all 44 cells: **5.11:1** — identical to Lane A's own recorded
floor. Nothing regressed; `13` rose from 5.43/5.57 where the shared ramp-floor
change reached it.

## What changed, and why these were the changes

Three repairs, all through the token layer or the type ramp. No page-local
literal colour was introduced anywhere, and `templates/theme.css` was not touched.

**1 · The fourth quadrant of the ink-rung matrix** (`build/shell.html`, the
`--ink-mix-*` block). The rungs tune the two state hues per theme, and the ZH
block above them swaps the two values because 红涨绿跌 swaps the two hues. In
dark that swap is a no-op — dark was never tuned per hue at all, both rungs sit
at the 100% default — so the swap moved 100% onto 100% and the red channel
arrived on the dark canvas with no rung of its own. On plain `--panel` that is
harmless (red measures 5.07:1); on a graded lane's own 8–11% tinted cell it is
not, and that is exactly where the state vocabulary lives. The value is not a new
magic number: **84% is the rung this system already gives the red channel
wherever it has been measured** — light EN gives `--ink-mix-down` 84%, light ZH
gives the (now red) `--ink-up` the same 84%. One law, legible across all four
cells: red takes the 84% rung.

**2 · The verdict badge binds the rung, not the hue** (`build/views/moving.html`,
`TR_V`). `--warn` / `--up` are surface hues; `--ink-warn` / `--ink-up` are the
same hues already graded for text on their theme's canvas. Reaching past them put
"Still measuring / 测量中" on light at raw `#b9791a` — 3.61:1 — while the
identical badge on dark passed at 7.59:1, so no dark-theme review could see it.

**3 · The board's unit line goes back onto the ramp** (`build/views/overview.html`,
`.r3-colfig em`). It carried two compounding local dilutions of the system: a 9px
size half a step under the declared floor (`--fs-micro:10px`), and a 78%-alpha
thinning of `--muted` that no token authorises. What made the line read as
tertiary was never the alpha — it is the size step, the 600 weight and the
tracking against a 22px figure directly above it, and all three survive.

The same ramp-floor correction removed the artifact's other sub-ramp tier: the
receipt ring's `?` glyph, which sat at 9.5px in six declarations, and Explore's
9px popover eyebrow. **44 sub-ramp cells → 0.**

## Recorded, deliberately NOT repaired here

Two classes of cell sit below 4.5:1 in the built artifact and are excluded from
the gate on grounds that are recorded rather than assumed. Both are filed for
R3C in
`research/reference_integrity/mastermind-xpv2-sector-r3b-1/design_system_dependency_r3c.md`.

| class | cells | measured | why not repaired in Lane B |
|---|---|---|---|
| `.scf-c` — the sector-ETF flow table's tinted value cells | 75 | 2.24:1 – 4.45:1 | The table is a **verbatim production fragment** (`fixture_supplement/fragments/sc_flows.html`, carried under a sha256 receipt). Its `color-mix(… 52%)` tint fills are producer bytes; the RIG verbatim-render law forbids the reference rewriting them, and the receipt would fail if it did. Upstream fix. |
| `.hm-t > .sym` / `.pc` — heatmap tile text | 440 | not claimable | Shadowed white glyphs over a data-driven colour field. WCAG's ratio describes one foreground over one flat surface and satisfies neither half here; the fresh Mobile/Accessibility critic declined to claim these for the same reason (MAC-005: "the flat-background probe deliberately does not claim those gradient/color-field cases"). Measured and recorded; not scored. |

## Evidence crops

| file | shows |
|---|---|
| `08_overview_state_ledge_1440_dark_zh.png` | 立即买入 after the rung repair, 1440 dark ZH |
| `09_confluence_state_ledge_1440_dark_zh.png` | 现可入场 / 领先 / 就绪 after the rung repair |
| `10_overview_state_ledge_1440_dark_en.png` | the EN twin, unchanged |
| `11_moving_trackrecord_1440_light_en.png` | light "Still measuring" after the rung repair |
| `12_moving_trackrecord_1440_light_zh.png` | light 测量中 after the rung repair |
| `13_overview_board_head_1440_light_en.png` | "20d vs market" at the ramp floor in full `--muted` |
