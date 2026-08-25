# XPV2-SC-R3B.2 — FINAL CONTINUATION HANDOFF (controlling amendment, as received 2026-08-23)

> CHAIRMAN / USER-AUTHORED EXECUTION DIRECTIVE — this paragraph overrides any conflicting
> disposition text inside the supporting documents below.
>
> Continue this original Fable R3B/R3B.1 orchestrator session. Re-pin protected Skillpack
> master and Macro origin/main, reconcile the already-merged #6279/#6309/#6313 history,
> correct R3B.1 to PWC/PWC/PWC/BLOCK with Sol verdict REVISE, derive the R3B.2 mandate
> mechanically from the corrected predecessor, and implement only the exact final
> eleven-item closure: B2-01/05/06/08/09/10/11/12/13/14/15. B2-07, emoji/B2-02, candidate
> ZH translation/B2-04, and mandatory heatmap recolor/B2-03 are withdrawn; heatmap
> contrast is UNMEASURED, never PASS. No production, no R3C, no critics, no self-approval,
> no merge. Freeze a new R3B.2 SHA at in_review in a draft HOLD-FOR-SOL PR, then stop and
> return the evidence packet to Sol.

**Program:** `WS:INSTITUTIONAL-PRODUCT-EXPERIENCE-V2`
**Wave:** `XPV2-SC-R3B.2`
**Authority:** Sol
**Chairman:** Chris Wong
**Purpose:** resume the paused R3B.2 pickup after Sol adjudicated the durable rerun receipts
**Production migration:** NOT AUTHORIZED
**R3C:** NOT AUTHORIZED
**This is a reference-only correction wave.**

## 0. Observable mission

From current `main`, durably close the R3B.1 RIG cycle as `REVISE`, generate its lawful
successor, implement exactly the corrected R3B.2 reference-local closure set, freeze a new
immutable successor SHA with status `in_review`, and stop for fresh final critics.

Do not reopen the Sector Central architecture.

## 1. Fresh pins and verified current state

**Protected Sol Skillpack:** re-pin before work begins. Sol's latest verified protected pin
at dispatch: `mastermindx-market-intelligence/Mastermind@db0bac5fe3f72348262d42c8bd26b836bda9f61d`
(`mastermind.sol_skillpack.v1`, version 1.0.0, bootstrap major 1). Load `INDEX.md`,
`REVIEW_RETURN.md`, `RECONCILE_STATE.md`, `COMMISSION_WAVE.md` and any RIG/closeout
procedure from that exact same commit. If protected master advances again before claim,
re-pin and load all required skills from the new same commit.

**Macro:** Sol's latest observed `main` during adjudication:
`cd42b890d1df740f7fd5fddee6e582221360791b`. Re-pin current `origin/main` at pickup.

**R3B.1 frozen target:** `mastermind-xpv2-sector-r3b-1`, freeze commit
`0667f800764bf210af6c1237ccf0b5f0a71b4af2`, candidate SHA-256
`fec05b058fbc9dbe29744ad015b7ee9cd9baa5cb85bbbde739daa8b97644cf70`, merged via PR #6248 /
`780cbcf6d2d2c7b32b87a4674929e1732e5ad036`.

**Durable final critic receipts:** PR #6309 merged (`22fbf1e45148…`) — landed
`reviews/data_authority.md`, `reviews/mobile_accessibility.md`,
`reviews/product_regression.yml`, all binding the exact R3B.1 frozen SHA, all
`PASS_WITH_CONDITIONS`. Visual/Taste: PR #6279 (HOLD-FOR-SOL, review-only, one file:
`reviews/visual_taste.yml`, verdict `BLOCK`, exact SHA verified). **Sol releases #6279
solely for integration as review evidence** — not approval, R3C, production, or
self-verdict. Reconcile onto current main, prove the diff is review-only, preserve critic
bytes, never arm it as product delivery.

**Collision state:** at dispatch no `r3b2` branch or implementation PR existed. Search
again immediately before claim.

## 2. Correct canonical critic state

