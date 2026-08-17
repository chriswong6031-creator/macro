"""Durable prospective W3 evidence ledger (PR-3C). Measurement plumbing only.

Accrues already-produced production C1 + v2-shadow paired observations, the one
shared grader (:func:`engine.us_prophet_grades.load_grades`), and the PR-3B
outcome-blind structural receipt. Writes three grains under
``data/us_prophet_rank/w3/``:

* ``paired/YYYY-MM/YYYY-MM-DD.parquet`` — one observation per
  ``(stamp_date, ticker, horizon)``. Horizon is H=10.
* ``family/YYYY-MM/YYYY-MM-DD.parquet`` — PR-3B LOFO receipt, serialized, never
  recomputed.
* ``coverage/YYYY-MM/YYYY-MM-DD.parquet`` — PR-3B member census, serialized.
* ``status.json`` — liveness pointer, rewritten nightly. Not an observation.

LAW (frozen by ``research/prophet_fusion/W3_RACE_PREREG.md``)
-------------------------------------------------------------
Population = canonical buy rows carrying both C1 and v2-shadow. Canonical =
``board_definition=us_prophet_v3`` + ``prophet_score`` / ``score_rank``.
Shadow = ``prophet_shadow_definition=us_prophet_v2_shadow`` + shadow score/rank.
Outcome = ``excess_spy`` vs SPY from the existing grader. One candidate row,
two rank columns, one grade row. No second scorer, no second grader, no
Pages backfill, no reconstructed history, no comparative statistic.

THIS MODULE HAS ZERO RANK / GATE / FEATURED / PLAN AUTHORITY. Nothing on the
live rank path may import it. The ranking engine itself must not write here;
PR-3B left the compact receipt on the board artifact and this ledger is the
only persistent W3 store, owned by the nightly ``us_prophet_ledgers`` job.

NIGHTLY IS THE SOLE ADVANCER. Every write gates on
``ledger_lane.nightly_advance_enabled()`` as its first statement.

APPEND-ONLY / IDEMPOTENT
------------------------
Observation identity is the economic/session grain
``(stamp_date, ticker, horizon)``, never a GitHub run id. Same-session retry
of an identical payload is a no-op. A conflicting rewrite of a frozen key
raises :class:`W3ConflictError` and prints both fingerprints. Unmatured H=10
is recorded with a pending (null) outcome — never fabricated as 0. Filling a
pending outcome when the identity fingerprint is unchanged is maturation, not
a rewrite. Null / missing / degraded is never coerced to zero or a tie.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from engine import ledger_lane
from engine import us_context_vector as ucv
from engine import us_prophet_grades as upg
from lib import config

log = logging.getLogger(__name__)

SCHEMA_PAIRED = "us.prophet_w3_paired/v1"
SCHEMA_FAMILY = "us.prophet_w3_family/v1"
SCHEMA_COVERAGE = "us.prophet_w3_coverage/v1"
SCHEMA_STATUS = "us.prophet_w3_status/v1"
STRUCTURAL_SCHEMA = "prophet_fusion.w3_structural.v1"

STORE_DIR = ucv.STORE_DIR
STORE_SUBDIR = "w3"

CANONICAL_BOARD = "us_prophet_v3"
SHADOW_DEFINITION = "us_prophet_v2_shadow"
FALLBACK_DEFINITION = "us_prophet_v2_fallback"
RETIRED_V2_BOARD = "us_prophet_v2"
PRIMARY_HORIZON = 10
BENCH = "SPY"
BUY_LANE = "buy"
SOURCE_CANDIDATES = "candidates_store"
SOURCE_GRADES = "grades_store"
SOURCE_RECEIPT = "board_fusion_receipt"

#: First durable post-#5769 paired stamp is the git event, not a peeked calendar
#: date. Pairing itself (null-shadow / pre-schema rows fail the filter) is the
#: start boundary. This SHA is recorded so a later reader does not invent one.
POST_5769_MERGE_SHA = "0233445657e8a6e40f3f5260d9cad7af4bb3e456"

PAIRED_KEY = ("stamp_date", "ticker", "horizon")
FAMILY_KEY = ("stamp_date", "family")
COVERAGE_KEY = ("stamp_date", "member")

#: Frozen identity of a paired observation. Outcome columns are deliberately
#: absent — filling a pending H=10 mark is maturation, not a new observation.
PAIRED_IDENTITY = (
    "stamp_date", "ticker", "horizon",
    "board_definition", "selection_era", "anchor_era", "stage",
    "prophet_score", "score_rank",
    "prophet_shadow_definition", "prophet_shadow_score", "prophet_shadow_score_rank",
    "benchmark", "schema",
)
PAIRED_OUTCOME = ("excess_spy", "fill_date", "mark_date", "graded_asof")

FAMILY_IDENTITY = (
    "stamp_date", "family", "active", "abstaining",
    "rows_contributing", "distinct_values", "modal_value", "modal_share",
    "dispersion", "mean_abs_rank_delta", "max_abs_rank_delta",
    "rows_moved", "top30_churn", "structural_schema",
)
COVERAGE_IDENTITY = (
    "stamp_date", "member", "family", "status", "coverage",
    "distinct_values", "variation_share", "presence_floor",
    "min_distinct_values", "min_variation_share", "reason", "source",
    "structural_schema",
)

LIVENESS_PAIRED_ACCRUED = "paired_accrued"
LIVENESS_UNMATURED = "unmatured"
LIVENESS_DEGRADED = "degraded_or_unpaired"
LIVENESS_MISSING = "session_missing"
LIVENESS_STATES = (
    LIVENESS_PAIRED_ACCRUED,
    LIVENESS_UNMATURED,
    LIVENESS_DEGRADED,
    LIVENESS_MISSING,
)

CANDIDATE_COLUMNS = (
    "stamp_date", "ticker", "board_definition", "selection_era", "anchor_era",
    "stage", "lane",
    "prophet_score", "score_rank",
    "prophet_shadow_definition", "prophet_shadow_score", "prophet_shadow_score_rank",
)
GRADE_COLUMNS = (
    "stamp_date", "ticker", "board_definition", "horizon",
    "excess_spy", "fill_date", "mark_date", "graded_asof", "bench",
)

_FORBIDDEN_SOURCE_TOKENS = (
    "pages", "reconstructed", "backfill", "http://", "https://",
)

STANDOUTS_REL = "site/factordata/us_standouts.json"
SNAPSHOTS_REL = "data/us_board_ledger/snapshots.jsonl"


class W3ConflictError(ValueError):
    """A frozen observation key was presented with a different identity payload."""

    def __init__(self, grain: str, key: tuple, existing_fp: str, incoming_fp: str,
                 existing: Mapping[str, Any], incoming: Mapping[str, Any]):
        self.grain = grain
        self.key = key
        self.existing_fp = existing_fp
        self.incoming_fp = incoming_fp
        self.existing = dict(existing)
        self.incoming = dict(incoming)
        super().__init__(
            f"W3 {grain} conflict on {key}: existing={existing_fp} incoming={incoming_fp}"
        )


class W3SchemaError(ValueError):
    """Structural receipt schema is missing or incompatible."""


class W3IntegrityError(ValueError):
    """Inputs are not a lawful W3 observation (mismatch, duplicates, Pages)."""


# --------------------------------------------------------------------------- #
# store
# --------------------------------------------------------------------------- #

def _repo_root(root: Any = None) -> Path:
    if root is None:
        return Path(config.ROOT)
    return Path(root)


def _data_root(root: Any = None) -> Path:
    if root is None:
        return Path(config.data_dir())
    return Path(root) / "data"


def _store_dir(root: Any = None) -> Path:
    return _data_root(root) / STORE_DIR / STORE_SUBDIR


def _part_path(grain: str, stamp_date: str, root: Any = None) -> Path:
    day = str(stamp_date)[:10]
    return _store_dir(root) / grain / day[:7] / f"{day}.parquet"


def status_path(root: Any = None) -> Path:
    return _store_dir(root) / "status.json"


def _coerce_null(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return value
    return value


def _canon_value(value: Any) -> Any:
    value = _coerce_null(value)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        # Ranks are integers in the wild; keep a stable 6-dp for scores.
        if value.is_integer() and abs(value) < 1e12:
            return int(value)
        return round(float(value), 10)
    if isinstance(value, str):
        return value
    return str(value)


def fingerprint(payload: Mapping[str, Any], keys: Iterable[str]) -> str:
    canon = {key: _canon_value(payload.get(key)) for key in keys}
    blob = json.dumps(canon, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _row_key(row: Mapping[str, Any], keys: Iterable[str]) -> tuple:
    return tuple(_canon_value(row.get(key)) for key in keys)


def _print_conflict(exc: W3ConflictError) -> None:
    print(
        f"::error title=w3-conflict::{exc.grain} key={exc.key} "
        f"existing={exc.existing_fp} incoming={exc.incoming_fp}",
        flush=True,
    )
    print(
        json.dumps({
            "grain": exc.grain,
            "key": [str(x) for x in exc.key],
            "existing_fingerprint": exc.existing_fp,
            "incoming_fingerprint": exc.incoming_fp,
            "existing": {k: _canon_value(v) for k, v in exc.existing.items()},
            "incoming": {k: _canon_value(v) for k, v in exc.incoming.items()},
        }, sort_keys=True, default=str),
        flush=True,
    )


def _outcome_pending(row: Mapping[str, Any]) -> bool:
    return _coerce_null(row.get("excess_spy")) is None


def _merge_keep_first(
    prior: pd.DataFrame,
    incoming: pd.DataFrame,
    *,
    key: tuple[str, ...],
    identity: tuple[str, ...],
    grain: str,
    allow_outcome_fill: bool,
) -> tuple[pd.DataFrame, int, int]:
    """Keep-first merge. Returns (frame, n_identical, n_matured).

    Identical payload → no-op row. Identity match + pending→filled (paired only)
    → maturation. Identity mismatch → :class:`W3ConflictError`.
    """
    if incoming.empty:
        return prior, 0, 0
    if prior.empty:
        return incoming.copy(), 0, 0

    prior_rows = prior.to_dict(orient="records")
    by_key: dict[tuple, dict] = {_row_key(row, key): dict(row) for row in prior_rows}
    identical = 0
    matured = 0
    changed = False
    for raw in incoming.to_dict(orient="records"):
        row = dict(raw)
        item_key = _row_key(row, key)
        existing = by_key.get(item_key)
        if existing is None:
            by_key[item_key] = row
            changed = True
            continue
        existing_fp = fingerprint(existing, identity)
        incoming_fp = fingerprint(row, identity)
        if existing_fp != incoming_fp:
            exc = W3ConflictError(grain, item_key, existing_fp, incoming_fp,
                                  existing, row)
            _print_conflict(exc)
            raise exc
        if allow_outcome_fill and _outcome_pending(existing) and not _outcome_pending(row):
            for column in PAIRED_OUTCOME:
                existing[column] = row.get(column)
            existing["source"] = row.get("source", existing.get("source"))
            by_key[item_key] = existing
            matured += 1
            changed = True
            continue
        # Same identity. If the incoming outcome disagrees with a frozen one, fail.
        if allow_outcome_fill:
            existing_out = fingerprint(existing, PAIRED_OUTCOME)
            incoming_out = fingerprint(row, PAIRED_OUTCOME)
            if (not _outcome_pending(existing)
                    and not _outcome_pending(row)
                    and existing_out != incoming_out):
                exc = W3ConflictError(
                    grain, item_key,
                    fingerprint(existing, identity + PAIRED_OUTCOME),
                    fingerprint(row, identity + PAIRED_OUTCOME),
                    existing, row)
                _print_conflict(exc)
                raise exc
        identical += 1
    if not changed:
        return prior, identical, matured
    merged = pd.DataFrame(list(by_key.values()))
    return merged, identical, matured


def _write_part(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(tmp, index=False)
    tmp.replace(path)


def _load_grain(grain: str, root: Any = None) -> pd.DataFrame:
    store = _store_dir(root) / grain
    if not store.exists():
        return pd.DataFrame()
    frames: list[pd.DataFrame] = []
    for part in sorted(store.glob("*/*.parquet")):
        try:
            frames.append(pd.read_parquet(part))
        except Exception as exc:  # noqa: BLE001
            log.warning("us_prophet_w3: part %s unreadable (%s)", part, exc)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_paired(root: Any = None) -> pd.DataFrame:
    return _load_grain("paired", root)


def load_family(root: Any = None) -> pd.DataFrame:
    return _load_grain("family", root)


def load_coverage(root: Any = None) -> pd.DataFrame:
    return _load_grain("coverage", root)


def _append_grain(
    rows: list[dict],
    *,
    grain: str,
    key: tuple[str, ...],
    identity: tuple[str, ...],
    allow_outcome_fill: bool,
    root: Any = None,
) -> dict[str, int]:
    if not ledger_lane.nightly_advance_enabled():
        log.info("us_prophet_w3 %s append gated — not the US nightly lane", grain)
        return {"written": 0, "identical": 0, "matured": 0, "stamps": 0}
    if not rows:
        return {"written": 0, "identical": 0, "matured": 0, "stamps": 0}

    incoming = pd.DataFrame(rows)
    incoming = incoming.sort_values(list(key), kind="mergesort").reset_index(drop=True)
    written = 0
    identical = 0
    matured = 0
    stamps = 0
    for stamp, group in incoming.groupby(incoming["stamp_date"].map(lambda v: str(v)[:10]),
                                         sort=True):
        path = _part_path(grain, str(stamp), root)
        prior = pd.read_parquet(path) if path.exists() else pd.DataFrame()
        merged, n_ident, n_mat = _merge_keep_first(
            prior, group.reset_index(drop=True),
            key=key, identity=identity, grain=grain,
            allow_outcome_fill=allow_outcome_fill)
        identical += n_ident
        matured += n_mat
        if prior.empty and merged.empty:
            continue
        if (not prior.empty and len(prior) == len(merged)
                and list(prior.columns) == list(merged.columns)
                and prior.sort_values(list(key), kind="mergesort")
                .reset_index(drop=True)
                .equals(merged.sort_values(list(key), kind="mergesort")
                        .reset_index(drop=True))):
            identical += max(0, len(group) - n_ident)
            continue
        merged = merged.sort_values(list(key), kind="mergesort").reset_index(drop=True)
        _write_part(path, merged)
        written += int(len(merged) - (0 if prior.empty else len(prior))) + n_mat
        stamps += 1
    return {"written": written, "identical": identical, "matured": matured,
            "stamps": stamps}


def append_paired(rows: list[dict], root: Any = None) -> dict[str, int]:
    return _append_grain(
        rows, grain="paired", key=PAIRED_KEY, identity=PAIRED_IDENTITY,
        allow_outcome_fill=True, root=root)


def append_family(rows: list[dict], root: Any = None) -> dict[str, int]:
    return _append_grain(
        rows, grain="family", key=FAMILY_KEY, identity=FAMILY_IDENTITY,
        allow_outcome_fill=False, root=root)


def append_coverage(rows: list[dict], root: Any = None) -> dict[str, int]:
    return _append_grain(
        rows, grain="coverage", key=COVERAGE_KEY, identity=COVERAGE_IDENTITY,
        allow_outcome_fill=False, root=root)


# --------------------------------------------------------------------------- #
# pairing
# --------------------------------------------------------------------------- #

def _require_committed_source(label: str, value: Any) -> None:
    text = str(value or "").strip().lower()
    if not text:
        return
    for token in _FORBIDDEN_SOURCE_TOKENS:
        if token in text:
            raise W3IntegrityError(
                f"W3 refuses {label}={value!r} — Pages-only / reconstructed / "
                "backfilled input cannot enter the durable race store")


def _is_finite_number(value: Any) -> bool:
    value = _coerce_null(value)
    if value is None or isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return number == number and number not in (float("inf"), float("-inf"))


def qualify_paired_candidates(candidates: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Apply the frozen W3 pairing filter. Does not invent outcomes."""
    doc = {
        "n_in": 0, "n_paired": 0,
        "excluded_definition": 0, "excluded_fallback": 0,
        "excluded_null_shadow": 0, "excluded_null_canonical": 0,
        "excluded_off_board": 0, "excluded_source": 0,
    }
    if candidates is None or candidates.empty:
        return pd.DataFrame(), doc
    frame = candidates.copy()
    doc["n_in"] = int(len(frame))
    if "source" in frame.columns:
        bad = frame["source"].map(
            lambda v: any(tok in str(v or "").lower() for tok in _FORBIDDEN_SOURCE_TOKENS))
        doc["excluded_source"] = int(bad.sum())
        if int(bad.sum()):
            raise W3IntegrityError(
                "W3 refuses Pages-only / reconstructed / backfilled candidate rows "
                f"({int(bad.sum())} row(s)) — durable store only")
    for column in ("stamp_date", "ticker"):
        if column not in frame.columns:
            raise W3IntegrityError(f"candidates missing required column {column}")

    definition = (frame["board_definition"].astype(str)
                  if "board_definition" in frame.columns
                  else pd.Series([""] * len(frame), index=frame.index))
    lane = (frame["lane"].astype(str)
            if "lane" in frame.columns
            else pd.Series([""] * len(frame), index=frame.index))
    shadow_def = (frame["prophet_shadow_definition"].astype(object)
                  if "prophet_shadow_definition" in frame.columns
                  else pd.Series([None] * len(frame), index=frame.index))

    off_board = lane != BUY_LANE
    fallback = definition.isin([FALLBACK_DEFINITION, RETIRED_V2_BOARD])
    not_v3 = definition != CANONICAL_BOARD
    null_canonical = ~(
        frame.get("prophet_score", pd.Series(index=frame.index)).map(_is_finite_number)
        & frame.get("score_rank", pd.Series(index=frame.index)).map(_is_finite_number)
    )
    null_shadow = ~(
        shadow_def.map(lambda v: str(v) == SHADOW_DEFINITION if _coerce_null(v) is not None else False)
        & frame.get("prophet_shadow_score", pd.Series(index=frame.index)).map(_is_finite_number)
        & frame.get("prophet_shadow_score_rank", pd.Series(index=frame.index)).map(_is_finite_number)
    )

    doc["excluded_off_board"] = int(off_board.sum())
    doc["excluded_fallback"] = int((fallback & ~off_board).sum())
    doc["excluded_definition"] = int((not_v3 & ~fallback & ~off_board).sum())
    doc["excluded_null_canonical"] = int((~not_v3 & ~off_board & null_canonical).sum())
    doc["excluded_null_shadow"] = int(
        (~not_v3 & ~off_board & ~null_canonical & null_shadow).sum())

    keep = (~off_board & ~not_v3 & ~null_canonical & ~null_shadow)
    paired = frame.loc[keep].copy()
    doc["n_paired"] = int(len(paired))
    return paired, doc


