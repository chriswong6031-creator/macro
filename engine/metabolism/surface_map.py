"""engine.metabolism.surface_map — Metabolism V12 site-surface census.

The deterministic evidence layer for the Surface Curator (R-V12-2..R-V12-4):

    build_surface_map(root)          → census every shipped page (bytes,
                                       structural markers, outline) and write
                                       data/metabolism/site_surface_map.json
    load_surface_map(root)           → read the committed census ({} on error)
    page_entry(page, smap)           → one page's census row (None if absent)
    is_saturated(page, smap, root)   → saturation verdict under
                                       config/metabolism_surface_rules.yml
    panel_dup_reason(title, page, smap)
                                     → token-quorum match of a proposed panel
                                       title against existing page outlines
                                       (same page first, then sitewide)
    realized_delta_from_diff(diff_text, root)
                                     → the SAME marker counter applied to a
                                       unified diff's front-page files
                                       (AUDIT teeth — R-V12-4)
    render_block(smap, lobe, root)   → byte-capped prompt block for PROPOSE

The census is EVIDENCE, not judgment (mirror of V9 criticality): a "marker"
is a cheap structural proxy for a panel/scoreboard — heading tags, sectioning
tags, and title/eyebrow-classed elements.  Absolute counts are approximate;
what enforcement relies on is that the SAME counter runs over the census and
over PR diffs, so deltas are consistent (R-V12-4).

NEVER-RAISE CONTRACT: every public function catches all exceptions and
returns a safe fail-open default.  The census never blocks a stage.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "metabolism.surface_map.v1"
MAP_REL = Path("data") / "metabolism" / "site_surface_map.json"
_RULES_REL = Path("config") / "metabolism_surface_rules.yml"
_UX_RULES_REL = Path("config") / "ux_simplicity_rules.yml"

# ── Structural-marker counter (shared census/diff counter — R-V12-4) ─────────
# A marker is a panel-grade structural unit: heading/sectioning tags, or an
# element carrying a title/eyebrow class token (the house card families use
# per-page prefixes — mx5-dg-eyebrow, nx-eyebrow, card-title, sec-title … —
# so we match the stable suffix tokens, not family prefixes).
_MARKER_TAG_RE = re.compile(r"<(?:h[1-4]|section|article|details|dialog)\b", re.I)
_MARKER_CLASS_RE = re.compile(
    r'class="[^"]*(?:eyebrow|[-_]title\b|\btitle[-_])[^"]*"', re.I
)

# Outline extraction: heading inner text + title/eyebrow-classed element text.
_HEADING_TEXT_RE = re.compile(r"<(h[1-4])\b[^>]*>(.*?)</\1>", re.I | re.S)
_CLASSED_TEXT_RE = re.compile(
    r'<(\w+)\b[^>]*class="[^"]*(?:eyebrow|[-_]title\b|\btitle[-_])[^"]*"[^>]*>'
    r"(.*?)</\1>",
    re.I | re.S,
)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")

_DEFAULT_RULES: dict[str, Any] = {
    "saturated_markers": 24,
    "saturated_bytes": 240_000,
    "max_new_bytes_saturated": 2_048,
    "outline_max": 20,
    "prompt_pages_max": 12,
    "page_overrides": {},
}


def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def load_surface_rules(root: Path | None = None) -> dict:
    """Read config/metabolism_surface_rules.yml; defaults on any error."""
    try:
        import yaml  # noqa: PLC0415
        p = _repo_root(root) / _RULES_REL
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        cfg = dict(_DEFAULT_RULES)
        for k in _DEFAULT_RULES:
            if k in raw:
                cfg[k] = raw[k]
        return cfg
    except Exception as exc:  # noqa: BLE001
        log.warning("surface_map.load_surface_rules: %s — defaults", exc)
        return dict(_DEFAULT_RULES)


def count_markers(text: str) -> int:
    """Count structural markers in HTML text.  NEVER raises."""
    try:
        return len(_MARKER_TAG_RE.findall(text)) + len(_MARKER_CLASS_RE.findall(text))
    except Exception:  # noqa: BLE001
        return 0


def _clean_text(fragment: str) -> str:
    txt = _TAG_STRIP_RE.sub(" ", fragment)
    return re.sub(r"\s+", " ", txt).strip()


def extract_outline(text: str, max_entries: int = 20) -> list[str]:
    """Extract heading/title texts from a page (best-effort).  NEVER raises."""
    try:
        seen: set[str] = set()
        out: list[str] = []
        for m in _HEADING_TEXT_RE.finditer(text):
            t = _clean_text(m.group(2))[:80]
            if t and t.lower() not in seen:
                seen.add(t.lower())
                out.append(t)
            if len(out) >= max_entries:
                return out
        for m in _CLASSED_TEXT_RE.finditer(text):
            t = _clean_text(m.group(2))[:80]
            if t and t.lower() not in seen:
                seen.add(t.lower())
                out.append(t)
            if len(out) >= max_entries:
                break
        return out
    except Exception as exc:  # noqa: BLE001
        log.debug("surface_map.extract_outline: %s", exc)
        return []


# ── Front-page classification (single source of truth: ux_simplicity_rules) ──

def _front_page_patterns(root: Path | None = None) -> tuple[list[str], list[str]]:
    """Return (includes, excludes) fnmatch patterns for front-page files."""
    try:
        import yaml  # noqa: PLC0415
        p = _repo_root(root) / _UX_RULES_REL
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        fp = (raw.get("surface_patterns") or {}).get("front_page") or {}
        return list(fp.get("include") or []), list(fp.get("exclude") or [])
    except Exception as exc:  # noqa: BLE001
        log.debug("surface_map._front_page_patterns: %s", exc)
        return (["site/*.html", "templates/*.html", "templates/*.j2"],
                ["*_lab*", "*_admin*", "*admin/*", "*committee*", "*research*"])


def is_front_page_path(path: str, root: Path | None = None) -> bool:
    """True when a repo-relative path is a front-page surface file."""
    try:
        import fnmatch  # noqa: PLC0415
        includes, excludes = _front_page_patterns(root)
        fn = str(path).replace("\\", "/").lstrip("/")
        if any(fnmatch.fnmatch(fn, pat.lstrip("/")) for pat in excludes):
            return False
        return any(fnmatch.fnmatch(fn, pat.lstrip("/")) for pat in includes)
    except Exception:  # noqa: BLE001
        return False


def page_key_for_path(path: str) -> str:
    """Normalize a site/template path to its census page key.

    site/us_stocks.html → us_stocks.html; templates/us_stocks.html.j2 →
    us_stocks.html.  NEVER raises.
    """
    try:
        name = str(path).replace("\\", "/").rsplit("/", 1)[-1]
        if name.endswith(".j2"):
            name = name[: -len(".j2")]
        return name
    except Exception:  # noqa: BLE001
        return str(path)


# ── Census build / load ──────────────────────────────────────────────────────

def build_surface_map(root: Path | None = None, write: bool = True) -> dict:
    """Census every front-page site/*.html and (optionally) write the map.

    Deterministic, no LLM, no network.  NEVER raises (returns {} shell).
    """
    r = _repo_root(root)
    rules = load_surface_rules(r)
    out: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_by": "build_surface_map",
        "pages": {},
        "counts": {"pages": 0, "saturated": 0},
        "authority": {
            "is_context_only": True,
            "note": "display-tier census; evidence for the Surface Curator "
                    "(R-V12-2) — never a market-facing signal",
        },
    }
    try:
        site = r / "site"
        outline_max = int(rules.get("outline_max") or 20)
        pages: dict[str, Any] = {}
        for f in sorted(site.glob("*.html")):
            rel = f"site/{f.name}"
            if not is_front_page_path(rel, r):
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                continue
            markers = count_markers(text)
            entry = {
                "bytes": len(text.encode("utf-8", "replace")),
                "markers": markers,
                "outline": extract_outline(text, outline_max),
            }
            entry["saturated"] = _saturated_under_rules(f.name, entry, rules)
            pages[f.name] = entry
        out["pages"] = pages
        out["counts"] = {
            "pages": len(pages),
            "saturated": sum(1 for p in pages.values() if p.get("saturated")),
        }
        if write:
            dest = r / MAP_REL
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("surface_map.build_surface_map: %s", exc)
    return out


def load_surface_map(root: Path | None = None) -> dict:
    """Read the committed census; {} on any error.  NEVER raises."""
    try:
        p = _repo_root(root) / MAP_REL
        return json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        log.debug("surface_map.load_surface_map: %s", exc)
        return {}


def page_entry(page: str, smap: dict | None = None, root: Path | None = None) -> dict | None:
    """Return one page's census row, resolving template paths.  NEVER raises."""
    try:
        m = smap if smap is not None else load_surface_map(root)
        return (m.get("pages") or {}).get(page_key_for_path(page))
    except Exception:  # noqa: BLE001
        return None


def _saturated_under_rules(page: str, entry: dict, rules: dict) -> bool:
    try:
        override = (rules.get("page_overrides") or {}).get(page)
        if isinstance(override, dict) and "saturated" in override:
            return bool(override["saturated"])
        return (
            int(entry.get("markers") or 0) >= int(rules.get("saturated_markers") or 0)
            or int(entry.get("bytes") or 0) >= int(rules.get("saturated_bytes") or 0)
        )
    except Exception:  # noqa: BLE001
        return False


def is_saturated(page: str, smap: dict | None = None, root: Path | None = None) -> bool:
    """Saturation verdict for a page (False when unknown — fail-open)."""
    try:
        entry = page_entry(page, smap, root)
        if not entry:
            return False
        if "saturated" in entry:
            return bool(entry["saturated"])
        return _saturated_under_rules(page_key_for_path(page), entry,
                                      load_surface_rules(root))
    except Exception:  # noqa: BLE001
        return False


# ── Duplicate-panel check (R-V12-2) ──────────────────────────────────────────

def _norm_tokens(s: str) -> list[str]:
    toks = re.sub(r"[^0-9a-z一-鿿]+", " ", str(s).lower()).split()
    return [t for t in toks if len(t) >= 4 or re.match(r"^[一-鿿]{2,}$", t)]


def panel_dup_reason(
    title: str,
    target_page: str,
    smap: dict | None = None,
    root: Path | None = None,
) -> str | None:
    """Return a deny reason when a proposed panel already exists, else None.

    Per-outline-entry token quorum (majority of the title's distinctive
    tokens, min 2) — same page first, then sitewide.  NEVER raises.
    """
    try:
        m = smap if smap is not None else load_surface_map(root)
        pages: dict[str, Any] = m.get("pages") or {}
        if not pages:
            return None
        tokens = _norm_tokens(title)
        if len(tokens) < 2:
            return None
        quorum = max(2, (len(tokens) + 1) // 2)

        def _entry_hit(outline: list[str]) -> str | None:
            for entry in outline or []:
                hay = f" {' '.join(_norm_tokens(entry))} "
                hits = sum(1 for t in tokens if f" {t} " in hay)
                if hits >= quorum:
                    return entry
            return None

        key = page_key_for_path(target_page)
        same = pages.get(key)
        if same:
            hit = _entry_hit(same.get("outline") or [])
            if hit:
                return (f"a panel with this meaning already exists on {key} "
                        f"('{hit}') — propose ui_mode=improve/consolidate on it instead")
        for other_key, entry in pages.items():
            if other_key == key:
                continue
            hit = _entry_hit(entry.get("outline") or [])
            if hit:
                return (f"this already exists on another page — {other_key} "
                        f"('{hit}'); do not duplicate it (link or consolidate instead)")
        return None
    except Exception as exc:  # noqa: BLE001
        log.debug("surface_map.panel_dup_reason: %s", exc)
        return None


# ── Realized delta from a unified diff (AUDIT teeth — R-V12-4) ───────────────

def realized_delta_from_diff(diff_text: str, root: Path | None = None) -> dict:
    """Compute per-front-page marker/byte deltas from a unified diff.

    Returns {"files": {page_key: {"path", "marker_delta", "net_bytes"}},
             "marker_delta": int, "net_bytes": int, "front_paths": [str]}.
    Uses the SAME counter as the census.  NEVER raises ({} shell on error).
    """
    result: dict[str, Any] = {"files": {}, "marker_delta": 0, "net_bytes": 0,
                              "front_paths": []}
    try:
        current: str | None = None
        for line in (diff_text or "").splitlines():
            if line.startswith("+++ "):
                p = line[4:].strip()
                p = p[2:] if p.startswith("b/") else p
                current = p if (p != "/dev/null" and is_front_page_path(p, root)) else None
                if current:
                    key = page_key_for_path(current)
                    result["files"].setdefault(
                        key, {"path": current, "marker_delta": 0, "net_bytes": 0})
                    if current not in result["front_paths"]:
                        result["front_paths"].append(current)
                continue
            if current is None:
                continue
            if line.startswith("+") and not line.startswith("+++"):
                body = line[1:]
                key = page_key_for_path(current)
                result["files"][key]["marker_delta"] += count_markers(body)
                result["files"][key]["net_bytes"] += len(body.encode("utf-8", "replace"))
            elif line.startswith("-") and not line.startswith("---"):
                body = line[1:]
                key = page_key_for_path(current)
                result["files"][key]["marker_delta"] -= count_markers(body)
                result["files"][key]["net_bytes"] -= len(body.encode("utf-8", "replace"))
        result["marker_delta"] = sum(f["marker_delta"] for f in result["files"].values())
        result["net_bytes"] = sum(f["net_bytes"] for f in result["files"].values())
    except Exception as exc:  # noqa: BLE001
        log.warning("surface_map.realized_delta_from_diff: %s", exc)
    return result


# ── Prompt block (PROPOSE context — R-V12-2) ─────────────────────────────────

def render_block(
    smap: dict | None = None,
    lobe: str = "",
    root: Path | None = None,
    max_bytes: int = 1600,
) -> str:
    """Byte-capped SITE SURFACE block: lobe-relevant pages + most-crowded pages."""
    try:
        m = smap if smap is not None else load_surface_map(root)
        pages: dict[str, Any] = m.get("pages") or {}
        if not pages:
            return "(census absent — run scripts/build_surface_map.py)"
        rules = load_surface_rules(root)
        cap = int(rules.get("prompt_pages_max") or 12)

        lobe_tokens = [t for t in re.split(r"[^0-9a-z]+", lobe.lower()) if len(t) >= 2]
        def _lobe_match(name: str) -> bool:
            return any(t in name for t in lobe_tokens if t not in ("site",))

        ranked = sorted(pages.items(), key=lambda kv: -int(kv[1].get("markers") or 0))
        chosen: list[tuple[str, dict]] = [kv for kv in ranked if _lobe_match(kv[0])]
        for kv in ranked:
            if len(chosen) >= cap:
                break
            if kv not in chosen:
                chosen.append(kv)

        lines: list[str] = []
        for name, e in chosen[:cap]:
            sat = "SATURATED (panel_delta must be <= 0)" if e.get("saturated") else "open"
            outline = " | ".join((e.get("outline") or [])[:8])
            lines.append(f"- {name}: {int(e.get('bytes') or 0)//1024}KB, "
                         f"{int(e.get('markers') or 0)} panels, {sat}"
                         + (f" — has: {outline}" if outline else ""))
        block = "\n".join(lines)
        return block[:max_bytes]
    except Exception as exc:  # noqa: BLE001
        log.debug("surface_map.render_block: %s", exc)
        return "(census unavailable)"
