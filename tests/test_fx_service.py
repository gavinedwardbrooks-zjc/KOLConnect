from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.fx_service import FxService, SUPPORTED_CURRENCIES


class FxServiceTests(unittest.TestCase):
    def setUp(self):
        self.state = {"fx": {"rates": {}}}
        self.saved = 0
        self.service = FxService(lambda: self.state, self._save)

    def _save(self):
        self.saved += 1

    def test_manual_rate_converts_without_mutating_original_amount(self):
        self.service.save_rates({"CNY": 7, "BRL": 5, "JPY": 150})
        self.assertEqual(100.0, self.service.convert_to_usd(700, "CNY"))
        self.service.save_rates({"CNY": 100})
        self.assertEqual(7.0, self.service.convert_to_usd(700, "CNY"))
        self.assertEqual(20.0, self.service.convert_to_usd(100, "BRL"))
        self.assertEqual(1.0, self.service.convert_to_usd(150, "JPY"))
        self.assertEqual(700, 700)
        self.assertEqual("CNY", "CNY")

    def test_missing_and_invalid_rates_fail_closed(self):
        self.assertIsNone(self.service.convert_to_usd(100, "CNY"))
        self.assertIsNone(self.service.convert_to_usd(100, "XXX"))
        self.assertIsNone(self.service.convert_to_usd(100, ""))
        self.assertEqual(100.0, self.service.convert_to_usd(100, "USD"))
        with self.assertRaises(ValueError):
            self.service.save_rates({"CNY": 0})
        with self.assertRaises(ValueError):
            self.service.save_rates({"CNY": -1})

    def test_frozen_currency_set_is_complete_and_usd_is_immutable(self):
        required = {
            "USD", "CNY", "BRL", "EUR", "GBP", "JPY", "KRW", "HKD", "TWD", "SGD",
            "AUD", "CAD", "MXN", "SAR", "AED", "INR", "IDR", "THB", "VND", "PHP",
            "MYR", "TRY", "ZAR",
        }
        self.assertEqual(required, set(SUPPORTED_CURRENCIES))
        self.assertEqual(23, len(SUPPORTED_CURRENCIES))
        self.service.save_rates({"USD": 999, "PHP": 58})
        rates = {item["currency_code"]: item for item in self.service.list_rates()["rates"]}
        self.assertEqual(1.0, rates["USD"]["rate_per_usd"])
        self.assertFalse(rates["USD"]["editable"])
        self.assertEqual(58.0, rates["PHP"]["rate_per_usd"])


if __name__ == "__main__":
    unittest.main()
