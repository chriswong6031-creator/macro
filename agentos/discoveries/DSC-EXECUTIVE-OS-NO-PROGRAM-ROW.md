---
key: EXECUTIVE-OS-NO-PROGRAM-ROW
claim: >
  The Executive OS has no row in config/mastermind_programs.yml, so the org's largest live
  infrastructure program is invisible to the 59-program semantic registry and to anything
  generated from it.
falsifier: >
  python3 -c "import yaml; d=yaml.safe_load(open('config/mastermind_programs.yml'))['programs']; print([k for k,v in d.items() if 'executive' in str(v).lower()])"
  — a non-empty result disproves this.
so_what: >
  A workstream for the Executive OS cannot currently declare a valid program parent, and any
  program-level rollup silently under-reports the org. Add a program row before modelling
  Executive OS work in the Agent OS, and treat this class of gap as a registry defect rather
  than working around it with an approximate parent.
kind: data
verified_at: 2026-08-12
verified_by: "python3 scan over config/mastermind_programs.yml programs dict (59 keys) — zero matches for 'executive'"
scope: [macro, "config/mastermind_programs.yml", "WS:AGENT-OS"]
confidence: verified
---

## Detail

The programs registry holds 59 keys covering Prophet, Terminal, Portfolio, China, Neural Web,
and infrastructure programs. None covers the Executive OS, despite five merged PRs (#20, #21,
#24, #25 and the Phase 1C bootstrap fix) and a dedicated `control_plane/` module set. This was
found while seeding Agent OS workstreams: the model refused to represent the work rather than
attaching it to an approximate parent, which is the intended behavior of a validated `program`
field.

## Suggested repair

Add an `executive-os` program row owned by the executive category, with `owns` covering
Mastermind `control_plane/executive_*.py` and `config/strategic_state.yml`. Not done here —
the registry has its own assigned workstream and this is a one-row change for that owner.
