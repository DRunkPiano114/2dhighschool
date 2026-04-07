"""Regression test: perception uses system + user two-message format for prefix caching."""

import asyncio
from unittest.mock import patch, MagicMock

from sim.models.agent import (
    AgentProfile, AgentState, Academics, Emotion,
    FamilyBackground, Gender, OverallRank, PressureLevel, Role,
)
from sim.models.dialogue import ActionType, PerceptionOutput
from sim.models.scene import Scene, SceneDensity
from sim.agent.storage import AgentStorage
from sim.interaction.turn import run_perception


def _make_profile() -> AgentProfile:
    return AgentProfile(
        agent_id="test_a", name="测试同学", gender=Gender.MALE, role=Role.STUDENT,
        academics=Academics(overall_rank=OverallRank.MIDDLE),
        family_background=FamilyBackground(pressure_level=PressureLevel.MEDIUM),
    )


def _make_scene() -> Scene:
    return Scene(
        scene_index=0, day=1, time="08:00", name="早读",
        location="教室", density=SceneDensity.HIGH,
        agent_ids=["test_a", "test_b"],
        opening_event="上课了",
    )


def _make_state() -> AgentState:
    return AgentState()


_FAKE_PERCEPTION = PerceptionOutput(
    observation="看了一下", inner_thought="没啥",
    emotion=Emotion.NEUTRAL, action_type=ActionType.OBSERVE,
    action_content=None, action_target=None,
    urgency=3, is_disruptive=False,
)


def test_perception_sends_system_and_user_messages():
    """run_perception must send messages as [system, user] for DeepSeek prefix caching."""
    profile = _make_profile()
    scene = _make_scene()
    state = _make_state()
    storage = MagicMock(spec=AgentStorage)
    storage.load_relationships.return_value = MagicMock(relationships={})
    storage.read_today_md.return_value = ""
    storage.read_recent_md_last_n_days.return_value = ""
    storage.load_key_memories.return_value = MagicMock(memories=[])
    narr = MagicMock()
    narr.narrative = ""
    narr.self_concept = []
    narr.current_tensions = []
    storage.load_self_narrative_structured.return_value = narr

    captured_messages = []

    fake_result = MagicMock()
    fake_result.data = _FAKE_PERCEPTION
    fake_result.tokens_prompt = 0
    fake_result.tokens_completion = 0
    fake_result.cost_usd = 0.0

    async def capture_call(response_model, messages, **kwargs):
        captured_messages.extend(messages)
        return fake_result

    with patch("sim.interaction.turn.structured_call", side_effect=capture_call):
        with patch("sim.interaction.turn.log_llm_call"):
            asyncio.run(run_perception(
                storage, profile, state, scene,
                {profile.agent_id: profile},
                known_events=[], next_exam_in_days=20,
                latest_event="上课了", scene_transcript="",
                private_history=[], tick_emotion=Emotion.NEUTRAL,
                day=1,
            ))

    assert len(captured_messages) == 2
    assert captured_messages[0]["role"] == "system"
    assert captured_messages[1]["role"] == "user"
    assert len(captured_messages[0]["content"]) > 0
    assert len(captured_messages[1]["content"]) > 0
