Effects system examples and rationale

Overview
========
The new effects system normalizes all in-story side-effects into typed effect objects. This makes effects explicit, composable, and easy to extend.

New JSON examples
=================
Single stat change (delta):

{
  "effects": [
    { "type": "stat", "target": "honor", "value": 10 }
  ]
}

Set a flag:

{
  "effects": [
    { "type": "flag", "target": "izuna_dead", "value": true }
  ]
}

Inventory changes:

{
  "effects": [
    { "type": "inventory", "action": "add", "item": "med_kit", "quantity": 1 }
  ]
}

Relationship adjustments:

{
  "effects": [
    { "type": "relationship", "target": "hashirama", "value": 5 }
  ]
}

Legacy compatibility
====================
Legacy format (object of stat deltas) is still supported:

{
  "effects": { "honor": 10, "compassion": -5 }
}

Why this scales better
======================
- Explicit typing: each effect declares its intent (`type`) which avoids ad-hoc key conventions.
- Extensible: add new `type` values (e.g., `quest`, `xp`, `scene_tag`) without changing processing code structure.
- Composable: a list of effects can include many different side-effects in a predictable order.
- Testable and debuggable: effect items can be inspected, logged, or replayed by tools.

Integration notes
=================
- The engine exposes `process_effects(effects)` in `engine/effects.py`.
- Templates now receive `inventory` and `relationships` via the session for easy display/debugging.
- Effects may also set flags; use `flag` effects or the `flags` top-level key for backward compatibility.
