"""engine.etf_board_ledger — forward measurement ledger for the ETF consensus board.

ETF page upgrade masterplan §3 W3. The Fund Flows board (``etfs.html``) has never
carried a measurement loop: it publishes a ranked consensus board every night and
nothing anywhere records what those names then did. This module is the missing
half — an append-only fire log of the board as it was published, plus a derived
forward-return store that fills in as each window matures.

THREE ARTIFACTS, three different jobs:

  ``data/etf_board_ledger/snapshots.jsonl``   — the PIT fire log. One JSON object
      per (as_of, ticker) on the night that board shipped, keep-FIRST: a row that
      already exists for a board date is NEVER rewritten. This is the evidence;
      everything else is derived and may be recomputed.

  ``data/etf_board_ledger/retro_grades.parquet`` — the derived grade store. One row
      per (as_of, ticker, horizon). Price-derived columns are FROZEN at first grade
      (``_FROZEN_PRICE_COLS``) exactly as ``scripts/grade_us_board.py`` freezes its
      own: the price ladder can re-base a series underneath us, so a keep-FRESH
      merge would silently restate an already-published measurement.

  ``site/factordata/etf_board_track.json``  — the small display projection the
      Calibration Lab reads. Summary per horizon + a capped tail of graded rows.

LANE LAW (house rule: nightly is the sole advancer of forward ledgers; masterplan
§0.7). Every ``data/`` write here is gated on
``engine.ledger_lane.nightly_advance_enabled()`` (``COLLECT_LANE=nightly``), fail-
closed, exactly like ``engine.board_ledger.append_board``. Off-lane the append and
the merge return without touching the filesystem — no file is created — so a render,
an intraday lane, or a local experiment can read and project the ledger but can
never advance it. The ``site/`` projection is derived from what is already on disk
and is therefore safe in any lane (same split as the Price Pressure lobe: ledger
gated, display artifact rebuilt anywhere).

WHAT THIS IS NOT. Display tier, context only. Nothing here feeds a rank, a score, a
gate or a size, and no ranking on etfs.html consults it. It exists so that a FUTURE
promotion (masterplan §4 — predictive fund weighting) has real forward evidence to
be gauntleted against instead of an assertion. Until then the honest reading of a
thin ledger is "collecting", and the surface says so.

SCHEMA TOLERANCE. Sibling waves are still adding fields to the consensus row
(flow/selection dollars, persistence, coverage flags). ``snapshot_record`` persists
whatever scalar fields the row carries, by iteration rather than by a hard-coded
column list, so a new engine field starts accruing the night it ships and an ABSENT
field is simply absent — never a crash. Heavy nested values (sparkline trajectories,
per-fund history) are dropped: the fire log has to stay small enough to commit every
night for years.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]

#: Ledger home, relative to the configured data root.
LEDGER_DIRNAME = "etf_board_ledger"
SNAPSHOTS_NAME = "snapshots.jsonl"
RETRO_NAME = "retro_grades.parquet"

#: Display projection the Calibration Lab tile reads.
TRACK_JSON = ROOT / "site" / "factordata" / "etf_board_track.json"
SCHEMA = "etf_board_track.v1"

#: Trading-day horizons. 5 ≈ a week, 21 ≈ a month, 63 ≈ a quarter — the same ladder
#: the US board ledger grades on, so the two records are readable side by side.
HORIZONS = (5, 21, 63)

#: Benchmark leg. Every return is reported absolute AND relative to this, because a
#: board of high-beta thematic names in a rising tape says nothing on its own.
BENCH = "SPY"

#: How many board rows to log per night. The board publishes up to 40; the top of it
#: is what a reader acts on, and a smaller fire log is a committable one.
TOP_N = 20

#: Tail of graded rows carried in the display artifact (size discipline: the whole
#: file must stay well under 100KB so the render path never pays for it).
DISPLAY_ROWS_CAP = 120

#: Keys never persisted: nested time-series and per-fund history that would grow the
#: fire log without being gradeable. Matched case-insensitively on the key name.
_HEAVY_KEYS = frozenset({
    "trajectory", "trajectories", "weight_trajectory", "spark", "sparkline",
    "history", "series", "points", "snapshots",
})

#: Cap on per-fund detail carried inside one snapshot record.
_MAX_FUNDS = 8

#: Identity of one graded observation.
_GRADE_KEYS = ["as_of", "ticker", "horizon"]

#: Price-derived columns, frozen at first grade. A graded row is a point-in-time
#: claim: the adjusted-first ladder can re-base a series (a split, a distribution, a
#: rung that gains history) so the same (ticker, date) reads differently later, and a
#: plain keep-FRESH merge would restate a published measurement with no disclosure.
_FROZEN_PRICE_COLS = [
    "entry_date", "entry_price", "fwd_price", "ret",
    "bench_entry_price", "bench_fwd_price", "bench_ret", "excess_bench",
    "mdd", "price_source", "bench_price_source", "graded_at",
]


# --------------------------------------------------------------------------- #
# paths + lane gate
# --------------------------------------------------------------------------- #
def _data_root(base_dir: str | Path | None = None) -> Path:
    """The data root to write under. ``base_dir`` overrides it (tests, scratch runs)."""
    if base_dir is not None:
        return Path(base_dir)
    from lib import config  # local import: keeps this module importable with no config
    return Path(config.data_dir())


def ledger_dir(base_dir: str | Path | None = None) -> Path:
    return _data_root(base_dir) / LEDGER_DIRNAME


def snapshots_path(base_dir: str | Path | None = None) -> Path:
    return ledger_dir(base_dir) / SNAPSHOTS_NAME


def retro_path(base_dir: str | Path | None = None) -> Path:
    return ledger_dir(base_dir) / RETRO_NAME


def lane_open() -> bool:
    """True only in the nightly engine lane (``COLLECT_LANE=nightly``).

    FAIL-CLOSED: if the canonical gate cannot even be imported we treat the lane as
    shut, because the failure mode of a wrong ``True`` here is duplicate rows in an
    append-only ledger — unrecoverable — while a wrong ``False`` costs one night.
    """
    try:
        from engine.ledger_lane import nightly_advance_enabled
        return bool(nightly_advance_enabled())
    except Exception as exc:  # noqa: BLE001
        log.warning("etf_board_ledger: ledger_lane import failed (%s) — "
                    "treating as off-lane (fail-closed)", exc)
        return False


# --------------------------------------------------------------------------- #
# as-of: the DATA date, never a wall clock
# --------------------------------------------------------------------------- #
def board_asof(roots: "list[Path] | None" = None,
               base_dir: str | Path | None = None) -> str | None:
    """Newest holdings-snapshot date across the tracked fleet, ``YYYY-MM-DD``.

    This is the same "fleet's own edge" reference ``engine.etf_consensus.fund_coverage``
    measures staleness against, and it is deliberately NOT ``date.today()``: the board
    is a function of the snapshots it was built from, so a night that collects nothing
    must not stamp a fresh board date onto stale holdings. Returns None when no
    snapshot exists anywhere (nothing to log).
    """
    if roots is None:
        root = _data_root(base_dir)
        roots = [root / "etf_holdings"]
        try:
            from lib import config
            cfg = config.load()
            roots.append(Path(config.ROOT) / cfg["storage"]["holdings_dir"])
        except Exception:  # noqa: BLE001 — the curated store alone is a valid answer
            pass
    latest: str | None = None
    for r in roots:
        try:
            if not Path(r).is_dir():
                continue
            for d in Path(r).iterdir():
                if not d.is_dir():
                    continue
                stems = sorted(p.stem for p in d.glob("*.parquet"))
                if stems and (latest is None or stems[-1] > latest):
                    latest = stems[-1]
        except Exception as exc:  # noqa: BLE001 — freshness must never be fatal
            log.warning("etf_board_ledger.board_asof: scan of %s failed: %s", r, exc)
    return latest


# --------------------------------------------------------------------------- #
# snapshot record: tolerant, forward-compatible serialization
# --------------------------------------------------------------------------- #
#: Decimal places kept on any float in the fire log. Beyond this the digits are
#: float noise, not measurement — and they are expensive: the raw rows carry
#: 14-decimal percentages, which cost ~40% of the file for information nobody can
#: use in an artifact that is committed every night for years.
_FLOAT_DP = 4


def _scalar(v: Any) -> Any:
    """Return ``v`` if it is a JSON-safe scalar (floats rounded), else None."""
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        # NaN/inf are not JSON and read as a value downstream — store the null.
        if v != v or v in (float("inf"), float("-inf")):
            return None
        return round(v, _FLOAT_DP)
    return None


def _compact_mapping(d: dict, limit: int = 24) -> dict:
    """Scalar-only projection of a nested dict (one level, capped)."""
    out: dict[str, Any] = {}
    for k, v in list(d.items())[:limit]:
        if str(k).lower() in _HEAVY_KEYS:
            continue
        s = _scalar(v)
        if s is not None or v is None:
            out[str(k)] = s
    return out


def snapshot_record(row: dict, *, as_of: str, rank: int) -> dict:
    """One fire-log record for one consensus-board row.

    Every scalar field the row carries is persisted by ITERATION — a field a sibling
    wave adds tomorrow starts accruing tomorrow with no edit here, and a field that is
    absent (an older engine, a degraded night) is simply absent rather than a crash.
    ``.get()``-tolerant throughout: the only truly required key is ``ticker``.

    Nested values are compacted: ``funds`` keeps up to ``_MAX_FUNDS`` scalar-only
    entries (the per-fund evidence behind the row), other dicts keep a one-level
    scalar projection, and the heavy time-series keys are dropped outright.
    """
    rec: dict[str, Any] = {
        "as_of": str(as_of),
        "ticker": str(row.get("ticker") or ""),
        "rank": int(rank),
    }
    for k, v in (row or {}).items():
        key = str(k)
        if key in ("as_of", "ticker", "rank") or key.startswith("_"):
            continue
        if key.lower() in _HEAVY_KEYS:
            continue
        if isinstance(v, dict):
            comp = _compact_mapping(v)
            if comp:
                rec[key] = comp
            continue
        if isinstance(v, (list, tuple)):
            items = [_compact_mapping(x) for x in v[:_MAX_FUNDS] if isinstance(x, dict)]
            items = [x for x in items if x]
            if items:
                rec[key] = items
            continue
        rec[key] = _scalar(v)
    return rec


def _existing_keys(path: Path) -> set[tuple[str, str]]:
    """(as_of, ticker) pairs already in the fire log. Unreadable lines are skipped —
    one corrupt line must never make the night's append look new and duplicate it."""
    keys: set[tuple[str, str]] = set()
    if not path.exists():
        return keys
    try:
        text = path.read_text()
    except OSError as exc:
        log.warning("etf_board_ledger: snapshots unreadable (%s) — refusing append", exc)
        raise
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        keys.add((str(d.get("as_of")), str(d.get("ticker"))))
    return keys


