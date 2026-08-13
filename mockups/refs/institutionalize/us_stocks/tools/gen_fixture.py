#!/usr/bin/env python3
"""Generate the Prophet Board mockup fixture from the REAL committed payload.

Reads site/prophet/index.json (plan book = Setups) and site/factordata/us_standouts.json
(screener rows = Candidates) off origin/main, derives lifecycle_state per the ruling
§6 precedence verbatim, and emits a self-contained JS data module for the mockup.

The derivation here is a MOCKUP-SIDE projection only. In production PR-0(c) publishes
lifecycle_state + lifecycle_counts and the page quotes them; nothing is re-derived
client-side. This script exists so the mockup's numbers are real and reconcile.
"""
import json
import subprocess
import collections
import datetime

REPO = "/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/prophet-board-mockup-gate-b3966f"


def git_json(path):
    out = subprocess.check_output(["git", "show", f"origin/main:{path}"], cwd=REPO)
    return json.loads(out)


# ── ruling §6 derivation, precedence order verbatim (first match wins) ──────────
def lifecycle_state(row):
    if row.get("closed") is True:
        return "resolved"
    ph = row.get("phase")
    if ph == "invalidated":
        return "invalidated"
    if ph == "overtime":
        return "overtime"
    if ph in ("at_t1", "between_t1_t2", "at_t2"):
        return "delivering"
    if ph == "triggered_pre_t1":
        return "entered"
    if ph == "pre_trigger":
        return "ready"
    return "ready"  # unknown/absent -> never advertised further along


CELLS = ["watch", "ready", "entered", "delivering", "overtime", "invalidated", "resolved"]
LIVE_CELLS = CELLS[:-1]


# ── STANCE: the single projection from Prophet's entry/actionability axis ──────
#
# Operator ruling 2026-08-13: the Board stance comes from the entry/actionability
# axis ONLY. It may NOT fall through to the management engine's
# `recommended_action` — that engine describes itself as trade-management-only and
# its action carries display/narrative authority, not order authority. A plan that
# cannot obtain the axis is BLOCKED_DATA, never a guessed "wait".
#
# The grouping below is FACTORED FROM the shipped engine logic, not re-invented:
# `engine/us_board_rank.py:365-368` already partitions the twelve-value domain into
# four buckets, and `STAGE_LABELS` (:379) already names them for users. This maps
# those same buckets onto the five shipped card verbs. If the engine's buckets
# move, this projection must move with them — pinned by tests/verify.py.
#
#   _LIVE_STATUSES       buy_now, partial, buy_soon   -> BUY / NEAR
#   _SETTING_UP_STATUSES await_confluence, bounce_wait, watch -> WAIT
#   _RAN_STATUSES        extended, topping, hold      -> HOLD
#   _BLOCKED_STATUSES    blocked, exit, avoid         -> AVOID
#
# `wait_pullback`, `later` and `await` carry an _ENTRY_VALUE but sit in no bucket;
# `stage_for()` routes wait_pullback to setting_up (us_board_rank.py:393), so they
# join WAIT. There is deliberately NO sixth verb: TRIM does not exist on the Board.
STANCE_BY_STATUS = {
    "buy_now": "buy", "partial": "buy",
    "buy_soon": "near",
    "await_confluence": "wait", "bounce_wait": "wait", "watch": "wait",
    "wait_pullback": "wait", "later": "wait", "await": "wait",
    "extended": "hold", "topping": "hold", "hold": "hold",
    "blocked": "avoid", "exit": "avoid", "avoid": "avoid",
}
BLOCKED_DATA = "blocked_data"


def stance(row, life):
    """Glance-tier Prophet stance — buy / near / wait / hold / avoid.

    Returns None when a stance is not applicable (a closed plan has no live
    stance), and BLOCKED_DATA when the actionability axis has not published for
    this plan. BLOCKED_DATA is a disclosed absence, NOT a cautious default: a
    guessed "wait" would originate a signal the engine never stated.
    """
    if life == "resolved":
        return None                        # not applicable, not missing
    if life == "invalidated":
        return "avoid"                     # the plan's own void level was hit
    st = row.get("entry_status")
    if st in STANCE_BY_STATUS:
        return STANCE_BY_STATUS[st]
    return BLOCKED_DATA                    # axis absent -> say so, never guess


def clip(s, n):
    """Trim to glance-tier length on a word boundary. The mockup shows one plain line."""
    if not s:
        return s
    s = str(s).strip()
    if len(s) <= n:
        return s
    cut = s[:n]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > n * 0.6 else cut).rstrip(" ,;.—-") + "…"


def short_en(row):
    """One plain line: what to do now, first step, trimmed to glance tier."""
    w = row.get("what_to_do_now")
    if isinstance(w, list) and w:
        return clip(w[0], 150)
    return ""


def short_zh(row):
    w = row.get("what_to_do_now_zh")
    if isinstance(w, list) and w:
        return clip(w[0], 70)
    return ""


