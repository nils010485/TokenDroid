"""Textual TUI for TokenDroid (`tokendroid tui`)."""

from __future__ import annotations

import logging
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widgets import Footer, Header, Static, TabbedContent, TabPane

from ..db import (
    get_cost_summary,
    get_global_stats,
    get_sessions,
    get_weekly_stats,
    sync,
)
from ..models import GlobalStats
from ..pricing import fmt_cost
from .utils import (
    COLOR_ACCENT,
    COLOR_GREEN,
    COLOR_MAUVE,
    COLOR_RED,
    COLOR_TEAL,
    COLOR_YELLOW,
    fmt_duration,
    fmt_tokens,
    sparkline,
)

logger = logging.getLogger(__name__)


class OverviewWidget(Static):
    """Overview dashboard with KPIs."""

    def refresh_data(self, stats: GlobalStats) -> None:
        sections = []
        sections.append(
            f"[bold {COLOR_ACCENT}]Sessions:[/] {stats.total_sessions:,}  "
            f"[bold {COLOR_GREEN}]Input:[/] {fmt_tokens(stats.total_input_tokens)}  "
            f"[bold {COLOR_TEAL}]Output:[/] {fmt_tokens(stats.total_output_tokens)}  "
            f"[bold {COLOR_YELLOW}]Cache:[/] {fmt_tokens(stats.total_cache_tokens)}  "
            f"[bold {COLOR_MAUVE}]Active:[/] {fmt_duration(stats.total_active_time_ms)}  "
            f"[bold {COLOR_RED}]Projects:[/] {stats.total_projects}  "
            f"[bold {COLOR_RED}]Models:[/] {stats.total_models}"
        )
        sections.append(
            f"[dim]Range: {stats.date_range_start[:10]} -> {stats.date_range_end[:10]}[/]"
        )

        if stats.by_day:
            daily_sessions = [d.sessions for d in stats.by_day]
            sections.append(f"\n[bold]Sessions/day (sparkline):[/]\n{sparkline(daily_sessions)}")

        if stats.by_model:
            sections.append(f"\n[bold {COLOR_ACCENT}]Top Models:[/]")
            for m in stats.by_model[:8]:
                bar_len = min(int(m.sessions / max(ms.sessions for ms in stats.by_model) * 30), 30)
                bar = f"[{COLOR_TEAL}]{'█' * bar_len}[/{COLOR_TEAL}]"
                sections.append(f"  {m.display_name:<25} {m.sessions:>4} sess  {bar}")

        if stats.by_project:
            sections.append(f"\n[bold {COLOR_ACCENT}]Top Projects:[/]")
            for p in stats.by_project[:8]:
                bar_len = min(
                    int(p.sessions / max(pr.sessions for pr in stats.by_project) * 30), 30
                )
                bar = f"[{COLOR_GREEN}]{'█' * bar_len}[/{COLOR_GREEN}]"
                sections.append(f"  {p.name:<30} {p.sessions:>4} sess  {bar}")

        self.update("\n".join(sections))


class DailyWidget(Static):
    """Daily breakdown with sparklines."""

    def refresh_data(self, stats: GlobalStats) -> None:
        lines = [f"[bold {COLOR_ACCENT}]Daily Activity[/]\n"]

        if not stats.by_day:
            lines.append("[dim]No data[/]")
            self.update("\n".join(lines))
            return

        daily_out = [d.output_tokens for d in stats.by_day]
        daily_in = [d.input_tokens for d in stats.by_day]
        daily_cache = [d.cache_tokens for d in stats.by_day]

        lines.append(f"  Output tokens: {sparkline(daily_out)}")
        lines.append(f"  Input tokens:  {sparkline(daily_in)}")
        lines.append(f"  Cache tokens:  {sparkline(daily_cache)}")
        lines.append("")

        lines.append(
            f"  {'Date':<12} {'Sess':>5} {'Input':>10} "
            f"{'Cache':>10} {'Output':>10} {'Active':>8} {'Msgs':>6}"
        )
        lines.append(f"  {'─' * 55}")

        for d in reversed(stats.by_day[-30:]):
            lines.append(
                f"  {d.date:<12} {d.sessions:>5} "
                f"{fmt_tokens(d.input_tokens):>10} "
                f"{fmt_tokens(d.cache_tokens):>10} "
                f"{fmt_tokens(d.output_tokens):>10} "
                f"{fmt_duration(d.active_time_ms):>8} {d.messages:>6}"
            )

        self.update("\n".join(lines))


