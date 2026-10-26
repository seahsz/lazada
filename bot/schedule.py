"""Monitoring windows: when the bot should be polling."""
from dataclasses import dataclass
from datetime import datetime, time, timedelta

DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


@dataclass(frozen=True)
class Window:
    days: frozenset[int]  # 0 = Monday
    start: time
    end: time

    def contains(self, now: datetime) -> bool:
        return now.weekday() in self.days and self.start <= now.time() < self.end

    def describe(self) -> str:
        days = ",".join(DAY_NAMES[d] for d in sorted(self.days))
        return f"{days} {self.start:%H:%M}-{self.end:%H:%M}"


def _parse_day(day: str) -> int:
    key = day.strip().lower()[:3]
    if key not in DAY_NAMES:
        raise ValueError(f"Unknown day: {day!r}")
    return DAY_NAMES.index(key)


def parse_windows(raw: list[dict]) -> list[Window]:
    windows = []
    for w in raw:
        start = time.fromisoformat(w["start"])
        end = time.fromisoformat(w["end"])
        if end <= start:
            raise ValueError(f"Window end must be after start: {w}")
        windows.append(Window(frozenset(_parse_day(d) for d in w["days"]), start, end))
    return windows


def active_window(windows: list[Window], now: datetime) -> Window | None:
    return next((w for w in windows if w.contains(now)), None)


def next_window_start(windows: list[Window], now: datetime) -> datetime | None:
    """Earliest window start strictly after `now`, looking up to a week ahead."""
    candidates = []
    for offset in range(8):
        day = now + timedelta(days=offset)
        for w in windows:
            if day.weekday() in w.days:
                start = datetime.combine(day.date(), w.start, tzinfo=now.tzinfo)
                if start > now:
                    candidates.append(start)
    return min(candidates, default=None)
