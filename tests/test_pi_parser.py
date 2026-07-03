"""Tests for the pi_parser module."""

import json
from pathlib import Path
from unittest.mock import patch

from tokendroid.pi_parser import (
    _clean_pi_project_name,
    _extract_timestamp_from_filename,
    get_pi_model_display_map,
    iter_pi_sessions,
    parse_pi_session_jsonl,
)


class TestCleanPiProjectName:
    def test_standard_path(self):
        assert _clean_pi_project_name("--home-nils-DEV-RUST-nssh--") == "~/DEV/RUST/nssh"

    def test_tmp_path(self):
        assert _clean_pi_project_name("--tmp--") == "tmp"

    def test_home_prefix(self):
        assert _clean_pi_project_name("--home-user--") == "~/user"

    def test_nested_path(self):
        result = _clean_pi_project_name(
            "--home-nils-DEV-PYTHON-work-spamtrap-dashboard--"
        )
        assert result == "~/DEV/PYTHON/work/spamtrap/dashboard"


class TestExtractTimestamp:
    def test_standard_filename(self):
        result = _extract_timestamp_from_filename(
            "2026-06-02T14-23-12-891Z_019e88b7-93fb-730b-a196-c52b1f267e77.jsonl"
        )
        assert result == "2026-06-02T14:23:12.891Z"

    def test_no_millis(self):
        result = _extract_timestamp_from_filename(
            "2026-06-07T09-31-54-716Z_019ea16c-addc-71ee-90c8-562bd534c868.jsonl"
        )
        assert result == "2026-06-07T09:31:54.716Z"

    def test_simple(self):
        result = _extract_timestamp_from_filename(
            "2026-06-02T13-52-26-261Z_abc123.jsonl"
        )
        assert result == "2026-06-02T13:52:26.261Z"


class TestGetPiModelDisplayMap:
    def test_no_models_file(self):
        with patch("tokendroid.pi_parser.PI_MODELS_FILE", Path("/nonexistent")):
            assert get_pi_model_display_map() == {}

    def test_valid_models(self, tmp_path):
        models_file = tmp_path / "models.json"
        data = {
            "providers": {
                "neuralwatt": {
                    "baseUrl": "https://api.neuralwatt.com/v1",
                    "models": [
                        {
                            "id": "zai-org/GLM-5.1-FP8",
                            "name": "GLM-5.1",
                            "cost": {"input": 0, "output": 0},
                        },
                        {
                            "id": "kimi-k2.6-fast",
                            "name": "Kimi K2.6 Fast",
                        },
                    ],
                },
                "other_provider": {
                    "baseUrl": "https://other.example.com",
                    "models": [
                        {
                            "id": "zai-org/GLM-5.1-FP8",
                            "name": "GLM-5.1 [Other]",
                        },
                    ],
                },
            }
        }
        models_file.write_text(json.dumps(data))
        with patch("tokendroid.pi_parser.PI_MODELS_FILE", models_file):
            result = get_pi_model_display_map()
        # Keyed by (provider, model_id) so the same model id under
        # different providers keeps its own display name.
        assert ("neuralwatt", "zai-org/GLM-5.1-FP8") in result
        assert result[("neuralwatt", "zai-org/GLM-5.1-FP8")].display_name == "GLM-5.1"
        assert ("other_provider", "zai-org/GLM-5.1-FP8") in result
        assert (
            result[("other_provider", "zai-org/GLM-5.1-FP8")].display_name
            == "GLM-5.1 [Other]"
        )
        assert ("neuralwatt", "kimi-k2.6-fast") in result
        assert (
            result[("neuralwatt", "kimi-k2.6-fast")].display_name == "Kimi K2.6 Fast"
        )


def _write_jsonl(path, lines):
    """Helper to write a list of dicts as JSONL."""
    path.write_bytes(
        b"\n".join(json.dumps(entry).encode() for entry in lines) + b"\n"
    )


