"""CLI для парсинга и отслеживания цен товаров на Wildberries, Ozon и Kaspi."""

from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from parser import parse_kaspi, parse_ozon, parse_wb

DB_PATH = Path("tracked_items.db")
CHECK_INTERVAL_SEC = 30 * 60


@dataclass
class Item:
    url: str
    marketplace: str
    last_price: float | None
    headless: bool


def detect_marketplace(url: str) -> str:
    url_lower = url.lower()
    if "wildberries" in url_lower or "wb.ru" in url_lower:
        return "wildberries"
    if "ozon" in url_lower:
        return "ozon"
    if "kaspi" in url_lower:
        return "kaspi"
    raise ValueError("Неподдерживаемый маркетплейс. Используйте Wildberries, Ozon или Kaspi.")


def get_parser(marketplace: str) -> Callable[[str, bool], dict[str, Any]]:
    parsers: dict[str, Callable[[str, bool], dict[str, Any]]] = {
        "wildberries": parse_wb,
        "ozon": parse_ozon,
        "kaspi": parse_kaspi,
    }
    return parsers[marketplace]


def parse_product(url: str, headless: bool = True) -> dict[str, Any]:
    marketplace = detect_marketplace(url)
    parser = get_parser(marketplace)
    return parser(url, headless=headless)


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tracked_items (
                url TEXT PRIMARY KEY,
                marketplace TEXT NOT NULL,
                last_price REAL,
                headless INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.commit()


def add_tracking_item(url: str, headless: bool = True) -> Item:
    result = parse_product(url, headless=headless)
    item = Item(
        url=url,
        marketplace=result["marketplace"],
        last_price=result.get("current_price"),
        headless=headless,
    )
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO tracked_items(url, marketplace, last_price, headless) VALUES(?, ?, ?, ?)",
            (item.url, item.marketplace, item.last_price, 1 if headless else 0),
        )
        conn.commit()
    return item


def load_tracking_items() -> list[Item]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT url, marketplace, last_price, headless FROM tracked_items").fetchall()
    return [Item(url=row[0], marketplace=row[1], last_price=row[2], headless=bool(row[3])) for row in rows]


def update_last_price(url: str, new_price: float | None) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE tracked_items SET last_price = ? WHERE url = ?", (new_price, url))
        conn.commit()


def send_notification(message: str) -> None:
    """Отправляет уведомление в консоль и опционально в Telegram."""
    print(f"\n[NOTIFY] {message}")

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not (bot_token and chat_id):
        return

    endpoint = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
    request = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(request, timeout=10)
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] Не удалось отправить уведомление в Telegram: {exc}")


def tracking_loop() -> None:
    print("Запущен режим отслеживания. Проверка цен каждые 30 минут...")
    while True:
        items = load_tracking_items()
        if not items:
            print("Нет товаров для отслеживания. Добавьте товар командой /track <url>.")
        for item in items:
            try:
                result = parse_product(item.url, headless=item.headless)
                current_price = result.get("current_price")
                if current_price != item.last_price:
                    send_notification(
                        f"Цена изменилась: {result.get('title') or item.url}\n"
                        f"Было: {item.last_price} -> Стало: {current_price}\n"
                        f"Ссылка: {item.url}"
                    )
                    update_last_price(item.url, current_price)
                else:
                    print(f"[OK] Без изменений: {item.url} ({current_price})")
            except Exception as exc:  # noqa: BLE001
                print(f"[ERROR] Ошибка проверки {item.url}: {exc}")

            # Случайная задержка между товарами.
            time.sleep(random.uniform(2.0, 5.0))

        print("Ожидание до следующего цикла...")
        time.sleep(CHECK_INTERVAL_SEC)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Парсинг карточек Wildberries/Ozon/Kaspi и отслеживание цены. "
            "Для трекинга также поддерживается команда /track <url>."
        )
    )
    parser.add_argument("target", nargs="?", help="Ссылка на товар или команда /track")
    parser.add_argument("url", nargs="?", help="Ссылка на товар для /track")
    parser.add_argument("--headed", action="store_true", help="Запустить браузер в видимом режиме (headless=False)")
    parser.add_argument("--track", action="store_true", help="Запустить бесконечный цикл отслеживания уже сохраненных товаров")
    return parser


def main() -> None:
    init_db()
    args = build_arg_parser().parse_args()
    headless = not args.headed

    # Режим: python main.py /track <url>
    if args.target == "/track":
        if not args.url:
            raise ValueError("Использование: python main.py /track <url>")
        item = add_tracking_item(args.url, headless=headless)
        print(f"Товар добавлен в отслеживание: {item.url}")
        print("Запускаю мониторинг каждые 30 минут...")
        tracking_loop()
        return

    # Режим: python main.py --track
    if args.track:
        tracking_loop()
        return

    # Режим: python main.py <url>
    if not args.target:
        raise ValueError("Передайте ссылку на товар или используйте /track.")

    result = parse_product(args.target, headless=headless)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nОстановлено пользователем.")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        sys.exit(1)
