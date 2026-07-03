# Wave-7 pre-registration v1 — the serial-P&L lockout gate (written BEFORE the runs)

> Fable, 2026-07-03. Seventh wave of the DURABLE_BOTTOM_FRAMEWORK program (§2/§4 bind verbatim).
> Successors: WAVE6_PREREG v2 §8 + WAVE6_REPORT. Wave-6 established: C-LOCKOUT's fixtures are
> perfect (Tencent: 1 admitted fire, 100% shut from knife onset) but per-fire clean15 is the
> WRONG AXIS for a ratchet — it prunes later, deeper (better-scoring) fires by design; its claimed
> value is SERIAL capital preservation (fires 2..N of a knife). Wave-6 also proved bear-context
> gaps are fixed-barrier vol artifacts → ATR-scaled economics are co-primary here, not a lens.
> DEGENERACY RULE (house): §5 shows every candidate's admitted-fire set is a strict subset of its
> control's on the identical fire sequence — verified on fixtures pre-run.

## 0. The question

Among the fires the live 200MA bar-raiser blocks (the wave-6 honest population: ¬above200-3D ∧
¬w_bull ∧ ¬bear-div ∧ ¬reclaim-saved), does the C-LOCKOUT ratchet, applied SERIALLY per name,
(a) cap the capital a knife destroys (the Tencent failure: repeated re-entries down a decline)
while (b) retaining most of the payoff of the recoveries (the MCD/KO mean-reversion dips)?
Decision fed: a display-only "mean-reversion candidate: ratchet OPEN / LOCKED" state on
stock.html (pairs with the shipped HOLD panel) for blocked names + ledger fields. NOT a
signal_quality change; NOT a board-eligibility change.

## 1. Serial policies (per name, fires in time order; identical population for all)

Ratchet (wave-6 C-LOCKOUT, frozen): OPEN until (dwell_m ≥ 4 ∨ entrenched-252d(≥70% below own
200MA) ∨ dist-below-200MA > 18%); then SHUT until (completed-ME monthly StochRSI D exits
oversold AND close reclaims the 200MA). All features on wave-6's completedness conventions
(ME-native, known-date, shift-1; fixed global fortnight phase where 2W is used).

- **S-ALL** — take every blocked fire (the unguarded counterfactual).
- **S-LOCKOUT** (primary) — take fires only while OPEN.
- **S-LOCKOUT+F7** (secondary, Holm-tightened) — OPEN and the weekly-stoch turn leg live at the
  fire (wave-6's only sign-consistent near-miss; frozen definition from wave6.py).
- **S-NONE** — take nothing (the incumbent gate; economics ≡ 0).

**Position realism (pre-committed):** one position per name at a time — a fire occurring while a
prior race is unresolved is SKIPPED (all policies alike). Per-fire economics = the barrier race
already used program-wide: fill next close; exit −5% stop / +15% target / 126d timeout close;
R = realized return. ATR-scaled twin (1.5×/4.5× ATR63 at fill) is CO-PRIMARY (G7c).

## 2. Metrics (per name, then cross-sectional)

- `cumR(name, policy)` — sum of realized per-fire R (the capital line).
- `minCumR(name, policy)` — running minimum of the cumulative line (max capital destruction).
- `n_taken`, mean-per-fire R (decomposes count-vs-quality; a ratchet wins by count).
- Inference: bootstrap over NAMES (the serial unit), 90% bounds; floors ≥40 serial names
  (≥3 blocked fires) on the deep panel; every gate read on both fixed and ATR economics.

## 3. Panels & fixtures

Deep US (211) → baskets OOS (2,335) → **HK decisive-adversarial** (157; knives live there — the
tail test that matters most). Fixtures (unit tests pre-panel, printed tables):
- **Tencent 0700.HK 2021-01..2022-10:** serial table per policy. Expected shape: S-ALL cumR
  deeply negative through the knife; S-LOCKOUT admits ≤1 fire (wave-6 verified) → the saved
  capital is THE headline number. Hard assert: S-LOCKOUT cumR > S-ALL cumR on this window.
- **MCD 2026-04..06 / KO 2024-12, 2025-09:** ratchet expected OPEN throughout (shallow, dwell 0,
  not entrenched) → S-LOCKOUT ≡ S-ALL on these names — printed to show the ratchet does NOT
  amputate the owner's dips (including MCD's June fire that measured fwd −4.6%: the ratchet is
  not a winner-picker and the table says so honestly).

## 4. Gates (pre-committed; bootstrap-over-names bounds; fixed AND ATR economics)

