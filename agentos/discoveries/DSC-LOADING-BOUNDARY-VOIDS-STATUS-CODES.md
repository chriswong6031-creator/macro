---
key: LOADING-BOUNDARY-VOIDS-STATUS-CODES
claim: >
  In the Terminal's Next.js App Router, a `loading.tsx` at a PARENT segment silently voids the
  HTTP status of every `redirect()` / `notFound()` raised by the pages beneath it. The fallback it
  declares lets React flush the shell — status line included — as soon as the LAYOUT resolves,
  while the page is still awaiting its async work; after that flush a redirect/notFound can only be
  delivered as a soft, client-side navigation carried inside the RSC payload, and the response
  stays 200. MEASURED on production 2026-08-21 (mastermind-terminal master @ c66c1154), anonymous,
  straight against the ORIGIN (127.0.0.1:3000, bypassing EdgeOne, so no CDN rewrite is in play):
  `GET /admin` answered 200 with a workspace skeleton and zero admin markup, while
  `terminal/app/(shell)/admin/page.tsx` plainly called `redirect("/login")`. The gate was never at
  fault — the served HTML carried `{"digest":"NEXT_REDIRECT;replace;/login;307;"}`, i.e. the page
  HAD asked for the 307 and `isAdminRequest()` HAD answered "anonymous". One shared
  `app/(shell)/loading.tsx` covered all seven routes of the group, and /admin was the one route in
  it whose entire first act is an auth decision. A segment-level `admin/layout.tsx` does NOT escape
  the parent boundary (measured: still 200). DIAGNOSTIC TRAP: that 200 body also contains "404"
  text and `nfTitle` — those are the not-found boundary being SERIALIZED INTO THE PAYLOAD for the
  segment, not evidence `notFound()` ran. Reading them as "the denied branch executed" sends the
  investigation at the gate instead of the boundary.
falsifier: >
  Any of: an anonymous `curl -o /dev/null -w "%{http_code}"` against the origin's /admin returning
  something other than 307 on current master (the fix landed in mastermind-terminal PR #455 — it is
  307 now, and 404 for a signed-in non-owner); restoring `app/(shell)/loading.tsx` and observing
  /admin still answer 307 (it reverts to 200 — this is the mutation check the pinning test
  performs); a Next.js release that buffers the status line past the first flush or that hoists
  auth-raising segments above their parent boundary; or a boundary declared BELOW the gate (a
  `loading.tsx` inside the admin segment itself) proving sufficient. Note the falsifier must be run
  with `ADMIN_DEV` UNSET — that env var grants admin whenever NODE_ENV === "development"
  (terminal/lib/adminGate.ts), so a dev probe carrying it measures the admin path and reports a
  legitimate 200.
so_what: >
  Three things a future session should carry. (1) Correct control flow in a Server Component is NOT
  a delivered status code. `redirect()`/`notFound()` are requests to the renderer, and a Suspense
  boundary above them converts the request into a client-side hint. Anywhere a status code is part
  of a CONTRACT — an owner plane, a paywall, a members-only route — the gate must sit with no
  streaming boundary above it, and the fallback must be declared per data workspace instead of once
  over a whole route group. Streaming a skeleton is the right trade for a data workspace and the
  wrong one for a gate. (2) The natural unit test for this is a FALSE GREEN. Mocking the gate and
  asserting the page throws NEXT_REDIRECT passes the entire time production answers 200, because
  the throw was never the broken part — the pin has to be STRUCTURAL (assert no `loading.tsx` on
  the segment chain above the route, no `Suspense` in the ancestor layouts, and that the sibling
  routes still HAVE their fallback so the fix cannot decay into "deleted the skeleton"). Any
  boundary-shaped defect has this property: the code that looks wrong is correct, and the file that
  is wrong contains no mention of the symptom. (3) This particular contract cannot be tested in the
  repo's Playwright suite at all — `terminal/playwright.config.ts` sets `ADMIN_DEV: "1"` for the
  whole e2e server, so every e2e request is already an admin. Check what a suite's server env
  GRANTS before assuming the suite can observe a denial.
kind: landmine
verified_at: 2026-08-21
verified_by: >
  Production measurement against the origin, anonymous, recorded in mastermind-terminal PR #455.
  Reproduced locally on `next dev` with `env -u ADMIN_DEV` and dummy Supabase env: /admin answered
  200; moving `app/(shell)/loading.tsx` aside flipped the identical request to `307 -> /login`;
  restoring it returned it to 200. All four verdicts measured by temporarily forcing the return of
  `terminal/lib/adminGate.ts` (a session cannot otherwise be had): anonymous 200->307,
  denied 200->404, admin 200 + console, unavailable 200 + authorityUnavailable. The
  `admin/layout.tsx`-does-not-help result was measured the same way (still 200). Fix shipped as
  mastermind-terminal PR #455: `app/(shell)/loading.tsx` deleted, shared fallback moved to
  `terminal/components/WorkspaceLoading.tsx`, six non-admin workspaces given their own one-line
  `loading.tsx`, /admin given none. Pinned by
  `terminal/lib/__tests__/adminPageStatusContract.test.ts` (7 tests), mutation-checked: restoring
  the parent `loading.tsx` turns the structural test red while the six branch tests stay green.
scope: [terminal]
confidence: verified
---

## Detail

The route group was the whole mechanism. `app/(shell)/` holds seven routes — `discover`,
`analysis`, `options`, `scripts`, `alerts`, `portfolio`, `admin`. Six are data workspaces where a
streamed skeleton is exactly right: the layout resolves, the shell paints, the table arrives when
the data does. The seventh is an owner gate whose first and only act before rendering anything is
`await isAdminRequest()`. One `loading.tsx` served all seven, and the trade that is correct six
times is a defect the seventh time.

What makes it hard to see in review is that no file involved is wrong on its own. The page reads
exactly as intended and its comments describe the intended contract accurately. The gate
(hardened in PR #442 to distinguish "not an admin" from "could not check") is correct.
`loading.tsx` is a correct four-line Suspense fallback. The defect exists only in the RELATIONSHIP
between two files that never import each other, and it is expressed in a file — `loading.tsx` —
that contains no reference to auth, status codes, or /admin.

The sibling API is what made the gap legible. PR #442 (F-1) had deliberately made 404 / 503 / 200
carry three distinct meanings for `/api/admin/searches`, with a wire-contract test to match. The
page beside it answered 200 to a visitor with no session at all. Nothing leaked — no admin markup
is ever served and the owner gate held — but monitoring, caching layers and crawlers were all told
the owner console URL is OK.

Worth recording separately: the investigation's first evidence was misleading in a specific,
repeatable way. The 200 body contains the string "404" and the `nfTitle` i18n key, which reads like
`notFound()` having run and the status having been lost on the way out. It is neither: the App
Router serializes the segment's not-found BOUNDARY into every payload for that segment, whether or
not it renders. The actual signal was further down the same payload — the `digest` field naming
`NEXT_REDIRECT;replace;/login;307;`, which identifies both the branch taken and the status that was
requested and dropped. When a status code goes missing, read the payload's digest, not the payload's
prose.
