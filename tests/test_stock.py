from bot.stock import Status, canonical_product_url, classify

# Modelled on live getDetailInfo results for the two products (Oct 2026).
IN_STOCK = {
    "kind": "ok",
    "ret": ["SUCCESS::调用成功"],
    "title": "Pokémon Center Original Plush Lunar New Year Pikachu Female",
    "skuId": "23932762661",
    "operations": [
        {"text": "Buy Now", "type": "buyNow", "disable": False},
        {"text": "Add to Cart", "type": "default", "disable": False},
    ],
    "maxQty": 34,
}
OUT_OF_STOCK = {
    "kind": "ok",
    "ret": ["SUCCESS::调用成功"],
    "title": "30th Celebration Pokémon Center Elite Trainer Box",
    "skuId": "124858765958",
    "operations": [{"text": "Add to Wishlist", "type": "wishlist", "disable": False}],
    "maxQty": 0,
}


def test_in_stock():
    r = classify(IN_STOCK)
    assert r.status is Status.IN_STOCK
    assert r.max_qty == 34


def test_out_of_stock():
    assert classify(OUT_OF_STOCK).status is Status.OUT_OF_STOCK


def test_disabled_buy_now_is_not_in_stock():
    raw = {**IN_STOCK, "operations": [{"text": "Buy Now", "type": "buyNow", "disable": True}]}
    assert classify(raw).status is Status.OUT_OF_STOCK


def test_zero_quantity_is_not_in_stock():
    assert classify({**IN_STOCK, "maxQty": 0}).status is Status.OUT_OF_STOCK


def test_anti_bot_codes_are_blocked():
    for ret in (["RGV587_ERROR::SM::哎哟喂,被挤爆啦"], ["FAIL_SYS_USER_VALIDATE::..."]):
        assert classify({"kind": "mtop_error", "ret": ret}).status is Status.BLOCKED


def test_missing_mtop_and_errors():
    assert classify({"kind": "no_mtop"}).status is Status.NO_API
    assert classify({"kind": "timeout"}).status is Status.ERROR


def test_canonical_url_drops_query():
    url = "https://www.lazada.sg/products/pdp-i3622415916-s23932762661.html?spm=abc&search=store"
    assert canonical_product_url(url) == "https://www.lazada.sg/products/pdp-i3622415916-s23932762661.html"
