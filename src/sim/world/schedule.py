import json
from pathlib import Path

from ..config import settings
from ..models.scene import SceneConfig


def load_schedule(schedule_path: Path | None = None) -> list[SceneConfig]:
    path = schedule_path or (settings.worldbook_dir / "schedule.json")
    data = json.loads(path.read_text("utf-8"))
    return [SceneConfig.model_validate(item) for item in data]
