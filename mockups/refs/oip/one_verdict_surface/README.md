# One verdict surface — the two chrome spots, after

Visual proof for the base-spec follow-up `W1_DESIGN_SPEC.md` §0.13 flagged and
`WORKSPACE_DESIGN_SPEC.md` §0.16 resolves: `options.html` now keeps **exactly one**
decision element, and the two pre-existing chrome spots that duplicated it keep their
caveat sentence instead of a stance chip.

| Crop | Theme / lang / width |
|---|---|
| `01_chrome_en_dark.png` | dark · EN · 1000px |
| `02_chrome_en_light.png` | light · EN · 1000px |
| `03_chrome_zh_dark.png` | dark · ZH · 1000px |
| `04_chrome_mobile_375.png` | dark · EN · 375px |

Each crop stacks the three elements the change touches, in page order:

1. **`.oew-nofuse` banner** — chip removed, sentence kept. It rides the persistent
   header on all four mode tabs, so its chip repeated the read's verdict everywhere.
2. **Ticker name header** — the page's one decision element, carrying the sole
   `data-verdict-surface` marker and the only surviving `.oew-stance` chip.
3. **"Today's measured flow" footer** — chip removed, sentence *and* as-of stamp kept.

## How these were captured

The `.oew` markup is real: sections 2 and 3 are the live DOM from a `renderTicker()`
run (Ticker mode is built entirely in JS), lifted verbatim into a small card harness
carrying the page's own `<style>` blocks plus `theme.css` and theme.js's
`soft-contrast` layer — the full `options.html` renders blank in the preview pane, and
Playwright is unusable on this host. The harness is scratch-only; only these PNGs ship.

Captions and the numbered eyebrows are harness chrome, not page copy, and stay English
in the ZH crop so the ZH shot shows only translated *page* strings.

## What the crops are evidence for

- exactly one `.oew-stance` chip renders across a whole Ticker read (verified in the
  live DOM, not just the source)
- both caveat sentences survive **verbatim in EN and ZH**, with the flow panel's as-of
- the layout holds with the chip gone, in both themes and at 375px

Pinned in CI by `tests/test_build_options_command.py`:
`test_exactly_one_verdict_surface` and
`test_chrome_caveats_keep_the_sentence_and_drop_the_chip`.
