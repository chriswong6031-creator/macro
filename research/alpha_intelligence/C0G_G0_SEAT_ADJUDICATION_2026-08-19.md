# c0g — G0 seat adjudication (FABLE-00, WS:ALPHA-INTELLIGENCE-INTEGRATION)

| K-PACKET FIELD | VALUE |
|---|---|
| WAVE | c0g (G0 return adjudication; depends_on c0, feeds k4) |
| SEAT | FABLE-00 integration COO lane, operator re-dispatch 2026-08-19 ("Execute c0g only… Adjudicate G0 under the existing WS:ALPHA-INTELLIGENCE-INTEGRATION authority") |
| RETURNS ADJUDICATED | Three plus one supplement: **US G0** PR #5955 (`research/earnings_intelligence/g0/`, Grok lane); **CN-G0** PR #5943 (`research/alpha_intelligence/censuses/CN-G0/`, Grok lane); the **#5822→#5953 rival US copy** (`research/alpha_intelligence/censuses/G0/` + an embedded non-seat `C0G_G0_ADJUDICATION_2026-08-19.md`, sonnet fleet researcher, #5822 CLOSED unmerged, payload carried forward on OPEN #5953); and the Grok lane's **pasted PARTIAL academic return** (no PR, no files — committed here as a supplementary receipt, §2.e) |
| VERIFICATION BASIS | Two independent opus `analyst` receipt-audits plus a targeted follow-up (this seat's commission, 2026-08-19): 14/14 CN claims verified; all US headline claims verified incl. live R2 production fetch (workspace sha256 `dbd50e5c…81197` matches manifest); mechanical line-overlap comparison of the two US copies (shared non-blank lines per file: 0/2/1/1/1 — different censuses, not a fork) |
| VERDICTS | US G0 **ACCEPTED — #5955 canonical**, six conditions (§2). CN-G0 **ACCEPTED** (§3). Venue ruling: Earnings event truth is venue-neutral (§4, `DEC:ALPHA-INTEL-EARNINGS-EVENT-TRUTH-IS-VENUE-NEUTRAL`). #5953's G0 cargo **non-canonical, preserved by citation** (§5). G lane stays WAIT behind E2 (unchanged from c0) |
| CEO DECISIONS NEEDED | **NONE.** (FIF-7 boundary overlap is named and parked at the K4-G commission gate, §6.3 — it sits behind Sol's pending FIF-1 review either way; nothing escalated now.) |
| AUTHORITY STATUS | NONE, unchanged. Nothing here gates, ranks, sizes, or publishes. |

---

## 1. What arrived, and how it was verified

G0 was commissioned as ONE census (post-event reinterpretation under the Earnings
owner). It returned as THREE artifacts plus a paste — two of them rival US censuses
sharing essentially zero prose. The seat had both PR bundles independently
receipt-audited (opus analysts; ROUTE analysis) against `origin/main`
(`11b87a5b1b9a` at audit time), with a follow-up pass that pulled the closed #5822's
diff and measured content overlap mechanically. Full audit packets live in this
session's transcript; every load-bearing receipt is restated below.

Naming (operator, 2026-08-19): **CN-G0 = China project; plain G0 = US.** #5943
renamed its directory to `censuses/CN-G0/` with `CN-G0_` prefixes mid-flight,
dissolving the `censuses/G0/` path collision the earlier c0g-draft worried about.

## 2. US G0 — PR #5955 ACCEPTED as the canonical US census

**Why this copy governs.** (i) It is the operator-designated US G0 return. (ii) Its
files land **inside** the Earnings owner's declared territory
(`WS-EARNINGS-INTELLIGENCE-OS.md:21-26` `owns_paths` includes
`research/earnings_intelligence/**`); the rival copy files outside it while itself
ruling that the G lane belongs to Earnings. (iii) It matches the commissioned
filename set. (iv) It is the only copy with production receipts: the live AAPL
generation `f709a0a6ec514282d5769e7d` was fetched over public R2 (HTTP 200, bytes
and sha256 matching the manifest) — reproduced independently by this seat's
auditor. (v) Its 68-row casebook keys to in-repo `research/winners/cases/` files —
all 60 cited filenames exist on origin/main (`comm -23` empty against 154
available); the rival's 48 rows rest on external news pages and one
TradingView chart annotation, none estate-receiptable.

**Conditions of acceptance (binding on any K4-G commission and on E-wave adoption):**

- **(a) Clock-direction correction.** The census's flagship finding — the two-clock
  firewall is collapsed on the live generation
  (`observed_at == source_available_at == generated_at`) — is VERIFIED and in fact
  under-claimed: the collapse is **structural, by construction**
  (`engine/company_intelligence/event_workspace_build.py:150` sets the build clock
  from `observed_at`; `:449` emits `generated_at` from that same clock;
  `scripts/refresh_event_workspaces.py:352,362-363` seeds BOTH `observed_at` and
  `source_available_at` from the SEC filing `acceptance_datetime`). But the
  census's remediation points the wrong way: spec draft §3 warns "do not stamp
  `source_available_at = generated_at`" — the code runs the opposite direction.
  **`source_available_at` is the one clock that is correct** (a genuine legal
  source time); the fields carrying no independent information are `observed_at`
  (not a real consumer-observation clock) and `generated_at` (a build value).
  Adopting waves fix those two, and never "repair" `source_available_at`.
  Recorded as `DSC:EVENT-WORKSPACE-CLOCKS-COLLAPSE-BY-CONSTRUCTION`.
- **(b) The frontier cannot be derived from lifecycle pairs.** On the only live
  workspace the lifecycle pair carries ONE instant, so any
  `information_frontier.v1` needs **per-source clocks** — and live `sources[]`
  carry none (`document_id/filing_key/kind/receipt_state/source_sha256/url` only),
  while `SourceDocument` already defines `fetched_at/published_at/available_at`
  (`engine/company_intelligence/documents.py:162-164`). That projection gap — not
  new state machinery — is the real build surface. (Neither US document caught
  this; it invalidates the rival adjudication's "compute frontier timestamps from
  lifecycle pairs" recipe, §5.)
- **(c) FIF-7 overlap named.** The census's "no canonical-owner conflict" is an
  over-claim: FIF-7's charter
  (`research/MASTERMIND_FINANCIAL_INTELLIGENCE_FABRIC_MASTERPLAN_2026-08-16.md:1672-1685`)
  claims — verbatim — "event workspace packet" and "market reaction", the exact
  surfaces G routes to Earnings. A real two-owner overlap, currently dormant
  (FIF-1 in Sol review; FIF-2 must not start; FIF-7 todo behind FIF-3). The K4-G
  commission MUST carry this boundary adjudication before any reaction/frontier
  build; do not resolve it silently in either direction.
- **(d) Casebook accepted as candidates, not verdicts** — its own framing
  ("candidate label… not a legal beat/miss and not a CEI verdict") is the correct
  epistemic posture and is retained verbatim. Per-row tape figures (e.g. NVDA
  +26.15%) were NOT verified against the case bodies; they carry display-tier
  weight only until a consumer re-checks them.
- **(e) Supplementary academic receipt committed.** The Grok lane's earlier pasted
  PARTIAL return (no PR, no files) is preserved as
  `research/alpha_intelligence/censuses/G0_SUPPLEMENTARY_US_ACADEMIC_RETURN_AS_RECEIVED_2026-08-19.md`.
  It carries PRIMARY-SOURCE-VERIFIED abstracts (RePEc/NBER/MPRA/SEC pages opened)
  for ~15 papers the #5955 review honestly tags INFERRED — Hollander/Pronk/
  Roelofsen 2010, Mayew 2008, Bradshaw–Sloan 2002, Brown et al. 2012, Li 2008/2010,
  Richardson–Teoh–Wysocki 2004, Graham–Harvey–Rajgopal 2005, DellaVigna–Pollet
  (JF 2009 AND the diverging NBER WP, conflict preserved), Hirshleifer–Lim–Teoh
  2009, Livnat–Mendenhall 2006 — plus the SEC 8-K Item 2.02 / 10-Q / Reg G legal
  clock. Where the two disagree on a tag, the SUPPLEMENT's stronger tag stands for
  the abstract-level claim and #5955's stands for everything else. Neither
  authorizes a promotion-bearing use — the Null law and gauntlet are untouched.
- **(f) One soft leak noted.** The bundle's only quantitative PEAD magnitude
  (Bernard–Thomas "~±2% over 60 trading days") rests on a review landing-page
  restatement; no downstream file consumes it. It stays display-caveated until a
  primary text is opened.

## 3. CN-G0 — PR #5943 ACCEPTED

14/14 CODE-VERIFIED claims held under audit, including the load-bearing negative
(快报 `preliminary.parquet` written by `collectors/china_preannounce.py:148-149`
and consumed by nothing — repo-wide grep clean; the special-sits engine reads
`forecast.parquet` only, `engine/china_special_situations.py:552`). Records are
schema-compliant; the DSC survives its own falsifier (all three named greps run
negative); the WS-EARNINGS edit is a +1/−0 list append against the current blob.

**Verdict adopted:** no independent G lane; **do not mint
`china_corporate_event.v1`**; after E2 ships unchanged, ONE later Earnings-owner
E-wave freezes a listing-identity adapter onto the existing `company_event.v1` /
`EVENT_STATES` contract and *references* the existing China collectors. The
audit sharpens the delta downward: `security_id_for(mic, ticker)` already admits
any 4-char MIC (`engine/company_intelligence/identity.py:61-66`) — only the
issuer layer is CIK-locked (`identity.py:40,50-58,158`;
`engine/company_intelligence/events.py:292`). The adapter is therefore an
identity-plane delta of three named sites, not an event-model change.

**Defects noted, none load-bearing:** a stale "#5822 OPEN" row in the adoption
map (self-corrected elsewhere in the same PR); casebook C7 cites a session-local
`refs/tmp/pr5822` ref — C7's `china_corporate_event.v1` claims carry **no
weight** in this adjudication (§4 resolves the question independently); the
handoff's "eight China cases" is off by one (C6 is the US contrast case).
Production freshness of the CN parquets is declared-unverified (sparse tree) —
honest, stays open for the owner.

## 4. Venue ruling (CN-G0's GQ7, routed to this seat)

**Earnings OS event/document/claim truth is VENUE-NEUTRAL.**
`DEC:EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP` grants event truth with no
geographic qualifier (venue-silent, not venue-inclusive — the census correctly
flagged its own reading as inference). The seat resolves the silence: one
issuer-keyed event truth store, all venues; the CIK lock is an identity-plane
implementation limit, never an ownership boundary; a second, venue-scoped event
store is exactly the "second Earnings store" the No-Rebuild law forbids. CN
issuer admission is a later Earnings-owner wave (post-E2) referencing Stock
Identity. Recorded as `DEC:ALPHA-INTEL-EARNINGS-EVENT-TRUTH-IS-VENUE-NEUTRAL`.

## 5. The #5822→#5953 rival copy — non-canonical, preserved by citation

#5822 is CLOSED unmerged; OPEN #5953 carries the identical G0 payload (six
census files under `research/alpha_intelligence/censuses/G0/` + a pre-written
`C0G_G0_ADJUDICATION_2026-08-19.md`). Rulings:

1. **The six census files are a rival census, not the canonical one** (zero
   shared prose with #5955; zero production receipts — and its stated reason,
   "worktree is sparse so no production artifact could be inspected", is FALSE:
   the workspace is public HTTPS, fetched from this same sparse tree in one
   call; its casebook's "18 verified events" headline is inflated — 3 of the 18
   are papers, 2 lack pinned identity, ≈13 defensible). Its genuine unique value
   is preserved BY CITATION from this packet: the world-exists contrast rows
   (e.g. Netflix Q4-2021, Amazon Q1-2023 — real phenomena the estate cannot yet
   license consensus to receipt), the Q1–Q8 owner questions, and two
   better-scoped receipts (`event_workspace.py:272-278` whole-loop cite;
   `promotion.py:52`). Nothing else from it is adopted.
2. **Its embedded C0G adjudication is a NON-SEAT DRAFT, superseded by this
   packet.** Where it was right, this packet adopts with credit: the frontier
   vocabulary as a **derived read-only view, never an `EVENT_STATES` enum edit**
   (convergently reached by both censuses independently — the strongest signal
   in the whole bundle); the beat/miss legal fence; G-behind-E2. Where it was
   wrong or stale, named: its ruling-1 recipe ("compute frontier timestamps from
   lifecycle pairs") is degenerate on the only live workspace (§2.b); its
   collision picture predates #5943's CN-G0 rename; it ratifies the inflated
   verified-event count; and its `engine/expectation_state.py` /
   `earnings_release/binding.py` citations remain UNVERIFIED (promisor-fetch
   stall during audit) — any adopting wave re-verifies before relying on them.
3. **Disposition request to the #5953 lane** (recorded here and in a PR comment;
   this seat does not edit that branch): drop the six `censuses/G0/` files and
   the `C0G_G0_ADJUDICATION_2026-08-19.md` from #5953, or re-home them under
   `research/china_alpha_intelligence/` clearly marked as a superseded non-canonical
   draft. #5953's China cargo (masterplan, WS, DEC, commissions) is NOT this
   seat's to adjudicate — it belongs to the China program's own process. If
   #5953 lands unchanged before that request is honored, the tree carries two
   US G0 censuses on disjoint paths: THIS packet is the governing record of
   which one is canonical (#5955), and `do_not_redo` in the WS record carries it.

## 6. What this feeds K4 (G-lane preconditions)

The G lane stays **WAIT behind E2** (unchanged from c0; E2 is unblocked and
unstarted — `WS-EARNINGS-INTELLIGENCE-OS.md:68-72`). A future K4-G commission
must carry, verbatim:

1. §2.a clock-direction correction (+ the DSC);
2. §2.b per-source-clock projection gap as the build surface;
3. §2.c FIF-7 boundary adjudication (owner-vs-owner, at commission time, with
   Sol's FIF-1 ruling as its gate);
4. §4 venue-neutral DEC (CN adapter = Earnings-owner identity-plane delta,
   three named sites, post-E2);
5. the beat/miss fence and frontier-as-derived-view constraints (§5.2, adopted);
6. casebook rows are candidates — any grading construction goes through the
   Eval OS gauntlet before authority, per standing law.

No commission files exist for K4-G yet; the operator/Sol author them. Do not
improvise the lane.

## 7. Mechanics

- This packet + the DEC + DSC + supplement + WS/handoff updates ship on the
  c0 session branch (PR #5933) — the seat's single records vehicle.
- #5955 and #5943 are ACCEPTED census returns: adjudication comments posted on
  each; both armed `merge-on-green` by this seat as the completion of the
  return-for-adjudication loop they were opened for (comment-audited for review
  freezes first; none present).
- #5953: disposition comment only (§5.3). Not armed, not blocked by this seat.
- The G0 census content reaches origin/main only when #5955/#5943 merge; until
  then this packet's citations to their content reference the PR heads
  (#5955 @ `5938ac1a5414`, #5943 @ `fd0e8b33e103`).
