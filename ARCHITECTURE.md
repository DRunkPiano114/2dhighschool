# Architecture & Technical Reference

Multi-agent simulation of a Chinese high school class set at **上海市建宁中学** (a fictional Shanghai 市重点 high school). Each agent (student/teacher) is an LLM-powered character that interacts through structured daily scenes, generating emergent narratives. Pure observation mode — no user intervention, text output only. The goal is to explore whether multi-agent LLM simulation can produce agents that behave like real people — with authentic personalities, evolving relationships, and believable decision-making across three years of high school life.

**Tech stack**: Python 3.12+, DeepSeek V3.2 via LiteLLM + Instructor (structured JSON output), Pydantic (data models + validation), Jinja2 (prompt templates), Loguru (logging), asyncio (concurrency), FastAPI + uvicorn (interactive chat API), SSE (streaming). All state stored as JSON + Markdown files — no database.

**Scale**: 10 students + 1 teacher (homeroom teacher). All character data, prompts, and narrative output are in Chinese.

---

## Architecture Overview

Five-layer design plus an API layer, all source code in `src/sim/`:

```
┌──────────────────────────────────────────────────────────┐
│  API Layer  (api/)                                        │
│  FastAPI server, God Mode + Role Play chat endpoints,     │
│  time-travel context assembly, SSE streaming              │
├──────────────────────────────────────────────────────────┤
│  Interaction Layer  (interaction/)                        │
│  Orchestrator, dialogue turns, tick resolution,          │
│  scene-end analysis, result application, solo reflection │
├──────────────────────────────────────────────────────────┤
│  Agent Layer  (agent/)                                   │
│  Profile/state storage, context assembly,                │
│  daily plan generation, state update formulas,           │
│  self-narrative generation, location re-planning         │
├──────────────────────────────────────────────────────────┤
│  World Layer  (world/)                                   │
│  Schedule, scene generation (location-split free         │
│  periods), agent grouping, event queue, exam system,     │
│  homeroom teacher                                        │
├──────────────────────────────────────────────────────────┤
│  LLM Layer  (llm/)                                       │
│  Instructor+LiteLLM client, streaming text calls,        │
│  Jinja2 prompt rendering, per-call JSON logging          │
├──────────────────────────────────────────────────────────┤
│  Memory Layer  (memory/)                                 │
│  Nightly compression, relevance-based retrieval,         │
│  memory writer helpers                                   │
├──────────────────────────────────────────────────────────┤
│  Models  (models/)                                       │
│  Pydantic data models for all domain objects             │
└──────────────────────────────────────────────────────────┘
```

---

## Daily Simulation Loop (Orchestrator)

`interaction/orchestrator.py` → `Orchestrator` class. Entry point: `Orchestrator.run(start_day, end_day)`.

Each simulated day runs through four sequential phases (plus an exam trigger before Phase 1):

### Phase 0.5: Exam Trigger (conditional)

Before daily plans, if `progress.next_exam_in_days <= 0`, the exam fires via `Orchestrator._run_exam()`:

1. Load previous exam results (most recent `simulation/world/exam_results/day_NNN.json`) for rank comparison
2. Generate exam scores (see Exam Score Generation below)
3. Apply exam effects — emotion changes + energy drain + pressure shock, written directly to disk
4. Reload all agent states from disk (to pick up the effects)
5. Teacher post-exam actions: `HomeroomTeacher.post_exam_actions()` creates gossip events for students who dropped ≥3 ranks (70% per student), injected via `EventQueueManager`
6. Set `progress.last_exam_day = day`, reset `progress.next_exam_in_days = exam_interval_days`
7. Store results in `self._exam_results` — used later to inject per-agent `exam_context` into scenes

**Per-agent exam context**: during scene execution, each student gets their own `format_exam_context()` string (personal scores + rank + rank change). The teacher (`he_min`) gets `format_teacher_exam_context()` — a class-level overview (top 3, struggling students, class average, notable improvers). The `exam_context` is passed as a `dict[str, str]` to `run_group_dialogue()` (keyed by agent_id) and as a plain `str` to `run_solo_reflection()`.

### Phase 0: Self-Narrative Generation (periodic)

On day 1 and every `self_narrative_interval_days` (default 3) days:
- For each agent (concurrently), call LLM with `self_narrative.j2` template
- Input: profile summary (including backstory), recent 3-day summary, active concerns, relationships with qualitative labels, previous `self_concept` and `current_tensions` (for continuity)
- Output: `SelfNarrativeResult` — structured model with three fields:
  - `narrative`: first-person self-reflection (teacher: 100-200 chars; student: 50-100 chars in 碎碎念 style — short sentences like thoughts drifting through the mind, not essay prose)
  - `self_concept`: up to 4 bullets ("我是一个 ___ 的人"), slow-changing (prompt instructs: change at most 1 bullet per update unless major event)
  - `current_tensions`: up to 3 bullets, what the agent is struggling with this week (can change fully each update)
- Saved to `simulation/state/<id>/self_narrative.json` (canonical) + `self_narrative.md` (human-readable mirror). Legacy md-only data is auto-migrated on read.
- `self_concept` + `current_tensions` are injected into daily_plan, self_reflection, and solo_reflection templates. `perception_static.j2` only gets `current_tensions` (kept lean since it runs per-tick).
- `inner_conflicts` (from profile, immutable) displayed as "你内心的永恒矛盾" vs `current_tensions` displayed as "你最近在和这些搏斗" — both coexist, representing permanent personality traits vs transient struggles.

### Phase 1: Daily Plan Generation (`day_phase = "daily_plan"`)

For each agent (concurrently, up to `max_concurrent_llm_calls`):
1. Load relationships (with qualitative labels), last 3 days of `recent.md`, yesterday's intentions (full lifecycle state), active concerns (with intensity labels), structured self-narrative (narrative + self_concept + current_tensions), and inner conflicts
2. Call LLM with `daily_plan.j2` template → returns `DailyPlan` (1-3 `Intention` objects + `mood_forecast` + `location_preferences`). The prompt shows each concern with its `[ref: <id>]` suffix and instructs the agent to fill `satisfies_concern` with the 6-hex ref (not the text). **Strict high-intensity rule** (PR6): intensity ≥ 7 ("强烈") concerns must be hooked to some intention, OR the agent must fill `satisfies_concern=null` AND write a concrete reason in `reason`. The earlier "allowed to avoid" language is gone. Yesterday's intentions appear with fulfillment status using **tiered urgency language** based on `pursued_days`: ≥5 days triggers escalated language ("拖了N天了…今天不面对，什么时候面对？"), ≥3 days triggers moderate urgency. Concern `text_history` still renders as "之前的想法". `joy_sources` section ("能让你开心的小事") is rendered from `profile.joy_sources` when available. Qualitative labels replace raw numbers.
3. Validate location preferences against valid lists (invalid → default)
4. **Carry-forward** (`_match_old_intention`): each new intention is matched against yesterday's intentions via two signals, skipping abandoned. (a) Same target + goal substring overlap (the original path, handles LLM paraphrasing the goal). (b) Both sides reference the same concern resolvable via `concern_lookup` (handles the case where the goal text shifts significantly — "想找爸爸聊数学" → "没敢提化学成绩" — but both tie to the same concern id). Matched → inherit `origin_day` and `pursued_days + 1`. Unmatched → `origin_day=today, pursued_days=1`.
5. **Audit + optional retry**: scan concerns with `intensity >= 7` (PR6: aligned to prompt threshold) whose `related_people` intersect known profile names. For each unhooked addressable concern, a warning is logged. If `settings.daily_plan_audit_retry` is True (PR8 feature flag, default False) AND the per-day per-agent budget isn't exhausted (`daily_plan_audit_max_retries_per_day_per_agent`, default 1), a second LLM call is made with a feedback message that **cites only the single highest-intensity unhooked concern** by `[ref: <id>]` (P2.B.3) and asks the agent to either hook it or explain the avoidance concretely. The earlier "list every unhooked concern" copy made the LLM treat retries as a coverage drill and mechanically hook all of them, killing daily variety; pointing at the loudest one focuses the revision without forcing a sweep. The retry plan goes through the same location validation + carry-forward, and a second audit runs on the retry output — at most one retry per call (`max_retries_per_call`, default 1), remaining unhooked concerns after retry just warn. Budget is tracked in the module-level `_audit_retry_budget` keyed by `(day, agent_id)` and **resets implicitly each day** (Sig9 regression: pre-PR8 streak design would permanently lock out chronically unhooked concerns). Retry is logged with `call_type="daily_plan_audit_retry"` for cost monitoring.
6. Save updated state with new plan

`Intention` has: `target` (optional agent name), `goal`, `reason`, `fulfilled` (bool), `abandoned` (bool), `satisfies_concern` (6-hex concern id, or null; substring fallback still works during migration), `origin_day` (first day this intention appeared), `pursued_days` (consecutive days in plan).

`LocationPreference` has: `morning_break` (课间 08:45), `lunch` (午饭 12:00), `afternoon_break` (课间 15:30). Each field's allowed values come from the corresponding free-period entry's `valid_locations` in `schedule.json`. The daily plan template renders the per-slot option list dynamically from the orchestrator's cached schedule, and `daily_plan.py` validates the LLM's output against each slot's `valid_locations` (falling back to the slot's `location` default if invalid).

### Phase 2: Scene Execution (`day_phase = "scenes"`)

**Catalyst Event Injection** (before scenes): at the start of `_run_scenes()`, the orchestrator loads `canon/worldbook/catalyst_events.json` and runs `CatalystChecker.check_and_inject()` once per day. `_check_trigger` is a **generator** — it yields every agent (or pair) that satisfies a trigger's condition, not just the first. The outer loop in `check_and_inject` iterates over every match and checks cooldown per match, so one isolation trigger can fire for three students on the same day.

- `concern_stalled`: a concern with matching `topic` and `today - last_new_info_day >= min_stale_days` (PR3: drives off `last_new_info_day`, not `last_reinforced_day`, so pure emotion reinforcement never masks a truly stalled concern). Entries in `catalyst_events.json` carry either `require_related_people: true` (→ only matches concerns with non-empty `related_people`, template uses `{related_person}`) or `require_empty_related_people: true` (→ only matches empty-people concerns, template has no `{related_person}` token). The two are mutually exclusive so a single concern can't fire both.
- `positive_concern_stalled` (P2.B.4): same staleness logic as `concern_stalled` but scoped to `positive=True` concerns and parametrized by `topic` (currently `期待的事` and `兴趣爱好`, the two positive buckets in `ConcernTopic`). Without this trigger, positive concerns silently die — there's no reinforcement path other than LLM-emitted `concern_updates`, and a 2-day decay defeats most of them inside a week. Templates are deliberately vague-but-positive ("收到一条相关消息", "刷到一条相关的推送") so the LLM has room to ground the catalyst in whatever joy_source the concern originally tied to.
- `isolation`: a student has `<= max_active_relationships` relationships with `days_since_interaction <= 3`
- `relationship_threshold`: any student pair where `favorability >= favorability_gte` (dedup via a seen-pair set inside the generator so each pair yields at most once per day)
- `intention_stalled`: an unfulfilled, non-abandoned intention with `pursued_days >= min_pursued_days` (break after first match per agent so a student with multiple stalled intentions isn't spammed)

Matching triggers fill a random template with agent names and inject the event via `EventQueueManager.add_event()` with `category="catalyst"`. **Cooldowns are always scoped** (per-agent or per-pair), keyed by `"<trigger_type>:<params_json>:<sorted_witnesses>"`. A global scope would starve every agent after the first match per day; the pre-PR4 `cooldown_scope == "per_pair"` conditional is gone — witness count drives scope automatically. Legacy cooldown keys (pre-PR4 format, no witness suffix after the params JSON) are filtered on load by `_load_cooldown_state` — expected to cause a small one-day catalyst burst on the upgrade-day as cleared-cooldown concerns fire (documented in PR4 changelog). Cooldowns persist to `world/catalyst_cooldowns.json`. After injection, the event queue is saved back to disk before scenes begin.

For each scene in `canon/worldbook/schedule.json` (sequentially):

**Step 2a — Scene Generation** (`world/scene_generator.py`):

Scene generation is now **lazy per-config**: the orchestrator iterates over `schedule.json` entries and generates scene(s) for each config, reloading agent states between configs (to reflect re-planning changes). `SceneGenerator.__init__` takes `current_day` parameter and loads `_cooldown_state` from `simulation/world/ambient_cooldowns.json` for ambient event cooldown tracking.

For **normal scenes** (`is_free_period=false`):
- LOW density scenes roll against `trigger_probability` (default 15%). If they don't trigger, they're skipped entirely. If they trigger, density is upgraded to HIGH_LIGHT and a random classroom event is injected (balanced across negative/neutral/positive events).
- Teacher participation: 20% chance during 晚自习 — when the roll succeeds, He Min joins as a full LLM-driven agent participant (not just a `teacher_present` flag). Teacher does not appear in 课间 normal scenes (课间 is a free period, handled separately).
- **Teacher patrol events**: when the teacher is NOT a full participant and the scene is 晚自习/早读/上课, a patrol event may be injected via `HomeroomTeacher.patrol_event()`. 晚自习/早读 have a 30% internal probability gate; 上课 always returns an event so a 30% gate is applied in the scene generator. Patrol events (e.g. "何老师巡视时发现有人在聊天") appear in the scene's `injected_events`.
- Present agents determined by location: 宿舍 → only dorm members; elsewhere → all students.

For **group interaction**, each group gets a scoped scene copy (`group_scene`) with `agent_ids` set to only that group's members. This ensures dorm scenes show correct participant lists (boys-only / girls-only) and the `teacher_present` flag is set correctly per-group (`scene.teacher_present OR "he_min" in group.agent_ids`).

For **free period scenes** (`is_free_period=true` — 课间 08:45, 午饭 12:00, 课间 15:30):
1. Read `pref_field` from the `SceneConfig` (declared in `schedule.json`) — maps the slot to the corresponding `LocationPreference` field (`morning_break`, `lunch`, or `afternoon_break`).
2. Group students by their chosen location from daily plan; if a student's preference falls outside `config.valid_locations`, fall back to `config.location` (the slot's default).
3. Teacher occasionally appears during free periods: 30% at 午饭, 10% at 课间. When she appears, she joins the slot's `default_location` (= `config.location`) group as a full agent participant.
4. Create one Scene per occupied location with location-specific opening events from `canon/worldbook/location_events.json`
5. Scene name becomes `f"{config.name}@{location}"` (e.g. "课间@走廊", "午饭@食堂")
6. Sequential scene indices assigned starting from current index

Available locations come from `schedule.json:valid_locations` per slot — currently 课间 → 教室/走廊/操场/小卖部/图书馆/天台; 午饭 → 食堂/教室/操场/小卖部. Editing the JSON is the only place to change these.

**Ambient event cooldowns**: `scene_ambient_events.json` supports a mixed format — plain strings (no cooldown) and dicts with `text` + `cooldown_days` fields. `_load_ambient_events()` returns `dict[str, list]` (mixed `str | dict`). `_maybe_inject_ambient_event()` filters out dict events still on cooldown (comparing `current_day` against `_cooldown_state`), then selects from the remaining pool. After injection, dict events update `_cooldown_state` with key `"{location}:{text[:30]}"`. `save_cooldown_state()` persists the state to `world/ambient_cooldowns.json` — called by the orchestrator after scenes complete.

**Step 2a.1 — Re-planning** (between configs):
After all sub-scenes for a config complete, if the next config is a free period, "affected" agents may re-plan their location. An agent is affected if ANY of (checked from their individual `AgentReflection`):
- Their reflection produced any `new_concerns`
- Their reflection emotion is an extreme emotion (ANGRY, EXCITED, SAD, EMBARRASSED, JEALOUS, GUILTY, FRUSTRATED, TOUCHED)
- Any of their `relationship_changes` has |favorability| >= 8 or |trust| >= 8

Re-plan uses `replan.j2` template → `ReplanResult` (changed, new_location, reason). The next slot's `pref_field` and `valid_locations` are read directly from its `SceneConfig`. If changed, updates `location_preferences` for the next slot. Only students are re-planned (teacher is excluded — she has no location preferences).

**Step 2b — Grouping** (`world/grouping.py`):
- First, identify solo agents: non-students (teacher) are never solo. For students: energy < `solo_energy_threshold` (default 20), or introvert without close relationships at 50% chance, or sad + low energy at 60% chance.
- For 宿舍 scenes: group by dorm assignment (single-dorm occupants are kept as 1-member groups, not silently dropped).
- For other scenes: greedy affinity clustering (max group size 5). Affinity = bidirectional favorability + structural label bonus (室友 +20, 同桌 +15, 前后桌 +10) + same-gender bonus (+5, or +100 in dorms) + intention targeting bonus (+25 if either agent has an unfulfilled intention targeting the other by name) + random noise ±10.
- **Singleton promotion**: after clustering, any 1-member social group is promoted to `is_solo=True`. The multi-agent orchestrator can't produce dialogue from one person — it would yield zero ticks and a trivial empty shell. The right pipeline for any lone agent (whether `_should_be_solo` fired or not) is `run_solo_reflection`.

