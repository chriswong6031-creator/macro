# Mag-7 Field Guide — cohort behavior, episodes, and fragmentation

**Status:** FIELD GUIDE (M7C-R9 deliverable). Understanding phase — no backtest ruler, no
signal claims, no verdicts. Descriptive arithmetic only.
**Produced:** 2026-07-11. **As-of:** baskets/ohlcv 2026-07-08; yahoo stores 2026-07-08.
**Parent program:** `research/MAG7_COMMAND_MASTERPLAN_BY_FABLE.md` (PR #2273, ruling M7C-R9).
**Cross-references:**
- `research/RATIO_LENS_MASTERPLAN_BY_FABLE.md` — pairwise ratio states between these
  baskets (mag7/ai_semiconductors, memory/ailogic, software/hardware). Read that for the
  ratio-series machinery; this guide describes the underlying price behavior those ratios
  reflect.
- `research/LEADER_RADAR_MASTERPLAN_BY_FABLE.md` — per-name leader lifecycle state machine
  (SUPPRESSED → QUIET_ACCUMULATION → CATALYST_WINDOW → BREAKAWAY → LEADERSHIP → CROWDED).
  That program owns the per-name stage classification; this field guide describes behavioral
  archetypes across episodes for use as field-guide narrative context.
- The haven audition report covers AAPL's shelter/exit-trap pattern and META's asymmetry
  in more depth than this guide repeats.

---

## COMPOSITION HONESTY

"Mag-7" as a named investment cohort emerged in 2023. The seven names — Apple (AAPL),
Microsoft (MSFT), NVIDIA (NVDA), Amazon (AMZN), Alphabet (GOOGL), Meta (META), Tesla
(TSLA) — existed as individual companies before that; they are back-calculated here as a
composite for pattern study only. Episodes labeled with * are **retrospective composites**:
the same seven names existed, the arithmetic is honest, but calling it a "Mag-7 episode"
before the cohort was named imposes today's frame on the past.

This matters most for interpretation. In 2016-2017, the NVDA-leads pattern reflects NVDA's
transformation from a GPU gaming company into an AI/compute supplier; market participants at
the time were not watching a "Mag-7 cohort" — they were watching NVDA and, separately,
FAANG. The post-2023 episodes (17 total) are the operationally relevant set.

---

## CAP-WEIGHT BASIS

The census composite uses **fixed representative weights** approximating 2024-Q4 market-cap
proportions (documented in `scripts/_mag7_field_guide_census.py`):

| Name  | Weight | Rationale |
|-------|--------|-----------|
| AAPL  | 24.0%  | Largest by mktcap, end-2024 |
| NVDA  | 21.5%  | Ascended to #2 through 2024 surge |
| MSFT  | 19.5%  | Stable #3 across the period |
| AMZN  | 12.0%  | AWS re-acceleration era |
| GOOGL | 10.5%  | Search/Gemini |
| META  | 8.5%   | Efficiency-era recovery |
| TSLA  | 4.0%   | Auto-cyclicality; lowest among the 7 |

The live engine composite (M7C-R2) uses daily Polygon mktcap references. These fixed weights
are a convenience approximation for the field guide; they underweight NVDA's pre-2024
position and overweight it in the retrospective pre-2023 periods.

---

## SECTION 1 — EPISODE TABLE

### Method

CW composite built on 2015-01-02 → 2026-07-08 (2,894 trading sessions, all 7 members).
Local troughs: positions where the composite is the rolling 20-session minimum, with at
least 5 sessions between consecutive troughs. Episodes: from each trough, look forward up
to 30 sessions for a peak; qualify if (peak − trough) / trough ≥ +8%.

**Overlap warning:** many trough dates are within 5 sessions of each other (the minimum gap
is only 5 sessions by design, to catch genuine re-tests). Many episode pairs share the same
peak date — this is expected, not a data error. In a sustained rally, multiple trough dates
(a first dip, then a second shakeout) each satisfy the +8%/30-session criterion versus the
same eventual peak. Do not count overlapping-endpoint episodes as independent samples. The
honest independent episode count is smaller than 61; see the 17 post-2023 episodes as the
more reliable (and still small) sample.

**Breadth metric:** number of the 7 members above their 50-day simple moving average at
episode start, mid-run (~15 sessions), and at peak.

**Resolution:** the 20-session post-peak behavior — `rolled_over` (CW fell ≥ 4% from peak
within 20 sessions), `broadened` (CW continued ≥ +3% in next 20), `chopped` (CW ±3%),
`data_end` (episode too close to store end for a full 20-session window).

**Concurrent:** SPY, SMH (semiconductors), MEM-EW (MU/WDC/STX equal-weight; SNDK excluded
as live only from 2025-02), and IGV (software proxy) returns over the SAME trough→peak
window.

### Full episode roster (61 qualifying episodes, 2015-01-02 → 2026-07-08)

```
 #       Trough         Peak  Dur   Gain  Brd(S/M/P) Leaders(top-2)  Laggards(bot-2)  SPY   SMH   MEM   IGV  Res-20
 1*   2015-03-25   2015-04-27   22  +8.8%  4/5/6  TSLA+AMZN        GOOGL+META       +2.4  +4.5  +7.8  +5.6  chopped
 2*   2015-04-01   2015-04-27   17  +9.6%  3/5/6  TSLA+AMZN        GOOGL+META       +2.5  +3.2  +8.8  +4.7  chopped
 3*   2015-06-29   2015-08-10   29  +9.9%  3/6/5  GOOGL+AMZN       AAPL+TSLA        +2.5  -2.8  +3.5  +4.1  rolled_over
 4*   2015-07-08   2015-08-17   28 +11.3%  2/4/5  GOOGL+AMZN       TSLA+AAPL        +3.0  -2.9  +6.5  +5.4  rolled_over
 5*   2015-08-21   2015-10-05   30  +9.5%  3/4/5  NVDA+AMZN        AAPL+GOOGL       +0.8  +9.5  +4.1  +2.8  broadened
 6*   2016-02-05   2016-03-21   30 +15.2%  1/2/6  TSLA+NVDA        MSFT+META        +9.5 +14.7  +9.7 +14.7  broadened
 7*   2016-04-26   2016-05-31   24 +11.7%  4/3/5  NVDA+AMZN        AAPL+TSLA        +0.4  +4.4  +0.5  +3.9  rolled_over
 8*   2016-06-24   2016-08-08   30 +19.0%  2/7/7  NVDA+GOOGL       META+AMZN        +7.3 +16.4 +13.3  +8.1  broadened
 9*   2016-09-09   2016-10-21   30  +9.7%  5/6/6  NVDA+AAPL        META+TSLA        +0.8  +6.5  +0.5  +1.6  broadened
10*   2016-11-03   2016-12-16   30 +20.9%  2/2/5  NVDA+TSLA        META+AMZN        +8.4  +7.7 +20.7  +0.3  broadened
11*   2016-11-10   2016-12-23   30 +27.9%  2/2/5  NVDA+TSLA        AMZN+META        +4.7 +10.2 +23.7  -0.3  chopped
12*   2017-04-10   2017-05-22   29 +22.7%  5/7/7  NVDA+GOOGL       MSFT+TSLA        +1.8  +7.8  -1.2  +7.8  broadened
13*   2017-06-27   2017-08-07   28 +11.8%  5/6/5  NVDA+META        GOOGL+TSLA       +2.7  +5.2 -11.6  +2.6  rolled_over
14*   2017-08-11   2017-09-18   25 +11.7%  4/5/5  NVDA+TSLA        AMZN+GOOGL       +2.8  +8.4 +16.1  +5.8  rolled_over
15*   2017-11-29   2018-01-12   30 +11.0%  4/6/6  NVDA+AMZN        AAPL+META        +6.3  +4.2  +7.3  +7.2  chopped
16*   2018-02-05   2018-03-12   24 +14.8%  4/6/7  NVDA+AAPL        TSLA+META        +5.5 +15.1 +35.9 +13.0  rolled_over
17*   2018-04-02   2018-05-10   28 +16.3%  0/3/7  TSLA+META        MSFT+GOOGL       +5.7  +4.7  -0.8 +11.7  rolled_over
18*   2018-06-25   2018-08-07   30  +8.6%  5/7/6  TSLA+AAPL        NVDA+META        +5.4  +6.0  -3.4  +5.2  broadened
19*   2018-10-29   2018-11-01    3 +11.5%  1/1/2  NVDA+AMZN        TSLA+MSFT        +3.7 +10.5 +14.7  +5.2  rolled_over
20*   2018-12-24   2019-01-25   21 +20.4%  0/3/5  NVDA+AMZN        AAPL+TSLA       +13.4 +19.7 +28.3 +18.8  rolled_over
21*   2019-05-28   2019-07-10   30 +10.6%  2/4/7  TSLA+AAPL        MSFT+GOOGL       +7.1 +13.5 +25.7  +7.4  rolled_over
22*   2019-08-05   2019-09-12   27 +13.6%  2/4/5  NVDA+AAPL        MSFT+META        +6.2 +12.6 +22.6  +3.0  rolled_over
23*   2020-02-27   2020-03-04    4  +9.9%  2/4/4  NVDA+AAPL        AMZN+META        +5.2  +7.3  +8.1  +4.2  rolled_over
24*   2020-03-09   2020-04-16   27 +18.8%  0/2/5  AMZN+TSLA        META+GOOGL       +2.4  +8.2  +1.3  +9.3  rolled_over
25*   2020-03-16   2020-04-27   29 +40.2%  0/0/7  TSLA+NVDA        GOOGL+AAPL      +20.4 +31.0 +28.1 +27.8  broadened
26*   2020-09-23   2020-10-12   13 +15.8%  2/6/7  NVDA+TSLA        META+MSFT        +9.2 +14.5  +3.0 +10.2  rolled_over
27*   2020-10-28   2020-11-06    7 +12.1%  0/1/7  GOOGL+NVDA       TSLA+AMZN        +7.2 +13.4  +9.8  +7.4  rolled_over
28*   2021-02-25   2021-04-09   30  +9.0%  2/2/6  META+GOOGL       NVDA+TSLA        +8.0  +8.5  +9.0  +2.7  chopped
29*   2021-03-04   2021-04-15   29 +23.1%  1/3/7  NVDA+META        GOOGL+AAPL      +10.8 +14.3  +9.3 +11.8  rolled_over
30*   2021-05-10   2021-06-22   30 +21.2%  5/3/6  NVDA+META        AAPL+TSLA        +1.6  +7.0  -3.9 +13.7  broadened
31*   2021-08-18   2021-09-03   12 +14.4%  5/6/7  NVDA+AMZN        AAPL+MSFT        +3.2  +8.0  +2.9  +6.7  rolled_over
32*   2021-09-28   2021-11-08   29 +35.7%  1/5/6  TSLA+NVDA        AMZN+META        +8.1 +15.9  +6.2 +11.2  broadened
33*   2021-12-20   2021-12-27    4 +10.2%  1/4/6  TSLA+NVDA        GOOGL+AMZN       +4.9  +8.6 +12.3  +5.4  rolled_over
34*   2022-01-25   2022-02-09   11 +15.3%  0/1/2  NVDA+AMZN        TSLA+META        +5.3  +9.0 +11.3  +9.5  rolled_over
35*   2022-02-23   2022-03-29   24 +24.2%  0/0/6  TSLA+NVDA        AAPL+GOOGL       +9.7 +10.0  -6.9 +11.9  rolled_over
36*   2022-03-07   2022-03-29   16 +28.5%  0/2/6  TSLA+NVDA        GOOGL+AAPL      +10.4 +16.9  +3.1 +12.8  rolled_over
37*   2022-03-14   2022-03-29   11 +29.4%  0/5/6  TSLA+NVDA        MSFT+GOOGL      +11.0 +18.8 +14.7 +17.2  rolled_over
38*   2022-05-24   2022-06-02    6 +17.6%  0/0/0  TSLA+NVDA        AAPL+MSFT        +6.0 +11.2 +10.2 +12.2  rolled_over
39*   2022-06-13   2022-07-21   26 +15.6%  0/0/7  TSLA+AMZN        MSFT+GOOGL       +6.8  +9.8  +7.7 +12.5  rolled_over
40*   2022-06-30   2022-08-04   24 +24.5%  0/5/6  TSLA+AMZN        GOOGL+META       +9.8 +20.4 +14.8 +13.3  rolled_over
41*   2022-09-29   2022-11-10   30 +12.3%  0/0/2  NVDA+AAPL        META+TSLA        +8.8 +13.8 +12.7  +4.4  broadened
42*   2022-10-07   2022-11-15   27 +19.8%  0/0/4  NVDA+AAPL        TSLA+AMZN        +9.8 +19.6 +13.0  +6.9  rolled_over
43*   2022-10-14   2022-11-15   22 +26.8%  0/2/4  NVDA+AAPL        AMZN+META       +11.4 +30.3 +15.5 +13.4  rolled_over
44*   2022-12-22   2023-02-07   30 +36.3%  2/4/7  META+TSLA        AAPL+MSFT        +9.1 +23.9 +33.0 +14.9  rolled_over
45    2023-04-25   2023-05-30   24 +42.3%  6/6/7  NVDA+META        AMZN+AAPL        +3.5 +23.8 +18.5 +12.4  rolled_over
46    2023-08-09   2023-08-31   16 +13.0%  3/3/5  NVDA+TSLA        AMZN+META        +1.0  +3.9  +5.3  +6.1  rolled_over
47    2023-10-20   2023-11-20   21 +19.5%  3/5/6  NVDA+AMZN        META+GOOGL       +7.9 +16.0 +15.8 +12.1  rolled_over
48    2024-04-17   2024-05-29   29 +32.1%  4/5/5  NVDA+AAPL        AMZN+META        +5.1 +15.7 +12.5  +2.6  rolled_over
49    2024-07-24   2024-08-19   18 +12.2%  2/1/4  META+NVDA        MSFT+GOOGL       +3.4  +4.3  -3.6  +4.4  rolled_over
50    2024-08-05   2024-08-19   10 +26.6%  0/2/4  NVDA+TSLA        MSFT+GOOGL       +8.2 +17.8 +16.8 +11.0  rolled_over
51    2024-09-06   2024-10-14   26 +30.6%  0/6/6  NVDA+META        MSFT+TSLA        +8.5 +21.5 +19.5 +12.0  rolled_over
52    2024-12-16   2025-01-06   13 +10.9%  6/7/6  NVDA+META        MSFT+TSLA        -1.6  +3.2  -6.8  -4.9  rolled_over
53    2025-01-27   2025-02-20   17 +15.5%  5/3/3  NVDA+AAPL        AMZN+TSLA        +1.8  +9.3  +7.7  +1.8  rolled_over
54    2025-02-03   2025-02-20   12 +17.1%  3/2/3  NVDA+AAPL        TSLA+GOOGL       +2.1  +8.0 +12.5  +1.5  rolled_over
55    2025-03-10   2025-03-24   10 +12.1%  0/0/0  TSLA+NVDA        GOOGL+AAPL       +2.7  +7.5  +8.4  +7.6  rolled_over
56    2025-04-03   2025-05-14   28 +30.7%  0/0/7  NVDA+TSLA        GOOGL+AAPL       +9.5 +26.8 +36.4 +21.0  broadened
57    2025-09-02   2025-10-09   27 +12.3%  4/7/6  TSLA+GOOGL       AMZN+META        +5.1 +20.5 +46.8  +7.8  rolled_over
58    2025-12-12   2026-01-28   30  +8.3%  3/4/5  NVDA+GOOGL       TSLA+AAPL        +2.3 +18.0 +67.6 -10.1  rolled_over
59    2026-02-04   2026-02-25   14 +10.5%  3/0/2  NVDA+TSLA        GOOGL+AMZN       +1.0 +11.6  +7.9  -3.6  rolled_over
60    2026-03-20   2026-04-27   25 +24.2%  0/2/6  AMZN+NVDA        AAPL+TSLA       +10.3 +31.6 +33.0  +2.9  rolled_over
61    2026-03-27   2026-05-11   30 +30.3%  0/7/6  GOOGL+AMZN       MSFT+META       +16.6 +54.0+116.0 +17.9  rolled_over
```

`*` = pre-2023 retrospective composite.
`Brd(S/M/P)` = members above 50dma at start/mid/peak.
MEM = MU/WDC/STX equal-weight. IGV = software proxy ETF.
Return columns are percentage points (e.g., +3.5 = +3.5%).

### Summary counts

- 61 qualifying episodes total (44 retrospective / 17 post-2023 named-cohort era)
- Broad at peak (≥5/7 above 50dma): 48 episodes
- Narrow at peak (<5/7): 13 episodes
- Post-peak resolution: rolled_over=44, broadened=12, chopped=5
- Leader frequency (top-2 by episode CW contribution, across all 61): NVDA 47, TSLA 27,
  AMZN 17, AAPL 12, META 10, GOOGL 9
  (NVDA dominance is partly a weight artifact — high weight × high return; MSFT is absent
  from the top-2 because it is a steady accumulator, rarely the explosive leg)

---

## SECTION 2 — PER-NAME BEHAVIOR

### 2.1 AAPL — Apple (shelter / late-cycle quality)

**Role:** AAPL rarely leads Mag-7 runs (top-2 leader in 12/61 episodes). Its contribution
pattern is characteristically different from NVDA or TSLA: it participates steadily but
does not spike. When it leads, the context is often a quality-rotation or defensive move
within the run.

**Shelter evidence (see also the haven audition report):** AAPL has the smallest maximum
drawdown among the 7 at −38.5%, and the highest percentage of days above its 200dma
(71.6%). During the 2022 bear year, AAPL fell −28.2% vs. the cohort composite at −48.3%,
preserving relative value. In the Apr-2025 tariff shock (Ep 56 trough), AAPL showed one of
its two best single-day gains: +15.33% on 2025-04-09 (along with TSLA at +22.69%), as
markets reacted to tariff pause news.

**Exit-trap (per haven audition report):** AAPL has been the weakest or second-weakest
member in several 2025-2026 episodes (Ep 53/54/55/58/59 show AAPL negative or lagging).
The Dec-Jan 2024-25 shelter premium partially reversed in early 2025. The haven audition
report documents the exit-trap context in detail.

**Key dates:** Worst single day: −12.86% on 2020-03-16 (COVID); Best single day: +15.33%
on 2025-04-09. Days with drawdown >30% from 52-week high: 33 (the least of the 7).

### 2.2 MSFT — Microsoft (steady compounding / enterprise laggard in spike runs)

**Role:** MSFT leads zero top-2 contribution slots across all 61 episodes — it is the
"missing from the headline" name. This is not a pathology; MSFT compounds steadily. In the
2022 bear year, MSFT fell only −27.7% (similar to AAPL), limiting damage. In 2023, MSFT
returned +58.3% — strong in absolute terms, but in a year where NVDA was +246% and META was
+184%, it was systematically the laggard.

**Implication for breadth reading:** When MSFT is in the top-2, the run has typically
exhausted NVDA/TSLA leadership and is broadening (a late-stage breadth catch-up). Example:
Ep 29 (Mar-2021) shows MSFT+AAPL lagging while NVDA+META led; Ep 45 (Apr-2023) shows MSFT
+20.5% alongside NVDA +52.9% — MSFT participated but was not the driver.

**Key dates:** Worst: −14.74% on 2020-03-16. Best: +14.22% on 2020-03-13 (COVID bounce).
Days deep drawdown (>30% from 52-week high): 48.

### 2.3 NVDA — NVIDIA (the acceleration amplifier / volatile decoupler)

**Role:** The dominant leader. NVDA appears in top-2 in 47/61 episodes. This reflects its
extreme volatility — it amplifies whatever direction the cohort is moving, and adds excess
return even when the rest of the cohort is muted.

**Decoupling pattern 1 — solo melt-up:** In late 2016 (Eps 10-11), NVDA gained +48-62%
while the rest of the seven barely moved (MSFT/META/AMZN lagged at 0–9%). This was NVDA's
first GPU-for-AI discovery moment. Memory (MEM-EW) ran +20-24% in Ep 10-11 as the AI
capex narrative formed.

**Decoupling pattern 2 — 2023 AI breakout:** Ep 45 (Apr-May 2023): NVDA +52.9% vs AMZN
+18.6%, AAPL +8.4%. SMH +23.8%. The entire run was NVDA-concentrated — the "ChatGPT
demand" moment. Subsequent episodes (46, 47, 48) show NVDA continuing to lead but with the
gap narrowing as the rest caught up.

**Decoupling pattern 3 — 2026 generals/memory split:** While the memory basket ran +199.6%
YTD through 2026-07-08, NVDA was itself up only modestly YTD (the stock was working through
the post-highs consolidation). The role reversal — memory leading, NVDA flat — lasted until
the late-June-2026 episode (Ep 61 GOOGL+AMZN led, NVDA a solid participant but not the
headline). See the live exhibit in §4.

**Volatility profile:** Max drawdown −66.3%, 463 days with drawdown >30% from 52-week high
(second-highest among the 7 after TSLA's 716). Best day: +29.81% on 2016-11-11. Worst day:
−18.76% on 2018-11-16. In the 2022 bear year: −51.4%.

### 2.4 AMZN — Amazon (growth-scare proxy / irregular leader)

**Role:** AMZN leads in 17/61 episodes, often in different market contexts from NVDA. In
2015 (Eps 3-4), AMZN's AWS growth story drove it to lead a run where NVDA was just beginning
its GPU arc. In 2020 COVID (Ep 24-25), AMZN led as the "pandemic beneficiary."

**Interesting pattern:** AMZN is frequently a laggard in NVDA-dominated AI-hardware runs
(Eps 45, 48, 53, 54). When AMZN leads, it tends to be in "macro relief" episodes where
risk-off pressure lifts and broad growth names catch up. In Ep 61 (Mar-May 2026, the
tariff-reversal run), AMZN +34.9% was the second-highest contributor. The pattern: AMZN
leads when the narrative is "growth is safe again" (not "AI hardware is exploding").

**Key dates:** Worst: −14.05% on 2022-04-29 (AWS guide-down quarter). Best: +14.13% on
2015-04-24. Max drawdown: −56.1%. Days deep drawdown: 223.

### 2.5 GOOGL — Alphabet (lone-alpha moments / search cash engine)

**Role:** GOOGL appears in top-2 in 9/61 episodes. Two memorable contexts:

1. **2015 earnings breakout (Eps 3-4):** GOOGL +22-28% — its most decisive single-episode
   leadership, driven by the first Ruth Porat restructuring signals and revenue beat.
2. **2026 GOOGL re-rate (Ep 61):** GOOGL +41.7% was the top performer in the
   Mar-May 2026 tariff-recovery run — an AMZN+GOOGL-led episode where MSFT/META lagged.
   This is the "lone alpha" rerate pattern referenced in the Leader Radar masterplan.

GOOGL is the name most often in the laggard slot (bottom-2) when NVDA or TSLA dominate.
In 2024 (full year), GOOGL returned +37.5% — respectable, but well below NVDA +178.9%.

**Key dates:** Best single day: +16.26% on 2015-07-17 (earnings). Worst: −11.63% on
2020-03-16. Max drawdown: −44.3%. Days deep drawdown: 123.

### 2.6 META — Meta Platforms (asymmetric recovery / ad-funded compute)

**Role:** META appears in top-2 in 10/61 episodes. Its most notable contribution is the
2023 "efficiency era" recovery: Ep 44 (Dec 2022 - Feb 2023) META +63.6%, TSLA +57% vs
AAPL +17%, MSFT +12%. This was META's "Year of Efficiency" phase — a 100%-drawdown-recovery
style episode. Before that, META had fallen −76.7% from its peak (the deepest drawdown
of the 7 aside from TSLA's −73.6%).

**Asymmetry pattern:** META's worst single day: −26.39% on 2022-02-03 (metaverse-pivot
earnings). Its best day: +23.28% on 2023-02-02 (efficiency-pivot earnings). These two
prints are mirror images of the same business. The haven audition report examines META's
status as an asymmetric haven candidate — the asymmetry works in both directions.

**Current pattern:** In Eps 49 and 51 (mid-to-late 2024), META led (13-18% in a 3-4 week
run) as the AI-monetization narrative hit. In the 2026 episodes (59, 60), META is
frequently in the laggard or middling slot — a contrast to its 2023-24 outperformance.

**Key dates:** Max drawdown: −76.7%. Days deep drawdown: 338. Best year: 2023 (+183.8%).

### 2.7 TSLA — Tesla (highest volatility / regime amplifier)

**Role:** TSLA appears in top-2 in 27/61 episodes, second only to NVDA. But TSLA's
leadership is negatively correlated with AI-narrative runs — it tends to lead in
momentum-regime (broad risk-on) and macro-relief episodes rather than AI-specific ones.

**Bear-beta:** When the cohort rolls over, TSLA leads the downside. Days with drawdown
>30%: 716 — far more than any other member. Max drawdown: −73.6%. Worst single day:
−21.06% on 2020-09-08 (S&P rejection, post-split). Best: +22.69% on 2025-04-09 (tariff
pause).

**Macro amplifier:** TSLA dominates the breadth-start=0 episodes — the runs that start
from maximum technical damage (all 7 below 50dma). In the 2022 bear rebounds (Eps 35-40),
TSLA +24-44% drove CW composites higher even as the rest of the cohort lagged. This is a
mean-reversion artifact: TSLA's larger drawdowns create larger bounces off the lows.

**Divergence from AI narrative:** In the NVDA-dominated AI episodes (Ep 45, 2023; Ep 51,
2024), TSLA is often in the laggard slot (4th-7th in contribution). The AI-hardware and
EV-narratives are decoupled.

**Key dates:** Max drawdown: −73.6%. Days deep drawdown: 716. Best year: 2023 (+129.9%).
2024: +62.6%. 2025-2026 YTD fluctuates with Optimus/robotaxi/tariff narratives.

---

## SECTION 3 — PLAYBOOK

### 3.1 What a Mag-7 run looks like at day 10-15

By day 10-15 of a qualifying run (from the census of all 61 episodes):

**Breadth shape at mid-episode (session ~15):**
- 37 of 61 episodes had 4+ of 7 members above 50dma at the midpoint (BrdMd ≥ 4)
- 11 episodes had 0-1 above 50dma at the midpoint, yet still hit +8% by peak — these are
  the pure-reversion "snapback from deep damage" runs (2022 bear era dominates here)
- The transition from BrdSt 0-1 → BrdMd 4-5 → BrdPk 6-7 is the "broadening into strength"
  pattern; when it does NOT happen (BrdMd stays below BrdSt), the run tends to roll over
  faster post-peak

**Who is leading at day 10:**
- In AI-narrative runs (post-2023): NVDA is almost always in the top-2 by session 10
- In macro-relief runs: leadership is more distributed (AMZN, GOOGL, TSLA rotate)
- If AAPL is in the top-2 by day 10, the run is likely a quality/defensive catch-up, not
  an AI-hardware acceleration — these runs tend to be smaller in magnitude

**SPY and SMH behavior at day 10:**
- SPY is almost always positive at the midpoint (the Mag-7 run rarely happens while the
  broader market is actively selling; it requires at least a pause in SPY selling)
- SMH is the more diagnostic read: in AI-hardware runs, SMH leads or keeps pace with
  Mag-7 CW; in "generals decouple from semis" episodes (see §3.3), SMH lags or is negative

### 3.2 Narrow vs broad runs — how each historically resolved

Of the 61 qualifying episodes:

**Broad runs (BrdPk ≥ 5/7, 48 episodes):**
- Rolled over: 33 (69%)
- Broadened: 11 (23%)
- Chopped: 4 (8%)
- Interpretation: even broad runs roll over most of the time — "broad" at peak is necessary
  but not sufficient for continuation. The difference between the 11 that broadened and the
  33 that rolled over is NOT captured by the breadth metric alone.

**Narrow runs (BrdPk < 5/7, 13 episodes):**
- Rolled over: 11 (85%)
- Broadened: 1 (8%)
- Chopped: 1 (8%)
- Interpretation: narrow-peak runs are more reliably terminal on the 20-session horizon.
  When only 2-3 names are above 50dma at the peak, the run is concentrated and fragile.

**Key honest null:** the rolled_over dominance (44/61 = 72%) is partly a mathematical
artifact of the episode extraction method — a sustained bull trend generates many overlapping
episodes, each of which "rolls over" before the next episode begins from a new trough. This
is not evidence that Mag-7 runs are inherently short-lived; it is an artifact of the 30-
session window and the trough-finding algorithm. Do not use the 72% figure to argue that
post-peak selling is "the pattern."

### 3.3 Generals-vs-semis decoupling episodes

The ratio between Mag-7 CW and SMH (semiconductors) has historically been the most
informative of the three concurrent metrics (SPY/SMH/MEM/IGV):

**When Mag-7 leads and SMH lags (generals decouple from semis):**

The best historical cases where SMH return was negative during a Mag-7 run:
- Ep 3 (Jun-Aug 2015): Mag-7 +9.9%, SMH **−2.8%** — GOOGL/AMZN-led, semis lagged
- Ep 4 (Jul-Aug 2015): Mag-7 +11.3%, SMH **−2.9%**
- Ep 7 (Apr-May 2016): Mag-7 +11.7%, SMH +4.4% (below-pace)

The **2026 live exhibit** is the most striking recent instance:
- Jun 26 → Jul 08 window: MAG7_CW +6.1% (in-store); operator-confirmed +~9% by Jul-10
- MEM-EW (MU/WDC/STX): **−11.4%** in the same window (Jun 26 → Jul 08)
- Context: memory basket had run +199.6% YTD 2026 before this reversal; the generals
  (AAPL +10.4%, META +9.6%, GOOGL +7.3%) rotated into relative leadership while the
  prior leaders (DRAM names) corrected sharply.
- This is the "handoff from extended melt-up leg to basing recovery" pattern described in
  the Leader Radar masterplan's §1 (memory_storage as extended donor, mag7 as recovering
  recipient).

**When SMH leads and Mag-7 follows:**
- Ep 8 (Jun-Aug 2016): Mag-7 +19%, SMH +16.4% — both ran, SMH competitive
- Ep 43 (Oct-Nov 2022): Mag-7 +26.8%, SMH +30.3% — SMH led into the 2022 lows
- Ep 56 (Apr-May 2025): Mag-7 +30.7%, SMH +26.8% — post-tariff broadening

**Pattern:** when SMH is simultaneously outrunning Mag-7 CW, it typically signals an AI-
hardware capex narrative is driving the whole complex. When Mag-7 runs while SMH is flat or
negative, it signals a "stock-picker quality" or "earnings-multiple" run — the kind driven
by individual name re-rates (GOOGL 2026, META 2023, AAPL quality bid).

**The software leg (IGV):**
- IGV tracked Mag-7 closely in 2015-2020 (both driven by the same FANG complex)
- Post-2022, IGV diverged: in 2025-26 episodes with strong memory (MEM-EW), IGV was often
  negative or flat (Ep 58: IGV −10.1%, MEM +67.6%; Ep 52: IGV −4.9%, MEM −6.8%)
- In the 2026 YTD through the store end, IGV was negative through January 2026 even as the
  memory melt-up ran. This software/semis decoupling is the other axis of the Ratio Lens
  program's decomposition tree.

### 3.4 How runs start, broaden, and end

**Start pattern (from the episode table):**
- Most runs start from low breadth: in 28/61 episodes, breadth at start (BrdSt) is 0-2
  of 7 above their 50dma. The run begins with the cohort technically damaged.
- The episodes with BrdSt 5-6 are usually continuations in a bull trend (e.g., Ep 9, 12,
  18, 28, 30) — pullbacks in ongoing uptrends.
- Name leadership at the start of a run does not reliably predict who leads mid-run. The
  roster shifts; NVDA often joins or accelerates mid-run even if it wasn't the first mover.

**Broadening signal:**
- Breadth moving from BrdSt ≤ 2 → BrdMid 5-6 → BrdPk 6-7 is the "compression then
  release" pattern. This is most visible in the 2020 COVID bounce (Ep 25: BrdSt 0 → BrdMd
  0 → BrdPk 7 — a V-recovery where everything moved together from extreme damage).