def _prepare_grades(grades: pd.DataFrame) -> pd.DataFrame:
    if grades is None or grades.empty:
        return pd.DataFrame(columns=list(GRADE_COLUMNS))
    frame = grades.copy()
    if "horizon" not in frame.columns:
        raise W3IntegrityError("grades missing required column horizon")
    frame["horizon"] = pd.to_numeric(frame["horizon"], errors="coerce")
    frame = frame.loc[frame["horizon"] == PRIMARY_HORIZON].copy()
    frame["stamp_date"] = frame["stamp_date"].astype(str).str.slice(0, 10)
    frame["ticker"] = frame["ticker"].astype(str)
    if "board_definition" in frame.columns:
        frame["board_definition"] = frame["board_definition"].astype(str)
    key_cols = ["stamp_date", "ticker", "board_definition", "horizon"]
    dup = frame.duplicated(subset=key_cols, keep=False)
    if int(dup.sum()):
        # Identical duplicates collapse; incompatible duplicates fail closed.
        conflicted = []
        for _, group in frame.loc[dup].groupby(key_cols, dropna=False):
            fps = {fingerprint(row, ("excess_spy", "fill_date", "mark_date", "bench"))
                   for row in group.to_dict(orient="records")}
            if len(fps) > 1:
                conflicted.append(tuple(group.iloc[0][c] for c in key_cols))
        if conflicted:
            raise W3IntegrityError(
                "grader produced duplicate incompatible outcome rows for "
                f"{conflicted[:5]}{'…' if len(conflicted) > 5 else ''}")
        frame = frame.drop_duplicates(subset=key_cols, keep="first")
    return frame


