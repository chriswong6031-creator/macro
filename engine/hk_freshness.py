"""HK data-freshness sentinel — 6-check guard that makes it IMPOSSIBLE for the HK
dashboard to render stale data as live.

ROOT CAUSE (2026-07-08 incident): `data/hk_breadth/_closes_cache.parquet` was
tracked in git despite being in .gitignore. The nightly `git add data/` staged the
stale local copy; `git pull --rebase -X theirs` then let the stale local cache WIN
over fresh asia-close data. Stale cache poisoned:
    _closes_cache -> compute_hk_global_betas -> betas["as_of"] -> scoreboard["as_of"]
    -> standouts["as_of"] -> hk_standouts.json `.as_of` -> hk.html showing 2026-07-02
    as if it were the current day.

FAIL-OPEN DESIGN: every check is wrapped in a try/except. A sentinel crash yields
an "error" per-check and page state "degraded" — the render proceeds WITH a banner.
The sentinel NEVER raises, NEVER blocks the nightly render.

Seven checks against `lib.hk_calendar.expected_last_session()`:
    1. Cache index.max() <= 2 calendar days behind expected (PRIMARY data source).
    2. Bellwether spot-check: data/hk_stocks/9988.HK.parquet index.max() <= 2 cal days.
    3. Standouts artifact: site/factordata/hk_standouts.json `.as_of` <= 2 cal days.
    4. Regime artifact: data/hk_regime/latest.json `.date` <= 1 cal day.
    5. Coherence: standouts.as_of == regime.date (divergence = incoherent snapshot).
    6. Regression: cache index.max() must never DECREASE run-over-run (detects the
       `-X theirs` clobber that caused the incident).
    7. Southbound holdings: data/hk_southbound/holdings.parquet index.max() <= 2 cal days.

State thresholds:
    lag <= 2 cal days -> "fresh"
    lag <= 4 cal days -> "slow" (weekend gaps, missed session)
    lag >= 5 cal days -> "stale"
    missing           -> "dead"

Page-level verdict: ok | degraded | stale
    ok       = all checks fresh/slow (no check stale/dead)
    degraded  = at most one non-critical check is stale/dead (coherence/regression OK)
    stale    = cache (check 1) is stale/dead, OR coherence is broken, OR regression fired
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from lib import config
from lib.hk_calendar import expected_last_session

log = logging.getLogger("hk_freshness")

# Where to persist the run-over-run regression baseline.
_STATE_DIR_REL = "hk_freshness"
_STATE_FILE = "state.json"

# Site factordata dir (relative to site root)
_FACTORDATA = "factordata"

# Freshness output artifact (written by this sentinel for the template to read)
_FRESHNESS_JSON = "hk_freshness.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lag_state(lag_days: int | None, *, tight: bool = False) -> str:
    """Convert a calendar-day lag to a staleness state label.

    Thresholds:
        0-2 cal days -> fresh   (normal: same day or weekend)
        3-4 cal days -> slow    (one missed session, or long weekend)
        >= 5 cal days -> stale  (two or more missed sessions; the 2026-07-08 incident
                                 had a 5-day lag from Jul-02 to Jul-07)
    When tight=True (regime check, tighter SLA):
        0-1 cal days -> fresh
        2   cal days -> slow
        >= 3 cal days -> stale
    """
    if lag_days is None:
        return "dead"
    if tight:
        if lag_days <= 1:
            return "fresh"
        elif lag_days <= 2:
            return "slow"
        else:
            return "stale"
    if lag_days <= 2:
        return "fresh"
    elif lag_days <= 4:
        return "slow"
    else:
        return "stale"


def _parquet_index_max(path: Path) -> date | None:
    """Read a parquet file and return the max date from its index. None on any error.

    Handles two on-disk shapes:
      * flat DatetimeIndex — the cache and bellwether price stores.
      * long-form MultiIndex whose levels include a datetime level — southbound
        holdings is keyed ``['date', 'ticker']`` (191k rows), so a naive
        ``isinstance(index, DatetimeIndex)`` check silently returns None and the
        sentinel falsely reports the store "dead". Prefer the level named
        ``date`` (the codebase idiom: ``index.get_level_values("date")``), else
        the first datetime-typed level.
    """
    try:
        if not path.exists():
            return None
        df = pd.read_parquet(path, columns=[])   # columns=[] reads only the index
        idx = df.index
        if isinstance(idx, pd.DatetimeIndex) and len(idx):
            return idx.max().normalize().date()
        if isinstance(idx, pd.MultiIndex) and len(idx):
            date_level: int | str | None = None
            if idx.names and "date" in idx.names:
                date_level = "date"
            else:
                for i in range(idx.nlevels):
                    if pd.api.types.is_datetime64_any_dtype(idx.get_level_values(i)):
                        date_level = i
                        break
            if date_level is not None:
                lv = idx.get_level_values(date_level)
                if len(lv):
                    return pd.Timestamp(lv.max()).normalize().date()
        return None
    except Exception as e:  # noqa: BLE001
        log.warning("hk_freshness: %s unreadable (%s)", path, e)
        return None


def _json_field(path: Path, field: str) -> str | None:
    """Read a JSON file and return a string field. None on any error."""
    try:
        if not path.exists():
            return None
        d = json.loads(path.read_text())
        v = d.get(field)
        return str(v) if v else None
    except Exception as e:  # noqa: BLE001
        log.warning("hk_freshness: %s[%s] unreadable (%s)", path, field, e)
        return None


def _load_state(state_path: Path) -> dict:
    try:
        if state_path.exists():
            return json.loads(state_path.read_text())
    except Exception:  # noqa: BLE001
        pass
    return {}


def _save_state(state_path: Path, payload: dict) -> None:
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(payload, indent=2))
    except Exception as e:  # noqa: BLE001
        log.warning("hk_freshness: state write failed (%s)", e)


def _badge(asof: date | None, expected: date, *, tight: bool = False) -> dict:
    """Build a per-store staleness badge dict."""
    if asof is None:
        return {"asof": None, "lag_days": None, "state": "dead"}
    lag = (expected - asof).days
    # Negative lag (asof AFTER expected) = store has fresh data.
    lag = max(lag, 0)
    return {"asof": str(asof), "lag_days": lag, "state": _lag_state(lag, tight=tight)}


# ---------------------------------------------------------------------------
# Core sentinel
# ---------------------------------------------------------------------------

def hk_freshness_sentinel(now: datetime | None = None) -> dict:
    """Run all 6 freshness checks; return a result dict suitable for JSON serialisation.

    Always returns a dict (never raises). Structure:
    {
        "checked_at": ISO timestamp,
        "expected_session": "YYYY-MM-DD",
        "stores": {
            "cache": {asof, lag_days, state},
            "bellwether": {...},
            "standouts": {...},
            "regime": {...},
            "southbound": {...},
        },
        "coherence": {"ok": bool, "standouts_asof": ..., "regime_date": ..., "note": ...},
        "regression": {"ok": bool, "prev_cache_max": ..., "curr_cache_max": ..., "note": ...},
        "verdict": "ok" | "degraded" | "stale",
        "banner_message": {"en": ..., "zh": ...} | None,
    }
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    checked_at = now.isoformat(timespec="seconds")

    try:
        expected = expected_last_session(now)
    except Exception as e:  # noqa: BLE001
        log.error("hk_freshness: calendar lookup failed (%s)", e)
        expected = now.date()

    data_root = config.data_dir()
    site_root = Path(config.ROOT) / config.load()["storage"]["site_dir"]
    state_path = data_root / _STATE_DIR_REL / _STATE_FILE

    checks: dict[str, dict] = {}

    # Check 1: _closes_cache.parquet
    try:
        cache_path = data_root / "hk_breadth" / "_closes_cache.parquet"
        cache_max = _parquet_index_max(cache_path)
        checks["cache"] = _badge(cache_max, expected)
    except Exception as e:  # noqa: BLE001
        log.error("hk_freshness check 1 (cache) crashed: %s", e)
        checks["cache"] = {"asof": None, "lag_days": None, "state": "error"}

    # Check 2: 9988.HK.parquet bellwether
    try:
        bell_path = data_root / "hk_stocks" / "9988.HK.parquet"
        bell_max = _parquet_index_max(bell_path)
        checks["bellwether"] = _badge(bell_max, expected)
    except Exception as e:  # noqa: BLE001
        log.error("hk_freshness check 2 (bellwether) crashed: %s", e)
        checks["bellwether"] = {"asof": None, "lag_days": None, "state": "error"}

    # Check 3: hk_standouts.json .as_of
    try:
        standouts_path = site_root / _FACTORDATA / "hk_standouts.json"
        standouts_asof_str = _json_field(standouts_path, "as_of")
        standouts_asof = (pd.Timestamp(standouts_asof_str).date()
                          if standouts_asof_str else None)
        checks["standouts"] = _badge(standouts_asof, expected)
    except Exception as e:  # noqa: BLE001
        log.error("hk_freshness check 3 (standouts) crashed: %s", e)
        checks["standouts"] = {"asof": None, "lag_days": None, "state": "error"}
        standouts_asof = None
        standouts_asof_str = None

    # Check 4: hk_regime/latest.json .date (tight: <= 1 cal day)
    try:
        regime_path = data_root / "hk_regime" / "latest.json"
        regime_date_str = _json_field(regime_path, "date")
        regime_date = (pd.Timestamp(regime_date_str).date()
                       if regime_date_str else None)
        checks["regime"] = _badge(regime_date, expected, tight=True)
    except Exception as e:  # noqa: BLE001
        log.error("hk_freshness check 4 (regime) crashed: %s", e)
        checks["regime"] = {"asof": None, "lag_days": None, "state": "error"}
        regime_date = None
        regime_date_str = None

    # Check 5: Coherence — standouts.as_of == regime.date
    try:
        coherent = (standouts_asof is not None
                    and regime_date is not None
                    and standouts_asof == regime_date)
        coherence = {
            "ok": coherent,
            "standouts_asof": str(standouts_asof) if standouts_asof else None,
            "regime_date": str(regime_date) if regime_date else None,
            "note": (None if coherent
                     else "standouts.as_of != regime.date — snapshot is incoherent"),
        }
    except Exception as e:  # noqa: BLE001
        log.error("hk_freshness check 5 (coherence) crashed: %s", e)
        coherence = {"ok": False, "note": f"coherence check error: {e}"}

    # Check 7: Southbound holdings store freshness (data/hk_southbound/holdings.parquet)
    try:
        sb_path = data_root / "hk_southbound" / "holdings.parquet"
        sb_max = _parquet_index_max(sb_path)
        checks["southbound"] = _badge(sb_max, expected)
    except Exception as e:  # noqa: BLE001
        log.error("hk_freshness check 7 (southbound) crashed: %s", e)
        checks["southbound"] = {"asof": None, "lag_days": None, "state": "error"}

    # Check 6: Regression — cache index.max() must not decrease run-over-run
    try:
        prev_state = _load_state(state_path)
        prev_cache_str = prev_state.get("cache_max")
        prev_cache = pd.Timestamp(prev_cache_str).date() if prev_cache_str else None
        curr_cache = cache_max  # from check 1 above

        regression_fired = bool(
            prev_cache is not None
            and curr_cache is not None
            and curr_cache < prev_cache
        )
        regression = {
            "ok": not regression_fired,
            "prev_cache_max": str(prev_cache) if prev_cache else None,
            "curr_cache_max": str(curr_cache) if curr_cache else None,
            "note": (f"cache rolled BACK from {prev_cache} to {curr_cache} "
                     "(likely -X theirs clobber)" if regression_fired else None),
        }
        # Update the state file with the latest cache max (only advance, never retreat
        # in the state file itself — so the regression check catches the retreat once).
        if curr_cache is not None:
            new_state = dict(prev_state)
            new_state["cache_max"] = str(curr_cache)
            new_state["last_checked"] = checked_at
            _save_state(state_path, new_state)
    except Exception as e:  # noqa: BLE001
        log.error("hk_freshness check 6 (regression) crashed: %s", e)
        regression = {"ok": False, "note": f"regression check error: {e}"}
        regression_fired = True

    # ---------------------------------------------------------------------------
    # Verdict
    # ---------------------------------------------------------------------------
    cache_state = checks.get("cache", {}).get("state", "error")
    cache_primary_bad = cache_state in ("stale", "dead", "error")
    coherence_bad = not coherence.get("ok", True)
    regression_bad = not regression.get("ok", True)

    # Any secondary stores stale/dead (non-cache)?
    secondary_bad = any(
        checks.get(k, {}).get("state") in ("stale", "dead", "error")
        for k in ("bellwether", "standouts", "regime", "southbound")
    )

    if cache_primary_bad or coherence_bad or regression_bad:
        verdict = "stale"
    elif secondary_bad:
        verdict = "degraded"
    else:
        verdict = "ok"

    # ---------------------------------------------------------------------------
    # Banner message (bilingual) — only when degraded or stale
    # ---------------------------------------------------------------------------
    banner = None
    if verdict in ("stale", "degraded"):
        stale_parts_en: list[str] = []
        stale_parts_zh: list[str] = []

        cache_info = checks.get("cache", {})
        cache_lag = cache_info.get("lag_days")
        cache_asof = cache_info.get("asof") or "—"
        if cache_info.get("state") in ("stale", "dead", "error"):
            sessions_str = f"{cache_lag} sessions" if cache_lag is not None else "unknown sessions"
            stale_parts_en.append(
                f"cache {sessions_str} behind (last {cache_asof})")
            stale_parts_zh.append(
                f"价格缓存落后 {cache_lag if cache_lag is not None else '—'} 个交易日（最后 {cache_asof}）")

        if regression_bad and regression.get("note"):
            stale_parts_en.append(regression["note"])
            stale_parts_zh.append(f"缓存数据回退：{regression.get('prev_cache_max','—')} → {regression.get('curr_cache_max','—')}")

        if coherence_bad:
            s_asof = coherence.get("standouts_asof") or "—"
            r_date = coherence.get("regime_date") or "—"
            stale_parts_en.append(
                f"snapshot incoherent — standouts {s_asof} vs regime {r_date}")
            stale_parts_zh.append(
                f"快照不一致 — 精选个股 {s_asof} vs 周期判断 {r_date}")

        # De-dup: when coherence fires it already names standouts and regime inline;
        # skip those two in the per-store loop so each store appears at most once.
        skip_in_store_loop: set[str] = {"standouts", "regime"} if coherence_bad else set()
        for k in ("bellwether", "standouts", "regime", "southbound"):
            if k in skip_in_store_loop:
                continue
            info = checks.get(k, {})
            if info.get("state") in ("stale", "dead", "error"):
                lag = info.get("lag_days")
                asof = info.get("asof") or "—"
                lag_str = f"{lag}d" if lag is not None else "—"
                stale_parts_en.append(f"{k} {lag_str} behind (last {asof})")
                stale_parts_zh.append(f"{k} 落后 {lag_str}（最后 {asof}）")

        if stale_parts_en:
            prefix_en = "HK data stale" if verdict == "stale" else "HK data degraded"
            prefix_zh = "港股数据已过期" if verdict == "stale" else "港股数据降级"
            banner = {
                "en": f"{prefix_en} — {'; '.join(stale_parts_en)}",
                "zh": f"{prefix_zh} — {'；'.join(stale_parts_zh)}",
            }
        else:
            banner = {
                "en": f"HK data {verdict} (expected session {expected})",
                "zh": f"港股数据{verdict}（预期交易日 {expected}）",
            }

    result = {
        "checked_at": checked_at,
        "expected_session": str(expected),
        "stores": checks,
        "coherence": coherence,
        "regression": regression,
        "verdict": verdict,
        "banner_message": banner,
    }
    return result


