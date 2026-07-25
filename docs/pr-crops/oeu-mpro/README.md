# OEU M-PRO crops — display-tier options context on the Prophet surfaces

Committed evidence for the M-PRO PR (`research/options_estate/OEU_MASTERPLAN.md` §4).
All shots are **real data**: today's `site/factordata/us_standouts.json` board rows and
`site/leaderradar/radar.json` radar rows, with the options context derived by the
shipping code paths (`scripts/build_site._attach_board_display_chips` and
`engine.leader_lifecycle.entry_read`) reading the real `site/gex/index.json` and
`data/polygon_gex/summary_<T>.parquet` stores. Rendered at 2× through the shipping
templates + `templates/theme.css`.

## Prophet card (hook 1) — `us_stocks.html`

| File | Shows |
|---|---|
| `prophet-card-en-dark.png` / `-light.png` | EN, both themes |
| `prophet-card-zh-dark.png` / `-light.png` | ZH, both themes |

Four real cards, left to right:

- **VZ** — gains the wall row (a scorable call wall 1.3% overhead)
- **ROST** — gains the IV row (options at the top of their own 34-day record)
- **WAB**, **STBA** — no options coverage; **rendered exactly as before this lane**

The options rows fold into the **same ⚠ popover** as every other caution. There is no
new chip, no new layout slot, and no change to verb / stage / edge / zone.

## Prophet card ⚠ popover (hook 1, copy legibility)

`prophet-card-popover-en-dark.png`, `prophet-card-popover-zh-dark.png`

The two flagged cards with the popover open, so the actual copy is readable. These two
pages carry **two harness-only CSS rules**, stated in the caption baked into each image:

1. the popover is force-shown (shipping: `:hover` / `:focus-within`), and
2. the card's `overflow:hidden` is lifted.

Nothing else differs from shipping. (2) exists because the shipping card clips ~18px of
this 162px popover — a **pre-existing** condition, not introduced here: the live board
already ships cards carrying 5–6 caution rows. Flagged in the PR body, not fixed in this
lane, because a `.pvcard` overflow change would alter every card on five boards and break
this lane's own zero-visual-diff baseline.

## Leader Radar entry caveats (hook 2) — `leader_radar.html`

`leader-radar-caveat-en-dark.png`, `leader-radar-caveat-zh-dark.png`

Lane cards with `entry_read().caveats` rendered as the quietest flag on the card:

- **ADBE** — turnaround verdict only, no options caveat (no coverage / below threshold)
- **INTU** — gains "Options pricing a bigger move than usual"
- **TRV**, **MSFT** — gain "Options ceiling just above — price tends to stall there"

Note the hierarchy: the loud flags (⚡ watch window, ⚠ already moved) still rule the card;
the options line is muted context underneath. The verdict itself is unchanged — replaying
all 173 radar rows with and without options context produced **0** changes to
`entry_read().key` or `.basis`.

## Reproducing

The harness lives in the PR session's scratchpad (not committed — it is a screenshot rig,
not a build step). It imports the shipping macro/template and the shipping builder attach
path; regenerating it means re-rendering `templates/_prophet_card.html.j2` and
`templates/leader_radar.html.j2` against the two stores above.
