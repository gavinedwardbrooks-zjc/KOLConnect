"""Read-only Google Sheets replica for authoritative Mail Follow-up state."""
from services import mail_follow_up_preferences as preferences

WORKSHEET = "Mail Follow-up"
HEADERS = [
    "KOLConnect Creator ID", "达人名称", "联系邮箱", "跟进状态", "等待天数",
    "最近邮件时间", "已同步收件数", "已同步发件数", "历史范围",
]
WAITING = {"me": "待我回复", "creator": "待对方回复", "unknown": "状态未知"}


class MailFollowUpGoogleSheetsReplicaService:
    def __init__(self, factory):
        self._factory = factory

    def rows(self):
        groups = preferences.follow_up_state(self._factory)
        names = self._names(groups)
        return [
            [
                creator_id := str(group.get("creator_id") or ""),
                names.get(creator_id, "未命名达人"),
                str(group.get("correspondent_email") or ""),
                WAITING.get(group.get("waiting_for"), "状态未知"),
                "" if group.get("days_waiting") is None else group["days_waiting"],
                str(group.get("last_mail_at") or ""),
                group.get("synced_inbound_count", 0),
                group.get("synced_outbound_count", 0),
                self._history_label(group.get("partial_history")),
            ]
            for group in groups
        ]

    def _names(self, rows):
        ids = sorted({str(row.get("creator_id") or "") for row in rows if row.get("creator_id")})
        if not ids:
            return {}
        with self._factory.read_connection() as connection:
            placeholders = ",".join("?" * len(ids))
            query = f"SELECT creator_id,name FROM creators WHERE creator_id IN ({placeholders})"
            return {
                str(row["creator_id"]): str(row["name"] or "未命名达人")
                for row in connection.execute(query, ids)
            }

    @staticmethod
    def _history_label(partial_history):
        if partial_history is True:
            return "部分历史"
        if partial_history is None:
            return "历史范围未知"
        return "已同步范围内"

    def sync(self, client, spreadsheet):
        return client.upsert_managed_worksheet(
            spreadsheet, WORKSHEET, HEADERS, self.rows(),
            ("KOLConnect Creator ID", "联系邮箱"),
        )