def build_paired_rows(
    candidates: pd.DataFrame,
    grades: pd.DataFrame,
    *,
    source: str = SOURCE_CANDIDATES,
) -> tuple[list[dict], dict]:
    """One paired observation per qualified (stamp_date, ticker) at H=10.

    One grade row serves both rank columns. Missing H=10 grade → pending outcome,
    never 0. Does not compute a return.
    """
    _require_committed_source("source", source)
    paired, qualify = qualify_paired_candidates(candidates)
    doc = dict(qualify)
    doc.update({"n_grades_in": 0 if grades is None else int(len(grades)),
                "n_joined": 0, "n_pending": 0, "horizon": PRIMARY_HORIZON})
    if paired.empty:
        return [], doc

    prepared = _prepare_grades(grades)
    doc["n_grades_in"] = int(len(prepared))

    paired = paired.copy()
    paired["stamp_date"] = paired["stamp_date"].astype(str).str.slice(0, 10)
    paired["ticker"] = paired["ticker"].astype(str)
    paired["board_definition"] = paired["board_definition"].astype(str)
    paired["_horizon"] = PRIMARY_HORIZON

    if not prepared.empty:
        overlap = prepared.merge(
            paired[["stamp_date", "ticker"]],
            on=["stamp_date", "ticker"], how="inner")
        if "board_definition" in overlap.columns and not overlap.empty:
            cand_def = paired.set_index(["stamp_date", "ticker"])["board_definition"]
            for row in overlap.itertuples(index=False):
                key = (str(row.stamp_date)[:10], str(row.ticker))
                if key in cand_def.index:
                    expected = cand_def.loc[key]
                    if isinstance(expected, pd.Series):
                        expected = expected.iloc[0]
                    got = str(getattr(row, "board_definition", ""))
                    if got and str(expected) != got:
                        raise W3IntegrityError(
                            f"candidate/grade board-definition mismatch on {key}: "
                            f"candidate={expected!r} grade={got!r}")

    grade_keep = [c for c in GRADE_COLUMNS if c in prepared.columns]
    left = paired.merge(
        prepared[grade_keep] if grade_keep else prepared,
        left_on=["stamp_date", "ticker", "board_definition", "_horizon"],
        right_on=["stamp_date", "ticker", "board_definition", "horizon"],
        how="left",
        suffixes=("", "_grade"),
    )
    # Permutation invariance: ticker order of the candidate frame must not matter.
    left = left.sort_values(["stamp_date", "ticker"], kind="mergesort")

    rows: list[dict] = []
    for raw in left.to_dict(orient="records"):
        excess = _coerce_null(raw.get("excess_spy"))
        pending = excess is None
        if pending:
            doc["n_pending"] += 1
        else:
            doc["n_joined"] += 1
        rows.append({
            "schema": SCHEMA_PAIRED,
            "stamp_date": str(raw["stamp_date"])[:10],
            "ticker": str(raw["ticker"]),
            "board_definition": CANONICAL_BOARD,
            "selection_era": _coerce_null(raw.get("selection_era")),
            "anchor_era": _coerce_null(raw.get("anchor_era")),
            "stage": _coerce_null(raw.get("stage")),
            "prophet_score": _canon_value(raw.get("prophet_score")),
            "score_rank": _canon_value(raw.get("score_rank")),
            "prophet_shadow_definition": SHADOW_DEFINITION,
            "prophet_shadow_score": _canon_value(raw.get("prophet_shadow_score")),
            "prophet_shadow_score_rank": _canon_value(raw.get("prophet_shadow_score_rank")),
            "horizon": PRIMARY_HORIZON,
            "excess_spy": _canon_value(excess),
            "benchmark": BENCH,
            "fill_date": _coerce_null(raw.get("fill_date")),
            "mark_date": _coerce_null(raw.get("mark_date")),
            "graded_asof": _coerce_null(raw.get("graded_asof")),
            "source": f"{SOURCE_CANDIDATES}+{SOURCE_GRADES}",
            "identity_fingerprint": None,  # filled below
        })
    for row in rows:
        row["identity_fingerprint"] = fingerprint(row, PAIRED_IDENTITY)
    doc["n_out"] = len(rows)
    return rows, doc


