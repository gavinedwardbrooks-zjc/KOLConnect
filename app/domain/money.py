from __future__ import annotations

"""Small monetary identity helpers for recorded Campaign cooperation amounts."""

from decimal import Decimal, InvalidOperation
import re
from typing import Any, Iterable


CURRENCY_CODE_PATTERN = re.compile(r"^[A-Z]{3}$")
QUOTE_UNITS = frozenset({"video", "post", "reel", "short", "story", "package", "other"})
STRUCTURED_QUOTE_FIELDS = (
    "quote_currency",
    "quote_unit_amount",
    "quote_quantity",
    "quote_unit",
)


def optional_decimal(value: object, label: str) -> Decimal | None:
    text = str(value if value is not None else "").strip().replace(",", "")
    if not text:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{label}必须是数字。") from exc
    if not number.is_finite() or number < 0:
        raise ValueError(f"{label}不能为负数。")
    return number


def currency_code(value: object, label: str, *, required: bool = False) -> str:
    code = str(value or "").strip().upper()
    if not code and not required:
        return ""
    if not CURRENCY_CODE_PATTERN.fullmatch(code):
        raise ValueError(f"{label}必须为 ISO 4217 三字母代码。")
    return code


def quote_unit(value: object, *, required: bool = False) -> str:
    unit = str(value or "").strip().lower()
    if not unit and not required:
        return ""
    if unit not in QUOTE_UNITS:
        raise ValueError("计价单位无效。")
    return unit


def positive_quantity(value: object, *, required: bool = False) -> int | str:
    text = str(value if value is not None else "").strip()
    if not text and not required:
        return ""
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("报价数量必须是正整数。") from exc
    if not number.is_finite() or number <= 0 or number != number.to_integral_value():
        raise ValueError("报价数量必须是正整数。")
    return int(number)


def normalized_number(number: Decimal | None) -> float | str:
    return "" if number is None else float(number)


def apply_quote_contract(payload: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    """Return monetary fields with structured quote consistency enforced."""
    merged = {field: payload.get(field, existing.get(field, "")) for field in STRUCTURED_QUOTE_FIELDS}
    structured_requested = any(field in payload for field in STRUCTURED_QUOTE_FIELDS)
    structured_present = any(str(merged.get(field) or "").strip() for field in STRUCTURED_QUOTE_FIELDS)
    values: dict[str, Any] = {}

    if structured_present:
        currency = currency_code(merged["quote_currency"], "报价币种", required=True)
        amount = optional_decimal(merged["quote_unit_amount"], "报价单价")
        quantity = positive_quantity(merged["quote_quantity"], required=True)
        unit = quote_unit(merged["quote_unit"], required=True)
        if amount is None:
            raise ValueError("报价单价不能为空。")
        total = amount * Decimal(quantity)
        supplied_total = optional_decimal(payload.get("creator_quote"), "达人报价") if "creator_quote" in payload else None
        if supplied_total is not None and supplied_total != total:
            raise ValueError("达人报价总额必须等于报价单价乘以数量。")
        values.update({
            "quote_currency": currency,
            "quote_unit_amount": normalized_number(amount),
            "quote_quantity": quantity,
            "quote_unit": unit,
            "creator_quote": normalized_number(total),
        })
    elif structured_requested:
        values.update({field: "" for field in STRUCTURED_QUOTE_FIELDS})
        if "creator_quote" in payload:
            values["creator_quote"] = normalized_number(
                optional_decimal(payload.get("creator_quote"), "达人报价")
            )
    elif "creator_quote" in payload:
        values["creator_quote"] = normalized_number(
            optional_decimal(payload.get("creator_quote"), "达人报价")
        )

    quote_currency_value = values.get("quote_currency", existing.get("quote_currency", ""))
    if "cost_currency" in payload:
        values["cost_currency"] = currency_code(payload.get("cost_currency"), "成本币种")
    if "cost" in payload:
        cost = optional_decimal(payload.get("cost"), "合作成本")
        values["cost"] = normalized_number(cost)
        if cost is not None and not str(values.get("cost_currency", existing.get("cost_currency", "")) or "").strip():
            if quote_currency_value:
                values["cost_currency"] = str(quote_currency_value)
            elif "cost_currency" in payload:
                raise ValueError("合作成本必须包含币种。")
    return values


def grouped_amounts(
    rows: Iterable[dict[str, Any]], amount_field: str, currency_field: str
) -> dict[str, Any]:
    """Group monetary totals; never combine known unlike currencies."""
    totals: dict[str, Decimal] = {}
    unknown = Decimal(0)
    unknown_count = 0
    for row in rows:
        try:
            amount = optional_decimal(row.get(amount_field), amount_field)
        except ValueError:
            continue
        if amount is None:
            continue
        code = str(row.get(currency_field) or "").strip().upper()
        if CURRENCY_CODE_PATTERN.fullmatch(code):
            totals[code] = totals.get(code, Decimal(0)) + amount
        else:
            unknown += amount
            unknown_count += 1
    groups = {code: float(totals[code]) for code in sorted(totals)}
    mixed = len(totals) > 1 or (bool(totals) and unknown_count > 0)
    if mixed:
        scalar = None
    elif totals:
        scalar = float(next(iter(totals.values())))
    else:
        scalar = float(unknown)
    return {
        "total": scalar,
        "totals_by_currency": groups,
        "unknown_currency_total": float(unknown) if unknown_count else None,
        "multiple_currencies": mixed,
    }
