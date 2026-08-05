"""Dark-pool positioning context — the plain-word read over the off-exchange desk,
plus a same-day-idempotent change-feed and the forward ledger that makes it gradeable.

WHAT CHANGED IN v2 (2026-08-05) AND WHY
---------------------------------------
v1 tagged each standout name `accumulation` / `distribution` / `unusual` and rendered
that as "leaning up" / "leaning down". Two independent problems killed it:

  1. HOUSE LAW FORBADE THE CONSTRUCTION. `research/DO_NOT_REBUILD.md` (PSS-AF1 row)
     and the PSS-AF1 charter:

         "FINRA short volume is not short interest, net selling, or institutional
          buying. Raw short ratio/off-exchange share remains forbidden as a
          standalone direction signal."

     v1 derived a direction from exactly raw off-exchange share + raw short ratio,
     standalone, and shipped it in the hero, the rail and every name card.

  2. MEASUREMENT GAVE IT NOTHING TO STAND ON. Walk-forward over the panel available
     at the time (47 dates; n=86 accumulation / 61 distribution):

         horizon   acc-minus-dist    t      p
         1d            +0.22%       0.33   0.74
         5d            -0.87%      -0.63   0.53
         10d           -0.10%      -0.05   0.96

     The sign flips between 1d and 5d and nothing is near significance. 47 dates
     cannot refute a signal — but they also never supported one, and the copy was
     asserting a direction anyway.

v2 keeps every fact and drops the claim. Names are grouped by the CONJUNCTION that was
actually observed — heavy hidden volume together with which way price went over the
same stretch — which is a description of settled data, and is not standalone (price is
required). The direction question is now *accrued* rather than assumed: every tagged
name is written to `data/darkpool/ledger/forward.jsonl` nightly so it can be graded
against outcomes later.

Front-facing language follows the operator's 2026-07-27 rule: projection windows and
"what we're watching" conditions, never verdict or refutation vocabulary.

EPISTEMICS (house law)
----------------------
Every tag is a deterministic threshold on already-observed data — no model, no LLM
origination, no score with authority. Display/context tier only (is_context_only=True,
display_only=True): it never gates, ranks, sizes, or escalates any surface, and the
word "validated" is never emitted. Roughly half of off-exchange volume is short-marked
by default, so the short tape is read as a CHANGE vs each name's own norm, never as a
raw level.

The change-feed (compact_state / diff_changes / build_changes) mirrors
`transmission_context` exactly: same-day rebuilds reuse the stored prev_state so the
day's accumulated diff is never wiped.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

SCHEMA = "darkpool_context.v2"

# ── standout gate (deterministic; documented on the page) ──────────────────────
STANDOUT_Z    = 1.5    # participation this far above the name's OWN norm
STANDOUT_PART = 0.40   # and at least this share of the day's volume printed off-exchange
BOARD_CAP     = 16     # standouts laid out on the glance board (rest live in the desk)
VENUE_MOVE    = 1.0    # |WoW share change| ≥ this (pp) → a venue "mover"

# The three observed conjunctions. NOT directions — see the module docstring.
_PATTERN_KEYS = ("heavy_into_weakness", "heavy_into_strength", "heavy_price_flat")

_PATTERN_LABEL = {
    "heavy_into_weakness": {"en": "Hidden volume, price falling", "zh": "暗池放量，股价下跌"},
    "heavy_into_strength": {"en": "Hidden volume, price rising",  "zh": "暗池放量，股价上涨"},
    "heavy_price_flat":    {"en": "Hidden volume, price flat",    "zh": "暗池放量，股价横盘"},
}
_PATTERN_READ = {
    "heavy_into_weakness": {
        "en": "An unusual amount of these names' volume printed away from the public "
              "tape while the price fell. Someone took the other side of that selling — "
              "the tape cannot say who, or whether they were early.",
        "zh": "这些个股有异常高比例的成交发生在公开盘面之外，同时股价下跌。有人承接了这些卖盘——"
              "但成交数据无法说明是谁，也无法说明他们是否过早入场。",
    },
    "heavy_into_strength": {
        "en": "Heavy off-exchange volume alongside a rising price. Big orders were being "
              "worked while the name was already moving up — which is as consistent with "
              "sellers meeting demand as with buyers chasing.",
        "zh": "场外成交沉重，同时股价上涨。大单在股价已经上行时被执行——这既可能是卖方在满足需求，"
              "也可能是买方在追高。",
    },
    "heavy_price_flat": {
        "en": "Unusually heavy hidden volume with the price going nowhere. Large size "
              "changed hands without moving the quote, which is what working an order "
              "quietly is supposed to look like.",
        "zh": "暗池成交异常沉重，但股价几乎未动。大量筹码易手却没有推动报价——"
              "这正是悄然执行大单应有的样子。",
    },
}
# "What we're watching" — conditions, not calls (operator 2026-07-27).
_PATTERN_WATCH = {
    "heavy_into_weakness": {
        "en": "Watching whether the hidden volume keeps up once the price stops falling.",
        "zh": "观察股价止跌后，暗池成交是否仍然维持。",
    },
    "heavy_into_strength": {
        "en": "Watching whether the off-exchange share fades as the move extends.",
        "zh": "观察随着涨势延伸，场外占比是否回落。",
    },
    "heavy_price_flat": {
        "en": "Watching which way the quote breaks once the size stops printing.",
        "zh": "观察大额成交结束后，报价向哪个方向突破。",
    },
}


# ── per-name label helpers ─────────────────────────────────────────────────────

def _norm_label(z: float | None) -> dict:
    """Plain-word 'vs its own norm' from the participation z."""
    if z is None:
        return {"en": "—", "zh": "—"}
    if z >= 3.0:
        return {"en": "Far above", "zh": "远超常态"}
    if z >= 2.0:
        return {"en": "Well above", "zh": "明显高于"}
    return {"en": "Above", "zh": "高于常态"}


def _streak_label(streak: int) -> dict:
    """A campaign reads differently from a one-day spike."""
    # Reads under an "Elevated for" label on the card, so the value carries the COUNT
    # only. Earlier drafts rendered "Running for 6 sessions running" (en) and
    # "已持续 连续 6 日" (zh) — the label's verb repeated in the value in both languages.
    # Phrased so streak == 1 also reads cleanly ("Elevated for 1 session").
    return {"en": f"{streak} session" + ("s" if streak != 1 else ""),
            "zh": f"{streak} 日"}


def _venue_character(ats_frac: float | None) -> dict:
    """How much of the hidden volume reached a REGISTERED dark pool (ATS).

    The old desk could not draw this at all — it called the whole off-exchange blob
    "dark pool" while only ever showing the ATS quarter of it. Descriptive cuts on an
    observed ratio, not a scored signal.
    """
    # Renders as "<label> <value>" on the card, where the label already says "Reached a
    # dark pool" — so the value carries the FIGURE only. Restating the label here
    # printed "Reached a dark pool 34% reached a dark pool" (and the same doubling in zh).
    if ats_frac is None:
        return {"en": "not yet reported", "zh": "尚未公布"}
    pct = ats_frac * 100
    # "only" below the ~25% typical large-cap level, where the headline "dark pool"
    # framing is most misleading; the bare figure at or above it.
    if ats_frac < 0.25:
        return {"en": f"only {pct:.0f}%", "zh": f"仅 {pct:.0f}%"}
    return {"en": f"{pct:.0f}%", "zh": f"{pct:.0f}%"}


def _counterparty_character(row: dict) -> dict | None:
    """Who internalized the rest — retail wholesaler vs bank/institutional desk.

    This is the half the desk could never see. Off-exchange volume that does NOT reach
    an ATS was internalized by a firm, and FINRA names that firm; mapping it to the
    firm's primary business (knowledge/darkpool/otc_firm_roles.yaml) separates retail
    order flow from institutional risk transfer. Measured week 2026-06-22 the split is
    strongly discriminating — AAPL 38.7% bank desks vs F 6.7%, while F is 73% wholesaler.

    A LABELLED HEURISTIC on firm business, never a measurement of who was trading, and
    never a direction. Returns None when nothing is attributable so the card omits the
    line rather than printing a hollow one.
    """
    whole = row.get("frac_retail_wholesaler")
    bank = row.get("frac_institutional_desk")
    unk = row.get("frac_unclassified")
    if whole is None and bank is None:
        return None
    whole = whole or 0.0
    bank = bank or 0.0
    tail_en = f" ({unk * 100:.0f}% unattributed)" if unk else ""
    tail_zh = f"（{unk * 100:.0f}% 无法归类）" if unk else ""
    if bank > whole:
        return {"en": f"{bank * 100:.0f}% via bank desks, {whole * 100:.0f}% via retail wholesalers{tail_en}",
                "zh": f"{bank * 100:.0f}% 经银行交易台，{whole * 100:.0f}% 经散户批发商{tail_zh}"}
    return {"en": f"{whole * 100:.0f}% via retail wholesalers, {bank * 100:.0f}% via bank desks{tail_en}",
            "zh": f"{whole * 100:.0f}% 经散户批发商，{bank * 100:.0f}% 经银行交易台{tail_zh}"}


def _name_read(pattern: str, streak: int, ats_frac: float | None) -> dict:
    """One-line, name-level plain read. Describes; never calls a direction."""
    if streak >= 5:
        en_pre, zh_pre = f"{streak} sessions of above-normal hidden volume", f"连续 {streak} 日暗池成交高于常态"
    else:
        en_pre, zh_pre = "Above-normal hidden volume", "暗池成交高于常态"
    if pattern == "heavy_into_weakness":
        en_mid, zh_mid = "while the price fell", "同时股价下跌"
    elif pattern == "heavy_into_strength":
        en_mid, zh_mid = "while the price rose", "同时股价上涨"
    else:
        en_mid, zh_mid = "with the price barely moving", "而股价几乎未动"
    tail_en = ""
    tail_zh = ""
    if ats_frac is not None and ats_frac >= 0.40:
        tail_en, tail_zh = ", and an unusually large slice ran through dark pools", "，且其中经由暗池的比例异常偏高"
    elif ats_frac is not None and ats_frac < 0.25:
        tail_en, tail_zh = ", though most of it was internalized retail flow", "，但其中多数是内部化的散户订单流"
    return {"en": f"{en_pre} {en_mid}{tail_en}.", "zh": f"{zh_pre}{zh_mid}{tail_zh}。"}


# ── classification ─────────────────────────────────────────────────────────────

def classify(row: dict) -> str | None:
    """Deterministic conjunction tag for one desk row, or None if not a standout.

    A *standout* has off-exchange participation both unusually high vs its own norm
    (participation_z ≥ STANDOUT_Z) and materially dark (≥ STANDOUT_PART of the day's
    volume). Requires the z — names without enough history are never tagged
    (honest-null, never forced).

    Returns None when price is unavailable: without price there is no conjunction to
    name, and naming one from off-exchange share alone is the forbidden construction.
    """
    z = row.get("participation_z")
    part = row.get("participation")
    if z is None or part is None:
        return None
    if z < STANDOUT_Z or part < STANDOUT_PART:
        return None
    return row.get("pattern")


def _conviction(row: dict) -> float:
    """Display-only ordering key (NOT a scored signal).

    Delegates to signals.unusualness so the standout board and the sortable desk below
    it agree on what "most unusual" means — two different orderings on one page reads
    as a bug to anyone who scrolls.
    """
    from engine.darkpool_signals import NameMetrics, unusualness
    return unusualness(NameMetrics(
        ticker=row.get("ticker", ""),
        participation=row.get("participation"),
        participation_z=row.get("participation_z"),
        streak=row.get("streak") or 0,
        offex_dollars=row.get("offex_dollars"),
        short_rate_z=row.get("short_rate_z"),
    ))


# ── snapshot ───────────────────────────────────────────────────────────────────

def _hero(tally: dict, gauge: dict | None, n_no_price: int = 0) -> dict:
    """Deterministic plain-word state of the tape. Describes; never calls direction."""
    total = sum(tally.values())
    g = gauge or {}
    dw = g.get("participation_dollar_wtd")
    mkt_en = ""
    mkt_zh = ""
    if dw is not None:
        mkt_en = f" Across the desk, {dw * 100:.0f}% of dollar volume printed off-exchange."
        mkt_zh = f"全盘来看，{dw * 100:.0f}% 的成交金额发生在场外。"
    if total == 0:
        return {
            "en": "No name is trading unusually far off its own off-exchange norm today."
                  + mkt_en,
            "zh": "今日没有个股的场外成交明显偏离自身常态。" + mkt_zh,
        }
    weak = tally.get("heavy_into_weakness", 0)
    strong = tally.get("heavy_into_strength", 0)
    flat = tally.get("heavy_price_flat", 0)
    lead = max(_PATTERN_KEYS, key=lambda k: tally.get(k, 0))
    if lead == "heavy_into_weakness":
        body_en = (f"{total} names are trading unusually dark; in {weak} of them the "
                   f"hidden volume showed up while the price was falling.")
        body_zh = f"{total} 只个股场外成交异常偏重，其中 {weak} 只是在股价下跌时出现的。"
    elif lead == "heavy_into_strength":
        body_en = (f"{total} names are trading unusually dark; in {strong} of them the "
                   f"hidden volume showed up while the price was rising.")
        body_zh = f"{total} 只个股场外成交异常偏重，其中 {strong} 只是在股价上涨时出现的。"
    else:
        body_en = (f"{total} names are trading unusually dark; in {flat} of them large "
                   f"size changed hands without moving the quote.")
        body_zh = f"{total} 只个股场外成交异常偏重，其中 {flat} 只是在报价几乎未动的情况下完成的。"
    return {"en": body_en + mkt_en, "zh": body_zh + mkt_zh}


def _venue_block(ats_table: dict | None) -> dict:
    """Prettified venue rollup: top venues by share + the biggest WoW mover."""
    if not ats_table or not ats_table.get("venues"):
        return {"week_start": None, "lag_note": None, "lag_days": None, "top": [], "mover": None}
    top = []
    for v in ats_table["venues"][:8]:
        top.append({
            "name": v.get("venue_name") or v.get("mpid"),
            "mpid": v.get("mpid"),
            "share_pct": v.get("share_of_total_pct"),
            "wow_pp": v.get("wow_pp"),
            "is_new": bool(v.get("wow_is_new")),
        })
    movers = [v for v in ats_table["venues"]
              if v.get("wow_pp") is not None and abs(v["wow_pp"]) >= VENUE_MOVE
              and not v.get("wow_is_new")]
    mover = None
    if movers:
        m = max(movers, key=lambda v: abs(v["wow_pp"]))
        mover = {"name": m.get("venue_name") or m.get("mpid"), "mpid": m.get("mpid"),
                 "wow_pp": m.get("wow_pp"), "share_pct": m.get("share_of_total_pct")}
    return {
        "week_start": ats_table.get("week_start"),
        "lag_note": ats_table.get("lag_note"),
        "lag_days": ats_table.get("lag_days"),
        "top": top,
        "mover": mover,
    }


def build_snapshot(rows: list[dict], ats_table: dict | None, asof: str,
                   gauge: dict | None = None, coverage: dict | None = None) -> dict:
    """Group desk rows by observed conjunction + a laid-out board + hero state. Pure."""
    tagged: list[tuple[str, dict]] = []
    for r in rows:
        pat = classify(r)
        if pat is not None:
            tagged.append((pat, r))

    tally = {k: sum(1 for pat, _ in tagged if pat == k) for k in _PATTERN_KEYS}

    patterns: dict = {}
    for k in _PATTERN_KEYS:
        names = [r["ticker"] for pat, r in
                 sorted((t for t in tagged if t[0] == k), key=lambda t: -_conviction(t[1]))]
        patterns[k] = {
            "n": tally[k],
            "label": _PATTERN_LABEL[k],
            "read": _PATTERN_READ[k],
            "watch": _PATTERN_WATCH[k],
            "names": names,
        }

    standouts = []
    for pat, r in sorted(tagged, key=lambda t: -_conviction(t[1]))[:BOARD_CAP]:
        standouts.append({
            "ticker": r.get("ticker"),
            "pattern": pat,
            "pattern_label": _PATTERN_LABEL[pat],
            "participation": r.get("participation"),
            "participation_norm": r.get("participation_norm"),
            "participation_z": r.get("participation_z"),
            "streak": r.get("streak") or 0,
            "price_change_pct": r.get("price_change_pct"),
            "offex_dollars": r.get("offex_dollars"),
            "short_rate": r.get("short_rate"),
            "short_trend_pp": r.get("short_trend_pp"),
            "exempt_rate": r.get("exempt_rate"),
            "ats_frac": r.get("ats_frac"),
            "frac_retail_wholesaler": r.get("frac_retail_wholesaler"),
            "frac_institutional_desk": r.get("frac_institutional_desk"),
            "frac_unclassified": r.get("frac_unclassified"),
            "ats_block_shares": r.get("ats_block_shares"),
            "nonats_block_shares": r.get("nonats_block_shares"),
            "top_ats_venue": r.get("top_ats_venue"),
            "top_nonats_firm": r.get("top_nonats_firm"),
            "norm_label": _norm_label(r.get("participation_z")),
            "streak_label": _streak_label(r.get("streak") or 0),
            "venue_character": _venue_character(r.get("ats_frac")),
            "counterparty_character": _counterparty_character(r),
            "read": _name_read(pat, r.get("streak") or 0, r.get("ats_frac")),
        })

    return {
        "asof": asof,
        "hero": _hero(tally, gauge, (coverage or {}).get("n_no_price", 0)),
        "gauge": gauge or {},
        "coverage": coverage or {},
        "tally": tally,
        "patterns": patterns,
        "standouts": standouts,
        "n_standouts": len(tagged),
        "venues": _venue_block(ats_table),
    }


# ── change-feed (mirrors engine/transmission_context.py idempotence) ───────────

_DIFF_ORDER = [
    "into_weakness", "into_strength", "into_flat",
    "left_weakness", "left_strength", "left_flat",
    "venue_mover", "venue_new",
]
_MAX_CHANGES = 6


def compact_state(snapshot: dict) -> dict:
    """Comparison fingerprint: which names sit in each pattern + the venue leader/mover."""
    pats = snapshot.get("patterns") or {}
    venues = snapshot.get("venues") or {}
    top = venues.get("top") or []
    out = {k: sorted((pats.get(k) or {}).get("names") or []) for k in _PATTERN_KEYS}
    out["venue_leader"] = top[0]["name"] if top else None
    out["venue_mover"] = (venues.get("mover") or {}).get("name") if venues.get("mover") else None
    out["venue_mover_pp"] = (venues.get("mover") or {}).get("wow_pp") if venues.get("mover") else None
    return out


def _names_phrase(names: list[str], zh: bool = False) -> str:
    """Join tickers into a plain phrase — connectors localised (tickers stay Latin)."""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]}、{names[1]}" if zh else f"{names[0]} and {names[1]}"
    if zh:
        return f"{names[0]}、{names[1]} 等{len(names)}只"
    return f"{names[0]}, {names[1]} and {len(names) - 2} more"


def diff_changes(prev: dict, curr: dict) -> list[dict]:
    """≤6 bilingual change items between two compact_state dicts.

    First-appearance (empty prev) emits nothing to avoid phantom "appeared" diffs.
    """
    if not prev:
        return []
    candidates: list[tuple[int, dict]] = []

    def _add(key: str, en: str, zh: str):
        idx = _DIFF_ORDER.index(key) if key in _DIFF_ORDER else 99
        candidates.append((idx, {"key": key, "en": en, "zh": zh}))

    moves = [
        ("heavy_into_weakness", "into_weakness", "left_weakness",
         ("started printing dark into weakness", "开始在下跌中出现暗池放量"),
         ("stopped printing dark into weakness", "不再于下跌中出现暗池放量")),
        ("heavy_into_strength", "into_strength", "left_strength",
         ("started printing dark into strength", "开始在上涨中出现暗池放量"),
         ("stopped printing dark into strength", "不再于上涨中出现暗池放量")),
        ("heavy_price_flat", "into_flat", "left_flat",
         ("started absorbing size without moving", "开始在价格未动时承接大量成交"),
         ("stopped absorbing size quietly", "不再于价格未动时承接大量成交")),
    ]
    for pat, in_key, out_key, (in_en, in_zh), (out_en, out_zh) in moves:
        pset, cset = set(prev.get(pat) or []), set(curr.get(pat) or [])
        entered = sorted(cset - pset)
        left = sorted(pset - cset)
        if entered:
            _add(in_key, f"{_names_phrase(entered)} {in_en}",
                 f"{_names_phrase(entered, zh=True)}{in_zh}")
        if left:
            _add(out_key, f"{_names_phrase(left)} {out_en}",
                 f"{_names_phrase(left, zh=True)}{out_zh}")

    mover, pp = curr.get("venue_mover"), curr.get("venue_mover_pp")
    if mover and pp is not None and mover != prev.get("venue_mover"):
        arrow = "▲" if pp > 0 else "▼"
        _add("venue_mover",
             f"Venue: {mover} pool share {arrow}{abs(pp):.1f}pp",
             f"场所：{mover} 暗池占比 {arrow}{abs(pp):.1f}pp")

    candidates.sort(key=lambda x: x[0])
    return [item for _, item in candidates[:_MAX_CHANGES]]


def build_changes(old_contract: dict | None, new_snapshot: dict, new_asof: str) -> tuple[dict, dict]:
    """Same-day-idempotent (changes_block, prev_state_block). Mirrors transmission_context.

    - old_contract None (first run): empty changes.
    - new day: diff yesterday's state → today.
    - same-day rebuild: reuse stored prev_state so the day's diff isn't wiped.
    """
    if old_contract is None:
        return {"vs_asof": None, "items": []}, {"as_of": None, "state": {}}

    new_cs = compact_state(new_snapshot)
    old_asof = old_contract.get("asof")
    if old_asof != new_asof:
        base = compact_state(old_contract)
        base_asof = old_asof
    else:
        prev_stored = old_contract.get("prev_state") or {}
        base = prev_stored.get("state") or {}
        base_asof = prev_stored.get("as_of")

    items = diff_changes(base, new_cs) if (base_asof and base) else []
    return {"vs_asof": base_asof, "items": items}, {"as_of": base_asof, "state": base}


# ── forward ledger — makes the read gradeable instead of assumed ───────────────

def _ledger_path(root: Path | str | None = None) -> Path:
    if root is None:
        from lib import config
        root = config.ROOT
    return Path(root) / "data" / "darkpool" / "ledger" / "forward.jsonl"


def append_ledger(snapshot: dict, asof: str, root: Path | str | None = None) -> int:
    """Append one row per tagged name for `asof`. Same-day idempotent.

    v1 shipped a directional call and never wrote down what it called, so after months
    of running there was nothing to grade it against — the null in the module docstring
    had to be reconstructed after the fact. This records the state at the time of the
    tag so the direction question becomes answerable from the desk's own history.

    Deliberately records ONLY observed inputs — no outcome, no score, no direction.
    Grading is a separate, later read over this file.

    Nightly is the sole advancer of forward ledgers (house law); an intraday rebuild
    rewrites the same `asof` block rather than appending a second one.
    """
    path = _ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)

    kept: list[str] = []
    if path.exists():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    if json.loads(line).get("asof") != asof:
                        kept.append(line)
                except json.JSONDecodeError:
                    kept.append(line)      # never drop a line we cannot parse
        except OSError as exc:
            log.warning("darkpool ledger unreadable (%s) — not appending", exc)
            return 0

    rows = []
    for s in snapshot.get("standouts") or []:
        rows.append(json.dumps({
            "asof": asof,
            "ticker": s.get("ticker"),
            "pattern": s.get("pattern"),
            "participation": s.get("participation"),
            "participation_z": s.get("participation_z"),
            "streak": s.get("streak"),
            "price_change_pct": s.get("price_change_pct"),
            "ats_frac": s.get("ats_frac"),
            "short_trend_pp": s.get("short_trend_pp"),
        }, separators=(",", ":")))

    path.write_text("\n".join(kept + rows) + ("\n" if (kept or rows) else ""), encoding="utf-8")
    return len(rows)


# ── artifact assembly + persistence ────────────────────────────────────────────

def _default_path(root: Path | str | None = None) -> Path:
    if root is None:
        from lib import config
        root = config.ROOT
    return Path(root) / "data" / "darkpool" / "context" / "latest.json"


def build_context_feed(
    rows: list[dict],
    ats_table: dict | None,
    *,
    asof: str,
    built: str,
    tier: str = "eod",
    gauge: dict | None = None,
    coverage: dict | None = None,
    root: Path | str | None = None,
    write: bool = True,
) -> dict:
    """Assemble + (optionally) persist the darkpool_context.v2 artifact.

    Reads the prior artifact BEFORE overwriting so the change-feed can diff against it
    (same-day-idempotent via build_changes). Returns the full artifact — the page
    template renders it directly and the Neural Web lobe reads a compact projection.

    Fail-open by construction: a missing prior file just means empty changes; the
    caller (build_darkpool_desk) wraps this so it can never break the HTML desk.
    """
    out_path = _default_path(root)
    snapshot = build_snapshot(rows, ats_table, asof, gauge=gauge, coverage=coverage)

    old_contract: dict | None = None
    if out_path.exists():
        try:
            old_contract = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("darkpool_context: prior artifact unreadable (%s) — no change-feed", exc)

    changes, prev_state = build_changes(old_contract, snapshot, asof)

    artifact = {
        "schema": SCHEMA,
        "asof": asof,
        "built": built,
        "tier": tier,
        "is_context_only": True,
        "display_only": True,
        "hero": snapshot["hero"],
        "gauge": snapshot["gauge"],
        "coverage": snapshot["coverage"],
        "tally": snapshot["tally"],
        "patterns": snapshot["patterns"],
        "standouts": snapshot["standouts"],
        "n_standouts": snapshot["n_standouts"],
        "venues": snapshot["venues"],
        "changes": changes,
        "prev_state": prev_state,
    }

    if write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(artifact, ensure_ascii=False, separators=(",", ":")),
                            encoding="utf-8")
        n_led = append_ledger(snapshot, asof, root)
        log.info("wrote %s (%d standouts: %s, %d changes, %d ledger rows)",
                 out_path, snapshot["n_standouts"],
                 " / ".join(f"{k.replace('heavy_', '')} {snapshot['tally'][k]}" for k in _PATTERN_KEYS),
                 len(changes["items"]), n_led)

    return artifact