class ModelWidget(Static):
    """Model breakdown."""

    def refresh_data(self, stats: GlobalStats) -> None:
        lines = [f"[bold {COLOR_ACCENT}]By Model[/]\n"]

        if not stats.by_model:
            lines.append("[dim]No data[/]")
            self.update("\n".join(lines))
            return

        max_sessions = max(m.sessions for m in stats.by_model)

        for m in stats.by_model:
            bar_len = min(int(m.sessions / max_sessions * 35), 35)
            bar = f"[{COLOR_TEAL}]{'█' * bar_len}[/{COLOR_TEAL}]"
            lines.append(
                f"  [bold]{m.display_name}[/]\n"
                f"    {m.sessions:>4} sess | "
                f"{fmt_tokens(m.output_tokens):>8} out | "
                f"{fmt_tokens(m.input_tokens):>8} in | "
                f"{fmt_tokens(m.cache_tokens):>8} cache | "
                f"{fmt_duration(m.active_time_ms):>6} active\n"
                f"    {bar}"
            )

        self.update("\n".join(lines))


class ProjectWidget(Static):
    """Project breakdown with per-project details."""

    def refresh_data(self, stats: GlobalStats) -> None:
        lines = [f"[bold {COLOR_ACCENT}]By Project[/]\n"]

        if not stats.by_project:
            lines.append("[dim]No data[/]")
            self.update("\n".join(lines))
            return

        max_sessions = max(p.sessions for p in stats.by_project)

        for p in stats.by_project:
            bar_len = min(int(p.sessions / max_sessions * 35), 35)
            bar = f"[{COLOR_GREEN}]{'█' * bar_len}[/{COLOR_GREEN}]"
            models_str = ", ".join(p.top_models) if p.top_models else "N/A"
            lines.append(
                f"  [bold]{p.name}[/]\n"
                f"    {p.sessions:>4} sess | "
                f"{fmt_tokens(p.output_tokens):>8} out | "
                f"{fmt_tokens(p.input_tokens):>8} in | "
                f"{fmt_tokens(p.cache_tokens):>8} cache | "
                f"{fmt_duration(p.active_time_ms):>6} active\n"
                f"    [dim]Models: {models_str}[/]\n"
                f"    {bar}"
            )

        self.update("\n".join(lines))


class WeekWidget(Static):
    """Weekly breakdown."""

    def refresh_data(self) -> None:
        lines = [f"[bold {COLOR_ACCENT}]Weekly Activity[/]\n"]

        weekly = get_weekly_stats()
        if not weekly:
            lines.append("[dim]No data[/]")
            self.update("\n".join(lines))
            return

        max_sessions = max(w["sessions"] for w in weekly) or 1

        lines.append(
            f"  {'Week':<10} {'Sess':>5} {'Input':>10} {'Cache':>10} {'Output':>10} {'Active':>8}"
        )
        lines.append(f"  {'─' * 60}")

        for w in weekly:
            bar_len = min(int(w["sessions"] / max_sessions * 30), 30)
            bar = f"[{COLOR_MAUVE}]{'█' * bar_len}[/{COLOR_MAUVE}]"
            lines.append(
                f"  {w['week']:<10} {w['sessions']:>5} {fmt_tokens(w['input_tokens']):>10} "
                f"{fmt_tokens(w.get('cache_tokens', 0) or 0):>10} "
                f"{fmt_tokens(w['output_tokens']):>10} {fmt_duration(w['active_time_ms']):>8}"
            )
            lines.append(f"  {bar}")

        self.update("\n".join(lines))


class SessionsWidget(Static):
    """Scrollable session list."""

    def refresh_data(self) -> None:
        lines = [f"[bold {COLOR_ACCENT}]Recent Sessions[/]\n"]

        sessions = get_sessions(limit=50)
        if not sessions:
            lines.append("[dim]No data[/]")
            self.update("\n".join(lines))
            return

        lines.append(f"  {'Date':<12} {'Project':<22} {'Model':<22} {'Output':>10} {'Active':>8}")
        lines.append(f"  {'─' * 85}")

        for s in sessions:
            date = str(s.get("started_at", ""))[:10]
            lines.append(
                f"  {date:<12} {str(s.get('project', ''))[:22]:<22} "
                f"{str(s.get('model_display', ''))[:22]:<22} "
                f"{fmt_tokens(s.get('output_tokens', 0)):>10} "
                f"{fmt_duration(s.get('active_time_ms', 0)):>8}"
            )

        self.update("\n".join(lines))


