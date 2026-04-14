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

## Documentation Sync Rule

Detailed technical documentation lives in `ARCHITECTURE.md`. **Every time you modify code, you MUST also update that file to reflect the changes.** A task is not complete until the doc is in sync.

What triggers a doc update:
- Add/remove/rename a module or file
- Change a data model (add/remove/rename fields)
- Change the simulation loop, phase logic, or orchestration flow
- Change algorithms (grouping, speaker selection, energy, pressure, exam scoring, etc.)
- Add/change LLM call types, templates, or temperature/token settings
- Add/change configuration options
- Change file storage format, paths, or initialization logic

The goal: a stranger should be able to fully understand this project's technical implementation, engineering details, and framework logic by reading `ARCHITECTURE.md` alone, without looking at source code.

## JSON Quoting Rule

JSON files under `data/` contain Chinese text. Use ASCII `"` (U+0022) for all JSON structural quotes (field names, string delimiters). Chinese curly quotes `""` (U+201C/201D) may only appear **inside** string content. After editing any JSON file, validate with `python -m json.tool`.
