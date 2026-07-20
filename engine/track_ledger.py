"""Shared plumbing for the Track-record popup ledger artifacts (`track_ledger/v1`).

Four host pages (US / CN / HK / CA) each ship a compact per-episode ledger JSON that
the Track-record popup dashboard fetches lazily and renders as a filterable table +
verdict cards. The four emitters live in their respective build scripts
(scripts/grade_us_board.py, scripts/build_china_library.py, scripts/build_hk_library.py,
scripts/build_canada.py) because each one consumes data ALREADY in memory on its own
render path (render budget is law — no redundant store reads). This module holds the
ONE piece they share: the schema shell, the numpy→pure-Python cast, the newest-first
truncation, and the tmp+rename atomic write.

Why a shared module (not four inlined copies): the numpy-scalar trap — json.dumps
crashes (or, worse, silently poisons the file via default=str) on np.float64/np.int64.
Casting every value once, in one tested place, is the only safe way to guarantee the
four artifacts are JSON-serializable. Mirrors engine/risk_radar_scorecard.py's
multi-writer atomic-write pattern.

Schema (track_ledger/v1):
    { schema, market, as_of, state, bench:{code,en,zh}, summary:{...}, rows:[...], meta:{...} }
Row compact keys:
    t ticker · nm name · sec sector · grp group · d logged/surfaced date · e entry ·
    l latest/exit · p pct vs entry · x excess vs bench pct (null ok) · dy days ·
    st up|stopped|flat|early|beat|lag|onboard · m matured bool · rk rank · tr tier ·
    fl flags subset of [locked, susp, delisted]. Nulls allowed except t, d, st.
"""
from __future__ import annotations

import datetime as _dt
import json as _json
import logging as _logging
import math as _math
import os as _os
import tempfile as _tempfile
from pathlib import Path
from typing import Any

log = _logging.getLogger(__name__)

SCHEMA = "track_ledger/v1"

# Newest-first hard cap on emitted rows; meta.truncated discloses the drop count.
MAX_ROWS = 2000

# The status vocabulary the `st` field is drawn from. Emitters must stay inside it
# (the template's status filter chips and dot-legend key off exactly these).
STATUS_VOCAB = ("up", "stopped", "flat", "early", "beat", "lag", "onboard")

# The flag vocabulary the `fl` list is drawn from.
FLAG_VOCAB = ("locked", "susp", "delisted")


