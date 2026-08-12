# Mastermind-X — Launch Gates

**Audit date:** 2026-08-12

Every gate below is **falsifiable**: it names a command to run or an artifact to produce, and
a pass condition someone else can check. A gate that cannot be checked is not a gate.

Gates derived from *this* architecture. Deliberately short — 6 must-fix items, not 40.

---

## MUST FIX BEFORE LAUNCH

### GATE-1 — Recovery gate: a restore has actually been performed

**Why:** MMX-001. Every other risk degrades service; this one destroys the record of who
paid you. No `pg_dump`, `pg_restore`, or PITR reference exists anywhere in the repo.

**Pass condition — all four:**
1. The active Supabase plan's backup/PITR setting is confirmed in writing (screenshot or
   API response), with its retention window stated.
2. A real restore into a scratch project has been performed **at least once**, and the
   measured RTO is written down.
3. A nightly `pg_dump` of the 7 user tables (`profiles`, `watchlists`, `watchlist_symbols`,
   `chart_layouts`, `saved_scripts`, `alerts`, `favorites`) plus `user_entitlements` and
   `stripe_events` ships to R2 with ≥30-day retention.
4. `docs/` contains a restore runbook naming the exact commands.

**Verify:** `ls` the R2 backup prefix for last night's dump; open the runbook; point at the
recorded RTO.

**Owner:** Ops / backend lead · **Est:** 4–6 hours

---

### GATE-2 — Cost gate: quota caps survive concurrency

**Why:** MMX-002/003/005. The quota ledger is the only thing between an anonymous visitor and
an unbounded Anthropic bill, and unlocked read-modify-write means *N* parallel requests cost
one quota unit.

**Pass condition — all four:**
1. Check-and-increment is atomic (`fcntl.flock` on the ledger, or the counter moved to
   Postgres with `UPDATE … RETURNING`).
2. Ledger writes are atomic (`tmp` + `os.replace`). A corrupt ledger alarms; it does not
   silently read as `count: 0`.
3. Guest quota **fails closed** on I/O error. Authenticated paying users may keep failing
   open — that asymmetry is correct and should be deliberate.
4. A global daily spend ceiling exists, independent of per-user ledgers.

