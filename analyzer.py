"""Формирование промтов и локальная оценка риска контрафакта для Telegram-бота."""

from __future__ import annotations

import re
from dataclasses import dataclass

SYSTEM_PROMPT = """Роль: Ты — эксперт по выявлению контрафактной продукции на маркетплейсах (Wildberries, Ozon, Kaspi). Твоя задача — анализировать входящие данные о товаре и выдавать вердикт о риске подделки.

Входные данные (тебе будут переданы):
- Ссылка на товар.
- Текущая цена (и средняя рыночная, если есть).
- Общий рейтинг и количество оценок.
- Текст последних 5-10 отзывов (особенно негативных).

Инструкция по анализу:
1) Цена: Если цена ниже рыночной на 40% и более — это высокий риск.
2) Отзывы: Ищи ключевые слова: «подделка», «реплика», «запах», «отличается упаковка», «не оригинал», «код не бьется».
3) Рейтинг: Огромное количество 5-звездочных отзывов без текста при наличии детальных жалоб на качество — признак «накрутки».

Формат ответа (строго по шаблону):
📊 Анализ завершён!
🧩 Риск подделки: [ЦВЕТОВОЙ ИНДИКАТОР] [УРОВЕНЬ РИСКА] ([ПРОЦЕНТ %])

[Краткое обоснование в 2-3 предложениях, почему сделан такой вывод. Укажи, на что именно обратить внимание: на подозрительную цену или жалобы в отзывах.]

Цветовые индикаторы:
- 🟢 НИЗКИЙ РИСК (0-30%)
- 🟡 СРЕДНИЙ РИСК (31-60%)
- 🔴 ВЫСОКИЙ РИСК (61-100%)"""

RISK_KEYWORDS = (
    "подделка",
    "реплика",
    "запах",
    "отличается упаковка",
    "не оригинал",
    "код не бьется",
)


@dataclass
class RiskResult:
    percentage: int
    label: str
    color: str
    reason: str

    def render(self) -> str:
        return (
            "📊 Анализ завершён!\n"
            f"🧩 Риск подделки: {self.color} {self.label} ({self.percentage}%)\n\n"
            f"{self.reason}"
        )


def build_user_prompt(
    title: str,
    price: float | None,
    rating: float | None,
    reviews: list[str],
    url: str,
    market_price: float | None = None,
    reviews_count: int | None = None,
) -> str:
    """Собирает пользовательский промт для LLM из данных парсинга."""
    price_part = f"{price:.0f} руб." if price is not None else "нет данных"
    rating_part = f"{rating:.1f}" if rating is not None else "нет данных"
    market_price_part = f"{market_price:.0f} руб." if market_price is not None else "нет данных"
    count_part = str(reviews_count) if reviews_count is not None else "нет данных"
    reviews_block = "\n- " + "\n- ".join(reviews[:10]) if reviews else "\n- нет текстовых отзывов"

    return (
        f"Проанализируй товар: {title}.\n"
        f"Ссылка: {url}.\n"
        f"Цена: {price_part}. Средняя рыночная цена: {market_price_part}.\n"
        f"Рейтинг: {rating_part}. Количество оценок: {count_part}.\n"
        f"Отзывы:{reviews_block}"
    )


def estimate_counterfeit_risk(
    *,
    price: float | None,
    market_price: float | None,
    rating: float | None,
    reviews_count: int | None,
    reviews: list[str],
) -> RiskResult:
    """Детерминированная эвристика риска на случай работы без LLM API."""
    score = 10
    reasons: list[str] = []

    if price is not None and market_price and market_price > 0:
        discount_pct = (1 - (price / market_price)) * 100
        if discount_pct >= 40:
            score += 45
            reasons.append("Цена ниже рыночной более чем на 40%, это сильный индикатор риска")
        elif discount_pct >= 25:
            score += 20
            reasons.append("Цена заметно ниже средней по рынку")

    negative_hits = 0
    for review in reviews:
        text = review.lower()
        if any(keyword in text for keyword in RISK_KEYWORDS):
            negative_hits += 1

    if negative_hits >= 3:
        score += 35
        reasons.append("В отзывах часто встречаются маркеры подделки")
    elif negative_hits > 0:
        score += 18
        reasons.append("В отзывах обнаружены отдельные жалобы на оригинальность")

    if rating is not None and reviews_count is not None:
        if rating >= 4.8 and reviews_count >= 500 and negative_hits > 0:
            score += 15
            reasons.append("Есть сочетание очень высокого рейтинга и жалоб — возможна накрутка")
        elif rating < 4.0:
            score += 10
            reasons.append("Низкий рейтинг усиливает подозрения по качеству")

    score = max(0, min(100, score))

    if score <= 30:
        color, label = "🟢", "НИЗКИЙ РИСК"
    elif score <= 60:
        color, label = "🟡", "СРЕДНИЙ РИСК"
    else:
        color, label = "🔴", "ВЫСОКИЙ РИСК"

    if not reasons:
        reasons.append("Явных признаков контрафакта по цене и отзывам не найдено")

    summary = ". ".join(reasons[:2]).strip()
    if not summary.endswith("."):
        summary += "."

    return RiskResult(percentage=score, label=label, color=color, reason=summary)


def extract_review_texts(latest_reviews: list[dict[str, object]]) -> list[str]:
    """Нормализует массив отзывов из парсеров к списку строк."""
    texts: list[str] = []
    for review in latest_reviews:
        text = review.get("text")
        if isinstance(text, str):
            normalized = re.sub(r"\s+", " ", text).strip()
            if normalized:
                texts.append(normalized)
    return texts