def write_freshness_json(result: dict, site_root: Path | None = None) -> None:
    """Persist the sentinel result to site/factordata/hk_freshness.json."""
    try:
        if site_root is None:
            site_root = Path(config.ROOT) / config.load()["storage"]["site_dir"]
        fdir = site_root / _FACTORDATA
        fdir.mkdir(parents=True, exist_ok=True)
        (fdir / _FRESHNESS_JSON).write_text(json.dumps(result, indent=2, default=str))
    except Exception as e:  # noqa: BLE001
        log.warning("hk_freshness: JSON write failed (%s)", e)


def run_sentinel(now: datetime | None = None) -> dict:
    """Run the sentinel, write JSON, and return the result. Never raises."""
    try:
        result = hk_freshness_sentinel(now=now)
    except Exception as e:  # noqa: BLE001 — total safety net
        log.error("hk_freshness sentinel totally crashed (%s); returning error verdict", e)
        result = {
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "expected_session": None,
            "stores": {},
            "coherence": {"ok": False, "note": "sentinel crashed"},
            "regression": {"ok": False, "note": "sentinel crashed"},
            "verdict": "degraded",
            "banner_message": {
                "en": "HK freshness sentinel crashed — data currency unknown",
                "zh": "港股数据新鲜度检查崩溃 — 数据时效未知",
            },
        }
    write_freshness_json(result)
    return result
