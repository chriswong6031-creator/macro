# Watchlist

A client-side holdings watchlist (`site/watchlist.html`). The user assembles a
list of tickers — equities, ETFs, commodities, crypto — and sees each one's live
signal from the analyzer engine (bottoming / buy-zone / uptrend / avoid), plus
momentum across timeframes. Add via the analyzer-style search; remove per row.

## How it works

- **Persist selection, not data.** Only the list of ticker symbols is stored
  (localStorage key `mdash.watchlist.v1`). Every name/state/signal is re-resolved
  live from the nightly `stockdata/index.json` (+ optional per-ticker JSON) on
  each load, so a saved list never goes stale across the nightly rebuild.
- **Index-first render.** The state badge for each row comes from `index.json`'s
  `st` field with zero extra fetches; richer detail (entry cue + momentum strip)
  is lazy-loaded per card as it scrolls into view.
- **Zero infra by default.** The local watchlist makes no third-party network
  calls. Cross-device works account-free via an export code / `#wl=` share link.

Files: `templates/watchlist.html.j2` (page), `templates/watchlist.js` (app),
`templates/stockdata.js` (shared signal helpers), `templates/auth.js` (optional
cloud sync). Built by `scripts/build_site.py` (in the `stock_search` block); the
hub card is added by `scripts/build_vector.py`. Config: `watchlist:` in `config.yml`.

## Cloud accounts (cross-device sync) — PROVISIONED

Project `MarketIntelligence` (`fsldfzlxyavsuwqbceod`) is wired up:

- `config.yml → watchlist.supabase` holds the project URL + **publishable** key
  (public by design — per-user isolation is enforced by RLS, never the key; the
  `service_role` key is never in this repo).
- The `watchlists` table + RLS (4 own-row policies) are created — verified the
  anon REST query returns `[]` (table exists, RLS blocks anyone not signed in).
- Auth is passwordless **magic link**: the free tier won't allow editing the
  email template (so no 6-digit code is possible with the default email
  provider), so sign-in emails a link the user clicks. The SDK is lazy-loaded
  only on sign-in / link-return, so anonymous visitors stay zero-third-party.
- Redirect allowlist + Site URL are set for `http://localhost:8741/**` (preview)
  and `https://chriswong6031-creator.github.io/macro/**` (production). If the
  deployed URL ever changes (custom domain, repo rename), update
  Supabase → Authentication → URL Configuration accordingly.

### Testing sign-in

Enter your email → **Email me a sign-in link** → open the email → click the link
→ it returns to the watchlist page signed in, and your list syncs. Free-tier
email is rate-limited (a few per hour) and may land in spam.

### Want the 6-digit code UX instead?

Connect a free custom SMTP provider (e.g. Resend) in Supabase → that unlocks
email-template editing; then the magic-link template can carry `{{ .Token }}`
and `auth.js` can switch back to a code-entry flow.

### Optional: keep-alive

Free projects pause after ~7 days idle. Add the keep-alive step at the bottom of
[`templates/watchlist_supabase.sql`](templates/watchlist_supabase.sql) to
`.github/workflows/daily.yml` (needs `SUPABASE_URL` + `SUPABASE_ANON_KEY` repo
secrets).

### Verifying RLS (do this — most Supabase leaks are RLS misconfig)

Sign in as two different emails and confirm one account cannot read or write the
other's row, and that a query with only the anon key (no signed-in JWT) returns
nothing.
