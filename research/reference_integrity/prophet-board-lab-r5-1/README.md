# Prophet Operator Lab — RIG R5.1 packet (R5.2 fix round)

**Status: `draft`. Not approvable, and the review shape this cycle owes is written into its own
predecessor's conditions.** The R5 verdict's **C12** requires R5.1 to run the proper §6 two-pass
shape — both critics' first passes frozen **before any reveal**, then the rationale revealed for
genuine amendment passes. This session authored the artifact and is disqualified from all of it.

Artifact: `mockups/refs/prophet_lab/`, frozen at `f40ae70ac98936b5c565a7a55ddd108cb70ae7fa`
(R5.2). SHA lineage and what each first-pass critic found against the R5.1 SHA are in
`manifest.yml` → `sha_lineage`.
Design record: `mockups/refs/prophet_lab/DESIGN_NOTES.md` (§0a closes the R5 verdict; **§0b and
§0b.1 close the R5.2 round**).
Answers: `../prophet-board-lab-r5/verdict.yml` — **REVISE**, 3 majors + 18 conditions — and this
reference's own first-pass critics (below).

---

## The R5.2 fix round — read this first

Both first passes have run against `f889d5eb35f3080cf43136ad58bb780b1152c2dc` and both raised
findings: **product_regression = BLOCK** (1 blocker + 8 minors), **visual_taste =
PASS_WITH_CONDITIONS** (2 majors + 2 optional). This round answers all of them, which re-freezes
the artifact and therefore stales those receipts by construction (RIG §3). Ledger:
`continuity.yml` → `fix_rounds[R5.2]`.

**The blocker is the one to read.** `PR51-1`: the sticky class divider *never pinned*. It declared
`position: sticky` inside `.lab-stream { overflow: hidden }`, which makes the list a scrollport, and
a sticky child pins to its nearest scrollport — one that can never scroll. Measured by the critic at
390×844, 2,000px into the seed region: **four seed rows on screen, zero worded class labels.**
Meanwhile the packet booked `add.sticky_class_divider`, marked `lab.observation_class` IMPROVE, and
minted **BETTER** on *"the same guarantee, one constant instead of 23"* — a capability booked
against a mechanism that had never once fired, guarded only by a check that read the CSS
declaration.

That is the finding a reviewer should press hardest on, and the repair is deliberately shaped so the
class of defect cannot recur silently:

| | R5.1 | R5.2 |
|---|---|---|
| the mechanism | `overflow: hidden` on the list killed the pin | clip moved to the list's end members; the pin is real |
| what pins | one 25-word sentence (would have cost ~12% of a 390 viewport permanently) | the **constant** only — date, class badge, one governing sentence; the lesson scrolls away with the crossing |
| the check | `getComputedStyle(m).position === 'sticky'` | **D6c3 scrolls 1,200px past it and reads the rect**, at 1440 and 390 |
| the crops | all framed the divider at the crossing — the one place pinned and unpinned look identical | `51`/`52`/`53` shot 1,200px in; `capture.py` raises if the mark is not at top 0 |
| the mutation | `M18` made it `static` and was caught by the declaration check | `M22` re-adds the `overflow` and is caught **only** by `D6c3` |

Receipts at the new SHA — 1440: mark top **0px**, 9 seed rows on screen; 390: mark top **0px**,
4 seed rows on screen at scrollY 4,183.

The two visual-taste majors are folded into the same round. **R52-D1**: the constant VTL-408
targeted was *still printing* — every seed row kept `signal date / not a sighting`, so Law 4 had
been relocated rather than closed (the rail is now the unit label alone; `D6i` pins that the class
assertion appears exactly once). **R52-D2**: at 390×844 the LAB mode returned **zero** complete
observations above the fold; measurement showed compression could not fix it (the frozen ladder and
selectors account for 432px of a 550px budget), so three duplicate preamble lines demote to landings
and the region is **landed on flip** — with `D24b`/`D24c` pinning that this stays a navigation and
not the viewport hijack the standing veto forbids. Neither R51-M1 nor C4 is reopened.

---

## What changed, in one table

