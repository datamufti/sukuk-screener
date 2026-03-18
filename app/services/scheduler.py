"""UAE business day awareness and scheduling logic."""
from datetime import date, timedelta

# UAE public holidays 2026 (approximate — may shift by 1-2 days for Islamic holidays)
UAE_HOLIDAYS_2026 = {
    date(2026, 1, 1),    # New Year's Day
    date(2026, 3, 20),   # Eid Al Fitr (approx)
    date(2026, 3, 21),
    date(2026, 3, 22),
    date(2026, 5, 27),   # Eid Al Adha (approx)
    date(2026, 5, 28),
    date(2026, 5, 29),
    date(2026, 6, 17),   # Islamic New Year (approx)
    date(2026, 7, 7),    # Commemoration Day (moved to Jul for 2026)
    date(2026, 8, 26),   # Prophet's Birthday (approx)
    date(2026, 11, 30),  # Commemoration Day
    date(2026, 12, 1),   # National Day
    date(2026, 12, 2),   # National Day
    date(2026, 12, 3),   # National Day (bridge)
}

# Extensible: add 2027+ holidays as needed
UAE_HOLIDAYS = UAE_HOLIDAYS_2026


def is_uae_weekend(d: date) -> bool:
    """Check if a date falls on a UAE weekend (Saturday=5, Sunday=6).

    UAE changed to Sat-Sun weekends in January 2022.
    """
    return d.weekday() in (5, 6)


def is_uae_holiday(d: date) -> bool:
    """Check if a date is a UAE public holiday."""
    return d in UAE_HOLIDAYS


def is_uae_business_day(d: date) -> bool:
    """Check if a date is a UAE business day."""
    return not is_uae_weekend(d) and not is_uae_holiday(d)


def last_business_day(d: date | None = None) -> date:
    """Return the most recent UAE business day on or before the given date."""
    if d is None:
        d = date.today()
    while not is_uae_business_day(d):
        d -= timedelta(days=1)
    return d


def next_business_day(d: date | None = None) -> date:
    """Return the next UAE business day after the given date."""
    if d is None:
        d = date.today()
    d += timedelta(days=1)
    while not is_uae_business_day(d):
        d += timedelta(days=1)
    return d
