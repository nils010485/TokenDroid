"""Tests for display.utils."""

from tokendroid.display.utils import (
    bar_str,
    fmt_date,
    fmt_duration,
    fmt_input_cache,
    fmt_tokens,
    sparkline,
)


class TestFmtTokens:
    def test_zero(self):
        assert fmt_tokens(0) == "0"

    def test_small(self):
        assert fmt_tokens(42) == "42"

    def test_thousands(self):
        assert fmt_tokens(1500) == "1.5K"

    def test_millions(self):
        assert fmt_tokens(2_500_000) == "2.50M"

    def test_billions(self):
        assert fmt_tokens(1_200_000_000) == "1.20B"

    def test_exact_thousand(self):
        assert fmt_tokens(1000) == "1.0K"


class TestFmtDuration:
    def test_seconds(self):
        assert fmt_duration(500) == "0s"

    def test_seconds_round(self):
        assert fmt_duration(30_000) == "30s"

    def test_hours(self):
        assert fmt_duration(3_600_000) == "1.0h"

    def test_days(self):
        assert fmt_duration(86_400_000) == "1.0d"


class TestFmtDate:
    def test_iso_string(self):
        assert fmt_date("2025-01-15T10:30:00") == "2025-01-15"

    def test_empty(self):
        assert fmt_date("") == "N/A"

    def test_date_only(self):
        assert fmt_date("2025-06-01") == "2025-06-01"


class TestFmtInputCache:
    def test_no_cache(self):
        assert fmt_input_cache(1000, 0) == "1.0K"

    def test_with_cache(self):
        result = fmt_input_cache(500, 200)
        assert "700" in result
        assert "200" in result


class TestBarStr:
    def test_zero(self):
        result = bar_str(0, 10)
        assert "░" in result

    def test_full(self):
        result = bar_str(10, 10)
        assert "█" in result

    def test_custom_width(self):
        result = bar_str(5, 10, width=10)
        assert result.count("█") == 5


class TestSparkline:
    def test_empty(self):
        assert "no data" in sparkline([])

    def test_basic(self):
        result = sparkline([1, 2, 3, 4, 5])
        assert len(result) > 0
        assert "▁" in result or "▅" in result or "█" in result

    def test_custom_color(self):
        result = sparkline([10], color="#ff0000")
        assert "#ff0000" in result
