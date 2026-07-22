# Track-Record "floating marks" — exit-semantics & contamination audit

Status: **audit memo** (Lane C, 2026-07-21). Companion to the display-honesty PR
(`fix/track-ledger-honest-marks`). Scope: map every consumer of the US/CN/HK/CA
Track-Record ledger artifacts, classify each as reading **FLOATING** (mark-to-latest,
path-dependent, retroactively mutating) or **COMMITTED** (fixed-horizon, immutable once
matured) values, and answer the operator's core worry: **do the floating marks feed any
self-improvement / adaptive loop that Prophet learns from?**

**Bottom line (verdict):** **No floating stat feeds any learning / ranking / sizing loop.**
Every floating consumer is a page/panel renderer. The Prophet learning lane is fed
exclusively by the committed fixed-horizon store (`retro_grades.parquet` →
`us_audit_scoreboard.json`), which is architecturally isolated from the floating lane.
The problem is therefore **display honesty, not data poisoning** — the fix is copy-only.

All file:line receipts below were opened and read this session.

---

## 1. What "floating" means here — the two floating artifacts

Two US artifacts mark every row to the **latest** close forever and recompute a
path-dependent `win_rate` every night. Neither has any exit discipline (no stop, no
time horizon, no indicator exit) — a name's status flips as its live price crosses ±2%.

### 1a. `site/factordata/us_track_ledger.json` — the popup ledger (PR #3116)
Producer: `scripts/grade_us_board.py::emit_ledger()` (~1374–1520), written at
`grade_us_board.py:1822–1832` via `engine.track_ledger.atomic_write()`.
- Row `e` = close on the ticker's **first-ever** buy-lane appearance across all board
  snapshots; row `l` = **latest** close; row `p` = `(l/e − 1)·100` — floating.
- Row `st` (~1465–1472): `onboard` if still on the current board, else by the CURRENT
  mark — `p > +2% → "up"`, `p < −2% → "stopped"`, else `"flat"`.
- Summary `win_rate` (~1499–1506) = `n_up / (n_up + n_stopped)` over these floating marks.

### 1b. `site/factordata/us_board_outcomes.json` — the "board exits" strip / scored chip
Producer: `scripts/grade_us_board.py::emit_outcomes()` (~1150–1370), written at
`grade_us_board.py:1803`.
- **Investigated per the task's open question ("bounded window rather than
  forever-floating?"): REFUTED.** `emit_outcomes` records a bounded `exit_date`
  (`grade_us_board.py:1251–1262`), but the return uses `last_price = float(ser.iloc[-1])`
  — the **latest bar in the closes cache**, not the price on `exit_date`
  (`grade_us_board.py:1248–1249`). So `pct_since`, `status`, and `win_rate` here float to
  the latest close forever, **same disease** as `emit_ledger` — only the `exit_date`
  *label* is bounded.
- `status` (`grade_us_board.py:1271–1276`): identical `±2%` floating thresholds →
  `running` / `stopped` / `flat`. `win_rate` = `n_running / (n_running + n_stopped)`
  (`grade_us_board.py:1305–1309`).

### The dishonesty this creates
- **Vocabulary:** `"stopped"` implies an executed stop-loss. No stop was ever executed
  — the name merely sits below its surfaced price at the latest close.
- **Path-dependence:** every row is marked-to-latest forever, so `win_rate` mutates
  retroactively every night. (Operator's COIN case: first surfaced 2026-07-02 @ 165.48;
  marked "stopped" at −3.1% on 07-20; 07-20 close 175.85 → flips to "up" the next night.)
- **Episode collapse:** a name that cycled the buy lane in two separate episodes gets a
  single row anchored to its *first* surfacing (see §4).

---

## 2. Consumer map — FLOATING vs COMMITTED

### The COMMITTED lane (the honest reference — NOT floating)
- `data/us_board_ledger/retro_grades.parquet` — retro fixed-horizon **21d excess** grades;
  matured rows immutable; one-grader law **SA-R14**. 1,537 matured rows feed Prophet.
- `engine/standout_audit.py` — module docstring lines 3, 8: *"Deterministic attribution
  over matured rows in `data/us_board_ledger/retro_grades.parquet` (committed; graded
  columns present)"* → writes `site/factordata/us_audit_scoreboard.json`
  (`_scoreboard_path`, `standout_audit.py:149–150`) and
  `data/standout_audit/us_attribution.parquet`.
- `site/factordata/us_board_track.json` — per-horizon ladder (also committed-store based).
- HK/CA/CN popup ledgers via `engine/track_ledger.from_board_ledger_grade` and
  `emit_cn_track_ledger`: matured rows carry committed 21d excess (`st='beat'/'lag'`,
  `m=true`); unmatured rows emit `x=null` — **honest null, not a fabricated mark**
  (`engine/track_ledger.py:194, 252–254`; CN docstring in `build_china_library.py`
  `emit_cn_track_ledger`). **Only US emits `st="stopped"`.**