| R5 finding | Verdict | R5.1 |
|---|---|---|
| **VTL-401** LAB deleted the subtitle, ladder, Candidates, Groups, Evidence & Record, footer | major · contract breach | The mode paints `#setups` **and nothing else**. Everything else survives; the Lab sits in a bounded, labelled region with an explicit end rule. The ladder stays operable with one line saying a cell click returns to Live. |
| **VTL-402** six pills printed a literal `0` from a feed that was not answering | major | Unavailable prints an **em dash in a dashed box** on every pill, plus the line that makes it a statement. Empty keeps its real `0`. The two states are no longer pixel-identical. |
| **VTL-403** the lead flattered one way: accent ink when favourable, the *absence* idiom when adverse, `Math.abs` before the sign was read | major | Signed branches (`+3 +2 +1 0 −3`), `Math.abs` gone, adverse carries its **magnitude**, and every measured outcome shares **one ink** — the word changes, the volume does not. |
| **C1** re-derivation pinned only by the controller's own counter | condition | A snapshot mutation (**M17**) + a **sentinel** check (**D22**). Under M17 the counter **passed** and the sentinel **failed** — the condition was right, and it is now proven. |
| **C3** copy-law scans ran on one board, in EN, never on LIVE | condition | 14 views: 6 boards × 2 languages in LAB + both languages in LIVE. Found a defect in the *check*: `"validated"` fires on the ruled word *Invalidated*. |
| **C4** three of six frozen boards off-screen at 390 | condition | The scroller is **removed** — the pills wrap. All six on screen, no gesture to discover. *(R5.2/PR51-2: unconditional, not scoped to 980w — that scoping rested on a claim that measures false at 981w and depends on counts the surface does not control. D20d pins 1000w.)* |
| **C5** two re-census citations imprecise | condition | Both corrected with fresh receipts in `D_LAB_R5_BLOCKER_RECENSUS.md`. |
| **C10 · C11 · R51-C13 · R51-C14 · R51-C15** | conditions | Hex literal deleted; aria bilingual; retry + last-known-good stamp; "Showing N of M" with filter-responsive counts; "Live" de-overloaded. |
| **VTL-406 · 408 · 410 · 412 · 413** | minors, taken | Overlap disclosure; **pinned divider** replaces 23 per-row constants; Lab controls clear the touch floor at 390; the two synonymous disclaimer lines merged; the 390 rail stops breaking mid-phrase. *(R5.2: VTL-408 was only half-closed at R5.1 — the pin was inert (PR51-1) and the rail kept printing the constant (R52-D1). Both repaired; see the fix-round section above.)* |
| **VTL-404** | minor, **not taken** | Downgraded by its own critic on the reasoning the source already gave; the alternative costs the production board vertical space. Argued in DESIGN_NOTES §1.2. |
| **C2 · C6 · C7 · C8 · C12** | conditions on later waves / this cycle's process | `CARRIED_BLOCK` in `continuity.yml`. |
| **C9** | condition | Complied with; **this cycle amends no predecessor record at all.** |

Every row above has a check id and a crop behind it in `continuity.yml`.

---

## What is missing, on purpose

`reviews/product_regression.yml` · `reviews/visual_taste.yml` · `verdict.yml` · `approval.yml` —
all absent. A reference may not approve itself (RIG §6/§7), and R5's receipts are stale against
this SHA by construction (RIG §3), which is why this is a **new artifact set** rather than an edit
to `prophet-board-lab-r5`. The gate agrees:

```
$ python3 scripts/check_reference_integrity.py --evaluate prophet-board-lab-r5-1
… 10 finding(s): missing-review-receipt ("a new reference cannot approve itself"),
  unwarranted-authority-unadjudicated auth.lab_observation_exists,
  unwarranted-authority-unadjudicated auth.measured_lead, …
reference-integrity: prophet-board-lab-r5-1 is BLOCKED — not approvable-shape
```

Repo-wide check: clean, `5 artifact set(s), 0 approved`.

**Quarantine is still achievable, and that is deliberate.** Every rationale document lives outside
the artifact's runtime files — `DESIGN_NOTES.md` is the only prose inside `mockups/refs/prophet_lab/`
and it is separable, while `proposal.yml`, `continuity.yml`, this README and the re-census are all
elsewhere. The R5 visual-taste critic held strict quarantine against exactly this split; C12 asks
for both critics to.

