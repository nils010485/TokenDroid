"""SQLite cache for TokenDroid with incremental sync."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from .models import DailyStat, GlobalStats, ModelSummary, ProjectSummary, SessionData
from .parser import get_file_mtimes, iter_sessions, parse_history

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
    tool_calls INTEGER NOT NULL DEFAULT 0
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


def _get_conn() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def needs_sync(conn: sqlite3.Connection) -> bool:
    """Check if any factory files changed since last sync."""
    current = get_file_mtimes()
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

        sessions = list(iter_sessions())
        _upsert_sessions(conn, sessions)
        _rebuild_daily(conn)
        _sync_history(conn)
        _update_sync_state(conn)
        conn.commit()
        return len(sessions)
    finally:
        conn.close()


def _upsert_sessions(conn: sqlite3.Connection, sessions: list[SessionData]) -> None:
    conn.executemany(
        """INSERT OR REPLACE INTO sessions
        (id, project, title, model, model_display, provider,
         interaction_mode, autonomy_level, reasoning_effort, started_at,
         input_tokens, output_tokens, thinking_tokens, cache_tokens,
         active_time_ms, message_count, user_messages, assistant_messages, tool_calls)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                s.id,
                s.project,
                s.title,
                s.model,
                s.model_display,
                s.provider,
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
            )
            for s in sessions
        ],
    )


