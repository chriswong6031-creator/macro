"""engine/prophet_lab — the Prophet Operator Lab projection (LAB-0 §1, §3-§5).

A presentation/projection layer over canonical Radar output.  Read / filter /
join / decorate only — see ``engine/prophet_lab/contracts.py`` for the frozen
shapes and ``engine/prophet_lab/response.py`` for the entry point
(:func:`build_lab_response`) served by ``app/prophet_lab.py``.
"""
from __future__ import annotations

from engine.prophet_lab.response import LabRoots, build_lab_response

__all__ = ["LabRoots", "build_lab_response"]