- The M7C-R3 trend_state `running_broad` (≥5/7 above 50dma, up defined as CW_r10 ≥ +2%
  AND CW > 20dma) corresponds to the BrdPk ≥ 5 episodes in this guide.

**Ending conditions from the census:**
- The most common end state is that the run peaks and then SPY/SMH both stabilize or
  continue, while Mag-7 CW sees a 20-session give-back (rolled_over)
- The "broadened" endings (12/61) cluster in two eras: 2016 (NVDA melt-up kept going) and
  2020-2021 (COVID stimulus kept the bull alive)
- The 2022 bear runs ALL rolled over — every bounce in 2022 gave back gains within 20
  sessions, consistent with a structural bear market

---

## SECTION 4 — LIVE EXHIBIT: JUN-JUL 2026 ROTATION

This is the closing live exhibit, directly derived from in-store data and the
MAG7_COMMAND_MASTERPLAN §0 incident of record.

### What the stores show (baskets/ohlcv, 2026-07-08 store end)

**Memory basket (MU/WDC/STX) 2026 YTD (through 2026-07-08):** +199.6%
This represents the memory/HBM melt-up driven by HBM demand expectations — MU was the
lead name, WDC and STX followed. NVDA was flat to modest YTD while memory ran.

**The reversal window (Jun 26 → store end Jul 08, in-store):**
- AAPL: +10.4%
- META: +9.6%
- GOOGL: +7.3%
- NVDA: +6.0%
- AMZN: +4.7%
- TSLA: +3.8%
- MSFT: +2.8%
- MAG7_CW (in-store): +6.1%
- MEM_EW (MU/WDC/STX): **−11.4%**

