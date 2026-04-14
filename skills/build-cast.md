# Cast Builder

Interactive workflow for replacing or editing the simulated class's characters.

**Audience**: a coding agent (Claude Code, Cursor, Codex, …) invoked by a user
who wants to customize the cast without touching code.

**User trigger** (from the project README):
> I want to use this project to simulate my own class. Please follow the workflow in `skills/build-cast.md` to guide me through editing the characters.

---

## Hard constraints — read these before doing anything

1. **Do not add, remove, or rename `agent_id` slots.** The codebase hardcodes
   the 10 student slots and the teacher slot (`he_min`) in:
   - `scripts/init_world.py` — `PRESET_RELATIONSHIPS`
   - `src/sim/world/scene_generator.py` — `DORMS` map and `"he_min"` magic
   - `src/sim/interaction/orchestrator.py` — `"he_min"` teacher hook
   - `src/sim/world/homeroom_teacher.py` — `"he_min"` magic
   - `web/src/components/world/CharacterSprite.ts` — sprite color per `agent_id`

   Replace the **content** of each slot, never the slot itself. If the user
   asks to add/remove agents or rename ids, decline and tell them it requires
   coordinated edits across the files above — out of scope for this skill.

2. **Touch only files under `data/`.** No source code edits.

3. **Schema source of truth is `src/sim/models/agent.py`.** Re-read it every
   time this skill runs. Never hardcode field lists in this file — they will
   drift.

4. **Don't change `agent_id`, `role`, `dorm_id`, `seat_number` unless the user
   explicitly asks.** These are structural; the rest is creative.

---

## Phase 0 — Setup (do this first, every time)

### 0a. Ask the user's working language

Character content (`name`, `backstory`, `speaking_style`,
`behavioral_anchors`, `joy_sources`, etc.) can be in any language. The
project's default cast is Chinese, but the user may want their own cast in
English, Japanese, or anything else.

Use `AskUserQuestion`:
> *"What language do you want to use for our conversation and for the
> character content? (e.g., English, 中文, 日本語)"*

After they answer, conduct **all** subsequent dialogue in that language, and
write the character JSON values in that language. The example prompts shown
in this file (Phases 3, 4, 6) are written in Chinese for illustration —
translate them to the user's chosen language when actually asking.

**Schema-locked exceptions** — these field values are Pydantic Literals and
must stay in Chinese regardless of working language:

- `academics.overall_rank` ∈ {`top`, `上游`, `中上`, `中游`, `中下`, `下游`}
- `academics.target` ∈ {`985`, `211`, `一本`, `二本`, `没想过`}
- `family_background.pressure_level` ∈ {`高`, `中`, `低`}

Tell the user upfront, in their language:
> *"Heads up: a few rank/target/pressure fields are locked to Chinese values
> like '中上' or '985' — schema constraint, would need code edits to change.
> Everything else (names, backstory, dialogue) follows your chosen language."*

### 0b. Discover the schema

Read these files and tell the user what you found in one sentence each:

- `src/sim/models/agent.py` — extract every field of `AgentProfile`,
  `Academics`, `FamilyBackground`, `BehavioralAnchors`; list the closed Enum
  values (`Gender`, `Role`, `OverallRank`, `AcademicTarget`, `PressureLevel`).
- `data/characters/he_min.json` — example: teacher
- `data/characters/jiang_haotian.json` — example: extroverted student

Then say: *"Schema loaded. Ready to start. Which mode?"*

---

## Phase 1 — Pick mode

Use `AskUserQuestion`:

- **Edit one** — change some fields of a single character (most common)
- **Replace one** — completely rewrite one slot's persona, keep its `agent_id`
- **Replace all** — rewrite all 11 slots (long session, save incrementally)

If "replace all", warn the user this is ~30–60 minutes of back-and-forth and
offer to checkpoint after each character.

---

## Phase 2 — Identify the slot

- List existing slots: `ls data/characters/*.json`
- For "edit one" / "replace one": ask which slot
- For "replace all": work in this order — `he_min` first (teacher sets the
  classroom tone), then students by current `seat_number` ascending

---

## Phase 3 — Collect fields in batches

**Never ask all fields at once.** Use `AskUserQuestion` per batch. For free-
text fields (`speaking_style`, `backstory`, the three `behavioral_anchors`
lists) let the user write a rough draft, then offer to polish.

### Batch A — Identity
- `name` (中文姓名)
- `gender` — Enum: `male` / `female`
- `position` — e.g. `班长` / `体育委员` / `学习委员` / null
- `personality` — list of ≤3 形容词
- (skip `agent_id`, `role`, `dorm_id`, `seat_number` — keep existing)

### Batch B — Speaking style
- `speaking_style` — 100–200 字, concrete tics (口头禅, 标志动作, 收敛习惯).
  Show the user the existing example for this slot or `jiang_haotian` if
  starting fresh.

