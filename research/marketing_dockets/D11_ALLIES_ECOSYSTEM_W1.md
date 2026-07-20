# MKT-D11 — Allies W1: Creator / Partner / Community Scaffold

**Department:** Allies (ecosystem) · **Priority: P3** · **Status: W1 SHIPPED 2026-07-19 (#3058)** — 68-target scored ledger (51 funds from `config.yml smart_money.funds` — the W1 in-repo subset of the 356-link corpus — + 11 rule-cited communities via `config/allies_communities.yml` + 5 newsletters + 1 creator), 68 materials kits with honest graded-receipt stats, paper-only referral schema (code/cut unset — operator decisions), admin Allies page with operator-only status transitions. Outreach remains 100% operator-gated; StockTwits/Discord excluded until their rules can be verified. The recommended program shape now lives in [`D11_AFFILIATE_CREATOR_PROGRAM_SHAPE_RULING.md`](D11_AFFILIATE_CREATOR_PROGRAM_SHAPE_RULING.md); economics remain unset until operator ratification. Next wave: operator-supplied creator lists + ratification and implementation of that ruling.
**Charter:** id=`ecosystem` ("Creator, Partner & Community Infrastructure", wave 5, 11 chartered engines — stubs).

## Why

From zero followers, borrowed audiences move faster than owned ones: finance creators who'd share a good chart, communities (Reddit/Discord/StockTwits) where a receipt-backed post earns real distribution, and eventually affiliates paid from MNZ revenue. W1 builds the *ledger and materials*, not the outreach — **every external contact is an operator decision**, executed by the operator or with explicit per-contact approval.

## Deliverables — W1

1. **Target ledger** (`data/marketing/allies_targets.jsonl` + `engine/marketing/allies.py`): structured candidate list — creators/communities scored deterministically (audience size proxy, topical overlap with our universe, receipt-friendliness). Seed sources: the fund-links corpus from the smart-money program (356 fund links), finance-creator lists the operator supplies, community rules pages (which subreddits/discords allow tool posts at all — record the rule citation per target).
2. **Materials kit:** a per-target one-pager generator — what we'd offer (free Pro access, a custom chart pack, an affiliate cut per MNZ pricing), with honest track-record stats from the graded ledger. Rendered to `data/marketing/allies_kits/`.
3. **Affiliate scaffold (paper only in W1):** the ledger schema for referral codes → D07 attribution join; no codes issued until the operator approves the program shape.
4. Admin **Allies page** (via `designer`): target ledger with scores + status (`candidate → operator_approved → contacted → active`), kit previews. Status transitions past `candidate` are operator-only actions.

## Acceptance

- Ledger populated with ≥50 scored candidates from in-repo sources; kits render with real receipts; the admin page makes the operator-gate explicit (no "contact" button that acts autonomously).

## Traps

- **Nothing outbound ships from this docket.** Community rules vary wildly and self-promo bans are common — the rule citation per target is mandatory before the operator ever acts.
- Affiliate economics must reference MNZ pricing truth (#2923/#2943), not invented margins.
