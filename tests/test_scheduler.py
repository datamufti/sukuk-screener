"""Tests for UAE business day awareness."""
import pytest
from datetime import date
from app.services.scheduler import (
    is_uae_weekend,
    is_uae_holiday,
    is_uae_business_day,
    last_business_day,
    next_business_day,
)


class TestUAEWeekend:
    def test_saturday_is_weekend(self):
        """Saturday March 14, 2026."""
        assert is_uae_weekend(date(2026, 3, 14)) is True

    def test_sunday_is_weekend(self):
        """Sunday March 15, 2026."""
        assert is_uae_weekend(date(2026, 3, 15)) is True

    def test_monday_not_weekend(self):
        assert is_uae_weekend(date(2026, 3, 16)) is False

    def test_friday_not_weekend(self):
        """Friday is a workday in UAE since 2022."""
        assert is_uae_weekend(date(2026, 3, 20)) is False

    def test_wednesday_not_weekend(self):
        assert is_uae_weekend(date(2026, 3, 18)) is False


class TestUAEHoliday:
    def test_national_day(self):
        assert is_uae_holiday(date(2026, 12, 2)) is True

    def test_new_year(self):
        assert is_uae_holiday(date(2026, 1, 1)) is True

    def test_regular_day(self):
        assert is_uae_holiday(date(2026, 3, 18)) is False


class TestUAEBusinessDay:
    def test_weekday_no_holiday(self):
        """Wednesday March 18, 2026 is a normal business day."""
        assert is_uae_business_day(date(2026, 3, 18)) is True

    def test_saturday_not_business(self):
        assert is_uae_business_day(date(2026, 3, 14)) is False

    def test_holiday_not_business(self):
        assert is_uae_business_day(date(2026, 1, 1)) is False


class TestLastBusinessDay:
    def test_weekday_returns_same(self):
        assert last_business_day(date(2026, 3, 18)) == date(2026, 3, 18)

    def test_saturday_returns_friday(self):
        """Saturday March 14 → Friday March 13."""
        assert last_business_day(date(2026, 3, 14)) == date(2026, 3, 13)

    def test_sunday_returns_friday(self):
        """Sunday March 15 → Friday March 13."""
        assert last_business_day(date(2026, 3, 15)) == date(2026, 3, 13)


class TestNextBusinessDay:
    def test_friday_returns_monday(self):
        """Friday March 13 → Monday March 16."""
        assert next_business_day(date(2026, 3, 13)) == date(2026, 3, 16)

    def test_wednesday_returns_thursday(self):
        assert next_business_day(date(2026, 3, 18)) == date(2026, 3, 19)
