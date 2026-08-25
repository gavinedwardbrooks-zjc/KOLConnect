"""Optional Feishu Assistant long-connection controls."""


def handle(handler, request: dict, context: dict) -> bool:
    method = request["method"]
    path = request["path"]
    if path not in {
        "/api/feishu-chat/status",
        "/api/feishu-chat/enable",
        "/api/feishu-chat/disable",
        "/api/feishu-chat/test",
    }:
        return False

    transport = context["services"]["feishu_chat"]
    state_access = context["state"]
    if method == "GET" and path == "/api/feishu-chat/status":
        handler._ok(**transport.status())
        return True
    if method != "POST":
        return False

    state = state_access["get"]()
    if path == "/api/feishu-chat/enable":
        state["feishu"]["chat_enabled"] = True
        state_access["save"]()
        handler._ok(**transport.start())
        return True
    if path == "/api/feishu-chat/disable":
        state["feishu"]["chat_enabled"] = False
        state_access["save"]()
        handler._ok(**transport.stop())
        return True
    handler._ok(**transport.local_test())
    return True
