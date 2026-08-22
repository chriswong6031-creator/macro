#!/usr/bin/env python3
"""Build readable, byte-replayable evidence catalogs from canonical SEC bytes."""
from __future__ import annotations

import argparse
from hashlib import sha256
import html
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence


_TEXT_NODE = re.compile(br">([^<>]+)<", re.DOTALL)
_SPACE = re.compile(r"\s+")
_STYLE_HINTS = ("font-family:", "font-size:", "text-decoration:", "@media ")


def _chunks(start: int, value: bytes, maximum: int = 700) -> Iterable[tuple[int, bytes]]:
    cursor = 0
    while cursor < len(value):
        stop = min(len(value), cursor + maximum)
        if stop < len(value):
            boundary = max(
                value.rfind(token, cursor + 80, stop)
                for token in (b". ", b"; ", b", ", b" ")
            )
            if boundary >= cursor + 80:
                stop = boundary + 1
        chunk = value[cursor:stop]
        yield start + cursor, chunk
        cursor = stop


def evidence_segments(
    *, packet_id: str, document_sha256: str, source: bytes
) -> list[dict[str, Any]]:
    if sha256(source).hexdigest() != document_sha256:
        raise ValueError("source bytes do not match canonical document SHA-256")
    spans: list[tuple[int, bytes]] = []
    for match in _TEXT_NODE.finditer(source):
        raw = match.group(1)
        left = len(raw) - len(raw.lstrip())
        right = len(raw.rstrip())
        if right <= left:
            continue
        spans.extend(_chunks(match.start(1) + left, raw[left:right]))
    # Plain-text fall-back; HTML/XML inputs normally use the branch above.
    if not spans:
        offset = 0
        for line in source.splitlines(keepends=True):
            stripped = line.strip()
            if stripped:
                start = offset + line.index(stripped)
                spans.extend(_chunks(start, stripped))
            offset += len(line)
    output: list[dict[str, Any]] = []
    for start, raw in spans:
        try:
            excerpt = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        display = _SPACE.sub(" ", html.unescape(excerpt)).strip()
        if len(display) < 12 or sum(char.isalpha() for char in display) < 8:
            continue
        if any(hint in display.lower() for hint in _STYLE_HINTS):
            continue
        end = start + len(raw)
        segment_id = "span_" + sha256(
            f"{packet_id}|{start}|{end}|{sha256(raw).hexdigest()}".encode()
        ).hexdigest()
        output.append({
            "segment_id": segment_id,
            "display_text": display,
            "evidence": {
                "document_sha256": document_sha256,
                "start": start,
                "end": end,
                "excerpt": excerpt,
            },
        })
    return output


def build_catalog(packet_index: Mapping[str, Any], root: Path) -> dict[str, Any]:
    packets: list[dict[str, Any]] = []
    for packet in packet_index.get("packets") or []:
        source_path = Path(root) / str(packet["source_path"])
        source = source_path.read_bytes()
        packets.append({
            **dict(packet),
            "segments": evidence_segments(
                packet_id=str(packet["packet_id"]),
                document_sha256=str(packet["document_sha256"]),
                source=source,
            ),
        })
    if len(packets) != 20:
        raise ValueError(f"evidence catalog requires exactly twenty packets; got {len(packets)}")
    return {
        "schema": "mastermind.dislocation_p0.a1r_evidence_catalog.v1",
        "packets": packets,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-index", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--packet-out-dir", type=Path)
    args = parser.parse_args(argv)
    index = json.loads(args.packet_index.read_text(encoding="utf-8"))
    catalog = build_catalog(index, args.root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(catalog, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    if args.packet_out_dir is not None:
        args.packet_out_dir.mkdir(parents=True, exist_ok=True)
        for packet in catalog["packets"]:
            slot = int(packet["slot"])
            target = args.packet_out_dir / f"{slot:02d}_evidence.json"
            target.write_text(
                json.dumps(
                    {"schema": catalog["schema"], "packet": packet},
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )
    print(json.dumps({
        "packets": len(catalog["packets"]),
        "segments": sum(len(packet["segments"]) for packet in catalog["packets"]),
        "sha256": sha256(args.out.read_bytes()).hexdigest(),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
