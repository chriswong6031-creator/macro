"""US post-board trajectory — what happens to Prophet US board names AFTER they leave.

RESEARCH TIER. This file measures. It changes no gate, no lane, no ranker, no surface
and no config. Nothing here is a promotion, and no verdict below licenses one.

THE QUESTION
    Names leave the US board constantly and silently. Nobody has ever graded what they
    did next. Three measured facts motivate the look:
      (1) the stage-ran cohort is the one stable positive in the program — BUY-lane rows
          whose entry_status buckets to STAGE_RAN graded 14.5% loser vs 27.6% for the
          rest of the buy lane (n=55, no half-split flip), #4547
          `label_grading_battery_results.json` §section_3_ran_lane;
      (2) departures are real and were invisible until #4554 — a marginal admission was
          dropped on one bad bar while its gate state stayed eligible, and departed
          names had no track-record row at all (`BOARD_CONTINUITY_FORENSIC_2026-08-05.md`);
      (3) the cascade is a FRESH-cross detector (FRESH_TICKS=2), so an aged-out cross is
          structurally un-readmittable, and widening that window is KILLED
          (`DNR:KILL-FRESH-TICKS-WINDOW`, #4546/#4548).
    So the open hypothesis is about ALREADY-ADMITTED names' post-departure path, not
    about re-entering anything.

KILLS CHECK (matched by RULE TEXT, cited by stable key — never by row number)
  * `DNR:KILL-PROPHET-POP-MERGE` — fences the graded-board POPULATION. This instrument
    reads published boards and writes nothing into them; the population is untouched.
  * `DNR:KILL-OUTCOME-AUDITION` — forbids per-name selection of a timing tool BY
    OUTCOME. Every cell here is a cohort defined by a label the board already stamped
    at departure. No per-name gate, rank, size or tool is chosen from any outcome.
  * The killed LEADER-PULLBACK-RESET family (`RESULTS_2026-08-03.md` §"Leader
    pullback-reset", −1.50% pooled / −2.12% per-name-first on 938 fires; referenced as
    "the §2.5 leader-family null" inside `DNR:KILL-FRESH-TICKS-WINDOW`) tested ENTERING
    leaders on dips. THIS study never enters anything: its population is names the board
    ALREADY ADMITTED, its anchor is the date they LEFT, and no cell contains a name that
    was not on the board. The two constructions share no fire.
  * `DNR:KILL-FRESH-TICKS-WINDOW` — forbids widening the admission window. Nothing here
    proposes an admission change; the freshness class is descriptive only.
  * `DNR:KILL-OFFHORIZON-VERDICTS` — verdicts only at registered horizons. The grid is
    the board's own registered ladder (`scripts/grade_us_board.HORIZONS = [5,10,21,63]`),
    plus 42 which is REPORTED AS ABSENT, never as a verdict.

FRAME REALITY vs THE COMMISSIONING BRIEF (census-first; the delta is the headline)
  * The brief pointed at `snapshots.jsonl` + `snapshots_v2.jsonl` (17 and 12 dates). The
    production grader does NOT read those alone: `scripts/grade_us_board.collect_boards`
    unions them with the git history of the published board artifact. Doing the same
    widens the membership frame from 17 board dates to 32 (2026-06-15..2026-07-31) —
    and it is the only source that carries the pre-06-30 board at all.
  * The frame still ENDS 2026-07-31. Commits exist through 08-05 but every one of them
    carries `as_of` 2026-07-31 (the collect outage; `BOARD_CONTINUITY_FORENSIC` §0
    "Was the 08-01..08-03 gap backfilled? No."). So names on the 07-31 board are
    RIGHT-CENSORED, not departed, and are reported in their own table.
  * H=42 and H=63 are STRUCTURALLY UNMEASURABLE on this frame, not merely thin. The
    widest possible forward budget is 31 sessions (earliest detectable departure
    2026-06-16 → last priced session 2026-07-31). The counterfactual the brief asks for
    ("what did holding through H=63 earn") has n=0 and is printed as such.
  * The board changed CONSTRUCTION four times inside the 32 dates (rank_by conviction →
    bottoming-alignment → confluence → us_prophet_v1; buy-lane size 120 → 33 on 06-25
    and 44 → 80 on 07-28; the gate-state block absent before 06-26; `eligible` True on
    15-50% of buy rows before 07-17 and on 100% from 07-17). Departures at those seams
    are construction, not signal, and are classed `roster_break`.

STATS GUARDS (binding on every cell)
  date-demeaned beside raw; per-name-first beside pooled; loser := excess vs SPY <
  -3pp (STATED, with medians printed so no verdict hangs on the threshold); thin cells
  print n and say thin; half-split robustness on every headline; per-sector
  concentration disclosure; per-class fire counts so an EMPTY class is visible rather
  than silently absent; and a survivor base-rate lift for every classification flag, so
  a class built on a label that every surviving name also carries is visibly
  non-informative rather than quietly persuasive.

SURVIVORSHIP (stated convention — this is where losers get deleted)
  A name whose price series stops before the horizon is NOT dropped. It is liquidated at
  its last print, kept in the cell, and counted in `n_truncated`; every headline is
  reprinted excluding those rows so the convention's effect is visible. A name with no
  resolvable price at all is counted `unpriced` and named. Dropping either silently is
  exactly how a post-departure study deletes its own losers.

FROZEN-REPLAY PIN
  REPRO_ASOF truncates BOTH the board frame and every price series, so this reproduces
  after any later nightly. Prices are pinned at 2026-07-31 rather than the freshest
  available close (2026-08-04) on purpose: only 25.8% of board tickers have a print past
  07-31, so extending the pin would silently restrict every late cell to a quarter of
  the roster. The extension is measured as a labelled sensitivity, never as the headline.

NUMPY-BOOL TRAP
  ``x is True`` on a numpy bool is ALWAYS False (memory:
  numpy-bool-is-true-deadens-a-feature-leg). Every truth test below goes through
  ``_truthy``/``==``, and every flag carries a fire count so a dead leg is visible.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

REPO = str(Path(__file__).resolve().parents[2])
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "post_board_trajectory_results.json")
os.chdir(REPO)
sys.path.insert(0, REPO)

from engine import us_board_rank as ubr                       # noqa: E402
from engine.confluence_tiers import FRESH_TICKS               # noqa: E402

# ---------------------------------------------------------------- constants --
REPRO_ASOF = "2026-07-31"       # frozen-replay pin: board frame AND every price series
PRICE_EXT_ASOF = "2026-08-04"   # sensitivity-only pin (yahoo tail; 25.8% coverage)
LOSER_PP = -3.0                 # loser := excess vs SPY < -3pp at the horizon (STATED)
H_GRID = (5, 10, 21, 42, 63)    # board's registered ladder + 42 (reported, never a verdict)
H_PRIMARY = 10
THIN_N = 20
BENCH = "SPY"
MIN_HIST = 60                   # panel columns with less than this are not a universe leg
PANEL_START = "2025-06-01"      # panel history floor: ~290 sessions before the board
                                # frame opens, so `first_valid` still separates a name
                                # that IPO'd inside the measurement window from one that
                                # merely predates the panel, at a fraction of the memory

BOARD_PATH = "site/factordata/us_standouts.json"
V2_BOARD_PATH = "site/factordata/us_standouts_v2.json"
SNAPSHOTS = "data/us_board_ledger/snapshots.jsonl"
V2_SNAPSHOTS = "data/us_board_ledger/snapshots_v2.jsonl"
LANES = ("buy", "watch", "leaders", "ran", "laggards", "laggard")
V2_LANES = ("entry_open", "setting_up")

# An era break is a CONSTRUCTION change, detected from the boards themselves rather than
# hand-listed, so a later era break is caught without editing this file.
ERA_SIZE_JUMP = 0.40    # lane row-count LEVEL change, as a fraction of the prior level
ERA_SIZE_MIN = 15       # ...and at least this many names, so churn in a 10-20 name lane
                        # is not read as a cap change (18->10->21->31 is not three eras)
ERA_SHARE_JUMP = 0.50   # level change in the share of rows carrying a readable/True gate
ERA_WINDOW = 3          # boards averaged either side; a construction change persists,
                        # composition churn reverts, and only the former should count
ERA_STEP_SHARE = 0.60   # the single day at the level shift must carry this much of it:
                        # a cap change is a STEP, a board emptying over a week is DRIFT

_GROUPS = ("breadth", "midcap_breadth", "smallcap_breadth")
_CLASS_ORDER = (
    "roster_break", "lane_move", "ran_advanced", "veto_blocked", "freshness_edge",
    "gate_ineligible", "weak_tier", "still_eligible_absent", "gate_state_absent",
)


# ------------------------------------------------------------------ helpers --
def _r(x, nd: int = 2):
    """Round, but never crash on a NaN/None/inf."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return round(f, nd) if np.isfinite(f) else None