# --------------------------------------------------------------------------- #
# structural receipt → family / coverage (no LOFO recomputation)
# --------------------------------------------------------------------------- #

def _require_structural_schema(receipt: Mapping[str, Any]) -> None:
    schema = receipt.get("schema")
    if schema != STRUCTURAL_SCHEMA:
        raise W3SchemaError(
            f"structural schema unknown/incompatible: {schema!r} "
            f"(expected {STRUCTURAL_SCHEMA})")


def family_rows_from_receipt(stamp_date: str, receipt: Mapping[str, Any] | None,
                             ) -> list[dict]:
    """Serialize the PR-3B LOFO block. Does not recompute displacement."""
    if receipt is None:
        return []
    _require_structural_schema(receipt)
    stamp = str(stamp_date)[:10]
    present = {str(name) for name in (receipt.get("families_present") or [])}
    absent = {}
    for item in receipt.get("families_absent") or []:
        if isinstance(item, Mapping):
            name = str(item.get("family") or "")
            if name:
                absent[name] = dict(item)
    rows: list[dict] = []
    seen: set[str] = set()
    for item in receipt.get("lofo") or []:
        family = str(item.get("family") or "")
        if not family:
            continue
        seen.add(family)
        active = family in present
        rows.append({
            "schema": SCHEMA_FAMILY,
            "stamp_date": stamp,
            "family": family,
            "active": bool(active),
            "abstaining": (not active),
            "rows_contributing": _canon_value(item.get("rows_carrying")),
            "distinct_values": _canon_value(item.get("distinct_values")),
            "modal_value": _canon_value(item.get("modal_value")),
            "modal_share": _canon_value(item.get("modal_share")),
            "dispersion": _canon_value(item.get("dispersion")),
            "mean_abs_rank_delta": _canon_value(item.get("mean_abs_rank_displacement")),
            "max_abs_rank_delta": _canon_value(item.get("max_abs_rank_displacement")),
            "rows_moved": _canon_value(item.get("rows_moved")),
            "top30_churn": _canon_value(item.get("top30_churn")),
            "structural_schema": STRUCTURAL_SCHEMA,
            "source": SOURCE_RECEIPT,
        })
    # Abstaining families have no LOFO displacement. Persist the receipt fact
    # with null LOFO fields — never a coerced 0.
    for family, info in sorted(absent.items()):
        if family in seen:
            continue
        rows.append({
            "schema": SCHEMA_FAMILY,
            "stamp_date": stamp,
            "family": family,
            "active": False,
            "abstaining": True,
            "rows_contributing": None,
            "distinct_values": None,
            "modal_value": None,
            "modal_share": None,
            "dispersion": None,
            "mean_abs_rank_delta": None,
            "max_abs_rank_delta": None,
            "rows_moved": None,
            "top30_churn": None,
            "reason": info.get("reason"),
            "structural_schema": STRUCTURAL_SCHEMA,
            "source": SOURCE_RECEIPT,
        })
    rows.sort(key=lambda row: (row["stamp_date"], row["family"]))
    return rows


