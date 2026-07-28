# MastermindX X ad campaign — July 2026

This package contains 20 launch-ready X image ads organized as 10 controlled
A/B pairs. Each pair holds the product surface, audience, destination and offer
constant while changing one primary persuasion variable.

## Deliverables

- `index.html` — editable artboard/gallery and exact-size render surface.
- `manifest.json` — post copy, headlines, CTAs, destinations, hypotheses and
  offer guardrails.
- `site/assets/landing/x-ads-2026-07/*.png` — final 1200 × 628 launch assets.

To preview all artboards, open `index.html`. To render one artboard at its exact
size, add its ID:

```text
index.html?ad=mx-x-01a
```

## Experiment map

| Pair | Product surface | A | B |
|---|---|---|---|
| 01 | Whole platform | Fragmentation problem | Daily decision outcome |
| 02 | Prophet signals | Tips lack a plan | Five-word decision system |
| 03 | Theme rotations | Fear of finding themes late | Discover leadership early |
| 04 | Insider/Congress | Processing-scale proof | Entry-timing benefit |
| 05 | 13F desk | Actions versus commentary | Research time saved |
| 06 | Options flow | Reduce the firehose | Find meaningful size early |
| 07 | Mastermind AI | One question, every desk | Market-aware AI |
| 08 | Terminal | Integrated research workflow | Free browser terminal |
| 09 | Full value stack | Replace many subscriptions | Context-to-risk workflow |
| 10 | Founding Pro | Savings first | Seven-day trial first |

## Offer language

Founding Pro is `$75/month billed annually` (`$900/year`). Monthly Pro is
`$149/month`. That is a `$888` saving versus 12 monthly payments, or about 50%
less. It is not 50% off the standard annual Pro price, so the campaign never
makes that claim.

The Founding Pro offer is limited to 2,000 memberships and the locked rate lasts
for as long as the member stays subscribed. Paid plans have a seven-day trial.

## Launch discipline

1. Run one pair per ad group with a 50/50 split.
2. Keep audience, placement, bid strategy, destination and schedule identical
   within the pair.
3. Use `trial_started / landing_view` as the primary decision rate.
4. Do not decide before both arms have at least 100 conversion opportunities.
5. Remove pair 10 immediately if the Founding Pro offer is no longer active.
6. Treat individual-stock values in the product UI as illustrative examples,
   not performance promises.
