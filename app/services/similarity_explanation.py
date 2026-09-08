"""Optional provider boundary; no provider/network is configured by default.

Providers may select existing reason IDs, never add prose, metrics or identities.
This makes an untrusted explanation incapable of inventing structured facts.
"""

from copy import deepcopy


def explain_candidates(candidates, *, requested=False, provider=None):
    if not requested:
        return {"status": "not_requested", "explanations": []}
    if provider is None:
        return {"status": "unavailable", "reason": "provider_not_configured", "explanations": []}
    allowed = {row["creator_id"]: {item["id"]: item["text"] for item in row["why_recommended"]} for row in candidates}
    payload = [{"creator_id": row["creator_id"], "base_similarity_score": row["base_similarity_score"],
                "dimensions": row["dimensions"], "reasons": row["why_recommended"],
                "unavailable_dimensions": row["unavailable_dimensions"]} for row in candidates]
    try:
        response = provider.explain(deepcopy(payload))
        if not isinstance(response, list) or len(response) > len(candidates):
            raise ValueError("invalid explanation result")
        seen, explanations = set(), []
        for item in response:
            if not isinstance(item, dict) or set(item) != {"creator_id", "reason_ids"}:
                raise ValueError("invalid explanation fields")
            identity, reason_ids = item["creator_id"], item["reason_ids"]
            if identity not in allowed or identity in seen or not isinstance(reason_ids, list):
                raise ValueError("invalid explanation identity")
            if any(not isinstance(key, str) or key not in allowed[identity] for key in reason_ids):
                raise ValueError("unsupported explanation")
            seen.add(identity)
            explanations.append({"creator_id": identity, "text": "；".join(allowed[identity][key] for key in dict.fromkeys(reason_ids))})
        explanations.sort(key=lambda item: item["creator_id"])
        return {"status": "available", "explanations": explanations}
    except Exception:
        return {"status": "unavailable", "reason": "provider_failed_or_invalid", "explanations": []}
