"""Tests for the db module."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tokendroid.db import (
    _build_where,
    _escape_like,
    _get_conn,
    get_global_stats,
    get_top_sessions,
    needs_sync,
    sync,
)

# Both source dirs must be patched to avoid reading real data
_PATCH_FACTORY_DIR = patch("tokendroid.parser.SESSIONS_DIR", Path("/nonexistent"))
_PATCH_PI_DIR = patch("tokendroid.pi_parser.PI_SESSIONS_DIR", Path("/nonexistent"))


@pytest.fixture
def db_dir(tmp_path):
    db_path = tmp_path / "tokendroid.db"
    with (
        patch("tokendroid.db.DB_DIR", tmp_path),
        patch("tokendroid.db.DB_PATH", db_path),
    ):
        yield tmp_path


@pytest.fixture
def conn(db_dir):
    c = _get_conn()
    yield c
    c.close()


class TestSchema:
    def test_tables_created(self, conn):
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        tables = {r[0] for r in rows}
        assert "sessions" in tables
        assert "daily_stats" in tables
        assert "sync_state" in tables
        assert "history" in tables


class TestBuildWhere:
    def test_no_filters(self):
        where, params = _build_where()
        assert where == "1=1"
        assert params == []

    def test_project_filter(self):
        where, params = _build_where(project_filter="myproj")
        assert "LIKE" in where
        assert "%myproj%" in params[0]

    def test_model_filter(self):
        where, params = _build_where(model_filter="gpt")
        assert "model LIKE" in where
        assert len(params) == 2

    def test_date_range(self):
        where, params = _build_where(
            date_from="2025-01-01", date_to="2025-01-31"
        )
        assert "started_at >=" in where
        assert "started_at <=" in where
        assert params[-1] == "2025-01-31T23:59:59"


class TestEscapeLike:
    def test_percent(self):
        assert _escape_like("100%") == "100\\%"

    def test_underscore(self):
        assert _escape_like("a_b") == "a\\_b"

    def test_backslash(self):
        assert _escape_like("a\\b") == "a\\\\b"

    def test_clean(self):
        assert _escape_like("hello") == "hello"


class TestNeedsSync:
    def test_empty_dir(self, conn):
        with _PATCH_FACTORY_DIR, _PATCH_PI_DIR:
            assert needs_sync(conn) is False


class TestSync:
    def test_sync_empty(self, db_dir):
        with _PATCH_FACTORY_DIR, _PATCH_PI_DIR:
            count = sync()
        assert count == 0

    def test_sync_with_sessions(self, db_dir, tmp_path):
        sessions_dir = tmp_path / "sessions" / "test-project"
        sessions_dir.mkdir(parents=True)
        sf = sessions_dir / "s1.settings.json"
        sf.write_text(json.dumps({
            "model": "gpt-4",
            "providerLockTimestamp": "2025-01-15T10:00:00",
            "tokenUsage": {"inputTokens": 100, "outputTokens": 50},
        }))
        jf = sessions_dir / "s1.jsonl"
        start = {"type": "session_start", "id": "s1", "title": "Test"}
        jf.write_bytes(json.dumps(start).encode() + b"\n")

        with (
            patch("tokendroid.parser.SESSIONS_DIR", tmp_path / "sessions"),
            patch("tokendroid.parser.SETTINGS_FILE", Path("/nonexistent")),
            _PATCH_PI_DIR,
        ):
            count = sync()

        assert count >= 1


class TestGetGlobalStats:
    def test_empty_db(self, db_dir):
        with _PATCH_FACTORY_DIR, _PATCH_PI_DIR:
            stats = get_global_stats()
        assert stats.total_sessions == 0
        assert stats.total_input_tokens == 0


class TestGetTopSessions:
    def test_empty(self, db_dir):
        with _PATCH_FACTORY_DIR, _PATCH_PI_DIR:
            result = get_top_sessions(5)
        assert result == []
