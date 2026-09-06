"""Build the deterministic premarket "AM Edition" delta artifact -> site/am_edition.json.

Producer half of MO-PAID-011 (packet A-MO-W2-3). Authority ceiling: display_only.
No signal, rank, score, gate, sizing, ENTRY_OPEN, Prophet, portfolio or trade
authority is originated here — every value is either an owner fact read
verbatim from an already-committed deterministic artifact, a deterministic
derived comparison (prior close vs last known price), a deterministic
calendar fact, or a reference to the EXISTING model-generated prior-close
brief (site/master_brief.json), never re-summarised or re-ranked.

This builder does LIGHT fail-open reads of committed deterministic artifacts
(market_state, regime, neuralweb market_plane, release_forecast, live quotes,
master_brief) — no new collector, no vendor, no LLM/model/provider/quota path.
Every per-block gather is wrapped in try/except and degrades to a visible
UNAVAILABLE/NOT_COVERED block with a plain-word EN/ZH reason; a gather NEVER
removes the block and NEVER breaks the render. Returns 0 on ANY error.

Usage: python -m scripts.build_am_edition   (run anytime; safe pre-open or post)
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_am_edition")

SCHEMA = "am_edition.v1"
STATES = ("CURRENT", "STALE_WITH_LAST_KNOWN", "UNAVAILABLE", "NOT_COVERED", "NOT_YET_OPEN")
CLASSIFICATIONS = (
    "owner_fact",
    "deterministic_derived_comparison",
    "deterministic_calendar",
    "existing_model_generated_prior_close_brief",
)

# Fixed tuple of (symbol, label_en, label_zh) for the tape-since-prior-close block.
_TAPE_SYMBOLS = (
    ("SPY", "S&P 500 ETF", "标普500 ETF"),
    ("QQQ", "Nasdaq 100 ETF", "纳斯达克100 ETF"),
    ("^RUT", "Russell 2000", "罗素2000指数"),
)

# US regular session opens 09:30 America/New_York on a weekday (DST-aware).
_US_OPEN_HOUR_LOCAL = 9
_US_OPEN_MINUTE_LOCAL = 30
_NY_TZ = ZoneInfo("America/New_York")

# Regime quad code -> plain-word EN/ZH label (engine/regime.py:25-26 is the
# authoritative code->name map; this is display copy only, never re-derived).
_QUAD_LABELS = {
    "Q1": ("Goldilocks", "金发姑娘（低通胀增长）"),
    "Q2": ("Reflation", "再通胀"),
    "Q3": ("Stagflation", "滞胀"),
    "Q4": ("Growth-scare / Deflation", "增长恐慌/通缩"),
}


def _load_json_safe(path: Path) -> dict | list | None:
    """Load JSON from path; return None on any error."""
    try:
        return json.loads(path.read_bytes())
    except Exception as exc:  # noqa: BLE001
        log.debug("am_edition: could not read %s (%s)", path, exc)
        return None


def _load_committed(site: Path, data_dir: Path, site_rel: str, data_rel: str) -> dict | list | None:
    """Committed-artifact load order: site/ copy preferred, data/ fallback
    (mirrors scripts/build_aibrief.py:71-96)."""
    val = _load_json_safe(site / site_rel)
    if val is None:
        val = _load_json_safe(data_dir / data_rel)
    return val


def _norm_clock(raw: str | None) -> tuple[str | None, str]:
    """Normalise a clock field to (iso_utc, precision). precision in
    {"second","minute","day"}. Returns (None, "day") if unparseable."""
    if not raw or not isinstance(raw, str):
        return None, "day"
    s = raw.strip()
    # Date-only, e.g. "2026-09-04"
    if len(s) == 10 and s.count("-") == 2:
        try:
            d = date.fromisoformat(s)
            return f"{d.isoformat()}T00:00:00+00:00", "day"
        except Exception:  # noqa: BLE001
            return None, "day"
    try:
        s2 = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        precision = "second" if (dt.second or dt.microsecond) else "minute"
        return dt.isoformat(), precision
    except Exception:  # noqa: BLE001
        return None, "day"


def _classify(
    source_as_of: str | None,
    generated_at: str,
    max_age_minutes: int | None,
    *,
    covered: bool = True,
    session_open: bool = True,
) -> tuple[str, int | None]:
    """Pure. -> (state, age_minutes). NEVER returns CURRENT when age > max_age,
    and NEVER returns CURRENT for a future-stamped (negative-age) source."""
    if not covered:
        return "NOT_COVERED", None
    if source_as_of is None:
        return "UNAVAILABLE", None
    try:
        gen_dt = datetime.fromisoformat(generated_at)
        src_dt = datetime.fromisoformat(source_as_of)
    except Exception:  # noqa: BLE001
        return "UNAVAILABLE", None
    age_seconds = (gen_dt - src_dt).total_seconds()
    age_minutes = int(age_seconds // 60)
    if age_seconds < 0:
        # Future-stamped source: never trust it as CURRENT.
        return "UNAVAILABLE", age_minutes
    # Freshness is judged purely by age against the source's own budget —
    # premarket is a real product window (intraday-fastpath runs
    # */30 11-21 UTC) and a reading from this morning must be able to read
    # CURRENT before the cash open, not be forced STALE by session_open alone.
    if max_age_minutes is not None and age_minutes <= max_age_minutes:
        return "CURRENT", age_minutes
    return "STALE_WITH_LAST_KNOWN", age_minutes


def _block(
    key: str,
    *,
    title_en: str,
    title_zh: str,
    source_ref: str,
    source_owner: str,
    classification: str,
    source_as_of: str | None,
    max_age_minutes: int | None,
    generated_at: str,
    rows: list | None = None,
    reason_en: str | None = None,
    reason_zh: str | None = None,
    covered: bool = True,
    session_open: bool = True,
    precision: str | None = None,
) -> dict:
    """Builds ONE contract-shaped block. `precision` MUST be the precision
    returned alongside source_as_of by the caller's own _norm_clock() call —
    re-deriving it here from the already-normalised ISO string always
    reads "minute" (the ...T00:00:00+00:00 padding looks second-exact) and
    silently upgrades a day-precision source into a false-precise one."""
    assert classification in CLASSIFICATIONS, f"invalid classification: {classification}"
    state, age_minutes = _classify(
        source_as_of, generated_at, max_age_minutes, covered=covered, session_open=session_open
    )
    if precision is None:
        _, precision = _norm_clock(source_as_of) if source_as_of else (None, "day")
    out = {
        "key": key,
        "title_en": title_en,
        "title_zh": title_zh,
        "state": state,
        "source_ref": source_ref,
        "source_owner": source_owner,
        "source_as_of": source_as_of if state in ("CURRENT", "STALE_WITH_LAST_KNOWN") else None,
        "source_as_of_precision": precision if state in ("CURRENT", "STALE_WITH_LAST_KNOWN") else None,
        "age_minutes": age_minutes if state in ("CURRENT", "STALE_WITH_LAST_KNOWN") else None,
        "max_age_minutes": max_age_minutes,
        "classification": classification,
    }
    if state in ("UNAVAILABLE", "NOT_COVERED", "NOT_YET_OPEN"):
        out["state_reason_en"] = reason_en or "Not available yet."
        out["state_reason_zh"] = reason_zh or "暂不可用。"
    elif state == "STALE_WITH_LAST_KNOWN" and not reason_en:
        hours = (age_minutes or 0) // 60
        if hours >= 1:
            out["state_reason_en"] = f"Last updated {hours} hour(s) ago — showing the last known reading, not a fresh one."
            out["state_reason_zh"] = f"最近一次更新在{hours}小时前——展示的是最新已知读数，而非最新数据。"
        else:
            out["state_reason_en"] = f"Last updated {age_minutes} minute(s) ago — showing the last known reading, not a fresh one."
            out["state_reason_zh"] = f"最近一次更新在{age_minutes}分钟前——展示的是最新已知读数，而非最新数据。"
    else:
        out["state_reason_en"] = reason_en
        out["state_reason_zh"] = reason_zh
    if rows is not None:
        out["rows"] = rows
    return out


def _is_session_open_now(now: datetime) -> bool:
    """True once the US regular session (09:30 America/New_York, DST-aware)
    has opened for the given UTC instant on a weekday (exchange holiday
    calendar not modelled here -> weekday-only gate)."""
    local = now.astimezone(_NY_TZ)
    if local.weekday() >= 5:
        return False
    open_local = local.replace(hour=_US_OPEN_HOUR_LOCAL, minute=_US_OPEN_MINUTE_LOCAL, second=0, microsecond=0)
    return local >= open_local


def _previous_trading_day(d: date) -> date:
    """Walk back to the previous weekday (Mon-Fri). Exchange holiday calendar
    is not modelled here -> weekend-only gate, same scope as _is_session_open_now."""
    prev = d - timedelta(days=1)
    while prev.weekday() >= 5:
        prev = prev - timedelta(days=1)
    return prev


def _session_clock_block(generated_at: str, now: datetime) -> dict:
    is_weekend = now.weekday() >= 5
    session_open = _is_session_open_now(now)
    if is_weekend:
        reason_en = "Markets are closed for the weekend."
        reason_zh = "周末休市。"
    elif not session_open:
        reason_en = "US markets have not opened yet today."
        reason_zh = "美股今日尚未开盘。"
    else:
        reason_en = None
        reason_zh = None
    state = "NOT_YET_OPEN" if (is_weekend or not session_open) else "CURRENT"
    return {
        "key": "session_clock",
        "title_en": "Session clock",
        "title_zh": "交易时段",
        "state": state,
        "source_ref": "computed",
        "source_owner": "build_am_edition",
        "source_as_of": generated_at if state == "CURRENT" else None,
        "source_as_of_precision": "second" if state == "CURRENT" else None,
        "age_minutes": 0 if state == "CURRENT" else None,
        "max_age_minutes": None,
        "classification": "deterministic_calendar",
        "state_reason_en": reason_en,
        "state_reason_zh": reason_zh,
    }


def _tape_block(site: Path, generated_at: str, now: datetime, prior_close_date: str) -> dict:
    session_open = _is_session_open_now(now)
    try:
        quotes = _load_json_safe(site / "live" / "quotes.json")
        if not quotes or not isinstance(quotes, dict):
            return _block(
                "tape_since_prior_close",
                title_en="Since yesterday's close",
                title_zh="自昨日收盘以来",
                source_ref="site/live/quotes.json",
                source_owner="intraday-fastpath",
                classification="deterministic_derived_comparison",
                source_as_of=None,
                max_age_minutes=240,
                generated_at=generated_at,
                covered=False,
                reason_en="No live tape reading is available.",
                reason_zh="暂无实时行情读数。",
            )
        as_of_iso, precision = _norm_clock(quotes.get("asof"))
        rows = []
        qmap = quotes.get("quotes") or {}
        for sym, label_en, label_zh in _TAPE_SYMBOLS:
            q = qmap.get(sym)
            if not q:
                continue
            rows.append({
                "label_en": label_en,
                "label_zh": label_zh,
                "symbol": sym,
                "prior_close": round(float(q.get("prevClose")), 4) if q.get("prevClose") is not None else None,
                "last": round(float(q.get("price")), 4) if q.get("price") is not None else None,
                "change_pct": round(float(q.get("changePct")), 4) if q.get("changePct") is not None else None,
                "basis": q.get("basis"),
                "quote_as_of": as_of_iso,
            })
        blk = _block(
            "tape_since_prior_close",
            title_en="Since yesterday's close",
            title_zh="自昨日收盘以来",
            source_ref="site/live/quotes.json",
            source_owner="intraday-fastpath",
            classification="deterministic_derived_comparison",
            source_as_of=as_of_iso,
            max_age_minutes=240,
            generated_at=generated_at,
            rows=rows,
            session_open=session_open,
            precision=precision,
        )
        if blk["state"] == "CURRENT" and not session_open:
            # Premarket is a real reading window (intraday-fastpath runs
            # */30 11-21 UTC) — a fresh reading before the cash open is not
            # stale, but it IS worth disclosing as premarket, not a live tape.
            blk["state_reason_en"] = "Premarket reading — the regular session has not opened yet."
            blk["state_reason_zh"] = "盘前读数——正式交易时段尚未开始。"
        return blk
    except Exception as exc:  # noqa: BLE001
        log.debug("am_edition: tape block failed (%s)", exc)
        return _block(
            "tape_since_prior_close",
            title_en="Since yesterday's close",
            title_zh="自昨日收盘以来",
            source_ref="site/live/quotes.json",
            source_owner="intraday-fastpath",
            classification="deterministic_derived_comparison",
            source_as_of=None,
            max_age_minutes=240,
            generated_at=generated_at,
            covered=False,
            reason_en="The live tape reading could not be read.",
            reason_zh="无法读取实时行情读数。",
        )


def _owner_state_block(site: Path, data_dir: Path, generated_at: str) -> dict:
    try:
        d = _load_committed(site, data_dir, "market_state.json", "market_state/latest.json")
        if not d:
            return _block(
                "market_state", title_en="Market state", title_zh="市场状态",
                source_ref="data/market_state/latest.json", source_owner="nightly",
                classification="owner_fact", source_as_of=None, max_age_minutes=1440,
                generated_at=generated_at, covered=False,
                reason_en="Market state has not been generated yet.",
                reason_zh="市场状态尚未生成。",
            )
        as_of_iso, precision = _norm_clock(d.get("asof"))
        rows = [{
            "label_en": d.get("label_en"), "label_zh": d.get("label_zh"),
            "posture_en": d.get("posture_en"), "posture_zh": d.get("posture_zh"),
            "headline_en": d.get("headline_en"), "headline_zh": d.get("headline_zh"),
        }]
        return _block(
            "market_state", title_en="Market state", title_zh="市场状态",
            source_ref="data/market_state/latest.json", source_owner="nightly",
            classification="owner_fact", source_as_of=as_of_iso, max_age_minutes=1440,
            generated_at=generated_at, rows=rows, precision=precision,
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("am_edition: market_state block failed (%s)", exc)
        return _block(
            "market_state", title_en="Market state", title_zh="市场状态",
            source_ref="data/market_state/latest.json", source_owner="nightly",
            classification="owner_fact", source_as_of=None, max_age_minutes=1440,
            generated_at=generated_at, covered=False,
            reason_en="Market state could not be read.", reason_zh="无法读取市场状态。",
        )


def _regime_block(site: Path, data_dir: Path, generated_at: str) -> dict:
    try:
        d = _load_committed(site, data_dir, "regime.json", "regime/latest.json")
        if not d:
            return _block(
                "regime", title_en="Regime", title_zh="宏观周期",
                source_ref="data/regime/latest.json", source_owner="nightly",
                classification="owner_fact", source_as_of=None, max_age_minutes=1440,
                generated_at=generated_at, covered=False,
                reason_en="Regime has not been generated yet.", reason_zh="宏观周期尚未生成。",
            )
        as_of_raw = d.get("asof") or d.get("date")
        as_of_iso, precision = _norm_clock(as_of_raw)
        quad_code = d.get("label")  # internal slug e.g. "Q2" — never surfaced raw
        label_en, label_zh = _QUAD_LABELS.get(quad_code, (d.get("quad_name"), d.get("quad_name")))
        rows = [{"quad_name_en": label_en, "quad_name_zh": label_zh}]
        return _block(
            "regime", title_en="Regime", title_zh="宏观周期",
            source_ref="data/regime/latest.json", source_owner="nightly",
            classification="owner_fact", source_as_of=as_of_iso, max_age_minutes=1440,
            generated_at=generated_at, rows=rows, precision=precision,
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("am_edition: regime block failed (%s)", exc)
        return _block(
            "regime", title_en="Regime", title_zh="宏观周期",
            source_ref="data/regime/latest.json", source_owner="nightly",
            classification="owner_fact", source_as_of=None, max_age_minutes=1440,
            generated_at=generated_at, covered=False,
            reason_en="Regime could not be read.", reason_zh="无法读取宏观周期。",
        )


def _plane_block(site: Path, data_dir: Path, generated_at: str) -> dict:
    try:
        d = _load_committed(site, data_dir, "neuralweb/market_plane.json", "neuralweb/market_plane.json")
        if not d:
            return _block(
                "cross_asset_plane", title_en="Cross-asset plane", title_zh="跨资产全景",
                source_ref="data/neuralweb/market_plane.json", source_owner="nightly",
                classification="owner_fact", source_as_of=None, max_age_minutes=1440,
                generated_at=generated_at, covered=False,
                reason_en="Cross-asset plane has not been generated yet.",
                reason_zh="跨资产全景尚未生成。",
            )
        as_of_iso, precision = _norm_clock(d.get("asof"))
        verdict_raw = d.get("verdict")
        if isinstance(verdict_raw, dict):
            # Authority-shaped verdict objects (e.g. a `score`/rank field) are
            # NEVER passed through whole — only the plain-word verdict label
            # is display_only; whitelist it field-by-field.
            verdict_val = {
                "verdict": verdict_raw.get("verdict"),
                "label_en": verdict_raw.get("label_en"),
                "label_zh": verdict_raw.get("label_zh"),
            }
        else:
            verdict_val = verdict_raw
        rows = [{
            "verdict": verdict_val,
            "contradiction_count": d.get("contradiction_count"),
            "stale": d.get("stale"),
            # "gaps" carries internal component slugs (e.g. "options_structure")
            # with no bilingual plain-word pair -> dropped, never surfaced raw.
        }]
        return _block(
            "cross_asset_plane", title_en="Cross-asset plane", title_zh="跨资产全景",
            source_ref="data/neuralweb/market_plane.json", source_owner="nightly",
            classification="owner_fact", source_as_of=as_of_iso, max_age_minutes=1440,
            generated_at=generated_at, rows=rows, precision=precision,
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("am_edition: plane block failed (%s)", exc)
        return _block(
            "cross_asset_plane", title_en="Cross-asset plane", title_zh="跨资产全景",
            source_ref="data/neuralweb/market_plane.json", source_owner="nightly",
            classification="owner_fact", source_as_of=None, max_age_minutes=1440,
            generated_at=generated_at, covered=False,
            reason_en="Cross-asset plane could not be read.", reason_zh="无法读取跨资产全景。",
        )


def _calendar_block(site: Path, data_dir: Path, generated_at: str, session_date: str) -> dict:
    try:
        d = _load_committed(site, data_dir, "release_forecast.json", "release_forecast/latest.json")
        if not d:
            return _block(
                "todays_calendar", title_en="Today's calendar", title_zh="今日日程",
                source_ref="data/release_forecast/latest.json", source_owner="nightly",
                classification="deterministic_calendar", source_as_of=None, max_age_minutes=1440,
                generated_at=generated_at, covered=False,
                reason_en="Today's calendar has not been generated yet.",
                reason_zh="今日日程尚未生成。",
            )
        as_of_iso, precision = _norm_clock(d.get("asof"))
        upcoming = d.get("upcoming") or []
        rows = [u for u in upcoming if isinstance(u, dict) and str(u.get("date", "")).startswith(session_date)]
        return _block(
            "todays_calendar", title_en="Today's calendar", title_zh="今日日程",
            source_ref="data/release_forecast/latest.json", source_owner="nightly",
            classification="deterministic_calendar", source_as_of=as_of_iso, max_age_minutes=1440,
            generated_at=generated_at, rows=rows, precision=precision,
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("am_edition: calendar block failed (%s)", exc)
        return _block(
            "todays_calendar", title_en="Today's calendar", title_zh="今日日程",
            source_ref="data/release_forecast/latest.json", source_owner="nightly",
            classification="deterministic_calendar", source_as_of=None, max_age_minutes=1440,
            generated_at=generated_at, covered=False,
            reason_en="Today's calendar could not be read.", reason_zh="无法读取今日日程。",
        )


def _prior_brief_ref_block(site: Path, data_dir: Path, generated_at: str) -> dict:
    try:
        d = _load_committed(site, data_dir, "master_brief.json", "regime/master_brief.json")
        if not d:
            return _block(
                "prior_close_brief_ref", title_en="Yesterday's brief", title_zh="昨日简报",
                source_ref="site/master_brief.json", source_owner="master_brain",
                classification="existing_model_generated_prior_close_brief",
                source_as_of=None, max_age_minutes=1440, generated_at=generated_at, covered=False,
                reason_en="No prior-close brief is available yet.", reason_zh="暂无昨日收盘简报。",
            )
        as_of_iso, precision = _norm_clock(d.get("generated_at"))
        rows = [{
            "generated_at": as_of_iso,
            "state_asof": d.get("state_asof"),
            "lens": d.get("lens"),
            "link": "/aibrief.html",
        }]
        return _block(
            "prior_close_brief_ref", title_en="Yesterday's brief", title_zh="昨日简报",
            source_ref="site/master_brief.json", source_owner="master_brain",
            classification="existing_model_generated_prior_close_brief",
            source_as_of=as_of_iso, max_age_minutes=1440, generated_at=generated_at, rows=rows,
            precision=precision,
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("am_edition: prior brief ref block failed (%s)", exc)
        return _block(
            "prior_close_brief_ref", title_en="Yesterday's brief", title_zh="昨日简报",
            source_ref="site/master_brief.json", source_owner="master_brain",
            classification="existing_model_generated_prior_close_brief",
            source_as_of=None, max_age_minutes=1440, generated_at=generated_at, covered=False,
            reason_en="The prior-close brief could not be read.", reason_zh="无法读取昨日收盘简报。",
        )


def _feasibility(tape_block: dict, prior_close_cut: str) -> tuple[str, str, str | None, str | None]:
    """-> (feasibility, internal_cause_for_logs_only, cause_en, cause_zh).
    The internal cause (repo paths, line numbers, raw timestamps) is for the
    build log ONLY — it is never a customer-facing field. cause_en/cause_zh
    are the plain-word pair actually shipped in the payload."""
    src = tape_block.get("source_as_of")
    if src is None:
        return (
            "BLOCKED",
            "site/live/quotes.json is gitignored (.gitignore) and only force-added by "
            "intraday-fastpath.yml; no committed tape reading is readable at all",
            "No live tape reading has been committed yet.",
            "暂无已提交的实时行情读数。",
        )
    try:
        src_dt = datetime.fromisoformat(src)
        cut_dt = datetime.fromisoformat(prior_close_cut)
    except Exception:  # noqa: BLE001
        return (
            "BLOCKED",
            "site/live/quotes.json is gitignored and only force-added by intraday-fastpath.yml; "
            "the committed as_of could not be parsed",
            "The committed tape reading could not be read.",
            "无法读取已提交的实时行情读数。",
        )
    if src_dt >= cut_dt:
        return "AVAILABLE", "", None, None
    return (
        "DEGRADED",
        f"site/live/quotes.json is gitignored and only force-added by intraday-fastpath.yml; "
        f"newest committed as_of={src} is older than the prior-close cut {prior_close_cut}",
        "The newest committed tape reading is older than yesterday's close — showing the last known values.",
        "最新已提交的行情读数早于昨日收盘——展示的是最新已知数值。",
    )


def build_payload(site: Path, data_dir: Path, *, now: datetime | None = None) -> dict:
    """PURE-ish, importable, deterministic given (site, data_dir, now)."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    generated_at = now.isoformat()
    session_date = now.strftime("%Y-%m-%d")
    # Previous TRADING day, not previous calendar day: a calendar walk-back
    # publishes Sunday as "prior_close_date" every Monday premarket (and any
    # day after a market holiday), which then falsely DEGRADEs feasibility
    # against a close that never happened. Exchange holiday calendar is not
    # modelled here (weekend-only gate, same scope as _is_session_open_now).
    prior_close_date = _previous_trading_day(now.date()).strftime("%Y-%m-%d")
    # Prior-close cut: 20:00 UTC (4pm ET, approx) on the prior trading date.
    prior_close_cut = f"{prior_close_date}T20:00:00+00:00"
    session_open = _is_session_open_now(now)

    blocks = []
    blocks.append(_session_clock_block(generated_at, now))
    tape = _tape_block(site, generated_at, now, prior_close_date)
    blocks.append(tape)
    blocks.append(_owner_state_block(site, data_dir, generated_at))
    blocks.append(_regime_block(site, data_dir, generated_at))
    blocks.append(_plane_block(site, data_dir, generated_at))
    blocks.append(_calendar_block(site, data_dir, generated_at, session_date))
    blocks.append(_prior_brief_ref_block(site, data_dir, generated_at))

    feasibility, feasibility_cause_internal, feasibility_cause_en, feasibility_cause_zh = _feasibility(
        tape, prior_close_cut
    )
    if feasibility_cause_internal:
        log.debug("am_edition: feasibility=%s cause=%s", feasibility, feasibility_cause_internal)

    null_count = sum(1 for b in blocks if b["state"] in ("UNAVAILABLE", "NOT_COVERED"))

    payload = {
        "schema": SCHEMA,
        "display_only": True,
        "authority": "display_only",
        "generated_at": generated_at,
        "session_date": session_date,
        "session_state": "NOT_YET_OPEN" if not session_open else "OPEN",
        "prior_close_date": prior_close_date,
        "morning_source_feasibility": feasibility,
        "morning_source_feasibility_cause_en": feasibility_cause_en,
        "morning_source_feasibility_cause_zh": feasibility_cause_zh,
        "null_count": null_count,
        "blocks": blocks,
    }
    return payload


def main() -> int:
    try:
        cfg = config.load()
        site = Path(cfg["storage"]["site_dir"])
        site.mkdir(parents=True, exist_ok=True)
        data_dir = Path(config.ROOT) / "data"

        payload = build_payload(site, data_dir)
        out_path = site / "am_edition.json"
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        log.info("wrote %s (%d bytes)", out_path, out_path.stat().st_size)
    except Exception as e:  # noqa: BLE001 — additive, must never break the site build
        log.error("AM edition build failed (%s); skipping", e)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
