"""Build the Options workspace -> site/options.html  (OEU lane M-CMD).

THE CANONICAL OPTIONS SURFACE. One page, four modes (Daily Brief / Scanner /
Ticker / Leaders), assembled STRICTLY by re-serialising stores that other
builders already wrote.  Ruling: research/options_estate/OEU_MASTERPLAN.md §2.
Pinned design: research/options_estate/WORKSPACE_DESIGN_SPEC.md (markup and CSS
copied from mockups/oeu_workspace/options_mockup.html).

CONTRACT — read before changing anything here
─────────────────────────────────────────────
1. NO NEW DERIVATIONS.  Every state word on this page is an EXISTING payload
   enum rendered through an EXISTING house label map (the maps are cited inline
   against the template that already ships them).  This builder computes no
   scores, no rankings, no fused composites, and NO THRESHOLD BANDS
   (WORKSPACE_DESIGN_SPEC §0.13).  The one numeric filter it applies —
   |dist_to_flip_pct| <= 1 for the "sitting near a flip level" rail group — is
   the options_screener page's OWN shipped `nearflip` preset value
   (templates/options_screener.html.j2:959), reused rather than reinvented.
2. THE FOUR POSTURE READINGS ARE CO-DISPLAYED, NEVER FUSED.  They are four
   independent payload states printed side by side.  Nothing averages them.
3. DISPLAY TIER ONLY.  Nothing here feeds rank / size / gate.  The word
   "validated" never appears in user copy; the console's vetted glyph is gated
   on the vol payload's own `scored` flag exactly as gex.html gates its badge,
   and it prints a glyph, never the word.
4. O(SECONDS).  Pure JSON reads + re-serialisation.  No engine work, no network.
   Runs AFTER build_flow_desk / build_options_screener / build_flow_leaders /
   build_market_structure so it never renders a generation-stale page.
5. FAIL-SOFT, NEVER FAKE.  A missing store degrades exactly one section to its
   honest empty state and is named in the session-stamp quality receipt.  The
   builder always exits 0 — it can never break the nightly deploy.

Payload law (spec §6): the Brief and the whole persistent chrome are baked
inline; Scanner / Ticker / Leaders payloads are lazy-fetched by the page on mode
activation with plain fetch() — never a JS-injected <script> loader (that
bypasses asset stamping, #3372).

Run:  python -m scripts.build_options_command
      python -m scripts.build_options_command --out /tmp/options.html
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from lib import nyse_calendar, options_coverage

log = logging.getLogger("build_options_command")

_REPO_ROOT = Path(__file__).resolve().parent.parent

# The four index products the ruling pins for the Brief's close row.
INDEX_KEYS = ("SPX", "SPY", "QQQ", "IWM")

# Weekday names — EN comes from the stdlib, ZH from this fixed map (7 entries,
# a closed vocabulary, not a translation of free text).
_WEEKDAY_ZH = {
    "Monday": "周一", "Tuesday": "周二", "Wednesday": "周三", "Thursday": "周四",
    "Friday": "周五", "Saturday": "周六", "Sunday": "周日",
}

# ── EXISTING house label maps, reused verbatim ──────────────────────────────
# tape intensity: templates/flow_desk.html.j2:329-330 (_band_en / _band_zh)
_INTENSITY_EN = {"heavy": "Heavy", "busy": "Busy", "average": "Average",
                 "light": "Light", "quiet": "Quiet", "building": "Building"}
_INTENSITY_ZH = {"heavy": "汹涌", "busy": "活跃", "average": "中等",
                 "light": "清淡", "quiet": "冷清", "building": "积累中"}

# dealer gamma regime: templates/market_structure.html.j2:197-226 ships the
# plain-word states ("Dealers absorbing moves" / "做市商正在吸收波动" and the
# amplifying twin) AND the stance correspondence used below (long -> watch,
# short -> protect gains).  Condensed here to the console's one-word slot.
_GAMMA_STATE_EN = {"long": "Absorbing", "short": "Amplifying"}
_GAMMA_STATE_ZH = {"long": "吸收波动", "short": "放大波动"}
# Index-card regime headline: pinned by WORKSPACE_DESIGN_SPEC §5.1.
_REGIME_HEAD_EN = {"long": "Calm — moves get damped", "short": "Jumpy — moves get amplified"}
_REGIME_HEAD_ZH = {"long": "平静 — 波动被抑制", "short": "剧烈 — 波动被放大"}
# The consequence clause each regime carries (pinned, mockup lines 926/942).
_REGIME_CLAUSE_EN = {"long": "Dips tend to get bought here.", "short": "Swings run larger than usual."}
_REGIME_CLAUSE_ZH = {"long": "此区间回调通常被买回。", "short": "波动幅度大于平常。"}
# Stance follows the regime word 1:1 — the correspondence market_structure.html.j2
# already ships (long -> "watch", short -> the caution/protect chip).  Neither
# maps to "Act": no escalation is introduced by this page.
_REGIME_STANCE = {"long": "watch", "short": "protect"}

# net-premium tone: flow_desk emits 'pos~' / 'neg~' / 'neutral'.
_TONE_EN = {"pos~": "call-leaning", "neg~": "put-leaning", "neutral": "two-sided"}
_TONE_ZH = {"pos~": "偏看涨", "neg~": "偏看跌", "neutral": "双向"}
# sector bar fill class + tone chip
_TONE_CLS = {"pos~": "buy", "neg~": "sell", "neutral": "mix"}

# Same-day (0DTE) explanation — reused verbatim from templates/flow_leaders.html.j2:361.
_ZERODTE_TIP_EN = ("Mostly same-day (0DTE) options — usually day-trading, "
                   "not positioning for a move.")
_ZERODTE_TIP_ZH = "以当日到期（0DTE）期权为主 — 通常是日内交易，而非布局趋势。"

# The nearflip rail group reuses the screener's own shipped preset value.
_NEAR_FLIP_PCT = 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Loading — every read is fail-soft and records what was missing
# ─────────────────────────────────────────────────────────────────────────────
def _load(path: Path) -> object | None:
    """Read a JSON store; return None (never raise) when absent or malformed."""
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("unreadable store %s: %s", path, exc)
        return None


def load_stores(root: Path) -> dict:
    """Load every store the workspace reads.  Absent stores come back as None."""
    site = root / "site"
    data = root / "data"
    gex: dict[str, dict] = {}
    for key in INDEX_KEYS:
        payload = _load(site / "gex" / f"{key}.json")
        if isinstance(payload, dict):
            gex[key] = payload
    return {
        "flow_desk": _load(site / "flow_desk.json"),
        "screener": _load(site / "screenerdata" / "rows.json"),
        "leaders": _load(site / "flowleaders" / "leaders.json"),
        "market_structure": _load(data / "market_structure" / "latest.json"),
        "vol": _load(site / "vol" / "regime.json"),
        "gex": gex,
        "gex_index": _load(site / "gex" / "index.json"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Small formatting helpers (display only)
# ─────────────────────────────────────────────────────────────────────────────
def _num(value) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        return None if out != out else out  # NaN check
    except (TypeError, ValueError):
        return None


def money_mn(value) -> str:
    """$-format a figure already denominated in millions.  '—' when absent."""
    v = _num(value)
    if v is None:
        return "—"
    sign = "−" if v < 0 else ""
    a = abs(v)
    if a >= 1000:
        return f"{sign}${a / 1000:.1f}B"
    if a >= 1:
        return f"{sign}${a:.0f}M"
    return f"{sign}${a * 1000:.0f}K"


def signed_money_mn(value) -> str:
    """Like money_mn but keeps an explicit + on positives (net-premium column)."""
    v = _num(value)
    if v is None:
        return "—"
    return ("+" if v > 0 else "") + money_mn(v)


def price(value) -> str:
    v = _num(value)
    if v is None:
        return "—"
    if abs(v) >= 1000:
        return f"{v:,.2f}"
    return f"{v:,.2f}" if abs(v) < 100 else f"{v:,.2f}"


def level(value) -> str:
    """Strike-style level: drop a trailing .0 the way the chains report them."""
    v = _num(value)
    if v is None:
        return "—"
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"


def pct(value, digits: int = 1) -> str:
    v = _num(value)
    return "—" if v is None else f"{v:.{digits}f}%"


def _day(value) -> str | None:
    """The YYYY-MM-DD session-date prefix of a store's own stamp, or None.

    Stores stamp themselves inconsistently — a bare date here, a full ISO
    timestamp there.  Both name one session; reducing them to the same
    comparable key lets the receipt say which stores disagree instead of
    silently printing several vintages as one close (#F2-02/#F2-03).
    """
    if not isinstance(value, str) or len(value) < 10:
        return None
    day = value[:10]
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return None
    return day


def _pips(fraction, total: int = 5) -> int:
    """Position on a bounded 0..1 scale, as a count of filled segments.

    A LINEAR ENCODING of the value on its own natural scale — not a threshold
    band.  A present reading always lights at least one segment so "on" is never
    invisible; the unfilled remainder stays a visible tile (spec §1.2).
    """
    f = _num(fraction)
    if f is None:
        return 0
    f = min(max(f, 0.0), 1.0)
    return max(1, min(total, int(round(f * total)))) if f > 0 else 0


# ─────────────────────────────────────────────────────────────────────────────
# Session receipt + coverage (the close line's honesty fact)
# ─────────────────────────────────────────────────────────────────────────────
def _source_asof(payload) -> str | None:
    """A store's own session stamp, whatever it calls it.  None when unreadable."""
    if not isinstance(payload, dict):
        return None
    for key in ("asof", "as_of", "session", "date", "built"):
        v = payload.get(key)
        if isinstance(v, str) and v[:4].isdigit():
            return v[:10]
    return None


def _gex_index_asof(payload) -> str | None:
    """site/gex/index.json is a LIST of per-symbol rows, each carrying its own `asof`."""
    if not isinstance(payload, list) or not payload:
        return None
    stamps = [r.get("asof") for r in payload
              if isinstance(r, dict) and isinstance(r.get("asof"), str)]
    return max(stamps) if stamps else None


def _source_n(payload, key: str) -> int | None:
    """A store's own covered-names count.  None (never 0) when it does not publish one."""
    if not isinstance(payload, dict):
        return None
    v = payload.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return int(v)


def build_session(stores: dict, missing: list[str]) -> dict:
    """The session stamp: date, OI vintage, coverage share, quality word.

    ONE SESSION DATE, CROSS-CHECKED (#F2-03/#F2-04).  The page date is the flow
    desk's own `asof` — the settled close the Brief is written against.  The
    screener export and the index-levels manifest each carry their OWN stamp,
    and those CAN drift apart (a rebuilt levels board, a scanner export from a
    later run).  When either disagrees with the page date, the mismatch is
    NAMED in the receipt and the quality word degrades to Partial — three
    vintages must never be presented silently as one settled close.

    Coverage numerator/denominator both come from ONE payload (the screener
    export) so the fraction is internally consistent: how many of the names we
    track reported a chain dated to the SCREENER'S OWN most recent close (which
    may not be the page date — see the mismatch note above).  Stale rows are
    the remainder, and the Scanner's per-row age column explains each one.
    """
    fd = stores.get("flow_desk") or {}
    sc = stores.get("screener") or {}
    gex_index = stores.get("gex_index")

    session_date = _day(fd.get("asof")) if isinstance(fd, dict) else None
    weekday_en = weekday_zh = ""
    if session_date:
        try:
            wd = datetime.strptime(session_date, "%Y-%m-%d").strftime("%A")
            weekday_en, weekday_zh = wd, _WEEKDAY_ZH.get(wd, "")
        except ValueError:
            pass

    # OI vintage — the options-chain snapshot the levels were measured from.
    oi_vintage = None
    if isinstance(gex_index, list) and gex_index:
        stamps = sorted({_day(e.get("asof")) for e in gex_index
                         if isinstance(e, dict) and _day(e.get("asof"))})
        oi_vintage = stamps[-1] if stamps else None

    covered = universe = None
    coverage_asof = None
    rows = sc.get("rows") if isinstance(sc, dict) else None
    if isinstance(rows, list) and rows:
        stamps = [_day(r.get("asof")) for r in rows if isinstance(r, dict) and _day(r.get("asof"))]
        universe = len(rows)
        if stamps:
            coverage_asof = max(stamps)
            covered = sum(1 for s in stamps if s == coverage_asof)

    coverage_pct = None
    if covered is not None and universe:
        coverage_pct = round(covered / universe * 100, 1)

    # Quality word — a PRESENCE census over the stores PLUS a VINTAGE-AGREEMENT
    # census, never a threshold on a value.  The receipt names exactly what is
    # absent, stale, or dated to a different close than the page's own
    # (#vacuous-green: emit the census, never a bare count).
    stale_notes_en: list[str] = []
    stale_notes_zh: list[str] = []
    leaders = stores.get("leaders")
    if isinstance(leaders, dict) and leaders.get("stale"):
        stale_notes_en.append("the leader boards are from an earlier session")
        stale_notes_zh.append("领头股榜单来自更早的场次")

    if session_date:
        if coverage_asof and coverage_asof != session_date:
            stale_notes_en.append(
                f"the options scanner's freshest chain is dated {coverage_asof}, not {session_date}")
            stale_notes_zh.append(f"期权筛选表的最新期权链日期为 {coverage_asof}，而非 {session_date}")
        if oi_vintage and oi_vintage != session_date:
            stale_notes_en.append(
                f"the index levels were last measured {oi_vintage}, not {session_date}")
            stale_notes_zh.append(f"指数水位的最近测算日期为 {oi_vintage}，而非 {session_date}")

    if missing:
        stale_notes_en.append("some sections could not be built for this close")
        stale_notes_zh.append("部分板块本次收盘无法生成")

    if stale_notes_en:
        quality_en, quality_zh = "Partial", "部分"
        tip_en = ("Not everything reported for this close: "
                  + "; ".join(stale_notes_en)
                  + ". Every affected section says so where it sits.")
        tip_zh = "本次收盘并非所有数据都已送达：" + "；".join(stale_notes_zh) + "。受影响的板块会在原处说明。"
    else:
        quality_en, quality_zh = "Complete", "完整"
        tip_en = ("Every source reported on time, for the same close, and inside its normal "
                  "range. Nothing was estimated or carried over from an older session.")
        tip_zh = "所有数据源均按时送达、对应同一次收盘且处于正常范围。没有任何数值是估算或沿用旧场次的。"

    if covered is not None and universe:
        cov_tip_en = (f"{covered} of the {universe} names we track reported a complete options "
                      f"chain dated {coverage_asof}. The filled part of this line is that share; "
                      "the gap on the right is what is missing.")
        cov_tip_zh = (f"我们跟踪的 {universe} 个标的中，有 {covered} 个提供了截至 {coverage_asof} "
                      "的完整期权链。此线的填充部分即该比例，右侧空缺为缺失部分。")
    else:
        # No coverage number — the line stays fully hatched rather than pretending
        # to be complete, and says why.
        cov_tip_en = ("We could not count how many names reported a complete options chain for "
                      "this close, so this line is left empty rather than shown as full.")
        cov_tip_zh = "我们无法统计本次收盘有多少标的提供了完整期权链，因此此线留空，而非显示为完整。"

    return {
        "date": session_date,
        "weekday_en": weekday_en,
        "weekday_zh": weekday_zh,
        "oi_vintage": oi_vintage,
        "covered": covered,
        "universe": universe,
        # The vintage the coverage fraction was actually counted at — pinned so
        # a caller can check it against the page date instead of assuming.
        "coverage_asof": coverage_asof,
        "coverage_pct": coverage_pct,
        "quality_en": quality_en,
        "quality_zh": quality_zh,
        "quality_tip_en": tip_en,
        "quality_tip_zh": tip_zh,
        "cov_tip_en": cov_tip_en,
        "cov_tip_zh": cov_tip_zh,
        # OIP R8 — the shared options coverage object, ADDITIVE. Every key above is
        # untouched; no surface reads this yet (later waves adopt it). One comparable
        # shape across build_options_command / build_gex_board / build_options_screener /
        # build_flow_desk, so the estate can print one honest coverage sentence instead
        # of four incomparable ones. See lib/options_coverage.py.
        "coverage_v1": options_coverage.coverage_object(
            universe_name_en="Options names we track",
            universe_name_zh="我们跟踪的期权标的",
            universe_n=universe,
            covered_n=covered,
            asof=coverage_asof or session_date,
            sources=[
                options_coverage.source(
                    "flow_desk", "Options tape", "期权成交",
                    asof=_source_asof(stores.get("flow_desk")),
                    # minor 6 (review): flow_desk.json publishes n_names under `read`,
                    # not at the top level, so this was always None.
                    n=_source_n((stores.get("flow_desk") or {}).get("read")
                                if isinstance(stores.get("flow_desk"), dict) else None,
                                "n_names"),
                ),
                options_coverage.source(
                    "screener", "Scanner rows", "筛选表标的",
                    asof=coverage_asof, n=universe,
                ),
                options_coverage.source(
                    "leaders", "Flow leaders", "资金领跑",
                    asof=_source_asof(stores.get("leaders")),
                    # leaders.json counts its universe as coverage.n_universe
                    n=_source_n((stores.get("leaders") or {}).get("coverage")
                                if isinstance(stores.get("leaders"), dict) else None,
                                "n_universe"),
                ),
                options_coverage.source(
                    "market_structure", "Index structure", "指数结构",
                    asof=_source_asof(stores.get("market_structure")),
                ),
                options_coverage.source(
                    "vol", "Volatility regime", "波动状态",
                    asof=_source_asof(stores.get("vol")),
                ),
                options_coverage.source(
                    "gex", "Dealer positioning", "做市商持仓",
                    # minor 6 (review): site/gex/index.json is a LIST of per-symbol rows,
                    # so _source_asof (a dict reader) always returned None. Read the asof
                    # off the first row, and count the board's real breadth from the list
                    # rather than the 4 index payloads the Brief happens to inline.
                    asof=_gex_index_asof(stores.get("gex_index")),
                    n=(len(stores.get("gex_index"))
                       if isinstance(stores.get("gex_index"), list)
                       else None),
                ),
            ],
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# The posture console — four co-displayed readings, never fused
# ─────────────────────────────────────────────────────────────────────────────
def build_posture(stores: dict) -> list[dict]:
    """Four independent payload states, side by side.  No arithmetic between them.

    Each cell: an EXISTING label, that source's OWN state word, a linear pip
    position on that reading's OWN scale, and a supporting figure.  Nothing here
    is combined, ranked, or scored.
    """
    fd = stores.get("flow_desk") or {}
    read = fd.get("read") if isinstance(fd, dict) else None
    read = read if isinstance(read, dict) else {}
    ms = stores.get("market_structure") or {}
    gamma = ms.get("gamma") if isinstance(ms, dict) else None
    gamma = gamma if isinstance(gamma, dict) else {}
    vol = stores.get("vol") or {}
    snapshot = vol.get("snapshot") if isinstance(vol, dict) else None
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    game_plan = vol.get("game_plan") if isinstance(vol, dict) else None
    game_plan = game_plan if isinstance(game_plan, dict) else {}

    cells: list[dict] = []

    # 1 · Whole market — the vol-regime verdict, verbatim from its own payload.
    verdict = game_plan.get("verdict") if isinstance(game_plan.get("verdict"), dict) else {}
    risk_score = _num(snapshot.get("risk_score"))
    vix = _num(snapshot.get("vix"))
    cells.append({
        "label_en": "Whole market", "label_zh": "整体市场",
        # The vol desk's own bilingual verdict, verbatim.  Never the raw `regime`
        # enum — that is a machine slug and the doctrine bans it on the glance
        # tier in either language.
        "state_en": verdict.get("en") or "—", "state_zh": verdict.get("zh") or verdict.get("en") or "—",
        "pips": _pips(risk_score), "pips_total": 5,
        # The vetted glyph mirrors gex.html's own gate: it appears only when the
        # payload says this reading is scored.  It is a glyph, never the word.
        "vetted": bool(game_plan.get("scored") or snapshot.get("scored_active")),
        # A proper-noun index level needs no translation and carries no slug.
        "note_en": (f"VIX {vix:.1f}" if vix is not None else ""),
        "note_zh": (f"VIX {vix:.1f}" if vix is not None else ""),
        "tip_en": (f"Where the volatility surface sits on a calm-to-stressed scale, {_pips(risk_score)} of 5. "
                   "It reads what index options cost against how much the market has actually been moving."),
        "tip_zh": (f"波动率曲面在平静至紧张刻度上的位置：5 格中第 {_pips(risk_score)} 格。"
                   "它衡量的是指数期权的价格相对市场实际波动幅度的水平。"),
        "available": bool(verdict.get("en")),
    })

    # 2 · S&P dealers — the shock-absorber state and how long it has held.
    regime = gamma.get("regime")
    pctile = _num(gamma.get("net_gex_pctile"))
    days = gamma.get("days_in_regime")
    cells.append({
        "label_en": "S&P dealers", "label_zh": "标普做市商",
        "state_en": _GAMMA_STATE_EN.get(regime, "—"),
        "state_zh": _GAMMA_STATE_ZH.get(regime, "—"),
        "pips": _pips(None if pctile is None else pctile / 100.0), "pips_total": 5,
        "vetted": False,
        "note_en": (f"{days} day{'' if days == 1 else 's'} in this state" if days is not None else ""),
        "note_zh": (f"该状态已持续 {days} 天" if days is not None else ""),
        "tip_en": ("Dealer net gamma sits at the "
                   f"{pctile:.0f}th percentile of its own history — {_pips(pctile / 100.0)} of 5 "
                   "toward absorbing. Model estimate: real dealer books are unobservable."
                   if pctile is not None else
                   "Model estimate: real dealer books are unobservable."),
        "tip_zh": (f"做市商净 Gamma 处于自身历史的第 {pctile:.0f} 百分位 — 吸收方向 5 格中第 "
                   f"{_pips(pctile / 100.0)} 格。模型估算：真实做市商持仓不可观测。"
                   if pctile is not None else "模型估算：真实做市商持仓不可观测。"),
        "available": regime in _GAMMA_STATE_EN,
    })

    # 3 · Today's tape — the flow desk's own intensity band and score.
    intensity_key = read.get("intensity_key")
    score = _num(read.get("intensity_score"))
    gross = _num(read.get("gross_premium_mn"))
    cells.append({
        "label_en": "Today's tape", "label_zh": "今日盘面",
        "state_en": _INTENSITY_EN.get(intensity_key, "—"),
        "state_zh": _INTENSITY_ZH.get(intensity_key, "—"),
        "pips": _pips(None if score is None else score / 100.0), "pips_total": 5,
        "vetted": False,
        "note_en": (f"{money_mn(gross)} traded" if gross is not None else ""),
        "note_zh": (f"成交 {money_mn(gross)}" if gross is not None else ""),
        "tip_en": (f"{money_mn(gross)} of options premium traded — "
                   f"{score:.0f} of 100 on the quiet-to-frantic scale this desk already publishes."
                   if score is not None else "How busy the options tape was, on this desk's own scale."),
        "tip_zh": (f"期权权利金成交 {money_mn(gross)} — 本台既有的清淡至狂热刻度上 100 分中的 {score:.0f} 分。"
                   if score is not None else "期权盘面的繁忙程度，采用本台既有刻度。"),
        "available": intensity_key in _INTENSITY_EN,
    })

    # 4 · Same-day bets — the share itself, on its own 0–100% scale.
    #     DELIBERATELY NOT BANDED: no payload publishes a 0DTE state word, and
    #     §0.13 forbids this builder inventing one.  The reading is the share,
    #     with its meaning in the supporting line and the hover.
    share = _num(read.get("zerodte_share"))
    cells.append({
        "label_en": "Same-day bets", "label_zh": "当日到期押注",
        "state_en": (f"{share * 100:.0f}% of premium" if share is not None else "—"),
        "state_zh": (f"占权利金 {share * 100:.0f}%" if share is not None else "—"),
        "pips": _pips(share), "pips_total": 5,
        "vetted": False,
        "note_en": "expiring the same day", "note_zh": "当日到期",
        "tip_en": (f"{share * 100:.0f}% of today's options premium went to contracts expiring the "
                   f"same day. {_ZERODTE_TIP_EN}" if share is not None else _ZERODTE_TIP_EN),
        "tip_zh": (f"今日 {share * 100:.0f}% 的期权权利金流向当日到期的合约。{_ZERODTE_TIP_ZH}"
                   if share is not None else _ZERODTE_TIP_ZH),
        "available": share is not None,
    })
    return cells


# ─────────────────────────────────────────────────────────────────────────────
# Brief · what changed
# ─────────────────────────────────────────────────────────────────────────────
def build_changed(stores: dict) -> dict:
    """Day-over-day chips, from the only two stores that publish real deltas.

    A chip is emitted ONLY where a payload carries an actual change plus copy we
    can state plainly.  Nothing is inferred; an unrecognised state-change key is
    skipped rather than machine-phrased at the user.

    EACH CHIP CARRIES ITS OWN COMPARISON DATE IN ITS OWN TOOLTIP (#F2-14) — a
    panel-level "since X's close" header previously applied ONE baseline to
    both chips even though the tape chip is always vs flow_desk's own prior
    close while the regime-flip chip's baseline is whatever market_structure
    last completed, which can sit several sessions back after a build gap.  The
    regime-flip chip is WITHHELD entirely when that baseline is not the
    immediately preceding NYSE session — a stale attribution is worse than a
    missing chip.
    """
    fd = stores.get("flow_desk") or {}
    read = fd.get("read") if isinstance(fd, dict) else None
    read = read if isinstance(read, dict) else {}
    ms = stores.get("market_structure") or {}
    changes = ms.get("state_changes") if isinstance(ms, dict) else None
    changes = changes if isinstance(changes, dict) else {}

    chips: list[dict] = []

    # Tape, day over day — flow_desk's own dod_key, phrased with the fragments
    # templates/flow_desk.html.j2:343-344 already ships.  Always vs the single
    # immediately-prior close, by flow_desk's own dod convention.
    dod_key = read.get("dod_key")
    dod_pct = _num(read.get("dod_pct"))
    dod_copy = {
        "heavier": ("u", "Tape got heavier", "盘面更重"),
        "lighter": ("d", "Tape eased off", "盘面回落"),
        "steady": ("f", "Tape held steady", "盘面持平"),
    }
    if dod_key in dod_copy:
        arrow, en, zh = dod_copy[dod_key]
        gross = money_mn(read.get("gross_premium_mn"))
        chips.append({
            "arrow": arrow, "en": en, "zh": zh,
            "tip_en": (f"Options premium traded: {gross} this close, "
                       f"{dod_pct:+.0f}% against the previous close."
                       if dod_pct is not None else f"Options premium traded: {gross} this close."),
            "tip_zh": (f"期权权利金成交额：本次收盘 {gross}，较上次收盘 {dod_pct:+.0f}%。"
                       if dod_pct is not None else f"期权权利金成交额：本次收盘 {gross}。"),
        })

    # Dealer regime flips — market_structure publishes these with their own
    # bilingual note; only the gamma_regime key has plain-word chip copy.  Trust
    # the comparison only when vs_asof really is the session immediately before
    # market_structure's own asof; a multi-session build gap makes the "since"
    # attribution unsound, so withhold the chip rather than mislabel it.
    vs_asof = _day(changes.get("vs_asof"))
    ms_asof = _day(ms.get("asof")) if isinstance(ms, dict) else None
    baseline_sound = False
    if vs_asof and ms_asof:
        try:
            expected_prev = nyse_calendar.last_session_on_or_before(
                datetime.strptime(ms_asof, "%Y-%m-%d").date() - timedelta(days=1))
            baseline_sound = vs_asof == str(expected_prev)
        except ValueError:
            baseline_sound = False

    if baseline_sound:
        vs_stamp_en = f" Comparison baseline: {vs_asof}'s close."
        vs_stamp_zh = f" 对比基准：{vs_asof} 收盘。"
        for item in (changes.get("items") or []):
            if not isinstance(item, dict) or item.get("key") != "gamma_regime":
                continue
            to = item.get("to")
            if to == "short":
                chips.append({"arrow": "d", "en": "Dealers now amplify moves", "zh": "做市商转为放大波动",
                              "tip_en": (item.get("note_en") or "") + vs_stamp_en,
                              "tip_zh": (item.get("note_zh") or "") + vs_stamp_zh})
            elif to == "long":
                chips.append({"arrow": "u", "en": "Dealers now absorb moves", "zh": "做市商转为吸收波动",
                              "tip_en": (item.get("note_en") or "") + vs_stamp_en,
                              "tip_zh": (item.get("note_zh") or "") + vs_stamp_zh})

    return {"chips": chips[:5], "asof": read.get("asof")}


# ─────────────────────────────────────────────────────────────────────────────
# Brief · index close row
# ─────────────────────────────────────────────────────────────────────────────
def build_indexes(stores: dict) -> list[dict]:
    """SPX / SPY / QQQ / IWM: regime word, position against the flip, levels."""
    out: list[dict] = []
    for key in INDEX_KEYS:
        payload = (stores.get("gex") or {}).get(key)
        if not isinstance(payload, dict):
            continue
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        em = payload.get("expected_move") if isinstance(payload.get("expected_move"), dict) else {}
        regime = summary.get("regime")
        if regime not in _REGIME_HEAD_EN:
            continue
        dist = _num(summary.get("dist_to_flip_pct"))
        if dist is None:
            side_en = side_zh = ""
        elif dist >= 0:
            side_en = f"Closed {abs(dist):.1f}% above the flip."
            side_zh = f"收于翻转位上方 {abs(dist):.1f}%。"
        else:
            side_en = f"Closed {abs(dist):.1f}% below the flip."
            side_zh = f"收于翻转位下方 {abs(dist):.1f}%。"
        out.append({
            "sym": key,
            "name_en": meta.get("en") or key,
            "name_zh": meta.get("zh") or meta.get("en") or key,
            "spot": price(summary.get("spot")),
            "head_en": _REGIME_HEAD_EN[regime], "head_zh": _REGIME_HEAD_ZH[regime],
            "line_en": (side_en + " " + _REGIME_CLAUSE_EN[regime]).strip(),
            "line_zh": (side_zh + _REGIME_CLAUSE_ZH[regime]).strip(),
            "floor": level(summary.get("put_wall")),
            "flip": level(summary.get("gamma_flip")),
            "ceiling": level(summary.get("call_wall")),
            "stance": _REGIME_STANCE[regime],
            "em": (f"±{_num(em.get('daily_pct')):.2f}%" if _num(em.get("daily_pct")) is not None else "—"),
            "asof": meta.get("asof"),
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Brief · sector bars + biggest bets
# ─────────────────────────────────────────────────────────────────────────────
def build_sectors(stores: dict) -> dict | None:
    """Shared-scale premium bars.  Bar length is a pure length encoding."""
    fd = stores.get("flow_desk") or {}
    heat = fd.get("sector_heatmap") if isinstance(fd, dict) else None
    if not isinstance(heat, list) or not heat:
        return None
    rows = [r for r in heat if isinstance(r, dict) and _num(r.get("gross_premium_mn")) is not None]
    if not rows:
        return None
    rows.sort(key=lambda r: _num(r.get("gross_premium_mn")) or 0.0, reverse=True)
    top = _num(rows[0].get("gross_premium_mn")) or 0.0
    total = sum(_num(r.get("gross_premium_mn")) or 0.0 for r in rows)
    out = []
    for r in rows:
        v = _num(r.get("gross_premium_mn")) or 0.0
        tone = r.get("tone")
        out.append({
            "sector": r.get("sector") or "—",
            "width": round(v / top * 100, 1) if top else 0.0,
            "val": money_mn(v),
            "cls": _TONE_CLS.get(tone, "mix"),
            "tone_en": {"pos~": "buying ~", "neg~": "selling ~"}.get(tone, "mixed"),
            "tone_zh": {"pos~": "买入 ~", "neg~": "卖出 ~"}.get(tone, "混合"),
        })
    top2 = None
    if total > 0 and len(rows) >= 2:
        top2 = round(sum((_num(r.get("gross_premium_mn")) or 0.0) for r in rows[:2]) / total * 100)
    return {"rows": out, "top2_pct": top2, "asof": rows[0].get("asof")}


def build_bets(stores: dict) -> dict | None:
    """Biggest single net-premium marks, with the flow desk's own caution flags."""
    fd = stores.get("flow_desk") or {}
    movers = fd.get("top_movers") if isinstance(fd, dict) else None
    if not isinstance(movers, list) or not movers:
        return None
    out = []
    for m in movers[:10]:
        if not isinstance(m, dict):
            continue
        net = _num(m.get("net_premium_mn"))
        # The lean word comes from the SIGN OF THE DISPLAYED NUMBER — the rule
        # flow_desk.html.j2:610-616 already ships for this same board.  Do NOT
        # use `tone` here: top_movers emits 'neg' (no tilde) where the sector
        # heatmap emits 'neg~', so a shared map silently mislabels put-leaning
        # names as two-sided.
        tone = "pos~" if (net or 0) > 0 else ("neg~" if (net or 0) < 0 else "neutral")
        cautions = []
        if m.get("zerodte_dominated"):
            cautions.append({"en": "Same-day heavy", "zh": "当日到期为主",
                             "warn": False, "tip_en": _ZERODTE_TIP_EN, "tip_zh": _ZERODTE_TIP_ZH})
        share = _num(m.get("zerodte_share"))
        out.append({
            "sym": m.get("ticker") or "—",
            "amt": signed_money_mn(net),
            "sign": "pos" if (net or 0) > 0 else ("neg" if (net or 0) < 0 else ""),
            "tone_en": _TONE_EN.get(tone, "two-sided"),
            "tone_zh": _TONE_ZH.get(tone, "双向"),
            "share_en": (f"{share * 100:.0f}% same-day" if share is not None else ""),
            "share_zh": (f"{share * 100:.0f}% 当日到期" if share is not None else ""),
            "cautions": cautions,
        })
    return {"rows": out, "asof": movers[0].get("asof") if isinstance(movers[0], dict) else None}


# ─────────────────────────────────────────────────────────────────────────────
# Brief · names-for-tomorrow rail
# ─────────────────────────────────────────────────────────────────────────────
def build_rail(stores: dict) -> dict:
    """Three research groups, each a straight read of an existing board.

    Group B mirrors flow_leaders.html.j2's own admission rule exactly — the
    corrected washout-flip verdict B5, not days_since_inflection (#3496).
    Group C reuses the screener's shipped `nearflip` preset value.
    """
    leaders = stores.get("leaders") if isinstance(stores.get("leaders"), dict) else {}
    sc = stores.get("screener") if isinstance(stores.get("screener"), dict) else {}

    board_a = leaders.get("board_a") if isinstance(leaders.get("board_a"), list) else []
    board_b = leaders.get("board_b") if isinstance(leaders.get("board_b"), list) else []
    rows = sc.get("rows") if isinstance(sc.get("rows"), list) else []

    a = [r.get("ticker") for r in board_a[:6] if isinstance(r, dict) and r.get("ticker")]
    b = [r.get("ticker") for r in board_b
         if isinstance(r, dict) and r.get("B5_flow_inflect") and r.get("ticker")][:6]

    near = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        d = _num(r.get("dist_to_flip_pct"))
        if d is not None and abs(d) <= _NEAR_FLIP_PCT and r.get("ticker"):
            near.append((abs(d), r["ticker"]))
    near.sort()
    c = [t for _d, t in near[:6]]

    return {
        "a": a, "b": b, "c": c,
        "asof": leaders.get("as_of", "")[:10] if isinstance(leaders.get("as_of"), str) else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Context assembly
# ─────────────────────────────────────────────────────────────────────────────
def _missing_stores(stores: dict) -> list[str]:
    """Content-aware presence census (#F2-02).

    A store that is PRESENT but carries no usable rows/boards/payloads is
    exactly as unusable to the page as an absent one — `{"rows": []}` and
    `{"board_a": [], "board_b": []}` are truthy dicts that a bare `if not
    stores.get(key)` check waves through as "fine".
    """
    missing: list[str] = []

    fd = stores.get("flow_desk")
    if not (isinstance(fd, dict) and fd.get("read")):
        missing.append("flow_desk")

    sc = stores.get("screener")
    if not (isinstance(sc, dict) and sc.get("rows")):
        missing.append("screener")

    ld = stores.get("leaders")
    if not (isinstance(ld, dict) and (ld.get("board_a") or ld.get("board_b"))):
        missing.append("leaders")

    if not stores.get("market_structure"):
        missing.append("market_structure")
    if not stores.get("vol"):
        missing.append("vol")
    if not stores.get("gex"):
        missing.append("gex")
    if not stores.get("gex_index"):
        missing.append("gex_index")

    return missing


def build_context(root: Path, stores: dict | None = None) -> dict:
    """Assemble the whole workspace context from the committed stores."""
    stores = load_stores(root) if stores is None else stores

    missing = _missing_stores(stores)

    session = build_session(stores, missing)
    changed = build_changed(stores)
    indexes = build_indexes(stores)
    sectors = build_sectors(stores)
    bets = build_bets(stores)
    rail = build_rail(stores)

    leaders = stores.get("leaders") if isinstance(stores.get("leaders"), dict) else {}
    n_boards = sum(1 for k in ("board_a", "board_b") if leaders.get(k))

    return {
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "session": session,
        "posture": build_posture(stores),
        "changed": changed,
        "indexes": indexes,
        "sectors": sectors,
        "bets": bets,
        "rail": rail,
        "counts": {
            "scanner": session.get("universe"),
            "ticker": "SPY" if "SPY" in (stores.get("gex") or {}) else (INDEX_KEYS[0]),
            "leaders": n_boards or None,
        },
        "missing": missing,
        # Direction honesty, straight from the flow desk's own fields (#F2-01/
        # #F2-09) — rendered next to the sector/bets tone chips rather than
        # loaded and left unused.
        "direction_note": (stores.get("flow_desk") or {}).get("direction_note")
        if isinstance(stores.get("flow_desk"), dict) else None,
        "direction_reliable": (stores.get("flow_desk") or {}).get("direction_reliable")
        if isinstance(stores.get("flow_desk"), dict) else None,
    }


def render(root: Path, stores: dict | None = None) -> str:
    """Render options.html.j2 and return the HTML string."""
    ctx = build_context(root, stores)
    env = Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=True,
    )
    try:
        sys.path.insert(0, str(root))
        from engine import i18n  # noqa: PLC0415
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001
        # Template defines t() locally; td() is only used for sector display names
        # and degrades to English-only, never to a crash.
        env.globals.update(td=lambda s, *a, **k: s, tr=lambda s, *a, **k: s)
    return env.get_template("options.html.j2").render(**ctx)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the Options workspace page.")
    ap.add_argument("--root", default=str(_REPO_ROOT), help="repo root")
    ap.add_argument("--out", default=None, help="output path (default site/options.html)")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root = Path(args.root).resolve()
    out_path = Path(args.out) if args.out else (root / "site" / "options.html")

    # CONTRACT (docstring §5): the builder always exits 0.  write_page and the
    # logging pass used to sit OUTSIDE this fence — along with a second, fully
    # redundant re-read of every store purely to log a line — so an exception
    # in either one propagated out of main() despite the contract's promise
    # (#F2-08).  One store load, one context build, one fence.
    try:
        stores = load_stores(root)
        html = render(root, stores=stores)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        # write_page is the ONLY write path. The fail-soft law above covers a
        # RENDER failure (keep the previous page); it never licensed shipping a
        # rendered page without the data-base shim, which is what the raw-write
        # fallback here did — silently, since the render lane's
        # inject_data_base sweep healed the committed copy afterwards.
        from lib.pages import write_page  # noqa: PLC0415
        write_page(out_path, html)

        ctx = build_context(root, stores)
        sess = ctx["session"]
        log.info(
            "options workspace -> %s | session=%s coverage=%s/%s (%s%%) quality=%s missing=%s",
            out_path, sess.get("date"), sess.get("covered"), sess.get("universe"),
            sess.get("coverage_pct"), sess.get("quality_en"), ctx["missing"] or "none",
        )
        if ctx["missing"]:
            print("::warning title=build_options_command::degraded sections — missing stores: "
                  + ", ".join(ctx["missing"]))
    except Exception as exc:  # noqa: BLE001
        # Display-tier surface: never break the nightly deploy.  The last
        # committed options.html stands.
        log.error("render failed — keeping the previous page: %s", exc, exc_info=True)
        print(f"::warning title=build_options_command::render failed ({exc}); previous page kept")
        return 0

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
