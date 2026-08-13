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

W6 — POPULATION DISCLOSURE (packet amendment A8). The brief now states, as a first-class
field, WHICH SET OF NAMES it computed over: `positions` (the user's held positions) or
`watchlist_union` (the union of their watchlist symbols, equal-weighted). This program's
founding defect was exactly this hole — a panel headed "your book" composed from a
watchlist, sitting above a table showing a third population, with nothing on screen
saying the three were different sets. The composer CANNOT derive the population (only
the loader that read Supabase knows which query answered), so it is PASSED IN; when a
caller does not pass one the brief says `unspecified` and prints a plain-word line
saying the set was not declared, rather than assuming "positions" and lying quietly.
Every consumer-facing sentence that summarizes the book — headline included — carries
the population, and equal-weighted watchlist analysis is labeled with A8's exact
words: "Watchlist structure — equal weighted".

Note the two axes are INDEPENDENT and must not be conflated: `population` is WHICH NAMES
(positions vs watchlist_union), `weighting` is HOW THEY ARE SIZED (by cost basis vs
equal). A positions population can be equal-weighted (positions with no cost basis
recorded), so neither field implies the other.

Public surface:
    compose_brief(ctx, holdings, today, generated_at, *, population=None,
                  previous=None) -> dict   (portfolio_brief.v2)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from engine.portfolio_changes import compose_since_section, snapshot_state
from engine.portfolio_vocab import SECTOR_ALIASES as _SECTOR_ALIASES
from engine.portfolio_vocab import STAGE_WORD as _STAGE_WORD
from engine.portfolio_vocab import sector_block as _sector_block

SCHEMA = "portfolio_brief.v2"

# ── weighting-mode labels (bilingual) — HOW the names are sized ──────────────
_MODE_LABELS = {
    "positions": {"en": "by cost basis", "zh": "按成本权重"},
    "equal": {"en": "equal-weighted", "zh": "等权"},
}

# ── population-mode labels (bilingual) — WHICH names (A8) ────────────────────
# "Watchlist structure — equal weighted" is A8's mandated wording, verbatim.
_POPULATION_LABELS = {
    "positions": {"en": "Your portfolio positions", "zh": "你的持仓"},
    "watchlist_union": {"en": "Watchlist structure — equal weighted",
                        "zh": "观察列表结构 — 等权"},
    "unspecified": {"en": "Names provided to the desk", "zh": "提交给桌面的标的"},
}
POPULATION_MODES = ("positions", "watchlist_union", "unspecified")


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
# `_sector_block` / `_SECTOR_ALIASES` / `_STAGE_WORD` now live in
# engine/portfolio_vocab.py — imported above so the brief and the change-history
# composer cannot drift apart on desk vocabulary. Values are unchanged.


# ── population plumbing (A8) ─────────────────────────────────────────────────

# The noun each summarizing sentence uses for the set of names. This is how "every
# consumer-facing string that summarizes a book states which population it describes"
# is honored WITHOUT bolting a disclaimer onto every line: the sentence names the set
# it is talking about. Calling a watchlist "your book" is the exact defect A8 closes.
_BOOK_NOUN = {
    "positions": {"en": "your book", "zh": "你的持仓"},
    "watchlist_union": {"en": "your watchlist", "zh": "你的观察列表"},
    "unspecified": {"en": "these names", "zh": "这些标的"},
}


def _norm_population(population: str | None) -> str:
    """Coerce the caller's population to a known mode. Anything unrecognized — including
    None — becomes `unspecified`, which is DISCLOSED rather than guessed."""
    p = str(population or "").strip().lower()
    return p if p in POPULATION_MODES else "unspecified"


def _noun(population: str, lang: str) -> str:
    return _BOOK_NOUN[population][lang]


def _population_block(population: str, n: int, weighting_mode: str) -> dict:
    """The first-class population field (A8). Carries the mode, its bilingual label, the
    count it describes, and a plain-word disclosure sentence a client can render as-is."""
    labels = _POPULATION_LABELS[population]
    unit_en = "name" if n == 1 else "names"
    if population == "positions":
        dis_en = f"This read describes the {n} {unit_en} you hold."
        dis_zh = f"此判读描述你持有的 {n} 只个股。"
    elif population == "watchlist_union":
        dis_en = (f"This read describes the {n} {unit_en} on your watchlists, "
                  f"equal weighted — not a position book.")
        dis_zh = f"此判读描述你观察列表中的 {n} 只个股，按等权计算 — 并非持仓。"
    else:
        dis_en = (f"This read describes the {n} {unit_en} sent to the desk. The set they "
                  f"came from was not declared.")
        dis_zh = f"此判读描述提交给桌面的 {n} 只个股。其来源集合未声明。"
    return {
        "mode": population,
        "label_en": labels["en"],
        "label_zh": labels["zh"],
        "n": n,
        "disclosure_en": dis_en,
        "disclosure_zh": dis_zh,
    }


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


def _exposure_section(ctx: dict, covered: list[str], weights: dict,
                      population: str = "unspecified") -> dict | None:
    ctx_sectors = ctx.get("sectors") or {}
    shares = _weighted_sector_shares(ctx, covered, weights)
    noun_en, noun_zh = _noun(population, "en"), _noun(population, "zh")
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
            en = (f"{pct}% of {noun_en} is {top_sector} — today's desk read on "
                  f"{top_sector} is {conviction}{paren}.")
            paren_zh = f"（{rotation}）" if rotation else ""
            zh = (f"{noun_zh}有 {pct}% 在{top_sector} — 桌面今日对{top_sector}的判读为"
                  f"{conviction_zh or conviction}{paren_zh}。")
        else:
            # No desk read for this sector (taxonomy mismatch or absent block) — state
            # the exposure honestly without inventing a stance.
            en = (f"{pct}% of {noun_en} is {top_sector} — no desk read on "
                  f"{top_sector} tonight.")
            zh = f"{noun_zh}有 {pct}% 在{top_sector} — 桌面今晚对{top_sector}没有判读。"
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


def _lanes_section(ctx: dict, covered: list[str], weights: dict,
                   population: str = "unspecified") -> dict | None:
    ctx_sectors = ctx.get("sectors") or {}
    sectors = _held_sectors_ordered(ctx, covered, weights)
    noun_en, noun_zh = _noun(population, "en"), _noun(population, "zh")
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
            # zh: the genitive form ("触及{noun}的…") produces a double 的 once the noun
            # itself carries one (你的持仓的), which reads as broken Chinese. The
            # "与…相关的" form is the natural phrasing for all three nouns.
            "en": (f"Desk tailwinds/headwinds touching {noun_en}: "
                   + "; ".join(seg_en) + "."),
            "zh": f"与{noun_zh}相关的桌面顺风/逆风：" + "；".join(seg_zh) + "。",
        })

    if not lines:
        return None
    return {"key": "lanes", "title_en": "Rotation board",
            "title_zh": "轮动板", "lines": lines}


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
            zh = f"本周：{t} 出现一笔国会{_SIDE_ZH[side]}披露（{filed}）。"
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
            "title_zh": "监管披露", "lines": lines}


