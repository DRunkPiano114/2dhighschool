# CLAUDE.md

## Test Sync Rule

Tests live in `tests/`. **When you modify logic in `src/sim/`, you MUST also update or add corresponding tests.** A task is not complete until tests pass.

What triggers a test update:
- Change an algorithm (grouping, speaker selection, energy, pressure, concern dedup, etc.)
- Change state update logic (energy deltas, decay, regression, etc.)
- Change qualitative threshold mappings
- Add/remove/rename fields on models used in tested functions
- Change memory retrieval, event queue, or narrative formatting logic

Write tests based on what a function is **supposed to do** (its design intent), not by mirroring its current implementation. Testing against the code as-is can cement bugs into passing tests.

Run `uv run python -m pytest` before considering any code change complete.

## JSON Quoting Rule

JSON files under `canon/` contain Chinese text (the 5 worldbook JSONs under `canon/worldbook/` and the character profiles under `canon/cast/profiles/`). Use ASCII `"` (U+0022) for all JSON structural quotes (field names, string delimiters). Chinese curly quotes `""` (U+201C/201D) may only appear **inside** string content. After editing any JSON file, validate with `python -m json.tool`.
