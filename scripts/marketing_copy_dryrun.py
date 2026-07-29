#!/usr/bin/env python3
"""scripts/marketing_copy_dryrun.py — see the new writer's copy before it ships.

Program: ``research/MARKETING_CONTENT_STUDIO_LLM_FIRST_MASTERPLAN_BY_FABLE.md``
§0 gate 8 ("live proof in the PR: dry-run against the real current plan with a
real key, >=5 model-written posts pasted in the PR body next to the template
posts they replace"). Interface pinned by
``research/marketing_dockets/CONTENT_STUDIO_W1_BUILD_CONTRACT.md`` §Dry-run.

WHAT IT DOES
------------
Reads the CURRENT nightly plan (``data/marketing/content_plan.json``), rebuilds
a writer context for each planned item, runs ``write_posts_llm_v2`` on the first
N of them, and prints the old template post next to the new model post with its
mode, critic verdict and any violations. Then a fallback-rate summary.

WHAT IT DOES NOT DO, AND THE ONE THING IT DOES
----------------------------------------------
**It never touches the outbox and never touches a marketing ledger.** No item is
queued, no status is transitioned, no plan is re-rendered, no file under
``data/marketing/`` is written or read for writing. That is the whole reason it
is safe to point at production data with a live key: nothing it does can reach a
reader.

**It DOES spend model credit, and credit spent is credit accounted for.** Each
post is a real ``llm_auth`` call, so the usual usage accounting happens: the
OAuth-pool bookkeeping and the ``ai_costs`` usage rows every model lane in this
repo writes. That is the accounting working correctly, not a side effect to
suppress — an un-ledgered live call is the actual defect. Budget for roughly two
model calls per item (writer, critic) plus one more per repair round.

SCAFFOLDING IS USUALLY ABSENT, AND THAT IS FINE
-----------------------------------------------
``content_plan.json`` is written with ``strip_scaffolding`` applied, so a queue
item on disk has no ``_plan``, no ``_receipt`` and no fact packet — only the
rendered headline/body plus ticker/type/account/slot. So this script REBUILDS
the packet from the same sources the nightly uses: ``chart_facts`` for a ticker
(needs the OHLCV store, which the minimal CI env does not have — that path
degrades to no facts rather than failing), ``market_facts`` for the non-ticker
kinds (pure stdlib + json, works anywhere).

Shape and angle are assigned here by a deterministic rotation. The real mixer
lives in ``content_studio`` and is Builder B's; this script only needs SOME
assignment to exercise every shape, and importing the mixer would couple a
diagnostic tool to a module it has no business depending on.

Usage
-----
    python3 scripts/marketing_copy_dryrun.py --limit 10
    python3 scripts/marketing_copy_dryrun.py --limit 5 --kind signal --kind chart

Exits 0 on every RUN path, including a mute provider lane: this is a diagnostic,
and a red exit code on "no credential in this shell" teaches nothing. The one
non-zero exit is 2, for a ``--shape`` that is not a shape, because that is an
operator typo and running 10 items against it teaches nothing either.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in (p.parent.parent, p.parent, *p.parents):
        if (candidate / "engine").is_dir() and (candidate / "scripts").is_dir():
            return candidate
    return p.parent.parent


ROOT = _repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: The kinds this wave rebuilds (contract §Emit). Movers/theme lists keep their
#: publish-time lane and are not this writer's business.
PLANNED_KINDS: tuple[str, ...] = (
    "signal", "chart", "education", "macro", "receipt", "watchlist", "event",
    # E2 filing lanes (2026-07-29) — planned kinds, same no-fallback law.
    "congress", "insider",
)

#: Contract §Context. Rotated deterministically so one run shows several.
ANGLES: tuple[str, ...] = (
    "level_watch", "risk_frame", "group_read", "precedent", "process",
    "receipt_frame", "macro_read", "event_read",
)


def _load_cfg() -> dict:
    """config/marketing.yml as a dict, or {}. Never raises."""
    try:
        import yaml  # noqa: PLC0415
        path = ROOT / "config" / "marketing.yml"
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] could not read config/marketing.yml ({exc}); using defaults")
        return {}


def _facts_for(item: dict, *, root: Path, caches: dict) -> dict | None:
    """Rebuild the fact packet for one stripped plan item. None when there is none.

    Ticker items need the OHLCV store (pandas/pyarrow). A minimal environment
    simply has no chart facts, and the item is reported as unsupported rather
    than written with an empty whitelist — a post whose numbers cannot be
    licensed would be dropped by the validators anyway, and that drop would say
    nothing about the writer.
    """
    kind = str(item.get("type") or "")
    ticker = str(item.get("ticker") or "")

    if ticker:
        try:
            from engine.marketing.chart_facts import compute_facts  # noqa: PLC0415
            from engine.marketing.chart_render import load_ohlcv  # noqa: PLC0415
            ohlcv = load_ohlcv(ticker, str(root), n=90)
            if ohlcv is None:
                return None
            d, o, h, low, c, v = ohlcv
            return compute_facts(ticker, d, o, h, low, c, v)
        except Exception:  # noqa: BLE001 — no bar store here, no chart facts
            return None

    try:
        from engine.marketing import market_facts as mf  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    if "macro" not in caches:
        caches["macro"] = mf.macro_facts(root)
        caches["event"] = mf.event_facts(root)
        caches["watchlist"] = mf.merge_facts(
            mf.breadth_facts(root), mf.sector_facts(root))
    if kind in ("macro", "event"):
        return caches.get(kind)
    if kind == "watchlist":
        return caches.get("watchlist")
    return None  # education is conceptual: no market facts by design


def _pick_shape(index: int, item: dict, forced: str | None) -> str:
    """Deterministic rotation across the shapes, caption only with a chart."""
    from engine.marketing.copywriter import SHAPES  # noqa: PLC0415
    if forced:
        return forced
    non_caption = tuple(s for s in SHAPES if s != "caption")
    if item.get("chart_id") and index % len(SHAPES) == len(SHAPES) - 1:
        return "caption"
    return non_caption[index % len(non_caption)]


def _plan_items(plan: dict, kinds: tuple[str, ...]) -> list[dict]:
    """Every planned-kind queue item, in plan order, with its account attached."""
    out: list[dict] = []
    for acct in plan.get("accounts") or []:
        acct_id = str(acct.get("id") or "")
        for item in acct.get("queue") or []:
            if str(item.get("type") or "") not in kinds:
                continue
            row = dict(item)
            row.setdefault("account", acct_id)
            out.append(row)
    return out


def _old_text(item: dict) -> str:
    hl = str(item.get("headline") or "").strip()
    bd = str(item.get("body") or "").strip()
    return "\n\n".join(p for p in (hl, bd) if p)


def _build_contexts(
    items: list[dict], *, root: Path, cfg: dict, forced_shape: str | None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """-> (contexts, source_items, skipped). Skipped = no fact packet available."""
    from engine.marketing.copywriter import build_context  # noqa: PLC0415

    personas = ((cfg.get("copywriter") or {}).get("personas") or {})
    caches: dict[str, Any] = {}
    contexts: list[dict] = []
    kept: list[dict] = []
    skipped: list[dict] = []
    # Same-ticker copy already in the plan is exactly what the writer must
    # diverge from, so the dry run threads the REAL prior text as siblings.
    by_ticker: dict[str, list[str]] = {}
    for it in items:
        tk = str(it.get("ticker") or "")
        if tk:
            by_ticker.setdefault(tk, []).append(_old_text(it))

    for i, item in enumerate(items):
        facts = _facts_for(item, root=root, caches=caches)
        kind = str(item.get("type") or "")
        if facts is None and kind != "education":
            skipped.append(item)
            continue
        acct = str(item.get("account") or "")
        persona = personas.get(acct) or {}
        ctx = build_context(item, persona=persona or None, facts=facts or None)
        ctx["type"] = kind
        ctx["voice"] = "authoritative desk"
        ctx["slot"] = item.get("slot", "")
        ctx["as_of"] = str((item.get("scheduled_at") or ""))[:10] or None
        ctx["shape"] = _pick_shape(i, item, forced_shape)
        ctx["angle"] = ANGLES[i % len(ANGLES)]
        tk = str(item.get("ticker") or "")
        ctx["sibling_texts"] = [
            t for t in by_ticker.get(tk, []) if t and t != _old_text(item)
        ][:2]
        contexts.append(ctx)
        kept.append(item)
    return contexts, kept, skipped


def _print_result(n: int, item: dict, ctx: dict, post: dict) -> None:
    bar = "=" * 78
    print(f"\n{bar}")
    print(f"[{n}] {ctx.get('account')} | kind={ctx.get('type')} "
          f"| shape={ctx.get('shape')} | angle={ctx.get('angle')} "
          f"| slot={ctx.get('slot')} | ticker={ctx.get('ticker') or '-'}")
    print(f"{bar}")
    print("--- OLD (template) ---")
    print(_old_text(item) or "(none)")
    mode = str(post.get("mode") or "?")
    if mode == "dropped":
        print(f"--- NEW: DROPPED at stage '{post.get('stage')}' ---")
        for r in (post.get("reasons") or [])[:8]:
            print(f"    ! {r}")
        return
    print(f"--- NEW (mode={mode}) ---")
    print(post.get("text") or "")
    critic = post.get("critic") or {}
    print(f"    critic: {critic.get('verdict')} "
          f"{'| ' + '; '.join(critic.get('reasons') or []) if critic.get('reasons') else ''}")
    if post.get("violations"):
        for v in post["violations"][:6]:
            print(f"    ! {v}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=8,
                    help="how many plan items to rewrite (default 8)")
    ap.add_argument("--plan", default=str(ROOT / "data" / "marketing" / "content_plan.json"),
                    help="path to content_plan.json")
    ap.add_argument("--root", default=str(ROOT), help="repo root for fact sources")
    ap.add_argument("--kind", action="append", default=None,
                    help="restrict to these kinds (repeatable)")
    ap.add_argument("--shape", default=None,
                    help="force every item to one shape (default: rotate)")
    args = ap.parse_args(argv)

    if args.shape:
        # A typo used to be assigned to every context, where shape_violations
        # reported "unknown shape" on all N items and the run looked like a
        # writer failure. Fail here, once, with the list.
        from engine.marketing.copywriter import SHAPES  # noqa: PLC0415

        if args.shape not in SHAPES:
            print(f"[error] --shape {args.shape!r} is not a shape. "
                  f"Choose one of: {', '.join(SHAPES)}")
            return 2

    root = Path(args.root)
    plan_path = Path(args.plan)
    if not plan_path.exists():
        print(f"[skip] no plan at {plan_path} — nothing to dry-run.")
        return 0
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[skip] could not read {plan_path}: {exc}")
        return 0

    kinds = tuple(args.kind) if args.kind else PLANNED_KINDS
    cfg = _load_cfg()
    cw_cfg = (cfg.get("copywriter") or {})

    items = _plan_items(plan, kinds)
    print(f"plan: {plan_path}  as_of={plan.get('as_of')}  "
          f"planned-kind items={len(items)}  kinds={','.join(kinds)}")
    if not items:
        print("[skip] no planned-kind items in this plan.")
        return 0

    from engine.marketing import copy_critic  # noqa: PLC0415
    from engine.marketing import copywriter as cw  # noqa: PLC0415

    cw.reset_writer_stats()
    copy_critic.reset_critic_stats()

    # Build MORE contexts than requested, then take the first `limit` that had a
    # usable fact packet — otherwise a run against a bar-less environment shows
    # 8 skips and no copy.
    contexts, kept, skipped = _build_contexts(
        items[:args.limit * 6], root=root, cfg=cfg, forced_shape=args.shape)
    contexts, kept = contexts[:args.limit], kept[:args.limit]
    if skipped:
        print(f"[note] {len(skipped)} item(s) had no rebuildable fact packet "
              f"(no OHLCV store in this environment) and were passed over.")
    if not contexts:
        print("[skip] no item could be rebuilt into a writer context here.")
        return 0

    posts = cw.write_posts_llm_v2(contexts, cw_cfg)

    for i, (item, ctx, post) in enumerate(zip(kept, contexts, posts), 1):
        _print_result(i, item, ctx, post)

    stats = cw.writer_stats()
    critic = copy_critic.critic_stats()
    modes: dict[str, int] = {}
    for p in posts:
        modes[str(p.get("mode"))] = modes.get(str(p.get("mode")), 0) + 1
    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"  attempted     : {len(posts)}")
    print(f"  modes         : {json.dumps(modes, sort_keys=True)}")
    print(f"  repairs       : {stats.get('repairs', 0)}")
    print(f"  dropped       : {stats.get('dropped', 0)} "
          f"(provider={stats.get('dropped_provider', 0)}, "
          f"validate={stats.get('dropped_validate', 0)}, "
          f"critic={stats.get('dropped_critic', 0)})")
    print(f"  drop rate     : {stats.get('drop_rate', 0.0):.1%}")
    print(f"  critic        : {json.dumps(critic, sort_keys=True)}")
    lane_ran = stats.get("dropped_provider", 0) < len(posts)
    if lane_ran and stats.get("drop_rate", 0.0) > 0.30:
        # Masterplan §0 gate 5: a drop rate over 30% of a night's plan is a
        # signal about the lane, not about one post. Gated on the lane having
        # actually RUN: "no credential in this shell" drops 100% of items and
        # says nothing about copy quality, so annotating it would train the
        # reader to ignore the annotation. Bare print at line start with flush —
        # an annotation behind a logger is not a line start and GitHub drops it
        # silently.
        print("::warning title=marketing_copy_dryrun_droprate::Dry-run drop rate "
              f"is {stats.get('drop_rate', 0.0):.0%} of attempted posts (gate 5 "
              "raises a warning above 30%). Read the per-item reasons above: a "
              "high validate-stage rate is a prompt problem, a high critic-stage "
              "rate is a copy problem.", flush=True)
    print("\n(no outbox writes, no marketing-ledger writes, no plan rewritten; "
          "live model calls DO write the usual llm_auth usage/ai_costs rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