def append_snapshot(rows: "list[dict] | None", as_of: str | None, *,
                    base_dir: str | Path | None = None,
                    top_n: int = TOP_N) -> int:
    """Append tonight's top-N consensus board to the fire log. Returns rows written.

    LANE-GATED (``COLLECT_LANE=nightly``): off-lane this returns 0 and does not create
    the directory or the file. Keep-FIRST on (as_of, ticker): a second run on the same
    board date appends nothing and leaves the file byte-identical, which is what makes
    the nightly step safe to re-run and safe to sit behind ``set +e``.
    """
    if not rows or not as_of:
        return 0
    if not lane_open():
        log.info("etf_board_ledger.append_snapshot: off-lane (COLLECT_LANE != nightly) "
                 "— skip write; read paths unaffected")
        return 0

    path = snapshots_path(base_dir)
    seen = _existing_keys(path)
    out: list[str] = []
    for i, row in enumerate(rows[:top_n], start=1):
        tk = str((row or {}).get("ticker") or "")
        if not tk:
            continue
        if (str(as_of), tk) in seen:
            continue
        seen.add((str(as_of), tk))
        out.append(json.dumps(snapshot_record(row, as_of=str(as_of), rank=i),
                              separators=(",", ":"), sort_keys=True, default=str))
    if not out:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write("\n".join(out) + "\n")
    return len(out)


