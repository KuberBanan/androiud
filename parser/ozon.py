"""Парсер карточки товара Ozon через Playwright."""

from __future__ import annotations

import random
import re
import time
from typing import Any

from playwright.sync_api import Browser, Error, Page, sync_playwright


class OzonParserError(RuntimeError):
    """Базовая ошибка парсера Ozon."""


def _to_float(value: str | None) -> float | None:
    if not value:
        return None
    cleaned = re.sub(r"[^\d,.]", "", value).replace(" ", "").replace(",", ".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _to_int(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    return int(digits) if digits else None


def _rand_sleep(low: float = 0.8, high: float = 2.4) -> None:
    time.sleep(random.uniform(low, high))


def _scroll_page(page: Page, steps: int = 6) -> None:
    for _ in range(steps):
        page.mouse.wheel(0, 1100)
        _rand_sleep(0.4, 1.0)
    page.wait_for_timeout(1400)


def _extract_reviews(page: Page, limit: int = 10) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    cards = page.locator("[data-widget='webReviewCollection'] article").all()
    if not cards:
        cards = page.locator("article[data-review-uuid]").all()

    for card in cards[:limit]:
        text = ""
        score = None

        if card.locator("[data-widget='webReviewText']").count():
            text = card.locator("[data-widget='webReviewText']").first.inner_text(timeout=1500)
        elif card.locator("div[role='paragraph']").count():
            text = card.locator("div[role='paragraph']").first.inner_text(timeout=1500)

        if card.locator("[aria-label*='из 5']").count():
            score = _to_int(card.locator("[aria-label*='из 5']").first.get_attribute("aria-label"))

        if text.strip() or score is not None:
            reviews.append({"text": text.strip(), "rating": score})

    return reviews


def _parse_with_browser(browser: Browser, url: str) -> dict[str, Any]:
    context = browser.new_context(locale="ru-RU")
    page = context.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=45_000)

    if "404" in page.url or "error" in page.url.lower():
        raise OzonParserError("Товар не найден или страница недоступна.")

    _rand_sleep()
    _scroll_page(page)

    title = page.locator("h1").first.inner_text(timeout=5000).strip() if page.locator("h1").count() else None

    current_price = None
    for selector in ["[data-widget='webPrice']", "[data-widget='webSale']", "[data-widget='webStickyProductPrice']"]:
        if page.locator(selector).count():
            text = page.locator(selector).first.inner_text(timeout=2000)
            current_price = _to_float(text)
            if current_price is not None:
                break

    old_price = None
    for selector in ["[data-widget='webPrice'] del", "[data-widget='webSale'] del"]:
        if page.locator(selector).count():
            old_price = _to_float(page.locator(selector).first.inner_text(timeout=1500))
            if old_price is not None:
                break

    rating = _to_float(page.locator("[data-widget='webSingleProductScore']").first.inner_text(timeout=1500)) if page.locator("[data-widget='webSingleProductScore']").count() else None
    reviews_count = _to_int(page.locator("[data-widget='webReviewProductScore']").first.inner_text(timeout=1500)) if page.locator("[data-widget='webReviewProductScore']").count() else None

    stock_text = ""
    for selector in ["[data-widget='webAddToCart']", "button[aria-label*='Корзин']", "[data-widget='webOutOfStock']"]:
        if page.locator(selector).count():
            stock_text = page.locator(selector).first.inner_text(timeout=1500).strip()
            if stock_text:
                break

    in_stock = not bool(re.search(r"нет в наличии|распродан", stock_text.lower())) if stock_text else None

    reviews = _extract_reviews(page, limit=10)
    context.close()

    return {
        "marketplace": "ozon",
        "url": url,
        "title": title,
        "current_price": current_price,
        "old_price": old_price,
        "rating": rating,
        "reviews_count": reviews_count,
        "latest_reviews": reviews,
        "in_stock": in_stock,
    }


def parse_ozon(url: str, headless: bool = True) -> dict[str, Any]:
    """Парсит карточку товара Ozon."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            try:
                return _parse_with_browser(browser, url)
            finally:
                browser.close()
    except Error as exc:
        raise OzonParserError(f"Не удалось открыть страницу Ozon: {exc}") from exc
