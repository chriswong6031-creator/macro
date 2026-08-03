#!/usr/bin/env python3
"""Prophet Learning Loop — US Buy-Board postmortem forensics (masterplan §2, gates G1/G2).

    python -m scripts.prophet_postmortem            # write summary + report
    python -m scripts.prophet_postmortem --dry-run  # print the headline, write nothing

WHAT IT PRODUCES
----------------
  data/prophet_postmortem/summary.json        aggregations + every episode row
  reports/prophet_postmortem_<as_of>.md       the same content rendered for a reader

WHERE EVERY FIELD COMES FROM
----------------------------
  data/us_board_ledger/retro_grades.parquet   board membership back to 2026-06-15 plus
                                              85 columns of signal state at entry.
  data/us_board_ledger/snapshots.jsonl        the board's OWN nightly JSON from
                                              2026-06-30 on — spotlight theme/sector
                                              read, alignment/extension read, entry
                                              plan (stop, chase level), hold state.
                                              Richer than the parquet; used first.
  data/breadth/_closes_cache.parquet (+ smallcap / midcap / russell)
                                              dividend-adjusted closes, FIRST-HIT-WINS
                                              across the four caches in that order —
                                              the same precedence build_stock_library
                                              uses to assemble its universe.
  data/yahoo/SPY.parquet                      benchmark leg (excess return).
  data/baskets/latest.json  VIA GIT HISTORY   theme state AS OF the entry date. The file
                                              is overwritten nightly, so the only way to
                                              know what the desk thought of a theme on
                                              2026-07-09 is to read the blob from the
                                              last commit whose own `as_of` is <= that
                                              date. 69 revisions are available.
  data/baskets/membership.json                ticker -> basket ids. CURRENT membership,
                                              not point-in-time — see MEMBERSHIP DRIFT.

MEMBERSHIP DRIFT (a caveat, printed on the artifact and in the report)
----------------------------------------------------------------------
membership.json is a single current file with no per-date history, so a ticker that
JOINED a basket after an entry date will be credited with that basket's entry-date
state. The theme STATE is point-in-time (git); the ticker->theme MAPPING is not. The
sector-basket leg is unaffected (it derives from the row's own sector at entry), and
the board's own `spotlight.theme.slug` is recorded beside the mapped ids so a reader
can see where the two disagree. Reconstructing membership history is a separate job.

SCORING — WHOSE NUMBERS ARE THESE?
----------------------------------
`engine.track_scoring`, unchanged (gate G4). Next-bar-close fill, forced verdict at
H=10, symmetric maturity gate, and NO stop / NO oscillator target: this study measures
the SIGNAL, so it must not mix in an exit policy. The published US ledger applies its
own exit rule, so the two agree except where that rule fired — e.g. IPGP 2026-07-15
scores -17.9% here and -18.7% in the ledger, which stopped out on day 8. Both are the
same fill and the same window; only the exit differs.

RE-ADMISSION: THE PRIOR-EPISODE SCAN
------------------------------------
`prior_episodes()` compares each entry against EVERY prior run of the same ticker whose
board exit sits inside the 10-session window — not just the immediately preceding one —
and reports one of them by a fixed precedence (buildable open drawdown, then resolved
loss, then the nearest prior as a decided negative). An in-window prior that cannot be
priced makes the row UNDECIDABLE rather than clean, and every row carries its comparison
in `prior_episode` with `prior_matured`, so a reader can see whether the number the leg
fired on is a resolved outcome or an outcome-conditioned mark.

IN-FLIGHT ROWS
--------------
Episodes without H forward bars are marked to the latest close, CLASSIFIED (four of the
eleven names the operator flagged on 2026-07-31 are still open — dropping them would
delete the most recent evidence), and then held in a block that enters no rate. See
engine/postmortem.py rule 4.

NO LLM ANYWHERE (constitution A7). Every label is a threshold rule in engine/postmortem.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import postmortem as pm  # noqa: E402
from engine import track_scoring as ts  # noqa: E402

RETRO_REL = Path("data/us_board_ledger/retro_grades.parquet")
SNAPSHOTS_REL = Path("data/us_board_ledger/snapshots.jsonl")
BASKETS_REL = Path("data/baskets/latest.json")
MEMBERSHIP_REL = Path("data/baskets/membership.json")
BENCH_REL = Path("data/yahoo/SPY.parquet")
OUT_REL = Path("data/prophet_postmortem/summary.json")
REPORT_DIR_REL = Path("reports")

#: Close-cache precedence. First cache that carries a ticker wins, matching
#: scripts/build_stock_library.universe — a name present in two caches must resolve to
#: the same series here as it does there, or the postmortem and the library would
#: disagree about the same ticker's price.
CLOSE_CACHE_GROUPS = ("breadth", "smallcap_breadth", "midcap_breadth", "russell_breadth")

#: The lane this study grades. `buy` is the board's actual call; `watch` and `laggards`
#: are context the desk publishes but does not claim as a pick.
LANE = "buy"

SCHEMA = "prophet_postmortem/v1"


# --------------------------------------------------------------------------- #
# input loading
# --------------------------------------------------------------------------- #
def load_closes(root: Path) -> pd.DataFrame:
    """Close matrix, first-hit-wins across CLOSE_CACHE_GROUPS in order."""
    frames: list[pd.DataFrame] = []
    for grp in CLOSE_CACHE_GROUPS:
        p = root / "data" / grp / "_closes_cache.parquet"
        if not p.exists():
            continue
        try:
            frames.append(pd.read_parquet(p))
        except Exception as e:  # noqa: BLE001 — a corrupt cache must not kill the run
            print(f"::warning title=prophet-postmortem::close cache {grp} unreadable ({e})",
                  flush=True)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, axis=1, sort=True)
    out = out.loc[:, ~out.columns.duplicated()]     # first cache wins
    out.index = pd.to_datetime(out.index)
    return out.sort_index()


def load_bench(root: Path) -> "pd.Series | None":
    p = root / BENCH_REL
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    s = df["close"] if "close" in df.columns else df.iloc[:, 0]
    s = pd.to_numeric(s, errors="coerce").dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def load_snapshots(root: Path) -> dict[str, dict[str, dict]]:
    """{board_date: {ticker: row}} over EVERY lane.

    Every lane, not just `buy`: the hold-state history that `thesis_break` reads has to
    follow a name after it drops out of `buy` into `watch`, which is exactly when a base
    breaks. Episode membership still comes from the buy lane alone.
    """
    out: dict[str, dict[str, dict]] = {}
    p = root / SNAPSHOTS_REL
    if not p.exists():
        return out
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except json.JSONDecodeError:
                continue
            d = str(doc.get("as_of") or "")
            if not d:
                continue
            bucket = out.setdefault(d, {})
            for lane in ("buy", "watch", "leaders", "laggards"):
                for row in (doc.get(lane) or []):
                    tk = row.get("ticker")
                    if tk and tk not in bucket:
                        bucket[str(tk)] = row
    return out


def load_retro(root: Path) -> pd.DataFrame:
    p = root / RETRO_REL
    if not p.exists():
        return pd.DataFrame()
    return pd.read_parquet(p)


def board_days(retro: pd.DataFrame, snaps: dict[str, dict[str, dict]],
               root: Path) -> dict[str, set[str]]:
    """{board_date: {ticker}} for the buy lane, unioning both sources.

    The retro ledger reaches back before the snapshot archive starts and the archive
    reaches forward past the last retro grade, so neither source alone covers the
    history. Where they overlap they agree (same nightly artifact, two encodings).
    """
    days: dict[str, set[str]] = {}
    if not retro.empty and {"as_of", "ticker", "lane"} <= set(retro.columns):
        sub = retro[retro["lane"].astype(str) == LANE]
        for d, tk in zip(sub["as_of"], sub["ticker"]):
            days.setdefault(str(d), set()).add(str(tk))
    p = root / SNAPSHOTS_REL
    if p.exists():
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    doc = json.loads(line)
                except json.JSONDecodeError:
                    continue
                d = str(doc.get("as_of") or "")
                if not d:
                    continue
                for row in (doc.get(LANE) or []):
                    if row.get("ticker"):
                        days.setdefault(d, set()).add(str(row["ticker"]))
    return days


# --------------------------------------------------------------------------- #
# git archaeology — theme state at a past date
# --------------------------------------------------------------------------- #
def basket_history(root: Path) -> list[tuple[str, dict[str, dict]]]:
    """[(blob_as_of, {theme_id: theme})] for every committed revision, ascending.

    Keyed on the blob's OWN `as_of`, not the commit date: the render lane commits the
    artifact the morning after it is built, so commit dates run a day ahead of the state
    they carry, and a caller asking "what did the desk think on 07-09" wants the file
    the 07-09 board was built from.

    LOUD on git failure. Silently returning [] would blank every theme reading in the
    artifact and leave the `sector_headwind` label evaluating against nothing — the
    same wrong-and-silent degradation that truncated the US ledger on 2026-07-26.
    """
    proc = subprocess.run(
        ["git", "log", "--format=%H", "--", str(BASKETS_REL)],
        cwd=root, capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git log over {BASKETS_REL} failed (rc={proc.returncode}): "
            f"{proc.stderr.strip()[:300]} — refusing to emit a postmortem whose "
            "entry-time theme context would be silently empty."
        )
    by_asof: dict[str, dict[str, dict]] = {}
    for sha in proc.stdout.split():
        blob = subprocess.run(
            ["git", "show", f"{sha}:{BASKETS_REL}"],
            cwd=root, capture_output=True, text=True, check=False,
        ).stdout
        if not blob:
            continue
        try:
            doc = json.loads(blob)
        except json.JSONDecodeError:
            continue
        asof = str(doc.get("as_of") or "")
        if not asof or asof in by_asof:
            continue          # git log is newest-first; the newest blob per as_of wins
        themes = {
            str(t.get("id")): t
            for t in (doc.get("themes") or [])
            if isinstance(t, dict) and t.get("id")
        }
        if themes:
            by_asof[asof] = themes
    return sorted(by_asof.items())


def themes_as_of(history: list[tuple[str, dict[str, dict]]], date: str
                 ) -> tuple[str | None, dict[str, dict]]:
    """The latest revision whose as_of is <= `date`. ('', {}) when none exists yet."""
    best: tuple[str | None, dict[str, dict]] = (None, {})
    for asof, themes in history:          # ascending
        if asof <= date:
            best = (asof, themes)
        else:
            break
    return best


def membership_map(root: Path) -> dict[str, list[str]]:
    """{ticker: [basket_id, ...]} from the CURRENT membership file (drift caveat above)."""
    p = root / MEMBERSHIP_REL
    if not p.exists():
        return {}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, set[str]] = {}
    for bid, basket in sorted((doc.get("baskets") or {}).items()):
        for member in (basket.get("members") or []):
            tk = member.get("ticker")
            if tk:
                out.setdefault(str(tk), set()).add(str(bid))
    return {tk: sorted(v) for tk, v in sorted(out.items())}


# --------------------------------------------------------------------------- #
# episode assembly
# --------------------------------------------------------------------------- #
def _retro_index(retro: pd.DataFrame) -> dict[tuple[str, str], dict]:
    """{(as_of, ticker): row} for the buy lane, one row per key (lowest horizon wins —
    the columns this study reads are entry-time state, identical across horizons)."""
    out: dict[tuple[str, str], dict] = {}
    if retro.empty or "lane" not in retro.columns:
        return out
    sub = retro[retro["lane"].astype(str) == LANE]
    if "horizon" in sub.columns:
        sub = sub.sort_values(["as_of", "ticker", "horizon"], kind="stable")
    for rec in sub.to_dict("records"):
        key = (str(rec.get("as_of")), str(rec.get("ticker")))
        out.setdefault(key, rec)
    return out


def _hold_broken(snaps: dict[str, dict[str, dict]], ticker: str,
                 entry_date: str, last_date: str | None) -> dict | None:
    """First board night in (entry_date, last_date] that stamped hold.state == broken."""
    for d in sorted(snaps):
        if d <= entry_date:
            continue
        if last_date is not None and d > last_date:
            break
        row = snaps.get(d, {}).get(ticker)
        state = (((row or {}).get("hold") or {}).get("state")) if row else None
        if str(state or "") == "broken":
            return {"board_date": d, "date": d}
    return None


def _compact_context(ctx: dict) -> dict:
    """The label-bearing fields only, for episodes in neither tail.

    Both tails keep their full entry context — that is what the learning loop reads.
    The ~530 neutral episodes keep every field a label keys on (so every label in the
    artifact stays re-derivable by hand) but drop the rest of the nested board payload,
    which is ~550 KB of context nobody reads for a name that finished flat. The full
    record is one deterministic re-run away: `python -m scripts.prophet_postmortem`.
    """
    ext = ctx.get("extension") or {}
    spot = ctx.get("spotlight") or {}
    plan = ctx.get("entry_plan") or {}
    conv = ctx.get("conviction") or {}
    return {
        "compact": True,
        "sector": ctx.get("sector"),
        "basket_asof": ctx.get("basket_asof"),
        "themes": [{"id": t.get("id"), "reco": t.get("reco")}
                   for t in (ctx.get("themes") or [])],
        "sector_basket": {k: (ctx.get("sector_basket") or {}).get(k)
                          for k in ("id", "reco", "label")} if ctx.get("sector_basket") else None,
        "spotlight": {"dir": spot.get("dir"), "sector_stage": spot.get("sector_stage"),
                      "sector_pctile_252d": spot.get("sector_pctile_252d")},
        "extension": {k: ext.get(k) for k in
                      ("overextended", "entry_tier", "ext_risk", "price",
                       "chase_above", "above_chase")},
        "entry_plan": {"status": plan.get("status"), "stop": plan.get("stop"),
                       "hold_state": plan.get("hold_state")},
        "conviction": {"band": conv.get("band"), "alpha": conv.get("alpha")},
    }


def _sessions_between(calendar: pd.DatetimeIndex, a: str, b: str) -> int | None:
    try:
        ia = calendar.searchsorted(pd.Timestamp(a), side="left")
        ib = calendar.searchsorted(pd.Timestamp(b), side="left")
    except (TypeError, ValueError):
        return None
    return int(ib - ia)


def _mark_at(prev: dict, when: str) -> float | None:
    """The prior position's open P/L, in %, on the night the name came back.

    None when the prior episode has no series or no fill price — the input the
    BUILDABLE `open_drawdown_at_readmit` leg is made of. The engine nulls that leg
    rather than reading the absence as "was not under water".
    """
    sc, series = prev["sc"], prev["series"]
    entry_px = (sc or {}).get("entry")
    if series is None or not entry_px:
        return None
    j = series.index.searchsorted(pd.Timestamp(when), side="left")
    if j >= len(series):
        return None
    return (float(series.iloc[j]) / float(entry_px) - 1.0) * 100.0


def _rev(date: Any) -> str:
    """Sort key that puts the LATEST date first inside an ascending `min()`.

    Dates here are fixed-width ISO strings, so inverting each character's code point
    orders them backwards without parsing. Keeps every tie-break deterministic.
    """
    return "".join(chr(255 - ord(ch)) for ch in str(date))


def prior_episodes(scored: list[dict], calendar: "pd.DatetimeIndex"
                   ) -> dict[tuple[str, str], dict]:
    """{(ticker, entry_date): prior-episode comparison} for the `re_admission` label.

    SCANS EVERY PRIOR EPISODE IN THE WINDOW, not just the immediately preceding one.
    Reading `items[i-1]` alone made the label answer a different question than the one
    it prints: a name that came back twice in a fortnight was compared only against its
    latest run, so a qualifying loss two runs back — inside the same 10-session window —
    was invisible. The scan collects every prior run whose board exit sits within
    `READMIT_MAX_SESSIONS` sessions of this entry and then picks ONE to report, by a
    fixed precedence:

      1. a prior that was ALREADY >= 8% under water at the re-admission (the buildable
         leg) — most negative mark wins, latest entry date breaks a tie;
      2. else a prior that RESOLVED to a >= 8% loss (the hindsight leg) — most negative
         outcome wins, latest entry date breaks a tie;
      3. else the NEAREST in-window prior, reported as a decided negative so the reader
         can see what the comparison actually was.

    NULLS, NOT SILENT ZEROS. An in-window prior that could not be scored (no close path)
    is not evidence that the name came back clean, so when no scoreable prior fires the
    row comes back `{"undecidable": "prior_episode_not_scoreable"}` and the engine nulls
    the label and both legs. An entry with NO in-window prior at all gets no key here at
    all, so the caller's lookup yields None — a decided negative that stays in every
    denominator.

    Every row carries `prior_matured`, because an unmatured prior's `outcome_pct` is a
    MARK — outcome-conditioned, and not the same evidence as a resolved loss.
    """
    by_ticker: dict[str, list[dict]] = {}
    for item in scored:
        by_ticker.setdefault(item["ep"]["ticker"], []).append(item)

    out: dict[tuple[str, str], dict] = {}
    for tk, items in sorted(by_ticker.items()):
        items.sort(key=lambda it: (it["ep"]["entry_date"], str(it["ep"].get("exit_date"))))
        for i, cur in enumerate(items):
            cs = str(cur["ep"]["entry_date"])
            cands: list[dict] = []
            n_unscoreable = 0
            for prev in items[:i]:
                prev_exit = str(prev["ep"].get("exit_date") or prev["ep"]["entry_date"])
                gap = _sessions_between(calendar, prev_exit, cs)
                if gap is None or gap > pm.READMIT_MAX_SESSIONS:
                    continue
                if prev["sc"] is None:
                    n_unscoreable += 1
                    continue
                psc = prev["sc"]
                matured = bool(psc.get("matured"))
                cands.append({
                    "entry_date": prev["ep"]["entry_date"],
                    "outcome_pct": psc.get("pnl") if matured else psc.get("mark"),
                    "prior_matured": matured,
                    "sessions_since_prior_exit": gap,
                    "mark_at_readmit_pct": _mark_at(prev, cs),
                })
            n_window = len(cands) + n_unscoreable
            if not n_window:
                continue                      # decided negative: no prior in the window

            open_leg = [c for c in cands
                        if c["mark_at_readmit_pct"] is not None
                        and c["mark_at_readmit_pct"] <= pm.READMIT_LOSS_PCT]
            loss_leg = [c for c in cands
                        if c["outcome_pct"] is not None
                        and c["outcome_pct"] <= pm.READMIT_LOSS_PCT]
            if open_leg:
                pick = min(open_leg, key=lambda c: (float(c["mark_at_readmit_pct"]),
                                                    _rev(c["entry_date"])))
                selected_by = pm.READMIT_LEG_OPEN_DRAWDOWN
            elif loss_leg:
                pick = min(loss_leg, key=lambda c: (float(c["outcome_pct"]),
                                                    _rev(c["entry_date"])))
                selected_by = pm.READMIT_LEG_PRIOR_LOSS
            elif n_unscoreable:
                out[(tk, cs)] = {
                    "undecidable": "prior_episode_not_scoreable",
                    "n_priors_in_window": n_window,
                    "n_priors_unscoreable": n_unscoreable,
                }
                continue
            else:
                pick = min(cands, key=lambda c: (c["sessions_since_prior_exit"],
                                                 _rev(c["entry_date"])))
                selected_by = "nearest_prior_no_leg_fired"
            out[(tk, cs)] = {
                **pick,
                "selected_by": selected_by,
                "n_priors_in_window": n_window,
                "n_priors_unscoreable": n_unscoreable,
            }
    return out


def build_rows(root: Path = ROOT, horizon: int = ts.DEFAULT_HORIZON) -> dict:
    """Score, contextualise and classify every buy-lane episode. Returns the artifact."""
    retro = load_retro(root)
    snaps = load_snapshots(root)
    closes = load_closes(root)
    bench = load_bench(root)
    history = basket_history(root)
    members = membership_map(root)
    retro_by_key = _retro_index(retro)

    days = board_days(retro, snaps, root)
    if not days:
        raise RuntimeError(
            "no board days found in retro_grades.parquet or snapshots.jsonl — "
            "refusing to emit an empty postmortem that would read as 'no losses'."
        )
    episodes = ts.build_episodes(days)
    calendar = bench.index if bench is not None else closes.index

    # ── pass 1: score every episode ───────────────────────────────────────────
    scored: list[dict] = []
    no_price: list[str] = []
    for ep in episodes:
        tk, d0 = ep["ticker"], ep["entry_date"]
        series = closes[tk].dropna() if tk in closes.columns else None
        sc = ts.score_episode(series, d0, horizon, bench_close=bench) if series is not None else None
        if sc is None:
            no_price.append(f"{tk}@{d0}")
            scored.append({"ep": ep, "sc": None, "series": None})
            continue
        scored.append({"ep": ep, "sc": sc, "series": series})

    # ── pass 2: prior-episode scan, per ticker, in entry order ────────────────
    prior_by_key = prior_episodes(scored, calendar)

    # ── pass 3: context + classification ──────────────────────────────────────
    rows: list[dict] = []
    for item in scored:
        ep, sc, series = item["ep"], item["sc"], item["series"]
        tk, d0 = ep["ticker"], ep["entry_date"]
        snap_row = snaps.get(d0, {}).get(tk)
        retro_row = retro_by_key.get((d0, tk))
        basket_asof, themes = themes_as_of(history, d0)
        ctx = pm.entry_context(snap_row, retro_row, themes, members.get(tk), basket_asof)

        if sc is None:
            maturity, outcome, excess, mark = "unscored", None, None, None
            mae = mfe = held = None
            fill_date = None
        else:
            matured = bool(sc.get("matured"))
            fill_pending = bool(sc.get("fill_pending"))
            maturity = "matured" if matured else ("unscored" if fill_pending else "in_flight")
            outcome = sc.get("pnl") if matured else sc.get("mark")
            excess = sc.get("excess")
            mark = sc.get("mark")
            mae, mfe, held = sc.get("mae"), sc.get("mfe"), sc.get("held")
            fill_date = sc.get("entry_date")

        # Three different reasons a path can be missing, and they must not share a
        # label: only the first is a coverage hole. A name whose fill bar has not
        # printed yet has a perfectly good price series.
        path = None
        path_reason = "no_price_path"
        if series is None:
            path_reason = "no_price_path"
        elif fill_date is None:
            path_reason = "fill_not_yet_printed"
        else:
            path = pm.path_features(
                series, fill_date, held, (ctx.get("entry_plan") or {}).get("stop"))
            if path is None:
                path_reason = "window_too_short"

        broken = _hold_broken(snaps, tk, d0, ep.get("exit_date"))
        prior = prior_by_key.get((tk, d0))
        labels, nulls = pm.classify(
            outcome_pct=outcome, excess_pct=excess, ctx=ctx, path=path,
            hold_broken=broken, prior=prior,
            path_missing_reason=path_reason,
        )

        rows.append({
            "ticker": tk,
            "entry_date": d0,
            "board_exit_date": ep.get("exit_date"),
            "fill_date": fill_date,
            "horizon": horizon,
            "maturity": maturity,
            "outcome_pct": None if outcome is None else round(float(outcome), 2),
            "pnl_pct": (round(float(sc["pnl"]), 2)
                        if sc and sc.get("pnl") is not None else None),
            "excess_pct": None if excess is None else round(float(excess), 2),
            "mark_pct": None if mark is None else round(float(mark), 2),
            "mae_pct": None if mae is None else round(float(mae), 2),
            "mfe_pct": None if mfe is None else round(float(mfe), 2),
            "held": held,
            "cohort": pm.cohort_of(outcome, excess),
            # The prior-episode comparison `re_admission` was decided on, on EVERY row
            # that had one — including the rows where no leg fired and the rows where the
            # prior could not be scored. Written out rather than left inside the label's
            # trigger because a comparison that produced no label is exactly the one a
            # reader cannot otherwise see, and `prior_matured` says whether the number it
            # was compared against is a resolved outcome or an outcome-conditioned mark.
            # None = the scan found no prior run inside the window (a decided negative).
            "prior_episode": prior,
            "entry_context": ctx,
            "labels": labels,
            "labels_null": sorted(nulls, key=lambda d: (d["label"], d["reason"])),
        })

    rows.sort(key=lambda r: (r["entry_date"], r["ticker"]))
    # Aggregate on the FULL rows, then trim the neutral tail for serialization —
    # never the other way round, or the summary would be computed on a trimmed sample.
    summary = pm.aggregate(rows)
    for r in rows:
        if r["cohort"] not in ("loser", "winner"):
            r["entry_context"] = _compact_context(r["entry_context"])
        # `en`/`zh` per label are pure duplication of summary.taxonomy, once per row.
        for lb in r["labels"]:
            lb.pop("en", None)
            lb.pop("zh", None)
    as_of = max(days)

    coverage = {
        "board_dates": len(days),
        "board_date_first": min(days),
        "board_date_last": as_of,
        "n_episodes": len(rows),
        "n_no_price_path": len(no_price),
        "tickers_no_price_path": sorted({s.split("@")[0] for s in no_price}),
        "basket_revisions": len(history),
        "basket_asof_first": history[0][0] if history else None,
        "basket_asof_last": history[-1][0] if history else None,
        "snapshot_dates": len(snaps),
        "membership_tickers": len(members),
    }
    caveats = [
        {"id": "membership_drift",
         "en": ("Theme STATE at entry is point-in-time (reconstructed from git history of "
                "data/baskets/latest.json); the ticker-to-theme MAPPING is today's "
                "membership.json, which carries no per-date history. A name that joined a "
                "basket after its entry date is credited with that basket's entry-date "
                "state. The sector-basket leg is unaffected."),
         "zh": ("入场时的主题状态为时点还原（取自 data/baskets/latest.json 的 git 历史）；"
                "而个股与主题的对应关系用的是当前的 membership.json，该文件没有按日期的历史。"
                "若某只股票是在入场日之后才加入某个篮子，会被算上该篮子在入场日的状态。"
                "行业篮子这一条不受影响。")},
        {"id": "mae_is_close_path",
         "en": ("MAE / MFE / gap detection run on daily CLOSES — the caches carry no "
                "intraday lows and no opens, so drawdown and overnight gaps are "
                "UNDER-stated, never over-stated."),
         "zh": ("最大回撤／最大浮盈／跳空识别均基于日收盘价 —— 缓存中没有盘中低点，也没有开盘价，"
                "因此回撤与隔夜跳空只会被低估，不会被高估。")},
        {"id": "overlapping_windows",
         "en": ("Episodes surfaced on the same board night share that night's tape and the "
                "ranker's state — they are one bet, not N. Every share below is reported "
                "over distinct entry DATES as well as over rows."),
         "zh": ("同一晚上榜的标的共享当晚行情与排序器状态 —— 属于一次下注，而非 N 次。"
                "下文每个占比都同时按不同入场日期与按行数两种口径给出。")},
        {"id": "in_flight_excluded_from_rates",
         "en": ("In-flight episodes are marked to the latest close and classified, but "
                "enter no rate and no expectancy — an unresolved position's mark is "
                "outcome-conditioned."),
         "zh": ("尚未到期的记录按最新收盘价标记并参与分类，但不计入任何胜率或期望值 —— "
                "未了结持仓的浮动盈亏会受结果选择影响。")},
        {"id": "measurement_tier_only",
         "en": ("Measurement and display tier only. Nothing here ranks, sizes or gates a "
                "pick. Any rule this suggests is a candidate for its own pre-registered "
                "study, never a live change."),
         "zh": ("仅为测量与展示层。此处内容不参与任何排序、仓位或准入判定。"
                "由此产生的任何规则都必须先走独立的预注册研究，不得直接上线。")},
    ]

    return {
        "schema": SCHEMA,
        "as_of": as_of,
        "generated_from": {
            "retro_grades": str(RETRO_REL),
            "snapshots": str(SNAPSHOTS_REL),
            "closes": [f"data/{g}/_closes_cache.parquet" for g in CLOSE_CACHE_GROUPS],
            "benchmark": str(BENCH_REL),
            "baskets_git": str(BASKETS_REL),
            "membership": str(MEMBERSHIP_REL),
        },
        "method": {
            "scorer": "engine.track_scoring (unchanged)",
            "fill": "next session close after the board date",
            "horizon": horizon,
            "exit_rule": "forced verdict at horizon — no stop, no oscillator target",
            "benchmark": "SPY",
            "lane": LANE,
            "llm_used": False,
            "detail_policy": (
                "Loser and winner episodes carry their full entry context. Neutral and "
                "unscored episodes carry a compact context holding every field a label "
                "keys on, so all labels stay re-derivable; the remaining board payload "
                "is dropped. Per-label EN/ZH copy lives once in summary.taxonomy."
            ),
        },
        "coverage": coverage,
        "caveats": caveats,
        "summary": summary,
        "episodes": rows,
    }


# --------------------------------------------------------------------------- #
# report rendering
# --------------------------------------------------------------------------- #
def _plain(v: Any) -> str:
    return "—" if v is None else str(v)


def _pct(v: Any) -> str:
    """A percentage cell. A missing number prints an em dash and NOT '—%' — a unit
    glued to an absence reads as a measured zero."""
    return "—" if v is None else f"{v}%"


def render_report(doc: dict) -> str:
    """Render the artifact as a reader-facing markdown report (descriptive only)."""
    s = doc["summary"]
    cov = doc["coverage"]
    out: list[str] = []
    A = out.append

    A(f"# Prophet postmortem — US Buy Board · as of {doc['as_of']}")
    A("")
    A(f"Generated by `python -m scripts.prophet_postmortem` from `{RETRO_REL}` + "
      f"`{SNAPSHOTS_REL}`. Scorer: `engine.track_scoring`, unchanged — next-bar-close "
      f"fill, forced verdict at H={doc['method']['horizon']}, no stop and no target "
      "(this study measures the signal, not an exit policy). **No LLM is used anywhere "
      "in the classification path.** Measurement tier only: nothing here ranks, sizes "
      "or gates a pick.")
    A("")
    A("## Coverage")
    A("")
    A(f"- {cov['n_episodes']} buy-lane episodes across {cov['board_dates']} board dates "
      f"({cov['board_date_first']} → {cov['board_date_last']})")
    A(f"- {s['n_matured']} matured · {s['n_in_flight']} in flight · "
      f"{s['n_unscored']} unscored")
    A(f"- {s['cohorts']['n_losers']} losers · {s['cohorts']['n_winners']} winners · "
      f"{s['cohorts']['n_neutral']} neutral "
      f"(loser gate {s['cohorts']['loser_gate']['abs_pct']}% absolute or "
      f"{s['cohorts']['loser_gate']['excess_pct']}% excess; winner gate "
      f"+{s['cohorts']['winner_gate']['abs_pct']}%)")
    A(f"- {cov['n_no_price_path']} episodes with no close path "
      f"({', '.join(cov['tickers_no_price_path']) or 'none'})")
    A(f"- theme state reconstructed from {cov['basket_revisions']} committed revisions of "
      f"`{BASKETS_REL}` ({cov['basket_asof_first']} → {cov['basket_asof_last']})")
    A("")

    A("## Failure taxonomy — both tails")
    A("")
    A("Shares are over the episodes on which each label could actually be DECIDED, not "
      "over the whole sample. Rows whose entry state was never recorded are excluded "
      "from that label's denominator and counted in `nulls` — putting them in the "
      "unflagged bucket would silently deflate every rate below.")
    A("")
    A("| Label | Visible at entry | Losers | of decidable losers | Winners | "
      "of decidable winners | loss contribution | loser coverage | nulls |")
    A("|---|---|---|---|---|---|---|---|---|")
    for f in s["label_frequency"]:
        A(f"| `{f['label']}` — {f['en']} | {'yes' if f['visible_at_entry'] else 'no'} "
          f"| {f['n_losers']} / {f['n_losers_evaluated']} "
          f"| {_pct(f['loser_share_pct'])} "
          f"| {f['n_winners']} / {f['n_winners_evaluated']} "
          f"| {_pct(f['winner_share_pct'])} "
          f"| {_pct(f['loss_contribution_pct'])} "
          f"| {f['n_losers_evaluated']} / {f['n_losers_total']} "
          f"({_pct(f['loser_coverage_pct'])}, {_pct(f['decidable_loss_share_pct'])} "
          f"of the loss) | {f['n_null_disclosed']} |")
    A("")
    A(f"`loss contribution` uses ONE denominator on every row — the whole matured-loser "
      f"book, {s['cohorts']['total_loser_loss_pct']:.2f}pp across "
      f"{s['cohorts']['n_losers']} episodes — so the column is comparable down the table "
      "and across runs. Labels are multi-label, so it does not sum to 100%.")
    A("")
    A("`loser coverage` is the honest companion to it: how many of those losers the label "
      "could even be DECIDED on, and what share of the loss book those rows carry. A "
      "label evaluable on a third of the book contributing 18.8% of it is a different "
      "sentence from one with full reach contributing 18.8%. Read the two columns "
      "together; never read contribution alone.")
    A("")
    A("`nulls` counts matured episodes where the label could not be evaluated (no entry "
      "state recorded, no price path, no stop recorded, no benchmark leg, no priceable "
      "prior episode) — those episodes stay in the artifact with the reason named on the "
      "row, and are excluded from that label's denominators above.")
    A("")

    beta = s["diagnostics"]["market_beta_excess_share"]
    if beta["n"]:
        A(f"On `market_beta`: across {beta['n']} matured losers the benchmark-excess loss "
          f"was {beta['min']:.2f}–{beta['max']:.2f} of the absolute loss "
          f"(median {beta['median']:.2f}), never below the {beta['threshold']} threshold. "
          "Over this window the losses were the picks, not the tape.")
        A("")
    idio = s["diagnostics"]["idiosyncratic_split"]
    A(f"On `idiosyncratic`: {idio['n_total']} matured episodes carry it, of which "
      f"{idio['n_fully_checked']} had every other leg checked and "
      f"{idio['n_with_unchecked_legs']} still have an unchecked leg. The second group is "
      "\"not fully looked at\", not \"no pattern found\" — each row's `labels_null` names "
      "the missing leg.")
    A("")

    A("## What a veto would have cost — both sides")
    A("")
    A("What refusing the flagged picks would have avoided, **and what it would have "
      "thrown away**. The winners-forfeited column is the point of the table. Each row is "
      "costed over the episodes where its own trigger was decidable, and `universe` says "
      "how many that is.")
    A("")
    A("**A row is a TRIGGER, not a label.** The `evidence` column says whether that "
      "trigger existed on the night of the pick (`buildable`) or needs a number that only "
      "arrived later (`hindsight upper bound`). The two are not comparable and are never "
      "summed: only a buildable row describes a rule anyone could pre-register.")
    A("")
    A("| Would-be veto | Evidence | Flagged | universe | of universe | Losers avoided "
      "| Loss avoided | **Winners forfeited** | **Gains forfeited** | Net | Dates flagged "
      "| Mean flagged | Mean unflagged |")
    A("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for v in s["veto_cost"]:
        A(f"| `{v['key']}` | {'buildable' if v['visible_at_entry'] else 'hindsight upper bound'} "
          f"| {v['n_flagged']} | {v['n_universe']} "
          f"| {_pct(v['flagged_share_of_universe_pct'])} "
          f"| {v['n_losers_avoided']} | {v['loss_avoided_pct']:.2f}pp "
          f"| **{v['n_winners_forfeited']}** | **{v['winners_forfeited_pct']:.2f}pp** "
          f"| {v['net_pct_if_vetoed']:+.2f}pp | {v['n_dates_flagged']} "
          f"| {_pct(v['mean_outcome_of_flagged_pct'])} "
          f"| {_pct(v['mean_outcome_of_unflagged_pct'])} |")
    A("")
    for name in sorted({v["label"] for v in s["veto_cost"] if v.get("leg")}):
        legs = [v for v in s["veto_cost"] if v["label"] == name]
        A(f"**`{name}` is {len(legs)} claims, not one**, so it is costed on "
          f"{len(legs)} lines:")
        A("")
        for v in legs:
            if v["visible_at_entry"]:
                zero = (" — it fires **zero** times on this window, and the zero is "
                        "printed rather than dropped: an empty buildable row is the "
                        "finding, and hiding it would leave only the hindsight line on "
                        "the page." if not v["n_flagged"] else ".")
                A(f"- `{v['leg']}` — **buildable**. {v['en']}. The board could read this "
                  f"at entry. Flagged {v['n_flagged']} of the {v['n_universe']} matured "
                  f"episodes it could be decided on{zero}")
            else:
                A(f"- `{v['leg']}` — **hindsight upper bound**. {v['en']}. This needs the "
                  f"earlier episode's RESOLVED outcome, which did not exist on the night "
                  f"the board bought the name back, so the "
                  f"{v['loss_avoided_pct']:.2f}pp on this line is a CEILING on what the "
                  f"pattern could be worth if a buildable trigger is ever found — never "
                  f"the value of a rule. Flagged {v['n_flagged']} of {v['n_universe']} "
                  f"across {v['n_dates_flagged']} entry dates.")
        A("")
    A("`Net` is loss avoided minus gains forfeited, in summed percentage points across "
      "matured episodes — a raw arithmetic counterfactual on equal weights, not a "
      "backtest and not an expectancy. It ignores position sizing, the overlap between "
      "episodes on one board night, and the fact that the same capital cannot take every "
      "pick. Read it as a first-order sanity check on whether a veto is even worth "
      "pre-registering.")
    A("")

    A("## Systemic or anomalous?")
    A("")
    A("A label on nine episodes across one night is one bad night. The same label across "
      "seven nights is a process fault. Distinct entry dates, not row counts, decide.")
    A("")
    A("| Label | Loser dates | of all loser dates | Largest single date | Read |")
    A("|---|---|---|---|---|")
    for v in s["systemic_vs_anomalous"]:
        A(f"| `{v['label']}` | {v['n_dates']} / {v['n_loser_dates_total']} "
          f"| {_pct(v['date_share_pct'])} "
          f"| {_plain(v['max_single_date'])}"
          f"{'' if v['max_single_date'] is None else f" ({_pct(v['max_single_date_share_pct'])} of the label's losers)"}"
          f" | {v['read']} |")
    A("")

    A("## Entry-state splits (matured episodes where the state was recorded)")
    A("")
    A("| Split | n | dates | losers | loss rate | winners | win rate | mean outcome |")
    A("|---|---|---|---|---|---|---|---|")
    for key in sorted(s["cohort_splits"]):
        c = s["cohort_splits"][key]
        A(f"| {key.replace('_', ' ')} | {c['n']} | {c['n_dates']} | {c['n_losers']} "
          f"| {_pct(c['loss_rate_pct'])} | {c['n_winners']} "
          f"| {_pct(c['win_rate_pct'])} | {_pct(c['mean_outcome_pct'])} |")
    A("")

    if s["repeat_offenders"]:
        A("## Repeat offenders")
        A("")
        A("| Ticker | Loser episodes | Entry dates | Total loss | Labels |")
        A("|---|---|---|---|---|")
        for r in s["repeat_offenders"]:
            A(f"| {r['ticker']} | {r['n_loser_episodes']} | {', '.join(r['entry_dates'])} "
              f"| {r['total_loss_pct']:.2f}pp | {', '.join(r['labels'])} |")
        A("")

    # ── the loser book, split by maturity, with counts that RECONCILE ─────────
    # One table pooling matured and marked-to-market rows invites exactly the read the
    # maturity gate exists to prevent, because today's worst open positions sort to the
    # top of it. Two labelled blocks, and a sentence whose numbers add up.
    losers = [r for r in doc["episodes"] if r["cohort"] == "loser"]
    by_maturity = {
        "matured": [r for r in losers if r["maturity"] == "matured"],
        "in_flight": [r for r in losers if r["maturity"] == "in_flight"],
        "unscored": [r for r in losers if r["maturity"] not in ("matured", "in_flight")],
    }
    parts = " + ".join(
        f"**{len(v)} {k.replace('_', ' ')}**" for k, v in by_maturity.items() if v)

    A("## Every loser, with its trigger values")
    A("")
    A(f"{len(losers)} episodes sit in the loser cohort: {parts} = {len(losers)}. The "
      "blocks are listed separately and never pooled. Every rate, share and "
      f"counterfactual above is computed on the matured block alone "
      f"({s['cohorts']['n_losers']} episodes) — a mark on an unresolved position is "
      "outcome-conditioned, and today's worst open names would sort straight to the top "
      "of a pooled table.")
    A("")

    def _loser_table(rows: list[dict]) -> None:
        A("| Ticker | Entry | Outcome | Excess | MAE | MFE | Held | Labels |")
        A("|---|---|---|---|---|---|---|---|")
        for r in sorted(rows, key=lambda r: (r["outcome_pct"]
                                             if r["outcome_pct"] is not None else 0.0)):
            A(f"| {r['ticker']} | {r['entry_date']} "
              f"| {_pct(r['outcome_pct'])} | {_pct(r['excess_pct'])} "
              f"| {_pct(r['mae_pct'])} | {_pct(r['mfe_pct'])} | {_plain(r['held'])} "
              f"| {', '.join(lb['label'] for lb in r['labels']) or '—'} |")
        A("")

    A(f"### Matured losers ({len(by_maturity['matured'])}) — these carry every rate above")
    A("")
    _loser_table(by_maturity["matured"])
    A(f"### In-flight losers ({len(by_maturity['in_flight'])}) — marked, in NO rate")
    A("")
    A("Fewer than H forward bars, so these are marked to the latest close. They are here "
      "because dropping them would delete the most recent evidence — not because they "
      "count. `Outcome` in this block is a MARK, not a result.")
    A("")
    _loser_table(by_maturity["in_flight"])
    if by_maturity["unscored"]:
        A(f"### Unscored losers ({len(by_maturity['unscored'])}) — no fill printed yet")
        A("")
        _loser_table(by_maturity["unscored"])

    infl_block = s["in_flight"]
    A("## In-flight rows (classified, counted in no rate)")
    A("")
    A(f"{infl_block['n']} episodes have fewer than H={doc['method']['horizon']} "
      "forward bars. They are marked to the latest close so the most recent evidence "
      "stays visible, and they enter no rate or expectancy — an unresolved position's "
      "mark is outcome-conditioned in exactly the way the maturity gate exists to "
      "prevent.")
    A("")
    A(f"By the mark: {infl_block['n_losers_marked']} at loser levels · "
      f"{infl_block['n_winners_marked']} at winner levels · "
      f"{infl_block['n_neutral_marked']} neutral · "
      f"{infl_block['n_unscored_marked']} unscored = {infl_block['n']}. The two tails are "
      "tabled below (the loser half repeats the in-flight block above); the neutral "
      "middle is in `summary.json`, not here.")
    A("")
    A("| Ticker | Entry | Mark | MAE | MFE | Held | Labels |")
    A("|---|---|---|---|---|---|---|")
    infl = [r for r in doc["episodes"]
            if r["maturity"] == "in_flight" and r["cohort"] in ("loser", "winner")]
    infl.sort(key=lambda r: (r["outcome_pct"] if r["outcome_pct"] is not None else 0.0))
    for r in infl:
        A(f"| {r['ticker']} | {r['entry_date']} | {_pct(r['outcome_pct'])} "
          f"| {_pct(r['mae_pct'])} | {_pct(r['mfe_pct'])} | {_plain(r['held'])} "
          f"| {', '.join(lb['label'] for lb in r['labels']) or '—'} |")
    A("")

    A("## Caveats")
    A("")
    for c in doc["caveats"]:
        A(f"- **{c['id']}** — {c['en']}")
    A("")
    A("---")
    A("")
    A("Review protocol: `docs/PROPHET_POSTMORTEM_PROTOCOL.md`. "
      "Program: `research/PROPHET_LEARNING_LOOP_MASTERPLAN_BY_FABLE.md`.")
    A("")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="US Buy-Board postmortem forensics")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--horizon", type=int, default=ts.DEFAULT_HORIZON)
    ap.add_argument("--out", default=None, help=f"default {OUT_REL}")
    ap.add_argument("--report-dir", default=None, help=f"default {REPORT_DIR_REL}")
    ap.add_argument("--dry-run", action="store_true", help="print the headline, write nothing")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    doc = build_rows(root, horizon=args.horizon)
    s = doc["summary"]

    print(f"prophet-postmortem as_of={doc['as_of']} episodes={s['n_episodes']} "
          f"matured={s['n_matured']} in_flight={s['n_in_flight']} "
          f"losers={s['cohorts']['n_losers']} winners={s['cohorts']['n_winners']}")
    for f in s["label_frequency"]:
        print(f"  {f['label']:<16} losers={f['n_losers']:<4} "
              f"({f['loser_share_pct']}%)  winners={f['n_winners']:<4} "
              f"({f['winner_share_pct']}%)  nulls={f['n_null_disclosed']}")
    for v in s["veto_cost"]:
        # `key`, not `label`: two rows share the label `re_admission` and differ only in
        # the leg, and the buildable one is the whole point of printing both.
        print(f"  veto[{v['key']}] {v['variant']} "
              f"flagged={v['n_flagged']}/{v['n_universe']} "
              f"losers_avoided={v['n_losers_avoided']} ({v['loss_avoided_pct']:.2f}pp) "
              f"winners_forfeited={v['n_winners_forfeited']} "
              f"({v['winners_forfeited_pct']:.2f}pp) net={v['net_pct_if_vetoed']:+.2f}pp")

    # GitHub annotations: bare print at line start, flush=True. A logger here would
    # prefix the line and GitHub would silently drop the annotation (house law).
    if doc["coverage"]["n_no_price_path"]:
        print(f"::warning title=prophet-postmortem::"
              f"{doc['coverage']['n_no_price_path']} episodes have no close path — "
              f"their path labels are emitted null, not dropped "
              f"({', '.join(doc['coverage']['tickers_no_price_path'][:12])})", flush=True)
    if not doc["coverage"]["basket_revisions"]:
        print("::warning title=prophet-postmortem::no committed revisions of "
              "data/baskets/latest.json found — entry-time theme context is empty",
              flush=True)

    if args.dry_run:
        return 0

    out_path = Path(args.out) if args.out else root / OUT_REL
    _write_json(out_path, doc)
    report_dir = Path(args.report_dir) if args.report_dir else root / REPORT_DIR_REL
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"prophet_postmortem_{doc['as_of']}.md"
    report_path.write_text(render_report(doc), encoding="utf-8")
    print(f"wrote {out_path} and {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
