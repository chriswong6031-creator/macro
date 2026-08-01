"""engine.marketing.indexnow — IndexNow submission adapter (D12 MKT-SEO-06).

Actively tells the IndexNow consortium (Bing, Yandex, Seznam, Naver) which of our
URLs are new, changed, or gone.  Google does not consume IndexNow, but Bing does —
and after the 2026-07-23 DNS outage deindexed www.mastermind-x.com everywhere, a
passive sitemap is a request to be re-crawled *eventually*.  This is the active push.

Protocol (https://www.indexnow.org/documentation):
  POST https://api.indexnow.org/indexnow
  {"host": ..., "key": ..., "keyLocation": ..., "urlList": [...]}
  The key is PUBLIC BY DESIGN — ownership is proven by serving the same string at
  ``keyLocation``.  There is no secret here and none is needed in the workflow.

Docket acceptance (D12 MKT-SEO-06): "IndexNow cannot bulk-submit unchanged
inventory."  So the submission set is a genuine diff against a committed state
file, not the sitemap.  ``--full`` is the explicit, deliberate override for a
recovery push like the post-outage reindex.

State: ``data/marketing/seo/indexnow_state.json``
  {"as_of": "<iso-utc>", "submitted": {"<url>": "<sha1 of the served bytes>"}}

The state is advanced ONLY after the endpoint accepts the batch.  A failed
submission leaves it untouched so the next run retries the same set — the
alternative (record-then-fail) silently drops URLs from the queue forever.

Ordering is core-pages-first: the ~67 hand-built core/product/learn/blog/tools
pages are submitted before the 1.5k ticker dossiers and 456 research landings, so
that under a cap the pages that carry the brand always fit.

Stdlib only — CI packs install minimal deps, never requirements.txt.

CLI:
  python -m engine.marketing.indexnow --root . [--dry-run] [--full] [--cap 10000]
  Always exits 0 except on an internal crash (exit 1).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# PUBLIC by protocol design — the key proves ownership only in combination with
# site/<key>.txt being served from this host.  Do NOT move it to a secret; the
# workflow needs no credentials and the file below is world-readable on purpose.
INDEXNOW_KEY = "88bb90b05303e3cf469878ebc4dc7543"
HOST = "www.mastermind-x.com"
KEY_LOCATION = "https://www.mastermind-x.com/88bb90b05303e3cf469878ebc4dc7543.txt"
ENDPOINT = "https://api.indexnow.org/indexnow"

# IndexNow's documented per-request ceiling is 10,000 URLs.
DEFAULT_CAP = 10000
_TIMEOUT_S = 30
_PLAN_PREVIEW_N = 20

_APEX_HOST = "mastermind-x.com"

_STATE_REL = Path("data") / "marketing" / "seo" / "indexnow_state.json"
_SITEMAP_REL = Path("site") / "sitemap.xml"
_SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

# Bulk estates, ranked AFTER the core pages so a cap can only ever drop tail
# inventory.  Order inside the tuple is the submission order.
_TAIL_PREFIXES = ("/stocks/", "/research/")

_USER_AGENT = "mastermind-x-indexnow/1.0 (+https://www.mastermind-x.com/)"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _now_iso(as_of: datetime | None = None) -> str:
    return (as_of or datetime.now(timezone.utc)).isoformat()


def _write_json_atomic(path: Path, obj: object) -> None:
    """Atomic write via temp file in the same directory (mirrors seo_director)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, ensure_ascii=False, sort_keys=True)
            fh.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:  # noqa: BLE001
            pass
        raise


def url_path(url: str) -> str:
    """The site-relative path of a sitemap URL, or '' if it is not ours."""
    try:
        parts = urllib.parse.urlsplit(url.strip())
    except Exception:  # noqa: BLE001
        return ""
    if parts.scheme and parts.scheme not in ("http", "https"):
        return ""
    host = (parts.netloc or "").lower().split(":")[0]
    if host and host not in (HOST, _APEX_HOST):
        return ""
    path = parts.path or "/"
    if not path.startswith("/"):
        return ""
    return path


def local_file(site_dir: Path, url: str) -> Path | None:
    """Map a sitemap URL to the built file under site/, or None if unmappable.

    ``/`` and any directory form resolve to that directory's index.html — the same
    mapping Caddy's ``file_server { index index.html }`` performs at the edge.
    """
    path = url_path(url)
    if not path:
        return None
    if path.endswith("/"):
        path += "index.html"
    candidate = site_dir / path.lstrip("/")
    # Traversal guard: a crafted sitemap entry must not reach outside site/.
    try:
        resolved = candidate.resolve()
        root = site_dir.resolve()
    except OSError:
        return None
    if resolved != root and root not in resolved.parents:
        return None
    return candidate


def _sha1_file(path: Path) -> str | None:
    try:
        h = hashlib.sha1()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 16), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _rank(url: str) -> int:
    """0 = core page, 1 = /stocks/, 2 = /research/. Core always fits under a cap."""
    path = url_path(url)
    for i, prefix in enumerate(_TAIL_PREFIXES):
        if path.startswith(prefix):
            return i + 1
    return 0


