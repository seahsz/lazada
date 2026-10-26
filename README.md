# Lazada Restock Bot

Watches Lazada SG products during the restock windows and buys the moment they come back in stock.

## How it works

- **Your installed Chrome**, with a dedicated profile in `./profile` that remembers your login.
- **Lightweight, parallel stock checks.** The bot keeps one tab parked on a product page and asks Lazada's
  own product-detail API (`mtop.global.detail.web.getDetailInfo`) about every product at once, using the
  page's signed request client. One small JSON request per product, all fired together (~200ms per round
  whether you track 1 product or 3), instead of full page loads.
  - In stock = the SKU has an enabled **Buy Now** operation and quantity limit > 0.
- **Only during the windows** (default Mon-Fri 13:00-15:00 and Fri 10:00-11:00 SGT). Rounds repeat every
  `interval_seconds ± jitter_seconds` (default 1-2s), so each product is checked roughly every 1.7s.
- **Captcha = you.** If Lazada asks for a slider/captcha, the bot beeps (and can push to your phone),
  waits for you to solve it in the browser window, then carries on.
- **In stock** -> opens the product in a new tab -> sets quantity -> Buy Now -> checkout -> Place Order.

## Setup (Windows)

```shell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy config.example.json config.json
```

Google Chrome must be installed (the bot uses it instead of Playwright's bundled Chromium).

Edit `config.json`:

| Key | Meaning |
|---|---|
| `products[].url` | Product page or `s.lazada.sg` share link (resolved once at startup) |
| `products[].quantity` | How many to buy (capped to what Lazada allows) |
| `windows` | When to poll. `days` use `mon`..`sun`, times are 24h in `timezone` |
| `polling.interval_seconds` / `jitter_seconds` | Pause between rounds: interval ± random jitter (minimum 0.5s) |
| `browser.cdp_url` | Optional, e.g. `http://localhost:9222`, to attach to a Chrome you started yourself |
| `purchase.auto_place_order` | `false` stops at checkout so you click Place Order yourself |
| `alerts.ntfy_topic` | Optional [ntfy.sh](https://ntfy.sh) topic for phone pushes. Pick a long random name: anyone who knows it can read your alerts |

## Run

```shell
# First: check every product once (logs in if needed, no buying)
python -m bot --check

# Full run on the schedule
python -m bot

# Rehearsal: polls now and stops at checkout without placing the order
python -m bot --ignore-schedule --dry-run
```

The first run opens Chrome on Lazada. Log in by hand and press Enter in the terminal. The session is
saved in `./profile`, which is git-ignored. Never commit or share that folder.

Logs go to the terminal and `logs/bot.log`.

### Using your everyday Chrome instead (optional)

Close Chrome, then start it with a debugging port and a separate profile folder:

```shell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="$env:LOCALAPPDATA\LazadaBotChrome"
```

Log in to Lazada in that window, set `"cdp_url": "http://localhost:9222"` in `config.json`, and run the bot.

## Tests

```shell
pip install -r requirements-dev.txt
pytest
```

## Notes

- The detail API is Lazada-internal and can change without notice. If every check starts coming back
  `ERROR` / `NO_API`, open a product page with DevTools and compare against `bot/stock.py`.
- Request volume = products × rounds. At the defaults, 3 products is ~105 requests/min (~12,600 per
  2-hour window). Faster polling makes a captcha mid-drop more likely, and while you're solving one
  the bot isn't checking. Tune `interval_seconds` against how often you actually hit captchas.
