"""Модуль парсеров маркетплейсов."""

from .kaspi import parse_kaspi
from .ozon import parse_ozon
from .wb import parse_wb

__all__ = ["parse_wb", "parse_ozon", "parse_kaspi"]
