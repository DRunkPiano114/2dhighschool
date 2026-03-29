from ..agent.storage import AgentStorage
from ..models.memory import KeyMemory


def append_to_today_md(storage: AgentStorage, content: str) -> None:
    storage.append_today_md(content)


def write_key_memory(storage: AgentStorage, memory: KeyMemory) -> None:
    storage.append_key_memory(memory)
