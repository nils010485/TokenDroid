"""Shared display utilities for TokenDroid."""

from __future__ import annotations

COLOR_DIM = "#6c7086"
COLOR_ACCENT = "#89b4fa"
COLOR_GREEN = "#a6e3a1"
COLOR_YELLOW = "#f9e2af"
COLOR_RED = "#f38ba8"
COLOR_MAUVE = "#cba6f7"
COLOR_TEAL = "#94e2d5"


def fmt_tokens(n: int) -> str:
    """Format a token count with K/M/B suffix."""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def fmt_input_cache(inp: int, cache: int) -> str:
    """Format total input with cache portion in parens: 296.78M (287.77M)."""
    total = inp + cache
    if cache > 0:
        return f"{fmt_tokens(total)} [dim]({fmt_tokens(cache)})[/dim]"
    return fmt_tokens(total)


def fmt_duration(ms: int) -> str:
    """Format milliseconds into a human-readable duration."""
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.0f}s"
    hours = seconds / 3600
    if hours < 24:
        return f"{hours:.1f}h"
    days = hours / 24
    return f"{days:.1f}d"


def fmt_date(iso: str) -> str:
    """Format an ISO datetime string to date only."""
    if not iso:
        return "N/A"
    return iso[:10]


def bar_str(value: int, max_val: int, width: int = 20, color: str = COLOR_ACCENT) -> str:
    """Render a Rich markup bar chart segment."""
    if max_val <= 0:
        max_val = 1
    bar_len = int((value / max_val) * width)
    return f"[{color}]{'█' * bar_len}[/{color}][dim]{'░' * (width - bar_len)}[/dim]"


def sparkline(data: list[int], width: int = 40, color: str = COLOR_ACCENT) -> str:
    """Render a sparkline string from a list of integers."""
    if not data:
        return "[dim]no data[/]"
    max_val = max(data) or 1
    bars = "▁▂▃▄▅▆▇█"
    step = max(1, len(data) // width)
    sampled = data[::step][-width:]
    result = []
    for v in sampled:
        idx = min(int((v / max_val) * (len(bars) - 1)), len(bars) - 1)
        result.append(bars[idx])
    return f"[{color}]{''.join(result)}[/{color}]"
