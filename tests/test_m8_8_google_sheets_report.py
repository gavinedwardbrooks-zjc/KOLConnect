import json
import importlib
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
client_module = importlib.import_module("google_sheets_client")
service_module = importlib.import_module("services.google_campaign_report_service")
from test_support.runtime_sandbox import test_runtime_sandbox


class FakeCampaignRepository:
    def getCampaign(self, campaign_id):
        return {"campaign_id": campaign_id, "name": "Launch"}


class FakeRelationRepository:
    def getCampaignCreators(self, **_kwargs):
        return [{
            "id": "relation_1", "creator_id": "creator_1",
            "planned_publish_dates": ["2026-09-05", "2026-09-08"],
            "execution_accounts": [
                {"account_uid": "tiktok:a"}, {"account_uid": "youtube:b"},
            ],
            "publications": [{"publication_id": "pub_1", "source": "manual"}],
        }]


def analytics_payload():
    return {
        "campaign_id": "campaign_1", "publication_count": 1,
        "totals": {
            "views": {"total": 0, "valid_count": 1, "missing_count": 0, "total_publications": 1},
            "likes": {"total": None, "valid_count": 0, "missing_count": 1, "total_publications": 1},
            "comments": {"total": 0, "valid_count": 1, "missing_count": 0, "total_publications": 1},
        },
        "average_er": 0, "valid_er_count": 1, "total_publications": 1,
        "top_creator": {"creator_id": "creator_1"}, "top_video": {"publication_id": "pub_1"},
        "highest_er": {"publication_id": "pub_1"}, "fastest_growing": None,
        "total_quote_by_currency": {"BRL": 700, "USD": 120},
        "total_cost_by_currency": {"BRL": 600, "USD": 100},
        "efficiency_by_currency": {"USD": {"cpv": None, "cpe": 1}},
        "roi": None, "roi_reason": "AUTHORITATIVE_RETURN_INPUT_UNAVAILABLE",
        "latest_observed_at": "2026-09-02T00:00:00Z",
        "publications": [{
            "campaign_creator_id": "relation_1", "creator_id": "creator_1",
            "publication_id": "pub_1", "platform": "TikTok", "video_id": "v1",
            "publication_url": "https://tiktok.example/video/1", "actual_account_uid": "tiktok:a",
            "published_at": "2026-09-01T00:00:00Z",
            "series": [
                {"observation_id": "obs_1", "observed_at": "2026-09-01T00:00:00Z", "views": None, "likes": 0, "comments": None, "shares": 0, "engagement_rate": None, "source": "manual", "confidence": "high"},
                {"observation_id": "obs_2", "observed_at": "2026-09-02T00:00:00Z", "views": 0, "likes": None, "comments": 0, "shares": None, "engagement_rate": 0, "source": "provider", "confidence": "high"},
            ],
        }],
    }


class FakeAnalytics:
    def get_campaign_performance(self, campaign_id):
        self.campaign_id = campaign_id
        return analytics_payload()


class FakeResponse:
    def __init__(self, status=200, value=None):
        self.status_code = status
        self.value = value or {}

    def json(self):
        return self.value


class FakeSession:
    def __init__(self, *, conflicting=False, fail_title="", metadata_status=200, fail_network=False):
        self.calls = []
        self.conflicting = conflicting
        self.fail_title = fail_title
        self.metadata_status = metadata_status
        self.fail_network = fail_network
        self.titles = ["Campaign Summary"]

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        if self.fail_network:
            raise OSError("offline")
        if url.endswith("values:batchGet"):
            marker = "OTHER" if self.conflicting else client_module.REPORT_MARKER
            ranges = [value for key, value in kwargs.get("params", []) if key == "ranges"]
            return FakeResponse(value={
                "valueRanges": [{"range": item, "values": [[marker]]} for item in ranges]
            })
        return FakeResponse(
            status=self.metadata_status,
            value={"sheets": [{"properties": {"title": title}} for title in self.titles]},
        )

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        if self.fail_title and self.fail_title.replace(" ", "%20") in url:
            return FakeResponse(status=500)
        if url.endswith(":batchUpdate"):
            for request in kwargs.get("json", {}).get("requests", []):
                title = request.get("addSheet", {}).get("properties", {}).get("title")
                if title and title not in self.titles:
                    self.titles.append(title)
        return FakeResponse(value={})

    def put(self, url, **kwargs):
        self.calls.append(("put", url, kwargs))
        return FakeResponse(value={})


