"""Deterministic "what changed since your last visit" spine (Watchlist+Portfolio W6).

The retention layer's engine half. Two pure functions and one section composer:

    snapshot_state(ctx, tickers)        -> portfolio_state_digest.v1
    diff_snapshots(previous, current)   -> [change, ...]
    compose_since_section(previous, current) -> brief section | None

**What a snapshot is.** A compact projection of the DESK's public state (stage number,
entry read, sector board class, earnings window, daily regime label) restricted to a
list of tickers. It is the smallest thing a client can keep between visits that still
lets us say what moved. It is a display artifact, not a record of the user.

**TWO-ORGANISMS LAW — the reason this module looks the way it does.** A snapshot carries
tickers and desk state and NOTHING ELSE: no shares, no cost basis, no entry price, no
weights, no account id, no timestamps of the user's own activity. That is not an
oversight to be "improved" later — it is the boundary. Consequences, all deliberate:

  * The user's holdings never enter a signal, score, or artifact write path. This module
    READS ctx and returns strings; it writes nothing, anywhere.
  * No snapshot is ever persisted to `data/` or to any repo artifact. Per-user state is
    the client's (or Supabase under owner-scoped RLS) — never this repo's.
  * Nothing here is loggable. Callers must not log a snapshot: even without money
    fields, the ticker set is the user's book. The composed CHANGE LINES are equally
    off-limits to logs (they name holdings).

**Descriptive, never prescriptive.** Change lines report transitions in the desk's own
vocabulary, copied verbatim (`entry.label`, `entry.state`, sector `class`,
`conviction_en`, regime `label_en`). No imperatives, no targets, no advice — the lines
pass the ask_brain advice filter by construction, and the zh strings avoid the
directional kill-list (买入/卖出/加仓/减仓/建仓/平仓 — RUL-NW4) by using neutral
transition verbs. Asserted in tests.

**Falsifier/refutation vocabulary is absent by construction** (operator 2026-07-27):
these are "what changed" lines, never "the thesis was refuted".

Determinism: pure dict/list math, no I/O, no clock reads. Same inputs → identical
output; names are iterated in sorted order so a dict's insertion order cannot leak into
the rendered sequence.
"""
from __future__ import annotations

from engine.portfolio_vocab import STAGE_WORD, sector_block

SNAPSHOT_SCHEMA = "portfolio_state_digest.v1"

# A name reports "soon" when the desk's own earnings block puts it inside this many
# days. The window is the brief's existing earnings-clock window (engine/portfolio_brief
# `_earnings_section`), reused so the two surfaces cannot disagree about what "soon"
# means — not a new threshold.
EARNINGS_WINDOW_DAYS = 10


def _norm_tickers(tickers) -> list[str]:
    """Uppercased, de-blanked, de-duplicated, SORTED (determinism)."""
    out: set[str] = set()
    for x in tickers or []:
        t = str(x or "").strip().upper()
        if t:
            out.add(t)
    return sorted(out)


