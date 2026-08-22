---
key: MARKET-OS-MUTATION-SUCCESS-REQUIRES-AFFECTED-ROW
claim: >
  For owner-scoped Portfolio writes, a transport success or an error-free database
  result does not prove that any row changed; success requires an exact affected-row
  receipt followed by an authoritative read that proves the intended postcondition.
falsifier: >
  Run `pnpm vitest run terminal/lib/__tests__/portfolio.test.ts
  terminal/lib/__tests__/portfolioRoute.test.ts` with the fixture transport's
  positions_mutation_noop fault enabled and show that update or delete can report
  success without returning the intended row or deleted id, or show a live owner-scoped
  mutation contract that guarantees a nonzero affected-row error instead.
so_what: >
  Every future Portfolio mutation path in Macro or Terminal must require the intended
  row identity in the write receipt and re-read canonical Portfolio authority before
  showing success or removing a row from the UI; error == null and HTTP 2xx are not
  completion evidence by themselves.
kind: architecture
verified_at: 2026-08-22
verified_by: >
  Terminal PR #456 focused service/route suites with positions_mutation_noop, deliberate
  mutation-red reversion, and authenticated production sentinel create/update/close/
  reopen/delete with exact receipts plus Terminal and Macro authoritative reloads
scope:
  - macro
  - terminal
  - terminal-user-services
  - "terminal/lib/portfolio.ts"
  - "terminal/app/api/portfolio/route.ts"
  - "terminal/components/PortfolioView.tsx"
confidence: verified
---

## Failure shape

The live RLS policies were not the defect: all four Portfolio operations remained
owner-scoped, and read-only catalog inspection found no trigger or external resurrection
writer. The unsafe inference was one layer above the database: treating the absence of a
driver error as proof that an update or delete affected its intended row.

Terminal PR #456 makes the receipt a law instead of an assumption. Update and delete now
select the affected row under the same owner scope; the route returns the exact written row
or deleted id; and the client reloads canonical Portfolio authority and proves that receipt's
postcondition before changing the visible success state. A controlled production 503 also
proved the negative half: the UI disclosed failure while the authoritative Portfolio
fingerprint remained unchanged.
