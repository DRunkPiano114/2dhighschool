from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SceneDensity(str, Enum):
    HIGH = "high"
    HIGH_LIGHT = "high_light"
    LOW = "low"


class SceneConfig(BaseModel):
    time: str
    name: str
    location: str
    density: SceneDensity
    max_rounds: int = 12
    trigger_probability: float = 1.0
    description: str = ""
    opening_events: list[str] = Field(default_factory=list)
    is_free_period: bool = False
    valid_locations: list[str] = Field(default_factory=list)
    pref_field: Literal["morning_break", "lunch", "afternoon_break"] | None = None

    @model_validator(mode="after")
    def _validate_free_period_fields(self):
        if self.is_free_period:
            if not self.pref_field:
                raise ValueError(f"Free period {self.name!r} missing pref_field")
            if not self.valid_locations:
                raise ValueError(f"Free period {self.name!r} missing valid_locations")
            if self.location not in self.valid_locations:
                raise ValueError(
                    f"Free period {self.name!r}: default location {self.location!r} "
                    f"not in valid_locations {self.valid_locations}"
                )
        return self


class GroupAssignment(BaseModel):
    group_id: int
    agent_ids: list[str]
    is_solo: bool = False


class Scene(BaseModel):
    scene_index: int
    day: int
    time: str
    name: str
    location: str
    density: SceneDensity
    max_rounds: int = 12
    description: str = ""
    agent_ids: list[str] = Field(default_factory=list)
    groups: list[GroupAssignment] = Field(default_factory=list)
    injected_events: list[str] = Field(default_factory=list)
    teacher_present: bool = False
    teacher_action: str | None = None
    opening_event: str = ""
