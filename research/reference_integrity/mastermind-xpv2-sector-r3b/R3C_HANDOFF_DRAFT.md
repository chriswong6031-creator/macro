# XPV2-SC-R3C — Production-migration handoff draft (R3B deliverable 13)

Commission: `research/reference_integrity/mastermind-xpv2-sector-r3b/COMMISSION.md`
§21 deliverable 13, §26 stop condition. Written by the R3B session for a
future R3C commissioning session (Sol + a fresh Fable orchestrator). Cold-
stranger rule: this file assumes no memory of the R3B conversation — every
claim below cites its source file.

---

## 0. AUTHORITY HEADER — DRAFT. DO NOT START R3C FROM THIS FILE ALONE.

This is a **draft handoff**, not a commission and not an authorization. It
was produced by the R3B session per commission §21 deliverable 13 and §26
("Return reference plus R3C handoff draft to Sol"). R3B's own stop condition
(§26) is explicit: *"Do not merge production UI, dispatch production
migration, self-approve, or reuse R3B authors as later independent
critics."*

**R3C has no authority to start until all of the following have happened**
(commission §27, "Required continuation"):

1. Four **fresh** independent critics — none of whom authored or reviewed
   R3B — review the frozen R3 candidate:
   - Product Regression critic
   - Visual/Taste critic
   - Mobile/Accessibility critic
   - Data/Authority critic
2. Sol approves the **exact frozen candidate SHA** these critics reviewed.

Only after both of those occur "may production migration begin" (commission
§27, verbatim). Nothing in this draft substitutes for that review or that
approval. Any session that opens this file and starts editing
`templates/sector_central.html.j2` or its partials without first confirming
(1) and (2) above against the live record is acting outside its authority.

**What R3C's fresh critics should know before reviewing:** the reference
artifact under review is NOT yet defect-free by the R3B lane's own
adversarial audit. `mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/build/QA_ATTACK_REPORT.md`
§8 records 1 CRITICAL, 6 MAJOR, 5 MINOR and 2 NOTE findings against the
candidate itself (not against production), and
`research/reference_integrity/mastermind-xpv2-sector-r3b/capability_crosscheck.md`
records 7 FINDING rows (6 distinct defects, F-1..F-6) against the R3A
capability ledger, none of them recorded as approved deviations in
`ORCHESTRATOR_ADJUDICATIONS.md`. Whether those defects must be repaired in
the reference before the candidate SHA is presented for critic review, or
may be repaired during migration, is itself an open call for Sol — this
draft does not resolve it. See §7 below for the full list.

---

## 1. What R3B delivered, and where

R3B's mission (`COMMISSION.md` §0) was a **reference-design wave, not a
production migration** — "Do not modify production templates, engines,
ranking, access, routes, global navigation or site behavior in this wave"
(§0). Confirmed: `ORCHESTRATOR_ADJUDICATIONS.md` §10, "No production file
modified."

R3B produced (commission §21, deliverables actually found on disk per
`capability_crosscheck.md` GAPS item 10 — several listed deliverables were
NOT found and are carried as open items, §7 below):

- **Interactive six-view reference artifact**:
  `mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html`
  (5,431,707 bytes; single self-contained file — `capability_crosscheck.md`
  header).
- **Build harness** (source of the assembled artifact, NOT itself a
  production migration target — see §2):
  `mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/build/`
  (`build_reference.py`, `runtime_shim.js`, `verify_reference.py`,
  `shell.html`, `views/*.html`, `fixture_supplement/**`,
  `README_BUILD.md`).
- **Capability cross-check** (deliverable 8, 92/92 rows verdicted):
  `research/reference_integrity/mastermind-xpv2-sector-r3b/capability_crosscheck.md`.
- **QA attack report** (adversarial responsive/a11y/access pass, not itself
  a numbered commission deliverable but material evidence):
  `mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/build/QA_ATTACK_REPORT.md`.
- **Orchestrator adjudication record** (every design-lane deviation ruled
  on): `research/reference_integrity/mastermind-xpv2-sector-r3b/ORCHESTRATOR_ADJUDICATIONS.md`.
- **Production baseline evidence** (pinned-commit local renders of the six
  views, plus the one live anonymous-regwall receipt):
  `mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/production/PROVENANCE.md`
  and its sibling PNGs.
