from __future__ import annotations

"""Same-origin session/CSRF boundary for creating publication capture capabilities."""

from services.mail_send_security import MailSendSessionStore
from services.publication_capture_service import PublicationCaptureError


COOKIE_NAME = "kolconnect_publication_capture_session"
CSRF_HEADER = "X-KOLConnect-Publication-Capture-CSRF"


class PublicationCaptureSessionStore(MailSendSessionStore):
    def issue(self, headers, port: int) -> dict[str, str]:
        try:
            issued = super().issue(headers, port)
        except Exception as exc:
            raise PublicationCaptureError("CAPTURE_ORIGIN_REJECTED", "采集任务只能由本地 KOLConnect 页面创建。", status=403) from exc
        issued["set_cookie"] = issued["set_cookie"].replace("kolconnect_mail_send_session", COOKIE_NAME)
        return issued

    def validate(self, headers, port: int) -> str:
        original_cookie = headers.get("Cookie", "")
        original_csrf = headers.get("X-KOLConnect-Mail-CSRF", "")
        proxy = dict(headers)
        proxy["Cookie"] = str(original_cookie).replace(COOKIE_NAME, "kolconnect_mail_send_session")
        proxy["X-KOLConnect-Mail-CSRF"] = headers.get(CSRF_HEADER, original_csrf)
        try:
            return super().validate(proxy, port)
        except Exception as exc:
            raise PublicationCaptureError("CAPTURE_CSRF_INVALID", "采集任务安全会话无效。", status=403) from exc