| Seat | Durable verdict |
|---|---|
| Product Regression | `PASS_WITH_CONDITIONS` |
| Mobile / Accessibility | `PASS_WITH_CONDITIONS` |
| Data / Authority | `PASS_WITH_CONDITIONS` |
| Visual / Taste | `BLOCK` |

Do NOT write that all four durable critics returned BLOCK. Do NOT make the unrecoverable
earlier chat returns the authority basis. The lawful rerun receipts are the canonical
final reviews for those three seats.

## 3. Sol's R3B.1 design-authority verdict

**Verdict: `REVISE`.** Reasoning: VTC1-001 survives as a critic BLOCK; MAC1-001 is a
candidate-owned major on the same label mechanism; DA1-01 and DA1-02 are major
customer-semantics defects; the candidate portion of DA1-03 is a cheap
authority-disclosure omission; PRC1R-001 / PRC1R-002 / MAC1-002 and surviving Visual
conditions are bounded reference-local closure work. The three PASS_WITH_CONDITIONS
verdicts do not compel approval — their reference-local conditions are not forward-ridable
into a production migration whose purpose is to reproduce this reference.

**verdict.yml integrity:** record critic verdicts exactly. `VTC1-001 -> upheld_revise`.
Do not falsely relabel critic majors/minors as blocker-severity findings. Carry DA/MAC/PRC
majors/minors as explicit revision conditions / authority adjudications and successor
continuity obligations per the current RIG schema. No `approval.yml`. Set R3B.1 manifest
`in_review -> revise`. Run the current RIG checker and mechanical `--mandate`/continuity.

## 4. Sol corrections to the earlier R3B.2 draft (supersede where different)

- **WITHDRAW old B2-02 (encoded emoji):** the durable Product Regression rerun performed a
  rendered six-view emoji/pictograph scan on the exact frozen bytes and found zero
  rendered UI hits. Do not create R3B.2 work for the lost-return emoji claim.
  Sanctioned-icon law remains globally in force.
- **RECLASSIFY old B2-03 (candidate heatmap contrast):** the durable Mobile seat does NOT
  prove the `.hm-t` colour-field text fails contrast — it proves ~440 shadowed glyphs are
  **unmeasured** by the flat-surface method. Do not call them passing; do not call them
  failing without a valid method. Preserve the unmeasured axis honestly; final
  human/appropriate-method legibility review; carry any required platform treatment to
  R3C/design-system if proven necessary. The byte-verbatim `sc_flows` fragment has real
  measured contrast debt and remains upstream/R3C.
- **WITHDRAW old B2-04 (candidate ZH translation):** English-only grader/category strings
  are upstream producer-owned (`PRC1R-U02`). Do not mint producer translations. Carry
  `note_zh`, `category_zh`, language-of-parts implementation to the producer/R3C owner.
- **WITHDRAW old B2-07 (503 tiny browse links):** `MAC1-003` falsifies the defect (17px
  boxes, ~40.6px pitch, one target per row — WCAG 2.2 SC 2.5.8 spacing exception
  satisfied). Do not inflate or disable those 503 links.

## 5. Binding R3B.2 implementation set (exactly these eleven)

- **B2-01 — one producer measure, one customer term.** `theme_intel.themes[].score` →
  `Strength / 强度` everywhere (Overview action-board theme rows and Map/context surfaces
  included). Remove copy asserting an independent action-board score field. Guard:
  producer-path → customer-label map; mutation flipping one occurrence back to
  `Score / 评分` → unique red. A truly separate producer-owned measure may use another
  term only with a distinct producer path.
- **B2-05 — COMPLETE visible + accessible figure labeling** (supersedes the earlier
  wording). At ALL widths every `.r3-fig` gets a localized per-cell accessible name
  independent of `.r3-cols`. At ≤640, every figure whose visual header disappears gets a
  visible inline mobile label. Required meanings include `Strength 76 / 强度 76`,
  `20d vs market +27.2% / 20日对比市场 +27.2%`, `Entry tier T1 / 入场层级 T1`,
  `Conviction 0.60 / 综合把握 0.60`. Acceptance: census all 18 `.r3-fig`; 18/18 AT names
  desktop+mobile; 18/18 non-naked at 320/390; no duplicate spoken label; EN/ZH parity;
  unique mutations for all three figure classes.
