"""Program watch — the four things that can move biopharma seasonality forward.

The operator should not have to poll a session to learn whether the program
moved.  Four independent things can move it, each with a DIFFERENT next action,
and each one is READ FROM REAL STATE here rather than restated as a reminder:

1. ``biocatalyst_event_contract`` — the sister session's producer contract
   landing is what unblocks :mod:`engine.seasonality.event_clock`, which today
   refuses every payload wholesale because its expectation is unratified.
2. ``first_matured_grade`` — the forward ledger's first grade is the first
   evidence the calendar clock has any forward edge at all.
3. ``catalyst_render`` — the catalyst UI reaching the built page.
4. ``deferred_followups`` — three small deferrals that rot quietly.

Three design constraints, all load-bearing:

* **No wall clock.**  ``asof`` is always an explicit argument.  A watch that
  reads ``date.today()`` produces a different answer on a re-run of the same
  night, which makes the artifact untestable and the builder non-idempotent.
  ``tests/test_seasonality_program_watch.py`` greps this module for
  ``datetime.now`` / ``date.today`` and fails on either.
* **Pure stdlib.**  This runs beside thin-runner code in the same package (see
  the package docstring): no ``yaml``, no ``pandas``.  The one YAML-ish read
  here — the synapse notes block — is done as a scoped text scan for exactly
  that reason.
* **``unavailable`` is a real state.**  When an input is missing or unreadable
  the tripwire says so.  Reporting ``waiting`` for something that could not be
  checked is the failure mode this exists to prevent: it looks identical to a
  checked-and-not-yet answer, and the operator would wait on it forever.

Nothing in this module is user-facing.  Everything it emits — the operator
prompts, the doc paths, the module names — is PRIVATE-CHANNEL content and must
never reach a ``site/`` page.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

WATCH_SCHEMA = "seasonality.program_watch.v1"

#: The three states a tripwire may report.  ``unavailable`` is not an error
#: state — it is the honest answer when the input could not be read.
STATES = ("fired", "waiting", "unavailable")

# --- input paths (all repo-relative; every read is fail-open) ---------------

BIOCATALYST_CONTRACTS_DIR = "contracts/biocatalyst"
LEDGER_PATH = "data/seasonality/nw_forward_ledger.jsonl"
SEASONALITY_TEMPLATE = "templates/stock_seasonality.html.j2"
SEASONALITY_PAGE = "site/stock_seasonality.html"
FOUNDATION_PATH = "engine/seasonality/foundation.py"
VALIDATION_PATH = "engine/validation.py"
SYNAPSE_PATH = "config/synapse.yml"
DAILY_WORKFLOW_PATH = ".github/workflows/daily.yml"

#: Where the nightly ORDER is described in prose rather than executed.  The
#: daily-order follow-up has two acceptable outcomes — reorder, or decide the lag
#: is fine and say so — and only the second one leaves a readable trace.
DAG_PATH = "config/dag.yml"

#: The explicit decision record for that second outcome.  Fail-closed: an ABSENT
#: token means undecided, not decided-and-undocumented, so the follow-up stays
#: ``open`` until somebody writes the reason down.  Deleting the token re-opens
#: the tripwire, which is the point — the order is only settled while the
#: rationale is still in the tree.
DAG_ORDER_DECISION_TOKEN = "seasonality_one_night_lag_accepted"

#: A BioCatalyst seasonality event-projection schema is matched on BOTH tokens
#: rather than on one exact filename: the producer session owns the naming, and
#: a watch that hardcoded today's guess would report ``waiting`` forever after
#: the contract actually landed under a neighbouring name.
CONTRACT_TOKENS = ("seasonality", "event")

#: …but the FILENAME heuristic alone misses the producer's own convention.  All
#: 51 contracts already in ``contracts/biocatalyst/`` are domain-first
#: (``trial_protocol_projection.v1.schema.json``, ``fda_regulatory_event.v1…``)
#: and NONE carries the token ``seasonality``; a landing named
#: ``biocatalyst_event_projection.v1.schema.json`` would be missed by the tokens
#: and the watch would stay green-that-never-turns.  So the CONTENT is matched
#: too, on the contract id the reader is already pinned to
#: (``engine/seasonality/event_clock.EXPECTED_PROJECTION_CONTRACT``).  Kept as a
#: literal rather than an import: this module is pure stdlib and must not drag
#: the event clock's dependencies into the nightly watch.  A drift between the
#: two is caught by ``tests/test_seasonality_program_watch.py``.
CONTRACT_ID_STEM = "biocatalyst_seasonality_event_projection"

#: Only machine-readable schema files count.  ``README_seasonality_event.md``
#: satisfies both filename tokens and is not a contract; matching it fires the
#: tripwire and sends the operator to run a reconciliation PR against nothing.
CONTRACT_SUFFIXES = (".json", ".yml", ".yaml")

#: The markers that say the catalyst mode reached a surface.  Two of them, so a
#: partial render (shell present, catalyst block absent) is distinguishable from
#: a page that never got the feature at all.
CATALYST_MARKERS = ("sx-mode", "sx-catalyst")

#: The synapse artifact whose notes still have to catch up to the v2 states.
SYNAPSE_ENTRY = "data-neuralweb-biopharma-seasonality-state"

_HANDOFF_GLOB = "BIOPHARMA_SEASONALITY_INTELLIGENCE*CONTINUATION_HANDOFF_*.md"
_HANDOFF_FALLBACK = "research/SEASONALITY_PROGRAM_HANDOFF_2026-08-02.md"
_SEAM_DOC = "research/SEASONALITY_BIOCATALYST_INTEGRATION_SEAM.md"
#: The trailing ISO date in a handoff filename — the ONLY part of the name that
#: orders two handoffs.  See :func:`latest_handoff`.
_HANDOFF_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?=\.md$)")


# ---------------------------------------------------------------------------
# small fail-open readers
# ---------------------------------------------------------------------------


def _read_text(path: Path) -> tuple[str | None, str | None]:
    """``(text, error)`` — never raises.  A missing file is an error, not ``""``."""
    try:
        return path.read_text(encoding="utf-8"), None
    except FileNotFoundError:
        return None, "absent"
    except (OSError, UnicodeDecodeError) as exc:  # unreadable is NOT "not there"
        return None, f"{type(exc).__name__}: {exc}"


def _rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def latest_handoff(root: Path) -> str:
    """The newest program handoff doc, by the ISO DATE PARSED OUT of its name.

    Not by mtime: file mtimes are observer-stamped repo-wide in this fleet (a
    status sweep or a reflog expiry restamps whole trees), so an mtime sort
    would pick an arbitrary doc.

    Not by whole-name lexicographic sort either, which is the bug this function
    used to carry.  The glob admits a variable infix
    (``…INTELLIGENCE*CONTINUATION_HANDOFF_…``) and this tree already holds two
    prefixes — ``…INTELLIGENCE_CLAUDE_CONTINUATION_HANDOFF_2026-08-06.md`` and
    ``…INTELLIGENCE_CONTINUATION_HANDOFF_2026-08-07.md``.  Sorting the whole
    string lets the PREFIX decide (``'L' < 'O'``), so a newer ``_CLAUDE_`` doc
    loses to an older plain one and every operator prompt cites a stale handoff.
    Only the trailing date orders two handoffs; the name is the tie-break so the
    answer stays deterministic when two docs carry the same date.
    """
    research = root / "research"
    try:
        names = [p.name for p in research.glob(_HANDOFF_GLOB) if p.is_file()]
    except OSError:
        names = []
    dated: list[tuple[tuple[int, int, int], str]] = []
    for name in names:
        m = _HANDOFF_DATE_RE.search(name)
        if m:
            dated.append(((int(m.group(1)), int(m.group(2)), int(m.group(3))), name))
    if not dated:
        # No parseable date anywhere: fall back to a name sort over whatever
        # matched, and to the pinned doc when nothing matched at all.  Guessing
        # is worse than citing a doc that is known to exist.
        return f"research/{sorted(names)[-1]}" if names else _HANDOFF_FALLBACK
    return f"research/{max(dated)[1]}"


# ---------------------------------------------------------------------------
# tripwire 1 — the BioCatalyst producer contract
# ---------------------------------------------------------------------------


def _contract_candidates(directory: Path) -> tuple[list[str], list[str], list[str]]:
    """``(matched, matched_by_content, scanned)`` under ``directory``, recursively.

    Two independent matchers, because either one alone has a known blind spot:

    * **Filename tokens** catch a landing the reader has never heard of, which is
      the whole point of not hardcoding one name — but they miss the producer's
      own domain-first convention (no existing contract there says
      "seasonality").
    * **Content** catches exactly that case: a schema whose body declares the
      contract id the event clock is pinned to, whatever the file is called.

    ``rglob`` rather than ``iterdir``: a producer that files the schema under
    ``contracts/biocatalyst/seasonality/`` is not "not landed", and a
    non-recursive scan reports ``waiting`` forever with ``n_files_scanned: 0``.
    """
    scanned: list[str] = []
    matched: list[str] = []
    by_content: list[str] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in CONTRACT_SUFFIXES:
            continue
        rel = path.relative_to(directory).as_posix()
        scanned.append(rel)
        # Tokens are matched over the RELATIVE PATH, not the bare filename: a
        # producer that files ``seasonality/event_projection.v1.schema.json``
        # has said both words, just one of them in a directory name.
        name_hit = all(tok in rel.lower() for tok in CONTRACT_TOKENS)
        text, _err = _read_text(path)
        content_hit = bool(text) and CONTRACT_ID_STEM in text
        if content_hit:
            by_content.append(rel)
        if name_hit or content_hit:
            matched.append(rel)
    return matched, by_content, scanned


def _tw_biocatalyst_event_contract(root: Path) -> dict[str, Any]:
    handoff = _SEAM_DOC
    directory = root / BIOCATALYST_CONTRACTS_DIR
    # State-specific prompts.  A single prompt written for the FIRED world and
    # returned from every branch hands the operator a false statement of current
    # state ("The contract has landed. Run the reconciliation PR…") on a night
    # when the tripwire is reporting that it has NOT landed — and the prompts are
    # the field an automation would pipe.
    fired_prompt = (
        "The BioCatalyst seasonality event-projection contract has landed. Run the W1B "
        "reconciliation PR against engine/seasonality/event_clock.py: pin the exact "
        "contract_id, the exact schema_version, and the producer's canonical content-hash "
        "convention, replace the unratified EXPECTED_PROJECTION_CONTRACT expectation with "
        f"the ratified one, and add a fixture from the real producer payload. Read {handoff} "
        "first. Any disagreement found is a bug in event_clock.py, not in the producer."
    )
    waiting_prompt = (
        "The BioCatalyst seasonality event-projection contract has NOT landed yet, so the "
        "event clock stays dark and there is nothing to reconcile. Nothing to do here "
        "tonight; when it lands this tripwire fires and carries the reconciliation prompt. "
        f"If you want to chase it, {handoff} names the seam and the producer session."
    )
    unavailable_prompt = (
        "Whether the BioCatalyst seasonality event-projection contract exists could not be "
        "checked in this checkout — this is NOT evidence that it is missing. Re-run the "
        f"seasonality program watch where contracts/biocatalyst/ is present. Context: {handoff}."
    )
    if not directory.is_dir():
        return {
            "key": "biocatalyst_event_contract",
            "state": "unavailable",
            "headline": "The BioCatalyst contracts directory is not in this checkout.",
            "why": (
                "Whether the producer contract exists cannot be answered from here, so "
                "this is not evidence that it is still missing."
            ),
            "evidence": {"dir": BIOCATALYST_CONTRACTS_DIR, "reason": "absent"},
            "operator_prompt": unavailable_prompt,
            "handoff_doc": handoff,
        }
    try:
        matched, by_content, scanned = _contract_candidates(directory)
    except OSError as exc:
        return {
            "key": "biocatalyst_event_contract",
            "state": "unavailable",
            "headline": "The BioCatalyst contracts directory could not be listed.",
            "why": "An unreadable directory is not the same answer as an empty one.",
            "evidence": {"dir": BIOCATALYST_CONTRACTS_DIR, "reason": f"{type(exc).__name__}: {exc}"},
            "operator_prompt": unavailable_prompt,
            "handoff_doc": handoff,
        }
    evidence = {
        "dir": BIOCATALYST_CONTRACTS_DIR,
        "match_tokens": list(CONTRACT_TOKENS),
        "match_contract_id_stem": CONTRACT_ID_STEM,
        "match_suffixes": list(CONTRACT_SUFFIXES),
        "matched": matched,
        "matched_by_content": by_content,
        "n_files_scanned": len(scanned),
    }
    if matched:
        return {
            "key": "biocatalyst_event_contract",
            "state": "fired",
            "headline": (
                "A BioCatalyst seasonality event-projection schema is now in the tree: "
                + ", ".join(matched)
            ),
            "why": (
                "Until this landed, the event clock refused every payload wholesale — its "
                "expected contract_id was a declared expectation written from the outside, "
                "not a ratified producer contract. The reconciliation PR can run now."
            ),
            "evidence": evidence,
            "operator_prompt": fired_prompt,
            "handoff_doc": handoff,
        }
    return {
        "key": "biocatalyst_event_contract",
        "state": "waiting",
        "headline": (
            "No BioCatalyst seasonality event-projection schema yet "
            f"({len(scanned)} contract files scanned)."
        ),
        "why": (
            "The event clock stays dark until the producer contract exists: it refuses any "
            "envelope whose contract_id is not an exact match, because a partial read of an "
            "unknown dialect is indistinguishable from a confident misread. Nothing to do "
            "until the sister session ships it."
        ),
        "evidence": evidence,
        "operator_prompt": waiting_prompt,
        "handoff_doc": handoff,
    }


# ---------------------------------------------------------------------------
# tripwire 2 — the first matured grade on the forward ledger
# ---------------------------------------------------------------------------


#: The ONE ``grade_status`` that is forward evidence.  ``engine.seasonality.state``
#: also writes ``row_type: "grade"`` rows with ``grade_status:
#: "ungradable_missing_prices"`` — ``realized_log_return``, ``outcome_up`` and
#: ``brier`` all ``None`` — for a symbol that left the price store, and its own
#: canonical forward-sample reader (``live_n_by_symbol``) excludes them by name:
#: "closed but carry no outcome, so they are not evidence and are not counted".
#: Counting a close-out as scored overclaims a forward record on a public page
#: and fires the "first forward evidence" tripwire on zero evidence.
GRADED_STATUS = "graded"


def read_ledger_counts(root: Path) -> dict[str, Any]:
    """Count the forward ledger by ``row_type``; never raises.

    A malformed line is COUNTED, never repaired and never fatal — the ledger is
    append-only and this module is not its writer.  Callers that PUBLISH a count
    must gate on ``malformed``: a file that parses partially yields an
    undercount that is indistinguishable from a true low count.

    Every population here is counted as DISTINCT KEYS, not rows.  Mixing the two
    (rows for one side, keys for the other) lets an append-only re-grade or
    re-register print ``graded > registered``.  Rows with no ``key`` are given a
    unique synthetic identity so they can never collapse onto one another: one
    keyless grade row must not mark every keyless register graded.
    """
    path = root / LEDGER_PATH
    text, err = _read_text(path)
    if text is None:
        return {"available": False, "reason": err, "path": LEDGER_PATH}
    by_type: dict[str, int] = {}
    malformed = 0
    keyless = 0
    unparseable_ends = 0
    register_keys: set[str] = set()
    graded_keys: set[str] = set()
    closed_out_keys: set[str] = set()
    grade_status_counts: dict[str, int] = {}
    register_ends: dict[str, str] = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            malformed += 1
            continue
        if not isinstance(row, dict):
            malformed += 1
            continue
        row_type = str(row.get("row_type") or "unknown")
        by_type[row_type] = by_type.get(row_type, 0) + 1
        raw_key = str(row.get("key") or "")
        if raw_key:
            key = raw_key
        else:
            keyless += 1
            key = f"\x00keyless:{lineno}"  # unique — never collides with a real key
        if row_type == "grade":
            status = str(row.get("grade_status") or "unknown")
            grade_status_counts[status] = grade_status_counts.get(status, 0) + 1
            if status == GRADED_STATUS:
                graded_keys.add(key)
            else:
                # Closed out with no outcome: not evidence, but no longer pending
                # either — it will never produce a grade.
                closed_out_keys.add(key)
        elif row_type == "register":
            register_keys.add(key)
            register_ends[key] = str(row.get("occurrence_end_date") or "")
    pending_keys = register_keys - graded_keys - closed_out_keys
    pending_ends: list[str] = []
    for key in sorted(pending_keys):
        end = register_ends.get(key, "")
        # An ISO date and nothing else: a garbled value must not become the
        # "earliest", which is the field the operator times their check-in on.
        # But a DROPPED date silently pushes that check-in LATER, so the drop is
        # counted and printed rather than hidden.
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", end):
            pending_ends.append(end)
        else:
            unparseable_ends += 1
    graded_registered = graded_keys & register_keys
    return {
        "available": True,
        "path": LEDGER_PATH,
        "by_type": dict(sorted(by_type.items())),
        "grade_status_counts": dict(sorted(grade_status_counts.items())),
        "registered": len(register_keys),
        # The published number: registered windows that carry a real outcome.
        "graded": len(graded_registered),
        "graded_total": len(graded_keys),
        # A grade whose key was never registered is a ledger inconsistency, not a
        # scored window; it must not deflate ``pending`` or inflate ``graded``.
        "graded_unregistered": len(graded_keys - register_keys),
        "closed_out_ungradable": len(closed_out_keys),
        "malformed": malformed,
        "keyless_rows": keyless,
        "pending": len(pending_keys),
        "pending_without_readable_end": unparseable_ends,
        "earliest_pending_occurrence_end": min(pending_ends) if pending_ends else None,
    }


def _tw_first_matured_grade(root: Path, handoff: str) -> dict[str, Any]:
    counts = read_ledger_counts(root)
    fired_prompt = (
        "The seasonality forward ledger has its first graded window. Read "
        f"{handoff}, then run the calibration read: grade counts by symbol, realized vs "
        "registered p, and whether the sample is anywhere near the pre-registered gate. "
        "Report it as accrual, not as a verdict — one grade is not a result — and update "
        "the Calibration Lab forward-record line."
    )
    waiting_prompt = (
        "No seasonality window has been graded yet, so there is no calibration read to "
        "run — a grade cannot exist before its window closes. Nothing to do tonight; this "
        f"tripwire fires with the calibration prompt when the first one lands. Context: {handoff}."
    )
    unavailable_prompt = (
        "The seasonality forward ledger could not be read, so grade progress is UNKNOWN, "
        "not zero. Check the checkout has data/seasonality/nw_forward_ledger.jsonl and "
        f"that build_seasonality_shadow_state ran; do not read this as 'nothing graded'. Context: {handoff}."
    )
    if not counts.get("available"):
        return {
            "key": "first_matured_grade",
            "state": "unavailable",
            "headline": "The seasonality forward ledger could not be read.",
            "why": (
                "Grade progress is unknown, not zero. A missing ledger in a partial "
                "checkout looks exactly like a ledger with nothing on it."
            ),
            "evidence": {"path": LEDGER_PATH, "reason": counts.get("reason")},
            "operator_prompt": unavailable_prompt,
            "handoff_doc": handoff,
        }
    evidence = {
        "registered": counts["registered"],
        "graded": counts["graded"],
        "graded_total": counts["graded_total"],
        "graded_unregistered": counts["graded_unregistered"],
        "closed_out_ungradable": counts["closed_out_ungradable"],
        "grade_status_counts": counts["grade_status_counts"],
        "malformed": counts["malformed"],
        "keyless_rows": counts["keyless_rows"],
        "pending": counts["pending"],
        "pending_without_readable_end": counts["pending_without_readable_end"],
        "earliest_pending_occurrence_end": counts["earliest_pending_occurrence_end"],
        "by_row_type": counts["by_type"],
        "path": LEDGER_PATH,
    }
    if counts["graded"] > 0:
        return {
            "key": "first_matured_grade",
            "state": "fired",
            "headline": (
                f"{counts['graded']} of {counts['registered']} registered seasonality "
                "windows now carry a grade."
            ),
            "why": (
                "This is the first forward evidence the calendar clock has any edge at "
                "all. Everything before it was a registered window with no outcome. "
                "Close-outs (ungradable_missing_prices) are NOT counted here — they are "
                "closed windows with no outcome, so they are not evidence."
            ),
            "evidence": evidence,
            "operator_prompt": fired_prompt,
            "handoff_doc": handoff,
        }
    earliest = counts["earliest_pending_occurrence_end"]
    when = f"the earliest pending window closes {earliest}" if earliest else (
        "no pending window carries a readable close date"
    )
    closed_out = counts["closed_out_ungradable"]
    aside = (
        f" ({closed_out} closed out with no prices — not evidence)" if closed_out else ""
    )
    return {
        "key": "first_matured_grade",
        "state": "waiting",
        "headline": (
            f"{counts['registered']} seasonality windows registered, 0 graded{aside} — {when}."
        ),
        "why": (
            "A grade cannot exist before its window closes, so this is expected-null at "
            "birth rather than a stall. The close date above is when to expect the first "
            "one; nothing before then is news."
        ),
        "evidence": evidence,
        "operator_prompt": waiting_prompt,
        "handoff_doc": handoff,
    }


# ---------------------------------------------------------------------------
# tripwire 3 — the catalyst UI reaching the built page
# ---------------------------------------------------------------------------


def _tw_catalyst_render(root: Path, handoff: str) -> dict[str, Any]:
    waiting_prompt = (
        "The seasonality catalyst mode is present in templates/stock_seasonality.html.j2 "
        "but missing from the built site/stock_seasonality.html. Check the render lane: "
        "find the most recent render.yml run whose head covers the merge that added the "
        "markers, read whether it concluded successfully, and whether one dead link "
        "aborted the publish. Do not re-run an in-flight render. "
        f"Context: {handoff}."
    )
    unavailable_prompt = (
        "The template-vs-page comparison for the seasonality catalyst mode could not be "
        "made in this checkout — this is NOT evidence that the render lane is behind. "
        "Read the tripwire's headline for which side was unreadable and re-run the watch "
        f"in a complete checkout before touching the render lane. Context: {handoff}."
    )
    tpl_path = root / SEASONALITY_TEMPLATE
    page_path = root / SEASONALITY_PAGE
    tpl_text, tpl_err = _read_text(tpl_path)
    if tpl_text is None:
        return {
            "key": "catalyst_render",
            "state": "unavailable",
            "headline": "The seasonality template could not be read.",
            "why": "Without the template there is no expectation to compare the page against.",
            "evidence": {"template": SEASONALITY_TEMPLATE, "reason": tpl_err},
            "operator_prompt": unavailable_prompt,
            "handoff_doc": handoff,
        }
    tpl_markers = [m for m in CATALYST_MARKERS if m in tpl_text]
    if len(tpl_markers) < len(CATALYST_MARKERS):
        # Includes the "no markers at all" case AND the strict-subset case. Both
        # are build-side states, not render-lane states — and the subset case is
        # the one that used to publish a false all-clear: with only ``sx-mode``
        # (a generic mode class) in the template, a page carrying ``sx-mode`` and
        # no catalyst block satisfied ``missing == []`` and the tripwire fired
        # "the catalyst mode is live on the built page". The marker pair exists
        # precisely so a partial render is distinguishable; half a pair cannot
        # make that distinction, so it must not claim to.
        missing_from_template = [m for m in CATALYST_MARKERS if m not in tpl_markers]
        headline = (
            "The catalyst markers are not in the seasonality template."
            if not tpl_markers
            else (
                "The seasonality template carries only part of the catalyst marker set "
                f"(missing: {', '.join(missing_from_template)})."
            )
        )
        return {
            "key": "catalyst_render",
            "state": "unavailable",
            "headline": headline,
            "why": (
                "There is nothing complete to render yet, so a built page without the "
                "full pair is correct rather than behind. This is a build-side state, not "
                "a render-lane state, and a partial marker set cannot tell a partial "
                "render from a complete one."
            ),
            "evidence": {
                "template": SEASONALITY_TEMPLATE,
                "markers": list(CATALYST_MARKERS),
                "template_markers": tpl_markers,
                "missing_from_template": missing_from_template,
            },
            "operator_prompt": unavailable_prompt,
            "handoff_doc": handoff,
        }
    page_text, page_err = _read_text(page_path)
    if page_text is None:
        return {
            "key": "catalyst_render",
            "state": "unavailable",
            "headline": "The built seasonality page is not in this checkout.",
            "why": (
                "The page is a render-lane output; a checkout without it cannot say "
                "whether the render lane is behind."
            ),
            "evidence": {
                "template": SEASONALITY_TEMPLATE,
                "page": SEASONALITY_PAGE,
                "template_markers": tpl_markers,
                "reason": page_err,
            },
            "operator_prompt": unavailable_prompt,
            "handoff_doc": handoff,
        }
    page_markers = [m for m in CATALYST_MARKERS if m in page_text]
    missing = [m for m in tpl_markers if m not in page_markers]
    evidence = {
        "template": SEASONALITY_TEMPLATE,
        "page": SEASONALITY_PAGE,
        "markers": list(CATALYST_MARKERS),
        "template_markers": tpl_markers,
        "page_markers": page_markers,
        "missing_from_page": missing,
    }
    if not missing:
        return {
            "key": "catalyst_render",
            "state": "fired",
            "headline": "The seasonality catalyst mode is live on the built page.",
            "why": (
                "Template and built page agree, so the render lane carried the change "
                "through. Nothing further is owed here."
            ),
            "evidence": evidence,
            "operator_prompt": (
                "The seasonality catalyst mode is now on the built page. Verify it live "
                f"(light + dark + zh) and close the render item in {handoff}."
            ),
            "handoff_doc": handoff,
        }
    return {
        "key": "catalyst_render",
        "state": "waiting",
        "headline": (
            "The seasonality catalyst mode is in the template and not on the built page "
            f"(missing: {', '.join(missing)})."
        ),
        "why": (
            "The divergence itself is the signal — deliberately NOT a stuck-for-N-days "
            "measure, because file mtimes are observer-stamped repo-wide in this fleet and "
            "would lie about age. Seeing this two nights running means the render lane is "
            "wedged, not merely behind."
        ),
        "evidence": evidence,
        "operator_prompt": waiting_prompt,
        "handoff_doc": handoff,
    }


# ---------------------------------------------------------------------------
# tripwire 4 — three deferrals that rot quietly
# ---------------------------------------------------------------------------


def _sub_spa_reality_check(root: Path) -> dict[str, Any]:
    key = "foundation_names_a_validation_symbol_that_does_not_exist"
    prompt = (
        "engine/seasonality/foundation.py declares 'spa_reality_check' as a selection "
        "control, but engine/validation.py defines no such symbol — it defines "
        "reality_check and spa_test. Reconcile the manifest to the real API (or add the "
        "wrapper), and add a test that asserts every declared selection control resolves "
        "to a defined symbol."
    )
    foundation, f_err = _read_text(root / FOUNDATION_PATH)
    validation, v_err = _read_text(root / VALIDATION_PATH)
    if foundation is None or validation is None:
        return {
            "key": key,
            "state": "unavailable",
            "detail": (
                f"{FOUNDATION_PATH}: {f_err or 'ok'}; {VALIDATION_PATH}: {v_err or 'ok'}"
            ),
            "prompt": prompt,
        }
    names_it = "spa_reality_check" in foundation
    defined = bool(re.search(r"^\s*def\s+spa_reality_check\b", validation, re.M)) or bool(
        re.search(r"^\s*spa_reality_check\s*=", validation, re.M)
    )
    siblings = sorted(
        set(re.findall(r"^def\s+(reality_check|spa_test)\b", validation, re.M))
    )
    return {
        "key": key,
        "state": "open" if (names_it and not defined) else "closed",
        "detail": (
            f"{FOUNDATION_PATH} names spa_reality_check={names_it}; "
            f"{VALIDATION_PATH} defines spa_reality_check={defined}, "
            f"defines {siblings or ['<none>']}"
        ),
        "prompt": prompt,
    }


def _synapse_entry_notes(text: str, entry: str) -> str | None:
    """The ``notes:`` body of one synapse artifact entry, by scoped text scan.

    A text scan rather than a YAML parse because this package must stay
    importable on a thin runner with no ``yaml`` installed (see the package
    docstring).  The scan is scoped: it walks from the entry's own key line to
    the next key at the SAME indentation, so it can never pick up a neighbour's
    notes.  Returns ``None`` when the entry is not present at all — which the
    caller reports as ``unavailable``, never as ``closed``.
    """
    lines = text.splitlines()
    start = None
    indent = 0
    pattern = re.compile(r"^(\s*)" + re.escape(entry) + r":\s*$")
    for i, line in enumerate(lines):
        m = pattern.match(line)
        if m:
            start = i
            indent = len(m.group(1))
            break
    if start is None:
        return None
    body: list[str] = []
    in_notes = False
    notes_indent = 0
    for line in lines[start + 1:]:
        stripped = line.strip()
        if stripped and not line.startswith(" " * (indent + 1)):
            break  # left the entry
        current_indent = len(line) - len(line.lstrip())
        if not in_notes:
            if re.match(r"^\s*notes:", line):
                in_notes = True
                notes_indent = current_indent
                after = line.split("notes:", 1)[1].strip()
                if after and after not in {">", "|", ">-", "|-"}:
                    body.append(after)
            continue
        if stripped and current_indent <= notes_indent:
            break  # next key inside the entry
        body.append(stripped)
    return "\n".join(body).strip()


def _sub_synapse_notes_v1(root: Path) -> dict[str, Any]:
    key = "synapse_notes_still_describe_v1_states"
    prompt = (
        f"config/synapse.yml's notes for {SYNAPSE_ENTRY} still describe v1 states while "
        "the producer emits v2. Rewrite the notes to describe what is actually emitted "
        "(the v2 per-state schema and the state_schema envelope field), then re-run "
        "scripts/check_synapse_registry.py."
    )
    text, err = _read_text(root / SYNAPSE_PATH)
    if text is None:
        return {"key": key, "state": "unavailable", "detail": f"{SYNAPSE_PATH}: {err}", "prompt": prompt}
    notes = _synapse_entry_notes(text, SYNAPSE_ENTRY)
    if notes is None:
        return {
            "key": key,
            "state": "unavailable",
            "detail": f"{SYNAPSE_PATH}: entry {SYNAPSE_ENTRY} not found",
            "prompt": prompt,
        }
    # The condition is "do the notes describe v2?", so the detector must test
    # THAT, not three magic substrings. The old test — ``_state_v2`` /
    # ``_state.v2`` / ``state v2`` — read ``open`` for correct rewrites such as
    # "Emits the v2 per-state schema; the envelope declares state_schema." or
    # "…now follow schema version 2", i.e. the follow-up could be done and the
    # tripwire would keep firing forever.
    #
    # ``\bv2\b`` is load-bearing in the other direction: ``_`` is a word
    # character, so it does NOT match inside a producer function name like
    # ``build_neuralweb_state_v2``. Notes that still describe v1 fields and merely
    # name the v2 builder therefore stay ``open``, which is the honest answer.
    v2_match = re.search(r"\bv2\b|\bversion\s+2\b", notes, re.I)
    mentions_v2 = bool(v2_match)
    return {
        "key": key,
        "state": "closed" if mentions_v2 else "open",
        "detail": (
            f"{SYNAPSE_PATH}:{SYNAPSE_ENTRY} notes mention the v2 per-state schema="
            f"{mentions_v2}"
            + (f" (matched {v2_match.group(0)!r})" if v2_match else "")
            + f" ({len(notes)} chars of notes read)"
        ),
        "prompt": prompt,
    }


def _strip_comments_keep_lines(text: str) -> str:
    """Blank out ``#`` comments while preserving every line number and offset.

    ``daily.yml`` is YAML wrapping shell; in both dialects ``#`` at start-of-line
    or after whitespace opens a comment.  Replacing the comment with spaces (not
    deleting it) keeps ``text[:m.start()].count("\\n")`` an honest line number.
    """
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            out.append(" " * len(line))
            continue
        cut = None
        for i, ch in enumerate(line):
            if ch == "#" and i > 0 and line[i - 1] in " \t":
                cut = i
                break
        out.append(line if cut is None else line[:cut] + " " * (len(line) - cut))
    return "\n".join(out)


def _sub_daily_order(root: Path) -> dict[str, Any]:
    key = "daily_workflow_runs_prophet_before_seasonality"
    prompt = (
        ".github/workflows/daily.yml runs build_prophet before build_stock_seasonality, so "
        "the Prophet lane can never read the night's fresh seasonality artifacts. Decide "
        "explicitly: either reorder the nightly, or document why the one-night lag is "
        "correct — and mirror whichever it is into config/dag.yml."
    )
    raw, err = _read_text(root / DAILY_WORKFLOW_PATH)
    if raw is None:
        return {"key": key, "state": "unavailable", "detail": f"{DAILY_WORKFLOW_PATH}: {err}", "prompt": prompt}
    # COMMENTS ARE NOT STEPS. The real workflow's first textual ``build_prophet``
    # is the line "# R2 creds: … build_prophet skips upload gracefully …" — prose,
    # not an invocation. Reading it made the verdict accidental: adding a comment
    # naming build_stock_seasonality above it would flip this sub-check to
    # ``closed`` with nothing about the nightly having changed.
    text = _strip_comments_keep_lines(raw)
    prophet = re.search(r"\bbuild_prophet\b", text)
    seasonality = re.search(r"\bbuild_stock_seasonality\b", text)
    if prophet is None or seasonality is None:
        return {
            "key": key,
            "state": "unavailable",
            "detail": (
                f"{DAILY_WORKFLOW_PATH}: build_prophet found={prophet is not None}, "
                f"build_stock_seasonality found={seasonality is not None}"
            ),
            "prompt": prompt,
        }
    p_line = text[: prophet.start()].count("\n") + 1
    s_line = text[: seasonality.start()].count("\n") + 1
    if p_line >= s_line:
        return {
            "key": key,
            "state": "closed",
            "detail": (
                f"{DAILY_WORKFLOW_PATH}: build_prophet first invoked at line {p_line}, "
                f"build_stock_seasonality first invoked at line {s_line} (comments excluded; "
                "line order, which is only an ordering guarantee inside one sequential job)"
            ),
            "prompt": prompt,
        }
    # Prophet-first. The follow-up asked for a DECISION, not for one particular
    # order, so a documented "the lag is fine" closes it just as a reorder would.
    # The decision record is the token in config/dag.yml — and it is read through
    # the same comment strip as the workflow scan, for the same reason: a token
    # sitting in a ``#`` comment is prose about the decision, not the decision.
    dag_raw, dag_err = _read_text(root / DAG_PATH)
    decided = dag_raw is not None and DAG_ORDER_DECISION_TOKEN in _strip_comments_keep_lines(dag_raw)
    if decided:
        return {
            "key": key,
            "state": "closed",
            "detail": (
                f"{DAILY_WORKFLOW_PATH}: build_prophet first at line {p_line}, "
                f"build_stock_seasonality at line {s_line} — prophet-first is a documented "
                f"decision: {DAG_PATH} carries {DAG_ORDER_DECISION_TOKEN} (one-night lag "
                "accepted; complete-year window family changes only at rollover)"
            ),
            "prompt": prompt,
        }
    return {
        "key": key,
        "state": "open",
        "detail": (
            f"{DAILY_WORKFLOW_PATH}: build_prophet first invoked at line {p_line}, "
            f"build_stock_seasonality first invoked at line {s_line} (comments excluded; "
            "line order, which is only an ordering guarantee inside one sequential job); "
            f"{DAG_PATH} carries no {DAG_ORDER_DECISION_TOKEN} decision record"
            + (f" ({dag_err})" if dag_raw is None else "")
        ),
        "prompt": prompt,
    }


def _tw_deferred_followups(root: Path, handoff: str) -> dict[str, Any]:
    subs = [
        _sub_spa_reality_check(root),
        _sub_synapse_notes_v1(root),
        _sub_daily_order(root),
    ]
    open_subs = [s for s in subs if s["state"] == "open"]
    unavailable_subs = [s for s in subs if s["state"] == "unavailable"]
    evidence = {
        "open": open_subs,
        "checked": subs,
        "n_open": len(open_subs),
        "n_closed": len([s for s in subs if s["state"] == "closed"]),
        "n_unavailable": len(unavailable_subs),
    }
    if open_subs:
        # "1 of 3 still open" reads as "2 are closed". When some sub-checks could
        # not be read, none of them is closed and the headline must say so — the
        # swallowed unavailable count is the same collapse this module exists to
        # prevent, one level down.
        unread = (
            f" ({len(unavailable_subs)} could not be checked)" if unavailable_subs else ""
        )
        return {
            "key": "deferred_followups",
            "state": "fired",
            "headline": (
                f"{len(open_subs)} of {len(subs)} deferred follow-up(s) still open{unread}: "
                + ", ".join(s["key"] for s in open_subs)
            ),
            "why": (
                "None of these break a build, which is exactly why they rot: each one is a "
                "small wrong statement about the system that a later session will read as "
                "true. Each carries its own prompt in evidence.open."
            ),
            "evidence": evidence,
            "operator_prompt": (
                "Clear the open seasonality follow-ups. Each has its own one-line prompt in "
                f"evidence.open of data/seasonality/program_watch.json; context is {handoff}."
            ),
            "handoff_doc": handoff,
        }
    if unavailable_subs:
        return {
            "key": "deferred_followups",
            "state": "unavailable",
            "headline": (
                f"{len(unavailable_subs)} of {len(subs)} deferred follow-up(s) could not be "
                "checked in this checkout."
            ),
            "why": "An unreadable input is not a closed follow-up.",
            "evidence": evidence,
            "operator_prompt": (
                "Re-run the seasonality program watch in a complete checkout — some "
                "follow-up inputs were unreadable."
            ),
            "handoff_doc": handoff,
        }
    return {
        "key": "deferred_followups",
        "state": "waiting",
        "headline": "All deferred seasonality follow-ups are closed.",
        "why": "Nothing here needs the operator. Kept in the watch so a regression re-fires it.",
        "evidence": evidence,
        "operator_prompt": (
            "No open seasonality follow-ups. Nothing to do — this line exists so a "
            "regression re-fires it."
        ),
        "handoff_doc": handoff,
    }


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def evaluate(root: Path, *, asof: str) -> dict[str, Any]:
    """Evaluate every tripwire against the tree at ``root``.

    ``asof`` is stamped, never read from a clock — see the module docstring.
    Never raises: every reader inside is fail-open, and a tripwire that cannot
    read its input reports ``unavailable`` rather than guessing.
    """
    root = Path(root)
    handoff = latest_handoff(root)
    tripwires = [
        _tw_biocatalyst_event_contract(root),
        _tw_first_matured_grade(root, handoff),
        _tw_catalyst_render(root, handoff),
        _tw_deferred_followups(root, handoff),
    ]
    counts = {state: 0 for state in STATES}
    for tw in tripwires:
        counts[tw["state"]] = counts.get(tw["state"], 0) + 1
    return {
        "schema": WATCH_SCHEMA,
        "asof": str(asof),
        "tripwires": tripwires,
        "counts": counts,
    }


#: Package-level alias.  ``engine.seasonality`` re-exports into one flat
#: namespace already crowded with verbs (``forecast``, ``screen_features``,
#: ``coverage_report``), and a bare ``evaluate`` there would say nothing about
#: what it evaluates.  Inside this module ``evaluate`` stays the name.
evaluate_program_watch = evaluate


__all__ = [
    "CATALYST_MARKERS",
    "CONTRACT_TOKENS",
    "LEDGER_PATH",
    "STATES",
    "WATCH_SCHEMA",
    "evaluate",
    "evaluate_program_watch",
    "latest_handoff",
    "read_ledger_counts",
]
