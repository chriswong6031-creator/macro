# BioCatalyst — functional benchmark parity ledger

| Field | Binding value |
|---|---|
| Purpose | The **denominator** for any "BioCatalyst is complete" claim |
| Authority | Reporting artifact. Authorizes nothing; activates nothing; promotes nothing |
| Denominator source | `research/BIOCATALYST_FULL_PARITY_SUPERINTELLIGENCE_BUILD_HANDOFF_FOR_FABLE_2026-08-02.md` §5, lines 308–344 — a **32-row** benchmark job matrix |
| Completion test applied | `research/BIOCATALYST_REMAINING_BUILD_WAVES_HANDOFF_FOR_CLAUDE_2026-08-06.md` §17 "Functional benchmark parity" |
| Audited base | `origin/main` at `b70deb5cf817c5ed32d6de2f07bfaa82717c51d8`, 2026-08-06 |
| Production observed | `https://www.mastermind-x.com/biocatalyst.html` → 200 / 61,226 bytes; `/api/health` checkout `cbee4e0e7ff`; anonymous `/api/biocatalyst/v1/trials` → **401**, `private, no-store`, `Vary: Authorization` |

Handoff §17 requires every benchmark job to be **implemented with an eligible source**,
**explicitly licensed-later with an honest unavailable state**, or **formally excluded by a
product ruling**. A job in none of those three buckets means parity is not achieved. This
document exists because that ledger had never been written, which made "complete" unfalsifiable.

---

## 1. The honest tally

| Bucket | Rows | Parity-satisfying? |
|---|---:|---|
| **Formally excluded** by an existing product ruling | 2 | yes |
| **Licensed-later**, with an honest unavailable state required | 1 | yes |
| **Correct by design** — deliberately not wired | 1 | yes |
| **Implemented** at display/context tier with an eligible source | 2 | yes |
| **Partial** — backend eligible, product surface incomplete | 6 | **no** |
| **Blocked on another plane** that publishes no executable versioned PIT contract | 13 | **no** |
| **Not built** — in-program model/domain work needing forward evidence | 7 | **no** |
| **Total** | **32** | **6 of 32 satisfy §17 today** |

**Parity is not achieved, and cannot be achieved by any amount of BioCatalyst-side work
alone.** Thirteen rows are gated on planes BioCatalyst does not own and must not duplicate;
seven more need forward evidence that accrues on a calendar, not in a session. That is a
structural fact about the program, not a work backlog.

---

## 2. Row-by-row

Legend — **EXCL** formally excluded · **LIC** licensed-later · **DESIGN** correct as-is ·
**IMPL** implemented · **PART** partial · **BLOCK** blocked on another plane · **TODO** in-program, not built.