**Deterministic scene generation**: Scene generation uses a per-day deterministic RNG seeded with `hash((base_seed, "scenes", day))`, separate from the main simulation RNG. This ensures the same set of LOW density scenes trigger on resume as on the original run, keeping `scene_index` values stable.

**Snapshot**: After grouping completes, mutable agent files (`state.json`, `relationships.json`, `key_memories.json`, `today.md`) are snapshotted to `world/snapshots/scene_N/<agent_id>/`. If the simulation is interrupted during the interaction phase and later resumed, the orchestrator detects the incomplete scene, restores agent files from the snapshot (reverting any partially-applied changes), resets the scene to the grouping phase, and re-runs it from scratch. A `.complete` marker ensures partially-written snapshots are discarded. Snapshots are cleared after each scene completes and at day boundaries (only when starting a fresh day, not on resume).

**Step 2c — Group Interaction: PDA Tick Loop** (`interaction/turn.py`):

Each tick, ALL agents in the group perceive the latest event, decide what to do, and a resolution step handles simultaneous actions. This replaces the old turn-based speaker selection system.

Tick loop (`run_group_dialogue`):
```
for tick in range(scene.max_rounds):  # per-scene cap from schedule.json
    1. GATE: for each non-queued active agent, decide if fresh perception is needed
       Trigger rules (any one → perceive):
       a. Tick 0 (no previous output to reuse)
       b. Agent was directly targeted by last resolved speech
       c. Agent's name appears in latest_event text
       d. Environmental event occurred this tick (disruptive action)
       e. A concern-related person is mentioned in latest_event
       f. 4-tick cadence: agent hasn't perceived in 4+ ticks
       If no trigger: reuse last PerceptionOutput with action_type=OBSERVE,
       urgency decremented by 1, no emotion_history append (prevents fake drift).
       These agents are tracked as "gated" this tick so their stale reused
       observation/inner_thought can be filtered out of downstream artefacts
       (see RECORD step 4 + `gated_agents` handling below).
    2. PERCEIVE: gated-in agents concurrently (semaphore-throttled)
       - Build per-agent context via prepare_context() with PDA params
       - LLM returns PerceptionOutput
    3. RESOLVE: resolve_tick() determines what happens (see PDA Tick Resolution)
    4. RECORD: store tick_record with all agent outputs + resolved actions +
       `gated_agents: list[str]` listing agents that reused last perception
       this tick (used by narrative/serialize layers to suppress stale copies)
    5. UPDATE: latest_event for next tick from resolved actions
    6. CHECK: scene ends if consecutive_quiet >= 4 and tick_count >= 3
```