- **This draft** (deliverable 13):
  `research/reference_integrity/mastermind-xpv2-sector-r3b/R3C_HANDOFF_DRAFT.md`.

Per `capability_crosscheck.md` GAPS item 10, the following commission §21
deliverables were **not found on disk** at the time of this cross-check and
are therefore open items for R3C, not confirmed R3B outputs: the EN/ZH copy
ledger (deliverable 4), responsive behavior contract (5), accessible-
alternative contract (6), state-matrix evidence (7), hash/deep-link evidence
(9), access/hydration evidence (10), evidence crop index (12). R3C should
verify current state of these before relying on their absence.

---

## 2. Migration surface map

The reference is quarantined and single-file (`README_BUILD.md` "Assembly
order", "What this harness explicitly does NOT do"). Production is the
opposite: server-rendered Jinja templates plus separately-served JS modules
and live fetches. A migration touches production files; it does not touch
the reference's own build harness (that harness is explicitly R3B-owned
plumbing, not a migration source of truth — `README_BUILD.md` "Lane
contract": harness files are owned by R3B and a design lane "does not edit
the shim directly").

| Production surface | Reference equivalent (what to consult, never what to copy verbatim) |
|---|---|
| `templates/sector_central.html.j2` (shell, view sections, inline boot script) | `build/shell.html` (throwaway placeholder shell — explicitly replaceable, `README_BUILD.md` "Lane contract") + `build/views/overview.html`, `map.html`, `moving.html`, `money.html`, `explore.html`, `confluence.html` (view markup/grammar) |
| `templates/si_workspace.js` (router: `VIEWS`, `LEGACY_ANCHORS`, `resolveThemeHash()` owner) | Embedded **verbatim** in the candidate, byte-compared at build time (`README_BUILD.md` "Assembly order" step 5) — R3C reuses this file unchanged; it is not a migration surface, it is a constraint (`routing_contract.md` §0: "R3 MUST reuse `templates/si_workspace.js` verbatim... it must NOT be reimplemented") |
| `templates/_us_act_now_board.html.j2` (Overview Act-Now board, Bottoming-Watch row anchors) | `build/views/overview.html` `#actnow`, `#ov-watch` markup |
| `templates/_us_bottoming_watch.html.j2` | `build/views/overview.html` `#ov-watch` — note F-2 (§7 below): the reference DROPPED the row `<a>` this partial emits |
| `subsectors.js` (Confluence table/detail logic, `_industry_map()`, `detailHref()`, `stockHref()`) | `build/views/confluence.html` |
| `heatmap.js` (Money treemap) | `build/views/money.html` `#heatmap-scorecard` |
| `forming_narratives.js`, `_forming_narratives.html.j2` (Explore) | `build/views/explore.html` `#forming-narratives` |
| `rotation_events.js`, `subsector_rotation.js`, `desk_watch.js` (Moving mounts) | `build/views/moving.html` `#rc-events-mount`, `#rotation-app`, `#desk-watch-mount` |
| `time_machine.js` (Explore Time Machine) | `build/views/explore.html` `#tm-mount` — reference is manifest-only, recorded-not-executed for episode/chunk fetches (`README_BUILD.md` "Time Machine — recorded-not-executed ruling") |
| `sector_cycles.js` / `sector_cycles_data.js` (Map cycle clock chart) | `build/views/map.html` `#sc-cyclemap` |
| `sector_central_china.html.j2` (ZH-specific production sibling; owns `LAYER_ZH` translation map) | Cited only as the source of a REQUIRED repair (§3.3 below) — not itself a reference equivalent |
| `templates/sector_central.html.j2:3088` (`window.__siViewReads(BASKETS)` call site) | `build/views/overview.html` boot handler — see F-1 (§7): the reference ADDS an extra `__siRoute()` call production does not have |
| production CSS (`macro-desk.css`, `theme.css`, `sector_cycles.css`, and any Sector-Central-specific rules) | Reference's own inline/embedded CSS in `build/shell.html`/view partials — a Principal-Design-Lead visual grammar exists per `ORCHESTRATOR_ADJUDICATIONS.md` §3 (`build/DESIGN_SYSTEM_SPEC.md`, if present — confirm it was actually delivered per §1's open-items note) |

