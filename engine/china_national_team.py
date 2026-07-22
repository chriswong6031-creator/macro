"""National Team Radar — detect Chinese state market intervention from its public footprint.

LEAF · DISPLAY/CONTEXT-ONLY · KEYLESS. The "国家队 / national team" radar for
china_policy_watch.html. State intervention (Central Huijin, China Reform/Chengtong, CSF,
state insurers, PBoC facilities) is *loud by design* — the point is to restore confidence —
so it leaves footprints in free data we already collect. This engine fans those footprints
into ONE deterministic display-tier intensity read. See research/NATIONAL_TEAM_RADAR_SPEC.md.

EPISTEMICS (HOUSE LAW — non-negotiable):
  * ``is_context_only: True`` — context/detection infrastructure; ships freely, no gauntlet.
  * ``may_originate=False, may_escalate=False`` — the composite is a deterministic *intensity*
    read, NOT an alpha score, NOT a rank/size/gate input. Never wire it into a trade gate.
  * Nulls printed — a tell with no data reads ``state:"null"``, ``have_data:False`` and is
    excluded from the renormalized composite. Never hidden, never a crash, never a NaN.
  * The news classifier uses DETERMINISTIC keyword rules over an already-collected tape; it
    de-noises, it does not originate a signal (LLMs may not originate).
  * The word "validated" never appears in a user-facing string (CI-enforced).

DATA SOURCES (all verified on disk 2026-07-22):
  etf_creation        data/china_flows/etf_shares.parquet (per-fund unit counts, ~5wk history)
  largecap_divergence data/china/{510050,510300}.SS (large) vs {510500,159915.SZ} (small), close
  market_rescue       engine.china_policy_transmission.snapshot()['policy_impulse']
  state_media_drumbeat/facility_watch  data/china_news_vector/events.parquet (tier-1 + keyword)
  pboc_posture        engine.china_pboc_stance.snapshot() + data/china_pboc/repo_rates.parquet FR007
  buyback_cascade     NEW ledger data/china_national_team/buyback_daily.parquet (w/w accel)
  margin_recovery     data/china_margin/balance.parquet fin_balance 5d inflection

ETF-CREATION STATISTIC — DELIBERATE DEVIATION FROM THE SPEC'S "cross-fund median" NOTE.
  The spec's data-source table suggests reusing china_participation's cross-fund *median* 5d
  z (``etf_share_chg``). That statistic is STRUCTURALLY BLIND to a state rescue: the national
  team buys the broad/tech INDEX ETFs specifically (CSI 300, STAR 50, SSE 50, CSI 500, ChiNext),
  so a concentrated 2-3 fund creation burst is a MINORITY of the ~21-fund panel and the median
  washes it out — on the real 2026-07-21 rescue (CSI 300 units +24%, STAR 50 +30% over the
  window) the cross-fund median 5d z is NEGATIVE (-0.75 on 2026-07-22). The spec's OWN verify
  step requires this rescue to FIRE etf_creation, and the receipt names CSI 300 / STAR 50
  explicitly — i.e. the tell is about *index-ETF* creation, not the panel median. We therefore
  fire on the MAX per-fund 5d creation z across the national-team index/tech ETFs, taken over a
  short trailing lookback (the footprint persists 1-2 sessions after the buy). We reuse
  china_participation's data path + per-fund-z + gap-handling idiom; only the aggregation
  (max-of-team vs median-of-all) differs, and it differs for a documented, tested reason.

Never raises: snapshot() degrades any missing input to a null tell + a named ``gaps`` entry.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "china_national_team.v1"

# --------------------------------------------------------------------------- #
# Tell registry — key, tier, weight, bilingual label. Firing rules live in the
# per-tell evaluators below. Weights renormalize over tells with have_data=True.
# --------------------------------------------------------------------------- #
TELLS = (
    # key                    tier          weight  label_en                 label_zh
    ("etf_creation",         "coincident", 0.28,  "ETF creation surge",     "ETF份额激增"),
    ("largecap_divergence",  "coincident", 0.16,  "Index-heavyweight lift",  "权重股护指数"),
    ("market_rescue",        "coincident", 0.14,  "Policy rescue impulse",   "政策托市"),
    ("state_media_drumbeat", "leading",    0.14,  "State-media drumbeat",    "官媒稳市喊话"),
    ("facility_watch",       "leading",    0.10,  "PBoC support facility",   "央行支持工具"),
    ("pboc_posture",         "leading",    0.06,  "PBoC easing into stress", "央行逆势宽松"),
    ("buyback_cascade",      "confirming", 0.08,  "SOE buyback cascade",     "国企回购潮"),
    ("margin_recovery",      "confirming", 0.04,  "Margin balance turning",  "两融企稳回升"),
)
_TELL_META = {k: (tier, w, en, zh) for (k, tier, w, en, zh) in TELLS}

# National-team ETFs — the broad-index + tech/STAR funds the state actually buys to
# defend the index. (ticker col in etf_shares.parquet -> short EN label for the receipt.)
_TEAM_ETFS = {
    "sh_510300": "CSI 300",
    "sh_588000": "STAR 50",
    "sh_510050": "SSE 50",
    "sh_510500": "CSI 500",
    "sh_159915": "ChiNext",
}
_ETF_LOOKBACK = 2          # trailing sessions to scan for the creation burst (footprint persists)
# Recalibrated (review 2026-07-22): the national-team RESCUE signature is BREADTH + size —
# multiple broad index ETFs creating units at once — not one noisy fund. A bare single-fund
# z>=1 (null max-of-N mean ~1.3) fired ~82% under noise, and even a lone 6% fund fires ~28% on
# the real (turbulent) sample. Require >=2 team ETFs EACH >=6%, OR one extreme (>=15%) outlier.
_ETF_PCT_FIRE = 6.0        # per-fund window unit-% counted toward the breadth of a creation wave
_ETF_COFIRE_MIN = 2        # min team ETFs each >= _ETF_PCT_FIRE to fire (the broad-buy signature)
_ETF_PCT_SOLO = 15.0       # single-fund unit surge % that fires alone (concentrated outlier)
_ETF_PCT_FULL = 18.0       # unit surge % mapping to full strength (07-21 STAR50 ~22% -> ~1.0)

_DIVERGENCE_FIRE_PP = 1.5  # 5d (large - small) return spread threshold, percentage points
_FR007_STRESS_Z = -1.0    # FR007 z ceiling for "easing into tight liquidity"
_DRUMBEAT_MIN_HITS = 2    # tier-1 stability hits in 7d to fire
_FACILITY_MIN_HITS = 1    # tier-1 facility hits in 30d to fire
_CASCADE_ACCEL_FIRE = 0.20  # board-proposal w/w acceleration to fire (+20%)


def _ledger_write_ok() -> bool:
    """Forward ledgers advance ONLY on the nightly asia lane (CN_LANE=asia) — house law: nightly
    is the sole advancer; intraday / render calls read the ledgers but must never persist a row
    (an intraday call would otherwise freeze that moment's score/band into the day's row)."""
    return os.environ.get("CN_LANE", "") == "asia"

# Deterministic bilingual keyword regexes over events.parquet.title (EN + ZH).
_KW_DRUMBEAT = re.compile(
    r"维护|稳定|平准|国家队|长期投资价值|增持|回购|稳市|信心|resolute|stabiliz|national team",
    re.IGNORECASE,
)
_KW_FACILITY = re.compile(
    r"互换便利|SFISF|再贷款|回购增持|swap facility|relending",
    re.IGNORECASE,
)

# Band thresholds (score -> band). accent tokens are NON-FLIPPING (never up/down).
_BANDS = (
    # min_score, band,        accent,   band_en,                      band_zh
    (68, "on",       "act",   "Hand on — active defense",  "出手 — 主动护盘"),
    (42, "elevated", "warn",  "Building — tells rising",   "升温 — 迹象增多"),
    (18, "quiet",    "ok",    "Quiet — trading freely",    "平静 — 自由交易"),
    (0,  "dormant",  "muted", "Off tape — hand withdrawn", "离场 — 政策之手已收"),
)

_STANCE = {
    "on": {
        "en": ("The state is actively defending the floor. Large-cap index levels are being "
               "held, but breadth is hollow — small caps and growth are left behind. Watch, "
               "don't chase: a defended floor is not a bull market, and the real risk is the "
               "exit, when the hand withdraws."),
        "zh": ("国家队正在主动护盘。大盘权重指数被托住，但市场宽度空心 —— 中小盘与成长股被抛在后面。"
               "观望，不要追高：被托住的地板不是牛市，真正的风险在退出之时，即政策之手撤离之际。"),
    },
    "elevated": {
        "en": ("Intervention tells are building — state media is turning supportive and policy "
               "is leaning in, but broad buying isn't confirmed yet. Watch for the ETF-creation "
               "fingerprint to fire."),
        "zh": ("干预迹象正在增多 —— 官媒转向维稳、政策开始倾斜，但尚未确认大范围买入。"
               "留意ETF份额激增这一指纹是否点亮。"),
    },
    "quiet": {
        "en": "No active state defense right now. The market is trading on its own two feet.",
        "zh": "当前没有国家队的主动护盘。市场靠自己的双脚在交易。",
    },
    "dormant": {
        "en": ("The state hand is off the tape. Policy is neutral-to-tightening; no intervention "
               "signals."),
        "zh": "政策之手已离场。政策中性偏紧；没有干预信号。",
    },
}


# --------------------------------------------------------------------------- #
# Data root + tiny read helpers (all degrade to None/empty, never raise)
# --------------------------------------------------------------------------- #
def _data_root() -> str:
    """Absolute path to the data dir. Single choke-point so tests can redirect reads."""
    try:
        return str(config.data_dir())
    except Exception:  # noqa: BLE001
        return os.path.join(os.path.dirname(__file__), "..", "data")


def _read(*parts: str) -> pd.DataFrame | None:
    path = os.path.join(_data_root(), *parts)
    if not os.path.exists(path):
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:  # noqa: BLE001
        log.debug("national_team read %s failed: %s", path, e)
        return None


def _close(sym: str) -> pd.Series | None:
    """Close series for a china/*.SS|.SZ parquet, handling the rare MultiIndex column shape."""
    df = _read("china", f"{sym}.parquet")
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        if "close" not in df.columns.get_level_values(-1):
            return None
        c = df.xs("close", axis=1, level=-1)
        c = c.iloc[:, 0] if isinstance(c, pd.DataFrame) else c
    else:
        if "close" not in df.columns:
            return None
        c = df["close"]
    c.index = pd.to_datetime(c.index)
    return c.dropna().sort_index()


def _clamp01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def _fmt_pct(x: float) -> str:
    return f"{x:+.0f}%"


def _tell(key: str, state: str, strength: float = 0.0, value_fmt: str | None = None,
          receipt_en: str = "", receipt_zh: str = "", have_data: bool = True) -> dict:
    """Assemble one tell dict from the registry meta + evaluated firing state."""
    tier, weight, label_en, label_zh = _TELL_META[key]
    return {
        "key": key, "tier": tier,
        "label_en": label_en, "label_zh": label_zh,
        "state": state,                       # firing | quiet | null
        "strength": round(_clamp01(strength), 4) if have_data else 0.0,
        "value_fmt": value_fmt,
        "receipt_en": receipt_en, "receipt_zh": receipt_zh,
        "have_data": bool(have_data), "weight": weight,
    }


# --------------------------------------------------------------------------- #
# Per-tell evaluators — each returns a tell dict + optional gap string.
# A missing/short input => state:"null", have_data:False (printed, not hidden).
# --------------------------------------------------------------------------- #
def _eval_etf_creation() -> tuple[dict, str | None]:
    """MAX per-fund 5d creation z across national-team index/tech ETFs, over a short lookback.

    See the module docstring: the cross-fund MEDIAN is blind to a concentrated state buy, so
    we fire on the strongest team-ETF creation z. Receipt reports CSI 300 / STAR 50 unit %."""
    df = _read("china_flows", "etf_shares.parquet")
    if df is None or df.empty or len(df) < 3:
        return _tell("etf_creation", "null", have_data=False), \
            "etf_creation: china_flows/etf_shares.parquet absent or <3 rows"
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    cols = [c for c in _TEAM_ETFS if c in df.columns]
    if not cols:
        return _tell("etf_creation", "null", have_data=False), \
            "etf_creation: no national-team ETF columns present in etf_shares.parquet"

    # Per-fund window unit-% (peak vs window start). The national-team rescue signature is
    # BREADTH + size: multiple broad index ETFs creating units at once — NOT one noisy fund
    # (a bare single-fund threshold fired the tell on a majority of days; review 2026-07-22).
    win = df[cols].iloc[-(_ETF_LOOKBACK + 1):]
    if len(win) < 2:
        return _tell("etf_creation", "null", have_data=False), \
            "etf_creation: <2 sessions of ETF unit history (too short for a creation read)"

    def _pct(tk: str) -> float | None:
        first = win[tk].iloc[0]
        if tk not in win.columns or pd.isna(first) or first == 0:
            return None
        return (win[tk].max() / first - 1.0) * 100.0

    pcts = {tk: _pct(tk) for tk in cols}
    avail = [p for p in pcts.values() if p is not None]
    if not avail:
        return _tell("etf_creation", "null", have_data=False), \
            "etf_creation: no usable team-ETF unit columns in etf_shares.parquet"
    max_pct = max(avail)
    n_big = sum(1 for p in avail if p >= _ETF_PCT_FIRE)   # team ETFs at rescue-scale creation

    # Fire on the broad-buy signature (>=2 team ETFs each >=6%) OR one extreme outlier (>=15%).
    fires = (n_big >= _ETF_COFIRE_MIN) or (max_pct >= _ETF_PCT_SOLO)
    strength = _clamp01(max_pct / _ETF_PCT_FULL) if fires else 0.0

    csi, star = pcts.get("sh_510300"), pcts.get("sh_588000")
    parts_en, parts_zh, vf = [], [], []
    if csi is not None:
        parts_en.append(f"CSI 300 units {_fmt_pct(csi)}"); parts_zh.append(f"沪深300份额{_fmt_pct(csi)}")
        vf.append(_fmt_pct(csi))
    if star is not None:
        parts_en.append(f"STAR 50 {_fmt_pct(star)}"); parts_zh.append(f"科创50 {_fmt_pct(star)}")
        vf.append(_fmt_pct(star))
    ndays = min(_ETF_LOOKBACK, len(df) - 1)
    if parts_en:
        rec_en = ", ".join(parts_en) + f" ({ndays}d)"
        rec_zh = "，".join(parts_zh) + f"（{ndays}日）"
    else:
        rec_en = f"peak team-ETF unit creation {_fmt_pct(max_pct)} ({ndays}d)"
        rec_zh = f"权重ETF份额峰值 {_fmt_pct(max_pct)}（{ndays}日）"
    if fires and n_big >= _ETF_COFIRE_MIN:
        rec_en += f" · {n_big} ETFs co-creating"; rec_zh += f" · {n_big}只ETF齐创设"

    gap = ("etf_creation: etf_shares history ~5wk (thin, disclosed); fires on the broad national-"
           "team signature (>=2 team ETFs each >=6%, or one >=15%) — not a single noisy fund")
    return _tell("etf_creation", "firing" if fires else "quiet",
                 strength=strength,
                 value_fmt=(" / ".join(vf) if vf else _fmt_pct(max_pct)),
                 receipt_en=rec_en, receipt_zh=rec_zh, have_data=True), gap


def _eval_largecap_divergence() -> tuple[dict, str | None]:
    """5d return spread: large-cap avg (SSE 50 + CSI 300) minus small-cap avg (CSI 500 + ChiNext).

    Positive + large = the index is being 'pulled' by heavyweights while breadth lags — the
    hollow-breadth signature of an index defense."""
    large = [_close("510050.SS"), _close("510300.SS")]
    small = [_close("510500.SS"), _close("159915.SZ")]
    large = [s for s in large if s is not None and len(s) >= 6]
    small = [s for s in small if s is not None and len(s) >= 6]
    if not large or not small:
        return _tell("largecap_divergence", "null", have_data=False), \
            "largecap_divergence: large/small-cap ETF close series absent or <6 rows"

    def _ret5(s: pd.Series) -> float:
        return (s.iloc[-1] / s.iloc[-6] - 1.0) * 100.0

    large_r = float(np.mean([_ret5(s) for s in large]))
    small_r = float(np.mean([_ret5(s) for s in small]))
    spread = large_r - small_r
    fires = spread >= _DIVERGENCE_FIRE_PP
    rec_en = f"Index heavyweights {large_r:+.1f}% vs small-caps {small_r:+.1f}% (5d)"
    rec_zh = f"权重股{large_r:+.1f}% vs 中小盘{small_r:+.1f}%（5日）"
    return _tell("largecap_divergence", "firing" if fires else "quiet",
                 strength=_clamp01(spread / 5.0) if fires else 0.0,
                 value_fmt=f"{spread:+.1f}pp",
                 receipt_en=rec_en, receipt_zh=rec_zh, have_data=True), None


def _eval_market_rescue() -> tuple[dict, str | None]:
    """policy_impulse in {market_rescue, targeted_support} = the state is leaning on markets."""
    try:
        from engine import china_policy_transmission as tr
        snap = tr.snapshot()
    except Exception as e:  # noqa: BLE001
        return _tell("market_rescue", "null", have_data=False), \
            f"market_rescue: china_policy_transmission unavailable ({e})"
    if not snap or not snap.get("policy_impulse"):
        return _tell("market_rescue", "null", have_data=False), \
            "market_rescue: policy_impulse unavailable"
    impulse = snap["policy_impulse"]
    if impulse == "market_rescue":
        strength, lab_en, lab_zh = 1.0, "market rescue", "全力托市"
    elif impulse == "targeted_support":
        strength, lab_en, lab_zh = 0.6, "targeted support", "定向支持"
    else:
        return _tell("market_rescue", "quiet", strength=0.0, value_fmt=impulse,
                     receipt_en=f"Policy impulse: {impulse}", receipt_zh=f"政策脉冲：{impulse}",
                     have_data=True), None
    return _tell("market_rescue", "firing", strength=strength, value_fmt=lab_en,
                 receipt_en=f"Policy impulse: {lab_en}", receipt_zh=f"政策脉冲：{lab_zh}",
                 have_data=True), None


def _news_events() -> pd.DataFrame | None:
    """china_news_vector/events.parquet with a robust effective-timestamp column (_eff, UTC)."""
    df = _read("china_news_vector", "events.parquet")
    if df is None or df.empty or "title" not in df.columns:
        return None
    df = df.copy()
    sd = pd.to_datetime(df.get("seendate"), errors="coerce", utc=True)
    fs = pd.to_datetime(df.get("first_seen_utc"), errors="coerce", utc=True)
    df["_eff"] = sd.fillna(fs)
    return df


def _news_hits(df: pd.DataFrame, pattern: re.Pattern, days: int) -> tuple[int | None, int]:
    """(tier1 keyword hits in-window, tier1 rows in-window). hits=None => no tier-1 data to read.

    Strictly tier-1 gated (state/official) — a stability read must not be originated by tier-2
    retail wires. When there are zero tier-1 rows in the window the tell has NO data (null),
    which is the honest state of the current tape (tier-1 patch is stale)."""
    now = pd.Timestamp.now(tz="UTC")
    cutoff = now - pd.Timedelta(days=days)
    win = df[(df["_eff"].notna()) & (df["_eff"] >= cutoff)]
    t1 = win[win.get("source_tier") == 1]
    if t1.empty:
        return None, 0
    titles = t1["title"].astype(str)
    hits = int(titles.str.contains(pattern, na=False).sum())
    return hits, len(t1)


def _cctv_tone_signal() -> tuple[float, float | None, str | None]:
    """CCTV 新闻联播 pro-growth tone z vs its own history → (strength, z, gap).

    CCTV's nightly bulletin is top-tier state media; a rising pro-growth/stability
    emphasis (tone above its own norm) is the classic 'national-team op-ed' leading
    tell. Deterministic z-score over an already-collected scalar — de-noises a tape,
    does not originate a signal."""
    df = _read("china_news", "cctv_tone.parquet")
    if df is None or df.empty or "tone" not in df.columns:
        return 0.0, None, "state_media_drumbeat: cctv_tone.parquet absent (tier-1 tape also thin)"
    s = pd.to_numeric(df["tone"], errors="coerce").dropna()
    if len(s) < 10:
        return 0.0, None, "state_media_drumbeat: cctv_tone history <10 rows (thin)"
    recent = float(s.tail(3).mean())
    base = s.iloc[:-3] if len(s) > 6 else s   # z the recent window against history that EXCLUDES it
    mu, sd = float(base.mean()), float(base.std(ddof=0))
    z = (recent - mu) / sd if sd > 0 else 0.0
    return _clamp01(z / 2.0), z, None


def _eval_state_media_drumbeat() -> tuple[dict, str | None]:
    """Leading tell: is state media beating the stability drum?

    Primary source = CCTV state-media tone (fresh, top-tier), fired when recent tone
    is elevated vs its own history. Tier-1 keyword hits on the news tape reinforce it
    when that tape carries tier-1 rows (currently thin). Null only when BOTH are absent."""
    cctv_str, cctv_z, cctv_gap = _cctv_tone_signal()
    hits = None
    df = _news_events()
    if df is not None:
        hits, _ = _news_hits(df, _KW_DRUMBEAT, days=7)
    kw_fires = hits is not None and hits >= _DRUMBEAT_MIN_HITS
    # Null when NEITHER source speaks: no CCTV tone AND no keyword fire. Never fabricate a
    # "CCTV tone …" receipt (or a z from absent data) just because the keyword tape has rows.
    if cctv_gap is not None and not kw_fires:
        return _tell("state_media_drumbeat", "null", have_data=False), cctv_gap
    strength = max(cctv_str, _clamp01(hits / 6.0) if kw_fires else 0.0)
    fires = cctv_str >= 0.5 or kw_fires
    if kw_fires:
        rec_en = f"{hits} state-media stability signals on the tape (7d)"
        rec_zh = f"官媒稳市信号 {hits} 条（7日）"
        vfmt = f"{hits}"
    else:  # reached only when CCTV tone IS present (cctv_gap is None) — receipt is truthful
        lvl_en = "elevated" if cctv_str >= 0.5 else ("firm" if cctv_str >= 0.2 else "neutral")
        lvl_zh = "偏暖" if cctv_str >= 0.5 else ("平稳" if cctv_str >= 0.2 else "中性")
        rec_en = f"CCTV state-media tone {lvl_en} vs history (pro-growth emphasis)"
        rec_zh = f"央视基调较历史{lvl_zh}（稳增长着墨）"
        vfmt = f"{cctv_z:+.1f}z" if cctv_z is not None else None
    return _tell("state_media_drumbeat", "firing" if fires else "quiet",
                 strength=strength if fires else 0.0, value_fmt=vfmt,
                 receipt_en=rec_en, receipt_zh=rec_zh, have_data=True), None


def _eval_facility_watch() -> tuple[dict, str | None]:
    df = _news_events()
    if df is None:
        return _tell("facility_watch", "null", have_data=False), \
            "facility_watch: china_news_vector/events.parquet absent/empty"
    hits, n_t1 = _news_hits(df, _KW_FACILITY, days=30)
    if hits is None:
        return _tell("facility_watch", "null", have_data=False), \
            "facility_watch: no tier-1 state-media rows in trailing 30d (tier-1 tape thin/stale)"
    fires = hits >= _FACILITY_MIN_HITS
    rec_en = f"PBoC support facility flagged ({hits}, 30d)"
    rec_zh = f"央行支持工具被提及（{hits} 条，30日）"
    return _tell("facility_watch", "firing" if fires else "quiet",
                 strength=_clamp01(hits / 3.0) if fires else 0.0, value_fmt=f"{hits}",
                 receipt_en=rec_en, receipt_zh=rec_zh, have_data=True), None


def _fr007_z(window: int = 120, min_periods: int = 30) -> float | None:
    df = _read("china_pboc", "repo_rates.parquet")
    if df is None or "FR007" not in df.columns:
        return None
    s = df["FR007"].dropna()
    if len(s) < min_periods:
        return None
    m = s.rolling(window, min_periods=min_periods).mean()
    sd = s.rolling(window, min_periods=min_periods).std().replace(0, np.nan)
    z = (s - m) / sd
    v = z.iloc[-1]
    return float(v) if pd.notna(v) else None


def _eval_pboc_posture() -> tuple[dict, str | None]:
    """Easing/neutral stance AND tight repo liquidity (FR007 z <= -1.0) = easing into stress."""
    try:
        from engine import china_pboc_stance as pboc
        stance = (pboc.snapshot() or {}).get("stance")
    except Exception as e:  # noqa: BLE001
        return _tell("pboc_posture", "null", have_data=False), \
            f"pboc_posture: china_pboc_stance unavailable ({e})"
    z = _fr007_z()
    if stance is None or z is None:
        return _tell("pboc_posture", "null", have_data=False), \
            "pboc_posture: PBoC stance or FR007 z unavailable"
    fires = stance in ("easing", "neutral") and z <= _FR007_STRESS_Z
    rec_en = f"PBoC easing into tight liquidity (FR007 z {z:+.2f})"
    rec_zh = f"央行逆势宽松，资金面偏紧（FR007 z {z:+.2f}）"
    return _tell("pboc_posture", "firing" if fires else "quiet",
                 strength=_clamp01(-z / 3.0) if fires else 0.0, value_fmt=f"{z:+.2f}z",
                 receipt_en=rec_en, receipt_zh=rec_zh, have_data=True), None


def _eval_buyback_cascade(ledger: pd.DataFrame | None) -> tuple[dict, str | None]:
    """w/w acceleration in董事会预案 (board-proposal) count, from the forward-accruing ledger.

    Needs >= ~2 weeks of accrued rows to compute a week-over-week delta; thinner than that reads
    null (forward-accruing, disclosed). Accel = (this_week - last_week) / max(last_week, 1)."""
    if ledger is None or ledger.empty or "n_board_proposal" not in ledger.columns:
        return _tell("buyback_cascade", "null", have_data=False), \
            "buyback_cascade: buyback_daily ledger empty (forward-accruing — thin on day 1)"
    df = ledger.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")
    if df.empty:
        return _tell("buyback_cascade", "null", have_data=False), \
            "buyback_cascade: no dated ledger rows yet"
    latest = df["date"].max()
    this_wk = df[df["date"] > latest - pd.Timedelta(days=7)]["n_board_proposal"]
    last_wk = df[(df["date"] <= latest - pd.Timedelta(days=7)) &
                 (df["date"] > latest - pd.Timedelta(days=14))]["n_board_proposal"]
    if this_wk.empty or last_wk.empty:
        return _tell("buyback_cascade", "null", have_data=False), \
            (f"buyback_cascade: <2 weeks of ledger history ({len(df)} rows) — cannot compute "
             "w/w acceleration yet (forward-accruing)")
    cur, prev = float(this_wk.mean()), float(last_wk.mean())
    accel = (cur - prev) / max(prev, 1.0)
    fires = accel >= _CASCADE_ACCEL_FIRE
    rec_en = f"SOE buyback proposals accelerating (+{accel * 100:.0f}% w/w)"
    rec_zh = f"国企回购预案加速（环比+{accel * 100:.0f}%）"
    return _tell("buyback_cascade", "firing" if fires else "quiet",
                 strength=_clamp01(accel) if fires else 0.0, value_fmt=f"+{accel * 100:.0f}%",
                 receipt_en=rec_en, receipt_zh=rec_zh, have_data=True), None


def _eval_margin_recovery() -> tuple[dict, str | None]:
    """fin_balance turning up after a drop = leverage returning (5d inflection).

    Fires when the last session ticks UP while the prior 5d trend was DOWN — the classic
    'bottom is being defended, retail leverage re-engaging' inflection."""
    df = _read("china_margin", "balance.parquet")
    if df is None or "fin_balance" not in df.columns:
        return _tell("margin_recovery", "null", have_data=False), \
            "margin_recovery: china_margin/balance.parquet fin_balance absent"
    s = df["fin_balance"].dropna()
    if len(s) < 7:
        return _tell("margin_recovery", "null", have_data=False), \
            "margin_recovery: fin_balance history <7 rows"
    prior_slope = (s.iloc[-2] - s.iloc[-7]) / 5.0          # 5d trend up TO the prior session
    last_tick = s.iloc[-1] - s.iloc[-2]                     # most-recent session change
    base = abs(s.iloc[-2]) or 1.0
    fires = prior_slope < 0 and last_tick > 0
    # Strength: size of the up-tick relative to balance, scaled to be meaningful at ~0.1%/session.
    strength = _clamp01((last_tick / base) * 1000.0) if fires else 0.0
    rec_en = "Margin balance turning up (leverage returning)"
    rec_zh = "两融余额企稳回升（杠杆资金回流）"
    return _tell("margin_recovery", "firing" if fires else "quiet",
                 strength=strength, value_fmt=f"{last_tick:+.0f}亿",
                 receipt_en=rec_en, receipt_zh=rec_zh, have_data=True), None


# --------------------------------------------------------------------------- #
# Composite + band
# --------------------------------------------------------------------------- #
def _composite(tells: list[dict]) -> int:
    """score = round(100 * Σ_available(w·strength) / Σ_available(w)) over have_data tells."""
    avail = [t for t in tells if t.get("have_data")]
    denom = sum(t["weight"] for t in avail)
    if denom <= 0:
        return 0
    num = sum(t["weight"] * t["strength"] for t in avail)
    return int(round(100.0 * num / denom))


def _band(score: int) -> tuple[str, str, str, str]:
    for min_s, band, accent, en, zh in _BANDS:
        if score >= min_s:
            return band, accent, en, zh
    return "dormant", "muted", _BANDS[-1][3], _BANDS[-1][4]


# --------------------------------------------------------------------------- #
# Forward-accruing ledgers (idempotent per date via _drip.append_snapshot)
# --------------------------------------------------------------------------- #
def _buyback_ledger_path():
    from pathlib import Path
    return Path(_data_root()) / "china_national_team" / "buyback_daily.parquet"


def _pressure_ledger_path():
    from pathlib import Path
    return Path(_data_root()) / "china_national_team" / "pressure_daily.parquet"


def _accrue_buyback(asof: str) -> tuple[pd.DataFrame | None, str | None]:
    """Seed today's buyback_daily row from the china_buyback snapshot; return the full ledger.

    buyback.parquet is a same-day SNAPSHOT (one asof) — no history of its own — so we accrue a
    daily (date, n_active, n_board_proposal, plan_amt_yi_sum) row forward. Idempotent per date."""
    src = _read("china_buyback", "buyback.parquet")
    path = _buyback_ledger_path()
    gap = None
    if src is not None and not src.empty and "progress" in src.columns:
        prog = src["progress"].astype(str)
        n_board = int((prog == "董事会预案").sum())
        n_active = int((~prog.isin(["完成实施", "停止实施", "股东大会否决"])).sum())
        plan_sum = float(pd.to_numeric(src.get("plan_amt_yi"), errors="coerce").sum()) \
            if "plan_amt_yi" in src.columns else float("nan")
        row = [{
            "date": asof, "n_active": n_active, "n_board_proposal": n_board,
            "plan_amt_yi_sum": round(plan_sum, 4) if pd.notna(plan_sum) else None,
        }]
        if _ledger_write_ok():
            try:
                from collectors import _drip
                _drip.append_snapshot(path, row, date_col="date")
            except Exception as e:  # noqa: BLE001 — ledger persistence is telemetry, never fatal
                log.warning("national_team buyback ledger append failed: %s", e)
    else:
        gap = "buyback_cascade: china_buyback/buyback.parquet absent — no row seeded today"
    # Return whatever is on disk (may include the row we just seeded).
    if path.exists():
        try:
            return pd.read_parquet(path), gap
        except Exception:  # noqa: BLE001
            return None, gap
    return None, gap


def _accrue_pressure(asof: str, score: int, band: str) -> tuple[list[dict], str | None]:
    """Append today's (date, score, band) to pressure_daily; return the history for the sparkline."""
    path = _pressure_ledger_path()
    if _ledger_write_ok():
        try:
            from collectors import _drip
            _drip.append_snapshot(path, [{"date": asof, "score": int(score), "band": band}],
                                  date_col="date")
        except Exception as e:  # noqa: BLE001
            log.warning("national_team pressure ledger append failed: %s", e)
    history: list[dict] = []
    gap = None
    if path.exists():
        try:
            hist = pd.read_parquet(path)
            hist["date"] = hist["date"].astype(str)
            hist = hist.drop_duplicates(subset=["date"], keep="last").sort_values("date")
            history = [{"date": d, "score": int(s)}
                       for d, s in zip(hist["date"], hist["score"])]
        except Exception:  # noqa: BLE001
            pass
    if len(history) < 5:
        gap = f"history: pressure sparkline forward-accruing ({len(history)} pts so far, thin)"
    return history, gap


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def snapshot(asof: date | str | None = None) -> dict:
    """Build the china_national_team.v1 view-model. Pure reads + two idempotent ledger appends.

    Deterministic and degrade-safe: any missing input reads state:"null", have_data:False and is
    excluded from the renormalized composite. Never raises, never NaN. is_context_only."""
    asof_str = str(asof)[:10] if asof else str(date.today())
    gaps: list[str] = []

    # Seed + read the buyback ledger BEFORE evaluating the cascade tell (idempotent per date).
    ledger, g = _accrue_buyback(asof_str)
    if g:
        gaps.append(g)

    # (key, evaluator) pairs — the key is explicit so a raising evaluator still recovers to an
    # honest null tell under its OWN key (never guess from __name__: the cascade is a lambda).
    evaluators = [
        ("etf_creation", _eval_etf_creation),
        ("largecap_divergence", _eval_largecap_divergence),
        ("market_rescue", _eval_market_rescue),
        ("state_media_drumbeat", _eval_state_media_drumbeat),
        ("facility_watch", _eval_facility_watch),
        ("pboc_posture", _eval_pboc_posture),
        ("buyback_cascade", lambda: _eval_buyback_cascade(ledger)),
        ("margin_recovery", _eval_margin_recovery),
    ]
    tells: list[dict] = []
    for key, ev in evaluators:
        try:
            t, gap = ev()
        except Exception as e:  # noqa: BLE001 — one bad tell must never sink the read
            t, gap = _tell(key, "null", have_data=False), f"{key}: evaluator error ({e})"
        tells.append(t)
        if gap:
            gaps.append(gap)

    score = _composite(tells)
    band, accent, band_en, band_zh = _band(score)

    firing = [t for t in tells if t["state"] == "firing"]
    n_null = sum(1 for t in tells if t["state"] == "null")
    top = max(firing, key=lambda t: t["strength"]) if firing else None

    history, hist_gap = _accrue_pressure(asof_str, score, band)
    if hist_gap:
        gaps.append(hist_gap)

    return {
        "schema": SCHEMA,
        "is_context_only": True,
        "authority": {"tier": "context_only", "may_originate": False, "may_escalate": False},
        "asof": asof_str,
        "built": datetime.now(timezone.utc).isoformat(),
        "pressure": {
            "score": score, "band": band,
            "band_en": band_en, "band_zh": band_zh,
            "accent": accent,                 # act|warn|ok|muted — NON-flipping (never up/down)
            "arc_frac": round(score / 100.0, 4),
        },
        "stance": {"en": _STANCE[band]["en"], "zh": _STANCE[band]["zh"]},
        "tells": tells,
        "tell_counts": {"firing": len(firing), "total": len(tells), "null": n_null},
        "top_footprint": top,
        "history": history,
        "gaps": gaps,
    }
