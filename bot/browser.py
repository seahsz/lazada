"""Browser setup: your installed Chrome, with a persistent logged-in profile."""
import logging
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

from bot.config import BrowserSettings
from bot.stock import canonical_product_url

log = logging.getLogger(__name__)

HOME_URL = "https://www.lazada.sg/"
LOGGED_OUT = "#anonLogin"
LOGGED_IN = "#myAccountTrigger"


class Browser:
    def __init__(self, settings: BrowserSettings):
        self.settings = settings
        self.playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self._cdp_browser = None

    def __enter__(self) -> "Browser":
        self.playwright = sync_playwright().start()
        if self.settings.cdp_url:
            # Attach to a Chrome you started yourself with --remote-debugging-port.
            self._cdp_browser = self.playwright.chromium.connect_over_cdp(self.settings.cdp_url)
            self.context = self._cdp_browser.contexts[0]
            log.info("Attached to running Chrome at %s", self.settings.cdp_url)
        else:
            profile = Path(self.settings.profile_dir).resolve()
            profile.mkdir(parents=True, exist_ok=True)
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile),
                channel=self.settings.channel,
                headless=False,
                no_viewport=True,
            )
            log.info("Launched %s with profile %s", self.settings.channel, profile)
        return self

    def __exit__(self, *exc):
        try:
            if self._cdp_browser:
                # Leave your own Chrome running; only drop the connection.
                self._cdp_browser.close()
            elif self.context:
                self.context.close()
        finally:
            if self.playwright:
                self.playwright.stop()

    def new_page(self) -> Page:
        return self.context.new_page()

    def first_page(self) -> Page:
        return self.context.pages[0] if self.context.pages else self.context.new_page()


def ensure_logged_in(page: Page) -> None:
    page.goto(HOME_URL, wait_until="domcontentloaded")
    try:
        page.wait_for_selector(f"{LOGGED_OUT}, {LOGGED_IN}", state="attached", timeout=30_000)
    except Exception:
        log.warning("Could not detect the login header; continuing anyway")
        return

    if page.query_selector(LOGGED_OUT):
        print("\n" + "=" * 50)
        print("NOT LOGGED IN - log in to Lazada in the browser window.")
        print("The session is saved in the profile for future runs.")
        print("=" * 50)
        input("Press Enter once you're logged in... ")
    else:
        name = (page.text_content(LOGGED_IN) or "").replace("'s account", "").strip()
        log.info("Logged in%s", f" as {name}" if name else "")


def resolve_product_url(page: Page, url: str) -> str:
    """Follow share links (s.lazada.sg/...) once, so polling uses the real product URL."""
    if "/products/" in urlsplit(url).path:
        return canonical_product_url(url)
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_url("**/products/**", timeout=30_000)
    return canonical_product_url(page.url)


def open_poll_tab(page: Page, product_url: str) -> None:
    """Park a tab on a product page so Lazada's signed API client is loaded."""
    page.goto(product_url, wait_until="domcontentloaded")
    page.wait_for_function(
        "() => window.Mtop && window.Mtop.default && window.Mtop.default.request",
        timeout=60_000,
    )
