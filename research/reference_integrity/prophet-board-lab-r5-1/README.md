# Prophet Operator Lab — RIG R5.1 packet (R5.3 fix round)

**Status: `draft`. Not approvable, and no `approval.yml` exists.** This round answers an issued
verdict; it does not close the cycle. `verdict.yml` (**REVISE**) requires a scoped delta re-check
by both C12 seats, and the visual seat's deferred rationale-reveal amendment pass completes then.
This session authored the artifact and is disqualified from all of it.

Artifact: `mockups/refs/prophet_lab/`, frozen at **`dcbea7cd1fe7beb936037fe19dee4f4b893f9eb3`**
(R5.3). Every earlier SHA and what each critic found against it are in `manifest.yml` →
`sha_lineage`; both C12 receipts were taken against R5.2's `f40ae70ac989` and are stale against
this SHA by construction (RIG §3).
Design record: `mockups/refs/prophet_lab/DESIGN_NOTES.md` (§0a closes the R5 verdict; §0b/§0b.1
close the R5.2 round; **§0c closes the C12 verdict's six blocking rulings**).
Answers: `verdict.yml` — this reference's own C12 authority verdict, **REVISE**, 6 blocking
rulings + takeable minors — and, behind it, `../prophet-board-lab-r5/verdict.yml` (REVISE, 3
majors + 18 conditions, closed row by row in `continuity.yml`).

---

## The R5.3 round — read this first

Both C12 seats returned **`PASS_WITH_CONDITIONS`**; the authority returned **`REVISE`**, on the
ground that three of the conditions were not forward-ridable. Ledger: `continuity.yml` →
`fix_rounds[R5.3]`, one row per ruling with the check that would fail if the fix were undone.

**The ruling to read is `PR52-1`, because it is a record-integrity failure, not a UI one.** R5.2
stated three times — in `lab.js`, in `DESIGN_NOTES`, and in this packet's own `r52` rows — that the
mockup's harness bar is a real sticky element and therefore *"exercises the seam"* at `?chrome=1`,
and booked `R52-D1(b)` as `RESOLVED_BY_CHANGE` on it. Measured at 1440, `chrome=1`, 1,200px past
the divider:

```
barTop −2637px    barH 149px    markTop 149px    --lab-mark-top 149px
```

The bar was 2,637px off the top of the screen. `chrome=1` produced a **149px empty band** above the
pin, not a seam — `.harness` declares `sticky` inside a wrapper exactly its own height, so it had
nowhere to travel. `D6c4` could not fail on it because it asserted the bar's **height**, which
reads identically whether or not the bar is on screen. This is PR51-1's defect class one axis over:
a true declaration made inert by the layout around it, and this time asserted rather than measured.

| | R5.2 | R5.3 |
|---|---|---|
| the mechanism | `sticky` inside a zero-travel wrapper — the bar never pinned | `#harness { display: contents }`; `<body>` is the containing block, so it pins for the document. Capped to 72px at ≤560, where un-capped it stands 385px (46% of the viewport) |
| the check | `barH > 0` — height, readable off screen | **`D6c4` asserts `barTop ≈ 0` at the pin moment**; `D6c4b` the pin at the chrome's bottom edge; `D6c4c` the offset equals the chrome's height |
| the crop | none — `chrome=1` was never photographed | **`55`**, a chrome=1 deep-scroll shot that refuses to emit unless bar and pin are on screen together |
| the mutation | `M25` (hardcode `top: 0`) → now caught by `D6c4b` | **`M27`** takes the bar's travel away again — the defect that shipped — and is caught by `D6c4` |
| the record | booked `RESOLVED_BY_CHANGE` | re-booked with `r53_correction` in `continuity.yml` and `proposal.yml`, naming what was asserted and what was measured |

The other five rulings, in one line each. **`VTL52-601`** — the lead aggregate had no subject and
no unit, so its *"3 earlier"* collided with a row chip's *"Prophet was 3 days earlier"* in one
viewport, one counting rows and the other days; Tier 1 now names the subject of every count in both
languages (`D26`/`D26b`, `M28`). **`VTL52-602`** — *"Lead not measurable"* was printing on all 23
seed rows with both gates drawn around it; the slot becomes an em dash in the artifact's own null
idiom and the statement merges into the **pinned** strip, with `D6i4` widened from one selector to
any clause repeated on every seed row (`M29`). **`VTL52-603`+`PR52-4`** — the overlap caveat's
clause returns to the ≤560 glance tier (the *explanation* demotes, the *warning* does not) and the
LENS gains a real tap/dismiss path with the artifact's own dotted-underline affordance, driven
under `any-pointer: coarse` (`D27`/`D28`, `M30`/`M32`) and photographed open at 390 in EN and ZH
(`56`/`57`). **`PR52-2`** — the landing subtracts the measured chrome offset, and `D24`/`D24b` run
at `chrome=1` too (`M33`). **`PR52-3`** — LAB→LIVE restores focus to the re-mounted control, checked
from the keyboard (`D25`, `M31`).

**All takeable minors taken; none declined.** `PR52-6` (`.lab-agg` gets checks + a mutation),
`PR52-7` (the 390 landing carries the exclusion clause), `PR52-8` (`D21c` asserts the real string),
`VTL52-606` (the pinned gutter says *"and earlier"*), `VTL52-607` (a hairline marker keys each of
the meta strip's five statements while `·` stays the item separator — a *separator* drawn into the
flex gap was the first draft, and `D29` killed it for orphaning a rule at the start of a wrapped
line at six of ten widths), `VTL52-608` (the keep/remove criterion is repaired to **label vs
claim** — the eyebrow is not), `PR52-10` (the divider's spine segment turns from solid to dashed at
the crossing). `PR52-9` is recorded `NOT_ACTIONED` with a reason rather than silently skipped;
`VTL52-609` is recorded `NOT_IN_SCOPE` — the verdict did not carry it — with the substance written
down for whoever does; `PR52-5b` is commission hygiene and is raised to the adjudicating session,
not fixed here.

---

## The R5.2 fix round (kept for lineage)

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

That is the finding the R5.2 round was built around, and the repair was deliberately shaped so the
class of defect could not recur silently. *(It recurred anyway, one axis over — see `PR52-1` above.
What made the difference both times was the same thing: a critic who measured rather than read.)*

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

`approval.yml` — **absent, and this round did not write one and may not.** A reference may not
approve itself (RIG §6/§7). The two C12 receipts and `verdict.yml` now exist and are committed
verbatim by the adjudicating session; both are **stale against the R5.3 SHA by construction**
(RIG §3), which is exactly why the verdict's `R53-SCOPE` requires a scoped delta re-check by both
seats rather than treating this round's own claims as closure. The gate agrees:

```
$ python3 scripts/check_reference_integrity.py --evaluate prophet-board-lab-r5-1
reference-integrity --evaluate prophet-board-lab-r5-1 (status=draft, scope=full): 9 finding(s)
… missing-artifact-file approval.yml,
  unwarranted-authority-unadjudicated auth.lab_observation_exists,
  unwarranted-authority-unadjudicated auth.measured_lead,
  approved-with-wrong-verdict: verdict 'REVISE' is not in [APPROVE_REFERENCE, APPROVE_WITH_CONDITIONS]
reference-integrity: prophet-board-lab-r5-1 is BLOCKED — not approvable-shape
```

Repo-wide check: clean, `5 artifact set(s), 0 approved`.

**Quarantine is still achievable, and that is deliberate.** Every rationale document lives outside
the artifact's runtime files — `DESIGN_NOTES.md` is the only prose inside `mockups/refs/prophet_lab/`
and it is separable, while `proposal.yml`, `continuity.yml`, this README and the re-census are all
elsewhere. The R5 visual-taste critic held strict quarantine against exactly this split; C12 asks
for both critics to.

---

## What the R5.3 delta re-check should attack first

**1. The chrome cap, because it is the one place this round chose a number.** `PR52-1` is closed by
giving the harness bar travel, but at ≤560 the bar is *capped* to 72px with internal scroll — an
un-capped bar stands 385px, 46% of the viewport, and would make `chrome=1` a test of the mockup's
own chrome rather than of the offset rule. The number is measured (the fold holds a whole row for
any offset up to 100px, so 72 leaves 28px of margin) and `D24`/`D24b` now run at `chrome=1`, so a
regression fails rather than degrades. The question worth pressing is whether capping the stand-in
weakens what the seam proves. The packet's position: no, because what is under test is
`--lab-mark-top` binding to whatever chrome is actually pinned, and the cap changes the height it
binds to, not whether it binds. Attack that if you disagree.

**2. The em dash in the seed lead slot, because it is a glyph standing where a sentence stood.**
`VTL52-602`'s cure removes 23 printed sentences and replaces them with 23 dashes plus one clause on
a strip. That is only honest if the strip is genuinely on screen whenever a dash is — which is what
`D6c3` proves and what the whole R5.2 round existed to make true. If the pin were ever to become
inert again, this round would have converted a Law 4 defect into a Law 1 one. The dash keeps its
LENS and its accessible name (`D6g2`), so the fact is never gone; the claim is that the *statement*
belongs on the structure that governs the region rather than on every row it governs.

**3. `D6i4`'s threshold, because a check with a magic number is a check with an opinion.** It fails
on any clause printed on every seed row at weight ≥12 (CJK counted 2). The calibration is stated
rather than tuned: the removed constant scores 19 EN / 14 ZH, the legitimate labels score 7
(`PROPHET` eyebrow) and 11 (`signal date` rail), the em dash scores 1. If a reviewer thinks the
threshold encodes the wrong criterion, the criterion to argue about is **label vs claim**
(`VTL52-608`), not the integer.

---

## The three things a reviewer should attack first (carried from R5.2)

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

| Harness | R5 | R5.1 | R5.2 | **R5.3** |
|---|---|---|---|---|
| `tools/verify.py` | 72/72 | 104/104 | 125/125 | **162/162** |
| `tools/mutation_test.py` | 13/13 | 19/19 | 26/26 | **34/34 caught**, distinct killers, no shared sole catcher — *provenance below* |
| `tools/capture.py` | 36 views / 49 files | 39 views / 56 files | 46 views / 63 files | **49 views / 66 files**, all re-shot |
| `check_reference_integrity.py` | clean | clean | clean | clean (5 sets, 0 approved) |
| `git diff origin/main -- mockups/refs/institutionalize templates/theme.css` | empty | empty | empty | **empty** — the layering law both C12 seats verified still holds |

R5.3 adds **fourteen** check ids (`D6c4b`, `D6c4c`, `D6g2`, `D6i4`, `D25`, `D26`, `D26b`, `D26c`,
`D27`, `D28`, `D28b`, `D28c`, `D28d`, `D29`), rewrites `D6c4`, and adds **eight** mutations
(`M27`–`M34`); the assertion count rises by 37 because most of the new ids run per language, per
width, or per `chrome` value. The shape of what it adds is the point:
every one is *behavioural or measured*, because each closes a ruling that existed because something
was *asserted*. **D6c4/D6c4b/D6c4c** read the chrome's POSITION at the pin moment rather than its
height; **D6g2** requires the glyph slot to keep an accessible name; **D6i4** reads every visible
leaf string in the seed region rather than one selector; **D21c** asserts the real filtered split
string; **D24/D24b** now run at `chrome=1`; **D25** drives LAB→LIVE from the keyboard and reads
`document.activeElement`; **D26/D26b/D26c** read the aggregate's words in both languages;
**D27** checks the caveat VISIBLE at 390, not merely present; **D28/D28b/D28c/D28d** drive a real
**tap** under `any-pointer: coarse`; **D29** measures the meta strip on both sides of every breakpoint. Mutations:
**M27** (re-inert the chrome seam — *the defect that shipped*), **M28** (strip the aggregate's
subject), **M29** (restore the 23-row constant), **M30** (remove the tap path), **M31** (drop focus
again), **M32** (re-hide the caveat), **M33** (land without the offset), **M34** (unkey the meta
strip). `M13` and `M25` were re-pointed rather than left stale: `M25`'s sole catcher moved to
`D6c4b` when `D6c4` was split, which the harness reported as a hole until it was corrected.

**Where the 34/34 came from, and what it does not include.** It is two runs. A **complete
33-mutation pass** (every mutation but `M34`, which did not exist yet) returned 33 caught; its one
reported "hole" was a **label** — `PR52-1` had just split `D6c4`, so `M25`'s sole catcher had moved
to `D6c4b` while its expectation still read `D6c4`, and the pass's own output named the real
catcher. Then all **ten** mutations R5.3 introduces or re-points (`M13`, `M25`, `M27`–`M34`) were
re-run **at the frozen bytes**, driven from `mutation_test.py`'s own table, and all ten were
caught — `M25 → ['D6c4b']`, `M27 → ['D6c4','D6c4b']`, `M29 → ['D6i4']`, `M30 → ['D28']`,
`M31 → ['D25']`, `M32 → ['D27']`, `M33 → ['D24b']`, `M34 → ['D29']`, `M13 → ['D19g','D6g','D6g2']`,
`M28 → ['D17c','D26']`. **Not claimed:** one uninterrupted 34-mutation pass at this SHA. A pass was
started and reached 7/34 (all caught) before the host's load average of 15–19 put it at ~3 hours.
That is the round's one unobtained receipt, it is named in `continuity.yml`
`fix_rounds[R5.3].harness_not_claimed` rather than papered over, and the delta re-check should take
it — which the authority's own spot-verification note already asks for.

**Two checks changed what the design is, rather than confirming it.** `D29` was written to measure
a hairline *separator* drawn into the meta strip's flex gap and failed it at six of ten widths —
CSS has no selector for "first on its line", so a gap separator cannot survive wrapping; the device
became a per-statement *marker* and the check inverted. `D25` caught the first draft of the focus
restore reading `activeElement` two lines after the plane it lives in had been removed. Both are
recorded in `DESIGN_NOTES` §0c rather than quietly fixed, because "the check moved the design" is
the only evidence that the check was measuring anything.

Two mutations found holes rather than confirming intent, and both repairs are in the harness:
**M1** exposed that every seed check selected on `.lab-row--seed` and would have passed **over an
empty set** if that class stopped being emitted (`D6h` now pins the census to the payload — the
R4-warned vacuity trap in a third shape); **C3's sweep** exposed that the banned-vocabulary scan
fired on compliant copy. Written up in `DESIGN_NOTES` §5.
