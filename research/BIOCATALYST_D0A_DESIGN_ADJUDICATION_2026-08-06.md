# BC-D0a — named design adjudication

| Field | Binding value |
|---|---|
| Ruling | **AMEND** — the information architecture is accepted and frozen; the reference *pack* is rejected as the D0b implementation target |
| Reviewer role | `fable_or_opus_design_owner` |
| Named reviewer | Claude Fable 5, commissioning session (BioCatalyst remaining-waves program) |
| Recorded at | 2026-08-06 |
| Audited base | `origin/main` at `b70deb5cf817c5ed32d6de2f07bfaa82717c51d8` |
| Subject | `config/biocatalyst_product_acceptance.yml` (`biocatalyst_product_acceptance_506244f236be52f12a8eaa96`, state `draft_human_approval_pending`) and its 24 plates under `mockups/refs/biocatalyst/d0a/` |
| Design spec under review | `research/BIOCATALYST_D0A_IA_STATE_CONTENT_CONTRACT.md` |
| Content law applied | `docs/DESIGN_DOCTRINE.md` (wins on conflict) |
| Visual bar applied | `frontend-design:frontend-design` skill |
| Authorizes | **Nothing.** This ruling is an input to a successor contract. It does not release UI, activate a source, change entitlements, promote a model, or touch Neural Web / Prophet authority. |

This adjudication discharges the W0-B gate in
`research/BIOCATALYST_REMAINING_BUILD_WAVES_HANDOFF_FOR_CLAUDE_2026-08-06.md` §5. A builder
could not have issued it; it is recorded here so the successor contract can bind it by hash.

---

## 0. Method — what was actually looked at

The ruling rests on opening the artifacts, not on reading their description. Plates opened
at full size and judged as designs:

- `mockups/refs/biocatalyst/d0a/d0a_desktop_dark_en_standard.png`
- `mockups/refs/biocatalyst/d0a/d0a_mobile_light_zh_standard.png`

Every defect below cites the plate it is visible in. Defects asserted without a plate
citation are not in this ruling.

---

## 1. Accepted and frozen — do not redesign these

These parts of D0a are correct, distinctive, and become binding inputs to D0b. A D0b PR that
changes any of them is out of scope and must be rejected at review.

1. **The seven-surface information architecture** (`§2`) — Radar, Explorer, Dossiers, Change
   Tape, Workbench, Alerts, Data/API. It maps to real jobs and does not fragment into
   mini-products.
2. **The shared-frame rules** (`§2`) — one frame, one evidence grammar, no per-surface
   reinvention.
3. **The Evidence Thread with an exact source locator.** The right-hand pane in
   `d0a_desktop_dark_en_standard.png` prints `/protocolSection/statusModule/overallStatus` —
   a literal JSON pointer into the source record, alongside the record excerpt and the
   submitting version (`v9 · submitted 15:42 UTC`). This is the single best idea in the pack.
   It is what a facts-first product should feel like and no benchmark competitor does it.
   **Freeze it and make it the signature element.**
4. **The Research Tray** (`§2`) — pinned questions persisting across surfaces.
5. **The twelve-rank deterministic state precedence table** (`§4`) and its tie-break
   (earliest `known_at`, then lexical state code). Correct and complete; adopt verbatim.
6. **The five non-optional adjacent cues** (`§1`) — Fact class, Time, Provenance,
   Completeness, Authority. The *cues* are right. Their **placement** is not (defect D5).

---

## 2. Rejected — four named defects, each with plate evidence

### D1 · Bilingual parity failure — HARD FAIL

`d0a_mobile_light_zh_standard.png` renders a Chinese surface containing untranslated English:

| Rendered on the ZH plate | Class of defect |
|---|---|
| `状态 / CHANGE TAPE CORRECTION` | raw English machine state enum inside ZH chrome |
| `Primary endpoint` · `Enrollment` · `Record correction` · `Site listing` | untranslated English field names, all four rows |
| `之前: Week 12 response` · `之前: 160 estimated` · `之前: Earlier value retained` · `之前: 14 locations` | ZH label welded to a raw English value |

