# F12 — Post-tenancy commercial and account scope: what changes when an account becomes a team

**Packet:** B-F12-6 · lane `marketontology-b4-f12-commercial-scope` · wave B4 · records-only
**Rows closed:** MO-PAID-079 (commercial_only) · MO-PAID-080 (account_only)
**Observed at:** 2026-09-06 · macro `main`; terminal reference = PR #514 (read-only)

## 0. Where this lives

<!-- backlinks -->
- Masterplan: `research/market_intelligence_productization/MASTERMIND_MARKET_INTELLIGENCE_PRODUCTIZATION_MASTERPLAN_2026-08-23.md`
- Ledgers: `MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv` (rows 118-119, read-only input to this packet)
  and `MARKET_ONTOLOGY_F00B_CURRENT_CAPABILITY_CROSSWALK_2026-08-28.csv` (rows 119-120, read-only input to this packet).
  Neither CSV is edited by this packet; row-status reconciliation is the wave owner's act.

## 1. Plain-words answer in three sentences

A seat is a membership row, not a licence. Creating a team changes nothing about an existing
subscription — no charge, no plan switch, no seat charge is issued, because macro entitlement is
keyed on the individual user, not on a team. And no account setting becomes workspace-scoped
today — every account setting macro exposes stays scoped to the signed-in user, exactly as before
a team existed.

## 2. What a seat is

A seat is **one Supabase auth user holding one membership row** in `public.team_members` for that
team: `unique (team_id, user_id)`, `role text not null check (role in ('owner','admin','member'))`
(terminal#514 `supabase/migrations/0014_tenancy_foundation.sql`, tables `teams` / `team_members` /
`team_invites`).

**A seat is membership, not a licence.** Entitlement in macro is keyed on the individual user:
`read_entitlement(user_id)` reads `public.user_entitlements?user_id=eq.<uid>`
(`macro:app/billing.py:643`, query at `macro:app/billing.py:658`) and writes upsert on
`on_conflict=user_id` (`macro:app/billing.py:694`). There is no team key anywhere in that path.

**NULL (typed `NOT_BUILT`, printed in plain words):** there is no `seat_limit` column, and no seat
count, in the tenancy foundation — a case-insensitive grep of the whole terminal#514 diff for
`seat` returns 0 hits.
The advertised "Team workspace / up to 10 seats" capability is `NOT_BUILT` and not enforced anywhere in this codebase (ledger MO-PAID-051, F00B crosswalk row 114: evidence "No team_id/tenant_id/seat_limit/workspace_id hits in app/, engine/, or charting-app source").
Independently re-verified in this checkout with extended-regex
`grep -rnE "team_id|seat_limit|workspace_id" app/ engine/ templates/` (a literal BRE grep
without `-E` returns 0 hits everywhere and is not usable evidence): `app/` returns 0 hits;
`engine/` returns 23 hits, all macro-workspace routing identifiers unrelated to tenancy
(`engine/market_os/macro_workspaces/build.py` lines 306, 328, 332, 336, 340, 344, 348, 352,
359, 366, 371, 376, 381, 386, 391, 396; `engine/market_os/macro_workspaces/registry.py` lines
305, 306, 309 and siblings; `engine/market_os/macro_workspaces/trade_flows.py:57`); `templates/`
returns 14 hits, one per `macro_*.html.j2` workspace template's
`data-mq-workspace="{{ workspace_id }}"` attribute (e.g.
`templates/macro_business_activity.html.j2:32`, and the 13 sibling `macro_*.html.j2` files) —
again macro's unrelated content-workspace routing, not tenancy. So no tenancy-scoped code (team
seats, workspace-as-tenant) exists in `app/`, `engine/`, or `templates/` today; the identifier
`workspace_id` is reused for macro's own content-workspace routing.

## 3. What happens to an existing single-user subscription when a team is created

**Nothing.** Creating a team inserts rows in `public.teams` and `public.team_members` (plus
optionally `public.team_invites`) and touches no billing object. The tenancy foundation states
this as law in its own source, twice: `// TWO-ORGANISMS LAW (UWP-R2): teams grant nothing.
Entitlement authority stays macro-api; nothing here reads or writes profiles.is_pro.`
(terminal#514 `terminal/app/api/teams/route.ts` header comment; repeated in
`terminal/lib/teams.ts`). Concretely, after a team exists:

- the creator keeps their own Stripe customer (`macro:app/billing.py:560 _stored_customer(user_id)`,
  `macro:app/billing.py:598 _existing_customer(user_id)`) and their own entitlement row
  (`macro:app/billing.py:679 _upsert_entitlement(user_id, ...)`);