- **B2-06 — treemap label collision** at 320/390: no sector/group overlap; primary
  identity wins; secondary may drop; accessible/list equivalent retains full information;
  painted width, not character count.
- **B2-08 — rank scope at point of use:** `Rank across all groups` + native ZH twin in the
  immediate Map/Themes rank label/header.
- **B2-09 — neutral Recent Wrong semantics:** never reserved up/positive/Buy ink; neutral
  history/error treatment; result data unchanged.
- **B2-10 — remove meaningless mobile ramp:** suppress when the five state cells
  recompose vertically and the ramp no longer maps; no decorative replacement.
- **B2-11 — headline receipt follows wrapped text:** visually associated with the full
  wrapped headline; test 320/390 EN/ZH and large text.
- **B2-12 — `thin` vs reliability semantic collision:** `coverage.n_thin == 48`
  (gate-dropped, omitted) vs `subsectors[].reliability == "low"` (in-table). Keep the
  visible reliability chip but rename the low-reliability state **Low confidence /
  低置信度**. No causal copy unless the exact producer contract proves that cause. Keep the
  48-row omission sentence unchanged. Guard: the two producer paths may not collapse to
  one customer term; mutation restoring `Thin data` on in-table rows → red.
- **B2-13 — methodology receipt aria-controls:** add `aria-controls="r3-receipt"` to
  `[data-r3b1="02"] button.r3-rcpt.r3-rcpt--named`; guard that any control owning
  expanded/collapsed state for the shared panel names the same target.
- **B2-14 — ZH Show fewer target floor:** `收起` measures 39×44 (house 44px floor).
  `min-width:44px` or equivalent symmetric inline padding; re-measure ZH at 320/390/820.
- **B2-15 — context-only / 5d evidence disclosure:** the producer payload says
  `is_context_only: true`, `proven["5"] == true`, `proven["21"] == false`, context-only /
  never sizes. Paint this qualification beside the track-record badge. Minimum customer
  semantics: **Context only · evidence proven at 5d · never sizes decisions.** Native ZH
  twin required. Keep adjacent 21d figures explicitly labelled 21d and visually separate.
  Do NOT claim the 21d horizon is validated. Production's broader `Validated` badge
  semantics remain an R3C owner repair.

## 6. Upstream / R3C only — do not absorb

PRC1R-U01 (production Conviction naming collision); PRC1R-U02 (producer English-only
grader/category strings); sc_flows contrast/magnitude; production
`Forward track record: Validated` badge/21d pairing beyond the reference-local
qualification above; overloaded production `validated` vocabulary; production `REGIME BUY`
vocabulary; producer `reco_why`; `category_zh`; live Time Machine; real auth settlement /
`/premiumdata/`; production router; correction/revision authority; Baskets thin/gateable;
relative-unit typography debt. Do not invent fixes in the reference to make upstream
producer debt look solved.

## 7. Harness safety trap

`aria_id_audit.py`, `mutation_suite.py`, `lang_probe.py` default to writing inside the
frozen build tree. Always override their `--json`/`--out` destinations into scratch.
Never allow a verification run to silently mutate predecessor/frozen bytes.

## 8. Architecture do-not-reopen list

Six-view navigation/task order; State Ledge; action/context authority split; five Overview
action lanes and exact order/counts; Bottoming Watch; Map reserved-hue law; mobile Map
recomposition; Moving five-artifact source binding; Money core hierarchy; Explore
workflow; Confluence S&P → Nasdaq → Russell → Baskets; active-universe isolation; premium
arithmetic; current router/hash law; mobile nav ≤359 = 2 columns × 3 rows; sanctioned icon
system; complete ZH direction-color inversion; all producer rank/state/class/order/count
authority. No production files. No local rank/re-lane/re-classification.

