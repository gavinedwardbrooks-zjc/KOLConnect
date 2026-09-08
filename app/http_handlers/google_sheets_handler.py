"""Google Sheets OAuth/status and manual Campaign report endpoints."""

import re

from google_sheets_client import GoogleSheetsError


ERROR_STATUS = {
    "NOT_CONFIGURED": 400,
    "INVALID_SPREADSHEET": 400,
    "AUTH_REQUIRED": 401,
    "REMOTE_PERMISSION_DENIED": 403,
    "WORKSHEET_NAME_CONFLICT": 409,
    "GOOGLE_SDK_UNAVAILABLE": 503,
    "NETWORK_ERROR": 503,
    "REMOTE_ERROR": 502,
}


def _failure(handler, exc: GoogleSheetsError) -> None:
    handler._json(
        {"ok": False, "status": "FAILED", "error": exc.code},
        status=ERROR_STATUS.get(exc.code, 500),
    )


def handle(handler, request: dict, context: dict) -> bool:
    method, path = request["method"], request["path"]
    services = context["services"]
    if method == "GET" and path == "/api/google-sheets/status":
        handler._json({"ok": True, **services["google_sheets_client"]().status()})
        return True
    if method == "POST" and path == "/api/google-sheets/connect":
        try:
            handler._json({"ok": True, **services["google_sheets_client"]().connect()})
        except GoogleSheetsError as exc:
            _failure(handler, exc)
        return True
    if method == "POST" and path == "/api/google-sheets/disconnect":
        handler._json({"ok": True, **services["google_sheets_client"]().disconnect()})
        return True
    sync_match = re.fullmatch(r"/api/campaigns/([^/]+)/google-sheets-sync", path)
    if method == "POST" and sync_match:
        try:
            result = services["google_campaign_report"].sync(
                sync_match.group(1),
                services["google_sheets_client"](),
                services["get_google_sheets_config"]().get("spreadsheet_id", ""),
            )
            handler._json({"ok": result["status"] == "SUCCESS", **result})
        except GoogleSheetsError as exc:
            _failure(handler, exc)
        except ValueError as exc:
            handler._json({"ok": False, "status": "FAILED", "error": "CAMPAIGN_NOT_FOUND"}, status=404)
        return True
    return False
