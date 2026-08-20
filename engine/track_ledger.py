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
Optional per-market row keys (consumers must tolerate their absence):
    xr exit reason · eb entry basis actually used (CN: t1_open|t1_hl2|t1_close) ·
    ed actual fill date (distinct from d, the surfaced date) · bd board definition/era ·
    er re-derived entry that DISAGREES with the published one, disclosed not substituted ·
    erw plain-word reason for that disagreement. eb/er/erw are the 2026-08-08 CN
    entry-price-integrity fields (see scripts/build_china_library._cn_ledger_rows).
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
#
# `unscored` = the desk admitted the name and can no longer price it. It exists so an
# admission is never DELETED from the book: pre-2026-08-05 an unpriceable episode was
# dropped outright, so VALE — five board dates in the buy lane, 6,131 closes sitting in
# data/yahoo/VALE.parquet — was simply absent from the dialog, indistinguishable from a
# name that had never been picked. An unscored row carries no numbers and enters no
# summary; it is the disclosure, not a result.
STATUS_VOCAB = ("up", "stopped", "flat", "early", "beat", "lag", "onboard", "unscored")

# The flag vocabulary the `fl` list is drawn from.
FLAG_VOCAB = ("locked", "susp", "delisted")

# The one ledger fenced by the era guard in atomic_write(). Duplicated from
# engine.track_era.GUARDED_BASENAME on purpose: the fail-closed branch runs when that
# module could not be imported, so it cannot ask the module for its own name. Pinned equal
# by tests/test_track_ledger_era.py.
ERA_GUARDED_LEDGER = "us_track_ledger.json"


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


def _board_ledger_row(gr: dict, name_lookup: dict) -> tuple[dict, bool, bool, bool]:
    """Build ONE JSON-ready ledger row from a board_ledger.grade() by_horizon entry.

    Shared by from_board_ledger_grade's current-era and legacy-era partitions
    (LEDGER-ERA track_ledger fence, 2026-08-20 review) so the two can never
    diverge in row SHAPE — only in which grade() rows feed each one. Returns
    (row_dict, suspended, matured, beat) — the three booleans let the caller
    tally its own era-scoped summary counters without re-deriving them.
    """
    tk = gr.get("ticker")
    d = gr.get("date")
    suspended = bool(gr.get("suspended"))
    excess = gr.get("excess_ret")
    matured = (excess is not None) and not suspended
    beat = bool(matured and excess > 0)

    fl: list[str] = []
    if suspended:
        fl.append("susp")

    if suspended or not matured:
        st = "early"  # suspended names have no grade; shown as early w/ susp flag
    else:
        st = "beat" if beat else "lag"

    disp = name_lookup.get(str(tk), {})
    fwd = gr.get("fwd_ret")
    row = {
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
        # Board-ledger rows already carry their selection-era stamp.  The popup
        # never needed it, but cross-product receipt consumers do: a legacy HK
        # call must not be relabelled as tonight's board.
        "bd": gr.get("board_definition"),
        "ed": gr.get("entry_date"),
    }
    return row, suspended, matured, beat


def _board_ledger_era_summary(state: str, rows: list[dict], n_susp: int,
                               n_matured: int, n_beat: int, n_lag: int,
                               first_read_est: str | None = None) -> dict:
    """The summary shape shared by from_board_ledger_grade's CURRENT-era summary
    and its prior_record's own summary (LEDGER-ERA track_ledger fence, 2026-08-20
    review). Carries this module's existing hit_matured/wilson_* vocabulary AND
    win_pct (0-100 scale) — the field _track_record_dlg.html.j2's prior-era
    ribbon actually reads (templates/_track_record_dlg.html.j2:1052-1064),
    mirroring engine.track_scoring.summarize's vocabulary (the CN producer;
    see scripts/build_china_library._cn_era_block). n_calls/n_logged are the
    ROW count of the era this summary describes, not the whole-ledger raw
    parquet count grade() reports — a pooled ledger-wide number has no place
    inside an era-scoped summary block (review 2026-08-20).
    """
    hit = round(n_beat / n_matured, 3) if n_matured else None
    wl, wh = wilson_ci(n_beat, n_matured)
    win_pct = round(hit * 100.0, 1) if hit is not None else None
    out = {
        "state": state,
        "n_calls": len(rows),
        "n_logged": len(rows),
        "n_matured": n_matured,
        "n_beat": n_beat,
        "n_lag": n_lag,
        "n_suspended": n_susp,
        "hit_matured": hit,
        "wilson_lo_pct": round(wl * 100.0, 1) if wl is not None else None,
        "wilson_hi_pct": round(wh * 100.0, 1) if wh is not None else None,
        "win_pct": win_pct,
    }
    if first_read_est is not None:
        out["first_read_est"] = first_read_est
    return out


