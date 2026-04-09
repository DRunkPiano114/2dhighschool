"""FastAPI server for God Mode and Role Play chat."""

import asyncio
import json

from litellm.exceptions import ContextWindowExceededError  # pyright: ignore[reportPrivateImportUsage]
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from ..agent.storage import WorldStorage
from ..llm.client import streaming_text_call, structured_call
from ..llm.prompts import render
from .context import build_context_at_timepoint
from .models import AgentReaction, AgentReactionLLM, ChatRequest, RolePlayRequest

_TOKEN_LIMIT_MSG = "对话太长了，请关闭后重新开始对话"

app = FastAPI(title="SimClass API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared world storage instance (loaded once)
_world: WorldStorage | None = None


def _get_world() -> WorldStorage:
    global _world
    if _world is None:
        _world = WorldStorage()
        _world.load_all_agents()
    return _world


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/agents")
async def list_agents():
    world = _get_world()
    agents = {}
    for aid, storage in world.agents.items():
        profile = storage.load_profile()
        agents[aid] = {"name": profile.name, "role": profile.role.value}
    return {"agents": agents}


@app.post("/api/god-mode/chat")
async def god_mode_chat(req: ChatRequest):
    world = _get_world()
    ctx = build_context_at_timepoint(req.agent_id, req.day, req.time_period, world)

    system_prompt = render("god_mode.j2", **ctx)

    messages = [{"role": "system", "content": system_prompt}]
    for msg in req.history:
        role = "user" if msg.role == "user" else "assistant"
        messages.append({"role": role, "content": msg.content})
    messages.append({"role": "user", "content": req.message})

    async def event_generator():
        try:
            async for token in streaming_text_call(messages):
                yield {"data": json.dumps({"token": token}, ensure_ascii=False)}
        except ContextWindowExceededError:
            yield {"data": json.dumps({"error": _TOKEN_LIMIT_MSG}, ensure_ascii=False)}
        except Exception as e:
            yield {"data": json.dumps({"error": str(e)}, ensure_ascii=False)}
        yield {"data": json.dumps({"done": True})}

    return EventSourceResponse(event_generator())


@app.post("/api/role-play/chat")
async def role_play_chat(req: RolePlayRequest):
    world = _get_world()

    # Build context for user's character (to know their name)
    user_storage = world.get_agent(req.user_agent_id)
    user_profile = user_storage.load_profile()
    user_name = user_profile.name

    # Build context for each target agent
    target_contexts = {}
    for aid in req.target_agent_ids:
        target_contexts[aid] = build_context_at_timepoint(aid, req.day, req.time_period, world)

    async def event_generator():
        # Signal thinking state
        yield {"data": json.dumps({
            "thinking": True,
            "agent_ids": req.target_agent_ids,
        }, ensure_ascii=False)}

        # Build conversation history for templates
        conv_history = [
            {"agent_name": msg.agent_name or msg.role, "content": msg.content}
            for msg in req.history
        ]

        # Build user message (variable per turn — separate for prefix caching)
        user_parts = []
        if conv_history:
            user_parts.append("## 对话记录")
            for msg in conv_history:
                user_parts.append(f"{msg['agent_name']}：{msg['content']}")
            user_parts.append("")
        user_parts.append("## 刚刚发生的")
        user_parts.append(f"{user_name}说：{req.message}")
        user_content = "\n".join(user_parts)

        # Run all agents in parallel
        async def get_reaction(aid: str) -> AgentReaction | None:
            ctx = target_contexts[aid]
            profile = ctx["_profile"]

            # Filter relationships to scene participants only
            participant_ids = {req.user_agent_id, *req.target_agent_ids}
            scene_rels = [r for r in ctx["relationships"] if r["target_id"] in participant_ids]

            system_prompt = render("role_play.j2", **{
                **ctx,
                "relationships": scene_rels,
            })

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]

            result = await structured_call(
                response_model=AgentReactionLLM,
                messages=messages,
                temperature=0.9,
                max_tokens=1024,
            )
            llm_output: AgentReactionLLM = result.data
            return AgentReaction(
                agent_id=aid,
                agent_name=profile.name,
                **llm_output.model_dump(),
            )

        tasks = [asyncio.create_task(get_reaction(aid)) for aid in req.target_agent_ids]

        for coro in asyncio.as_completed(tasks):
            try:
                reaction = await coro
                if reaction and reaction.action != "silence":
                    yield {"data": json.dumps(
                        reaction.model_dump(), ensure_ascii=False
                    )}
            except ContextWindowExceededError:
                yield {"data": json.dumps({"error": _TOKEN_LIMIT_MSG}, ensure_ascii=False)}
            except Exception as e:
                yield {"data": json.dumps({"error": str(e)}, ensure_ascii=False)}

        yield {"data": json.dumps({"done": True})}

    return EventSourceResponse(event_generator())


def run():
    uvicorn.run("sim.api.server:app", host="0.0.0.0", port=8000, reload=True)
