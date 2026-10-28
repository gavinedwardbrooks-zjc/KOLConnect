from __future__ import annotations

"""Versioned multilingual mail templates with deterministic safe rendering."""

from datetime import datetime, timezone
import json
import re
from typing import Any, Callable, Mapping
import uuid


LANGUAGE_PATTERN = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,3}$")
VARIABLE_PATTERN = re.compile(r"{{\s*([a-z][a-z0-9_]*)\s*}}")
GROUP_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
ALLOWED_DRAFT_TYPES = {"initial_outreach", "reply", "follow_up"}
ALLOWED_VARIABLES = {
    "creator_name", "brand_name", "game_name", "sender_name", "campaign_name", "collaboration_type",
}
SUBJECT_LIMIT = 998
BODY_LIMIT = 100_000
VARIABLE_VALUE_LIMIT = 4_000


class MailTemplateError(ValueError):
    def __init__(self, code: str, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def normalize_language_tag(value: object) -> str:
    raw = str(value or "").strip()
    if len(raw) > 35 or not LANGUAGE_PATTERN.fullmatch(raw):
        raise MailTemplateError("MAIL_LANGUAGE_INVALID", "目标语言必须是有效的 BCP 47 语言标签。")
    parts = raw.split("-")
    normalized = [parts[0].lower()]
    for part in parts[1:]:
        if len(part) == 4 and part.isalpha():
            normalized.append(part.title())
        elif len(part) == 2 and part.isalpha():
            normalized.append(part.upper())
        else:
            normalized.append(part.lower())
    return "-".join(normalized)


def select_target_language(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise MailTemplateError("MAIL_LANGUAGE_SELECTION_REQUIRED", "请选择邮件目标语言。")
    if set(value) - {"mode", "target_language", "evidence"}:
        raise MailTemplateError("MAIL_LANGUAGE_SELECTION_INVALID", "语言选择包含不支持的字段。")
    mode = str(value.get("mode") or "").strip()
    if mode == "explicit":
        return {"mode": mode, "language": normalize_language_tag(value.get("target_language")), "evidence": "user_selected"}
    if mode != "auto":
        raise MailTemplateError("MAIL_LANGUAGE_SELECTION_INVALID", "语言选择模式无效。")
    evidence = value.get("evidence")
    if not isinstance(evidence, Mapping) or set(evidence) - {"source", "language"}:
        raise MailTemplateError("MAIL_LANGUAGE_SELECTION_REQUIRED", "自动语言选择缺少可靠证据。")
    source = str(evidence.get("source") or "").strip()
    if source not in {"user_communication_language", "selected_mail_body", "verified_language_field"}:
        raise MailTemplateError("MAIL_LANGUAGE_SELECTION_REQUIRED", "自动语言选择缺少可靠证据。")
    return {"mode": mode, "language": normalize_language_tag(evidence.get("language")), "evidence": source}


BUILTIN_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "template_id": "builtin-initial-outreach-en-v1", "template_group_id": "builtin-initial-outreach",
        "template_version": 1, "template_source": "builtin", "draft_type": "initial_outreach", "language": "en",
        "name": "Creator collaboration introduction", "tone": "professional",
        "subject_template": "Collaboration opportunity with {{brand_name}}",
        "body_template": "Hello {{creator_name}},\n\nI'm {{sender_name}} from {{brand_name}}. We'd like to discuss a {{collaboration_type}} collaboration.\n\nBest regards,\n{{sender_name}}",
        "required_variables": ["brand_name", "collaboration_type", "creator_name", "sender_name"], "active": True,
    },
    {
        "template_id": "builtin-initial-outreach-zh-cn-v1", "template_group_id": "builtin-initial-outreach",
        "template_version": 1, "template_source": "builtin", "draft_type": "initial_outreach", "language": "zh-CN",
        "name": "Creator 合作邀请", "tone": "professional",
        "subject_template": "{{brand_name}} 合作邀请",
        "body_template": "你好，{{creator_name}}：\n\n我是 {{brand_name}} 的 {{sender_name}}。我们希望与你沟通 {{collaboration_type}} 合作。\n\n谢谢！\n{{sender_name}}",
        "required_variables": ["brand_name", "collaboration_type", "creator_name", "sender_name"], "active": True,
    },
    {
        "template_id": "builtin-initial-outreach-pt-br-v1", "template_group_id": "builtin-initial-outreach",
        "template_version": 1, "template_source": "builtin", "draft_type": "initial_outreach", "language": "pt-BR",
        "name": "Convite para colaboração", "tone": "professional",
        "subject_template": "Oportunidade de colaboração com {{brand_name}}",
        "body_template": "Olá, {{creator_name}}!\n\nSou {{sender_name}}, da {{brand_name}}. Gostaríamos de conversar sobre uma colaboração de {{collaboration_type}}.\n\nAtenciosamente,\n{{sender_name}}",
        "required_variables": ["brand_name", "collaboration_type", "creator_name", "sender_name"], "active": True,
    },
)


