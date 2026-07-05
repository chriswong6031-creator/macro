# News Delta Desk — Masterplan (Fable, 2026-07-04)

**Program:** upgrade `news.html` from a tag-recitation headline accordion into an institutional
News Delta Desk that (a) renders parsed deltas instead of headlines and (b) feeds Neural Web
through a **governed, earned-authority channel** — never through laundered context.

**Supersedes:** the Opus assessment (`research/NEWS_DELTA_DESK_ASSESSMENT.md`) — its verified
findings stand; its plan was subtraction-only and is extended here. External ChatGPT doc
(`~/Downloads/news_intelligence_upgrade_plan.md`) is the original problem statement.

---

## 1. Grounded diagnosis (all verified in-repo)

1. **The page product is tag-recitation.** `templates/news.html.j2` renders one accordion of
   ~18 headlines; the "condensed read" is template-synthesized from the headline's own tags.
   Zero information beyond the tagger's guess.
2. **The keep-side classifier mislabels events.** Live sample: "U.S. job creation cools…
   payrolls growth of just 57,000" → `theme: "stocks"`. NFP — whose date `event_calendar.py`
   knew in advance, whose value sits in the title — renders as a generic mis-themed row.
   Root cause: keyword-hit ≠ event identity (same disease as the Nuveen leak, keep side).
3. **Substrate ≠ product.** News engines *write into* qbus (`financial_news.py:211`,
   `build_news.py:152`) but the page never *reads back* `novelty_z`, `echo_stats`, or any
   qledger grade. One-way plumbing; the integration is the unbuilt work.
4. **Phase-0 reject families are already built and verified** (uncommitted PoC on the working
   tree): `low_value_reason()` + fund-distribution / lifestyle / personal-finance-QA /
   ahead-of-earnings families; 12/12 new tests, 83-test news suite green.
5. **No macro-surprise parser exists anywhere** — raw official release titles display unparsed.

## 2. Architecture: the earned-authority spine

**Non-negotiable firewall:** news engines stay LEAF / `is_context_only=True` for the
*allocation-scoring path*. Direct news→scoring is the laundered-override pattern (see BTC
vector registry program) and is banned.

**The Neural Web channel is earned, per event class:**

```
kept item → event object (type, direction, numbers, novelty, echo)
         → qledger forward grading per EVENT CLASS (1d/5d/21d, Wilson intervals)
         → governance ledger claims
         → Wilson gate: class clears → bounded, revocable signal emission to Neural Web
                        class fails  → stays context, calibration board says so
```

News is never grandfathered as signal. Pre-registered honesty clause: **W5 may end with zero
classes clearing the gate** (prior: narrative rank-IC≈0). The plan is robust to that — W1-W4
stand alone, and a calibration board reading "guidance_cut: n=42, not yet significant" IS the
institutional product.

**Consumer-decision spec** (every rendered card must answer):
what changed · vs. what expectation · who's affected · confirmed elsewhere? · what has this
event class done historically. Can't answer → rejected or explicitly display-only.

## 3. Waves

| Wave | Deliverable | Depends | Tier | Status |
|---|---|---|---|---|
| **W0** | Land Phase-0 PoC on clean branch; wire `low_value_reason()` into the 3 call sites; per-feed `rejected` metadata → `site/news/rejected.json` | — | Sonnet build · Opus review · Haiku merge | dispatching |
| **W1** | Macro Surprise Engine: release registry keyed off `event_calendar`; FRED actual/prior/revision; surprise fallback hierarchy (revised prior → trailing trend → 3-5y z-score → nowcast deviation); `site/news/macro_releases.json` cards; raw stub suppression | W0 merged | Sonnet build · Opus review | dispatching |
| **W2** | Event identity layer: `engine/news_events.py` deterministic ~20-class event-type taxonomy + numeric extraction + keep-side centrality; first read-back of qbus `novelty_z` + `echo_stats` onto headline dicts. Display-only fields; no gating | W0 merged | Sonnet build · Opus review | dispatching |
| **W3** | Page rebuild as boards: Executive read · Delta board · Macro release board · Theme-confirmation board (join subsector rotation + basket velocity) · Reject log · Calibration board | W1+W2 | Sonnet + frontend idiom | queued |
| **W4** | Ledger closes the loop: kept events auto-enter qledger; per-class Wilson grading; live calibration board; grade a **sample of rejects** (over-filter guard) | W2 | Sonnet build · Opus judge | queued |
| **W5** | Neural Web earned-authority channel: claims → governance ledger → Wilson gate → bounded revocable emission. Load `ORACLE_CONSTITUTION.md` first | W4 evidence | Opus/Fable | queued |