---

## The three things a reviewer should attack first

**1. The two authority claims are still unwarranted, and one of them got stronger.**
`auth.measured_lead` now states results in **both** directions — which is the fix VTL-403 demanded
and also a wider claim than R5 made. Radar's live transport still has not landed, so the Lab plane
of the fixture remains synthetic (`DESIGN_NOTES` §4). The R5 verdict scoped this
`APPROVE_AHEAD_OF_PRODUCER_SCOPED`; nothing about R5.1 changes the dependency, and C6/C7 are
carried as blocks.

**2. The 390 fold is bought with a scroll, and that deserves scrutiny.** R5.1's answer to "no
observation row is above the fold at 390×844" was to disclose it as the unavoidable bill for R51-M1
and C4. R5.2 rejects that as a stopping point — disclosure is not service — and pays it two ways:
three duplicate preamble lines demote to landings, and **the Lab region is scrolled to the top of
the viewport when the reader flips into it**. The measurement that forced the second half is in
`continuity.yml` (first row at 1,009px, 294px tall, needs to start by 550px; the frozen ladder and
selectors are 432px of that), so compression alone was never going to reach it. The thing to attack
is whether landing the region is a legitimate navigation or the viewport hijack the standing
operator veto forbids. The packet's defence is three checkable properties, not an argument: it fires
only on a deliberate flip, the control the reader just pressed is what lands at the top (`D24b`),
and flipping back restores the scroll position they left (`D24c`). If a reviewer rules against it,
the fallback is to accept the fold and re-open the disclosure — **not** to reopen R51-M1 or C4,
both of which are intact.

**3. R4 is still unreviewed, and R5.1 does not change that.** C8 stands: R4's composition has never
had a §6 dual-critic pass, this artifact still loads R4 unmodified (empty diff re-verified at this
SHA), and approving R5.1 would not supply one. P-MP1-SHELL stays blocked absent that pass or an
explicit named override.

---

## Verification at the frozen SHA

| Harness | R5 | R5.1 | **R5.2** |
|---|---|---|---|
| `tools/verify.py` | 72/72 | 104/104 | **125/125** |
| `tools/mutation_test.py` | 13/13 | 19/19 | **26/26 caught**, distinct killers, no shared sole catcher |
| `tools/capture.py` | 36 views / 49 files | 39 views / 56 files | **46 views / 63 files**, all re-shot |
| `check_reference_integrity.py` | clean | clean | clean (5 sets, 0 approved) |
| `git diff origin/main -- mockups/refs/institutionalize templates/` | empty | empty | **empty** — the layering law both critics verified still holds |

The seven checks R5.2 adds are the ones the round exists for, and each is behavioural rather than
declarative: **D6c3** (the divider pins, read from the rect after a 1,200px scroll, at both widths),
**D6c4** (the pin clears the sticky chrome above it — 149px with `chrome=1`, 0 with `chrome=0`),
**D6i/D6i2/D6i3** (the class assertion is printed exactly once, no row rail makes one, and the two
rails differ), **D20d** (all six boards on screen at 1000w, the band no check had looked at), and
**D24/D24b/D24c** (one complete observation above the 390 fold in both languages; the flip does not
scroll its own control away; the landing is undone on the return). Seven new mutations attack them:
**M20**/**M21** (D4b/D4c, asserted since R5.1 and never proven to bite), **M22** (the shipped
defect — re-clip the stream), **M23** (repeat the class assertion on all 23 rails), **M24**/**M26**
(remove the landing, then never undo it), **M25** (hardcode the pin to `top: 0`).

Two mutations found holes rather than confirming intent, and both repairs are in the harness:
**M1** exposed that every seed check selected on `.lab-row--seed` and would have passed **over an
empty set** if that class stopped being emitted (`D6h` now pins the census to the payload — the
R4-warned vacuity trap in a third shape); **C3's sweep** exposed that the banned-vocabulary scan
fired on compliant copy. Written up in `DESIGN_NOTES` §5.
