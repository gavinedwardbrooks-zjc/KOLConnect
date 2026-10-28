from __future__ import annotations

"""Configuration and explicit health endpoints for the generative AI boundary."""

from services.ai_provider import AIProviderError
from services.ai_provider_configuration import AIProviderConfigurationError
from services.ai_secret_storage import AISecretStorageError


def handle(handler, request: dict, context: dict) -> bool:
    method = request["method"]
    path = request["path"]
    if path not in {"/api/settings/ai-provider", "/api/settings/ai-provider/health"}:
        return False
    service = context["services"]["ai_provider_configuration"]

    if method == "GET" and path == "/api/settings/ai-provider":
        try:
            handler._json({"ok": True, "configuration": service.client_configuration()})
        except (AIProviderConfigurationError, AISecretStorageError):
            handler._api_error(
                "AI_PROVIDER_CONFIGURATION_UNAVAILABLE",
                "AI provider configuration is unavailable.",
                status=500,
            )
        return True

    if method != "POST":
        return False

    payload = request["get_payload"]()
    if not isinstance(payload, dict):
        handler._api_error(
            "AI_PROVIDER_REQUEST_INVALID",
            "AI provider request must be an object.",
            status=400,
        )
        return True
    if path == "/api/settings/ai-provider":
        try:
            configuration = service.update(payload)
            handler._json({"ok": True, "configuration": configuration})
        except (AIProviderConfigurationError, AISecretStorageError) as exc:
            context["logging"]["error"](
                "AIProviderConfiguration",
                f"AI provider configuration update failed; no credential content was logged. exception_type={type(exc).__name__}",
            )
            handler._api_error(
                getattr(exc, "code", "AI_PROVIDER_CONFIGURATION_INVALID"),
                "AI provider configuration was not saved.",
                status=400,
            )
        return True

    if set(payload) - {"remote"} or payload.get("remote") is not True:
        handler._api_error(
            "AI_PROVIDER_TEST_CONFIRMATION_REQUIRED",
            "Remote AI provider tests must be explicitly requested.",
            status=400,
        )
        return True
    try:
        result = service.health_check(remote=payload.get("remote") is True)
        handler._json({"ok": bool(result.get("ok")), "health": result})
    except AIProviderError as exc:
        handler._api_error(exc.code.value, str(exc), status=503)
    except (AIProviderConfigurationError, AISecretStorageError):
        handler._api_error(
            "AI_PROVIDER_CONFIGURATION_UNAVAILABLE",
            "AI provider configuration is unavailable.",
            status=500,
        )
    return True