This is the defect `docs/DESIGN_DOCTRINE.md` §5.5 names by example (`慢速评级: HOLD` is a
defect) and that D0a's own `§3.4` forbids in its own words — Chinese copy must be native
concise product copy, "never a raw English token drop." The reference pack violates the
contract it is the reference for.

The failure is not "the translation is wrong." It is that the ZH surface is **English-shaped**:
the layout, the field inventory, and the sentence rhythm were designed in English and had
Chinese chrome applied around them. Native ZH product copy is shorter, drops the copula, and
names the object before the qualifier. A D0b built from this reference ships the defect.

**Ruling:** ZH is a first-class design target, not a translation pass. D0b must produce ZH
copy authored against a fixed glossary, and the successor contract must carry a
machine-checkable gate: **no Latin-script token may appear in a ZH-locale Tier-1 string**
except a whitelisted proper noun (`ClinicalTrials.gov`, `FDA`, `NCT########`, ISO dates,
units). This gate is testable and must be tested.

### D2 · No stance anywhere — DESIGN_DOCTRINE Law 1

Every plate shows state and never answers *so what do I do*.
`d0a_desktop_dark_en_standard.png` prints four rows of source-reported dates and a right pane
of provenance; a cold reader learns what the record says and nothing about what to do next.

The root cause is a genuine collision the draft never resolved, and this is the most important
finding in the ruling:

