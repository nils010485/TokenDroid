"""Rich CLI stat display commands for TokenDroid."""

from __future__ import annotations

import json as json_mod

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..db import (
    get_cost_summary,
    get_global_stats,
    get_monthly_stats,
    get_sessions,
    get_top_sessions,
    get_weekly_stats,
)
from .utils import (
    COLOR_ACCENT,
    COLOR_DIM,
    COLOR_GREEN,
    COLOR_MAUVE,
    COLOR_RED,
    COLOR_TEAL,
    COLOR_YELLOW,
    bar_str,
    fmt_date,
    fmt_duration,
    fmt_input_cache,
    fmt_tokens,
)


def _cost_card(label: str, value: str, color: str = COLOR_ACCENT) -> Panel:
    return Panel(
        Text(value, style=f"bold {color}", justify="center"),
        subtitle=Text(label, style=COLOR_DIM),
        border_style="dim",
        padding=(0, 2),
    )


def _stat_card(label: str, value: str, color: str = COLOR_ACCENT) -> Panel:
    return Panel(
        Text(value, style=f"bold {color}", justify="center"),
        subtitle=Text(label, style=COLOR_DIM),
        border_style="dim",
        padding=(0, 2),
    )


def display_overview(
    project: str | None = None,
    model: str | None = None,
    json_output: bool = False,
) -> None:
    """Global overview with KPIs, models, projects."""
    console = Console()
    stats = get_global_stats(project_filter=project, model_filter=model)

    if json_output:
        data = {
            "total_sessions": stats.total_sessions,
            "total_input_tokens": stats.total_input_tokens,
            "total_cache_tokens": stats.total_cache_tokens,
            "total_output_tokens": stats.total_output_tokens,
            "total_active_time_ms": stats.total_active_time_ms,
            "total_messages": stats.total_messages,
            "total_projects": stats.total_projects,
            "total_models": stats.total_models,
            "date_range": [stats.date_range_start, stats.date_range_end],
            "by_model": [
                {
                    "model": m.display_name,
                    "sessions": m.sessions,
                    "input_tokens": m.input_tokens,
                    "cache_tokens": m.cache_tokens,
                    "output_tokens": m.output_tokens,
                    "active_time_ms": m.active_time_ms,
                    "projects": m.projects,
                }
                for m in stats.by_model
            ],
            "by_project": [
                {
                    "project": p.name,
                    "sessions": p.sessions,
                    "input_tokens": p.input_tokens,
                    "cache_tokens": p.cache_tokens,
                    "output_tokens": p.output_tokens,
                    "active_time_ms": p.active_time_ms,
                    "top_models": p.top_models,
                }
                for p in stats.by_project
            ],
        }
        print(json_mod.dumps(data, indent=2, ensure_ascii=False))
        return

    cards = [
        _stat_card("Sessions", f"{stats.total_sessions:,}", COLOR_ACCENT),
        _stat_card(
            "Input (cache)",
            fmt_tokens(stats.total_input_tokens),
            COLOR_GREEN,
        ),
        _stat_card("Output", fmt_tokens(stats.total_output_tokens), COLOR_TEAL),
        _stat_card("Active Time", fmt_duration(stats.total_active_time_ms), COLOR_MAUVE),
        _stat_card("Projects", str(stats.total_projects), COLOR_RED),
        _stat_card("Models", str(stats.total_models), COLOR_RED),
    ]
    console.print()
    console.print(Columns(cards, equal=True, expand=True))
    console.print()

    t = Table(
        title="By Model",
        show_lines=False,
        border_style="dim",
        title_style=f"bold {COLOR_ACCENT}",
    )
    t.add_column("Model", style="bold white", max_width=28)
    t.add_column("Sess", justify="right", style=COLOR_GREEN, width=6)
    t.add_column("Input (cache)", justify="right", min_width=16)
    t.add_column("Output", justify="right", style=COLOR_TEAL)
    t.add_column("Active", justify="right", style=COLOR_MAUVE)
    t.add_column("Msgs", justify="right", style=COLOR_DIM)
    t.add_column("Projs", justify="right", style=COLOR_DIM, width=5)
    for m in stats.by_model:
        t.add_row(
            m.display_name,
            str(m.sessions),
            fmt_input_cache(m.input_tokens, m.cache_tokens),
            fmt_tokens(m.output_tokens),
            fmt_duration(m.active_time_ms),
            str(m.messages),
            str(m.projects),
        )
    tot_sess = sum(m.sessions for m in stats.by_model)
    tot_in = sum(m.input_tokens for m in stats.by_model)
    tot_cache = sum(m.cache_tokens for m in stats.by_model)
    tot_out = sum(m.output_tokens for m in stats.by_model)
    tot_active = sum(m.active_time_ms for m in stats.by_model)
    tot_msgs = sum(m.messages for m in stats.by_model)
    t.add_row(
        "[bold]TOTAL[/]",
        f"[bold]{tot_sess}[/]",
        f"[bold]{fmt_input_cache(tot_in, tot_cache)}[/]",
        f"[bold]{fmt_tokens(tot_out)}[/]",
        f"[bold]{fmt_duration(tot_active)}[/]",
        f"[bold]{tot_msgs}[/]",
        "",
    )
    console.print(t)
    console.print()

    t = Table(
        title="By Project",
        show_lines=False,
        border_style="dim",
        title_style=f"bold {COLOR_ACCENT}",
    )
    t.add_column("Project", style="bold white", max_width=40)
    t.add_column("Sess", justify="right", style=COLOR_GREEN, width=6)
    t.add_column("Input (cache)", justify="right", min_width=16)
    t.add_column("Output", justify="right", style=COLOR_TEAL)
    t.add_column("Active", justify="right", style=COLOR_MAUVE)
    t.add_column("Top Models", style=COLOR_DIM, max_width=45)
    for p in stats.by_project:
        t.add_row(
            p.name,
            str(p.sessions),
            fmt_input_cache(p.input_tokens, p.cache_tokens),
            fmt_tokens(p.output_tokens),
            fmt_duration(p.active_time_ms),
            ", ".join(p.top_models),
        )
    tp_sess = sum(p.sessions for p in stats.by_project)
    tp_in = sum(p.input_tokens for p in stats.by_project)
    tp_cache = sum(p.cache_tokens for p in stats.by_project)
    tp_out = sum(p.output_tokens for p in stats.by_project)
    tp_active = sum(p.active_time_ms for p in stats.by_project)
    t.add_row(
        "[bold]TOTAL[/]",
        f"[bold]{tp_sess}[/]",
        f"[bold]{fmt_input_cache(tp_in, tp_cache)}[/]",
        f"[bold]{fmt_tokens(tp_out)}[/]",
        f"[bold]{fmt_duration(tp_active)}[/]",
        "",
    )
    console.print(t)
    console.print()


