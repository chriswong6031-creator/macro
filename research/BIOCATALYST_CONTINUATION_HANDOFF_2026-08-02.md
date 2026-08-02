# BioCatalyst continuation handoff — 2026-08-02

Canonical continuation note. The active objective remains full BioPharmCatalyst-class parity and superiority through clean-room public-source intelligence. Never use, store, or transmit competitor credentials.

## Shipped foundation: B1

- PR [#4227](https://github.com/chriswong6031-creator/macro/pull/4227) merged as `6f41169bdf13`; all four CI packs and security fences passed.
- Production advanced to a descendant (`/api/health` returned checkout `837e55db1b8`). The deployed `site/biocatalyst.html` hash exactly matched `origin/main`.
- The VPS setup installed the isolated worker runtime and units. `macro-api` is active; anonymous `/api/biocatalyst/v1/health`, `/trials`, and `/trials/{NCT}` return `401`, not `404`; the same three paths are mounted in the internal OpenAPI document.
- `/etc/macro-biocatalyst.env` is root-owned mode `0600`. `macro-biocatalyst.timer` is disabled/inactive and must stay dark: there are no dedicated R2 credentials or source-rights approval.
- B1's `render` and `engine-render` runs `30733044334` and `30733044318` were still queued behind older long-running render jobs at handoff. Production itself was independently verified.

## Merged, awaiting final live verification: B2 exact registry history

- PR [#4251](https://github.com/chriswong6031-creator/macro/pull/4251) merged as `91b5299a4be5`. Its final branch was `codex/biocatalyst-b2-history-final-20260802`; the preserved backup branch is `codex/biocatalyst-b2-history-20260802` and must not be force-pushed.
- GitHub accepted the squash while PR CI was queued. Continue by waiting for CI run `30734026827` and fences run `30734026814`; investigate any failure rather than treating the merge as proof. At merge time production `/api/health` was still on checkout `a35aa77395a`, immediately before B2.
- Fresh post-rebase validation: `531 passed, 5 warnings in 692.61s`; warnings are FastAPI/Starlette deprecations. `git diff --check`, shell syntax, and all four changed JS assets pass. Earlier responsive browser QA passed at 390/820/1440 in dark/light and English/Chinese.
- B2 adds exact ClinicalTrials.gov Record History receipts, version snapshots, deterministic diffs and neutral change facts, replay-bound promotion, authenticated API history output, and before/after UI. It remains facts-only, rights-gated, `production_ingest_allowed: false`, and has no materiality, prediction, Prophet, or trade authority.

Finish B2 from any clean checkout: verify `91b5299a4be5` remains on `origin/main`; wait for the PR checks and render queues; wait for production health to advance to that merge or a descendant; restart `macro-api` only if the normal updater did not; verify anonymous BioCatalyst API requests remain authenticated (`401`, not `404`), the deployed workbench matches `origin/main`, and `macro-biocatalyst.timer` remains disabled/inactive. Do not run ingestion.

## Next parity lane

Resume B4A only after B2 ships. Its empty worktree is `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/biocatalyst-b4a-regulatory-20260802`; fetch and rebase it to fresh `origin/main`. Build official weekday Drugs@FDA complete-ZIP receipts and exact release/table manifests into an FDA-native application/product/submission/action/document graph. Keep it dark pending source-rights approval. Exclude fuzzy company/ticker/trial joins, pending PDUFA/IND/hold/CRL claims, approval odds, and medical claims. Subsequent lanes are Orange Book patents/exclusivities; labels, shortages, and safety; then governed company/SEC identity consumers for cash runway, dilution, licensing economics, Neural Web context, Mastermind synthesis, and Prophet scoring.
