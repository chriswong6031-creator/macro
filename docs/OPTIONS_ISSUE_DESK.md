# Private Options Issue Desk

The authenticated `GET /api/options/issue-desk` and `POST /api/options/issue-desk/reviews`
endpoints are private Macro API surfaces. Terminal proxies them only for a verified,
canonical operator; neither endpoint is a public static/R2 artifact.

State defaults to `$MACRO_API_STATE_DIR/options_issue_desk` unless
`OPTIONS_ISSUE_DESK_STATE_DIR` is set. Set an optional explicit UUID restriction with
`OPTIONS_ISSUE_DESK_OPERATOR_USER_ID` (or the existing `SUPABASE_OPERATOR_USER_ID`);
otherwise the canonical `/api/me` operator email allowlist is authoritative. No new
production owner environment value is required.

The exact payload and immutable receipt rules are frozen in
`research/OPTIONS_ISSUE_DESK_R62_PREREG.md` and JSON Schemas in `contracts/options/`.
The API intentionally has no daily workflow or public R2 publication: it is a
request-driven private ledger and does not change Macro rankings or execution authority.
