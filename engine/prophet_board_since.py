"""Current continuous published-board membership start (`board_since`).

Display-tier only. Reads existing published board fossils and stamps an in-memory
field onto candidate rows. This is not a new ledger, identity system, or authority.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import AbstractSet, Any, Iterable, Mapping, Sequence

# Keep identical to engine.china_standout_track.WATCH_DEFINITIONS. Imported lazily
# nowhere at module top so the pure resolver stays import-light; the equality is
# pinned by tests/test_prophet_board_since.py::test_cn_watch_definitions_match_engine.
CN_WATCH_DEFINITIONS = frozenset({
    "cn_reversal_watch_v1",
    "cn_prophet_v2_shadow",
    "cn_prophet_v3_shadow",
    "cn_continuation_watch_v1",
})

US_SNAPSHOT_LANES = ("buy", "watch", "leaders", "ran", "laggards", "laggard")
US_VISIBLE_LANES = US_SNAPSHOT_LANES
CN_VISIBLE_LANES = ("buy", "more_actionable", "late_or_unfillable")
HK_CA_VISIBLE_LANES = ("buy", "watch")
INTL_VISIBLE_LANES = ("buy",)
HK_CA_VISIBLE_GROUPS = frozenset({"entry_open", "setting_up", "watch"})

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REPO_ROOT = Path(__file__).resolve().parents[1]

Observation = tuple[str, frozenset[str]]


def is_iso_date(val: Any) -> bool:
    return isinstance(val, str) and bool(_ISO.fullmatch(val))


def _iso_from_value(val: Any) -> str | None:
    if val is None:
        return None
    if is_iso_date(val):
        return val
    text = str(val).strip()
    if not text or text in ("nan", "NaT", "None"):
        return None
    head = text[:10]
    return head if is_iso_date(head) else None


def collapse_published_observations(
    observations: Iterable[tuple[Any, Iterable[Any]]] | None,
) -> list[Observation]:
    """Last snapshot per ISO date wins; dates sort ascending; missing dates stay omitted."""
    by_date: dict[str, frozenset[str]] = {}
    for item in observations or ():
        if not item or len(item) != 2:
            continue
        date, ids = item
        iso = _iso_from_value(date)
        if not iso:
            continue
        cleaned = {
            str(x) for x in (ids or ())
            if x is not None and str(x).strip() not in ("", "nan", "None")
        }
        by_date[iso] = frozenset(cleaned)
    return [(d, by_date[d]) for d in sorted(by_date)]


def with_current_board(
    observations: Iterable[tuple[Any, Iterable[Any]]] | None,
    current_as_of: Any,
    current_ids: Iterable[Any] | None,
) -> list[Observation]:
    extra: list[tuple[Any, Iterable[Any]]] = list(observations or ())
    iso = _iso_from_value(current_as_of)
    if iso:
        extra.append((iso, current_ids or ()))
    return collapse_published_observations(extra)


def current_continuous_membership_start(
    observations: Iterable[tuple[Any, Iterable[Any]]] | None,
    identity: Any,
) -> str | None:
    """Earliest date of the current uninterrupted published-board presence streak.

    Identity must appear on the last observation. A published observation that
    omits the identity resets. Dates simply absent from `observations` do not.
    """
    ident = str(identity).strip() if identity is not None else ""
    if not ident or ident in ("nan", "None"):
        return None
    obs = collapse_published_observations(observations)
    if not obs:
        return None
    last_date, last_ids = obs[-1]
    if ident not in last_ids:
        return None
    start = last_date
    for date, ids in reversed(obs[:-1]):
        if ident in ids:
            start = date
            continue
        break
    return start if is_iso_date(start) else None


def observations_from_us_snapshots_jsonl(path: Path) -> list[Observation]:
    by_date: dict[str, frozenset[str]] = {}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            snap = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(snap, dict):
            continue
        iso = _iso_from_value(snap.get("as_of"))
        if not iso:
            continue
        ids: set[str] = set()
        for lane in US_SNAPSHOT_LANES:
            for row in snap.get(lane) or []:
                if isinstance(row, dict):
                    tk = row.get("ticker")
                    if tk:
                        ids.add(str(tk))
        by_date[iso] = frozenset(ids)
    return [(d, by_date[d]) for d in sorted(by_date)]


def observations_from_cn_frame(df: Any, watch_definitions: AbstractSet[str] | None = None) -> list[Observation]:
    if df is None or getattr(df, "empty", False):
        return []
    cols = set(getattr(df, "columns", ()))
    if "date" not in cols or "ticker" not in cols:
        return []
    watch = frozenset(watch_definitions if watch_definitions is not None else CN_WATCH_DEFINITIONS)
    live = df
    if "board_definition" in cols:
        live = df[~df["board_definition"].astype(str).isin(watch)]
    by_date: dict[str, set[str]] = {}
    for date_val, grp in live.groupby("date", sort=False):
        iso = _iso_from_value(date_val)
        if not iso:
            continue
        tickers = {
            str(t) for t in grp["ticker"].tolist()
            if t is not None and str(t).strip() not in ("", "nan", "None")
        }
        by_date[iso] = tickers
    return [(d, frozenset(by_date[d])) for d in sorted(by_date)]


def observations_from_board_ledger_frame(df: Any) -> list[Observation]:
    if df is None or getattr(df, "empty", False):
        return []
    cols = set(getattr(df, "columns", ()))
    if "date" not in cols or "ticker" not in cols:
        return []
    vis = df
    if "group" in cols:
        vis = df[df["group"].astype(str).isin(HK_CA_VISIBLE_GROUPS)]
    by_date: dict[str, set[str]] = {}
    for date_val, grp in vis.groupby("date", sort=False):
        iso = _iso_from_value(date_val)
        if not iso:
            continue
        tickers = {
            str(t) for t in grp["ticker"].tolist()
            if t is not None and str(t).strip() not in ("", "nan", "None")
        }
        by_date[iso] = tickers
    return [(d, frozenset(by_date[d])) for d in sorted(by_date)]


def observations_from_intl_setups_history(versions: Sequence[Mapping[str, Any]] | None) -> list[Observation]:
    raw: list[tuple[Any, Iterable[Any]]] = []
    for blob in versions or ():
        if not isinstance(blob, Mapping):
            continue
        iso = _iso_from_value(blob.get("as_of"))
        if not iso:
            continue
        ids = identities_in_lanes(blob, INTL_VISIBLE_LANES)
        raw.append((iso, ids))
    return collapse_published_observations(raw)


def load_intl_setups_git_history(
    repo_root: Path | None = None,
    relpath: str = "site/factordata/intl_setups.json",
    *,
    max_commits: int = 40,
) -> list[dict[str, Any]]:
    root = repo_root or _REPO_ROOT
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "log", "--pretty=%H", "--reverse", "--", relpath],
            capture_output=True, text=True, timeout=45, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    shas = [s for s in proc.stdout.split() if s]
    if len(shas) > max_commits:
        shas = shas[-max_commits:]
    out: list[dict[str, Any]] = []
    for sha in shas:
        try:
            show = subprocess.run(
                ["git", "-C", str(root), "show", f"{sha}:{relpath}"],
                capture_output=True, text=True, timeout=20, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if show.returncode != 0 or not show.stdout:
            continue
        try:
            blob = json.loads(show.stdout)
        except json.JSONDecodeError:
            continue
        if isinstance(blob, dict):
            out.append(blob)
    return out


def identities_in_lanes(
    artifact: Mapping[str, Any] | None,
    lanes: Sequence[str],
    identity_key: str = "ticker",
) -> set[str]:
    ids: set[str] = set()
    if not artifact:
        return ids
    for lane in lanes:
        for row in artifact.get(lane) or []:
            if not isinstance(row, dict):
                continue
            ident = row.get(identity_key)
            if ident is None or str(ident).strip() in ("", "nan", "None"):
                continue
            ids.add(str(ident))
    return ids


def _prior_maps(
    prior: Mapping[str, Any] | None,
    lanes: Sequence[str],
    identity_key: str,
) -> tuple[set[str], dict[str, str]]:
    members: set[str] = set()
    since: dict[str, str] = {}
    if not prior:
        return members, since
    for lane in lanes:
        for row in prior.get(lane) or []:
            if not isinstance(row, dict):
                continue
            ident = row.get(identity_key)
            if ident is None or str(ident).strip() in ("", "nan", "None"):
                continue
            ident_s = str(ident)
            members.add(ident_s)
            val = row.get("board_since") or row.get("added_date")
            if is_iso_date(val):
                since[ident_s] = val
    return members, since


def stamp_artifact_rows(
    artifact: dict[str, Any] | None,
    observations: Iterable[tuple[Any, Iterable[Any]]] | None,
    *,
    lanes: Sequence[str] = ("buy",),
    identity_key: str = "ticker",
    prior_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Mutate candidate rows in-place with `board_since`. History wins; carry is fallback."""
    if not artifact:
        return artifact
    obs = collapse_published_observations(observations)
    prior_members, prior_since = _prior_maps(prior_artifact, lanes, identity_key)
    for lane in lanes:
        rows = artifact.get(lane)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            ident = row.get(identity_key)
            if ident is None or str(ident).strip() in ("", "nan", "None"):
                row["board_since"] = None
                continue
            ident_s = str(ident)
            computed = current_continuous_membership_start(obs, ident_s)
            if computed is not None:
                row["board_since"] = computed
            elif ident_s in prior_members and is_iso_date(prior_since.get(ident_s)):
                row["board_since"] = prior_since[ident_s]
            else:
                row["board_since"] = None
    return artifact


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return blob if isinstance(blob, dict) else None


