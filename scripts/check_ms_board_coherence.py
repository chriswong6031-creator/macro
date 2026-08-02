#!/usr/bin/env python3
"""Static guard (ui.ms_board_coherence): every rendered Market State board must be
single-snapshot coherent — the verdict word, 0-100 score, meter tick, thesis,
override notes and flip line must all be derivable from ONE
engine/market_state.py snapshot.

Why this exists — 2026-07-07 incident (commit 5bf116a3b3): the 07:27 render
push raced the 07:10 engine-render (7a1c30ced4). The push step's
`git pull --rebase --autostash -X theirs origin main` resolves whole conflict
REGIONS toward the replayed render, so the pushed site/macro.html stitched
upstream's fresh verdict/score ("Mixed" / 56, six tone-good factor rows) to the
replayed run's stale board text ("Risk-off — stress is elevated" thesis +
"Risk Radar forces Risk-off." note) — a pair market_state_snapshot can never
emit: the "forces" note only fires when the radar ceiling < 42, and the caller
then does score = min(score, ceiling), so a "forces" board must bake score <= 41
and verdict Risk-off. ui.template_site_sync (#1807) heals only plain-copy
template assets post-rebase; rendered pages had no coherence guard at all.

Invariants (constants mirrored from engine/market_state.py — _verdict_from_score,
_LABEL, _HEADLINES, _radar_override / _radar_override_intl, _flip_text and the
score-cap block in market_state_snapshot; tests/test_check_ms_board_coherence.py
cross-checks every copy against the engine so they cannot drift):

  (a) verdict word <-> score band: Risk-off <=> score <= 41, Mixed <=> 42..59,
      Risk-on <=> score >= 60. Strict equivalence holds because the snapshot
      pulls the score into a forced verdict's band BEFORE the final re-cap.
  (b) meter tick position == score.
  (c) thesis headline prefix <-> verdict word.
  (d) "... Risk Radar forces Risk-off." note => word Risk-off AND score <= 41
      (intl boards prefix a market name; the note is matched anywhere).
  (e) "Capped at Mixed by the Risk Radar above." note => word != Risk-on AND
      score <= 59.
  (f) any "forced to Risk-off" note => word Risk-off; any "capped at Mixed"
      note => word != Risk-on (stress/dislocation and alert/regime overrides).
  (g) flip-line shape <-> verdict word ("→ Green if" <=> Mixed,
      "→ Mixed if" <=> Risk-on, "→ Mixed when" <=> Risk-off).
  (h) score-path endpoint <-> board score, WHEN they claim the same session:
      the chart's last data-point carries its own date, so a gap between it and
      the headline is legitimate and disclosed ("last graded <date>") — but only
      while the dates DIFFER. When the last point's date equals the board's
      as-of, the two are the same read and must carry the same number and the
      same band. Added after the 2026-08-02 operator report: macro.html baked a
      69 / Risk-on gauge beside a Jul 31 endpoint of 66, because the two come
      from artifacts with opposite write policies for one session —
      market_state_audit.log_snapshot is first-write-wins per as-of (a PIT
      ledger must not be rewritten), engine.market_state.persist is
      last-write-wins (every build) — so any session whose recompute moved
      shipped two numbers under one date, with the stamp asserting they matched.
      build_site._ms_history_view now reconciles the DISPLAY endpoint to the
      board (the logged row is left alone); this pins that it stays reconciled.

Only the l-en spans are parsed: EN and ZH share each <p> source line, so a
line-granular rebase stitch cannot split the pair.

Exit 0 on clean (pages without an ms-board are skipped). Exit 1 with a readable
listing on any violation, including a present-but-unparseable board.

Usage:
    python3 scripts/check_ms_board_coherence.py                  # scan site/*.html
    python3 scripts/check_ms_board_coherence.py PAGE [PAGE ...]  # explicit pages
    python3 scripts/check_ms_board_coherence.py --heal-from REF [PAGE ...]
        # render lanes, post-rebase: restore each incoherent page WHOLESALE from
        # REF (`git checkout REF -- PAGE`) — a coherent board at most one render
        # old beats a stitched hybrid; the next render re-lands freshness.
        # Exit 0 if everything is (or heals) clean, 1 if still incoherent.
    python3 scripts/check_ms_board_coherence.py --selftest       # synthetic fixtures
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ── Constants mirrored from engine/market_state.py (drift-pinned by tests) ───
# _verdict_from_score bands, keyed by the _LABEL display word.
BANDS = {"Risk-off": (0, 41), "Mixed": (42, 59), "Risk-on": (60, 100)}
# _HEADLINES[verdict] opening words (the full sentence follows the em-dash).
HEADLINE_PREFIX = {
    "Risk-on": "Risk-on —",
    "Mixed": "Mixed / transition —",
    "Risk-off": "Risk-off —",
}
# _flip_text(verdict) opening words -> the only verdict that emits them.
FLIP_PREFIX = {
    "→ Mixed if": "Risk-on",
    "→ Mixed when": "Risk-off",
    "→ Green if": "Mixed",
}
# _radar_override (US) / _radar_override_intl ("{market} " prefix) note bodies.
NOTE_FORCES = "Risk Radar forces Risk-off."
NOTE_CAPPED = "Capped at Mixed by the Risk Radar above."
# stress/dislocation overrides ("... — forced to Risk-off.") and the
# alert/regime overrides ("... — capped at Mixed ..."), matched case-insensitively.
NOTE_FORCED_GENERIC = "forced to Risk-off"
NOTE_CAPPED_GENERIC = "capped at mixed"

_SECTION = re.compile(r'<section class="ms-verdict">(.*?)</section>', re.S)
_WORD = re.compile(r'id="ms-word"><span class="l-en">([^<]*)</span>')
_SCORE = re.compile(r'id="ms-score">(\d+)<')
_TICK = re.compile(r'id="ms-tick" style="left:\s*([0-9.]+)%')
_THESIS = re.compile(r'class="v-thesis"><span class="l-en">([^<]*)</span>')
_OVERRIDE = re.compile(
    r'class="v-override">(?:<span class="ic">[^<]*</span>)?<span class="l-en">([^<]*)</span>'
)
_FLIP = re.compile(r'class="v-flip"><span class="l-en">([^<]*)</span>')

# ── (h) score-path endpoint vs the board it sits beside ─────────────────────
# The chart's data-points array is single-quoted (it carries JSON), and the board
# score / as-of stamps carry different attribute orders per page, so both are
# matched attribute-first rather than by exact markup.
_PATH_PTS = re.compile(r"<svg class=\"mx5-path-svg\"[^>]*?data-points='(.*?)'", re.S)
_SCORE_ANY = re.compile(r'id="ms-score"[^>]*>(\d+)<')
_ASOF_ANY = re.compile(r'id="(?:regime-asof|ms-date)"[^>]*>(\d{4}-\d{2}-\d{2})<')


def _band(score: float) -> str:
    for word, (lo, hi) in BANDS.items():
        if lo <= score <= hi:
            return word
    return "?"


def check_path_endpoint(name: str, html: str) -> list[str]:
    """(h): the score-path chart must not contradict the board for ONE session.

    Runs independently of the ms-verdict section — china.html carries the chart
    and an #ms-score but bakes its board in its own markup. Pages with no chart,
    no score, or no parseable as-of are skipped: without a date on both sides
    there is no way to tell a legitimate "endpoint is yesterday" gap from a
    split, and inventing a violation there would wedge the render lane. That
    blind spot is real — hk.html and canada.html bake neither #regime-asof nor
    a dated #ms-date, so only their per-point band self-consistency is checked.
    """
    pts_m = _PATH_PTS.search(html)
    if not pts_m:
        return []
    try:
        pts = json.loads(unescape(pts_m.group(1)))
    except Exception as e:  # noqa: BLE001 — a garbled array is a loud violation
        return [f"(h) {name}: score-path data-points unparseable ({e})"]
    if not pts:
        return []

    v: list[str] = []
    # every point's own verdict word must match its own score band — a stitched
    # or hand-edited array shows up here even when no date lines up
    for p in pts:
        s, word = p.get("s"), p.get("v")
        if s is None or word is None:
            continue
        if _band(float(s)) != word:
            v.append(f"(h) {name}: path point {p.get('d')} scores {s} but is labelled"
                     f" {word!r} (band {_band(float(s))})")

    last = pts[-1]
    score_m, asof_m = _SCORE_ANY.search(html), _ASOF_ANY.search(html)
    if not score_m or not asof_m or not last.get("d"):
        return v
    if str(last["d"]) != asof_m.group(1):
        return v                      # different sessions — the header stamp discloses it
    board = int(score_m.group(1))
    if float(last.get("s")) != float(board):
        v.append(
            f"(h) {name}: board and path endpoint both claim {asof_m.group(1)} but score"
            f" {board} ({_band(board)}) vs {last['s']} ({_band(float(last['s']))}) —"
            f" one session cannot have two scores"
        )
    return v


def check_text(name: str, html: str) -> list[str]:
    """Return violation strings for one rendered page. Empty list = clean.

    A page without an ms-verdict section is clean (not every market ships the
    board); a section that is present but unparseable is a violation — a
    stitched hybrid may garble the markup itself.
    """
    # (h) is board-section-independent: a page can ship the chart without the
    # ms-verdict markup (china.html does), so it is collected either way.
    path_v = check_path_endpoint(name, html)

    section = _SECTION.search(html)
    if not section:
        return path_v
    sec = section.group(1)

    word_m, score_m = _WORD.search(sec), _SCORE.search(sec)
    if not word_m or not score_m:
        return path_v + [f"{name}: ms-board present but verdict word / score unparseable"]
    word = word_m.group(1).strip()
    score = int(score_m.group(1))
    if word not in BANDS:
        return path_v + [f"{name}: unknown verdict word {word!r} (expected {sorted(BANDS)})"]

    v: list[str] = list(path_v)
    lo, hi = BANDS[word]
    if not lo <= score <= hi:
        v.append(f"(a) {name}: verdict {word!r} with score {score} outside band {lo}..{hi}")

    tick_m = _TICK.search(sec)
    if tick_m and float(tick_m.group(1)) != float(score):
        v.append(f"(b) {name}: meter tick at {tick_m.group(1)}% but score is {score}")

    thesis_m = _THESIS.search(sec)
    if thesis_m:
        thesis = thesis_m.group(1).strip()
        if not thesis.startswith(HEADLINE_PREFIX[word]):
            v.append(
                f"(c) {name}: verdict {word!r} but thesis reads {thesis[:60]!r}"
                f" (expected prefix {HEADLINE_PREFIX[word]!r})"
            )

    for note in _OVERRIDE.findall(sec):
        note = note.strip()
        if NOTE_FORCES in note:
            if word != "Risk-off" or score > 41:
                v.append(
                    f"(d) {name}: note {note!r} demands verdict Risk-off + score <= 41,"
                    f" board bakes {word!r} / {score}"
                )
        elif NOTE_CAPPED in note:
            if word == "Risk-on" or score > 59:
                v.append(
                    f"(e) {name}: note {note!r} demands verdict <= Mixed + score <= 59,"
                    f" board bakes {word!r} / {score}"
                )
        elif NOTE_FORCED_GENERIC in note and word != "Risk-off":
            v.append(f"(f) {name}: note {note!r} demands verdict Risk-off, board bakes {word!r}")
        elif NOTE_CAPPED_GENERIC in note.lower() and word == "Risk-on":
            v.append(f"(f) {name}: note {note!r} demands verdict <= Mixed, board bakes Risk-on")

    flip_m = _FLIP.search(sec)
    if flip_m:
        flip = flip_m.group(1).strip()
        for prefix, expected in FLIP_PREFIX.items():
            if flip.startswith(prefix) and word != expected:
                v.append(
                    f"(g) {name}: flip line {flip[:50]!r} is the {expected!r} shape,"
                    f" board bakes {word!r}"
                )
    return v


def check_page(path: Path) -> list[str]:
    if not path.exists():
        return []  # absent page is not a violation (scoped render / new market)
    try:
        html = path.read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001 — unreadable page = loud violation
        return [f"{path}: unreadable ({e})"]
    return check_text(str(path), html)


def heal_from(ref: str, path: Path) -> bool:
    """Restore `path` wholesale from `ref`; True if git succeeded."""
    res = subprocess.run(
        ["git", "checkout", ref, "--", path.name],
        cwd=path.parent,
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        print(f"  heal failed: git checkout {ref} -- {path}: {res.stderr.strip()}")
    return res.returncode == 0


def _default_pages() -> list[Path]:
    return sorted((ROOT / "site").glob("*.html"))


# ── Selftest fixtures (the incident, verbatim, plus synthetic edge cases) ─────

def _path_page(board_asof, board_score, pt_date, pt_score, word=None) -> str:
    """(h) fixture: a page carrying a score-path chart, and optionally the board
    stamps (#ms-score + a dated #ms-date) the endpoint is checked against."""
    pts = [{"d": "2026-07-29", "md": "Jul 29", "s": 40, "v": "Risk-off",
            "x": 44.0, "y": 120.4},
           {"d": pt_date, "md": "Jul x", "s": pt_score,
            "v": word or _band(float(pt_score)), "x": 988.0,
            "y": round(10 + (100 - pt_score) / 100 * 184, 2)}]
    head = ""
    if board_asof is not None and board_score is not None:
        head = (f'<span class="v-score" id="ms-score">{board_score}</span>'
                f'<span class="ms-date" id="ms-date">{board_asof}</span>')
    return (f'<html><body>{head}'
            f'<svg class="mx5-path-svg" viewBox="0 0 1000 224" '
            f"data-points='{json.dumps(pts)}'></svg></body></html>")


def _board(word, score, thesis, note, flip, tick=None) -> str:
    note_html = (
        f'<p class="v-override"><span class="ic">⚠</span><span class="l-en">{note}</span>'
        f'<span class="l-zh">zh</span></p>' if note else ""
    )
    flip_html = (
        f'<p class="v-flip"><span class="l-en">{flip}</span><span class="l-zh">zh</span></p>'
        if flip else ""
    )
    return f"""<section class="ms-verdict">
      <p class="v-word" id="ms-word"><span class="l-en">{word}</span><span class="l-zh">zh</span><span class="arr">▶</span></p>
      <div class="v-scorerow"><span class="v-score" id="ms-score">{score}</span><span class="v-outof">/ 100</span></div>
      <div class="v-meter"><span class="tick" id="ms-tick" style="left:{score if tick is None else tick}%"></span></div>
      <p class="v-thesis"><span class="l-en">{thesis}</span><span class="l-zh">zh</span></p>
      {note_html}{flip_html}
    </section>"""


FIX_COHERENT_MIXED = _board(
    "Mixed", 56,
    "Mixed / transition — the signals disagree. Trade smaller.",
    "Capped at Mixed by the Risk Radar above.",
    "→ Green if risk appetite firms up (now 70/100); → Red if it deteriorates further.",
)
FIX_COHERENT_RISKOFF = _board(
    "Risk-off", 40,
    "Risk-off — stress is elevated; defend capital first.",
    "Risk Radar forces Risk-off.",
    "→ Mixed when trend & technicals stabilises and stress fades.",
)
# The 2026-07-07 hybrid (commit 5bf116a3b3): upstream's word/score beside the
# replayed run's stale thesis/note/flip. Violates (c), (d) and (g) at once.
FIX_HYBRID_INCIDENT = _board(
    "Mixed", 56,
    "Risk-off — stress is elevated; defend capital first.",
    "Risk Radar forces Risk-off.",
    "→ Mixed when trend & technicals stabilises and stress fades.",
)
FIX_INTL_FORCES_OK = _board(
    "Risk-off", 28,
    "Risk-off — stress is elevated; defend capital first.",
    "Hong Kong Risk Radar forces Risk-off.",
    "→ Mixed when breadth stabilises and stress fades.",
)


def _selftest() -> int:
    cases = [
        ("coherent mixed", FIX_COHERENT_MIXED, 0),
        ("coherent risk-off", FIX_COHERENT_RISKOFF, 0),
        ("2026-07-07 hybrid", FIX_HYBRID_INCIDENT, 3),
        ("intl forces prefix", FIX_INTL_FORCES_OK, 0),
        ("band mismatch", _board("Risk-on", 55, "Risk-on — the tape lines up.", "", ""), 1),
        ("tick drift", _board("Mixed", 50, "Mixed / transition — x.", "", "", tick=80), 1),
        ("no board", "<html><body>no board here</body></html>", 0),
        ("garbled board", '<section class="ms-verdict"><p>mangled</p></section>', 1),
        # (h) — the 2026-08-02 report: one date, two scores, two bands
        ("path endpoint splits the session", _path_page("2026-07-31", 44, "2026-07-31", 66), 1),
        ("path endpoint agrees", _path_page("2026-07-31", 69, "2026-07-31", 69), 0),
        # a genuine day gap is legitimate and disclosed by the header stamp
        ("path endpoint is yesterday", _path_page("2026-07-31", 44, "2026-07-30", 66), 0),
        # a point mislabelled against its own score, with no date to compare
        ("path point band mislabelled", _path_page(None, None, "2026-07-30", 66,
                                                   word="Risk-off"), 1),
    ]
    failed = False
    for label, html, want in cases:
        got = check_text(label, html)
        ok = len(got) == want
        print(f"  {'PASS' if ok else 'FAIL'} {label}: {len(got)} violation(s), expected {want}")
        for g in got:
            print(f"      {g}")
        failed |= not ok
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return _selftest()
    heal_ref = None
    if "--heal-from" in argv:
        i = argv.index("--heal-from")
        try:
            heal_ref = argv[i + 1]
        except IndexError:
            print("--heal-from requires a git ref"); return 2
        argv = argv[:i] + argv[i + 2:]

    pages = [Path(a) if Path(a).is_absolute() else ROOT / a for a in argv] or _default_pages()

    violations: dict[Path, list[str]] = {}
    for p in pages:
        v = check_page(p)
        if v:
            violations[p] = v

    if not violations:
        print(f"ms-board coherence: OK ({len(pages)} page(s) scanned)")
        return 0

    print("ms-board coherence violations:")
    for p, vs in violations.items():
        for line in vs:
            print(f"  {line}")

    if heal_ref is None:
        return 1

    print(f"healing incoherent page(s) from {heal_ref} (coherent-but-older beats a hybrid):")
    still_bad = False
    for p in violations:
        if heal_from(heal_ref, p) and not check_page(p):
            print(f"  healed: {p}")
        else:
            print(f"  STILL INCOHERENT after restore: {p} (predates this run?)")
            still_bad = True
    return 1 if still_bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