**Do not treat the build harness (`build/build_reference.py`,
`build/runtime_shim.js`, `build/verify_reference.py`,
`build/fixture_supplement/**`) as a migration source.** It exists to prove
the reference pipeline runs end-to-end and to quarantine the reference from
live data (`README_BUILD.md` "Lane contract" table, "R3B build harness"
row) — production keeps its own live fetch/Jinja-bake machinery untouched.

---

## 3. Required production dependencies the reference exposed

These are not recommendations; each is either a commission-mandated
behavior or a demonstrated production defect that a migration must not
silently reproduce or silently omit.

### 3.1 Scroll-offset repair (commission §14)

Commission §14: "canonical and legacy hash landings must not place the
page/view answer underneath sticky chrome... Reference must demonstrate
correct scroll-offset behavior... If production requires a router/CSS
repair later, file it explicitly in R3C." The router itself
(`templates/si_workspace.js`) is UNCHANGED — the fix is `scroll-margin-top`
CSS compensation on legacy-anchor targets, wired via a measured
`--ref-sticky-offset` CSS custom property (`ORCHESTRATOR_ADJUDICATIONS.md`
§2: "scroll-offset wiring (`scroll-margin-top`... the §14 required
behavior; the router's `scrollIntoView({block:'start'})` honors it)").

**However**, the QA attack lane's independent re-measurement
(`QA_ATTACK_REPORT.md` §1.6 Gate 6, cross-referenced by
`capability_crosscheck.md` F-6) found the mechanism is not fully sound: two
of the measured legacy-anchor landings (`#tm-mount`, `#grader`) settle far
below the fold because the anchor's async organs render AFTER the initial
`scrollIntoView` fires, and the actually-consumed `scroll-margin-top` (56px,
a static CSS fallback) does not match the JS-measured `--ref-sticky-offset`
(40px) the shim writes. R3C must carry the CORRECT version of this
mechanism to production — not the reference's incompletely-wired one — and
should re-verify against Gate 6's method (`QA_ATTACK_REPORT.md` §1.6) before
calling it fixed. Production's `routing_contract.md` §8 seam (b) ("Mobile
≤767px sticky top bar has no compensating `scroll-margin-top`") is the
specific defect this repair addresses.

### 3.2 A7 seams — filed, not repaired, still open for adjudication

`routing_contract.md` §8 / `ADJUDICATIONS.md` A7 record three routing seams
as recorded-not-repaired in R3A and R3B:

- **(a)** `#theme-*` resolves only at initial boot, never on a later
  `hashchange` (the router's own `hashchange` listener intercepts `#theme-*`
  first and activates Overview instead).
- **(b)** Mobile ≤767px sticky bar has no compensating `scroll-margin-top`
  on legacy anchor targets — **this is §3.1 above**, the one seam commission
  §14 promotes to a required REFERENCE behavior; production repair is
  explicitly deferred to R3C by §14's own text.
- **(c)** `sc-top` (and, per `routing_contract.md` §2, `forming-narratives`,
  unconfirmed) legacy-anchor targets are not confirmed present as literal
  DOM ids in production; routing to the correct VIEW still works, only the
  intra-view scroll silently no-ops. `ORCHESTRATOR_ADJUDICATIONS.md` §4
  confirms the reference deliberately did NOT mint `id="sc-top"` either
  ("`sc-top` id NOT minted (A7 seam (c) recorded, not repaired)").

Seams (a) and (c) are NOT commission-mandated for repair — they require a
fresh adjudication before R3C may touch them. Do not repair silently; file
an explicit ruling request if repair is proposed.

### 3.3 QA2-13 — "Validated" vocabulary allowlist coverage (REQUIRED before any Money-view migration)

`QA_ATTACK_REPORT.md` §8 QA2-13 (NOTE severity, but load-bearing for
migration): the reference's Money view renders "Forward track record:
**Validated**" — BC-2-governed vocabulary, producer-faithful to
`templates/sector_central.html.j2:3463`. It is not a defect in the
reference because `mockups/` is outside `scripts/check_validated_claims.py`'s
scan set. **The migration wave must confirm the CI allowlist entry's
`surfaces` list covers the new surface before this string ships to
`templates/` or `site/`** — otherwise the merged production change will be
red on `scripts/check_validated_claims.py` (house law:
`CLAUDE.md` §Epistemics, "The word 'validated' in user-facing text is
CI-enforced"). This is a REQUIRED pre-migration check, not optional
cleanup.

---

## 4. Production repair candidates discovered by R3B (recommend, do not mandate)

Each item below is a finding the R3B lane or the QA attack lane made against
CURRENT PRODUCTION, filed for R3C consideration. None of these is fixed;
none is authorized for repair by this draft. Each requires its own
adjudication at migration time, per the pattern `ORCHESTRATOR_ADJUDICATIONS.md`
itself uses ("filed as a delta for R3C, never claimed fixed" — header note).

1. **Anonymous regwall vs the R3A access contract's original GAP.**
   `mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/production/PROVENANCE.md`:
   the live site 401-gates `si_workspace.js` and every non-Overview view
   asset for anonymous visitors (`x-regwall: deny`,
   `authentication_required`). This resolves R3A's open access-contract GAP
   ("ungated = config grep, not live curl") in the direction of a **site-
   wide anonymous regwall in front of** the single premium Act-Now tier
   gate — it does not contradict the tier-gate semantics for signed-in
   readers, but it is a materially different production behavior than the
   R3A binding matrix's "ungated" language implied for Map/Moving/Money/
   Explore/Confluence. `ORCHESTRATOR_ADJUDICATIONS.md` §8: "The finding
   itself is R3C input, not something this cycle repairs."

2. **Desk Watch outage-reads-as-calm conflation.**
   `ORCHESTRATOR_ADJUDICATIONS.md` §5: the reference's Desk Watch
   distinguishes an absent-vs-empty state using only production's own
   recorded strings, making the binding matrix's own failure state
   reachable and answering commission §24 ("null→zero collapse").
   Production's own conflation — an outage reading as a calm/quiet desk —
   is explicitly "filed for R3C as a recommended repair" (same §5 line).

3. **`renderFormingNarratives` defer-order race.**
   `production/PROVENANCE.md` "Known, non-blocking production console
   error": `sector_central.html` loads `forming_narratives.js` with
   `defer`, and the very next `<script>` calls
   `renderFormingNarratives({base: "basketdata/"})` synchronously — a
   deferred script runs after DOM parsing but after the following
   non-deferred inline script, so the inline call throws a `ReferenceError`
   on every first paint, live and in the pinned-commit mirror alike. Does
   not block any view from mounting (confirmed by direct visual inspection
   of all six baseline PNGs per the same doc), but is a genuine console
   error reproducible on demand.

4. **Production emoji in the leadership strip vs commission §18.**
   `ORCHESTRATOR_ADJUDICATIONS.md` §6: "production's decorative emoji
   dropped (§18)" — the reference dropped decorative emoji in the Money
   view's style-tilt/leadership-driver presentation because commission §18
   bars "decorative Unicode stars, emoji section icons, arcane glyphs...".
   The source is production, still shipping the emoji; not repaired by R3B
   (out of scope), filed here as a candidate.

5. **`sc_flows` fragment — EN-inside-`.l-zh` spans and inline hex color
   tints.** `ORCHESTRATOR_ADJUDICATIONS.md` §6: the D3 lane replaced "14
   hardcoded hexes" in the extracted `#sc-flows` fragment with a "4×4 stroke
   identity" token scheme, and separately treated "two achromatic literals
   mirroring heatmap.js" as approved reference-side substitutions. The
   underlying production fragment (server-rendered, embedded verbatim per
   `README_BUILD.md` step 3) is the source of both the hardcoded hex colors
   and any EN-inside-`.l-zh` span defect this substitution was working
   around — read `ORCHESTRATOR_ADJUDICATIONS.md` §6 in full before deciding
   scope; this draft does not have independent evidence beyond that ruling
   summary and the production fragment itself must be inspected directly by
   R3C.

6. **Map `reco`/context conflation — already filed separately (A3), reference only de-amplified.**
   `ADJUDICATIONS.md` (R3A) A3: production's Map board renders
   `theme_intel.themes[].reco` as Buy/Add/Hold/Trim/Avoid tags beneath its
   own context-only disclaimer — "the same defect class the critics filed
   against the R2 mockup (DAC-001/002), live in production." R3A ruled this
   `authority: CONFLICT (context surface rendering action vocabulary)` and
   forbade the R3 designer from amplifying it. R3B's D2 lane additionally
   did NOT render the RVX_Q stance-text half of this same conflict
   (`ORCHESTRATOR_ADJUDICATIONS.md` §5), calling it "de-amplification," and
   flagged it explicitly for the Data/Authority critic. **Production repair
   itself is out of scope for R3B and remains a separately-filed item**, not
   something this handoff resolves — A3's own text: "Production repair is
   out of scope (handoff non-goal) and is filed separately."

7. **Overview stale-guard fail-open — already filed separately (A6).**
   `ADJUDICATIONS.md` (R3A) A6: "Overview stale guard fails open on
   malformed `as_of_utc`" (`sector_central.html.j2:1799-1800`,
   `isFinite` short-circuit returns not-stale). `capability_crosscheck.md`
   #27 confirms the reference carries this defect unrepaired, matching the
   R3A ledger note. Repair filed separately per A6's own text ("repair
   filed separately (non-goal here)").

8. **Production ≤767 nav scroller hides Explore/Confluence.**
   `ORCHESTRATOR_ADJUDICATIONS.md` §3: two APPROVED reference-side chrome
   divergences from production exist, both CSS-only, both "repairing the
   VTC-002 hidden-offscreen defect class": (a) view labels kept on the
   768–1100 rail (reference diverges from production here); (b) production's
   ≤767 six-tab horizontal scroller pushes Explore and Confluence — an
   Action view — off-edge, replaced in the reference by a 3×2 grid.
   **"R3C must adjudicate both for production"** — verbatim instruction
   from that section. This is the single most explicit "adjudicate at
   migration" item in the whole R3B record; do not silently carry either
   the reference's divergent behavior or production's current behavior
   without a ruling.

---

## 5. Migration method guidance

### 5.1 Quarantine boundary — what NEVER ships to production

The reference's display-tier machinery is quarantine-only and must not be
migrated as code, even in spirit:

- The **runtime shim** (`build/runtime_shim.js`: `REF.registry`,
  `REF.fragments`, `REF.parseJSON`, the `window.fetch` override,
  `REF.nav`, `REF.accessState`/`setAccessState`, `REF.simulateFetchFail`,
  `REF.log`) — production keeps its real `fetch()`, its real auth/session
  state, and its real navigation. `README_BUILD.md` "Lane contract" already
  bars the design lane from editing this file; R3C bars it from production
  entirely.
- The **embedded data registry** (one `<script type="application/json">`
  block per fixture/supplement file, baked into the single HTML file at
  build time) — production fetches these paths live; a migration wires
  production's existing fetch/bake paths, never a frozen embedded copy.
- The **quarantine drawer** (`#ref-access` lang/theme/access-state/
  fetch-fail harness UI, plus the recorder log `REF.log`/`REF.renderLog()`)
  — reviewer/QA tooling only, never customer-facing.
- The **Time Machine recorded-not-executed stub** — `README_BUILD.md`
  "Time Machine" section: the reference deliberately never fetches
  `tm_episodes.json` or per-year chunks. Production's REAL Time Machine
  fetch behavior (whatever it currently is) is unaffected by this reference
  choice and must be re-plumbed from production's own `time_machine.js`,
  not copied from the reference's manifest-only stub.

### 5.2 What maps roughly 1:1

- View markup/CSS grammar per view partial (§2 table) — the visual
  language, spacing, typography, and component structure the Principal
  Design Lead ratified (`ORCHESTRATOR_ADJUDICATIONS.md` §3, "State Ledge"
  spatial grammar, token-level color rationing, `.r3-tag` tertiary device,
  names-never-ellipsize law — "ratified as binding lane law", cited to
  `build/DESIGN_SYSTEM_SPEC.md` if that file exists; verify per §1's
  open-items note).
- Design tokens (colors, spacing scale, type scale) — subject to
  `research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md`'s "tokens extend theme.css
  only" law (`CLAUDE.md` §Design).
- ARIA/tablist behavior AS SPECIFIED by commission §17 ("Use proper tab
  semantics for tabs, group/toolbar/pressed semantics for filters/
  segments") — but NOT as literally implemented in the reference, which QA
  found broken in two of three tablists (`QA_ATTACK_REPORT.md` §4 QA2-08,
  QA2-09 — Confluence's Universe tablist has no arrow-key navigation and an
  `aria-controls` pointing at a non-tabpanel element; the Timing-states
  tablist ejects focus to the document root on ArrowRight). Migrate the
  SPEC, not the broken implementation; repair the implementation as part of
  migration or file it as a blocking pre-migration fix.
- Accessible chart equivalents (Map's rotation-map table, cycle-clock
  table; Money's heatmap-scorecard structure; Moving's `drawStrip()`
  equivalent) — subject to §7's F-5 exception below (Moving's
  `drawTrackRecord()` half is MISSING, not merely divergent).

### 5.3 What must be re-plumbed, not copied

- **Fetch paths**: production's real `fetch()` against real `site/`-served
  JSON/JS, with production's real error/retry/auth semantics — never the
  registry lookup.
- **Jinja bakes**: server-side template rendering (`_us_act_now_board.html.j2`,
  `_us_bottoming_watch.html.j2`, `_forming_narratives.html.j2`, the sector-
  central shell itself) — the reference's embedded-verbatim-fragment
  technique (`README_BUILD.md` step 3, `#sc-flows`) is a quarantine
  convenience, not a bake pattern to reproduce.
- **Hydrate flow**: production's real authenticated-fetch-then-DOM-insert
  cycle for the Act-Now premium payload. The reference's own hydrate path
  is independently known-broken — `capability_crosscheck.md` F-3 and
  `QA_ATTACK_REPORT.md` QA2-07 (CRITICAL) both document that the
  reference's `hydrated` access state removes the sign-in disclosure and
  paints a "Show more (N)" control that inserts ZERO rows when clicked,
  because the reference never routes the premium payload through
  `REF.fetchJSON` at all. **Do not migrate this behavior.** Production's
  real hydrate path (`access_hydration_contract.md` §3, cited by
  `README_BUILD.md` "Access-state mechanics") must be reused/re-verified
  independently, not derived from the reference's placeholder.
- **EN/ZH via production's own `tr()`/`L()` paths**: the reference uses its
  own inline `L()`/`.l-en`/`.l-zh` mechanism for the quarantined artifact;
  production has its own translation call sites (e.g.
  `sector_central_china.html.j2`'s `LAYER_ZH` map, cited in
  `capability_crosscheck.md` F-4 as the precedent production ALREADY
  maintains for exactly the untranslated-producer-enum problem the
  reference's Map board reintroduces). New display copy discovered by R3B
  (§below) must land through production's existing i18n mechanism, not a
  standalone dictionary.

### 5.4 Copy-ledger strings become template strings

`ORCHESTRATOR_ADJUDICATIONS.md` records new display copy authored during
R3B, destined for a copy ledger (§1's open-items note: the copy ledger
deliverable itself was NOT found on disk at cross-check time — R3C should
re-verify current state before relying on any specific inventory). Named in
the adjudication record:

- §4 (D1): authored ZH twin for the thin-data dot (production ships an
  EN-only `title=`, banned by house law); empty-lane copy for the four
  Confluence buckets production ships no list copy for.
- §5 (D2): rank-note clarifier ("Rank across all groups / 排名范围：全部分组").
- §6 (D3): manifest-derived Time Machine tier labels; section subheads;
  empty-state "why" lines.
- §7 (D1 follow-up): two disclosed fallback behaviors for the Confluence
  supporting-organs disclosure (ZH falls back to EN instead of a raw slug;
  an unmapped enum prints the raw producer value instead of a bare em-dash)
  — both are dead code on the frozen fixture, both disclosed rather than
  silent; R3C must decide whether to carry these fallback behaviors into
  production or handle them differently now that live data (not a frozen
  fixture) is in play.

Additionally, `capability_crosscheck.md` F-4 identifies NEW display copy
owed a copy-ledger entry that is not yet recorded anywhere: the Map board's
`reasoning[]` chain (`layer`/`tier` labels) is a NEW display surface —
production's own `#board` renders no such reasoning chain at all — so ZH
twins for `Cycle state`, `Trend gate`, `Regime gate`, `Momentum`, `Heat`,
`Fragility`, `validated`, `display`, `confirmer` are new copy obligations,
not carried-forward ones. Production's `sector_central_china.html.j2:1425`
`LAYER_ZH` map is the precedent for how to close this gap.

### 5.5 Render-budget note

Any new build-path work introduced during migration — additional Jinja
partials, additional baked JSON, additional nightly compute for new display
surfaces such as the Map reasoning-chain table — must respect the standing
render budget: "render budget is law (~67 min, 4-core-bound) — heavy compute
off the render path, artifacts to R2" (`CLAUDE.md` header). This applies
specifically to anything migrated from the accessible-equivalent tables
(Map rotation-board, cycle-clock table, heatmap text equivalent) if their
production implementation requires new server-side aggregation rather than
reusing already-baked payload fields — verify against the actual producer
payloads named in `routing_contract.md` §7 and the R3A binding matrix before
assuming any new compute is needed at all.

---

## 6. Evidence/acceptance skeleton for R3C

R3C's acceptance evidence should include, at minimum:

1. **Per-view visual parity to the approved reference** — not to R3B's
   candidate as delivered, but to the EXACT SHA Sol approves per commission
   §27. If the four fresh critics require repairs before approval, parity
   is against the repaired, approved SHA.
2. **The R3A attack suite as the floor** — commission §24: "R3A attack
   suite is the floor. Do not weaken it." `ORCHESTRATOR_ADJUDICATIONS.md`
   §0 records it green (59/59) at R3B's start; R3C must re-run it against
   production post-migration and show it still passes, not merely that it
   passed pre-migration.
3. **Capability cross-check re-run against production after migration** —
   the same 92-row standard `capability_crosscheck.md` used
   (`research/reference_integrity/mastermind-xpv2-sector-r3/capability_disposition_ledger.md`),
   re-probed against the LIVE/rendered production pages, not the reference
   artifact. Given the reference's own defects (§7), a clean pass against
   the reference does not imply a clean pass against production — R3C's
   cross-check is a fresh probe, not a copy of R3B's verdicts.
4. **Re-verification of every item in §7 below** — each must be either
   confirmed repaired (with its own evidence) or confirmed carried forward
   with an explicit note, mirroring the discipline
   `ORCHESTRATOR_ADJUDICATIONS.md` itself uses throughout ("recorded,
   approved" / "filed for R3C, not fixed").
5. **QA2-13 allowlist confirmation** (§3.3) before any Money-view
   "Validated" string change ships.
6. **The two §4 item 8 chrome divergences** — an explicit production
   ruling (adopt reference behavior, keep production behavior, or a third
   design), not a silent choice.

---

## 7. Open items inherited from R3B (fixture-coverage gaps and QA notes)

### 7.1 Findings against the reference itself (not production) — RESOLVED before freeze

STATUS UPDATE (orchestrator, freeze pass 2026-08-21): every finding below was
FIXED in the reference and re-probed green before the candidate froze — see
`FIX_VERIFICATION.md` (F-1..F-6, QA2-01..12) and the QA3 closure commit
(`afc6c8e2394c`: pg-plus class taxonomy, layer dedupe, boot-time `?reffail=1`
arming, nav aria-label ZH, heatmap per-stock "Browse the names" disclosure).
The one accepted residual: `#tm-mount`/`#grader`/`#scc-leadership` deep links
land at the page's natural scroll ceiling (near-bottom targets; visible, not
under chrome — §14 satisfied; page-length property, not a timing defect).
The original finding text is retained below for critic context:

- **F-1 (MAJOR, ledger #83)** — `#read-<id>` deep link opens the trace card
  then immediately closes it, because the reference's Overview boot handler
  calls an extra `window.__siRoute()` that production's own call site
  (`templates/sector_central.html.j2:3088`) does not call; a second,
  independent defect on the same path pollutes the route recorder (a
  `stopPropagation()` vs `stopImmediatePropagation()` mismatch between two
  capture-phase listeners on the same node).
- **F-2 (MINOR, ledger #11)** — Bottoming-Watch rows render as inert
  `<div>`s with no destination link, though the fixture carries real
  `href`s and production renders them as `<a class="actitem" data-rpop
  href="{{ x.href }}">` (`templates/_us_bottoming_watch.html.j2:95`); not
  recorded as an approved divergence.
- **F-3 (MINOR, ledger #19 + #32)** — the premium-hydration fetch leg and
  its 401/403/offline failure branch are unreachable from any harness
  control because the payload is read synchronously from the embedded
  registry rather than through `REF.fetchJSON`. Same root cause as QA2-07
  (CRITICAL) below.
- **F-4 (MAJOR, ledger #40 + smaller instance on #53)** — untranslated raw
  producer strings (`validated`, `display`, `confirmer`, `Cycle state`,
  `Trend gate`, `Regime gate`, `Momentum`, `Heat`, `Fragility` — 114 nodes)
  leak into the Map board's ZH surface; a smaller instance leaks three
  EN-only driver legs into Money's `#scc-leadership` ZH half. See §5.4.
- **F-5 (MAJOR, ledger #45)** — Moving's whole-market map names TWO
  accessible-equivalent functions (`drawStrip()`, `drawTrackRecord()`); only
  `drawStrip()` is reproduced. The `track_record` block IS present in the
  frozen fixture (`marketdata/subsector_rotation.json`,
  `n_snapshots:6716, n_days:25`) and production renders it
  (`templates/subsector_rotation.js:319-345`) — this is a straightforward
  omission, not a data gap.
- **F-6 (MINOR, ledger #85)** — deep-link landings for `#tm-mount` and
  `#grader` overshoot because the anchor scroll fires before async organs
  above it finish rendering, and the measured sticky-offset CSS variable
  (40px) does not match the value actually consumed by `scroll-margin-top`
  (56px static fallback). This is the §3.1 caveat above.

### 7.2 Findings against production, discovered via QA attack (`QA_ATTACK_REPORT.md`)

QA2-13 is covered in §3.3. The remaining QA findings (QA2-01 through
QA2-12) are against the REFERENCE candidate, not production, and are listed
in `QA_ATTACK_REPORT.md` §8 in full (1 CRITICAL — QA2-07, already covered
as F-3's root cause; 6 MAJOR — QA2-01/02/06/08/09/10; 5 MINOR —
QA2-03/04/05/11/12). R3C's fresh Mobile/Accessibility and Product
Regression critics should treat this table as their starting punch list for
the reference candidate, separate from the production-repair candidates in
§4.

### 7.3 Fixture-coverage GAPs carried (no artifact defect — data limitation only)

From `capability_crosscheck.md` "GAPS carried" section — these mean the
reference could not be EXERCISED on certain code paths because the frozen
fixture doesn't contain the triggering data, not that the code is broken:

1. buy_soon `days`-ascending sort: only one fixture row carries `days`.
2. `+N more` disclosure: fixture emits `more` only for hold/avoid lanes;
   the affordance is lane-generic in code but only one lane is exercised.
3. `#44` Moving's rotation-events table alternative: R3A GAP carried
   verbatim, still not resolved.
4. `#60` `ai_watch` is `null` in the fixture — the A8 "Model analysis /
   模型分析" branch is live code that cannot be shown visually on this
   fixture.
5. `#62` the falsifier-copy rewrite (`watchEn()`/`watchZh()`, the 2026-07-27
   #3821 house-law fix) never fires because `narrative_emergence.json`
   carries no falsifier field on this fixture.
6. `#67` the nonzero-`n_thin` branch for Nasdaq/Russell Confluence
   universes is still unobserved (both are 0/0 on this fixture).
7. `#68` only 7 of 9 producer Confluence states appear on this fixture.
8. `#75` the members-listing sort lives on `subsector_detail.html.j2`,
   outside the six-view reference scope — only the destination link is
   provable from this artifact, not the sort itself.
9. `sc-top`/`forming-narratives` legacy-anchor target-id existence was
   never independently confirmed against literal production DOM ids
   (`routing_contract.md` GAPS items 1, 3) — routing to the correct view
   works regardless; only the intra-view scroll target is unconfirmed.
10. A full auth-tier gating map of every destination link was never built
    — only the two confirmed `plans.html` tease links are named
    (`routing_contract.md` GAPS item 5).
11. `site/sector_central.html`/`site/si_workspace.js` (rendered output)
    were never byte-diffed against the templates to confirm currency at
    R3A census time — the routing contract is sourced from the TEMPLATE
    per authority order (`routing_contract.md` GAPS item 4). R3C works
    against current `origin/main` regardless and should re-verify template
    vs rendered-output currency itself.