> **DESIGN_DOCTRINE Law 1 requires a stance on every panel. Its stance vocabulary
> (Act / Get ready / Watch — don't chase / Protect gains / Stand aside / Ignore) is a
> *market* vocabulary. The BioCatalyst authority boundary forbids BioCatalyst from
> holding a market stance at all.**

The draft resolved this by having no stance, which fails Law 1. The correct resolution is that
**BioCatalyst's stance is a research stance**, in the same plain-word grammar, scoped to what a
facts platform can honestly tell someone to do. Minted here as binding vocabulary:

| Research stance | When it fires | Plain ZH |
|---|---|---|
| **Read the record** | current, complete, uncontested | 记录可直接看 |
| **Check the source** | something moved, or coverage is partial — go to the exact locator | 去核对来源 |
| **Wait for the record** | not knowable yet from this source; nothing has posted | 等记录更新 |
| **Reconcile the conflict** | two sources disagree; the contradiction rail holds the pair | 两处对不上 |
| **Treat as historical** | an as-known-at view; today's record differs | 这是当时的记录 |
| **Nothing here** | empty result or unavailable dependency — and why | 暂无内容 |

These are stances, not signals. None ranks, scores, sizes, or directs a trade, so the A0/A1
authority ceiling is intact and `DNR:KILL-PHASE3-START-WEIGHT` is untouched.

### D3 · A constant repeated on every row — Law 4

`d0a_desktop_dark_en_standard.png`: all four Catalyst Radar rows carry the identical secondary
line `Source-reported completion constraint`. This is the exact anti-pattern
`docs/DESIGN_DOCTRINE.md` §Law 4 names ("the old strip printed 'T+1 58% fade' on every row — a
constant belongs in the footer, once"). Four rows spend their entire secondary line saying
nothing that distinguishes them.

The same plate also prints `Next 30 days · 04 source-bound records` — a zero-padded machine
count at Tier 1.

**Ruling:** a constant moves to the panel footer, once. Row secondary lines must carry what
differs between rows — for Catalyst Radar, that is the *date type and its precision source*
(company guidance vs registry timing vs regulator-confirmed), which is exactly what the
program's §10 W5-B requires anyway.

### D4 · A graphic that carries no meaning — Law 3

The "Source timeline" panel in `d0a_desktop_dark_en_standard.png` is eight bars of varying
height with no axis, no units, no scale, and no interpretation, captioned
"Known-at order keeps the earlier record visible." A reader cannot say what the bars measure or
what a tall bar means. Under Law 3 it is decoration, and decoration on a facts-first product is
a credibility cost, not a neutral one.

It is also occupying the place where this product's actual differentiator belongs. Every
BioCatalyst fact carries **two clocks**: when it was true (effective / as-of) and when we knew
it (known-at). The gap between them is the whole point of a point-in-time evidence product, and
nothing in the pack renders it.

**Ruling:** replace the meaningless bar chart with the two-clock primitive specified in §3.

### D5 · Tier mis-assignment and dead space

The four-cell strip `Fact class · As known · Precision · Coverage` in
`d0a_desktop_dark_en_standard.png` is a `label: value` grid. `docs/DESIGN_DOCTRINE.md` §1 puts
structured `label: value` on **Tier 2**. It currently occupies the widest, highest band of the
main pane — the most valuable real estate on the page — and pushes the actual content down,
leaving roughly a third of the main pane empty below the rows.

**Ruling:** the five cues survive (they are accepted in §1.6) but move — inline into the
Decision Sentence line and the row anatomy, with full precision on hover. Tier 1 shows meaning;
Tier 2 shows the grid.

### D6 · Light mode is a token swap, and both themes sit on an AI default

`d0a_mobile_light_zh_standard.png` is the dark plate with inverted tokens: same geometry, same
proportions, cream ground, no re-considered depth or ink weight.
`docs/DESIGN_DOCTRINE.md` §5.8 is explicit — "light is a design target, not a translation" — and
lists the idioms that must carry an explicit `html[data-theme="light"]` counterpart.

Separately, judged against the `frontend-design` calibration: the dark plate is near-black with
a single teal accent, and the light plate is a warm cream with a serif-ish display. Those are
respectively defaults #2 and #1 on the skill's list of looks that appear regardless of subject.
Neither is derived from this subject's world.

**Ruling:** D0b derives its palette and type from the subject (clinical-registry record
material — versioned documents, submission stamps, JSON pointers, redline diffs), not from a
generic dashboard default. One risk, justified, per §3.4.

---

## 3. Binding additions — the two primitives the handoff names and D0a never defined

`research/BIOCATALYST_REMAINING_BUILD_WAVES_HANDOFF_FOR_CLAUDE_2026-08-06.md` §7 W2-A orders
D0b to implement a **Decision Sentence** and a **Temporal Braid**. Neither term appears anywhere
in `research/BIOCATALYST_D0A_IA_STATE_CONTENT_CONTRACT.md`. That is a real discrepancy between
the two governing documents, and it is resolved here by definition rather than by dropping
either — both name a real gap the plates demonstrate (D2 and D4).

### 3.1 Decision Sentence *(resolves D2)*

One line, first thing in the main pane, above the fold, on every surface.

```
<RESEARCH STANCE> — <the one reason, in plain words>
```

- Stance from the §2/D2 table only. No other vocabulary is legal.
- Total budget **≤ 14 words EN**; **≤ 24 characters ZH**. Hard limit, enforced at review.
- The reason names what changed or what is missing — never a statistic, never a study ID,
  never a state enum, never a falsifier.
- When the honest stance is *Nothing here*, it still ships. An empty surface with a Decision
  Sentence is compliant; an empty surface without one is not.
- Banned inside it: `signal`, `score`, `rank`, `forecast`, `probability`, any trade directive,
  any internal state code, and — per the operator ruling of 2026-07-27 — any
  falsifier/refutation language (`falsifier fired`, `thesis refuted`, `证伪`). Tripwires keep
  evaluating in the background; the user-facing form is "what we're watching".

Worked example, replacing the D3 Catalyst Radar header:

> **Check the source** — the completion date moved twice this week.

### 3.2 Temporal Braid *(resolves D4)*

The two-clock primitive. Renders **effective time** (when the fact was true) and **known-at
time** (when we learned it) as one object, so the lag between them is directly visible.

Required behavior:

- Two parallel tracks, effective above known-at, sharing one horizontal time scale that is
  **labelled with units**.
- Each record is one mark on each track, joined by a connector whose length *is* the reporting
  lag. Long connector = the source told us late. That is the reading, and it must be stated in
  words in the panel footer, once.
- Corrections render as a branch off the original mark, never as a replacement of it —
  the original stays visible. This is the visual form of the append-only law.
- Historical / as-known-at mode moves a single playhead; the braid does not re-render into a
  different shape.
- Reduced motion: the braid is fully readable with no animation. Motion may only ease the
  playhead. No information may live in the animation.
- Accessible: every mark is keyboard-reachable with a text equivalent naming both clocks. It
  must satisfy `no_hover_only_meaning`, already required by all 24 cells.

The braid is the **signature element** of this product. Per the visual-bar discipline, it is
where boldness is spent; everything around it stays quiet.

### 3.3 The bilingual gate *(resolves D1)*

A ZH-locale Tier-1 string may contain a Latin-script run only if it is a whitelisted proper
noun: `ClinicalTrials.gov`, `FDA`, `NCT########`, an ISO-8601 date/time, a unit, or a
version token (`v9`). Everything else must be native ZH. This is machine-checkable and the
successor contract must require a test that fails on a violation.

### 3.4 Visual direction

Derive from the subject: this product's material is the **versioned regulatory record** — a
document that was submitted at a time, by someone, and can be pointed into. The vocabulary of
that world is submission stamps, version numbers, JSON pointers, redlines, and the gap between
filing and knowing. The palette, the type pairing, and the signature element must come from
there. Neither of the two defaults observed in D6 is acceptable as a starting point. Light and
dark are two designs, and the light one is judged as a design.

---

## 4. The irreducible blocker — and what it actually costs

`tests/test_biocatalyst_d0a_design_contract.py:245-300` proves something the handoff's wave map
does not account for:

> Even with a fully materialized repo — real files, real hashes, approval / performance /
> per-cell fields all set to approved-and-passed, and a well-formed fabricated measurement
> receipt — the manifest still fails on exactly one code:
> **`product_acceptance.trusted_browser_verifier_unavailable`**.

No self-authored artifact can ever clear it. It requires an independent verifier component
**that does not exist in this repository**. Consequences that must be stated plainly:

1. **This ruling alone cannot make D0b acceptable.** A named design approval was necessary and
   is now recorded, but it is not sufficient. Anyone reading the wave map as "get the design
   approved, then D0b can pass" is wrong.
2. **The verifier is an unscheduled prerequisite lane.** It must render the real page in a real
   browser across the frozen 24-cell matrix and emit a receipt whose trust does not derive from
   the manifest it validates.
3. **The v1 manifest cannot be edited into a passing state, at all.** `state` is const-locked to
   `draft_human_approval_pending` at the schema level, both `supersedes_*` fields are const
   null, and all six `authorizes_*` flags are const false. A successor is a **new contract id
   and a new schema**, never a mutation of v1. `tests/test_biocatalyst_d0a_design_contract.py`
   asserts every one of these and must keep passing unchanged.

**Ruling:** the successor contract (`biocatalyst_product_acceptance_manifest.v2`) and the
trusted browser verifier are one lane, because a successor without a verifier is a contract
that provably cannot be satisfied.

---

## 5. What this ruling authorizes and forbids

**Authorizes:** drafting a v2 successor contract that binds this ruling by hash; building a
trusted browser verifier; and beginning D0b implementation against §1 (frozen) and §3 (added).

**Forbids, explicitly:**

- editing `config/biocatalyst_product_acceptance.yml` or its v1 schema into any non-draft
  state, or weakening any assertion in `tests/test_biocatalyst_d0a_design_contract.py`;
- treating this ruling as a UI release, a source activation, an entitlement change, a model
  promotion, or any Neural Web / Prophet authority;
- claiming a browser capture, a performance measurement, a soak, or an operator decision
  happened;
- shipping any of the 24 plates as production truth. They remain **draft contract-state
  plates**, non-portable, non-authorizing — and after D1/D3/D4 they are explicitly **not** the
  D0b implementation target.

---

## 6. Hand-off to D0b

D0b implements, in the existing shell only
(`templates/biocatalyst.html.j2` / `.css` / `.js`, `scripts/build_biocatalyst.py`) — no
`biocatalyst-v2`, no second SPA, no browser-side truth store:

1. §1 frozen IA, shared frame, Evidence Thread with exact source locator, Research Tray,
   twelve-rank state precedence.
2. §3.1 Decision Sentence on every surface, with the research-stance vocabulary.
3. §3.2 Temporal Braid replacing the Source-timeline decoration.
4. §3.3 bilingual gate, tested.
5. Row anatomy carrying what differs; constants in the footer, once (D3).
6. The five cues inline at Tier 1, full precision at Tier 2 (D5).
7. Light and dark as two designs (D6).

Acceptance for D0b is the browser-verified matrix under the v2 contract, not these plates.