def fmt_date(iso):
    if not iso:
        return None
    try:
        d = datetime.date.fromisoformat(str(iso)[:10])
    except Exception:
        return None
    return {
        "iso": d.isoformat(),
        "en": d.strftime("%b %-d"),
        "zh": f"{d.month}月{d.day}日",
    }


def assert_projection_tracks_engine():
    """Fail regeneration if the engine's actionability buckets drift from the
    stance projection. The projection is FACTORED FROM those buckets, so it may
    not silently fall out of step with them — that is how a display mapping turns
    into an independent, unowned semantic."""
    import re
    src = open(f"{REPO}/engine/us_board_rank.py").read()

    def bucket(name):
        m = re.search(name + r"\s*=\s*frozenset\(\(([^)]*)\)\)", src)
        if not m:
            raise AssertionError(f"{name} not found in engine/us_board_rank.py")
        return {x.strip().strip("\"'") for x in m.group(1).split(",") if x.strip()}

    expected = {
        "_LIVE_STATUSES": {"buy", "near"},
        "_SETTING_UP_STATUSES": {"wait"},
        "_RAN_STATUSES": {"hold"},
        "_BLOCKED_STATUSES": {"avoid"},
    }
    for name, verbs in expected.items():
        values = bucket(name)
        missing = sorted(v for v in values if v not in STANCE_BY_STATUS)
        assert not missing, f"{name} gained unmapped status(es): {missing}"
        got = {STANCE_BY_STATUS[v] for v in values}
        assert got <= verbs, f"{name} projects to {sorted(got)}, expected within {sorted(verbs)}"
    assert "trim" not in set(STANCE_BY_STATUS.values()), "no sixth TRIM verb on the Board"
    print("stance projection tracks engine buckets: OK (12 statuses, 5 verbs, no TRIM)")


