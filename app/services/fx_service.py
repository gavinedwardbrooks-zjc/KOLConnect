from __future__ import annotations

"""Local, manual foreign-exchange settings and fail-closed USD conversion."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable


SUPPORTED_CURRENCIES = (
    "USD", "CNY", "BRL", "EUR", "GBP", "JPY", "KRW", "HKD", "TWD", "SGD",
    "AUD", "CAD", "MXN", "SAR", "AED", "INR", "IDR", "THB", "VND", "PHP",
    "MYR", "TRY", "ZAR",
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class FxService:
    def __init__(self, state_provider: Callable[[], dict[str, Any]], save_state: Callable[[], None]) -> None:
        self._state_provider = state_provider
        self._save_state = save_state

    def list_rates(self) -> dict[str, Any]:
        state = self._state_provider()
        configured = state.get("fx", {}) if isinstance(state.get("fx"), dict) else {}
        raw_rates = configured.get("rates", {}) if isinstance(configured.get("rates"), dict) else {}
        rates = []
        for code in SUPPORTED_CURRENCIES:
            record = raw_rates.get(code, {}) if isinstance(raw_rates.get(code), dict) else {}
            rate = 1.0 if code == "USD" else self._valid_rate(record.get("rate_per_usd"))
            rates.append({"currency_code": code, "rate_per_usd": rate, "updated_at": record.get("updated_at") or "", "editable": code != "USD"})
        return {"base_currency": "USD", "rates": rates}

    def save_rates(self, values: object) -> dict[str, Any]:
        if not isinstance(values, dict):
            raise ValueError("汇率必须为对象。")
        state = self._state_provider()
        fx = state.setdefault("fx", {})
        rates = fx.setdefault("rates", {})
        now = _timestamp()
        for code, raw in values.items():
            normalized = str(code or "").strip().upper()
            if normalized not in SUPPORTED_CURRENCIES:
                raise ValueError("不支持的币种。")
            if normalized == "USD":
                continue
            rate = self._require_rate(raw)
            rates[normalized] = {"rate_per_usd": rate, "updated_at": now}
        self._save_state()
        return self.list_rates()

    def convert_to_usd(self, amount: object, currency: object) -> float | None:
        if amount is None or str(amount).strip() == "":
            return None
        try:
            value = Decimal(str(amount).strip())
        except InvalidOperation:
            return None
        if not value.is_finite():
            return None
        code = str(currency or "").strip().upper()
        if code not in SUPPORTED_CURRENCIES:
            return None
        if code == "USD":
            return float(value)
        configured = self._state_provider().get("fx", {})
        raw_rates = configured.get("rates", {}) if isinstance(configured, dict) else {}
        entry = raw_rates.get(code, {}) if isinstance(raw_rates, dict) else {}
        rate = self._valid_rate(entry.get("rate_per_usd") if isinstance(entry, dict) else None)
        return float(value / Decimal(str(rate))) if rate else None

    @staticmethod
    def _valid_rate(value: object) -> float | None:
        try:
            rate = Decimal(str(value).strip())
        except (InvalidOperation, AttributeError):
            return None
        return float(rate) if rate.is_finite() and rate > 0 else None

    @classmethod
    def _require_rate(cls, value: object) -> float:
        rate = cls._valid_rate(value)
        if rate is None:
            raise ValueError("汇率必须是大于 0 的数字。")
        return rate
