"""Parse Plasma coding agent data from its platform-specific data directory.

Plasma is a Pi-compatible harness: sessions use the exact same JSONL format
as Pi, only the storage directory differs. We reuse pi_parser's parsing logic
(``parse_pi_session_jsonl``, ``_clean_pi_project_name``) and override only the
directory and ``source`` label.

Plasma is a Tauri app, so its data directory follows the OS convention:
  - Windows: ``%APPDATA%/plasma/pi-agent``  (usually ``~/AppData/Roaming/...``)
  - macOS:   ``~/Library/Application Support/plasma/pi-agent``
  - Linux:   ``~/.local/share/plasma/pi-agent``
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import orjson

from .models import ModelInfo, SessionData
from .pi_parser import _clean_pi_project_name, parse_pi_session_jsonl


def _plasma_base_dir() -> Path:
    """Return the Plasma data directory, OS-aware (Tauri app conventions)."""
    # Windows: respect %APPDATA% when set, fall back to ~/AppData/Roaming.
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "plasma" / "pi-agent"
        return Path.home() / "AppData" / "Roaming" / "plasma" / "pi-agent"
    # macOS: ~/Library/Application Support
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "plasma" / "pi-agent"
    # Linux / other: XDG data dir
    return Path.home() / ".local" / "share" / "plasma" / "pi-agent"


PLASMA_DIR = _plasma_base_dir()
PLASMA_SESSIONS_DIR = PLASMA_DIR / "sessions"
PLASMA_MODELS_FILE = PLASMA_DIR / "models.json"


def get_plasma_dir() -> Path:
    """Return the Plasma agent directory path."""
    return PLASMA_DIR


def get_plasma_model_display_map() -> dict[tuple[str, str], ModelInfo]:
    """Parse Plasma's models.json providers into a ``(provider, model_id) -> ModelInfo`` map.

    The same model ``id`` can exist under several providers with different
    names (e.g. ``glm-5.2`` is ``GLM-5.2 [NW]`` under ``neuralwatt-extra``
    but ``GLM5.2 [Z.AI]`` under ``zai``). Keying by ``(provider, model_id)``
    keeps each combination distinct instead of letting the first provider's
    name win for every session.
    """
    mapping: dict[tuple[str, str], ModelInfo] = {}
    if not PLASMA_MODELS_FILE.exists():
        return mapping
    with open(PLASMA_MODELS_FILE, "rb") as f:
        data = orjson.loads(f.read())
    providers = data.get("providers", {})
    for provider_id, provider in providers.items():
        if not isinstance(provider, dict):
            continue
        base_url = provider.get("baseUrl", "")
        for m in provider.get("models", []):
            mid = m.get("id", "")
            if not mid:
                continue
            mapping[(provider_id, mid)] = ModelInfo(
                model_id=mid,
                display_name=m.get("name", mid),
                provider=provider_id,
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

        for jsonl_file in sorted(project_dir.rglob("*.jsonl")):
            try:
                data = parse_pi_session_jsonl(jsonl_file)

                model_id = data["model"]
                info = model_map.get((data["provider"], model_id))
                model_display = info.display_name if info else model_id

                # Depth-1 files (directly under the project dir) are normal
                # sessions; anything nested deeper is a subagent session
                # stored under <uuid>/<hash>/run-N/session.jsonl.
                is_subagent = len(jsonl_file.relative_to(project_dir).parts) > 1

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
                    is_subagent=is_subagent,
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
        for f in project_dir.rglob("*.jsonl"):
            try:
                rel = f"plasma:{f.relative_to(PLASMA_SESSIONS_DIR)}"
                mtimes[rel] = f.stat().st_mtime
            except OSError:
                continue
    return mtimes
