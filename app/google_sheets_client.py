from __future__ import annotations

"""Minimal Google Sheets REST client with desktop OAuth and no Drive access."""

import json
import os
import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlparse

from runtime_paths import atomic_write_json, load_json_with_backup

try:
    from google.auth.transport.requests import AuthorizedSession, Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:  # Report a stable runtime code when optional integration deps are absent.
    AuthorizedSession = Request = Credentials = InstalledAppFlow = None


SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
REPORT_MARKER = "KOLCONNECT_CAMPAIGN_PERFORMANCE_REPORT_V1"
SPREADSHEET_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,}$")


class GoogleSheetsError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def parse_spreadsheet_id(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        raise GoogleSheetsError("NOT_CONFIGURED")
    if text.startswith(("http://", "https://")):
        parsed = urlparse(text)
        if parsed.scheme != "https" or parsed.netloc not in {
            "docs.google.com", "sheets.google.com"
        }:
            raise GoogleSheetsError("INVALID_SPREADSHEET")
        match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", parsed.path)
        text = match.group(1) if match else ""
    if not SPREADSHEET_ID_PATTERN.fullmatch(text):
        raise GoogleSheetsError("INVALID_SPREADSHEET")
    return text


class GoogleOAuthTokenStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def exists(self) -> bool:
        return self.path.is_file()

    def load(self) -> dict[str, Any] | None:
        value, _ = load_json_with_backup(self.path)
        return value if isinstance(value, dict) else None

    def save(self, value: dict[str, Any]) -> None:
        atomic_write_json(self.path, value)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
        self.path.with_name(f"{self.path.name}.bak").unlink(missing_ok=True)


class GoogleSheetsClient:
    def __init__(
        self,
        config: dict[str, Any],
        token_store: GoogleOAuthTokenStore,
        *,
        session_provider: Callable[[Any], Any] | None = None,
    ) -> None:
        self.config = {key: str(value or "").strip() for key, value in config.items()}
        self.token_store = token_store
        self._session_provider = session_provider

    def status(self) -> dict[str, Any]:
        configured = all(self.config.get(key) for key in (
            "client_id", "client_secret", "spreadsheet_id",
        ))
        target_valid = False
        if self.config.get("spreadsheet_id"):
            try:
                parse_spreadsheet_id(self.config["spreadsheet_id"])
                target_valid = True
            except GoogleSheetsError:
                pass
        return {
            "configured": configured,
            "connected": self.token_store.exists(),
            "target_valid": target_valid,
            "status": "CONNECTED" if configured and self.token_store.exists() and target_valid
            else ("NOT_CONNECTED" if configured and target_valid else "NOT_CONFIGURED"),
        }

    def connect(self) -> dict[str, Any]:
        self._require_client_config()
        if InstalledAppFlow is None:
            raise GoogleSheetsError("GOOGLE_SDK_UNAVAILABLE")
        flow = InstalledAppFlow.from_client_config(
            {"installed": {
                "client_id": self.config["client_id"],
                "client_secret": self.config["client_secret"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }},
            [SHEETS_SCOPE],
        )
        credentials = flow.run_local_server(port=0, open_browser=True)
        self._save_credentials(credentials)
        return self.status()

    def disconnect(self) -> dict[str, Any]:
        self.token_store.clear()
        return self.status()

    def sync_managed_worksheets(
        self, spreadsheet: object, worksheets: list[dict[str, Any]]
    ) -> dict[str, Any]:
        spreadsheet_id = parse_spreadsheet_id(spreadsheet)
        session = self._authorized_session()
        metadata = self._request(
            session, "get", f"{SHEETS_API}/{spreadsheet_id}",
            params={"fields": "sheets.properties(sheetId,title)"},
        )
        existing = {
            str(item.get("properties", {}).get("title") or ""):
            item.get("properties", {})
            for item in metadata.get("sheets", []) if isinstance(item, dict)
        }
        required_titles = [str(item["title"]) for item in worksheets]
        existing_titles = [title for title in required_titles if title in existing]
        if existing_titles:
            ranges = [f"'{title.replace("'", "''")}'!A1:AZ5" for title in existing_titles]
            markers = self._request(
                session, "get", f"{SHEETS_API}/{spreadsheet_id}/values:batchGet",
                params=[("ranges", item) for item in ranges],
            ).get("valueRanges", [])
            for title, value_range in zip(existing_titles, markers):
                values = value_range.get("values") or []
                first = str(values[0][0]) if values and values[0] else ""
                has_content = any(str(cell or "") for row in values for cell in row)
                if has_content and first != REPORT_MARKER:
                    raise GoogleSheetsError("WORKSHEET_NAME_CONFLICT")

        missing = [title for title in required_titles if title not in existing]
        if missing:
            self._request(session, "post", f"{SHEETS_API}/{spreadsheet_id}:batchUpdate", json={
                "requests": [{"addSheet": {"properties": {"title": title}}} for title in missing]
            })

        statuses = []
        for worksheet in worksheets:
            title = str(worksheet["title"])
            escaped = title.replace("'", "''")
            values = [
                [REPORT_MARKER, str(worksheet.get("schema_version") or "1")],
                list(worksheet["headers"]),
                *[list(row) for row in worksheet["rows"]],
            ]
            try:
                self._request(session, "post", f"{SHEETS_API}/{spreadsheet_id}/values/{quote(f"'{escaped}'!A:AZ", safe='')}:clear", json={})
                self._request(
                    session, "put",
                    f"{SHEETS_API}/{spreadsheet_id}/values/{quote(f"'{escaped}'!A1", safe='')}",
                    params={"valueInputOption": "RAW"}, json={"majorDimension": "ROWS", "values": values},
                )
                statuses.append({"worksheet": title, "status": "SUCCESS", "row_count": len(worksheet["rows"])})
            except GoogleSheetsError as exc:
                statuses.append({"worksheet": title, "status": "FAILED", "error": exc.code})
        succeeded = sum(item["status"] == "SUCCESS" for item in statuses)
        return {
            "status": "SUCCESS" if succeeded == len(statuses) else ("PARTIAL" if succeeded else "FAILED"),
            "spreadsheet_id": spreadsheet_id,
            "worksheets": statuses,
        }

    def _require_client_config(self) -> None:
        if not self.config.get("client_id") or not self.config.get("client_secret"):
            raise GoogleSheetsError("NOT_CONFIGURED")

    def _authorized_session(self):
        self._require_client_config()
        token = self.token_store.load()
        if token is None:
            raise GoogleSheetsError("AUTH_REQUIRED")
        if Credentials is None or AuthorizedSession is None or Request is None:
            raise GoogleSheetsError("GOOGLE_SDK_UNAVAILABLE")
        credentials = Credentials.from_authorized_user_info(token, [SHEETS_SCOPE])
        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                self._save_credentials(credentials)
            except Exception as exc:
                raise GoogleSheetsError("AUTH_REQUIRED") from exc
        if not credentials.valid:
            raise GoogleSheetsError("AUTH_REQUIRED")
        return (self._session_provider or AuthorizedSession)(credentials)

    def _save_credentials(self, credentials: Any) -> None:
        self.token_store.save(json.loads(credentials.to_json()))

    @staticmethod
    def _request(session: Any, method: str, url: str, **kwargs) -> dict[str, Any]:
        try:
            response = getattr(session, method)(url, timeout=30, **kwargs)
        except Exception as exc:
            raise GoogleSheetsError("NETWORK_ERROR") from exc
        status = int(getattr(response, "status_code", 0) or 0)
        if status in {401, 403}:
            code = "AUTH_REQUIRED" if status == 401 else "REMOTE_PERMISSION_DENIED"
            raise GoogleSheetsError(code)
        if status == 404:
            raise GoogleSheetsError("INVALID_SPREADSHEET")
        if status < 200 or status >= 300:
            raise GoogleSheetsError("REMOTE_ERROR")
        try:
            value = response.json()
        except Exception:
            value = {}
        return value if isinstance(value, dict) else {}
