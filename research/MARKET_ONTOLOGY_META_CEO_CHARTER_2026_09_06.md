# Market Ontology Meta-CEO Charter (2026-09-06)

Binding charter for the two Claude Meta-CEOs of the Market Ontology program. A cold-start
session on the Claude3 account (Meta-CEO B) can pick up half B from this file alone, plus
`origin/main` and this repo's `CLAUDE.md`/`AGENTS.md`. This file does not restate CLAUDE.md
law — it points to it and adds only what is specific to this program.

Source note for the reader: this charter was compiled by a routed `drafter` session from a
frozen decisions seed written by Meta-CEO A (Claude8 session `5b29ad85-0490-42c8-b5e4-1e32b1922014`)
plus a fresh multi-file census of the repo, GitHub, and Slack state. Every seed decision in
`§0`-`§8` is reproduced as written; census facts fill in row IDs, PR states, and file paths.
Where the census could not resolve a fact, this file says `UNKNOWN` and names who resolves it
— it does not invent a value.

## §0 Authority

Chairman Chris, in the Claude8 chat on 2026-09-05 PDT (after 05:15Z on 2026-09-06 UTC), wrote:

> "We are working too slowly and nothign is being actively built out. I have overridden the
> ChatGPT CEO and placed you as Claude Meta-CEO for this project, to take it on completely and
> deliver an end to end solution for us. First i want you to create a counterpart who can be
> responsible for half of the project tasks, and give them the same authority as you and
> information you have, so that we can hand off to a sister claude account next door and work
> side by side on both accounts, as the usage limits are resetting on both accounts soon. Then
> i want you both to immediately intiiate fan out of building the complete build out of
> MarketOntology autonomously end to end without requiring ChatGPT orchestration or oversight
> or more of the administrative and bureaucracy burden. You are more than capable of taking on
> the orchestrator role completely. You should also not need to ask me for anything or
> permissions for anything."

Follow-ups in the same turn:

> "F08 and F13 currently exist on the other claude account, Claude3 account. You are Claude8
> account. So we can keep those there and u can add additional things for that orchestrator to
> take on."

> "Ultracode is now on."

> "u can use computer-use to command the other claude accounts. theres four claude mac apps in
> total, we want to prioritize using this current one and Claude 3 since the limits are going to
> reset soon. But the other two can be used as well when needed. The priority is just to get
> this marketontology program completely finished."

**What this supersedes, for this program only:** the ChatGPT CEO ("Sol", ChatGPT3
`U0BR1GQH7SB`) and the Grok Secretary transport are relieved of authority over the Market
Ontology program; every past Sol ruling, HOLD-FOR-SOL label, and READ_ONLY_ARCHAEOLOGY state on
a Market Ontology PR or lane is history, not a gate, from this override forward. This also
supersedes the 2026-08-29 hierarchy amendment's do-not-redo lines "Do not flatten the hierarchy
back into Meta-CEO -> generic coding workers" and "Do not treat Computer Use typing as pickup"
**for this program** (a receiver-side ACK is kept as a one-comment receipt — see §4). Nothing
else in CLAUDE.md, AGENTS.md, `research/DO_NOT_REBUILD.md`, or any other program's authority is
touched by this override.

**Chairman Chris remains final authority.** A Chairman message in ANY Claude chat (Claude3,
Claude8, or either auxiliary app) binds both Meta-CEOs immediately, overrides anything in this
charter, and does not require a permission request back.

