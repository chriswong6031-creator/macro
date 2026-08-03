# Wire breaking-card reference shots

Committed 2026-08-02 with the wire-relay defect fix. These are the reference
images a future session gets INSTEAD of prose — the spawn-handoff law (CLAUDE.md
§Spawn-handoff law, rule 2: never hand off a look in prose, the session cannot
see your screenshots).

Renderer: `engine.marketing.chart_render.render_breaking_card`.
Rasterized through the house path (`rasterize_svg`, headless Chrome, scale 1).

| File | What it pins |
|---|---|
| `01_before_landscape_at_feed_width.png` | The rejected state: 1000×560 landscape, six real items at 400px feed width. The headline is unreadable and the right third of every card is void. |
| `02_after_square_at_feed_width.png` | The same six items at 1080×1080, same 400px feed width. This pair IS the acceptance evidence for AD_MASTER_PAPER §0 AG-3. |
| `03_square_1080_geopolitical_flash.png` | Long headline filling the box — 6 lines, no clip, no dead space. Generic relay source shows the tier alone (`AGGREGATOR`), never an @handle. |
| `04_square_1080_with_tape_strip.png` | Headline + summary + 2×2 tape strip + official-tier chip. The densest layout the card supports. |
| `05_square_1080_tragedy_no_cta.png` | Sentinel tone rule: `suppress_cta=True` collapses the footer to the sober brand mark — no URL, no trial button. |
| `06_tall_1080x1350_quote.png` | The allowed 4:5 variant. Same code path; the extra room buys headline lines, not padding. |
| `07_square_1080_earnings_call_sibling.png` | `earnings_call_lane` shares this renderer with `eyebrow="EARNINGS CALL"` — proof the sibling lane still lays out. |

## The rules these shots encode

- **Canvas**: 1080×1080 default, 1080×1350 when content warrants (AD_MASTER_PAPER §4.1).
- **Type floors on 1080** (§0 AG-3): headline ≥ 84px (76px absolute floor before
  the copy is clipped instead), summary ≥ 40px, chips ≥ 27px.
- **Composition**: masthead → amber dateline rule → desk eyebrow → the news at
  poster scale → summary as an indented second voice → the source slug (tier
  chip + timestamp) → tape strip → brand footer. The slug sits UNDER the copy,
  where a wire slip puts its source line.
- **Never on a card**: an @handle in any input (screened before render), a
  summary that restates the headline, a card that restates the post text.

Regenerate with `tests/test_marketing_card_earns_pixels.py` fixtures; the
geometry and legibility floors are pinned there, so a change that breaks these
shots turns a test red first.