def _truthy(v) -> bool:
    """Null-safe truth test. NEVER ``is True`` — that is always False on a numpy bool."""
    if v is None:
        return False
    if isinstance(v, float) and not np.isfinite(v):
        return False
    try:
        if pd.isna(v):
            return False
    except (TypeError, ValueError):
        pass
    return bool(v)


def _is_false(v) -> bool:
    """Explicitly stamped False (distinct from absent — absent is its own class)."""
    if v is None:
        return False
    try:
        if pd.isna(v):
            return False
    except (TypeError, ValueError):
        pass
    return bool(v) is False


def _fin_int(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if np.isfinite(f) else None


def _contiguous_runs(idxs) -> list[list[int]]:
    """[0,1,2,5,6] -> [[0,1,2],[5,6]]. Shared by the episode builder (board-date runs)
    and the era detector (candidate-date runs)."""
    idxs = sorted(int(i) for i in idxs)
    if not idxs:
        return []
    runs = [[idxs[0]]]
    for i in idxs[1:]:
        if i == runs[-1][-1] + 1:
            runs[-1].append(i)
        else:
            runs.append([i])
    return runs


def stats_block(ex_spy_pp, ex_dm_pp, tickers, *, thin_n: int = THIN_N) -> dict:
    """The house stat row (idiom copied from `label_grading_battery.stats_block`, #4547):
    pooled raw + demeaned + per-name-first, with n and a thin flag."""
    n = len(ex_spy_pp)
    if n == 0:
        return {"n": 0, "thin": True, "note": "no observations in this cell"}
    s = pd.Series(np.asarray(ex_spy_pp, dtype=float))
    d = pd.Series(np.asarray(ex_dm_pp, dtype=float))
    byname = pd.DataFrame({"t": list(tickers), "ex": s.to_numpy()}).groupby("t")["ex"].median()
    out = {
        "n": int(n),
        "names": int(byname.shape[0]),
        "loser_rate_pct": _r((s < LOSER_PP).mean() * 100, 1),
        "win_rate_pct": _r((s > 0).mean() * 100, 1),
        "median_excess_spy_pp": _r(s.median()),
        "median_excess_dm_pp": _r(d.median()),
        "per_name_first_median_pp": _r(byname.median()),
        "mean_excess_spy_pp": _r(s.mean()),
        "p25_pp": _r(s.quantile(0.25), 1),
        "p75_pp": _r(s.quantile(0.75), 1),
    }
    if n < thin_n:
        out["thin"] = True
        out["thin_note"] = f"THIN CELL — n={n} < {thin_n}; directional read only"
    return out


def half_split(dates, ex_spy_pp, ex_dm_pp, tickers) -> dict:
    """Robustness: split at the median event date and re-stat each half. A headline that
    exists in only one half is not a stable headline."""
    if len(dates) < 4:
        return {"note": "too few observations to half-split", "n": int(len(dates))}
    dser = pd.Series(pd.to_datetime(list(dates)))
    n_dates = int(dser.nunique())
    if n_dates < 2:
        return {"note": "UNRUNNABLE — all observations share a single date; a time "
                        "half-split cannot test this cohort",
                "n": int(len(dates)), "distinct_dates": n_dates}
    cut = dser.median()
    first = (dser <= cut).to_numpy()
    if first.all() or (~first).all():
        first = (dser < cut).to_numpy()
    if first.sum() == 0 or (~first).sum() == 0:
        return {"note": "UNRUNNABLE — dates too concentrated to form two non-empty halves",
                "n": int(len(dates)), "distinct_dates": n_dates}
    ex_spy_pp = np.asarray(ex_spy_pp, dtype=float)
    ex_dm_pp = np.asarray(ex_dm_pp, dtype=float)
    tk = np.asarray(list(tickers), dtype=object)
    a = stats_block(ex_spy_pp[first], ex_dm_pp[first], tk[first])
    b = stats_block(ex_spy_pp[~first], ex_dm_pp[~first], tk[~first])
    out = {"split_at": str(pd.Timestamp(cut).date()), "distinct_dates": n_dates,
           "first_half": a, "second_half": b}
    pa, pb = a.get("per_name_first_median_pp"), b.get("per_name_first_median_pp")
    if pa is not None and pb is not None:
        out["sign_flip_across_halves"] = bool((pa > 0) != (pb > 0))
        out["per_name_median_gap_pp"] = _r(abs(pa - pb))
    return out


def sector_concentration(tickers, sector_of: dict, top: int = 4) -> dict:
    """A cohort verdict carried by one sector is a sector call wearing a label's clothes."""
    secs = pd.Series([sector_of.get(str(t), "unknown") for t in tickers])
    if secs.empty:
        return {"coverage_pct": 0.0}
    vc = secs.value_counts(normalize=True) * 100
    return {
        "coverage_pct": _r(float((secs != "unknown").mean() * 100), 1),
        "top_sectors_pct": {str(k): _r(v, 1) for k, v in vc.head(top).items()},
        "max_single_sector_pct": _r(vc.max(), 1),
    }


# ------------------------------------------------------------ board history --
def _git_asof_map(path: str) -> dict:
    """{as_of -> newest sha touching the board artifact with that as_of}.

    Mirrors `scripts/grade_us_board._git_revisions` + `collect_boards`: `git log` is
    newest-first and the FIRST sha seen for an as_of wins, so a re-render on the same
    day resolves to its last published bytes. LOUD on failure — a silent [] here would
    quietly cut the frame in half (the 2026-07-26 incident recorded at
    grade_us_board.py:405-412).

    Only the first bytes of each blob are read: the artifact is ~1.7MB and `as_of` is the
    first key, so a truncated read is ~500x cheaper than inflating 524 revisions.
    """
    proc = subprocess.run(["git", "log", "--format=%H", "--", path],
                          cwd=REPO, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git log failed for {path}: {proc.stderr.strip()[:200]}")
    out: dict[str, str] = {}
    for sha in proc.stdout.split():
        p = subprocess.Popen(["git", "show", f"{sha}:{path}"], cwd=REPO,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            chunk = p.stdout.read(300)
        finally:
            p.stdout.close()
            p.wait()
        txt = chunk.decode("utf-8", "ignore")
        i = txt.find('"as_of"')
        if i < 0:
            continue
        j = txt.find('"', i + 8)
        k = txt.find('"', j + 1)
        as_of = txt[j + 1:k]
        if as_of and as_of not in out:
            out[as_of] = sha
    return out


def _git_blob(sha: str, path: str) -> dict:
    proc = subprocess.run(["git", "show", f"{sha}:{path}"], cwd=REPO,
                          capture_output=True, text=True)
    return json.loads(proc.stdout)


def _flat(as_of: str, family: str, lane: str, pos: int, r: dict) -> dict:
    """One board row, flattened to the state fields the taxonomy reads."""
    sig = r.get("signal") or {}
    es = r.get("entry_signal") or {}
    cv = r.get("conviction") or {}
    tt = cv.get("trust_tier")
    return {
        "as_of": as_of, "family": family, "lane": lane, "position": int(pos),
        "ticker": str(r.get("ticker") or ""), "sector": r.get("sector"),
        "state": r.get("state"), "urgency": r.get("urgency"), "dir": r.get("dir"),
        "align_tier": r.get("align_tier"), "alpha": r.get("alpha"),
        "entry_status": es.get("status"), "act_level": es.get("act_level"),
        "eligible": sig.get("eligible"), "tier": sig.get("tier"),
        "sig_reason": sig.get("reason"), "above200": sig.get("above200"),
        "weekly_bull": sig.get("weekly_bull"), "ticks": sig.get("ticks"),
        "tier_cascade": sig.get("tier_cascade"),
        "conv_score": cv.get("score"), "conv_band": cv.get("band"),
        "cycle_blocked": cv.get("cycle_blocked"), "rank_pctile": cv.get("rank_pctile"),
        "trust_tier": tt.get("tier") if isinstance(tt, dict) else None,
    }


def board_history() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Board rows + lane presence + provenance, over the union frame.

    Returns (rows, presence, prov). ``presence`` carries one row per
    (family, lane, as_of) for which the lane KEY existed in the artifact, even when the
    lane was empty. That distinction is load-bearing: a lane that is present-and-empty
    departed everyone in it; a lane whose key is absent (birth/retirement — `leaders`
    arrived 2026-07-28) never departed anyone.
    """
    rows: list[dict] = []
    pres: list[dict] = []
    prov: dict = {}
    for family, board_path, snap_path, lanes in (
            ("v1", BOARD_PATH, SNAPSHOTS, LANES),
            ("v2", V2_BOARD_PATH, V2_SNAPSHOTS, V2_LANES)):
        boards: dict[str, tuple[str, dict]] = {}
        # (1) snapshots first — exact bytes at build time, they take precedence
        sp = Path(REPO) / snap_path
        if sp.exists():
            for line in sp.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("as_of"):
                    boards[d["as_of"]] = ("snapshot", d)
        n_snap = len(boards)
        # (2) git history fills every as_of the snapshots do not carry
        amap = _git_asof_map(board_path)
        for as_of, sha in amap.items():
            if as_of not in boards:
                boards[as_of] = ("git", _git_blob(sha, board_path))
        prov[family] = {
            "board_artifact": board_path, "snapshot_store": snap_path,
            "as_of_from_snapshots": n_snap, "as_of_from_git_history": len(boards) - n_snap,
            "git_revisions_scanned": len(amap),
            "as_of_total": len(boards),
            "date_range": [min(boards), max(boards)] if boards else None,
        }
        for as_of, (src, d) in boards.items():
            if as_of > REPRO_ASOF:            # frozen-replay pin on the board frame
                continue
            container = (d.get("lanes") or {}) if family == "v2" else d
            for lane in lanes:
                v = container.get(lane)
                if not isinstance(v, list):
                    continue                   # key absent → lane not born / retired
                pres.append({"family": family, "lane": lane, "as_of": as_of,
                             "n": len(v), "source": src,
                             "rank_by": d.get("rank_by")})
                for i, r in enumerate(v):
                    if not isinstance(r, dict) or not r.get("ticker"):
                        continue
                    x = _flat(as_of, family, lane, i, r)
                    x["source"] = src
                    rows.append(x)
    return pd.DataFrame(rows), pd.DataFrame(pres), prov


# ------------------------------------------------------------- era breaks ----
def detect_era_breaks(rows: pd.DataFrame, presence: pd.DataFrame) -> dict:
    """{(family, lane) -> {as_of -> [trigger, ...]}} — construction seams, measured.

    A departure whose drop date is a seam is a CONSTRUCTION change, not a signal event.
    Detected, never hand-listed, so a later seam is caught without editing this file.
    """
    breaks: dict = {}
    for (family, lane), g in presence.groupby(["family", "lane"]):
        g = g.sort_values("as_of")
        sub = rows[(rows.family == family) & (rows.lane == lane)]
        seq, prof = [], []
        for _, r in g.iterrows():
            day = sub[sub.as_of == r["as_of"]]
            seq.append(r["as_of"])
            prof.append({
                # a NULL rank_by is a real, CONSTANT state on the v2 boards; comparing
                # raw NaN to raw NaN is always unequal and fired a false break on EVERY
                # v2 date until this normalisation.
                "rank_by": "" if pd.isna(r.get("rank_by")) else str(r.get("rank_by")),
                "n": float(r["n"]),
                "gate_readable": float(day["eligible"].notna().mean()) if len(day) else 0.0,
                "gate_true": float((day["eligible"] == True).mean()) if len(day) else 0.0,  # noqa: E712
            })

        def _win(i: int, key: str, back: bool) -> float:
            """Mean of ``key`` over up to ERA_WINDOW boards before / from index i."""
            lo, hi = (max(0, i - ERA_WINDOW), i) if back else (i, min(len(prof), i + ERA_WINDOW))
            vals = [prof[j][key] for j in range(lo, hi)]
            return float(np.mean(vals)) if vals else float("nan")

        trig_by_date: dict[str, list[str]] = {}

        def _add(date: str, msg: str) -> None:
            trig_by_date.setdefault(date, []).append(msg)

        # (a) rank_by — an exact, unambiguous event. Never windowed, never de-smeared.
        for i in range(1, len(seq)):
            if prof[i]["rank_by"] != prof[i - 1]["rank_by"]:
                _add(seq[i], f"rank_by {prof[i - 1]['rank_by'] or '<null>'} -> "
                             f"{prof[i]['rank_by'] or '<null>'}")

        # (b) level metrics. Two failure modes had to be closed at once:
        #   * a one-day delta test fires on ordinary churn in a 10-20 name lane
        #     (18->10->21->31 read as three separate eras), so the test is a LEVEL SHIFT
        #     over ERA_WINDOW boards either side;
        #   * a level test SMEARS — the window straddles the break, so the three dates
        #     around a single cap change all trip it (06-24/25/26/29 for one 06-25 cut).
        # So each contiguous run of candidates collapses to the day the step actually
        # landed, and that day must carry most of the shift (ERA_STEP_SHARE). A cap
        # change is a STEP; a board quietly emptying over a week is DRIFT, and drift is
        # not a construction change — misfiling it as one would move real signal
        # departures into the roster bucket and hide them.
        # KNOWN LIMITATION (pinned by test_two_cap_steps_inside_one_window_collapse_to_
        # the_first_KNOWN_LIMITATION): two genuine cap steps within ERA_WINDOW of each
        # other land in ONE candidate run, and only the first is emitted. On this frame
        # the two cap changes are 20 board dates apart and the third seam fires through
        # rank_by (exact, never collapsed), so it is inert here. A board that re-caps
        # twice in a week would need a per-step changepoint pass, not a threshold tweak.
        for key, lbl, use_rel in (("n", "lane size", True),
                                  ("gate_readable", "gate-state block appeared/vanished", False),
                                  ("gate_true", "eligible-share step", False)):
            shifts: dict[int, float] = {}
            for i in range(1, len(seq)):
                b, f = _win(i, key, True), _win(i, key, False)
                if not (np.isfinite(b) and np.isfinite(f)):
                    continue
                shift = abs(f - b)
                hit = ((shift >= ERA_SIZE_MIN and shift / max(b, 1.0) >= ERA_SIZE_JUMP)
                       if use_rel else (shift >= ERA_SHARE_JUMP))
                if hit:
                    shifts[i] = shift
            for run in _contiguous_runs(sorted(shifts)):
                best = max(run, key=lambda i: abs(prof[i][key] - prof[i - 1][key]))
                step = abs(prof[best][key] - prof[best - 1][key])
                if step < ERA_STEP_SHARE * shifts[best]:
                    continue                       # drift, not a step — not a break
                lo, hi = _win(best, key, True), _win(best, key, False)
                fmt = "{:.0f}" if key == "n" else "{:.2f}"
                _add(seq[best],
                     f"{lbl} level {fmt.format(lo)} -> {fmt.format(hi)} "
                     f"(step {fmt.format(prof[best - 1][key])} -> "
                     f"{fmt.format(prof[best][key])} on {seq[best]})")
        if trig_by_date:
            breaks[(family, lane)] = trig_by_date
    return breaks


# --------------------------------------------------------------- episodes ----
def build_episodes(rows: pd.DataFrame, presence: pd.DataFrame) -> pd.DataFrame:
    """One row per (family, lane, ticker) CONTIGUOUS RUN over the lane's own board-date
    sequence.

    The sequence is the dates on which the lane KEY existed — so a calendar gap (no board
    written at all) can never manufacture a departure, which is exactly the outage trap.
    An episode whose last board date is the lane's final date is RIGHT-CENSORED, not
    departed: there is no next board to be absent from.
    """
    seqs: dict[tuple[str, str], list[str]] = {}
    for (family, lane), g in presence.groupby(["family", "lane"]):
        seqs[(family, lane)] = sorted(g["as_of"].unique())
    out: list[dict] = []
    for (family, lane, ticker), g in rows.groupby(["family", "lane", "ticker"]):
        seq = seqs.get((family, lane), [])
        if not seq:
            continue
        pos = {d: i for i, d in enumerate(seq)}
        idxs = sorted({pos[d] for d in g["as_of"].unique() if d in pos})
        if not idxs:
            continue
        runs = _contiguous_runs(idxs)
        prev_end = None
        for ep_ix, run in enumerate(runs):
            last_i = run[-1]
            departed = last_i < len(seq) - 1
            out.append({
                "family": family, "lane": lane, "ticker": ticker,
                "episode_ix": ep_ix,
                "first_seen": seq[run[0]], "last_seen": seq[last_i],
                "board_days": len(run),
                "departed": bool(departed),
                "drop_date": seq[last_i + 1] if departed else None,
                "reentry": bool(ep_ix > 0),
                "boards_out_before_reentry": (run[0] - prev_end - 1) if prev_end is not None else None,
            })
            prev_end = last_i
    return pd.DataFrame(out)


# ------------------------------------------------------------ classification --
def classify(episodes: pd.DataFrame, rows: pd.DataFrame, breaks: dict) -> pd.DataFrame:
    """Attach the stamped state at last appearance, the non-exclusive flags, and one
    exclusive class per departure.

    Priority (documented, and the overlap matrix is printed beside it so nothing hides):
      roster_break > lane_move > ran_advanced > veto_blocked > freshness_edge >
      gate_ineligible > weak_tier > still_eligible_absent > gate_state_absent

    ``ran_advanced`` deliberately outranks the gate classes: it is the hypothesis under
    test and it reads a field that is ~100% populated from 2026-06-18 on, whereas the
    gate block is absent for the whole first era. ``gate_ineligible`` is kept DISTINCT
    from ``veto_blocked`` because before 2026-07-17 `eligible=False` was the MODAL state
    of the buy lane — calling it a veto there would be a misassignment, and a misassigned
    class is worse than an honest unknown.
    """
    ran_statuses = set(ubr._RAN_STATUSES)
    keep = ("sector", "state", "urgency", "entry_status", "eligible", "tier", "ticks",
            "tier_cascade", "cycle_blocked", "rank_pctile", "conv_score", "position",
            "sig_reason", "above200", "weekly_bull", "align_tier")
    # last-appearance state, keyed exactly; a duplicated key keeps its FIRST row (board
    # position order) rather than raising, and duplicates are counted for disclosure.
    state: dict[tuple, dict] = {}
    dup = 0
    for r in rows.to_dict("records"):
        k = (r["family"], r["lane"], r["ticker"], r["as_of"])
        if k in state:
            dup += 1
            continue
        state[k] = r
    lane_n_by = rows.groupby(["family", "lane", "as_of"]).size().to_dict()
    # who is on which lane on a given board date, per family
    by_date: dict[tuple[str, str], dict[str, set]] = {}
    for (family, as_of), g in rows.groupby(["family", "as_of"]):
        by_date[(family, as_of)] = {ln: set(x) for ln, x in
                                    g.groupby("lane")["ticker"].apply(set).items()}
    recs = []
    for ep in episodes.to_dict("records"):
        key = (ep["family"], ep["lane"], ep["ticker"], ep["last_seen"])
        st = state.get(key)
        if st is None:
            continue
        rec = dict(ep)
        rec["_dup_board_keys"] = dup
        for c in keep:
            rec[f"last_{c}"] = st.get(c)
        lane_n = int(lane_n_by.get((ep["family"], ep["lane"], ep["last_seen"]), 0))
        rec["last_lane_n"] = lane_n
        pos = _fin_int(st.get("position"))
        rec["last_rank_frac"] = (pos / lane_n) if (lane_n and pos is not None) else None

        ticks = _fin_int(st.get("ticks"))
        rec["flag_ran"] = bool(str(st.get("entry_status") or "") in ran_statuses)
        rec["flag_veto"] = _truthy(st.get("cycle_blocked"))
        rec["flag_ineligible"] = _is_false(st.get("eligible"))
        rec["flag_gate_absent"] = bool(pd.isna(st.get("eligible")) or st.get("eligible") is None)
        rec["flag_fresh_edge"] = bool(ticks is not None and ticks >= FRESH_TICKS
                                      and not rec["flag_gate_absent"])
        rec["flag_weak_tier"] = bool(str(st.get("tier_cascade") or "") in ("T3", "T4"))
        rec["flag_bottom_quartile"] = bool(rec["last_rank_frac"] is not None
                                           and rec["last_rank_frac"] >= 0.75)
        drop = ep["drop_date"]
        if ep["departed"] and drop:
            lanes_now = by_date.get((ep["family"], drop), {})
            dest = [ln for ln, s in lanes_now.items() if ep["ticker"] in s and ln != ep["lane"]]
            rec["flag_lane_move"] = bool(dest)
            rec["move_to"] = "|".join(sorted(dest)) if dest else None
            rec["flag_era_break"] = bool(drop in breaks.get((ep["family"], ep["lane"]), {}))
            rec["era_break_trigger"] = "; ".join(
                breaks.get((ep["family"], ep["lane"]), {}).get(drop, [])) or None
            rec["flag_still_eligible"] = bool(
                _truthy(st.get("eligible")) and not rec["flag_veto"]
                and (ticks is None or ticks < FRESH_TICKS))
            if rec["flag_era_break"]:
                cls = "roster_break"
            elif rec["flag_lane_move"]:
                cls = "lane_move"
            elif rec["flag_ran"]:
                cls = "ran_advanced"
            elif rec["flag_veto"]:
                cls = "veto_blocked"
            elif rec["flag_fresh_edge"]:
                cls = "freshness_edge"
            elif rec["flag_ineligible"]:
                cls = "gate_ineligible"
            elif rec["flag_weak_tier"]:
                cls = "weak_tier"
            elif rec["flag_still_eligible"]:
                cls = "still_eligible_absent"
            else:
                cls = "gate_state_absent"
            rec["dep_class"] = cls
        else:
            rec["flag_lane_move"] = False
            rec["move_to"] = None
            rec["flag_era_break"] = False
            rec["era_break_trigger"] = None
            rec["flag_still_eligible"] = bool(
                _truthy(st.get("eligible")) and not rec["flag_veto"]
                and (ticks is None or ticks < FRESH_TICKS))
            rec["dep_class"] = "censored_frame_end"
        recs.append(rec)
    return pd.DataFrame(recs)


def flag_lift(rows: pd.DataFrame, dep: pd.DataFrame) -> dict:
    """P(flag | departed) vs P(flag | stayed) on the SAME (family, lane, board-date)
    pairs. A class whose flag is just as common among survivors carries no information
    about departure — printing the lift is what makes that visible."""
    ran_statuses = set(ubr._RAN_STATUSES)
    d = dep[dep.departed == True]                                   # noqa: E712
    if d.empty:
        return {"note": "no departures"}
    pairs = set(zip(d["family"], d["lane"], d["last_seen"]))
    dep_keys = set(zip(d["family"], d["lane"], d["ticker"], d["last_seen"]))
    recs = rows.to_dict("records")
    stay = [r for r in recs
            if (r["family"], r["lane"], r["as_of"]) in pairs
            and (r["family"], r["lane"], r["ticker"], r["as_of"]) not in dep_keys]
    left = []
    for r in d.to_dict("records"):
        x = {k[len("last_"):] if k.startswith("last_") else k: v for k, v in r.items()}
        x["as_of"] = r["last_seen"]        # the board the departing name was last ON
        left.append(x)
    out: dict = {
        "basis": "same (family, lane, board-date) pairs on both sides — a flag that is "
                 "just as common among the names that STAYED carries no information "
                 "about departure, whatever its cohort's outcome looks like",
        "n_departed": int(len(left)), "n_stayed_same_boards": int(len(stay))}
    if not stay:
        return out

    def _rate(frame, fn):
        vals = [bool(fn(r)) for r in frame]
        return _r(100.0 * float(np.mean(vals)), 1) if vals else None

    # rank displacement is the obvious NON-stamped explanation, so it is tested beside
    # the stamped ones: a fixed-cap lane sheds its bottom whatever its state says.
    lane_n_by = rows.groupby(["family", "lane", "as_of"]).size().to_dict()

    def _bottom_q(r) -> bool:
        n = lane_n_by.get((r.get("family"), r.get("lane"), r.get("as_of")), 0)
        p = _fin_int(r.get("position"))
        return bool(n and p is not None and (p / n) >= 0.75)

    tests = {
        "ran_status": lambda r: str(r.get("entry_status") or "") in ran_statuses,
        "cycle_blocked": lambda r: _truthy(r.get("cycle_blocked")),
        "eligible_false": lambda r: _is_false(r.get("eligible")),
        "ticks_ge_fresh": lambda r: (_fin_int(r.get("ticks")) is not None
                                     and _fin_int(r.get("ticks")) >= FRESH_TICKS),
        "tier_cascade_T3_T4": lambda r: str(r.get("tier_cascade") or "") in ("T3", "T4"),
        "bottom_quartile_of_lane": _bottom_q,
    }
    for name, fn in tests.items():
        pdep, pstay = _rate(left, fn), _rate(stay, fn)
        out[name] = {"departed_pct": pdep, "stayed_pct": pstay,
                     "lift_pp": _r(pdep - pstay, 1)
                     if (pdep is not None and pstay is not None) else None}
    return out


# ----------------------------------------------------------------- prices ----
def _file_close(path: str, asof: str, start: str) -> pd.Series | None:
    if not os.path.exists(path):
        return None
    try:
        d = pd.read_parquet(path)
    except (OSError, ValueError):
        return None
    col = next((c for c in ("close", "close_price") if c in d.columns), None)
    if col is None:
        return None
    s = d[col].dropna()
    s.index = pd.to_datetime(s.index)
    s = s[(s.index <= pd.Timestamp(asof)) & (s.index >= pd.Timestamp(start))]
    return s if not s.empty else None


def price_panel(tickers: list[str], asof: str = REPRO_ASOF) -> tuple[pd.DataFrame, dict]:
    """Wide close panel on the SPY session calendar, pinned at ``asof``.

    ADJUSTMENT BASIS — found by hand-check, not assumed. The breadth closes caches are
    FORWARD-ACCRUING: each session's close is written as-of and never retro-adjusted.
    `data/baskets/ohlcv` and `data/yahoo` carry BACK-ADJUSTED history. Measured at
    2026-06-22: CFG reads 67.9900 in the cache vs 67.5514 in baskets, ALLY 45.5700 vs
    45.2556 — while both agree to the cent at 2026-07-07 (after the ex-div), and every
    name with no ex-div in the window agrees exactly across all four sources (ALB, CEG,
    and the payers JPM and KO). So a cache-priced name books its own dividend as a LOSS.
    SPY is only available adjusted, so a cache-primary panel would put a dividend-shaped
    bias into every excess-vs-SPY number in this file — small (~0.06pp expected at H=10)
    but the same order as the deltas being reported.

    The ladder is therefore ADJUSTED-FIRST, so the name leg and the benchmark leg share
    one basis:  data/baskets/ohlcv -> data/yahoo -> data/stocks -> closes caches.
    The count of names that still land on the unadjusted cache is printed, not hidden.
    Coverage still comes first for the DEPARTED names specifically — that is the fix
    `BOARD_CONTINUITY_FORENSIC` §1 shipped for the VALE class, and dropping an unpriced
    departure would delete exactly the names this study exists to find.
    """
    prov = {"asof": asof, "panel_start": PANEL_START,
            "resolved_from": {"baskets_ohlcv": 0, "yahoo": 0, "data_stocks": 0,
                              "closes_cache_UNADJUSTED": 0, "unresolved": 0},
            "unresolved_tickers": []}
    cols: dict[str, pd.Series] = {}
    # (1) the broad adjusted panel — every basket name, so the universe-median leg is on
    #     the same basis as the cohort leg
    for p in sorted(Path("data/baskets/ohlcv").glob("*.parquet")):
        s = _file_close(str(p), asof, PANEL_START)
        if s is not None:
            cols[p.stem] = s
    prov["baskets_panel_names"] = len(cols)
    # (2) every board ticker the basket panel misses, adjusted sources first
    caches = None
    for t in map(str, tickers):
        if t in cols:
            prov["resolved_from"]["baskets_ohlcv"] += 1
            continue
        s = _file_close(f"data/yahoo/{t}.parquet", asof, PANEL_START)
        src = "yahoo"
        if s is None:
            s = _file_close(f"data/stocks/{t}.parquet", asof, PANEL_START)
            src = "data_stocks"
        if s is None:
            if caches is None:
                caches = []
                for g in _GROUPS:
                    c = pd.read_parquet(f"data/{g}/_closes_cache.parquet")
                    c.index = pd.to_datetime(c.index)
                    caches.append(c[(c.index <= pd.Timestamp(asof))
                                    & (c.index >= pd.Timestamp(PANEL_START))])
            for c in caches:
                if t in c.columns:
                    cc = c[t].dropna()
                    if not cc.empty:
                        s, src = cc, "closes_cache_UNADJUSTED"
                        break
        if s is None:
            prov["resolved_from"]["unresolved"] += 1
            prov["unresolved_tickers"].append(t)
        else:
            prov["resolved_from"][src] += 1
            cols[t] = s
    wide = pd.DataFrame(cols).sort_index()
    prov["panel_names"] = int(wide.shape[1])
    prov["panel_sessions"] = int(wide.shape[0])
    prov["panel_range"] = [str(wide.index.min().date()), str(wide.index.max().date())]
    prov["board_tickers_on_unadjusted_basis"] = prov["resolved_from"]["closes_cache_UNADJUSTED"]
    return wide, prov


class Panel:
    """Forward-return machinery on one frozen price panel."""

    def __init__(self, px: pd.DataFrame, asof: str, bench: pd.Series | None = None):
        """``bench`` is injectable so the truncation/delisting path is testable without
        repo data; production leaves it None and the SPY store supplies the calendar."""
        self.asof = asof
        if bench is None:
            for path in (f"data/yahoo/{BENCH}.parquet", f"data/baskets/ohlcv/{BENCH}.parquet"):
                if not os.path.exists(path):
                    continue
                d = pd.read_parquet(path)
                col = next((c for c in ("close", "close_price") if c in d.columns), None)
                if col is None:
                    continue
                s = d[col].dropna()
                s.index = pd.to_datetime(s.index)
                bench = s[(s.index <= pd.Timestamp(asof))
                          & (s.index >= pd.Timestamp(PANEL_START))]
                break
        if bench is None or bench.empty:
            raise RuntimeError(f"no {BENCH} series available for the benchmark leg")
        bench = bench.copy()
        bench.index = pd.to_datetime(bench.index)
        self.sess = pd.DatetimeIndex(sorted(set(bench.index) | set(px.index)))
        self.sess = self.sess[self.sess <= pd.Timestamp(asof)]
        self.px = px.reindex(self.sess)
        self.first_valid = self.px.apply(lambda c: c.first_valid_index())
        self.last_valid = self.px.apply(lambda c: c.last_valid_index())
        self.ff = self.px.ffill()
        self.bench = bench.reindex(self.sess).ffill()
        self.pos = {d: i for i, d in enumerate(self.sess)}
        # universe median forward return per (date, H), over PRICED, NON-TRUNCATED cells
        self._univ: dict[int, pd.Series] = {}
        deep = self.px.notna().sum() >= MIN_HIST
        self._univ_cols = [c for c in self.px.columns if bool(deep.get(c, False))]

    def budget(self, date: str) -> int:
        i = self.pos.get(pd.Timestamp(date))
        if i is None:
            i = int(self.sess.searchsorted(pd.Timestamp(date)))
            if i >= len(self.sess):
                return -1
        return len(self.sess) - 1 - i

    def _anchor_pos(self, date: str):
        t = pd.Timestamp(date)
        i = self.pos.get(t)
        if i is not None:
            return i
        j = int(self.sess.searchsorted(t))
        return j if j < len(self.sess) else None

    def univ_median(self, h: int) -> pd.Series:
        """Median forward return over the panel on each anchor date.

        Only PRICED, NON-TRUNCATED, MATURE cells count: a name that had not started
        printing, or that stopped printing before the horizon, must not drag the
        market-neutral denominator, and an immature tail must not silently shrink it.
        """
        if h not in self._univ:
            cols = self._univ_cols
            sub = self.ff[cols]
            fwd = (sub.shift(-h) / sub - 1.0).to_numpy()
            anchor = self.sess.to_numpy().astype("datetime64[ns]")[:, None]
            horizon = np.concatenate([anchor[h:], np.full((h, 1), np.datetime64("NaT"))])
            lv = pd.to_datetime(self.last_valid[cols]).to_numpy().astype("datetime64[ns]")[None, :]
            fv = pd.to_datetime(self.first_valid[cols]).to_numpy().astype("datetime64[ns]")[None, :]
            ok = (~np.isnat(horizon)) & (~np.isnat(lv)) & (~np.isnat(fv))
            ok &= (horizon <= lv) & (anchor >= fv)
            with warnings.catch_warnings():        # an all-immature tail row is a NaN
                warnings.simplefilter("ignore", RuntimeWarning)
                med = np.nanmedian(np.where(ok, fwd, np.nan), axis=1)
            self._univ[h] = pd.Series(med, index=self.sess)
            self._univ_n = getattr(self, "_univ_n", {})
            self._univ_n[h] = pd.Series(ok.sum(axis=1), index=self.sess)
        return self._univ[h]

    def excess(self, ticker: str, date: str, h: int) -> dict | None:
        """Forward excess vs SPY and vs the same-day universe median, from ``date``.

        Returns None when the horizon is IMMATURE on this frame (a budget fact, not a
        data fact). Truncation (the name stops printing) is KEPT and flagged.
        """
        t = str(ticker)
        if t not in self.ff.columns:
            return {"status": "unpriced", "reason": "ticker not resolvable on the panel"}
        i = self._anchor_pos(date)
        if i is None:
            return {"status": "unpriced", "reason": "anchor date beyond the frame"}
        if i + h > len(self.sess) - 1:
            return None                                    # immature — frame budget
        d0, d1 = self.sess[i], self.sess[i + h]
        fv, lv = self.first_valid.get(t), self.last_valid.get(t)
        if fv is None or pd.isna(fv) or d0 < fv:
            return {"status": "unpriced", "reason": "no print at or before the anchor"}
        p0, p1 = self.ff[t].iloc[i], self.ff[t].iloc[i + h]
        if not np.isfinite(p0) or not np.isfinite(p1) or p0 <= 0:
            return {"status": "unpriced", "reason": "non-finite price at anchor/horizon"}
        truncated = bool(lv is not None and not pd.isna(lv) and lv < d1)
        b0, b1 = self.bench.iloc[i], self.bench.iloc[i + h]
        ret = float(p1 / p0 - 1.0)
        bret = float(b1 / b0 - 1.0)
        um = self.univ_median(h).iloc[i]
        return {
            "status": "ok",
            "ret_pp": ret * 100.0,
            "excess_spy_pp": (ret - bret) * 100.0,
            "excess_univmed_pp": (ret - float(um)) * 100.0 if np.isfinite(um) else None,
            "truncated": truncated,
            "sessions_priced": int(min(h, self.sess.searchsorted(lv) - i)) if truncated else int(h),
        }


# ------------------------------------------------------------------ grading --
def grade(dep: pd.DataFrame, panel: Panel, sector_of: dict) -> dict:
    """Per-departure outcomes at every horizon, from BOTH anchors, with the maturity and
    survivorship census that makes an empty cell legible."""
    recs: list[dict] = []
    census: dict = {}
    for h in H_GRID:
        n_mat = n_imm = n_unpriced = n_trunc = 0
        for _, r in dep.iterrows():
            if not bool(r["departed"]):
                continue
            drop = r["drop_date"]
            res = panel.excess(r["ticker"], drop, h)
            if res is None:
                n_imm += 1
                continue
            if res.get("status") != "ok":
                n_unpriced += 1
                recs.append({"h": h, "anchor": "drop", "ticker": r["ticker"],
                             "date": drop, "dep_class": r["dep_class"],
                             "status": res.get("status"), "reason": res.get("reason")})
                continue
            n_mat += 1
            n_trunc += int(bool(res["truncated"]))
            adm = panel.excess(r["ticker"], r["first_seen"], h)
            recs.append({
                "h": h, "anchor": "drop", "ticker": r["ticker"], "date": drop,
                "family": r["family"], "lane": r["lane"], "dep_class": r["dep_class"],
                "move_to": r.get("move_to"), "status": "ok",
                "excess_spy_pp": res["excess_spy_pp"],
                "excess_univmed_pp": res["excess_univmed_pp"],
                "truncated": bool(res["truncated"]),
                "board_days": int(r["board_days"]),
                "first_seen": r["first_seen"], "last_seen": r["last_seen"],
                "adm_excess_spy_pp": (adm or {}).get("excess_spy_pp")
                if (adm or {}).get("status") == "ok" else None,
            })
        census[f"H{h}"] = {
            "matured": n_mat, "immature_frame_budget": n_imm,
            "unpriced": n_unpriced, "truncated_kept": n_trunc,
        }
    df = pd.DataFrame(recs)
    out: dict = {"maturity_census": census}
    if df.empty or "excess_spy_pp" not in df.columns:
        out["note"] = "no matured, priced departures at any horizon on this frame"
        return out
    ok = df[df.status == "ok"].copy()
    ok["date"] = pd.to_datetime(ok["date"])
    # `truncated` arrives as object dtype (the unpriced rows carry no value), and `~` on
    # an object column is a bitwise-not on ints, not a boolean negation.
    ok["truncated"] = ok["truncated"].fillna(False).astype(bool)
    # date-demeaned within the drop-date cohort (the house market-neutral column)
    ok["ex_dm"] = ok["excess_spy_pp"] - ok.groupby(["h", "date"])["excess_spy_pp"].transform("mean")
    out["per_horizon"] = {}
    for h in H_GRID:
        g = ok[ok.h == h]
        if g.empty:
            out["per_horizon"][f"H{h}"] = {
                "n": 0,
                "note": ("STRUCTURALLY ABSENT on this frame — every departure is immature "
                         f"at H={h}; see maturity_census and frame_budget"),
            }
            continue
        blk = {
            "all_departures": stats_block(g["excess_spy_pp"], g["ex_dm"], g["ticker"]),
            "sector_mix": sector_concentration(g["ticker"].tolist(), sector_of),
            "half_split": half_split(g["date"], g["excess_spy_pp"], g["ex_dm"], g["ticker"]),
            "median_excess_univmed_pp": _r(g["excess_univmed_pp"].median()),
            "n_truncated": int(g["truncated"].sum()),
            "ex_truncated": stats_block(g.loc[~g.truncated, "excess_spy_pp"],
                                        g.loc[~g.truncated, "ex_dm"],
                                        g.loc[~g.truncated, "ticker"]),
            "by_class": {},
        }
        for cls in _CLASS_ORDER:
            c = g[g.dep_class == cls]
            if c.empty:
                blk["by_class"][cls] = {"n": 0, "fire_count": 0,
                                        "note": "EMPTY CLASS — no departure of this kind "
                                                "matured at this horizon"}
                continue
            rest = g[g.dep_class != cls]
            cb = stats_block(c["excess_spy_pp"], c["ex_dm"], c["ticker"])
            cb["fire_count"] = int(len(c))
            cb["median_excess_univmed_pp"] = _r(c["excess_univmed_pp"].median())
            cb["n_truncated"] = int(c["truncated"].sum())
            nd = int(c["date"].nunique())
            cb["distinct_drop_dates"] = nd
            if nd <= 2:
                cb["demean_degenerate"] = (
                    f"the whole class sits on {nd} drop date(s) — the date-demeaned "
                    "column is a within-cohort deviation, NOT a cross-date control. "
                    "Read median_excess_univmed_pp (vs the same-day universe median) "
                    "and treat the raw column as carrying that day's market move.")
            cb["sector_mix"] = sector_concentration(c["ticker"].tolist(), sector_of)
            cb["half_split"] = half_split(c["date"], c["excess_spy_pp"], c["ex_dm"], c["ticker"])
            cb["on_board_excess_spy_pp_median"] = _r(
                pd.to_numeric(c["adm_excess_spy_pp"], errors="coerce").median())
            cb["vs_rest_of_departures"] = {
                "rest": stats_block(rest["excess_spy_pp"], rest["ex_dm"], rest["ticker"]),
                "delta_per_name_median_pp": _r(
                    (cb.get("per_name_first_median_pp") or 0)
                    - (stats_block(rest["excess_spy_pp"], rest["ex_dm"],
                                   rest["ticker"]).get("per_name_first_median_pp") or 0)),
            }
            if cls == "lane_move":
                cb["by_destination"] = {
                    str(dest): stats_block(x["excess_spy_pp"], x["ex_dm"], x["ticker"])
                    for dest, x in c.groupby(c["move_to"].fillna("<none>"))}
            blk["by_class"][cls] = cb
        out["per_horizon"][f"H{h}"] = blk
    return out


def stayed_contrast(dep: pd.DataFrame, rows: pd.DataFrame, presence: pd.DataFrame,
                    panel: Panel, sector_of: dict) -> dict:
    """The counterfactual that actually matches: on the SAME board date, what did the
    names the board KEPT earn, against what the names it DROPPED earned?

    SPY and the universe median answer "did the departed names beat the market". Neither
    answers "did the board drop its better names", because both denominators contain
    thousands of names the board never considered. The matched contrast holds the board's
    own population and its own decision date fixed: on board date d, the kept cohort is
    the names present on both d-1 and d; the dropped cohort is the names on d-1 and not
    on d; both are anchored at d. The delta IS the board's selection decision, priced.
    """
    seqs: dict[tuple[str, str], list[str]] = {}
    for (family, lane), g in presence.groupby(["family", "lane"]):
        seqs[(family, lane)] = sorted(g["as_of"].unique())
    on: dict[tuple[str, str, str], set] = {
        (f, ln, d): set(x) for (f, ln, d), x in
        rows.groupby(["family", "lane", "as_of"])["ticker"].apply(set).items()}
    drop_dates = {(r["family"], r["lane"], r["drop_date"])
                  for r in dep[dep.departed == True].to_dict("records")}    # noqa: E712
    out: dict = {"method": (
        "on board date d: KEPT = names present on both d-1 and d; DROPPED = names on d-1 "
        "and not on d; both anchored at d. SPY and the universe median answer 'did the "
        "departed names beat the market' — neither answers 'did the board drop its better "
        "names', because both denominators contain thousands of names the board never "
        "considered. This one holds the board's own population and decision date fixed.")}
    for h in H_GRID:
        kept: list[dict] = []
        for (family, lane, d) in sorted(drop_dates):
            seq = seqs.get((family, lane), [])
            if d not in seq:
                continue
            i = seq.index(d)
            if i == 0:
                continue
            prev = seq[i - 1]
            held = on.get((family, lane, d), set()) & on.get((family, lane, prev), set())
            for t in sorted(held):
                res = panel.excess(t, d, h)
                if res is None or res.get("status") != "ok":
                    continue
                kept.append({"ticker": t, "date": d, "family": family, "lane": lane,
                             "excess_spy_pp": res["excess_spy_pp"],
                             "excess_univmed_pp": res["excess_univmed_pp"]})
        if not kept:
            out[f"H{h}"] = {"n": 0, "note": "no kept-cohort observations matured at this "
                                            "horizon (frame budget)"}
            continue
        k = pd.DataFrame(kept)
        k["date"] = pd.to_datetime(k["date"])
        k["ex_dm"] = k["excess_spy_pp"] - k.groupby("date")["excess_spy_pp"].transform("mean")
        blk = stats_block(k["excess_spy_pp"], k["ex_dm"], k["ticker"])
        blk["median_excess_univmed_pp"] = _r(k["excess_univmed_pp"].median())
        blk["sector_mix"] = sector_concentration(k["ticker"].tolist(), sector_of)
        blk["half_split"] = half_split(k["date"], k["excess_spy_pp"], k["ex_dm"], k["ticker"])
        out[f"H{h}"] = blk
    return out


# -------------------------------------------------------------------- main ----
def main() -> dict:
    rows, presence, prov = board_history()
    breaks = detect_era_breaks(rows, presence)
    episodes = build_episodes(rows, presence)
    dep = classify(episodes, rows, breaks)

    sector_of = (rows.dropna(subset=["ticker", "sector"])
                     .drop_duplicates("ticker").set_index("ticker")["sector"].to_dict())
    sector_of = {str(k): str(v) for k, v in sector_of.items()}

    tickers = sorted(set(rows["ticker"].astype(str)))
    px, pxprov = price_panel(tickers)
    panel = Panel(px, REPRO_ASOF)

    lane_seq = {f"{f}:{ln}": sorted(g["as_of"].unique().tolist())
                for (f, ln), g in presence.groupby(["family", "lane"])}
    budget = {d: panel.budget(d) for d in sorted(rows["as_of"].unique())}

    res: dict = {
        "instrument": "research/prophet_us_audit/post_board_trajectory.py",
        "tier": "RESEARCH — measurement only. No gate, lane, ranker, surface or config "
                "changes from this file. No promotion is implied by any number below.",
        "repro_asof": REPRO_ASOF,
        "loser_def_pp": LOSER_PP,
        "horizons": list(H_GRID),
        "fresh_ticks": int(FRESH_TICKS),
        "ran_statuses": sorted(ubr._RAN_STATUSES),
        "kills_check": {
            "DNR:KILL-PROPHET-POP-MERGE": "board population read-only; nothing written",
            "DNR:KILL-OUTCOME-AUDITION": "cohorts are board-stamped labels, not "
                                         "outcome-selected per-name tools",
            "leader_pullback_reset_family": "distinct construction — that family ENTERED "
                                            "leaders on dips (RESULTS_2026-08-03.md, "
                                            "-1.50% pooled); this study never enters, it "
                                            "grades already-admitted names from their "
                                            "departure date",
            "DNR:KILL-FRESH-TICKS-WINDOW": "no admission change proposed; the freshness "
                                           "class is descriptive",
            "DNR:KILL-OFFHORIZON-VERDICTS": "grid is the board's registered ladder "
                                            "[5,10,21,63]; H=42 is reported as absent, "
                                            "never as a verdict",
        },
        "provenance": {"boards": prov, "prices": pxprov,
                       "lane_date_sequences": lane_seq},
        "frame_budget": {
            "note": "forward SESSIONS available from each board date at the frozen price "
                    "pin. H=42 and H=63 exceed the widest budget, so they are absent by "
                    "arithmetic, not by data quality.",
            "max_forward_sessions": int(max(budget.values())) if budget else None,
            "per_board_date": {k: int(v) for k, v in budget.items()},
        },
        "era_breaks": {f"{f}:{ln}": {d: t for d, t in sorted(v.items())}
                       for (f, ln), v in sorted(breaks.items())},
        "era_break_method": {
            "rank_by": "exact dated event, never windowed or collapsed",
            "level_metrics": (f"level shift over {ERA_WINDOW} boards either side; "
                              f"size needs >={ERA_SIZE_MIN} names AND "
                              f">={ERA_SIZE_JUMP:.0%}, share needs >={ERA_SHARE_JUMP:.2f}; "
                              f"each contiguous candidate run collapses to the day the "
                              f"step landed, which must carry >={ERA_STEP_SHARE:.0%} of "
                              f"the shift (a cap change is a STEP, a board emptying over "
                              f"a week is DRIFT)"),
            "KNOWN_LIMITATION": (
                "two genuine cap steps within "
                f"{ERA_WINDOW} boards of each other collapse to the FIRST one; the second "
                "is folded in silently. Inert on this frame (the two cap changes are 20 "
                "board dates apart and the third seam fires through rank_by), pinned by "
                "test_two_cap_steps_inside_one_window_collapse_to_the_first_KNOWN_"
                "LIMITATION, and it would need a per-step changepoint pass to fix."),
        },
    }

    # ---- census ---------------------------------------------------------------
    v1buy = rows[(rows.family == "v1") & (rows.lane == "buy")]
    res["census"] = {
        "board_rows": int(len(rows)),
        "board_dates": int(rows["as_of"].nunique()),
        "date_range": [str(rows["as_of"].min()), str(rows["as_of"].max())],
        "rows_by_family_lane": {f"{f}:{ln}": int(n) for (f, ln), n in
                                rows.groupby(["family", "lane"]).size().items()},
        "distinct_tickers": int(rows["ticker"].nunique()),
        "episodes": int(len(episodes)),
        "episodes_by_lane": {f"{f}:{ln}": int(n) for (f, ln), n in
                             episodes.groupby(["family", "lane"]).size().items()},
        "departures": int(dep["departed"].sum()),
        "censored_at_frame_end": int((~dep["departed"]).sum()),
        "reentries": int(dep["reentry"].sum()),
        "buy_lane_state_availability": {
            "entry_status_null_pct": _r(100.0 * v1buy["entry_status"].isna().mean(), 1),
            "eligible_null_pct": _r(100.0 * v1buy["eligible"].isna().mean(), 1),
            "ticks_null_pct": _r(100.0 * v1buy["ticks"].isna().mean(), 1),
            "tier_cascade_null_pct": _r(100.0 * v1buy["tier_cascade"].isna().mean(), 1),
            "note": "the gate-state block is absent for the ENTIRE first era "
                    "(2026-06-15..06-25); entry_status is absent only 06-15..06-17.",
        },
        "class_census": {c: int((dep["dep_class"] == c).sum()) for c in
                         list(_CLASS_ORDER) + ["censored_frame_end"]},
        "class_census_buy_only": {
            c: int(((dep["dep_class"] == c) & (dep.lane == "buy")).sum())
            for c in list(_CLASS_ORDER) + ["censored_frame_end"]},
        "flag_overlap_departures": {
            f: int(dep.loc[dep.departed == True, f].sum())               # noqa: E712
            for f in ("flag_era_break", "flag_lane_move", "flag_ran", "flag_veto",
                      "flag_ineligible", "flag_fresh_edge", "flag_weak_tier",
                      "flag_gate_absent", "flag_still_eligible", "flag_bottom_quartile")},
        "lane_move_destinations": {
            str(k): int(v) for k, v in
            dep.loc[dep.flag_lane_move == True, "move_to"].value_counts().items()},  # noqa: E712
        "reentry_gap_boards": {
            "median": _r(pd.to_numeric(dep["boards_out_before_reentry"],
                                       errors="coerce").median(), 1),
            "n": int(pd.to_numeric(dep["boards_out_before_reentry"],
                                   errors="coerce").notna().sum())},
    }
    res["flag_lift_vs_survivors"] = flag_lift(rows, dep)

    # ---- grading --------------------------------------------------------------
    res["all_lanes"] = grade(dep, panel, sector_of)
    res["buy_lane"] = grade(dep[dep.lane == "buy"], panel, sector_of)

    # ---- the matched counterfactual: dropped vs KEPT on the same board date ----
    buy_rows, buy_pres = rows[rows.lane == "buy"], presence[presence.lane == "buy"]
    buy_dep = dep[dep.lane == "buy"]

    def _compare(dsub: pd.DataFrame, label: str) -> dict:
        kept = stayed_contrast(dsub, buy_rows, buy_pres, panel, sector_of)
        dropped = grade(dsub, panel, sector_of)
        blk: dict = {"scope": label, "kept_cohort": kept,
                     "dropped_cohort": {f"H{h}": dropped.get("per_horizon", {})
                                        .get(f"H{h}", {}).get("all_departures", {"n": 0})
                                        for h in H_GRID},
                     "delta_dropped_minus_kept": {},
                     "overlap_caveat": (
                         "the KEPT cohort re-observes a name on every board date it "
                         "survived, so its rows are heavily overlapping and its n is not "
                         "an independent sample size; per_name_first_median_pp is the "
                         "column to read against the dropped side, and the loser-rate "
                         "gap is reported in pp, not tested.")}
        for h in H_GRID:
            d_blk = blk["dropped_cohort"].get(f"H{h}")
            k_blk = kept.get(f"H{h}")
            if not d_blk or not k_blk or not d_blk.get("n") or not k_blk.get("n"):
                blk["delta_dropped_minus_kept"][f"H{h}"] = {
                    "note": "not computable at this horizon (frame budget)"}
                continue
            blk["delta_dropped_minus_kept"][f"H{h}"] = {
                "median_excess_spy_pp": _r((d_blk["median_excess_spy_pp"] or 0)
                                           - (k_blk["median_excess_spy_pp"] or 0)),
                "per_name_first_median_pp": _r((d_blk["per_name_first_median_pp"] or 0)
                                               - (k_blk["per_name_first_median_pp"] or 0)),
                "loser_rate_pp": _r((d_blk["loser_rate_pct"] or 0)
                                    - (k_blk["loser_rate_pct"] or 0), 1),
                "n_dropped": d_blk["n"], "n_kept": k_blk["n"],
                "read": ("POSITIVE = the dropped names went on to do BETTER than the ones "
                         "the board kept, i.e. the drop cost something. NEGATIVE = the "
                         "board kept the better names."),
            }
        return blk

    res["kept_vs_dropped_buy_lane"] = _compare(buy_dep, "all buy-lane departures")
    # The roster cuts land on 4 dates and dominate the dropped side; if the whole delta
    # lives there it is a construction artefact, not the board's daily decision.
    res["kept_vs_dropped_excl_roster_breaks"] = _compare(
        buy_dep[buy_dep.dep_class != "roster_break"],
        "buy-lane departures EXCLUDING construction-seam dates (the primary read)")

    # ---- the motivating hypothesis, in one place ------------------------------
    res["ran_cohort_focus"] = {
        "hypothesis": ("#4547 §section_3_ran_lane found STAGE_RAN rows graded 14.5% loser "
                       "vs 27.6% for the rest of the buy lane FROM ADMISSION (n=55). This "
                       "block asks the different question: once such a name LEAVES the "
                       "board, does it keep working?"),
        "ran_statuses": sorted(ubr._RAN_STATUSES),
        "flag_lift": res["flag_lift_vs_survivors"].get("ran_status"),
        "per_horizon": {
            f"H{h}": res["buy_lane"].get("per_horizon", {}).get(f"H{h}", {})
                        .get("by_class", {}).get("ran_advanced", {"n": 0})
            for h in H_GRID},
    }

    # ---- the counterfactual, stated as the identity it is ---------------------
    res["counterfactual_note"] = (
        "Dropping at departure earns, by construction, ZERO excess from the drop date "
        "onward. So the drop-anchored distribution IS the hold-minus-drop delta — it is "
        "not a second measurement, and reading it as one would double-count. "
        "`on_board_excess_spy_pp_median` beside it is what the name earned WHILE on the "
        "board (admission -> last appearance), which is what separates 'dropped a winner "
        "mid-run' from 'dropped a name that never worked'.")

    # ---- sensitivity: does the price pin cost anything? -----------------------
    try:
        px2, pxprov2 = price_panel(tickers, asof=PRICE_EXT_ASOF)
        panel2 = Panel(px2, PRICE_EXT_ASOF)
        cov = int(sum(1 for t in tickers
                      if t in panel2.last_valid.index
                      and panel2.last_valid.get(t) is not None
                      and not pd.isna(panel2.last_valid.get(t))
                      and panel2.last_valid.get(t) >= pd.Timestamp(PRICE_EXT_ASOF)))
        g2 = grade(dep[dep.lane == "buy"], panel2, sector_of)
        res["price_pin_sensitivity"] = {
            "note": "SENSITIVITY ONLY, not a headline. Extending the price pin to "
                    f"{PRICE_EXT_ASOF} buys 2 extra sessions, but only "
                    f"{cov}/{len(tickers)} board tickers ({100.0 * cov / max(len(tickers), 1):.1f}%) "
                    f"print past {REPRO_ASOF}. Every observation it adds is therefore "
                    "either restricted to that sliver or booked as TRUNCATED against a "
                    "name that simply stops printing on the pin date — the extension "
                    "manufactures truncation rather than maturity, which is why the pin "
                    "stays at the common ceiling.",
            "tickers_with_print_at_ext_pin": cov,
            "tickers_total": len(tickers),
            "prices": pxprov2,
            "buy_lane": g2.get("per_horizon", {}).get(f"H{H_PRIMARY}", {}).get("all_departures"),
            "maturity_census": g2.get("maturity_census"),
        }
    except (OSError, ValueError, RuntimeError) as e:      # never let the sensitivity kill the run
        res["price_pin_sensitivity"] = {"error": f"{type(e).__name__}: {e}"}

    with open(OUT, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print(f"wrote {OUT}")
    return res


if __name__ == "__main__":
    r = main()
    c = r["census"]
    print(f"board dates={c['board_dates']} rows={c['board_rows']} "
          f"episodes={c['episodes']} departures={c['departures']} "
          f"censored={c['censored_at_frame_end']}")
    print("class census:", c["class_census"])
    print("maturity:", r["buy_lane"]["maturity_census"])
