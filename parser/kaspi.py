"""Парсер карточки товара Kaspi через Playwright."""

from __future__ import annotations

import random
import re
import time
from typing import Any

from playwright.sync_api import Browser, Error, Page, sync_playwright


class KaspiParserError(RuntimeError):
    """Базовая ошибка парсера Kaspi."""


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


def _rand_sleep(low: float = 1.0, high: float = 2.6) -> None:
    time.sleep(random.uniform(low, high))


def _scroll_page(page: Page, steps: int = 6) -> None:
    for _ in range(steps):
        page.mouse.wheel(0, 1000)
        _rand_sleep(0.4, 0.8)
    page.wait_for_timeout(1200)


def _extract_reviews(page: Page, limit: int = 10) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    cards = page.locator(".reviews__item").all()

    for card in cards[:limit]:
        text = card.locator(".reviews__text").first.inner_text(timeout=1500).strip() if card.locator(".reviews__text").count() else ""
        score = _to_int(card.locator(".rating__item_active").count().__str__())
        if text or score is not None:
            reviews.append({"text": text, "rating": score})

    return reviews


def _parse_with_browser(browser: Browser, url: str) -> dict[str, Any]:
    context = browser.new_context(locale="ru-RU")
    page = context.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=45_000)

    if "404" in page.url or "error" in page.url.lower():
        raise KaspiParserError("Товар не найден или страница недоступна.")

    _rand_sleep()
    _scroll_page(page)

    title = page.locator("h1").first.inner_text(timeout=5000).strip() if page.locator("h1").count() else None

    current_price = None
    for selector in [".item__price-once", ".item__price", "[data-test-id='defaultPrice']"]:
        if page.locator(selector).count():
            current_price = _to_float(page.locator(selector).first.inner_text(timeout=2000))
            if current_price is not None:
                break

    old_price = _to_float(page.locator(".item__price-old").first.inner_text(timeout=1500)) if page.locator(".item__price-old").count() else None

    rating = _to_float(page.locator(".rating__text").first.inner_text(timeout=1500)) if page.locator(".rating__text").count() else None
    reviews_count = _to_int(page.locator(".reviews__count").first.inner_text(timeout=1500)) if page.locator(".reviews__count").count() else None

    stock_text = ""
    for selector in [".item__availability", ".item__delivery", "button"]:
        if page.locator(selector).count():
            stock_text = page.locator(selector).first.inner_text(timeout=1500).strip()
            if stock_text:
                break
    in_stock = not bool(re.search(r"нет в наличии|распродан", stock_text.lower())) if stock_text else None

    reviews = _extract_reviews(page, limit=10)
    context.close()

    return {
        "marketplace": "kaspi",
        "url": url,
        "title": title,
        "current_price": current_price,
        "old_price": old_price,
        "rating": rating,
        "reviews_count": reviews_count,
        "latest_reviews": reviews,
        "in_stock": in_stock,
    }


def parse_kaspi(url: str, headless: bool = True) -> dict[str, Any]:
    """Парсит карточку товара Kaspi."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            try:
                return _parse_with_browser(browser, url)
            finally:
                browser.close()
    except Error as exc:
        raise KaspiParserError(f"Не удалось открыть страницу Kaspi: {exc}") from exc