def pyify(obj: Any) -> Any:
    """Recursively coerce numpy scalars / NaN / pandas NA to pure-Python JSON types.

    The single most important function in this module. numpy scalars (np.float64,
    np.int64, np.bool_) are NOT instances of the built-in float/int/bool for json's
    purposes and either crash json.dumps or slip through `default=str` as ugly
    stringified reprs that poison the artifact. NaN / inf are coerced to None (null)
    so the JSON is strict-valid (json.dumps emits bare `NaN` which is invalid JSON
    for many consumers, including JS JSON.parse).

    Handles dict / list / tuple recursively. Anything already str/bool/None passes
    through. Unknown objects fall back to str() as a last resort (never crash).
    """
    # Fast path for the common leaf types (order matters: bool is an int subclass).
    if obj is None or isinstance(obj, (str, bool)):
        return obj
    # numpy / pandas scalars expose .item(); use it before the isinstance checks so
    # np.bool_ / np.int64 / np.float64 all collapse to their Python equivalents.
    item = getattr(obj, "item", None)
    if callable(item) and obj.__class__.__module__ == "numpy":
        try:
            obj = obj.item()
        except Exception:  # noqa: BLE001 — degrade to the generic handling below
            pass
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, int):
        return int(obj)
    if isinstance(obj, float):
        if _math.isnan(obj) or _math.isinf(obj):
            return None
        return float(obj)
    if isinstance(obj, dict):
        return {str(k): pyify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [pyify(v) for v in obj]
    # pandas NA / NaT probe FIRST — pd.NaT is a datetime subclass whose .isoformat()
    # returns the string 'NaT' (poisons the artifact), so it must collapse to null
    # BEFORE the datetime branch below.
    try:  # pandas may be present; a NaT/NA is not JSON-safe
        import pandas as _pd  # noqa: PLC0415
        if obj is _pd.NaT or _pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass  # pd.isna raised on an unrecognized type — fall through
    except Exception:  # noqa: BLE001
        pass
    # datetime / date → ISO string
    if isinstance(obj, (_dt.date, _dt.datetime)):
        if isinstance(obj, _dt.datetime):
            return obj.isoformat()
        return obj.isoformat()[:10]
    return str(obj)


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    """Wilson score interval for a binomial proportion. (None, None) when n == 0.

    Mirrors grade_us_board.wilson_ci / china_standout_track._wilson_ci — same z, same
    algebra — but returns None on the empty case (cleaner for JSON than NaN)."""
    if n <= 0:
        return (None, None)
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * _math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


def build_shell(
    market: str,
    as_of: str | None,
    state: str,
    bench: dict,
    summary: dict,
    rows: list[dict],
    grain: str,
    survivorship: dict | None = None,
    extra_meta: dict | None = None,
) -> dict:
    """Assemble the track_ledger/v1 dict: sort rows newest-first, cap to MAX_ROWS with
    a truncation count in meta, and coerce EVERYTHING to JSON-safe types via pyify.

    Rows are sorted by their `d` (logged/surfaced date) descending — newest first —
    so the cap keeps the most recent episodes (the ones a reader scrolling the popup
    sees first). Ties keep input order (stable sort).

    The returned dict is guaranteed json.dumps-safe with no `default=` needed. Callers
    still write via atomic_write() below.
    """
    rows = list(rows or [])
    # newest-first by logged date; missing/None dates sort last (treated as "").
    rows.sort(key=lambda r: (r.get("d") or ""), reverse=True)
    n_total = len(rows)
    truncated = 0
    if n_total > MAX_ROWS:
        truncated = n_total - MAX_ROWS
        rows = rows[:MAX_ROWS]

    meta: dict = {
        "n_total": n_total,
        "truncated": truncated,
        "grain": grain,
    }
    if survivorship is not None:
        meta["survivorship"] = survivorship
    if extra_meta:
        meta.update(extra_meta)

    doc = {
        "schema": SCHEMA,
        "market": market,
        "as_of": as_of,
        "state": state,
        "bench": bench,
        "summary": summary or {},
        "rows": rows,
        "meta": meta,
    }
    return pyify(doc)


def from_board_ledger_grade(
    market: str,
    grade: dict | None,
    scorecard: dict | None,
    bench: dict,
    name_lookup: dict | None = None,
    as_of: str | None = None,
) -> dict:
    """Build a track_ledger/v1 doc from an engine.board_ledger.grade(market) result
    (HK / CA). Consumes the grade() dict ALREADY computed on the build's render path —
    this function performs NO store reads and NO writes (board_ledger.grade already ran
    on the build path; re-running it would re-trigger its parquet write-back).

    grade() shape: {available, n_calls, n_graded, n_suspended,
                    by_horizon: {"21d": [{date,ticker,board_pos,group,edge_z,fwd_ret,
                                          bench_ret,excess_ret,suspended}, ...], ...}}
    One ledger row per unique (date, ticker) — keyed off the 21d horizon list (the
    grading basis). Matured rows (excess_ret non-null): st='beat'/'lag' by sign,
    m=true, x=excess_ret*100. Suspended rows: fl=['susp'], excluded from summary.
    Unmatured, non-suspended: st='early', m=false, x=null (grade() carries no raw
    price to mark unrealized cheaply — honest null rather than a fabricated mark).

    scorecard() supplies the panel state ('accruing' | 'scored') and first_read_est.
    name_lookup: {ticker: {"nm": .., "sec": .., "grp": ..}} display map (optional).
    """
    name_lookup = name_lookup or {}
    m = (market or "").upper()

    status = "accruing"
    first_read_est = None
    if isinstance(scorecard, dict):
        status = scorecard.get("status") or "accruing"
        first_read_est = scorecard.get("first_read_est")
    # board_ledger uses 'accruing'/'scored'; the track_ledger `state` vocabulary is the
    # same 'accruing'/'scored'/'interim' set, so pass it through.
    state = status if status in ("accruing", "scored", "interim") else "accruing"

    rows_out: list[dict] = []
    n_susp = 0
    n_beat = 0
    n_lag = 0
    n_matured = 0
    if isinstance(grade, dict) and grade.get("available"):
        h21 = (grade.get("by_horizon") or {}).get("21d") or []
        for gr in h21:
            tk = gr.get("ticker")
            d = gr.get("date")
            if not tk or not d:
                continue
            suspended = bool(gr.get("suspended"))
            excess = gr.get("excess_ret")
            matured = (excess is not None) and not suspended

            fl: list[str] = []
            if suspended:
                fl.append("susp")
                n_susp += 1

            if suspended:
                st = "early"  # suspended names have no grade; shown as early w/ susp flag
            elif matured:
                st = "beat" if excess > 0 else "lag"
                n_matured += 1
                if excess > 0:
                    n_beat += 1
                else:
                    n_lag += 1
            else:
                st = "early"

            disp = name_lookup.get(str(tk), {})
            fwd = gr.get("fwd_ret")
            rows_out.append({
                "t": tk,
                "nm": disp.get("nm"),
                "sec": disp.get("sec"),
                "grp": gr.get("group"),
                "d": d,
                "e": None,   # board_ledger grade carries no raw entry/latest price
                "l": None,
                "p": round(fwd * 100.0, 1) if (fwd is not None and not suspended) else None,
                "x": round(excess * 100.0, 2) if (excess is not None and not suspended) else None,
                "dy": 21 if matured else None,
                "st": st,
                "m": bool(matured),
                "rk": gr.get("board_pos") or None,
                "tr": None,
                "fl": fl,
            })

    hit = round(n_beat / n_matured, 3) if n_matured else None
    wl, wh = wilson_ci(n_beat, n_matured)
    summary = {
        "state": state,
        "n_calls": (grade or {}).get("n_calls") if isinstance(grade, dict) else len(rows_out),
        "n_logged": len(rows_out),
        "n_matured": n_matured,
        "n_beat": n_beat,
        "n_lag": n_lag,
        "n_suspended": n_susp,
        "hit_matured": hit,
        "wilson_lo_pct": round(wl * 100.0, 1) if wl is not None else None,
        "wilson_hi_pct": round(wh * 100.0, 1) if wh is not None else None,
        "first_read_est": first_read_est,
    }

    doc_as_of = as_of
    if doc_as_of is None and rows_out:
        doc_as_of = max((r["d"] for r in rows_out if r["d"]), default=None)

    return build_shell(
        m, doc_as_of, state, bench, summary, rows_out, grain="board_day",
        survivorship={"n_suspended": n_susp,
                      "note": "no delisting archive — vanished names leave the sample"},
    )


def atomic_write(path: Path, doc: dict) -> bool:
    """Serialize `doc` to `path` via tmp-file + os.replace (never open('w') truncation —
    house law). Returns True on success. Never raises — a failed ledger write must not
    break a nightly render (the artifact bakes next run).

    `doc` must already be JSON-safe (build_shell guarantees this); we still pass
    default=str as a belt-and-braces guard so an unexpected type degrades instead of
    crashing the whole build.
    """
    path = Path(path)
    tmp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _json.dumps(doc, ensure_ascii=False, indent=1, default=str)
        fd, tmp = _tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            _os.write(fd, payload.encode("utf-8"))
        finally:
            _os.close(fd)
        _os.replace(tmp, path)
        return True
    except Exception as e:  # noqa: BLE001 — additive artifact; never fatal
        log.warning("track_ledger atomic write to %s failed: %s", path, e)
        if tmp is not None:
            try:
                _os.unlink(tmp)
            except Exception:  # noqa: BLE001
                pass
        return False
