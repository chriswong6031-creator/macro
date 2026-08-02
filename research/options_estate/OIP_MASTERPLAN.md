# OIP — Options Intelligence Program: the EOD options-suite upgrade masterplan

Produced by the Fable main loop, 2026-07-29. Origin: operator brief ("advanced improvement
and upgrade loop for our options suite... radically improving usability, feature suite,
signal use, what it can do for users... completely upgrade the engine... this can also mean
taking data from Terminal's intraday data and its engines and signals to be used in our EOD
suite here. CREATE MASTER BUILD PLAN FIRST") → 4-lane sonnet census fan-out (macro surfaces,
macro engines/data, Terminal intraday suite, adjudications/kills) → live M1 ops probe →
Fable synthesis under `docs/DESIGN_DOCTRINE.md` + the frontend-design skill.

**Status: BUILDING — W0 in flight since 2026-07-29** (operator go: "lets start this build
out"). Every build wave ships through its own spawn with §0 inlined.

**Amendments (2026-07-29, W0 build-out — commissioning session, terrain-verified):**
1. **E2a struck.** Build-time recon verified `data/options_skew/snapshots.parquet` and
   `data/options_ivspread/snapshots.parquet` already append (concat + dedup on
   (date, underlying)); only the `site/` surfaces are latest-only, correctly so. The census
   claim behind §6 E2(a) was wrong; no store flip ships.
2. **The live system event log is not built in W0; E1 derives events instead.** The Python
   parity evaluators live in charting-app (`ingest/alerts_engine.py`) with prod wiring still
   fixture-based, and a third parity copy in macro would drift. The digest derives session
   events (flip crossings, wall touches, premium bursts, hot pockets, 0DTE spikes)
   deterministically from the archived minute series — same archives in, same events out —
   with thresholds documented against the Terminal evaluators they mirror. The
   `live_flow.events.v1` contract stays reserved for a future live writer if alert-fidelity
   events become a product need. T-lane = dated archive writers only; no charting-app code
   in W0.
3. **M1 greek-tap already armed** — the W0 "re-arm" item collapsed to verification (liveflow
   publishes SPY/QQQ/IWM greek surfaces per-minute, coverage 0.90–0.96, verified live
   2026-07-29). The real W0 ops work was the flow-ops-wt vintage-skew heal (r2sync
   ImportError dead since the 07-25 migration; pre-#3521 matrix gate) — recorded in
   `ops/THETADATA_R2_SYNC_RUNBOOK.md`.
4. **THE ONE-DOOR RULING (operator authorization 2026-08-01).** The operator, reviewing the
   estate ("SUPER CONFUSING. i don't know why we need five pages for options… you are
   authorized to consolidate, merge, group, create, remove, upgrade any features"),
   granted the page-retirement authority that OEU lacked. This supersedes, for the four
   ABSORBED pages only, the OEU satellite ruling "no page kills, no redirects, banners
   forever" and this plan's §1 "no page is killed": `gex.html`, `options_screener.html`,
   `flow_desk.html`, `flow_leaders.html` fold their remaining unique value into the
   workspace and become **redirect stubs** at their old URLs (the house pattern the Crypto
   Cockpit consolidation established — `templates/vector_allocation.html.j2`, #4037:
   `noindex,follow` + meta-refresh 0 + styled fallback link + `location.replace`, hash/param
   mapped). URLs never 404; bookmarks land on the right mode. The banner partial
   (`_options_workspace_banner.html.j2`) retires with them. `darkpool.html`,
   `market_structure.html`, `intraday_flow.html`, `movers.html` remain real pages — they
   were never absorbed and are not options surfaces. Full ruling + build spec:
   `research/options_estate/ONE_DOOR_RULING_AND_SPEC.md`. Wave table gains W1.6 (§11).

**Standing law honored.** This plan composes with, and does not re-adjudicate: OEU
(`research/options_estate/OEU_MASTERPLAN.md` — workspace IA, legacy-pages-live-forever,
posture-never-fused); Quanted (`research/quanted_options/MASTERPLAN.md` — Terminal
amalgamation, licensing honesty); Options Alpha (`research/OPTIONS_ALPHA_MASTERPLAN.md` —
gauntlet lanes, storage law); Options→NW Entry Intelligence (RO-1..13 — no fused composites,
per-source signing authority); the OPEX vanna/charm adjudication (signed-charm narratives
KILLED; S-FRONT-CHARM / S-VANNA-RELIEF alive); MSP rulings (no composite regime scorecard,
MSP-R3 no fused VC+CTA); LRV-O9-idiom Prophet fence (options context never enters
K-of-N/state/fire/sort/`select_candidates`); `research/DO_NOT_REBUILD.md` §1/§2 rows quoted
in §12. Registry rows carry no numeric IDs — cite rows by their text, never by invented
"DNR-nnn" numbers (a prior session's "DNR-104" citation does not exist in the registry).

---

## §0 ACCEPTANCE GATES — inline these verbatim into every OIP build spawn

Phrased "not done unless". A wave that cannot meet a gate returns to the commissioning
session with the gap named — it does not ship around it.

1. **Fresh-eyes happy path, zero workarounds.** A cold session on the built branch loads the
   surface end-to-end against production-shaped data (real `site/`/`data/` stores, not
   fixtures) with zero manual steps, zero console errors, zero races you reload around.
2. **Visual proof in the PR body.** Light + dark + ZH + 375px mobile crops of every changed
   surface, committed under `mockups/refs/oip/<wave>/`, plus computed-style verification
   (`getComputedStyle`) for any color/typography claim. Screenshot-at-scroll-0 is not proof
   for below-fold sections — crop each changed section.
3. **The 5-second test, transcribed.** PR body includes the one-sentence answer a cold reader
   gives to "what does this panel mean and what do I do" for each new Tier-1 panel. If the
   answer needs the builder's narration, the panel fails.
4. **Word budgets are hard limits.** Panel title ≤ 4 words; subtitle ≤ 14; row ≤ 1 line;
   exactly one stance chip + at most one footnote + one as-of per panel. Doctrine §1 table
   governs; demote, never compress into jargon.
5. **Banned-vocabulary sweep runs, not asserted.** Strip tags/tips/scripts from rendered
   HTML and grep the doctrine's banned Tier-1 terms plus this estate's slugs (`FlowZ`,
   `TSBrd`, `NotTrap`, `pain_dist`, `wilson_`, internal state enums, `n=`, study IDs,
   "validated" outside CI-sanctioned strings). Zero hits in visible copy, EN and ZH.
6. **Bilingual parity.** Every `.l-en` has an `.l-zh` twin; ZH is independently plain (no
   English state names inside ZH strings); no translated text in `title=` attributes
   (CI-guarded); ZH directional color flip untouched for direction-encoding elements and
   NOT applied to stance/structure accents.
7. **Honesty survives the upgrade.** Nulls, staleness, and coverage printed in plain words
   on Tier 1 with receipts on hover; staleness renders as calm chips/banners, never red
   alarm boxes; no "validated" claims (CI-guarded); no return-improvement claims for the
   vol-regime layer (`backtest_vol_overlay` verdict: regime layer adds no measurable value
   beyond vol-targeting — the #441 transparency-chip language is the ceiling).
8. **Direction claims route through sanctioned instruments only.** Any user-facing direction
   read cites tape_flow (calibration-passed) or ΔOI (reliable) — never the minute tick-rule
   path, which stays `~`-marked soft. No new fused scores, no posture arithmetic (MSP-R3).
9. **Ledger discipline.** Forward ledgers advance only in the nightly lane
   (`COLLECT_LANE=nightly` pattern); intraday/fastpath lanes write zero `data/`; replays
   and backfills never rewrite graded rows.
10. **Render-budget delta reported.** PR body states the measured wall-clock delta each new
    builder adds to its band (engine job ceiling is 200 min and fragile) and why its
    placement (collect / off-path / serial spine) is correct. Heavy compute proves it is off
    the render path.
11. **Session integrity guards.** Every new reader of dated stores session-filters via
    `lib/nyse_calendar` before `.iloc[-1]`/percentile logic (the #3721 weekend-row class);
    ET windows are exchange-calendar-derived, never UTC-pinned (DST class); derived ratios
    verify same-session inputs (mixed-asof class); percent-vs-fraction units asserted at
    ingestion with a unit test against BOTH fixture and prod shapes (the ×100 class, hit
    twice).
12. **No child self-merge on flagship UI.** Build lanes return PR + committed crops to the
    commissioning session, which reviews and completes the squash-merge chain
    (`merge-on-green` label) itself.
13. **Old URLs keep working.** Any nav/IA change keeps every legacy URL live with its
    banner; same-PR nav + SEO map updates; post-merge live re-check that the page and its
    banner survived the next render.
14. **Express-lane coverage travels with the surface.** Any page whose builder is added or
    materially changed gets `render.yml`/`engine-render.yml` dirty-scope coverage in the
    same PR (the flow_leaders staleness class, #3515), plus a `tests/` presence check that
    the builder is wired in `daily.yml`.
15. **GitHub annotations start the line** (`print("::warning ...", flush=True)`, never via a
    logger) — CI-guarded, see `tests/test_gh_annotation_line_start.py` exemptions before
    converting any module.

---

## §1 Verdict & thesis

The estate's engines are ahead of its product. Underneath eight nav entries sit: a
691-payload nightly GEX board with walls/flip/smile/term/tilt; a measured-flow desk over
353 names; a calibration-passed per-trade signing instrument (tape_flow, 0.8848 agreement)
accruing almost unused at SPY+KRE breadth; a 6-state dealer-regime machine with pin
probabilities and cascade triggers; a market-structure desk with a forward ledger already
grading expected-move breaches; a 380-root × 15-year options history store; and a live
intraday plane snapshotting per-minute flow surfaces to R2. The product shows a fraction of
this, hides its best instrument (the unified workspace — linked from **no** navigation),
duplicates thinner copies of pages it absorbed, contradicts its own pricing page (options
marketed Insider-paid; enforcement in observe mode; the "free lead magnet" movers page is
regwalled), and throws away the intraday session's story every evening because nothing
reads the Terminal's R2 artifacts back at the close.

**The thesis: the Evening Desk.** Terminal explains what is changing *now*; Macro explains
what *settled* — and the settled close is a story, not a snapshot. After every close the
estate answers five questions, in order, each owned by exactly one surface:

| # | Question | Owner |
|---|---|---|
| 1 | What kind of day was it? | Daily Brief (workspace) — new session-character read |
| 2 | What did positioning do? | Ticker workbench + Market Structure — walls/flip/ΔOI/regime |
| 3 | What is rich vs cheap now? | Scanner + Ticker — IV rank/term/skew/expected move |
| 4 | Which names earned attention? | Leaders + extremes shelf — persistence, washouts, builds |
| 5 | What does tomorrow inherit? | Brief "tomorrow" rail — levels, expirations, earnings, watch conditions |

The engine program (§6) makes each answer computable with receipts; the surface program
(§5) makes each answer legible in five seconds; the bridge (E1) makes question 1 possible
at all by digesting the intraday plane nightly. Satellite verdicts up front: **no page is
killed, no page is renamed, nothing new is fused** — the workspace becomes the front door
it was ruled to be, satellites keep their jobs with sharpened identities, and the estate
finally cross-links as one product.

---

## §2 Diagnosis — what is actually wrong today

Census evidence (2026-07-29, four independent lanes + live probes). Symptom → evidence →
root cause.

### 2.1 Product autopsy

| # | Symptom | Evidence | Root cause |
|---|---|---|---|
| 1 | The canonical surface is unreachable | `options.html` appears nowhere in `templates/_navlinks.html.j2` (verified post-#3957); trigger is still `gex.html`; movers still in the flyout | OEU nav regroup was deferred for a colliding icon PR (#3484) and the mechanical follow-up never landed |
| 2 | Marketed tier ≠ enforced tier | `plans.html.j2` sells "live options data… included with Insider and Pro"; no options path in `site_access.yml` `premium.enforced_early`; paywall observe-mode; any Free signed-in account walks in | Funnel and enforcement were never adjudicated for this family; pricing copy shipped ahead of gating |
| 3 | The "free lead magnet" is walled | `movers.html.j2` header comment + nav say Free; page absent from `regwall.py` PUBLIC_PATHS and `site_access.yml` public list → anon 302 | Same: access tiering never executed for the family |
| 4 | Workspace modes are thinner than the pages they absorbed, silently | Scanner caps 200 rows (standalone: all 384); Leaders top-12; Ticker mode has no charts and **no ticker search** (gex.html has both) | Modes re-implement reads in inline JS instead of sharing renderers; caps undeclared |
| 5 | The intraday story dies at 16:05 ET | Terminal census: tide/dte curves overwritten each minute; flip-cross/burst/hot-pocket/state-transition events discarded unless a user's alert was armed; nothing in nightly reads `live_flow/*` R2 back | The intraday↔EOD boundary is architecturally one-way (macro→R2→Terminal only) |
| 6 | Universe fragmentation reads as sloppiness | 384 (chains) / 353 (flow) / ~370 (ivspread) / ~360 (darkpool) / curated list (intraday_flow) with per-page ad-hoc disclosure | No shared coverage object; each builder discloses differently |
| 7 | Two risk philosophies in one nav group | `intraday_flow.html` uses "Buy now / Take profits" lanes; every sibling restricts to the closed six stances | Page predates the estate's restrained vocabulary; never reconciled |
| 8 | Best-in-repo signals invisible | S-FRONT-CHARM / S-VANNA-RELIEF (alive, sign-stable) surfaced nowhere; PRISM matrix published to R2 with no site consumer; `gex_state` 6-state machine + pin probability shown nowhere on macro; `oi_delta_clusters` always empty; tape_flow breadth SPY+KRE only | Engines shipped ahead of surfaces; accrual extensions never scheduled |
| 9 | History reads are shallow or frozen | Payload `iv_rank` is a ~40-day window; skew/ivspread stores keep latest-date only; `data/index_gex_history` frozen at last manual run (zero scheduled callers; hardcoded path to a store that moved hosts) | Accrual and reconstruction lanes were built as one-offs, never wired to cadence |
| 10 | Robustness gaps repeat known classes | `build_options_command` absent from express lanes (#3515 class); `build_flow_leaders._check_stale` imports a nonexistent calendar symbol → staleness gate silently vacuous; movers ZH never translated; market_structure raw-slug fallback on unknown enum | Known failure classes not yet swept across this family |

### 2.2 Process autopsy — why incremental fixes left these

OEU fixed correctness and unified the IA in one week, but three structural forces kept the
gaps open: (a) **deferred-mechanical work has no owner** — the nav regroup was correctly
deferred for a file collision, then nothing tracked it to landing; (b) **depth parity was
out of scope** — OEU's contract banned new derivations in the workspace, so modes shipped
as thin re-serializations and nobody owned closing the gap afterward; (c) **the bridge had
no charter** — reading Terminal's R2 output back into the nightly was named in the 07-23
consolidation review as the obvious next program and explicitly parked. OIP is that next
program, with owners and gates.

### 2.3 Ops truth (probed live, 2026-07-29)

The 2026-07-25 M2→M1 migration moved the ThetaData store and every ThetaData-dependent
launchd lane off this host. Probe of M1 (`ssh m1`, read-only): store intact at
`~/flow-ops-wt/data/thetadata_eod` (eod/oi/greeks, SPY oi through 2026); ThetaTerminal
running (last served 07-28 18:39); `com.mastermind.liveflow` loaded (last exit 0);
`com.macro.optionsmatrix`, `com.macro.thetadata-r2sync`, `com.macro.thetadata-backfill`
loaded with **last exit 1** — W0 triages whether those are safe-gate aborts or breakage.
This host's CI-side `audit_thetadata_accrual` checks only the repo-local stub and cannot
see M1 staleness — the real dead-man's switch is the M1-side audit, and OIP W0 verifies it.

---

## §3 Design language — "the record, developed"

Binding inputs: `docs/DESIGN_DOCTRINE.md` (content law, wins on conflict), the
frontend-design skill, and `research/options_estate/WORKSPACE_DESIGN_SPEC.md` (the pinned
`.oew` system: fill-track thesis, slate-indigo structure accent, brass record ink, closed
six-stance vocabulary, mono-for-figures type law, question-framed eyebrows). OIP **extends**
that system; it does not fork it. A designer lane pins exact markup/CSS per wave before any
builder assembles (spawn-handoff law §3); this section fixes direction and vocabulary.

**Identity.** The estate's subject is the settled record of dealer positioning and paid-for
conviction. The workspace already renders the *ledger* (stamp, coverage line, posture
console). OIP adds the missing register: **time**. The settled close is a developed
photograph of the session, and the estate should read like a record that remembers —
today's stamp, the session's arc, and the level's history in one visual language.

**The signature — the session filmstrip.** One new estate-wide element: a compact
Signal-Ink strip (SSR SVG via `lib/illus.py`, never Plotly) drawing the day's premium
arrival as a bounded arc with tick marks where structure events fired (flip crossings,
burst events, wall touches — from E1). Denominator visible (the session window is the
track; the close caps it). It appears identically in three homes — Brief's
session-character panel, Ticker mode's "how the day traded" row, gex.html's detail head —
and nowhere else. Under `prefers-reduced-motion` and on missing data it degrades to a flat
labeled track ("no intraday record for this session" in plain words). This is the one
memorable thing; everything around it stays quiet.

**Supporting vocabulary (each generalizes the ratified fill-track, no new chart idioms):**
- **History tick on every rank figure.** IV rank, GEX percentile, skew percentile render as
  the existing 5-pip track plus a small brass tick marking where today sits vs its own
  1-year path — the "record" accent doing real work (brass stays confined to record uses).
- **Expected-move cone with calibration dots.** The EM figure becomes a bounded band with
  up-to-5 grey dots = the last five sessions' realized moves, and a one-line plain-word
  calibration sentence sourced from the em ledger (E4). No new arithmetic in the template —
  the payload carries the sentence.
- **Build/unwind bars.** ΔOI by strike renders as the sector-bar idiom (pure length, value
  in its own mono column), diverging around zero; direction-neutral tint (build = accent,
  unwind = muted) so ZH flip never touches it.
- **Calendar chips.** Earnings/expiration/macro-event chips: mono day-count + plain-word
  label ("Earnings in 3 sessions"), `--warn` only inside 2 sessions, never red.

**Verdict law.** Each surface keeps exactly one decision element (the stance chip row of its
hero/footer). New shelves add facts, never verdicts — machine-checkable: one
`data-verdict-surface` marker per page; CI greps for duplicates.

**Alert & staleness policy.** Staleness is a calm chip + narrowed close-line, never a red
box (spec §9 pattern); "what we're watching" conditions replace any falsifier/refuted
language (operator 2026-07-27); event proximity uses the calendar chip ramp above.

**Vocabulary reconciliation (R5).** The closed six stances become estate-law on all nine
surfaces. `intraday_flow.html` maps its lanes into them (Buy now → Act; Take profits →
Protect gains) keeping its lane mechanics; ZH strings resolve through the `LEX` glossary
six (spec §5.0 — the three missing entries ship with W1's first surface PR).

**Bilingual as a feature.** Every new string lands as an EN/ZH pair at design time (pinned
in the wave spec, not left to builders); ZH is independently plain; the movers theme-name
gap and the market_structure enum fallback are swept in W2.

---

## §4 Information architecture — the estate map

**The ruled IA stands.** One workspace front door, four modes, satellites with sharpened
one-line jobs, legacy URLs alive forever with banners. OIP executes the missing pieces and
sharpens identities; it does not re-open absorption.

```
Options & Flow  (nav flyout — OEU-ruled regroup, finally executed; W1)
├── Options — the workspace            options.html          (trigger; 4 mode deep-links)
│     Daily Brief · Scanner · Ticker · Leaders
├── Adjacent desks
│   ├── Options Desk (instruments)     gex.html              charts bench: profile/heatmap/smile/term
│   ├── Intraday Flow Tracker          intraday_flow.html    curated live tape (scope label honest)
│   ├── Dark Pool Desk                 darkpool.html         off-exchange record (FINRA semantics)
│   └── Market Structure & Vol         market_structure.html index regime/vol/dispersion/calendar
└── (Daily Movers → moves to the US / markets group, per the standing OEU ruling)
```

**Division of labor inside macro (R3).** The workspace is the *reading* surface (words,
stances, decisions); gex.html is the *instrument bench* (interactive charts, search-first).
Ticker mode therefore gains a ticker search/typeahead and the missing depth **reads**
(§5.1) plus a prominent "Open the instrument bench →" handoff — it does not clone
gex.html's charts. Scanner/Leaders modes declare their caps in visible copy ("top 200 by
premium — open the full screener for all 384") — thinner by declaration, never silently.

**Shelf-budget law.** Every new shelf lands with a hard budget in its wave spec (rows,
words, one stance, one as-of) and the no-new-arithmetic rule: templates render payload
fields; every number a shelf shows must exist in a named engine artifact first.

**Cross-linking (the estate becomes one product).** W2 adds: per-ticker deep links from
Scanner/Leaders/extremes rows → Ticker mode → gex.html → Terminal (existing `?symbol=`
pattern); a compact "elsewhere on the desk" footer rail on all satellites (workspace ·
bench · structure · dark pool); per-stock dossier pages (`stocks/<T>.html`) gain an
"Options read" chip row linking into Ticker mode — today they link zero options surfaces.

**Access & funnel (PROPOSE-ONLY — operator site_access adjudication required; R4).**
The plan proposes, and marks clearly as needing the operator's call: (a) `movers.html`
enters `public` (it is designed, labeled, and marketed as the lead magnet); (b) the options
family enters `premium` posture via the existing `TIER_PREVIEW_PATTERN` (free-registered
sees the Brief's chrome + posture console as teaser; full modes at Insider) so `plans.html`
stops overpromising; (c) sitemap entry for whatever becomes public. None of this is built
without the ruling; W1 ships the mismatch *documentation* (this section) and the mechanical
prep only.

---

## §5 Surface programs

Each block lists: what it shows (Tier-1 → Tier-2), payload source, and its gate-relevant
notes. Designer lane pins exact markup per wave; budgets per §3/§0.

### 5.1 S1 — Ticker workbench depth (workspace Ticker mode + gex.html head)

New reads, all payload-driven (E2/E3/E1), identical data on both surfaces:
- **Rich or cheap** — IV-rank fill-track with brass history tick + one plain line
  ("Options on NVDA cost more than 82 of the last 100 sessions") + term-slope word
  (front-loaded / flat / carry) + skew read with percentile. Hover: exact figures, window,
  coverage depth ("young history — 4 months" until 252d).
- **Where positions built** — top-3 build / top-3 unwind strikes as diverging bars (ΔOI,
  reliable read), OI-vintage stamped. Hover: contract-level receipt.
- **How the day traded** — the session filmstrip (E1) + one sentence ("Premium arrived on
  the open drive; flip crossed twice; closed above it").
- **What the move is worth** — EM cone with last-5 realized dots + calibration sentence
  (E4). The straddle-implied number arrives with its track record.
- **Expiration pressure** — front-week concentration read (E7, display-tier): "A large
  share of this name's open positions expire Friday — moves near $X can feed on themselves"
  with the S-FRONT-CHARM receipt on hover. Never a direction claim.
- **Ticker search/typeahead** in the mode header (parity with gex.html; `/` focuses).
- Strategy-fit education chip (S6) at the footer.

### 5.2 S2 — Daily Brief 2.0 (workspace Brief mode)

Adds three shelves, keeps everything shipped:
- **Session character** (top, after posture console): filmstrip + "what kind of day" plain
  sentence + up to 3 structure-event chips (flip recross, late-day burst, wall rejection)
  from E1. Honest empty state when the intraday record is absent.
- **Tomorrow inherits**: index levels that held/broke at the close; calendar chips
  (expirations this week incl. OPEX distance, earnings count among covered names, macro
  prints); up to 3 "what we're watching" conditions in plain words (no falsifier language).
- **Extremes shelf (S5)** — see below; lives here, not a new page.

### 5.3 S3 — Scanner v2 (workspace Scanner + options_screener.html)

- New columns (E2/E3): true IV rank (young-flagged until 252d), term slope, skew pct, ΔOI
  net (5d), EM-vs-realized flag, session tag (from E1: open-drive / faded / pinned).
- Preset packs mapped to user intents: *Rich vol (premium-selling tailwind)* · *Cheap vol
  (owning moves is cheap)* · *Crowded calls* · *Protection bid* · *Earnings this week* ·
  *Near a flip* · *Fresh builds*. Each preset carries a one-line plain-word "why you'd
  look here".
- Declared caps + "open the full screener" (R3); saved-view via localStorage; CSV export
  on the standalone page (Insider-tier feature flag, prep-only until R4 ruling).
- The standalone page's dense provenance paragraph moves into a `?` LENS tip (doctrine
  demotion; text unchanged).

### 5.4 S4 — Market Structure & Vol desk (market_structure.html)

- Absorbs the "vol weather" duty as the estate's index-vol home: adds VIX term-structure
  strip (M1–M6 from `vix_curve.parquet`, accruing since 2026-06), VVIX/VIX candidate read
  (display + receipt, sign per validator), and the **expiration calendar shelf** (E5): next
  OPEX/quad-witching distance, front-week gamma share (E7), plus the honest "no robust
  edge" line on OPEX seasonality (existing verdict).
- Dealer-exposure history panel gains the multi-year percentile once E3 heals
  `index_gex_history` (frozen today); until then the panel says its window plainly.
- Fix in W2: theme.js load-order (its toggles are inert today — spec §0.20 documents the
  trap), the raw-slug enum fallback, and the builder docstring rot.
- Vol-regime hero language stays inside the #441 ceiling (no return-improvement claims).

### 5.5 S5 — Extremes & positioning shelf (inside Brief; no new page)

Six rows, each a named existing/E-lane artifact, cross-sectional over the covered universe:
highest/lowest IV rank · biggest 5d builds/unwinds (ΔOI) · walls that broke at the close ·
pinned names (close within 0.5% of max-pain with high pin-prob, language per pin-risk
display rules) · crowded-calls chip (call_skew_rich — LRV-R6: vote HELD at None pending
an n≥60 re-benchmark ~mid-Oct 2026; the construction behind the hold is ≥3 of the last 5
sessions above the window-excluded own-Q80 over ≥21 real readings) · heaviest same-day
share. Each row: 3–5 mono tickers deep-linking to
Ticker mode + one plain line. Stance: Watch — don't chase.

### 5.6 S6 — Strategy-fit education layer

Per-name chip + expandable read on Ticker mode/gex.html tying the E2 state to *structure
classes*, phrased as mechanics education with the Learn track as Tier-3:
"IV rank 82 + front-loaded term → selling premium is tailwinded; owning outright options
pays a high toll. If you'd rather own the move, defined-risk spreads cut the toll." Rules:
closed stance vocabulary; no strike/size/date prescriptions; no "validated"; every chip
carries the hover receipt (numbers + window) and a "learn the mechanics" link
(`learn/options/*` — 7 lessons shipped). ZH pinned at design time. This is the compliant
home for "recommendations": regime-conditional education, never trade instructions.

### 5.7 S7 — Estate chrome & funnel unification

- Satellites inherit the workspace session-stamp + close-line chrome as a shared partial
  (per-page coverage denominators — R8's shared coverage object).
- Nav regroup executes the OEU mechanical list (W1; sequencing note §11 re crypto-cockpit's
  planned touch of the same file).
- Cross-link rail + dossier chips (§4); movers ZH theme names; access-tier prep per R4.

---

## §6 Engine program

Display-tier first, always: every engine below ships freely as context with nulls printed;
nothing ranks, sizes, or gates without the existing gauntlet (§8). New artifacts register
in `config/synapse.yml` with schema/cadence/SLA; heavy compute stays off the render path
(§7). "Compose, don't rebuild" — each lane names the organ it extends.

**E1 — Session Digest (the Terminal→EOD bridge; flagship).**
New `engine/session_digest.py` + `scripts/build_session_digest.py`. Inputs, all read-only
from R2: `live_flow/surface/{ROOT}/{DATE}/` archives (exist today, 10-session retain),
`{DATE}/idx.json`, plus two **new dated archives** the intraday side starts writing
(T-lane): `live_flow/tide/{DATE}.json` and `live_flow/dte_tide/{DATE}.json` (today's
`*_current.json` are overwritten each minute — the digest cannot exist without them), and
a **system event log** `live_flow/events/{DATE}.jsonl` emitted by the alert-engine math
running on a *system* watchlist (flip crossings, wall touches, premium bursts, hot pockets,
0DTE spikes — the exact evaluators that exist in TS+Python parity today; Amendment 2: not
built as a live writer in W0 — the digest derives these event families from the archived
minute series). Privacy law:
the digest never reads user alert rows (`public.alerts` is owner-scoped); system events
only. Outputs: `data/options_session/{DATE}/{ROOT}.json` + `site/session/{ROOT}.json`
(latest, for surfaces) + a session ledger row (arc shape, event counts, 0DTE peak, wall
migration) — nightly lane only. Guards per §0.11. Cost: reads ~3–5 roots of small JSONs;
~1–2 min, collect job.

**E2 — IV analytics v2 (true history).**
(a) Flip `data/options_skew` + `data/options_ivspread` from latest-snapshot to appending
daily grids (schema change, synapse re-registration) *(Amendment 1: struck — the stores
already append; verified at build time)*. (b) True IV-rank/percentile: 15y
where ThetaData greeks cover a root (M1-side batch reconstruction → R2 artifact
`options_iv_history/{ROOT}.parquet`, one-shot + weekly delta), polygon-accrual window
otherwise, depth printed per name (young-flag < 252d stands). (c) Term slope + 25Δ skew
percentile join the per-symbol payload. The 502-day massive backfill path
(`OPTIONS_ALPHA` W1.1, Spearman ≥ 0.90 acceptance) remains the fallback if M1 batch
proves impractical. Placement: reconstruction on M1/launchd, never CI; nightly only joins
artifacts.

**E3 — Positioning persistence.**
(a) Light `oi_delta_clusters` (the always-empty field in `gex_state`) from
`data/polygon_gex/chains/{date}.parquet` (per-strike snapshots exist since 2026-06-15) —
build/unwind by strike with vintage stamps. (b) Wall-stability: sessions-at-level count for
current call/put walls from payload `history[]`. (c) Heal `index_gex_history`: repoint the
hardcoded store path through `resolve_thetadata_store()`, schedule the reconstruction
weekly on the store-bearing host, publish to R2; `market_gamma`'s multi-year percentile
stops silently freezing. (d) GEX percentile-vs-own-history joins per-symbol payloads.

**E4 — Expected-move calibration (extend, don't invent).**
`data/market_structure/ledger.parquet` already grades index `em_breach` (MSP-R10). E4
extends the same ledger pattern per-name: nightly record straddle-implied EM for covered
names; grade T+1/T+5 realized; emit per-name and universe hit-rate receipts →
`site/em_calibration.json`. Surfaces consume the plain-word sentence only (§3). Nightly
sole advancer; no backfilled grades; Calibration Lab (measurement.html) gains the options
wing below the fold.

**E5 — Events desk data.**
Earnings calendar heal is a W0 gate item (the 07-29 E-waves census found 3/1364 fresh) —
source fix or honest descope; then: per-name next-earnings + implied-move-into-earnings vs
last-8 realized post-earnings moves (theta history where covered); OPEX/quad-witching
distances from `engine/opex.py` (exists); macro prints from the existing econ calendar
feed. Output: `site/options_events.json`.

**E6 — tape_flow breadth.**
The estate's only calibration-passed direction instrument accrues SPY(+KRE) only. E6
completes the chartered ≥5-session multi-root hardening, then extends accrual to the
liquid-index+mega-cap set the workspace actually fronts (SPX/SPY/QQQ/IWM + top premium
names), with per-root coverage printed. Every surface direction read then upgrades from
`~`-soft to measured where tape coverage exists (§0.8).

**E7 — Expiration-pressure read.**
Front-week charm/gamma concentration + vanna-relief (S-FRONT-CHARM / S-VANNA-RELIEF —
alive, sign-stable after RV residualization) become a display-tier per-name and index read
with receipts; explicitly distinct from the KILLED signed-charm narrative family — copy
never claims direction, only concentration mechanics ("a large share of open interest rolls
off Friday").

**E8 — Integrity & ops sweep (W0).**
M1 triage (exit-1 lanes: optionsmatrix / r2sync / backfill — safe-gate abort vs breakage;
R2 matrix vintage; greek-tap re-arm so surface `gex/vanna/charm` grids start populating);
fix the vacuous `_check_stale` import in `build_flow_leaders`; express-lane coverage for
`build_options_command` (+ new builders, §0.14); coverage-audit test drift (28 vs 36);
`call_skew_rich` activation check; weekend-row audit across remaining options readers;
unit-divergence tests (percent/fraction) on every ingestion seam; shared coverage object
(R8) emitted by each family builder.

---

## §7 Data plane, budget & ops accounting

**Placement law.** Nightly render band gains only: `build_session_digest` join (~1–2 min,
collect job), events/extremes assemblers (seconds, pure joins), payload enrichment inside
existing builders (bounded — measured deltas reported per §0.10). Heavy or historical
compute (IV history reconstruction, index-GEX reconstruction, tape_flow backfill windows)
runs on the M1/launchd plane or one-shot operator-run scripts, publishing R2 artifacts the
nightly *reads*. The engine job's 200-min ceiling is treated as full.

**R2 contracts (new/changed).** `live_flow/tide/{DATE}.json`, `live_flow/dte_tide/{DATE}.json`,
`live_flow/events/{DATE}.jsonl` *(reserved — Amendment 2)* (T-lane writers, retain ≥ 30 sessions — the digest ledger
is the durable record, R2 archives are working files); `options_iv_history/{ROOT}.parquet`;
`index_gex_history/*.parquet` mirror. Surface archive retain stays 10 (digest persists what
matters). All writers idempotent, heal-now on missing index files (deferred heals never
arrive for `--once` runs).

**Cross-repo T-lane (charting-app + ops).** Small, sharply-scoped: dated tide/dte archive
writes in the poller loop; the system event log emitted from the alert evaluators' shared
math (new module reusing `optionsAlerts` ports); no Terminal UI work in OIP. Deploy per the
liveflow runbook ritual; both repos' laws apply (spawn audits target-repo AGENTS first).

**Registry.** Every new artifact registers in `config/synapse.yml` (schema/cadence/SLA);
`docs/site_semantics/` gains glossary entries for each new user-facing stat (IV rank, term
slope, skew pct, session tags, EM calibration, expiration pressure) — the Context Index
answer path for "what does this stat mean".

---

## §8 Signals & epistemics

**The honest ledger (as of 2026-07-29, census-verified):** nothing in this estate is
authority-tier today. `data/gex/gate.json` scored:false (building_history, n=11–29/bucket
vs 30); `data/vol_regime/gate.json` absent and `regime.json` scored_active:false; index
gamma-regime sign is era-dependent → context forever; minute tick-rule direction 0.41 →
permanently soft; sector-ΔOI dead; skew-decel unsupported; max pain has no validation
program (language stays careful). Passed instruments: tape_flow signing (0.8848/0.80,
tape-pipeline artifacts only); reliable ΔOI (matched-contract day-over-day). Alive
hypotheses accruing toward Q4-26 verdicts: S-CWIV, S-FRONT-CHARM, S-VANNA-RELIEF,
VVIX/VIX candidate, fire-conditioned gates (come_back_on 2026-10-15 / 2026-12-15).

**Rules of the program.** Display-tier ships freely with nulls printed in plain words +
Tier-2 receipts (the compliant form); promotion to any rank/size/gate authority only
through the existing pre-registered gauntlet lanes — OIP schedules **no** new gate flips
and its surfaces must read correctly under every gate state; no fused composites of any
kind (posture co-display law); direction only via sanctioned instruments; LLMs de-escalate
calibrated keys only, never originate; the Prophet fence stands verbatim; "validated" stays
CI-guarded; falsifier vocabulary stays off cycle surfaces (projection windows + "what we're
watching" + Calibration Lab below the fold).

**What OIP adds epistemically:** the EM calibration ledger (E4) and session ledger (E1)
create *gradeable* forward records where none exist — the estate's trust story ("we grade
our own expected moves nightly") without a single authority claim.

---

## §9 Competitor read (brief — recon exists)

`research/quanted_options/RECON.md` (Quanted teardown) and the Terminal-side QuantData
parity docs already cover the intraday competitor field; OIP's EOD field: SpotGamma-style
evening letters, MenthorQ levels, Unusual Whales flow digests. Adopt: evening-digest
cadence discipline (our Brief becomes the letter, automated). Adapt: levels-with-history
(walls + stability + percentile beats static levels). Skip: signed-participant claims (no
license — "OI-assumption model" honesty stands), alert-noise firehoses (Terminal owns live;
EOD mines the system event log), fused "market score" dashboards (killed by law). Our
moats: calibration receipts on our own numbers, bilingual EN/ZH, education-in-surface,
honesty layer (coverage/vintage/staleness as chrome), and the intraday→EOD session record
nobody else keeps.

---

## §10 Bilingual, SEO & access

Bilingual parity is a §0 gate; new-string EN/ZH pairs pinned in wave specs; `td()`/`LEX`
for dynamic labels (three missing stance strings added in W1). SEO: per-stock dossier
"Options read" chips (S7) create the family's first crawlable internal links; sitemap
entries follow the R4 access ruling only. Access: §4's PROPOSE-ONLY block is the complete
statement — movers public, family tier posture via TIER_PREVIEW, plans.html reconciliation;
operator adjudicates; W1 prepares mechanically without flipping anything.

---

## §11 Build phasing

Model routing per CLAUDE.md: Opus `builder` builds, Opus `designer` pins surface specs
first (flagship modes may pull the main loop per the design lane), Opus `reviewer` runs
verify stages, sonnet only for mechanical census, Fable main loop adjudicates and merges.
Spawn-handoff law: §0 inline; refs committed (`mockups/refs/oip/`); commissioning session
merges. Every wave: PR(s) → `merge-on-green` label → live verify.

| Wave | Scope | Lanes (routing) | Ships |
|---|---|---|---|
| **W0 — truth & spine** | E8 integrity sweep; M1 triage + greek-tap re-arm; T-lane archive writers (events → E1, Amendment 2); E1 digest engine (data only); E5 calendar heal check; E2a struck (Amendment 1) | builder ×2 (macro, cross-repo T-lane) + reviewer | data artifacts + guards; zero UI |
| **W1 — front door & workbench** | Nav regroup (OEU mechanical list); ticker search; S1 Ticker depth reads; LEX stances; declared caps | designer (pins S1 spec + filmstrip) → builder; reviewer | the workbench answer to Q2/Q3 |
| **W1.6 — one door (Amendment 4)** | W1.6-A capability: Flow mode (flow_desk fold); Ticker raw-structure shelf + primer (gex fold); Scanner uncap + filters + CSV + 7th preset (screener fold); Leaders full boards (leaders fold); Terminal `sym` param fix. W1.6-B flip: 4 redirect stubs; banner retires; nav regroup to 3 entries; intraday_flow relocates to the US/markets group | Fable main loop pins the spec → builder ×2 sequential; reviewer | one options destination |
| **W2 — the evening read** | S2 Brief 2.0 (session character + tomorrow rail); S5 extremes shelf; cross-link rail + dossier chips; movers ZH; market_structure enum/theme.js fixes | designer → builder ×2 | the Q1/Q4/Q5 surfaces |
| **W3 — scanner & structure** | S3 Scanner v2 (columns/presets/saved views); S4 Structure & Vol desk (term structure, calendar shelf, E7 read) | designer → builder ×2 | the Q3 breadth + index home |
| **W4 — calibration & education** | E4 EM ledger + Calibration Lab wing; S6 strategy-fit layer + Learn tie-ins; E6 tape_flow breadth surfacing | builder + reviewer (stats) | the trust story |
| **W5 — adversarial wave** | Bug hunt both repos across everything OIP shipped (finders → refutation-first verify → fix lanes), then full live verification | reviewer ×N → builder fix lanes | closure, per house pattern (bugs last) |

**Sequencing notes.** (1) `_navlinks.html.j2` is also targeted by the crypto-cockpit plan
(W2 there, plan-only): whichever program lands first, the other rebases; the OIP diff edits
the existing Options group only, crypto adds a new group — semantic conflict is nil, git
conflict is likely; coordinate at land time. (2) `gex_state` schema changes stay
backward-compatible (crypto H7 reads COIN/MSTR payloads). (3) W1–W3 surface waves depend on
W0 artifacts existing but degrade honestly if a store is late (empty-state law). (4) The
access flip (R4) is **not scheduled** — it executes only on the operator's site_access
ruling.

**Not scheduled — needs its own adjudication:** ~~legacy-URL sunset/redirects~~
(scheduled 2026-08-01 as W1.6 per Amendment 4 — operator authorization received);
intraday_flow's long-term home (macro vs Terminal — OEU deferred, still deferred;
W1.6 only relocates its NAV entry out of the options group, the page is untouched);
research/watchlist API and authenticated user-state service; Terminal workspace-system and
contract-tape items (Terminal charter, not OIP); any gate flip.

---

## §12 Risks & standing-kill compliance

**Compliance table (kills → how OIP complies):**

| Standing rule | OIP compliance |
|---|---|
| Fused per-position composite / composite regime scorecard / positioning fusion (DNR §1, MSP-R2, Signal Commons) | Zero new composites; extremes shelf = named single-metric rows; posture console untouched; verdict law limits decision elements |
| Signed-charm narratives KILLED (vol/size confound) | E7 surfaces *concentration mechanics* only, direction-free copy; receipts cite S-FRONT-CHARM/S-VANNA-RELIEF (the alive, distinct studies) |
| DOI dead at sector level; skew-decel unsupported | Neither resurfaces; ΔOI shown per-name as descriptive build/unwind (reliable read), never a sector signal or ranker |
| Tick-rule direction soft; delta-adj rejected | §0.8; tick-path stays `~`-marked; E6 upgrades via tape only |
| Volume-spike ranker refuted (equity fingerprint row) | Session tags/RVOL remain descriptive context, never rank or admit names |
| Prophet fence (LRV-O9 idiom) | No OIP artifact enters Prophet selection/state/fire paths; display hooks only via existing M-PRO seams |
| OEU IA rulings (no kills/renames/merges; banners; posture never fused) | §4 executes the ruled regroup; absorption not re-opened; satellites keep names |
| Charm honesty / OI-assumption honesty (Quanted) | Education copy keeps "OI-assumption model" framing; no signed-participant claims |
| Vol-regime no-return-claims (#441 ceiling) | §0.7 gate |
| Nightly sole ledger advancer; intraday writes no data/ | E1/E4 ledgers nightly-only; T-lane writes R2 archives only |

**Ranked risks:**
1. **M1 single point of failure** (store + intraday plane on one host; r2sync last-exit 1;
   CI audit blind to it). Mitigation: W0 triage + M1-side dead-man's audit verified + R2
   offsite sync confirmed before any W1+ engine depends on it; every consumer fails to
   honest empty states.
2. **Render budget** (200-min ceiling, 11-builder band). Mitigation: §7 placement law,
   §0.10 measured deltas, heavy compute off-path by construction.
3. **Duplicate-implementation drift** (workspace modes vs legacy pages). Mitigation: R3
   declared-caps + shared payload fields (drift becomes visible data drift, not silent UI
   drift); W5 adversarial wave diffs both surfaces against the same payload.
4. **Nav-file collision** with crypto cockpit. Mitigation: §11 sequencing note; mechanical
   list kept small.
5. **Known failure classes recur** (weekend rows, DST windows, mixed-asof ratios,
   percent/fraction units, express-lane gaps, vacuous staleness guards). Mitigation: each
   is a named §0 gate (11, 14) and a W0 sweep item with tests pinning the defect class.
6. **Scope creep into Terminal**. Mitigation: T-lane charter is three writers + one event
   log; all Terminal UI explicitly out of scope (§11 not-scheduled list).
7. **Access-tier limbo persists** (marketed ≠ enforced). Mitigation: R4 proposal packaged
   for one operator decision; until ruled, no surface claims a tier it doesn't enforce.

---

## Appendix A — disposition table (census-complete; nothing survives outside it)

| Existing block | Disposition |
|---|---|
| `options.html` chrome (stamp/console/close-line/tabs) | KEEP verbatim; becomes nav front door (W1) |
| Brief mode shelves (chips/index cards/sector bars/bets/rail/handoff) | KEEP; add session-character, tomorrow rail, extremes (W2) |
| Scanner mode | KEEP; declared cap + v2 columns/presets (W3) |
| Ticker mode | KEEP; + search + S1 depth reads + bench handoff (W1) |
| Leaders mode | KEEP; declared cap; feeds extremes deep-links (W2) |
| `gex.html` ladder/charts/primer/search | KEEP as instrument bench; head gains filmstrip + S1 reads (W1) |
| `options_screener.html` full board + filters | KEEP; v2 columns; provenance paragraph → LENS tip; CSV prep (W3) |
| `flow_desk.html` tide/sectors/themes/bets + live overlay | KEEP; overlay upgrades to dated-archive read when E1 lands (W2, optional) |
| `flow_leaders.html` boards + ladders | KEEP; staleness-guard fix (W0) |
| `intraday_flow.html` lanes/spotlight/board | KEEP; stance-vocab mapping + honest scope label (W2); ownership stays deferred |
| `darkpool.html` desk | KEEP; chrome partial + cross-link rail only (W2) |
| `market_structure.html` 6 panels | KEEP; becomes Structure & Vol (S4) + fixes (W2/W3) |
| `movers.html` | KEEP; moves nav group (W1); ZH fix (W2); public flip awaits R4 ruling |
| OEU banners on absorbed pages | KEEP forever (house law) |
| PRISM matrix R2 artifact | Consumer stays Terminal-side; macro surfaces None of it in OIP (explicit non-goal) |
| `oi_delta_clusters` empty field | LIT by E3 (W0/W1 data, W1 surface) |
| Wave-2 greek grid keys (netprem-only today) | Populated via W0 greek-tap re-arm; Terminal renders them; macro digest reads netprem only |
| `index_gex_history` frozen parquets | HEALED + scheduled (E3, W0) |
| `em_breach` index ledger rows | EXTENDED per-name (E4, W4) |
| skew/ivspread latest-only stores | Amendment 1: already appending — no flip needed |
| tape_flow SPY+KRE accrual | EXTENDED (E6, W4) |
| Learn options track (7 lessons) | LINKED from S6 chips; no rewrites |
| `.pvcard` popover clip (5-board defect) | NOT OIP scope; stays with its flagged owner; OIP avoids `_prophet_card` edits |

## Appendix B — new artifact contracts (sketch; final schemas in wave PRs + synapse.yml)

- `options_session.v1` — `data/options_session/{DATE}/{ROOT}.json` + `site/session/{ROOT}.json`:
  `{root, session_date, arc:[{t,ncp,npp}]↓sampled, events:[{t,type,level?,side?,z?}],
  zero_dte:{peak_share,at}, walls:{open:{call,put},close:{call,put},migrated:bool},
  flip:{crosses:int,last_side}, coverage:{minutes,expected,gaps}, asof, schema}`
- `options_iv_history.v1` — R2 `options_iv_history/{ROOT}.parquet`: `date, iv30, iv_rank_252,
  term_slope, rr25, skew_pct, depth_days, source{theta|polygon}`
- `em_calibration.v1` — `site/em_calibration.json`: per-name `{em_1d, realized_1d, inside:bool}`
  ledger aggregates `{n, hit_rate, window}` + pinned plain-word sentence EN/ZH
- `options_events.v1` — `site/options_events.json`: `{earnings:[{t,name,days,implied_move,
  past_moves[]}], expirations:[{date,kind,front_share}], macro:[{date,label}]}`
- `live_flow.events.v1` — R2 `live_flow/events/{DATE}.jsonl`: one JSON object per system
  event `{t, root, type, level?, side?, z?, share?}` (types = the five evaluator families;
  reserved — Amendment 2, not written in W0)

## Appendix C — census provenance

Four lane reports (2026-07-29, sonnet Explore, read-only): macro surfaces (9 pages + nav,
per-page inventories, gating/i18n/cross-link audit); macro engines (per-engine I/O,
schedules, history depths, dormant list, ops-host probe); Terminal suite (views, alert
math, artifact cadences, ephemeral-signal list, export ranking); adjudications (registry
rows quoted, gate states live-read, open-lane collisions, house format). Plus a live
read-only `ssh m1` probe (store + launchd states). Claims in this plan cite those censuses;
builders re-verify file:line specifics at build time (the estate moves fast).
