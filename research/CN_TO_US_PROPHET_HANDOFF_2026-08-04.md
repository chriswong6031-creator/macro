# CN → US Prophet handoff — what the China breakthrough transfers, and what it must not

**From:** the CN Prophet loser-intelligence session (masterplan
`research/CHINA_PROPHET_LOSER_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`; V3 Relay
Engine #4509; era-retro verdict #4521: v3 rule 89.2% win vs v2 62.2%,
catastrophic 16.2% → 1.5%, on a WIDER shelf).
**To:** the US Prophet trend-intelligence program
(`research/PROPHET_US_TREND_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`, W-waves +
§9 rungs). Operator-requested transfer, 2026-08-04.

The regimes are opposites — CN's tape mean-reverts, the US tape pays
continuation — so the CN *answer* (feature the unconfirmed-early window,
demote confirmed-late) must NOT be copied. What transfers is the method that
found it, three cheap measurements the US side has not run in this form, and
the shipping pattern that turned a finding into a live flip in one day.

---

## 1. The unlock was: grade the system's OWN internal labels as if they were signals

The CN breakthrough did not come from a new indicator. It came from
stratifying matured episode outcomes by labels the system already stamps —
and finding the entry gauge's ladder INVERTED (its "wait, turn not confirmed"
demotion state won 93%; its "buy now — window open" state was the loser
cohort). The alpha was hiding inside a demotion label.

**US action (hours, not weeks):** run the same stratification over the
US board ledger's matured episodes:

- `by_entry_status` — the SAME `entry_signal.assess` gauge runs on US rows.
  Nobody has verified its ladder is correctly ordered FOR the US tape. The
  momentum-regime prediction is that buy_now/confirmed should WIN there — if
  it does, the current featured logic is validated with a receipt; if it
  doesn't, the US has its own one-week R1-class flip available.
- **Every veto/exclusion reason as a label**, graded from the VETO DAY:
  what was the forward return of buying `not_topped(stoch_ob)` prints?
  `freshness_expired` prints (the MSFT case was +15.9% after expiry)?
  `rsi_cap` prints? Each veto is a timing label that may be mispriced.
  §2.5's leader-reset study tested ONE construction (fresh 2D cross on RS
  leaders, −1.50%) — it did not grade the veto labels themselves.
- **The ran lane from its OWN anchor**: CN's RAN_LATE cohort — excluded from
  featured — ran 83% win / +6.0 median excess, best shelf on the board. The
  US ran lane deserves the same forward grade before another door is built.

Template: `research/cn_prophet_audit/v1_loser_audit.py` (episode frame from
`track_scoring.build_episodes`, admission-day joins, `_slice_table` idiom,
G0.7 winner-forfeiture costing on every candidate filter).

## 2. The era-retro stand-in escapes the telemetry calendar

The US G0.2 clock (5 green nightlies) restarted with the #4534 heal; scored
changes are queued behind it. The CN program's answer to exactly this:
**retro-apply the candidate rule to the frozen episode frame with the
production scorer — verdict in hours** (`research/cn_prophet_audit/
v3_era_retro.py`; 9s runtime; leg-attribution block shows WHICH change
carries the delta). Two traps already hit and solved there, which the US
retro will hit too:

- **Frozen-replay pin**: truncate every price series at the frame's freeze
  date or the P0 reproduction gate breaks the next nightly (#4522).
- **`x is True` on a numpy bool is always False** — a silently dead feature
  leg; per-leg fire-count diagnostics catch it
  (memory: numpy-bool-is-true-deadens-a-feature-leg).

## 3. Priority re-order suggested by the CN result

CN found the population gate FIT its tape (89% of era runners sighted) and
the whole loss came from the timing layer within it. The US audit shows the
opposite topology: the population gate itself excludes the winners (48/150
never eligible; 91% veto-blocked; median window 3 sessions). Implication:
the US's R1-class lever is most likely in the two places already chartered
but not yet measured:

- **W5.2 FRESH_TICKS (2→3→4)** — CN's flip was entirely about WHEN within a
  valid setup; the US equivalent dial is the freshness window that expires
  winners mid-run. Run it as an era-retro NOW (pre-registered bar already
  exists), don't wait for the telemetry clock.
- **W1 intake sort** — already Grade-A-backed; the CN precedent (rank-IC
  +0.073 anti-predictive, setup score higher on losers) says ordering
  defects compound quietly.

And one asymmetry worth stealing outright: **v3 improved every headline
while WIDENING the shelf.** Quality did not require tightness — it required
the right axis. The US funnel converts 2 of 102 sighted winners; widening
along measured-good labels (not wholesale veto deletion — §2.5 already
killed that) is where the CN evidence says the payoff hides.

## 4. The shipping pattern that turned a finding into a live flip in one day

Measured inversion + coherent mechanism ⇒ operator ratification ⇒ ship the
flip LIVE with (a) the displaced rule still grading nightly as a labeled
shadow under `WATCH_DEFINITIONS` (the race runs anyway, favored side live),
(b) a named tripwire in the telemetry (≥5pp win-rate trail over 60 matured →
alarm + revert proposal), (c) a single-commit revert path. This is G0.8 in
the CN masterplan; the helpers (`engine/cn_v3_tripwires.py`, the
shadow-append idiom in `build_china_library.py`) lift directly.

## 5. What NOT to transfer

- The patience-flip DIRECTION. CN evidence is from the Korea-semis contagion
  window (CSI −9.1%, semis −37%) — a mean-reversion extreme. On the US
  momentum tape the same measurement may validate confirmation instead.
  Measure first; the method is the transfer, not the sign.
- CN's relay/limit mechanics (A-share microstructure; no US analog).
- Nothing here touches the US board's graded population without its own
  ratification — DNR row 49 and the US plan's own G0.4 stand.

## 6. One shared future both desks now need

Both markets have now proven the same meta-lesson from opposite directions:
**one entry family cannot serve two regimes** (US: washout detector starves
in a trend; CN: confirmation layer poisons in a reversion). The durable
architecture is the same on both desks — both families present, each graded,
with regime-scoped weights adjudicated when each desk's regime store carries
two regimes (CN P-SI-4; the CN store is one rebound away from its second
regime). Whoever builds the regime-conditional weight machinery first should
build it market-agnostic.
