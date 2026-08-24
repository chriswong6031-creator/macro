# K2-B Institutional Intelligence — Manager Research Intent

This is a pure, read-only contract for describing manager-complex observations. It is not an institutional data store, a 13F replacement, a trading signal, a ranker, an entry gate, or a product/runtime adapter.

The four separate planes are `manager_research_intent`, `fund_flow_pressure`, `theme_capital_rotation`, and `institutionalization_saturation`. They may be reported together but are never netted into a score. `form_13f` observations require report-period, filing, publication, and knowability clocks; before knowability they are `NOT_KNOWABLE`, and they can never be `live_flow`.

Manager complex and vehicle identities are epoch-bound. The independent count is a distinct `(manager_complex_id, manager_identity_epoch)` count, so vehicles at one complex cannot multiply consensus. Passive, systematic, overlay, leveraged, and synthetic vehicles cannot emit manager research intent. Mechanical flow stays in its own plane and compiles to `MECHANICAL_FLOW_NOT_INTENT`.

The sole provenance surface is a K1-style pointer (`reference_id`, owner-native object id, accession, source URL and clocks). Owner payloads are rejected. Corrections append a new observation that supersedes an earlier one. Reliability is a descriptive, shrunk posterior keyed by manager complex × domain × horizon × action; it has no oracle semantics. All five authority axes are false.
