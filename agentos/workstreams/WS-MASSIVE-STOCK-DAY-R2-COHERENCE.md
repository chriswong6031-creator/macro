---
key: MASSIVE-STOCK-DAY-R2-COHERENCE
title: massive_stock_day public R2 publication coherence
objective: >
  Make public R2 massive_stock_day manifest and per-ticker objects one atomic
  generation so ticker-count and publish-last Last-Modified cannot diverge.
  Done = overlapping collect/publish cannot produce a generation the W2C
  technical consumer must refuse, without weakening that consumer.
status: active
program: market-memory
repos: [macro]
owner: coo-fable
class: build
blast_radius: reversible
ambiguity: scoped
owns_paths:
  - collectors/massive_stock_day.py
  - collectors/massive_flatfiles.py
  - scripts/publish_r2.py
waves:
  - id: C0
    title: Source-liveness first-cause + R2 coherence archaeology
    status: in_progress
    next_action: >
      Public generation is at session 2026-08-21 and internally coherent.
      Remaining C0 work is overlapping-publisher atomicity, not source
      liveness. Do not weaken
      engine/neuralweb/market_memory_technical_observation.py.
next_action: >
  Leave overlapping-publisher atomicity as the remaining C0 item. Do not
  mix with W2C v2. Ordinary v1 technicals may now consume session 2026-08-21.
do_not_redo:
  - Do not weaken the technical consumer to accept a torn generation.
  - Do not thin-publish SPY as a substitute for whole-store coherence.
  - Do not repair this inside a W2C v2 registration PR.
  - Do not treat a stock-day 403 on unpublished calendar-today as a Massive
    stock entitlement regression or substitute ThetaData.
  - Do not flatten probe_available reason into no_entitled_date.
landmines:
  - Two daily.yml collects overlapping still tear R2.
  - Manifest is put last in publish_r2.py; SPY can still land after a previous
    manifest Last-Modified if a prior run uploaded SPY late.
  - Unpublished stock_day keys 403 with an empty listing; listed+403 is the
    Options grant class. probe_available must keep those apart.
artifacts:
  - agentos/handoffs/MASSIVE-STOCK-DAY-R2-COHERENCE-2026-08-20.md
  - agentos/handoffs/MASSIVE-STOCK-DAY-R2-COHERENCE-2026-08-23.md
  - agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-m0b.md
decisions:
  - "DEC:MASSIVE-PROBE-UNLISTED-403-IS-UNPUBLISHED"
  - "DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA"
discoveries:
  - "DSC:MASSIVE-STOCK-DAY-UNPUBLISHED-TODAY-RETURNS-403"
  - "DSC:MASSIVE-DAY-AGGS-LASTMODIFIED-FOLLOWS-0430Z"
  - "DSC:MASSIVE-OPTIONS-FLATFILE-ENTITLEMENT-REGRESSION"
---

C0 first cause (2026-08-23): acquisition discovery, not an R2 publisher race.
Public R2 at classification was internally coherent and stale at session
2026-08-18 (count 21353 = n_tickers 21352+1; SPY parquet tip 2026-08-18;
manifest Last-Modified 2026-08-23 00:56:32Z is a re-put of that generation).
The 2026-08-19 ticker-count / publish-last tear remains a real D-class defect
and is not tonight's freeze.

