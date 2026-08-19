---
key: PROPHET-LAB-OWNS-NO-CN-LIMIT-PATHS
claim: >
  The Prophet Operator Lab added after the R5 pin (app/prophet_lab.py, wired in
  app/main.py) contains zero references to the China candidate/rank/standout/
  cn_limit planes — it is a fixture-based US/Radar-owned surface
  (WS:PROPHET-US-V4-RECOVERY / WS:LIVE-ENTRY-RADAR) and shares no owner path
  with the CN-Limit program.
falsifier: >
  grep -n -i "china\|cn_limit\|prophet_rank\|standout" app/prophet_lab.py —
  any hit that reads or writes a China candidate/grade/exact-plane store
  falsifies this and reopens the fence question with the lab's owners.
so_what: >
  Treat the lab as fenced adjacency per DEC:CNLI-PROPHET-LAB-FENCED-ADJACENCY:
  no CN-Limit wave touches its owner paths, no CN-Limit store/grader/ontology
  lives inside it, and a read-only CN-Limit consumer in any lab needs a
  separate product/owner decision. Sessions auditing "what changed since the
  R5 pin" can skip the lab when scoping CN-Limit collisions.
kind: architecture
verified_at: 2026-08-19
verified_by: "grep -n -i 'china|cn_limit|prophet_rank|standout' app/prophet_lab.py → no matches at origin/main ccdb62402eb6"
scope:
  - macro
  - app/prophet_lab.py
  - research/cn_limit/
confidence: verified
---

R6 classifies the lab BUILT_NOT_PROVEN inside its own program; that status is
the lab owners' to advance and is irrelevant to CN-Limit gating.
