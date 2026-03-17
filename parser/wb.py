"""Парсер карточки товара Wildberries через Playwright."""

from __future__ import annotations

import random
import re
import time
from typing import Any

from playwright.sync_api import Browser, Error, Page, sync_playwright


class WbParserError(RuntimeError):
    """Базовая ошибка парсера Wildberries."""


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


def _rand_sleep(low: float = 0.7, high: float = 2.2) -> None:
    """Случайная задержка для снижения вероятности блокировки."""
    time.sleep(random.uniform(low, high))


def _scroll_page(page: Page, steps: int = 5) -> None:
    """Плавный скролл для догрузки динамических блоков."""
    for step in range(steps):
        page.mouse.wheel(0, 900)
        _rand_sleep(0.4, 0.9)
        # Дополнительное ожидание после последних шагов.
        if step == steps - 1:
            page.wait_for_timeout(1200)


def _extract_reviews(page: Page, limit: int = 10) -> list[dict[str, Any]]:
    """Собирает последние отзывы (текст + оценка)."""
    reviews: list[dict[str, Any]] = []
    cards = page.locator(".comments__item").all() or page.locator("[data-link*='review']").all()

    for card in cards[:limit]:
        text = card.locator(".feedback__text").inner_text(timeout=1200) if card.locator(".feedback__text").count() else ""
        if not text and card.locator(".comment__text").count():
            text = card.locator(".comment__text").inner_text(timeout=1200)

        score = None
        if card.locator(".feedback__rating").count():
            score = _to_int(card.locator(".feedback__rating").inner_text(timeout=1200))
        elif card.locator("[aria-label*='оценка']").count():
            score = _to_int(card.locator("[aria-label*='оценка']").first.get_attribute("aria-label"))

        if text.strip() or score is not None:
            reviews.append({"text": text.strip(), "rating": score})

    return reviews


def _parse_with_browser(browser: Browser, url: str) -> dict[str, Any]:
    context = browser.new_context(locale="ru-RU")
    page = context.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=45_000)

    if "404" in page.url or "not-found" in page.url:
        raise WbParserError("Товар не найден (404).")

    _rand_sleep()
    _scroll_page(page)

    title = page.locator("h1").first.inner_text(timeout=5000).strip() if page.locator("h1").count() else None
    current_price = None
    for selector in [".price-block__final-price", ".price-block__wallet-price", "ins.price-block__final-price"]:
        if page.locator(selector).count():
            current_price = _to_float(page.locator(selector).first.inner_text(timeout=2000))
            if current_price is not None:
                break

    old_price = None
    for selector in [".price-block__old-price", "del.price-block__old-price"]:
        if page.locator(selector).count():
            old_price = _to_float(page.locator(selector).first.inner_text(timeout=2000))
            if old_price is not None:
                break

    rating = _to_float(page.locator(".product-review__rating").first.inner_text(timeout=1200)) if page.locator(".product-review__rating").count() else None
    reviews_count = _to_int(page.locator(".product-review__count-review").first.inner_text(timeout=1200)) if page.locator(".product-review__count-review").count() else None

    stock_text = ""
    for selector in [".product-order__quantity", ".product-order__button", ".sold-out-product"]:
        if page.locator(selector).count():
            stock_text = page.locator(selector).first.inner_text(timeout=1500).strip()
            if stock_text:
                break
    in_stock = not bool(re.search(r"нет в наличии|распродан", stock_text.lower())) if stock_text else None

    reviews = _extract_reviews(page, limit=10)
    context.close()

    return {
        "marketplace": "wildberries",
        "url": url,
        "title": title,
        "current_price": current_price,
        "old_price": old_price,
        "rating": rating,
        "reviews_count": reviews_count,
        "latest_reviews": reviews,
        "in_stock": in_stock,
    }


def parse_wb(url: str, headless: bool = True) -> dict[str, Any]:
    """Парсит карточку товара на Wildberries."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            try:
                return _parse_with_browser(browser, url)
            finally:
                browser.close()
    except Error as exc:
        raise WbParserError(f"Не удалось открыть страницу WB: {exc}") from exc