def coverage_rows_from_receipt(stamp_date: str, receipt: Mapping[str, Any] | None,
                               ) -> list[dict]:
    """Serialize the PR-3B member census. Outcome-blind; no grade join."""
    if receipt is None:
        return []
    _require_structural_schema(receipt)
    stamp = str(stamp_date)[:10]
    rows: list[dict] = []
    for item in receipt.get("census") or []:
        thresholds = item.get("thresholds") or {}
        rows.append({
            "schema": SCHEMA_COVERAGE,
            "stamp_date": stamp,
            "member": item.get("member"),
            "family": item.get("family"),
            "status": item.get("status"),
            "coverage": _canon_value(item.get("coverage")),
            "distinct_values": _canon_value(item.get("distinct_values")),
            "variation_share": _canon_value(item.get("variation_share")),
            "presence_floor": _canon_value(thresholds.get("presence_floor")),
            "min_distinct_values": _canon_value(thresholds.get("min_distinct_values")),
            "min_variation_share": _canon_value(thresholds.get("min_variation_share")),
            "reason": item.get("reason"),
            "source": item.get("source") or SOURCE_RECEIPT,
            "staleness_basis": item.get("staleness_basis"),
            "structural_schema": STRUCTURAL_SCHEMA,
        })
    rows.sort(key=lambda row: (row["stamp_date"], str(row.get("member") or "")))
    return rows


