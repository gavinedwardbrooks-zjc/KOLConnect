from __future__ import annotations

"""Read-only, user-triggered Creator AI decision orchestration."""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol

from domain.money import grouped_amounts
from domain.normalization import normalize_followers, normalize_number, normalize_tags
from services.ai_provider import AIProviderError, AIProviderErrorCode, AIRequest
from services.creator_intelligence_service import CreatorIntelligenceService
from services.creator_summary_service import CreatorSummaryService
from services.openai_compatible_ai_provider import validate_json_schema


CREATOR_DECISION_INPUT_SCHEMA_VERSION = "m9.1-b-input-v1"
CREATOR_DECISION_OUTPUT_SCHEMA_VERSION = "m9.1-b-output-v1"
CREATOR_DECISION_SERVICE_VERSION = "m9.1-b-v1"
MAX_ACCOUNTS = 20
MAX_HISTORY_RECORDS = 20

CREATOR_DECISION_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "recommendation": {
            "type": "string",
            "enum": ["recommend", "consider", "not_recommend", "insufficient_data"],
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "summary": {"type": "string", "minLength": 1, "maxLength": 1200},
        "reasons": {"type": "array", "maxItems": 8, "items": {"type": "string", "minLength": 1, "maxLength": 300}},
        "risks": {"type": "array", "maxItems": 8, "items": {"type": "string", "minLength": 1, "maxLength": 300}},
        "missing_information": {
            "type": "array", "maxItems": 8, "items": {"type": "string", "minLength": 1, "maxLength": 300},
        },
        "suggested_next_actions": {
            "type": "array", "maxItems": 8, "items": {"type": "string", "minLength": 1, "maxLength": 300},
        },
    },
    "required": [
        "recommendation", "confidence", "summary", "reasons", "risks",
        "missing_information", "suggested_next_actions",
    ],
    "additionalProperties": False,
}

DECISION_INSTRUCTION = """Assess whether the recorded Creator may merit further cooperation consideration.
Use only supplied facts. Do not infer missing values, identities, prices, performance, campaign goals, or business status.
Keep metrics separated by account and platform. Never add monetary values across currencies.
Without explicit decision_context, provide only a general recommendation based on recorded evidence.
If evidence is insufficient, recommendation must be insufficient_data and confidence must be low.
Return JSON matching the supplied output schema."""


class CreatorDecisionReader(Protocol):
    def getCreatorIntelligenceSourceData(self, creator_id: str) -> dict[str, Any]: ...


class AIProviderConfigurationPort(Protocol):
    def client_configuration(self) -> dict[str, Any]: ...

    def create_provider(self) -> Any: ...