class CostWidget(Static):
    """Cost estimation breakdown."""

    def refresh_data(self) -> None:
        lines = [f"[bold {COLOR_ACCENT}]Cost Estimation[/]\n"]
        lines.append("[dim]Based on models.dev pricing data[/]\n")

        try:
            cost = get_cost_summary()
        except Exception:
            lines.append("[dim]Failed to load cost data[/]")
            self.update("\n".join(lines))
            return

        t = cost.get("total", {})
        lines.append(
            f"  [bold]Total:[/] {fmt_cost(t.get('total_cost', 0))}  "
            f"[{COLOR_GREEN}]In:[/] {fmt_cost(t.get('input_cost', 0))}  "
            f"[{COLOR_TEAL}]Out:[/] {fmt_cost(t.get('output_cost', 0))}  "
            f"[{COLOR_YELLOW}]Cache:[/] {fmt_cost(t.get('cache_cost', 0))}  "
            f"[{COLOR_MAUVE}]Reason:[/] {fmt_cost(t.get('reasoning_cost', 0))}"
        )

        by_model = cost.get("by_model", [])
        matched = [m for m in by_model if m.get("matched")]
        if matched:
            lines.append(f"\n[bold {COLOR_ACCENT}]By Model[/]")
            max_cost = max(m.get("total_cost", 0) for m in matched) or 1
            for m in matched:
                bar_len = min(int(m.get("total_cost", 0) / max_cost * 35), 35)
                bar = f"[{COLOR_TEAL}]{'█' * bar_len}[/{COLOR_TEAL}]"
                lines.append(
                    f"  {m['name']:<25} {fmt_cost(m.get('total_cost', 0)):>10}  "
                    f"[dim]in:{fmt_cost(m.get('input_cost', 0))} "
                    f"out:{fmt_cost(m.get('output_cost', 0))} "
                    f"cache:{fmt_cost(m.get('cache_cost', 0))}[/]\n"
                    f"    {bar}"
                )

        by_project = cost.get("by_project", [])
        with_cost = [p for p in by_project if p.get("total_cost", 0) > 0]
        if with_cost:
            lines.append(f"\n[bold {COLOR_ACCENT}]By Project[/]")
            max_p = max(p.get("total_cost", 0) for p in with_cost) or 1
            for p in with_cost[:10]:
                bar_len = min(int(p.get("total_cost", 0) / max_p * 35), 35)
                bar = f"[{COLOR_GREEN}]{'█' * bar_len}[/{COLOR_GREEN}]"
                lines.append(f"  {p['name']:<30} {fmt_cost(p.get('total_cost', 0)):>10}  {bar}")

        monthly = cost.get("monthly", [])
        if monthly:
            lines.append(f"\n[bold {COLOR_ACCENT}]Monthly[/]")
            lines.append(
                f"  {'Month':<10} {'Total':>10} {'Input':>10} {'Output':>10} {'Cache':>10}"
            )
            lines.append(f"  {'─' * 55}")
            for m in reversed(monthly):
                lines.append(
                    f"  {m['month']:<10} {fmt_cost(m.get('total_cost', 0)):>10} "
                    f"{fmt_cost(m.get('input_cost', 0)):>10} "
                    f"{fmt_cost(m.get('output_cost', 0)):>10} "
                    f"{fmt_cost(m.get('cache_cost', 0)):>10}"
                )

        self.update("\n".join(lines))


class NstatApp(App):
    """TokenDroid - Factory Droid Analytics TUI."""

    TITLE = "TokenDroid"
    SUB_TITLE = "Factory Droid Analytics"

    CSS = """
    Screen {
        layout: vertical;
    }
    #main-content {
        height: 1fr;
    }
    .tab-content {
        padding: 1 2;
        height: auto;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("s", "force_sync", "Force Sync"),
    ]

    auto_refresh: reactive[bool] = reactive(True)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent():
            with TabPane("Overview", id="tab-overview"):
                yield OverviewWidget(id="overview")
            with TabPane("Daily", id="tab-daily"):
                yield DailyWidget(id="daily")
            with TabPane("Models", id="tab-models"):
                yield ModelWidget(id="models")
            with TabPane("Projects", id="tab-projects"):
                yield ProjectWidget(id="projects")
            with TabPane("Weeks", id="tab-weeks"):
                yield WeekWidget(id="weeks")
            with TabPane("Sessions", id="tab-sessions"):
                yield SessionsWidget(id="sessions")
            with TabPane("Cost", id="tab-cost"):
                yield CostWidget(id="cost")
        yield Footer()

    def on_mount(self) -> None:
        self._load_data()
        self.set_interval(30, self._auto_refresh_tick)

    def _auto_refresh_tick(self) -> None:
        if self.auto_refresh:
            self._load_data()

    def action_refresh(self) -> None:
        self._load_data()

    def action_force_sync(self) -> None:
        self.notify("Force syncing...")
        sync(full=True)
        self._load_data()
        self.notify("Sync complete!")

    def _load_data(self) -> None:
        self.run_worker(self._worker_load, exclusive=True)

    async def _worker_load(self) -> None:
        stats = get_global_stats()
        self._update_ui(stats)

    def _update_ui(self, stats: GlobalStats) -> None:
        try:
            self.query_one("#overview", OverviewWidget).refresh_data(stats)
            self.query_one("#daily", DailyWidget).refresh_data(stats)
            self.query_one("#models", ModelWidget).refresh_data(stats)
            self.query_one("#projects", ProjectWidget).refresh_data(stats)
            self.query_one("#weeks", WeekWidget).refresh_data()
            self.query_one("#sessions", SessionsWidget).refresh_data()
            self.query_one("#cost", CostWidget).refresh_data()
        except Exception:
            logger.exception("Failed to update TUI widgets")


def run_tui() -> None:
    app = NstatApp()
    app.run()
