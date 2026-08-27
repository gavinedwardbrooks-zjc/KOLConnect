import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from http_handlers import settings_handler


def normalize_account(account):
    return {
        "name": str(account.get("name") or "").strip(),
        "password": str(account.get("password") or ""),
    }


def normalize_mail_state(raw_mail):
    raw_mail = raw_mail or {}
    accounts = raw_mail.get("accounts")
    if not isinstance(accounts, list):
        return {"accounts": [], "template_subject": "", "template_body": ""}
    return {
        "accounts": [normalize_account(account) for account in accounts if isinstance(account, dict)],
        "template_subject": str(raw_mail.get("template_subject") or ""),
        "template_body": str(raw_mail.get("template_body") or ""),
    }


def merge_masked_mail_passwords(payload, _existing):
    return copy.deepcopy(payload)


class FakeHandler:
    def __init__(self):
        self.response = None

    def _ok(self, **payload):
        self.response = {"ok": True, **payload}


class MailPartialUpdateTests(unittest.TestCase):
    def setUp(self):
        self.state = {
            "mail": {
                "accounts": [{"name": "Account A", "password": "secret-a"}],
                "template_subject": "Subject T1",
                "template_body": "Body T1",
            }
        }
        self.save_count = 0
        self.services = {
            "normalize_mail_state": normalize_mail_state,
            "merge_masked_mail_passwords": merge_masked_mail_passwords,
        }

    def update(self, payload):
        request = {
            "method": "POST",
            "path": "/api/settings/mail",
            "get_payload": lambda: copy.deepcopy(payload),
        }
        context = {
            "state": {
                "get": lambda: self.state,
                "save": self._save,
            },
            "services": self.services,
            "modules": {},
            "config": {},
        }
        handler = FakeHandler()
        self.assertTrue(settings_handler.handle(handler, request, context))
        self.assertEqual(handler.response, {"ok": True})

    def _save(self):
        self.save_count += 1

    def test_template_only_update_preserves_accounts(self):
        self.update({"template_subject": "Subject T2", "template_body": "Body T2"})
        self.assertEqual(self.state["mail"]["accounts"][0]["name"], "Account A")
        self.assertEqual(self.state["mail"]["template_subject"], "Subject T2")
        self.assertEqual(self.state["mail"]["template_body"], "Body T2")

    def test_accounts_only_update_preserves_template(self):
        self.update({"accounts": [{"name": "Account B", "password": "secret-b"}]})
        self.assertEqual(self.state["mail"]["accounts"][0]["name"], "Account B")
        self.assertEqual(self.state["mail"]["template_subject"], "Subject T1")
        self.assertEqual(self.state["mail"]["template_body"], "Body T1")

    def test_absent_and_explicit_empty_are_distinct(self):
        self.update({"accounts": []})
        self.assertEqual(self.state["mail"]["accounts"], [])
        self.assertEqual(self.state["mail"]["template_subject"], "Subject T1")
        self.update({"template_subject": "", "template_body": ""})
        self.assertEqual(self.state["mail"]["accounts"], [])
        self.assertEqual(self.state["mail"]["template_subject"], "")
        self.assertEqual(self.state["mail"]["template_body"], "")

    def test_full_state_update_remains_compatible(self):
        self.update({
            "accounts": [{"name": "Account B", "password": "secret-b"}],
            "template_subject": "Subject T2",
            "template_body": "Body T2",
        })
        self.assertEqual(self.state["mail"], {
            "accounts": [{"name": "Account B", "password": "secret-b"}],
            "template_subject": "Subject T2",
            "template_body": "Body T2",
        })

    def test_template_then_account_round_trip_preserves_each_owner(self):
        self.update({"template_subject": "Subject T2", "template_body": "Body T2"})
        self.update({"accounts": [{"name": "Account B", "password": "secret-b"}]})
        self.assertEqual(self.state["mail"], {
            "accounts": [{"name": "Account B", "password": "secret-b"}],
            "template_subject": "Subject T2",
            "template_body": "Body T2",
        })
        self.assertEqual(self.save_count, 2)


if __name__ == "__main__":
    unittest.main()
