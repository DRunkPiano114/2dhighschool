import time

from loguru import logger

from ..agent.context import prepare_context
from ..agent.storage import AgentStorage
from ..config import settings
from ..llm.client import structured_call
from ..llm.logger import log_llm_call
from ..llm.prompts import render
from ..models.agent import AgentProfile, AgentState
from ..models.dialogue import SoloReflection
from ..models.event import Event
from ..models.scene import Scene


async def run_solo_reflection(
    agent_id: str,
    storage: AgentStorage,
    profile: AgentProfile,
    state: AgentState,
    scene: Scene,
    all_profiles: dict[str, AgentProfile],
    known_events: list[Event],
    next_exam_in_days: int,
    day: int,
) -> SoloReflection:
    ctx = prepare_context(
        storage, profile, state, scene, all_profiles,
        known_events, next_exam_in_days,
    )

    prompt = render("solo_reflection.j2", **ctx)
    messages = [{"role": "user", "content": prompt}]

    start = time.time()
    result = await structured_call(
        SoloReflection,
        messages,
        temperature=settings.creative_temperature,
        max_tokens=settings.max_tokens_solo,
    )
    latency = (time.time() - start) * 1000

    log_llm_call(
        day=day,
        scene_name=scene.name,
        group_id=f"solo_{agent_id}",
        call_type="solo_reflection",
        input_messages=messages,
        output=result,
        latency_ms=latency,
        temperature=settings.creative_temperature,
    )

    logger.info(f"  Solo {profile.name}: {result.activity} ({result.emotion.value})")

    return result
