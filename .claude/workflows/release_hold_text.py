#!/usr/bin/env python3
"""Release a Sol-era hold on a Market Ontology PR so the merge-on-green sweeper will merge it.

Charter: research/MARKET_ONTOLOGY_META_CEO_CHARTER_2026_09_06.md §4 (takeover) and §5 (Wave 0).
Chairman override 2026-09-05 PDT: agentos/decisions/DEC-CHAIRMAN-OVERRIDE-CLAUDE-META-CEO-REGIME-2026-09-06.md.

Why a script: ``scripts/merge_on_green.py`` refuses to merge any PR whose title, body or
comments carry a hold marker at line start (``HOLD-FOR-*``, ``HELD FOR *``, ``HOLD —``,
``DO NOT MERGE``), and a comment-carried hold is cleared only by a later comment that
starts with ``HOLD-RELEASED``. Editing the title alone leaves the body/comment hold in
force, so a subagent doing this by hand burns its tool budget and still gets refused.
This script uses the sweeper's OWN ``recorded_hold`` to verify the result.

Usage (one call from the ship stage):
    python3 .claude/workflows/release_hold_text.py <pr-number> [--repo owner/name] [--ceo A|B] [--dry-run]

Effects (all idempotent):
  1. Title: strips a leading hold marker; verified with the sweeper's title scan.
  2. Body: every line the sweeper would classify as a hold is rewritten to
     ``Released 2026-.. (Chairman override; formerly: <line without markers>)`` and a
     release section is appended once. Prior text is preserved, never deleted.
  3. Comment: posts ONE ``HOLD-RELEASED — ...`` comment (only if none by this script exists).
  4. Ready + labels: ``gh pr ready``, remove ``merge-blocked``, add ``merge-on-green``.
  5. Re-fetches and asserts ``recorded_hold(body, comments, title)`` is falsy; exit 2 otherwise.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.environ.get("MO_REPO_ROOT") or os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import merge_on_green as mog  # noqa: E402  (the sweeper's own hold logic)

DEC_KEY = "DEC:CHAIRMAN-OVERRIDE-CLAUDE-META-CEO-REGIME-2026-09-06"
CHARTER = "research/MARKET_ONTOLOGY_META_CEO_CHARTER_2026_09_06.md"
RELEASE_SENTINEL = "Released under the Chairman override (Meta-CEO"
_MARKER_WORDS = re.compile(r"HOLD-FOR-[A-Z0-9_-]+|HELD[- ]FOR[- ][A-Z0-9_-]+|DO\s+NOT\s+MERGE|\bHOLD\b", re.IGNORECASE)


def _gh(*args: str, input_text: str | None = None) -> str:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, input=input_text)
    if proc.returncode != 0:
        raise SystemExit(f"gh {' '.join(args[:3])} failed rc={proc.returncode}: {proc.stderr.strip()[:400]}")
    return proc.stdout


def fetch(repo: str, pr: int) -> tuple[dict, list[dict]]:
    pull = json.loads(_gh("api", f"repos/{repo}/pulls/{pr}"))
    comments = json.loads(_gh("api", f"repos/{repo}/issues/{pr}/comments?per_page=100"))
    return pull, comments


def neutralize_title(title: str) -> str:
    """Remove hold markers anywhere in the title ("[HOLD]", "[DRAFT / HOLD-FOR-SOL]",
    "HOLD-FOR-SOL —", "[F10-X1] HOLD-FOR-SOL:", "HELD FOR SOL"), keep everything else."""
    t = re.sub(r"\[[^\]]*\bH[EO]LD\b[^\]]*\]", " ", title, flags=re.IGNORECASE)
    t = re.sub(r"(HOLD-FOR-[A-Z0-9_-]+|HELD[- ]FOR[- ][A-Z0-9_-]+)\s*[—:\-]*", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\bDO\s+NOT\s+MERGE\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s{2,}", " ", t).strip(" —:-")
    return t or title


def neutralize_body(body: str, today: str, ceo: str) -> str:
    out: list[str] = []
    changed = False
    for line in (body or "").splitlines():
        if mog._classify_comment(line) == None or mog._classify_comment(line)[0] != "hold":  # noqa: E711
            out.append(line)
            continue
        plain = _MARKER_WORDS.sub(lambda m: m.group(0).replace("-", " ").replace("HOLD", "hold").replace("hold", "hold"), line)
        plain = plain.replace("**", "").replace("#", "").strip(" -—:")
        out.append(f"Released {today} (Chairman override; formerly: {plain})")
        changed = True
    text = "\n".join(out)
    if RELEASE_SENTINEL not in text:
        text += (
            f"\n\n## {RELEASE_SENTINEL} {ceo}, {today})\n\n"
            f"The Sol-era hold on this pull request was released by Meta-CEO {ceo} under {DEC_KEY} "
            f"(charter `{CHARTER}`): opus review -> fixes -> Ready -> merge-on-green -> merge -> live proof. "
            f"Prior hold text above is preserved as history and no longer binds any merge path.\n"
        )
        changed = True
    return text if changed else body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pr", type=int)
    ap.add_argument("--repo", default="mastermindx-market-intelligence/macro")
    ap.add_argument("--ceo", default="A")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    today = _dt.date.today().isoformat()

    pull, comments = fetch(a.repo, a.pr)
    if pull.get("merged") or pull.get("state") != "open":
        print(json.dumps({"pr": a.pr, "state": pull.get("state"), "merged": pull.get("merged"), "action": "none"}))
        return 0
    before = mog.recorded_hold(pull.get("body") or "", comments, pull.get("title") or "")
    new_title = neutralize_title(pull.get("title") or "")
    new_body = neutralize_body(pull.get("body") or "", today, a.ceo)
    already_released = any(
        (c.get("body") or "").lstrip().upper().startswith("HOLD-RELEASED") and RELEASE_SENTINEL in (c.get("body") or "")
        for c in comments
    )
    plan = {
        "pr": a.pr, "held_before": before, "title_before": pull.get("title"), "title_after": new_title,
        "body_changed": new_body != (pull.get("body") or ""), "release_comment_exists": already_released,
        "draft_before": pull.get("draft"),
    }
    if a.dry_run:
        print(json.dumps(plan, indent=1))
        return 0

    if new_title != pull.get("title") or new_body != (pull.get("body") or ""):
        payload = json.dumps({"title": new_title, "body": new_body})
        _gh("api", "-X", "PATCH", f"repos/{a.repo}/pulls/{a.pr}", "--input", "-", input_text=payload)
    if not already_released:
        text = (
            f"HOLD-RELEASED — {RELEASE_SENTINEL} {a.ceo}, {today}). Releasing authority: {DEC_KEY} "
            f"(charter `{CHARTER}`). Path: opus review -> fixes -> Ready -> merge-on-green -> squash-merge -> live proof. "
            f"Every earlier hold comment on this pull request is superseded for the Market Ontology program."
        )
        _gh("pr", "comment", str(a.pr), "-R", a.repo, "--body", text)
    if pull.get("draft"):
        _gh("pr", "ready", str(a.pr), "-R", a.repo)
    labels = {l.get("name") for l in pull.get("labels") or []}
    if "merge-blocked" in labels:
        _gh("pr", "edit", str(a.pr), "-R", a.repo, "--remove-label", "merge-blocked")
    if "merge-on-green" not in labels:
        _gh("pr", "edit", str(a.pr), "-R", a.repo, "--add-label", "merge-on-green")

    pull2, comments2 = fetch(a.repo, a.pr)
    after = mog.recorded_hold(pull2.get("body") or "", comments2, pull2.get("title") or "")
    plan.update({"held_after": after, "draft_after": pull2.get("draft"), "labels_after": [l.get("name") for l in pull2.get("labels") or []]})
    print(json.dumps(plan, indent=1))
    if after:
        print(f"::error title=hold-still-recorded::PR #{a.pr} still records a hold: {after}", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
