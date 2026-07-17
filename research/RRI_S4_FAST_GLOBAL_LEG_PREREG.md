# RRI-S4 — Fast Global Leg for the US Radar (intl_bridge claim declaration, prereg)

**Status: DRAFT claim declaration — awaiting operator ratification; on ratification the two
claims below are declared into the `intl_bridge` trial-ledger family via
`scripts/intl_phase0.py --declare` BEFORE any builder runs.**
This study is **NOT** in the `rri_2026h2` BH family (cover §4): it follows the intl→US wire
constitution — IRD-R1: promotion of any intl metric to US authority goes through
`intl_phase0` as new pre-registered claims with the full gate battery and the family's
Deflated-Sharpe declared-N discipline.

## 1 · The question, in plain English

The US radar's only global equity read is the Tier-B `global_breadth` leg (claim C3,
CONFIRMED 2026-07-02, wired accruing per INTL-38): % of US-listed country ETFs above their
200dma. On 2026-07-16 it read **87% above = calm** (EWY +30%, EWT +34% above) while our own
cn/hk/tw radars stood at 98/91/98 — two structural blind spots:

- **Latency.** Country ETFs price at the US close; the nightly US build of day T sees Asia's
  day-T close at best. An Asia crash on T+1 (their session) is visible to *local-index* data
  at the asia-close lane (~09:00 UTC), roughly 13 hours before the ETF prints — and a full
  build cycle before the ETF-based leg can move.
- **Content.** %>200dma is a *level* lens: at a parabolic top the crashing market is still far
  above its 200dma (the ITR F3 arithmetic), so ETF breadth reads "healthy" precisely when the
  intl radars read extension risk. The intl radars' own alert states aggregate the drivers
  that actually front-ran 07-17.

**Do global reads built from LOCAL-close data — (a) local-index breadth, (b) the intl radar
fleet's own alert breadth — carry US-drawdown information incremental to the existing C3 ETF
leg and the US domestic legs?**

## 2 · The two declared claims (grammar of `engine/intl_claims.CLAIMS`)

```python
{
  "id": "c3b_local_index_breadth",
  "channel": "C3",
  "hypothesis": "% of local bench indices (>=8 of the 10 radar benches, LOCAL closes) above "
                "their 200dma, with its 63d slope, leads US >=5% drawdowns — the C3 mechanism "
                "on a substrate that is a session faster and immune to US-session smoothing.",
  "direction": "de-risk",
  "target": ("yahoo", "_GSPC"),
  "horizons": (21, 42),
  "source_series": [("intl","^KS11"),("intl","^N225"),("intl","^TWII"),("intl","^NSEI"),
                    ("intl","^AXJO"),("intl","^FTSE"),("intl","^STOXX"),
                    ("china","000001.SS"),("hk","_HSI"),("canada","_GSPTSE")],
  "freshness_sla_days": 5,
  "builder": None,          # W2-style builder PR only after ratification
  "notes": "RRI-S4a (2026-07-17). Anti-fire postmortem of 2026-07-17 Asia crash. Extra gate: "
           "incremental content vs c3_global_etf_breadth (see prereg §3).",
},
{
  "id": "c3c_intl_radar_alert_breadth",
  "channel": "C3",
  "hypothesis": "Fraction of intl radar profiles (10 markets) in gated elevated/risk-off, "
                "causal 504d percentile, leads US >=5% drawdowns — the radars aggregate "
                "rate/FX/extension drivers that individual breadth lenses miss.",
  "direction": "de-risk",
  "target": ("yahoo", "_GSPC"),
  "horizons": (21, 42),
  "source_series": [("intl","^KS11"),("intl","^N225"),("intl","^TWII"),("intl","^NSEI"),
                    ("intl","^AXJO"),("intl","^FTSE"),("intl","^STOXX"),
                    ("china","000001.SS"),("hk","_HSI"),("canada","_GSPTSE"),
                    ("fred","DGS2"),("fred","DFII10"),("fred","DGS10"),
                    ("intl","USDKRW=X"),("intl","USDJPY=X"),("intl","USDTWD=X"),
                    ("intl","USDINR=X"),("intl","AUDUSD=X"),("intl","GBPUSD=X"),
                    ("intl","EURUSD=X"),("yahoo","DX-Y.NYB"),("yahoo","CNH_F"),
                    ("china_property","cgb"),("china_breadth","breadth"),
                    ("canada_breadth","breadth")],
  "freshness_sla_days": 5,
  "builder": None,
  "notes": "RRI-S4b (2026-07-17). Deterministic transform of committed store data via "
           "engine.risk_radar_intl.composite_series — a DATA leg, not a verdict router "
           "(FR-1/R3 fence): no can_force, no veto, no state is consumed; only the count of "
           "band-crossings of a published deterministic construction.",
}
```