class FakeCredentials:
    expired = False
    refresh_token = "refresh"
    valid = True

    def to_json(self):
        return json.dumps({"token": "access", "refresh_token": self.refresh_token})


class FakeRefreshCredentials(FakeCredentials):
    expired = True
    refreshed = False

    @classmethod
    def from_authorized_user_info(cls, _token, _scopes):
        return cls()

    def refresh(self, _request):
        self.expired = False
        self.refreshed = True


class FakeFlow:
    received_scopes = None

    @classmethod
    def from_client_config(cls, _config, scopes):
        cls.received_scopes = scopes
        return cls()

    def run_local_server(self, **_kwargs):
        return FakeCredentials()


class M88ReportTests(unittest.TestCase):
    def setUp(self):
        self.runtime_context = test_runtime_sandbox("m8_8_google_sheets")
        self.runtime = self.runtime_context.__enter__()
        self.service = service_module.GoogleCampaignReportService(
            FakeCampaignRepository(), FakeRelationRepository(), FakeAnalytics()
        )

    def tearDown(self):
        self.runtime_context.__exit__(None, None, None)

    def test_assembly_consumes_analytics_without_publication_fanout(self):
        first = self.service.assemble("campaign_1")
        second = self.service.assemble("campaign_1")
        self.assertEqual(first, second)
        worksheets = {item["title"]: item for item in first["worksheets"]}
        publications = worksheets["Publications"]
        self.assertEqual(1, len(publications["rows"]))
        row = dict(zip(publications["headers"], publications["rows"][0]))
        self.assertEqual("pub_1", row["publication_id"])
        self.assertEqual(["2026-09-05", "2026-09-08"], json.loads(row["planned_dates"]))
        self.assertEqual(["tiktok:a", "youtube:b"], json.loads(row["planned_account_uids"]))
        self.assertEqual("tiktok:a", row["actual_account_uid"])
        self.assertEqual("manual", row["publication_source"])
        self.assertEqual("provider", row["observation_source"])
        self.assertEqual("2026-09-01T00:00:00Z", row["published_at"])
        self.assertEqual("2026-09-02T00:00:00Z", row["latest_observed_at"])

    def test_history_identity_and_null_zero_are_preserved(self):
        history = self.service.assemble("campaign_1")["worksheets"][2]
        self.assertEqual(["obs_1", "obs_2"], [row[0] for row in history["rows"]])
        first = dict(zip(history["headers"], history["rows"][0]))
        second = dict(zip(history["headers"], history["rows"][1]))
        self.assertEqual("", first["views"])
        self.assertEqual(0, second["views"])
        self.assertEqual(0, first["likes"])
        self.assertEqual("", second["likes"])
        self.assertEqual("", first["engagement_rate"])
        self.assertEqual(0, second["engagement_rate"])

    def test_summary_groups_money_and_never_invents_roi(self):
        summary = self.service.assemble("campaign_1")["worksheets"][0]
        values = {row[0]: row[1] for row in summary["rows"]}
        self.assertEqual({"BRL": 600, "USD": 100}, json.loads(values["total_cost_by_currency"]))
        self.assertEqual({"BRL": 700, "USD": 120}, json.loads(values["total_quote_by_currency"]))
        self.assertEqual("", values["roi"])
        self.assertEqual(0, values["total_views"])
        self.assertEqual("", values["total_likes"])

    def test_spreadsheet_id_parser_accepts_id_and_supported_url_only(self):
        identifier = "a-valid_sheet-ID_123456789"
        self.assertEqual(identifier, client_module.parse_spreadsheet_id(identifier))
        self.assertEqual(identifier, client_module.parse_spreadsheet_id(f"https://docs.google.com/spreadsheets/d/{identifier}/edit#gid=0"))
        for invalid in ("", "https://drive.google.com/file/d/example", "https://evil.test/spreadsheets/d/a-valid_sheet-ID_123456789"):
            with self.assertRaises(client_module.GoogleSheetsError):
                client_module.parse_spreadsheet_id(invalid)

    def test_client_manages_only_named_ranges_and_repeated_sync_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            client = client_module.GoogleSheetsClient(
                {"client_id": "id", "client_secret": "secret", "spreadsheet_id": "a-valid_sheet-ID_123456789"},
                client_module.GoogleOAuthTokenStore(Path(directory) / "token.json"),
            )
            session = FakeSession()
            client._authorized_session = lambda: session
            report = self.service.assemble("campaign_1")["worksheets"]
            first = client.sync_managed_worksheets("a-valid_sheet-ID_123456789", report)
            second = client.sync_managed_worksheets("a-valid_sheet-ID_123456789", report)
        self.assertEqual("SUCCESS", first["status"])
        self.assertEqual(first, second)
        self.assertEqual(1, sum(url.endswith(":batchUpdate") for method, url, _ in session.calls if method == "post"))
        self.assertEqual(6, sum(method == "put" for method, _, _ in session.calls))
        self.assertFalse(any(":clear" in url and "A%3AAZ" not in url for method, url, _ in session.calls if method == "post"))

    def test_name_collision_fails_closed_and_partial_write_is_reported(self):
        client = client_module.GoogleSheetsClient(
            {"client_id": "id", "client_secret": "secret", "spreadsheet_id": "a-valid_sheet-ID_123456789"},
            client_module.GoogleOAuthTokenStore(Path("unused-token.json")),
        )
        client._authorized_session = lambda: FakeSession(conflicting=True)
        with self.assertRaisesRegex(client_module.GoogleSheetsError, "WORKSHEET_NAME_CONFLICT"):
            client.sync_managed_worksheets("a-valid_sheet-ID_123456789", self.service.assemble("campaign_1")["worksheets"])
        client._authorized_session = lambda: FakeSession(fail_title="Publications")
        result = client.sync_managed_worksheets("a-valid_sheet-ID_123456789", self.service.assemble("campaign_1")["worksheets"])
        self.assertEqual("PARTIAL", result["status"])

    def test_token_store_is_separate_and_disconnect_removes_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "google_sheets_token.json"
            store = client_module.GoogleOAuthTokenStore(path)
            store.save({"refresh_token": "sensitive"})
            self.assertTrue(store.exists())
            client = client_module.GoogleSheetsClient(
                {"client_id": "id", "client_secret": "secret", "spreadsheet_id": "a-valid_sheet-ID_123456789"}, store
            )
            status = client.disconnect()
            self.assertFalse(status["connected"])
            self.assertFalse(path.exists())

    def test_desktop_oauth_uses_only_sheets_scope_and_never_exposes_token(self):
        with tempfile.TemporaryDirectory() as directory:
            store = client_module.GoogleOAuthTokenStore(Path(directory) / "token.json")
            client = client_module.GoogleSheetsClient({
                "client_id": "client", "client_secret": "secret",
                "spreadsheet_id": "a-valid_sheet-ID_123456789",
            }, store)
            with mock.patch.object(client_module, "InstalledAppFlow", FakeFlow):
                status = client.connect()
            self.assertEqual([client_module.SHEETS_SCOPE], FakeFlow.received_scopes)
            self.assertTrue(status["connected"])
            self.assertNotIn("token", status)
            self.assertNotIn("refresh_token", status)
            self.assertIn("refresh_token", store.load())

    def test_auth_required_refresh_permission_and_network_errors_are_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            store = client_module.GoogleOAuthTokenStore(Path(directory) / "token.json")
            unconfigured = client_module.GoogleSheetsClient({}, store)
            with self.assertRaisesRegex(client_module.GoogleSheetsError, "NOT_CONFIGURED"):
                unconfigured.connect()

            config = {
                "client_id": "client", "client_secret": "secret",
                "spreadsheet_id": "a-valid_sheet-ID_123456789",
            }
            client = client_module.GoogleSheetsClient(config, store)
            with self.assertRaisesRegex(client_module.GoogleSheetsError, "AUTH_REQUIRED"):
                client._authorized_session()

            store.save({"refresh_token": "refresh"})
            session_marker = object()
            client._session_provider = lambda credentials: (session_marker, credentials.refreshed)
            with mock.patch.object(client_module, "Credentials", FakeRefreshCredentials), mock.patch.object(
                client_module, "Request", lambda: object()
            ), mock.patch.object(client_module, "AuthorizedSession", object()):
                self.assertEqual((session_marker, True), client._authorized_session())

            worksheets = self.service.assemble("campaign_1")["worksheets"]
            client._authorized_session = lambda: FakeSession(metadata_status=403)
            with self.assertRaisesRegex(client_module.GoogleSheetsError, "REMOTE_PERMISSION_DENIED"):
                client.sync_managed_worksheets(config["spreadsheet_id"], worksheets)
            client._authorized_session = lambda: FakeSession(fail_network=True)
            with self.assertRaisesRegex(client_module.GoogleSheetsError, "NETWORK_ERROR"):
                client.sync_managed_worksheets(config["spreadsheet_id"], worksheets)


if __name__ == "__main__":
    unittest.main()
