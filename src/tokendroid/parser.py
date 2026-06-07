"""Parse Factory Droid data from ~/.factory and Pi agent data from ~/.pi/agent/."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import orjson

from .models import HistoryEntry, ModelInfo, SessionData

_SURROGATE_RE = re.compile(r"[\ud800-\udfff]")

FACTORY_DIR = Path.home() / ".factory"
SESSIONS_DIR = FACTORY_DIR / "sessions"
SETTINGS_FILE = FACTORY_DIR / "settings.json"
HISTORY_FILE = FACTORY_DIR / "history.json"


def get_factory_dir() -> Path:
    return FACTORY_DIR


def get_model_display_map() -> dict[str, ModelInfo]:
    """Parse settings.json customModels into a model_id -> ModelInfo map."""
    mapping: dict[str, ModelInfo] = {}
    if not SETTINGS_FILE.exists():
        return mapping
    with open(SETTINGS_FILE, "rb") as f:
        data = orjson.loads(f.read())
    for m in data.get("customModels", []):
        mid = m.get("id", "")
        mapping[mid] = ModelInfo(
            model_id=mid,
            display_name=m.get("displayName", mid),
            provider=m.get("provider", ""),
            base_url=m.get("baseUrl", ""),
        )
    return mapping


def _clean_project_name(dirname: str) -> str:
    """Convert session dir name to a readable project path."""
    name = dirname.lstrip("-")
    name = name.replace("-", "/")
    if name.startswith("home/"):
        name = "~" + name[4:]
    return name


def parse_session_settings(settings_path: Path, model_map: dict[str, ModelInfo]) -> dict:
    """Parse a single .settings.json file into a raw dict."""
    with open(settings_path, "rb") as f:
        data = orjson.loads(f.read())

    model_id = data.get("model", "?")
    info = model_map.get(model_id)
    model_display = info.display_name if info else model_id

    tokens = data.get("tokenUsage", {})
    return {
        "model": model_id,
        "model_display": model_display,
        "provider": data.get("providerLock", ""),
        "interaction_mode": data.get("interactionMode", ""),
        "autonomy_level": data.get("autonomyLevel", ""),
        "reasoning_effort": data.get("reasoningEffort", ""),
        "started_at": data.get("providerLockTimestamp", ""),
        "input_tokens": tokens.get("inputTokens", 0),
        "output_tokens": tokens.get("outputTokens", 0),
        "thinking_tokens": tokens.get("thinkingTokens", 0),
        "cache_tokens": tokens.get("cacheReadTokens", 0) + tokens.get("cacheCreationTokens", 0),
        "active_time_ms": data.get("assistantActiveTimeMs", 0),
    }


def parse_session_jsonl(jsonl_path: Path) -> dict:
    """Parse a .jsonl session file for message counts and metadata."""
    result: dict = {
        "title": "",
        "session_id": jsonl_path.stem,
        "cwd": "",
        "owner": "",
        "message_count": 0,
        "user_messages": 0,
        "assistant_messages": 0,
        "tool_calls": 0,
    }
    with open(jsonl_path, "rb") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entry = orjson.loads(line)
            except (orjson.JSONDecodeError, ValueError):
                continue
            entry_type = entry.get("type", "")
            if entry_type == "session_start":
                result["title"] = entry.get("title", "")[:120]
                result["session_id"] = entry.get("id", jsonl_path.stem)
                result["cwd"] = entry.get("cwd", "")
                result["owner"] = entry.get("owner", "")
            elif entry_type == "message":
                msg = entry.get("message", {})
                role = msg.get("role", "")
                result["message_count"] += 1
                if role == "user":
                    result["user_messages"] += 1
                elif role == "assistant":
                    result["assistant_messages"] += 1
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "tool_use":
                                result["tool_calls"] += 1
    return result


def iter_sessions() -> Iterator[SessionData]:
    """Iterate over all sessions in ~/.factory/sessions/."""
    model_map = get_model_display_map()

    if not SESSIONS_DIR.exists():
        return

    for project_dir in sorted(SESSIONS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        project_name = _clean_project_name(project_dir.name)

        settings_files: dict[str, Path] = {}
        jsonl_files: dict[str, Path] = {}

        for f in project_dir.iterdir():
            if f.suffix == ".json" and f.name.endswith(".settings.json"):
                settings_files[f.stem.replace(".settings", "")] = f
            elif f.suffix == ".jsonl":
                jsonl_files[f.stem] = f

        all_ids = set(settings_files.keys()) | set(jsonl_files.keys())

        for sid in sorted(all_ids):
            try:
                settings = {}
                if sid in settings_files:
                    settings = parse_session_settings(settings_files[sid], model_map)

                jsonl_data = {}
                if sid in jsonl_files:
                    jsonl_data = parse_session_jsonl(jsonl_files[sid])

                yield SessionData(
                    id=jsonl_data.get("session_id", sid),
                    project=project_name,
                    title=jsonl_data.get("title", ""),
                    model=settings.get("model", "?"),
                    model_display=settings.get("model_display", "?"),
                    provider=settings.get("provider", ""),
                    interaction_mode=settings.get("interaction_mode", ""),
                    autonomy_level=settings.get("autonomy_level", ""),
                    reasoning_effort=settings.get("reasoning_effort", ""),
                    started_at=settings.get("started_at", ""),
                    input_tokens=settings.get("input_tokens", 0),
                    output_tokens=settings.get("output_tokens", 0),
                    thinking_tokens=settings.get("thinking_tokens", 0),
                    cache_tokens=settings.get("cache_tokens", 0),
                    active_time_ms=settings.get("active_time_ms", 0),
                    message_count=jsonl_data.get("message_count", 0),
                    user_messages=jsonl_data.get("user_messages", 0),
                    assistant_messages=jsonl_data.get("assistant_messages", 0),
                    tool_calls=jsonl_data.get("tool_calls", 0),
                )
            except Exception:
                continue


def parse_history() -> list[HistoryEntry]:
    """Parse history.json."""
    if not HISTORY_FILE.exists():
        return []
    with open(HISTORY_FILE, "rb") as f:
        raw = f.read()
    try:
        data = orjson.loads(raw)
    except orjson.JSONDecodeError:
        import json

        data = json.loads(raw)
    entries: list[HistoryEntry] = []
    for item in data:
        command = item.get("command", "")
        if _SURROGATE_RE.search(command):
            command = _SURROGATE_RE.sub("", command)
        entries.append(
            HistoryEntry(
                timestamp=item.get("timestamp", ""),
                command=command,
                entry_type=item.get("type", ""),
                mode=item.get("mode", ""),
            )
        )
    return entries


def get_file_mtimes() -> dict[str, float]:
    """Get modification times for all session files for incremental sync."""
    mtimes: dict[str, float] = {}
    if not SESSIONS_DIR.exists():
        return mtimes
    for project_dir in SESSIONS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        for f in project_dir.iterdir():
            try:
                rel = str(f.relative_to(SESSIONS_DIR))
                mtimes[rel] = f.stat().st_mtime
            except OSError:
                continue
    return mtimes


def get_all_file_mtimes() -> dict[str, float]:
    """Get modification times for Factory + Pi session files."""
    from .pi_parser import get_pi_file_mtimes

    mtimes = get_file_mtimes()
    mtimes.update(get_pi_file_mtimes())
    return mtimes


def iter_all_sessions() -> Iterator[SessionData]:
    """Iterate over sessions from both Factory and Pi sources."""
    yield from iter_sessions()

    from .pi_parser import iter_pi_sessions

    yield from iter_pi_sessions()