# ── v2 `data` block — machine-renderable, arithmetic only ────────────────────
#
# PSI §5.2 specifies a larger packet (posture/ENB, correlation, options, lanes, tape,
# score). Those legs are DELIBERATELY ABSENT here, not stubbed: every one of them needs
# the factor machinery that today lives client-side in `risk_core.js` / `watchlist_risk.js`
# (the W3 lane) or artifacts this endpoint does not read. Emitting them as nulls would
# read as "the desk abstained" when the truth is "this composer cannot see it", so the
# keys are omitted and the gap is named in the PR body as the follow-up wave. What ships
# here is exactly what the composer can derive from the weights the user supplied plus
# the ctx it already reads: pure arithmetic, no new signal, no threshold, no ranking.


def _concentration_block(ctx: dict, covered: list[str], weights: dict) -> dict:
    """Descriptive concentration arithmetic over the weights the user themselves gave.

    top_name_pct / top3_pct / hhi are standard descriptive statistics of a weight
    vector — no calibration, no gate, no verdict word attached. `sectors` and `themes`
    carry the ctx's own vocabulary verbatim.

    Theme shares are computed over covered names carrying at least one theme; a name in
    two themes counts in both, so theme shares need NOT sum to 100 (stated here because
    a reader would otherwise take it for a bug).
    """
    ranked = sorted(((weights.get(t, 0.0), t) for t in covered), key=lambda wt: (-wt[0], wt[1]))
    total = sum(w for w, _ in ranked)
    out: dict = {}
    if total > 0:
        out["top_name_pct"] = _pct(ranked[0][0] / total)
        out["top3_pct"] = _pct(sum(w for w, _ in ranked[:3]) / total)
        # Herfindahl over renormalized weights; 4dp keeps it deterministic in JSON.
        out["hhi"] = round(sum((w / total) ** 2 for w, _ in ranked), 4)

    ctx_sectors = ctx.get("sectors") or {}
    sectors: list[dict] = []
    for name, share in _weighted_sector_shares(ctx, covered, weights):
        blk = _sector_block(ctx_sectors, name)
        row = {"name": name, "pct": _pct(share)}
        for src, dst in (("class", "class"), ("conviction_en", "conviction"),
                         ("rotation_state", "rotation_state")):
            if blk.get(src):
                row[dst] = blk[src]
        sectors.append(row)
    if sectors:
        out["sectors"] = sectors

    ctx_tk = ctx.get("tickers", {})
    theme_w: dict[str, float] = {}
    theme_meta: dict[str, dict] = {}
    themed_total = 0.0
    for t in covered:
        blk = ctx_tk.get(t) or {}
        themes = blk.get("themes") or []
        seen_here: set[str] = set()
        counted = False
        for th in themes:
            if not isinstance(th, dict):
                continue
            tid = th.get("id")
            if not tid or tid in seen_here:
                continue
            seen_here.add(tid)
            w = weights.get(t, 0.0)
            theme_w[tid] = theme_w.get(tid, 0.0) + w
            theme_meta.setdefault(tid, th)
            counted = True
        if counted:
            themed_total += weights.get(t, 0.0)
    if themed_total > 0:
        rows = []
        for tid, w in theme_w.items():
            m = theme_meta[tid]
            row = {"id": tid, "name": m.get("name") or tid, "pct": _pct(w / themed_total)}
            if m.get("reco"):
                row["reco"] = m["reco"]
            rows.append(row)
        rows.sort(key=lambda r: (-r["pct"], r["id"]))
        if rows:
            out["themes"] = rows
    return out