def snapshot_state(ctx: dict, tickers) -> dict:
    """Project the desk's current state for `tickers` into a compact diffable digest.

    Uncovered names are OMITTED from `names` rather than recorded as empty: a name the
    desk does not cover has no desk state to change, and an empty record would later
    diff as a spurious "changed" when coverage arrived. Coverage arrival is reported by
    the membership diff instead (a name appearing in `names` for the first time).
    """
    ctx = ctx if isinstance(ctx, dict) else {}
    ctx_tk = ctx.get("tickers")
    ctx_tk = ctx_tk if isinstance(ctx_tk, dict) else {}
    ctx_sectors = ctx.get("sectors") or {}
    regime = ctx.get("regime") or {}
    us = regime.get("us") if isinstance(regime, dict) else None
    us = us if isinstance(us, dict) else {}

    names: dict[str, dict] = {}
    sectors: dict[str, dict] = {}

    for t in _norm_tickers(tickers):
        blk = ctx_tk.get(t)
        if not isinstance(blk, dict):
            continue
        rec: dict = {}

        stage = blk.get("stage")
        if isinstance(stage, dict) and stage.get("n") is not None:
            try:
                rec["stage"] = int(stage.get("n"))
            except (TypeError, ValueError):
                pass

        entry = blk.get("entry")
        if isinstance(entry, dict):
            label = entry.get("label")
            state = entry.get("state")
            if label or state:
                # Verbatim desk words, joined for comparison; rendered back apart.
                rec["entry"] = " / ".join(str(x) for x in (label, state) if x)

        sec = blk.get("sector")
        if sec:
            rec["sector"] = str(sec)
            if str(sec) not in sectors:
                sblk = sector_block(ctx_sectors, str(sec))
                srec: dict = {}
                if sblk.get("class"):
                    srec["class"] = str(sblk["class"])
                if sblk.get("conviction_en"):
                    srec["conviction_en"] = str(sblk["conviction_en"])
                if sblk.get("conviction_zh"):
                    srec["conviction_zh"] = str(sblk["conviction_zh"])
                if srec:
                    sectors[str(sec)] = srec

        earn = blk.get("earnings")
        if isinstance(earn, dict) and earn.get("next") is not None:
            try:
                days = int(earn.get("days_to"))
            except (TypeError, ValueError):
                days = None
            if days is not None:
                rec["earnings_next"] = str(earn.get("next"))[:10]
                rec["earnings_soon"] = days <= EARNINGS_WINDOW_DAYS

        names[t] = rec

    snap: dict = {
        "schema": SNAPSHOT_SCHEMA,
        "asof": ctx.get("asof"),
        "names": names,
        "sectors": sectors,
    }
    if us.get("label_en"):
        snap["regime_en"] = str(us["label_en"])
    if us.get("label_zh"):
        snap["regime_zh"] = str(us["label_zh"])
    return snap


def _stage_phrase(n) -> tuple[str, str]:
    """(en, zh) for a stage number — 'Stage 2 uptrend' / '第 2 阶段上升'."""
    try:
        i = int(n)
    except (TypeError, ValueError):
        return ("an unknown stage", "未知阶段")
    en, zh = STAGE_WORD.get(i, ("stage", "阶段"))
    return (f"Stage {i} {en}", f"第 {i} 阶段{zh}")


def _names_of(snap: dict) -> dict:
    n = snap.get("names") if isinstance(snap, dict) else None
    return n if isinstance(n, dict) else {}