def _sort_key(url: str) -> tuple[int, str]:
    return (_rank(url), url)


# ---------------------------------------------------------------------------
# Sitemap + state
# ---------------------------------------------------------------------------


def read_sitemap_urls(sitemap: Path) -> list[str]:
    """Every <loc> in sitemap.xml that belongs to this host, de-duplicated."""
    try:
        tree = ElementTree.parse(sitemap)
    except Exception as exc:  # noqa: BLE001
        log.warning("indexnow: sitemap unreadable (%s): %s", sitemap, exc)
        return []
    seen: dict[str, None] = {}
    for loc in tree.getroot().iter(f"{_SITEMAP_NS}loc"):
        raw = (loc.text or "").strip()
        if raw and url_path(raw):
            seen.setdefault(raw, None)
    return list(seen)


def load_state(root: Path) -> dict:
    path = root / _STATE_REL
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"as_of": None, "submitted": {}}
    except Exception as exc:  # noqa: BLE001
        # A corrupt state file must not wedge the lane: treat it as a first run.
        log.warning("indexnow: state unreadable, treating as first run: %s", exc)
        return {"as_of": None, "submitted": {}}
    submitted = data.get("submitted")
    if not isinstance(submitted, dict):
        submitted = {}
    return {"as_of": data.get("as_of"), "submitted": dict(submitted)}


def key_file_ok(site_dir: Path) -> tuple[bool, str]:
    """The key file must exist AND carry the key, or the endpoint rejects us."""
    path = site_dir / f"{INDEXNOW_KEY}.txt"
    try:
        body = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False, f"key file missing: site/{INDEXNOW_KEY}.txt"
    except OSError as exc:
        return False, f"key file unreadable: {exc}"
    if body.strip() != INDEXNOW_KEY:
        return False, f"key file contents do not match INDEXNOW_KEY (site/{INDEXNOW_KEY}.txt)"
    return True, "ok"


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


def build_plan(root: Path, *, full: bool = False, cap: int = DEFAULT_CAP) -> dict:
    """Diff the sitemap against state and return the ordered submission plan.

    Returns a dict with:
      new / changed / deleted : sorted URL lists (the classification)
      submit                  : the ordered, capped list actually to be POSTed
      dropped                 : URLs the cap removed (never silently truncated)
      hashes                  : {url: sha1} for every currently-served sitemap URL
      unresolved              : sitemap URLs with no local file AND no prior state
    """
    site_dir = root / "site"
    sitemap_urls = read_sitemap_urls(root / _SITEMAP_REL)
    state = load_state(root)
    prior: dict = state["submitted"]

    hashes: dict[str, str] = {}
    unresolved: list[str] = []
    new: list[str] = []
    changed: list[str] = []
    missing_now: list[str] = []          # in the sitemap, but the file is gone

    for url in sitemap_urls:
        path = local_file(site_dir, url)
        digest = _sha1_file(path) if path is not None else None
        if digest is None:
            # A sitemap entry whose file does not exist is either a deletion we
            # have already announced (in state → announce it) or an entry that
            # never had content (not in state → nothing honest to submit).
            if url in prior:
                missing_now.append(url)
            else:
                unresolved.append(url)
            continue
        hashes[url] = digest
        if url not in prior:
            new.append(url)
        elif prior[url] != digest:
            changed.append(url)

    gone = [u for u in prior if u not in hashes and u not in missing_now]
    deleted = sorted(set(missing_now) | set(gone))

    if full:
        candidates = sorted(hashes, key=_sort_key)
    else:
        candidates = sorted(set(new) | set(changed) | set(deleted), key=_sort_key)

    cap = max(0, int(cap))
    submit = candidates[:cap]
    dropped = candidates[cap:]

    return {
        "new": sorted(new, key=_sort_key),
        "changed": sorted(changed, key=_sort_key),
        "deleted": sorted(deleted, key=_sort_key),
        "submit": submit,
        "dropped": dropped,
        "hashes": hashes,
        "unresolved": sorted(unresolved),
        "sitemap_urls": len(sitemap_urls),
        "prior_urls": len(prior),
        "full": bool(full),
        "cap": cap,
    }


def next_state(plan: dict, prior: dict, *, as_of: datetime | None = None) -> dict:
    """State after a SUCCESSFUL submission of ``plan['submit']``.

    Only URLs actually submitted advance.  A URL the cap dropped keeps its old
    hash (or stays absent), so the next run re-queues it instead of losing it.
    """
    submitted = dict(prior)
    hashes: dict = plan["hashes"]
    for url in plan["submit"]:
        if url in hashes:
            submitted[url] = hashes[url]
        else:
            submitted.pop(url, None)          # announced as deleted
    return {"as_of": _now_iso(as_of), "submitted": submitted}


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------


