#!/usr/bin/env python3
"""Reproduce the TFG-1 development separator falsifier measurement.

MEASUREMENT EVIDENCE ONLY - this is not the TFG-1 compiler implementation and nothing
imports it. It exists so Sol can independently re-derive the 113-vs-110 structural
separator diff that stopped the TFG-1 wave, without trusting a prose claim.

It reads only the 16 already-open TFG-0 development revisions named in the frozen
selection receipt. It never touches the eight embargoed holdout revisions (ranks 17-24),
makes no model call, and writes nothing outside the path given by --out.

    python3 research/earnings_intelligence/e3/tfg1_separator_falsifier_measurement.py
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
E3 = ROOT / "research/earnings_intelligence/e3"
TX_BASE = "https://app.mastermind-x.com/data/tx"
UA = "Mastermind TFG-1 falsifier measurement"
HOUSEKEEPING = {"operator", "ir"}

# Case-sensitive even under IGNORECASE cues, and period-free, so a name can never run
# across a sentence boundary into a following return clause.
_NAME = r"(?-i:[A-Z][A-Za-zÀ-ɏ'’\-]*(?:\s+[A-Z][A-Za-zÀ-ɏ'’\-]*){0,3})"

# A question is attributed to a named person within one sentence.
_ATTRIB = re.compile(
    r"\bquestions?\b[^.?!]{0,60}?\b(?:from|of|the\s+line\s+of)\s+(?:the\s+line\s+of\s+)?"
    r"(?P<name>" + _NAME + r")",
    re.IGNORECASE,
)
# "One moment for our first question. It's from Richard Garchitorena with Barclays."
_ATTRIB_CONT = re.compile(
    r"\bquestions?\b[^.?!]{0,40}[.]\s*(?:It(?:'s|’s| is)|This is)\s+from\s+"
    r"(?P<name>" + _NAME + r")",
    re.IGNORECASE,
)
# Named continuation handoff: "We'll move on now to Chris Muller with Citizens JMP."
_CONTINUE = re.compile(
    r"\b(?:we(?:'ll|’ll| will| shall)?\s+)?(?:now\s+)?(?:mov(?:e|ing)\s+on|go)\s+"
    r"(?:on\s+)?(?:now\s+)?to\s+(?P<name>" + _NAME + r")",
    re.IGNORECASE,
)
# Returns to management and opening prepared-speaker handoffs are never separators.
_RETURN = re.compile(
    r"\b(?:turn|hand|pass|give|send)\b[^.?!]{0,60}?\bback\b|\bback\s+(?:over\s+)?to\b"
    r"|\b(?:turn|hand)\s+(?:the\s+)?(?:call|conference|floor|program|meeting)\s+over\s+to\b",
    re.IGNORECASE,
)


def canon(payload: dict) -> str:
    """TFG-0's replay convention. NOT sha256 of the raw decompressed body."""
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def norm(v: object) -> str:
    return " ".join(str(v or "").split())


def _return_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    for m in _RETURN.finditer(text):
        end = text.find(".", m.end())
        spans.append((m.start(), len(text) if end < 0 else end))
    return spans


def handoff_name(text: object) -> str | None:
    """The named questioner of a question-bearing handoff, else None."""
    t = norm(text)
    spans = _return_spans(t)
    hits = []
    for rx in (_ATTRIB, _ATTRIB_CONT, _CONTINUE):
        for m in rx.finditer(t):
            pos = m.start("name")
            if any(a <= pos <= b for a, b in spans):
                continue
            hits.append((pos, m.group("name").strip(" ,.")))
    if not hits:
        return None
    hits.sort()
    return hits[-1][1]


def is_housekeeping(seg: dict) -> bool:
    role = norm(seg.get("role")).casefold()
    speaker = norm(seg.get("speaker")).casefold()
    return role in HOUSEKEEPING or speaker == "operator" or speaker.endswith(" operator")