### FLOATING consumers (all DISPLAY-ONLY)
| Consumer (file:line) | Reads | Class | What it does |
|---|---|---|---|
| `templates/_track_record_dlg.html.j2:619` (JS `fetch`) | `us_track_ledger.json` rows (`p`, `st`) | FLOATING | Popup table + status dots. **Relabeled in this PR.** |
| `templates/dashboard.html.j2:15573–15590` (`trd` dict) | `us_board_outcomes.json` summary (`win_rate`, `n_stopped`…) | FLOATING | Builds the scored chip + segment legend. **Legend relabeled in this PR.** |
| `scripts/build_track_record_page.py:370, 394–404, 462` | `us_board_outcomes.json` summary (`win_rate`) | FLOATING | Renders `us_track_record.html` hero + writes `us_track_history.json`. Hero copy already neutral ("above surfacing price") + display-only disclosure (`us_track_record.html.j2:151, 178, 187`). |
| `scripts/build_track_record_page.py:296–307` (`outcomes_rows`) | `us_board_outcomes.json` rows (`status`, `pct_since`) | FLOATING | "Recent board exits" table — dot only, no visible "stopped" text (`us_track_record.html.j2:304`). |
| `admin/prophet.py:165–180` | `us_track_history.json` `cohort_rollup.horizons.h21.win_rate` | mostly COMMITTED (history rollup) | Admin panel display. No decision downstream. |

### COMMITTED consumers (display + the learning lane)
| Consumer (file:line) | Reads | Class | Feeds a loop? |
|---|---|---|---|
| `engine/neuralweb/prophet_governor.py:254–264` | `us_audit_scoreboard.json` `win_rate` | COMMITTED | See §3 — carried into `prophet_status.json` diagnostics; **not used in any suggestion/grade decision.** |
| `engine/standout_audit.py` (whole module) | `retro_grades.parquet` | COMMITTED | Produces the scoreboard/attribution — the honest lane. |
| `scripts/build_track_record_page.py:321–351, 375` (`failure_mix`) | `data/standout_audit/us_attribution.parquet` | COMMITTED | "Why names stopped out" section (`us_track_record.html.j2:320`) — **graded** losses, not floating. Left as-is (accurate). |
| `engine/calibration_hub.py:224–299, 592–593` | `us_board_track.json`, `us_board_outcomes.json`, `us_track_history.json` | mixed (freshness/data-gap only) | Reads `as_of`/presence for staleness diagnostics; does not consume `win_rate` into any adaptation. |

**Note the survivorship tilt** (applies to both lanes, unchanged by this PR):
delisted / no-price names are silently dropped (`grade_us_board.py:1220–1231`;
`emit_ledger` survivorship note in `engine/track_ledger.py:286–288`), so any win/loss
mix is survivor-tilted. Disclosed on-page (`us_track_record.html.j2` survivorship
section) but worth keeping in mind for the promotion lane.

---

## 3. THE question — does any self-improvement loop read the floating stats?

**Answer: No.** Verified with my own reads, with positive controls on the load-bearing
negatives (Fable-mode §3.4 — a null that supports the hoped-for conclusion must be
positive-controlled):

1. **`us_track_ledger.json` is read by nothing but its writer + one test.**
   `grep -rn "us_track_ledger" --include=*.py` over `engine scripts admin tests` returns
   exactly two hits: `scripts/grade_us_board.py:104` (the writer) and
   `tests/test_track_record_dlg.py:47` (a fixture). No engine, no governor, no
   metabolism module reads it.

2. **The Prophet governor deliberately drops the floating `win_rate`.**
   `engine/neuralweb/prophet_governor.py:239–252` reads `us_board_outcomes.json` but
   extracts **only** `as_of`, `n_picks`, `status` (lines 244–248) into
   `block["board_outcomes"]` — it does **not** read `win_rate` from the floating file.
   The only `win_rate` it carries (line 263) is from `us_audit_scoreboard.json`, with the
   in-code comment *"carry if present; deterministic from committed store."* That
   scoreboard is written by `engine/standout_audit.py` from `retro_grades.parquet`
   (§2, committed). So the governor's `win_rate` is a **committed** value, not a floating
   one.

3. **`_build_suggestions()` uses no `win_rate` of any kind.**
   `grep` of `engine/neuralweb/prophet_governor.py:699–795` for
   `win_rate|board_track|outcomes` returns **zero** hits. The governor's suggestions are
   built only from SLA-freshness breaches and data-gap counts (the freshness watchlist at
   `prophet_governor.py:591–593`), never from any win-rate.