- **G7a knife-tail protection (deep):** on serial names, the WORST-DECILE per-name cumR improves
  by ≥ 0.5R (S-LOCKOUT vs S-ALL) at the 90% bound, AND median minCumR improves (≥ 0.25R).
  (The ratchet's claim lives in the left tail, not the median.)
- **G7b recovery retention (deep):** on names whose sequence resolved positive under S-ALL
  (cumR > 0), S-LOCKOUT retains ≥ 80% of aggregate positive cumR.
- **G7c ATR honesty:** G7a clauses hold on ATR economics (vol-artifact kill; F8 lesson).
- **G7d OOS + adversarial:** G7a direction replicates on baskets; on HK, S-LOCKOUT beats S-ALL
  on worst-decile cumR at the 90% bound (the Tencent-class test) — HK is REQUIRED here, unlike
  wave-6 (a knife-guard that fails where knives live does not ship).
- **G7e beat-the-incumbent:** aggregate cumR(S-LOCKOUT) > 0 at the 90% bound on deep AND baskets
  — else S-NONE (the current block-everything gate) is the simpler winner and NOTHING ships
  (CHARTER §3 kill-to-simpler; this is the gate most likely to fail and that is fine).
- **G7f (secondary, Holm-tightened):** S-LOCKOUT+F7 must beat S-LOCKOUT on aggregate cumR AND
  not worsen worst-decile, both at 95% bounds, to earn the refinement; else primary stands alone.
- **Ship rule:** the OPEN/LOCKED state ships (stock.html + ledger, display-only) iff G7a–G7e.
  Failed gates → ledger rows, nothing ships, and the honest conclusion "keep blocking everything"
  is recorded as the wave's answer.

## 5. Degeneracy & honesty checks

- Admitted-fire sets: S-LOCKOUT ⊊ S-ALL and S-LOCKOUT+F7 ⊊ S-LOCKOUT, verified non-empty on both
  sides per panel pre-run (fixtures prove strictness: Tencent for the first, F7-off days for the
  second). Controls are POLICIES over the identical sequence — no wave-5-style collapse possible;
  the cumR-vs-count conflation is handled by reporting mean-per-fire alongside (§2).
- Same-name overlapping races removed by the single-position rule (applied to ALL policies).
- Survivorship: deep panel survivors-only understates knives → HK panel carries the tail burden;
  stated in the report.
- Multiplicity: ONE ship decision (S-LOCKOUT state); F7 refinement secondary at 95%.

## 6. Deliverables

`wave7.py` (reuses wave6.py population/ratchet/feature code by import; new code = serial engine +
name-bootstrap), `--selftest` = fixtures + subset assertions + single-position rule test,
`WAVE7_REPORT.md`, gates JSON, ledger rows in DURABLE_BOTTOM_FRAMEWORK §8.

## 7. Amendments

*(empty at registration)*

---

## 8. RETIREMENT (2026-07-03, pre-run — the panel answered the question with existing data)

The 4-reviewer adversarial panel (2 FLAWED, 2 SOUND_WITH_FIXES-with-criticals) killed this wave
BEFORE any compute, and — decisively — MEASURED the answer from the wave-6 parquets and fixtures:

1. **Feasibility inversion (mechanism, quantitative):** under the registered stop-disciplined
   economics the program's headline knife (Tencent 2021-22) costs S-ALL only **−0.15R**
   (3 blocked fires × −5% stop); S-LOCKOUT saves **+0.10R** — 5× below the G7a margin. The
   lockout's theoretical ceiling is `n_saved_stops × 0.05R`.
2. **Net-negative under the 3:1 barrier asymmetry:** the ratchet prunes the later, deeper,
   winner-skewed fires (wave-6 established); blocking one +15% winner costs 3× one saved −5%
   stop. Measured proxy on wave-6 parquets: worst-decile benefit −0.35R (HK) / −0.20R (stocks);
   61% of HK serial names NEGATIVE. G7a and G7b are jointly unsatisfiable.
3. **The release condition chases:** Tencent SHUT 2021-08 → next admit 2023-11 (~27 months),
   re-opening a year AFTER the recovery ran (failure mode c). KO-class year-long sub-200 bases
   never trigger the reclaim leg — SHUT is near-absorbing exactly where entries live.
4. **Design breaks of the wave-5 class (caught pre-run, third time):** the single-position skip
   rule breaks the §5 subset nesting (worked counterexamples — policies can trade DISJOINT
   sequences); "R = realized return … program-wide" was false (only binary race indicators exist;
   timeout-R sign convention undefined for a measured 22.6% of fires); the Tencent hard-assert
   is tautological for ANY subset policy in a decline; "ATR63" is the 14-period EWM atrp and
   degenerates to |Δclose| on close-only HK; G7e tested against zero, not against S-ALL; no
   memoryless-cooldown baseline isolated the state machine's marginal content.

**Verdict: RETIRED. The lockout candidate is closed** — its maximum measurable benefit sits
below any meaningful gate margin because the −5% stop already caps knife damage. The knife
protection the 200MA gate was built for is substantially provided by stop discipline.

**The live question this opened (unregistered, for a future wave ONLY with owner direction and
CHARTER-compliant framing):** the panel's proxy measured S-ALL (trade every blocked fire, stop-
disciplined) as net-POSITIVE on all three panels incl. HK — the 200MA bar-raiser may be blocking
a population whose per-fire risk is already capped. Any follow-up must use honest signed-R
economics (new code, convention-pinned), survivorship-honest panels, and be framed as a
surfacing/recall question (CHARTER: risk tool, not return engine).
