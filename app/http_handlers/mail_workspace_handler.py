"""Same-origin API for explicit on-demand body reads and Sent reconciliation."""

from __future__ import annotations

import re

from services.mail_send_service import MailSendError
from services.mail_inbox_facts import mail_account_identity, normalize_address


BODY_PATH = re.compile(r"^/api/mail/messages/([^/]+)/body$")


def _session(handler, context: dict) -> None:
    context["services"]["mail_send_sessions"].validate(handler.headers, int(handler.server.server_port))


def handle(handler, request: dict, context: dict) -> bool:
    method = request["method"]
    path = request["path"]
    body_match = BODY_PATH.fullmatch(path)
    if not body_match and path not in {"/api/mail/sent-reconciliation", "/api/mail/workspace/options"}:
        return False
    service = context["services"]["mail_workspace"]
    try:
        _session(handler, context)
        if method == "GET" and path == "/api/mail/workspace/options":
            state = context["state"]["get"]()
            raw_accounts = state.get("mail", {}).get("accounts", [])
            accounts = []
            for raw in raw_accounts if isinstance(raw_accounts, list) else []:
                if not isinstance(raw, dict) or not raw.get("enabled"):
                    continue
                account = context["services"]["normalize_mail_account"](raw)
                account_id, _identity = mail_account_identity(account)
                accounts.append({
                    "mail_account_id": account_id,
                    "name": str(account.get("name") or account.get("email") or ""),
                    "email": normalize_address(account.get("email")),
                    "sender_name": str(account.get("sender_name") or ""),
                })
            creator_id = str((request.get("query", {}).get("creator_id") or [""])[0]).strip()
            contacts = []
            if creator_id:
                with context["services"]["get_mail_connection_factory"]().read_connection() as connection:
                    contacts = [dict(row) for row in connection.execute(
                        "SELECT account_uid,platform,username,account_email FROM creator_accounts "
                        "WHERE creator_id=? AND trim(COALESCE(account_email,''))<>'' ORDER BY platform,username,account_uid",
                        (creator_id,),
                    )]
            ai = context["services"]["ai_provider_configuration"].client_configuration()
            handler._json({
                "ok": True,
                "mail_accounts": accounts,
                "creator_contacts": contacts,
                "ai_provider": {"provider": ai.get("provider"), "model": ai.get("model"),
                                "enabled": bool(ai.get("enabled") and ai.get("key_configured"))},
            })
            return True
        if method == "POST" and body_match:
            handler._json({"ok": True, "message": service.read_body(body_match.group(1))})
            return True
        if method == "POST" and path == "/api/mail/sent-reconciliation":
            payload = request["get_payload"]()
            handler._json({"ok": True, "result": service.reconcile_sent_attempts(payload.get("mail_account_id"))})
            return True
        return False
    except MailSendError as exc:
        handler._api_error(exc.code, str(exc), status=exc.status)
        return True
