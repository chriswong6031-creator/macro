"""Generate site/cycle_ontology.js from engine/cycle_ontology.py.

The JS file is DATA + tiny lookup helpers only — no classification logic.
resolve_state / classify_phase / canonical_position NEVER exist in JS;
pages render the resolved fields the Python build stamps.

Usage:
    python -m scripts.gen_ontology_js          # write site/cycle_ontology.js
    python -m scripts.gen_ontology_js --check  # diff only; exit 1 on drift

Called as the FIRST step in scripts/build_site.py (A12 ruling) so the JS is
always up-to-date before any page template reads it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Allow running as a script from the repo root
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from engine.cycle_ontology import export_payload, ONTOLOGY_VERSION  # noqa: E402


_OUT_PATH = os.path.join(_REPO, "site", "cycle_ontology.js")


def _render_js(payload: dict) -> str:
    """Render the JS file content from the payload dict."""
    payload_json = json.dumps(payload, indent=2, ensure_ascii=False)

    lines = [
        "/* GENERATED from engine/cycle_ontology.py",
        f"   version {ONTOLOGY_VERSION}",
        "   DO NOT EDIT — regenerate: python -m scripts.gen_ontology_js */",
        "",
        "(function (root) {",
        f"  var payload = {payload_json};",
        "",
        "  /**",
        "   * Tiny lookup helpers — data lookups ONLY.",
        "   * classify_phase / resolve_state / canonical_position run in Python only.",
        "   */",
        "",
        "  /**",
        "   * zoneWord(pos, lang) → zone word string for a 0–100 position.",
        "   * @param {number} pos  0–100 canonical position.",
        "   * @param {string} lang 'en' | 'zh'.",
        "   * @returns {string}",
        "   */",
        "  payload.zoneWord = function(pos, lang) {",
        "    var zones = payload.zones;",
        "    var field = (lang === 'zh') ? 'word_zh' : 'word';",
        "    for (var i = 0; i < zones.length; i++) {",
        "      if (pos >= zones[i].lo) return zones[i][field];",
        "    }",
        "    return zones[zones.length - 1][field];",
        "  };",
        "",
        "  /**",
        "   * phaseMeta(phase) → {label, short, label_zh, short_zh, hue}.",
        "   * @param {string} phase  One of the 5 phase keys.",
        "   * @returns {Object}",
        "   */",
        "  payload.phaseMeta = function(phase) {",
        "    return payload.phases[phase] || null;",
        "  };",
        "",
        "  /**",
        "   * stanceMeta(stance) → {en, zh, tone}.",
        "   * @param {string} stance  One of the 9 stance keys.",
        "   * @returns {Object}",
        "   */",
        "  payload.stanceMeta = function(stance) {",
        "    return payload.stances[stance] || null;",
        "  };",
        "",
        "  /**",
        "   * crosswalkLookup(phase, ladder) → {stance, divergence, tone, en, zh, ...}.",
        "   * For the pos-gated Downturn cells, pos must be supplied.",
        "   * @param {string} phase",
        "   * @param {string} ladder",
        "   * @param {number} [pos]  optional position for gated cells",
        "   * @returns {Object|null}",
        "   */",
        "  payload.crosswalkLookup = function(phase, ladder, pos) {",
        "    if (phase === 'Downturn' && (ladder === 'TURN SIGNALED' || ladder === 'FRESH BUY')) {",
        "      var gate = (typeof pos === 'number' && pos >= 55) ? '>=55' : '<55';",
        "      return payload.crosswalk[phase + '|' + ladder + '|pos' + gate] || null;",
        "    }",
        "    return payload.crosswalk[phase + '|' + ladder] || null;",
        "  };",
        "",
        "  root.CYCLE_ONTOLOGY = payload;",
        "}(typeof window !== 'undefined' ? window : (typeof global !== 'undefined' ? global : this)));",
        "",
    ]
    return "\n".join(lines)


def generate(out_path: str = _OUT_PATH) -> str:
    """Generate the JS content and return it as a string."""
    payload = export_payload()
    return _render_js(payload)


def write(out_path: str = _OUT_PATH) -> None:
    """Write site/cycle_ontology.js."""
    content = generate(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    print(f"[gen_ontology_js] Written: {out_path}")


def check(out_path: str = _OUT_PATH) -> bool:
    """Regenerate and diff against committed file.  Returns True if clean (no drift)."""
    fresh = generate(out_path)

    if not os.path.exists(out_path):
        print(f"[gen_ontology_js --check] FAIL: {out_path} does not exist", file=sys.stderr)
        return False

    with open(out_path, encoding="utf-8") as fh:
        committed = fh.read()

    if committed == fresh:
        print(f"[gen_ontology_js --check] OK: {out_path} is up to date (v{ONTOLOGY_VERSION})")
        return True

    # Find first differing line for a helpful message
    committed_lines = committed.splitlines()
    fresh_lines = fresh.splitlines()
    for i, (a, b) in enumerate(zip(committed_lines, fresh_lines)):
        if a != b:
            print(f"[gen_ontology_js --check] DRIFT at line {i + 1}:", file=sys.stderr)
            print(f"  committed: {a!r}", file=sys.stderr)
            print(f"  generated: {b!r}", file=sys.stderr)
            break
    else:
        print(f"[gen_ontology_js --check] DRIFT: line count differs "
              f"(committed {len(committed_lines)}, generated {len(fresh_lines)})", file=sys.stderr)
    print("[gen_ontology_js --check] FAIL — regenerate: python -m scripts.gen_ontology_js",
          file=sys.stderr)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate site/cycle_ontology.js")
    parser.add_argument("--check", action="store_true",
                        help="Diff against committed file; exit 1 on drift (CI use)")
    parser.add_argument("--out", default=_OUT_PATH,
                        help=f"Output path (default: {_OUT_PATH})")
    args = parser.parse_args()

    if args.check:
        return 0 if check(args.out) else 1
    else:
        write(args.out)
        return 0


if __name__ == "__main__":
    sys.exit(main())
