from __future__ import annotations

"""Provider-neutral contracts for bounded generative AI requests."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, Mapping, Protocol, TypeVar


T = TypeVar("T")


class AIProviderErrorCode(str, Enum):
    DISABLED = "AI_PROVIDER_DISABLED"
    UNAVAILABLE = "AI_PROVIDER_UNAVAILABLE"
    AUTHENTICATION_FAILED = "AI_PROVIDER_AUTHENTICATION_FAILED"
    RATE_LIMITED = "AI_PROVIDER_RATE_LIMITED"
    TIMEOUT = "AI_PROVIDER_TIMEOUT"
    CONNECTION_FAILED = "AI_PROVIDER_CONNECTION_FAILED"
    INVALID_OUTPUT = "AI_PROVIDER_INVALID_OUTPUT"
    UNSAFE_ENDPOINT = "AI_PROVIDER_UNSAFE_ENDPOINT"


class AIProviderError(RuntimeError):
    """Safe typed error that never contains prompts, responses, or credentials."""

    def __init__(
        self,
        code: AIProviderErrorCode,
        message: str,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class AIRequest:
    trace_id: str
    feature: str
    instruction: str
    data: Mapping[str, Any] = field(default_factory=dict)
    input_schema_version: str = "1"
    output_schema_version: str = "1"

    def __post_init__(self) -> None:
        if not self.trace_id.strip() or len(self.trace_id) > 128:
            raise ValueError("AI request trace_id is required and must be at most 128 characters.")
        if not self.feature.strip() or len(self.feature) > 80:
            raise ValueError("AI request feature is required and must be at most 80 characters.")
        if not self.instruction.strip() or len(self.instruction) > 4000:
            raise ValueError("AI request instruction is required and must be at most 4000 characters.")


@dataclass(frozen=True)
class AIUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class AIResponseMetadata:
    trace_id: str
    feature: str
    provider: str
    model: str
    latency_ms: int
    status: str
    input_schema_version: str
    output_schema_version: str
    usage: AIUsage = field(default_factory=AIUsage)


@dataclass(frozen=True)
class AIResponse(Generic[T]):
    value: T
    metadata: AIResponseMetadata


@dataclass(frozen=True)
class AIProviderMetadata:
    provider: str
    model: str
    enabled: bool
    available: bool
    supports_structured_output: bool
    adapter_version: str = "1"


class AIProvider(Protocol):
    """Generation only. This boundary intentionally exposes no tools or repositories."""

    def generate_text(self, request: AIRequest) -> AIResponse[str]: ...

    def generate_structured(
        self,
        request: AIRequest,
        output_schema: Mapping[str, Any],
    ) -> AIResponse[dict[str, Any]]: ...

    def health_check(self, *, remote: bool = False) -> dict[str, Any]: ...

    def provider_metadata(self) -> AIProviderMetadata: ...


class UnavailableAIProvider:
    def __init__(self, *, reason: str = "unavailable", disabled: bool = False) -> None:
        self._reason = reason if reason in {"disabled", "unavailable", "configuration_incomplete"} else "unavailable"
        self._disabled = disabled

    def _raise(self) -> None:
        code = AIProviderErrorCode.DISABLED if self._disabled else AIProviderErrorCode.UNAVAILABLE
        message = "AI provider is disabled." if self._disabled else "AI provider is unavailable."
        raise AIProviderError(code, message)

    def generate_text(self, request: AIRequest) -> AIResponse[str]:
        self._raise()

    def generate_structured(
        self,
        request: AIRequest,
        output_schema: Mapping[str, Any],
    ) -> AIResponse[dict[str, Any]]:
        self._raise()

    def health_check(self, *, remote: bool = False) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "disabled" if self._disabled else "unavailable",
            "remote": False,
            "reason": self._reason,
        }

    def provider_metadata(self) -> AIProviderMetadata:
        return AIProviderMetadata(
            provider="disabled" if self._disabled else "unavailable",
            model="",
            enabled=not self._disabled,
            available=False,
            supports_structured_output=False,
        )