def next_source_turn(segs: list, i: int) -> int | None:
    for j in range(i + 1, len(segs)):
        if norm(segs[j].get("role")).casefold() in HOUSEKEEPING:
            continue
        if not norm(segs[j].get("speaker")):
            continue
        return j
    return None


def separators(segs: list) -> list[int]:
    """Question-bearing named handoff immediately followed by a non-housekeeping turn."""
    return [
        i for i, s in enumerate(segs)
        if is_housekeeping(s) and handoff_name(s.get("text")) and next_source_turn(segs, i) is not None
    ]


def fetch(ticker: str, txid: str, cache: Path | None) -> dict:
    if cache:
        hit = cache / f"{ticker}_{txid}.json"
        if hit.exists():
            return json.loads(hit.read_text(encoding="utf-8"))
    req = Request(f"{TX_BASE}/{ticker}/{txid}.json.gz", headers={"User-Agent": UA})
    with urlopen(req, timeout=60) as r:
        payload = json.loads(gzip.decompress(r.read()).decode("utf-8"))
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
        (cache / f"{ticker}_{txid}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    time.sleep(0.2)
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, default=None, help="optional body cache directory")
    ap.add_argument("--out", type=Path, default=None, help="write the measured matrix as JSON")
    args = ap.parse_args()

    selection = json.loads((E3 / "tfg0_transcript_format_development_corpus_selection.json").read_text())
    gold = {c["pair"]: c for c in json.loads(
        (E3 / "tfg0_development_boundary_identity_adjudication.json").read_text())["per_call"]}

    replayed = detected = frozen_total = 0
    rows, omissions = [], []
    for row in selection["selected"]:
        pair, ticker, txid = row["pair"], row["ticker"], row["transcript_id"]
        payload = fetch(ticker, txid, args.cache)
        actual = canon(payload)
        if actual != row["body_sha256"]:
            print(f"::error title=tfg1-replay::{pair} canonical replay mismatch {actual}", flush=True)
            return 2
        replayed += 1
        segs = payload["segments"]
        got = separators(segs)
        want = sorted(gold[pair]["true_question_handoff_indices"])
        detected += len(got)
        frozen_total += len(want)
        extra = sorted(set(got) - set(want))
        missed = sorted(set(want) - set(got))
        rows.append({"pair": pair, "frozen": want, "detected": got,
                     "omitted_by_frozen_receipt": extra, "missed_by_detector": missed,
                     "frozen_source_clean": gold[pair]["source_clean_for_full_call_reconstruction"]})
        for i in extra:
            j = next_source_turn(segs, i)
            named = handoff_name(segs[i].get("text"))
            omissions.append({
                "pair": pair, "segment_index": i, "operator_named": named,
                "next_speaker": norm(segs[j].get("speaker")),
                "next_first_utterance": norm(segs[j].get("text"))[:160],
                "questioner_class": ("direct"
                                     if named and named.casefold() == norm(segs[j].get("speaker")).casefold()
                                     else "unresolved"),
            })

    missed_total = sum(len(r["missed_by_detector"]) for r in rows)
    print(f"byte replay (canonical)     : {replayed}/16")
    print(f"frozen structural separators: {frozen_total}")
    print(f"detected structural separators: {detected}")
    print(f"false negatives vs frozen gold: {missed_total}")
    print(f"separators omitted by frozen receipt: {len(omissions)}")
    for o in omissions:
        print(f"  {o['pair']} #{o['segment_index']}: operator named {o['operator_named']!r}"
              f" -> next speaker {o['next_speaker']!r} [{o['questioner_class']}]")
    if args.out:
        args.out.write_text(json.dumps(
            {"schema": "tfg1.separator_falsifier_measurement.v1",
             "byte_replayed": replayed, "frozen_separators": frozen_total,
             "detected_separators": detected, "false_negatives": missed_total,
             "omissions": omissions, "per_call": rows}, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
