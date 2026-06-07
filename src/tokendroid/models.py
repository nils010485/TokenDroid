"""Data models for TokenDroid."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SessionData:
    """Parsed session from settings.json + jsonl."""

    id: str
    project: str
    title: str
    model: str
    model_display: str
    provider: str
    interaction_mode: str
    autonomy_level: str
    reasoning_effort: str
    started_at: str
    source: str = "factory"  # "factory" or "pi"
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cache_tokens: int = 0
    active_time_ms: int = 0
    message_count: int = 0
    user_messages: int = 0
    assistant_messages: int = 0
    tool_calls: int = 0


@dataclass
class HistoryEntry:
    """Single entry from history.json."""

    timestamp: str
    command: str
    entry_type: str
    mode: str


@dataclass
class DailyStat:
    """Aggregated stats for a single day."""

    date: str
    project: str = ""
    model: str = ""
    sessions: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cache_tokens: int = 0
    active_time_ms: int = 0
    messages: int = 0


@dataclass
class ModelInfo:
    """Model display name mapping from settings.json."""

    model_id: str
    display_name: str
    provider: str
    base_url: str


@dataclass
class ProjectSummary:
    """Summary stats for a project."""

    name: str
    sessions: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cache_tokens: int = 0
    active_time_ms: int = 0
    messages: int = 0
    top_models: list[str] = field(default_factory=list)


@dataclass
class ModelSummary:
    """Summary stats for a model."""

    model_id: str
    display_name: str
    sessions: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cache_tokens: int = 0
    active_time_ms: int = 0
    messages: int = 0
    projects: int = 0


@dataclass
class ModelPrice:
    """Price per 1M tokens for a model from models.dev."""

    model_id: str
    input_per_1m: float = 0.0
    output_per_1m: float = 0.0
    cache_read_per_1m: float = 0.0
    cache_write_per_1m: float = 0.0
    reasoning_per_1m: float = 0.0


@dataclass
class CostSummary:
    """Computed cost breakdown."""

    input_cost: float = 0.0
    output_cost: float = 0.0
    cache_cost: float = 0.0
    reasoning_cost: float = 0.0

    @property
    def total_cost(self) -> float:
        return self.input_cost + self.output_cost + self.cache_cost + self.reasoning_cost


@dataclass
class GlobalStats:
    """Global aggregated statistics."""

    total_sessions: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_thinking_tokens: int = 0
    total_cache_tokens: int = 0
    total_active_time_ms: int = 0
    total_messages: int = 0
    total_projects: int = 0
    total_models: int = 0
    date_range_start: str = ""
    date_range_end: str = ""
    by_model: list[ModelSummary] = field(default_factory=list)
    by_project: list[ProjectSummary] = field(default_factory=list)
    by_day: list[DailyStat] = field(default_factory=list)