- every other member keeps whatever tier they personally hold, **including `free`** — membership
  grants no tier;
- no proration, no plan switch, no new charge, no seat charge is issued, because no seat-priced
  product exists (see §6 ceilings);
- the Stripe lifecycle endpoints are unchanged and remain user-scoped: checkout
  `macro:app/billing.py:932`, offers `macro:app/billing.py:1002`, portal
  `macro:app/billing.py:1008`, config `macro:app/billing.py:1050`, subscribe init/complete
  `macro:app/billing.py:1070`/`macro:app/billing.py:1149`, upgrade `macro:app/billing.py:1265`,
  webhook `macro:app/billing.py:1587`.

**Typed state:** single-user billing = `PROVEN_LIVE` (unchanged); team/seat billing = `NOT_BUILT`
(`DEFER` — dependency the tenancy foundation, F00C row for MO-PAID-079).

## 4. Which account settings become workspace-scoped

**Today: none of macro's account settings become workspace-scoped.** The full inventory of
account settings and their scope after a team exists:

| Setting | Owner (file:line) | Scope after a team exists |
|---|---|---|
| Plan / entitlement display (plan pill) | `macro:app/main.py:1044` `/api/account` → `macro:templates/account.js:208`, pill rendered `macro:templates/account.js:397`, label map `macro:app/main.py:1036` `_PLAN_LABELS` | user-scoped (unchanged) |
| Whoami + entitlement + chat budget | `macro:app/main.py:1004` `/api/me` → `macro:app/main.py:1021` `billing.read_entitlement(user_id)` | user-scoped (unchanged) |
| Preferences | `macro:templates/account.js:242` `/api/account/prefs` | user-scoped (unchanged) |
| Email change | `macro:templates/account.js:438` `/api/account/email` | user-scoped (unchanged) |
| Password change | `macro:templates/account.js:451` `/api/account/password` | user-scoped (unchanged) |
| Sign out everywhere | `macro:templates/account.js:519` `/api/account/signout-everywhere` | user-scoped (unchanged) |
| Account deletion | `macro:templates/account.js:463` `/api/account/delete` | user-scoped; consequences are B-F12-4's to state, not this packet's |

The only genuinely workspace-scoped state that exists anywhere today is **team name, membership
and pending invites**, and it lives in terminal#514's three tables — governed by B-F12-3, not
here.

**NULL (typed `NOT_BUILT`, printed):** a team-shared / tenant-scoped entitlement view does not
exist (F00C row MO-PAID-080: `missing_contract_or_proof = team-scoped entitlement view`). Nothing
in macro reads a `team_id` when computing or displaying a plan, and this packet does not invent
one.

## 5. What is NOT built (nulls, printed)

| Null | Typed state | Evidence |
|---|---|---|
| Seat/team billing (a seat-priced product or seat charge) | `NOT_BUILT` | `config/plans.yml` has zero `seat`/`team` hits; no Stripe product for seats exists |
| `seat_limit` enforcement (the "10 seats" claim) | `NOT_BUILT` — not enforced | zero `seat_limit` hits in `app/`, `engine/`, `templates/`; "10 seats" is marketing copy only |
| Team-scoped entitlement view | `NOT_BUILT` | no `team_id` read anywhere in `app/billing.py` or `app/main.py`'s entitlement/account paths |

For contrast, single-user billing itself is `PROVEN_LIVE` (§3) — the null is specifically the
team/seat layer on top of it, and it is a `DEFER` pending the tenancy foundation (B-F12-1) plus a
Chairman pricing decision (§6).

## 6. Ceilings and the Chairman defer

- **MO-PAID-079 — `commercial_only`.** This packet may *describe* commercial consequence. It may
  not create, rename, re-price, or imply any product, price, offer or seat charge.
  `config/plans.yml` contains **zero** seat/team products — a case-insensitive grep for
  `seat|team` in that file returns 0 — so a team plan would be a brand-new commercial object.
- **MO-PAID-080 — `account_only`.** Entitlement display may only render what the canonical owner
  returns (`macro:app/billing.py:643`). No team-shared entitlement may be synthesized, and no
  LLM-originated signal, score or escalation appears anywhere in this record.

> **Deferred to the Chairman:** no pricing, plan, price, offer, or seat-charge change is made or implied by this packet; any team pricing or seat-pricing decision is the Chairman's alone.

