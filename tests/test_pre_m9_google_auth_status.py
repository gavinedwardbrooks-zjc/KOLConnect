import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import google_sheets_client as module


class Credentials:
    def __init__(self, *, valid=False, refresh_token=""):
        self.valid = valid
        self.refresh_token = refresh_token

    @classmethod
    def from_authorized_user_info(cls, value, _scopes):
        if value.get("broken"):
            raise ValueError("broken")
        return cls(valid=bool(value.get("valid")), refresh_token=str(value.get("refresh_token") or ""))


class GoogleAuthorizationStatusTests(unittest.TestCase):
    def client(self, directory):
        return module.GoogleSheetsClient(
            {"client_id": "id", "client_secret": "secret", "spreadsheet_id": "a-valid_sheet-ID_123456789"},
            module.GoogleOAuthTokenStore(Path(directory) / "token.json"),
        )

    def test_configured_without_token_is_auth_required_not_connected(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(module, "Credentials", Credentials):
            status = self.client(directory).status()
        self.assertEqual("AUTH_REQUIRED", status["status"])
        self.assertFalse(status["connected"])

    def test_broken_or_unrefreshable_token_is_auth_required(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(module, "Credentials", Credentials):
            client = self.client(directory)
            client.token_store.save({"broken": True})
            self.assertEqual("AUTH_REQUIRED", client.status()["status"])
            client.token_store.save({"valid": False})
            self.assertEqual("AUTH_REQUIRED", client.status()["status"])

    def test_valid_or_refreshable_token_is_connected(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(module, "Credentials", Credentials):
            client = self.client(directory)
            client.token_store.save({"token": "access", "valid": True})
            self.assertEqual("CONNECTED", client.status()["status"])
            client.token_store.save({"valid": False, "refresh_token": "stored"})
            self.assertEqual("CONNECTED", client.status()["status"])
            self.assertTrue(client.status()["connected"])

    def test_disconnect_returns_auth_required(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(module, "Credentials", Credentials):
            client = self.client(directory)
            client.token_store.save({"valid": True})
            self.assertEqual("AUTH_REQUIRED", client.disconnect()["status"])


if __name__ == "__main__": unittest.main()