**Operator-confirmed extension (Jul 08 → Jul 10, per MAG7_COMMAND §0):**
- MAGS (Roundhill traded ETF): $61.60 → ~$67 (+~9%)
- SMH: −3.2% over the start window
- The run extended after the store end; in-store data captures only the first 8 sessions.

### What this episode demonstrates

This is a textbook "generals decouple from semis" episode:
1. Memory ran +199% YTD while the generals (AAPL, META, GOOGL) lagged
2. Memory then reversed sharply (−11.6% in 8 sessions)
3. The generals simultaneously ran their best 8-10-session stretch
4. SMH was negative while Mag-7 was up — confirming the rotation was within-tech, not a
   broad semiconductor bull

The Ratio Lens program (see `research/RATIO_LENS_MASTERPLAN_BY_FABLE.md`) will track the
memory_storage / ai_semiconductors pair and the mag7 / ai_semiconductors pair as formal
ratio objects. This field guide provides the episode context for those ratio series.

---

## SECTION 5 — LIMITS AND HONEST NULLS

**Small N:** 17 post-2023 (named-cohort) episodes is a small sample. Any "pattern" from this
section is a descriptive observation, not a statistical finding. The pre-2023 (retrospective)
episodes add N but require composition-honesty discounting.

**Overlap artifact:** the trough-finder algorithm produces overlapping episodes (multiple
troughs leading to the same peak). This inflates N and creates correlated "independent"
events. The honest independent episode count is lower. When using this table, focus on the
unique peak dates — not the episode count.

