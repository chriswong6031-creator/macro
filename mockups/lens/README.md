# Lens — site-wide explainer popover system

Design session 2026-07-19 (main-loop, taste-as-deliverable per CLAUDE.md Design lane).
Operator ask: overhaul every hover/`?` explainer container — concise, no machine text,
illustrated, beautifully formatted, billion-dollar-SaaS bar, great on desktop **and**
mobile. Standing content rule saved as memory `hover-popup-doctrine`.

**Demo:** open `index.html` (bilingual EN/中文, dark/light). Production artifacts:
`lens.css` + `lens.js` — written against house tokens with fallback chains so they load
in **both** CSS families (theme.css `--panel/--text/--muted` and vector `--card/--ink`).

## The design in one paragraph

One glass card for every explainer. Anatomy: category-tinted **illustration disc** +
small-caps **kicker** naming the kind of answer → plain **title + body** (glance-tier
vocabulary only) → the **receipt**: machine facts (n, window, source, cadence) in small
mono **below a dashed perforation** — the doctrine's plain-words-above / receipt-below
honesty made structural. Signature risk: a 1px **aurora hairline** with a category-tinted
arc at the crown and a single light sweep on open; no arrow — the card materializes from
the trigger via spring transform-origin. Five kinds map to the doctrine's Tier-2 taxonomy:

| kind | kicker | accent | use for |
|---|---|---|---|
| `define` | What this is | `--info` blue | term definitions |
| `read` | How to read it | `--q2` gold | scales, thresholds, anchors |
| `record` | Track record | `--ok` green | base rates, nulls in plain words |
| `source` | Where it's from | slate | provenance, cadence, delay |
| `caution` | Heads-up | `--warn` amber | staleness, delays, honest asterisks |

## Behavior spec

- Desktop: hover-intent 90 ms open / 180 ms close grace; card itself hoverable.
- Entrance: 280 ms spring (`cubic-bezier(.34,1.26,.4,1)`) scale+rise from the trigger,
  content staggers 45/90 ms, sheen sweeps once then the card is still. Exit 120 ms.
- ≤640 px: bottom sheet — scrim (blur+darken), drag handle, ✕, swipe-down ≥64 px or
  tap-away dismisses, `env(safe-area-inset-bottom)`, scroll-locked page.
- Keyboard: focus opens (triggers are real `<button>`s / `tabindex=0` terms with
  focus-visible rings), Esc closes, `aria-describedby` wired to the singleton.
- One singleton `#lensPop` in the DOM; `prefers-reduced-motion` → fades only;
  `@supports not (backdrop-filter)` → near-opaque fill.

## Content contract

- **String tier (zero migration):** existing `data-tip-en` / `data-tip-zh` attributes
  render through the new card (`.lens-plain`). Also accepts `data-lens-en/zh`.
- **Rich tier:** trigger (`.lens-q` button or `.lens-term` dotted span) + a `.lens-src`
  hidden block (child or next sibling) carrying `data-lens-kind` and the anatomy markup
  (see `index.html` for canonical blocks, or the header comment in `lens.css`).
- Bilingual via `l-en`/`l-zh` spans everywhere — **never `title=`** (CI law).
- Copy law (memory `hover-popup-doctrine` + doctrine Tier 2): ≤80 words, glance-tier
  vocabulary above the perforation, machine facts only inside `.lens-receipt`.

## Integration map (follow-up PR, source-only)

The census (2026-07-19) found 17 tooltip mechanisms. Lens lands at the one seam that
upgrades most of the site at once, then absorbs the forks opportunistically:

1. **Restyle the singleton** — replace `.i18n-tip-pop` (theme.css:1256, theme.js:2891)
   with Lens: **486 `data-tip-en/zh` attributes** restyle with zero template changes, and
   `upgradeHelpIcons()` (theme.js:3024) keeps feeding the **~295 legacy `help()` `?`
   icons** into it unchanged. Keep the `.help` markup contract; restyle the glyph to
   `.lens-q` visuals.
2. **Rich tier** — add a `lens(kind, …)` Jinja macro beside `t()`/`help()`; adopt on
   surfaces as they're touched (start where receipts already exist: us_stocks Turn-Watch
   `?`, baskets footers, transmission `.txq`).
3. **Absorb page forks** when touching their pages: `.txq` (transmission), `.tm-flag`,
   `.st-th-tip::after`, `.hovchart` (keep canvas, adopt card chrome), `.nb-cau`,
   special_situations `data-tip→title` (kills an EN-only + native-tooltip defect).
4. **Out of scope** (different component class): `.row-pop`, `.mx5-popover/.mx5-dlg`
   dialogs, nav/alert/settings popovers, `.lst-ovl`, `.sx` islands — though the sheet
   mechanics and hairline recipe are reusable there.
5. z-index registry: Lens sits at 12600 (above `.row-pop` 12000; replaces 12500).
