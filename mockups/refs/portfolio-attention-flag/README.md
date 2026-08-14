# Portfolio attention flag — extension-grade vocabulary fix

Before/after crops for the fix in `templates/portfolio.js`: the row attention flag and
deterministic attention-stack rules 1 and 3 compared extension grades against `'high'`
and `'extreme'`, words `engine/extension.py` has never emitted.

| | holdings row | attention stack |
|---|---|---|
| before | `holdings-before-dark.png` / `-light.png` | `stack-before-dark.png` / `-light.png` |
| after | `holdings-after-dark.png` / `-light.png` | `stack-after-dark.png` / `-light.png` |

## What the crops show

Nine positions, of which four carry an elevated grade in the artifact:

| name | `ext.grade` | `pct_vs_200dma` | before | after |
|---|---|---:|---|---|
| DELL | stretched | +114.4% | — | **Stretched** |
| CBRL | parabolic | +69.3% | — | **Stretched** |
| MSFT | stretched | +14.1% | — | **Stretched** |
| KO | stretched | +13.9% | — | **Stretched** |
| IRDM | steady | +58.3% | — | — |
| NVDA | intrend | +15.3% | — | — |
| AAPL | intrend | +8.0% | — | — |
| COST | intrend | −0.6% | — | — |
| PG | intrend | −1.2% | — | — |

The attention stack goes from **1 of 9 positions** (only rule 5, context) to **3 of 9**:
rule 3 now fires for MSFT and DELL — "Sitting far above its own trend after a long run
up."

IRDM and KO are the pair worth reading twice. IRDM sits **+58.3%** above its 200-day
line and is NOT flagged; KO sits **+13.9%** above and IS. That is the engine behaving as
designed — the grade is a z-score against the name's OWN extension history, not raw
distance from a moving average — and it is the reason a wrong-vocabulary comparison was
invisible for so long: a page that flags nothing looks exactly like a calm book.

## How they were produced

Both variants were captured in one Playwright run against the real `site/watchlist.html`
over a live local server, with only ONE input changed between them:

- `**/portfolio.js*` was routed to `origin/main`'s copy for *before* and to this branch's
  copy for *after*. Nothing else differs — the RISK SHARE column is byte-identical across
  the pair (13/10/19/6/13/12/12/7/7), which is what makes this a controlled comparison
  rather than two screenshots of two moments.
- `**/*.r2.dev/stockdata/*.json` was routed to frozen copies of the production artifacts
  (pulled from R2 on 2026-08-13 into `site/stockdata/`, which is gitignored). The page
  reads its per-ticker data from R2 in production, and the nightly re-bake moves grades,
  so freezing is what makes the pair reproducible.

The book is seeded into `localStorage['mdash.pf.v1']` — the signed-out path
`watchstore.js` resolves to — and the holdings section is pinned to the top of the
viewport for the crop. Neither touches the table's own rendering.

The capture script is not committed: it depends on frozen artifacts that are gitignored
and on a local server, so a checked-in copy could not be re-run as-is. The behaviour it
demonstrates is pinned in CI instead, by
`tests/test_watchlist_workspace_js.py` §9 — including a node-shelled probe that runs the
shipped closure over all five real grades.