**Verify (this is chaos test #2):** fire 50 concurrent requests from one guest identity
against a cap of 10. Pass = at most 10 succeed. Today's expected result is ~50.

**Owner:** Backend / AI platform · **Est:** 1 day

---

### GATE-3 — Availability gate: Supabase Auth cannot take the product down

**Why:** MMX-004. `require_user` makes an uncached, blocking, 5s-timeout call to Supabase on
every authenticated request, inside a ~40-thread pool. 40 concurrent users is the first
scale cliff, and a Supabase slowdown stalls even unauthenticated routes.

**Pass condition — all three:**
1. `require_user` uses the same short-TTL token cache `app/paywall.py:_fresh_identity`
   already implements (≤60s, keyed on `sha256(token)`). The code exists in-repo; it is not
   new work.
2. Concurrent upstream auth calls are bounded by a semaphore so a slow vendor sheds load
   rather than exhausting the pool.
3. `/api/health` remains responsive while Supabase is unreachable.

**Verify (chaos test #1):** block Supabase at the firewall; confirm `/api/health` still
answers and that cached sessions continue to work for the cache TTL.

**Owner:** Backend lead · **Est:** 0.5 day

---

### GATE-4 — Commercial observability gate: someone is paged before a customer tweets

**Why:** the brief's standard — *"if the first alert is a customer tweets at us, the system
is not ready."* Data freshness is well monitored by the sentinel. The **commercial** path has
no alarms at all.

**Pass condition:** an alert fires to a channel a human watches for each of:
1. Stripe webhook failure rate / no webhook received in N hours
2. Checkout creation failures
3. Authentication error-rate spike (`502` from `require_user`)
4. **LLM spend rate above a daily threshold** — the one that protects GATE-2 in depth
5. The existing `::error::` quota fail-open line

**Verify:** trigger each condition in staging and confirm the alert arrives. Reuse the
sentinel's existing Telegram/Discord/email transport — no new vendor needed.

**Owner:** Ops · **Est:** 1 day

---

### GATE-5 — Secret-history gate

**Why:** the working tree is clean (no `SERVICE_ROLE` or JWT literals in `templates/`
or `site/`; all secrets in root-only `0600` env files). **Git history was not scanned.**

**Pass condition:** `gitleaks detect --log-opts="--all"` (or equivalent) runs clean across
all three repositories, or every hit is triaged and the corresponding credential rotated.

**Verify:** the scan output.

**Owner:** Security / backend · **Est:** 2 hours

---

### GATE-6 — Isolation-invariant gate: a test protects the thing that matters most

**Why:** `_pg()` authenticates with `SUPABASE_SERVICE_ROLE_KEY`, which **bypasses RLS
entirely**. Today this is safe only because every `user_id` derives from a Supabase-verified
token and never from client input. That invariant is currently protected by convention alone —
one future endpoint accepting `user_id` from a request body becomes full cross-tenant access.

**Pass condition:** a CI test asserts that no route handler derives a `user_id` from
request body, query, or path parameters. (A simple AST check in the style of the existing
`scripts/check_*.py` house-law guards fits the repo's own idiom.)

**Verify:** the test fails when a deliberately-added offending handler is introduced —
i.e. prove the guard can see the failure, not merely that it is green.

**Owner:** Backend · **Est:** 3 hours

---

## SHOULD FIX BEFORE SCALE

| # | Item | Finding | Condition |
|---|---|---|---|
| S-1 | **Multi-worker API** | MMX-006 | `--workers 2+`. **Must land after GATE-2** — extra processes make an unlocked file ledger strictly worse. |
| S-2 | **Webhook claim-before-handle** | MMX-007 | `INSERT` the event id first (unique-constraint rejection = duplicate), then handle. A store exception means "cannot verify" ⇒ let Stripe retry, don't proceed. Verify with two concurrent identical deliveries producing one email. |
| S-3 | **One rate-limit policy** | MMX-008 | The 31 unauthenticated `government_revenue` + `hub` routes get the `_allow_request` treatment `company_intelligence` already has, ideally as middleware. **Also resolve the open question: does EdgeOne provide edge rate limiting?** |
| S-4 | **Dunning grace decision** | MMX-014 | An explicit product ruling on whether `past_due` customers keep access during Stripe's retry window. Either answer is defensible; inheriting the default silently is not. |
| S-5 | **Identity sentinel removal** | MMX-011/012 | `user.get("id") or user.get("email") or "unknown"` becomes a hard 401. No constant sentinel as an identity key. |

---

## POST-LAUNCH HARDENING

| # | Item | Finding |
|---|---|---|
| H-1 | Fix the 3 naive `datetime.now().date()` sites (`special_arb.py:194`, `congress_members.py:155`, `signal_sanity.py:344`) | MMX-010 |
| H-2 | Ratify or shorten the 24h positive-entitlement grace; document it as policy | MMX-009 |
| H-3 | Delete or wire up the dead `_PUBLIC_GET` set in `admin/server.py` | MMX-013 |
| H-4 | Move durable counters (quota, token ceilings, credit pools) off the local filesystem into Postgres | Structural |
| H-5 | Add an error tracker (no Sentry-equivalent found in any repo) | Part XIX gap |
| H-6 | Trace the LLM JSON/schema-failure path — currently unverified (chaos test #7) | Part XXIII gap |
| H-7 | Dedicated corporate-actions / splits / delistings correctness pass | Part VII, not covered |

---

## Explicitly NOT gates

Recording what this audit decided **not** to demand, since over-gating is its own failure
(Part XXX):

- **No Kubernetes, no autoscaling, no service mesh.** A single VPS with systemd timers is the
  right architecture at this scale and removes entire classes of failure.
- **No queue broker.** Choosing systemd timers over Celery/Redis structurally eliminates
  duplicate delivery, poison messages, and unbounded queue growth.
- **No auth rewrite.** Secretless network verification is a genuinely strong design. It needs
  a cache, not a redesign.
- **No entitlement re-architecture.** One canonical table, one writer, one reader is already
  what the brief asks for.
- **No additional observability vendors.** The sentinel's existing transport covers GATE-4.
- **No CSRF tokens on the public API.** It is bearer-token authenticated, not cookie
  authenticated; CSRF does not apply. The admin console — which *is* cookie-authenticated —
  already has double-submit CSRF.

---

## Gate summary

| Gate | Finding | Effort | Blocks launch? |
|---|---|---|---|
| GATE-1 Recovery | MMX-001 | 4–6h | **YES** |
| GATE-2 Cost | MMX-002/003/005 | 1d | **YES** |
| GATE-3 Availability | MMX-004 | 0.5d | **YES** |
| GATE-4 Commercial alerts | Part XIX | 1d | **YES** |
| GATE-5 Secret history | Part XVI | 2h | **YES** |
| GATE-6 Isolation invariant | Part IV | 3h | **YES** |

**Total critical path: roughly 3–4 engineer-days.** All six are small, well-scoped, and
independently verifiable. None requires re-architecting anything.
