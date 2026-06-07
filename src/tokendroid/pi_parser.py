"""Parse Pi coding agent data from ~/.pi/agent/."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import orjson

from .models import ModelInfo, SessionData

PI_DIR = Path.home() / ".pi" / "agent"
PI_SESSIONS_DIR = PI_DIR / "sessions"
PI_SETTINGS_FILE = PI_DIR / "settings.json"
PI_MODELS_FILE = PI_DIR / "models.json"

_SURROGATE_RE = re.compile(r"[\ud800-\udfff]")


def get_pi_dir() -> Path:
    """Return the Pi agent directory path."""
    return PI_DIR


def get_pi_model_display_map() -> dict[str, ModelInfo]:
    """Parse models.json providers into a model_id -> ModelInfo map.

    Pi stores model definitions per provider in models.json. Each provider
    has a ``models`` list with ``id``, ``name``, and cost fields. The cost
    fields are always 0 in NeuralWatt's config, but we read the display names
    so the UI shows human-readable model names.
    """
    mapping: dict[str, ModelInfo] = {}
    if not PI_MODELS_FILE.exists():
        return mapping
    with open(PI_MODELS_FILE, "rb") as f:
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
            # Only store the first occurrence so the primary provider wins
            if mid not in mapping:
                mapping[mid] = ModelInfo(
                    model_id=mid,
                    display_name=m.get("name", mid),
                    provider=_provider_id,
                    base_url=base_url,
                )
    return mapping


def _clean_pi_project_name(dirname: str) -> str:
    """Convert Pi session dir name to a readable project path.

    Pi uses directory names like:
      ``--home-nils-DEV-RUST-nssh--``
    which encode the working directory path with ``-`` as separator and
    ``--`` as delimiters. This converts them back to a readable form:
      ``~/DEV/RUST/nssh``

    Since ``-`` replaces ``/``, multi-segment names like ``home-nils``
    become ``home/nils``.  We strip the ``home/<user>`` prefix to get
    the concise ``~/<rest>`` form that matches Factory's convention.
    """
    name = dirname.strip("-")
    name = name.replace("-", "/")
    if name.startswith("home/"):
        name = "~" + name[4:]  # /home/... → ~/...
        # Strip the username segment: ~/nils/DEV → ~/DEV
        parts = name.split("/")
        if len(parts) > 2 and parts[0] == "~":
            username = parts[1]
            if username and not username.isupper():
                # Looks like a username (not DEV, TMP, etc.)
                name = "~/" + "/".join(parts[2:])
    return name


def _extract_timestamp_from_filename(filename: str) -> str:
    """Extract the ISO timestamp from a Pi session filename.

    Filenames look like:
      ``2026-06-02T14-23-12-891Z_019e88b7-93fb-730b-a196-c52b1f267e77.jsonl``
    The part before ``_`` is the timestamp with ``-`` colons.
    """
    parts = filename.split("_", 1)
    if len(parts) < 1:
        return ""
    raw = parts[0]
    # Replace dashes that represent colons in the time portion
    # Format: YYYY-MM-DDTHH-MM-SS-mmmZ
    # We need to turn it into: YYYY-MM-DDTHH:MM:SS.mmmZ
    try:
        # Split on T to handle date vs time
        if "T" not in raw:
            return raw
        date_part, time_part = raw.split("T", 1)
        # Time part: HH-MM-SS-mmmZ → HH:MM:SS.mmmZ
        segments = time_part.split("-")
        if len(segments) >= 3:
            hours = segments[0]
            minutes = segments[1]
            seconds = segments[2]
            rest = ""
            if len(segments) > 3:
                # Handle milliseconds + Z: 891Z → .891Z
                millis_z = segments[3]
                rest = f".{millis_z[:-1]}Z" if millis_z.endswith("Z") else f"-{millis_z}"
            elif seconds.endswith("Z"):
                seconds = seconds[:-1]
                rest = "Z"
            time_str = f"{hours}:{minutes}:{seconds}{rest}"
            return f"{date_part}T{time_str}"
    except (ValueError, IndexError):
        pass
    return raw


def parse_pi_session_jsonl(jsonl_path: Path) -> dict:
    """Parse a Pi .jsonl session file for token usage, message counts, and metadata.

    Pi's JSONL format stores all data inline:
      - ``type: "session"`` — session metadata (id, cwd, timestamp)
      - ``type: "model_change"`` — model/provider change events
      - ``type: "thinking_level_change"`` — thinking level setting
      - ``type: "message"`` — messages with ``usage`` on assistant messages

    Token counts are aggregated from all assistant message ``usage`` blocks.
    Unlike Factory, Pi does NOT have separate settings files — everything
    is in the JSONL.

    IMPORTANT: Pi's models.json declares cost=0 for all models. We ignore
    those costs and compute our own via models.dev.
    """
    result: dict = {
        "session_id": "",
        "title": "",
        "cwd": "",
        "started_at": "",
        "model": "",
        "model_display": "",
        "provider": "",
        "thinking_level": "",
        "input_tokens": 0,
        "output_tokens": 0,
        "thinking_tokens": 0,
        "cache_tokens": 0,  # cacheRead + cacheWrite
        "active_time_ms": 0,
        "message_count": 0,
        "user_messages": 0,
        "assistant_messages": 0,
        "tool_calls": 0,
    }

    first_timestamp: str | None = None
    last_timestamp: str | None = None

    with open(jsonl_path, "rb") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entry = orjson.loads(line)
            except (orjson.JSONDecodeError, ValueError):
                continue

            entry_type = entry.get("type", "")

            if entry_type == "session":
                result["session_id"] = entry.get("id", "")
                result["cwd"] = entry.get("cwd", "")
                ts = entry.get("timestamp", "")
                result["started_at"] = ts
                if not first_timestamp:
                    first_timestamp = ts
                last_timestamp = ts

            elif entry_type == "model_change":
                result["model"] = entry.get("modelId", result["model"])
                result["provider"] = entry.get("provider", result["provider"])

            elif entry_type == "thinking_level_change":
                result["thinking_level"] = entry.get("thinkingLevel", "")

            elif entry_type == "message":
                msg = entry.get("message", {})
                role = msg.get("role", "")
                result["message_count"] += 1

                if role == "user":
                    result["user_messages"] += 1
                elif role == "assistant":
                    result["assistant_messages"] += 1

                    # Aggregate token usage from this assistant turn
                    usage = msg.get("usage", {})
                    if isinstance(usage, dict):
                        result["input_tokens"] += usage.get("input", 0)
                        result["output_tokens"] += usage.get("output", 0)
                        result["thinking_tokens"] += usage.get("reasoning", 0)
                        result["cache_tokens"] += (
                            usage.get("cacheRead", 0) + usage.get("cacheWrite", 0)
                        )

                    # Count tool calls in assistant content
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict) and part.get("type") in (
                                "toolCall",
                                "tool_use",
                            ):
                                result["tool_calls"] += 1

                ts = entry.get("timestamp", "")
                if ts:
                    if not first_timestamp:
                        first_timestamp = ts
                    last_timestamp = ts

    # Compute active time from first to last message
    if first_timestamp and last_timestamp and first_timestamp != last_timestamp:
        try:
            from datetime import datetime

            fmt = "%Y-%m-%dT%H:%M:%S"
            # Parse timestamps, handling fractional seconds and Z suffix
            def _parse_ts(ts: str) -> datetime:
                ts = ts.rstrip("Z")
                fmt_full = "%Y-%m-%dT%H:%M:%S.%f" if "." in ts else fmt
                return datetime.strptime(ts, fmt_full)

            delta = _parse_ts(last_timestamp) - _parse_ts(first_timestamp)
            result["active_time_ms"] = int(delta.total_seconds() * 1000)
        except (ValueError, TypeError):
            result["active_time_ms"] = 0

    # Use filename-extracted timestamp if session entry didn't have one
    if not result["started_at"]:
        result["started_at"] = _extract_timestamp_from_filename(jsonl_path.name)

    if not result["session_id"]:
        result["session_id"] = jsonl_path.stem

    return result


def iter_pi_sessions() -> Iterator[SessionData]:
    """Iterate over all Pi sessions in ~/.pi/agent/sessions/."""
    model_map = get_pi_model_display_map()

    if not PI_SESSIONS_DIR.exists():
        return

    for project_dir in sorted(PI_SESSIONS_DIR.iterdir()):
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
                    source="pi",
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


def get_pi_file_mtimes() -> dict[str, float]:
    """Get modification times for all Pi session files for incremental sync."""
    mtimes: dict[str, float] = {}
    if not PI_SESSIONS_DIR.exists():
        return mtimes
    for project_dir in PI_SESSIONS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        for f in project_dir.iterdir():
            if f.suffix != ".jsonl":
                continue
            try:
                # Use pi: prefix to avoid collision with factory paths
                rel = f"pi:{f.relative_to(PI_SESSIONS_DIR)}"
                mtimes[rel] = f.stat().st_mtime
            except OSError:
                continue
    return mtimes
