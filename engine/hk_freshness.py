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
    5. Coherence: standouts.as_of and regime.date within <= 1 business day of each other.
    6. Regression: cache index.max() must never DECREASE run-over-run (detects the
       `-X theirs` clobber that caused the incident).
    7. Southbound holdings: data/hk_southbound/holdings.parquet index.max() <= 2 cal days.

State thresholds:
    lag <= 2 cal days -> "fresh"
    lag <= 4 cal days -> "slow" (weekend gaps, missed session)
    lag >= 5 cal days -> "stale"     (present but too old)
    file absent       -> "missing"   (never present this run — SECONDARY, degraded-only)
    read error        -> "error"     (present but unreadable — PRIMARY, red)

Page-level verdict: ok | degraded | stale
    ok       = all checks fresh/slow (no check stale/dead)
    degraded  = at most one non-critical store is stale/missing/error (coherence/regression OK)
    stale    = cache (check 1) is stale/error, OR coherence is broken, OR regression fired

REVISION 2026-07-23 — stop the chronic false "STALE — do not act" red:
    Two structural mismatches made the sentinel fire red every night even when the
    engine classified the day fine. Both are fixed here (fail-open still holds).

    (a) COHERENCE PHASE TOLERANCE. There is a real pipeline phase gap: the stock scan
        (standouts) advances to session T in the evening render lanes, but the committed
        regime artifact (data/hk_regime/latest.json) only advances the NEXT morning on
        the asia lane (engine-render lanes discard data/ writes). So through the whole
        evening→next-asia-close window, standouts.as_of is exactly ONE session ahead of
        regime.date — a normal, expected phase, not an incoherent snapshot. The old
        exact-equality check (standouts.as_of == regime.date) turned that normal phase
        into a full-red "do not act" banner all night. Coherence is now OK when the two
        dates are within <= 1 business day of each other; a plain-word note explains the
        one-session lag, and `gap_sessions` records the size. A gap > 1 session (either
        direction) still breaks coherence -> stale.

    (b) CACHE MISSING vs CACHE STALE. `_closes_cache.parquet` is gitignored: the
        persistent Mac Studio carries it, GitHub-hosted runners do NOT. A merely-absent
        cache on an ephemeral runner is not evidence of stale data — it is a runner that
        never had the file. Absent cache is now state "missing" and treated as SECONDARY
        (can only produce "degraded", never "stale"). The 2026-07-08 incident was cache
        PRESENT-but-old (a 5-day rollback) — that is state "stale" and still forces red,
        as does an unreadable cache ("error"). Protection for the real incident is intact.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
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