def _urlopen(req: urllib.request.Request, timeout: int):  # pragma: no cover - seam
    """Test seam: the ONLY place this module touches the network."""
    return urllib.request.urlopen(req, timeout=timeout)


def submit_batch(urls: list[str]) -> tuple[bool, str]:
    """POST one IndexNow batch. Returns (accepted, detail). Never raises."""
    payload = {
        "host": HOST,
        "key": INDEXNOW_KEY,
        "keyLocation": KEY_LOCATION,
        "urlList": list(urls),
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": _USER_AGENT,
        },
    )
    try:
        with _urlopen(req, _TIMEOUT_S) as resp:
            status = int(getattr(resp, "status", 0) or getattr(resp, "code", 0) or 0)
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} from {ENDPOINT}"
    except urllib.error.URLError as exc:
        return False, f"network error: {exc.reason}"
    except Exception as exc:  # noqa: BLE001 — timeouts, TLS, anything
        return False, f"submission failed: {exc.__class__.__name__}: {exc}"
    if status in (200, 202):
        return True, f"HTTP {status}"
    return False, f"unexpected HTTP {status} from {ENDPOINT}"


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def _print_plan(plan: dict, *, dry_run: bool) -> None:
    label = "DRY RUN" if dry_run else "SUBMIT"
    print(f"\n=== IndexNow ({label}) ===")
    print(f"host        : {HOST}")
    print(f"sitemap URLs: {plan['sitemap_urls']}  (state knows {plan['prior_urls']})")
    print(f"new         : {len(plan['new'])}")
    print(f"changed     : {len(plan['changed'])}")
    print(f"deleted     : {len(plan['deleted'])}")
    if plan["unresolved"]:
        print(f"unresolved  : {len(plan['unresolved'])} (sitemap URL with no built file — not submitted)")
    print(f"to submit   : {len(plan['submit'])}"
          + (f"  (cap {plan['cap']}, {len(plan['dropped'])} deferred)" if plan["dropped"] else ""))
    preview = plan["submit"][:_PLAN_PREVIEW_N]
    for url in preview:
        print(f"  {url}")
    if len(plan["submit"]) > len(preview):
        print(f"  … {len(plan['submit']) - len(preview)} more")


def run(
    root: Path,
    *,
    dry_run: bool = False,
    full: bool = False,
    cap: int = DEFAULT_CAP,
    as_of: datetime | None = None,
) -> dict:
    """Full cycle. Fail-soft: returns a result dict, never raises for an outage."""
    root = Path(root)
    ok, detail = key_file_ok(root / "site")
    if not ok:
        print(f"::warning title=indexnow::{detail} — skipping submission", flush=True)
        return {"status": "skipped", "reason": detail, "submitted": 0}

    plan = build_plan(root, full=full, cap=cap)
    _print_plan(plan, dry_run=dry_run)

    if plan["dropped"]:
        print(
            f"::notice title=indexnow::capped at {plan['cap']} URLs — "
            f"{len(plan['dropped'])} deferred to the next run "
            f"(core pages submitted first; deferred set is tail inventory)",
            flush=True,
        )

    if not plan["submit"]:
        print("indexnow: nothing to submit (sitemap unchanged since last run)")
        return {"status": "noop", "submitted": 0, "plan": plan}

    if dry_run:
        print("indexnow: dry run — no request sent, state untouched")
        return {"status": "dry_run", "submitted": 0, "plan": plan}

    accepted, why = submit_batch(plan["submit"])
    if not accepted:
        print(f"::warning title=indexnow::{why} — state NOT advanced, "
              f"{len(plan['submit'])} URLs will retry next run", flush=True)
        return {"status": "failed", "reason": why, "submitted": 0, "plan": plan}

    prior = load_state(root)["submitted"]
    try:
        _write_json_atomic(root / _STATE_REL, next_state(plan, prior, as_of=as_of))
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=indexnow::state write failed after a successful "
              f"submission: {exc}", flush=True)
        return {"status": "state_write_failed", "submitted": len(plan["submit"]), "plan": plan}

    print(f"indexnow: {why} — {len(plan['submit'])} URLs accepted")
    return {"status": "ok", "submitted": len(plan["submit"]), "plan": plan}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="IndexNow adapter — push new/changed/deleted URLs to Bing/Yandex/Seznam"
    )
    parser.add_argument("--root", default=".", help="Repo root (default: .)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the plan; send nothing, write nothing")
    parser.add_argument("--full", action="store_true",
                        help="Ignore state and submit every sitemap URL (recovery push)")
    parser.add_argument("--cap", type=int, default=DEFAULT_CAP,
                        help=f"Max URLs per run (default: {DEFAULT_CAP})")
    args = parser.parse_args(argv)

    try:
        run(Path(args.root).resolve(), dry_run=args.dry_run, full=args.full, cap=args.cap)
    except Exception as exc:  # noqa: BLE001
        print(f"::error title=indexnow::crashed: {exc}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
