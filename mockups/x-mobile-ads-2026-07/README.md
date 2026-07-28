# MastermindX X mobile campaign system

Twenty launch-ready 4:5 assets built for the X mobile feed:

- Five standalone hero ads.
- Five three-card carousel stories (15 cards).

The hero ads communicate the complete acquisition argument in a single frame:
one promise, one dominant product proof, no more than three evidence points, and
the Founding Pro offer. The carousels separate that same argument into a
promise, evidence, and offer so the product breadth never has to compete with
mobile legibility.

## Deliverables

- `index.html` — editable 1440 × 1800 artboards and full gallery.
- `manifest.json` — launch copy, hypotheses, destinations, asset paths and
  offer guardrails.
- `site/assets/landing/x-mobile-ads-2026-07/*.png` — five hero PNGs and 15
  carousel PNGs.

Render one exact artboard with:

```text
index.html?creative=mx-mobile-01
index.html?creative=mx-carousel-01-1
```

## Mobile rules

- Master canvas: 1440 × 1800 (4:5).
- Critical headlines: 112–128 px.
- Primary support copy: 46–48 px.
- Product outcomes and trade-plan numbers: 25–50 px.
- One dominant product surface per hero.
- Three evidence points maximum in a standalone hero.
- Carousel structure is always promise → evidence → offer.
- Every artboard is reviewed at 390 px rendered width.

## Offer language

Founding Pro is `$75/month billed annually` (`$900/year`). Monthly Pro is
`$149/month`, so the offer is `$888` less than 12 monthly payments, or about
50% less. It is not described as 50% off the standard annual price.

Paid plans include a seven-day trial. The locked Founding Rate lasts while the
membership stays active.

## Experiment discipline

1. Test the five hero ads against one another as one set.
2. Test the five carousel stories against one another as a separate set.
3. Keep audience, bid, placement, destination and schedule identical within
   each set.
4. Do not compare hero and carousel performance until each format has enough
   conversion opportunity.
5. Judge the primary result on `trial_started / landing_view`.
6. Pause every offer creative immediately if Founding Pro terms change.