**Cap-weight approximation:** Fixed 2024-Q4 weights misrepresent the pre-2024 composite.
NVDA had a ~3% market cap weight in 2016; the 21.5% fixed weight massively amplifies its
contribution to retrospective CW returns. The dominance of NVDA in the leader frequency
table (47/61 episodes) is partly a result of this; the retrospective composite would have
a materially different pattern under historically correct weights.

**Composition drift:** TSLA was not in many "Mag-7" framings pre-2022; NVDA was not in
most "mega-cap software" framings pre-2023. The seven names are fixed here but their roles
in actual market narratives shifted over time.

**Memory basket exclusions:** SNDK excluded (live only since 2025-02; WDC/SNDK were the
same enterprise until Feb 2025 spin). NTAP excluded (network-attached storage, different
from DRAM/NAND). The MEM_EW therefore uses only MU/WDC/STX (3 names), biasing toward
commodity DRAM (MU) and enterprise disk (WDC/STX) over hyperscaler storage.

**Post-peak data gaps:** episodes 60-61 show `n/a` for p60 post-peak returns — the store
ends before 60 sessions elapse from the peak.

**No verdicts stated here:** Per M7C-R9 (understanding before backtest) and the house
epistemics law, this field guide contains no signal claims, no win-rate claims, and no
predictive assertions. The word "pattern" throughout means "historical observation" only.
Rulers for any future study are derived from this playbook separately, with pre-registration
and appropriate statistical controls (DT-R14 time-preserving permutations, calendar-episode
clustering).

