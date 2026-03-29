from ..models.agent import AgentProfile
from ..models.memory import KeyMemory, KeyMemoryFile
from ..models.scene import Scene


def _extract_triggers(scene: Scene, profiles: dict[str, AgentProfile]) -> set[str]:
    triggers: set[str] = set()
    # People present
    for aid in scene.agent_ids:
        if aid in profiles:
            triggers.add(profiles[aid].name)
            triggers.add(aid)
    # Location
    triggers.add(scene.location)
    # Scene name
    triggers.add(scene.name)
    return triggers


def _overlap(memory: KeyMemory, triggers: set[str]) -> int:
    tags: set[str] = set()
    tags.update(memory.people)
    tags.update(memory.topics)
    tags.add(memory.location)
    return len(tags & triggers)


def get_relevant_memories(
    memory_file: KeyMemoryFile,
    scene: Scene,
    profiles: dict[str, AgentProfile],
    max_k: int = 10,
) -> list[KeyMemory]:
    triggers = _extract_triggers(scene, profiles)
    relevant = [m for m in memory_file.memories if _overlap(m, triggers) > 0]
    # Sort by importance descending, then by overlap
    relevant.sort(key=lambda m: (m.importance, _overlap(m, triggers)), reverse=True)
    return relevant[:max_k]
