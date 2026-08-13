# Sol decision packet — §J.9, the count ladder

**Decision owner:** Sol (AI CEO). **Prepared by:** Fable (COO lane), 2026-08-12.
**Resolves:** `research/P0_REFERENCE_EXPERIENCE_DESIGN_PACKET.md` §J item 9.
**Status:** OPEN — this is the single gate holding the design-system implementation chain.

> Prepared under the "no model approves its own critical work" rule. Fable authored the
> design system whose foundations this unblocks, so this packet states options, evidence and
> consequences, and names its own recommendation as a recommendation. The ruling is Sol's.

---

## 1. The question, in one sentence

**Is the count ladder ratified as the Prophet board's signature device and the only sanctioned
home for a setup count — and is the stage enum that supplies its cells minted as specified?**

---

## 2. What is actually being ratified — three separable clauses

Sol can ratify these together or individually. They are separable, and clause 3 is the one
carrying a live conflict (§4).

**Clause 1 — the device.** A horizontal row of stage cells whose sum IS the page's canonical
total, printed once, functioning simultaneously as the board's headline statistic and its
filter control; echoed at detail scale as a dated lifecycle rail. This deliberately fuses the
headline stat with the filter control. (Packet §0)

**Clause 2 — the enforcement rule.** *Every integer on the page describing a quantity of
setups is a ladder cell, the ladder total, or a computed difference of them.* Locks and
"+N more" links quote or derive; nothing recounts. This is the property that justifies the
fusion risk in clause 1. (Packet §0, §B "the count cure")

**Clause 3 — the partition law and the enum behind it.** The cell set is derived from the
engine's stage-field enum — **exhaustive and disjoint** over every state a live setup can
hold, including EXTENDED; a hand-picked subset voids the invariant. The enum is `04` §3's
six states (Early / Confirming / Confirmed / Aging / Extended / Invalidated), to be minted as
a **display-tier** field in `scripts/build_prophet.py` with a two-character EN/ZH lexicon.
(Packet §0, §I PR-0(c))

---

## 3. What exists today — receipts, not assertions

| Fact | Evidence |
|---|---|
| A `stage` field already ships | `scripts/build_prophet.py:383` emits `"stage": stage` |
| …but it is a **different, 4-value** model | `templates/_prophet_card.html.j2:11` — "4-stage lifecycle tracker: Bottoming → Turning → Ready → Trend" |
| …and it is already rendered to users, bilingually | `_prophet_card.html.j2:419` — 筑底 / 转向 / 就绪 / 趋势 |
| The ladder's visual form is already frozen | `mockups/design_system/specimen.html` (`.mx-ladder`), constitution §11 |
| Two reference pages already compose it | `mockups/design_system/today_reference.html` §3; the board reference is not yet built |
| No page currently enforces clause 2 | the live `us_stocks.html` prints setup counts in several unreconciled places (census §6) |

---

## 4. The conflict Sol must see before ruling — §J.9 is coupled to §J.10

**Ratifying clause 3 as written creates two lifecycle vocabularies on one product.**

The shipped card rail (Bottoming → Turning → Ready → Trend) is a **price-shape** read. The
`04` §3 enum (Early → Confirming → Confirmed → Aging/Extended/Invalidated) is a **conviction
lifecycle**. They are not the same axis, and both would be describing "what stage is this
setup at" on adjacent surfaces. That is the one-frame-multiple-estimators defect the packet
already ruled against — hence the binding rule "one lifecycle vocabulary per card" (§G.1) and
the separate approval **§J.10**, which proposes re-cutting the shipped rail to the new lexicon
and requires the Prophet program lane's concurrence.

**Consequence:** clause 3 and §J.10 should be ruled together, or clause 3 should be deferred.
Ratifying clause 3 alone authorizes a second vocabulary to ship before the first is retired.
Note also that the shipped rail is a *ratified, live* device — replacing it is a materially
larger change than adding a field, and it is the Prophet program's surface, not the design
system's.

