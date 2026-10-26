"""Buy flow: product page -> Buy Now -> checkout -> Place Order."""
import logging
import time

from playwright.sync_api import Page

from bot.alerts import Alerter
from bot.config import Product

log = logging.getLogger(__name__)

BUY_NOW = 'button:has-text("Buy Now")'
QUANTITY_INPUT = '#module_quantity-input input[type="text"]'
PLACE_ORDER = 'button:has-text("Place Order"), .checkout-order-total:has-text("Place Order")'
# Alibaba "baxia" slider / punish page elements.
CAPTCHA = '#baxia-dialog-content, .baxia-dialog, iframe[src*="punish"], #nocaptcha, .nc-container'


def captcha_visible(page: Page) -> bool:
    try:
        return page.locator(CAPTCHA).first.is_visible(timeout=200)
    except Exception:
        return False


def wait_for_human(page: Page, alerter: Alerter, reason: str, timeout_s: int = 300) -> bool:
    """Alert, then wait for you to clear the captcha in the browser window."""
    alerter.alert("CAPTCHA - action needed", f"{reason}. Solve it in the browser window.", urgent=True)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not captcha_visible(page):
            log.info("Captcha cleared")
            return True
        time.sleep(1)
    return False


def _wait_or_captcha(page: Page, locator, alerter: Alerter, what: str, timeout_s: int) -> bool:
    """Wait for `locator` to show up, pausing for you if a captcha appears instead."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            locator.first.wait_for(state="visible", timeout=1_000)
            return True
        except Exception:
            pass
        if captcha_visible(page):
            if not wait_for_human(page, alerter, f"Captcha while waiting for {what}"):
                return False
            deadline = time.monotonic() + timeout_s
    log.error("Timed out waiting for %s", what)
    return False


def set_quantity(page: Page, quantity: int) -> bool:
    box = page.locator(QUANTITY_INPUT).first
    try:
        box.wait_for(state="visible", timeout=5_000)
        box.fill(str(quantity))
        box.press("Tab")
        actual = box.input_value()
    except Exception as e:
        log.error("Could not set quantity: %s", e)
        return False
    if actual != str(quantity):
        log.warning("Quantity box shows %s instead of %s (stock or per-person limit?)", actual, quantity)
    return True


def purchase(page: Page, product: Product, product_url: str, max_qty: int | None,
             auto_place_order: bool, alerter: Alerter) -> bool:
    quantity = min(product.quantity, max_qty) if max_qty else product.quantity
    log.info("Buying %s x%d", product.name, quantity)

    page.goto(product_url, wait_until="domcontentloaded")
    if not _wait_or_captcha(page, page.locator(BUY_NOW), alerter, "Buy Now button", 20):
        return False

    if quantity > 1 and not set_quantity(page, quantity):
        return False

    page.locator(BUY_NOW).first.click()
    try:
        page.wait_for_url("**checkout.lazada.sg/**", timeout=30_000)
    except Exception:
        if captcha_visible(page) and wait_for_human(page, alerter, "Captcha after Buy Now"):
            page.wait_for_url("**checkout.lazada.sg/**", timeout=30_000)
        else:
            log.error("Did not reach checkout (still on %s)", page.url)
            return False

    place = page.locator(PLACE_ORDER)
    if not _wait_or_captcha(page, place, alerter, "Place Order button", 30):
        return False

    if not auto_place_order:
        alerter.alert("AT CHECKOUT", f"{product.name} x{quantity} - place the order yourself.", urgent=True)
        return True

    place.first.click()
    log.info("Clicked Place Order for %s", product.name)
    alerter.alert("ORDER PLACED", f"{product.name} x{quantity} - check the browser to finish payment.",
                  urgent=True)
    return True
