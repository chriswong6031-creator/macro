# Prophet Operator Lab — RIG R5.1 packet

**Status: `draft`. Not approvable, and the review shape this cycle owes is written into its own
predecessor's conditions.** The R5 verdict's **C12** requires R5.1 to run the proper §6 two-pass
shape — both critics' first passes frozen **before any reveal**, then the rationale revealed for
genuine amendment passes. This session authored the artifact and is disqualified from all of it.

Artifact: `mockups/refs/prophet_lab/`, frozen at `f889d5eb35f3080cf43136ad58bb780b1152c2dc`.
Design record: `mockups/refs/prophet_lab/DESIGN_NOTES.md` (§0a is the closure map).
Answers: `../prophet-board-lab-r5/verdict.yml` — **REVISE**, 3 majors + 18 conditions.

---

## What changed, in one table

| R5 finding | Verdict | R5.1 |
|---|---|---|
| **VTL-401** LAB deleted the subtitle, ladder, Candidates, Groups, Evidence & Record, footer | major · contract breach | The mode paints `#setups` **and nothing else**. Everything else survives; the Lab sits in a bounded, labelled region with an explicit end rule. The ladder stays operable with one line saying a cell click returns to Live. |
| **VTL-402** six pills printed a literal `0` from a feed that was not answering | major | Unavailable prints an **em dash in a dashed box** on every pill, plus the line that makes it a statement. Empty keeps its real `0`. The two states are no longer pixel-identical. |
| **VTL-403** the lead flattered one way: accent ink when favourable, the *absence* idiom when adverse, `Math.abs` before the sign was read | major | Signed branches (`+3 +2 +1 0 −3`), `Math.abs` gone, adverse carries its **magnitude**, and every measured outcome shares **one ink** — the word changes, the volume does not. |
| **C1** re-derivation pinned only by the controller's own counter | condition | A snapshot mutation (**M17**) + a **sentinel** check (**D22**). Under M17 the counter **passed** and the sentinel **failed** — the condition was right, and it is now proven. |
| **C3** copy-law scans ran on one board, in EN, never on LIVE | condition | 14 views: 6 boards × 2 languages in LAB + both languages in LIVE. Found a defect in the *check*: `"validated"` fires on the ruled word *Invalidated*. |
| **C4** three of six frozen boards off-screen at 390 | condition | The scroller is **removed** below 980w — the pills wrap. All six on screen, no gesture to discover. |
| **C5** two re-census citations imprecise | condition | Both corrected with fresh receipts in `D_LAB_R5_BLOCKER_RECENSUS.md`. |
| **C10 · C11 · R51-C13 · R51-C14 · R51-C15** | conditions | Hex literal deleted; aria bilingual; retry + last-known-good stamp; "Showing N of M" with filter-responsive counts; "Live" de-overloaded. |
| **VTL-406 · 408 · 410 · 412 · 413** | minors, taken | Overlap disclosure; **sticky divider** replaces 23 per-row constants; Lab controls clear the touch floor at 390; the two synonymous disclaimer lines merged; the 390 rail stops breaking mid-phrase. |
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

**2. The R51-M1 fix costs a fold at 390, and the packet says so.** With the ladder restored above
the Lab region and six selectors wrapped into three rows, **no observation row is above the fold at
390×844** — R5 got one there. That is the bill for two capabilities the verdict ruled
non-negotiable. Crops `14`, `34`, `42`, `45`, `48` show it. If a reviewer wants it back, the lever
is the ladder's position, not the selector wrap: re-hiding boards is the defect C4 exists to stop.

**3. R4 is still unreviewed, and R5.1 does not change that.** C8 stands: R4's composition has never
had a §6 dual-critic pass, this artifact still loads R4 unmodified (empty diff re-verified at this
SHA), and approving R5.1 would not supply one. P-MP1-SHELL stays blocked absent that pass or an
explicit named override.

---

## Verification at the frozen SHA

| Harness | R5 | R5.1 |
|---|---|---|
| `tools/verify.py` | 72/72 | **104/104** |
| `tools/mutation_test.py` | 13/13 | **19/19 caught**, distinct killers, no shared sole catcher |
| `tools/capture.py` | 36 views / 49 files | **39 views / 56 files**, all re-shot |
| `check_reference_integrity.py` | clean | clean (5 sets, 0 approved) |
| `git diff origin/main -- mockups/refs/institutionalize templates/` | empty | **empty** — the layering law both critics verified still holds |

Two mutations found holes rather than confirming intent, and both repairs are in the harness:
**M1** exposed that every seed check selected on `.lab-row--seed` and would have passed **over an
empty set** if that class stopped being emitted (`D6h` now pins the census to the payload — the
R4-warned vacuity trap in a third shape); **C3's sweep** exposed that the banned-vocabulary scan
fired on compliant copy. Written up in `DESIGN_NOTES` §5.