def display_daily(
    project: str | None = None,
    model: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    json_output: bool = False,
) -> None:
    """Daily breakdown."""
    console = Console()
    stats = get_global_stats(
        project_filter=project,
        model_filter=model,
        date_from=date_from,
        date_to=date_to,
    )

    if json_output:
        print(
            json_mod.dumps(
                [
                    {
                        "date": d.date,
                        "sessions": d.sessions,
                        "input_tokens": d.input_tokens,
                        "cache_tokens": d.cache_tokens,
                        "output_tokens": d.output_tokens,
                        "active_time_ms": d.active_time_ms,
                        "messages": d.messages,
                    }
                    for d in stats.by_day
                ],
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    t = Table(
        title="Daily Activity",
        show_lines=False,
        border_style="dim",
        title_style=f"bold {COLOR_ACCENT}",
    )
    t.add_column("Date", style="bold white", width=12)
    t.add_column("Sess", justify="right", style=COLOR_GREEN, width=6)
    t.add_column("Input (cache)", justify="right", min_width=16)
    t.add_column("Output", justify="right", style=COLOR_TEAL)
    t.add_column("Active", justify="right", style=COLOR_MAUVE)
    t.add_column("Msgs", justify="right", style=COLOR_DIM, width=6)
    t.add_column("Bar", min_width=20)

    max_sess = max((d.sessions for d in stats.by_day), default=1) or 1
    for d in reversed(stats.by_day[-30:]):
        t.add_row(
            d.date,
            str(d.sessions),
            fmt_input_cache(d.input_tokens, d.cache_tokens),
            fmt_tokens(d.output_tokens),
            fmt_duration(d.active_time_ms),
            str(d.messages),
            bar_str(d.sessions, max_sess),
        )
    td_sess = sum(d.sessions for d in stats.by_day)
    td_in = sum(d.input_tokens for d in stats.by_day)
    td_cache = sum(d.cache_tokens for d in stats.by_day)
    td_out = sum(d.output_tokens for d in stats.by_day)
    td_active = sum(d.active_time_ms for d in stats.by_day)
    td_msgs = sum(d.messages for d in stats.by_day)
    t.add_row(
        "[bold]TOTAL[/]",
        f"[bold]{td_sess}[/]",
        f"[bold]{fmt_input_cache(td_in, td_cache)}[/]",
        f"[bold]{fmt_tokens(td_out)}[/]",
        f"[bold]{fmt_duration(td_active)}[/]",
        f"[bold]{td_msgs}[/]",
        "",
    )
    console.print()
    console.print(t)
    console.print()
    console.print()


def display_weekly(
    project: str | None = None,
    model: str | None = None,
    json_output: bool = False,
) -> None:
    """Weekly breakdown."""
    console = Console()
    weekly = get_weekly_stats(project_filter=project, model_filter=model)

    if json_output:
        print(json_mod.dumps(weekly, indent=2, ensure_ascii=False))
        return

    t = Table(
        title="Weekly Activity",
        show_lines=False,
        border_style="dim",
        title_style=f"bold {COLOR_ACCENT}",
    )
    t.add_column("Week", style="bold white", width=12)
    t.add_column("Sess", justify="right", style=COLOR_GREEN, width=6)
    t.add_column("Input (cache)", justify="right", min_width=16)
    t.add_column("Output", justify="right", style=COLOR_TEAL)
    t.add_column("Active", justify="right", style=COLOR_MAUVE)
    t.add_column("Msgs", justify="right", style=COLOR_DIM, width=6)
    t.add_column("Bar", min_width=20)

    max_sess = max((w["sessions"] for w in weekly), default=1) or 1
    for w in reversed(weekly):
        t.add_row(
            w["week"],
            str(w["sessions"]),
            fmt_input_cache(
                w.get("input_tokens", 0) or 0,
                w.get("cache_tokens", 0) or 0,
            ),
            fmt_tokens(w.get("output_tokens", 0) or 0),
            fmt_duration(w.get("active_time_ms", 0) or 0),
            str(w.get("messages", 0) or 0),
            bar_str(w["sessions"], max_sess, color=COLOR_MAUVE),
        )
    tw_sess = sum(w.get("sessions", 0) for w in weekly)
    tw_in = sum(w.get("input_tokens", 0) or 0 for w in weekly)
    tw_cache = sum(w.get("cache_tokens", 0) or 0 for w in weekly)
    tw_out = sum(w.get("output_tokens", 0) or 0 for w in weekly)
    tw_active = sum(w.get("active_time_ms", 0) or 0 for w in weekly)
    tw_msgs = sum(w.get("messages", 0) or 0 for w in weekly)
    t.add_row(
        "[bold]TOTAL[/]",
        f"[bold]{tw_sess}[/]",
        f"[bold]{fmt_input_cache(tw_in, tw_cache)}[/]",
        f"[bold]{fmt_tokens(tw_out)}[/]",
        f"[bold]{fmt_duration(tw_active)}[/]",
        f"[bold]{tw_msgs}[/]",
        "",
    )
    console.print()
    console.print(t)
    console.print()


def display_monthly(
    project: str | None = None,
    model: str | None = None,
    json_output: bool = False,
) -> None:
    """Monthly breakdown."""
    console = Console()
    monthly = get_monthly_stats(project_filter=project, model_filter=model)

    if json_output:
        print(json_mod.dumps(monthly, indent=2, ensure_ascii=False))
        return

    t = Table(
        title="Monthly Activity",
        show_lines=False,
        border_style="dim",
        title_style=f"bold {COLOR_ACCENT}",
    )
    t.add_column("Month", style="bold white", width=10)
    t.add_column("Sess", justify="right", style=COLOR_GREEN, width=6)
    t.add_column("Input (cache)", justify="right", min_width=16)
    t.add_column("Output", justify="right", style=COLOR_TEAL)
    t.add_column("Active", justify="right", style=COLOR_MAUVE)
    t.add_column("Msgs", justify="right", style=COLOR_DIM, width=6)
    t.add_column("Bar", min_width=20)

    max_sess = max((m["sessions"] for m in monthly), default=1) or 1
    for m in reversed(monthly):
        t.add_row(
            m["month"],
            str(m["sessions"]),
            fmt_input_cache(
                m.get("input_tokens", 0) or 0,
                m.get("cache_tokens", 0) or 0,
            ),
            fmt_tokens(m.get("output_tokens", 0) or 0),
            fmt_duration(m.get("active_time_ms", 0) or 0),
            str(m.get("messages", 0) or 0),
            bar_str(m["sessions"], max_sess, color=COLOR_YELLOW),
        )
    tm_sess = sum(m.get("sessions", 0) for m in monthly)
    tm_in = sum(m.get("input_tokens", 0) or 0 for m in monthly)
    tm_cache = sum(m.get("cache_tokens", 0) or 0 for m in monthly)
    tm_out = sum(m.get("output_tokens", 0) or 0 for m in monthly)
    tm_active = sum(m.get("active_time_ms", 0) or 0 for m in monthly)
    tm_msgs = sum(m.get("messages", 0) or 0 for m in monthly)
    t.add_row(
        "[bold]TOTAL[/]",
        f"[bold]{tm_sess}[/]",
        f"[bold]{fmt_input_cache(tm_in, tm_cache)}[/]",
        f"[bold]{fmt_tokens(tm_out)}[/]",
        f"[bold]{fmt_duration(tm_active)}[/]",
        f"[bold]{tm_msgs}[/]",
        "",
    )
    console.print()
    console.print(t)
    console.print()


def display_top_sessions(limit: int = 15, json_output: bool = False) -> None:
    """Top sessions by total tokens."""
    console = Console()
    top = get_top_sessions(limit)

    if json_output:
        print(json_mod.dumps(top, indent=2, ensure_ascii=False))
        return

    t = Table(
        title="Top Sessions (by total tokens)",
        show_lines=False,
        border_style="dim",
        title_style=f"bold {COLOR_ACCENT}",
    )
    t.add_column("#", style=COLOR_DIM, width=3)
    t.add_column("Project", style="bold white", max_width=28)
    t.add_column("Model", style=COLOR_TEAL, max_width=22)
    t.add_column("Total", justify="right", style=COLOR_GREEN)
    t.add_column("Input (cache)", justify="right", min_width=16)
    t.add_column("Output", justify="right", style=COLOR_TEAL)
    t.add_column("Date", style=COLOR_DIM)
    t.add_column("Title", max_width=35, no_wrap=True)

    for i, s in enumerate(top, 1):
        inp = s.get("input_tokens", 0) or 0
        out = s.get("output_tokens", 0) or 0
        cache = s.get("cache_tokens", 0) or 0
        total = inp + out + cache
        t.add_row(
            str(i),
            str(s.get("project", "")),
            str(s.get("model_display", "")),
            fmt_tokens(total),
            fmt_input_cache(inp, cache),
            fmt_tokens(out),
            fmt_date(str(s.get("started_at", ""))),
            str(s.get("title", ""))[:35],
        )
    console.print()
    console.print(t)
    console.print()


def display_sessions(
    limit: int = 15,
    show_top: bool = False,
    project: str | None = None,
    model: str | None = None,
    json_output: bool = False,
) -> None:
    """List recent sessions, or top sessions if --top."""
    console = Console()

    if show_top:
        rows = get_top_sessions(limit)
        title = "Top Sessions (by total tokens)"
    else:
        rows = get_sessions(
            project_filter=project,
            model_filter=model,
            limit=limit,
            order_by="started_at DESC",
        )
        rows = rows
        title = "Recent Sessions"

    if json_output:
        print(json_mod.dumps(rows, indent=2, ensure_ascii=False))
        return

    t = Table(
        title=title,
        show_lines=False,
        border_style="dim",
        title_style=f"bold {COLOR_ACCENT}",
    )
    t.add_column("#", style=COLOR_DIM, width=3)
    t.add_column("Project", style="bold white", max_width=28)
    t.add_column("Model", style=COLOR_TEAL, max_width=22)
    t.add_column("Input", justify="right", style=COLOR_GREEN)
    t.add_column("Cache", justify="right", style=COLOR_GREEN)
    t.add_column("Output", justify="right", style=COLOR_TEAL)
    t.add_column("Active", justify="right", style=COLOR_MAUVE)
    t.add_column("Date", style=COLOR_DIM)
    t.add_column("Title", max_width=35, no_wrap=True)

    for i, s in enumerate(rows, 1):
        inp = s.get("input_tokens", 0) or 0
        cache = s.get("cache_tokens", 0) or 0
        out = s.get("output_tokens", 0) or 0
        active = s.get("active_time_ms", 0) or 0
        t.add_row(
            str(i),
            str(s.get("project", "")),
            str(s.get("model_display", "")),
            fmt_tokens(inp),
            fmt_tokens(cache) if cache else "-",
            fmt_tokens(out),
            fmt_duration(active),
            fmt_date(str(s.get("started_at", ""))),
            str(s.get("title", ""))[:35],
        )
    console.print()
    console.print(t)
    console.print()


def display_cost(
    project: str | None = None,
    model: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    breakdown: str | None = None,
    json_output: bool = False,
) -> None:
    """Display cost estimation using models.dev pricing."""
    from ..pricing import fmt_cost

    console = Console()
    data = get_cost_summary(
        project_filter=project,
        model_filter=model,
        date_from=date_from,
        date_to=date_to,
    )
    total = data["total"]

    if json_output:
        print(json_mod.dumps(data, indent=2, ensure_ascii=False))
        return

    cards = [
        _cost_card("Total Cost", fmt_cost(total["total_cost"]), COLOR_YELLOW),
        _cost_card("Input Cost", fmt_cost(total["input_cost"]), COLOR_GREEN),
        _cost_card("Output Cost", fmt_cost(total["output_cost"]), COLOR_TEAL),
        _cost_card("Cache Cost", fmt_cost(total["cache_cost"]), COLOR_MAUVE),
        _cost_card("Reasoning Cost", fmt_cost(total["reasoning_cost"]), COLOR_RED),
    ]
    console.print()
    console.print(Columns(cards, equal=True, expand=True))
    console.print()

    dl = data["daily"]
    from datetime import date, timedelta

    today_s = date.today().isoformat()
    today_cost = next((d["total_cost"] for d in dl if d["date"] == today_s), 0.0)
    td = date.today()
    d7 = sum(d["total_cost"] for d in dl if date.fromisoformat(d["date"]) >= td - timedelta(days=7))
    d30 = sum(
        d["total_cost"] for d in dl if date.fromisoformat(d["date"]) >= td - timedelta(days=30)
    )
    d90 = sum(
        d["total_cost"] for d in dl if date.fromisoformat(d["date"]) >= td - timedelta(days=90)
    )
    quick = [
        _cost_card("Today", fmt_cost(today_cost), COLOR_RED),
        _cost_card("Last 7d", fmt_cost(d7), COLOR_TEAL),
        _cost_card("Last 30d", fmt_cost(d30), COLOR_GREEN),
        _cost_card("Last 90d", fmt_cost(d90), COLOR_YELLOW),
    ]
    console.print(Columns(quick, equal=True, expand=True))
    console.print()

    if breakdown == "model" or breakdown is None:
        t = Table(
            title="Cost by Model",
            show_lines=False,
            border_style="dim",
            title_style=f"bold {COLOR_ACCENT}",
        )
        t.add_column("Model", style="bold white", max_width=35)
        t.add_column("Input", justify="right", style=COLOR_GREEN)
        t.add_column("Output", justify="right", style=COLOR_TEAL)
        t.add_column("Cache", justify="right", style=COLOR_MAUVE)
        t.add_column("Reasoning", justify="right", style=COLOR_RED)
        t.add_column("Total", justify="right", style=COLOR_YELLOW)
        t.add_column("Price Found", justify="center", width=10)
        for m in data["by_model"]:
            matched_str = "[green]Yes[/]" if m["matched"] else "[dim]No[/]"
            t.add_row(
                m["name"],
                fmt_cost(m["input_cost"]),
                fmt_cost(m["output_cost"]),
                fmt_cost(m["cache_cost"]),
                fmt_cost(m["reasoning_cost"]),
                fmt_cost(m["total_cost"]),
                matched_str,
            )
        t.add_row(
            "[bold]TOTAL[/]",
            fmt_cost(sum(m["input_cost"] for m in data["by_model"])),
            fmt_cost(sum(m["output_cost"] for m in data["by_model"])),
            fmt_cost(sum(m["cache_cost"] for m in data["by_model"])),
            fmt_cost(sum(m["reasoning_cost"] for m in data["by_model"])),
            fmt_cost(sum(m["total_cost"] for m in data["by_model"])),
            "",
        )
        console.print(t)
        console.print()

    if breakdown == "project" or breakdown is None:
        t = Table(
            title="Cost by Project",
            show_lines=False,
            border_style="dim",
            title_style=f"bold {COLOR_ACCENT}",
        )
        t.add_column("Project", style="bold white", max_width=40)
        t.add_column("Total", justify="right", style=COLOR_YELLOW)
        t.add_column("Input", justify="right", style=COLOR_GREEN)
        t.add_column("Output", justify="right", style=COLOR_TEAL)
        t.add_column("Cache", justify="right", style=COLOR_MAUVE)
        t.add_column("Reasoning", justify="right", style=COLOR_RED)
        for p in data["by_project"]:
            if p["total_cost"] == 0:
                continue
            t.add_row(
                p["name"],
                fmt_cost(p["total_cost"]),
                fmt_cost(p["input_cost"]),
                fmt_cost(p["output_cost"]),
                fmt_cost(p["cache_cost"]),
                fmt_cost(p["reasoning_cost"]),
            )
        if t.row_count:
            active_p = [p for p in data["by_project"] if p["total_cost"] > 0]
            t.add_row(
                "[bold]TOTAL[/]",
                fmt_cost(sum(p["total_cost"] for p in active_p)),
                fmt_cost(sum(p["input_cost"] for p in active_p)),
                fmt_cost(sum(p["output_cost"] for p in active_p)),
                fmt_cost(sum(p["cache_cost"] for p in active_p)),
                fmt_cost(sum(p["reasoning_cost"] for p in active_p)),
            )
        if t.row_count:
            console.print(t)
            console.print()

    if breakdown == "day":
        t = Table(
            title="Cost / Day",
            show_lines=False,
            border_style="dim",
            title_style=f"bold {COLOR_ACCENT}",
        )
        t.add_column("Date", style=COLOR_DIM)
        t.add_column("Total", justify="right", style=COLOR_YELLOW)
        t.add_column("Input", justify="right", style=COLOR_GREEN)
        t.add_column("Output", justify="right", style=COLOR_TEAL)
        t.add_column("Cache", justify="right", style=COLOR_MAUVE)
        t.add_column("Reasoning", justify="right", style=COLOR_RED)
        for d in reversed(data["daily"]):
            if d["total_cost"] == 0:
                continue
            t.add_row(
                d["date"],
                fmt_cost(d["total_cost"]),
                fmt_cost(d["input_cost"]),
                fmt_cost(d["output_cost"]),
                fmt_cost(d["cache_cost"]),
                fmt_cost(d["reasoning_cost"]),
            )
        if t.row_count:
            active_d = [d for d in data["daily"] if d["total_cost"] > 0]
            t.add_row(
                "[bold]TOTAL[/]",
                fmt_cost(sum(d["total_cost"] for d in active_d)),
                fmt_cost(sum(d["input_cost"] for d in active_d)),
                fmt_cost(sum(d["output_cost"] for d in active_d)),
                fmt_cost(sum(d["cache_cost"] for d in active_d)),
                fmt_cost(sum(d["reasoning_cost"] for d in active_d)),
            )
        if t.row_count:
            console.print(t)
            console.print()

    if breakdown == "week":
        t = Table(
            title="Cost / Week",
            show_lines=False,
            border_style="dim",
            title_style=f"bold {COLOR_ACCENT}",
        )
        t.add_column("Week", style=COLOR_DIM)
        t.add_column("Total", justify="right", style=COLOR_YELLOW)
        t.add_column("Input", justify="right", style=COLOR_GREEN)
        t.add_column("Output", justify="right", style=COLOR_TEAL)
        t.add_column("Cache", justify="right", style=COLOR_MAUVE)
        t.add_column("Reasoning", justify="right", style=COLOR_RED)
        for w in data["weekly"]:
            if w["total_cost"] == 0:
                continue
            t.add_row(
                w["week"],
                fmt_cost(w["total_cost"]),
                fmt_cost(w["input_cost"]),
                fmt_cost(w["output_cost"]),
                fmt_cost(w["cache_cost"]),
                fmt_cost(w["reasoning_cost"]),
            )
        if t.row_count:
            active_w = [w for w in data["weekly"] if w["total_cost"] > 0]
            t.add_row(
                "[bold]TOTAL[/]",
                fmt_cost(sum(w["total_cost"] for w in active_w)),
                fmt_cost(sum(w["input_cost"] for w in active_w)),
                fmt_cost(sum(w["output_cost"] for w in active_w)),
                fmt_cost(sum(w["cache_cost"] for w in active_w)),
                fmt_cost(sum(w["reasoning_cost"] for w in active_w)),
            )

    if breakdown == "month":
        t = Table(
            title="Cost / Month",
            show_lines=False,
            border_style="dim",
            title_style=f"bold {COLOR_ACCENT}",
        )
        t.add_column("Month", style=COLOR_DIM)
        t.add_column("Total", justify="right", style=COLOR_YELLOW)
        t.add_column("Input", justify="right", style=COLOR_GREEN)
        t.add_column("Output", justify="right", style=COLOR_TEAL)
        t.add_column("Cache", justify="right", style=COLOR_MAUVE)
        t.add_column("Reasoning", justify="right", style=COLOR_RED)
        for mo in data["monthly"]:
            if mo["total_cost"] == 0:
                continue
            t.add_row(
                mo["month"],
                fmt_cost(mo["total_cost"]),
                fmt_cost(mo["input_cost"]),
                fmt_cost(mo["output_cost"]),
                fmt_cost(mo["cache_cost"]),
                fmt_cost(mo["reasoning_cost"]),
            )
        if t.row_count:
            active_mo = [mo for mo in data["monthly"] if mo["total_cost"] > 0]
            t.add_row(
                "[bold]TOTAL[/]",
                fmt_cost(sum(mo["total_cost"] for mo in active_mo)),
                fmt_cost(sum(mo["input_cost"] for mo in active_mo)),
                fmt_cost(sum(mo["output_cost"] for mo in active_mo)),
                fmt_cost(sum(mo["cache_cost"] for mo in active_mo)),
                fmt_cost(sum(mo["reasoning_cost"] for mo in active_mo)),
            )
        if t.row_count:
            console.print(t)
            console.print()
