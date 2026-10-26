"""
Lightweight stock check via Lazada's own product-detail API.

Product pages fill in live stock with `mtop.global.detail.web.getDetailInfo`.
Lazada's page script `window.Mtop.default.request` signs these calls, so any open
lazada.sg product tab can ask about any product without loading its page.
"""
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlsplit

# Runs inside the page. Checks all URLs concurrently and returns one small summary per
# URL instead of the ~90KB module JSON. Lazada's page enables mtop's syncCookieMode,
# which keeps concurrent requests correctly signed.
STOCK_CHECK_JS = """
async ({urls, timeoutMs}) => {
  if (!window.Mtop || !window.Mtop.default || !window.Mtop.default.request) {
    return urls.map(() => ({kind: 'no_mtop'}));
  }
  const cookieParams = {};
  for (const item of document.cookie.split('; ')) {
    const i = item.indexOf('=');
    if (i > 0) cookieParams[item.slice(0, i)] = item.slice(i + 1);
  }
  const checkOne = (url) => new Promise((resolve) => {
    const u = new URL(url);
    const m = u.pathname.match(/\\/([\\w-]+)\\.html/);
    const uri = m ? m[1] : '';
    const timer = setTimeout(() => resolve({kind: 'timeout'}), timeoutMs);
    const done = (r) => { clearTimeout(timer); resolve(r); };
    window.Mtop.default.request({
      api: 'mtop.global.detail.web.getDetailInfo',
      v: '1.0',
      type: 'POST',
      needLogin: false,
      data: {
        deviceType: 'pc',
        path: u.origin + u.pathname,
        uri: uri,
        headerParams: JSON.stringify({'user-agent': navigator.userAgent}),
        cookieParams: JSON.stringify(cookieParams),
        requestParams: JSON.stringify({}),
      },
    }, (res) => {
      let f;
      try {
        f = JSON.parse(res.data.module);
      } catch (e) {
        return done({kind: 'bad_response', ret: res && res.ret, error: String(e)});
      }
      const skuId = f.primaryKey && f.primaryKey.skuId;
      const skus = f.skuInfos || {};
      const sku = skus[skuId] || skus['0'] || null;
      const ops = sku ? (sku.operations || (sku.operation ? [sku.operation] : [])) : [];
      done({
        kind: 'ok',
        ret: res.ret,
        title: f.product && f.product.title,
        skuId: skuId,
        operations: ops.map((o) => ({text: o.text, type: o.type, disable: !!o.disable})),
        maxQty: sku && sku.quantity && sku.quantity.limit ? sku.quantity.limit.max : null,
      });
    }, (err) => done({kind: 'mtop_error', ret: err && err.ret}));
  });
  return await Promise.all(urls.map(checkOne));
}
"""

# mtop return codes that mean Alibaba's anti-bot layer wants a human check.
BLOCKED_MARKERS = ("RGV587", "USER_VALIDATE", "PUNISH", "DENY")


class Status(Enum):
    IN_STOCK = "IN_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    BLOCKED = "BLOCKED"  # captcha / slider required
    NO_API = "NO_API"  # poll tab isn't a ready product page
    ERROR = "ERROR"


@dataclass
class StockResult:
    status: Status
    title: str | None = None
    max_qty: int | None = None
    buttons: list[str] = field(default_factory=list)
    detail: str = ""


def canonical_product_url(url: str) -> str:
    """Drop query strings/tracking so each check sends only the product path."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def classify(raw: dict) -> StockResult:
    kind = raw.get("kind")
    ret = " ".join(raw.get("ret") or [])

    if any(marker in ret.upper() for marker in BLOCKED_MARKERS):
        return StockResult(Status.BLOCKED, detail=ret)
    if kind == "no_mtop":
        return StockResult(Status.NO_API, detail="window.Mtop not available on poll tab")
    if kind != "ok":
        return StockResult(Status.ERROR, detail=f"{kind}: {ret or raw.get('error', '')}".strip())

    ops = raw.get("operations") or []
    buttons = [f"{o.get('text')}{' (disabled)' if o.get('disable') else ''}" for o in ops]
    max_qty = raw.get("maxQty")
    can_buy = any(
        (o.get("type") == "buyNow" or (o.get("text") or "").lower() == "buy now") and not o.get("disable")
        for o in ops
    )
    in_stock = can_buy and (max_qty is None or max_qty > 0)
    return StockResult(
        Status.IN_STOCK if in_stock else Status.OUT_OF_STOCK,
        title=raw.get("title"),
        max_qty=max_qty,
        buttons=buttons,
    )


def check_stock(page, product_urls: list[str], timeout_ms: int = 5_000) -> list[StockResult]:
    """Check every URL in parallel; results come back in the same order."""
    try:
        raws = page.evaluate(STOCK_CHECK_JS, {"urls": product_urls, "timeoutMs": timeout_ms})
    except Exception as e:  # page navigated, crashed, etc.
        return [StockResult(Status.ERROR, detail=f"evaluate failed: {e}") for _ in product_urls]
    return [classify(raw) for raw in raws]
