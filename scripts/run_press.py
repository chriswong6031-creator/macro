"""scripts/run_press.py — Media Network W1 (docket D14) press orchestrator.

Two modes, and the default is the safe one:

    python -m scripts.run_press                 # --staging (default)
    python -m scripts.run_press --staging       # plan -> write -> validate
    python -m scripts.run_press --emit          # publish what already passed

--staging  Plans slots, writes drafts, runs the whole deterministic validator
           suite, and writes one JSON per slot (draft + validator_report +
           attempt history) to data/press/staging/.  It writes NOTHING under
           content/ or site/.  That is a tested invariant, not a convention:
           tests/test_press_run.py::test_staging_writes_nothing_outside_staging
           snapshots the tree and fails on any other write.

--emit     Takes the staged items whose status is `passed`, writes
           content/seo/blog/<slug>.md, renders the estate with the EXISTING
           free-content builder, copies the /blog/ subtree (pages + feed.xml)
           into site/, and appends one row per piece to
           data/press/published.jsonl.

           site/sitemap.xml is NEVER written here — the nightly owns it.
           Only site/blog/** is copied out of the render, so this lane cannot
           clobber the learn/tools/calculator pages the render lanes own.

QUARANTINE FLOW: fail -> regenerate (<= quarantine.max_regenerations) -> drop
the slot with a logged reason.  A thin day beats a padded one, so a dropped
slot is a normal outcome and exits 0.

The render replay is the non-obvious part of --emit.  The committed estate is
NOT the builder's raw output — the render lanes run idempotent sweeps over
site/ afterwards (externalize_css, optimize_assets), and
`build_free_content --check` replays those sweeps before comparing.  So an emit
that committed raw builder output would turn the estate drift check red on the
very next PR.  This replays the same sweeps, through the same helpers --check
uses, so what lands in site/blog/ is the post-sweep image --check expects.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.press import desk_planner, validators, writer  # noqa: E402

log = logging.getLogger("run_press")

_SITE_BASE = "https://www.mastermind-x.com"


# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────


def _paths(cfg: dict, root: Path) -> dict:
    p = (cfg.get("paths") or {}) if isinstance(cfg, dict) else {}
    return {
        "staging": root / str(p.get("staging_dir") or "data/press/staging"),
        "ledger": root / str(p.get("ledger") or "data/press/published.jsonl"),
        "content": root / str(p.get("content_dir") or "content/seo/blog"),
        "site_blog": root / "site" / "blog",
    }


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _env_int(name: str, default: int) -> int:
    """Env override for a config-supplied spend guard.

    Empty or unparsable falls back to the config value — a typo in a workflow
    variable must not silently uncap the budget.
    """
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        log.warning("press: %s=%r is not an integer — using config value %s",
                    name, raw, default)
        return default


def _annotate(level: str, title: str, message: str) -> None:
    """GitHub annotation.  Bare print, line-start, flushed — a logger would
    prefix the line and GitHub would silently drop it (house law)."""
    print(f"::{level} title={title}::{message}", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# Slug de-collision (runs BEFORE validation, never after)
# ─────────────────────────────────────────────────────────────────────────────


def _unique_slug(base: str, slot: dict, taken: set[str]) -> str:
    """A free slug for this draft.

    De-colliding AFTER validation would invalidate the frontmatter check that
    just passed, so it happens here, once, before anything is scored.  The
    suffix mirrors the research-vault idiom: a short stable hash of the story.
    """
    slug = desk_planner.slugify(base) or "market-note"
    if slug not in taken:
        return slug
    suffix = desk_planner.story_key(str(slot.get("id") or ""), slug)[:6]
    return f"{slug[:70 - len(suffix) - 1]}-{suffix}".strip("-")


# ─────────────────────────────────────────────────────────────────────────────
# STAGING
# ─────────────────────────────────────────────────────────────────────────────


def run_staging(root: Path, cfg: dict, *, desks=None, as_of=None,
                max_slots: int | None = None) -> dict:
    paths = _paths(cfg, root)
    paths["staging"].mkdir(parents=True, exist_ok=True)

    run_date = as_of or date.today().isoformat()
    slots = desk_planner.plan(desks, as_of=run_date, root=root, cfg=cfg)
    if max_slots is not None:
        slots = slots[:max_slots]

    llm_cfg = (cfg.get("llm") or {})
    state = writer.RunState(
        token_budget=_env_int("PRESS_RUN_TOKEN_BUDGET",
                              int(llm_cfg.get("run_token_budget") or 240_000)),
        breaker_threshold=_env_int("PRESS_CIRCUIT_BREAKER_FAILURES",
                                   int(llm_cfg.get("circuit_breaker_consecutive_failures") or 3)),
    )
    max_regen = int(((cfg.get("quarantine") or {}).get("max_regenerations")) or 2)

    pub_refs, pub_slugs = desk_planner.published_refs(root, cfg)
    stg_refs, stg_slugs = desk_planner.staged_refs(root, cfg)
    taken = desk_planner.taken_slugs(root) | pub_slugs | stg_slugs

    summary = {"run_at": _now(), "as_of": run_date, "planned": len(slots),
               "passed": 0, "quarantined": 0, "items": []}

    for slot in slots:
        attempts: list[dict] = []
        prior: list[str] = []
        passed_payload = None

        for attempt in range(max_regen + 1):
            res = writer.write(slot, cfg, state=state, attempt=attempt,
                               prior_failures=prior or None)
            if not res.get("ok"):
                attempts.append({"attempt": attempt, "ok": False,
                                 "reason": res.get("reason")})
                if res.get("reason") in ("circuit_open", "token_budget_exhausted",
                                         "no_provider", "llm_disabled"):
                    break                       # a run-level stop, not a draft problem
                prior = [f"writer: {res.get('reason')}"]
                continue

            draft = dict(res["draft"])
            draft["slug"] = _unique_slug(draft.get("slug") or slot.get("slug_hint") or "",
                                         slot, taken)
            report = validators.validate(draft, slot, cfg, root=root)
            attempts.append({"attempt": attempt, "ok": bool(report["ok"]),
                             "failed": report["failed"],
                             "our_value_share": report.get("our_value_share"),
                             "max_block_jaccard": report.get("max_block_jaccard"),
                             "provider": res.get("provider")})
            if report["ok"]:
                taken.add(draft["slug"])
                passed_payload = (draft, report, res)
                break
            prior = [f"{c['name']}: {c['detail']}" for c in report["checks"] if not c["ok"]]

        item = _stage_item(slot, passed_payload, attempts, run_date)
        out = paths["staging"] / f"{slot['id']}.json"
        out.write_text(json.dumps(item, ensure_ascii=False, indent=2, default=str) + "\n",
                       encoding="utf-8")
        summary["items"].append({"id": slot["id"], "desk": slot["desk"],
                                 "status": item["status"],
                                 "reason": item.get("quarantine_reason", "")})
        if item["status"] == "passed":
            summary["passed"] += 1
        else:
            summary["quarantined"] += 1
            log.warning("press: slot %s quarantined — %s", slot["id"],
                        item.get("quarantine_reason"))

    summary["writer_state"] = state.snapshot()
    (paths["staging"] / "_run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8")

    _annotate("notice", "press_staging",
              f"press staging: {summary['passed']} passed, "
              f"{summary['quarantined']} quarantined of {summary['planned']} planned "
              f"(tokens {state.tokens_used}/{state.token_budget})")
    if summary["planned"] and not summary["passed"]:
        _annotate("warning", "press_staging_empty",
                  "press staging produced NO passing draft — every planned slot was "
                  "quarantined or dropped. A thin day is legal; a permanently thin "
                  "lane is a defect. Check data/press/staging/ for reasons.")
    return summary


def _stage_item(slot: dict, passed_payload, attempts: list[dict], run_date: str) -> dict:
    """One staging record — the whole audit trail for a slot, pass or fail."""
    base = {
        "id": slot["id"],
        "desk": slot["desk"],
        "publication": slot.get("publication"),
        "as_of": slot.get("as_of") or run_date,
        "staged_at": _now(),
        "sources": list(slot.get("sources") or []),
        "seed_refs": list(slot.get("seed_refs") or []),
        "slot": slot,
        "attempts": attempts,
    }
    if passed_payload is None:
        # Explicit branches, not an `or` chain: `"validators: " + ""` is a
        # TRUTHY empty-list join, so the chained form could never reach its own
        # fallback and an attempt-less slot was quarantined with the reason
        # "validators: " — a blank explanation in the one field the operator
        # reads to find out why the day was thin.
        last = attempts[-1] if attempts else {}
        failed = last.get("failed") or []
        if last.get("reason"):
            reason = str(last["reason"])
        elif failed:
            reason = "validators: " + ", ".join(failed)
        else:
            reason = "no draft produced"
        base.update({"status": "quarantined", "slug": "", "draft": None,
                     "validator_report": None, "quarantine_reason": reason})
        return base
    draft, report, res = passed_payload
    base.update({
        "status": "passed",
        "slug": draft["slug"],
        "draft": draft,
        "validator_report": report,
        "provider": res.get("provider"),
        "model": res.get("model"),
    })
    return base


# ─────────────────────────────────────────────────────────────────────────────
# EMIT
# ─────────────────────────────────────────────────────────────────────────────


def _frontmatter_md(draft: dict, slot: dict, cfg: dict) -> str:
    """The .md file: frontmatter fence + the HTML body fragment.

    Frontmatter keys and their order follow the six hand-written posts in
    content/seo/blog/ so the estate reads as one corpus.
    """
    fm = validators.frontmatter_for(draft, slot, cfg)
    title = str(fm["title"]).replace('"', "'")
    desc = str(fm["description"]).replace('"', "'")
    lines = [
        "---",
        f"slug: {fm['slug']}",
        "family: article",
        f'title: "{title}"',
        f'description: "{desc}"',
        f"cluster: {fm['cluster']}",
        f"published: {fm['published']}",
        f"updated: {fm['updated']}",
        "---",
        draft["body_html"].strip(),
        "",
    ]
    return "\n".join(lines)


# daily.yml's alert-ticker tag. This lane cannot replay that sweep, so it
# carries the committed page's tag across instead of dropping it.
_WHB_TAG_RE = re.compile(rb"[ \t]*<script[^>]*\bdata-whb\b[^>]*></script>\n?")


def _carry_wh_banner(rendered: bytes, committed: Path) -> bytes:
    """Re-attach the committed page's wh_banner tag to a legitimately-changed page.

    `_same_page` stops us rewriting pages that only DIFFER by this tag, but a
    page that genuinely changed (blog/index.html gaining a card) still gets
    rendered without it, because only daily.yml injects it. `--check`
    normalises the tag away so it would never notice — and the page would ship
    without its alert ticker until the next nightly. One day of a regressed
    page is a day too many for a tag we can simply carry over.
    """
    if not committed.exists() or committed.suffix != ".html":
        return rendered
    if _WHB_TAG_RE.search(rendered):
        return rendered
    m = _WHB_TAG_RE.search(committed.read_bytes())
    if not m:
        return rendered
    tag = m.group(0)
    # Re-insert where the sweep puts it: immediately before </body>.
    idx = rendered.rfind(b"</body>")
    if idx == -1:
        return rendered
    return rendered[:idx] + tag + rendered[idx:]


def _same_page(rendered: Path, committed: Path) -> bool:
    """True when the committed file already IS this render, in the projection
    this lane is accountable for.

    HTML is compared through build_free_content._comparable, which strips the
    daily.yml-only wh_banner tag and normalises the `?v=` asset stamps — the two
    sweeps a press emit cannot replay and does not own.  Everything else (the
    RSS feed) is a plain byte compare.
    """
    if not committed.exists():
        return False
    a, b = rendered.read_bytes(), committed.read_bytes()
    if a == b:
        return True
    if rendered.suffix != ".html":
        return False
    from scripts.build_free_content import _comparable  # noqa: PLC0415
    try:
        return _comparable(a.decode("utf-8")) == _comparable(b.decode("utf-8"))
    except UnicodeDecodeError:
        return False


def _render_blog_subtree(root: Path) -> tuple[list[str], list[str]]:
    """Render the estate to a temp tree, replay the render-lane sweeps, and copy
    ONLY site/blog/** back.  Returns (copied_relpaths, unowned_new_assets).

    Reuses build_free_content's own sweep helpers so what lands in site/ is the
    exact post-image `--check` compares against.  tests/test_press_run.py pins
    these helper names: a rename upstream must fail loudly here, not quietly
    ship raw pages that turn the drift check red on someone else's PR.

    A page is only rewritten when it differs in the projection this lane is
    ACCOUNTABLE for — `_comparable()`, the same projection `--check` uses.  Two
    sweeps cannot be replayed here: daily.yml's wh_banner tag, and the `?v=`
    asset stamps whose hashes track files this lane does not own.  Copying on a
    raw byte diff would strip the banner from every already-committed article on
    the way past — six unrelated pages rewritten, and invisible to `--check`
    because it normalises exactly those two things away.
    """
    from scripts.build_free_content import (  # noqa: PLC0415
        _comparable, _normalize_like_render_lane, _seed_hashable_assets, render_all,
    )

    copied: list[str] = []
    unowned: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_site = Path(tmp) / "site"      # named "site" so lib.pages resolves depth
        tmp_site.mkdir(parents=True, exist_ok=True)
        render_all(tmp_site)
        _seed_hashable_assets(tmp_site)
        _normalize_like_render_lane(tmp_site)

        for src in sorted((tmp_site / "blog").rglob("*")):
            if not src.is_file():
                continue
            rel = src.relative_to(tmp_site)
            dst = root / "site" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if _same_page(src, dst):
                continue
            dst.write_bytes(_carry_wh_banner(src.read_bytes(), dst))
            copied.append(str(rel))

        # externalize_css lifts inline <style> into site/assets/css/<hash>.css.
        # Every estate article shares one stylesheet, so a press article should
        # never mint a new one — but if it does, the workflow's git-add scope
        # (content/seo/blog + site/blog + the ledger) would leave it behind and
        # `build_free_content --check` would go red with "MISSING in site/".
        # Say so loudly rather than discovering it in someone else's PR.
        for src in sorted((tmp_site / "assets" / "css").glob("*.css")):
            if not (root / "site" / "assets" / "css" / src.name).exists():
                unowned.append(f"site/assets/css/{src.name}")

    return copied, unowned


def run_emit(root: Path, cfg: dict) -> dict:
    paths = _paths(cfg, root)
    stage = paths["staging"]
    if not stage.exists():
        _annotate("notice", "press_emit", "press emit: no staging directory — nothing to do")
        return {"emitted": 0, "items": []}

    sitemap = root / "site" / "sitemap.xml"
    sitemap_before = sitemap.read_bytes() if sitemap.exists() else None

    items = []
    for path in sorted(stage.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("press emit: unreadable staging file %s: %s", path, exc)
            continue
        if isinstance(obj, dict) and obj.get("status") == "passed" and obj.get("draft"):
            items.append((path, obj))

    if not items:
        _annotate("notice", "press_emit",
                  "press emit: no passing staged drafts — nothing published")
        return {"emitted": 0, "items": []}

    paths["content"].mkdir(parents=True, exist_ok=True)
    written: list[dict] = []
    for path, obj in items:
        slot = obj.get("slot") or {}
        draft = obj["draft"]
        md_path = paths["content"] / f"{draft['slug']}.md"
        if md_path.exists():
            # The slug was free when it was staged and is not now — another lane
            # or an earlier emit took it.  Re-slugging here would bypass the
            # frontmatter check that passed against THIS slug, so quarantine it.
            obj["status"] = "quarantined"
            obj["quarantine_reason"] = f"slug collision at emit: {draft['slug']}.md exists"
            path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n",
                            encoding="utf-8")
            _annotate("warning", "press_emit_collision",
                      f"press emit: slug {draft['slug']} already exists — slot quarantined")
            continue
        md_path.write_text(_frontmatter_md(draft, slot, cfg), encoding="utf-8")
        written.append({"staging_path": path, "obj": obj, "md_path": md_path})

    if not written:
        return {"emitted": 0, "items": []}

    # ── ATOMIC FROM HERE ─────────────────────────────────────────────────────
    # The .md files are already on disk and the render is about to rewrite
    # site/blog/. If anything below raises, the tree must go back to exactly
    # what it was: a run that leaves .md files with no matching site/ pages is
    # the render-clobber class — `build_free_content --check` reports the
    # missing pages and the NEXT PR inherits a red estate it did not cause.
    site_snapshot = {p: p.read_bytes()
                     for p in (root / "site" / "blog").rglob("*") if p.is_file()}
    try:
        copied, unowned = _render_blog_subtree(root)
        if unowned:
            _annotate("warning", "press_emit_unowned_asset",
                      "press emit produced asset(s) outside the workflow's git-add "
                      "scope: " + ", ".join(unowned)
                      + " — commit them or the estate drift check will go red.")

        # The nightly owns the sitemap.  Assert it, do not assume it.
        sitemap_after = sitemap.read_bytes() if sitemap.exists() else None
        if sitemap_after != sitemap_before:
            raise RuntimeError("press emit modified site/sitemap.xml — the nightly owns it")
    except BaseException:
        _rollback_emit(root, written, site_snapshot)
        _annotate("error", "press_emit_rollback",
                  "press emit failed after writing content — rolled the tree back "
                  "to its pre-emit state (no .md without a rendered page).")
        raise

    ledger_rows = []
    for w in written:
        obj, draft = w["obj"], w["obj"]["draft"]
        row = {
            "id": obj["id"],
            "ts": _now(),
            "desk": obj.get("desk"),
            "publication": obj.get("publication"),
            "slug": draft["slug"],
            "sources": list(obj.get("sources") or []),
            "seed_refs": list(obj.get("seed_refs") or []),
            "validator_report": obj.get("validator_report"),
            "urls": [f"{_SITE_BASE}/blog/{draft['slug']}.html"],
        }
        ledger_rows.append(row)
    try:
        append_ledger(paths["ledger"], ledger_rows)
    except BaseException:
        _rollback_emit(root, written, site_snapshot)
        _annotate("error", "press_emit_rollback",
                  "press ledger append failed — rolled the tree back. Published "
                  "content with no ledger row is an unrecorded publication.")
        raise

    # Staged items that are now in the ledger are consumed.  Quarantined items
    # deliberately stay put — the admin panel is where the operator reads them.
    for w in written:
        try:
            w["staging_path"].unlink()
        except OSError:
            pass

    _annotate("notice", "press_emit",
              f"press emit: {len(ledger_rows)} article(s) published; "
              f"{len(copied)} file(s) written under site/blog/")
    return {"emitted": len(ledger_rows), "items": ledger_rows, "site_files": copied}


def _rollback_emit(root: Path, written: list[dict], site_snapshot: dict) -> None:
    """Put the tree back exactly as the emit found it.

    Deletes every .md this run created and restores every site/blog file that
    existed before it (removing any the render added).  Best-effort per path:
    one unwritable file must not stop the rest of the rollback.
    """
    for w in written:
        try:
            w["md_path"].unlink(missing_ok=True)
        except OSError as exc:  # noqa: PERF203
            log.warning("press rollback: could not remove %s: %s", w["md_path"], exc)
    blog = root / "site" / "blog"
    if not blog.exists():
        return
    for path in list(blog.rglob("*")):
        if not path.is_file():
            continue
        try:
            if path in site_snapshot:
                if path.read_bytes() != site_snapshot[path]:
                    path.write_bytes(site_snapshot[path])
            else:
                path.unlink()                # added by the failed render
        except OSError as exc:  # noqa: PERF203
            log.warning("press rollback: could not restore %s: %s", path, exc)


def append_ledger(path: Path, rows: list[dict]) -> int:
    """Append-only.  The press --emit path is the SOLE writer of this file."""
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    return len(rows)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Media Network W1 press orchestrator.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--staging", action="store_true",
                      help="plan + write + validate into data/press/staging/ (default)")
    mode.add_argument("--emit", action="store_true",
                      help="publish PASSING staged drafts to content/seo/blog + site/blog")
    ap.add_argument("--desks", default="",
                    help="comma-separated desk names (default: every desk in config)")
    ap.add_argument("--as-of", default="", help="run date YYYY-MM-DD (default: today)")
    ap.add_argument("--root", default="", help="repo root override (tests)")
    ap.add_argument("--max-slots", type=int, default=None,
                    help="cap the number of slots this run attempts")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    root = Path(args.root).resolve() if args.root else _REPO
    cfg = desk_planner.load_config(root)
    if not cfg:
        _annotate("error", "press_config",
                  "config/press.yml is missing or unparsable — press lane cannot run")
        return 1

    desks = [d.strip() for d in args.desks.split(",") if d.strip()] or None

    if args.emit:
        out = run_emit(root, cfg)
    else:
        out = run_staging(root, cfg, desks=desks,
                          as_of=(args.as_of or None), max_slots=args.max_slots)

    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