def _board_ledger_prior_label(rows: list[dict]) -> tuple[str, str]:
    """Bilingual label for a board_ledger prior_record block, derived from the
    era's own date span (never hard-coded — see
    scripts/build_china_library._cn_era_label, the CN sibling this mirrors
    locally rather than importing, per packet §7.3's "implement locally").
    """
    dates = sorted(r["d"] for r in rows if r.get("d"))
    if not dates:
        return ("previous board definition", "上一版选股口径")
    d_from, d_to = dates[0], dates[-1]
    return (f"previous board definition · {d_from} – {d_to}",
            f"上一版选股口径 · {d_from} – {d_to}")


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
                                          bench_ret,excess_ret,suspended,
                                          board_definition}, ...], ...}}
    One ledger row per unique (date, ticker) — keyed off the 21d horizon list (the
    grading basis). Matured rows (excess_ret non-null): st='beat'/'lag' by sign,
    m=true, x=excess_ret*100. Suspended rows: fl=['susp'], excluded from summary.
    Unmatured, non-suspended: st='early', m=false, x=null (grade() carries no raw
    price to mark unrealized cheaply — honest null rather than a fabricated mark).

    scorecard() supplies the panel state ('accruing' | 'scored'), first_read_est,
    AND (as of LEDGER-ERA, 2026-08-20 review) the ERA FENCE: when
    scorecard['board_definition'] is not None, ONLY rows carrying that definition
    enter `rows`/`summary` — the same current-era scoping board_ledger.scorecard()
    itself already applies to n/n_buy/hit_rate_21d/by_group. Before this fix,
    from_board_ledger_grade re-pooled every era back together with no filter at
    all, publishing a competing, uncorrected win rate right beside the correctly
    scoped one in board_ledger.scorecard(). Rows outside the current era are
    NEVER dropped: they surface, in full, under the returned doc's top-level
    `prior_record` key — same block shape scripts/build_china_library._cn_era_block
    produces for CN (label_en/label_zh, board_definition, date_from/date_to,
    state, summary, rows, meta), so _track_record_dlg.html.j2's existing
    hasLegacy()/era-chip/prior-ribbon JS (already shipped for CN) lights up for
    HK/CA with zero template changes. When scorecard carries no definition (a
    ledger that never stamps, e.g. every legacy HK row, or any market pre-stamp)
    behavior is BYTE-IDENTICAL to before this fix: every row goes to `rows`, no
    `prior_record` key is added.

    name_lookup: {ticker: {"nm": .., "sec": .., "grp": ..}} display map (optional).
    """
    name_lookup = name_lookup or {}
    m = (market or "").upper()

    status = "accruing"
    first_read_est = None
    current_definition = None
    if isinstance(scorecard, dict):
        status = scorecard.get("status") or "accruing"
        first_read_est = scorecard.get("first_read_est")
        current_definition = scorecard.get("board_definition")
    # board_ledger uses 'accruing'/'scored'; the track_ledger `state` vocabulary is the
    # same 'accruing'/'scored'/'interim' set, so pass it through.
    state = status if status in ("accruing", "scored", "interim") else "accruing"

    cur_rows: list[dict] = []
    cur_n_susp = cur_n_beat = cur_n_lag = cur_n_matured = 0
    legacy_rows: list[dict] = []
    legacy_n_susp = legacy_n_beat = legacy_n_lag = legacy_n_matured = 0

    if isinstance(grade, dict) and grade.get("available"):
        h21 = (grade.get("by_horizon") or {}).get("21d") or []
        for gr in h21:
            tk = gr.get("ticker")
            d = gr.get("date")
            if not tk or not d:
                continue

            row, suspended, matured, beat = _board_ledger_row(gr, name_lookup)

            # ERA FENCE: only partition when the scorecard actually names a current
            # definition. When it does not (current_definition is None), EVERY row
            # goes to the current bucket unconditionally — never compare a row's
            # board_definition to None, which would misclassify an orphaned old
            # stamp as "legacy" on a ledger board_ledger.py itself still pools
            # (byte-identical requirement, packet §7.3).
            is_current = current_definition is None or row["bd"] == current_definition

            if is_current:
                cur_rows.append(row)
                if suspended:
                    cur_n_susp += 1
                elif matured:
                    cur_n_matured += 1
                    if beat:
                        cur_n_beat += 1
                    else:
                        cur_n_lag += 1
            else:
                legacy_rows.append(row)
                if suspended:
                    legacy_n_susp += 1
                elif matured:
                    legacy_n_matured += 1
                    if beat:
                        legacy_n_beat += 1
                    else:
                        legacy_n_lag += 1

    summary = _board_ledger_era_summary(
        state, cur_rows, cur_n_susp, cur_n_matured, cur_n_beat, cur_n_lag,
        first_read_est=first_read_est,
    )

    doc_as_of = as_of
    if doc_as_of is None and cur_rows:
        doc_as_of = max((r["d"] for r in cur_rows if r["d"]), default=None)

    doc = build_shell(
        m, doc_as_of, state, bench, summary, cur_rows, grain="board_day",
        survivorship={"n_suspended": cur_n_susp,
                      "note": "no delisting archive — vanished names leave the sample"},
    )

    # ── the prior-definition record, alongside and NEVER pooled ────────────────
    # Only when the scorecard names a current era AND at least one row fell
    # outside it — mirrors board_ledger.scorecard()'s own historical_context
    # gate exactly, and matches build_china_library's `if prior and
    # prior["rows"]:` gate for CN's prior_record.
    if current_definition is not None and legacy_rows:
        label_en, label_zh = _board_ledger_prior_label(legacy_rows)
        legacy_summary = _board_ledger_era_summary(
            state, legacy_rows, legacy_n_susp, legacy_n_matured,
            legacy_n_beat, legacy_n_lag,
        )
        dates = sorted(r["d"] for r in legacy_rows if r.get("d"))
        doc["prior_record"] = pyify({
            "label_en": label_en,
            "label_zh": label_zh,
            "board_definition": None,  # legacy pool may span several/no stamps
            "date_from": dates[0] if dates else None,
            "date_to": dates[-1] if dates else None,
            "state": state,
            "summary": legacy_summary,
            "rows": legacy_rows[:MAX_ROWS],
            "meta": {
                "n_total": len(legacy_rows),
                "truncated": max(0, len(legacy_rows) - MAX_ROWS),
                "grain": "board_day",
                "closed": False,  # HK/CA legacy pools may still receive backfill
                "survivorship": {"n_suspended": legacy_n_susp,
                                 "note": "no delisting archive — vanished names "
                                         "leave the sample"},
                "pooling_note_en": ("Graded with the same scorer and horizon as "
                                    "the current record, and reported "
                                    "separately. This era selected its board by "
                                    "a different rule, so the two must never be "
                                    "added together."),
                "pooling_note_zh": ("与当前记录采用相同的评分方法与持有期，但单独"
                                    "统计。该时期的选股口径不同，因此绝不可与上方"
                                    "记录合并计算。"),
            },
        })

    return doc


def _read_existing(path: Path) -> dict | None:
    """The doc currently published at `path`, or None if absent/unreadable.

    Unreadable is deliberately indistinguishable from absent HERE: the era guard treats a
    missing predecessor as "nothing has moved", which is the only honest reading when the
    old numbers cannot be recovered to compare against.
    """
    try:
        if not path.exists():
            return None
        obj = _json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception:  # noqa: BLE001 — a corrupt predecessor must not break the write path
        return None


def atomic_write(path: Path, doc: dict) -> bool:
    """Serialize `doc` to `path` via tmp-file + os.replace (never open('w') truncation —
    house law). Returns True on success. Never raises — a failed ledger write must not
    break a nightly render (the artifact bakes next run).

    `doc` must already be JSON-safe (build_shell guarantees this); we still pass
    default=str as a belt-and-braces guard so an unexpected type degrades instead of
    crashing the whole build.

    ERA GUARD (2026-08-07, fail-closed). Every writer of a track ledger goes through this
    function — house law forbids open('w') truncation — so it is the one place a publish
    refusal cannot be routed around. `engine.track_era.check_publish` fences
    `us_track_ledger.json` only: a write whose PUBLISHED headline moves beyond a small
    tolerance without carrying the active grading construction's `meta.anchor_era` is
    refused, the previously published file is left in place, and a line-start ::error
    annotation says so. Returns False on refusal, exactly like an IO failure — callers
    already treat a False as "the artifact bakes next run".
    """
    path = Path(path)
    tmp = None
    try:
        from engine import track_era as _era  # noqa: PLC0415 — keep import cost off cold paths

        ok, _why = _era.check_publish(path, doc, _read_existing(path))
    except Exception as e:  # noqa: BLE001 — see the two branches below
        # A guard that could not RUN is not a guard that passed. For the fenced artifact
        # that means refuse (the published file stays put — stale beats silently re-baked);
        # for the other three markets, which carry no ruled era boundary, a broken US guard
        # must not wedge their nightly, so they degrade to a warning and publish.
        if path.name == ERA_GUARDED_LEDGER:
            print(f"::error title=track-ledger-era::REFUSED to publish "
                  f"{ERA_GUARDED_LEDGER}: the era guard could not run ({e}). A guard that "
                  f"cannot run is not a pass — the previously published file is left in "
                  f"place. See engine/track_era.py.", flush=True)
            return False
        log.warning("track_ledger era guard skipped for %s: %s", path, e)
        ok = True
    if not ok:
        return False
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