class TestParsePiSessionJsonl:
    def test_basic_session(self, tmp_path):
        jf = tmp_path / "2026-06-02T14-23-12-891Z_abc123.jsonl"
        lines = [
            {
                "type": "session",
                "version": 3,
                "id": "abc123",
                "timestamp": "2026-06-02T14:23:12.891Z",
                "cwd": "/home/user/project",
            },
            {
                "type": "model_change",
                "provider": "neuralwatt",
                "modelId": "zai-org/GLM-5.1-FP8",
            },
            {"type": "thinking_level_change", "thinkingLevel": "medium"},
            {
                "type": "message",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "hello"}],
                },
            },
            {
                "type": "message",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Hi!"}],
                    "usage": {
                        "input": 500,
                        "output": 50,
                        "cacheRead": 100,
                        "cacheWrite": 0,
                        "reasoning": 20,
                        "totalTokens": 670,
                        "cost": {"total": 0},
                    },
                },
                "timestamp": "2026-06-02T14:23:45.000Z",
            },
        ]
        _write_jsonl(jf, lines)
        result = parse_pi_session_jsonl(jf)
        assert result["session_id"] == "abc123"
        assert result["model"] == "zai-org/GLM-5.1-FP8"
        assert result["provider"] == "neuralwatt"
        assert result["input_tokens"] == 500
        assert result["output_tokens"] == 50
        assert result["cache_tokens"] == 100  # cacheRead
        assert result["thinking_tokens"] == 20
        assert result["user_messages"] == 1
        assert result["assistant_messages"] == 1
        assert result["message_count"] == 2
        assert result["thinking_level"] == "medium"
        assert result["started_at"] == "2026-06-02T14:23:12.891Z"

    def test_multiple_assistant_messages_aggregate(self, tmp_path):
        jf = tmp_path / "2026-06-02T14-00-00-000Z_sid1.jsonl"
        lines = [
            {
                "type": "session",
                "id": "sid1",
                "timestamp": "2026-06-02T14:00:00Z",
                "cwd": "/tmp",
            },
            {"type": "message", "message": {"role": "user", "content": "hi"}},
            {
                "type": "message",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "hello"}],
                    "usage": {
                        "input": 100,
                        "output": 10,
                        "cacheRead": 0,
                        "cacheWrite": 0,
                    },
                },
            },
            {"type": "message", "message": {"role": "user", "content": "more"}},
            {
                "type": "message",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "sure"},
                        {"type": "toolCall", "name": "bash", "id": "call1"},
                    ],
                    "usage": {
                        "input": 200,
                        "output": 50,
                        "cacheRead": 50,
                        "cacheWrite": 0,
                        "reasoning": 10,
                    },
                },
            },
        ]
        _write_jsonl(jf, lines)
        result = parse_pi_session_jsonl(jf)
        assert result["input_tokens"] == 300  # 100 + 200
        assert result["output_tokens"] == 60  # 10 + 50
        assert result["cache_tokens"] == 50  # 0 + 50
        assert result["thinking_tokens"] == 10  # 0 + 10
        assert result["tool_calls"] == 1
        assert result["assistant_messages"] == 2

    def test_empty_file(self, tmp_path):
        jf = tmp_path / "empty.jsonl"
        jf.write_bytes(b"")
        result = parse_pi_session_jsonl(jf)
        assert result["message_count"] == 0
        assert result["input_tokens"] == 0

    def test_corrupt_line_skipped(self, tmp_path):
        jf = tmp_path / "bad.jsonl"
        jf.write_bytes(b"not json\n")
        result = parse_pi_session_jsonl(jf)
        assert result["message_count"] == 0

    def test_active_time_computation(self, tmp_path):
        jf = tmp_path / "2026-06-02T14-00-00-000Z_sid1.jsonl"
        lines = [
            {
                "type": "session",
                "id": "sid1",
                "timestamp": "2026-06-02T14:00:00Z",
                "cwd": "/tmp",
            },
            {
                "type": "message",
                "timestamp": "2026-06-02T14:00:00Z",
                "message": {"role": "user", "content": "hi"},
            },
            {
                "type": "message",
                "timestamp": "2026-06-02T14:05:00Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "done"}],
                    "usage": {"input": 100, "output": 10},
                },
            },
        ]
        _write_jsonl(jf, lines)
        result = parse_pi_session_jsonl(jf)
        assert result["active_time_ms"] == 300000  # 5 minutes

    def test_fallback_to_filename_timestamp(self, tmp_path):
        jf = tmp_path / "2026-06-02T14-23-12-891Z_noid.jsonl"
        lines = [
            {"type": "message", "message": {"role": "user", "content": "hi"}},
        ]
        _write_jsonl(jf, lines)
        result = parse_pi_session_jsonl(jf)
        assert result["started_at"] == "2026-06-02T14:23:12.891Z"

    def test_pi_costs_ignored(self, tmp_path):
        """Verify that Pi's inline cost=0 does not affect our parsing.

        Pi's models.json declares all costs as 0. The parser should not
        use these values - costs are computed independently via models.dev
        in pricing.py.
        """
        jf = tmp_path / "2026-06-02T14-00-00-000Z_sid1.jsonl"
        lines = [
            {
                "type": "session",
                "id": "sid1",
                "timestamp": "2026-06-02T14:00:00Z",
                "cwd": "/tmp",
            },
            {
                "type": "message",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "hi"}],
                    "usage": {
                        "input": 1000,
                        "output": 100,
                        "cacheRead": 0,
                        "cacheWrite": 0,
                        "cost": {
                            "input": 0,
                            "output": 0,
                            "cacheRead": 0,
                            "cacheWrite": 0,
                            "total": 0,
                        },
                    },
                },
            },
        ]
        _write_jsonl(jf, lines)
        result = parse_pi_session_jsonl(jf)
        # Parser only extracts token counts, not costs
        assert result["input_tokens"] == 1000
        assert result["output_tokens"] == 100
        # No cost fields in the result dict - cost is computed downstream
        assert "input_cost" not in result