def diff_snapshots(previous: dict, current: dict) -> list[dict]:
    """Return the ordered list of changes between two snapshots.

    Each change is {kind, en, zh} plus `ticker` or `sector` where one applies. Order is
    fixed and deterministic: regime, then per-name state (sorted by ticker) for names
    present in BOTH snapshots, then sector board moves (sorted), then membership.

    A missing/blank `previous` yields [] — a first visit has nothing to compare against,
    and inventing "everything is new" would spam the panel on day one.
    """
    if not isinstance(previous, dict) or not isinstance(current, dict):
        return []
    prev_names = _names_of(previous)
    cur_names = _names_of(current)
    if not prev_names and not previous.get("regime_en"):
        return []

    out: list[dict] = []

    # ── the desk's daily read ────────────────────────────────────────────────
    p_reg = previous.get("regime_en")
    c_reg = current.get("regime_en")
    if p_reg and c_reg and p_reg != c_reg:
        p_zh = previous.get("regime_zh") or p_reg
        c_zh = current.get("regime_zh") or c_reg
        out.append({
            "kind": "regime",
            "en": f"The desk's daily read moved from {p_reg} to {c_reg}.",
            "zh": f"桌面的每日判读从{p_zh}转为{c_zh}。",
        })

    # ── per-name desk state (only names present in both) ─────────────────────
    for t in sorted(set(prev_names) & set(cur_names)):
        p = prev_names.get(t) or {}
        c = cur_names.get(t) or {}
        if not isinstance(p, dict) or not isinstance(c, dict):
            continue

        p_stage, c_stage = p.get("stage"), c.get("stage")
        if p_stage is not None and c_stage is not None and p_stage != c_stage:
            pe, pz = _stage_phrase(p_stage)
            ce, cz = _stage_phrase(c_stage)
            out.append({
                "kind": "stage", "ticker": t,
                "en": f"{t} moved from {pe} to {ce}.",
                "zh": f"{t} 从{pz}转为{cz}。",
            })

        p_entry, c_entry = p.get("entry"), c.get("entry")
        if p_entry and c_entry and p_entry != c_entry:
            out.append({
                "kind": "entry", "ticker": t,
                "en": f"{t}'s entry read changed: {p_entry} → {c_entry}.",
                "zh": f"{t} 的入场判读发生变化：{p_entry} → {c_entry}。",
            })

        # Earnings ENTERING the window is the retention-relevant transition; leaving it
        # (a report that has happened) is reported as its own quieter line.
        if c.get("earnings_soon") and not p.get("earnings_soon"):
            nxt = c.get("earnings_next") or ""
            date_en = f" ({nxt})" if nxt else ""
            date_zh = f"（{nxt}）" if nxt else ""
            out.append({
                "kind": "earnings", "ticker": t,
                "en": (f"{t} now reports inside {EARNINGS_WINDOW_DAYS} "
                       f"days{date_en}."),
                "zh": f"{t} 将在 {EARNINGS_WINDOW_DAYS} 天内公布财报{date_zh}。",
            })
        elif p.get("earnings_soon") and not c.get("earnings_soon"):
            out.append({
                "kind": "earnings_passed", "ticker": t,
                "en": f"{t} is no longer inside the {EARNINGS_WINDOW_DAYS}-day earnings window.",
                "zh": f"{t} 已不在 {EARNINGS_WINDOW_DAYS} 天财报窗口内。",
            })

    # ── sector board moves touching the book ─────────────────────────────────
    p_sec = previous.get("sectors") if isinstance(previous.get("sectors"), dict) else {}
    c_sec = current.get("sectors") if isinstance(current.get("sectors"), dict) else {}
    for sec in sorted(set(p_sec) & set(c_sec)):
        p = p_sec.get(sec) or {}
        c = c_sec.get(sec) or {}
        if not isinstance(p, dict) or not isinstance(c, dict):
            continue
        if p.get("class") and c.get("class") and p["class"] != c["class"]:
            out.append({
                "kind": "sector_class", "sector": sec,
                "en": (f"{sec} moved from {p['class']} to {c['class']} on the desk's "
                       f"rotation board."),
                "zh": f"{sec} 在桌面轮动板上从 {p['class']} 转为 {c['class']}。",
            })
        elif (p.get("conviction_en") and c.get("conviction_en")
                and p["conviction_en"] != c["conviction_en"]):
            p_zh = p.get("conviction_zh") or p["conviction_en"]
            c_zh = c.get("conviction_zh") or c["conviction_en"]
            out.append({
                "kind": "sector_conviction", "sector": sec,
                "en": (f"The desk read on {sec} moved from {p['conviction_en']} to "
                       f"{c['conviction_en']}."),
                "zh": f"桌面对{sec}的判读从{p_zh}转为{c_zh}。",
            })

    # ── membership (names you added / removed) ───────────────────────────────
    added = sorted(set(cur_names) - set(prev_names))
    removed = sorted(set(prev_names) - set(cur_names))
    if added:
        out.append({
            "kind": "added",
            "en": (f"{len(added)} {'name' if len(added) == 1 else 'names'} joined this "
                   f"read since your last visit: {', '.join(added)}."),
            "zh": f"自你上次查看以来，新增 {len(added)} 只个股：{'、'.join(added)}。",
        })
    if removed:
        out.append({
            "kind": "removed",
            "en": (f"{len(removed)} {'name' if len(removed) == 1 else 'names'} left this "
                   f"read since your last visit: {', '.join(removed)}."),
            "zh": f"自你上次查看以来，移出 {len(removed)} 只个股：{'、'.join(removed)}。",
        })

    return out


def compose_since_section(previous: dict, current: dict, *, cap: int = 8) -> dict | None:
    """Render the diff as a brief section, or None when nothing changed.

    A quiet stretch returns None — the panel then shows nothing rather than an "all
    quiet" line it would have to repeat every day. `cap` bounds the rendered lines; the
    count line names the overflow rather than dropping it silently.
    """
    changes = diff_snapshots(previous, current)
    if not changes:
        return None
    lines = [{"en": c["en"], "zh": c["zh"]} for c in changes[:cap]]
    extra = len(changes) - len(lines)
    if extra > 0:
        lines.append({
            "en": f"{extra} further {'change' if extra == 1 else 'changes'} not shown here.",
            "zh": f"另有 {extra} 项变化未在此列出。",
        })
    return {
        "key": "since",
        "title_en": "Since your last visit",
        "title_zh": "自你上次查看以来",
        "lines": lines,
    }
