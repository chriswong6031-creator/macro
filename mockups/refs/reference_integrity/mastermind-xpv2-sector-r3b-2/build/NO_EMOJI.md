# B2-02 — decoded emoji closure guard

Binding sweep of the assembled candidate for literal emoji codepoints, decimal/hex numeric character references that decode into an emoji range, and the decoded DOM text / accessible names / CSS generated content the browser actually paints. Method, ranges, and the three enumerated exclusions are documented in `no_emoji_audit.py`'s module docstring.

| metric | value |
|---|---|
| bytes scanned | **5414676** chars, 32 numeric char-refs |
| byte-scan hits | **0** |
| DOM cells swept | **12** (6 views x EN/ZH) |
| DOM hits | **0** |
| excluded-by-allowlist matches | 45 bytes-side (see docstring for the 3 enumerated codepoints) |
| cells with an empty census in any population | **0** |

[no-emoji] RESULT: ALL GREEN — bytes PASS, 0 DOM hit(s) across 12 (view x lang) cells, 0 populations with an empty census
