# The Bottom Ledger — measuring Prophet's actual objective (2026-07-22)

**Operator charter statement (2026-07-22): "pinpoint bottom picks — that's the main objective
of Prophet."** This design makes that objective *measurable*, because today it is not: the
committed 21d-excess grades measure payoff only, the −5%-stop ruler grades a perfect bottom
call as a loss when one wide bar wicks it (63–68% stop-outs in deep washouts at every rung —
`washout_ladder_study.py`), and the floating Track-Record marks measure nothing stable at all.
**A system cannot learn to pinpoint bottoms when nothing in it measures bottom-pinpointing.**

## First-principles decomposition

A bottom *call* has four separable qualities. Any single win/loss number conflates them,
and the conflation is precisely what confused the exit discussion — exits are *policy*,
measurement must be policy-free:

| Quality | Question | Metric (frozen at maturity H=60td) |
|---|---|---|
| **Proximity** | how close to the actual low? | signal close vs trough low in [t−10, t+60]; `pin5` = within 5% |
| **Durability** | did the called floor hold? | undercut depth of trailing-20d low: held ≤0.5% / probed ≤3% / deep ≤10% / **broke** >10% — depth graded, a recovered probe is NOT a failure |
| **Path** | what pain before payoff? | MAE60 before MFE60 (what sizing/stop policy must survive) |
| **Payoff** | what did it deliver? | MFE60, fwd60, excess vs bench (context, never a verdict alone) |

## Evidence the ruler works (`bottom_ruler_study.py`, 232-name panel, matured events only)

Since 2018 (modern regime), per rung — prox = median % above eventual trough; pin5 = % of
calls within 5% of the low; held/broke = floor undercut ≤0.5% / >10%:

| Rung | n | prox | pin5 | held% | broke% | MFE60 | fwd60 |
|---|---|---|---|---|---|---|---|
| W0 thrust (demand day) | 250 | 16.6 | 0.0 | **71.6** | **12.4** | **16.1** | **7.2** |
| **W1 2D StochRSI** | 832 | **8.9** | **25.8** | 42.9 | 20.1 | 12.8 | 6.0 |
| W2 2D MACD | 981 | 10.0 | 16.6 | 47.3 | 18.9 | 12.8 | 5.7 |
| W3 1W cross | 951 | 10.4 | 16.1 | 47.3 | 18.4 | 12.5 | 5.2 |
| W4 2W cross | 1368 | 11.9 | 10.7 | 58.2 | 15.6 | 12.2 | 4.8 |
| **CASCADE_P (what the board admits today)** | 1077 | 10.7 | **8.4** | 55.0 | 13.8 | 10.6 | **3.4** |

Three structural facts fall out:

1. **The current admitted signal is a trend-resumption detector, not a bottom detector.** It
   has the *lowest* pinpoint rate on the board (8.4%) and the weakest payoff (MFE 10.6 /
   fwd60 3.4). Prophet's stated objective is currently unmeasured AND unoptimized.
2. **There is an earliness↔durability frontier, not a single best rung.** W1 (2D stoch) is the
   precision scout — closest to the low, 26% pinpoint — but 1-in-5 of its floors later break
   (it fires early into some continuing downtrends; median trough arrives 12 days *after* it).
   The thrust bar is the mirror image: never within 5% of the low (by construction) but the
   floor almost always holds after it (72%) with the best payoff. The 2W cross is the
   durability confirmation (58% held) at mid lateness — the operator's "higher score for 2W"
   is exactly right *as a confirmation tier*.
3. **The testable next construction is the confluence sequence, not a better single trigger:**
   floored state → W1 turn (precision) → thrust/2W confirm (durability). That is literally the
   operator's own CRCL sequence. The Bottom Ledger exists to grade such sequences from live
   forward data instead of debating them.

## The two-instrument architecture (replaces the floating marks entirely)

**Instrument 1 — the Bottom Ledger (learning; policy-free; feeds Prophet).**
Every bottom-class flag — washout WAIT-lane entries, bottoming-lane board buys, Prophet plans
tagged bottom-class — gets one row at flag time and is graded ONCE at H=60 maturity on the
four qualities. Frozen when matured (one-grader law SA-R14). No exits, no stops, no policy.
Nightly cohort table by configuration (rung, weeks-at-floor, dd252 bucket, sector, vol class)
→ consumed by the Prophet governor/autopsies as the objective function for bottom-picking.
Promotion decisions (washout lane → scored tiers / Prophet origination) read THIS ledger
against the pre-registered gate (VETO_LEG_AUDIT.md). The panel replay above is committed as
the calibration baseline the live cohorts are compared against as they mature.

**Instrument 2 — the Episode Record (trust; user-facing Track Record).**
Entry→exit episodes with the exit POLICY DECLARED AT ENTRY and stamped into the row:
trend-class names → the validated house exit (confluence SELL* / fast-reversal cut + −5%);
washout-class names → floor stop + SELL* + time cap (the −5% ruler is measured-wrong for that
class). Episode grain from `snapshots.jsonl` (COIN 07-02 and 07-14 become two rows), frozen at
close, delisted names graded at last price rather than dropped. Replaces `emit_ledger` /
`emit_outcomes` floating marks; the win_rate is computed over closed episodes only and stops
mutating retroactively.

Why two instruments: the floating-mark incident was a policy/measurement conflation. The
learning loop must never contain exit policy (or it learns the policy, not the bottoms); the
public record must always contain declared policy (or it isn't honest). One artifact cannot
do both jobs.

## Phasing

- **Phase 1 (build now):** `engine/bottom_ruler.py` (pure grading functions) +
  `scripts/grade_bottom_calls.py` (nightly-only advancer; accrues flags from board snapshots +
  washout WAIT payloads + Prophet plans; matures rows at H=60; writes
  `data/bottom_ledger/rows.parquet` + `site/factordata/us_bottom_ledger.json` display artifact
  + committed panel-baseline JSON). Additive; no user-facing surface changes; governor gets a
  read-only display-tier block. Live rows begin maturing ~2026-09-25 (H=60 from the first
  06-30 snapshots); the panel baseline carries the learning until then.
- **Phase 2 (operator go):** Episode Record v2 (emit overhaul, episode grain, declared-exit
  stamping, survivorship fix) + the us_track_record page gains a "bottom-calling skill" panel
  (prox/durability distributions vs baseline — the instrument panel for the main objective);
  Prophet plan tagging + origination from the washout lane once the promotion gate passes.

Display-tier throughout until the gate passes; the word "validated" stays out of user-facing
text; nulls printed.