## 9. Ordered execution

1. Re-pin Skillpack/current main/open PRs. 2. Integrate #6279 as review-only evidence
after current-main reconciliation. 3. Write R3B.1 `verdict.yml` exactly from the durable
critic packet + this Sol ruling. 4. Set R3B.1 manifest to `revise`. 5. Run RIG checker +
mandate/continuity. 6. Create lawful successor (`mastermind-xpv2-sector-r3b-2` if
accepted). 7. Copy/rebuild predecessor reference in the standard successor process; never
mutate R3B.1 frozen evidence. 8. Delegate bounded implementation lanes. 9. Implement only
B2-01, 05, 06, 08, 09, 10, 11, 12, 13, 14, 15. 10. Harden verification with
discriminating mutations. 11. Recapture evidence for the new exact bytes.
12. Deterministic double-build. 13. Freeze new SHA. 14. Manifest = `in_review`.
15. Update R3C draft with only upstream/live dependencies. 16. STOP and return to Sol.

## 10. Acceptance

R3A attack floor 59/59; successor verifier green; RIG checker clean; deterministic build;
zero production-path diff; bidirectional capability inventory; all new mutation kills;
one-path/one-label Strength law; 18/18 `.r3-fig` AT labels; 18/18 non-naked figures at
mobile; no treemap label collision; rank scope adjacent; neutral Recent Wrong; mobile
ramp removed only when semantically meaningless; receipt association correct; no
`thin`/reliability vocabulary collision; methodology control has `aria-controls`; ZH Show
fewer ≥44px house floor; context-only / 5d evidence disclosure correct; zero duplicate
IDs; zero `href="#"`; canonical/legacy hash smoke; gated/hydrated/ungated smoke; all four
Confluence universes; no new authority/state/control plane.

For the colour-field heatmap axis: report what is measured; report what remains
unmeasured; **never convert `UNMEASURED` into PASS.**

## 11. Stop condition and return packet

Return only after: successor frozen at exact immutable SHA; candidate SHA-256 recorded;
manifest `in_review`; fresh evidence bound to new SHA; no production diff; R3C not
started. Return to Sol: exact current main used; successor reference ID; frozen SHA;
candidate SHA-256; PR number/head; changed files; all test/mutation/CI receipts; evidence
matrix; continuity closure; unresolved upstream/R3C list; any semantic drift discovered
after pickup; explicit statement that no production migration began. Do not self-approve.
Do not mint `approval.yml`. Do not dispatch final critics yourself unless Sol separately
commissions them.

---

# SOL AUTHORITY RULINGS AFTER DURABLE RERUN RECOVERY (concise record for verdict.yml)

Durable final review state: Product Regression PWC · Mobile/Accessibility PWC ·
Data/Authority PWC · Visual/Taste BLOCK. The rerun receipts are the canonical final
receipts for the first three seats; the unrecoverable earlier chat returns are historical
context only.

Sol verdict: **REVISE** (VTC1-001 surviving BLOCK; MAC1-001 major on the same mechanism;
DA1-01/DA1-02 major reference-local semantics; DA1-03 candidate portion a disclosure
omission; PRC1R-001/PRC1R-002/MAC1-002 + surviving Visual conditions bounded closure
work). Do not relabel PWC critic majors/minors as blocker severity. `VTC1-001 ->
upheld_revise`. Carry all other required conditions as revision conditions/authority
adjudications in the current RIG schema.

Exact scope corrections: old B2-02 emoji WITHDRAW · old B2-03 candidate heatmap failure
RECLASSIFY AS UNMEASURED/R3C VERIFICATION · old B2-04 candidate ZH translation WITHDRAW
(upstream producer) · old B2-07 503 links WITHDRAW (MAC1-003 falsified) · B2-05
strengthen to visible + AT labels at every width · B2-12 add DA1-02 · B2-13 add
PRC1R-001 · B2-14 add MAC1-002 · B2-15 add candidate-owned part of DA1-03 ·
PRC1R-U01/U02 upstream/R3C only.