def _rebuild_daily(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM daily_stats")
    conn.execute(
        """INSERT INTO daily_stats (date, project, model, sessions,
           input_tokens, output_tokens, thinking_tokens, cache_tokens,
           active_time_ms, messages)
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
            SUM(message_count)
        FROM sessions
        WHERE started_at != ''
        GROUP BY date, project, model"""
    )


def _sync_history(conn: sqlite3.Connection) -> None:
    entries = parse_history()
    if not entries:
        return
    conn.execute("DELETE FROM history")
    conn.executemany(
        "INSERT OR IGNORE INTO history (timestamp, command, type, mode) VALUES (?, ?, ?, ?)",
        [(e.timestamp, e.command[:500], e.entry_type, e.mode) for e in entries],
    )


def _update_sync_state(conn: sqlite3.Connection) -> None:
    mtimes = get_file_mtimes()
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
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _build_where(
    project_filter: str | None = None,
    model_filter: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> tuple[str, list[Any]]:
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


def get_cost_summary(
    project_filter: str | None = None,
    model_filter: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Compute cost breakdown using models.dev pricing data.

    Returns a dict with total costs, by_model, by_project, daily, weekly,
    and monthly breakdowns. Models without a price match get cost of 0.
    """
    from .pricing import compute_cost, match_model_price

    def _zero_cost() -> dict[str, float]:
        return {
            "input_cost": 0.0,
            "output_cost": 0.0,
            "cache_cost": 0.0,
            "reasoning_cost": 0.0,
            "total_cost": 0.0,
        }

    def _add_cost(target: dict[str, float], delta: dict[str, float]) -> None:
        for k in target:
            target[k] += delta.get(k, 0)

    stats = get_global_stats(
        project_filter=project_filter,
        model_filter=model_filter,
        date_from=date_from,
        date_to=date_to,
    )

    model_prices: dict[str, Any] = {}
    model_names: dict[str, str] = {}
    for m in stats.by_model:
        model_prices[m.model_id] = match_model_price(m.display_name, m.model_id)
        model_names[m.model_id] = m.display_name

    total: dict[str, float] = _zero_cost()

    by_model = []
    for m in stats.by_model:
        price = model_prices.get(m.model_id)
        cost = compute_cost(
            m.input_tokens,
            m.output_tokens,
            m.cache_tokens,
            m.thinking_tokens,
            price,
        )
        by_model.append(
            {
                "name": m.display_name,
                "model_id": m.model_id,
                "matched": price is not None,
                **cost,
            }
        )
        _add_cost(total, cost)

    by_project = []
    for p in stats.by_project:
        pcost = _zero_cost()
        conn = _ensure_synced()
        try:
            rows = conn.execute(
                """SELECT model,
                    COALESCE(SUM(input_tokens), 0) as input_tokens,
                    COALESCE(SUM(output_tokens), 0) as output_tokens,
                    COALESCE(SUM(thinking_tokens), 0) as thinking_tokens,
                    COALESCE(SUM(cache_tokens), 0) as cache_tokens
                FROM sessions WHERE project = ?
                GROUP BY model""",
                [p.name],
            ).fetchall()
            for r in rows:
                price = model_prices.get(r["model"])
                if price is None:
                    continue
                c = compute_cost(
                    r["input_tokens"],
                    r["output_tokens"],
                    r["cache_tokens"],
                    r["thinking_tokens"],
                    price,
                )
                _add_cost(pcost, c)
        finally:
            conn.close()
        by_project.append({"name": p.name, **pcost})

    daily_by_model: dict[str, list[dict[str, Any]]] = {}
    daily = []
    conn = _ensure_synced()
    try:
        for d in stats.by_day:
            dcost = _zero_cost()
            rows = conn.execute(
                """SELECT model,
                    COALESCE(SUM(input_tokens), 0) as input_tokens,
                    COALESCE(SUM(output_tokens), 0) as output_tokens,
                    COALESCE(SUM(thinking_tokens), 0) as thinking_tokens,
                    COALESCE(SUM(cache_tokens), 0) as cache_tokens
                FROM sessions WHERE DATE(started_at) = ?
                GROUP BY model""",
                [d.date],
            ).fetchall()
            for r in rows:
                price = model_prices.get(r["model"])
                if price is None:
                    continue
                c = compute_cost(
                    r["input_tokens"],
                    r["output_tokens"],
                    r["cache_tokens"],
                    r["thinking_tokens"],
                    price,
                )
                _add_cost(dcost, c)
                mname = next(
                    (m.display_name for m in stats.by_model if m.model_id == r["model"]),
                    r["model"],
                )
                daily_by_model.setdefault(mname, []).append({"date": d.date, **c})
            daily.append({"date": d.date, **dcost})
    finally:
        conn.close()

    weekly, weekly_by_model = _compute_period_costs_weekly(
        model_prices,
        model_names,
        project_filter=project_filter,
        model_filter=model_filter,
        date_from=date_from,
        date_to=date_to,
    )
    monthly, monthly_by_model = _compute_period_costs_monthly(
        model_prices,
        model_names,
        project_filter=project_filter,
        model_filter=model_filter,
        date_from=date_from,
        date_to=date_to,
    )

    return {
        "total": total,
        "by_model": by_model,
        "by_project": by_project,
        "daily": daily,
        "daily_by_model": daily_by_model,
        "weekly": weekly,
        "weekly_by_model": weekly_by_model,
        "monthly": monthly,
        "monthly_by_model": monthly_by_model,
    }


def _compute_period_costs_weekly(
    model_prices: dict[str, Any],
    model_names: dict[str, str],
    project_filter: str | None = None,
    model_filter: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """Compute weekly cost breakdown."""
    from .pricing import compute_cost

    def _zero() -> dict[str, float]:
        return {
            "input_cost": 0.0,
            "output_cost": 0.0,
            "cache_cost": 0.0,
            "reasoning_cost": 0.0,
            "total_cost": 0.0,
        }

    def _add(target: dict[str, float], delta: dict[str, float]) -> None:
        for k in target:
            target[k] += delta.get(k, 0)

    weekly_rows = get_weekly_stats(
        project_filter=project_filter,
        model_filter=model_filter,
    )
    conn = _ensure_synced()
    result = []
    by_model: dict[str, list[dict[str, Any]]] = {}
    try:
        for w in weekly_rows:
            wcost = _zero()
            where, params = _build_where(
                project_filter,
                model_filter,
                date_from,
                date_to,
            )
            params.append(w.get("week", ""))
            rows = conn.execute(
                f"""SELECT model,
                    COALESCE(SUM(input_tokens), 0) as input_tokens,
                    COALESCE(SUM(output_tokens), 0) as output_tokens,
                    COALESCE(SUM(thinking_tokens), 0) as thinking_tokens,
                    COALESCE(SUM(cache_tokens), 0) as cache_tokens
                FROM sessions WHERE {where}
                AND strftime('%Y-W%W', started_at) = ?
                GROUP BY model""",
                params,
            ).fetchall()
            for r in rows:
                price = model_prices.get(r["model"])
                if price is None:
                    continue
                c = compute_cost(
                    r["input_tokens"],
                    r["output_tokens"],
                    r["cache_tokens"],
                    r["thinking_tokens"],
                    price,
                )
                _add(wcost, c)
                mname = model_names.get(r["model"], r["model"])
                by_model.setdefault(mname, []).append({"week": w.get("week", ""), **c})
            result.append({"week": w.get("week", ""), **wcost})
    finally:
        conn.close()
    return result, by_model


def _compute_period_costs_monthly(
    model_prices: dict[str, Any],
    model_names: dict[str, str],
    project_filter: str | None = None,
    model_filter: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """Compute monthly cost breakdown."""
    from .pricing import compute_cost

    def _zero() -> dict[str, float]:
        return {
            "input_cost": 0.0,
            "output_cost": 0.0,
            "cache_cost": 0.0,
            "reasoning_cost": 0.0,
            "total_cost": 0.0,
        }

    def _add(target: dict[str, float], delta: dict[str, float]) -> None:
        for k in target:
            target[k] += delta.get(k, 0)

    monthly_rows = get_monthly_stats(
        project_filter=project_filter,
        model_filter=model_filter,
    )
    conn = _ensure_synced()
    result = []
    by_model: dict[str, list[dict[str, Any]]] = {}
    try:
        for mo in monthly_rows:
            mcost = _zero()
            where, params = _build_where(
                project_filter,
                model_filter,
                date_from,
                date_to,
            )
            params.append(mo.get("month", ""))
            rows = conn.execute(
                f"""SELECT model,
                    COALESCE(SUM(input_tokens), 0) as input_tokens,
                    COALESCE(SUM(output_tokens), 0) as output_tokens,
                    COALESCE(SUM(thinking_tokens), 0) as thinking_tokens,
                    COALESCE(SUM(cache_tokens), 0) as cache_tokens
                FROM sessions WHERE {where}
                AND strftime('%Y-%m', started_at) = ?
                GROUP BY model""",
                params,
            ).fetchall()
            for r in rows:
                price = model_prices.get(r["model"])
                if price is None:
                    continue
                c = compute_cost(
                    r["input_tokens"],
                    r["output_tokens"],
                    r["cache_tokens"],
                    r["thinking_tokens"],
                    price,
                )
                _add(mcost, c)
                mname = model_names.get(r["model"], r["model"])
                by_model.setdefault(mname, []).append({"month": mo.get("month", ""), **c})
            result.append({"month": mo.get("month", ""), **mcost})
    finally:
        conn.close()
    return result, by_model
