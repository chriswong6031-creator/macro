---
key: TERMINAL-GREY-DOT-IDENTITY
claim: >
  The operator's "grey dot" early-entry marker is the Terminal repo's early anticipation
  dot: signal_layer/confluence_v2.py::early_dots() at charting-app origin/master — 3D
  StochRSI K×D bullish cross while D dipped below 20 within 8 bars, AND the 2D RSI-MACD
  histogram strictly rising, PIT-joined by known_ts. It renders as a 2.2px circle, 55%
  opacity, fill #717a8e (--muted), 9px below the bar low, behind the "Signals detail"
  chip; only washout-context dots are promoted to the amber EARLY marker (#e8b339), and
  the unpromoted grey form remains the overwhelming majority (29 dots ≥2025 across
  NVDA/TSLA/NFLX; 3 promoted, all NFLX). The emitter comment names "the old gray
  side-channel dot" verbatim (confluence_v2.py@origin/master:1174-1176).
falsifier: >
  The operator naming a remembered dot (symbol + approximate date) that does NOT appear
  in that symbol's computed early_dots list (Track A §2.6 fired-date tables), or a second
  grey/muted anticipation marker being found in the Terminal chart layer that the census
  missed. Runnable check: the fired-date tables at
  research/live_entry_radar/TRACK_A_GREY_DOT_FORENSICS.md:204-208, recomputable via
  `git show origin/master:signal_layer/confluence_v2.py` (staged with confluence.py to a
  temp dir; run early_dots(compute_signals(close), close) over data/stocks/<SYM>.parquet);
  glyph census receipt terminal/components/ChartPanel.tsx@origin/master:3845-3855.
so_what: >
  Live Entry Radar's champion detector G0 is this exact implementation — spec locked in
  research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md §3.1, parity via the versioned
  mastermind.indicator/v1 artifact pinned on (source_hash, SIGNAL_ERA). Sessions must
  read the spec from origin/master, never the charting-app working checkout (a month
  stale, still carrying the pre-#392 leaking 2D→3D map), and must treat event `ts` (3D
  bar OPEN date) as display-only — the decision date is `known_ts`, up to 2 sessions
  later. The identity's operator ratification (gate G0-VIS) blocks only PR-2's parity
  freeze.
kind: data
verified_at: 2026-08-13
verified_by: >
  Track A census (research/live_entry_radar/TRACK_A_GREY_DOT_FORENSICS.md): direct reads
  of git show origin/master:signal_layer/confluence_v2.py + confluence.py +
  terminal/components/ChartPanel.tsx + contracts.py; fired-date computation by staging
  origin/master signal_layer into a temp dir and running compute_signals()/early_dots()
  over the shared data/stocks parquets (NVDA n=135, NFLX n=132, TSLA n=80 all-history).
scope: [macro, terminal]
confidence: verified
---

## Detail

**Operator ratification, 2026-08-13:** the operator confirmed the identification for the
raw grey anticipation-dot family (CEO amendment, contract §18 A1) — gate G0-VIS closed.
The same amendment rules that the grey dot is one of several distinct Terminal entry-event
families (candidate experts), all preserved with full provenance; it is not the universal
incumbent.

The 2026-08-11 Terminal commit 935389d4 (PR #392) introduced the washout-context
promotion (amber EARLY + bottom-watch lane) and the PIT `known_ts` join that fixed the
2B-left-edge-label leak. The grey render path itself is unchanged since the 9ef273b4 VPS
snapshot. The "~4.6d lead" in the docstring is an unsourced paraphrase — the published
figure is +4.89d matched-pair mean at 49.9% coverage (research/signal_engine/
CONFLUENCE_TUNING.md:105), and charging every dot to the next confirmed buy yields ~12.7
sessions mean (n=190) — so no lead claim may be quoted without a declared matching rule.
Macro's research/signal_engine/confluence.py is a verified silent fork of the pre-PIT
oracle (byte-identical oscillator math, zero known_ts) and must never seed a
reimplementation.