### Batch C — Academics
- `academics.overall_rank` — Enum: `top` / `上游` / `中上` / `中游` / `中下` / `下游`
- `academics.strengths` — list of subjects
- `academics.weaknesses` — list of subjects
- `academics.study_attitude` — short free text
- `academics.target` — Enum: `985` / `211` / `一本` / `二本` / `没想过`
- `academics.homework_habit` — short free text

### Batch D — Family background
- `family_background.pressure_level` — Enum: `高` / `中` / `低`
- `family_background.expectation` — short free text (parents' hopes)
- `family_background.situation` — paragraph (家庭构成, 经济, 隐藏的张力)

### Batch E — Inner life
- `long_term_goals` — list (3–5 typical)
- `inner_conflicts` — list (1–3 typical)
- `joy_sources` — list (3–5 typical, concrete moments not abstract states —
  e.g. "打篮球进了三分的时候" not "运动")

### Batch F — Behavioral anchors (these directly drive LLM imitation)
- `behavioral_anchors.must_do` — list ≤5, observable behaviors
- `behavioral_anchors.never_do` — list ≤5
- `behavioral_anchors.speech_patterns` — list ≤6, concrete catchphrases

Always show the user one example from `jiang_haotian.json` or `he_min.json`
before asking — these fields are easy to write generically and useless if so.

### Batch G — Backstory
500–1000 字. Don't ask for it cold. Walk through prompts:
- 家庭情况和氛围？
- 课外生活？爱好、装备、网上常去哪？
- 和班里其他同学有什么具体关系？(座位邻居, 室友, 对头)
- 有什么不能告诉别人的挣扎？
- 选科倾向 / 未来打算？

Then assemble a draft, show it, iterate. Aim for the texture of
`jiang_haotian.json`'s backstory — concrete details (王者荣耀钻石段位, AJ 球鞋,
保温杯, 暗格水杯藏手机), not abstract personality summaries.

---

## Phase 4 — Cross-references (only for "replace all" or when ≥2 slots changed)

After all updated slots are drafted, run a relationship pass:

1. List the new cast and ask which pairs have meaningful relationships.
2. For each pair: "A 和 B 是什么关系？强度？正向还是负向？"
3. Weave the answer into BOTH characters' `backstory` (one sentence each
   minimum). Mention each other by `name`.
4. Update `scripts/init_world.py`'s `PRESET_RELATIONSHIPS` list to match.
   Format: `(agent_a, agent_b, label, a_fav, b_fav, a_trust, b_trust)`.
   Typical favorability: 5–20 (positive), -5 to -15 (negative). Trust: 0–15.
   Common labels: `"同桌"` / `"室友"` / `"前后桌"` / `"对头"`.

   This is the **one** code edit this skill is allowed to make. Show the user
   the exact diff before writing.

---

## Phase 5 — Validate before writing

After each character's draft is complete, before saving:

1. **JSON structural check** (project hard rule from `CLAUDE.md`):
   ```bash
   python -m json.tool data/characters/<agent_id>.json > /dev/null
   ```

2. **Pydantic round-trip** (must succeed):
   ```bash
   uv run python -c "from src.sim.models.agent import AgentProfile; AgentProfile.model_validate_json(open('data/characters/<agent_id>.json').read())"
   ```

3. **Soft warnings** (report, don't block):
   - `seat_number` collides with another student
   - `backstory` references a name that isn't any current `name` field
   - `behavioral_anchors.must_do` / `never_do` is empty (loses LLM steering)

If validation fails, fix and re-validate. Don't move on with a broken file.

---

## Phase 6 — Side files (ask, default skip)

After characters are saved, ask the user:

- *"Backstory 里出现了非中文的家庭称呼吗？比如 papa / mama / 外婆昵称？"*
  → If yes, update `data/name_aliases.json` (`alias` → canonical form like
  `父亲` / `母亲`). Otherwise skip.

- *"想自定义剧情触发模板吗？"* → If yes, walk through
  `data/catalyst_events.json`. Otherwise skip — the defaults are
  class-agnostic.

**Do not touch**: `schedule.json`, `location_events.json`,
`scene_ambient_events.json`. These are class-agnostic.

---

## Phase 7 — Tell the user what to run

Print this verbatim:

> 角色文件改完了。注意：`init_world.py` 会**清空** `agents/` 和 `world/` 目录
> （包括之前所有的运行历史）。如果想保留旧 run，先备份再继续。
>
> ```bash
> uv run python scripts/init_world.py    # rebuild initial world from new characters
> uv run sim --days 5                    # run 5 days
> ```

---

## Operating notes for the agent

- **Save incrementally.** Write each character file as soon as Phase 5 passes
  for it. Don't batch all 11 in memory and save at the end — if anything
  interrupts, the user loses everything.
- **Use `AskUserQuestion`** for enums and short answers. Reserve free chat
  for the long free-text fields.
- **Show, don't tell.** Before asking the user to write `speech_patterns` or
  `behavioral_anchors.must_do`, paste 2–3 examples from existing characters.
  These fields are useless if generic.
- **Echo decisions.** After each batch, print a one-line summary so the user
  catches mistakes early.
- **If the user fatigues**, save the in-progress draft to a scratch file and
  offer to resume next session.
