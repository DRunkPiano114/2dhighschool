import time

from loguru import logger

from ..config import settings
from ..llm.client import structured_call
from ..llm.logger import log_llm_call
from ..llm.prompts import render
from ..models.agent import AgentProfile
from ..models.dialogue import SceneEndAnalysis
from ..models.scene import Scene


async def run_scene_end_analysis(
    turn_records: list[dict],
    group_agent_ids: list[str],
    profiles: dict[str, AgentProfile],
    scene: Scene,
    day: int,
    group_id: int,
) -> SceneEndAnalysis:
    # Build full conversation log
    lines: list[str] = []
    for rec in turn_records:
        name = rec["speaker_name"]
        out = rec["output"]
        line = f"【{name}】"
        if out.get("directed_to"):
            line += f"（对{out['directed_to']}）"
        line += f"：{out['speech']}"
        if out.get("action"):
            line += f"  [{out['action']}]"
        lines.append(line)

    full_log = "\n".join(lines)
    long_conversation = len(turn_records) > 20

    group_members = [
        {"name": profiles[aid].name, "personality": profiles[aid].personality}
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
    result = await structured_call(
        SceneEndAnalysis,
        messages,
        temperature=settings.analytical_temperature,
        max_tokens=settings.max_tokens_scene_end,
    )
    latency = (time.time() - start) * 1000

    log_llm_call(
        day=day,
        scene_name=scene.name,
        group_id=group_id,
        call_type="scene_end",
        input_messages=messages,
        output=result,
        latency_ms=latency,
        temperature=settings.analytical_temperature,
    )

    logger.info(
        f"  Scene-end analysis: {len(result.key_moments)} moments, "
        f"{len(result.relationship_changes)} rel changes, "
        f"{len(result.memories)} memories"
    )

    return result
