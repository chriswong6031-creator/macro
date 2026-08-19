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
SCHEMA_SESSION = "us.prophet_w3_session/v1"
STRUCTURAL_SCHEMA = "prophet_fusion.w3_structural.v1"
HONEST_N_FLOOR = 20

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
#: session_missing and degraded_or_unpaired are terminal W3 race dispositions.
#: A later generic product backfill (#5878) must not resurrect them as race sessions.
TERMINAL_LIVENESS = (LIVENESS_MISSING, LIVENESS_DEGRADED)
LAWFUL_LIVENESS_TRANSITION = {(LIVENESS_UNMATURED, LIVENESS_PAIRED_ACCRUED)}
#: Tokens the pre-floor status surface must never emit. Sealed: we do not
#: compute hidden comparison statistics and hide them; we do not compute them.
FORBIDDEN_STATUS_TOKENS = (
    "IC_C1", "IC_shadow", "delta IC", "delta_ic", "ΔIC",
    "p-value", "pvalue", "p_value",
    "HAC", "confidence interval", "confidence_interval",
    "who is winning", "leader", "winner",
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


def sessions_path(root: Any = None) -> Path:
    return _store_dir(root) / "sessions.jsonl"


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
    """Refuse Pages/reconstructed/backfill *inputs*, not coincidental path substrings.

    Filesystem paths to git-committed artifacts are legal even when a pytest tmp
    directory or a folder name happens to contain ``pages``. Network URLs and
    candidate ``source`` fields are what this fence actually polices.
    """
    if isinstance(value, Path):
        text = str(value)
        if text.startswith(("http://", "https://")):
            raise W3IntegrityError(
                f"W3 refuses {label}={value!r} — Pages-only / reconstructed / "
                "backfilled input cannot enter the durable race store")
        return
    text = str(value or "").strip().lower()
    if not text:
        return
    if text.startswith("/") or text.startswith("data/") or text.startswith("site/"):
        if text.startswith(("http://", "https://")):
            raise W3IntegrityError(
                f"W3 refuses {label}={text!r} — Pages-only / reconstructed / "
                "backfilled input cannot enter the durable race store")
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
    _assert_no_comparison_payload(payload)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
                    encoding="utf-8")
    return True


def _assert_no_comparison_payload(payload: Mapping[str, Any]) -> None:
    text = json.dumps(payload, default=str)
    lowered = text.lower()
    for token in FORBIDDEN_STATUS_TOKENS:
        if token.lower() in lowered:
            raise W3IntegrityError(
                f"W3 status surface refused forbidden comparison token {token!r} "
                "before the honest-N floor")


def load_sessions(root: Any = None) -> list[dict[str, Any]]:
    path = sessions_path(root)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        if isinstance(item, Mapping):
            rows.append(dict(item))
    return rows


def sessions_by_stamp(root: Any = None) -> dict[str, dict[str, Any]]:
    """Current disposition per stamp_date. Keep-first, then lawful maturation only."""
    by: dict[str, dict[str, Any]] = {}
    for row in load_sessions(root):
        stamp = str(row.get("stamp_date") or "")[:10]
        if len(stamp) != 10:
            continue
        existing = by.get(stamp)
        if existing is None:
            by[stamp] = dict(row)
            continue
        prior = str(existing.get("liveness") or "")
        incoming = str(row.get("liveness") or "")
        if (prior, incoming) in LAWFUL_LIVENESS_TRANSITION:
            by[stamp] = dict(row)
    return by


def is_terminal_excluded(stamp: str, root: Any = None) -> dict[str, Any] | None:
    rec = sessions_by_stamp(root).get(str(stamp)[:10])
    if rec and rec.get("liveness") in TERMINAL_LIVENESS:
        return rec
    return None


