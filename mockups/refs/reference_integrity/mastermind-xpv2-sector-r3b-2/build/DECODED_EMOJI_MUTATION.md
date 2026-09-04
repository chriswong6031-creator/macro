# decoded_emoji_audit.py — mutation proof

The mutation reinserts `&#128202;` only in an in-memory copy of the Moving `Track record / 跟踪记录` heading. The governed source and proposal are never changed.

**Pristine baseline green:** YES (0 violations; 12/12 rendered cells)

**Mutation produced one semantic-owner red:** YES

**Violation owners:** `['moving.track_record_heading']`

**Axis counts:** `{'accessible_name': 4, 'decimal_numeric_entity': 2, 'rendered_dom_text': 2}`

**Rendered DOM languages hit:** `['en', 'zh']`

**Accessible-name languages hit:** `['en', 'zh']`

## Mutated-copy violations
- `decimal_numeric_entity` owner `moving.track_record_heading`: `&#128202;`
- `decimal_numeric_entity` owner `moving.track_record_heading`: `&#128202;`
- `rendered_dom_text` owner `moving.track_record_heading` at en:moving: `['📊']`
- `accessible_name` owner `moving.track_record_heading` at en:moving: `['📊']`
- `accessible_name` owner `moving.track_record_heading` at en:moving: `['📊']`
- `rendered_dom_text` owner `moving.track_record_heading` at zh:moving: `['📊']`
- `accessible_name` owner `moving.track_record_heading` at zh:moving: `['📊']`
- `accessible_name` owner `moving.track_record_heading` at zh:moving: `['📊']`
