"""Tests for the parser module."""

import json
from pathlib import Path
from unittest.mock import patch

from tokendroid.models import ModelInfo
from tokendroid.parser import (
    _clean_project_name,
    get_model_display_map,
    iter_sessions,
    parse_history,
    parse_session_jsonl,
    parse_session_settings,
)


class TestCleanProjectName:
    def test_simple(self):
        assert _clean_project_name("my-project") == "my/project"

    def test_leading_dashes(self):
        assert _clean_project_name("--my-proj") == "my/proj"

    def test_home_prefix(self):
        assert _clean_project_name("home-user-proj") == "~/user/proj"


class TestGetModelDisplayMap:
    def test_no_settings_file(self):
        with patch("tokendroid.parser.SETTINGS_FILE", Path("/nonexistent")):
            assert get_model_display_map() == {}

    def test_valid_settings(self, tmp_path):
        settings = tmp_path / "settings.json"
        data = {
            "customModels": [
                {
                    "id": "gpt-4",
                    "displayName": "GPT-4",
                    "provider": "openai",
                    "baseUrl": "https://api.openai.com",
                },
            ]
        }
        settings.write_text(json.dumps(data))
        with patch("tokendroid.parser.SETTINGS_FILE", settings):
            result = get_model_display_map()
        assert "gpt-4" in result
        assert result["gpt-4"].display_name == "GPT-4"

    def test_missing_display_name_fallback(self, tmp_path):
        settings = tmp_path / "settings.json"
        settings.write_text(json.dumps({"customModels": [{"id": "m1"}]}))
        with patch("tokendroid.parser.SETTINGS_FILE", settings):
            result = get_model_display_map()
        assert result["m1"].display_name == "m1"


class TestParseSessionSettings:
    def _make_info(self):
        return ModelInfo(
            model_id="gpt-4",
            display_name="GPT-4",
            provider="openai",
            base_url="",
        )

    def test_basic(self, tmp_path):
        sf = tmp_path / "test.settings.json"
        data = {
            "model": "gpt-4",
            "providerLock": "openai",
            "interactionMode": "agent",
            "autonomyLevel": "full",
            "reasoningEffort": "high",
            "providerLockTimestamp": "2025-01-15T10:00:00",
            "tokenUsage": {
                "inputTokens": 100,
                "outputTokens": 200,
                "cacheReadTokens": 50,
            },
            "assistantActiveTimeMs": 30000,
        }
        sf.write_text(json.dumps(data))
        result = parse_session_settings(sf, {"gpt-4": self._make_info()})
        assert result["model"] == "gpt-4"
        assert result["model_display"] == "GPT-4"
        assert result["input_tokens"] == 100
        assert result["cache_tokens"] == 50

    def test_unknown_model(self, tmp_path):
        sf = tmp_path / "test.settings.json"
        sf.write_text(json.dumps({"model": "unknown"}))
        result = parse_session_settings(sf, {})
        assert result["model_display"] == "unknown"


class TestParseSessionJsonl:
    def test_basic(self, tmp_path):
        jf = tmp_path / "test.jsonl"
        start = {
            "type": "session_start",
            "id": "sid1",
            "title": "Test Session",
            "cwd": "/home/user",
            "owner": "user",
        }
        user_msg = {
            "type": "message",
            "message": {"role": "user", "content": "hello"},
        }
        assistant_msg = {
            "type": "message",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "hi"},
                    {"type": "tool_use", "name": "run"},
                ],
            },
        }
        lines = [start, user_msg, assistant_msg]
        jf.write_bytes(
            b"\n".join(json.dumps(entry).encode() for entry in lines) + b"\n"
        )
        result = parse_session_jsonl(jf)
        assert result["session_id"] == "sid1"
        assert result["title"] == "Test Session"
        assert result["message_count"] == 2
        assert result["user_messages"] == 1
        assert result["assistant_messages"] == 1
        assert result["tool_calls"] == 1

    def test_empty_file(self, tmp_path):
        jf = tmp_path / "empty.jsonl"
        jf.write_bytes(b"")
        result = parse_session_jsonl(jf)
        assert result["message_count"] == 0
        assert result["session_id"] == "empty"

    def test_corrupt_line_skipped(self, tmp_path):
        jf = tmp_path / "bad.jsonl"
        jf.write_bytes(b"not json\n")
        result = parse_session_jsonl(jf)
        assert result["message_count"] == 0


class TestParseHistory:
    def test_no_file(self):
        with patch("tokendroid.parser.HISTORY_FILE", Path("/nonexistent")):
            assert parse_history() == []

    def test_valid_history(self, tmp_path):
        hf = tmp_path / "history.json"
        entry = {
            "timestamp": "2025-01-15T10:00:00",
            "command": "droid run",
            "type": "run",
            "mode": "agent",
        }
        hf.write_text(json.dumps([entry]))
        with patch("tokendroid.parser.HISTORY_FILE", hf):
            result = parse_history()
        assert len(result) == 1
        assert result[0].command == "droid run"


class TestIterSessions:
    def test_no_sessions_dir(self):
        with patch("tokendroid.parser.SESSIONS_DIR", Path("/nonexistent")):
            assert list(iter_sessions()) == []
