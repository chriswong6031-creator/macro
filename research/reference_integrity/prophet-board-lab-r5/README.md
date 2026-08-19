# Prophet Operator Lab — RIG R5 packet

**Status: `draft`. This packet cannot be approved and must not be treated as canonical.**
The independent critique is **owed**, and it is owed by someone who is not the author.

The reference artifact is `mockups/refs/prophet_lab/`, frozen at
`6ee8f34480ce3299b4692a3e732c6a5c75d9782a`. Its design record — every decision, every
deliberate deviation, and every known limit — is `mockups/refs/prophet_lab/DESIGN_NOTES.md`.

---

## What is missing, on purpose

| File | Why it is absent |
|---|---|
| `reviews/product_regression.yml` | Reviewer A has not run. RIG §6 requires a critic who is **not the author**, judging the result against production **before** seeing the designer's rationale. |
| `reviews/visual_taste.yml` | Reviewer B has not run, same rule. |
| `verdict.yml` | A verdict is a design-authority act over a completed review packet (RIG §7). No reviews exist, so no verdict can. |
| `approval.yml` | **A reference may not approve itself** (RIG §7, no self-canonization). This session authored the artifact; it is disqualified from approving it, and did not write one. |

The gate agrees, and says so mechanically:

```
$ python3 scripts/check_reference_integrity.py --evaluate prophet-board-lab-r5
reference-integrity --evaluate prophet-board-lab-r5 (status=draft, scope=full): 10 finding(s)
  missing-artifact-file          … verdict.yml / reviews/*.yml / approval.yml
  missing-review-receipt         … "a new reference cannot approve itself (RIG §6)"
  unwarranted-authority-unadjudicated  auth.lab_observation_exists
  unwarranted-authority-unadjudicated  auth.measured_lead
  approved-without-receipt, approved-with-wrong-verdict
reference-integrity: prophet-board-lab-r5 is BLOCKED — not approvable-shape
```

The repo-wide check is clean at this status (`4 artifact set(s), 0 approved`), which is the
correct state for a candidate in review.

---

## What is here

| File | What it is |
|---|---|
| `manifest.yml` | Reference id, surface, scope, status, author, the frozen SHA, and the lineage. |
| `baseline.yml` | §4 design memory + the §5 capability ledger for the board the Lab extends — 30 capability ids, the ruling lineage, the rejected variants, and the honest evidence gaps. |
| `proposal.yml` | A disposition for every baseline id, the Lab's own `additions`, the §6 user-task matrix, the §7 authority delta, and the information-economics audit. |
| `continuity.yml` | §13 closure over the r3 verdict's 10 blockers and 11 conditions — every item, by id. |
| *(no reviews, verdict or approval)* | See above. |

The blocker re-census the LAB-0 contract required is a separate document, because it is about
production rather than about this artifact:
**`research/prophet_v4/D_LAB_R5_BLOCKER_RECENSUS.md`**.

---

## The three things a reviewer should attack first

**1. Two authority claims are unwarranted at this SHA, and the packet says so itself.**
`auth.lab_observation_exists` and `auth.measured_lead` are `direction: stronger,
warranted: false`. Radar's live transport (R-LAB-1 / W4.1) has not landed, so every timing,
detector and observation-class fact in the fixture is **synthetic** — disclosed in
`DESIGN_NOTES` §4 and marked `data-mock-lab` in the DOM, with ticker, name, sector, the spark
SVG and the whole Prophet comparison taken real from the committed payload. **The open question
is whether a reference may be approved ahead of its producer.** That is a design-authority
call, not the author's, and it is deliberately left standing as a review-blocking finding
rather than argued away.

**2. R4 has never been independently reviewed, and R5 inherits that.**
The R4 closure cycle (`../prophet-board-5514-r4/`) answered the R3 `REVISE`, produced the
artifact this candidate loads unmodified, and stopped — minting no artifact set, no reviews and
no verdict. So `continuity.yml`'s `RESOLVED_BY_CHANGE` rows mean *"a checkable change exists in
the new SHA"*, **not** *"a critic agreed"*. The R5 cycle is the first opportunity to adjudicate
R4's own composition, and **a verdict that approves the Lab while leaving R4 unadjudicated would
launder ten unreviewed closures into canon**. `COND-RESUBMISSION` is recorded as `CARRIED_BLOCK`
for exactly this reason.

**3. Three of the twelve re-censused blockers are still open in production.**
Not caused by this cycle, and named so the MP-1 shell wave inherits an accurate list rather than
R4's five-day-old prose:

- **DA-002** — `templates/theme.css:80-81` and `:152-153` declare `--pv-buy` **byte-identical**
  to `--up` in both themes, so a shipped BUY chip and a shipped positive change still resolve to
  one hex. R4 fixed this inside its own stylesheet; production never received it.
- **PRC-303** — `templates/_us_board_cards.html.j2:96,99`: the chase caution's gate never
  consults the zone state, so "Don't chase above the buy zone" can still print on a card with no
  read and no zone.
- **VTC-301** (half) — production equalised the chartless hero's height but ships **no printed
  absence label**; the null is a hue-tinted void.

And the headline the other way: **both blockers R4 refused to waive are now closed** — G-D
(#5541, `5c9f31af1f1a`) and the overtime producer contradiction (#5540, `444f80d62774`), with
measured integers in the re-census.

---

## A deviation this packet had to make, recorded for the record

`research/reference_integrity/prophet-board-5514-r3/verdict.yml` was amended by this cycle:
its eleven `conditions` were bare strings and therefore **uncitable**, which
`check_reference_integrity.py` reports as `condition-without-id` the instant a successor exists
that must carry them forward (RIG §13.3 — and the rule's own prescribed fix is exactly this).
Each condition is now `{id, text}` with the `text` **byte-identical** to the string it replaced;
ids 1–8 are the blocker each condition remedies, 9–11 are minted. **No verdict content was
added, removed, softened or reordered.** The frozen evidence copy that record was judged against
is vendored and sha256-pinned separately at `../prophet-board-5514-r4/r3_source/verdict.yml` and
is untouched, so `build_ledger.py --check` is unaffected.

This is outside the D-LAB-R5 commission's owned-file list. It is called out here, and in the
session's return, so the commissioning session can accept or revert it deliberately rather than
discover it.

---

## Verification at the frozen SHA

| Harness | Result |
|---|---|
| `mockups/refs/prophet_lab/tools/verify.py` — the acceptance floor, run against the rendered page | **72/72** |
| `mockups/refs/prophet_lab/tools/mutation_test.py` — do the guards actually bite? | **13/13 caught**, each with a distinct killer, no shared sole catcher |
| `mockups/refs/prophet_lab/tools/capture.py` — the crop set | **36 views → 49 files**, every capture asserting its own state before shooting |
| `python3 scripts/check_reference_integrity.py` | clean (4 sets, 0 approved) |

Four of the first thirteen mutations **survived** the first version of the harness. Each hole
and its repair is written up in `DESIGN_NOTES` §5 — including one the R4 README had warned the
next cycle to look for, in a shape R4 had not seen: a **crashed** verify run reports no failures,
and "no failures" is indistinguishable from "clean" unless the runner is told otherwise.

**The crops are the deliverable. Green checks are a floor, not the acceptance.**
