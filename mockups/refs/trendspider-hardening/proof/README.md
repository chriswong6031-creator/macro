# PR-C proof renders — chart director, end to end

Rendered by `engine/marketing/chart_director.py` off the **real** split-adjusted
daily store (`data/baskets/ohlcv/`), as of 2026-08-03. Every fact was computed
by `engine/marketing/chart_facts.py` on COMPLETED bars; every chart plots the
live bar. `MANIFEST.json` carries each spec's audit slice — the claim kind, the
fact id, the plotted axis, the numbers restated in frame, and anything the
claim-window law refused on the way.

| File | Gate | What it shows | Reference |
|---|---|---|---|
| `a-level-touch-nvda-daily.png` | (a) | `ma_touch_200` on NVDA: four blue-grey discs on prior visits to the 200-day, a gold disc on now labelled `5th visit`, the average inline-labelled `200 SMA` in its own colour, and a `192.93` axis tag in that same colour. Volume profile in the runway. Axis 2025-06-23 → 2026-07-31 (279 bars) — the fact's own 252-bar window fits inside it. | `ref-27-ma-touch-discs-mu-daily.jpg` |
| `b-analog-ame-weekly.png` | (b) | `multi_year_high` on AME, WEEKLY + LOG: blue-grey discs on the separated prior instances, gold disc labelled `5-year high` on now, real volume pane, no moving average (the editorial chart draws none). Axis 2020-11-06 → 2026-07-31 (300 weekly bars) covers the 5-year claim. | `ref-13-enumerate-circle-amzn-monthly-log.jpg` |
| `c-stage-read-duol-weekly.png` | (c) | Stage read on DUOL, WEEKLY: the 30-week average inline-labelled `30 SMA`, a gold disc with the `Stage 2` chart label, volume profile. The COPY for this post says "marking up"; `Stage 2` is chart-label vocabulary only. | `ref-04-weinstein-stage-duol-daily-log.jpg` |
| `d-streak-intc-weekly.png` | (d) | `tf_streak_down` on INTC, WEEKLY: the six record weeks boxed in a translucent zone labelled `6 red weeks in a row`, and a consecutive-candles sub-pane whose y-unit IS the claim's unit (bottoming at −6). One 50-week average behind it. | `ref-10-streak-pane-mu-weekly.jpg` |
| `e-longtail-ax-weekly.png` | (e) | A **long-tail** name drawn live from an attention pool. `tf_record_high` on AX (Axos Financial), WEEKLY + LOG, gold disc labelled `Highest weekly close in 5 years`. | — |

## The pool row that produced (e)

```json
{"ticker": "AX", "why": "search attention z 3.7 (153 page views)",
 "asof": "2026-07-31", "source": "wiki_attention",
 "pool": "retail_attention", "fresh": true}
```

`AX` is outside the 524-name universe this program used to be fenced to
(S&P 500 membership ∪ the Nasdaq-100 file), which is what makes it a long-tail
pick rather than a mega cap that happens to top an attention ranking. The live
supply on this date was **228 rows**: hot_story 16, retail_attention 79,
options_volume 70, dollar_volume 63, stage2_leaders 0.

## Honest caveat on (c)

`stage2_leaders` and `stage_transitions` returned **[]** on this date. The
Weinstein backfill parquet is stamped 2026-07-17 and its freshness gate refuses
anything more than three sessions behind, so the pool is legitimately empty and
a separate collector fix is in flight. The stage proof therefore hands the
director the fact SHAPE those pools produce, rather than reconstructing a stage
read from the ungated `radar_internal._feed_stage`. In production the same code
path emits **no stage fact at all** until the backfill refreshes — which is the
gate working, and is asserted by
`tests/test_chart_director.py::TestFactDiscipline::test_stage_facts_degrade_to_nothing_when_the_pool_is_empty`.
