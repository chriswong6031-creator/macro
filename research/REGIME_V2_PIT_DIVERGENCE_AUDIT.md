# Regime v2 PIT spine — divergence audit

**CPI program P-D5-1 (regime_v2_pit), phase 4a.** Builder:
`scripts/build_regime_v2_pit.py` → `data/regime/regime_v2_pit.parquet` +
`data/regime/regime_v2_pit_divergence.json` (the machine artifact behind every
number below). Vintage store as-of: **2026-06-25**; frame: 1971-01-04 →
2026-07-02 (14,479 business days, 14,396 with a confirmed quad on both legs).

## Headline

**The PIT quad differs from the revised quad on 4.69% of all comparable dates —
8.78% of vintage-covered dates (1997-01-10 →), and 17.15% in the worst era
(2020+).** The raw (pre-hysteresis) quad diverges on 3.20% of dates; hysteresis
path-dependence amplifies raw divergence into longer confirmed-quad runs
(59 runs, median 7 bd, p90 27 bd, max 82 bd).

Read this as the *revision-leak tax on the quad label*: on ~1 vintage-covered
date in 11, the regime the engine's history claims for that day is not the
regime a real-time reader of initial releases would have printed.

## What was re-run, and how

The exact live pipeline (`engine.inputs.build_features` →
`engine.axes.score_axis` → `engine.regime.classify` incl. the same
hysteresis/shock-override state machine → `engine.transition` flags + state
machine — zero forked math, injected via a no-behavior-change `overrides` seam
in `build_features`), with the five revision-leaky macro legs read as-of each
date from `data/fred_vintage/vintages.parquet`:

| leg (column) | FRED sid | vintage from | fallback (latest-revised, flagged) |
|---|---|---|---|
| payrolls | PAYEMS | 1997-01-10 | 1971 → 1997-01 (6,726 leg-dates) |
| indpro | INDPRO | 1997-01-17 | 1971 → 1997-01 (6,542) |
| wei | WEI | 2020-04-21 | 2008 → 2020-04 (3,141) |
| gdpnow | GDPNOW | 2016-08-04 | 2011 → 2016-08 (1,266) |
| sticky_cpi | STICKCPIM157SFRBATL | 2014-03-18 | 1971 → 2014-03 (11,188) |

All other legs are market-priced (rates, breakevens, OAS, equities,
commodities, breadth) — PIT-pure by construction, untouched. Per-date
`pit_class`: `revised_latest` 6,789 rows (essentially pre-1997),
`mixed` 6,072 (1997 → 2020-04), `pit_vintage` 1,618 (2020-04 →, all active
legs on vintage basis). `fallback_notes` lists the falling-back legs per date.

**Control:** the fresh latest-revised rebuild reproduces the committed
`data/regime/regime_history.parquet` quad on **100.0%** of 14,396 common dates,
and the PIT frame is byte-identical to live before any vintage coverage
(0 divergent days pre-1997, as it must be). Two consecutive builds are
byte-identical (deterministic).

## Divergence by era

| era | comparable dates | quad divergent | note |
|---|---|---|---|
| pre-2008 | 9,568 | **2.19%** (210 d) | ALL of it in 1997-2007 (7.34% of those 2,862 d); pre-1997 is structurally 0 |
| 2008-09 | 523 | **0.00%** | see below |
| 2010-19 | 2,608 | **6.67%** (174 d) | gdpnow (2016→) + sticky (2014→) join the vintage set |
| 2020+ | 1,697 | **17.15%** (291 d) | all five legs vintaged; WEI/GDPNow nowcast stamping dominates |

Per-axis sign divergence (the `g >= 0` / `i >= 0` raw-quad convention): growth
2.53% of dates, inflation 0.76%. Mean |score delta| is small (growth 0.034,
inflation 0.014; max 0.40 / 0.16) — divergence concentrates where an axis
hovers near zero and a 0.5-weight macro leg flips it, then hysteresis holds the
two paths apart for weeks.

## Known revision-prone windows

**2008-09: zero divergence, all 19 revised quad transitions matched by PIT at a
0-day shift.** This is a *finding, not a bug*: through the GFC both axes were
pinned far from zero by the market-priced legs (credit, copper/gold, breadth),
so even the famously large payroll revisions of 2008 never flipped an axis
sign. The quad engine's GFC story is market-led and survives PIT scrutiny
untouched.

**2020: the engine's COVID path partially dissolves under PIT.**
- 2020-01-21 Q2→Q4: identical (market-led crash onset).
- 2020-04-14 Q4→Q3 (revised): **no PIT counterpart** — the brief revised-data
  "stagflation" blip in April 2020 is an artifact of revised macro data; the
  PIT frame never printed it (divergence run starts exactly 2020-04-14).
- 2020-05-21 Q3→Q2 and 2020-09-16 Q2→Q1: matched at 0 days.
- 2020-12-01 Q1→Q2 (revised): PIT flips **35 days earlier** (2020-10-27) —
  initial-release nowcasts (WEI/GDPNow) saw the reflation turn before the
  revised series did.

## Divergence run-lengths

59 runs; mean 11.4 bd, median 7, p90 27, max **82 bd (2001-03-01 → 2001-06-22)**
— the 2001 recession onset, where initial payroll/INDPRO releases and their
later revisions told different stories for a full quarter. Next-longest:
2025-10-24 → 2026-01-15 (60 bd), 2015-04-14 → 2015-06-09 (41 bd).

## Honesty bounds (what this spine can NOT claim)

1. **Initial releases only.** The vintage store keeps one row per period (the
   first print). For GDPNOW that means the *first nowcast of each quarter*; the
   live intra-quarter updates are genuinely new information a real-time reader
   had but this spine lacks — gdpnow-leg divergence is therefore an upper bound
   relative to a full-vintage reconstruction. (Also: 6 dates in 2025-12/2026-03
   lose the gdpnow leg where >95 bd separate initial releases, and the last
   5 frame dates lose wei because the vintage store's collection as-of
   (2026-06-25) trails the price store; the axis renormalizes, as live does.)
2. **Seam mixing at coverage starts.** Legs enter the axes as 63 bd (payrolls,
   wei, gdpnow, sticky) / 252 bd (indpro) diffs — for one window after each
   coverage start the diff compares a vintage current value against a
   latest-revised base. `fallback_notes` flags by current-value basis only.
3. **Pre-coverage eras are structurally zero.** The 4.69% overall figure
   dilutes over 6,706 pre-1997 days that cannot diverge; 8.78% on
   vintage-covered dates is the honest like-for-like rate, and even that is a
   *lower bound* on the true full-history revision tax (pre-1997 payroll
   revisions simply are not measurable from this store).
4. **Hysteresis amplification is real behaviour, not noise.** The confirmed
   quad diverges more than the raw quad (4.69% vs 3.20%) because a shifted flip
   date de-synchronizes the 7-day confirmation clocks; this is exactly what a
   real-time reader would have experienced.

## Scope fence

Phase 4a is builder + audit ONLY, additive: `regime_history.parquet`,
`latest.json` and every live consumer are untouched (verified byte-for-byte in
`tests/test_regime_v2_pit.py`), the builder is registered in synapse
(`regime-v2-pit`, tier infrastructure, cadence on-demand) and is NOT wired into
any DAG lane. The W4.4 cell re-keying onto this spine is a later,
preregistration-governed wave.
