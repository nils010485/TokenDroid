"""SQLite cache for TokenDroid with incremental sync."""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .models import DailyStat, GlobalStats, ModelSummary, ProjectSummary, SessionData
from .parser import get_all_file_mtimes, iter_all_sessions, parse_history

logger = logging.getLogger(__name__)

DB_DIR = Path.home() / ".local" / "share" / "tokendroid"
DB_PATH = DB_DIR / "tokendroid.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_state (
    factory_path TEXT PRIMARY KEY,
    last_modified REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    project TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    model_display TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'factory',
    is_subagent INTEGER NOT NULL DEFAULT 0,
    interaction_mode TEXT NOT NULL DEFAULT '',
    autonomy_level TEXT NOT NULL DEFAULT '',
    reasoning_effort TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT '',
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    thinking_tokens INTEGER NOT NULL DEFAULT 0,
    cache_tokens INTEGER NOT NULL DEFAULT 0,
    active_time_ms INTEGER NOT NULL DEFAULT 0,
    message_count INTEGER NOT NULL DEFAULT 0,
    user_messages INTEGER NOT NULL DEFAULT 0,
    assistant_messages INTEGER NOT NULL DEFAULT 0,
    tool_calls INTEGER NOT NULL DEFAULT 0,
    input_cost REAL NOT NULL DEFAULT 0.0,
    output_cost REAL NOT NULL DEFAULT 0.0,
    cache_cost REAL NOT NULL DEFAULT 0.0,
    reasoning_cost REAL NOT NULL DEFAULT 0.0,
    total_cost REAL NOT NULL DEFAULT 0.0,
    cache_savings REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS daily_stats (
    date TEXT NOT NULL,
    project TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    sessions INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    thinking_tokens INTEGER NOT NULL DEFAULT 0,
    cache_tokens INTEGER NOT NULL DEFAULT 0,
    active_time_ms INTEGER NOT NULL DEFAULT 0,
    messages INTEGER NOT NULL DEFAULT 0,
    input_cost REAL NOT NULL DEFAULT 0.0,
    output_cost REAL NOT NULL DEFAULT 0.0,
    cache_cost REAL NOT NULL DEFAULT 0.0,
    reasoning_cost REAL NOT NULL DEFAULT 0.0,
    total_cost REAL NOT NULL DEFAULT 0.0,
    cache_savings REAL NOT NULL DEFAULT 0.0,
    PRIMARY KEY (date, project, model)
);

CREATE TABLE IF NOT EXISTS history (
    timestamp TEXT NOT NULL,
    command TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (timestamp, command)
);

CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project);
CREATE INDEX IF NOT EXISTS idx_sessions_model ON sessions(model);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_stats(date);
"""

_COST_COLUMNS = [
    "input_cost",
    "output_cost",
    "cache_cost",
    "reasoning_cost",
    "total_cost",
    "cache_savings",
]

_COST_SELECT = ",\n           ".join(
    f"COALESCE(SUM({c}), 0) as {c}" for c in _COST_COLUMNS
)

_MIGRATIONS: list[tuple[str, list]] = [
    ("sessions", _COST_COLUMNS),
    ("daily_stats", _COST_COLUMNS),
    ("sessions", [("source", "TEXT NOT NULL DEFAULT 'factory'")]),
    ("sessions", [("is_subagent", "INTEGER NOT NULL DEFAULT 0")]),
]

_migrated = False


def _migrate(conn: sqlite3.Connection) -> None:
    """Add cost columns to existing tables that lack them.

    Each migration entry is either a bare column name (added as
    ``REAL NOT NULL DEFAULT 0.0`` for historic cost columns) or a
    ``(name, definition)`` tuple where ``definition`` is the full SQL type +
    constraint to use in the ``ALTER TABLE ... ADD COLUMN``.
    """
    global _migrated
    if _migrated:
        return
    for table, columns in _MIGRATIONS:
        existing = {
            r[1]
            for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for col in columns:
            if isinstance(col, tuple):
                name, definition = col
            else:
                name, definition = col, "REAL NOT NULL DEFAULT 0.0"
            if name not in existing:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
                )
    _migrated = True


def _get_conn() -> sqlite3.Connection:
    """Create a SQLite connection with WAL mode and ensure schema is up to date."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    _migrate(conn)
    return conn