class MailTemplateService:
    def __init__(self, factory_provider: Callable[[], Any], *, now: Callable[[], datetime] | None = None) -> None:
        self._factory_provider = factory_provider
        self._now = now or (lambda: datetime.now(timezone.utc))

    def list_templates(self, *, draft_type: object = None, language: object = None, include_inactive: bool = False) -> list[dict[str, Any]]:
        normalized_type = self._draft_type(draft_type) if draft_type not in (None, "") else None
        normalized_language = normalize_language_tag(language) if language not in (None, "") else None
        builtins = [self._builtin(item) for item in BUILTIN_TEMPLATES]
        with self._factory_provider().read_connection() as connection:
            rows = connection.execute("SELECT * FROM mail_templates ORDER BY template_group_id,template_version DESC").fetchall()
        users = [self._row(row) for row in rows]
        result = builtins + users
        return [item for item in result if (not normalized_type or item["draft_type"] == normalized_type)
                and (not normalized_language or item["language"] == normalized_language)
                and (include_inactive or item["active"])]

    def get_template(self, template_id: object) -> dict[str, Any]:
        normalized = str(template_id or "").strip()
        builtin = next((self._builtin(item) for item in BUILTIN_TEMPLATES if item["template_id"] == normalized), None)
        if builtin:
            return builtin
        with self._factory_provider().read_connection() as connection:
            row = connection.execute("SELECT * FROM mail_templates WHERE template_id=?", (normalized,)).fetchone()
        if row is None:
            raise MailTemplateError("MAIL_TEMPLATE_NOT_FOUND", "邮件模板不存在。", status=404)
        return self._row(row)

    def create_template(self, payload: Mapping[str, object]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise MailTemplateError("MAIL_TEMPLATE_INVALID", "邮件模板必须是对象。")
        copy_id = payload.get("copy_from_template_id")
        source = self.get_template(copy_id) if copy_id else {}
        values = self._validated({**source, **payload}, creating=True)
        group_id = str(payload.get("template_group_id") or f"template_group_{uuid.uuid4().hex}").strip()
        if not GROUP_PATTERN.fullmatch(group_id) or group_id.startswith("builtin-"):
            raise MailTemplateError("MAIL_TEMPLATE_GROUP_INVALID", "模板组标识无效。")
        return self._insert(group_id, 1, values)

    def update_template(self, template_id: object, payload: Mapping[str, object]) -> dict[str, Any]:
        current = self.get_template(template_id)
        if current["template_source"] != "user":
            raise MailTemplateError("MAIL_TEMPLATE_BUILTIN_READ_ONLY", "内置模板不可直接修改。", status=403)
        if not isinstance(payload, Mapping) or "template_version" not in payload:
            raise MailTemplateError("MAIL_TEMPLATE_VERSION_REQUIRED", "必须提供当前模板版本。")
        if payload.get("template_version") != current["template_version"]:
            raise MailTemplateError("MAIL_TEMPLATE_VERSION_CONFLICT", "模板已更新，请重新加载。", status=409)
        values = self._validated({**current, **payload}, creating=False)
        now = self._timestamp()
        with self._factory_provider().write_transaction() as connection:
            cursor = connection.execute(
                "UPDATE mail_templates SET active=0,updated_at=? WHERE template_id=? AND template_version=? AND active=1",
                (now, current["template_id"], current["template_version"]),
            )
            if cursor.rowcount != 1:
                raise MailTemplateError("MAIL_TEMPLATE_VERSION_CONFLICT", "模板已更新，请重新加载。", status=409)
            result = self._insert_with_connection(connection, current["template_group_id"], current["template_version"] + 1, values, now)
        return result

    def deactivate_template(self, template_id: object, template_version: object) -> dict[str, Any]:
        current = self.get_template(template_id)
        if current["template_source"] != "user":
            raise MailTemplateError("MAIL_TEMPLATE_BUILTIN_READ_ONLY", "内置模板不可停用。", status=403)
        if template_version != current["template_version"]:
            raise MailTemplateError("MAIL_TEMPLATE_VERSION_CONFLICT", "模板已更新，请重新加载。", status=409)
        with self._factory_provider().write_transaction() as connection:
            cursor = connection.execute(
                "UPDATE mail_templates SET active=0,updated_at=? WHERE template_id=? AND template_version=? AND active=1",
                (self._timestamp(), current["template_id"], current["template_version"]),
            )
            if cursor.rowcount != 1:
                raise MailTemplateError("MAIL_TEMPLATE_VERSION_CONFLICT", "模板已更新，请重新加载。", status=409)
        return {**current, "active": False}

    def render(self, template_id: object, variables: object) -> dict[str, Any]:
        template = self.get_template(template_id)
        if not template["active"]:
            raise MailTemplateError("MAIL_TEMPLATE_INACTIVE", "邮件模板已停用。", status=409)
        if not isinstance(variables, Mapping):
            raise MailTemplateError("MAIL_TEMPLATE_VARIABLES_INVALID", "模板变量必须是对象。")
        unknown = set(variables) - ALLOWED_VARIABLES
        if unknown:
            raise MailTemplateError("MAIL_TEMPLATE_VARIABLE_UNKNOWN", "模板变量包含未允许的名称。")
        missing = [name for name in template["required_variables"] if name not in variables or variables[name] is None]
        if missing:
            raise MailTemplateError("MAIL_TEMPLATE_VARIABLE_MISSING", "缺少必填模板变量。")
        normalized: dict[str, str] = {}
        for name, value in variables.items():
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise MailTemplateError("MAIL_TEMPLATE_VARIABLE_INVALID", "模板变量值无效。")
            text = str(value)
            if len(text) > VARIABLE_VALUE_LIMIT:
                raise MailTemplateError("MAIL_TEMPLATE_VARIABLE_TOO_LONG", "模板变量值超出长度限制。")
            normalized[name] = text

        def substitute(match: re.Match[str]) -> str:
            return normalized[match.group(1)]

        subject = VARIABLE_PATTERN.sub(substitute, template["subject_template"])
        body = VARIABLE_PATTERN.sub(substitute, template["body_template"])
        if "\r" in subject or "\n" in subject:
            raise MailTemplateError("MAIL_TEMPLATE_SUBJECT_INVALID", "渲染后的主题包含无效换行。")
        if len(subject) > SUBJECT_LIMIT or len(body) > BODY_LIMIT:
            raise MailTemplateError("MAIL_TEMPLATE_OUTPUT_TOO_LONG", "渲染后的邮件内容超出长度限制。")
        return {"template_id": template["template_id"], "template_version": template["template_version"],
                "language": template["language"], "subject": subject, "body": body, "tone": template["tone"]}

    def _validated(self, payload: Mapping[str, object], *, creating: bool) -> dict[str, Any]:
        allowed = {"copy_from_template_id", "template_group_id", "template_version", "template_id", "template_source",
                   "draft_type", "language", "name", "tone", "subject_template", "body_template", "required_variables",
                   "active", "created_at", "updated_at"}
        if set(payload) - allowed:
            raise MailTemplateError("MAIL_TEMPLATE_INVALID", "邮件模板包含不支持的字段。")
        draft_type = self._draft_type(payload.get("draft_type"))
        language = normalize_language_tag(payload.get("language"))
        name = self._text(payload.get("name"), "模板名称", 200, False)
        tone = self._text(payload.get("tone"), "语气", 80, False)
        subject = self._text(payload.get("subject_template"), "主题模板", SUBJECT_LIMIT, True)
        body = self._text(payload.get("body_template"), "正文模板", BODY_LIMIT, False, header=False)
        placeholders = self._placeholders(subject) | self._placeholders(body)
        declared = payload.get("required_variables")
        if declared is not None:
            if not isinstance(declared, list) or any(not isinstance(item, str) for item in declared):
                raise MailTemplateError("MAIL_TEMPLATE_VARIABLES_INVALID", "必填变量列表无效。")
            if set(declared) != placeholders:
                raise MailTemplateError("MAIL_TEMPLATE_VARIABLES_MISMATCH", "必填变量与模板占位符不一致。")
        return {"draft_type": draft_type, "language": language, "name": name, "tone": tone,
                "subject_template": subject, "body_template": body, "required_variables": sorted(placeholders)}

    @staticmethod
    def _placeholders(text: str) -> set[str]:
        names = set(VARIABLE_PATTERN.findall(text))
        if "{{" in VARIABLE_PATTERN.sub("", text) or "}}" in VARIABLE_PATTERN.sub("", text):
            raise MailTemplateError("MAIL_TEMPLATE_SYNTAX_INVALID", "模板占位符语法无效。")
        if names - ALLOWED_VARIABLES:
            raise MailTemplateError("MAIL_TEMPLATE_VARIABLE_UNKNOWN", "模板包含未允许的变量。")
        return names

    @staticmethod
    def _text(value: object, name: str, maximum: int, allow_empty: bool, *, header: bool = True) -> str:
        text = str(value or "")
        if header and ("\r" in text or "\n" in text):
            raise MailTemplateError("MAIL_TEMPLATE_HEADER_INJECTION", f"{name}不能包含换行符。")
        if not allow_empty and not text.strip():
            raise MailTemplateError("MAIL_TEMPLATE_FIELD_REQUIRED", f"{name}不能为空。")
        if len(text) > maximum:
            raise MailTemplateError("MAIL_TEMPLATE_FIELD_TOO_LONG", f"{name}超出长度限制。")
        return text

    @staticmethod
    def _draft_type(value: object) -> str:
        normalized = str(value or "").strip()
        if normalized not in ALLOWED_DRAFT_TYPES:
            raise MailTemplateError("MAIL_TEMPLATE_DRAFT_TYPE_INVALID", "邮件用途无效。")
        return normalized

    def _insert(self, group_id: str, version: int, values: Mapping[str, Any]) -> dict[str, Any]:
        now = self._timestamp()
        with self._factory_provider().write_transaction() as connection:
            return self._insert_with_connection(connection, group_id, version, values, now)

    @staticmethod
    def _insert_with_connection(connection, group_id: str, version: int, values: Mapping[str, Any], now: str) -> dict[str, Any]:
        template_id = f"template_{uuid.uuid4().hex}"
        connection.execute(
            "INSERT INTO mail_templates(template_id,template_group_id,template_version,template_source,draft_type,"
            "language,name,tone,subject_template,body_template,required_variables,active,created_at,updated_at) "
            "VALUES (?,?,?,'user',?,?,?,?,?,?,?,1,?,?)",
            (template_id, group_id, version, values["draft_type"], values["language"], values["name"], values["tone"],
             values["subject_template"], values["body_template"], json.dumps(values["required_variables"]), now, now),
        )
        return {"template_id": template_id, "template_group_id": group_id, "template_version": version,
                "template_source": "user", **dict(values), "active": True, "created_at": now, "updated_at": now}

    @staticmethod
    def _row(row: Any) -> dict[str, Any]:
        value = dict(row)
        value["required_variables"] = json.loads(value["required_variables"])
        value["active"] = bool(value["active"])
        return value

    @staticmethod
    def _builtin(value: Mapping[str, Any]) -> dict[str, Any]:
        return {**dict(value), "created_at": None, "updated_at": None}

    def _timestamp(self) -> str:
        return self._now().astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
