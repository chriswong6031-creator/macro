"""Deterministic portfolio-brief composer — "your book, through the desk's eyes".

Portfolio-Aware Intelligence, W1 (charter:
research/PORTFOLIO_BRIEF_MASTERPLAN_BY_FABLE.md §1 V1, §2, §4). This is the ONE
composer that serves three homes: the macro-api endpoint (GET /api/portfolio/brief),
the Brain tool (get_portfolio_brief), and — through the endpoint's proxy — the
mastermind-terminal Portfolio page (which is already built against the v1 contract
below).

DESIGN-TIER LAW (§4). This module RE-EXPRESSES the nightly per-ticker context
artifact (portfolio_ctx.v1, baked by scripts/build_portfolio_ctx.py). It originates
NOTHING — no new signal, score, classification, threshold, or number of its own. It
JOINS the user's holdings against the artifact and renders deterministic bilingual
sentences. Guardrails, all hard:
  * Descriptive, never prescriptive — exposures, counts, dates, plain-word desk
    stances applied to the book. No "sell X / buy Y / rebalance to Z", no imperatives,
    no model-originated targets. The composed lines pass the ask_brain advice filter
    UNTOUCHED by construction (asserted in tests).
  * Vocabulary VERBATIM from the ctx — conviction_en/zh, label_en/zh, name/name_zh,
    rotation_state, entry label/state — copied, never paraphrased into a judgement.
  * No fabricated numbers. Percentages are whole-number rounded; weights are
    renormalized ONLY over the names that carry the relevant field (never invent a
    sector for an uncovered name).
  * The word "validated" appears NOWHERE.
  * Pure dict/list math — no pandas, no I/O. Determinism: same inputs → byte-identical
    output (the caller passes fixed today/generated_at; golden-file tests pin it).

Public surface:
    compose_brief(ctx, holdings, today, generated_at) -> dict   (portfolio_brief.v1)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

SCHEMA = "portfolio_brief.v1"

# ── weighting-mode labels (bilingual) ────────────────────────────────────────
_MODE_LABELS = {
    "positions": {"en": "by cost basis", "zh": "按成本权重"},
    "equal": {"en": "equal-weighted", "zh": "等权"},
}

# Sector-name reconciliation. The per-ticker `sector` field (from stockdata profiles
# via us_standouts / screener rows) uses one taxonomy ("Information Technology",
# "Health Care", "Financials", "Materials"); the ctx.sectors block is keyed by the
# rotation-board's taxonomy ("Technology", "Healthcare", "Financial", "Basic
# Materials"). To read a held name's sector stance we must reconcile the two. This map
# is a pure display alias — it changes NO value, only which sector block we look up;
# when neither the raw name nor an alias matches a block we omit the stance clause and
# state the exposure honestly (the "no desk read for <sector>" path). Documented and
# descriptive, not a new classification.
_SECTOR_ALIASES = {
    "information technology": "Technology",
    "health care": "Healthcare",
    "financials": "Financial",
    "consumer staples": "Consumer Defensive",
    "consumer discretionary": "Consumer Cyclical",
    "materials": "Basic Materials",
    "communication": "Communication Services",
    "telecommunication services": "Communication Services",
}


# ── weekday / stale arithmetic (pure, deterministic) ─────────────────────────

def _parse_iso(d: str) -> date | None:
    try:
        return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _weekdays_between(start: date, end: date) -> int:
    """Count weekdays strictly AFTER `start` up to and including `end` (0 if end<=start).

    Pure Mon–Fri counting — a Friday asof read on the following Monday is 1 weekday
    old (Sat/Sun don't count), so the 2-weekday stale threshold survives a weekend.
    """
    if end <= start:
        return 0
    n = 0
    cur = start
    while cur < end:
        cur = cur + timedelta(days=1)
        if cur.weekday() < 5:  # Mon..Fri
            n += 1
    return n


def _is_stale(asof: str, today: str) -> bool:
    """True iff the ctx asof is MORE than 2 weekdays before today. Fail-safe: unknown
    dates → not stale (never invent staleness we can't prove)."""
    a = _parse_iso(asof)
    t = _parse_iso(today)
    if a is None or t is None:
        return False
    return _weekdays_between(a, t) > 2


# ── holdings normalization + weighting ───────────────────────────────────────

def _normalize_holdings(holdings: list[dict]) -> tuple[list[str], dict[str, float], str]:
    """Return (ordered unique tickers, {ticker: weight}, mode).

    Mode "positions" when >=1 row has shares>0 AND entry_price>0 → weight =
    shares*entry_price, summed on duplicate tickers, renormalized to 1. Else "equal":
    every unique ticker gets 1/n. Tickers uppercased; blanks dropped; first-seen order
    preserved. Position rows with missing/non-positive fields contribute 0 cost in
    positions mode (they still count as held names — an equal share of 0 cost is 0,
    which is honest: a name with no cost basis carries no cost-basis weight).
    """
    order: list[str] = []
    seen: set[str] = set()
    cost: dict[str, float] = {}
    any_positions = False

    for row in holdings or []:
        if not isinstance(row, dict):
            continue
        raw = row.get("ticker")
        t = str(raw or "").strip().upper()
        if not t:
            continue
        if t not in seen:
            seen.add(t)
            order.append(t)
            cost.setdefault(t, 0.0)
        shares = row.get("shares")
        entry = row.get("entry_price")
        try:
            sh = float(shares) if shares is not None else None
            ep = float(entry) if entry is not None else None
        except (TypeError, ValueError):
            sh = ep = None
        if sh is not None and ep is not None and sh > 0 and ep > 0:
            any_positions = True
            cost[t] += sh * ep

    if not order:
        return [], {}, "equal"

    if any_positions:
        total = sum(cost.values())
        if total > 0:
            weights = {t: cost[t] / total for t in order}
            return order, weights, "positions"
        # cost basis present on the flag rows but total is 0 (shouldn't happen given the
        # >0 guard) — fall through to equal rather than divide by zero.

    n = len(order)
    weights = {t: 1.0 / n for t in order}
    return order, weights, "equal"


# ── ctx sector lookup ────────────────────────────────────────────────────────

def _sector_block(ctx_sectors: dict, sector: str | None) -> dict:
    """Return the ctx.sectors block for a held name's sector, reconciling taxonomies.

    Tries the raw sector name, then the display alias. Returns {} when neither matches
    (honest: we then omit the stance clause rather than fabricate a read)."""
    if not sector or not isinstance(ctx_sectors, dict):
        return {}
    if sector in ctx_sectors:
        blk = ctx_sectors[sector]
        return blk if isinstance(blk, dict) else {}
    alias = _SECTOR_ALIASES.get(sector.strip().lower())
    if alias and alias in ctx_sectors:
        blk = ctx_sectors[alias]
        return blk if isinstance(blk, dict) else {}
    return {}


# ── section builders — each returns a section dict or None ────────────────────

def _pct(x: float) -> int:
    """Whole-number percent (round half to even is fine; deterministic)."""
    return int(round(x * 100))


def _covered(ctx: dict, tickers: list[str]) -> tuple[list[str], list[str]]:
    ctx_tk = ctx.get("tickers") if isinstance(ctx, dict) else None
    ctx_tk = ctx_tk if isinstance(ctx_tk, dict) else {}
    covered = [t for t in tickers if t in ctx_tk]
    uncovered = [t for t in tickers if t not in ctx_tk]
    return covered, uncovered


def _weighted_sector_shares(ctx: dict, covered: list[str], weights: dict) -> list[tuple[str, float]]:
    """[(sector, share)] over covered names that carry a sector, renormalized over
    exactly those names, sorted by share desc then name asc (deterministic)."""
    ctx_tk = ctx.get("tickers", {})
    by_sector: dict[str, float] = {}
    total = 0.0
    for t in covered:
        blk = ctx_tk.get(t) or {}
        sec = blk.get("sector")
        if not sec:
            continue
        w = weights.get(t, 0.0)
        by_sector[sec] = by_sector.get(sec, 0.0) + w
        total += w
    if total <= 0:
        return []
    shares = [(s, w / total) for s, w in by_sector.items()]
    shares.sort(key=lambda kv: (-kv[1], kv[0]))
    return shares


def _held_sectors_ordered(ctx: dict, covered: list[str], weights: dict) -> list[str]:
    """Unique held sectors ordered by book weight desc (uses raw sector names)."""
    shares = _weighted_sector_shares(ctx, covered, weights)
    return [s for s, _ in shares]


def _exposure_section(ctx: dict, covered: list[str], weights: dict) -> dict | None:
    ctx_sectors = ctx.get("sectors") or {}
    shares = _weighted_sector_shares(ctx, covered, weights)
    lines: list[dict] = []

    if shares:
        top_sector, top_share = shares[0]
        pct = _pct(top_share)
        blk = _sector_block(ctx_sectors, top_sector)
        conviction = blk.get("conviction_en")
        conviction_zh = blk.get("conviction_zh")
        rotation = blk.get("rotation_state")
        if conviction:
            paren = f" ({rotation})" if rotation else ""
            en = (f"{pct}% of your book is {top_sector} — today's desk read on "
                  f"{top_sector} is {conviction}{paren}.")
            paren_zh = f"（{rotation}）" if rotation else ""
            zh = (f"你的持仓有 {pct}% 在{top_sector} — 桌面今日对{top_sector}的判读为"
                  f"{conviction_zh or conviction}{paren_zh}。")
        else:
            # No desk read for this sector (taxonomy mismatch or absent block) — state
            # the exposure honestly without inventing a stance.
            en = (f"{pct}% of your book is {top_sector} — no desk read on "
                  f"{top_sector} tonight.")
            zh = f"你的持仓有 {pct}% 在{top_sector} — 桌面今晚对{top_sector}没有判读。"
        lines.append({"en": en, "zh": zh})

        # Diversification caveat — DISPLAY COPY from the charter's own worked example
        # (§1 V1: "41% ... so your effective diversification is thinner than it looks").
        # It is descriptive, NOT prescriptive: it flags concentration + a cautious/reduce
        # or headwind top sector, never tells the user to trim. Threshold (>=40% weight)
        # is that example's own number, reproduced here as display copy — not a new
        # calibrated gate.
        cls = blk.get("class")
        if pct >= 40 and (cls == "headwind" or conviction in ("Cautious", "Reduce")):
            lines.append({
                "en": ("With that much in one sector, your effective diversification "
                       "is thinner than it looks."),
                "zh": "如此集中于单一板块，你的实际分散度比看上去要薄。",
            })

    # Optional second fact: the most common theme among covered names (>=2 share it).
    theme_line = _common_theme_line(ctx, covered)
    if theme_line is not None:
        lines.append(theme_line)

    if not lines:
        return None
    return {"key": "exposure", "title_en": "Exposure",
            "title_zh": "持仓暴露", "lines": lines}


def _common_theme_line(ctx: dict, covered: list[str]) -> dict | None:
    """Most common theme across covered names when >=2 names share it. Verbatim theme
    name + reco + name_zh."""
    ctx_tk = ctx.get("tickers", {})
    counts: dict[str, int] = {}
    meta: dict[str, dict] = {}
    first_seen: dict[str, int] = {}
    idx = 0
    for t in covered:
        blk = ctx_tk.get(t) or {}
        themes = blk.get("themes") or []
        seen_here: set[str] = set()
        for th in themes:
            if not isinstance(th, dict):
                continue
            tid = th.get("id")
            if not tid or tid in seen_here:
                continue
            seen_here.add(tid)
            counts[tid] = counts.get(tid, 0) + 1
            if tid not in meta:
                meta[tid] = th
                first_seen[tid] = idx
                idx += 1
    if not counts:
        return None
    # Most common; tie-break by first-seen order (deterministic).
    best = max(counts.items(), key=lambda kv: (kv[1], -first_seen[kv[0]]))
    tid, n = best
    if n < 2:
        return None
    m = meta[tid]
    name = m.get("name") or tid
    name_zh = m.get("name_zh") or name
    reco = m.get("reco")
    reco_paren = f" ({reco})" if reco else ""
    en = f"{n} of your names sit in the same theme: {name}{reco_paren}."
    reco_paren_zh = f"（{reco}）" if reco else ""
    zh = f"你有 {n} 只个股同属一个主题：{name_zh}{reco_paren_zh}。"
    return {"en": en, "zh": zh}


def _lanes_section(ctx: dict, covered: list[str], weights: dict) -> dict | None:
    ctx_sectors = ctx.get("sectors") or {}
    sectors = _held_sectors_ordered(ctx, covered, weights)
    lines: list[dict] = []

    if sectors:
        parts_en: list[str] = []
        parts_zh: list[str] = []
        for sec in sectors[:5]:
            blk = _sector_block(ctx_sectors, sec)
            conv = blk.get("conviction_en")
            conv_zh = blk.get("conviction_zh")
            rot = blk.get("rotation_state")
            if conv:
                paren = f" ({rot})" if rot else ""
                parts_en.append(f"{sec} — {conv}{paren}")
                paren_zh = f"（{rot}）" if rot else ""
                parts_zh.append(f"{sec} — {conv_zh or conv}{paren_zh}")
            else:
                parts_en.append(f"{sec} — no read")
                parts_zh.append(f"{sec} — 暂无判读")
        lines.append({
            "en": "Your sectors on the board: " + "; ".join(parts_en) + ".",
            "zh": "你的板块在桌面的位置：" + "；".join(parts_zh) + "。",
        })

    # Tailwinds / headwinds touching the book (from `class`), deduped, order by weight.
    tailwinds: list[str] = []
    headwinds: list[str] = []
    for sec in sectors:
        blk = _sector_block(ctx_sectors, sec)
        cls = blk.get("class")
        if cls in ("tailwind", "entry_now") and sec not in tailwinds:
            tailwinds.append(sec)
        elif cls == "headwind" and sec not in headwinds:
            headwinds.append(sec)
    if tailwinds or headwinds:
        seg_en: list[str] = []
        seg_zh: list[str] = []
        if tailwinds:
            seg_en.append("tailwind " + ", ".join(tailwinds))
            seg_zh.append("顺风：" + "、".join(tailwinds))
        if headwinds:
            seg_en.append("headwind " + ", ".join(headwinds))
            seg_zh.append("逆风：" + "、".join(headwinds))
        lines.append({
            "en": "Desk tailwinds/headwinds touching your book: " + "; ".join(seg_en) + ".",
            "zh": "触及你持仓的桌面顺风/逆风：" + "；".join(seg_zh) + "。",
        })

    if not lines:
        return None
    return {"key": "lanes", "title_en": "Rotation board",
            "title_zh": "轮动板", "lines": lines}


# Weinstein stage → plain word (DISPLAY re-expression, fixed wording per spec).
_STAGE_WORD = {1: ("base", "筑底"), 2: ("uptrend", "上升"),
               3: ("topping", "见顶"), 4: ("decline", "下行")}


def _signals_section(ctx: dict, covered: list[str]) -> dict | None:
    ctx_tk = ctx.get("tickers", {})
    lines: list[dict] = []

    # Stage tally over covered names carrying a stage block.
    staged = [(t, (ctx_tk.get(t) or {}).get("stage")) for t in covered]
    staged = [(t, s) for t, s in staged if isinstance(s, dict) and s.get("n") is not None]
    n_staged = len(staged)
    if n_staged:
        by_n: dict[int, int] = {}
        fresh_by_n: dict[int, int] = {}
        for _t, s in staged:
            try:
                sn = int(s.get("n"))
            except (TypeError, ValueError):
                continue
            by_n[sn] = by_n.get(sn, 0) + 1
            if s.get("fresh"):
                fresh_by_n[sn] = fresh_by_n.get(sn, 0) + 1
        # Lead clause: the most common stage. Fixed wording: "Stage N uptrends/…".
        if by_n:
            lead_n = max(by_n.items(), key=lambda kv: (kv[1], -kv[0]))[0]
            lead_count = by_n[lead_n]
            fresh = fresh_by_n.get(lead_n, 0)
            word_en, word_zh = _STAGE_WORD.get(lead_n, ("stage", "阶段"))
            noun_en = {2: "uptrends", 4: "declines"}.get(lead_n, f"{word_en}s")
            fresh_en = f" ({fresh} fresh)" if fresh else ""
            en = (f"{lead_count} of your {n_staged} covered names are in "
                  f"Stage {lead_n} {noun_en}{fresh_en}.")
            fresh_zh = f"（{fresh} 只为新转）" if fresh else ""
            zh = (f"你 {n_staged} 只有覆盖的个股中，有 {lead_count} 只处于第 {lead_n} "
                  f"阶段{word_zh}趋势{fresh_zh}。")
            # Trailing clause: the most notable OTHER stage (prefer 4 decline, then 3).
            other = None
            for cand in (4, 3, 1):
                if cand != lead_n and by_n.get(cand):
                    other = cand
                    break
            if other is not None:
                ow_en, ow_zh = _STAGE_WORD.get(other, ("stage", "阶段"))
                onoun = {2: "uptrend", 4: "decline"}.get(other, ow_en)
                oc = by_n[other]
                en += f" {oc} {'is' if oc == 1 else 'are'} in a Stage {other} {onoun}."
                zh += f"另有 {oc} 只处于第 {other} 阶段{ow_zh}。"
            lines.append({"en": en, "zh": zh})

    # Global entry gate shut.
    gate_go = ctx.get("gate_go")
    if gate_go is False:
        lines.append({
            "en": ("The desk's global entry gate is shut tonight — new-entry signals "
                   "are blocked."),
            "zh": "桌面的全局入场闸门今晚关闭 — 新入场信号被拦下。",
        })

    # Per-name entry reads (verbatim label/state), cap 4 by act_level desc.
    entries: list[tuple[str, dict]] = []
    for t in covered:
        blk = ctx_tk.get(t) or {}
        e = blk.get("entry")
        if isinstance(e, dict) and (e.get("label") or e.get("state")):
            entries.append((t, e))

    def _act(e: dict) -> int:
        try:
            return int(e.get("act_level"))
        except (TypeError, ValueError):
            return -1
    entries.sort(key=lambda te: (-_act(te[1]), te[0]))
    for t, e in entries[:4]:
        label = e.get("label")
        state = e.get("state")
        read = " ".join(x for x in (label, state) if x)
        if state and label:
            en = f"{t}: {label} ({state})."
            zh = f"{t}：{label}（{state}）。"
        else:
            en = f"{t}: {read}."
            zh = f"{t}：{read}。"
        lines.append({"en": en, "zh": zh})

    if not lines:
        return None
    return {"key": "signals", "title_en": "Signals",
            "title_zh": "信号", "lines": lines}


def _regime_section(ctx: dict, covered: list[str], weights: dict) -> dict | None:
    regime = ctx.get("regime") or {}
    us = regime.get("us") if isinstance(regime, dict) else None
    us = us if isinstance(us, dict) else {}
    lines: list[dict] = []

    label_en = us.get("label_en")
    label_zh = us.get("label_zh")
    score = us.get("score")
    if label_en is not None and score is not None:
        lines.append({
            "en": f"The desk's daily read: {label_en} ({score}/100).",
            "zh": f"桌面今日判读：{label_zh or label_en}（{score}/100）。",
        })

    # Second line only if held sectors intersect tailwind/headwind classes. The
    # favor=tailwind|entry_now / against=headwind mapping IS the ctx `class` vocabulary
    # itself (subsector_confluence's own class names) — not a new classification.
    ctx_sectors = ctx.get("sectors") or {}
    sectors = _held_sectors_ordered(ctx, covered, weights)
    favored: list[str] = []
    against: list[str] = []
    for sec in sectors:
        cls = _sector_block(ctx_sectors, sec).get("class")
        if cls in ("tailwind", "entry_now") and sec not in favored:
            favored.append(sec)
        elif cls == "headwind" and sec not in against:
            against.append(sec)
    if favored or against:
        if favored and against:
            en = (f"Of your sectors, the regime favors {', '.join(favored)} and leans "
                  f"against {', '.join(against)}.")
            zh = (f"在你的板块中，当前环境偏好{'、'.join(favored)}，对"
                  f"{'、'.join(against)}偏弱。")
        elif favored:
            en = f"Of your sectors, the regime favors {', '.join(favored)}."
            zh = f"在你的板块中，当前环境偏好{'、'.join(favored)}。"
        else:
            en = f"Of your sectors, the regime leans against {', '.join(against)}."
            zh = f"在你的板块中，当前环境对{'、'.join(against)}偏弱。"
        lines.append({"en": en, "zh": zh})

    if not lines:
        return None
    return {"key": "regime", "title_en": "Regime",
            "title_zh": "市场环境", "lines": lines}


def _earnings_section(ctx: dict, covered: list[str]) -> dict | None:
    ctx_tk = ctx.get("tickers", {})
    rows: list[tuple[str, str, int]] = []
    for t in covered:
        e = (ctx_tk.get(t) or {}).get("earnings")
        if not isinstance(e, dict):
            continue
        nxt = e.get("next")
        days = e.get("days_to")
        try:
            di = int(days)
        except (TypeError, ValueError):
            continue
        if nxt is None or di > 10:
            continue
        rows.append((t, str(nxt), di))
    if not rows:
        return None
    # Sort by days ascending, then ticker (deterministic).
    rows.sort(key=lambda r: (r[2], r[0]))
    n = len(rows)
    first_t, first_d, first_days = rows[0]
    lines: list[dict] = []
    plural_en = "names report" if n != 1 else "name reports"
    en = (f"{n} {plural_en} inside 10 days — {first_t} first "
          f"({first_d}, in {first_days} day{'s' if first_days != 1 else ''}).")
    zh = (f"有 {n} 只个股将在 10 天内公布财报 — {first_t} 最早"
          f"（{first_d}，{first_days} 天后）。")
    lines.append({"en": en, "zh": zh})
    if n > 1:
        listed_en = ", ".join(f"{t} ({d})" for t, d, _ in rows)
        listed_zh = "、".join(f"{t}（{d}）" for t, d, _ in rows)
        lines.append({"en": "All: " + listed_en + ".",
                      "zh": "全部：" + listed_zh + "。"})
    return {"key": "earnings", "title_en": "Earnings clock",
            "title_zh": "财报时钟", "lines": lines}


def _filings_section(ctx: dict, covered: list[str], today: str) -> dict | None:
    ctx_tk = ctx.get("tickers", {})
    t_date = _parse_iso(today)
    lines: list[dict] = []

    # Congress buys/sells filed within 7 days of today, cap 3. side verbatim.
    if t_date is not None:
        cutoff = t_date - timedelta(days=7)
        cong_lines: list[tuple[str, str, str]] = []  # (filed, ticker, side)
        for t in covered:
            for c in ((ctx_tk.get(t) or {}).get("congress") or []):
                if not isinstance(c, dict):
                    continue
                filed = _parse_iso(c.get("filed") or "")
                if filed is None or filed < cutoff or filed > t_date:
                    continue
                side = c.get("side")
                if side not in ("buy", "sell", "other"):
                    continue
                cong_lines.append((str(c.get("filed"))[:10], t, side))
        # Dedupe identical (filed, ticker, side) disclosures — two rows indistinguishable
        # at display granularity must not render as two identical lines. Preserve
        # deterministic order via a seen-set (descriptive, drops no distinct fact).
        _seen_cong: set = set()
        cong_lines = [c for c in cong_lines
                      if not (c in _seen_cong or _seen_cong.add(c))]
        # Most-recent first, cap 3.
        cong_lines.sort(key=lambda r: (r[0], r[1]), reverse=True)
        _SIDE_EN = {"buy": "buy", "sell": "sell", "other": "trade"}
        # zh side words: NEUTRAL filing nouns (购入/售出/交易), never the advice-filter
        # kill-list directional verbs (买入/卖出/加仓/减仓/建仓/平仓 — RUL-NW4). A
        # Congress DISCLOSURE is a reported fact, not an instruction to trade.
        _SIDE_ZH = {"buy": "购入", "sell": "售出", "other": "交易"}
        for filed, t, side in cong_lines[:3]:
            en = f"This week: a Congress {_SIDE_EN[side]} in {t} (filed {filed})."
            zh = f"本周：{t} 出现一笔国会{_SIDE_ZH[side]}披露（申报于 {filed}）。"
            lines.append({"en": en, "zh": zh})

    # Insider tape for held names with buyers+sellers>0, top 2 by |net_mn|.
    insiders: list[tuple[str, dict, float]] = []
    for t in covered:
        ins = (ctx_tk.get(t) or {}).get("insider")
        if not isinstance(ins, dict):
            continue
        buyers = ins.get("buyers") or 0
        sellers = ins.get("sellers") or 0
        try:
            tot = int(buyers) + int(sellers)
        except (TypeError, ValueError):
            continue
        if tot <= 0:
            continue
        try:
            mag = abs(float(ins.get("net_mn"))) if ins.get("net_mn") is not None else 0.0
        except (TypeError, ValueError):
            mag = 0.0
        insiders.append((t, ins, mag))
    insiders.sort(key=lambda r: (-r[2], r[0]))
    for t, ins, _mag in insiders[:2]:
        buyers = int(ins.get("buyers") or 0)
        sellers = int(ins.get("sellers") or 0)
        en = f"Insider tape: {t} {buyers} buyers / {sellers} sellers."
        zh = f"内部人动向：{t} {buyers} 买 / {sellers} 卖。"
        lines.append({"en": en, "zh": zh})

    # 13F trend line when any f13 blocks: compare adds vs trims counts.
    more_adds = 0
    more_trims = 0
    for t in covered:
        f13 = (ctx_tk.get(t) or {}).get("f13")
        if not isinstance(f13, dict):
            continue
        adds = f13.get("adds")
        trims = f13.get("trims")
        try:
            a = int(adds) if adds is not None else None
            tr = int(trims) if trims is not None else None
        except (TypeError, ValueError):
            continue
        if a is None or tr is None:
            continue
        if a > tr:
            more_adds += 1
        elif tr > a:
            more_trims += 1
    if more_adds or more_trims:
        # Both sides present → the charter's "…more adds than trims; N the reverse" form.
        # One side only → a standalone clause (never a dangling "N the reverse").
        if more_adds and more_trims:
            en = (f"13F trend: {more_adds} of your names saw more adds than trims last "
                  f"quarter; {more_trims} the reverse.")
            zh = (f"13F 趋势：上季度有 {more_adds} 只被更多机构增持而非减持；"
                  f"另有 {more_trims} 只相反。")
        elif more_adds:
            en = (f"13F trend: {more_adds} of your names saw more adds than trims last "
                  f"quarter.")
            zh = f"13F 趋势：上季度有 {more_adds} 只被更多机构增持而非减持。"
        else:
            en = (f"13F trend: {more_trims} of your names saw more trims than adds last "
                  f"quarter.")
            zh = f"13F 趋势：上季度有 {more_trims} 只被更多机构减持而非增持。"
        lines.append({"en": en, "zh": zh})

    if not lines:
        return None
    return {"key": "filings", "title_en": "Filings desk",
            "title_zh": "监管申报", "lines": lines}


# ── public composer ──────────────────────────────────────────────────────────

def compose_brief(ctx: dict, holdings: list[dict], today: str,
                  generated_at: str) -> dict:
    """Compose the portfolio_brief.v1 payload from a portfolio_ctx.v1 dict + holdings.

    Pure. See module docstring for the guardrails. Returns EXACTLY the v1 contract the
    terminal Portfolio panel is built against.
    """
    ctx = ctx if isinstance(ctx, dict) else {}
    asof = ctx.get("asof")
    stale = _is_stale(asof, today)

    order, weights, mode = _normalize_holdings(holdings)
    covered, uncovered = _covered(ctx, order)

    book = {"n": len(order), "covered": len(covered), "uncovered": uncovered}
    weighting = {
        "mode": mode,
        "label_en": _MODE_LABELS[mode]["en"],
        "label_zh": _MODE_LABELS[mode]["zh"],
    }

    base = {
        "schema": SCHEMA,
        "asof": asof,
        "generated_at": generated_at,
        "stale": stale,
        "weighting": weighting,
        "book": book,
    }

    # Empty book: no names at all.
    if len(order) == 0:
        base["headline"] = {
            "en": "Add names to your watchlist to see your book through the desk's eyes.",
            "zh": "把标的加入你的观察列表，即可用桌面的视角审视你的持仓。",
        }
        base["sections"] = []
        return base

    # Names held, but none covered by the desk artifact.
    if len(covered) == 0:
        base["headline"] = {
            "en": (f"Your book has {len(order)} "
                   f"{'name' if len(order) == 1 else 'names'}, but none has desk "
                   f"coverage yet — no read to show tonight."),
            "zh": (f"你的持仓有 {len(order)} 只个股，但暂无任何一只被桌面覆盖 — "
                   f"今晚没有可展示的判读。"),
        }
        base["sections"] = []
        return base

    # Full brief.
    sections: list[dict] = []
    for builder in (
        lambda: _exposure_section(ctx, covered, weights),
        lambda: _lanes_section(ctx, covered, weights),
        lambda: _signals_section(ctx, covered),
        lambda: _regime_section(ctx, covered, weights),
        lambda: _earnings_section(ctx, covered),
        lambda: _filings_section(ctx, covered, today),
    ):
        sec = builder()
        if sec is not None and sec.get("lines"):
            sections.append(sec)

    # Headline: names, top weight, desk read.
    shares = _weighted_sector_shares(ctx, covered, weights)
    regime = ctx.get("regime") or {}
    us = regime.get("us") if isinstance(regime, dict) else None
    read_en = (us or {}).get("label_en") if isinstance(us, dict) else None
    read_zh = (us or {}).get("label_zh") if isinstance(us, dict) else None
    n = len(order)
    if shares:
        top_sector, top_share = shares[0]
        pct = _pct(top_share)
        read_clause_en = f", desk read {read_en}" if read_en else ""
        read_clause_zh = f"，桌面判读{read_zh or read_en}" if read_en else ""
        base["headline"] = {
            "en": (f"Your book today: {n} {'name' if n == 1 else 'names'}, top weight "
                   f"{top_sector} {pct}%{read_clause_en}."),
            "zh": (f"你今日的持仓：{n} 只个股，最大权重{top_sector} {pct}%"
                   f"{read_clause_zh}。"),
        }
    else:
        read_clause_en = f", desk read {read_en}" if read_en else ""
        read_clause_zh = f"，桌面判读{read_zh or read_en}" if read_en else ""
        base["headline"] = {
            "en": (f"Your book today: {n} covered "
                   f"{'name' if n == 1 else 'names'}{read_clause_en}."),
            "zh": f"你今日的持仓：{n} 只已覆盖个股{read_clause_zh}。",
        }

    base["sections"] = sections
    return base