### Acceptance criteria

- **W0:** doc's garbage headlines rejected with named reasons (regression tests); rejected.json
  artifact written with capped rows `{title, domain, reason, feed}`; full news suite green;
  PR squash-merged same-day.
- **W1:** "Manufacturing and Trade Inventories and Sales" never displays raw — either a parsed
  surprise card exists or the stub is suppressed with reason `macro_release_stub`; NFP/CPI/claims
  produce cards with actual/prior/surprise + z-score; module degrades gracefully offline (never
  raises into build); PIT caveat documented (revised-vs-first-print; ALFRED vintages = later).
- **W2:** NFP-style titles classify `event_type=macro_release` (not theme "stocks" as primary
  identity); taxonomy fixtures pass (guidance cut/raise, contract award, probe, offering, M&A
  rumor vs confirmed…); numeric payloads extracted ($, %, guidance ranges); novelty_z/echo
  attached to kept headline dicts; zero gating changes (diff proves display-only).
- **W3:** every card meets the consumer-decision spec or is labeled display-only; i18n rules
  respected (no translated text in title= attrs; zh up/down token flip).
- **W4:** calibration table renders with honest "insufficient n" cells; reject-sample grading
  report exists.
- **W5:** emission only for Wilson-cleared classes; revocation path tested; LEAF firewall
  audit passes (no scoring-path import of news modules).

### Kill criteria

- **K-W1:** if free FRED plumbing cannot support ≥6 releases with sane surprise math, ship
  registry + suppression only, defer cards; do not fake consensus.
- **K-W2:** if deterministic taxonomy precision on fixture set <90%, narrow the class set
  rather than adding an LLM gate.
- **K-W5:** zero classes clear the Wilson gate → no emission ships; calibration board is the
  deliverable. This is a valid program outcome, not a failure.

## 4. Orchestration protocol (this program)

- **Fable = orchestrator/planner/reviewer of last resort.** Never spawns Fable subagents.
- **Tier routing:** Sonnet builds · Opus reviews/judges · Haiku mechanical (merges, cleanup).
- **Escalation ladder:** Sonnet build fails or review rejects twice → Opus rebuild → still
  failing → Fable intervenes by hand.
- **Isolation:** every builder works in its own `git worktree` off fresh `origin/main` at
  `/tmp/nw_*`; the primary working tree (branch `codex/remove-us-stocks-risk-radar`, has
  unrelated uncommitted WIP) is NEVER touched by agents.
- **Merge discipline:** branch off main → PR → squash-merge same-day (standing approval);
  sequential merges with rebase for the second of a parallel pair.

## 5. Hazards ledger (pre-loaded from memory, builders must respect)

- `fredgraph.csv` WAF blocks browser UAs — send library UA (`FREDGRAPH_UA`).
- qledger numpy-json: parquet-derived `np.int64` in `json.dumps` → TypeError swallowed by broad
  except → silently zeroed claims (CI-only). Cast to native types before dumps (W4/W5 blast path).
- New tracked write paths (e.g. `site/news/rejected.json`) must be added to the sentinel's
  `git add` step or rebases exit 128.
- Jinja: `{% if d.key is not none %}` crashes on MISSING key — guard with `d.get('key')`.
- Worktrees: verify `git rev-parse --show-toplevel` before destructive ops; a dead worktree's
  git ops fall through to the MAIN repo. Remove worktrees when done (disk pressure).
- No translated text in `title=` attributes (`check_title_i18n` CI guard).
- theme.js/css source of truth = `templates/`, render overwrites `site/`.

## 6. Decision log

- 2026-07-04 · Earned-authority channel chosen over both "context-only forever" (Opus) and
  "route news into engines" (ChatGPT doc) — reconciles "feed real signals to Neural Web" with
  the anti-laundering constitution.
- 2026-07-04 · Event-type (what happened) replaces theme-keyword (what words appeared) as the
  primary identity axis; theme demoted to secondary facet.
- 2026-07-04 · W2 ships deterministic-only; LLM-for-borderline deferred until calibration data
  justifies the spend.
- 2026-07-04 · W1 v1 computes surprise vs revised-prior/trend/z-score; first-print vintage
  (ALFRED) honesty upgrade deferred to W4+, caveat documented in-module.