def _read_json(path: Path) -> Any:
    _require_committed_source("path", path)
    if str(path).startswith(("http://", "https://")):
        raise W3IntegrityError("W3 refuses a network path for the structural receipt")
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def extract_structural_receipt(payload: Mapping[str, Any] | None) -> dict | None:
    if not isinstance(payload, Mapping):
        return None
    ranking = payload.get("ranking") if isinstance(payload.get("ranking"), Mapping) else payload
    fusion = (ranking or {}).get("fusion") if isinstance(ranking, Mapping) else None
    if not isinstance(fusion, Mapping):
        return None
    block = fusion.get("w3_structural")
    if not isinstance(block, Mapping):
        return None
    return dict(block)


def load_committed_structural_receipt(stamp_date: str, root: Any = None) -> dict | None:
    """Read the PR-3B receipt from git-committed board artifacts only.

    Never fetches Pages. A missing artifact is a structural gap, not a zero.
    """
    stamp = str(stamp_date)[:10]
    repo = _repo_root(root)
    standouts = repo / STANDOUTS_REL
    payload = _read_json(standouts) if standouts.exists() else None
    if isinstance(payload, Mapping):
        as_of = str(payload.get("as_of") or payload.get("asof") or "")[:10]
        if as_of == stamp:
            block = extract_structural_receipt(payload)
            if block is not None:
                _require_structural_schema(block)
                return block
    snapshots = repo / SNAPSHOTS_REL
    if snapshots.exists():
        _require_committed_source("path", snapshots)
        with snapshots.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(item, Mapping):
                    continue
                as_of = str(item.get("as_of") or item.get("asof") or "")[:10]
                if as_of != stamp:
                    continue
                block = extract_structural_receipt(item)
                if block is not None:
                    _require_structural_schema(block)
                    return block
    return None


