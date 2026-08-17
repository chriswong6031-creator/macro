# Independent W8 critique — PR #5737

**independent_of_author: true.** This is not the author-session `CRITIQUE.md`.
Do not rubber-stamp that file. Do not treat this as a design-authority verdict
(`verdict.yml` is not written). Do not merge. Do not start W9.

Binding receipts (RIG V1 §6):

- `research/reference_integrity/entry-radar-w8/reviews/product_regression.yml` (CRITIC_A)
- `research/reference_integrity/entry-radar-w8/reviews/visual_taste.yml` (CRITIC_B)

First freeze judged: `b4f5576330b079c7704102c2af8d59e7ed989f17` (APPROVE-WITH-NITS).
Nits applied at `5ef3626d2e59c101dfd9cc76399fa97f11b0e561`.
Continuation visual critic C (opus designer, identity distinct from author and from A/B)
judged `5ef3626` and returned **REVISE** — two freeze blockers introduced by the nits
commit (overlay `nowrap` occluding Candidate as “CAN”; translated `title=`). Those
are repaired on the current working tree; a new freeze SHA will be recorded after
the repair commit. Pinned Prophet Board: merge `168a9be006914441051cff393927ce465e39138e` / tree `d540f493a097`.

Both receipts are from one commissioning session wearing two lenses, not two
quarantined Opus spawns. The design authority should weigh that. They are still
not the author (`cursor-cloud-w8-entry-radar-9f9d`).

---

## Disposition

**APPROVE-WITH-NITS**

RIG critic verdicts: both **PASS_WITH_CONDITIONS**. No blocker-severity finding
survived. This is not APPROVE (W9 must not copy the package as-is) and not BLOCK
(the attack list the brief named is substantially clean).

Must-fix before this freeze is treated as W9-copyable law — nits, not a rewrite:

1. **PRC-001** — Quiet crop cannot say "0 in the Probe Set" and "the Probe Set can still be live."
2. **PRC-002** — Implement the printed sort, or delete the sentence.
3. **PRC-003 / VTC-009** — Best / 首选 cannot look like a measured rank. Qualify or dash the count.
4. **PRC-004 / VTC-003** — Featured glow is not Best (2 vs 10) and has no label. Align the bytes with DESIGN_NOTES or delete the glow.
5. **PRC-006** — Stale card must not print "No path yet" because the fixture forgot a spark.
6. **PRC-010** — Drop the dead `#ticker` full-card link, or stop claiming Prophet PRC-301 is closed.
7. **PRC-007 / PRC-008** — W9 handoff CAN COPY must not list the reduced card as §14 complete. Reserve the missing slots as ACCRUING / UNAVAILABLE or file them BLOCKED_DATA.
8. **VTC-002** — Sixteen identical PRIORITY ACCRUING stamps. One board-level line + em-dash on the card.
9. **VTC-004** — Candidate `--ok` green vs ZH `--down` green. Keep `--ok` off `--pv-buy`; pick a third mix for lifecycle.
10. **VTC-005 / VTC-006** — Do not pin 390 with `overflow-x: hidden`. Unwrap the C2 overlay on the 232px card.

Polish (not freeze-blocking): PRC-011, PRC-012, PRC-013, PRC-014, VTC-007, VTC-008, VTC-010, PRC-009 residual.

---

## Attack list (the brief)

| Attack | Result |
|---|---|
| Sister language vs cargo-culted Prophet semantics (Own-It, seven-cell, fake plans) | **Clean.** Radar lifecycle is Probing / Pre-candidate / Candidate \| Invalidated / Expired. No Own-It. No delivering cell. Sister card geometry is real. |
| Expert identities flattened? C4 as a firing expert? | **Clean on the arena.** G0/C1/C2/C3/C5 are one card per ticker×expert. C4 throws if used as a row expert and cannot be a lane filter. Residual: Terminal STARTER / RE-ENTRY / amber EARLY have no slot (PRC-009, downgraded). |
| Provisional shown as confirmed? Stale as live? Unavailable as non-fire? | **Mostly clean, one major.** Footers are honest. Stale/unavailable/raw/degraded are dashed and unlifted. Glance CANDIDATE chip is the same for provisional C1 and confirmed C3/G0 (PRC-005). Stale prints the wrong null ("No path yet", PRC-006). |
| Fabricated Priority / Opportunity / probability? | **No numbers.** Slots exist. Best 10 / 首选 10 and two silent featured glows are the unmeasured-rank residue (PRC-003, PRC-004). Printed sort is not a sort (PRC-002). |
| EN/ZH hierarchy mismatch? Dark/light regressions? 390 overflow? | **Structural bilingualism holds. Light plane is white. 390 is one column.** ZH 首选 / 累计中 overclaim (VTC-009, PRC-012). Candidate green vs ZH down-green (VTC-004). 390 proof is clip, not fit (VTC-005). Overlay wraps on 232px (VTC-006). |
| Reference assets looking like production? | **Clean.** Banner on every state. REF.*/FIX.* tickers. No `templates/entry_radar.html.j2` or `site/entry_radar.html` on this branch. |
| Honest ACCRUING / NOT YET MEASURED slots? | **Present.** ACCRUING on unavailable/stale cards is the leftover (PRC-011). 累计中 is the worse ZH (PRC-012). |

---

## What the author pass missed (do not rubber-stamp)

Author `CRITIQUE.md` filed no blockers and ACCEPT/RETAIN'd six product + four visual items. Independently found and not in that list: PRC-001 (quiet self-contradiction — they saw the 0 and not the copy fight), PRC-002, PRC-003, PRC-004 (they claimed featured = Best; fixtures are 2 vs 10), PRC-005, PRC-006, PRC-007, PRC-008, PRC-010 (they claimed PRC-301 closed), VTC-001, VTC-002, VTC-004, VTC-005.

Author FIXED PRC-W8-002 (`--pv-buy` → `--ok`) is real and credited.

---

## Not done here

- No `verdict.yml` / no `approval.yml` / manifest stays `in_review`.
- No W9 work. No merge. No `merge-on-green`.