def append_sessions(records: Iterable[Mapping[str, Any]], root: Any = None) -> dict[str, int]:
    """Append-only session dispositions. Terminal states cannot become race sessions."""
    if not ledger_lane.nightly_advance_enabled():
        log.info("us_prophet_w3 sessions append gated — not the US nightly lane")
        return {"written": 0, "identical": 0, "matured": 0, "refused": 0}
    incoming = [dict(row) for row in records]
    if not incoming:
        return {"written": 0, "identical": 0, "matured": 0, "refused": 0}

    existing = sessions_by_stamp(root)
    written = identical = matured = refused = 0
    path = sessions_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for raw in incoming:
            stamp = str(raw.get("stamp_date") or "")[:10]
            if len(stamp) != 10:
                raise W3IntegrityError(f"session record missing stamp_date: {raw!r}")
            rec = dict(raw)
            rec["schema"] = SCHEMA_SESSION
            rec["stamp_date"] = stamp
            state = str(rec.get("liveness") or "")
            if state not in LIVENESS_STATES:
                raise W3IntegrityError(f"unknown W3 liveness {state!r} on {stamp}")
            rec["terminal"] = state in TERMINAL_LIVENESS
            rec.setdefault("source", SOURCE_CANDIDATES)
            prior = existing.get(stamp)
            if prior is None:
                handle.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
                existing[stamp] = rec
                written += 1
                continue
            prior_state = str(prior.get("liveness") or "")
            if prior_state == state:
                identical += 1
                continue
            if prior_state in TERMINAL_LIVENESS:
                refused += 1
                log.info(
                    "us_prophet_w3 refusing resurrection of terminal session %s "
                    "(%s → %s); generic backfill cannot enter the race",
                    stamp, prior_state, state)
                continue
            if (prior_state, state) in LAWFUL_LIVENESS_TRANSITION:
                handle.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
                existing[stamp] = rec
                matured += 1
                continue
            refused += 1
            log.info(
                "us_prophet_w3 refusing unlawful liveness transition %s: %s → %s",
                stamp, prior_state, state)
    return {"written": written, "identical": identical, "matured": matured,
            "refused": refused}


def resolve_board_as_of(root: Any = None) -> str | None:
    """Committed board as_of is the observation identity. Never wall-clock / run id."""
    standouts = _repo_root(root) / STANDOUTS_REL
    _require_committed_source("path", standouts)
    payload = _read_json(standouts) if standouts.exists() else None
    if not isinstance(payload, Mapping):
        return None
    as_of = str(payload.get("as_of") or payload.get("asof") or "")[:10]
    if len(as_of) != 10:
        return None
    return as_of


def store_is_commissioned(root: Any = None) -> bool:
    store = _store_dir(root)
    if not store.exists():
        return False
    if sessions_path(root).exists() or status_path(root).exists():
        return True
    for grain in ("paired", "family", "coverage"):
        if any((_store_dir(root) / grain).glob("*/*.parquet")):
            return True
    return False


