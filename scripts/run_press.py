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

W1.5 EMIT ROUTING (config/press.yml `cutover`).  Each passing draft is routed by
its DESK's publication:

  cutover: false (today)   every desk keeps the path above, byte for byte.  The
                           property trees still get built by
                           scripts/build_press_properties.py, but nothing about
                           this lane's writes changes.
  cutover: true            a publication that carries `property_tree` takes its
                           own road: the .md goes to that publication's
                           content_dir (NOT content/seo/blog), the free-content
                           estate render is SKIPPED for it entirely, and its
                           property tree is re-rendered from the ledger.

Both branches now write `url` and `title` on the ledger row.  That is what makes
the cutover migration-free: a row states where IT was published, so pre-cutover
rows keep pointing at /blog/ forever and no historic row is ever rewritten.  The
ledger is append-only and every consumer reads it with .get(), so rows written
before this change (which carry neither field) stay readable.

DELTA VS W1 (declared, not incidental): the ledger row's `publication` now comes
from the DESK's config entry at emit time, not from the staged record's copy of
it.  W1 read `obj["publication"]`, which was written when the draft was STAGED —
so re-pointing a desk to another publication between staging and emit published
the piece under the new routing while recording the old name.  The staged value
remains the fallback for a desk that has since been deleted from config.

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

from engine.press import desk_planner, properties, validators, writer  # noqa: E402

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


def _emit_route(cfg: dict, root: Path, paths: dict, obj: dict, slug: str) -> dict:
    """Where this piece publishes, and under what URL.

    Returns {publication, routed, md_dir, url}.  `routed` is the ONLY switch in
    this file that the cutover flag moves, and it is deliberately conservative:
    a publication is routed only when cutover is true AND it carries all three
    of property_tree / content_dir / base_url.  A half-filled registry entry
    therefore keeps the existing estate path instead of writing a page at a URL
    it cannot name — and load_config already refuses that combination at
    cutover, so this is the second of two locks on the same door.

    The DESK's publication wins over the staged item's copy of it: the staged
    record was written by an earlier run and a desk can be re-pointed between
    staging and emit.
    """
    desks = (cfg.get("desks") or {}) if isinstance(cfg, dict) else {}
    desk_cfg = desks.get(str(obj.get("desk") or ""))
    desk_cfg = desk_cfg if isinstance(desk_cfg, dict) else {}
    pub_key = str(desk_cfg.get("publication") or obj.get("publication") or "")

    pubs = (cfg.get("publications") or {}) if isinstance(cfg, dict) else {}
    pub = pubs.get(pub_key)
    pub = pub if isinstance(pub, dict) else {}
    tree, content_dir = pub.get("property_tree"), pub.get("content_dir")
    base_url = str(pub.get("base_url") or "").rstrip("/")

    if cfg.get("cutover") is True and tree and content_dir and base_url:
        return {"publication": pub_key, "routed": True,
                "md_dir": root / str(content_dir),
                "url": f"{base_url}/articles/{slug}.html"}
    return {"publication": pub_key, "routed": False,
            "md_dir": paths["content"],
            "url": f"{_SITE_BASE}/blog/{slug}.html"}


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


def _source_revisions(obj: dict) -> dict[str, str]:
    """Revision receipts recorded on a slot, staged item, or ledger row."""

    raw = obj.get("source_revisions") if isinstance(obj, dict) else None
    if not isinstance(raw, dict):
        slot = obj.get("slot") if isinstance(obj, dict) else None
        raw = slot.get("source_revisions") if isinstance(slot, dict) else None
    out = {
        str(ref): str(receipt).lower()
        for ref, receipt in (raw or {}).items()
        if ref and receipt
    }
    if out:
        return out
    # Compatibility with the first revision-aware staged shape, which carried
    # the receipt only under primary_source before the top-level map existed.
    slot = obj.get("slot") if isinstance(obj, dict) else None
    slot = slot if isinstance(slot, dict) else obj
    primary = slot.get("primary_source") if isinstance(slot, dict) else None
    if isinstance(primary, dict) and primary.get("ref") and primary.get("receipt"):
        return {str(primary["ref"]): str(primary["receipt"]).lower()}
    return {}