- Tick 0 starts with `scene.opening_event` as the latest event (randomly selected from `schedule.json:opening_events` per scene config)
- **Scene `max_rounds` selection** (Fix 8A): long-form scenes are deliberately bounded to prevent open-ended drift into "literary cliché" emotional spirals. Current values: 课间 = 12 (was 20), 午饭 = 20 (was 25), 宿舍夜聊 = 22 (was 35); 早读/上课/晚自习 stay at 8. The remaining ceiling beyond what the scene actually consumes is absorbed by the natural-end check (`consecutive_quiet >= 4 AND tick_count >= 3`). `tests/test_schedule.py:test_schedule_max_rounds_sane` enforces upper-bound caps so future edits cannot regress.
- Queued agents (losers from previous tick's speaker resolution) skip the PERCEIVE step and reuse their previous PerceptionOutput with +3 urgency per tick queued
- **Perception gating** reduces LLM calls by 30-60% for silent background agents. Gating state (`last_perception`, `last_perceive_tick`) is local to `run_group_dialogue` scope — rebuilt from scratch on crash recovery (deterministic with same seed). Solo groups (`_run_single_scene` → `run_solo_reflection`) are not affected by gating.
- Narrative formatting (`interaction/narrative.py`):
  - `format_public_transcript()`: public events visible to all (speech, actions, exits). Mid-scene summarization after 12 ticks: ticks 1-6 are collapsed into a one-line summary
  - `format_agent_transcript()`: public view + agent's own prior observations and inner thoughts as private history. **Gated-tick suppression**: when the focal agent appears in `tick_record["gated_agents"]`, that tick contributes NOTHING to their private history — the observation/inner_thought there is a verbatim reuse of an earlier fresh perception and re-rendering it produces duplicate lines that pollute downstream reflection prompts. Other agents' perspective on the same tick is unaffected.
  - `format_latest_event()`: one-line summary of what just happened, used as the "latest event" for next tick's perception prompt

**Step 2c (solo)** — `interaction/solo.py`: If a group has `is_solo=true`, run `solo_reflection.j2` instead → returns `SoloReflection` with `inner_thought`, `emotion`, `activity`.

**Trivial scene fast path** (Fix 3): immediately after `run_group_dialogue` returns, the orchestrator calls `is_trivial_scene(turn_records)` to detect "nothing happened" scenes (empty turn_records, no speech AND no environmental_event in any tick, or ≤2 ticks of pure observe / non-disruptive non_verbal). When true, `apply_trivial_scene_result` writes a placeholder `（场景没有特别发生什么）` line to each agent's `today.md` and the orchestrator skips both narrative extraction and per-agent self-reflection LLM calls. The group is marked `gc.status = "applied"` directly (skipping the `llm_done` intermediate state) so a crash recovery never tries to re-run absent LLM outputs. The trivial fast path does NOT touch `state.emotion`, `active_concerns`, `key_memories`, or relationships — emotion decay is independently driven by `_end_of_day` (overnight semantics), so trivial scenes do not need to advance any per-scene counter.

**Step 2d — Narrative Extraction + Per-Agent Self-Reflection** (two-phase post-dialogue):

After the dialogue ends, two types of LLM calls run **concurrently**:

**Phase 1: Narrative Extraction** (`interaction/scene_end.py`) — 1 LLM call:
- Build conversation log from tick_records using `format_public_transcript()` (includes speech, non-verbal actions, exits). Inner thoughts and observations are NOT included — extraction only sees externally observable behavior.
- `long_conversation` threshold: 12 ticks
- Feed the conversation log to LLM with `scene_end_analysis.j2` (analytical temperature 0.3) as a purely objective recorder
- Returns `NarrativeExtraction`:
  - `key_moments`: list of significant events as one-line summaries (objectivity constraint: no 刻意 / 似乎 / 暗中 推测词)
  - `fulfilled_intentions`: list of "name:intention" strings
  - `events_discussed`: event IDs that were actually mentioned (updates `known_by`)
  - `new_events`: gossip/conflicts/decisions that may spread to other scenes — each carries a `cite_ticks: list[int]` (1-indexed `[Tick N]` numbers from the conversation log) used by Fix 13's grounding validation in `apply_scene_end_results`

**Phase 2: Per-Agent Self-Reflection** (`interaction/self_reflection.py`) — N concurrent LLM calls:
- For each agent in the group, build an agent-specific prompt with:
  - Full agent context (profile, relationships, memories, concerns, self-narrative) via `prepare_context()`
  - Agent-specific conversation log via `format_agent_transcript()`
- Render `self_reflection.j2` template (reflection temperature 0.7)
- Each agent independently evaluates the conversation from their own perspective
- Returns `AgentReflection` per agent:
  - `emotion`: Emotion enum — agent's post-dialogue emotional state
  - `relationship_changes`: list of `AgentRelChange` (to_agent, favorability/trust/understanding deltas) — no from_agent needed since the reflection belongs to the focal agent
  - `memories`: list of `AgentMemoryCandidate` (text, emotion, importance, people, location, topics) — no agent field needed
  - `new_concerns`: list of `AgentConcernCandidate` — persistent emotional preoccupations from the agent's perspective (can be positive or negative, flagged via `positive` field)
  - `concern_updates`: list of `AgentConcernUpdate` — intensity adjustments to the agent's existing concerns
  - `intention_outcomes`: list of `IntentionOutcome` — agent self-evaluates each pending intention from the dialogue (status: fulfilled/attempted/frustrated/abandoned/pending/missed_opportunity, brief_reason). This replaces the old `narrative.fulfilled_intentions` substring matching which had 0% hit rate.
- Error handling: if an individual agent's reflection fails (LLM error, timeout), a default `AgentReflection()` is used (NEUTRAL emotion, no changes) so one failure doesn't block the group

This two-phase design enables **asymmetric perception**: the same conversation can produce different emotions, relationship changes, and memories for each participant, based on their personality, history, and existing concerns.

**Step 2e — Apply Results** (`interaction/apply_results.py`):
- For each agent in the group (using their individual `AgentReflection`):
  - Update emotion directly from reflection (Emotion enum, no try/except needed)
  - Append key moments from shared `NarrativeExtraction` to `today.md` (formatted as `## time scene @ location`)
  - Save key memories with importance >= `settings.key_memory_write_threshold` (=3, Fix 14: lowered from 7) from agent's own reflection to `key_memories.json`
  - Apply relationship deltas from agent's own reflection using baseline snapshot (for idempotency): `new_value = baseline + clamped_delta`, clamped to valid range. **Auto-insertion** (Fix 4): if the change targets an in-profiles agent that has no entry in this agent's `relationships.json` yet, a zero-state `Relationship` is created on the fly and the delta is applied on top. The `label` is picked from **both** source and target roles: HOMEROOM_TEACHER → student auto-inserts as `"学生"`, any agent → HOMEROOM_TEACHER as `"老师"`, otherwise `"同学"`. (Prior bug: label was picked from target role only, so a teacher auto-inserting a student fell through to `"同学"`.) Hallucinated names that don't resolve to any profile are dropped with a warning. Previously, missing targets were silently dropped — leading to permanently empty relationship maps for low-interaction agents.
  - **Bystander vs Direct Interaction Clamp (Fix 5)**: each `AgentRelChange` now carries a `direct_interaction: bool` field (LLM self-label). Python applies a **double-gate** before accepting deltas > ±1: (1) LLM must have set `direct_interaction=True`, AND (2) `_build_direct_interaction_set(aid, tick_records, profiles)` must confirm that the agent actually interacted with the target in the tick records (speech with `action_target`, non-verbal action targeting, or being targeted by another agent). Only when both gates pass is `max_delta=3` allowed; otherwise `max_delta=1`. This prevents a bystander from inflating relationship scores via "far observation" while still allowing observers to accumulate small signals over time (±1 per scene). The `self_reflection.j2` template explicitly instructs the LLM that bystander relationship changes are valid and expected.
  - **recent_interactions log**: whenever any relationship_change has a non-zero delta, append the tag `"Day {day} {mark}{scene.name}"` to `rel.recent_interactions`, where `mark` is a one-character valence prefix derived from the signed `favorability + trust` delta of that row: `+` for net-positive (warm interaction), `−` (U+2212) for net-negative (friction), `·` (U+00B7) for net-zero but still interacting (e.g. understanding-only change where fav/trust cancel). Understanding is excluded from the valence sum because it measures "how well I know them", not affect. Dedup is keyed on the full tag (day + mark + scene name), so two rows with the same sign in the same scene collapse but a mixed scene where one row is `+` and another is `−` legitimately records both events — rare but possible across multi-target or multi-tick reflections. The list is capped at `settings.max_recent_interactions` (default 10, FIFO eviction). Downstream prompts (`perception_static.j2`, `self_reflection.j2`, etc.) render the log as an interaction timeline so the LLM can distinguish "Day 3 +课间@走廊" (warm) from "Day 4 −宿舍夜聊" (friction) at a glance without having to re-infer valence from the current absolute relationship scores. Lays the groundwork for Phase 2+ relationship-strength signals.
  - **Mark intention outcomes** from agent's own `intention_outcomes` (replaces old `narrative.fulfilled_intentions` substring matching). Each matched intent is recorded in a per-agent `processed_intent_ids: set[int]` (identity via `id(intent)`) so the PR7 silence-synthesis pass below doesn't double-count. All six `IntentionOutcome.status` values are explicitly handled — any unrecognized status (schema drift) hits an `else` branch that logs a warning instead of being silently dropped:
    - `fulfilled` → mark intent as fulfilled; if `satisfies_concern` is set, `concern_lookup` resolves the concern and intensity decays by 2 (drains bypass the per-day cap). `reinforcement_count` also decreases by 3 (explicit reward — a fulfilled concern should leave "stuck topic" territory even if it had high reinforcement history)
    - `frustrated` → if `satisfies_concern` is set, `concern_lookup` resolves and intensity rises by 1 via `bump_concern_intensity`. There is no `pursued_days` multiplier — once `pending`/`attempted` are first-class statuses, "long pursuit" is no longer an automatic failure signal
    - `abandoned` → mark intent as abandoned (excluded from carry-forward)
    - `missed_opportunity` (PR7) → if `satisfies_concern` is set, intensity rises by 1 via `bump_concern_intensity` (same net effect as the synthesis pass below)
    - `attempted` / `pending` → legitimate "still in progress" verdicts. Concern intensity untouched, intent stays open (`fulfilled` and `abandoned` both False), `pursued_days` carries forward via `_match_old_intention`. The intent is added to `processed_intent_ids` so silence synthesis below cannot second-guess the LLM and bump the linked concern
    - Matching between outcome goal and intent goal still uses bidirectional substring (`concern_match`) — LLM paraphrase of goal is expected
  - **Silence synthesis** (PR7): after processing LLM-reported outcomes, scan remaining unfulfilled/un-abandoned intents. If `id(intent) in processed_intent_ids`, skip entirely (Cr2 regression: respect LLM judgment even for paraphrased goals; also covers the `pending`/`attempted` no-op above). Otherwise, if `intent.target` is a name in the same group (`group_agent_ids`, NOT full scene — avoids punishing a dorm-night agent for not addressing someone in a different group) AND that agent is not in `_build_direct_interaction_set(aid, tick_records, profiles)`, synthesize a `missed_opportunity`: bump the linked concern via `bump_concern_intensity`. **High-intensity immune gate**: if the linked concern is already at `intensity >= 7` ("强烈"), the synth bump is skipped entirely — once a concern is loud, "didn't talk to them again today" stops carrying new information and would just run the intensity to 10 against a stuck topic.
  - Apply new concerns from agent's own reflection via `add_concern` with `source="reflection"` (topic-based dedup; alias-normalized people sets). Propagates `positive` flag and chosen `topic` from `AgentConcernCandidate`. See **Concern Topic Bucketing & Dedup**.
  - Apply concern intensity adjustments from `concern_updates` via `concern_lookup`. Positive adjustments go through `bump_concern_intensity` and respect the per-day cap; the `last_reinforced_day` / `reinforcement_count` bookkeeping only fires if the cap actually let a non-zero delta land (a capped update is a silent no-op, otherwise rejected updates would still inflate backstop counters). `last_new_info_day` is NOT advanced (concern_updates is "LLM says this got worse", not "new event happened"). Non-positive adjustment is pure relief: intensity drains immediately (cap doesn't apply to drains), nothing else moves. Remove concerns that reach intensity <= 0.
- Update event queue from shared `NarrativeExtraction`: mark discussed events as known by all group members; **for new events, run Fix 13's 3-layer cite_ticks grounding** before saving.

**Fix 13 — `new_events` grounding** (`apply_results.py`): each `NewEventCandidate` carries `cite_ticks: list[int]` (1-indexed `[Tick N]` numbers as the LLM saw them). Before adding to the event queue, three layers run:

1. **Layer 1 (non-empty)**: drop if `cite_ticks` is empty.
2. **Layer 2 (existence + summarized exclusion)**: build `valid_ticks = {tick + 1: tick_record}` to align with the `[Tick N]` 1-indexed display in `narrative.py:54/:104`. When `len(tick_records) > 12`, exclude ticks 0–5 (0-indexed) since `format_public_transcript` collapses them into one summary line and the LLM cannot have legitimately quoted their content. Drop if any cited tick is outside `valid_ticks`.
3. **Layer 3 (bigram overlap)**: compute Chinese-character bigrams of `event.text` and the concatenated raw content of all cited ticks (`_extract_tick_content` pulls speech / actions / environmental_event). The primary signal is `event_ratio = |overlap| / |event_bigrams|`; the threshold is 0.3. Using the event side as denominator means longer / more elaborated event text must overlap more — catching the "expansion" failure mode where the LLM cites one short tick but writes a long elaborated description. The log also reports `min_ratio = |overlap| / min(|event|, |cited|)` for tuning.

Events that pass all three layers are persisted via `event_manager.add_event(...)` with `cite_ticks` and `group_index` carried through onto the `Event` model itself (Fix 13 follow-up). Persisting both fields means M1 sanity check can validate ground-truth against `event_queue.json` without re-running the LLM; the `group_index` is essential because cite_ticks are group-local — different groups in the same scene have independent tick numbering, and earlier audits that unioned visible ticks across groups would false-pass cross-group cites. System-generated events (e.g. `HomeroomTeacher.post_exam_actions`) leave `group_index=None` and are excluded from the M1 audit.

The orchestrator now passes `tick_records=turn_records` into `apply_scene_end_results` so the validator has access to the raw conversation. Drops are logged with the prefix `[scene_end] drop` so post-rerun analysis can count rejections.
- (File output moved to orchestrator — see "Scene File Output" below)

### Phase 3: Nightly Compression (`day_phase = "compression"`)

For each agent (concurrently):
1. Read `today.md` content, active concerns, and unfulfilled intentions from daily plan
2. Call LLM with `nightly_compress.j2` → returns `CompressionResult`:
   - `daily_summary`: 1-2 sentence summary of the day. The prompt requires neutral 中性记录式 phrasing (no 似乎/仿佛/暗流涌动 — see Fix 1). If there are unfulfilled intentions, the prompt asks the LLM to briefly note why (no opportunity? changed mind? interrupted?) — reflections enter `recent.md` with natural ~3 day half-life
   - `daily_highlight`: ≤120-char "single most important moment of the day" anchor line rendered as `高光：...` in `recent.md`. Validated by `_validate_daily_highlight` (below) before persistence.
   - `permanent_memories`: candidates with importance scores (subject to the same intensity scale anchor from Fix 1)
   - `new_concerns`: concerns surfaced by reviewing the whole day (safety net for scene-end misses). Can be positive (positive=true) — e.g. anticipation, warmth
3. Append daily summary + validated highlight to `recent.md` as `# Day N` section (both entries used by the next day's `daily_plan.j2` via `recent_days`)
4. Save memories with importance ≥ `settings.key_memory_write_threshold` (=3, Fix 14) to `key_memories.json`
5. Apply new concerns via `add_concern` (Fix 2 — topic-based dedup), with `source_scene=""`
6. **Fix 14 per-day cap post-pass**: `cap_today_memories(storage, day, profile_name)` keeps at most `settings.per_day_memory_cap` (=2) of today's memories, dropping the lowest-importance excess. Both scene-end reflections and the compression call feed into the same key_memories file at threshold ≥3, so a single busy day could otherwise blow out an agent's memory list. Older days are untouched.
7. Clear `today.md`

**`_validate_daily_highlight`** (`memory/compression.py`): three base checks (non-empty, length ≥10, no >50% bigram overlap with any of the last 3 days' highlights) plus a **grounding check** — the LLM's highlight must share ≥30% of its bigrams with `today.md`, otherwise it's presumed fabricated. Grounding is the main filter: LLM frequently dramatizes the highlight into a catchy-but-fictional phrase (e.g. "在走廊上确认了沈逸凡翻墙的真相" when the actual scene was her spreading that rumor, not confirming it). Bigram overlap is a deliberately crude code-level check that catches "vocabulary from today's content pasted into an invented framing" without an extra LLM call.

**Two-tier fallback on grounding failure** (P2-followup): when the highlight fails the 30% threshold, `_try_summary_fallback` applies the same grounding check to the same round's `daily_summary`. If summary passes, it is truncated to `SUMMARY_FALLBACK_MAX_LEN` (100 chars) and returned with source tag `fallback:summary`. Rationale: `daily_summary`'s prompt demands neutral 记录式 style, so it hallucinates less than the highlight even when the LLM is otherwise cooperating poorly, and reusing it is zero-cost (same LLM round). Only if the summary is also ungrounded, empty, or too short does the system fall through to the generic `DAILY_HIGHLIGHT_FALLBACK_POOL` (`"今天没什么戏"`, `"日常的一天"`, …) with tag `fallback:ungrounded`. This prevents the pathological case where an eventful day produces a grounding-rejected highlight and `recent.md` ends up asserting "today was uneventful", which then poisons tomorrow's `daily_plan` context. Telemetry tags distinguish the three paths (`llm` / `fallback:summary` / `fallback:ungrounded`) so post-run analysis can measure how often each tier carries the load.

Hard char truncation is used instead of sentence-aware splitting because LLM summary terminators are inconsistent (`...`, `，`, missing `。`), and a mid-phrase cut is strictly more informative than `"今天没什么戏"`. Other failure tags (`fallback:empty`, `fallback:short`, `fallback:repetitive`) skip the summary fallback and go straight to the generic pool — an empty/fragmented highlight is a structural LLM failure rather than a dramatization problem, and a repetitive highlight means today's content blurred with a recent day's, which summary wouldn't fix either.

### Phase 3.5: Daily Snapshots (after compression)

After compression completes, `_save_daily_snapshots(day)` copies each agent's current `state.json`, `relationships.json`, and `self_narrative.json` to `simulation/days/day_{N:03d}/agent_snapshots/{agent_id}/`. These snapshots represent agent state at **end of Day N** = **start of Day N+1**.

**Day 0 initial snapshot**: `_save_day0_snapshot_if_needed()` runs at the start of each day loop, idempotently creating `simulation/days/day_000/agent_snapshots/` from the pristine agent files if it doesn't already exist. This is the baseline for Day 1 morning state.

**Snapshot semantics**: `day_N` snapshot = agent state at end of Day N. Exception: `day_000` = initial state before any simulation = start of Day 1.

**Retroactive backfill**: `scripts/export_frontend_data.py` includes `backfill_snapshots()` which creates `day_000` and fills any missing `day_NNN` snapshots for already-simulated days using current agent files.

**Purpose**: Snapshots enable the interactive chat API to reconstruct agent state at any historical timepoint (used by God Mode and Role Play chat).

```
simulation/days/day_001/agent_snapshots/
  lin_zhaoyu/
    state.json
    relationships.json
    self_narrative.json
  fang_yuchen/
    ...
```

### End of Day

For all agents (students + teacher):
- Reset energy to 85 (sleep)
- Decay all active concern intensities (high-intensity concerns at half rate; see **Concern Decay** below); evict any concern with intensity <= 0 OR `last_reinforced_day` more than `settings.concern_stale_days` (=5) behind today.
- **Emotion decay**: extreme emotions (angry, excited, sad, embarrassed, jealous, guilty, frustrated, touched) have 50% chance of resetting to neutral overnight
- **Relationship regression**: favorability and trust each nudge 1 point toward zero daily. Understanding does not regress (it represents cognitive knowledge that doesn't fade overnight)
- **Academic pressure update** (students only): calls `update_academic_pressure()` with current countdown and days since last exam. This activates countdown pressure escalation (≤14 days: +3, ≤7 days: +8, ≤3 days: +15) and post-exam recovery (day 0 resets to base, then -2/day decay). `days_since_exam` is computed from `progress.last_exam_day`.

Global end-of-day:
- Save trajectory data to `simulation/days/day_NNN/trajectory.json`
- Write `simulation/days/day_NNN/scenes.json` — scene index for frontend navigation (built from scene files written during the day)
- Expire events older than `event_expire_days` (default 3)
- Decrement `next_exam_in_days`
- Advance progress to next day

### Scene File Output

After all groups in a scene complete, the orchestrator writes a single frontend-ready scene file: `simulation/days/day_NNN/HHMM_scenename.json` (e.g. `0845_课间@教室.json`). `scene.name` already includes `@location` for free periods.

**Format:**
```json
{
  "scene": { "scene_index", "time", "name", "location", "description", "day" },
  "participant_names": { "agent_id": "中文名" },
  "groups": [
    {
      "group_index": 0, "participants": ["agent_id", ...],
      "ticks": [
        {
          "tick": 0,
          "public": { "speech", "actions", "environmental_event", "exits" },
          "minds": { "agent_id": { PerceptionOutput fields } }
        }
      ],
      "narrative": { NarrativeExtraction fields },
      "reflections": { "agent_id": { AgentReflection fields } }
    },
    {
      "group_index": 1, "participants": ["agent_id"],
      "is_solo": true,
      "solo_reflection": { "inner_thought", "emotion", "activity" }
    }
  ]
}
```

Key details:
- `serialize_tick_records()` in `orchestrator.py` converts in-memory tick records to the `ticks` array; Chinese names in `action_target` are converted to `agent_id`
- `write_scene_file()` in `apply_results.py` atomically writes the assembled data
- `minds` **excludes gated agents** — agents listed in `tick_record["gated_agents"]` reused `last_perception` verbatim (PDA optimization) and their observation/inner_thought are stale copies. Serializing them would produce the same long line across consecutive ticks in the scene JSON log, which confuses human review and downstream analysis. The serialized tick still carries a `gated_agents: list[str]` field alongside `minds` so frontend / debug tooling can render "who was quiet this tick" without relying on absence.
- Solo groups use `is_solo: true` + `solo_reflection` (no fake ticks/narrative)
- No `baselines` in scene file — frontend uses `reflections.relationship_changes` (delta values)

---

## Data Models (`models/`)

### AgentProfile (`models/agent.py`) — Immutable

```
agent_id: str                    # e.g. "lin_zhaoyu"
name: str                        # e.g. "林昭宇"
gender: Gender                   # male | female
role: Role                       # student | homeroom_teacher
seat_number: int | None
dorm_id: str | None              # e.g. "male_301"
position: str | None             # e.g. "班长", "学习委员"
personality: list[str]           # e.g. ["内向", "认真", "敏感"] (林昭宇)
speaking_style: str              # natural language description
academics: Academics
  overall_rank: OverallRank      # top | 上游 | 中上 | 中游 | 中下 | 下游
  strengths: list[str]           # e.g. ["数学", "物理"]
  weaknesses: list[str]          # e.g. ["英语"]
  study_attitude: str            # e.g. "极其刻苦，课间也在刷题"
  target: AcademicTarget         # 985 | 211 | 一本 | 二本 | 没想过
  homework_habit: str
family_background: FamilyBackground
  pressure_level: PressureLevel  # 高 | 中 | 低
  expectation: str
  situation: str
long_term_goals: list[str]
backstory: str
inner_conflicts: list[str]       # e.g. ["渴望友情但社交笨拙", "用AI查题后的负罪感和对成绩的执念在拉扯"]
behavioral_anchors: BehavioralAnchors  # Fix 5 — hard constraints for character consistency
  must_do: list[str] (max 5)           # things this character always does, regardless of mood
  never_do: list[str] (max 5)          # things this character would never do, even when provoked
  speech_patterns: list[str] (max 6)   # signature verbal tics / phrases
joy_sources: list[str]                 # small things that make this character happy (used in daily_plan.j2)
```

**Character Anchoring (Fix 5):** `behavioral_anchors` are hard constraints injected into every LLM prompt (perception, reflection, daily plan, self-narrative) via the shared `templates/partials/_anchors.j2` partial. They prevent the LLM from writing characters as generic high school students. `behavioral_anchors` (including `must_do`, `never_do`, and `speech_patterns`) and `joy_sources` are populated in all 10 character JSON files. Generated once offline via `scripts/generate_behavioral_anchors.py` (reads character backstory → LLM outputs anchors → human review → written back to character JSON). Not dynamically updated during simulation.

### AgentState (`models/agent.py`) — Mutable, updated every scene

```
emotion: Emotion                 # 15 values: happy, sad, anxious, angry, excited, calm,
                                 #   embarrassed, bored, neutral, jealous, proud, guilty,
                                 #   frustrated, touched, curious
energy: int (0-100)              # Default 85, sleep resets to 85
academic_pressure: int (0-100)   # Based on family + exam proximity + rank changes
location: str                    # e.g. "教室"
daily_plan: DailyPlan
  intentions: list[Intention]    # max 3, each has target/goal/reason/fulfilled/abandoned/satisfies_concern/origin_day/pursued_days
  mood_forecast: Emotion
  location_preferences: LocationPreference
    morning_break: str           # 课间 08:45 destination (default "教室")
    lunch: str                   # 午饭 12:00 destination (default "食堂")
    afternoon_break: str         # 课间 15:30 destination (default "教室")
day: int
active_concerns: list[ActiveConcern]  # max 4 persistent emotional preoccupations
```

### ActiveConcern (`models/agent.py`)

```
id: str (6-hex)                  # Stable id (secrets.token_hex(3)); auto-generated per instance.
                                 # Rendered in prompts as `[ref: <id>]`; LLM references via satisfies_concern / concern_updates.
text: str                        # "被江浩天当众嘲笑数学成绩"
source_event: str                # Brief trigger description (merged tail-biased, capped 500 chars)
source_scene: str                # e.g. "课间" — legacy structural-dedup field
source_day: int
emotion: str                     # "羞耻"
intensity: int (1-10)            # Decays at end of day; 0 → removed
related_people: list[str]        # Compared after alias-normalize (爸爸 → 父亲)
positive: bool                   # False=negative (worry/hurt), True=positive (warmth/excitement/anticipation)
                                 # Positive concerns are immune to the "stuck topic" backstops.
topic: ConcernTopic              # 10-value Literal enum used for dedup bucket
last_reinforced_day: int         # Bumps on BOTH merge AND pure emotion reinforcement (concern_updates)
last_new_info_day: int           # TTL counter — drives stale eviction. Only bumps when new information
                                 # arrives (merge via add_concern, or source="reflection"/"shock").
                                 # concern_updates (pure emotion delta) does NOT advance this.
reinforcement_count: int         # Counts every reinforcement. Used for backstops that catch the
                                 # "LLM keeps emitting as new_concerns" rumination case.
text_history: list[str] (max 3)  # Previous versions of concern text preserved on merge/evolution
id_history: list[str] (max 5)    # Previous ids of concerns merged into this one. `concern_lookup`
                                 # checks this so old `[ref: id]` references still resolve after merge.
```

Concerns are generated at three points: per-agent self-reflection (post-scene, `source="reflection"`), nightly compression (`source="reflection"` — the compress step extracts new worries, which semantically is reflection, not consolidation), and exam shock (`source="shock"`). All three go through `add_concern`. Per-scene concern intensity adjustments (no `add_concern` call) come from `concern_updates` which references concerns by `[ref: <id>]` and only moves intensity + reinforcement_count — never `last_new_info_day`.

**Lookup — `concern_lookup(state, id_or_text)`** (`interaction/apply_results.py`): the single entry point for resolving an LLM reference to a concern. Normalizes input (strips `[`, `]`, `ref:` prefix; lowercases) then tries, in order: exact id match, id_history match, text-substring fallback. A debug log records which path hit (`by_id` / `by_id_history` / `by_substring` / `miss`) for monitoring the fallback's usage, with the intent of removing it once substring hits are < 1% for a week. Call sites: `apply_results.py` intention_outcomes + concern_updates + fulfilled/frustrated, `interaction/resolution.py` priority scoring, `agent/daily_plan.py` audit and old-intention match.

**TTL + backstops** (`agent/state_update.decay_concerns`): three-layer eviction runs end-of-day. Layer 1 — TTL stale (`today - last_new_info_day >= concern_stale_days`, default 5): evict. Layer 2 — stuck-topic forced decay: `reinforcement_count >= 10` on a negative concern forces `decay=2` even for high-intensity (defeats the "high-intensity stickiness" that would otherwise freeze a stuck topic). Layer 3 — hard eviction: `reinforcement_count >= 15` on a negative concern drops it regardless of TTL. After thresholds, `reinforcement_count` decays `-1` per day (natural forgetting; prevents long-run systematic eviction). `intent.fulfilled` with a linked concern also deducts 3 from count — explicit reward that pushes a fulfilled concern out of stuck territory. Positive concerns are immune to both backstops so natural recurrence ("喜欢陆思远") is never suppressed.

**Merge via `add_concern`** performs topic-based dedup with alias-normalized `related_people` sets (`agent/name_aliases.normalize` sourced from `canon/worldbook/name_aliases.json`). For `其他` topic: exact people-set match required (Frankenstein guard still refuses to merge empty-people pairs). For other topics: any non-empty people intersection merges. Merge always bumps `reinforcement_count`, `last_reinforced_day`, and `last_new_info_day` (to `today`). New (non-merge) paths seed `last_reinforced_day` and `last_new_info_day` to `today` so day-0 concerns don't immediately look stale.

Max 4 concerns per agent; lowest intensity evicted when full. `ConcernTopic` is a `Literal[10]` enum (`models/agent.py`): `学业焦虑 / 家庭压力 / 人际矛盾 / 恋爱 / 自我认同 / 未来规划 / 健康 / 兴趣爱好 / 期待的事 / 其他`. Both positive buckets (`兴趣爱好`, `期待的事`) ensure positive concerns aren't pushed into `其他` and outcompeted by negative ones.

### Relationship (`models/relationship.py`)

```
target_name: str
target_id: str
favorability: int (-100 to 100)  # How much you like them
trust: int (-100 to 100)         # How much you trust them
understanding: int (0 to 100)    # How well you know them
label: str                       # 学生 | 老师 | 同学 | 室友 | 同桌 | 前后桌
                                 # Auto-insert picks from source+target role (see Apply Results)
recent_interactions: list[str]   # "Day N {+|−|·}scene_name" tags with valence
                                 # prefix from signed fav+trust delta; capped at
                                 # settings.max_recent_interactions (=10, FIFO)
```

`RelationshipChange`: `from_agent`, `to_agent`, `favorability`/`trust`/`understanding` (delta values).

### Scene (`models/scene.py`)

```
scene_index: int
day: int
time: str                        # e.g. "08:45"
name: str                        # e.g. "课间"
location: str                    # 教室 | 食堂 | 宿舍 | 走廊 | 操场 | 小卖部 | 图书馆 | 天台
density: SceneDensity            # high | high_light | low
max_rounds: int                  # Default 12
description: str
agent_ids: list[str]
groups: list[GroupAssignment]    # group_id, agent_ids, is_solo
injected_events: list[str]      # Random events injected into LOW→HIGH_LIGHT scenes
teacher_present: bool
teacher_action: str | None
opening_event: str               # Randomly selected from schedule.json opening_events, used as tick 0 event
```

`SceneConfig` (loaded from `schedule.json`) has these additional fields:
- `opening_events: list[str]` — pool of environment descriptions for the PDA loop's initial tick
- `is_free_period: bool` — marks 课间/午饭 for location-split scene generation
- `valid_locations: list[str]` — allowed locations for free periods (only used when `is_free_period=true`)
- `pref_field: Literal["morning_break", "lunch", "afternoon_break"] | None` — which `LocationPreference` field this slot maps to (only used when `is_free_period=true`)

A `model_validator` enforces that any `is_free_period=true` entry has a non-empty `pref_field` and `valid_locations`, and that `location` (the slot's default) is itself in `valid_locations`. This makes typos and missing fields fail immediately at `load_schedule()` time. Schedule data is the single source of truth — `scene_generator.py`, `daily_plan.py`, and `replan` all read directly from `SceneConfig`.

### Event (`models/event.py`)

```
id: str                          # e.g. "evt_1"
source_scene: str
source_day: int
text: str                        # Natural language description
category: str                    # gossip, conflict, achievement, teacher_talk, discipline, etc.
witnesses: list[str]             # Agent IDs who saw it happen
known_by: list[str]              # Agent IDs who know about it (starts = witnesses, grows via gossip)
spread_probability: float (0-1)  # Chance of being shared when a knower meets a non-knower
active: bool                     # False after event_expire_days
cite_ticks: list[int]            # Fix 13: 1-indexed [Tick N] grounding the event in the source conversation. Empty for system-generated events
group_index: int | None          # Fix 13: which scene group the event came out of. None for system-generated events. Used by M1 sanity check for per-group cite validation
```

### Dialogue Models (`models/dialogue.py`)

```
ActionType: speak | non_verbal | observe | exit

PerceptionOutput:                  # PDA tick loop output per agent per tick
  observation: str                 # What the agent noticed (1 sentence)
  inner_thought: str               # What they're thinking (1-2 sentences)
  emotion: Emotion                 # Updated emotion after perceiving
  action_type: ActionType          # What they decide to do
  action_content: str | None       # Speech/action text (null if observe)
  action_target: str | None        # Who it's directed at (null if general)
  urgency: int (1-10)             # How strongly they want to act
  is_disruptive: bool             # For non_verbal: would this get everyone's attention?

TurnOutput:                        # Legacy model (kept for reference, no longer used in PDA loop)
  speech: str
  directed_to: str | None
  inner_thought: str
  action: str | None
  emotion: Emotion
  want_to_continue: bool

SceneEndAnalysis:                            # Legacy model (kept for reference)
  key_moments: list[str]
  relationship_changes: list[RelationshipChange]
  fulfilled_intentions: list[str]
  events_discussed: list[str]
  memories: list[MemoryCandidate]
  new_events: list[NewEventCandidate]
  final_emotions: dict[str, str]
  new_concerns: list[ConcernCandidate]
  concern_updates: list[ConcernUpdate]

NarrativeExtraction:                         # Objective facts from dialogue (1 per group)
  key_moments: list[str]                     # Significant events as one-line summaries (Fix 13: no 推测词)
  fulfilled_intentions: list[str]            # "name:intention" format
  events_discussed: list[str]                # Event IDs
  new_events: list[NewEventCandidate]        # Gossip/conflicts that may spread

NewEventCandidate:                           # Fix 13: each new event must cite source ticks
  text: str
  category: str
  witnesses: list[str]
  spread_probability: float
  cite_ticks: list[int]                      # 1-indexed [Tick N] from the conversation log

IntentionOutcome:                            # Agent self-eval of one intention
  goal: str                                  # LLM's restatement of the intention goal
  status: Literal["fulfilled","attempted","frustrated","abandoned","pending","missed_opportunity"]
                                              # missed_opportunity (PR7): target was present but
                                              # the agent never engaged. Synthesized by the code
                                              # path in apply_scene_end_results when the LLM
                                              # silently drops an intent whose target is in the
                                              # same group but not in the direct-interaction set.
  brief_reason: str                          # One-sentence explanation

AgentReflection:                             # Per-agent subjective reflection (1 per agent per group)
  emotion: Emotion                           # Post-dialogue emotional state
  relationship_changes: list[AgentRelChange] # to_agent, favorability/trust/understanding deltas
  memories: list[AgentMemoryCandidate]       # text, emotion, importance, people, location, topics
  new_concerns: list[AgentConcernCandidate]  # text, source_event, emotion, intensity, related_people
  concern_updates: list[AgentConcernUpdate]  # concern_text, adjustment (±int)
  intention_outcomes: list[IntentionOutcome]  # Self-eval of pending intentions from the dialogue

AgentRelChange:                              # Single-direction, no from_agent (belongs to focal agent)
  to_agent: str
  favorability: int                          # Delta
  trust: int                                 # Delta
  understanding: int                         # Delta
  direct_interaction: bool = False           # Fix 5: LLM self-label; Python double-gate clamps to ±1 if False or unverified

AgentMemoryCandidate:                        # No agent field (belongs to focal agent)
  text: str
  emotion: str
  importance: int (1-10)
  people: list[str]
  location: str
  topics: list[str]

AgentConcernCandidate:                       # No agent field (belongs to focal agent)
  text: str
  source_event: str
  emotion: str
  intensity: int (1-10)
  related_people: list[str]
  positive: bool                             # True for positive concerns (warmth, anticipation)

AgentConcernUpdate:                          # No agent field (belongs to focal agent)
  concern_text: str
  adjustment: int                            # Positive=worsened, negative=soothed

SoloReflection:
  inner_thought: str
  emotion: Emotion
  activity: str
```

### Progress (`models/progress.py`) — Checkpoint for crash recovery

```
current_day: int
current_date: str
day_phase: "daily_plan" | "scenes" | "compression" | "complete"
current_scene_index: int
scenes: list[SceneProgress]
  scene_index: int
  scene_id: str
  phase: "grouping" | "interaction" | "scene_end" | "applying" | "complete"
  groups: list[GroupCompletion]
    group_index: int
    status: "pending" | "llm_done" | "applied"
next_exam_in_days: int           # Default 29 (first exam on day 30), reset to exam_interval_days after each exam
last_exam_day: int | None        # Day number of most recent exam (None if no exam yet)
total_days_simulated: int
last_updated: str                # ISO timestamp
seed: int | None                 # Persisted RNG seed for deterministic scene generation on resume
```

### Memory (`models/memory.py`)

```
KeyMemory:
  date: str                      # e.g. "Day 3"
  day: int
  people: list[str]
  location: str
  emotion: str
  importance: int (1-10)         # Only >= 7 gets persisted
  topics: list[str]
  text: str
```

---

## Key Algorithms

### Energy System (`agent/state_update.py`)

Energy changes per scene type:
| Scene | Delta |
|-------|-------|
| 上课 | -5 |
| 早读 | -3 |
| 晚自习 | -5 |
| 课间 | +5 |
| 午饭 | +15 |
| 宿舍夜聊 | -5 |

Sleep resets to 85. Clamped to 0-100.

### Academic Pressure Formula (`agent/state_update.py`)

On exam day (days_since_exam=0): pressure resets directly to base. Otherwise:
```
pressure = base + countdown_delta + recovery
```
- `base`: HIGH family → 50, MEDIUM → 30, LOW → 15
- `countdown_delta`: exam in ≤3 days → +15, ≤7 → +8, ≤14 → +3, else 0
- `recovery` (days 1+ after exam): -2 × days_since_exam

Note: exam shock (rank_drop × 2) is applied separately in `apply_exam_effects()`, not through this function.

### Emotion Decay (`agent/state_update.py`)

Two emotion sets control different behaviors:

- **`EXTREME_EMOTIONS`** (angry, excited, sad, embarrassed, jealous, guilty, frustrated, touched) — triggers orchestrator re-plan when an agent's emotion enters this set. Kept narrow to avoid re-plan storms.
- **`DECAYABLE_EMOTIONS`** — superset of `EXTREME_EMOTIONS` plus `ANXIOUS` and `BORED`. Used only by `maybe_decay_emotion()` for overnight reset. Low-arousal stuck states (anxious, bored) should decay overnight but should NOT trigger re-planning.

`maybe_decay_emotion()` checks `DECAYABLE_EMOTIONS` and resets to NEUTRAL with 50% probability when `scenes_since_extreme >= 2`. Called in `_end_of_day` with hardcoded `scenes_since_extreme=2` (overnight sleep = natural emotional reset).

### Relationship Regression (`agent/state_update.py`)

Asymmetric daily regression via `regress_relationships()`:

- **Negative** `favorability`/`trust` heal every day (nudge 1 point toward 0), unconditionally.
- **Positive** `favorability`/`trust` only decay after `settings.relationship_positive_stale_days` (default 5) consecutive days without interaction.
- **`understanding`** never regresses — it represents cognitive knowledge that doesn't fade overnight.

The `days_since_interaction` counter (on `Relationship` model, default 0) increments each end-of-day call and resets to 0 whenever `apply_scene_end_results` processes any `RelationshipChange` for that pair (even if all deltas are 0 — presence in the LLM output = interacted). This means actively maintained friendships stay stable, while neglected ones slowly erode, and negative relationships always heal.

### Relationship Labels (`agent/qualitative.py`)

`relationship_label(favorability, trust)` produces a qualitative label for LLM prompts. Uses a 7-tier **favorability-driven** system (trust is a secondary gate only for the top tier):

| Tier | Condition | Label |
|------|-----------|-------|
| 1 | `favorability >= 20 AND trust >= 10` | 很亲近的朋友 |
| 2 | `favorability >= 15` | 关系不错 |
| 3 | `favorability >= 8` | 还行，有些好感 |
| 4 | `favorability >= 0` | 普通同学 |
| 5 | `favorability >= -5` | 有点疏远 |
| 6 | `favorability >= -10` | 关系紧张 |
| 7 | `favorability < -10` | 互相看不顺眼 |

### Concern Decay (`agent/state_update.py`)

`decay_concerns(state, today)` runs at end of day. Three-layer eviction:

1. **TTL stale** (`today - last_new_info_day >= settings.concern_stale_days`, default 5): evict outright. PR3: TTL drives off `last_new_info_day` (not `last_reinforced_day`) so pure emotion reinforcement via `concern_updates` doesn't keep a zombie concern alive. `last_new_info_day` only advances when a genuinely new event arrives (via `add_concern` merge with `source="reflection"`/`"shock"`, or a fresh non-merge path).
2. **Backstop A — stuck-topic forced decay**: on a non-positive concern with `reinforcement_count >= 10`, force `decay=2` regardless of intensity. This defeats the "high-intensity stickiness" (decay=1 at intensity≥6) that would otherwise freeze a stuck topic for days. Purpose: catch the rumination failure mode where the LLM keeps re-emitting the same concern as `new_concerns` — TTL stays fresh but count accrues.
3. **Backstop B — hard stuck-topic eviction**: on a non-positive concern with `reinforcement_count >= 15`, drop regardless of TTL or intensity.

Positive concerns (`positive=True`) are **immune** to both backstops so "喜欢陆思远" reinforced daily doesn't get suppressed after 10-15 days (positive emotional obsession isn't a failure mode we're treating).

After the threshold checks, every surviving concern has `reinforcement_count` decayed by 1 (clamped to 0). Natural forgetting — prevents long-run (30+ day) simulations from systematically killing every negative concern that's ever been reinforced. **Ordering matters**: threshold checks run BEFORE the `-= 1` decrement, so `>= 15` / `>= 10` mean exactly that in runtime rather than `>= 16` / `>= 11`.

The companion reward: `apply_results.py` intention_outcomes path, on `fulfilled` with a linked concern, deducts 3 from `reinforcement_count` in addition to the usual -2 intensity. Fulfilling a concern is strong evidence that it's no longer stuck and should exit backstop territory.

### Concern Intensity Bump Throttling (`bump_concern_intensity`)

`bump_concern_intensity(c, day, delta, *, daily_cap=2, skip_cap=False)` (in `interaction/apply_results.py`) is the single chokepoint for raising a concern's intensity. Every intensify path goes through it: frustrated outcome (+1), missed_opportunity outcome (+1), `concern_updates` positive adjustment (+N), silence synthesis (+1), and the `add_concern` merge (+1).

Within one day, a single concern can absorb at most `daily_cap=2` accumulated intensify delta. The cap exists to defeat the "same concern hammered by 4-5 independent paths in one reflection cycle → +4~+7" anti-pattern; with the cap, frustrated + concern_updates can co-exist as two independent failure signals (the typical second hit), but a third or fourth path is silently dropped. The cap state lives on the concern itself (`last_bump_day`, `bumps_today`); it resets lazily on day rollover so callers never need to clear it.

Two opt-outs:
- **Drains** (`delta <= 0`) bypass the cap entirely. fulfilled's -2, concern_updates with negative adjustment, and any future relief paths always land in full.
- **`skip_cap=True`** is reserved for shock-source `add_concern` merges (currently only `apply_exam_effects` exercises it). Strong external events should not be throttled by reflection-bookkeeping budgets.

The `concern_updates` caller specifically only counts a positive update toward `reinforcement_count` / `last_reinforced_day` if the cap actually let a non-zero delta land — otherwise capped updates would still inflate Backstop A/B counters from updates the system rejected.

### Concern Topic Bucketing & Dedup

`ActiveConcern.topic` is a `Literal[10]` enum (`ConcernTopic` in `models/agent.py`): `学业焦虑 / 家庭压力 / 人际矛盾 / 恋爱 / 自我认同 / 未来规划 / 健康 / 兴趣爱好 / 期待的事 / 其他`. The two positive buckets (`兴趣爱好`, `期待的事`) give positive concerns a habitat so they don't get pushed into `其他` and evicted by negative ones. The Pydantic `Literal` is enforced by Instructor on every LLM call so drift like `英语焦虑` vs `学业焦虑` cannot create parallel buckets.

`add_concern(state, new, today, *, source="reflection"|"shock", skip_cap=False)` (in `interaction/apply_results.py`) is the single entry point for new concerns from all three callers (`apply_scene_end_results` self-reflection, `nightly_compress`, `exam.apply_exam_effects`). The `source` kwarg is currently always `"reflection"` (both scene-end and nightly) or `"shock"` (exam) — both advance `last_new_info_day`; the Literal is kept open for a future `"consolidation"` path that would leave the TTL alone, though today `_apply_consolidation` mutates state directly without going through `add_concern`. Logic:

1. **Find existing match** via `_find_existing_concern` with alias-normalized `related_people` (so `爸爸` and `父亲` collide into one bucket):
   - For categorized topics (everything except `其他`): same topic + any non-empty people overlap → merge.
   - For `其他`: same topic + EXACT people set match → merge. If either side has empty people, NEVER merge (Frankenstein guard — empty-people `其他` buckets are almost always unrelated).
2. **Merge**: bump intensity by 1 via `bump_concern_intensity` (so `source="reflection"` merges respect the per-day cap; `source="shock"` passes `skip_cap=True` and additionally anchors intensity at `max(existing, incoming)` before the +1 so a follow-up shock can drive the floor up). Preserve the old `text` in `text_history` (max 3 entries, FIFO) before overwriting, append the new `source_event` with `；` as a delimiter (capped `[-500:]` — tail-biased for recency). Unconditionally update `last_reinforced_day = today`, `reinforcement_count += 1`, and — when `source in ("reflection", "shock")` — `last_new_info_day = today`.
3. **No match** (new concern path): cap intensity at `settings.concern_autogen_max_intensity` (=6) unless `skip_cap=True`, **seed `last_reinforced_day = today` AND `last_new_info_day = today`** (critical — without seeding the latter, a brand-new concern on day 0 would satisfy `today - last_new_info_day == today >= concern_stale_days` and be immediately evicted by `decay_concerns` later the same day). Then either append or evict the lowest-intensity concern when at `max_active_concerns` (=4).

The only production caller of `skip_cap=True` today is `apply_exam_effects` (`world/exam.py`): when a student's `rank_change <= -3` after an exam, an `ActiveConcern(topic="学业焦虑", intensity=min(10, 5 + magnitude))` (8/9/10 ladder) is pushed via `add_concern(skip_cap=True, source="shock", today=day)`.

**Name aliases** (`agent/name_aliases.py`, `canon/worldbook/name_aliases.json`): a hand-maintained mapping from informal appellations to canonical form (爸爸 → 父亲, 妈妈 → 母亲, etc.). Only applied inside `_find_existing_concern`'s comparison — rendered prompts, narrative, and concern.text all keep whatever spelling the LLM used. New aliases (class nicknames, etc.) are added via PR; no automatic learning.

**Concern id + lookup**: every concern has a stable 6-hex `id` (auto-generated). `id_history` preserves ids of concerns that were merged away (populated by `_apply_consolidation`'s merge branch). All LLM prompts render `[ref: <id>]` on each concern, and callers use `concern_lookup` to resolve references — see the ActiveConcern section above for details.

**Backfill migration** (`scripts/backfill_concern_ids.py`): one-shot script for pre-PR1 state.json files. Assigns a deterministic `id` (blake2b of `source_day:source_scene:text[:30]:idx`), seeds `last_new_info_day = max(source_day, last_reinforced_day)`, initializes `id_history = []` and `reinforcement_count = 0`. Idempotent: re-running on a fully migrated file is a no-op. The script fails fast if two concerns in the same file hash to the same id — expected to never fire since the `idx` (list position) tiebreaker handles same-day same-prefix collisions. Run manually via `uv run python scripts/backfill_concern_ids.py` before the first simulation run on a PR1+ codebase.

### Exam Score Generation (`world/exam.py`)

**Trigger**: when `progress.next_exam_in_days` reaches 0, the orchestrator calls `_run_exam()` at the start of the day, before daily plans. Full chain: `load_previous_exam_results()` → `generate_exam_results()` → `apply_exam_effects(today=day)` → `save_exam_results()` → reload states → `HomeroomTeacher.post_exam_actions()` → set `progress.last_exam_day` and reset countdown.

`apply_exam_effects` mutates `academic_pressure` (+`abs(rank_change)*2`), `emotion`, `energy` (-15), AND now writes a high-intensity `学业焦虑` `ActiveConcern` for `rank_change <= -3` via `add_concern(skip_cap=True)` so the shock survives the autogen cap. The `today` parameter (required) sets `last_reinforced_day` so the new concern doesn't immediately look stale to `decay_concerns`.

**Teacher exam context**: `format_teacher_exam_context()` produces a class-level overview (total students, class average, top 3, struggling/improved students) instead of the per-student view.

Not LLM-driven — pure formula:
```
score = base(overall_rank) + subject_mod(±5 for strengths/weaknesses)
      + effort_mod(pressure/100 × attitude_coeff × 5) + gaussian_noise(0, variance)
```
- Base scores: top=88, 上游=78, 中上=70, 中游=62, 中下=54, 下游=45
- Variance inversely correlated with rank: top=3.0, 下游=10.0 (stronger students more consistent)
- Attitude coefficient maps `study_attitude` text → 0.0-1.2 multiplier
- Post-exam effects: rank drop ≥5 → SAD, rank rise ≥5 → EXCITED, high-pressure family + rank>5 → ANXIOUS, energy -15
- Results saved to `simulation/world/exam_results/day_NNN.json`

### PDA Tick Resolution (`interaction/resolution.py`)

Pure Python, no LLM calls. Resolves one tick of the Perception-Decision-Action loop.

**State** (`ResolutionState`): tracks queued speakers (agent_id → PerceptionOutput + ticks_queued), consecutive all-observe count, tick count, and active agent set.

**Speaker arbitration**: when multiple agents want to SPEAK in the same tick, a resolution score determines who speaks:
```
resolution_score = urgency + bonuses
```
Bonuses:
- +5 if agent was addressed in the previous resolved speech (action_target matches agent name)
- +3 to +6 if agent has an unfulfilled intention targeting someone present (base +3, scaled up to +6 by linked concern intensity: `3 * max(1.0, concern.intensity / 5.0)`)
- +3 per tick queued (from previous ticks)

**Urgency clustering fallback**: if variance of urgency values among this tick's speakers is ≤ 2 (everyone equally urgent), bonuses become the primary signal and urgency is demoted to a 0.1× tiebreaker. This prevents urgency from dominating when LLM outputs cluster.

Ties broken randomly via the provided `rng`.

**Queue management**: losers are queued with their PerceptionOutput. Queued agents whose action_target has exited are discarded. Queued outputs expire after 3 ticks.

**Action resolution by type**:
| ActionType | Resolution |
|------------|-----------|
| SPEAK | Competes for single speaker slot via scoring |
| NON_VERBAL | All resolve simultaneously into resolved_actions. If is_disruptive=True, generates environmental_event string: `【動作】{name}: {content}` |
| OBSERVE | No action. Non-disruptive, counts toward quiet tick |
| EXIT | Agent removed from active set |

**Scene termination** (`quiet_tick`): scene ends when `consecutive_quiet >= settings.consecutive_quiet_to_end` (default 4) AND `tick_count >= settings.min_ticks_before_termination` (default 3). A "quiet tick" means no speech resolved, no queued speakers waiting, and no environmental event (disruptive action). Non-disruptive NON_VERBAL actions do not block termination.

**Embodied pacing label** (Fix 8B): `_compute_pacing_label(tick, max_rounds)` in `interaction/turn.py` translates `tick / max_rounds` into one of three short Chinese strings (`刚开始` / `在聊` / `差不多该散了`). Labels are deliberately deflationary — "差不多该散了" rather than "高潮即将到来" — to discourage the LLM from staging dramatic climaxes near scene boundaries. The label is only injected into `perception_dynamic.j2` (under `## 场景节奏`) when it crosses a threshold from the previous tick: tick 0 (`刚开始`) is silently consumed by the loop's init value, the transition to `在聊` fires once, and the transition to `差不多该散了` fires once. Every other tick passes an empty `scene_pacing_label` so the template's `{% if %}` block renders nothing — preventing the same string from polluting 12-22 consecutive perception prompts.

### Gossip Propagation (`world/event_queue.py`)

Before each group interaction:
1. Find active events where at least one group member knows it and at least one doesn't
2. Roll `spread_probability` — if success, inject event into knower's context
3. LLM decides naturally whether to mention it
4. Only events listed in `events_discussed` output actually update `known_by` (avoids false positives)

### Memory Retrieval (`memory/retrieval.py`)

Tag-overlap based (not embedding-based):
1. Extract trigger tags from current scene: present agent names/IDs, location, scene name
2. For each key memory, compute overlap = |memory_tags ∩ triggers| where memory_tags = people + topics + location
3. Filter to memories with overlap > 0
4. Sort by (importance DESC, overlap DESC), return top K (default 10)

### Homeroom Teacher (He Min)

He Min is a full LLM-driven agent, participating in scenes like any student. She goes through daily plan generation, perception, dialogue, self-reflection, and nightly compression — using the same pipeline but with role-aware prompts.

**Scene participation** (probabilistic — she doesn't attend every scene):
| Scene type | Probability | Notes |
|-----------|-------------|-------|
| 晚自习 | 20% | Joins as full participant |
| 课间 (free period) | 10% | Appears in 教室 |
| 午饭 (free period) | 30% | Appears in 食堂 |
| 宿舍夜聊 | Never | Not in dorm |

**Role-aware prompt adaptations**:
- `system_base.j2`: "上海高中老师" instead of "上海高中生" language guidance
- `daily_plan.j2`: teacher-specific need prompts (student attention, parent calls, lesson prep). No location preferences section (teacher doesn't choose free-period locations). Academic fields (成绩/目标/学习态度) skipped.
- `self_narrative.j2`: conditional identity ("班主任兼语文老师" vs "高中生"), narrative/self_concept instructions adapted for teacher role
- `nightly_compress.j2`: uses `role_description` variable for opening line identity
- `perception_dynamic.j2` + `dialogue_turn.j2`: "班主任正在附近，说话注意点！" warning only shown to students (`teacher_present and not is_teacher`)
- `self_reflection.j2`: teacher's intention evaluation acknowledges observing/guiding students as part of her role
- `perception_static.j2`: dorm scene examples show NON_VERBAL + SPEAK patterns
- Re-planning skipped for teacher (no location preferences)
- **Suppression effect**: When `teacher_present=true`, the perception template warning naturally suppresses student speech urgency. The teacher herself does NOT see this warning (guarded by `is_teacher`).
- `prepare_context()` provides `is_student`/`is_teacher` booleans to all templates via the context dict

**Grouping**: teacher never goes solo — `_should_be_solo()` returns `False` early for non-students, regardless of energy/emotion state.

**Cold start**: He Min starts with empty relationships (`{}`). Her backstory names specific students she monitors, and the "班主任" position gives LLM enough context. Relationships populate naturally after scene interactions.

**Rule-driven behaviors** (`world/homeroom_teacher.py`):
- **Post-exam talks**: `post_exam_actions()` — for each student whose rank dropped ≥3 places, 70% chance of a teacher-student talk. Creates gossip events via `EventQueueManager` that spread through the student network.
- **Patrol events**: `patrol_event()` — injected into 晚自习/早读 (with internal 30% probability gate) and 上课 (30% gate applied in `scene_generator.py`) when the teacher is NOT a full scene participant. Events like "何老师巡视时发现有人在聊天" appear in `injected_events`.

---

## LLM Calls

All LLM calls go through `llm/client.py:structured_call()` which uses Instructor + LiteLLM to guarantee Pydantic model output. `structured_call()` returns an `LLMResult` dataclass containing the parsed Pydantic model (`.data`), token counts (`.tokens_prompt`, `.tokens_completion`), and cost (`.cost_usd`). Token usage is extracted from the raw completion response via `create_with_completion()`, and cost is calculated using `litellm.completion_cost()`. Each call has a dedicated Jinja2 template in `src/sim/templates/`.

| Call Type | Template | Response Model | Temperature | Max Tokens | Per Scene |
|-----------|----------|---------------|-------------|------------|-----------|
| Perception (PDA) | `perception_static.j2` (system) + `perception_dynamic.j2` (user) | `PerceptionOutput` | 0.9 | 32000 | N × ticks |
| Daily plan | `daily_plan.j2` | `DailyPlan` | 0.7 | 32000 | — |
| Solo reflection | `solo_reflection.j2` | `SoloReflection` | 0.9 | 32000 | 1 per solo |
| Narrative extraction | `scene_end_analysis.j2` | `NarrativeExtraction` | 0.3 | 32000 | 1 per group |
| Self-reflection | `self_reflection.j2` | `AgentReflection` | 0.7 | 32000 | N per group |
| Nightly compression | `nightly_compress.j2` | `CompressionResult` | 0.5 | 32000 | — |

**Emotion guidance**: templates that output an `emotion` field (`perception_dynamic.j2`, `dialogue_turn.j2`, `self_reflection.j2`) now list all 15 Emotion enum values with Chinese translations (e.g. `happy=开心, excited=兴奋, ... neutral=没什么特别的`) and include a baseline anchor (`课间闲聊大部分时候是 bored/curious/calm`) to prevent drift toward dramatic emotions in mundane scenes.

**Reflection intensity calibration** (Fix 1) — `self_reflection.j2`, `nightly_compress.j2`, and `solo_reflection.j2` share a Jinja partial `partials/_intensity_scale.j2` that defines a 1-10 importance/intensity scale ("1-2 = 路过的小情绪 / 9-10 = 创伤级"), default-empty `new_concerns`, and explicit "trivial scene → empty memories" / "solo scene → close to baseline" rules. The partial is included once at the top of `nightly_compress.j2` so it covers both 任务2 (memories) and 任务3 (new concerns); `solo_reflection.j2` carries an inline 独处场景 anchor (≤25 字 inner_thought, banned 小说化 phrases) since it doesn't emit memory/concern lists; `nightly_compress.j2` 任务1 also gets a 中性记录式 style requirement to avoid 叙述者口吻.
| Self-narrative | `self_narrative.j2` | `SelfNarrativeResult` | 0.7 | 32000 | — |
| Re-plan | `replan.j2` | `ReplanResult` | 0.7 | 32000 | — |

Narrative extraction + N self-reflections run concurrently after each group dialogue (replacing the single `SceneEndAnalysis` call). Effective latency ≈ 1 LLM call despite N+1 total calls.

All templates include `system_base.j2` (shared system prompt establishing the Shanghai 建宁中学 setting as a 市重点 high school, role-aware language guidance — "上海��中生" for students vs "上海高中老师" for teacher — natural dialogue requirements, role consistency rules, few-shot examples of natural Chinese teen speech patterns, and inner_thought voice guidelines with bad/good examples to prevent self-analysis-report style thinking). After the 要求 section, `system_base.j2` includes a 语域约束 (register constraints) section (student vocabulary limits, colloquial replacements for formal connectives, no 成语, inner_thought ≤ 25 chars) and a 禁用词 (banned words) section listing academic/literary phrases whose presence counts as a failure.

Context assembly (`agent/context.py:prepare_context()`):
- Profile summary (name, gender, personality, speaking style, academic rank/strengths/weaknesses/study attitude/homework habit/target, position, family expectation/situation, long-term goals, backstory, inner_conflicts)
- Relationships filtered to agents present in the scene, with qualitative `label_text` computed from `relationship_label()` — a 7-tier favorability-driven system (see Key Algorithms)
- Today's events so far (`today.md`)
- Recent memory (last 3 days from `recent.md`)
- Relevant key memories (tag-overlap retrieval, max 10)
- Pending unfulfilled intentions (with `satisfies_concern` and `pursued_days` for display)
- **Active concerns** — persistent emotional preoccupations with qualitative `intensity_label` (轻微/中等/较强/强烈) replacing raw "强度 X/10"
- **Qualitative state labels** — `energy_label` (精疲力尽→精神充沛), `pressure_label` (轻松→几乎扛不住), `exam_label` (月考还远→月考近在眼前) via `agent/qualitative.py`
- **Self-narrative** — narrative text + `self_concept` (up to 4 identity bullets) + `current_tensions` (up to 3 struggle bullets) from `self_narrative.json`
- **Role booleans** — `is_student` and `is_teacher` (derived from `profile.role`) used by templates for role-conditional rendering
- Scene info (time, location, who's present)
- Known events (gossip the agent knows about)
- Exam countdown context
- **Inner conflicts** — character's permanent internal contradictions. Displayed as "你内心的永恒矛盾" to distinguish from `current_tensions` ("你最近在和这些搏斗")
- PDA tick loop params (used by `perception_static.j2` + `perception_dynamic.j2`):
  - `latest_event`: what just happened (string)
  - `scene_transcript`: formatted public events so far
  - `private_history`: agent's own prior observations + inner thoughts
  - `tick_emotion`: in-memory emotion override (updated each tick without persisting to state)
  - `emotion_trace`: last 5 emotion values from the current scene's tick history (displayed as "你的情绪变化" chain when >1 entry)
- **`sampled_joy_source`** (P2.A): one entry from `profile.joy_sources` picked deterministically per `(day, scene.time, scene.location, agent_id)` via `_sample_joy_source` (uses `hashlib.sha1` for cross-process stability — the builtin `hash()` would be `PYTHONHASHSEED`-randomized and break snapshot-resume determinism). Rendered by `perception_static.j2` and `solo_reflection.j2` under "## 今天你心里惦记着的一件小事" when non-None. The injection is intentionally low-volume — one short positive hook into otherwise tense scenes — and skipped silently when the profile has no `joy_sources` configured. Threaded into `prepare_context` via the new `day` parameter; callers are `interaction/turn.py` (perception), `interaction/self_reflection.py` (post-scene reflection), and `interaction/solo.py` (solo-scene reflection).

`system_base.j2` no longer contains the line "不要刻意戏剧化，允许平淡的日常对话" (P2.A.1). It was inadvertently suppressing positive moments alongside drama; with joy_source injection + self_reflection's positive-concern guidance now carrying the "everyday is OK" load explicitly, the negative-only suppression line was net-harmful. The 禁用词 / inner_thought / register constraints all stay.

Every LLM call is logged to `simulation/days/day_NNN/debug/scene_name/group_id/calltype_timestamp.json` with full input/output, latency, and token counts. Costs are appended to `simulation/costs.jsonl`.

---

## File Layout

```
canon/                           # Class-story canon (pre-run, hand-authored)
  cast/                          # People
    profiles/                    # 10 student + 1 teacher JSON profiles (immutable source of truth)
      lin_zhaoyu.json, tang_shihan.json, jiang_haotian.json, lu_siyuan.json,
      he_jiajun.json, shen_yifan.json, cheng_yutong.json, su_nianyao.json,
      fang_yuchen.json, he_min.json
    portraits/                   # Derived 320×320 portrait PNGs (checked in, regenerated by scripts/generate_portraits.py)
    visual_bible.json            # Per-agent visual config (sprite_source, crop, colors, motif) for share-card rendering
  worldbook/                     # World rules
    schedule.json                # 8 daily scenes: 07:00 早读 → 22:00 宿舍夜聊 (3 with is_free_period=true)
    location_events.json         # Location-specific opening events for free period scenes
    scene_ambient_events.json    # Fix 12: per-location ambient events — mixed plain strings and dicts with `text` + `cooldown_days` fields
    catalyst_events.json         # Conditional trigger definitions. PR4: `concern_stalled` 人际矛盾 and 学业焦虑 each split into `-relational` (require_related_people) and `-generic` (require_empty_related_people) entries — mutex on related_people presence
    name_aliases.json            # PR1: hand-maintained informal→canonical name mapping (爸爸→父亲 etc). Nested under `aliases` key; `_doc` prefix is metadata. Loader: `agent/name_aliases.py`

simulation/                      # Simulation output (post-run, generated — tracked in git so Vercel builds see it)
  sim.log                        # Main log (10MB rotation, gitignored)
  costs.jsonl                    # Per-call cost tracking (gitignored)
  state/                         # Per-agent runtime state (was top-level `agents/`); created by init_world.py
    <agent_id>/
      profile.json               # Copy of character profile
      state.json                 # Current emotion, energy, pressure, plan, day, active_concerns
      relationships.json         # Sparse relationship map {target_id: Relationship}
      self_narrative.json        # Structured self-narrative (narrative + self_concept + current_tensions)
      self_narrative.md          # Human-readable mirror of narrative text (not read as source)
      key_memories.json          # Permanent memories (importance ≥ key_memory_write_threshold, Fix 14: =3)
      today.md                   # Raw events from current day (cleared nightly)
      recent.md                  # Compressed daily summaries (rolling window)
  world/                         # Global world state (was top-level `world/`); created by init_world.py
    progress.json                # Simulation checkpoint
    event_queue.json             # Active + expired events
    ambient_cooldowns.json       # Per-event cooldown state for ambient events with cooldown_days
    catalyst_cooldowns.json      # Per-trigger cooldown state for catalyst events
    exam_results/                # Per-exam result files (day_NNN.json)
    snapshots/                   # Pre-scene agent snapshots for crash recovery (transient)
      scene_N/
        .complete                # Marker: snapshot fully written
        <agent_id>/
          state.json, relationships.json, key_memories.json, today.md
  days/                          # Per-day sim output (was top-level `logs/`)
    day_NNN/
      HHMM_scenename.json        # One file per scene, all groups inside (frontend-ready)
      scenes.json                # Scene index for frontend navigation
      trajectory.json            # Per-agent location/emotion trajectory for frontend
      agent_snapshots/           # End-of-day state copy used by chat-mode time travel
        <agent_id>/
          state.json, relationships.json, self_narrative.json
      debug/                     # Raw LLM call logs (gitignored)
        scene_name/
          group_id/
            calltype_timestamp.json

assets/                          # External media
  fonts/                         # OFL-licensed Chinese fonts (tracked in git via whitelist)
    LXGWWenKai-Regular.ttf, NotoSerifSC-{Regular,Bold}.ttf, NotoSansSC-{Regular,Bold}.ttf, LICENSES.md
  moderninteriors-win/           # LimeZu Modern Interiors sprite sheets (commercial, gitignored)
  modernexteriors-win/           # LimeZu Modern Exteriors (commercial, gitignored)
  Complete_UI_Essential_Pack_v2.4/  # Commercial UI pack (gitignored)
  kenney_emotes-pack/, 32x32_emote-chat-balloons_pack/, bubble emotes july update.png  # Emote packs (gitignored)

.cache/
  cards/                         # Share-card render cache (gitignored, regenerated from sim data)
  self_test/                     # Phase 0 self-test output PNGs (gitignored)

tests/                           # Unit tests (pytest)
  test_resolution.py             # PDA tick resolution logic (31 tests)
  test_narrative.py              # Transcript formatting and summarization
  test_models.py                 # Pydantic model validation (PerceptionOutput, ActionType)

scripts/
  init_world.py                  # Initialize simulation/state/ and simulation/world/ from canon/cast/profiles/
  inspect_state.py               # Debug tool to view current simulation state
  export_frontend_data.py        # Copy simulation output → web/public/data/
  generate_behavioral_anchors.py # Fix 5: one-shot LLM generation of behavioral_anchors for each character
  backfill_concern_ids.py        # PR1 migration: seed id / id_history / last_new_info_day / reinforcement_count on legacy state.json files
  sanity_check/                  # Phase 1+1.5 milestone scripts (M1-M6)
    m1_ungrounded_events.py      # Fix 13: count events with missing or invalid cite_ticks
    m2_per_day_memory_cap.py     # Fix 14: assert per-day key_memories ≤ per_day_memory_cap
    m3_concern_topic_dedup.py    # Fix 2: assert each (agent, topic) bucket has ≤1 entry (其他 informational)
    m4_empty_relationships.py    # Fix 4: assert no agent has an empty relationships map
    m5_positive_emotion_ratio.py # Fix 1+3: positive emotion share across reflections ≥ 25%
    m6_per_agent_memory_count.py # Fix 1+14: per-agent memory count + importance histogram (OBSERVE only)
    run_all.py                   # Aggregate runner — emits a Markdown report

src/sim/
  main.py                        # CLI entry point (argparse → Orchestrator.run)
  config.py                      # Settings via pydantic-settings (SIM_ env prefix)
  models/                        # Pydantic models (agent, dialogue, event, memory, progress, relationship, scene, trajectory)
  agent/                         # Agent-level logic
    storage.py                   # AgentStorage + WorldStorage (file I/O, atomic writes, structured self_narrative load/save)
    context.py                   # prepare_context() — assembles full LLM context; also computes `intended_targets_present` (PR7) for perception_dynamic
    daily_plan.py                # generate_daily_plan() — intention generation with concern linkage + carry-forward; PR8 audit-retry with per-day/per-agent budget
    self_narrative.py            # generate_self_narrative() — periodic identity reflection (structured: narrative + self_concept + current_tensions)
    qualitative.py               # Numeric → qualitative label helpers (energy, pressure, intensity, relationship, exam)
    name_aliases.py              # normalize() — hand-maintained informal→canonical name mapping (爸爸 → 父亲); used only in concern comparison, never in rendered prompts
    replan.py                    # maybe_replan() — reactive location changes between scenes
    state_update.py              # Energy, pressure, emotion, concern decay formulas (PR3: three-layer decay + backstops)
  world/                         # World-level logic
    schedule.py                  # load_schedule() from canon/worldbook/schedule.json
    scene_generator.py           # SceneGenerator — lazy per-config scene generation, free period location splitting, ambient event cooldowns
    grouping.py                  # group_agents() — solo detection + affinity-based clustering
    event_queue.py               # EventQueueManager — add, spread, expire events
    catalyst.py                  # CatalystChecker — conditional event injection based on agent state (concern_stalled, positive_concern_stalled, isolation, relationship_threshold, intention_stalled)
    exam.py                      # generate_exam_results(), apply_exam_effects(), format_exam_context()
    homeroom_teacher.py          # HomeroomTeacher — rule-driven post-exam talks + patrol events
  interaction/                   # Scene execution logic
    orchestrator.py              # Orchestrator — main loop, serialize_tick_records(), scene file + scenes.json output
    turn.py                      # run_perception() + run_group_dialogue(group_index=) — PDA tick loop with perception gating
    resolution.py                # resolve_tick() — PDA tick resolution (speaker arbitration, queue, scene end)
    narrative.py                 # format_public_transcript(), format_agent_transcript(), format_latest_event()
    scene_end.py                 # run_scene_end_analysis() — objective narrative extraction (post-dialogue)
    self_reflection.py           # run_agent_reflection() + run_all_reflections() — per-agent subjective reflection
    apply_results.py             # apply_scene_end_results() + apply_solo_result() + write_scene_file() + concern_match() + concern_lookup() + add_concern(source=..., skip_cap=...); PR7 missed_opportunity synthesis
    solo.py                      # run_solo_reflection() — solo agent inner monologue
  llm/                           # LLM infrastructure
    client.py                    # structured_call() via Instructor + LiteLLM; auto-fallback to llm_fallback_model on failure
    prompts.py                   # render() — Jinja2 template rendering
    logger.py                    # log_llm_call() — per-call JSON logging + cost tracking
  memory/                        # Memory management
    compression.py               # nightly_compress() — summarize today → recent, extract key memories
    retrieval.py                 # get_relevant_memories() — tag-overlap retrieval
    writer.py                    # Helper wrappers for today.md and key_memory writes
  templates/                     # Jinja2 prompt templates (all in Chinese)
    partials/
      _intensity_scale.j2        # Shared intensity / importance 1-10 scale + default-empty new_concerns + trivial-scene rules (Fix 1)
      _anchors.j2                # Fix 5: behavioral anchors (must_do / never_do / speech_patterns) — included in perception, reflection, daily_plan, self_narrative
    system_base.j2               # Shared system prompt (high school setting + dialogue rules + few-shot teen speech examples). P2.A.1: the "不要刻意戏剧化" line was removed — it was over-suppressing positive concerns alongside drama
    perception_static.j2         # PDA perception system message — agent identity, relationships, memories, scene info (stable within a scene; enables DeepSeek prefix caching). P2.A.4: renders sampled_joy_source under "## 今天你心里惦记着的一件小事" when present
    perception_dynamic.j2        # PDA perception user message — transcript, latest_event, emotion trace, output format instructions with all 15 Emotion values + Chinese translations (changes per tick)
    dialogue_turn.j2             # Legacy per-turn dialogue (kept for A/B comparison reference) — includes all 15 Emotion values + Chinese translations, intimacy hint for close relationships (favorability >= 15)
    daily_plan.j2                # Morning plan with concern linkage (satisfies_concern), yesterday intentions display with tiered urgency language, joy_sources section, concern text_history visibility, self_concept + current_tensions. P2.A.6 adds an explicit "everyday joy intentions are valid (satisfies_concern=null)" nudge
    solo_reflection.j2           # Solo inner monologue (qualitative labels, self_concept + current_tensions). P2.A.5: also renders sampled_joy_source above "## 任务" — solo scenes are where rumination concentrates, so the positive hook matters most here
    scene_end_analysis.j2        # Post-dialogue objective narrative extraction
    self_reflection.j2           # Per-agent reflection (qualitative labels, intention_outcomes self-eval, self_concept + current_tensions) — includes all 15 Emotion values + Chinese translations, good/bad examples for memories and concerns output. P2.B.1: examples symmetrized between negative + positive (added a "那首歌她竟然也听" intensity-3-5 positive example, a touched memory example), and explicit guidance under concern_updates that positive concerns may emit a +1 reinforce on small same-day signals to avoid silent decay
    nightly_compress.j2          # Daily summary + permanent memory + concern extraction (qualitative intensity labels)
    self_narrative.j2            # Periodic structured self-reflection (narrative compressed to 50-100 chars 碎碎念 style for students, self_concept + current_tensions)
    replan.j2                    # Reactive location re-planning (qualitative concern labels)
```

---

## Configuration (`config.py`)

All settings via `pydantic-settings` `BaseSettings`, loaded from `.env` file, overridable with `SIM_` env prefix:

| Setting | Default | Description |
|---------|---------|-------------|
| `llm_model` | `deepseek/deepseek-chat` | LiteLLM model identifier |
| `llm_fallback_model` | `openrouter/google/gemini-3-flash-preview` | Fallback model for structured calls when primary fails validation |
| `creative_temperature` | 0.9 | Dialogue turns, solo reflection |
| `analytical_temperature` | 0.3 | Scene-end analysis |
| `plan_temperature` | 0.7 | Daily plan generation |
| `compression_temperature` | 0.5 | Nightly compression |
| `max_tokens_per_turn` | 32000 | Dialogue turn max tokens |
| `max_tokens_scene_end` | 32000 | Scene-end analysis max tokens |
| `max_tokens_daily_plan` | 32000 | Daily plan max tokens |
| `max_tokens_compression` | 32000 | Nightly compression max tokens |
| `max_tokens_solo` | 32000 | Solo reflection max tokens |
| `max_retries` | 3 | LLM call retries |
| `min_ticks_before_termination` | 3 | Minimum ticks before scene can end |
| `consecutive_quiet_to_end` | 4 | Consecutive quiet ticks to trigger scene end |
| `perception_temperature` | 0.9 | PDA perception LLM call temperature |
| `max_tokens_perception` | 32000 | PDA perception max tokens |
| `max_concurrent_llm_calls` | 5 | Async semaphore limit |
| `exam_interval_days` | 30 | Days between exams |
| `event_expire_days` | 3 | Days before events become inactive |
| `recent_md_max_weeks` | 4 | Rolling window for recent.md |
| `max_key_memories` | 10 | Max key memories in context |
| `key_memory_write_threshold` | 3 | Fix 14: minimum importance to write a memory (lowered from hardcoded 7) |
| `per_day_memory_cap` | 2 | Fix 14: post-compression cap on today's memory count per agent |
| `solo_energy_threshold` | 20 | Energy below this → solo (Fix 18: lowered from 25) |
| `self_narrative_interval_days` | 3 | Days between self-narrative regeneration |
| `self_narrative_temperature` | 0.7 | Self-narrative LLM temperature |
| `max_tokens_self_narrative` | 32000 | Self-narrative max tokens |
| `replan_temperature` | 0.7 | Re-plan LLM temperature |
| `max_tokens_replan` | 32000 | Re-plan max tokens |
| `max_active_concerns` | 4 | Max concerns per agent |
| `concern_decay_per_day` | 2 | Fix 2: end-of-day intensity decay (was effectively 1) |
| `concern_stale_days` | 5 | Fix 2: days without reinforcement → evict regardless of intensity |
| `concern_autogen_max_intensity` | 6 | Cap for reflection/compression-generated concerns; bypassed via `skip_cap=True` |
| `daily_plan_audit_retry` | False | PR8: enable retry when high-intensity addressable concerns are unhooked. Default off — observe one week of audit warning volume before flipping on |
| `daily_plan_audit_max_retries_per_call` | 1 | PR8: retries per single `generate_daily_plan` call |
| `daily_plan_audit_max_retries_per_day_per_agent` | 1 | PR8: retries per (day, agent_id) — budget resets implicitly each day |
| `relationship_positive_stale_days` | 5 | Days without interaction before positive favorability/trust decay starts |
| `max_recent_interactions` | 10 | Per-relationship FIFO cap on `recent_interactions` tag log (populated on any non-zero relationship_change) |

---

## Initialization (`scripts/init_world.py`)

1. Wipes `simulation/state/`, `simulation/world/`, and `simulation/days/` directories
2. For each character in `canon/cast/profiles/*.json`:
   - Copies profile to `simulation/state/<id>/profile.json`
   - Creates initial state (energy=85, pressure based on family: 高→60, 中→35, 低→15, emotion=neutral, active_concerns=[])
   - Creates relationships from preset pairs (defined in `PRESET_RELATIONSHIPS` — roommates, seatmates, desk neighbors with initial favorability/trust values)
   - Creates empty `key_memories.json`, `today.md`, `recent.md`, `self_narrative.md`
3. Creates `simulation/world/progress.json` (day 1, daily_plan phase, next_exam_in_days=29)
4. Creates empty `simulation/world/event_queue.json`
5. Creates `simulation/world/exam_results/` directory

### Dorm Assignments (hardcoded in `world/scene_generator.py`)

```
male_301:   lin_zhaoyu, jiang_haotian, lu_siyuan, shen_yifan
male_303:   he_jiajun
female_302: tang_shihan, cheng_yutong, su_nianyao, fang_yuchen
```

### Preset Relationships (from `scripts/init_world.py`)

```
lin_zhaoyu ↔ tang_shihan    同桌    fav: 10/5   trust: 5/5
lin_zhaoyu ↔ jiang_haotian  前后桌  fav: 5/10   trust: 0/5
lin_zhaoyu ↔ lu_siyuan      室友    fav: 15/15  trust: 10/10
lin_zhaoyu ↔ shen_yifan     室友    fav: 10/10  trust: 5/5
jiang_haotian ↔ lu_siyuan   室友    fav: 5/5    trust: 5/5
jiang_haotian ↔ shen_yifan  室友    fav: -5/0   trust: 0/0
cheng_yutong ↔ su_nianyao   同桌    fav: 5/10   trust: 5/5
su_nianyao ↔ fang_yuchen    前后桌  fav: 20/20  trust: 15/15
tang_shihan ↔ fang_yuchen   室友    fav: 15/15  trust: 10/10
tang_shihan ↔ cheng_yutong  室友    fav: 5/5    trust: 5/5
tang_shihan ↔ su_nianyao    室友    fav: 10/10  trust: 5/5
```

---

## Trajectory Output (`models/trajectory.py`)

Per-day trajectory data saved to `simulation/days/day_NNN/trajectory.json` for frontend visualization:

```
DayTrajectory:
  day: int
  agents: dict[str, list[AgentSlot]]   # agent_id → time slots

AgentSlot:
  time: str                             # e.g. "08:45"
  scene_name: str                       # e.g. "课间@走廊"
  location: str                         # e.g. "走廊"
  emotion: str                          # emotion at scene start
```

Collected during scene execution; each agent gets one slot per scene they participate in.

---

## Key Engineering Patterns

- **Atomic writes** (`agent/storage.py:atomic_write_json(path, data: dict | list)`): All JSON writes use temp file + `os.fsync` + `os.replace` to prevent corruption on crash.
- **Checkpoint-based recovery**: Every phase transition saves progress. On restart, the orchestrator skips completed phases/scenes/groups. Group status tracks: `pending` → `llm_done` → `applied`.
- **Pre-scene snapshot/restore**: Before interaction begins, agent files are snapshotted. If the scene is interrupted and resumed, the snapshot is restored, the scene resets to grouping, and re-runs from scratch. This prevents silent scene skips caused by lost in-memory group assignments and avoids double-applying partially-written state changes.
- **Per-day deterministic scene generation**: Scene generation uses a separate RNG seeded with `hash((base_seed, "scenes", day))`, ensuring the scene list (which LOW density scenes triggered) is identical across resume. The base seed is persisted in `progress.json` on first run; resume always reloads it. CLI `--seed` overrides the saved seed. Without this, the main RNG's consumption history would differ on resume, causing scene indices to shift.
- **Idempotent result application**: Scene-end results are saved with baseline relationship snapshots. Deltas are applied to baselines, not current values, so re-applying the same result is safe.
- **Structured LLM output**: All LLM calls use Instructor's `response_model` parameter to guarantee Pydantic model parsing. No free-form text parsing anywhere.
- **Async concurrency**: Daily plans and nightly compression run all agents concurrently, throttled by `asyncio.Semaphore(max_concurrent_llm_calls)`. Scene execution is sequential (each scene depends on the previous scene's state changes).
- **Name ↔ ID mapping**: LLM prompts use Chinese names (林昭宇). Code uses snake_case IDs (lin_zhaoyu). `name_to_id` mapping is built from profiles during result application.

---

## Frontend — SimClass Pixel World

Split-pane "AI social reality show + read-the-mind" viewer. Top half (~55vh) is the pixel-art stage (rooms, sprites, speech bubble over the speaker only). Bottom half (~45vh) is the **NarrativePanel** — a persistent reading column that surfaces `public.speech` and every agent's inner monologue side-by-side. Mind-reading is always on; there is no toggle.

**Tech stack**: Vite + React 19 + TypeScript, PixiJS 8 + @pixi/react 8 (canvas rendering), Tailwind CSS 3, Framer Motion (panel animations), Zustand 5 (state), React Router 7, D3.js (Phase 2 graphs), Vitest (narrative unit tests). Fonts: LXGW WenKai (thoughts), Noto Sans SC (body).

**Architecture**: Outer layout is a flex-column (stage area `flex-1 min-h-0` over NarrativePanel `h-[45vh]` / mobile `h-[60vh]`). PixiJS owns the stage (rooms, sprites, camera). React owns the NarrativePanel, TopBar (absolute-positioned over the stage), SidePanel (slide-out overlay), and chat modals. BubbleOverlay is an imperative DOM layer synced to the PixiJS Ticker. Camera state lives on the PixiJS Container transform, not in Zustand.

### Data Pipeline

`scripts/export_frontend_data.py` copies simulation output → `web/public/data/`. Drama scores and character positions are computed in the frontend, not the export script.

**Display-worthy filter**: a scene is included in `meta.days[]` and the per-day `scenes.json` only if at least one of its groups has real content. A multi-agent group qualifies when `ticks` is non-empty (the backend's `is_trivial_scene` marks empty/no-action scenes as `ticks: []`). A solo group qualifies when `solo_reflection.inner_thought` or `activity` is non-empty. Days with zero qualifying scenes (notably the `day_000` initialization placeholder) are skipped from `meta.days[]` entirely. Raw scene files are still copied verbatim into `days/day_NNN/` so the archive is preserved; only the dropdown index shrinks.

```
web/public/data/
  meta.json                     # days, agent map, schedule, date, exam countdown
  agents/{agent_id}.json        # profile + state + relationships + self_narrative + key_memories
  portraits/{agent_id}.png      # staged from canon/cast/portraits/ so CharacterGallery can fetch them
  days/day_001/
    scenes.json                 # scene index
    0845_课间@教室.json          # scene files with tick data
    trajectory.json             # per-agent per-scene emotions/activities
  events.json                   # event queue
```

### File Structure

```
web/src/
  main.tsx                      # Entry, BrowserRouter
  App.tsx                       # Routes: / (PixiCanvas), /relationships, /timeline
  index.css                     # Tailwind directives + custom styles (dark theme: bg #0d0d1a, text #e8e6f0)
  stores/
    useWorldStore.ts            # Zustand: day, scene, tick, group, room, focusedAgent. setCurrentSceneFile/setActiveGroupIndex auto-seek to findFirstSpeechTick. goNext/goPrev cross group + scene boundaries automatically.
    useAppStore.ts              # Legacy store (used by Phase 2 views only)
  lib/
    types.ts                    # Data interfaces + RoomId, RoomZone, RoomLayout. Emotion is 15 values (adds guilty/frustrated/touched/curious).
    data.ts                     # fetch+cache + prefetchDay() for current day (~650KB)
    constants.ts                # SEAT_LAYOUT, EMOTION_COLORS/LABELS/EMOJIS/SENTIMENT (all 15 emotions), LOCATION_ICONS
    sceneGroup.ts               # groupScenesByTimeSlot() — merges consecutive scenes sharing time+name for the TopBar dropdown
    roomConfig.ts               # Room zone definitions (7 rooms), derivePositions() for character placement
    drama.ts                    # scoreTick(), dramaThreshold(), isDramaPeak(), sortScenesByDrama()
  components/
    narrative/                  # Bottom-panel reading column (the product's core value surface)
      NarrativePanel.tsx        # Top-level assembly. Subscribes to sceneFile/activeGroup/currentTick. Renders EnvironmentalBanner + GroupPills + FocalCard + ObserverRow + TickNav. Branches: solo → SoloCard; trivial/empty → "(平静的时刻)"; null file → animate-pulse skeleton.
      EnvironmentalBanner.tsx   # Derived from ticks ≤ currentTick: most-recent non-empty environmental_event + unresolved public.exits since that event (persist until next event overrides). No internal state — switching scene/group implicitly resets.
      GroupPills.tsx            # Horizontal pills when sceneFile.groups.length > 1. Solo groups show 🧘 name. Click → setActiveGroupIndex (which auto-seeks to first speech tick).
      FocalCard.tsx             # The one tick-focused speaker / actor / observer. Three visual variants by Focal.kind: 说 / 动作 / 观察 badge. Inner thought shown under speech/non_verbal. First mount uses 400ms intro fade + translate-y; subsequent tick swaps use 200ms — keeps manual nav snappy without losing the entrance. (hasMountedRef guards this since key=tickIdx+agentId forces remount.)
      SoloCard.tsx              # Standalone card for solo groups (is_solo). activity + inner_thought + emotion emoji + top-1~2 active_concerns (lazy-fetched via loadAgent for psychological texture). TickNav hidden.
      ObserverRow.tsx           # Non-focal minds from current tick, sorted is_disruptive DESC → urgency DESC (see partitionObservers). All rows visually uniform — 12-13px, opacity 0.7, no accent bar / size diff / badge — drama surfaces via spatial top-row primacy, not visual weight. Container has max-h-full overflow-y-auto. Empty observer list → entire block does not render.
      TickNav.tsx               # Manual ←/→ buttons + tick progress bars (drama-intensity heights, click to jump within group) + scene stepper (◀场▶). The arrow buttons call store.goPrev/goNext which cross group and scene boundaries; keyboard ←/→ wired in PixiCanvas does the same. No play/pause, no speed selector — viewer paces themselves.
      focal.ts                  # Pure helpers: pickFocal(tick, group), partitionObservers(tick, focalAgentId), findFirstSpeechTick(group). Focal priority: speech > is_disruptive > highest-urgency non_verbal > highest-urgency observation > first participant fallback.
      focal.test.ts             # Vitest coverage for pickFocal, partitionObservers sort/stability, findFirstSpeechTick fallback (11 cases).
    world/                      # PixiJS rendering
      PixiCanvas.tsx            # Outer flex-col: stage (flex-1 min-h-0) + NarrativePanel. PixiJS Application resizeTo the stage div. Data loading uses a shared generation token (useRef) across loadScenes+loadSceneFile so rapid Day1→Day2→Day1 clicks drop stale responses. UI_INSET top=48 for TopBar. Non-solo: only the speaker gets a bubble. Solo: only the solo agent gets one emoji bubble. Emotion signal for everyone else lives in ObserverRow.
      Room.tsx                  # Programmatic tilemap for each of 7 rooms. Draw functions: drawClassroom, drawHallway, drawCafeteria, drawDorm, drawPlayground, drawLibrary, drawConvenienceStore.
      CharacterSprite.ts        # Colored circle + head + name label. Per-agent colors. Expanded hitArea rectangle so clicks stay reliable at the smaller ~55vh stage. updateSpriteState() for talking/dimming.
      Camera.ts                 # Free-scroll (drag + wheel zoom) + auto-pan (lerp). State on PixiJS Container transform, updated via Ticker.
      BubbleOverlay.ts          # Imperative DOM overlay. 3 bubble types: speech (cream bg — only speakers get this), emoji (solo-only single indicator), action (small italic for non_verbal, currently unused by PixiCanvas but kept as a reusable type). Viewport-clamped positioning via sprite.toGlobal() each frame with overlap push-apart. Click forwarding via onBubbleClick → setFocusedAgent. Fade-in via opacity transition. Recreates DOM element on type change.
      ErrorBoundary.tsx         # Minimal React Error Boundary. Catches render errors, logs to console, renders nothing on crash (prevents blank page).
    ui/                         # React overlays
      TopBar.tsx                # Day dropdown (Day NNN ▾) + scene dropdown (click-away-close menu that reuses groupScenesByTimeSlot for hierarchical time-slot grouping) + 角色扮演 button. On mount pings /api/health with 1.5s timeout; if API is offline the 角色扮演 button is disabled with a tooltip pointing at `uv run api`. No mind-reading toggle, no mode switch, no playback controls.
      RolePlaySetup.tsx         # Modal for picking your character + targets. Rendered via createPortal to document.body so it escapes TopBar's pointer-events-none container — without the portal, child clicks would silently fail in most browsers.
      SidePanel.tsx             # Slide-out character detail: emotion, personality, academics, concerns, relationships, recent thoughts. Framer Motion animated.
    layout/                     # Legacy (Phase 2 analytical views)
      Header.tsx                # Nav bar for /relationships, /timeline
      PageShell.tsx             # Wrapper for legacy views
    relationships/
      ForceGraph.tsx            # D3 force graph (Phase 2)
      RelationshipCard.tsx      # Relationship detail
    timeline/
      EmotionTimeline.tsx       # SVG emotion waveform (Phase 2)
```

### Room System

7 rooms, each with a programmatic tilemap and named zones for character positioning:

| Room | Dimensions | Zones | Visual features |
|------|-----------|-------|-----------------|
| 教室 | 24×18 | 20 seat zones + teacher | Blackboard, 5×4 desks, windows |
| 走廊 | 28×10 | left, center, right | Lockers, notice board, windows |
| 食堂 | 28×20 | 6 table zones | Food counter, 6 dining tables |
| 宿舍 | 24×16 | 3 beds + desk area | Bunk beds, shared desk, window |
| 操场 | 30×20 | court, 2 benches, track | Basketball court, running track |
| 图书馆 | 24×18 | 4 tables + shelves | Bookshelves (colored spines), reading tables |
| 小卖部 | 16×14 | counter, 2 aisles | Counter with register, product shelves |

Classroom uses seat-based positioning from agent metadata. Other rooms spread participants in circular patterns within assigned zones.

### Navigation Model

Manual only — there is no auto-playback. The viewer paces themselves like reading a novel.

- **store.goNext / goPrev**: tick-level step that crosses group and scene boundaries. At the last tick of a group, advances to the next group's `findFirstSpeechTick`; at the last tick of the last group, advances to the next scene; symmetric for backward.
- **TickNav** (bottom of NarrativePanel): ←/→ buttons (call goPrev/goNext), drama-intensity bars (click to jump within current group), scene stepper ◀场▶ (jumps whole scenes ignoring tick context).
- **Keyboard**: ←/→ wired in `PixiCanvas` calls goPrev/goNext (skipped while focus is in INPUT/TEXTAREA so RolePlay chat input still works).
- **Drama score** per tick (`drama.ts:scoreTick`): `speak×1 + disruptive×5 + max_urgency×0.5 + exit×2` — used to size/color the TickNav bars so viewers can spot peaks at a glance.

### Focal Selection

`pickFocal(tick, group)` chooses the FocalCard subject, priority order:

1. `public.speech` present → **speaker** (speaker fixed; speech has authoritative clarity)
2. Any `is_disruptive` mind → **non_verbal** (dramatic interruption)
3. Highest-urgency `action_type === 'non_verbal'` with `action_content` → **non_verbal**
4. Highest-urgency observation → **observation**
5. Fallback → `group.participants[0]`

`partitionObservers(tick, focalAgentId)` returns all remaining minds sorted `is_disruptive DESC → urgency DESC`. Gated agents are already filtered by the backend serializer (never in `tick.minds`), so no second filter needed. The ObserverRow renders every remaining mind — no top-N cap, no visual weighting. Reading order does the job of "most dramatic first."

### Key Interactions

- **Narrative panel** is always-on. Top of page shows the pixel stage (where everyone stands, who is talking), bottom shows the reading column (speech + all minds).
- **Click character**: SidePanel slides open with full profile. Other characters dim to 40%.
- **Click character name in NarrativePanel**: same as clicking the sprite — opens SidePanel.
- **TickNav**: visual drama intensity bars. Click to jump within group; ←/→ buttons (or keyboard) to step across groups and scenes.
- **Scene dropdown** (TopBar): consecutive same-time scenes collapse into a single "08:45 课间" header with location sub-items.
- **Day dropdown** (TopBar): a single "Day NNN ▾" button instead of a row of buttons — scales to ~1000 days over three school years.
- **Camera**: drag to pan, scroll to zoom.
- **Keyboard**: ←/→ = navigate (cross-scene aware). Disabled when focus is in INPUT/TEXTAREA.

### Running

```bash
uv run python scripts/export_frontend_data.py   # Generate frontend data
cd web && pnpm dev                               # Dev server
cd web && pnpm build                             # Production build → web/dist/
uv run api                                       # Start API server (port 8000)
```

---

## Interactive Chat API (`api/`)

FastAPI server providing two interactive chat modes. Both are **read-only** (don't affect simulation state) and **time-aware** (context matches the selected point in the timeline).

**Module structure:**
- `api/server.py` — FastAPI app with CORS, endpoints, SSE streaming
- `api/models.py` — Pydantic request/response models (`ChatRequest`, `RolePlayRequest`, `AgentReaction`, `AgentReactionLLM`)
- `api/context.py` — Time-travel context assembly (`build_context_at_timepoint()`)

**Dependencies:** `fastapi`, `uvicorn`, `sse-starlette` (added to `pyproject.toml`)

### Time-Travel Context Assembly

`build_context_at_timepoint(agent_id, day, time_period, world)` reconstructs full agent context at a specific (day, time_period):

1. **Baseline state**: Load from `simulation/days/day_{N-1}/agent_snapshots/` (previous day's end-of-day = this day's start). For Day 1, uses `day_000` (initial state).
2. **Key memories**: Filter `key_memories.json` to `day <= N`, sorted by importance.
3. **Recent summary**: Last 3 days from `recent.md`, filtered to `day <= N` via `max_day` parameter to prevent time-travel (viewing Day 1 won't leak Day 5 content).
4. **"Today so far"**: Reconstruct from scene files — loads `scenes.json`, filters scenes before the given time period, extracts `narrative.key_moments` and `reflections[agent_id].emotion` from scene JSONs.
5. **Emotion**: Scene emotion > baseline state emotion.
6. **Qualitative labels**: Reuses `energy_label()`, `pressure_label()`, `intensity_label()`, `relationship_label()` from `agent/qualitative.py`.

Returns a dict with all template variables needed for `god_mode.j2` or `role_play.j2`.

### God Mode

User clicks an agent and chats with their inner self. The agent responds with full honesty (no social mask).

- **Endpoint**: `POST /api/god-mode/chat` → `EventSourceResponse` (SSE)
- **Template**: `templates/god_mode.j2` (includes `chat_base.j2`)
- **Streaming**: Raw `litellm.acompletion(stream=True)` via `streaming_text_call()` — character-by-character
- **SSE events**: `{"token": "..."}` per chunk, `{"done": true}` at end
- **Prompt**: Agent identity + state + relationships + memories, ending with "respond as if writing in your diary — completely honest, no social mask"
- **Error handling**: Catches `ContextWindowExceededError` specifically and returns a user-friendly message ("对话太长了，请关闭后重新开始对话") instead of a raw error.

### Role Play

User becomes an agent, picks 1-4 other agents, and has a freeform group chat. All agents respond in character with social dynamics.

- **Endpoint**: `POST /api/role-play/chat` → `EventSourceResponse` (SSE)
- **Template**: `templates/role_play.j2` — system prompt contains stable agent context only (identity, relationships, state). Conversation history and latest message are sent as a separate user message for prefix caching.
- **Streaming**: Not token-level. Each agent gets a parallel `structured_call()` → `AgentReactionLLM` model (excludes `agent_id`/`agent_name` — these are filled from profile data). Results stream as SSE events as they complete.
- **Relationship filtering**: Each agent's context is filtered to only include relationships with scene participants (user agent + target agents), matching the template header "你和在场人物的关系".
- **SSE events**: `{"thinking": true, "agent_ids": [...]}` first, then `{"agent_id": "...", "content": "...", ...}` per agent reaction, `{"done": true}` at end
- **Actions**: Typed as `Literal["speak", "action", "silence"]` — Instructor enforces valid values and retries on hallucinated action types. Silent agents are filtered out.
- **Error handling**: Same `ContextWindowExceededError` handling as God Mode.

### Chat Templates

- `chat_base.j2` — Shared base for both modes. Same school setting as `system_base.j2` but without simulation-specific instructions (no tick system, no speaker selection rules, no structured output format).
- `god_mode.j2` — Full agent context (profile, relationships, memories, concerns, tensions, conflicts) + inner monologue instructions.
- `role_play.j2` — Stable agent context + social mask instructions. Conversation history and latest message are excluded from the template (sent as a separate user message by `server.py`) so the system prompt stays constant across turns for prefix caching.

### LLM Streaming

`llm/client.py` now has two functions:
- `structured_call()` — Existing function for structured output via Instructor. Role Play uses it with `AgentReactionLLM` as `response_model`.
- `streaming_text_call()` — New function for raw text streaming via `litellm.acompletion(stream=True)`. Used by God Mode. Returns `AsyncGenerator[str, None]`.

Both functions use `if value is not None else default` for `temperature` and `max_tokens` parameters to correctly handle explicit `0` / `0.0` values.

### Prefix Caching Strategy

Multi-turn chat benefits from LLM prefix caching when the message prefix stays identical across requests:

- **God Mode**: System prompt (agent context) is fully stable across turns. Chat history is sent as separate `user`/`assistant` messages that only append — each request is a prefix extension of the previous one. Optimal by default.
- **Role Play**: System prompt contains only stable agent context (identity, personality, state, relationships). Conversation history and latest message are sent as a separate `user` message, so the system prompt is identical across all turns within a session. Previously, history was embedded in the system prompt via the template, breaking caching on every turn.

---

## Visual Foundation

### Character Sprites (`spriteConfig.ts`, `CharacterSprite.ts`)

Characters are rendered as animated sprites from the LimeZu Modern Interiors premade character sheets (16×32 frame grid, 2× scale = 32px rendered). Each agent maps to a specific premade character PNG via `AGENT_SPRITE_MAP`.

**Frame map**: `ANIMATIONS` defines grid positions for `idle_down`, `idle_right`, `idle_up`, `idle_left` (4 frames each at different grid rows). The `AnimatedSprite` from PixiJS plays the idle animation at 4 FPS.

**Fallback**: Agents without sprite sheets render as the original colored circles with head + name label.

### Tileset Rendering (`tilesetConfig.ts`, `TilesetRenderer.ts`, `Room.tsx`)

Room floors use tileset textures via `TilingSprite` for repeating fills. Each room type maps to a floor tile reference in `ROOM_FLOOR`. Furniture and walls are still rendered procedurally via PixiJS `Graphics` (hybrid approach — tileset floors + procedural furniture details).

**Tilesets used**: `room_builder_16x16.png` (floors/walls), `classroom_library.png`, `bedroom.png`, `kitchen.png`, `grocery_store.png`, `gym_sport.png`, `exteriors_16x16.png`.

### Stage Bubbles (`BubbleOverlay.ts`)

On the stage, only the speaker gets a cream speech bubble (non-speakers have nothing over their head — their emotion signal lives in ObserverRow). Solo groups are the one exception: the solo agent gets a single emoji bubble tied to their `solo_reflection.emotion`. This keeps the stage visually quiet so 11 characters in one room don't become an emoji soup at 55vh.

### Asset Pipeline

Purchased pixel art assets are copied from `assets/` (gitignored) into `web/public/assets/` (also gitignored — not committed). Directory structure:
```
web/public/assets/
  tilesets/       ← Room tile textures (16×16 tiles)
  sprites/        ← Character sprite sheets (premade_NN.png)
  emotes/         ← Emote balloon spritesheets (32×32)
  ui/paper_theme/ ← UI panel assets
```

---

## Frontend Chat UI

### God Mode Chat (`GodModeChat.tsx`)

Slide-in panel from right (same position as SidePanel, using Framer Motion). Entry: click "内心" button in SidePanel header. Shows agent sprite portrait, streaming text with diary-style font (`LXGW WenKai`), user messages right-aligned, agent responses left-aligned with italic handwritten style.

### Role Play Chat (`RolePlaySetup.tsx`, `RolePlayChat.tsx`)

- **Setup**: Modal with agent portrait grid. Step 1: pick your character. Step 2: pick 1-4 conversation partners. Modal is rendered via `createPortal(..., document.body)` so it escapes TopBar's `pointer-events-none` ancestor — without the portal, child clicks (✕, agent portraits, 开始对话) silently fail in most browsers.
- **Chat view**: Full-screen replacement of the PixiCanvas. Participant portraits in header, messages from all participants with sprite avatars, "正在思考..." indicator while agents process.
- **Entry**: "角色扮演" button in TopBar. The TopBar pings `/api/health` on mount (1.5s timeout); when the API is unreachable the button is disabled with a tooltip pointing at `uv run api`, so users get clear feedback instead of an inert modal.

### Store Extensions (`useWorldStore.ts`)

Chat state added to Zustand store:
- `chatMode`: `'off' | 'god' | 'roleplay'`
- `chatMessages`, `chatStreaming`, `chatStreamBuffer` — message history + streaming state
- `rolePlayUserAgent`, `rolePlayTargetAgents`, `rolePlayReactions` — role play session state
- Actions: `openGodModeChat()`, `openRolePlayChat()`, `closeChat()`, `appendStreamToken()`, `flushStreamBuffer()`, `appendAgentReaction()`

### SSE Client (`chat.ts`)

Frontend SSE streaming client using `fetch()` + `ReadableStream` reader. Two async generators:
- `streamGodModeChat()` — yields text tokens
- `streamRolePlayChat()` — yields `AgentReaction` objects or `{thinking: true}` events

### Vite Proxy

`vite.config.ts` proxies `/api` requests to `http://localhost:8000` for development.

## Share-Card Generation (`src/sim/cards/`)

Phase 0–3 of the 小红书传播 initiative: server-side rendered PNGs that users save + post to 小红书 / Twitter / Reddit. All rendering is Pillow on the FastAPI server — the frontend never does HTML→PNG conversion. Card bytes are cached on disk at `.cache/cards/` (gitignored); cache invalidation is manual (`rm -rf .cache/cards/` after a sim rerun).

### Rendering Foundation

- `base.py` — Canvas constants (`CANVAS_W=1080`, `CANVAS_H=1440` — 3:4 for 小红书), palette (`PAPER_CREAM`, `INK_BLACK`, `INK_GRAY`, `CINNABAR_RED`), font loaders (`font_wen`/`font_serif`/`font_sans` via `lru_cache`), `paper_background()` (procedural cream with ruled lines + red margin).
- `assets.py` — Paths (`FONTS_DIR`, `PORTRAITS_DIR`, `SPRITE_SHEETS_DIR`, `CACHE_DIR`, `VISUAL_BIBLE_PATH`), `load_visual_bible()` (cached JSON load), `get_agent_visual(agent_id)`, `portrait_path(agent_id)`.
- `cache.py` — `get_or_render(key, render_fn)` returns cached PNG path, rendering + writing if missing. `clear()` wipes the dir.
- `captions.py` — Pure caption/filename/hashtag builders. Three entry points: `scene_caption()`, `daily_caption()`, `agent_caption()`. Each returns `{caption, hashtags, filename}`. CJK filenames are sanitized of filesystem-unsafe characters.
- `elements/` — Compositional primitives: `portrait.py` (loads pre-generated pixel-art portraits with NEAREST resampling), `seal.py` (cinnabar rounded-square with reversed-out text — brand mark 「班」 and date stamps), `balloon.py` (CJK-wrapped speech + thought bubbles), `banner.py` (dashed dividers), `paper.py` (re-exports `paper_background`).

### Data Model (`canon/cast/visual_bible.json`)

Per-agent visual config: `name_cn`, `sprite_source` (LimeZu premade sheet), `crop` (x/y/w/h for the portrait frame), `main_color` (seeded from `CharacterSprite.ts::AGENT_COLORS` — do not change without syncing), `accent_color`, `motif_emoji`, `motif_tag`, `archetype_keywords`, and `is_teacher` flag for teacher-specific rendering paths. `scripts/generate_portraits.py` reads this and writes `canon/cast/portraits/{agent_id}.png` — rerun after any `sprite_source` or `crop` change.

### Scene Card (`scene_card.py`, Phase 1)

Most dramatic multi-agent group in a scene, rendered 1080×1440.

Three-layer design for testability:
1. **Selection** (`select_featured_group(scene_data)`) — pure. Ranks multi-agent groups by `sum(tick.urgency) + sum(len(inner_thought))`. Returns `None` if every group is solo (scene card skipped; API returns 404). Solo reflections belong on the agent card.
2. **LayoutSpec** (`scene_to_layout_spec(scene_data, group_index)`) — frozen `@dataclass`. Ordered portraits (speaker, target, top witness, capped at 3), bubbles (speech + key thoughts), `featured_quote` for caption.
3. **Render** (`_render_card(spec)`) — Pillow only. Header with 「第N天」 seal + title, portraits row with name + motif, speech/thought bubbles (`br`/`bl` tails alternate), 「班」 brand footer.

Scene loading: `load_scene_by_array_index(day, scene_idx)` — `scene_idx` is the **array position in `scenes.json`**, not the semantic `scene_index` field (which becomes non-sequential after the export filter drops trivial scenes; the frontend already navigates by array position).

**Tests** — Three files, all pure:
- `tests/test_cards_logic.py` — selection heuristics, caption format, hashtag rules.
- `tests/test_cards_layout.py` — scene_data → LayoutSpec projection.
- `tests/test_cards_render.py` — smoke tests (render doesn't raise, output is valid PNG at correct dimensions). No pixel-level golden image diff: Pillow output is not byte-deterministic across libfreetype + font-hinting versions.

### Daily Card + Report (`daily_card.py`, `aggregations.py`, Phase 2)

The daily PNG summarizes a whole day. The same aggregation also drives the landing-page `DailyReport.tsx` — the frontend consumes `/api/card/daily/{day}.json` and renders the structured sections in HTML (faster + linkable), with a "save PNG" button for the shareable version.

**Aggregations** (`aggregations.py`): pure functions over `load_day_scenes(day)` (reads every `web/public/data/days/day_NNN/*.json`).
- `pick_headline(scenes)` — highest-rank beat by `rich_thought_flag (len ≥ 15) + urgency × 4 + thought_len`.
- `pick_secondaries(scenes, exclude, limit=3)` — next 3 beats, one per scene, excluding the headline's scene file.
- `compute_mood_map(scenes)` — per-agent `Counter` of emotions across ticks; returns dominant emotion in visual-bible order.
- `pick_cp(scenes)` — sums `(fav + trust + understanding)` deltas across both directions of each pair; returns the strongest positive pair. Resolves `to_agent` display-name back to `agent_id` via `_build_name_to_id` (participant_names map + visual bible fallback).
- `pick_golden_quote(scenes, exclude_text=None)` — most tweetable inner thought by `urgency × 5 + len`; accepts `exclude_text` so it doesn't duplicate the headline.
- `scene_thumbs(scenes)` — lightweight thumbnail list for the landing-page scene strip.
- `build_daily_summary(day)` — assembles `DailySummary` dataclass (frozen) from all of the above.
- `summary_to_dict(summary)` — JSON-friendly shape for the API; enriches `mood_map` entries with `main_color` + `motif_emoji` from the visual bible.

**Daily card render** (`daily_card._render_card`) places: 「第N天 · 班级日报」 header, headline (meta + speech + thought bubbles), golden quote (balloon), mood chip strip (one dot per agent tinted by `main_color`), CP block (two portraits + ♥ + delta labels), brand footer.

**Tests** — `tests/test_cards_daily.py` covers selection dedup, CP summing across both directions, mood dominance, `summary_to_dict` JSON-safety.

### Agent Archive Card (`agent_card.py`, Phase 3)

Cumulative growth: Day N card reflects state at end of Day N. Reuses `sim.api.context.build_context_at_timepoint(agent_id, day, "22:00", world)` — same snapshot-loading + today-so-far reconstruction as the chat/role-play endpoints. The fixed `"22:00"` time period corresponds to end-of-day state.

- `EMOTION_LABELS_CN` — local mapping from the `Emotion` enum's raw English values to Chinese display labels. Kept in sync with `web/src/lib/constants.ts::EMOTION_LABELS`.
- `_featured_quote_for(agent_id, day)` — scans the day's scenes for the agent's strongest `(urgency × 5 + len)` inner thought (fallback to `solo_reflection.inner_thought` for solo groups).
- `context_to_agent_spec()` — pure: chat-context dict → `AgentLayoutSpec` (portrait, name, state pills, featured quote, top-3 relationships by favorability, top-2 memories by importance, strongest active concern). Teacher cards skip the relationships block (teacher `is_teacher=True` in the visual bible).
- `_render_card(spec)` — header strip tinted by `main_color`, big portrait, 3-pill state row (情绪 · 精力 · 压力), featured quote balloon, relationships list. Footer identical to other cards.
- `spec_to_dict(spec)` — JSON serializer for the API.

### API Endpoints (`src/sim/api/server.py`)

All card routes share `_get_world()` — the same `WorldStorage` singleton used by role-play chat. Creating a fresh instance per request would re-load all agents + snapshots (seconds-scale latency).

- `GET /api/card/scene/{day}/{scene_idx}.png` — scene card PNG; `scene_idx` is the array position in `scenes.json`. Returns 404 when every group in the scene is solo. `Content-Disposition` uses **RFC 5987** `filename*=UTF-8''...` via `urllib.parse.quote` so CJK filenames survive Safari and older Chrome.
- `GET /api/card/scene/{day}/{scene_idx}.json` — caption payload + `group_index` for the featured group.
- `GET /api/card/daily/{day}.(png|json)` — daily card + structured summary. The JSON includes `caption_payload` (caption + hashtags + filename) so the frontend copy-button reuses it.
- `GET /api/card/agent/{agent_id}/{day}.(png|json)` — agent archive card.

All PNG responses set `Cache-Control: public, max-age=86400`. The server-side disk cache (`cache.py`) makes repeat renders a file-read.

### Frontend Share UI

- `web/src/components/narrative/ShareButtons.tsx` — Generic share UI (📥 保存图 + 📋 复制文案). Takes `cardEndpoint` prop (e.g., `/api/card/scene/1/0`); appends `.png`/`.json`. Probes `/api/health` + the endpoint on mount; grays out with appropriate tooltips when unavailable (four states: `unknown` / `online` / `not_available` / `offline`). Save path is progressively enhanced — tries Web Share API with `File` first (mobile native share sheet), falls back to blob download (`<a download={filename}>`).
- Integrated into `GroupGrid.tsx` (scene cards), `DailyReport.tsx` (daily cards), `CharacterArchive.tsx` (agent cards).
- `web/src/components/daily/DailyReport.tsx` — Landing page at `/day/:dayId`. `/` routes to `DailyReportHome`, which fetches `meta.days` and redirects to the latest day. Renders headline (with "进入现场 →" link to PixiCanvas scene), golden quote block, secondaries (clickable scene links), mood map grid, CP tracker, scene thumbnail strip, gallery link. Gracefully handles offline API with a fallback link into PixiCanvas.
- `web/src/components/gallery/CharacterGallery.tsx` + `CharacterArchive.tsx` — `/characters` (and `/characters/day/:dayId`) show a 2×5 grid of portraits. Teacher card gets a visually distinct tile. Drill-in at `/characters/:agentId?day=day_NNN` renders the full archive, reuses the share buttons, and offers a "与 TA 聊聊 →" shortcut into the role-play chat via `openRolePlayChat`.

### Routing Changes (`web/src/App.tsx`)

- `/` → `DailyReportHome` (redirects to `/day/:latest`).
- `/day/:dayId` → `DailyReport` (landing).
- `/day/:dayId/scene/:sceneFile` → `PixiCanvas` (scene deep-dive; linked from DailyReport).
- `/characters`, `/characters/day/:dayId` → `CharacterGallery`.
- `/characters/:agentId` → `CharacterArchivePage` (reads `?day=` query param).
- Legacy `/relationships`, `/timeline` preserved.