# --------------------------------------------------------------------------- #
# liveness / status (no comparative outcome)
# --------------------------------------------------------------------------- #

def _session_liveness(stamp: str, *,
                      in_candidates: bool,
                      n_v3_buy: int,
                      n_paired: int,
                      n_pending: int,
                      degraded: bool) -> dict[str, Any]:
    if not in_candidates:
        state = LIVENESS_MISSING
        reason = "candidate session missing from the durable store; not pulled from Pages"
    elif degraded or n_v3_buy == 0 or n_paired == 0:
        state = LIVENESS_DEGRADED
        reason = ("fallback/degraded/unpaired session excluded from the paired race; "
                  "not a zero and not a tie")
    elif n_pending:
        state = LIVENESS_UNMATURED
        reason = "paired observation accrued; H=10 outcome pending (not zero)"
    else:
        state = LIVENESS_PAIRED_ACCRUED
        reason = "paired H=10 observation accrued with shared-grader outcome"
    return {
        "stamp_date": stamp,
        "liveness": state,
        "n_v3_buy_rows": n_v3_buy,
        "n_paired": n_paired,
        "n_pending_outcome": n_pending,
        "reason": reason,
    }


def write_status(doc: Mapping[str, Any], root: Any = None) -> bool:
    if not ledger_lane.nightly_advance_enabled():
        log.info("us_prophet_w3 status gated — not the US nightly lane")
        return False
    path = status_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(doc)
    payload.setdefault("schema", SCHEMA_STATUS)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
                    encoding="utf-8")
    return True


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #

def _candidate_columns_present(root: Any) -> list[str]:
    wanted = list(CANDIDATE_COLUMNS)
    return wanted