def _read_ledger_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        log.warning("press revision reconciliation: cannot read %s: %s", path, exc)
        return rows
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception as exc:  # noqa: BLE001
            log.warning("press revision reconciliation: invalid ledger row: %s", exc)
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _mark_revision_state(path: Path, obj: dict, *, status: str, reason: str,
                         details: dict) -> bool:
    """Persist one terminal/non-emittable revision state exactly once."""

    if obj.get("status") == status and obj.get("revision_state") == details:
        return False
    obj["status"] = status
    obj["revision_state"] = details
    obj["quarantine_reason"] = reason
    obj[f"{status}_at"] = _now()
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return True


def reconcile_earnings_call_revisions(root: Path, cfg: dict) -> dict:
    """Reconcile mutable transcript revisions with immutable Press state.

    Pending stale drafts are retained but made non-emittable.  Once a prior
    revision has been published, a changed (or unverifiable legacy) revision is
    represented by an explicit ``correction_required`` staging record; it is
    never converted into a normal passing draft automatically.
    """

    paths = _paths(cfg, root)
    paths["staging"].mkdir(parents=True, exist_ok=True)
    current = desk_planner.earnings_call_revisions(root)

    published: dict[str, dict] = {}
    for row in _read_ledger_rows(paths["ledger"]):
        revisions = _source_revisions(row)
        for ref in row.get("sources") or []:
            ref = str(ref)
            if ref in current:
                # Append-only ledger order: the last row is the latest explicit
                # publication state for this stable story ref.
                published[ref] = {
                    "row": row,
                    "receipt": revisions.get(ref, ""),
                }

    mismatches: dict[str, dict] = {}
    for ref, state in current.items():
        prior = published.get(ref)
        if prior is None:
            continue
        current_receipt = str(state.get("receipt") or "")
        published_receipt = str(prior.get("receipt") or "")
        if not state.get("valid") or current_receipt != published_receipt:
            mismatches[ref] = {
                "current": state,
                "published": prior,
            }

    stage_rows: list[tuple[Path, dict]] = []
    for path in sorted(paths["staging"].glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("press revision reconciliation: unreadable %s: %s", path, exc)
            continue
        if isinstance(obj, dict):
            stage_rows.append((path, obj))

    superseded = 0
    resolved = 0
    for path, obj in stage_rows:
        revisions = _source_revisions(obj)
        tracked_refs = [ref for ref in revisions if ref in current]
        missing_refs = [ref for ref in revisions if ref not in current]

        if obj.get("status") == "correction_required":
            active = [
                ref for ref in tracked_refs
                if ref in mismatches
                and revisions.get(ref) == str(current[ref].get("receipt") or "")
            ]
            if active:
                continue
            details = {
                "state": "published_revision_now_current"
                if tracked_refs and not any(ref in mismatches for ref in tracked_refs)
                else "correction_record_superseded",
                "recorded": revisions,
                "current": {
                    ref: str(current[ref].get("receipt") or "") for ref in tracked_refs
                },
            }
            if _mark_revision_state(
                path, obj, status="resolved", reason=details["state"], details=details,
            ):
                resolved += 1
            continue

        stale_refs = [
            ref for ref in tracked_refs
            if not current[ref].get("valid")
            or revisions.get(ref) != str(current[ref].get("receipt") or "")
        ]
        published_changed = [ref for ref in tracked_refs if ref in mismatches]
        if missing_refs or stale_refs or published_changed:
            reason = (
                "published_revision_changed_requires_correction"
                if published_changed else "source_revision_changed"
            )
            details = {
                "state": reason,
                "recorded": revisions,
                "current": {
                    ref: str(current[ref].get("receipt") or "") for ref in tracked_refs
                },
                "missing_current_refs": missing_refs,
            }
            if _mark_revision_state(
                path, obj, status="superseded", reason=reason, details=details,
            ):
                superseded += 1

    correction_required = 0
    # Re-read the small staging set conceptually through stage_rows plus any
    # state changes above.  A matching correction record is idempotent and
    # prevents one file per run.
    existing_corrections: set[tuple[str, str]] = set()
    for _path, obj in stage_rows:
        if obj.get("status") != "correction_required":
            continue
        for ref, receipt in _source_revisions(obj).items():
            existing_corrections.add((ref, receipt))

    for ref, mismatch in sorted(mismatches.items()):
        state = mismatch["current"]
        receipt = str(state.get("receipt") or "")
        if (ref, receipt) in existing_corrections:
            continue
        prior = mismatch["published"]
        row = prior["row"]
        correction_id = (
            "press-correction-"
            + desk_planner.story_key(ref, receipt or "unverifiable")
        )
        correction = {
            "id": correction_id,
            "desk": row.get("desk") or "brief",
            "publication": row.get("publication") or "mastermind_news",
            "as_of": state.get("date") or date.today().isoformat(),
            "staged_at": _now(),
            "status": "correction_required",
            "correction_reason": (
                "published_source_revision_changed"
                if receipt else "current_source_revision_unverifiable"
            ),
            "sources": [ref],
            "source_revisions": {ref: receipt},
            "seed_refs": [],
            "slug": "",
            "draft": None,
            "validator_report": None,
            "attempts": [],
            "correction": {
                "state": "requires_editorial_correction",
                "auto_emit_allowed": False,
                "source_ref": ref,
                "published": {
                    "id": row.get("id"),
                    "receipt": prior.get("receipt") or None,
                    "url": row.get("url"),
                    "ts": row.get("ts"),
                },
                "current": state,
            },
        }
        (paths["staging"] / f"{correction_id}.json").write_text(
            json.dumps(correction, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        correction_required += 1

    return {
        "current_sources": len(current),
        "superseded": superseded,
        "resolved": resolved,
        "correction_required": correction_required,
        "published_mismatches": len(mismatches),
    }


def run_staging(root: Path, cfg: dict, *, desks=None, as_of=None,
                max_slots: int | None = None) -> dict:
    paths = _paths(cfg, root)
    paths["staging"].mkdir(parents=True, exist_ok=True)

    run_date = as_of or date.today().isoformat()
    revision_reconciliation = reconcile_earnings_call_revisions(root, cfg)
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
               "passed": 0, "quarantined": 0, "items": [],
               "revision_reconciliation": revision_reconciliation}

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
        "source_revisions": dict(slot.get("source_revisions") or {}),
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

    # Re-check the exact Chronicle receipt at the last safe boundary.  A call
    # can be corrected after staging; no previously-passing draft is allowed to
    # cross that race as stale copy.
    revision_reconciliation = reconcile_earnings_call_revisions(root, cfg)

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
        return {"emitted": 0, "items": [],
                "revision_reconciliation": revision_reconciliation}

    paths["content"].mkdir(parents=True, exist_ok=True)
    written: list[dict] = []
    for path, obj in items:
        slot = obj.get("slot") or {}
        draft = obj["draft"]
        route = _emit_route(cfg, root, paths, obj, draft["slug"])
        md_path = route["md_dir"] / f"{draft['slug']}.md"
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
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_frontmatter_md(draft, slot, cfg), encoding="utf-8")
        written.append({"staging_path": path, "obj": obj, "md_path": md_path,
                        "route": route})

    if not written:
        return {"emitted": 0, "items": []}

    # The rows are built BEFORE the render so a routed publication's property can
    # be re-rendered WITH the piece it is publishing in this same pass. They are
    # appended only after everything succeeds, so a failed render still leaves
    # the ledger untouched.
    ledger_rows = []
    for w in written:
        obj, draft, route = w["obj"], w["obj"]["draft"], w["route"]
        ledger_rows.append({
            "id": obj["id"],
            "ts": _now(),
            "desk": obj.get("desk"),
            "publication": route["publication"] or obj.get("publication"),
            "slug": draft["slug"],
            # W1.5 additive fields. `url` is what makes the cutover
            # migration-free: the row states where IT was published, so no
            # historic row ever needs rewriting. `title` lets a consumer list
            # the archive without opening every .md.
            "title": str(draft.get("title") or ""),
            "url": route["url"],
            "sources": list(obj.get("sources") or []),
            "source_revisions": dict(_source_revisions(obj)),
            "seed_refs": list(obj.get("seed_refs") or []),
            "validator_report": obj.get("validator_report"),
            "urls": [route["url"]],
        })

    # ── ATOMIC FROM HERE ─────────────────────────────────────────────────────
    # The .md files are already on disk and the render is about to rewrite
    # site/blog/ (and, post-cutover, the property trees). If anything below
    # raises, the tree must go back to exactly what it was: a run that leaves
    # .md files with no matching rendered pages is the render-clobber class —
    # `build_free_content --check` reports the missing pages and the NEXT PR
    # inherits a red estate it did not cause.
    site_snapshot = {p: p.read_bytes()
                     for p in (root / "site" / "blog").rglob("*") if p.is_file()}
    routed_pubs: list[str] = []
    for w in written:
        key = w["route"]["publication"]
        if w["route"]["routed"] and key not in routed_pubs:
            routed_pubs.append(key)
    tree_snapshots: dict[Path, dict] = {}
    for key in routed_pubs:
        tree = properties.property_tree_path(root, cfg, key)
        tree_snapshots[tree] = {p: p.read_bytes()
                                for p in tree.rglob("*") if p.is_file()} \
            if tree.exists() else {}

    try:
        # A routed piece never touches the free-content estate, so an emit whose
        # every piece is routed skips that render entirely. Pre-cutover nothing
        # is routed and this is the existing call, unchanged.
        if any(not w["route"]["routed"] for w in written):
            copied, unowned = _render_blog_subtree(root)
            if unowned:
                _annotate("warning", "press_emit_unowned_asset",
                          "press emit produced asset(s) outside the workflow's git-add "
                          "scope: " + ", ".join(unowned)
                          + " — commit them or the estate drift check will go red.")
        else:
            copied = []

        for key in routed_pubs:
            pending = [row for row, w in zip(ledger_rows, written)
                       if w["route"]["routed"] and w["route"]["publication"] == key]
            properties.render_property(root, cfg, key, extra_rows=pending)

        # The nightly owns the sitemap.  Assert it, do not assume it.
        sitemap_after = sitemap.read_bytes() if sitemap.exists() else None
        if sitemap_after != sitemap_before:
            raise RuntimeError("press emit modified site/sitemap.xml — the nightly owns it")
    except BaseException:
        _rollback_emit(root, written, site_snapshot, tree_snapshots)
        _annotate("error", "press_emit_rollback",
                  "press emit failed after writing content — rolled the tree back "
                  "to its pre-emit state (no .md without a rendered page).")
        raise

    try:
        append_ledger(paths["ledger"], ledger_rows)
    except BaseException:
        _rollback_emit(root, written, site_snapshot, tree_snapshots)
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

    routed_note = (f"; properties re-rendered: {', '.join(routed_pubs)}"
                   if routed_pubs else "")
    _annotate("notice", "press_emit",
              f"press emit: {len(ledger_rows)} article(s) published; "
              f"{len(copied)} file(s) written under site/blog/{routed_note}")
    return {"emitted": len(ledger_rows), "items": ledger_rows, "site_files": copied,
            "properties": routed_pubs,
            "revision_reconciliation": revision_reconciliation}


def _restore_tree(base: Path, snapshot: dict) -> None:
    """Restore one rendered tree to `snapshot`, removing anything it gained.

    Best-effort per path: one unwritable file must not stop the rest of the
    rollback.  Empty directories are left behind on purpose — they hold no
    content, and pruning them is how a rollback grows a second failure mode.
    """
    if not base.exists():
        return
    for path in list(base.rglob("*")):
        if not path.is_file():
            continue
        try:
            if path in snapshot:
                if path.read_bytes() != snapshot[path]:
                    path.write_bytes(snapshot[path])
            else:
                path.unlink()                # added by the failed render
        except OSError as exc:  # noqa: PERF203
            log.warning("press rollback: could not restore %s: %s", path, exc)


def _rollback_emit(root: Path, written: list[dict], site_snapshot: dict,
                   tree_snapshots: dict | None = None) -> None:
    """Put the tree back exactly as the emit found it.

    Deletes every .md this run created — which after cutover means the routed
    publication's content_dir as well as content/seo/blog, because `md_path` is
    the ROUTED path — and restores every site/blog file and every property-tree
    file that existed before it, removing any the render added.
    """
    for w in written:
        try:
            w["md_path"].unlink(missing_ok=True)
        except OSError as exc:  # noqa: PERF203
            log.warning("press rollback: could not remove %s: %s", w["md_path"], exc)
    _restore_tree(root / "site" / "blog", site_snapshot)
    for tree, snapshot in (tree_snapshots or {}).items():
        _restore_tree(tree, snapshot)


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
