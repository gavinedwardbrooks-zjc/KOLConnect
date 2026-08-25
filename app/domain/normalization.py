from __future__ import annotations

"""Pure normalization helpers shared by storage, analytics, and assistants."""

import math
import re
from typing import Any


_MISSING_VALUES = {"", "--", "n/a", "unknown", "null", "none"}
_COUNTRIES = {
    "BR": ("BRA", "Brazil", "Brasil", "巴西"),
    "US": ("USA", "United States", "United States of America", "美国"),
    "MX": ("MEX", "Mexico", "México", "墨西哥"),
    "AR": ("ARG", "Argentina", "阿根廷"),
    "CL": ("CHL", "Chile", "智利"),
    "CO": ("COL", "Colombia", "哥伦比亚"),
    "PE": ("PER", "Peru", "Perú", "秘鲁"),
    "ES": ("ESP", "Spain", "España", "西班牙"),
    "PT": ("PRT", "Portugal", "葡萄牙"),
    "GB": ("GBR", "United Kingdom", "UK", "英国"),
    "FR": ("FRA", "France", "法国"),
    "DE": ("DEU", "Germany", "Deutschland", "德国"),
    "IT": ("ITA", "Italy", "Italia", "意大利"),
    "JP": ("JPN", "Japan", "日本"),
    "KR": ("KOR", "South Korea", "Korea", "韩国"),
    "CN": ("CHN", "China", "中国"),
    "TW": ("TWN", "Taiwan", "台湾"),
    "HK": ("HKG", "Hong Kong", "香港"),
    "SG": ("SGP", "Singapore", "新加坡"),
    "ID": ("IDN", "Indonesia", "印度尼西亚", "印尼"),
    "TH": ("THA", "Thailand", "泰国"),
    "VN": ("VNM", "Vietnam", "越南"),
    "PH": ("PHL", "Philippines", "菲律宾"),
    "MY": ("MYS", "Malaysia", "马来西亚"),
    "IN": ("IND", "India", "印度"),
    "CA": ("CAN", "Canada", "加拿大"),
    "AU": ("AUS", "Australia", "澳大利亚"),
}


def _country_key(value: object) -> str:
    return re.sub(r"[\s._-]+", " ", str(value or "").strip()).casefold()


_COUNTRY_ALIASES = {
    _country_key(alias): code
    for code, aliases in _COUNTRIES.items()
    for alias in (code, *aliases)
}


def normalize_country(value: object) -> str | None:
    """Return a recognized ISO alpha-2 identity without guessing regions."""
    key = _country_key(value)
    return None if not key or key in _MISSING_VALUES else _COUNTRY_ALIASES.get(key)


def extract_country(value: object) -> str | None:
    """Find one unambiguous supported country alias in natural-language text."""
    text = str(value or "").casefold()
    matches = {
        code
        for alias, code in _COUNTRY_ALIASES.items()
        if (re.fullmatch(r"[a-z]{2,3}", alias) and re.search(rf"\b{re.escape(alias)}\b", text))
        or (not re.fullmatch(r"[a-z]{2,3}", alias) and alias in _country_key(text))
    }
    return next(iter(matches)) if len(matches) == 1 else None


def normalize_number(value: object, *, integer: bool = False) -> float | int | None:
    """Normalize a non-negative finite number, including K/M/B shorthand."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        raw = str(value).strip()
        if raw.casefold() in _MISSING_VALUES:
            return None
        match = re.fullmatch(
            r"([0-9]+(?:\.[0-9]+)?)\s*([kKmMbB])?",
            raw.replace(",", ""),
        )
        if not match:
            return None
        multiplier = {
            "": 1,
            "k": 1_000,
            "m": 1_000_000,
            "b": 1_000_000_000,
        }[(match.group(2) or "").casefold()]
        number = float(match.group(1)) * multiplier
    if not math.isfinite(number) or number < 0:
        return None
    if integer:
        return int(round(number)) if number.is_integer() else None
    return int(number) if number.is_integer() else number


def normalize_followers(value: object) -> int | None:
    number = normalize_number(value)
    if number is None:
        return None
    amount = float(number)
    return int(amount) if amount.is_integer() else None


def format_compact_number(value: object) -> str:
    number = normalize_number(value)
    if number is None:
        return "--"
    amount = float(number)
    for suffix, divisor in (("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)):
        if amount >= divisor:
            rendered = f"{amount / divisor:.2f}".rstrip("0").rstrip(".")
            return f"{rendered}{suffix}"
    return str(int(amount)) if amount.is_integer() else str(amount)


def normalize_tags(value: Any) -> list[str]:
    values = value if isinstance(value, (list, tuple, set)) else re.split(r"[,，]", str(value or ""))
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        tag = str(item or "").strip()
        key = tag.casefold()
        if tag and key not in seen:
            result.append(tag)
            seen.add(key)
    return result