class TestIterPiSessions:
    def test_no_sessions_dir(self):
        with patch("tokendroid.pi_parser.PI_SESSIONS_DIR", Path("/nonexistent")):
            assert list(iter_pi_sessions()) == []

    def test_with_pi_sessions(self, tmp_path):
        sessions_dir = tmp_path / "sessions" / "--home-user-project--"
        sessions_dir.mkdir(parents=True)
        jf = sessions_dir / "2026-06-02T14-00-00-000Z_sid1.jsonl"
        lines = [
            {
                "type": "session",
                "id": "sid1",
                "timestamp": "2026-06-02T14:00:00Z",
                "cwd": "/home/user/project",
            },
            {
                "type": "model_change",
                "provider": "neuralwatt",
                "modelId": "zai-org/GLM-5.1-FP8",
            },
            {
                "type": "message",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "hi"}],
                },
            },
            {
                "type": "message",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "hello"}],
                    "usage": {"input": 500, "output": 50},
                },
            },
        ]
        _write_jsonl(jf, lines)

        with (
            patch(
                "tokendroid.pi_parser.PI_SESSIONS_DIR",
                tmp_path / "sessions",
            ),
            patch("tokendroid.pi_parser.PI_MODELS_FILE", Path("/nonexistent")),
        ):
            sessions = list(iter_pi_sessions())

        assert len(sessions) == 1
        s = sessions[0]
        assert s.source == "pi"
        assert s.project == "~/project"
        assert s.model == "zai-org/GLM-5.1-FP8"
        assert s.input_tokens == 500
        assert s.output_tokens == 50
        assert s.is_subagent is False

    def test_display_name_resolved_per_provider(self, tmp_path):
        """Same model id under different providers keeps distinct names."""
        sessions_dir = tmp_path / "sessions" / "--home-user-project--"
        sessions_dir.mkdir(parents=True)

        # A model_change declares the *actual* provider used by the session.
        # The same model id exists under two providers in models.json with
        # different display names; the session must resolve to the one
        # matching its provider.
        def _session(path, sid, provider):
            _write_jsonl(
                path,
                [
                    {
                        "type": "session",
                        "id": sid,
                        "timestamp": "2026-06-02T14:00:00Z",
                        "cwd": "/home/user/project",
                    },
                    {
                        "type": "model_change",
                        "provider": provider,
                        "modelId": "glm-5.2",
                    },
                    {
                        "type": "message",
                        "message": {
                            "role": "assistant",
                            "content": [{"type": "text", "text": "hi"}],
                            "usage": {"input": 100, "output": 10},
                        },
                    },
                ],
            )

        _session(
            sessions_dir / "2026-06-02T14-00-00-000Z_a.jsonl", "a", "neuralwatt-extra"
        )
        _session(sessions_dir / "2026-06-02T15-00-00-000Z_b.jsonl", "b", "zai")

        models_file = tmp_path / "models.json"
        models_file.write_text(
            json.dumps(
                {
                    "providers": {
                        "neuralwatt-extra": {
                            "baseUrl": "https://api.neuralwatt.com/v1",
                            "models": [{"id": "glm-5.2", "name": "GLM-5.2 [NW]"}],
                        },
                        "zai": {
                            "baseUrl": "https://api.z.ai",
                            "models": [{"id": "glm-5.2", "name": "GLM5.2 [Z.AI]"}],
                        },
                    }
                }
            )
        )

        with (
            patch("tokendroid.pi_parser.PI_SESSIONS_DIR", tmp_path / "sessions"),
            patch("tokendroid.pi_parser.PI_MODELS_FILE", models_file),
        ):
            sessions = {s.id: s for s in iter_pi_sessions()}

        assert sessions["a"].model_display == "GLM-5.2 [NW]"
        assert sessions["b"].model_display == "GLM5.2 [Z.AI]"

    def test_nested_subagent_sessions_discovered(self, tmp_path):
        """Nested subagent session.jsonl files are picked up and flagged."""
        project = tmp_path / "sessions" / "--home-user-project--"
        project.mkdir(parents=True)

        # Normal top-level session
        _write_jsonl(
            project / "2026-06-02T14-00-00-000Z_parent.jsonl",
            [
                {
                    "type": "session",
                    "id": "parent",
                    "timestamp": "2026-06-02T14:00:00Z",
                    "cwd": "/home/user/project",
                },
                {
                    "type": "model_change",
                    "provider": "neuralwatt",
                    "modelId": "glm-5.2",
                },
                {
                    "type": "message",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "hi"}],
                        "usage": {"input": 1000, "output": 100},
                    },
                },
            ],
        )

        # Nested subagent session: <uuid>/<hash>/run-N/session.jsonl
        sub = project / "2026-06-02T14-00-00-000Z_parent" / "abc123" / "run-0"
        sub.mkdir(parents=True)
        _write_jsonl(
            sub / "session.jsonl",
            [
                {
                    "type": "session",
                    "id": "sub-run-0",
                    "timestamp": "2026-06-02T14:01:00Z",
                    "cwd": "/home/user/project",
                },
                {
                    "type": "model_change",
                    "provider": "neuralwatt",
                    "modelId": "glm-5.2",
                },
                {
                    "type": "message",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "work"}],
                        "usage": {"input": 5000, "output": 500},
                    },
                },
            ],
        )

        with (
            patch("tokendroid.pi_parser.PI_SESSIONS_DIR", tmp_path / "sessions"),
            patch("tokendroid.pi_parser.PI_MODELS_FILE", Path("/nonexistent")),
        ):
            sessions = {s.id: s for s in iter_pi_sessions()}

        assert set(sessions) == {"parent", "sub-run-0"}
        assert sessions["parent"].is_subagent is False
        assert sessions["sub-run-0"].is_subagent is True
        assert sessions["parent"].input_tokens == 1000
        assert sessions["sub-run-0"].input_tokens == 5000
