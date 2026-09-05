---
key: SUPABASE-MANAGEMENT-PAT-EXPIRES-AT-30-DAYS
claim: >
  The `SUPABASE_ACCESS_TOKEN` repo secret is a Supabase Management API PAT (`sbp_…`) that
  EXPIRES ~30 DAYS after it is minted, and nothing in this estate watches that clock. The
  secret written 2026-07-14T13:08:18Z killed the `geo-enrich` lane at its exact 30-day
  anniversary: run #402 / 31698815868 succeeded 2026-08-13T12:10:34Z, run #403 /
  31707633952 failed 2026-08-13T13:57:48Z, and every one of the ~370 runs after it failed
  identically with `urllib.error.HTTPError: HTTP Error 401: Unauthorized` on the first
  Management API call. The API's own body is `{"message":"Unauthorized"}` — Supabase
  rejecting the bearer token, NOT the Cloudflare edge-1010 UA block that
  `scripts/geo_enrich.py` and `scripts/ad_ingest_run.py` already carry a browser-UA fix
  for. The blast radius is every Management API consumer sharing the pair:
  `scripts/geo_enrich.py` (red and loud) and `daily.yml`'s `ad central — ingest
  split-test exposures` step running `scripts/ad_ingest_run.py`, which is wrapped in
  `set +e … exit 0` and so has been degrading SILENTLY behind a `::warning` for the same
  13 days. Separately, `SUPABASE_PROJECT_REF` is not a repo secret at all — it renders
  empty in the run env (a set secret masks as `***`) and only works because
  `geo_enrich.py` falls back to a hardcoded `fsldfzlxyavsuwqbceod`.
falsifier: >
  `gh api repos/mastermindx-market-intelligence/macro/actions/secrets --jq '.secrets[]|
  select(.name=="SUPABASE_ACCESS_TOKEN")'` showing an `updated_at` more than ~30 days
  before a run that still authenticates, or a `geo-enrich` run concluding success on a
  PAT older than 30 days. Either refutes the 30-day TTL.
so_what: >
  When a Supabase-backed lane starts 401ing with no code change, check the secret's
  `updated_at` age FIRST — do not debug the script, the URL, the UA, or the project ref.
  Neither `scripts/geo_enrich.py` nor `.github/workflows/geo-enrich.yml` had changed since
  2026-07-14, so every code-side hypothesis was dead on arrival. The remedy is always the
  same and is OPERATOR-ONLY: mint a fresh `sbp_…` PAT and update the
  `SUPABASE_ACCESS_TOKEN` repo secret. Rotating it also un-freezes `ad_ingest_run`, which
  will not tell you it is broken. Budget ~30 days from each rotation.
kind: landmine
verified_at: 2026-08-26
verified_by: >
  gh run list --workflow geo-enrich.yml (0 success / 88 failure / 12 cancelled in last
  100); gh run view 31698815868 / 31707633952 / 32944647884; secret updated_at
  2026-07-14T13:08:18Z; repaired-lane dispatch run 32947717639 capturing the provider
  body `{"message":"Unauthorized"}`; PR #6468
scope:
  - mastermindx-market-intelligence/macro
  - scripts/geo_enrich.py
  - scripts/ad_ingest_run.py
  - .github/workflows/geo-enrich.yml
confidence: verified
---

The timeline is the whole argument. `scripts/geo_enrich.py` last changed 2026-07-14
(`074cfd1f1698`); `.github/workflows/geo-enrich.yml` last changed 2026-07-13
(`f450333bcbbf`). The secret was written 2026-07-14T13:08:18Z. The lane then ran green for
30 days and died between 12:10:34Z and 13:57:48Z on 2026-08-13 — bracketing 13:08:18Z. No
code moved; the clock did.

What makes this a landmine rather than a log line is that the estate has no instrument
pointed at it. A PAT expiry is invisible to every staleness check we own: the secret still
exists, `updated_at` still reads July 14, and the only symptom is a 401 at request time.
The `geo-enrich` badge went red and stayed red for 13 days without anyone reading it,
while its sibling on the same credential — `ad_ingest_run` under `daily.yml`, wrapped in
`set +e … exit 0` — produced no signal at all. Prefer the loud lane when auditing: if
`geo-enrich` is 401ing, assume every Management API consumer is dead and check the quiet
ones by hand.