---

## APPENDIX — Data provenance

| Store | Path | Coverage | Notes |
|-------|------|----------|-------|
| Member closes | `data/baskets/ohlcv/{AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA}.parquet` | 2014-01-02 → 2026-07-08 | Primary source for CW composite and per-name stats |
| SPY | `data/yahoo/SPY.parquet` | 1993-01-29 → 2026-07-08 | Long history; close column |
| SMH | `data/yahoo/SMH.parquet` | 2000-06-05 → 2026-07-08 | VanEck Semiconductor ETF |
| IGV | `data/yahoo/IGV.parquet` | 2001-07-17 → 2026-07-08 | iShares software ETF proxy |
| Memory EW | `data/baskets/ohlcv/{MU,WDC,STX}.parquet` | 2014-01-02 → 2026-07-08 | SNDK/NTAP excluded (see §LIMITS) |
| MAGS (reference) | `data/massive_stock_day/MAGS.parquet` | ~2021 → 2026-07-02 | Traded reference only; not used in computation (RL-R12 law) |

Census script: `scripts/_mag7_field_guide_census.py`

---

## SECTION 6 — Presidential buy-endorsement episodes (exhibit, FC-R9)

**Status:** Event catalog only. No signal claims. No win-rate claims. PS-R1 standing: no
intent prediction, no timing forecast, no LLM-emitted probabilities.

