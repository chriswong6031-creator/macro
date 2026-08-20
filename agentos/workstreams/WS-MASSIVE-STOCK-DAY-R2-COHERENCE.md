---
key: MASSIVE-STOCK-DAY-R2-COHERENCE
title: massive_stock_day public R2 publication coherence
objective: >
  Make public R2 massive_stock_day manifest and per-ticker objects one atomic
  generation so ticker-count and publish-last Last-Modified cannot diverge.
  Done = overlapping collect/publish cannot produce a generation the W2C
  technical consumer must refuse, without weakening that consumer.
status: proposed
program: market-memory
repos: [macro]
owner: coo-fable
class: build
blast_radius: reversible
ambiguity: scoped
owns_paths:
  - collectors/massive_stock_day.py
  - scripts/publish_r2.py
waves:
  - id: C0
    title: Archaeology + single-writer / atomic-manifest repair
    status: todo
    next_action: >
      Confirm there is no competing writer, then make manifest put strictly
      after a coherent file set (n_tickers+1==count and manifest Last-Modified
      not before SPY). Do not weaken
      engine/neuralweb/market_memory_technical_observation.py.
next_action: >
  Do not start until a session claims this wave. Do not mix with W2C v2.
do_not_redo:
  - Do not weaken the technical consumer to accept a torn generation.
  - Do not thin-publish SPY as a substitute for whole-store coherence.
  - Do not repair this inside a W2C v2 registration PR.
landmines:
  - Two daily.yml collects overlapping still tear R2.
  - Manifest is put last in publish_r2.py; SPY can still land after a previous
    manifest Last-Modified if a prior run uploaded SPY late.
artifacts:
  - agentos/handoffs/MASSIVE-STOCK-DAY-R2-COHERENCE-2026-08-20.md
  - agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-m0b.md
---

D-class side finding from W2C M0B/M0C. Not a W2C admission repair.