def load_snapshots(base_dir: str | Path | None = None) -> list[dict]:
    """The whole fire log, oldest first. Absent → []. Never raises on a bad line."""
    path = snapshots_path(base_dir)
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        text = path.read_text()
    except OSError as exc:
        log.warning("etf_board_ledger.load_snapshots: %s unreadable: %s", path, exc)
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("as_of") and d.get("ticker"):
            out.append(d)
    out.sort(key=lambda r: (str(r.get("as_of")), int(r.get("rank") or 0), str(r["ticker"])))
    return out


# --------------------------------------------------------------------------- #
# grading
# --------------------------------------------------------------------------- #
def _close_panel(tickers: list[str], start: str | None):
    """Adjusted-first close panel for the graded universe + the benchmark.

    One ladder, one basis on both legs — the excess return is a difference, so pricing
    the name off an unadjusted cache and the benchmark off an adjusted store books the
    name's own distribution as a loss (engine/price_ladder.py, PRICE-BASIS LAW).
    """
    from engine.price_ladder import close_panel
    return close_panel(sorted(set(tickers) | {BENCH}), start=start)


def grade_snapshots(records: "list[dict] | None", *,
                    horizons: tuple[int, ...] = HORIZONS,
                    panel: "pd.DataFrame | None" = None,
                    price_source: "dict | None" = None) -> pd.DataFrame:
    """Forward returns for every (board date, ticker, horizon) in the fire log.

    Next-bar entry fill (``engine.grading.forward_metrics`` — the validated house
    convention: entry is the first bar STRICTLY AFTER the board date, never the board
    bar itself). A horizon without enough forward bars yet grades to None and stays in
    the frame as a pending row, so "not matured" and "matured and flat" are never the
    same cell. A ticker with no price series anywhere also keeps its rows, ungraded,
    with ``price_source`` null — a vanished name is survivorship, and silently dropping
    it is the failure this ledger exists to avoid.

    ``panel``/``price_source`` are injectable so tests and offline replays can grade
    against a fixture without touching the store.
    """
    if not records:
        return pd.DataFrame()
    from engine.grading import forward_metrics

    tickers = sorted({str(r.get("ticker")) for r in records if r.get("ticker")})
    dates = sorted({str(r.get("as_of")) for r in records if r.get("as_of")})
    start = None
    if dates:
        try:
            start = (pd.Timestamp(dates[0]) - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
        except Exception:  # noqa: BLE001
            start = None

    if panel is None:
        try:
            panel, prov = _close_panel(tickers, start)
            price_source = prov.get("price_source") or {}
        except Exception as exc:  # noqa: BLE001 — a dead price store must not kill the log
            log.error("etf_board_ledger.grade_snapshots: price panel failed: %s", exc)
            panel, price_source = pd.DataFrame(), {}
    price_source = price_source or {}

    bench = None
    if panel is not None and not panel.empty and BENCH in panel.columns:
        bench = pd.to_numeric(panel[BENCH], errors="coerce").dropna()

    bench_cache: dict[str, dict] = {}
    graded_at = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows: list[dict] = []
    for rec in records:
        tk = str(rec.get("ticker"))
        as_of = str(rec.get("as_of"))
        close = None
        if panel is not None and not panel.empty and tk in panel.columns:
            s = pd.to_numeric(panel[tk], errors="coerce").dropna()
            close = s if not s.empty else None
        fm = forward_metrics(close, as_of, horizons=horizons) if close is not None else {}
        if bench is not None:
            if as_of not in bench_cache:
                bench_cache[as_of] = forward_metrics(bench, as_of, horizons=horizons)
            bm = bench_cache[as_of]
        else:
            bm = {}
        for h in horizons:
            ret = fm.get(f"fwd_ret_{h}")
            b_ret = bm.get(f"fwd_ret_{h}")
            rows.append({
                "as_of": as_of,
                "ticker": tk,
                "horizon": int(h),
                "rank": _int_or_none(rec.get("rank")),
                "n_accum": _int_or_none(rec.get("n_accum")),
                "n_trim": _int_or_none(rec.get("n_trim")),
                "net_conviction_pp": _float_or_none(rec.get("net_conviction_pp")),
                "total_usd": _float_or_none(rec.get("total_usd")),
                "flow_usd": _float_or_none(rec.get("flow_usd")),
                "selection_usd": _float_or_none(rec.get("selection_usd")),
                "direction": rec.get("direction"),
                "entry_date": fm.get("fill_date"),
                "entry_price": _float_or_none(fm.get("entry_price")),
                "fwd_price": _float_or_none(fm.get(f"fwd_price_{h}")),
                "ret": _float_or_none(ret),
                "mdd": _float_or_none(fm.get(f"fwd_mdd_{h}")),
                "bench_entry_price": _float_or_none(bm.get("entry_price")),
                "bench_fwd_price": _float_or_none(bm.get(f"fwd_price_{h}")),
                "bench_ret": _float_or_none(b_ret),
                "excess_bench": (None if ret is None or b_ret is None
                                 else round(float(ret) - float(b_ret), 6)),
                "price_source": price_source.get(tk),
                "bench_price_source": price_source.get(BENCH),
                "graded_at": graded_at if ret is not None else None,
            })
    return pd.DataFrame(rows)


def _int_or_none(v) -> int | None:
    try:
        return None if v is None else int(v)
    except (TypeError, ValueError):
        return None


def _float_or_none(v) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def freeze_graded_prices(fresh: pd.DataFrame, stored: pd.DataFrame) -> pd.DataFrame:
    """Restore stored price-derived values onto rows that already carry a grade.

    Same law as ``scripts/grade_us_board.py::_freeze_graded_prices``: an already-graded
    row is a published claim and is write-once. Rows whose stored ``ret`` is null are
    still open and take the fresh grade — which is the entire point of re-running.
    """
    if fresh is None or fresh.empty or stored is None or stored.empty:
        return fresh
    if "ret" not in stored.columns:
        return fresh
    key_cols = [c for c in _GRADE_KEYS if c in fresh.columns and c in stored.columns]
    if not key_cols:
        return fresh
    graded = stored[stored["ret"].notna()]
    if graded.empty:
        return fresh
    cols = [c for c in _FROZEN_PRICE_COLS if c in stored.columns]
    if not cols:
        return fresh

    prior = graded.drop_duplicates(subset=key_cols, keep="last").set_index(key_cols)[cols]
    out = fresh.set_index(key_cols)
    common = out.index.intersection(prior.index)
    if len(common):
        for c in cols:
            if c not in out.columns:
                out[c] = None
            out.loc[common, c] = prior.loc[common, c]
    out = out.reset_index()
    out.attrs.update(getattr(fresh, "attrs", {}))
    out.attrs["frozen_rows"] = int(len(common))
    return out


def load_grades(base_dir: str | Path | None = None) -> pd.DataFrame:
    """The accumulated grade store (empty frame when absent). Read path — no gate."""
    p = retro_path(base_dir)
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(p)
    except Exception as exc:  # noqa: BLE001
        log.error("etf_board_ledger.load_grades: %s unreadable: %s", p, exc)
        return pd.DataFrame()


def merge_grades(fresh: pd.DataFrame, *,
                 base_dir: str | Path | None = None) -> pd.DataFrame:
    """Merge freshly-graded rows into the store and return the FULL accumulated frame.

    LANE-GATED write: off-lane nothing is written and the stored frame is returned
    unchanged, so a display rebuild in any lane still projects the committed record.
    Keep-FRESH on (as_of, ticker, horizon) for annotations — new columns and backfills
    reach historical rows — EXCEPT the price-derived columns, which are frozen by
    ``freeze_graded_prices``. Returning the merged frame (not just the fresh rows) is
    what keeps a night that matures nothing from publishing an empty track record.
    """
    stored = load_grades(base_dir)
    if fresh is None or fresh.empty:
        return stored
    if stored.empty:
        merged = fresh.copy()
    else:
        for col in fresh.columns:
            if col not in stored.columns:
                stored[col] = None
        key_cols = [c for c in _GRADE_KEYS if c in fresh.columns and c in stored.columns]
        fresh = freeze_graded_prices(fresh, stored)
        if key_cols:
            fresh_keys = set(map(tuple, fresh[key_cols].astype(str).values.tolist()))
            keep = ~stored[key_cols].astype(str).apply(tuple, axis=1).isin(fresh_keys)
            merged = pd.concat([stored[keep], fresh], ignore_index=True)
        else:
            merged = pd.concat([stored, fresh], ignore_index=True)

    sort_cols = [c for c in _GRADE_KEYS if c in merged.columns]
    if sort_cols:
        merged = merged.sort_values(sort_cols).reset_index(drop=True)

    if not lane_open():
        log.info("etf_board_ledger.merge_grades: off-lane (COLLECT_LANE != nightly) — "
                 "skip write; returning the in-memory merge for display only")
        return merged

    p = retro_path(base_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(p, index=False)
    return merged


# --------------------------------------------------------------------------- #
# display projection
# --------------------------------------------------------------------------- #
def _median(vals: list[float]) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    return float(s[mid]) if n % 2 else float((s[mid - 1] + s[mid]) / 2.0)


def _horizon_block(df: pd.DataFrame, h: int) -> dict:
    """One horizon's forward-window summary. Plain counts; no composite, no score."""
    block = {
        "horizon": int(h),
        "n_rows": 0, "n_graded": 0, "n_pending": 0, "n_boards": 0, "n_names": 0,
        "n_vs_bench": 0, "n_ahead": None,
        "median_excess_bench": None, "mean_excess_bench": None,
        "median_ret": None, "state": "collecting",
    }
    if df is None or df.empty or "horizon" not in df.columns:
        return block
    sub = df[pd.to_numeric(df["horizon"], errors="coerce") == int(h)]
    if sub.empty:
        return block
    block["n_rows"] = int(len(sub))
    graded = sub[sub["ret"].notna()] if "ret" in sub.columns else sub.iloc[0:0]
    block["n_graded"] = int(len(graded))
    block["n_pending"] = int(len(sub) - len(graded))
    if graded.empty:
        return block
    block["n_boards"] = int(graded["as_of"].nunique())
    block["n_names"] = int(graded["ticker"].nunique())
    rets = [float(v) for v in graded["ret"].dropna().tolist()]
    block["median_ret"] = _round(_median(rets))
    # The benchmark leg is counted SEPARATELY: a name can mature without a usable SPY
    # window (or vice versa), and folding the two denominators into one number is how
    # "3 of 8 ahead" quietly starts describing a different 8.
    if "excess_bench" in graded.columns:
        exc = [float(v) for v in graded["excess_bench"].dropna().tolist()]
        block["n_vs_bench"] = len(exc)
        if exc:
            block["median_excess_bench"] = _round(_median(exc))
            block["mean_excess_bench"] = _round(sum(exc) / len(exc))
            block["n_ahead"] = int(sum(1 for v in exc if v > 0))
    block["state"] = "open" if block["n_graded"] else "collecting"
    return block


def _round(v: float | None, nd: int = 6) -> float | None:
    return None if v is None else round(float(v), nd)


def build_track(records: "list[dict] | None", grades: "pd.DataFrame | None", *,
                as_of: str | None = None,
                horizons: tuple[int, ...] = HORIZONS,
                rows_cap: int = DISPLAY_ROWS_CAP) -> dict:
    """The Calibration Lab payload: per-horizon forward windows + a tail of rows.

    Deliberately dumb: counts, a median, and "x of y ahead of the benchmark". No hit
    "accuracy", no composite, no verdict — the windows are re-drawn every night and a
    thin one is reported as thin (``state: collecting``) rather than dressed up.
    """
    records = records or []
    df = grades if grades is not None else pd.DataFrame()
    board_dates = sorted({str(r.get("as_of")) for r in records if r.get("as_of")})
    per_horizon = {f"h{h}": _horizon_block(df, h) for h in horizons}
    n_graded_total = sum(b["n_graded"] for b in per_horizon.values())

    rows: list[dict] = []
    if df is not None and not df.empty and "ret" in df.columns:
        g = df[df["ret"].notna()].copy()
        if not g.empty:
            g = g.sort_values(["as_of", "horizon", "rank"],
                              ascending=[False, True, True]).head(rows_cap)
            for _, r in g.iterrows():
                rows.append({
                    "as_of": str(r.get("as_of")),
                    "ticker": str(r.get("ticker")),
                    "rank": _int_or_none(r.get("rank")),
                    "horizon": _int_or_none(r.get("horizon")),
                    "n_accum": _int_or_none(r.get("n_accum")),
                    "net_conviction_pp": _round(_float_or_none(r.get("net_conviction_pp")), 4),
                    "ret": _round(_float_or_none(r.get("ret")), 5),
                    "excess_bench": _round(_float_or_none(r.get("excess_bench")), 5),
                })

    return {
        "schema": SCHEMA,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": as_of or (board_dates[-1] if board_dates else None),
        "first_board": board_dates[0] if board_dates else None,
        "benchmark": BENCH,
        "horizons": list(horizons),
        "n_boards_logged": len(board_dates),
        "n_snapshot_rows": len(records),
        "n_graded_total": int(n_graded_total),
        "collecting": bool(n_graded_total == 0),
        "per_horizon": per_horizon,
        "rows": rows,
        "source_ledger": f"data/{LEDGER_DIRNAME}/",
    }


def write_track(payload: dict, path: str | Path | None = None) -> Path:
    """Write the display projection. Derived from committed state, so any lane may
    rebuild it — it can never advance the ledger, only re-describe it."""
    p = Path(path) if path is not None else TRACK_JSON
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=1, sort_keys=False, default=str))
    return p
