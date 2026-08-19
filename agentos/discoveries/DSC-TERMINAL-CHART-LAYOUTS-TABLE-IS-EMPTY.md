---
key: TERMINAL-CHART-LAYOUTS-TABLE-IS-EMPTY
claim: >
  `public.chart_layouts` in the shared Supabase project (fsldfzlxyavsuwqbceod) held ZERO rows
  estate-wide on 2026-08-19 — not "zero duplicates", zero rows. No user has ever successfully
  saved a chart layout in production, across 31 profiles. The neighbouring user-plane tables
  are populated on the same read (watchlists 24, portfolio_positions 9, saved_scripts 4), so
  this is a property of the LAYOUTS feature, not of an empty estate. It is explained by the
  defects the feature shipped with: a guest Save control wired to a guaranteed 401, a client
  that never inspected the POST result and cleared the name box regardless, and a server that
  answered `200 {layouts: []}` for a failed read — so a save that silently did nothing was
  indistinguishable from one that worked. Separately on the same census, all 4 `saved_scripts`
  rows (2 distinct owners) carry `is_public = false`, and no writer anywhere in the estate sets
  that flag.
falsifier: >
  Re-run the census and get a non-zero count:
  `curl -sI "$NEXT_PUBLIC_SUPABASE_URL/rest/v1/chart_layouts?select=id" -H "apikey: $SUPABASE_SERVICE_ROLE_KEY"
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" -H "Range: 0-0" -H "Prefer: count=exact"`
  returning anything other than `content-range: */0`. Expected to become false once the
  post-#427 Save path reaches production and real users save layouts — which is the point.
  The `saved_scripts` half falsifies the moment any row reports `is_public = true`.
so_what: >
  It is what made `supabase/migrations/0008_chart_layouts_unique_name.sql` safe to write and
  apply: a `unique (user_id, name)` index over an empty table cannot reject an existing row, so
  the loss-preserving duplicate reconciliation the delivery packet asked for had no input and
  was deliberately NOT implemented — writing an untested merge routine for an empty table would
  be speculation shipped as a migration. A future session must re-run the census before applying
  that file to any non-empty environment. It also bounds the blast radius of the Saved Layout
  contract change (DEC:TERMINAL-SAVED-LAYOUT-CONTRACT-V2): there are no legacy v1 configs in
  production to migrate, so the normalizer's back-compat paths are correctness insurance rather
  than a live data path. And it is the reason the My Scripts owner-scope fix is stated as a
  CONTRACT bug rather than a live leak: with no public rows, nothing is cross-visible today.
kind: data
verified_at: 2026-08-19
verified_by: >
  Read-only PostgREST census with the service key from the VPS
  (`/opt/terminal/terminal/.env.local` on root@146.190.142.17), 2026-08-19:
  `GET /rest/v1/chart_layouts?select=id,user_id,name,updated_at,created_at` -> HTTP 200, body `[]`;
  the same path with `Range: 0-0` + `Prefer: count=exact` -> `content-range: */0`.
  Same read over the sibling tables -> profiles 0-30/31, watchlists 0-23/24,
  portfolio_positions 0-8/9, saved_scripts 0-3/4.
  `GET /rest/v1/saved_scripts?select=id,user_id,name,lang,is_public,updated_at` -> 4 rows,
  2 distinct `user_id`, `is_public=false` on all four.
  Policy text that makes the ownership question non-trivial:
  supabase/migrations/0001_init.sql:121-127 (scripts_owner + scripts_public_read).
  Defects that explain the zero: terminal/app/api/layouts/route.ts and
  terminal/components/TerminalShell.tsx as of #427's base, fixed in #427.
scope: ["terminal/app/api/layouts/**", "terminal/lib/layouts.ts", "supabase/migrations/**"]
confidence: verified
---

## Grounds

The census was run because the delivery packet forbade adding a unique constraint without first
counting what it would reject. The answer turned out to be more informative than the question:
the table is not merely free of duplicates, it has never been written to successfully.

That reframes the whole wave. "Saved Layouts" was not a feature with a data-integrity bug on top
of a working base — it was a feature whose write path had never demonstrably worked for anyone,
which is exactly what the four defects predict. It also means every fix in that PR is additive
against production: no reconciliation, no backfill, no migration of existing configs.

The service key bypasses RLS, so `[]` is a genuine table-wide empty rather than a policy-filtered
view. The same key returned populated counts for four sibling tables in the same session, which
rules out a credential or endpoint problem masquerading as an empty table.
