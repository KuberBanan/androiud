# Marketplace Parser (Wildberries / Ozon / Kaspi)

Парсер карточек товаров с маркетплейсов **без официальных API** (только парсинг страниц через Playwright).

## Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Пример запуска

### Разовый парсинг

```bash
python main.py "https://www.wildberries.ru/catalog/123456/detail.aspx"
```

### Режим с видимым браузером (headless off)

```bash
python main.py --headed "https://www.ozon.ru/product/..."
```

### Добавить товар в отслеживание и сразу запустить мониторинг каждые 30 минут

```bash
python main.py /track "https://kaspi.kz/shop/p/..."
```

### Запустить только цикл мониторинга для уже сохраненных товаров

```bash
python main.py --track
```

## Формат JSON ответа

```json
{
  "marketplace": "wildberries",
  "url": "...",
  "title": "Название",
  "current_price": 15990.0,
  "old_price": 17990.0,
  "rating": 4.8,
  "reviews_count": 125,
  "latest_reviews": [
    {"text": "Хороший товар", "rating": 5}
  ],
  "in_stock": true
}
```

## Уведомления при изменении цены

По умолчанию уведомления выводятся в консоль.

Опционально можно отправлять в Telegram:

```bash
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
```
