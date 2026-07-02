"""Parse the curated cycle seed out of ``site/cycle_data.js`` — pure Python, no node.

``cycle_data.js`` remains the CURATED-TURN SEED STORE (D3-W3.2 mandate): the hand-dated
turning-point history + the archetype / read / falsifier / regimeNote prose live there and
nowhere else.  The engine-backed builder (``scripts/build_cycle.py``) needs that seed to:

  • emit FRAME bands' curated ``turns[]`` + period stats + the A8 leg-length list,
  • carry the dated analyst OPINION prose onto every card (MEASURED + FRAME),
  • run the build-time tolerance assertion (hand ``now.pos`` vs the engine's).

CI has no node, so this is a small tolerant tokenizer for the ONE file's dialect:
unquoted identifier keys, ``"a" + "b"`` string concatenation, ``null``, ``/* */`` + ``//``
comments, trailing commas, ``true``/``false``.  It rejects arbitrary JS (no function calls,
no template literals) — cycle_data.js is a pure data literal by construction.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


# ── comment stripping (string-aware) ─────────────────────────────────────────
def _strip_comments(src: str) -> str:
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        ch = src[i]
        if ch in ('"', "'"):
            j = i + 1
            while j < n and src[j] != ch:
                if src[j] == "\\":
                    j += 2
                    continue
                j += 1
            out.append(src[i:j + 1])
            i = j + 1
            continue
        if ch == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if ch == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


# ── tokenizer ────────────────────────────────────────────────────────────────
_IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$-]*")
_NUM = re.compile(r"-?(?:\d+\.\d+|\.\d+|\d+)(?:[eE][+-]?\d+)?")


def _tokenize(src: str) -> list[tuple[str, object]]:
    toks: list[tuple[str, object]] = []
    i, n = 0, len(src)
    while i < n:
        ch = src[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "{}[]:,+":
            toks.append((ch, ch))
            i += 1
            continue
        if ch in ('"', "'"):
            j = i + 1
            buf: list[str] = []
            while j < n and src[j] != ch:
                if src[j] == "\\":
                    nxt = src[j + 1] if j + 1 < n else ""
                    buf.append({"n": "\n", "t": "\t", "\\": "\\", '"': '"',
                                "'": "'", "/": "/", "r": "\r", "b": "\b"}.get(nxt, nxt))
                    j += 2
                    continue
                buf.append(src[j])
                j += 1
            toks.append(("str", "".join(buf)))
            i = j + 1
            continue
        m = _NUM.match(src, i)
        if m and (ch.isdigit() or (ch == "-" and i + 1 < n and (src[i + 1].isdigit() or src[i + 1] == "."))
                  or (ch == "." and i + 1 < n and src[i + 1].isdigit())):
            txt = m.group(0)
            toks.append(("num", float(txt) if ("." in txt or "e" in txt or "E" in txt) else int(txt)))
            i = m.end()
            continue
        m = _IDENT.match(src, i)
        if m:
            word = m.group(0)
            if word == "true":
                toks.append(("lit", True))
            elif word == "false":
                toks.append(("lit", False))
            elif word == "null":
                toks.append(("lit", None))
            else:
                toks.append(("ident", word))
            i = m.end()
            continue
        raise ValueError(f"_cycle_seed: unexpected char {ch!r} at {i} (…{src[max(0,i-20):i+20]!r})")
    return toks


# ── recursive-descent value parser ───────────────────────────────────────────
class _P:
    def __init__(self, toks: list[tuple[str, object]]):
        self.t = toks
        self.i = 0

    def peek(self) -> tuple[str, object]:
        return self.t[self.i] if self.i < len(self.t) else ("eof", None)

    def next(self) -> tuple[str, object]:
        tok = self.peek()
        self.i += 1
        return tok

    def expect(self, kind: str) -> object:
        k, v = self.next()
        if k != kind:
            raise ValueError(f"_cycle_seed: expected {kind}, got {k} ({v!r})")
        return v

    def value(self):
        k, v = self.peek()
        if k == "{":
            return self.obj()
        if k == "[":
            return self.arr()
        if k == "str":
            return self.concat_str()
        if k in ("num", "lit"):
            self.next()
            return v
        if k == "ident":
            # a bare identifier value (e.g. a phase enum written unquoted) → its name
            self.next()
            return v
        raise ValueError(f"_cycle_seed: unexpected token {k} ({v!r})")

    def concat_str(self) -> str:
        parts = [self.expect("str")]
        while self.peek()[0] == "+":
            self.next()
            if self.peek()[0] != "str":
                raise ValueError("_cycle_seed: '+' only supports string concatenation in this dialect")
            parts.append(self.expect("str"))
        return "".join(parts)

    def obj(self) -> dict:
        self.expect("{")
        out: dict = {}
        while self.peek()[0] != "}":
            k, v = self.next()
            key = v if k in ("ident", "str") else None
            if key is None:
                raise ValueError(f"_cycle_seed: bad object key {k} ({v!r})")
            self.expect(":")
            out[key] = self.value()
            if self.peek()[0] == ",":
                self.next()
        self.expect("}")
        return out

    def arr(self) -> list:
        self.expect("[")
        out: list = []
        while self.peek()[0] != "]":
            out.append(self.value())
            if self.peek()[0] == ",":
                self.next()
        self.expect("]")
        return out


def _extract_assignment(src: str, name: str) -> str:
    """Return the literal RHS text of ``window.<name> = <literal>;`` (balanced)."""
    key = f"window.{name}"
    start = src.find(key)
    if start < 0:
        raise ValueError(f"_cycle_seed: {key} not found")
    eq = src.find("=", start + len(key))
    j = eq + 1
    while j < len(src) and src[j].isspace():
        j += 1
    open_ch = src[j]
    close_ch = {"[": "]", "{": "}"}.get(open_ch)
    if close_ch is None:
        raise ValueError(f"_cycle_seed: {key} RHS is not an object/array literal (got {open_ch!r})")
    depth, k, in_str, esc, quote = 0, j, False, False, ""
    while k < len(src):
        ch = src[k]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
        else:
            if ch in ('"', "'"):
                in_str, quote = True, ch
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return src[j:k + 1]
        k += 1
    raise ValueError(f"_cycle_seed: unbalanced literal for {key}")


def load_seed(path: str | Path) -> dict:
    """Parse ``cycle_data.js`` → {"meta": {...}, "cycles": [...], "by_id": {...}}."""
    raw = Path(path).read_text(encoding="utf-8")
    src = _strip_comments(raw)
    cycles = _P(_tokenize(_extract_assignment(src, "CYCLES"))).value()
    meta = _P(_tokenize(_extract_assignment(src, "CYCLE_META"))).value()
    if not isinstance(cycles, list):
        raise ValueError("_cycle_seed: window.CYCLES did not parse to a list")
    by_id = {c["id"]: c for c in cycles if isinstance(c, dict) and "id" in c}
    return {"meta": meta, "cycles": cycles, "by_id": by_id}


if __name__ == "__main__":
    import sys
    seed = load_seed(sys.argv[1] if len(sys.argv) > 1 else "site/cycle_data.js")
    print(json.dumps({"n_cycles": len(seed["cycles"]),
                      "ids": list(seed["by_id"]),
                      "meta_xDomain": seed["meta"].get("xDomain"),
                      "sample_semis_turns": len(seed["by_id"]["semis"]["turns"])}, indent=2))