def build_status_surface(root: Any = None, *,
                         run_doc: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Lawful pre-floor operator/research status. No comparison computation."""
    commissioned = store_is_commissioned(root)
    by = sessions_by_stamp(root)
    sessions = sorted(by.values(), key=lambda row: str(row.get("stamp_date") or ""))
    missing = [s for s in sessions if s.get("liveness") == LIVENESS_MISSING]
    degraded = [s for s in sessions if s.get("liveness") == LIVENESS_DEGRADED]
    unmatured = [s for s in sessions if s.get("liveness") == LIVENESS_UNMATURED]
    accrued = [s for s in sessions if s.get("liveness") == LIVENESS_PAIRED_ACCRUED]
    race = unmatured + accrued
    first_paired = min((str(s["stamp_date"])[:10] for s in race), default=None)
    latest = sessions[-1] if sessions else None
    family = load_family(root)
    coverage = load_coverage(root)
    payload: dict[str, Any] = {
        "schema": SCHEMA_STATUS,
        "commissioned": bool(commissioned),
        "authority": "measurement only / none",
        "comparison_surface": "forbidden",
        "first_lawful_comparison_read": (
            f"PENDING until {HONEST_N_FLOOR} matured H=10 sessions"),
        "honest_n_floor": HONEST_N_FLOOR,
        "paired_sessions_accrued": len(race),
        "matured_h10_sessions": len(accrued),
        "unmatured_sessions": len(unmatured),
        "first_eligible_paired_stamp": first_paired,
        "latest_session": (
            {
                "stamp_date": latest.get("stamp_date"),
                "liveness": latest.get("liveness"),
                "reason": latest.get("reason"),
            } if latest else None),
        "missing_sessions": [
            {"stamp_date": s.get("stamp_date"), "reason": s.get("reason")}
            for s in missing
        ],
        "degraded_or_unpaired_sessions": [
            {"stamp_date": s.get("stamp_date"), "reason": s.get("reason")}
            for s in degraded
        ],
        "n_missing": len(missing),
        "n_degraded_or_unpaired": len(degraded),
        "structural": {
            "schema": STRUCTURAL_SCHEMA,
            "outcome_blind": True,
            "n_family_rows": int(len(family)),
            "n_coverage_rows": int(len(coverage)),
        },
    }
    if not commissioned:
        payload["w3_not_commissioned_reason"] = (
            "W3 store missing — not commissioned; no false green")
    if run_doc:
        payload["last_run"] = {
            "n_paired_rows": run_doc.get("n_paired_rows", 0),
            "n_family_rows": run_doc.get("n_family_rows", 0),
            "n_coverage_rows": run_doc.get("n_coverage_rows", 0),
            "paired": run_doc.get("paired") or {},
            "family": run_doc.get("family") or {},
            "coverage": run_doc.get("coverage") or {},
            "sessions_written": run_doc.get("sessions_written") or {},
            "reconstruction_refused": list(run_doc.get("reconstruction_refused") or []),
            "failures": list(run_doc.get("failures") or []),
            "board_as_of": run_doc.get("board_as_of"),
            "require_stamp": run_doc.get("require_stamp"),
            "dry_run": bool(run_doc.get("dry_run")),
        }
    _assert_no_comparison_payload(payload)
    return payload


def render_status_text(payload: Mapping[str, Any]) -> str:
    """Human-readable lawful status. Machine/operator artifact, not a dashboard."""
    _assert_no_comparison_payload(payload)
    if not payload.get("commissioned"):
        reason = payload.get("w3_not_commissioned_reason") or "W3 store missing"
        return f"W3 STATUS: NOT COMMISSIONED\n{reason}\n"
    latest = payload.get("latest_session") or {}
    missing = payload.get("missing_sessions") or []
    degraded = payload.get("degraded_or_unpaired_sessions") or []
    lines = [
        "W3 STATUS: COMMISSIONED (measurement only / none)",
        f"paired sessions accrued: {payload.get('paired_sessions_accrued', 0)}",
        f"matured H=10 sessions: {payload.get('matured_h10_sessions', 0)}",
        f"unmatured sessions: {payload.get('unmatured_sessions', 0)}",
        f"first eligible paired stamp: {payload.get('first_eligible_paired_stamp')}",
        f"latest session: {latest.get('stamp_date')} {latest.get('liveness')}",
        f"missing sessions: {payload.get('n_missing', 0)}",
    ]
    for item in missing:
        lines.append(f"  missing {item.get('stamp_date')}: {item.get('reason')}")
    lines.append(f"degraded/unpaired sessions: {payload.get('n_degraded_or_unpaired', 0)}")
    for item in degraded:
        lines.append(f"  degraded {item.get('stamp_date')}: {item.get('reason')}")
    lines.append(f"first lawful comparison read: {payload.get('first_lawful_comparison_read')}")
    lines.append(f"prereg honest-N floor: {payload.get('honest_n_floor')}")
    lines.append(f"W3 authority: {payload.get('authority')}")
    structural = payload.get("structural") or {}
    lines.append(
        f"structural (outcome-blind): family_rows={structural.get('n_family_rows', 0)} "
        f"coverage_rows={structural.get('n_coverage_rows', 0)}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #

def _candidate_columns_present(root: Any) -> list[str]:
    wanted = list(CANDIDATE_COLUMNS)
    return wanted


def _receipt_for_stamp(
    stamp: str,
    root: Any,
    structural_by_stamp: Mapping[str, Mapping[str, Any] | None] | None,
) -> Mapping[str, Any] | None:
    if structural_by_stamp is not None:
        if stamp in structural_by_stamp:
            return structural_by_stamp[stamp]
        return None
    return load_committed_structural_receipt(stamp, root)


def _persist_run(doc: dict[str, Any], *,
                 session_records: list[dict[str, Any]],
                 paired_rows: list[dict],
                 family_rows: list[dict],
                 coverage_rows: list[dict],
                 root: Any,
                 dry_run: bool) -> None:
    """Write grains + gap receipts BEFORE any fail-closed raise so commit can land them."""
    current = sessions_by_stamp(root)
    matured = {stamp for stamp, rec in current.items()
               if rec.get("liveness") == LIVENESS_PAIRED_ACCRUED}
    matured.update(s["stamp_date"] for s in session_records
                   if s.get("liveness") == LIVENESS_PAIRED_ACCRUED)
    # Terminal history still counts as matured only if already paired_accrued.
    doc["honest_n_matured_h10_sessions"] = len(matured)
    doc["sessions"] = session_records
    doc["n_paired_rows"] = len(paired_rows)
    doc["n_family_rows"] = len(family_rows)
    doc["n_coverage_rows"] = len(coverage_rows)
    if dry_run:
        doc["paired"] = {"written": 0, "identical": 0, "matured": 0, "stamps": 0}
        doc["family"] = {"written": 0, "identical": 0, "matured": 0, "stamps": 0}
        doc["coverage"] = {"written": 0, "identical": 0, "matured": 0, "stamps": 0}
        doc["sessions_written"] = {"written": 0, "identical": 0, "matured": 0, "refused": 0}
        return
    doc["paired"] = append_paired(paired_rows, root)
    doc["family"] = append_family(family_rows, root)
    doc["coverage"] = append_coverage(coverage_rows, root)
    doc["sessions_written"] = append_sessions(session_records, root)
    write_status(build_status_surface(root, run_doc=doc), root)


def accrue(root: Any = None, *,
           dry_run: bool = False,
           candidates: pd.DataFrame | None = None,
           grades: pd.DataFrame | None = None,
           structural_by_stamp: Mapping[str, Mapping[str, Any] | None] | None = None,
           require_stamp: str | None = None,
           require_board_as_of: bool = False) -> dict[str, Any]:
    """Accrue paired + structural grains. Never emits a comparative W3 read.

    Gap receipts (session_missing / degraded_or_unpaired) are persisted before
    fail-closed raises so the nightly ``if: always()`` commit can still land them.
    """
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
            "Comparison surface forbidden before the honest-N floor."
        ),
        "degraded": [],
        "failures": [],
        "reconstruction_refused": [],
        "require_stamp": None,
        "board_as_of": None,
    }
    board_as_of = resolve_board_as_of(root)
    doc["board_as_of"] = board_as_of
    if require_board_as_of and not require_stamp:
        require_stamp = board_as_of
        if not require_stamp:
            doc["failures"].append(
                "workflow cannot identify a durable candidate stamp from the "
                "committed board as_of — refusing Pages / wall-clock inference")
            missing = _session_liveness(
                "unresolved", in_candidates=False, n_v3_buy=0,
                n_paired=0, n_pending=0, degraded=False)
            missing["stamp_date"] = "unresolved"
            missing["reason"] = doc["failures"][-1]
            # Do not persist a fake stamp_date. Status records the unresolved run.
            if not dry_run:
                write_status(build_status_surface(root, run_doc=doc), root)
            raise W3IntegrityError(doc["failures"][-1])
    if require_stamp:
        _require_committed_source("require_stamp", require_stamp)
        require_stamp = str(require_stamp)[:10]
        doc["require_stamp"] = require_stamp

    existing = sessions_by_stamp(root)
    reconstruction_refused: list[str] = []
    required_already_terminal = False
    if require_stamp:
        prior_required = existing.get(require_stamp)
        if prior_required and prior_required.get("liveness") in TERMINAL_LIVENESS:
            required_already_terminal = True
            reconstruction_refused.append(require_stamp)

    if candidates is None:
        wanted = _candidate_columns_present(root)
        candidates = ucv.load_candidates(root, columns=wanted)
    if grades is None:
        grades = upg.load_grades(root, columns=list(GRADE_COLUMNS))

    if candidates is None:
        candidates = pd.DataFrame()
    else:
        candidates = candidates.copy()
        if not candidates.empty and "stamp_date" in candidates.columns:
            candidates["stamp_date"] = candidates["stamp_date"].astype(str).str.slice(0, 10)
            drop = candidates["stamp_date"].map(
                lambda stamp: bool(existing.get(str(stamp)[:10], {}).get("liveness")
                                   in TERMINAL_LIVENESS))
            refused_stamps = sorted({
                str(stamp)[:10] for stamp in candidates.loc[drop, "stamp_date"].tolist()
            })
            for stamp in refused_stamps:
                if stamp not in reconstruction_refused:
                    reconstruction_refused.append(stamp)
            if int(drop.sum()):
                candidates = candidates.loc[~drop].copy()
    doc["reconstruction_refused"] = list(reconstruction_refused)

    stamps: list[str] = []
    if not candidates.empty and "stamp_date" in candidates.columns:
        stamps = sorted(set(candidates["stamp_date"].dropna().astype(str).str.slice(0, 10)))

    failures: list[str] = list(doc["failures"])

    missing_required: dict[str, Any] | None = None
    if require_stamp and require_stamp not in stamps and not required_already_terminal:
        missing_required = _session_liveness(
            require_stamp, in_candidates=False, n_v3_buy=0,
            n_paired=0, n_pending=0, degraded=False)
        failures.append(
            f"expected candidate stamp {require_stamp} absent from the durable "
            "store — session_missing; refusing Pages backfill")

    if candidates.empty:
        session_records: list[dict[str, Any]] = []
        if missing_required is not None:
            session_records.append(missing_required)
            doc["failures"] = failures
            _persist_run(
                doc, session_records=session_records, paired_rows=[], family_rows=[],
                coverage_rows=[], root=root, dry_run=dry_run)
            raise W3IntegrityError(failures[-1])
        if required_already_terminal and require_stamp:
            session_records.append(dict(existing[require_stamp]))
            doc["note"] = (
                f"required stamp {require_stamp} already terminal "
                f"({existing[require_stamp].get('liveness')}); reconstruction refused")
        else:
            doc["note"] = (
                "no candidate rows in the durable store — nothing accrued; "
                "gaps remain gaps")
        doc["failures"] = failures
        _persist_run(
            doc, session_records=session_records, paired_rows=[], family_rows=[],
            coverage_rows=[], root=root, dry_run=dry_run)
        return doc

    paired_rows, pair_doc = build_paired_rows(candidates, grades)
    doc["paired_qualify"] = pair_doc

    paired_by_stamp: dict[str, list[dict]] = {}
    for row in paired_rows:
        paired_by_stamp.setdefault(row["stamp_date"], []).append(row)

    family_rows: list[dict] = []
    coverage_rows: list[dict] = []
    sessions: list[dict] = []

    definition = (candidates["board_definition"].astype(str)
                  if "board_definition" in candidates.columns
                  else pd.Series([""] * len(candidates), index=candidates.index))
    lane = (candidates["lane"].astype(str)
            if "lane" in candidates.columns
            else pd.Series([""] * len(candidates), index=candidates.index))

    for stamp in stamps:
        mask = candidates["stamp_date"] == stamp
        defs = set(definition.loc[mask].tolist())
        degraded = FALLBACK_DEFINITION in defs and CANONICAL_BOARD not in defs
        n_v3_buy = int(((definition.loc[mask] == CANONICAL_BOARD)
                        & (lane.loc[mask] == BUY_LANE)).sum())
        stamp_paired = paired_by_stamp.get(stamp, [])
        n_pending = sum(1 for row in stamp_paired if _outcome_pending(row))
        session = _session_liveness(
            stamp, in_candidates=True, n_v3_buy=n_v3_buy,
            n_paired=len(stamp_paired), n_pending=n_pending, degraded=degraded)
        if board_as_of:
            session["board_as_of"] = board_as_of
        sessions.append(session)
        if session["liveness"] == LIVENESS_DEGRADED:
            doc["degraded"].append({"stamp_date": stamp, "reason": session["reason"]})

        receipt = _receipt_for_stamp(stamp, root, structural_by_stamp)
        if receipt is not None:
            family_rows.extend(family_rows_from_receipt(stamp, receipt))
            coverage_rows.extend(coverage_rows_from_receipt(stamp, receipt))
            session["structural_schema"] = STRUCTURAL_SCHEMA
        elif session["liveness"] in (LIVENESS_UNMATURED, LIVENESS_PAIRED_ACCRUED):
            # Valid pair with no structural receipt: do not fabricate family/coverage.
            # Fail closed on the required/current stamp; historical pre-receipt
            # stamps are named but do not abort the run.
            target = require_stamp or board_as_of
            msg = (f"structural receipt absent for otherwise valid pair {stamp} "
                   f"— not fabricating family/coverage diagnostics")
            if target and stamp == target:
                failures.append(msg)
            else:
                session["reason"] = f"{session['reason']}; {msg}"

    if missing_required is not None:
        sessions.append(missing_required)

    if board_as_of and require_stamp and board_as_of != require_stamp:
        failures.append(
            f"committed board as_of {board_as_of} mismatches required stamp "
            f"{require_stamp}")

    doc["failures"] = failures
    race_paired = [row for row in paired_rows
                   if row["stamp_date"] not in {
                       s["stamp_date"] for s in sessions
                       if s["liveness"] == LIVENESS_DEGRADED
                   }]
    # Degraded sessions already have zero paired rows by construction of the
    # qualify filter; keep the list explicit so a future filter bug cannot
    # silently write a fallback night into the race.
    _persist_run(
        doc, session_records=sessions, paired_rows=race_paired,
        family_rows=family_rows, coverage_rows=coverage_rows,
        root=root, dry_run=dry_run)

    if required_already_terminal:
        doc["note"] = (
            f"required stamp {require_stamp} already terminal; "
            "reconstruction refused; honest-N unchanged")
        return doc

    if failures:
        raise W3IntegrityError("; ".join(failures))
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
