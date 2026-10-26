"""
Lazada restock bot.

    python -m bot                 # run on the configured schedule
    python -m bot --check         # check every product once and exit (no buying)
    python -m bot --dry-run       # full run, but stop at checkout instead of placing the order
"""
import argparse
import logging
import random
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bot.alerts import Alerter
from bot.browser import Browser, ensure_logged_in, open_poll_tab, resolve_product_url
from bot.config import Config, Product, load_config
from bot.purchase import captcha_visible, purchase, wait_for_human
from bot.schedule import active_window, next_window_start
from bot.stock import Status, StockResult, check_stock

log = logging.getLogger("bot")

MAX_CONSECUTIVE_ERRORS = 3
BLOCKED_BACKOFF_S = 60
MIN_SLEEP_S = 0.5
STATUS_EVERY_S = 60


def setup_logging() -> None:
    Path("logs").mkdir(exist_ok=True)
    fmt = "%(asctime)s %(levelname)-7s %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(), logging.FileHandler("logs/bot.log", encoding="utf-8")],
    )


def describe(product: Product, result: StockResult) -> str:
    extra = f" max={result.max_qty}" if result.max_qty is not None else ""
    buttons = f" [{', '.join(result.buttons)}]" if result.buttons else ""
    detail = f" {result.detail}" if result.detail else ""
    return f"{result.status.value:<12} {product.name}{extra}{buttons}{detail}"


class Bot:
    def __init__(self, cfg: Config, browser: Browser, alerter: Alerter, dry_run: bool):
        self.cfg = cfg
        self.browser = browser
        self.alerter = alerter
        self.auto_place_order = cfg.auto_place_order and not dry_run
        self.tz = ZoneInfo(cfg.timezone)
        self.poll_page = browser.first_page()
        self.targets: list[tuple[Product, str]] = []

    def prepare(self) -> None:
        ensure_logged_in(self.poll_page)
        for product in self.cfg.products:
            url = resolve_product_url(self.poll_page, product.url)
            log.info("Tracking %s -> %s", product.name, url)
            self.targets.append((product, url))
        self.refresh_poll_tab()

    def refresh_poll_tab(self) -> None:
        open_poll_tab(self.poll_page, self.targets[0][1])

    def check_once(self) -> None:
        results = check_stock(self.poll_page, [url for _, url in self.targets])
        for (product, _), result in zip(self.targets, results):
            log.info(describe(product, result))

    def run(self, ignore_schedule: bool) -> None:
        pending = list(self.targets)
        errors = 0
        rounds = 0
        last_status = 0.0
        was_idle = False

        while pending:
            now = datetime.now(self.tz)
            if not ignore_schedule and not active_window(self.cfg.windows, now):
                was_idle = self._idle(now, was_idle)
                continue
            if was_idle:
                log.info("Monitoring window open - refreshing poll tab")
                self.refresh_poll_tab()
                was_idle = False

            # Every pending product in one parallel batch.
            results = check_stock(self.poll_page, [url for _, url in pending])
            rounds += 1
            statuses = {r.status for r in results}

            if Status.BLOCKED in statuses:
                log.warning(" | ".join(describe(p, r) for (p, _), r in zip(pending, results)))
                self._handle_block()
                continue

            if statuses & {Status.ERROR, Status.NO_API}:
                log.warning(" | ".join(describe(p, r) for (p, _), r in zip(pending, results)))
                errors += 1
                if errors >= MAX_CONSECUTIVE_ERRORS:
                    log.warning("Repeated errors - reloading poll tab")
                    self._safe_refresh()
                    errors = 0
            else:
                errors = 0

            in_stock = [(p, url, r) for (p, url), r in zip(pending, results) if r.status is Status.IN_STOCK]
            for product, url, result in in_stock:
                log.info(describe(product, result))
                self.alerter.alert("IN STOCK", f"{product.name} - buying now", urgent=True)
                if self._buy(product, url, result):
                    pending.remove((product, url))

            # One status line a minute instead of a log line per check.
            if time.monotonic() - last_status >= STATUS_EVERY_S:
                last_status = time.monotonic()
                log.info("Round %d: %s", rounds,
                         " | ".join(f"{p.name}={r.status.value}" for (p, _), r in zip(pending, results)))

            if pending and not in_stock:
                p = self.cfg.polling
                time.sleep(max(MIN_SLEEP_S, p.interval_seconds + random.uniform(-p.jitter_seconds, p.jitter_seconds)))

        self.alerter.alert("DONE", "Every product has been bought.")

    def _buy(self, product: Product, url: str, result: StockResult) -> bool:
        page = self.browser.new_page()
        try:
            ok = purchase(page, product, url, result.max_qty, self.auto_place_order, self.alerter)
        except Exception as e:
            log.exception("Purchase crashed: %s", e)
            ok = False
        if not ok:
            # Leave the tab open so you can take over by hand.
            self.alerter.alert("PURCHASE FAILED", f"{product.name} - finish it manually in the open tab.",
                               urgent=True)
        return ok

    def _handle_block(self) -> None:
        self._safe_refresh()
        if captcha_visible(self.poll_page):
            if wait_for_human(self.poll_page, self.alerter, "Lazada wants a captcha on the poll tab", 600):
                self._safe_refresh()
                return
        else:
            self.alerter.alert("BLOCKED", "Lazada rejected the stock check. Backing off.", urgent=True)
        time.sleep(BLOCKED_BACKOFF_S)

    def _safe_refresh(self) -> None:
        try:
            self.refresh_poll_tab()
        except Exception as e:
            log.warning("Poll tab refresh failed: %s", e)

    def _idle(self, now: datetime, was_idle: bool) -> bool:
        nxt = next_window_start(self.cfg.windows, now)
        if not was_idle:
            log.info("Outside monitoring windows. Next: %s", f"{nxt:%a %d %b %H:%M}" if nxt else "none")
        wait = (nxt - now).total_seconds() if nxt else 60
        time.sleep(max(1.0, min(60.0, wait)))
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Lazada restock bot")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--check", action="store_true", help="check every product once, then exit")
    parser.add_argument("--dry-run", action="store_true", help="stop at checkout, don't place the order")
    parser.add_argument("--ignore-schedule", action="store_true", help="poll now, outside the windows")
    args = parser.parse_args()

    setup_logging()
    cfg = load_config(args.config)
    alerter = Alerter(cfg.alert_sound, cfg.ntfy_topic)
    log.info("Windows: %s", "; ".join(w.describe() for w in cfg.windows))
    if args.dry_run or not cfg.auto_place_order:
        log.info("Will stop at checkout (no automatic Place Order)")

    with Browser(cfg.browser) as browser:
        bot = Bot(cfg, browser, alerter, args.dry_run)
        bot.prepare()
        if args.check:
            bot.check_once()
            return
        try:
            bot.run(args.ignore_schedule)
        except KeyboardInterrupt:
            log.info("Stopped by user")
            return
        input("Press Enter to close the browser... ")


if __name__ == "__main__":
    main()