4. **No ranking / sizing / promotion consumes the floating stats.** Repo-wide, the many
   `win_rate` hits in `engine/marketing/*`, `engine/prophet_stage_*`, `engine/odds_lab.py`,
   `scripts/build_ticker_pages.py`, etc. all compute their own `win_rate` from *other*
   committed/backtest sources (`tech_confluence.json`, `data/edgar/` fires,
   per-ticker bar history) — none read `us_track_ledger.json` or the floating
   `us_board_outcomes.json` win_rate. (Consumer sweep cross-checked two ways: filename
   grep and `win_rate` grep across all `.py`.)

### Safe-to-learn-from vs display-only (the deliverable line)
- **Safe to learn from (COMMITTED, immutable once matured):** `retro_grades.parquet`,
  `us_audit_scoreboard.json` (`win_rate`, strata, coverage), `us_attribution.parquet`,
  the HK/CA/CN `beat`/`lag` matured rows, `us_board_track.json` per-horizon ladder.
- **Display-only noise (FLOATING, path-dependent — never learn from these):**
  `us_track_ledger.json` row `p` and summary `win_rate`; `us_board_outcomes.json`
  `status` / `pct_since` / `win_rate`; and anything derived from them on
  `us_track_record.html` (the hero win-rate card + "Recent board exits" dots).

---

## 4. Single-episode collapse — finding + fix sketch (NO implementation here)

**Finding.** `emit_ledger()` keys **one row per ticker** on its *first-ever* buy-lane
appearance across all board snapshots (the "first-surfaced" anchor). A name that left
and re-entered the buy lane in distinct episodes collapses to a single row anchored to
episode 1, with `e` = episode-1 entry and `l` = latest close — spanning the gap between
episodes as if it were one continuous hold. (Operator's COIN case: buy lane
07-02→07-06 and again 07-14→07-15, but the ledger shows one row anchored 07-02.)

**Fix sketch (for the separate exit-rule / episode lane — do NOT build here).** The
episode source of truth is `data/us_board_ledger/snapshots.jsonl` (each line a board
snapshot with `as_of` + buy-lane rows). Re-key rows on **(first_surfaced_of_episode,
ticker)**:
1. Walk `snapshots.jsonl` chronologically; for each ticker, detect episode boundaries
   as maximal runs of consecutive board dates on the buy lane (a gap of ≥1 board date
   with the ticker absent from the buy lane closes an episode).
2. Emit one ledger row per (episode-start-date, ticker): `e` = close at that episode's
   start, `d` = episode-start date, and — once an exit rule exists — `l`/`p`/`st` pinned
   at that episode's **exit** (last buy-lane date, or the exit rule's trigger), not the
   latest close.
3. Mature rows become immutable (like `retro_grades`), which kills the retroactive
   `win_rate` mutation at the same time as fixing episode collapse.

This is a schema + grading-math change and is explicitly **out of scope** for the
display-honesty PR; it belongs to the exit-rule adjudication lane.

---

## 5. What the companion PR changes (display-honesty only)

Wire codes (`st="stopped"`, `STATUS_VOCAB`, JSON schema) are **unchanged** — display
strings only. Surfaces re-labeled in `templates/_track_record_dlg.html.j2` (the ONE
shared popup partial for all four boards; `.j2` → nightly re-renders `site/`):
- Row status label `st="stopped"`: EN "Stopped" → **"Below entry"**; ZH "止损" →
  **"低于入场价"** (JS `T` dict; also the status filter-chip label, which still filters on
  the `stopped` wire code). `st="up"` kept as "Up"/"上涨" (already neutral — spec-permitted).
- Segment-mix legend (US `scored` block): "stopped"/"止损" → **"below entry"/"低于入场价"**;
  segbar `aria-label` "…/ stopped mix" → "…/ below-entry mix".
- Added a US-gated Tier-2 caption above the ledger table: EN *"Open marks — priced at the
  latest close; not executed exits."* / ZH *"实时标记——按最新收盘计价，并非已执行的离场。"*
  US-only because CN/HK/CA grade on committed excess (the note would misdescribe their
  matured rows). No CJK in `title=` (uses `l-en`/`l-zh` spans); Tier-2 register per
  `DESIGN_DOCTRINE.md` §Law 4/5.

Deliberately **not** changed: `templates/us_track_record.html.j2` — its hero already uses
neutral "above surfacing price" language + a display-only disclosure
(`us_track_record.html.j2:151, 178, 187`), and its "Why names stopped out" section
(`:320`) is driven by the **committed** attribution parquet (graded losses), where
"stopped out" is accurate.
