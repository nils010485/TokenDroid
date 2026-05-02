"""FastAPI web dashboard for TokenDroid (`tokendroid web`)."""

from __future__ import annotations

import socket
import threading
import time
import webbrowser
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from ..db import (
    get_dow_distribution,
    get_global_stats,
    get_hourly_distribution,
    get_monthly_stats,
    get_top_sessions,
    get_weekly_stats,
    sync,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"

app = FastAPI(title="TokenDroid", docs_url=None, redoc_url=None)


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html = (TEMPLATES_DIR / "dashboard.html").read_text()
    return HTMLResponse(html)


@app.get("/api/dashboard")
async def api_dashboard():
    """Single payload for the web dashboard."""
    stats = get_global_stats()
    top_sessions = get_top_sessions(30)
    hourly = get_hourly_distribution()
    dow = get_dow_distribution()
    monthly = get_monthly_stats()
    weekly = get_weekly_stats()

    return JSONResponse(
        {
            "daily": [
                {
                    "date": d.date,
                    "sessions": d.sessions,
                    "input": d.input_tokens,
                    "output": d.output_tokens,
                    "cache": d.cache_tokens,
                    "active_h": round(d.active_time_ms / 3600000, 2),
                    "messages": d.messages,
                }
                for d in stats.by_day
            ],
            "models": [
                {
                    "name": m.display_name,
                    "sessions": m.sessions,
                    "input": m.input_tokens,
                    "output": m.output_tokens,
                    "cache": m.cache_tokens,
                    "active_h": round(m.active_time_ms / 3600000, 2),
                    "projects": m.projects,
                }
                for m in stats.by_model
            ],
            "projects": [
                {
                    "name": p.name,
                    "sessions": p.sessions,
                    "input": p.input_tokens,
                    "cache": p.cache_tokens,
                    "output": p.output_tokens,
                    "active_h": round(p.active_time_ms / 3600000, 2),
                    "top_models": p.top_models,
                }
                for p in stats.by_project
            ],
            "hourly": hourly,
            "dow": dow,
            "monthly": [
                {
                    "month": m.get("month", ""),
                    "sessions": m.get("sessions", 0),
                    "input": m.get("input_tokens", 0) or 0,
                    "output": m.get("output_tokens", 0) or 0,
                    "cache": m.get("cache_tokens", 0) or 0,
                    "active_h": round((m.get("active_time_ms", 0) or 0) / 3600000, 2),
                    "messages": m.get("messages", 0) or 0,
                }
                for m in monthly
            ],
            "weekly": [
                {
                    "week": w.get("week", ""),
                    "sessions": w.get("sessions", 0),
                    "input": w.get("input_tokens", 0) or 0,
                    "output": w.get("output_tokens", 0) or 0,
                    "cache": w.get("cache_tokens", 0) or 0,
                    "active_h": round((w.get("active_time_ms", 0) or 0) / 3600000, 2),
                    "messages": w.get("messages", 0) or 0,
                }
                for w in weekly
            ],
            "top": [
                {
                    "project": s.get("project", ""),
                    "model": s.get("model_display", ""),
                    "input": s.get("input_tokens", 0) or 0,
                    "output": s.get("output_tokens", 0) or 0,
                    "cache": s.get("cache_tokens", 0) or 0,
                    "date": str(s.get("started_at", ""))[:10],
                    "title": str(s.get("title", ""))[:60],
                }
                for s in top_sessions
            ],
        }
    )


@app.get("/api/stats")
async def api_stats(
    project: str | None = None,
    model: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    stats = get_global_stats(
        project_filter=project,
        model_filter=model,
        date_from=date_from,
        date_to=date_to,
    )
    return JSONResponse(
        {
            "total_sessions": stats.total_sessions,
            "total_input_tokens": stats.total_input_tokens,
            "total_output_tokens": stats.total_output_tokens,
            "total_cache_tokens": stats.total_cache_tokens,
            "total_active_time_ms": stats.total_active_time_ms,
            "total_messages": stats.total_messages,
            "total_projects": stats.total_projects,
            "total_models": stats.total_models,
            "date_range": [stats.date_range_start, stats.date_range_end],
            "by_model": [
                {
                    "model": m.display_name,
                    "sessions": m.sessions,
                    "input": m.input_tokens,
                    "cache": m.cache_tokens,
                    "output": m.output_tokens,
                    "active_ms": m.active_time_ms,
                    "projects": m.projects,
                }
                for m in stats.by_model
            ],
            "by_project": [
                {
                    "project": p.name,
                    "sessions": p.sessions,
                    "input": p.input_tokens,
                    "cache": p.cache_tokens,
                    "output": p.output_tokens,
                    "active_ms": p.active_time_ms,
                    "top_models": p.top_models,
                }
                for p in stats.by_project
            ],
            "by_day": [
                {
                    "date": d.date,
                    "sessions": d.sessions,
                    "input": d.input_tokens,
                    "output": d.output_tokens,
                }
                for d in stats.by_day
            ],
        }
    )


@app.post("/api/sync")
async def api_sync():
    count = sync(full=True)
    return JSONResponse({"synced": count})


def _find_free_port(host: str = "127.0.0.1") -> int:
    """Ask the OS for a free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def run_web(host: str = "127.0.0.1", port: int = 0, open_browser: bool = True) -> None:
    import uvicorn

    if port == 0:
        port = _find_free_port(host)

    if open_browser:
        url = f"http://{host}:{port}"

        def _open():
            time.sleep(1.5)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="warning")