Name convention: series names follow the engine profiles exactly (caret forms for the intl
group; `lib.store` sanitizes `^`→`_` on disk). The freshness gate must read the declared
tuples via `store`, the same path the engine uses — a claim must never grade PENDING on a
naming artifact. Grading machinery: both claims are graded by the `intl_phase0` battery
against `_GSPC` at horizons (21, 42) — **NOT** by `risk_radar_intl_audit` (whose h5/h10/h21
ruler grades the intl radars themselves, not US-target claims).

Declared-N accounting: `intl_bridge` family grows by 2 claims × 2 horizons; every DSR in the
battery deflates by the honest post-add count. No third construction, no alternative
threshold/slope window may be scanned — the builder implements exactly what the claim
declares (level+63d-slope for c3b mirroring C3's frozen form; alert-fraction percentile
for c3c).

## 3 · Gate battery (the full intl_phase0 constitution + two claim-specific gates)

Standard hard gates (per `intl_phase0.decide()`, all frozen there): DSR ≥ 0.90 at the
declared-N; orthogonality vs the US domestic legs; crisis-count ≥ 3; split-half same-sign;
crisis-independent ES; MaxDD-cut for de-risk direction; fail-closed freshness.

Claim-specific frozen gates:

- **Incrementality vs C3 (the decisive one).** Residual content must survive partialling out
  the SAME-DAY `c3_global_etf_breadth` feature: residual Spearman(feature | C3-ETF-leg +
  US-domestic legs, forward DD) must retain ≥ 0.50 of the unconditional surviving fraction
  (the C3-precedent orthogonality grammar). A fast leg that is just the ETF leg one session
  early fails this and dies honestly.
- **Timing decomposition (printed receipt, gates Stage-B wiring).** The claim is graded twice:
  on the local-close date stamp (t, the asia-close information set) and on t+1 (the US-close
  set). The wiring into any US surface may only use the alignment that was graded; if the edge
  lives entirely at t+1, the "fast" framing is dropped and the claim competes as a plain
  content claim.

## 4 · Fire-rate context (outcome-blind census, cover §5)

≥3 of 10 markets in gated alert = 9.0% of last-10y days, 32 non-overlapping episodes
full-history; local-bench breadth ≤40% on 28.2% of days (why the declared construction is
level+slope, mirroring C3, not a bare level threshold). Base rates for _GSPC forward
drawdowns are whatever `intl_phase0`'s battery measures — none were computed for this prereg.

## 5 · Seam (post-promotion only — named now so nobody invents it later)

If a claim clears the battery: it enters the US radar's **`global` Tier-B scare** alongside
`global_breadth` (0.7) and `jpy_carry` (0.3) (current split at drafting, `engine/risk_radar.py`
`_SCARES["global"]` — re-verify at wiring time), with weights re-split by explicit operator
ruling in the wiring PR — Tier-B law binds: **escalator-only, never originates a US state**
(INTL-38/W4 precedent; C3's 0.20 weight-cap precedent governs any scorer-facing use). The
wiring PR must also solve the data path honestly: the leg's series is computed and committed
by the asia-close lane (lane-gated appends, the #2693 arming trap) and read by the US build
as last-committed data — no intraday recompute on the render path.

## 6 · What would kill it (frozen)

- Incrementality gate fails → REJECT-REDUNDANT row vs C3 (the ETF leg already owns the
  channel; latency alone carried no residual content).
- DSR/orthogonality/ES fail → the standard intl_phase0 CONTEXT/kill grammar: truthful
  graveyard row in `data/intl_bridge/ledger.json`, claim moves to display-only forever-until-
  new-evidence.
- Either way the intl radars themselves are untouched — this study only concerns the US book's
  global leg.

## 7 · Anti-look-ahead checklist

- Local-close date stamping is explicit in the builder (t vs t+1 graded separately, §3).
- c3c consumes `composite_series` replays with trailing causal percentiles only.
- The 10-bench panel is fixed here (the radar benches); no panel search.
- No US outcome joined before ratification; census counted alert-days only.

## Ratification

Drafted: Fable (main loop), 2026-07-17. On ratification: `--declare` PR first (claims land in
the ledger as PENDING), builder PR second, wiring PR (if CONFIRMED) third — three separate
gates, per the C3 lifecycle precedent.
Operator: ☐ ratify both claims · ☐ ratify c3b only · ☐ ratify c3c only · ☐ decline.
