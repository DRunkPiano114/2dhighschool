from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv(override=True)


class Settings(BaseSettings):
    model_config = {"env_prefix": "SIM_"}

    # Paths
    project_root: Path = Path(".")
    cast_dir: Path = Path("canon/cast")
    worldbook_dir: Path = Path("canon/worldbook")
    simulation_dir: Path = Path("simulation")
    days_dir: Path = Path("simulation/days")
    agents_dir: Path = Path("simulation/state")
    world_dir: Path = Path("simulation/world")

    # LLM
    llm_model: str = "openrouter/google/gemini-3.1-flash-lite-preview"
    llm_fallback_model: str = "openrouter/google/gemini-3-flash-preview"
    creative_temperature: float = 0.9
    analytical_temperature: float = 0.3
    plan_temperature: float = 0.7
    compression_temperature: float = 0.5
    max_tokens_per_turn: int = 32000
    max_tokens_scene_end: int = 32000
    max_tokens_daily_plan: int = 32000
    max_tokens_compression: int = 32000
    max_tokens_solo: int = 32000
    max_retries: int = 3

    # PDA tick loop
    min_ticks_before_termination: int = 3
    consecutive_quiet_to_end: int = 4
    perception_temperature: float = 0.9
    max_tokens_perception: int = 32000

    # Simulation
    exam_interval_days: int = 30
    event_expire_days: int = 3
    recent_md_max_weeks: int = 4
    max_key_memories: int = 10
    solo_energy_threshold: int = 20  # Fix 18: lowered from 25

    # key_memories write controls
    key_memory_write_threshold: int = 3       # min importance to write
    per_day_memory_cap: int = 2               # post-pass cap on today's memories

    # Self-narrative
    self_narrative_interval_days: int = 3
    self_narrative_temperature: float = 0.7
    max_tokens_self_narrative: int = 32000

    # Re-planning
    replan_temperature: float = 0.7
    max_tokens_replan: int = 32000

    # Self-reflection (post-scene per-agent)
    reflection_temperature: float = 0.7
    max_tokens_reflection: int = 32000
    max_tokens_narrative: int = 32000

    # Concerns
    max_active_concerns: int = 4
    concern_decay_per_day: int = 2            # intensity drop per end-of-day
    concern_stale_days: int = 5               # days without reinforcement → evict
    concern_autogen_max_intensity: int = 6    # cap for reflection-generated concerns

    # Daily plan audit retry (PR8). Flag-off default: PR6 prompt changes
    # may already absorb most of the "high-intensity concern not hooked"
    # signal. Observe a week of audit-warning volume before flipping on.
    daily_plan_audit_retry: bool = False
    daily_plan_audit_max_retries_per_call: int = 1
    daily_plan_audit_max_retries_per_day_per_agent: int = 1

    # Ambient events (Fix 12)
    ambient_event_probability: float = 0.3
    ambient_events_file: Path = Path("canon/worldbook/scene_ambient_events.json")

    # Consolidation (Fix 15)
    consolidation_interval_days: int = 3
    consolidation_lookback_days: int = 7
    consolidation_temperature: float = 0.3
    max_tokens_consolidation: int = 4000

    # Relationships
    max_recent_interactions: int = 10         # per-relationship recent interaction log cap
    relationship_positive_stale_days: int = 5 # days without interaction before positive decay starts

    # Concurrency
    max_concurrent_llm_calls: int = 5


settings = Settings()
