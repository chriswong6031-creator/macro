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

from engine.portfolio_vocab import STAGE_WORD, class_word, sector_block

SNAPSHOT_SCHEMA = "portfolio_state_digest.v1"

# ── bounds on client-supplied input ──────────────────────────────────────────
# `previous` arrives from the CLIENT. Every value read from it is echoed into a sentence
# the server composes and the panel renders next to desk-authored prose, so it is
# untrusted text, not merely stale text. Two defences, both cheap here and expensive to
# retrofit after a client ships:
#   * `_safe_text` — allowlist + length bound. A value that fails is DROPPED (the clause
#     is omitted), never echoed and never partially cleaned.
#   * cardinality caps — a snapshot with 100k names must not turn into 100k sentences.
MAX_PREVIOUS_NAMES = 500     # names read from a client snapshot
MAX_CHANGES = 200            # changes returned from one diff
_MEMBERSHIP_LIST_CAP = 20    # tickers named inside a single added/removed sentence
_TEXT_LIMIT = 64             # entry reads / regime labels / conviction words
_NAME_LIMIT = 48             # tickers and sector names
# Rejected outright: angle brackets and braces (markup/template injection), backslash,
# and any C0/C1 control character (line breaks that would forge a second sentence).
_FORBIDDEN_CHARS = set("<>{}\\")


def _safe_text(value, limit: int = _TEXT_LIMIT) -> str | None:
    """Return `value` as displayable text, or None if it is not safe to echo."""
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s or len(s) > limit:
        return None
    for ch in s:
        if ch in _FORBIDDEN_CHARS or ord(ch) < 32 or 127 <= ord(ch) <= 159:
            return None
    return s


def is_snapshot(obj) -> bool:
    """True iff `obj` is structurally a state digest this module produced.

    This is the SINGLE definition of "the client had a prior visit", shared by
    `diff_snapshots` and by the endpoint's `first_visit` field so the two cannot
    contradict each other. The test is the presence of a `names` MAPPING — not a
    non-empty one: `snapshot_state` legitimately returns `names: {}` for a user whose
    holdings are all desk-uncovered (uncovered names are omitted), and that is a real
    visit whose membership changes must still be reported.
    """
    return isinstance(obj, dict) and isinstance(obj.get("names"), dict)

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


def _stage_phrase(n) -> tuple[str, str] | None:
    """(en, zh) for a stage number, or None when it is not a stage we can name.

    Returns None rather than a generic phrase for an out-of-range value: a client-supplied
    `stage: 999` would otherwise render "moved from Stage 999 stage to …", which is
    client text wearing the desk's voice. No word, no clause.
    """
    if isinstance(n, bool):
        return None
    try:
        i = int(n)
    except (TypeError, ValueError):
        return None
    words = STAGE_WORD.get(i)
    if words is None:
        return None
    return (f"Stage {i} {words[0]}", f"第 {i} 阶段{words[1]}")


def _names_of(snap: dict) -> dict:
    n = snap.get("names") if isinstance(snap, dict) else None
    return n if isinstance(n, dict) else {}