def _read_parquet(path: Path) -> Any:
    import pandas as pd  # noqa: PLC0415 — optional adapter dep
    return pd.read_parquet(path)


def stamp_setups(
    market: str,
    artifact: dict[str, Any] | None,
    *,
    data_dir: Path | None = None,
    repo_root: Path | None = None,
    prior_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Stamp `board_since` for one market's candidate artifact. Missing history → null."""
    if not artifact:
        return artifact
    root = repo_root or _REPO_ROOT
    data = Path(data_dir) if data_dir is not None else root / "data"
    market_key = (market or "").lower()
    if market_key == "us":
        lanes = US_VISIBLE_LANES
        hist = observations_from_us_snapshots_jsonl(data / "us_board_ledger" / "snapshots.jsonl")
    elif market_key == "cn":
        lanes = CN_VISIBLE_LANES
        path = data / "china_standout_track" / "board.parquet"
        try:
            hist = observations_from_cn_frame(_read_parquet(path)) if path.exists() else []
        except Exception:  # noqa: BLE001 — display stamp, never fatal
            hist = []
    elif market_key in ("hk", "ca"):
        lanes = HK_CA_VISIBLE_LANES
        fname = "hk_board.parquet" if market_key == "hk" else "ca_board.parquet"
        path = data / "board_ledger" / fname
        try:
            hist = observations_from_board_ledger_frame(_read_parquet(path)) if path.exists() else []
        except Exception:  # noqa: BLE001
            hist = []
    elif market_key == "intl":
        lanes = INTL_VISIBLE_LANES
        hist = observations_from_intl_setups_history(load_intl_setups_git_history(root))
        if prior_artifact is None:
            prior_path = root / "site" / "factordata" / "intl_setups.json"
            prior_artifact = _read_json(prior_path)
    else:
        return artifact
    current_ids = identities_in_lanes(artifact, lanes)
    # Empty history must not mint as_of/today as a fake first-seen date.
    # When fossils exist, fold the current published board onto that series so
    # same-session rebuilds last-win and genuine new names get this session.
    obs = (
        with_current_board(hist, artifact.get("as_of"), current_ids)
        if hist
        else []
    )
    return stamp_artifact_rows(
        artifact, obs, lanes=lanes, prior_artifact=prior_artifact,
    )


def stamp_setups_fail_open(
    market: str,
    artifact: dict[str, Any] | None,
    *,
    data_dir: Path | None = None,
    repo_root: Path | None = None,
    prior_artifact: Mapping[str, Any] | None = None,
    log: Any | None = None,
) -> dict[str, Any] | None:
    try:
        return stamp_setups(
            market, artifact,
            data_dir=data_dir, repo_root=repo_root, prior_artifact=prior_artifact,
        )
    except Exception as exc:  # noqa: BLE001 — additive display field
        if log is not None:
            log.warning("%s board_since stamp failed (%s)", market, exc)
        return artifact