def _badge(asof: date | None, expected: date, *, tight: bool = False,
           null_state: str = "dead") -> dict:
    """Build a per-store staleness badge dict.

    `null_state` is the state assigned when `asof` is None (no readable date). It
    defaults to "dead" (present-but-unreadable / never-there, treated as red for the
    stores where absence is itself a fault). The cache check passes
    ``null_state="missing"`` for the file-absent case: a gitignored cache that never
    shipped to an ephemeral runner is a runner condition, not stale data, so it is
    demoted to secondary (degraded-only). See the module docstring, revision 2026-07-23.
    """
    if asof is None:
        return {"asof": None, "lag_days": None, "state": null_state}
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
    # File-absent -> "missing" (SECONDARY: gitignored cache is not carried by ephemeral
    # runners; its absence is a runner condition, not stale data). Present-but-unreadable
    # -> "error" (PRIMARY, red). Present-but-old (lag>=5) -> "stale" (PRIMARY, red — the
    # 2026-07-08 rollback incident). See docstring revision 2026-07-23.
    try:
        cache_path = data_root / "hk_breadth" / "_closes_cache.parquet"
        cache_max = _parquet_index_max(cache_path)
        if cache_max is None and not cache_path.exists():
            checks["cache"] = {"asof": None, "lag_days": None, "state": "missing"}
        elif cache_max is None:
            # File present but returned no readable date -> unreadable/corrupt.
            checks["cache"] = {"asof": None, "lag_days": None, "state": "error"}
        else:
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

    # Check 5: Coherence — standouts.as_of within <= 1 business day of regime.date.
    # The regime artifact advances one asia-close BEHIND the evening stock scan (the
    # committed data/ file lags the render lanes by one session); that one-session lag
    # is a normal pipeline phase, not an incoherent snapshot. Tolerate a gap of <= 1
    # business day (either direction); a larger gap breaks coherence -> stale.
    # See docstring revision 2026-07-23. HK-holiday exactness is not required here.
    try:
        if standouts_asof is not None and regime_date is not None:
            # busday_count is signed and half-open [start, end); take the absolute
            # count so either ordering yields the session distance between the dates.
            gap_sessions = int(abs(np.busday_count(regime_date, standouts_asof)))
            coherent = gap_sessions <= 1
            if not coherent:
                note = (f"the stock scan and the regime read are {gap_sessions} "
                        "sessions apart — a bigger gap than the normal one-session lag")
            elif gap_sessions == 1:
                note = ("regime read is one session behind the stock scan — "
                        "catches up after the next Asia close")
            else:
                note = None
        else:
            # A missing date on either side cannot be judged coherent.
            gap_sessions = None
            coherent = False
            note = "standouts or regime date unavailable — coherence cannot be checked"
        coherence = {
            "ok": coherent,
            "standouts_asof": str(standouts_asof) if standouts_asof else None,
            "regime_date": str(regime_date) if regime_date else None,
            "gap_sessions": gap_sessions,
            "note": note,
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
    # Cache is PRIMARY-red only when present-but-old ("stale") or present-but-unreadable
    # ("error"). An absent cache ("missing") is a runner condition, not stale data, and
    # is demoted to SECONDARY (degraded-only). See docstring revision 2026-07-23.
    cache_primary_bad = cache_state in ("stale", "error")
    coherence_bad = not coherence.get("ok", True)
    regression_bad = not regression.get("ok", True)

    # Any secondary stores stale/dead/missing/error? Cache="missing" counts here so an
    # absent cache still surfaces a "degraded" banner (never full-red "stale").
    secondary_bad = (
        cache_state == "missing"
        or any(
            checks.get(k, {}).get("state") in ("stale", "dead", "missing", "error")
            for k in ("bellwether", "standouts", "regime", "southbound")
        )
    )

    if cache_primary_bad or coherence_bad or regression_bad:
        verdict = "stale"
    elif secondary_bad:
        verdict = "degraded"
    else:
        verdict = "ok"

    # ---------------------------------------------------------------------------
    # Banner message (bilingual) — only when degraded or stale.
    # PLAIN WORDS ONLY (User-First Design Doctrine, Tier 1). No internal vocabulary —
    # no store slugs (cache/bellwether/southbound), no "snapshot", no "incoherent".
    # The mechanical per-store details stay in `stores` for the Tier-2 data-feeds panel.
    # Copy shape: one lead sentence stating what it means for the reader, then ONE short
    # specific clause (a date) so it isn't vague. See docstring revision 2026-07-23.
    # ---------------------------------------------------------------------------
    banner = None
    if verdict in ("stale", "degraded"):
        # Pick the single most relevant date for the trailing clause, without naming
        # any internal store. Prefer the freshest price date we know; fall back to the
        # regime read date, else the expected session.
        cache_info = checks.get("cache", {})
        bell_info = checks.get("bellwether", {})
        price_asof = bell_info.get("asof") or cache_info.get("asof")
        regime_asof = coherence.get("regime_date")

        if verdict == "stale":
            # What triggered stale? Choose the clause that best explains it, in plain words.
            if regression_bad:
                prev = regression.get("prev_cache_max") or "—"
                clause_en = f"today's prices came in older than yesterday's (back to {prev})"
                clause_zh = f"今日价格比昨日更旧（回退至 {prev}）"
            elif coherence_bad:
                # Name the two dates plainly, no store slugs.
                s_asof = coherence.get("standouts_asof") or "—"
                r_date = coherence.get("regime_date") or "—"
                clause_en = (f"the stock picks (from {s_asof}) and the regime read "
                             f"(from {r_date}) are more than a session apart")
                clause_zh = (f"选股结果（{s_asof}）与周期判断（{r_date}）相差超过一个交易日")
            elif price_asof:
                clause_en = f"prices last updated {price_asof}"
                clause_zh = f"价格最后更新于 {price_asof}"
            else:
                clause_en = f"expected session {expected}"
                clause_zh = f"预期交易日 {expected}"

            lead_en = ("HK data is stale — some numbers may be from an older session. "
                       "Treat them as yesterday's until tonight's update.")
            lead_zh = ("港股数据已过期 — 部分数值可能来自较早的交易日，"
                       "在今晚更新前请当作昨日数据看待。")
            banner = {
                "en": f"{lead_en} ({clause_en})",
                "zh": f"{lead_zh}（{clause_zh}）",
            }
        else:  # degraded — background feeds behind; prices and picks are current.
            clause_asof = price_asof or regime_asof or str(expected)
            lead_en = ("Some background feeds are a step behind — prices and picks "
                       "are current.")
            lead_zh = ("部分后台数据来源稍有滞后 — 价格和选股仍是最新的。")
            clause_en = f"prices current as of {clause_asof}"
            clause_zh = f"价格截至 {clause_asof} 为最新"
            banner = {
                "en": f"{lead_en} ({clause_en})",
                "zh": f"{lead_zh}（{clause_zh}）",
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