def diff_snapshots(previous: dict, current: dict) -> list[dict]:
    """Return the ordered list of changes between two snapshots.

    Each change is {kind, en, zh} plus `ticker` or `sector` where one applies. Order is
    fixed and deterministic: regime, then per-name state (sorted by ticker) for names
    present in BOTH snapshots, then sector board moves (sorted), then membership.

    `previous` yields [] iff it is not structurally a snapshot (`is_snapshot`) — a first
    visit has nothing to compare against, and inventing "everything is new" would spam
    the panel on day one. Note what this does NOT treat as a first visit: a real snapshot
    whose `names` is empty. That is what a user holding only desk-uncovered names stores,
    and the day one of those names gains coverage its membership change is a genuine
    "since your last visit" fact. Callers MUST derive their own first-visit flag from
    `is_snapshot` for the same reason, or the flag and the changes will disagree.

    Every value read from `previous` is client-supplied and passes `_safe_text` before it
    reaches a sentence; a value that fails is dropped along with its clause.
    """
    if not is_snapshot(previous) or not isinstance(current, dict):
        return []
    prev_names = _names_of(previous)
    cur_names = _names_of(current)
    if len(prev_names) > MAX_PREVIOUS_NAMES:
        # Bounded rather than rejected: the first N by ticker still produce a truthful
        # (if partial) read, and the cap is what stops a hostile or corrupt snapshot from
        # becoming an unbounded response.
        prev_names = {k: prev_names[k] for k in sorted(prev_names)[:MAX_PREVIOUS_NAMES]}

    out: list[dict] = []

    # ── the desk's daily read ────────────────────────────────────────────────
    p_reg = _safe_text(previous.get("regime_en"))
    c_reg = current.get("regime_en")
    if p_reg and c_reg and p_reg != c_reg:
        p_zh = _safe_text(previous.get("regime_zh")) or p_reg
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
            prev_phrase = _stage_phrase(p_stage)
            cur_phrase = _stage_phrase(c_stage)
            if prev_phrase and cur_phrase:
                out.append({
                    "kind": "stage", "ticker": t,
                    "en": f"{t} moved from {prev_phrase[0]} to {cur_phrase[0]}.",
                    "zh": f"{t} 从{prev_phrase[1]}转为{cur_phrase[1]}。",
                })

        p_entry, c_entry = _safe_text(p.get("entry")), c.get("entry")
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
        # Board class. Rendered ONLY through CLASS_WORD: the ctx's `class` values are
        # internal slugs, and printing them raw put untranslated English tokens inside a
        # Chinese sentence. An unmapped class has no display word, so the clause is
        # omitted and the conviction comparison below gets its turn instead — never a
        # slug fallback.
        p_cls, c_cls = _safe_text(p.get("class"), _NAME_LIMIT), c.get("class")
        p_word = class_word(p_cls)
        c_word = class_word(c_cls)
        emitted = False
        if p_cls and c_cls and p_cls != c_cls and p_word and c_word:
            out.append({
                "kind": "sector_class", "sector": sec,
                "en": (f"{sec} moved from {p_word[0]} to {c_word[0]} on the desk's "
                       f"rotation board."),
                "zh": f"{sec} 在桌面轮动板上从{p_word[1]}转为{c_word[1]}。",
            })
            emitted = True
        if not emitted:
            p_conv = _safe_text(p.get("conviction_en"))
            c_conv = c.get("conviction_en")
            if p_conv and c_conv and p_conv != c_conv:
                p_zh = _safe_text(p.get("conviction_zh")) or p_conv
                c_zh = c.get("conviction_zh") or c_conv
                out.append({
                    "kind": "sector_conviction", "sector": sec,
                    "en": f"The desk read on {sec} moved from {p_conv} to {c_conv}.",
                    "zh": f"桌面对{sec}的判读从{p_zh}转为{c_zh}。",
                })

    # ── membership (names you added / removed) ───────────────────────────────
    # `added` comes from the server's own snapshot; `removed` comes from the CLIENT's, so
    # those ticker strings are echoed text and are filtered before they reach a sentence.
    added = sorted(set(cur_names) - set(prev_names))
    removed = sorted(x for x in (set(prev_names) - set(cur_names))
                     if _safe_text(x, _NAME_LIMIT))

    def _membership(kind: str, names: list[str], verb_en: str, verb_zh: str) -> dict:
        """One membership line. The NAME LIST is capped separately from the count: a
        book that gained 400 names is a true count but not a readable sentence, and
        pasting 400 tickers into one line is how a "sentence" becomes a data dump."""
        n = len(names)
        shown = names[:_MEMBERSHIP_LIST_CAP]
        rest = n - len(shown)
        more_en = f", and {rest} more" if rest else ""
        more_zh = f"等 {rest} 只" if rest else ""
        return {
            "kind": kind,
            "en": (f"{n} {'name' if n == 1 else 'names'} {verb_en} this read since your "
                   f"last visit: {', '.join(shown)}{more_en}."),
            "zh": (f"自你上次查看以来，{verb_zh} {n} 只个股："
                   f"{'、'.join(shown)}{more_zh}。"),
        }

    if added:
        out.append(_membership("added", added, "joined", "新增"))
    if removed:
        out.append(_membership("removed", removed, "left", "移出"))

    return out[:MAX_CHANGES]


# The "since your last visit" marker is whatever the CLIENT stored, so its scope is the
# client's storage — per-device today. That is a real limitation users will otherwise
# discover by being confused ("why does my phone say nothing changed?"), so it is
# disclosed IN THE PAYLOAD, the same mechanism `population.disclosure_*` uses to make
# silence visible. A cross-device cursor would need an owner-scoped Supabase table.
CURSOR_DISCLOSURE = {
    "scope": "device",
    "note_en": ("This “since your last visit” marker is kept on this device, so a "
                "different browser or phone keeps its own separate history."),
    "note_zh": "“自你上次查看以来”的记录保存在本设备上，因此换用其他浏览器或手机时会各自独立计算。",
}


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