def main():
    assert_projection_tracks_engine()
    idx = git_json("site/prophet/index.json")
    su = git_json("site/factordata/us_standouts.json")

    plans = idx["plans"]
    buy = {r["ticker"]: r for r in su.get("buy", [])}

    # ── episodes: per ticker, ordinal by opening date ──────────────────────────
    by_ticker = collections.defaultdict(list)
    for r in plans:
        by_ticker[r["asset"]].append(r)

    def opened(r):
        return (r.get("entry_date") or r.get("recorded_at") or r.get("signal_date") or "")

    episode_of = {}
    multi_tickers = set()
    for tk, rows in by_ticker.items():
        if len(rows) < 2:
            continue
        multi_tickers.add(tk)
        for i, r in enumerate(sorted(rows, key=lambda x: (opened(x), x["id"])), start=1):
            episode_of[r["id"]] = i

    # newest OPEN row per multi ticker -> the "newer plan on this name" link target
    newest_open = {}
    for tk in multi_tickers:
        opens = [r for r in by_ticker[tk] if r.get("closed") is not True]
        if opens:
            newest_open[tk] = max(opens, key=lambda x: (opened(x), x["id"]))["id"]

    rows_out = []
    for r in plans:
        tk = r["asset"]
        b = buy.get(tk)
        lane = b.get("lane") if b else None
        if lane not in ("bottoming", "continuation"):
            lane = None  # no recovery chip, no watch chip: mark chip is bottoming/continuation only
        life = lifecycle_state(r)
        tgts = r.get("targets") or []
        rows_out.append({
            "id": r["id"],
            "tk": tk,
            "nm": (b or {}).get("name"),
            "sec": (b or {}).get("sector"),
            "life": life,
            "dir": r.get("direction"),
            "entry": r.get("entry"),
            "inval": r.get("invalidation"),
            "t1": tgts[0] if tgts else None,
            "px": (b or {}).get("price"),
            "lane": lane,
            "verb": (b or {}).get("state") or None,
            "age": r.get("age_days"),
            "hz": r.get("horizon_days"),
            # the engine's own readiness rank — the board's global sort key.
            # Higher priority = more ready today, NOT more likely to win (§G0.7).
            "pri": r.get("_priority_score"),
            "opened": fmt_date(r.get("entry_date") or r.get("recorded_at")),
            "pulse": r.get("pulse"),
            "pulse_zh": r.get("pulse_zh"),
            "do": short_en(r),
            "do_zh": short_zh(r),
            "ep": episode_of.get(r["id"]),
            "eps": len(by_ticker[tk]) if tk in multi_tickers else None,
            "newer": newest_open.get(tk) if (r.get("closed") is True and tk in newest_open) else None,
            "adm": r.get("admission_class"),
            # ── the enriched half of the card contract ────────────────────────
            # spark/price/name/sector/lane all arrive through the candidate join
            # and are therefore PARTIAL today (~25%). They are carried anyway:
            # the target UX is the chart-first card, and the coverage gap is an
            # implementation dependency to solve (DESIGN_NOTES §6 Q1), not a
            # reason to design the flagship card down to the lowest common field.
            # The spark_svg already carries its own relevant-zone band and paints
            # in var(--up), so it flips correctly under zh for free.
            "spark": (b or {}).get("spark_svg"),
            "stance": stance(r, life),
            # Zone — the glance-tier price area. Real on 61 rows; the rest carry a
            # state so the footer can say WHY there is no zone rather than blank.
            "zlo": (r.get("entry_zone") or {}).get("low"),
            "zhi": (r.get("entry_zone") or {}).get("high"),
            "zstate": ((r.get("entry_zone_state") or {}).get("state")
                       if isinstance(r.get("entry_zone_state"), dict) else None),
            "zclass": (r.get("entry_zone") or {}).get("zone_class"),
            # marks, restrained: star (join) · new (100%, age<=1) · lane (join)
            "star": bool(((b or {}).get("coiled") or {}).get("star")),
            "new": bool(r.get("age_days") is not None and r.get("age_days") <= 1),
            # ⚡ trigger chip — kept high-signal: only a RECENT trigger, or one
            # about to fire. Not on all 96 entered rows (that is chip spam).
            "trg": ("triggered" if (life == "entered" and (r.get("age_days") or 99) <= 3)
                    else "imminent" if (life == "ready" and r.get("entry_status") == "buy_now")
                    else None),
        })

    counts = collections.Counter(r["life"] for r in rows_out)
    watch_present = "early_turn_watch" in (idx.get("intake") or {})
    watch_n = len((idx.get("intake") or {}).get("early_turn_watch") or []) if watch_present else None

    live_total = sum(counts.get(c, 0) for c in LIVE_CELLS)
    grand_total = sum(counts.values())

    # ── invariant check (ruling §6) ────────────────────────────────────────────
    assert live_total == idx["open_count"], (live_total, idx["open_count"])
    assert grand_total == idx["active_count"], (grand_total, idx["active_count"])

    # ── Candidates: buy rows grouped by shipped triage buckets ─────────────────
    TRIAGE = ["live", "setting_up", "ran", "basing", "blocked"]
    cand_rows = []
    for r in su.get("buy", []):
        cand_rows.append({
            "tk": r["ticker"], "nm": r.get("name"), "sec": r.get("sector"),
            "triage": r.get("stage"), "px": r.get("price"),
            "label": clip(r.get("label"), 110), "label_zh": clip(r.get("label_zh"), 70),
        })
    cand_counts = collections.Counter(r["triage"] for r in cand_rows)
    assert sum(cand_counts.get(t, 0) for t in TRIAGE) == len(cand_rows)

    payload = {
        "asof": idx.get("asof"),
        "recorded_at": idx.get("recorded_at"),
        "cand_asof": su.get("as_of"),
        "counts": {c: counts.get(c, 0) for c in CELLS},
        "watch_key_present": watch_present,
        "watch_n": watch_n,
        "live_total": live_total,
        "grand_total": grand_total,
        "open_count": idx["open_count"],
        "active_count": idx["active_count"],
        "plan_count": idx["plan_count"],
        "rows": rows_out,
        "multi_tickers": sorted(multi_tickers),
        "cand_total": len(cand_rows),
        "cand_counts": {t: cand_counts.get(t, 0) for t in TRIAGE},
        "cand_rows": cand_rows,
        "groups": {
            "leaders": len(su.get("leaders") or []),
            "laggards": len(su.get("laggards") or []),
            "ran": len(su.get("ran") or []),
        },
    }

    out = (
        "/* GENERATED — real payload extract for the Prophet Board mockup.\n"
        "   Source: site/prophet/index.json (asof %s) + site/factordata/us_standouts.json (as_of %s)\n"
        "   on origin/main. lifecycle_state derived per PROPHET_RULING_J9C_J10 §6 (mockup-side only;\n"
        "   production reads the published lifecycle_state / lifecycle_counts from PR-0(c)).\n"
        "   Regenerate: python3 tools/gen_fixture.py  */\n"
        "window.BOARD = %s;\n" % (payload["asof"], payload["cand_asof"],
                                  json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    )
    import sys
    dest = sys.argv[1]
    with open(dest, "w") as f:
        f.write(out)

    print("cells:", payload["counts"])
    print("live_total", live_total, "== open_count", idx["open_count"], "OK")
    print("grand_total", grand_total, "== active_count", idx["active_count"], "OK")
    print("watch key present:", watch_present)
    print("multi-episode tickers:", len(multi_tickers), sorted(multi_tickers))
    print("candidates:", len(cand_rows), payload["cand_counts"])
    print("lane join: %d of %d rows (%.0f%%)" % (
        sum(1 for r in rows_out if r["lane"]), len(rows_out),
        100.0 * sum(1 for r in rows_out if r["lane"]) / len(rows_out)))
    print("wrote", dest, "%.1f KB" % (len(out) / 1024.0))


if __name__ == "__main__":
    main()