def accrue(root: Any = None, *,
           dry_run: bool = False,
           candidates: pd.DataFrame | None = None,
           grades: pd.DataFrame | None = None,
           structural_by_stamp: Mapping[str, Mapping[str, Any] | None] | None = None,
           require_stamp: str | None = None) -> dict[str, Any]:
    """Accrue paired + structural grains. Never emits a comparative W3 read."""
    doc: dict[str, Any] = {
        "schema": SCHEMA_STATUS,
        "dry_run": bool(dry_run),
        "horizon": PRIMARY_HORIZON,
        "benchmark": BENCH,
        "canonical_board": CANONICAL_BOARD,
        "shadow_definition": SHADOW_DEFINITION,
        "grader": "engine.us_prophet_grades.load_grades",
        "post_5769_merge_sha": POST_5769_MERGE_SHA,
        "comparison_surface": "forbidden",
        "paired": {},
        "family": {},
        "coverage": {},
        "sessions": [],
        "honest_n_matured_h10_sessions": 0,
        "note": (
            "W3 measurement plumbing. Accrual/maturity/gap status only. "
            "No C1 IC, no shadow IC, no delta, no p-value, no leader."
        ),
        "degraded": [],
    }
    if require_stamp:
        _require_committed_source("require_stamp", require_stamp)

    if candidates is None:
        wanted = _candidate_columns_present(root)
        candidates = ucv.load_candidates(root, columns=wanted)
    if grades is None:
        grades = upg.load_grades(root, columns=list(GRADE_COLUMNS))

    if candidates is None or candidates.empty:
        if require_stamp:
            raise W3IntegrityError(
                f"workflow cannot identify a durable candidate stamp {require_stamp!r} "
                "— refusing Pages backfill")
        doc["note"] = (
            "no candidate rows in the durable store — nothing accrued; "
            "gaps remain gaps")
        doc["sessions"] = []
        if not dry_run:
            write_status(doc, root)
        return doc

    paired_rows, pair_doc = build_paired_rows(candidates, grades)
    doc["paired_qualify"] = pair_doc

    # Session census over candidate stamps (durable store only).
    frame = candidates.copy()
    frame["stamp_date"] = frame["stamp_date"].astype(str).str.slice(0, 10)
    stamps = sorted(set(frame["stamp_date"].dropna().tolist()))
    if require_stamp:
        want = str(require_stamp)[:10]
        if want not in stamps:
            raise W3IntegrityError(
                f"workflow cannot identify a durable candidate stamp {want!r} "
                "— refusing Pages backfill")

    paired_by_stamp: dict[str, list[dict]] = {}
    for row in paired_rows:
        paired_by_stamp.setdefault(row["stamp_date"], []).append(row)

    family_rows: list[dict] = []
    coverage_rows: list[dict] = []
    sessions: list[dict] = []

    definition = (frame["board_definition"].astype(str)
                  if "board_definition" in frame.columns
                  else pd.Series([""] * len(frame), index=frame.index))
    lane = (frame["lane"].astype(str)
            if "lane" in frame.columns
            else pd.Series([""] * len(frame), index=frame.index))

    for stamp in stamps:
        mask = frame["stamp_date"] == stamp
        defs = set(definition.loc[mask].tolist())
        degraded = FALLBACK_DEFINITION in defs and CANONICAL_BOARD not in defs
        n_v3_buy = int(((definition.loc[mask] == CANONICAL_BOARD)
                        & (lane.loc[mask] == BUY_LANE)).sum())
        stamp_paired = paired_by_stamp.get(stamp, [])
        n_pending = sum(1 for row in stamp_paired if _outcome_pending(row))
        sessions.append(_session_liveness(
            stamp, in_candidates=True, n_v3_buy=n_v3_buy,
            n_paired=len(stamp_paired), n_pending=n_pending, degraded=degraded))

        receipt: Mapping[str, Any] | None
        if structural_by_stamp is not None:
            if stamp in structural_by_stamp:
                receipt = structural_by_stamp[stamp]
            else:
                receipt = None
        else:
            receipt = load_committed_structural_receipt(stamp, root)
        if receipt is not None:
            family_rows.extend(family_rows_from_receipt(stamp, receipt))
            coverage_rows.extend(coverage_rows_from_receipt(stamp, receipt))
        elif degraded:
            # Fallback nights have no canonical W3 structural observation.
            pass

    if require_stamp and str(require_stamp)[:10] not in stamps:
        sessions.append(_session_liveness(
            str(require_stamp)[:10], in_candidates=False, n_v3_buy=0,
            n_paired=0, n_pending=0, degraded=False))

    matured = {s["stamp_date"] for s in sessions
               if s["liveness"] == LIVENESS_PAIRED_ACCRUED}
    doc["honest_n_matured_h10_sessions"] = len(matured)
    doc["sessions"] = sessions
    doc["n_paired_rows"] = len(paired_rows)
    doc["n_family_rows"] = len(family_rows)
    doc["n_coverage_rows"] = len(coverage_rows)

    if dry_run:
        doc["paired"] = {"written": 0, "identical": 0, "matured": 0, "stamps": 0}
        doc["family"] = {"written": 0, "identical": 0, "matured": 0, "stamps": 0}
        doc["coverage"] = {"written": 0, "identical": 0, "matured": 0, "stamps": 0}
        return doc

    doc["paired"] = append_paired(paired_rows, root)
    doc["family"] = append_family(family_rows, root)
    doc["coverage"] = append_coverage(coverage_rows, root)
    write_status(doc, root)
    return doc


def summary_line(doc: Mapping[str, Any]) -> str:
    paired = doc.get("paired") or {}
    return (
        f"w3 ledger: paired_rows={doc.get('n_paired_rows', 0)} "
        f"family_rows={doc.get('n_family_rows', 0)} "
        f"coverage_rows={doc.get('n_coverage_rows', 0)} "
        f"written_paired={paired.get('written', 0)} "
        f"identical={paired.get('identical', 0)} "
        f"matured_fill={paired.get('matured', 0)} "
        f"sessions={len(doc.get('sessions') or [])} "
        f"honest_n_matured_h10={doc.get('honest_n_matured_h10_sessions', 0)} "
        f"(comparison forbidden)"
    )
