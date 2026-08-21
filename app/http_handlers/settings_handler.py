"""Settings, health, account, and mail HTTP endpoints."""


def _merge_mail_configuration_update(payload: dict, existing_mail: dict | None, services: dict) -> dict:
    """Apply only explicitly supplied mail fields, then normalize the complete state."""
    current = services["normalize_mail_state"](existing_mail)
    supplied = services["merge_masked_mail_passwords"](payload, current)
    merged = dict(current)
    for field in ("accounts", "template_subject", "template_body"):
        if field in supplied:
            merged[field] = supplied[field]
    return services["normalize_mail_state"](merged)


def handle(handler, request: dict, context: dict) -> bool:
    method = request["method"]
    path = request["path"]
    state_access = context["state"]
    services = context["services"]
    modules = context["modules"]

    # GET /api/system/health → 读取系统健康检查；{"ok": true, "status": "ok", "checks": [...], "debug": {...}}
    if method == "GET" and path == "/api/system/health":
        handler._json({"ok": True, **services["get_system_health"]()})
        return True

    # GET /api/state → 读取客户端设置（敏感值已遮罩）；{"ui": {...}, "profiles": [...], "selectedProfile": "...", "accounts": [...], "feishu": {...}, "creator_library": {...}, "mail": {...}}
    if method == "GET" and path == "/api/state":
        state = state_access["get"]()
        four_table_config = services["get_four_table_feishu_config"]()
        client_state = services["state_for_client"](state)
        client_feishu = client_state["feishu"]
        handler._json(
            {
                "ui": client_state["ui"],
                "profiles": services["get_profiles"](),
                "selectedProfile": client_state["profiles"].get("selected", "Default"),
                "accounts": services["build_accounts_payload"](),
                "feishu": {
                    "app_id": client_feishu.get("app_id", ""),
                    "app_secret": client_feishu.get("app_secret", ""),
                    "has_app_secret": bool(state["feishu"].get("app_secret")),
                    "app_token": client_feishu.get("app_token", ""),
                    "has_app_token": bool(four_table_config["app_token"]),
                    "creator_table_id": four_table_config["creator_table_id"],
                    "account_table_id": four_table_config["account_table_id"],
                    "agency_table_id": four_table_config["agency_table_id"],
                    "contact_table_id": four_table_config["contact_table_id"],
                },
                "creator_library": client_state.get("creator_library", {}),
                "mail": client_state["mail"],
            }
        )
        return True

    # GET /api/mail/inbox/messages → 读取最近邮件；{"ok": true, "updated_at": "...", "summary": {...}, "messages": [...], "accounts": {...}}
    if method == "GET" and path == "/api/mail/inbox/messages":
        data = modules["mail_sync"].load_mail_messages()
        messages = data.get("messages") if isinstance(data.get("messages"), list) else []
        summary = {
            "total": len(messages),
            "unread": sum(1 for item in messages if isinstance(item, dict) and item.get("is_unread")),
            "matched": sum(
                1 for item in messages
                if isinstance(item, dict) and item.get("reply_status") == "matched"
            ),
        }
        handler._ok(
            updated_at=str(data.get("updated_at") or ""),
            summary=summary,
            messages=messages[:50],
            accounts=data.get("accounts") if isinstance(data.get("accounts"), dict) else {},
        )
        return True

    if method != "POST":
        return False

    settings_paths = {
        "/api/settings/ui", "/api/settings/profiles", "/api/settings/accounts",
        "/api/account/open", "/api/settings/feishu", "/api/settings/mail",
        "/api/settings/creator-library", "/api/mail/test", "/api/mail/inbox/sync",
        "/api/mail/inbox/sync-crm-replies",
    }
    if path not in settings_paths:
        return False

    payload = request["get_payload"]()
    state = state_access["get"]()

    # POST /api/settings/ui → 保存界面设置；{"ok": true}
    if path == "/api/settings/ui":
        language = (payload.get("language") or "").strip()
        state["ui"]["language"] = "en" if language == "en" else "zh"
        state["ui"]["debug_mode"] = bool(payload.get("debug_mode"))
        state_access["save"]()
        handler._ok()
        return True

    # POST /api/settings/profiles → 保存自动化 Profile；{"ok": true}
    if path == "/api/settings/profiles":
        state["profiles"]["selected"] = (
            (payload.get("selected") or "").strip() or context["config"]["automation_profile_name"]
        )
        state_access["save"]()
        handler._ok()
        return True

    # POST /api/settings/accounts → 保存账号列表；{"ok": true}
    if path == "/api/settings/accounts":
        entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
        state["accounts"]["entries"] = [
            {
                "profile": str(item.get("profile") or "").strip(),
                "alias": str(item.get("alias") or "").strip(),
                "usage": str(item.get("usage") or "通用").strip() or "通用",
            }
            for item in entries
            if isinstance(item, dict) and str(item.get("profile") or "").strip()
        ]
        state_access["save"]()
        handler._ok()
        return True

    # POST /api/account/open → 打开指定 Chrome Profile；{"ok": true}
    if path == "/api/account/open":
        profile = (payload.get("profile") or "").strip()
        if not profile:
            handler._error("缺少 profile。")
            return True
        services["open_chrome_profile"](profile)
        handler._ok()
        return True

    # POST /api/settings/feishu → 保存飞书配置；{"ok": true}
    if path == "/api/settings/feishu":
        state["feishu"]["app_id"] = str(payload.get("app_id") or "").strip()
        new_secret = str(payload.get("app_secret") or "").strip()
        if new_secret and not services["is_sensitive_mask"](new_secret):
            state["feishu"]["app_secret"] = new_secret
        for key in (
            "app_token", "creator_table_id", "account_table_id", "agency_table_id", "contact_table_id",
        ):
            if key in payload:
                value = str(payload.get(key) or "").strip()
                if key == "app_token" and services["is_sensitive_mask"](value):
                    continue
                state["feishu"][key] = value
        state_access["normalize_and_save"]()
        handler._ok()
        return True

    # POST /api/settings/mail → 保存邮件配置；{"ok": true}
    if path == "/api/settings/mail":
        state["mail"] = _merge_mail_configuration_update(payload, state.get("mail"), services)
        state_access["save"]()
        handler._ok()
        return True

    # POST /api/settings/creator-library → 保存达人库工作簿路径；{"ok": true}
    if path == "/api/settings/creator-library":
        try:
            state["creator_library"]["workbook_path"] = services["normalize_creator_library_workbook_path"](
                payload.get("workbook_path")
            )
        except ValueError as exc:
            handler._error(str(exc))
            return True
        state_access["save"]()
        handler._ok()
        return True

    # POST /api/mail/test → 测试邮件账号连接；{"ok": true}
    if path == "/api/mail/test":
        raw_account = payload.get("account") if isinstance(payload.get("account"), dict) else payload
        merged_test_accounts = services["merge_masked_mail_passwords"](
            {"accounts": [raw_account]}, state.get("mail")
        ).get("accounts", [])
        account = services["normalize_mail_account"](merged_test_accounts[0] if merged_test_accounts else None)
        services["test_imap_login"](account)
        services["test_smtp_login"](account)
        handler._ok(imap_ok=True, smtp_ok=True)
        return True

    # POST /api/mail/inbox/sync → 同步收件箱；{"ok": true, "updated_at": "...", "accounts_checked": 0, "messages_fetched": 0, "messages_new": 0, "matched_messages": 0, "messages_total": 0, "errors": [...]}
    if path == "/api/mail/inbox/sync":
        accounts = state.get("mail", {}).get("accounts") if isinstance(state.get("mail"), dict) else []
        enabled_accounts = [item for item in accounts if isinstance(item, dict) and item.get("enabled")]
        if not enabled_accounts:
            handler._error("没有启用的邮箱账户。")
            return True
        limit_per_account = payload.get("limit_per_account") or 20
        four_table_config = services["get_four_table_feishu_config"]()
        required_keys = ("app_id", "app_secret", "app_token", "creator_table_id", "account_table_id")
        missing_keys = [key for key in required_keys if not four_table_config.get(key)]
        if missing_keys:
            handler._error(f"四表飞书配置不完整：缺少 {', '.join(missing_keys)}。")
            return True
        result = modules["mail_sync"].sync_enabled_mail_accounts(
            enabled_accounts,
            {"limit_per_account": limit_per_account, "four_table_config": four_table_config},
        )
        handler._ok(
            updated_at=str(result.get("updated_at") or ""),
            accounts_checked=int(result.get("accounts_checked") or 0),
            messages_fetched=int(result.get("messages_fetched") or 0),
            messages_new=int(result.get("messages_new") or 0),
            matched_messages=int(result.get("matched_messages") or 0),
            messages_total=int(result.get("messages_total") or 0),
            errors=result.get("errors") if isinstance(result.get("errors"), list) else [],
        )
        return True

    # POST /api/mail/inbox/sync-crm-replies → 同步达人邮件回复；{"ok": true, "updated_at": "...", "updated": 0, "time_only": 0, "skipped": 0, "failed": 0, "processed_messages": 0, "errors": [...]}
    four_table_config = services["get_four_table_feishu_config"]()
    required_keys = ("app_id", "app_secret", "app_token", "creator_table_id")
    missing_keys = [key for key in required_keys if not four_table_config.get(key)]
    if missing_keys:
        handler._error(f"达人表飞书配置不完整：缺少 {', '.join(missing_keys)}。")
        return True
    result = modules["mail_sync"].sync_creator_replies(four_table_config)
    handler._ok(
        updated_at=str(result.get("updated_at") or ""),
        updated=int(result.get("updated") or 0),
        time_only=int(result.get("time_only") or 0),
        skipped=int(result.get("skipped") or 0),
        failed=int(result.get("failed") or 0),
        processed_messages=int(result.get("processed_messages") or 0),
        errors=result.get("errors") if isinstance(result.get("errors"), list) else [],
    )
    return True