**Timing note for the receiving session:** the most recent Sol/Root comments on macro#6819
(2026-09-06T00:10Z-00:34Z, covering PR #6890's "Stage A"/"Stage B" release procedure) predate
this override by several hours. They no longer bind. But re-read GitHub state fresh before
acting on #6890 (see §5 Wave 0) — Root's "Stage B" disarm step may have already executed between
the census and whenever you read this.

## §1 Roles

- **Meta-CEO A** = Claude8 account, Code session `5b29ad85-0490-42c8-b5e4-1e32b1922014`
  (app-realm `local_a43a5e87-f178-472b-bde0-c6f4bda22a1b`, Slack seat Claude8 `U0BS3H525NW`).
  Runs Fable in the main loop. Wrote this charter's frozen decisions.
- **Meta-CEO B** = Claude3 account (Slack seat `U0BSLFRGA79`; already hosts the F08 "Portfolio
  alerts monitoring" and F13 "OPS learning reliability Fable" sessions). B is co-equal: same
  authority, same information (this charter + `origin/main`), sovereign inside its half.
- **Auxiliary capacity** = the two other running Claude desktop apps. Either Meta-CEO may
  commission them (by typing a packet via computer-use, or by the Chairman pasting one) as
  additional lane executors. A commissioned auxiliary session ACKs with one comment on
  macro#6819 naming its session id and lane, then owns that packet to merge + live proof.
- **Workers** = workflow subagents (`builder`/sonnet, `reviewer`/opus, `designer`/opus,
  `analyst`/opus, `scout`/sonnet, `drafter`/sonnet, `debugger`/opus) per CLAUDE.md §Model
  routing. Meta-CEOs adjudicate; they do not grind code in the main loop.

## §2 Program definition and DONE

- **Backlog of record** =
  `research/market_intelligence_productization/MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv`
  (130 ids: 88 MO-PAID + 42 MO-DELTA; per lane F01=12 F02=10 F03=16 F04=9 F05=4 F06=3 F07=5
  F08=7 F09=29 F10=5 F11=6 F12=18 F13=6; dispositions NEW_BOUNDED_BUILD 46,
  UPGRADE_EXISTING_OWNER 40, PROJECTION_ONLY 20, BLOCKED_RIGHTS 7, CONTEXT_ONLY 7,
  EXACT_EQUIVALENT 5). The 1,556-row historical P1 corpus stays a separate gated denominator —
  do not import or reconstruct it (see §9).
- **Product target** = a coherent Mastermind product across Macro (mastermind-x.com, static
  site + engine, LIVE per `curl -sI https://www.mastermind-x.com/` → HTTP/2 200) and Terminal
  (app.mastermind-x.com, Next.js + Supabase, LIVE and redirecting to `/terminal`), reachable
  through the two existing nav families. NOT a clone: never copy Market Ontology proprietary
  code, text, data, assets, branding, or hidden interfaces (DNR + program do-not-redo bind).
- **DONE for the program** = every ledger row terminal with proof: NEW_BOUNDED_BUILD /
  UPGRADE_EXISTING_OWNER / PROJECTION_ONLY rows are merged AND live-verified (live URL +
  readback/screenshot in the PR body) with the ledger status updated in the same or next PR;
  BLOCKED_RIGHTS rows carry a recorded rejection naming the commercial/rights gate (a Chairman
  decision, not a build); CONTEXT_ONLY / EXACT_EQUIVALENT rows carry a pointer to the existing
  owner. **DONE for any packet** = merged + live-verified (fleet law), never "PR open".

## §3 The split (whole lanes; exclusive path ownership follows the lane)

| Lane | Half | Ledger rows | Key PRs (open, per census) | Repo weight |
|---|---|---|---|---|
| F00 shared shell/nav/contract freeze + integration | A | n/a (program control) | #6819 (carrier) | macro |
| F01 Macro/Markets/Briefings | A | 12 | #6873 (hub R1), #6890 (pack-5 repair), #6826 (architecture) | macro + read-only Terminal projections |
| F02 Policy/Geo | A | 10 | #6834 (F02-X1 sanctions geography) | UNKNOWN (inferred macro via WS:MARKET-OS) |
| F03 Options/Expression | A | 16 | #6604 (Options C0 lineage, state UNKNOWN — see §10) | UNKNOWN (inferred macro, Options owner) |
| F04 Ontology/Transmission/Opportunity | A | 9 | #6872 (X1 WTI), #6809 (D2C, state UNKNOWN — see §10), #6820 (merged records) | macro (explicit PR numbers) |
| F05 Event/Impact/Catalyst | A | 4 | none open in census | UNKNOWN |
| F10 Quant/Analogs | A | 5 | #6830 (F10-X1 implication cards) | UNKNOWN |
| F01F13 Market Orientation (cross-cutting AM Edition -> Indicator Library -> Glossary, `DEC-MARKET-ONTOLOGY-MARKET-ORIENTATION-PROJECTION-2026-08-30`, currently UNPLACED) | A | n/a | none | macro (`scripts/build_aibrief.py`, `templates/aibrief.html.j2`) |
| **A subtotal** | | **56 rows + shell** | | |
| F06 Security/Ticker Workspace | B | 3 | #6831 (MSFT security_state child) | UNKNOWN (Market OS/Terminal projections implied) |
| F07 Valuation/Scenario | B | 5 | none open in census | UNKNOWN |
| F08 Portfolio/Alerts | B | 7 | #6892 (architecture freeze, not held), #6526 (badge refresh, not held) | UNKNOWN (already on Claude3) |
| F09 Capital/Ownership/Materials | B | 29 | #6793 (F09-1, cash-deal premium) | UNKNOWN |
| F11 Human Research/Thesis/RMS | B | 6 | Terminal #502 (Thesis Object migration) | macro + Terminal (Supabase) |
| F12 Team/Tenant/API/Platform | B | 18 | none open in census | UNKNOWN; Supabase-owned |
| F13 Ops/Learning/Reliability | B | 6 | #6861 (F13 capability health V1) | UNKNOWN (already on Claude3) |
| Supabase migration-ledger namespace settlement + identity/tenant contract freeze (F11/F12 depend on it) | B | n/a | Terminal #502, #507 | Terminal (charting-app) |
| **B subtotal** | | **74 rows + platform** | | |

**Shared surfaces:** A owns the Macro shell (`templates/_site_nav.html.j2`,
`_navlinks.html.j2`, `_public_nav.html.j2` family, `theme.css`/`theme.js`,
`navigation-refresh.css`, `research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md`,
`docs/DESIGN_DOCTRINE.md`, the ledger CSV's schema). B owns the Terminal shell (charting-app
`terminal/app` layout/nav), `supabase/migrations` namespace, identity/tenant/entitlement
contracts, alert delivery plumbing. A cross-half change: open the PR, label it
`meta-ceo-shared`, comment on #6819 — do NOT wait; the owning half reviews at its next wave
boundary and may follow up with its own PR. Conflicts: the surface owner decides.

**PR allocation rule** for open program PRs: a PR belongs to the half that owns its lane (by
branch name/title/files); unknown -> A adjudicates within one wave. See §5 for the concrete
Wave 0 table built from this rule.

## §4 Coordination protocol (minimal)

- **Running log** = comments on macro#6819 (git carrier). Each Meta-CEO posts ONE comment per
  wave boundary: wave id, packets shipped (PR, merge sha, live URL), packets failed, ledger rows
  closed, next wave. One comment per takeover of a previously held PR ("Meta-CEO A taking PR #N
  under the Chairman override; owner session X may stop"). Optionally mirror to Slack root
  `C0BSBM78V1N/1788510607.305039` — Slack is a record, not a gate.
- **Durable state** = `agentos/handoffs/MARKET-ONTOLOGY-META-CEO-A-<date>.md` and
  `...-META-CEO-B-<date>.md`, each written ONLY by its owner at wave boundaries (never edit the
  other's), plus the ledger CSV row edits (row-level; rebase on conflict). No new stores.
- **Held-PR takeover procedure:**
  1. Fresh-read the PR (state, head, checks, last comment).
  2. If a live session commented on it within 2h and shows in-flight work, post the takeover
     comment and wait ONE wave (not longer); otherwise take it now.
  3. Opus `reviewer` pass on the diff against fresh `origin/main`.
  4. Fix blockers via `builder`.
  5. Mark Ready, `gh pr edit --add-label merge-on-green`, wait for CONCLUDED checks,
     squash-merge, live-verify.
  6. Comment the merge sha + live proof on #6819.
  Never close a held PR as "superseded" without a diff against fresh main proving the content
  already landed.
- **Decisions:** the half owning the lane rules; cross-half -> both, A tiebreaks on Macro
  surfaces, B on Terminal/platform; a Chairman message overrides both. Every durable choice ->
  DEC record in the same PR; every verified non-obvious fact -> DSC.
- **No waiting protocols** (for this program only): no HOLD-FOR-SOL, no
  READ_ONLY_ARCHAEOLOGY as a lane state, no PICKUP_ACK/START ceremony beyond the one comment, no
  DECISION_REQUEST to Sol, no exact-root Slack re-reads before every act (a fresh read of GitHub
  state before every push/merge is still required — that is ordinary fleet law, not a Sol
  ceremony).

## §5 Waves

### Wave 0 (both, immediately): heal main and release the held backlog

PR allocation table (13-PR tight census set + #6890 + the three named Terminal PRs; state as
captured by the census, re-read fresh before acting):

| PR | Half | Current state (census) | Wave 0 action |
|---|---|---|---|
| macro#6890 | A (F01) | **MERGED** as `7db17edb53d1141abeff2f9ef8846b6a4771873c` at 2026-09-06T01:33Z (Root released its hold at 01:33Z); main proven green on that merge by ci.yml run 34005007960 (workflow_dispatch, success) | Nothing to do — main is healed. Every later PR rebases onto this base. |
| macro#6873 | A (F01) | Draft, `HOLD-FOR-SOL — do not merge`, head `b7d237f0`, 0 reviews; collides with #6872 on `.github/ci/legacy-jobs.yml`, `app/deploy/Caddyfile`, `config/site_access.yml`, `tests/test_site_access_boundary.py` | Merge second, right after #6890 (heals pack-5 too). Global admission (NaN/True finite-number obligation) stays open per the F00 continuity reconciliation — resolve or explicitly re-scope before Ready. |
| macro#6872 | A (F04) | Draft, `HOLD-FOR-SOL`, head `ba62f5a5`, "PARTIAL / BUILT_NOT_PROVEN" | Rebase onto #6873 once it merges (shared-file collision above). Owes a corrected B-1 body + a RED-first nightly-hook test before Ready. |
| macro#6865 | A | Draft, `DRAFT / HOLD-FOR-SOL / SOURCE_LAW_CANDIDATE / SPEC_ONLY`, head `9f04ee4b`; first Opus review `5120047737` still CHANGES_REQUESTED, undismissed | A closes or disposes honestly (repaired but not approved; do not self-approve a candidate law). |
| macro#6604 | A (F03) | UNKNOWN — not resolved by the open-PR census's tight regex (branch likely named `options-intelligence-*`, excluded from the tight match); repeatedly cited elsewhere as the F03 commissioning owner for MO-PAID-070/076 and MO-DELTA-033 | A fresh-reads (`gh pr view` / `gh pr list --search`) before disposing; do not build a competing F03 workflow while its state is unread (see §10). |
| macro#6809 | A (F04) | UNKNOWN — same regex gap as #6604; last known state REQUEST_REPAIR, head `44c27dd3`, review `5110800144` (D2C) | A fresh-reads and disposes; do not absorb into F04 without an independent review. |
| macro#6861 | B (F13) | Draft, `HOLD-FOR-F13 — do not merge`; release condition named as "independent non-author Opus review PASS + F13 principal + Sol release" | B runs the named review itself (Sol release is no longer required, §0) and takes it to merge. |
| macro#6834 | A (F02) | Draft, `DRAFT / HOLD-FOR-SOL`, head `5d540ba`; PR's own file list hit the GraphQL 50-file cap, so its true diff may be larger than captured | A takes over per the held-PR procedure; re-pull the full file list before reviewing. |
| macro#6831 | B (F06) | Draft, `OPEN / DRAFT / HOLD-FOR-SOL / REVIEW_APPROVED / BUILT_NOT_PROVEN / PRODUCTION_INERT`, head `fca73b7` | Already review-approved — B verifies the approval still applies to the current head, then Ready/merge/live-verify. |
| macro#6830 | A (F10) | Draft, `HOLD-FOR-SOL — DRAFT — DO NOT MERGE`, head `693f6dd` | A takes over per the held-PR procedure. |
| macro#6826 | A (F01) | Draft, `OPEN / DRAFT / HOLD-FOR-SOL`, head `58e8cbb` | A takes over; note this is architecture-only (F01's 12/12 workspace suite already merged via #6836-#6849) — confirm it is not stale before reviving. |
| macro#6810 | A (adjudicate; program-wide) | Draft, `RECORDS_ONLY / DRAFT / HOLD-FOR-SOL`, head `2292068` ("checkpoint ontology continuation control state") | A disposes within Wave 0 per the unknown-lane rule (§3) — this is a continuation-control record, not a numbered lane. |
| macro#6793 | B (F09) | Draft, `HOLD-FOR-SOL — DRAFT. Do not mark ready, do not arm merge-on-green, do not merge.`, head `29b60c1`; maps to ledger row MO-PAID-064 / MO-DELTA-023 (cash-deal premium, EDGAR tender filings) | B takes over per the held-PR procedure — this hold no longer binds (§0). |
| macro#6595 | A (adjudicate; program-wide) | Draft, `DRAFT / HOLD-FOR-SOL / RECORDS-ONLY / NO LANE START / NO PRODUCT EFFECT` (Fable root-seat topology reconciliation) | A disposes as a records-only close; no product effect to release. |
| macro#6892 | B (F08) | **Not** Draft, label `merge-on-green`, no HOLD text found | Already unblocked — B verifies the armed merge-on-green completes (or takes it over if stalled) and live-verifies. |
| macro#6526 | B (F08) | **Not** Draft, no HOLD text, "refresh Portfolio badge after authoritative A1B reread" | B fresh-reads; if still open and green, take to merge. |
| terminal#490 | B | Draft, "fix: host existing Brain in Analysis shell", HOLD status unchecked by the census | B census's this PR before disposing (title carries no HOLD marker, but confirm). |
| terminal#502 | B (F11) | Draft, `[F11-1][HOLD]`, adds `supabase/migrations/0011_thesis_objects.sql` (private versioned Thesis Object) | B resolves the migration-namespace collision with #507 (see next row) before Ready. |
| terminal#507 | B | Open, labels `merge-on-green`,`merge-blocked`, adds `supabase/migrations/0011_analytics_eid.sql` (CA1A envelope-v1 identity) | **Numbering collision with #502** — both open PRs add a file named `0011_*.sql`. B settles which merges first and renumbers the loser before either lands (see §10 Supabase namespace question). |

*Note on an internal tension in the frozen seed:* §5's original prose lists "#6830, #6834,
#6861, #6826, #6810" under Meta-CEO B's Wave 0 actions ("remaining B-lane holds... by lane"),
but §3's explicit PR-allocation rule assigns #6830/#6834/#6826 to F10/F02/F01 (A's lanes) and
only #6861 is genuinely F13 (B's lane); #6810 is program-wide, not lane-specific. The table
above resolves this using §3's rule (the more specific, explicitly-named allocation law) —
lane ownership decides the half, not the sentence in §5. Either Meta-CEO may re-open this in a
DEC if they read it differently; until then, treat the table above as the working allocation.

Also in Wave 0: **B settles the Supabase migration-namespace collision** (both charting-app PRs
#502 and #507 independently claim `0011_*.sql`; per `agentos/discoveries/DSC-TERMINAL-HAS-NO-MIGRATION-LEDGER.md`,
Terminal's Supabase project has no `supabase_migrations` schema — files are hand-applied,
order-independent, source-of-record only). B greps every open charting-app PR for
`supabase/migrations` before assigning the next free number, merges one, and renumbers the
other in the same wave.

### Wave 1 (both): the first two independently useful verticals per lane

Copied from `agentos/handoffs/MARKET-ONTOLOGY-F00-FULL-SITE-RESTART-INTEGRATOR-2026-09-04.md`
L115-125 (the frozen critical-path seed), with ledger-row detail filled in from the F00C CSV.

**A also freezes the interim shared-contract list** (same file, L105-113) as the binding
contract page for this charter:

1. **Page shell/navigation** — only the two existing nav families; route additions follow the
   design-system archetype registry; no third header.
2. **Evidence/source/time/null/correction** — K1 EvidenceRef/EvidenceBlock/EvidenceRecipe
   contracts are the binding form; corrections are typed states.
3. **Authority** — the ledger's `authority_ceiling` column binds; LLMs never originate market
   facts, scores, or escalations.
4. **No-rebuild** — each lane's durable-handoff `do_not_redo` binds as written.
5. **Identity/tenant** — Stock Identity + Data OS for securities; Supabase auth for users; no
   new identity planes.

Every packet below runs through `Workflow({name:'marketontology-vertical-build', ...})` (§6).

#### Meta-CEO A packets

**A-F02-1**
- id: `A-F02-1` · lane: F02 · title: Base map + OFAC sanctions overlay
- repo: macro · kind: engine+ui
- ledger_rows: `MO-DELTA-031`, `MO-PAID-008`
- spec_sources: `engine/qbus.py` family (F02's stated owner engine, no direct hit found by the
  census — greenfield); `research/DO_NOT_REBUILD.md` (no second geospatial store)
- owned_paths: none existing named by the ledger (`real_producer: NONE` for both rows) —
  the `analyst` spec stage proposes the exact new engine module + template
- entry_points: UNKNOWN — no "Policy"/"Geo" nav item found in the current
  `templates/_navlinks.html.j2` census; the spec stage must place this under an existing nav
  family, not invent a third header
- acceptance (ledger `acceptance_test`): "a rendered base map with an OFAC sanctions overlay
  joined through an existing store"; missing_contract_or_proof: "base map + 4 layers; only
  base-map + sanctions overlay (OFAC public lists) are rights-clear" — chokepoint/military/
  satellite layers stay CONTEXT_ONLY behind the rights docket (do not build them here)
- live_url: TBD in spec (new page under an existing nav family)

**A-F02-2**
- id: `A-F02-2` · lane: F02 · title: Deterministic policy lifecycle state machine
- repo: macro · kind: engine+ui
- ledger_rows: `MO-DELTA-032`
- spec_sources: `engine/policy_intent_desk.py`, `templates/policy_watch.html.j2` (existing
  coarse thread-taggers to extend)
- owned_paths: `engine/policy_intent_desk.py`, `templates/policy_watch.html.j2`, plus a new
  state-machine store (TBD at build per the ledger row)
- entry_points: `policy_watch.html` route (existing page — confirm exact nav placement in spec)
- acceptance: "a jurisdiction-scoped policy item advances through deterministic lifecycle
  states on a real store, rendered"; missing_contract_or_proof: "deterministic
  proposal->passage->enactment->enforcement state machine"
- live_url: TBD (existing `policy_watch.html` page, updated)

**A-F05-1**
- id: `A-F05-1` · lane: F05 · title: Event-to-asset impact upgrade
- repo: macro · kind: engine+ui
- ledger_rows: `MO-PAID-017` (row not independently re-fetched by this census pass; cited via
  its paired row MO-DELTA-001, same substrate)
- spec_sources: `engine/chronicle/spine.py`
- owned_paths: `engine/chronicle/spine.py` and its consumer template (spec proposes exact file)
- entry_points: UNKNOWN — confirm in spec whether an existing "Market-Feed" surface exists
  (this is exactly what MO-DELTA-001 below asks)
- acceptance: per MO-PAID-017's own row (not fetched this pass — spec stage must read the row
  directly before building)
- live_url: TBD

**A-F05-2**
- id: `A-F05-2` · lane: F05 · title: Market-Feed alias confirmation
- repo: macro · kind: analysis+ui
- ledger_rows: `MO-DELTA-001`
- spec_sources: `engine/chronicle/spine.py` (same substrate as MO-PAID-017)
- owned_paths: fold into MO-PAID-017's projection per the ledger's own `next_bounded_child`
- entry_points: whatever MO-PAID-017's projection serves (resolve in A-F05-1's spec first)
- acceptance: "MO-PAID-017 interface confirmed to serve (or explicitly not serve) a
  Market-Feed surface"
- live_url: TBD (fold-in, not a new page)

**A-F10-1**
- id: `A-F10-1` · lane: F10 · title: Implication-card output contract over two estimators
- repo: macro · kind: engine+ui
- ledger_rows: `MO-PAID-039` (cites prior PR #6822, status UNKNOWN in this census — fresh-read
  before assuming it is still open)
- spec_sources: `engine/synthetic_control.py`, `engine/seasonality/event_study.py` (both
  "pure unwired estimators" per the ledger)
- owned_paths: `engine/synthetic_control.py`, `engine/seasonality/event_study.py`, plus one new
  card-schema/UI surface (spec proposes exact file)
- entry_points: "a routed UI" (unnamed in the ledger — spec stage picks the nearest existing
  research page in the correct nav family)
- acceptance: "an implication card renders in a routed UI from estimator output"; this is an
  ADJUDICATED single child with MO-DELTA-016 (not separately listed here — read that row before
  building)
- live_url: TBD

**A-F10-2**
- id: `A-F10-2` · lane: F10 · title: One additional econometric family
- repo: macro · kind: engine
- ledger_rows: `MO-DELTA-015`
- spec_sources: `synthetic_control.py` (matched_k v0), `event_study.py` — 9 of ~11 econometric
  families confirmed absent by grep; 2 of 11 exist in code
- owned_paths: one new family module under the same engine directory (principal scopes which
  family ships first — the ledger names no single next child yet)
- entry_points: none named (research_only per the ledger's authority_ceiling)
- acceptance: "one additional family implemented, callable, tested"
- live_url: n/a (research/CLI surface, not a page, unless the spec proposes one)

**A-F03-1 / A-F03-2 (contingent on §10 resolving #6604's state first)**
- ids: `A-F03-1` (`MO-PAID-076`, Structure Builder), `A-F03-2` (`MO-DELTA-033`/`MO-PAID-070`,
  catalyst->exposure->structure workflow modules)
- repo: macro · kind: engine+ui
- All three rows carry `next_bounded_child: ABSORBED-BY #6604` — the F03 commissioning owner.
  **Do not build these independently of #6604's own drafting session** until A has fresh-read
  #6604's actual state (§10). If #6604 is stale/abandoned, A converts these into normal Wave 1
  packets with `#6604` removed as a dependency and records that choice as a DEC.
- spec_sources: ThetaData chain/flow (named as available in the ledger; exact module UNKNOWN —
  spec stage locates it), catalyst/event feed (binding source UNKNOWN)
- acceptance: per each row's `acceptance_test` (none machine-checkable yet per the ledger —
  "n/a — #6604 drafts it")

A's Wave 1 total: **6 concrete packets** (A-F02-1, A-F02-2, A-F05-1, A-F05-2, A-F10-1, A-F10-2),
plus 2 contingent F03 packets pending §10.

*F01 and F04 note:* F01's 12/12 workspace suite is already merged (PRs #6836, #6843-#6849 per
the census); F04's WTI vertical is already built but held (#6872). Wave 1 work on F01/F04 is
therefore **close-out of the Wave 0 PRs above**, not new packets — do not open a second F01 or
F04 vertical while #6873/#6872/#6890/#6826 are unresolved.

#### Meta-CEO B packets

**B-F08-1**
- id: `B-F08-1` · lane: F08 · title: Alert preferences UI/API + mailer wiring
- repo: macro · kind: engine+ui
- ledger_rows: `MO-PAID-085`
- spec_sources: `app/account_prefs.py` (no alert prefs today), `engine/portfolio_digest.py`
  ("SEND PATH IS NOT WIRED, DELIBERATELY"), `app/mailer.py` (existing, unwired)
- owned_paths: `app/account_prefs.py`, `engine/portfolio_digest.py`, `app/mailer.py`, plus the
  settings template that surfaces the preference
- entry_points: existing `alerts.html` (Alert Command Center, live in the US nav menu) and/or
  an account/settings page — confirm exact route in spec
- acceptance: "a set preference causes an actual send on the next matching alert"; named
  integrity gap to respect: `scripts/build_bonds.py:1433-1440` falls back silently on a failed
  nightly, so a stale alert state can render as current — this packet's spec must not repeat
  that pattern (per `research/MARKET_ONTOLOGY_F08_ARCHAEOLOGY_CENSUS_2026-09-04.md`)
- live_url: `https://www.mastermind-x.com/alerts.html` (existing page, extended)

**B-F08-2**
- id: `B-F08-2` · lane: F08 · title: Event/scenario -> touched-position mapping
- repo: macro · kind: engine+ui
- ledger_rows: `MO-PAID-028`, `MO-DELTA-042` (ADJUDICATED single child — build together)
- spec_sources: A1A/A1B holdings truth (Portfolio state authority, PROVEN_LIVE per PR #6508);
  `engine/alerts.py`, `engine/alert_triage.py` (existing rule engine + display)
- owned_paths: `engine/alerts.py`, `engine/alert_triage.py`, plus a new event-schema module
  (direction/mechanism/timeframe/invalidation) per MO-DELTA-042's requirement
- entry_points: routed page over existing Portfolio/Alert surfaces (confirm exact route in spec)
- acceptance: "an event object resolves to the user positions it touches on a routed page"
- live_url: TBD (extension of the Alert Command Center or Portfolio page)

**B-F09-1**
- id: `B-F09-1` · lane: F09 · title: HY/IG credit-window gating leg
- repo: macro · kind: engine+ui
- ledger_rows: `MO-PAID-060` (paired with `MO-DELTA-019`, not separately detailed here)
- spec_sources: `engine/ipo_radar.py` (`window_context()` at L79), `collectors/ipo_calendar.py`
- owned_paths: extension of `engine/ipo_radar.py`'s `window_context()` pattern to HY/IG credit
  windows (a scoped-down build per the ledger, not a new engine)
- entry_points: UNKNOWN — nearest existing IPO/credit surface; confirm in spec
- acceptance: "a follow-on/HY-IG window gate exists parallel to the IPO leg"; named gap: "deal-
  calendar (upcoming IPO) source not found in repo" (UNVERIFIED per the ledger)
- live_url: TBD
- *Run this only after B has taken over and merged #6793 (F09-1, MO-PAID-064/MO-DELTA-023) in
  Wave 0* — MO-PAID-060 is F09's *second* vertical, not its first.

**B-F11-1**
- id: `B-F11-1` · lane: F11 · title: Thesis Condition monitor -> notification
- repo: macro (+ Terminal for the Thesis Object store via #502) · kind: engine+ui
- ledger_rows: `MO-PAID-047`
- spec_sources: `engine/falsifier_tripwires.py` (production tripwire machinery; latch law
  verified: FIRED is sticky, un-fired only by version bump); consumers `moat_falsifiers`,
  `theme_thesis`, `research_factory`
- owned_paths: project a user monitor over the *existing* tripwire state machine — do not
  build a second engine; wire the notification through the F08 delivery path (B-F08-1)
- entry_points: UNKNOWN — no RMS/thesis nav item found in the current site census; confirm
  placement in spec (do not create a third nav family)
- acceptance: "a subscribed Thesis Condition FIRED transition triggers a notification via the
  F08 delivery path"; **house law**: user-facing text never says "falsifier" (CLAUDE.md
  §Epistemics + #3821 ruling) — use "windows, not certainties" language instead
- live_url: TBD
- *Depends on* Terminal #502 (Thesis Object migration) landing first — resolve the Supabase
  0011 namespace collision (Wave 0) before this packet's build stage.

**B-F12-1**
- id: `B-F12-1` · lane: F12 · title: Tenancy foundation (team_id-scoped membership)
- repo: Terminal (charting-app; Supabase-owned) · kind: data+engine
- ledger_rows: `MO-PAID-051` (coordinated with `MO-PAID-081` invitation flow, which the ledger
  marks ABSORBED-BY this same foundation)
- spec_sources: none exist today — "NONE (no team_id/tenant_id/seat_limit/workspace_id anywhere
  in app/ or engine/)" per the ledger; coordinate with WS:MARKET-OS's A2-A6 host wave rather
  than duplicating it
- owned_paths: new `supabase/migrations/00NN_tenancy_foundation.sql` (settle the namespace
  first, Wave 0), plus the Terminal API routes that read/write `team_id`
- entry_points: internal (no public route required for this row alone)
- acceptance: "a team_id-scoped membership row is created/read by a live route"
- live_url: n/a (platform row; a live Terminal API route counts as proof)
- **Gate**: `research/DO_NOT_REBUILD.md` / `DEC-CROSS-REPO-CONTRACT-GOVERNANCE-FEDERATED-NO-RUNTIME`
  forbids this becoming a cross-repo traffic middleman — keep it inside Terminal's own stack.

**B-F13-1**
- id: `B-F13-1` · lane: F13 · title: Public glossary over the existing vocabulary
- repo: macro · kind: ui
- ledger_rows: `MO-DELTA-011`
- spec_sources: `docs/site_semantics/` (6 files, the Context Index source),
  `scripts/context_index_query.py` (internal query tool, not the page itself)
- owned_paths: one new `templates/glossary.html.j2` + paired `site/glossary.html` (plain-copy
  pair rule applies if not a `.j2`-only render) + the static content it renders
- entry_points: new nav entry under the existing "Research" menu family (do not invent a third
  header) — confirm exact placement in spec
- acceptance: "a public page lists >=50 defined terms from the existing vocabulary"
- live_url: `https://www.mastermind-x.com/glossary.html` (proposed; confirm in spec)
- *Note:* `MO-PAID-088`'s `/help` + changelog half of this same "F01/F13 cheap-projection
  batch" is already shipped — PR #6828 merged a governed public help directory (per the census
  merged-PR list, `[F13-X1][HOLD-FOR-F00] Add governed public help directory`, merged
  2026-09-05T08:44:06Z). Do not re-build `/help`; this packet is the glossary half only.

**F06 and F07 note:** both lanes' first two verticals are explicitly `DEFER`red in the ledger —
F06's `MO-PAID-021`/`MO-DELTA-002` wait on MO-PAID-020's renderer/CIK repair (§10) and on F07's
valuation inputs; F07's `MO-PAID-022`/`035`/`026`/`037` wait on a Chairman/Sol valuation-source
rights ruling (F00B fanout item 3). B's Wave 1 action for these two lanes is to **resolve the
dependency** (route MO-PAID-020 per §10; get the valuation-source ruling from the Chairman) —
not to build a vertical against an unresolved dependency. #6831 (MSFT security_state, Wave 0)
is F06's real near-term product motion.

B's Wave 1 total: **4 buildable concrete packets** (B-F08-1, B-F08-2, B-F09-1, B-F11-1) plus
2 more with concrete file paths (B-F12-1, B-F13-1) — 6 in total, plus F06/F07 dependency-
resolution actions.

### Wave 2..N: close remaining ledger rows per lane in ledger order

NEW_BOUNDED_BUILD and UPGRADE_EXISTING_OWNER rows with proven-live owners first,
PROJECTION_ONLY next; BLOCKED_RIGHTS rows get a recorded rejection naming the gate;
`<=6` packets per workflow run (the script itself hard-caps at 8 — see §6); one workflow run
per lane batch; the Meta-CEO adjudicates results, updates the ledger and its handoff, posts the
wave comment, launches the next wave. **Program ends when the ledger has zero non-terminal
rows and both handoffs say COMPLETE with live proof links.**

## §6 Execution recipe (workflow)

**Script:** `.claude/workflows/marketontology_vertical_build.js`
(`meta.name = 'marketontology-vertical-build'`), invoked as:

```
Workflow({
  name: 'marketontology-vertical-build',
  args: { ceo: 'A'|'B', wave: '<id>', packets: [ /* <= 8, script hard cap */ ] }
})
```

**Packet shape** (exactly as the script destructures it):

```
{
  id, lane, title, repo: 'macro'|'terminal', kind: 'ui'|'engine'|'data'|'records',
  ledger_rows: ['MO-PAID-0xx', ...], spec_sources: [...], owned_paths: [...],
  entry_points: [...], acceptance: [...], live_url: '<expected>'
}
```

The script throws if `packets` is empty/missing, and throws above 8 packets (charter guidance
above is `<=6`; the script's hard ceiling is 8 — keep to 6 in practice for review load).

**Stages** (each packet flows independently through the pipeline):

1. **Spec** — `designer` (kind `ui`) or `analyst` (otherwise) freezes the packet into an
   implementable spec: exact files, markup/CSS or data contract, tests, entry-point wiring,
   live URL, and (for UI) both dark and light theme treatments. Schema requires
   `spec_markdown`, `owned_paths`, `sources_read`.
2. **Build** — `builder`, isolated sparse worktree. Fetches the packet's default branch
   (`main` for macro, `master` for terminal), opens `git checkout -B claude/mo-<ceo>-<wave>-<id>`,
   implements, runs the touched tests, produces evidence crops for UI (dark/light x EN/ZH x
   1440/390), commits, pushes, opens the PR (title `[MO-<CEO><WAVE>] <id>: <title>`), arms
   `merge-on-green`.
3. **Review** — `reviewer` (opus) attacks the diff against fresh `origin/<default-branch>`;
   verdict `PASS`/`FIX_REQUIRED`/`REJECT` with blockers/majors/minors, each citing file:line.
4. **Fix** — only runs if verdict is not `PASS`/`REJECT`; `builder` repairs blockers+majors on
   the same branch, then one re-review.
5. **Ship** — `builder`, low effort: preflights `gh api rate_limit`, waits CONCLUDED checks
   with exactly one watcher (`gh pr checks <n> --watch --interval 150`), squash-merges on
   green (or records the sweeper's merge), then live-verifies — macro via the shared
   `render.yml` lane (watch, never cancel/re-run), Terminal via polling
   `https://app.mastermind-x.com` post-`terminal-build.sh`.

A packet that fails `spec` (BLOCKED) or is `REJECT`ed at review does not proceed; the pipeline
records it and moves on. The workflow returns
`{ ceo, wave, shipped, total, packets: [{ id, lane, ledger_rows, spec, pr, pr_url, verdict,
blockers_open, merged, merge_sha, live_verified, live_proof, gaps }] }` — the Meta-CEO reads
this summary to update the ledger and write the wave handoff comment.

**Takeover procedure** for a PR opened by a prior session (not by this workflow): see §4's
held-PR takeover procedure — it is identical whether the PR came from this workflow or from an
earlier program phase (Sol/Codex/etc.).

**Standing gates inline in every packet** (spawn-handoff law, CLAUDE.md): fresh end-to-end
happy path, zero manual workarounds; UI packets post dark/light x EN/ZH x 1440/390 crops in the
PR body and pass `check_design_system.py --mode enforce-added`,
`check_runtime_style_injection.py`, `check_ui_visual_evidence.py`, `check_template_site_sync.py`;
entry points wired in the existing nav family; nulls printed not hidden; no LLM-originated
signals/scores; no trading authority; tests added/updated; GitHub annotations start the line.

### 6.x Worker budget law (measured 2026-09-06, binding for both halves)

Workflow subagents are cut off at **exactly 30 tool calls with no return** (two Opus reviewers
and one drafter died this way on 2026-09-06; the orchestrator sees only "completed without
calling StructuredOutput"). Consequences: every stage prompt carries a HARD BUDGET (spec 20,
build 26, review 22, fix 24, ship 20); packets are sized so a builder can implement, test, push
and open the PR inside 26 calls (split bigger work into more packets); builders checkpoint WIP
with a push and return PARTIAL + `remaining_steps`, and `marketontology_vertical_build.js`
resumes them on the same branch up to three times; reviewers write the diff to a file once and
read it in ranges; every worker appends progress notes to `$TMPDIR/mo-progress-*.md` so a
cut-off still leaves evidence. A workflow that dies with "subagent completed without calling
StructuredOutput" is a budget failure, not a refusal — read the agent transcript under the
workflow's directory before assuming nothing happened (the 2026-09-06 #6834 takeover had
succeeded and pushed before its reviewer was cut).

## §7 Laws retained and Sol-era rules repealed

**Retained in full (pointer list; do not restate):** CLAUDE.md + AGENTS.md in full (ship loop
incl. merge on CONCLUDED checks, merge-on-green, quota, model routing + ROUTE registry, sparse
worktrees, navigation source-of-truth, design doctrine + theme art direction,
epistemics/gauntlet, instrument-is-not-market-verdict, annotations, Agent OS hygiene);
`research/DO_NOT_REBUILD.md`; each lane handoff's `do_not_redo` unless refuted with evidence in
a DEC; K1 EvidenceRef/EvidenceBlock/EvidenceRecipe contracts; Stock Identity + Data OS +
Supabase auth as the only identity planes; no proprietary copying; no trade/transfer execution
ever (safety rule, not repealable); Supabase DDL only through reviewed migration files in the
settled namespace.

**Repealed for this program only, per the Chairman override in §0:**
- Sol (ChatGPT CEO) and the Grok Secretary transport hold no authority over Market Ontology;
  their past rulings are history, not gates.
- Every HOLD-FOR-SOL label/comment on a Market Ontology PR listed in §5 no longer blocks a
  merge — the Meta-CEO who owns the lane may take it over per §4's procedure. (`DEC:SOL-HOLD-IS-A-MERGE-BARRIER`
  still governs every OTHER program in this repo; it is not repealed generally.)
- READ_ONLY_ARCHAEOLOGY is not a valid lane state for this program going forward.
- PICKUP_ACK/START ceremony is reduced to the one-comment ACK in §4; no DECISION_REQUEST posts
  to Sol; no exact-root Slack re-read is required before every act (ordinary GitHub-state
  freshness checks before push/merge still apply — that is fleet law, not a Sol ceremony).
- The 2026-08-29 hierarchy amendment's "flatten the hierarchy" and "Computer Use typing is not
  pickup" do-not-redo lines are superseded for this program (§0).

## §8 Pickup prompt for Meta-CEO B

Verbatim block (from the frozen seed; file paths adjusted only for accuracy against what this
drafting task actually produced):

> "You are Meta-CEO B of the Market Ontology program on the Claude3 account, co-equal with
> Meta-CEO A (Claude8 session 5b29ad85). Chairman Chris overrode the ChatGPT CEO on 2026-09-05
> PDT and placed Claude as Meta-CEO; the charter is
> `research/MARKET_ONTOLOGY_META_CEO_CHARTER_2026_09_06.md` on origin/main (also
> `agentos/handoffs/MARKET-ONTOLOGY-META-CEO-AB-CHARTER-2026-09-06.md` and
> `agentos/decisions/DEC-CHAIRMAN-OVERRIDE-CLAUDE-META-CEO-REGIME-2026-09-06.md`; all three ship
> in the same PR, macro#6894, together with the reusable workflows
> `.claude/workflows/marketontology_vertical_build.js` and
> `.claude/workflows/marketontology_release_held_pr.js`). Do: (1) `git fetch origin` && read the charter fully; (2) open a fresh sparse
> worktree on a `claude/*` branch off `origin/main`; (3) post ONE comment on macro#6819:
> 'META-CEO B ACK — session `<your native uuid>`, account Claude3, taking half B (F06 F07 F08
> F09 F11 F12 F13 + platform)'; (4) run Wave 0 for half B with
> `Workflow({scriptPath:'<worktree>/.claude/workflows/marketontology_release_held_pr.js',
> args:{ceo:'B', repo:'macro', prs:[6892, 6793, 6831, 6861, 6526]}})` (takeover -> rebase ->
> opus review -> fix -> Ready -> merge-on-green -> merge -> live proof), then the Terminal
> PRs (#490, #502, #507 first) with `repo:'terminal'`; (5) run Wave
> 1 with `Workflow({name:'marketontology-vertical-build', args:{ceo:'B', wave:'B1',
> packets:[...]}})` using the packets in charter §5/§9; (6) write
> `agentos/handoffs/MARKET-ONTOLOGY-META-CEO-B-<date>.md` at each wave boundary and post the
> wave comment; keep going wave after wave until half B's ledger rows are all terminal with
> live proof. Never wait for Sol; never ask the Chairman for permission; fleet law in
> CLAUDE.md still binds; ultracode is on — orchestrate with workflows, adjudicate in the main
> loop."

## §9 Danger areas and do-not-redo union

### 9.1 Program-wide do-not-redo (deduped union, source noted)

- Never create a third/second Market Ontology workstream, lifecycle, queue, identity/evidence/
  graph/financial/portfolio/thesis/tenant/API/job/grading/correction/learning/scheduler/
  runner/cleanup/retry plane. [multiple F00-family handoffs, 2026-08-26 through 09-05]
- Never literal-clone/copy Market Ontology proprietary code/data/corpora/assets/branding/
  credentials/hidden interfaces. [2026-08-26 program handoff; F00-META-CEO-PRODUCT-RESET]
- Never treat context/research parity as trading/rank/gate/size/entry authority without the
  promotion gauntlet. [2026-08-26 program handoff]
- Never reconstruct the retained 1,556-row/460-finding P1 corpus from model memory; admission
  is byte-exact via the open F00A gate only. [F00-PARITY-CONTROL; multiple later handoffs]
- Never mint replacement/substitute operation keys for F01-F13 lanes already assigned.
  [F00-F13-FANOUT-MANIFEST; F00-FULL-SITE-RESTART]
- Never infer Fable/worker execution, pickup, or ACK from Slack DELIVERY_ONLY visibility,
  Linear status, GitHub review request, PR merge, or an F00 records merge alone. [k2c;
  sol-final; F04-EXPLORER-RETURN-RECONCILIATION]
- Merged is not accepted — for OTHER programs, always read a HOLD carrier at its acceptance
  state, not its merge state. For THIS program, §0/§7 repeal the Sol-acceptance requirement,
  but "merged" still is not "live-verified" (§2 DONE). [F00B-CROSSWALK; COVERAGE-C0]
- Never recommission or duplicate K2-C or K3-D (bound to PR #6498/#6533, separate canonical
  commissions). [2026-08-26 program; pickup; COVERAGE-C0]
- Never absorb F01-F13 implementation carriers into F00; F00 is program control, not a serial
  approval hop or the implementer. [F00-PARITY-CONTROL]
- Never resume the quarantined F00 UUID `1727abca-4b22-4106-a498-6b83ad223a73` or old F01 UUID
  `550dc8b0`; do not re-ACK/re-START any already-bound lane session id (F01 `dd51ef8f`, F04
  `d6317c9b`, F05 `cc2d9d31`, F06 `03200f5b`, F09 `641ca8f7`, F10 `9c9ac628`, F11 `d937f8bd`,
  F12 `local_abf9f882`, F03 `local_cc5baa49`). [F00-META-CEO-PRODUCT-RESET;
  F00-CONTINUITY-RECONCILIATION]
- Sparse worktrees omit `site/`/`data/`/`mockups/` — absence there is a worktree-profile
  artifact, never capability evidence. [F00-PARITY-CONTROL; COVERAGE-C0]
- Rights-gated rows (military/maritime/satellite/chokepoint/deal-flow/sovereign/
  BLOCKED_RIGHTS) must never be commissioned as builds before explicit Chairman/commercial
  gates. [F00-PARITY-CONTROL; COVERAGE-C2]
- Fast-moving main can go stale under a records-only PR proof; re-check current base before
  merge. [2026-08-28 granular; CODEX-WORK-TRANSITION]
- Never mass-stop the fleet or centralize all execution into one provider account/subscription.
  [F00-META-CEO-PRODUCT-RESET]
- Never fabricate receiver capacity, OPEN_PICKUP, ACK, START, watcher, or RuntimeBinding.
  [POST-TIMEOUT-COMPLETION; POST-TIMEOUT-EXECUTION-ADMISSION]
- Never call CI green/merge/schema-apply/runner-online/screenshots "product acceptance" —
  production proof requires an actual working consumer. [2026-08-26 program;
  POST-TIMEOUT-EXECUTION-ADMISSION]

### 9.2 Per-lane do-not-redo (one line each, source = that lane's 2026-08-26 handoff)

- **F01**: no new macro data store/source registry/identity plane/event plane/ranker/alert
  lifecycle; no LLM brief->fact/score/rank/trade authority; no collapsing credit/rates/FX/
  commodity into one risk-on/off scalar.
- **F02**: no second event database/country master/sanctions store/geospatial object store/map
  identity plane; no LLM-created sanctions/military/shipping/causal facts.
- **F03**: no second option chain/surface/Greeks/flow/strategy-pricing engine; no loose LLM
  trade recommendation/rank/entry/sizing/order execution.
- **F04**: no 4th relationship graph/generic RELATED edge/causal DAG alpha/magic opportunity
  scalar; do not absorb the separately-bound K3-D carrier; do not replace `/transmission.html`.
- **F05**: no 2nd event ID/database, no headline-count event identity, no LLM fact-extraction
  authority, no opaque catalyst ranker feeding Prophet.
- **F06**: no 2nd security_state/dossier truth object, no issuer-specific renderer fork, no
  local ticker identity plane; Research Screener may not become a trade ranker without
  promotion.
- **F07**: no new statements/consensus DB, no hidden spreadsheet truth, no arbitrary LLM
  assumption mutation, no unexplained fair-value residual; no displayed probability/confidence
  with decision significance absent a calibration receipt.
- **F08**: no 2nd holdings store/portfolio state model/risk engine/alert scheduler/local
  offline truth; research weights must not become execution/sizing authority.
- **F09**: no monolithic capital-markets DB/deal truth store/sovereign entity master/materials
  graph/logistics identity plane; no physical-financial arbitrage signal authority absent
  prospective validation.
- **F10**: no rival grader/backtester/trial ledger/outcome store, no p-hacking explorer, no
  causal label from association, no analog-derived live signal without promotion.
- **F11**: no 2nd Agent OS, generic AI memory DB, canonical fact store, chat transcript
  authority, or analyst leaderboard; human conviction never machine rank/gate/size authority by
  default.
- **F12**: no 2nd auth/tenant/job/event queue, API truth store, webhook retry DB, secret store,
  collaboration state plane; no public redistribution rights inferred from internal data
  rights.
- **F13**: no 2nd observability platform/evaluation ledger/release truth/support case system/
  source scheduler/operator control plane; no universal analyst/feature score conflating
  research quality/retention/alpha/P&L.

### 9.3 Danger areas (one line each, source = that lane's 2026-08-26 handoff)

- **F01**: mixed clocks/session semantics; missing/stale coverage must not read as zero/calm;
  briefing prose overstating causality.
- **F02**: proposal vs enactment vs effective/enforced state; sanctions/license amendments;
  source corrections; location/entity identity; sensitive/paid feed rights.
- **F03**: OI staleness, dealer-sign assumptions, vol-surface timestamp, liquidity, corporate
  actions, multiplier/contract identity, false completeness.
- **F04**: graph proximity/color/decimals look causal; terminal-only scenario magnitude is not
  path shape; no backdating current values into a historical cutoff; high hop frequency can
  coexist with no alpha.
- **F05**: source correction, duplicate econ development across headlines, event-time vs
  known-at, direct vs 2nd-order materiality, causal labels stronger than evidence.
- **F06**: ticker/listing/issuer ambiguity, share classes, stale CIK, partial evidence shown
  complete, privacy leakage, mobile degradation.
- **F07**: consensus vintage/lookahead, unit/period mismatch, share-count/debt/cash identity,
  double-counted assumption changes, saved-object/library divergence, sector model misuse.
- **F08**: mixed live/cost basis, partial price/identity coverage, duplicate holdings,
  benchmark/annualization mismatch, false-zero risk, alert failure masquerading as clear/
  current.
- **F09**: deal amendment/pricing clocks, issuer/security identity, pro-forma capitalization,
  rights/vendor terms, physical-flow latency, chokepoint causal overstatement.
- **F10**: lookahead, non-independent samples, multiple testing, clustered/time-series
  inference, weak instruments, treatment overlap, synthetic-control donor leakage, analog
  outcome leakage/honest N.
- **F11**: thesis duplication, silent edits vs revisions, monitor failure state, source
  correction, permissions, hallucinated chat refs, wrong-metric claim scoring.
- **F12**: cross-tenant leakage, entitlement drift, idempotency ambiguity, replay/webhook
  dedupe, secret exposure, deletion/export incompleteness, schema compatibility, rights.
- **F13**: false-green health after a failed refresh, privacy leakage, vanity usage metrics,
  retrospective claim scoring without a preregistered resolution law, stale methodology docs.

## §10 Open questions the Meta-CEOs must rule on in Wave 0

1. **MO-PAID-020: ListingAlias -> ListingKey renderer + CIK-leg ownership.** Ruled
   OWNER-CORRECTION already at the ledger level (belongs to WS:MARKET-OS/F06, not
   WS:STOCK-IDENTITY), but still `CAPACITY_SELECTABLE / WAITING_CAPACITY` — no session has
   self-assigned it. It gates F06's `MO-PAID-021` (B1B cockpit second issuer) directly, and
   the broader event->security continuation for F05/F06. **Owner: B (F06's lane).** B must
   either self-assign this repair in Wave 0 (per the Chairman override, no capacity-selection
   ceremony is required to block it) or explicitly defer it with a named reason.
2. **F04 X1 K1 exception scope.** The prior ruling permits "typed read-only native
   TXI-episode-transition projections inside the commissioned snapshot" for X1 only,
   explicitly superseding Amendment 3 §5's every-leg K1 clause for this one bounded slice —
   it does not change K1 vocabulary generally or waive checks elsewhere. **Owner: A (F04's
   lane).** Confirm this scope is still what #6872's current head implements before taking it
   to Ready; do not widen it to other F04 legs without a new DEC.
3. **F09 row-accounting repair.** The F09 ledger plan is preserved but needs a repair: "held
   par != issuer debt outstanding" and "theme/name matcher != canonical issuer join" were
   flagged as product-claim errors in the prior F09 planning. **Owner: B (F09's lane).** Fold
   the correction into B's next ledger CSV write; do not ship MO-PAID-060 or any other F09
   row that inherits the uncorrected accounting.
4. **Supabase migration-namespace collision (`0011_*.sql`).** Two open charting-app PRs
   (#502 `0011_thesis_objects.sql`, #507 `0011_analytics_eid.sql`) both claim `0011`; there is
   no `supabase_migrations` schema in Terminal's Supabase project, so files are hand-applied
   and order-independent — the risk is a silent renumbering conflict, not a runtime failure.
   **Owner: B.** Settle in Wave 0 (§5) before either merges.
5. **#6604 and #6809 current state (F03/F04).** The open-PR census's tight regex excluded
   both (likely because #6604's branch name doesn't match the `marketontology|market-os|
   ontology|F0x/F1x` pattern — the census's own methodology note names `options-intelligence-*`
   as excluded from even the broad match). Three F03 ledger rows (`MO-PAID-070`, `MO-PAID-076`,
   `MO-DELTA-033`) are marked `ABSORBED-BY #6604`, and F04's D2C row lives on #6809. **Owner:
   A.** Fresh-read both PRs' real state with `gh pr view`/`gh pr list --search` before disposing
   or building against them (§5).
6. **`WS-MARKET-OS.md` owns_paths.** The census could not confirm this workstream record's
   `owns_paths` field (grep returned no second match under budget) — nine of the thirteen
   lanes cite `WS:MARKET-OS` as their workstream but its exact path ownership is UNKNOWN.
   **Owner: whichever Meta-CEO next needs to cite it precisely** — re-run
   `grep -n -A5 'owns_paths' agentos/workstreams/WS-MARKET-OS.md` before relying on an assumed
   scope.