def needs_sync(conn: sqlite3.Connection) -> bool:
    """Check if any source files (Factory or Pi) changed since last sync."""
    current = get_all_file_mtimes()
    if not current:
        return False
    rows = conn.execute("SELECT factory_path, last_modified FROM sync_state").fetchall()
    stored = {row["factory_path"]: row["last_modified"] for row in rows}

    for path, mtime in current.items():
        if stored.get(path, 0) < mtime:
            return True
    return any(path not in current for path in stored)


def sync(full: bool = False) -> int:
    """Sync factory data into SQLite. Returns number of sessions synced."""
    conn = _get_conn()
    try:
        if full:
            conn.execute("DELETE FROM sessions")
            conn.execute("DELETE FROM daily_stats")
            conn.execute("DELETE FROM sync_state")
            conn.execute("DELETE FROM history")

        sessions = list(iter_all_sessions())
        _upsert_sessions(conn, sessions)
        _rebuild_daily(conn)
        _sync_history(conn)
        _update_sync_state(conn)
        conn.commit()
        return len(sessions)
    finally:
        conn.close()


def _upsert_sessions(conn: sqlite3.Connection, sessions: list[SessionData]) -> None:
    """Insert or update session records in the database."""
    from .pricing import compute_cost, match_model_price

    price_cache: dict[str, Any] = {}
    rows = []
    for s in sessions:
        price = price_cache.get(s.model)
        if price is None:
            price = match_model_price(s.model_display, s.model)
            price_cache[s.model] = price
        cost = compute_cost(
            s.input_tokens, s.output_tokens, s.cache_tokens, s.thinking_tokens, price
        )
        rows.append(
            (
                s.id,
                s.project,
                s.title,
                s.model,
                s.model_display,
                s.provider,
                s.source,
                int(s.is_subagent),
                s.interaction_mode,
                s.autonomy_level,
                s.reasoning_effort,
                s.started_at,
                s.input_tokens,
                s.output_tokens,
                s.thinking_tokens,
                s.cache_tokens,
                s.active_time_ms,
                s.message_count,
                s.user_messages,
                s.assistant_messages,
                s.tool_calls,
                cost["input_cost"],
                cost["output_cost"],
                cost["cache_cost"],
                cost["reasoning_cost"],
                cost["total_cost"],
                cost["cache_savings"],
            )
        )
    conn.executemany(
        """INSERT OR REPLACE INTO sessions
        (id, project, title, model, model_display, provider, source,
         is_subagent,
         interaction_mode, autonomy_level, reasoning_effort, started_at,
         input_tokens, output_tokens, thinking_tokens, cache_tokens,
         active_time_ms, message_count, user_messages, assistant_messages, tool_calls,
         input_cost, output_cost, cache_cost, reasoning_cost, total_cost, cache_savings)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )


def _rebuild_daily(conn: sqlite3.Connection) -> None:
    """Rebuild the daily_stats table from sessions."""
    conn.execute("DELETE FROM daily_stats")
    conn.execute(
        """INSERT INTO daily_stats (date, project, model, sessions,
           input_tokens, output_tokens, thinking_tokens, cache_tokens,
           active_time_ms, messages,
           input_cost, output_cost, cache_cost, reasoning_cost, total_cost, cache_savings)
        SELECT
            DATE(started_at) as date,
            project,
            model,
            COUNT(*) as sessions,
            SUM(input_tokens),
            SUM(output_tokens),
            SUM(thinking_tokens),
            SUM(cache_tokens),
            SUM(active_time_ms),
            SUM(message_count),
            SUM(input_cost),
            SUM(output_cost),
            SUM(cache_cost),
            SUM(reasoning_cost),
            SUM(total_cost),
            SUM(cache_savings)
        FROM sessions
        WHERE started_at != ''
        GROUP BY date, project, model"""
    )


def _sync_history(conn: sqlite3.Connection) -> None:
    """Parse and persist shell history entries."""
    entries = parse_history()
    if not entries:
        return
    conn.execute("DELETE FROM history")
    conn.executemany(
        "INSERT OR IGNORE INTO history (timestamp, command, type, mode) VALUES (?, ?, ?, ?)",
        [(e.timestamp, e.command[:500], e.entry_type, e.mode) for e in entries],
    )


def _update_sync_state(conn: sqlite3.Connection) -> None:
    """Record current file mtimes as the sync checkpoint."""
    mtimes = get_all_file_mtimes()
    conn.executemany(
        "INSERT OR REPLACE INTO sync_state (factory_path, last_modified) VALUES (?, ?)",
        list(mtimes.items()),
    )


def _ensure_synced() -> sqlite3.Connection:
    """Get a connection, auto-syncing if needed."""
    conn = _get_conn()
    if needs_sync(conn):
        try:
            sync()
            conn.close()
            conn = _get_conn()
        except Exception:
            logger.exception("Auto-sync failed")
    return conn


def get_global_stats(
    project_filter: str | None = None,
    model_filter: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> GlobalStats:
    """Compute global aggregated statistics with optional filters."""
    conn = _ensure_synced()
    try:
        where, params = _build_where(project_filter, model_filter, date_from, date_to)

        row = conn.execute(
            f"""SELECT
                COUNT(*) as total_sessions,
                COALESCE(SUM(input_tokens), 0) as total_input,
                COALESCE(SUM(output_tokens), 0) as total_output,
                COALESCE(SUM(thinking_tokens), 0) as total_thinking,
                COALESCE(SUM(cache_tokens), 0) as total_cache,
                COALESCE(SUM(active_time_ms), 0) as total_active,
                COALESCE(SUM(message_count), 0) as total_messages
            FROM sessions WHERE {where}""",
            params,
        ).fetchone()

        date_range = conn.execute(
            f"SELECT MIN(started_at), MAX(started_at) FROM sessions WHERE {where}",
            params,
        ).fetchone()

        by_model = _get_model_summaries(conn, where, params)
        by_project = _get_project_summaries(conn, where, params)
        by_day = _get_daily_stats(conn, where, params)

        return GlobalStats(
            total_sessions=row["total_sessions"],
            total_input_tokens=row["total_input"],
            total_output_tokens=row["total_output"],
            total_thinking_tokens=row["total_thinking"],
            total_cache_tokens=row["total_cache"],
            total_active_time_ms=row["total_active"],
            total_messages=row["total_messages"],
            total_projects=len({p.name for p in by_project}),
            total_models=len(by_model),
            date_range_start=date_range[0] or "",
            date_range_end=date_range[1] or "",
            by_model=by_model,
            by_project=by_project,
            by_day=by_day,
        )
    finally:
        conn.close()


def _escape_like(value: str) -> str:
    """Escape SQL LIKE wildcards in a value."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _build_where(
    project_filter: str | None = None,
    model_filter: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> tuple[str, list[Any]]:
    """Build a SQL WHERE clause from optional filter arguments.

    Returns:
        A tuple of (where_clause, params_list).
    """
    clauses: list[str] = ["1=1"]
    params: list[Any] = []
    if project_filter:
        clauses.append("project LIKE ? ESCAPE '\\'")
        params.append(f"%{_escape_like(project_filter)}%")
    if model_filter:
        clauses.append("(model LIKE ? ESCAPE '\\' OR model_display LIKE ? ESCAPE '\\')")
        params.extend([f"%{_escape_like(model_filter)}%", f"%{_escape_like(model_filter)}%"])
    if date_from:
        clauses.append("started_at >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("started_at <= ?")
        params.append(date_to + "T23:59:59")
    return " AND ".join(clauses), params


def _get_model_summaries(
    conn: sqlite3.Connection, where: str, params: list[Any]
) -> list[ModelSummary]:
    """Aggregate session stats grouped by model."""
    rows = conn.execute(
        f"""SELECT
            model, model_display,
            COUNT(*) as sessions,
            SUM(input_tokens) as input_tokens,
            SUM(output_tokens) as output_tokens,
            SUM(thinking_tokens) as thinking_tokens,
            SUM(cache_tokens) as cache_tokens,
            SUM(active_time_ms) as active_time_ms,
            SUM(message_count) as messages,
            COUNT(DISTINCT project) as projects
        FROM sessions WHERE {where}
        GROUP BY model, model_display
        ORDER BY sessions DESC""",
        params,
    ).fetchall()
    return [
        ModelSummary(
            model_id=r["model"],
            display_name=r["model_display"],
            sessions=r["sessions"],
            input_tokens=r["input_tokens"] or 0,
            output_tokens=r["output_tokens"] or 0,
            thinking_tokens=r["thinking_tokens"] or 0,
            cache_tokens=r["cache_tokens"] or 0,
            active_time_ms=r["active_time_ms"] or 0,
            messages=r["messages"] or 0,
            projects=r["projects"],
        )
        for r in rows
    ]


def _get_project_summaries(
    conn: sqlite3.Connection, where: str, params: list[Any]
) -> list[ProjectSummary]:
    """Aggregate session stats grouped by project."""
    rows = conn.execute(
        f"""SELECT
            project,
            COUNT(*) as sessions,
            SUM(input_tokens) as input_tokens,
            SUM(output_tokens) as output_tokens,
            SUM(thinking_tokens) as thinking_tokens,
            SUM(cache_tokens) as cache_tokens,
            SUM(active_time_ms) as active_time_ms,
            SUM(message_count) as messages
        FROM sessions WHERE {where}
        GROUP BY project
        ORDER BY sessions DESC""",
        params,
    ).fetchall()
    results: list[ProjectSummary] = []
    for r in rows:
        top_models = conn.execute(
            f"""SELECT model_display FROM sessions
            WHERE project = ? AND {where}
            GROUP BY model_display ORDER BY COUNT(*) DESC LIMIT 3""",
            [r["project"], *params],
        ).fetchall()
        results.append(
            ProjectSummary(
                name=r["project"],
                sessions=r["sessions"],
                input_tokens=r["input_tokens"] or 0,
                output_tokens=r["output_tokens"] or 0,
                thinking_tokens=r["thinking_tokens"] or 0,
                cache_tokens=r["cache_tokens"] or 0,
                active_time_ms=r["active_time_ms"] or 0,
                messages=r["messages"] or 0,
                top_models=[m["model_display"] for m in top_models],
            )
        )
    return results


def _get_daily_stats(conn: sqlite3.Connection, where: str, params: list[Any]) -> list[DailyStat]:
    """Aggregate session stats grouped by date."""
    rows = conn.execute(
        f"""SELECT
            DATE(started_at) as date,
            COUNT(*) as sessions,
            SUM(input_tokens) as input_tokens,
            SUM(output_tokens) as output_tokens,
            SUM(thinking_tokens) as thinking_tokens,
            SUM(cache_tokens) as cache_tokens,
            SUM(active_time_ms) as active_time_ms,
            SUM(message_count) as messages
        FROM sessions WHERE {where} AND started_at != ''
        GROUP BY date ORDER BY date""",
        params,
    ).fetchall()
    return [
        DailyStat(
            date=r["date"] or "",
            sessions=r["sessions"],
            input_tokens=r["input_tokens"] or 0,
            output_tokens=r["output_tokens"] or 0,
            thinking_tokens=r["thinking_tokens"] or 0,
            cache_tokens=r["cache_tokens"] or 0,
            active_time_ms=r["active_time_ms"] or 0,
            messages=r["messages"] or 0,
        )
        for r in rows
    ]


_ALLOWED_ORDER = {
    "started_at DESC",
    "started_at ASC",
    "input_tokens DESC",
    "input_tokens ASC",
    "output_tokens DESC",
    "output_tokens ASC",
    "message_count DESC",
    "message_count ASC",
    "project DESC",
    "project ASC",
    "model DESC",
    "model ASC",
}


def get_sessions(
    project_filter: str | None = None,
    model_filter: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
    order_by: str = "started_at DESC",
) -> list[dict[str, Any]]:
    """Get raw session rows for table display."""
    safe_order = order_by if order_by in _ALLOWED_ORDER else "started_at DESC"
    conn = _ensure_synced()
    try:
        where, params = _build_where(project_filter, model_filter, date_from, date_to)
        rows = conn.execute(
            f"""SELECT * FROM sessions WHERE {where}
            ORDER BY {safe_order} LIMIT ? OFFSET ?""",
            [*params, limit, offset],
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_weekly_stats(
    project_filter: str | None = None,
    model_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Get aggregated weekly stats."""
    conn = _ensure_synced()
    try:
        where, params = _build_where(project_filter, model_filter)
        rows = conn.execute(
            f"""SELECT
                strftime('%Y-W%W', started_at) as week,
                COUNT(*) as sessions,
                SUM(input_tokens) as input_tokens,
                SUM(output_tokens) as output_tokens,
                SUM(thinking_tokens) as thinking_tokens,
                SUM(cache_tokens) as cache_tokens,
                SUM(active_time_ms) as active_time_ms,
                SUM(message_count) as messages
            FROM sessions WHERE {where} AND started_at != ''
            GROUP BY week ORDER BY week""",
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_model_daily(
    model_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Get daily stats broken down by model for charts."""
    conn = _ensure_synced()
    try:
        where, params = _build_where(model_filter=model_filter)
        rows = conn.execute(
            f"""SELECT
                DATE(started_at) as date,
                model_display,
                COUNT(*) as sessions,
                SUM(output_tokens) as output_tokens,
                SUM(input_tokens) as input_tokens
            FROM sessions WHERE {where}
            GROUP BY date, model_display
            ORDER BY date""",
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_hourly_distribution() -> list[dict[str, Any]]:
    """Get session count by hour of day (heatmap data)."""
    conn = _ensure_synced()
    try:
        rows = conn.execute(
            """SELECT
                CAST(strftime('%H', started_at) AS INTEGER) as hour,
                COUNT(*) as sessions
            FROM sessions WHERE started_at != ''
            GROUP BY hour ORDER BY hour"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_dow_distribution() -> list[dict[str, Any]]:
    """Get session count by day of week."""
    conn = _ensure_synced()
    try:
        rows = conn.execute(
            """SELECT
                CAST(strftime('%w', started_at) AS INTEGER) as dow,
                COUNT(*) as sessions,
                SUM(output_tokens) as output_tokens
            FROM sessions WHERE started_at != ''
            GROUP BY dow ORDER BY dow"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_top_sessions(n: int = 10) -> list[dict[str, Any]]:
    """Get top N sessions by total tokens (input + output + cache)."""
    conn = _ensure_synced()
    try:
        rows = conn.execute(
            """SELECT *,
                (input_tokens + output_tokens + cache_tokens) as total_tokens
            FROM sessions ORDER BY total_tokens DESC LIMIT ?""",
            [n],
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_monthly_stats(
    project_filter: str | None = None,
    model_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Get aggregated monthly stats."""
    conn = _ensure_synced()
    try:
        where, params = _build_where(project_filter, model_filter)
        rows = conn.execute(
            f"""SELECT
                strftime('%Y-%m', started_at) as month,
                COUNT(*) as sessions,
                SUM(input_tokens) as input_tokens,
                SUM(output_tokens) as output_tokens,
                SUM(thinking_tokens) as thinking_tokens,
                SUM(cache_tokens) as cache_tokens,
                SUM(active_time_ms) as active_time_ms,
                SUM(message_count) as messages
            FROM sessions WHERE {where} AND started_at != ''
            GROUP BY month ORDER BY month""",
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _cost_dict(row: sqlite3.Row, **extra: Any) -> dict[str, Any]:
    """Extract the standard cost columns from a query row into a dict."""
    d = {c: row[c] for c in _COST_COLUMNS}
    d.update(extra)
    return d


def _query_cost_by_period(
    conn: sqlite3.Connection,
    where: str,
    params: list[Any],
    period_fmt: str,
    period_key: str,
) -> list[dict[str, Any]]:
    """Query cost aggregated by a time period (day/week/month)."""
    rows = conn.execute(
        f"""SELECT strftime('{period_fmt}', started_at) as {period_key},
            {_COST_SELECT}
        FROM sessions WHERE {where} AND started_at != ''
        GROUP BY {period_key} ORDER BY {period_key}""",
        params,
    ).fetchall()
    return [_cost_dict(r, **{period_key: r[period_key]}) for r in rows]


def _query_cost_by_period_and_model(
    conn: sqlite3.Connection,
    where: str,
    params: list[Any],
    period_fmt: str,
    period_key: str,
) -> dict[str, list[dict[str, Any]]]:
    """Query cost by period and model_display, returning a model -> entries map."""
    rows = conn.execute(
        f"""SELECT strftime('{period_fmt}', started_at) as {period_key}, model_display,
            {_COST_SELECT}
        FROM sessions WHERE {where} AND started_at != ''
        GROUP BY {period_key}, model_display ORDER BY {period_key}""",
        params,
    ).fetchall()
    result: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        result.setdefault(r["model_display"], []).append(
            _cost_dict(r, **{period_key: r[period_key]})
        )
    return result


def get_cost_summary(
    project_filter: str | None = None,
    model_filter: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Compute cost breakdown from pre-stored cost columns in SQLite.

    Returns a dict with total costs, by_model, by_project, daily, weekly,
    monthly breakdowns, cache_savings, forecast, and avg cost metrics.
    Models without a price match get cost of 0.
    """
    from .pricing import match_model_price

    conn = _ensure_synced()
    try:
        where, params = _build_where(project_filter, model_filter, date_from, date_to)

        # Total
        row = conn.execute(
            f"""SELECT {_COST_SELECT},
                COUNT(*) as total_sessions,
                COALESCE(SUM(message_count), 0) as total_messages,
                SUM(CASE WHEN total_cost > 0 THEN 1 ELSE 0 END) as sessions_priced,
                SUM(CASE WHEN total_cost > 0 THEN message_count ELSE 0 END) as messages_priced
            FROM sessions WHERE {where}""",
            params,
        ).fetchone()
        total = _cost_dict(row)
        total_avg = {
            "avg_cost_per_session": (
                row["total_cost"] / row["sessions_priced"] if row["sessions_priced"] else 0.0
            ),
            "avg_cost_per_message": (
                row["total_cost"] / row["messages_priced"] if row["messages_priced"] else 0.0
            ),
        }

        # By model
        model_rows = conn.execute(
            f"""SELECT model, model_display,
                COUNT(*) as sessions,
                SUM(message_count) as messages,
                {_COST_SELECT}
            FROM sessions WHERE {where}
            GROUP BY model, model_display
            ORDER BY sessions DESC""",
            params,
        ).fetchall()
        by_model = []
        for r in model_rows:
            avg_sess = r["total_cost"] / r["sessions"] if r["sessions"] else 0.0
            avg_msg = r["total_cost"] / r["messages"] if r["messages"] else 0.0
            price = match_model_price(r["model_display"], r["model"])
            by_model.append(
                _cost_dict(
                    r,
                    name=r["model_display"],
                    model_id=r["model"],
                    matched=price is not None,
                    sessions=r["sessions"],
                    messages=r["messages"],
                    avg_cost_per_session=avg_sess,
                    avg_cost_per_message=avg_msg,
                )
            )

        # By project
        project_rows = conn.execute(
            f"""SELECT project,
                {_COST_SELECT}
            FROM sessions WHERE {where}
            GROUP BY project
            ORDER BY total_cost DESC""",
            params,
        ).fetchall()
        by_project = [_cost_dict(r, name=r["project"]) for r in project_rows]

        # Daily / Weekly / Monthly
        daily = _query_cost_by_period(conn, where, params, "%Y-%m-%d", "date")
        weekly = _query_cost_by_period(conn, where, params, "%Y-W%W", "week")
        monthly = _query_cost_by_period(conn, where, params, "%Y-%m", "month")

        daily_by_model = _query_cost_by_period_and_model(conn, where, params, "%Y-%m-%d", "date")
        weekly_by_model = _query_cost_by_period_and_model(conn, where, params, "%Y-W%W", "week")
        monthly_by_model = _query_cost_by_period_and_model(conn, where, params, "%Y-%m", "month")

        # Hourly / Day-of-week cost
        hourly_cost = _get_hourly_cost_distribution(conn)
        dow_cost = _get_dow_cost_distribution(conn)

        forecast = _compute_forecast(daily)

        return {
            "total": total,
            "total_avg": total_avg,
            "forecast": forecast,
            "by_model": by_model,
            "by_project": by_project,
            "daily": daily,
            "daily_by_model": daily_by_model,
            "weekly": weekly,
            "weekly_by_model": weekly_by_model,
            "monthly": monthly,
            "monthly_by_model": monthly_by_model,
            "hourly_cost": hourly_cost,
            "dow_cost": dow_cost,
        }
    finally:
        conn.close()


def _compute_forecast(daily: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute 30-day linear forecast and trend from daily cost data."""
    if not daily or len(daily) < 2:
        return {
            "projected_cost_30d": 0.0,
            "daily_avg_30d": 0.0,
            "trend_pct": 0.0,
            "trend_direction": "flat",
        }

    today = date.today()
    cutoff_30 = today - timedelta(days=30)
    cutoff_14 = today - timedelta(days=14)
    cutoff_7 = today - timedelta(days=7)

    last_30 = [d for d in daily if date.fromisoformat(d["date"]) >= cutoff_30]
    if not last_30:
        return {
            "projected_cost_30d": 0.0,
            "daily_avg_30d": 0.0,
            "trend_pct": 0.0,
            "trend_direction": "flat",
        }

    sum_30 = sum(d["total_cost"] for d in last_30)
    first_dt = date.fromisoformat(last_30[0]["date"])
    last_dt = date.fromisoformat(last_30[-1]["date"])
    days_covered = max((last_dt - first_dt).days + 1, 1)
    daily_avg = sum_30 / days_covered
    projected_30d = daily_avg * 30

    last_7 = [d for d in daily if date.fromisoformat(d["date"]) >= cutoff_7]
    prev_7 = [d for d in daily if cutoff_14 <= date.fromisoformat(d["date"]) < cutoff_7]

    avg_last7 = sum(d["total_cost"] for d in last_7) / max(len(last_7), 1)
    avg_prev7 = sum(d["total_cost"] for d in prev_7) / max(len(prev_7), 1)

    trend_pct = (avg_last7 - avg_prev7) / avg_prev7 * 100 if avg_prev7 > 0 else 0.0

    if trend_pct > 5:
        trend_direction = "up"
    elif trend_pct < -5:
        trend_direction = "down"
    else:
        trend_direction = "flat"

    return {
        "projected_cost_30d": round(projected_30d, 4),
        "daily_avg_30d": round(daily_avg, 4),
        "trend_pct": round(trend_pct, 1),
        "trend_direction": trend_direction,
    }


def _get_hourly_cost_distribution(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Get cost by hour of day for heatmap toggle."""
    rows = conn.execute(
        f"""SELECT CAST(strftime('%H', started_at) AS INTEGER) as hour,
            {_COST_SELECT}
        FROM sessions WHERE started_at != ''
        GROUP BY hour ORDER BY hour"""
    ).fetchall()
    hourly = {r["hour"]: r["total_cost"] for r in rows}
    return [{"hour": h, "cost": round(hourly.get(h, 0.0), 4)} for h in range(24)]


def _get_dow_cost_distribution(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Get cost by day of week for heatmap toggle."""
    rows = conn.execute(
        f"""SELECT CAST(strftime('%w', started_at) AS INTEGER) as dow,
            {_COST_SELECT}
        FROM sessions WHERE started_at != ''
        GROUP BY dow ORDER BY dow"""
    ).fetchall()
    dow_map = {r["dow"]: r["total_cost"] for r in rows}
    return [{"dow": d, "cost": round(dow_map.get(d, 0.0), 4)} for d in range(7)]