def _events_block(ctx: dict, covered: list[str]) -> dict:
    """Earnings inside the desk's own 10-day window — the same rows the prose section
    renders, in machine form so a client need not re-parse the sentence."""
    ctx_tk = ctx.get("tickers", {})
    rows: list[dict] = []
    for t in covered:
        e = (ctx_tk.get(t) or {}).get("earnings")
        if not isinstance(e, dict) or e.get("next") is None:
            continue
        try:
            days = int(e.get("days_to"))
        except (TypeError, ValueError):
            continue
        if days > 10:
            continue
        rows.append({"ticker": t, "date": str(e.get("next"))[:10], "days_to": days})
    rows.sort(key=lambda r: (r["days_to"], r["ticker"]))
    return {"earnings_10d": rows} if rows else {}


# ── public composer ──────────────────────────────────────────────────────────

def compose_brief(ctx: dict, holdings: list[dict], today: str,
                  generated_at: str, *, population: str | None = None,
                  previous: dict | None = None) -> dict:
    """Compose the portfolio_brief.v2 payload from a portfolio_ctx.v1 dict + holdings.

    Pure. See module docstring for the guardrails.

    v2 is ADDITIVE over v1: every v1 key keeps its name, type and meaning, so the
    terminal Portfolio panel and any other v1 client keep working untouched. New in v2:
      * `population` — WHICH names this describes (A8). REQUIRED of callers in practice;
        an omitted value renders as `unspecified` and says so, never as a guess.
      * `data` — machine-renderable book/concentration/events + the state digest a
        client persists to get "since your last visit" on the next visit.
      * a `since` section when `previous` (a prior state digest) is supplied.

    `previous` is the CLIENT's own stored digest. Nothing about it is persisted here —
    see engine/portfolio_changes for the two-organisms boundary this respects.
    """
    ctx = ctx if isinstance(ctx, dict) else {}
    asof = ctx.get("asof")
    stale = _is_stale(asof, today)
    population = _norm_population(population)

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
        "population": _population_block(population, len(order), mode),
    }

    # `data.book` + `data.state_digest` are present on EVERY response, including the two
    # degenerate books below: a client that stores the digest each visit must not lose
    # its cursor on the night a book happens to be empty or uncovered.
    def _thin_data() -> dict:
        return {"book": {"n": len(order), "covered": len(covered),
                         "modeled": len(covered), "unmodeled": uncovered,
                         "weighting": mode, "population": population},
                "state_digest": snapshot_state(ctx, order)}

    # Empty book: no names at all.
    if len(order) == 0:
        base["headline"] = {
            "en": "Add names to your watchlist to see your book through the desk's eyes.",
            "zh": "把标的加入你的观察列表，即可用桌面的视角审视你的持仓。",
        }
        base["sections"] = []
        base["data"] = _thin_data()
        return base

    # Names held, but none covered by the desk artifact.
    if len(covered) == 0:
        noun_en, noun_zh = _noun(population, "en"), _noun(population, "zh")
        base["headline"] = {
            "en": (f"{noun_en.capitalize()} has {len(order)} "
                   f"{'name' if len(order) == 1 else 'names'}, but none has desk "
                   f"coverage yet — no read to show tonight."),
            "zh": (f"{noun_zh}有 {len(order)} 只个股，但暂无任何一只被桌面覆盖 — "
                   f"今晚没有可展示的判读。"),
        }
        base["sections"] = []
        base["data"] = _thin_data()
        return base

    # Full brief.
    sections: list[dict] = []
    for builder in (
        lambda: _exposure_section(ctx, covered, weights, population),
        lambda: _lanes_section(ctx, covered, weights, population),
        lambda: _signals_section(ctx, covered),
        lambda: _regime_section(ctx, covered, weights),
        lambda: _earnings_section(ctx, covered),
        lambda: _filings_section(ctx, covered, today),
    ):
        sec = builder()
        if sec is not None and sec.get("lines"):
            sections.append(sec)

    # "Since your last visit" — composed only when the caller supplied a prior digest.
    # It leads the sections: what moved is the reason a returning user opened the page.
    since = compose_since_section(previous, snapshot_state(ctx, order)) if previous else None
    if since is not None:
        sections.insert(0, since)

    # Headline: WHICH names, how many, top weight, desk read. The lead phrase names the
    # population (A8) — a watchlist is never called a book.
    shares = _weighted_sector_shares(ctx, covered, weights)
    regime = ctx.get("regime") or {}
    us = regime.get("us") if isinstance(regime, dict) else None
    read_en = (us or {}).get("label_en") if isinstance(us, dict) else None
    read_zh = (us or {}).get("label_zh") if isinstance(us, dict) else None
    n = len(order)
    lead_en = {"positions": "Your book today", "watchlist_union": "Your watchlist today",
               "unspecified": "The names you sent today"}[population]
    lead_zh = {"positions": "你今日的持仓", "watchlist_union": "你今日的观察列表",
               "unspecified": "你今日提交的标的"}[population]
    # A8: equal-weighted watchlist analysis is labeled as such wherever it is summarized.
    ew_en = ", equal weighted" if (population == "watchlist_union" and mode == "equal") else ""
    ew_zh = "（等权）" if (population == "watchlist_union" and mode == "equal") else ""
    read_clause_en = f", desk read {read_en}" if read_en else ""
    read_clause_zh = f"，桌面判读{read_zh or read_en}" if read_en else ""
    if shares:
        top_sector, top_share = shares[0]
        pct = _pct(top_share)
        base["headline"] = {
            "en": (f"{lead_en}: {n} {'name' if n == 1 else 'names'}{ew_en}, top weight "
                   f"{top_sector} {pct}%{read_clause_en}."),
            "zh": (f"{lead_zh}{ew_zh}：{n} 只个股，最大权重{top_sector} {pct}%"
                   f"{read_clause_zh}。"),
        }
    else:
        base["headline"] = {
            "en": (f"{lead_en}: {n} covered "
                   f"{'name' if n == 1 else 'names'}{ew_en}{read_clause_en}."),
            "zh": f"{lead_zh}{ew_zh}：{n} 只已覆盖个股{read_clause_zh}。",
        }

    base["sections"] = sections
    # `data` — machine-renderable arithmetic + the digest a client stores for next time.
    data: dict = _thin_data()
    conc = _concentration_block(ctx, covered, weights)
    if conc:
        data["concentration"] = conc
    events = _events_block(ctx, covered)
    if events:
        data["events"] = events
    base["data"] = data
    return base
