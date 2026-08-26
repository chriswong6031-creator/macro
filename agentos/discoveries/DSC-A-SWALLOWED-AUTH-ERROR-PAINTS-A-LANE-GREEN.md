---
key: A-SWALLOWED-AUTH-ERROR-PAINTS-A-LANE-GREEN
claim: >
  A broad per-item `except Exception: failed += 1` inside an enrichment loop converts a
  CREDENTIAL failure into a benign per-item counter, so the loop runs to completion and
  the lane reports success having written NOTHING. Measured against unmodified
  `scripts/geo_enrich.py` on 2026-08-26: a 401 raised by `upsert()` produced
  `{"ok": true, "pending": 2, "enriched": 0, "failed": 2}` and exit code 0. The read-plane
  version of the same fault was loud (an unhandled traceback), so the lane that WAS
  visibly broken was the lucky one; a PAT that lapsed between the read and the writes
  would have gone green instead. `public.ip_geo` is `LEFT JOIN`ed by every view in
  `admin/analytics_first_party.py`, so a false green there serves advancing analytics
  events against frozen geography with no signal anywhere.
falsifier: >
  `python3 -m pytest tests/test_geo_enrich.py::test_credential_rejected_during_upsert_never_reports_success`
  passing against a `run()` whose per-IP handler catches `CredentialRejected` into
  `failed`, or any run summary reporting `ok: true` alongside `reason:
  credential_rejected`.
so_what: >
  An auth/credential exception is a WHOLE-RUN terminal state, never a per-item failure —
  catch it ahead of the broad `except Exception` (it is a `RuntimeError`, so ordering is
  load-bearing) and abort. When auditing any batch enrichment lane, ask "what does a dead
  credential on the WRITE plane do here" separately from the read plane; the read plane
  failing loudly does not mean the write plane will. Do NOT resolve a credential fault by
  exiting 0 to clear a red badge: a lane that cannot enrich must stay red, but it must
  name the credential to rotate in a line-start `::error` annotation rather than a bare
  traceback — `geo-enrich` sat red for 13 days / ~370 runs precisely because the red
  carried no diagnosis.
kind: landmine
verified_at: 2026-08-26
verified_by: >
  direct execution against unmodified scripts/geo_enrich.py returning
  `{"ok": true, "enriched": 0}` + exit 0; tests/test_geo_enrich.py (22 cases, 6 red before
  the fix); PR #6468
scope:
  - mastermindx-market-intelligence/macro
  - scripts/geo_enrich.py
  - admin/analytics_first_party.py
confidence: verified
---

The asymmetry is the lesson. `scripts/geo_enrich.py` calls the same `_sql()` helper from
two places: `pending_ips()` on the read plane and `upsert()` on the write plane. An
identical 401 produced opposite outcomes — an unhandled traceback and a red badge from the
read, a silent `failed += 1` and a GREEN run from the write — purely because the write
call sat inside a `try` whose last handler was `except Exception`. Nobody chose that; it
fell out of a handler written to keep one bad IP from ending a 900-IP batch.

That is the general shape worth carrying: broad per-item handlers are correct for per-item
faults and catastrophic for whole-run faults, and the two are indistinguishable at the
catch site unless the whole-run class has its own exception type. Giving the credential
fault a named type (`CredentialRejected`) and catching it ahead of the broad handler is
what separates them. The fix deliberately did NOT make the lane green — a lane that cannot
enrich must stay red — it made the red legible, which is a different and smaller claim
than "the lane is repaired".
