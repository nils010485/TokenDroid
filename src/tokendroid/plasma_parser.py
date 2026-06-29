"""Parse Plasma coding agent data from ~/.local/share/plasma/pi-agent/.

Plasma is a Pi-compatible harness: sessions use the exact same JSONL format
as Pi, only the storage directory differs. We reuse pi_parser's parsing logic
(``parse_pi_session_jsonl``, ``_clean_pi_project_name``) and override only the
directory and ``source`` label.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import orjson

from .models import ModelInfo, SessionData
from .pi_parser import _clean_pi_project_name, parse_pi_session_jsonl

PLASMA_DIR = Path.home() / ".local" / "share" / "plasma" / "pi-agent"
PLASMA_SESSIONS_DIR = PLASMA_DIR / "sessions"
PLASMA_MODELS_FILE = PLASMA_DIR / "models.json"


def get_plasma_dir() -> Path:
    """Return the Plasma agent directory path."""
    return PLASMA_DIR


def get_plasma_model_display_map() -> dict[str, ModelInfo]:
    """Parse Plasma's models.json providers into a model_id -> ModelInfo map."""
    mapping: dict[str, ModelInfo] = {}
    if not PLASMA_MODELS_FILE.exists():
        return mapping
    with open(PLASMA_MODELS_FILE, "rb") as f:
        data = orjson.loads(f.read())
    providers = data.get("providers", {})
    for _provider_id, provider in providers.items():
        if not isinstance(provider, dict):
            continue
        base_url = provider.get("baseUrl", "")
        for m in provider.get("models", []):
            mid = m.get("id", "")
            if not mid:
                continue
            if mid not in mapping:
                mapping[mid] = ModelInfo(
                    model_id=mid,
                    display_name=m.get("name", mid),
                    provider=_provider_id,
                    base_url=base_url,
                )
    return mapping


def iter_plasma_sessions() -> Iterator[SessionData]:
    """Iterate over all Plasma sessions in ~/.local/share/plasma/pi-agent/sessions/."""
    if not PLASMA_SESSIONS_DIR.exists():
        return

    model_map = get_plasma_model_display_map()
    for project_dir in sorted(PLASMA_SESSIONS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        project_name = _clean_pi_project_name(project_dir.name)

        for jsonl_file in sorted(project_dir.glob("*.jsonl")):
            try:
                data = parse_pi_session_jsonl(jsonl_file)

                model_id = data["model"]
                info = model_map.get(model_id)
                model_display = info.display_name if info else model_id

                yield SessionData(
                    id=data["session_id"],
                    project=project_name,
                    title=data["title"],
                    model=model_id,
                    model_display=model_display,
                    provider=data["provider"],
                    interaction_mode="",
                    autonomy_level="",
                    reasoning_effort=data.get("thinking_level", ""),
                    started_at=data["started_at"],
                    source="plasma",
                    input_tokens=data["input_tokens"],
                    output_tokens=data["output_tokens"],
                    thinking_tokens=data["thinking_tokens"],
                    cache_tokens=data["cache_tokens"],
                    active_time_ms=data["active_time_ms"],
                    message_count=data["message_count"],
                    user_messages=data["user_messages"],
                    assistant_messages=data["assistant_messages"],
                    tool_calls=data["tool_calls"],
                )
            except Exception:
                continue


def get_plasma_file_mtimes() -> dict[str, float]:
    """Get modification times for all Plasma session files for incremental sync."""
    mtimes: dict[str, float] = {}
    if not PLASMA_SESSIONS_DIR.exists():
        return mtimes
    for project_dir in PLASMA_SESSIONS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        for f in project_dir.iterdir():
            if f.suffix != ".jsonl":
                continue
            try:
                rel = f"plasma:{f.relative_to(PLASMA_SESSIONS_DIR)}"
                mtimes[rel] = f.stat().st_mtime
            except OSError:
                continue
    return mtimes
