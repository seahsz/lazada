from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from bot.schedule import active_window, next_window_start, parse_windows

SGT = ZoneInfo("Asia/Singapore")
WINDOWS = parse_windows([
    {"days": ["mon", "tue", "wed", "thu", "fri"], "start": "13:00", "end": "15:00"},
    {"days": ["fri"], "start": "10:00", "end": "11:00"},
])


def at(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=SGT)


# 2026-10-26 is a Monday, 2026-10-30 a Friday, 2026-10-31 a Saturday.
@pytest.mark.parametrize("now, expected", [
    (at(2026, 10, 26, 13, 0), True),
    (at(2026, 10, 26, 14, 59), True),
    (at(2026, 10, 26, 15, 0), False),
    (at(2026, 10, 26, 10, 30), False),  # Friday-only morning window
    (at(2026, 10, 30, 10, 30), True),
    (at(2026, 10, 30, 11, 0), False),
    (at(2026, 10, 31, 14, 0), False),
])
def test_active_window(now, expected):
    assert (active_window(WINDOWS, now) is not None) is expected


@pytest.mark.parametrize("now, expected", [
    (at(2026, 10, 26, 9, 0), at(2026, 10, 26, 13, 0)),
    (at(2026, 10, 29, 16, 0), at(2026, 10, 30, 10, 0)),  # Thu evening -> Fri morning
    (at(2026, 10, 30, 11, 30), at(2026, 10, 30, 13, 0)),
    (at(2026, 10, 30, 15, 0), at(2026, 11, 2, 13, 0)),  # Fri after close -> Mon
])
def test_next_window_start(now, expected):
    assert next_window_start(WINDOWS, now) == expected


def test_rejects_bad_windows():
    with pytest.raises(ValueError):
        parse_windows([{"days": ["mon"], "start": "15:00", "end": "13:00"}])
    with pytest.raises(ValueError):
        parse_windows([{"days": ["funday"], "start": "13:00", "end": "15:00"}])