**Honest n statement (binding):** The three historical episodes below are *selected* episodes
with no false-positive denominator — nobody has counted the loud market-positive statements
that marked nothing. What is known is n≈3-4 with outcomes that vary. That is an anecdote,
not an edge. The registry (`data/statement_tape/registry.jsonl`) exists so a base rate can
ever be measured when enough episodes accumulate and a denominator can be defined.

### Historical catalog (n=3, pre-2026)

| Date | Venue | Approximate quote / context | Market context on date | 30-day outcome |
|------|-------|-----------------------------|------------------------|----------------|
| 2018-12-26 | Twitter | Multiple tweets criticizing the Fed / urging markets higher (fed_pressure + market_boost) | One day **after** the exact S&P 500 bear-market intraday low (2018-12-24). The low was already in. | SPY +7.9% over the subsequent 30 calendar days from the Dec 24 low. Statement trailed the low. |
| 2020-03-13 | White House press briefing / emergency declaration | "The market is going to be fine" (paraphrase); emergency Coronavirus declaration accompanied by rally claims | ~10% **above** the eventual price low (2020-03-23). | SPY fell approximately −10% further over the next 10 trading days before the real low. Statement was 10 days and −10% early. |
| 2025-04-09 | Truth Social | "THIS IS A GREAT TIME TO BUY!!! DJT" (verbatim, 09:37 ET) | Statement was posted at 09:37 ET; a tariff-pause announcement followed hours later the same day. SPY +9.5% on the day. | Subsequent weeks formed a durable low. Statement was coincident with both the price low and the policy catalyst. |

