# reviews/ — XPV2-SC-R3B.2 final critic receipts (durability record)

**This file is records-layer prose authored by the R3B.2 durability pass (2026-08-24). It is
NOT critic prose.** Every file it lists is a byte-exact copy of what an independent critic seat
authored; none of it was rewritten, normalized, summarized or reconstructed. Recompute the
hashes below before trusting any statement here.

Canonical carrier: PR #6337 / `claude/xpv2-sc-r3b2-build`.
Frozen content SHA: `d0830a374795925ee1e55b66c0cc42e329ac172d`.
Candidate SHA-256: `4adb4b6245e8e4aa5b68c850a615461327c0a5d2e672e4c203d6ba32a3b8d53c` (5,506,871 bytes).
All four seats bind exactly those two values; dispatch head `0e542f3eda09721f8a255a08bb9db09070090871`.

## Persisted receipts

| Seat | Receipt (this dir) | SHA-256 | First pass | SHA-256 |
|---|---|---|---|---|
| Product regression | `product_regression.yml` | `93c11f0aa8e7d9ae309b8940b192587ddd37f24f55b12a37dc9185be4d8ff880` | `evidence/first_pass_product_regression.md` | `2c15eb6cc33564c1e47af796b2329a85ab900033f5740630956a3526d0680203` |
| Visual / taste | `visual_taste.yml` | `ddce48c3f5f98c825913b06fbe62a6d769d96d6cdc22105dd6f99f91f12d4bfd` | `evidence/first_pass_visual_taste.md` | `a8ca128a61cf5540050611c72a837d6bfb325dd490b5343493b105107c8a3748` |
| Mobile / accessibility | `mobile_accessibility.md` | `a1087a0a039d7304f936138d29da60c46485257ea02a6b50ece4eebc026affd9` | `evidence/first_pass_mobile_accessibility.md` | `347f81ccb36eda38fdc9055bd15c43a1d63cf27ecd072c3d51d071cb43226e80` |
| Data / authority | `data_authority.md` | `5eb3f07618c5e24319bfe377755adda852365741d2c09a8145f2b14a6fea7792` | `evidence/first_pass_data_authority.md` | `d64a758d5aa9ec9693d3541b2da1120103dfba05ccf75a3261616c8da531e3ae` |

Recompute:

    shasum -a 256 research/reference_integrity/mastermind-xpv2-sector-r3b-2/reviews/*.yml \
                  research/reference_integrity/mastermind-xpv2-sector-r3b-2/reviews/*.md \
                  research/reference_integrity/mastermind-xpv2-sector-r3b-2/reviews/evidence/*.md

`README.md` itself is excluded from that list's expectations — it is this record, not a receipt.

## Path note (why receipt-internal paths differ from the persisted ones)

`product_regression.yml:quarantine.first_pass_path` and `visual_taste.yml:quarantine.first_pass_record`
name `critic_return/first_pass_<seat>.md` — the seat-local working path in each critic's own
worktree at authoring time. Those lines are critic bytes and were deliberately **not** edited.
The same bytes are persisted here as `evidence/first_pass_<seat>.md`; the SHA-256 column above is
the join. The RIG checker does not resolve those strings as filesystem paths.

## Seat shape

RIG's schema-bound review slots are `product_regression` and `visual_taste` (`REVIEW_ROLES`), and
both are present here as `mastermind.rig_review.v1` YAML. `mobile_accessibility.md` and
`data_authority.md` are the two additional independent seats Sol commissioned for this cycle;
they are Markdown by seat design and sit alongside the schema-bound pair rather than inside it.

## MA2-001

Mobile/accessibility finding `MA2-001` (minor, evidence provenance, attributed upstream, not to
candidate bytes) states that `baseline.yml`'s six named production screenshots are marked
PLANNED/not captured. That was a true reading of stale `baseline.yml` prose from a sparse
checkout where `mockups/` is not materialized. All six files are in fact committed on
`origin/main` (merged PR #6197, adding commit `f5b0094614b6`). Disposition:

    MA2-001 = REFUTED_BY_CANONICAL_GITHUB_EVIDENCE

The receipt above is preserved byte-exact and carries the original finding. The refutation is
recorded in `../baseline.yml` (`evidence.screenshots`) and carried to Sol — never by editing the
critic's words. `MA2-002` (heatmap colour-field **UNMEASURED**) is untouched and remains an open
condition for R3C; UNMEASURED is not PASS.

## State at persistence

`manifest.yml` remains `status: in_review`. No `verdict.yml` and no `approval.yml` exist, and
this pass authored neither. Candidate bytes are unchanged.
