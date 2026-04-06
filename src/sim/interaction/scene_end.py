import time

from loguru import logger

from ..config import settings
from ..llm.client import structured_call
from ..llm.logger import log_llm_call
from ..llm.prompts import render
from ..models.agent import AgentProfile
from ..models.dialogue import NarrativeExtraction
from ..models.scene import Scene
from .narrative import format_public_transcript


async def run_scene_end_analysis(
    tick_records: list[dict],
    group_agent_ids: list[str],
    profiles: dict[str, AgentProfile],
    scene: Scene,
    day: int,
    group_id: int,
) -> NarrativeExtraction:
    full_log = format_public_transcript(tick_records, profiles)
    long_conversation = len(tick_records) > 12

    group_members = [
        {"name": profiles[aid].name}
        for aid in group_agent_ids
        if aid in profiles
    ]

    scene_info = {
        "time": scene.time,
        "location": scene.location,
        "name": scene.name,
    }

    prompt = render(
        "scene_end_analysis.j2",
        full_conversation_log=full_log,
        group_members=group_members,
        scene_info=scene_info,
        long_conversation=long_conversation,
    )

    messages = [{"role": "user", "content": prompt}]

    start = time.time()
    llm_result = await structured_call(
        NarrativeExtraction,
        messages,
        temperature=settings.analytical_temperature,
        max_tokens=settings.max_tokens_narrative,
    )
    latency = (time.time() - start) * 1000
    result = llm_result.data

    log_llm_call(
        day=day,
        scene_name=scene.name,
        group_id=group_id,
        call_type="narrative_extraction",
        input_messages=messages,
        output=result,
        tokens_prompt=llm_result.tokens_prompt,
        tokens_completion=llm_result.tokens_completion,
        cost_usd=llm_result.cost_usd,
        latency_ms=latency,
        temperature=settings.analytical_temperature,
    )

    logger.info(
        f"  Narrative extraction: {len(result.key_moments)} moments, "
        f"{len(result.new_events)} new events"
    )

    return result