**Pattern read (conditions-framing, not a signal):** In 2018 the statement came one day after
the low (a near-miss in the endorser's favor, but the low was already in). In 2020 it came
10 trading sessions and ~10% before the real low (a miss). In 2025 it coincided with the
low and was followed hours later by the policy action that drove the rally. Three episodes,
three different relationships between statement and low. No consistent leading or lagging
pattern is established.

### 2026 instance (this cycle)

The 2026 Mag-7 drawdown low was **2026-06-26** (MAGS ~$61.60). Verified statement dates:

| Date | Venue | Content | Timing vs 2026-06-26 low |
|------|-------|---------|--------------------------|
| 2026-06-07 | Truth Social | "Stocks should go up, not down" (paraphrase) | **19 calendar days before** the low — statement preceded the low |
| 2026-06-26 | Public remarks | Warsh-confidence / low-rates remarks (paraphrase) | **Same day** as the low — coincident |
| 2026-07-02 | CNBC Squawk Box | "81 records… everybody's profiting" (paraphrase) | **~4 trading sessions after** the low — statement trailed |
| 2026-07-06 | Rose Garden | Anti-short-seller remarks (paraphrase) | **~7 trading sessions after** the low — statement trailed |

**2026 heuristic result:** The Jun 7 statement was 19 days early. The Jun 26 coincident
statement aligned with the low but could not be distinguished from coincidence in real time.
The Jul 2 and Jul 6 statements trailed the low. **The "buy-endorsement" heuristic as an
entry trigger was a miss for this instance** — the operator's real-time doubt ("memory was
falling off a cliff") was reasonable, and the statements that most loudly endorsed markets
came after the recovery was already underway.

### What the registry is for

The statement tape (`data/statement_tape/registry.jsonl`) is append-only. Its purpose is to
accumulate a denominator. Over time — with both the episodes above AND the statements that
marked nothing notable — it will be possible to test whether there is any systematic
relationship between loud market-positive statements and price behavior. Until that
denominator exists, the catalog above is a descriptive exhibit, not a testable hypothesis.

**No "validated" language appears here because nothing has been tested with a pre-registered
denominator.** The word "pattern" in this section means "historical observation in a small
selected sample."