No trading authority is asserted; the record contains no signal, no rank, no size, no gate.

## 7. Boundaries against sibling packets

- **B-F12-1 (terminal#514, tenancy foundation) owns** the schema: teams, team_members, team_invites, their RLS policies and the two SECURITY DEFINER helpers. Read-only reference here; this packet changes no schema.
- **B-F12-3 (roles / invites lifecycle) owns** role semantics (owner/admin/member), invitation issue/accept/expire, membership mutation policy and access enforcement. This packet restates none of it and consumes only the fact that a member is a row in team_members.
- **B-F12-4 (export / deletion) owns** what data leaves or is destroyed, including account deletion (templates/account.js:463) and any team-scoped export. This packet names deletion only to hand its commercial and entitlement consequences to B-F12-4.
- **This packet (B-F12-6) owns** exactly two questions: what changes commercially (MO-PAID-079) and what changes in account/entitlement scope (MO-PAID-080) when an account becomes a team. No other surface is claimed.

## 8. Row closure

- **Acceptance (MO-PAID-079)**: team creation issues no charge, changes no plan, and switches no product — single-user billing stays `PROVEN_LIVE` untouched while seat/team billing remains `NOT_BUILT`, deferred to the Chairman.
- **Acceptance (MO-PAID-080)**: entitlement stays keyed on `user_id` end to end, no account setting becomes workspace-scoped today, and a team-scoped entitlement view is `NOT_BUILT` and not synthesized by this packet.

## 9. Evidence

`terminal:` refs are cross-repo, read-only references into `mastermind-terminal` PR #514; they are
declared unresolvable-in-CI here and are not asserted to resolve against this repository's tree.
This is a records file, not a product evidence surface — no EvidenceBlock/EvidenceRecipe JSON is
emitted.

| claim | ref | observed_at |
|---|---|---|
| entitlement read is keyed on user_id | macro:app/billing.py:643 | 2026-09-06 |
| entitlement read query is user-scoped | macro:app/billing.py:658 | 2026-09-06 |
| entitlement upsert is keyed on user_id | macro:app/billing.py:694 | 2026-09-06 |
| stored Stripe customer is per-user | macro:app/billing.py:560 | 2026-09-06 |
| existing Stripe customer lookup is per-user | macro:app/billing.py:598 | 2026-09-06 |
| entitlement upsert function is per-user | macro:app/billing.py:679 | 2026-09-06 |
| checkout endpoint is user-scoped | macro:app/billing.py:932 | 2026-09-06 |
| offers endpoint is user-scoped | macro:app/billing.py:1002 | 2026-09-06 |
| portal endpoint is user-scoped | macro:app/billing.py:1008 | 2026-09-06 |
| billing config endpoint is user-scoped | macro:app/billing.py:1050 | 2026-09-06 |
| subscribe init endpoint is user-scoped | macro:app/billing.py:1070 | 2026-09-06 |
| subscribe complete endpoint is user-scoped | macro:app/billing.py:1149 | 2026-09-06 |
| upgrade endpoint is user-scoped | macro:app/billing.py:1265 | 2026-09-06 |
| webhook endpoint is user-scoped | macro:app/billing.py:1587 | 2026-09-06 |
| /api/me reads entitlement | macro:app/main.py:1004 | 2026-09-06 |
| /api/me calls read_entitlement(user_id) | macro:app/main.py:1021 | 2026-09-06 |
| plan label map is user-scoped | macro:app/main.py:1036 | 2026-09-06 |
| /api/account endpoint is user-scoped | macro:app/main.py:1044 | 2026-09-06 |
| account page fetches /api/account | macro:templates/account.js:208 | 2026-09-06 |
| plan pill renders from user-scoped data | macro:templates/account.js:397 | 2026-09-06 |
| preferences endpoint is user-scoped | macro:templates/account.js:242 | 2026-09-06 |
| email change endpoint is user-scoped | macro:templates/account.js:438 | 2026-09-06 |
| password change endpoint is user-scoped | macro:templates/account.js:451 | 2026-09-06 |
| sign-out-everywhere endpoint is user-scoped | macro:templates/account.js:519 | 2026-09-06 |
| account deletion endpoint is user-scoped | macro:templates/account.js:463 | 2026-09-06 |
| tenancy foundation schema (cross-repo, read-only reference) | terminal:supabase/migrations/0014_tenancy_foundation.sql | 2026-09-06 |
| TWO-ORGANISMS law comment (cross-repo, read-only reference) | terminal:app/api/teams/route.ts | 2026-09-06 |