class CreatorAIDecisionError(ValueError):
    def __init__(self, code: str, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class CreatorDecisionInput:
    creator_id: str
    creator: dict[str, Any]
    accounts: list[dict[str, Any]]
    historical: dict[str, Any]
    limitations: list[str]
    decision_context: dict[str, Any] | None
    evidence_level: str
    schema_version: str = CREATOR_DECISION_INPUT_SCHEMA_VERSION

    def provider_data(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "creator_id": self.creator_id,
            "creator": self.creator,
            "accounts": self.accounts,
            "historical": self.historical,
            "limitations": self.limitations,
            "decision_context": self.decision_context,
            "evidence_level": self.evidence_level,
        }

    def fingerprint(self) -> str:
        payload = json.dumps(
            self.provider_data(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class _DetachedCreatorFacts:
    """Feed one detached repository read through existing deterministic services."""

    def __init__(self, source: dict[str, Any]) -> None:
        self.source = source

    def getCreatorIntelligenceSourceData(self, _creator_id: str) -> dict[str, Any]:
        return self.source

    def getCreatorSummarySourceData(self, _creator_id: str) -> dict[str, Any]:
        return {
            "creator": self.source.get("creator") or {},
            "insight": self.source.get("insight") or {},
            "snapshots": self.source.get("snapshots") or [],
            "campaign_creator_count": len(self.source.get("campaign_creators") or []),
        }


class CreatorAIDecisionService:
    def __init__(
        self,
        repository_provider: Callable[[], CreatorDecisionReader],
        ai_configuration: AIProviderConfigurationPort,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository_provider = repository_provider
        self._ai_configuration = ai_configuration
        self._now = now or (lambda: datetime.now(timezone.utc))

    def get_capability_and_facts(
        self,
        creator_id: object,
        *,
        decision_context: object = None,
    ) -> dict[str, Any]:
        normalized_id = self._creator_id(creator_id)
        context = self._decision_context(decision_context)
        decision_input, deterministic = self._build_input(normalized_id, context)
        configuration_error = None
        try:
            configuration = self._ai_configuration.client_configuration()
        except (ValueError, RuntimeError):
            configuration = {}
            configuration_error = AIProviderErrorCode.UNAVAILABLE.value
        return {
            "mode": "deterministic_preview",
            "schema_version": CREATOR_DECISION_OUTPUT_SCHEMA_VERSION,
            "status": "ready" if decision_input.evidence_level != "insufficient" else "insufficient_data",
            "capability": {
                "enabled": bool(configuration.get("enabled")),
                "key_configured": bool(configuration.get("key_configured")),
                "provider": str(configuration.get("provider") or ""),
                "model": str(configuration.get("model") or ""),
                "selected_endpoint": str(configuration.get("base_url") or ""),
                "byok": True,
                "remote_request_performed": False,
                "error_code": configuration_error,
            },
            "input": decision_input.provider_data(),
            "input_fingerprint": decision_input.fingerprint(),
            "deterministic": deterministic,
            "decision": None,
        }

    def generate_decision(
        self,
        creator_id: object,
        *,
        trace_id: str,
        decision_context: object = None,
    ) -> dict[str, Any]:
        normalized_id = self._creator_id(creator_id)
        context = self._decision_context(decision_context)
        decision_input, deterministic = self._build_input(normalized_id, context)
        fingerprint = decision_input.fingerprint()
        generated_at = self._timestamp()

        if decision_input.evidence_level == "insufficient":
            return {
                "mode": "deterministic_guard",
                "schema_version": CREATOR_DECISION_OUTPUT_SCHEMA_VERSION,
                "provider": "not_called",
                "model": "",
                "generated_at": generated_at,
                "trace_id": trace_id,
                "input_fingerprint": fingerprint,
                "status": "insufficient_data",
                "decision": self._insufficient_decision(decision_input.limitations),
                "deterministic": deterministic,
                "remote_request_performed": False,
            }

        request = AIRequest(
            trace_id=trace_id,
            feature="creator_ai_decision",
            instruction=DECISION_INSTRUCTION,
            data=decision_input.provider_data(),
            input_schema_version=CREATOR_DECISION_INPUT_SCHEMA_VERSION,
            output_schema_version=CREATOR_DECISION_OUTPUT_SCHEMA_VERSION,
        )
        metadata = None
        try:
            provider = self._ai_configuration.create_provider()
            metadata = provider.provider_metadata()
            response = provider.generate_structured(request, CREATOR_DECISION_OUTPUT_SCHEMA)
            validate_json_schema(response.value, CREATOR_DECISION_OUTPUT_SCHEMA)
            self._enforce_evidence_policy(response.value, decision_input)
        except AIProviderError as exc:
            return self._provider_fallback(
                code=exc.code.value,
                retryable=exc.retryable,
                metadata=metadata,
                generated_at=generated_at,
                trace_id=trace_id,
                fingerprint=fingerprint,
                deterministic=deterministic,
            )
        except (ValueError, RuntimeError):
            return self._provider_fallback(
                code=AIProviderErrorCode.UNAVAILABLE.value,
                retryable=False,
                metadata=metadata,
                generated_at=generated_at,
                trace_id=trace_id,
                fingerprint=fingerprint,
                deterministic=deterministic,
            )

        return {
            "mode": "ai",
            "schema_version": CREATOR_DECISION_OUTPUT_SCHEMA_VERSION,
            "provider": response.metadata.provider,
            "model": response.metadata.model,
            "generated_at": generated_at,
            "trace_id": response.metadata.trace_id,
            "input_fingerprint": fingerprint,
            "status": "success",
            "decision": response.value,
            "diagnostics": {
                "latency_ms": response.metadata.latency_ms,
                "input_schema_version": response.metadata.input_schema_version,
                "output_schema_version": response.metadata.output_schema_version,
                "usage": {
                    "input_tokens": response.metadata.usage.input_tokens,
                    "output_tokens": response.metadata.usage.output_tokens,
                    "total_tokens": response.metadata.usage.total_tokens,
                },
            },
            "remote_request_performed": True,
        }

    @staticmethod
    def _provider_fallback(
        *,
        code: str,
        retryable: bool,
        metadata: object,
        generated_at: str,
        trace_id: str,
        fingerprint: str,
        deterministic: dict[str, Any],
    ) -> dict[str, Any]:
        provider = str(getattr(metadata, "provider", None) or "unavailable")
        model = str(getattr(metadata, "model", None) or "")
        return {
            "mode": "deterministic_fallback",
            "schema_version": CREATOR_DECISION_OUTPUT_SCHEMA_VERSION,
            "provider": provider,
            "model": model,
            "generated_at": generated_at,
            "trace_id": trace_id,
            "input_fingerprint": fingerprint,
            "status": "provider_error",
            "provider_error": {"code": code, "retryable": retryable},
            "decision": None,
            "deterministic": deterministic,
            "remote_request_performed": bool(getattr(metadata, "available", False)),
        }

    def _build_input(
        self,
        creator_id: str,
        decision_context: dict[str, Any] | None,
    ) -> tuple[CreatorDecisionInput, dict[str, Any]]:
        source = self._repository_provider().getCreatorIntelligenceSourceData(creator_id)
        detached = _DetachedCreatorFacts(source)
        intelligence = CreatorIntelligenceService(
            lambda: detached,
            now=self._now,
        ).get_creator_intelligence(creator_id)
        summary = CreatorSummaryService(
            lambda: detached,
            now_provider=self._now,
        ).get_creator_summary(creator_id)
        creator = source.get("creator") if isinstance(source.get("creator"), dict) else {}
        accounts, account_limitations = self._accounts(source)
        historical, historical_limitations = self._historical(source)
        limitations = self._limitations(
            creator,
            accounts,
            account_limitations + historical_limitations + list(intelligence.get("limitations") or []),
        )
        evidence_level = self._evidence_level(accounts, limitations)
        decision_input = CreatorDecisionInput(
            creator_id=creator_id,
            creator={
                "name": self._bounded_text(creator.get("name"), 200) or None,
                "country": self._bounded_text(creator.get("country"), 80) or None,
                "language": self._bounded_text(creator.get("language"), 80) or None,
                "content_category": self._bounded_text(creator.get("content_category"), 120) or None,
                "tags": normalize_tags(creator.get("tags"))[:20],
                "bio": self._bounded_text(creator.get("bio"), 1000) or None,
            },
            accounts=accounts,
            historical=historical,
            limitations=limitations,
            decision_context=decision_context,
            evidence_level=evidence_level,
        )
        deterministic = {
            "summary_mode": summary.get("mode"),
            "data_status": summary.get("data_status"),
            "intelligence_mode": intelligence.get("mode"),
            "intelligence_version": intelligence.get("version"),
            "freshness": intelligence.get("data_freshness"),
            "confidence": intelligence.get("confidence"),
            "limitations": limitations,
        }
        return decision_input, deterministic

    def _accounts(self, source: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        snapshots = [row for row in source.get("snapshots") or [] if isinstance(row, dict)]
        result: list[dict[str, Any]] = []
        limitations: list[str] = []
        raw_accounts = [row for row in source.get("accounts") or [] if isinstance(row, dict)]
        for account in raw_accounts[:MAX_ACCOUNTS]:
            uid = str(account.get("account_uid") or "").strip()
            candidates = [row for row in snapshots if uid and str(row.get("account_uid") or "") == uid]
            candidates.sort(key=lambda row: str(row.get("captured_at") or ""), reverse=True)
            latest = candidates[0] if candidates else {}
            followers_raw = account.get("followers")
            if followers_raw in (None, ""):
                followers_raw = latest.get("followers")
            measured_at = str(latest.get("captured_at") or account.get("last_scrape_time") or "").strip() or None
            result.append({
                "account_uid": uid or None,
                "platform": self._bounded_text(account.get("platform"), 40) or None,
                "username": self._bounded_text(account.get("username"), 200) or None,
                "followers": normalize_followers(followers_raw),
                "average_views": self._number(latest.get("average_views")),
                "median_views": self._number(latest.get("median_views")),
                "video_count": self._nonnegative_integer(latest.get("video_count")),
                "measured_at": measured_at,
                "freshness": self._freshness(measured_at),
                "source": self._bounded_text(latest.get("source"), 80) or None,
            })
        if len(raw_accounts) > MAX_ACCOUNTS:
            limitations.append("account_list_truncated")
        if not result:
            limitations.append("missing_accounts")
        return result, limitations

    def _historical(self, source: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
        relations = [row for row in source.get("campaign_creators") or [] if isinstance(row, dict)]
        relations.sort(key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)
        quote_summary = grouped_amounts(relations, "creator_quote", "quote_currency")
        cost_summary = grouped_amounts(relations, "cost", "cost_currency")
        performance: list[dict[str, Any]] = []
        for row in relations[:MAX_HISTORY_RECORDS]:
            views = self._nonnegative_number(row.get("views"))
            likes = self._nonnegative_number(row.get("likes"))
            comments = self._nonnegative_number(row.get("comments"))
            cost = self._nonnegative_number(row.get("cost"))
            currency = str(row.get("cost_currency") or "").strip().upper() or None
            engagements = None if likes is None and comments is None else (likes or 0) + (comments or 0)
            performance.append({
                "views": views,
                "likes": likes,
                "comments": comments,
                "recorded_at": str(row.get("updated_at") or row.get("created_at") or "").strip() or None,
                "cpv": (cost / views) if cost is not None and views and currency else None,
                "cpe": (cost / engagements) if cost is not None and engagements and currency else None,
                "metric_currency": currency if cost is not None and currency else None,
            })
        limitations: list[str] = []
        if not relations:
            limitations.append("no_recorded_collaboration")
        if quote_summary["recorded_amount_count"] == 0:
            limitations.append("missing_recorded_quote")
        if cost_summary["recorded_amount_count"] == 0:
            limitations.append("missing_recorded_cost")
        if not any(any(row.get(field) is not None for field in ("views", "likes", "comments")) for row in performance):
            limitations.append("missing_recorded_performance")
        if quote_summary["multiple_currencies"] or cost_summary["multiple_currencies"]:
            limitations.append("multiple_currencies_not_combined")
        if len(relations) > MAX_HISTORY_RECORDS:
            limitations.append("history_truncated")
        return {
            "recorded_collaboration_count": len(relations),
            "quotes": self._money_summary(quote_summary),
            "costs": self._money_summary(cost_summary),
            "performance": performance,
        }, limitations

    @staticmethod
    def _money_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "recorded_amount_count": int(summary.get("recorded_amount_count") or 0),
            "totals_by_currency": dict(summary.get("totals_by_currency") or {}),
            "unknown_currency_total": summary.get("unknown_currency_total"),
            "multiple_currencies": bool(summary.get("multiple_currencies")),
        }

    def _limitations(
        self,
        creator: Mapping[str, Any],
        accounts: list[dict[str, Any]],
        inherited: list[str],
    ) -> list[str]:
        values = [str(value) for value in inherited if str(value)]
        for field in ("country", "language", "content_category"):
            if not str(creator.get(field) or "").strip():
                values.append(f"missing_{field}")
        for account in accounts:
            uid = str(account.get("account_uid") or "unknown")
            if all(account.get(field) is None for field in ("followers", "average_views", "median_views", "video_count")):
                values.append(f"account_metrics_missing:{uid}")
            if account.get("freshness") in {"stale", "unknown"}:
                values.append(f"account_data_{account.get('freshness')}:{uid}")
        return list(dict.fromkeys(values))[:30]

    @staticmethod
    def _evidence_level(accounts: list[dict[str, Any]], limitations: list[str]) -> str:
        usable = any(
            any(account.get(field) is not None for field in ("followers", "average_views", "median_views", "video_count"))
            for account in accounts
        )
        if not accounts or not usable:
            return "insufficient"
        if any("stale" in item or "unknown" in item for item in limitations):
            return "limited"
        return "sufficient"

    @staticmethod
    def _enforce_evidence_policy(decision: Mapping[str, Any], decision_input: CreatorDecisionInput) -> None:
        if decision.get("recommendation") == "insufficient_data" and decision.get("confidence") != "low":
            raise AIProviderError(AIProviderErrorCode.INVALID_OUTPUT, "AI output confidence conflicts with insufficient evidence.")
        if decision_input.evidence_level == "limited" and decision.get("confidence") == "high":
            raise AIProviderError(AIProviderErrorCode.INVALID_OUTPUT, "AI output confidence exceeds recorded evidence.")

    @staticmethod
    def _insufficient_decision(limitations: list[str]) -> dict[str, Any]:
        missing = [item for item in limitations if item.startswith(("missing_", "account_metrics_missing"))][:8]
        return {
            "recommendation": "insufficient_data",
            "confidence": "low",
            "summary": "现有记录不足以形成可靠的合作判断。",
            "reasons": [],
            "risks": ["基于不完整数据作出结论可能产生误导。"],
            "missing_information": missing or ["需要更多可验证的账号表现数据。"],
            "suggested_next_actions": ["补充或更新账号级公开表现数据后重新判断。"],
        }

    @staticmethod
    def _decision_context(value: object) -> dict[str, Any] | None:
        if value in (None, {}):
            return None
        if not isinstance(value, dict):
            raise CreatorAIDecisionError("INVALID_DECISION_CONTEXT", "decision_context must be an object.")
        allowed = {
            "objective": 500,
            "target_country": 80,
            "target_language": 80,
            "target_platform": 40,
            "budget_currency": 3,
        }
        unknown = set(value) - set(allowed)
        if unknown:
            raise CreatorAIDecisionError("INVALID_DECISION_CONTEXT", "decision_context contains unsupported fields.")
        normalized = {
            key: CreatorAIDecisionService._bounded_text(value.get(key), limit)
            for key, limit in allowed.items()
            if str(value.get(key) or "").strip()
        }
        currency = normalized.get("budget_currency")
        if currency:
            currency = currency.upper()
            if not re.fullmatch(r"[A-Z]{3}", currency):
                raise CreatorAIDecisionError("INVALID_DECISION_CONTEXT", "budget_currency must be an ISO currency code.")
            normalized["budget_currency"] = currency
        return normalized or None

    @staticmethod
    def _creator_id(value: object) -> str:
        creator_id = str(value or "").strip()
        if not creator_id or len(creator_id) > 128 or not re.fullmatch(r"[A-Za-z0-9_.:-]+", creator_id):
            raise CreatorAIDecisionError("INVALID_CREATOR_ID", "creator_id is invalid.")
        return creator_id

    @staticmethod
    def _bounded_text(value: object, limit: int) -> str:
        return str(value or "").strip()[:limit]

    @staticmethod
    def _number(value: object) -> int | float | None:
        number = normalize_number(value)
        if number is None or not math.isfinite(float(number)):
            return None
        return int(number) if float(number).is_integer() else float(number)

    @classmethod
    def _nonnegative_number(cls, value: object) -> int | float | None:
        number = cls._number(value)
        return number if number is not None and number >= 0 else None

    @classmethod
    def _nonnegative_integer(cls, value: object) -> int | None:
        number = cls._nonnegative_number(value)
        return int(number) if number is not None and float(number).is_integer() else None

    def _freshness(self, value: str | None) -> str:
        if not value:
            return "unknown"
        try:
            measured = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if measured.tzinfo is None:
                measured = measured.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return "unknown"
        now = self._now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        days = max(0, (now.astimezone(timezone.utc) - measured.astimezone(timezone.utc)).days)
        return "fresh" if days <= 7 else "aging" if days <= 30 else "stale"

    def _timestamp(self) -> str:
        value = self._now()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