| # | Benchmark job | Bucket | Precise blocker / state | Who must move it |
|---:|---|---|---|---|
| 1 | Trial search / screening | PART | `GET /trials:screen` + `/facets` shipped (#4449, #4453); the browser consumes neither | BioCatalyst — D0b/W2 |
| 2 | Trial milestones | IMPL | Registry milestone view shipped and served. Display tier only — a registry milestone is not a market catalyst | — |
| 3 | Trial revision intelligence | PART | Exact-diff + prospective + replay-verified Change Tape shipped (#4434); browser still calls the legacy `/trials/changes` | BioCatalyst — D0b/W2 |
| 4 | Trial peer landscape | PART | Explicit-NCT facts-only resolver shipped (#4367); no Peer Matrix UI | BioCatalyst — D0b/W2 |
| 5 | Company / pipeline screen | BLOCK | Company **PIT identity is blocked**. Current Company Intelligence context is not a point-in-time identity service | Company Intelligence owner |
| 6 | Company dossier (Bio lens) | BLOCK | Same PIT identity blocker; a Bio lens without it would infer issuer from an NCT record, which the authority boundary forbids | Company Intelligence owner |
| 7 | Asset × Indication dossier | BLOCK | Needs the W3 temporal asset/ownership graph, which needs the PIT identity bridge | Identity owners, then BioCatalyst W3 |
| 8 | FDA / PDUFA / AdCom calendar | BLOCK | Drugs@FDA is `dark_b4a_private_only`; production ingest not allowed. No PDUFA, CRL, or ticker join may be inferred from it | Rights decision, then BioCatalyst W4-A |
| 9 | Regulatory history | BLOCK | Private Drugs@FDA graph only; regulator-native projection needs the same rights ruling | Rights decision, then W4-B |
| 10 | Safety / label / recall / shortage | BLOCK | openFDA production ingest not allowed — needs a separate rights/source lane | Rights decision, then W4-A |
| 11 | Patents / exclusivities | TODO | Orange Book / Purple Book lanes unstarted; each needs its own rights record | BioCatalyst W4-A |
| 12 | Licensing / partnership economics | BLOCK | Corporate documents/spans blocked except the narrow transcript seam (#4442). BioCatalyst must not build a second document archive | Corporate document owner |
| 13 | Cash / runway / dilution | BLOCK | The private Capital Structure PIT adapter now supplies one-issuer filing-event context, but its owner contract still declares cash runway, fully diluted shares, instruments, remaining capacity, and financing probability unavailable. BioCatalyst may not turn event context into a duplicate "true runway" | Capital Structure owner |
| 14 | Historical catalysts / outcomes | TODO | Needs `BC-O1b` forecast/outcome homes plus an eligible market-data join | BioCatalyst W6-A/B |
| 15 | Probability of success | TODO | W6-C baseline. Requires point-in-time, correction-aware, non-leaking cohorts that do not exist yet | BioCatalyst W6-C |
| 16 | Catalyst timing | TODO | W6-C timing baseline; same cohort prerequisite | BioCatalyst W6-C |
| 17 | Catalyst impact / options | BLOCK | Requires `BC-MKT0`, a rights-reviewed PIT market/options adapter. No licence exists | Market-data owner + rights |
| 18 | Expected value | TODO | W6-F. Depends jointly on rows 13, 16, 17 — all blocked. Cannot be honestly built before them | BioCatalyst W6-F |
| 19 | Earnings / filings / transcripts | PART | Only the narrow receipt-bound caller-ticker transcript seam (#4442). No general document/span adapter | Corporate owner |
| 20 | Alerts / watchlists / cohorts | BLOCK | Saved state belongs to Terminal/Supabase; no tenant-scoped adapter is available. BioCatalyst must not create a user database or a localStorage authority | Terminal/Supabase owner |
| 21 | API / data product | PART | Authenticated trial API shipped with correct entitlement, cursor, and cache boundaries. Versioned search/dossier/events/as-of/updated-since surface incomplete | BioCatalyst W5-D |
| 22 | Medical-device calendar / pipeline | TODO | `BC-MD1` MedTech pack unstarted. **Does not block a biopharma closed beta**; it *does* block any whole-benchmark parity claim that includes device scope | BioCatalyst W9-C |
| 23 | IPO / lockup workflow | BLOCK | Needs Capital + Corporate PIT event adapters (row 13's blocker) | Capital / Corporate owners |
| 24 | Insider / 13F / hedge-fund lenses | BLOCK | Must reuse existing beneficial-ownership projections; no Bio lens exists. `13F` is delayed institutional context, never a live ownership or conviction signal | Ownership owners |
| 25 | M&A / asset transactions | BLOCK | Needs the W3 asset/rights graph plus Corporate evidence spans | Identity + Corporate owners |
| 26 | Analyst ratings / targets / estimates | **LIC** | No licensed vendor contract exists. §17-satisfying **only while** the product shows a first-class unavailable state rather than a placeholder | Commercial decision |
| 27 | Biotech movers / market screener | BLOCK | Requires `BC-MKT0` (row 17). No duplicate quote plane may be built | Market-data owner + rights |
| 28 | Editorial / newsletter workflow | **EXCL** | Ruled out by the architecture doc: explicitly **not** a separate BioCatalyst CMS/newsletter product. Bio emits governed facts into the existing News/Press/Research planes | — (settled) |
| 29 | Portfolio-news workflow | BLOCK | Routing depends on the same Terminal/Supabase user-state plane as row 20 | Terminal/Supabase owner |
| 30 | Community games / expert lists | **EXCL** | Explicitly excluded pending a distinct user job and a moderation model. Cannot block intelligence completion or contaminate probabilities | — (settled) |
| 31 | Mastermind research | PART | Launch affordance only. The `BC-N0a` compiler shipped (#4401) but had **no production caller** — no packet is produced and none is read | BioCatalyst W7-A/B |
| 32 | Neural Web / Prophet | **DESIGN** | Not wired, deliberately. Prophet remains the selection owner; BioCatalyst cannot originate or reorder candidates. This row is *correct* in its current state | — (correct as-is) |

---

## 2a. The blockers, measured rather than asserted

The BLOCK rows above are not inherited from prose. Read directly from
`data/biocatalyst/fixtures/shared_plane_read_adapters.v1.json` at the audited base —
**3 of 6 shared-plane adapters are eligible**:

| Adapter | Eligible | State / blocker |
|---|:--:|---|
| `biocatalyst_trial_read_api.v1` | **yes** | `implemented_current_record_facts_only` |
| `biocatalyst_earnings_transcript_span_adapter.v1` | **yes** | `implemented_private_in_process_transcript_only` |
| `biocatalyst_company_identity_pit_adapter.v1` | no | `blocked_no_pit_identity_adapter` → needs `reviewed_point_in_time_company_identity_contract` |
| `biocatalyst_security_identity_pit_adapter.v1` | no | `unavailable_bootstrap_roster_only` → needs `complete_point_in_time_security_and_corporate_actions_contract` |
| `biocatalyst_corporate_document_span_adapter.v1` | no | `blocked_no_cross_domain_read_adapter` → needs `versioned_document_and_exact_span_read_contract` |
| `biocatalyst_capital_structure_pit_adapter.v1` | **yes** | `implemented_private_in_process_event_state_only`; explicit SEC issuer + system-time read, with cash/runway/dilution capabilities still unavailable |

The three remaining blocker strings still govern rows 5, 6, 7, 12, 19, 20, 23, 24, 25,
and 29. Row 13 remains blocked by declared owner capabilities, not by the read-adapter seam.

The eligibility record was reconciled against
`22cf8a9f8f54e341e2efb63c6d5c6984476252db` before the BC-C2 promotion. The successor
receipt binds the exact post-promotion registry and fixture bytes and records the one eligibility
change without widening any Capital Structure capability or authority.

---

## 3. What the blockers actually have in common

Eleven of the thirteen BLOCK rows reduce to **one missing thing**: no adjacent plane publishes
an *executable, versioned, point-in-time contract with defined ambiguity and unavailable
behavior*. Rows 5, 6, 7, 12, 13, 19, 20, 23, 24, 25, and 29 are all waiting on that same shape
from a different owner.

This is the highest-leverage observation in the ledger. **The fastest route to parity is not
more BioCatalyst code — it is one owning plane publishing one PIT read contract.** Each one
that lands unblocks two to four rows at once. Rows 8, 9, 10, 17, and 27 are the other pattern:
a **rights decision**, not an engineering task.

Two failure modes this ledger exists to prevent:

1. **Manufacturing eligibility.** Marking an adapter eligible because a module could be
   imported, rather than because a versioned PIT contract exists, converts a blocked row into
   a silently wrong one. A reconciliation that changes nothing is a correct result.
2. **Counting partial rows as parity.** Rows 1, 3, 4, and 31 all have a shipped, tested backend
   and no user-reachable surface. That is genuinely valuable substrate and it is genuinely not
   parity. A capability the user cannot reach has not shipped.

---

## 4. What "complete" can honestly mean

Three different claims are available, and they must not be conflated:

- **Biopharma closed beta** (handoff §17) — reachable, but gated on an operator arming decision
  and **fourteen continuous days** of soak. No session can compress that; it is a calendar.
- **Functional benchmark parity** — requires all 32 rows in a §17 bucket. **26 are not**, and
  20 of those depend on decisions or contracts outside BioCatalyst's control.
- **BioCatalyst superiority** — point-in-time evidence, correction lineage, cross-source
  temporal identity, calibrated forward evidence. Depends on parity plus months of accrual.

The honest present-tense statement is: BioCatalyst is a **strong, narrow, facts-first trial
platform with a large shipped backend, a correct authority boundary, and an incomplete product
surface** — not a benchmark-parity competitor, and it should not be described as one.
