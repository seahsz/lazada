"""Load and validate config.json."""
import json
from dataclasses import dataclass, field
from pathlib import Path

from bot.schedule import Window, parse_windows


@dataclass
class Product:
    name: str
    url: str
    quantity: int = 1


@dataclass
class Polling:
    interval_seconds: float = 1.5
    jitter_seconds: float = 0.5


@dataclass
class BrowserSettings:
    channel: str = "chrome"
    profile_dir: str = "./profile"
    cdp_url: str | None = None


@dataclass
class Config:
    products: list[Product]
    windows: list[Window]
    timezone: str = "Asia/Singapore"
    polling: Polling = field(default_factory=Polling)
    browser: BrowserSettings = field(default_factory=BrowserSettings)
    auto_place_order: bool = True
    alert_sound: bool = True
    ntfy_topic: str | None = None


def load_config(path: str | Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config not found: {path}. Copy config.example.json to config.json and edit it."
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    return parse_config(raw)


def parse_config(raw: dict) -> Config:
    products = [
        Product(name=p.get("name") or p["url"], url=p["url"], quantity=int(p.get("quantity", 1)))
        for p in raw.get("products", [])
    ]
    if not products:
        raise ValueError("No products configured.")
    for p in products:
        if p.quantity < 1:
            raise ValueError(f"{p.name}: quantity must be at least 1")

    windows = parse_windows(raw.get("windows", []))
    if not windows:
        raise ValueError("No monitoring windows configured.")

    polling_raw = raw.get("polling", {})
    polling = Polling(
        interval_seconds=float(polling_raw.get("interval_seconds", 1.5)),
        jitter_seconds=float(polling_raw.get("jitter_seconds", 0.5)),
    )
    if polling.interval_seconds < 0.5:
        raise ValueError("polling.interval_seconds must be at least 0.5")

    browser_raw = raw.get("browser", {})
    browser = BrowserSettings(
        channel=browser_raw.get("channel", "chrome"),
        profile_dir=browser_raw.get("profile_dir", "./profile"),
        cdp_url=browser_raw.get("cdp_url"),
    )

    alerts = raw.get("alerts", {})
    return Config(
        products=products,
        windows=windows,
        timezone=raw.get("timezone", "Asia/Singapore"),
        polling=polling,
        browser=browser,
        auto_place_order=bool(raw.get("purchase", {}).get("auto_place_order", True)),
        alert_sound=bool(alerts.get("sound", True)),
        ntfy_topic=alerts.get("ntfy_topic"),
    )