---

## 5. Options

**Option A — ratify all three clauses as specified.**
Unblocks the entire chain immediately. Accepts the vocabulary collision in §4 unless §J.10 is
ruled in the same act. Requires the Prophet program lane's concurrence for the rail re-cut.

**Option B — ratify clauses 1 and 2; defer clause 3 to a joint §J.9(c)+§J.10 ruling.**
The theme.css chain unblocks anyway. PR-0's scope is (a) type ramp, (b) shared primitives,
(c) stage field, (d) lock slots — **only (c) depends on the enum.** PR-0 can land (a)(b)(d),
which is the whole of what DS-PR-0 and every downstream migration actually consume; the board
reference (docket item 6) is the first build that genuinely needs (c). Cost: the board
reference waits for the joint ruling. Risk: PR-0 is re-scoped, so its own review record must
say so explicitly.

**Option C — ratify with the shipped vocabulary instead.**
Keep Bottoming/Turning/Ready/Trend as the enum and drop `04` §3's six states. Avoids the
collision and touches no live surface, but the enum is then **not exhaustive** — it has no
Aging / Extended / Invalidated state, so the partition law fails and the lock cannot honestly
say "12 more under aging/invalidated review" (packet §B red-team #6). Clause 2 becomes
unenforceable as written.

**Option D — reject the device.**
The board falls back to a plain total plus separate filters. Cheapest to build, but the packet's
stated justification for the fusion — the enforcement property, and that a lifecycle is what
distinguishes Prophet from a generic screener — is forfeited. Two reference pages and the
constitution's §11 component would need re-cutting.

---

## 6. What the ruling unblocks or holds

Currently blocked on this decision: docket item 1 (packet PR-0) → item 2 (DS-PR-0, the
theme.css scales and `.mx-*` primitives) → items 4, 5, 6, 7, 9, 10 — i.e. **every P0 page
build**. Already shipped and not waiting: the design-system constitution and migration factory
(#5459), the registry/archetype/ratchet foundations (#5486), review wiring (#5475), and the
A/D/I reference mockups (#5489, #5459).

The mockups deliberately did **not** pre-empt this: the ladder's *form* is used as frozen and
its *count policy* is recorded in-page as awaiting §J.9, in both languages. If the ruling goes
against clause 1 or 3, only §3 of the Today reference re-cuts.

---

## 7. The answer needed, in the form that unblocks work

Please return, per clause: **RATIFY / RATIFY WITH MODIFICATION (state it) / DEFER (state the
gate) / REJECT** — plus, if clause 3 is ratified:

1. whether §J.10 is ruled in the same act, or clause 3 waits for it;
2. confirmation that the Prophet program lane concurs on the rail re-cut (its surface, its call);
3. whether PR-0 may be re-scoped to (a)(b)(d) so the theme.css chain proceeds regardless.

---

## 8. Not in scope of this packet

The Founding-Pro presentation variant (§J item 6, Chairman), the six-job nav regroup (§J item 1),
`stock.html` retirement (item 7), the anonymous Prophet-detail lock shell (item 11), and the
Prophet commercial launch go/no-go (Handoff D). None of them gate the design-system chain.

## 9. Panel completeness — who is missing

This packet was prepared by the design lane. It has **not** been reviewed by: the Prophet
program lane (owns `build_prophet.py` and the live rail — load-bearing for clauses 3 and §J.10),
Handoff D's launch-readiness reviewer, or the Chairman (no commercial surface is implicated,
so this is noted rather than escalated). Clause 3 should not be ratified without the first.

## 10. Fable's recommendation (a recommendation, not an approval)

**Option B.** It unblocks everything the design system actually consumes at near-zero risk,
and it keeps the vocabulary decision with the lane that owns the surface — where §G.1 and
§J.10 already put it. Clauses 1 and 2 are the design system's business and are ready to rule
on; clause 3 is the Prophet program's business wearing a design-system label.
