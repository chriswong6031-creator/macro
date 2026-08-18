---
key: GOVREV-AGENCY-STRINGIFY-IS-COLLECTOR-THEN-ACTION-OMIT
claim: >
  Live workspace.json (bundle grw2-dd9d7af893a7f3c773909351, 500 events) has
  two agency shapes: 478 action rows with agency {name:null, subagency:null}
  because award_action_versions.parquet omits awarding_agency from
  source_field_presence, and 22 snapshot rows whose agency.name is a Python
  repr of the nested USAspending awarding_agency object (toptier/subtier names
  intact, top-level name None). Compact HTML then drops name/subagency, so
  first paint was agency: {}. D1 agencyName() rejected any string starting
  with "{" or containing ": None", which discarded the 22 real names.
falsifier: >
  python reading data/government_revenue/workspace.json for
  govws-a6c70850a9cbdce9fa3e7f3b shows a structured department_name, or
  award_action_versions.parquet for CONT_TX_9700_-NONE-_HC101319C0006_P00032
  has a non-null awarding_agency declared in source_field_presence.
so_what: >
  Heal canonicalize_agency() in engine/government_revenue/award_events.py
  (ast.literal_eval + USAspending toptier/subtier whitelist) and inherit the
  award-snapshot agency onto actions that omitted the field. Do not parse
  Python in the browser. Do not rewrite collector hashes; do not treat
  funding_agency as awarding agency.
kind: data
verified_at: 2026-08-17
verified_by: >
  venv python on HEAD workspace.json + award_action_versions.parquet +
  award_event_snapshots.parquet for HC101319C0006/P00032: action awarding_agency
  <NA>, presence list omits it; snapshot awarding_agency is the DISA/DoD
  Python literal; 478 empty vs 22 repr in the 500-event tape.
scope: [macro, government-revenue-foresight]
confidence: verified
---

P00032 is an action-rail omission plus a snapshot-rail stringify, not a missing
USAspending fact. The official award snapshot for the same award_key already
carries Department of Defense / DISA.
