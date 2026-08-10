"""Product, Campaign, and CampaignCreator HTTP endpoints."""

import re


def handle(handler, request: dict, context: dict) -> bool:
    method = request["method"]
    path = request["path"]
    query = request["query"]
    repositories = context["repositories"]

    if method == "GET" and path == "/api/products":
        include_archived = str((query.get("include_archived") or [""])[0]).lower() == "true"
        try:
            products = repositories["product"]().getProducts(include_archived=include_archived)
            handler._json({"ok": True, "products": products})
        except (RuntimeError, ValueError) as exc:
            handler._repository_error(exc)
        return True

    product_match = re.fullmatch(r"/api/products/([^/]+)", path)
    if method == "GET" and product_match:
        try:
            handler._json({"ok": True, "product": repositories["product"]().getProduct(product_match.group(1))})
        except (RuntimeError, ValueError) as exc:
            handler._repository_error(exc)
        return True

    if method == "GET" and path == "/api/campaigns":
        try:
            campaigns = repositories["campaign"]().getCampaigns(
                product_id=(query.get("product_id") or [""])[0],
                status=(query.get("status") or [""])[0],
                creator_id=(query.get("creator_id") or [""])[0],
                include_archived=str((query.get("include_archived") or [""])[0]).lower() == "true",
            )
            handler._json({"ok": True, "campaigns": campaigns if isinstance(campaigns, list) else []})
        except (RuntimeError, ValueError) as exc:
            handler._repository_error(exc)
        return True

    campaign_creators_match = re.fullmatch(r"/api/campaigns/([^/]+)/creators", path)
    if method == "GET" and campaign_creators_match:
        campaign_id = campaign_creators_match.group(1)
        try:
            repositories["campaign"]().getCampaign(campaign_id)
            records = repositories["campaign_creator"]().getCampaignCreators(
                campaign_id=campaign_id,
                include_archived=str((query.get("include_archived") or [""])[0]).lower() == "true",
            )
            handler._json({"ok": True, "campaign_creators": records})
        except (RuntimeError, ValueError) as exc:
            handler._repository_error(exc)
        return True

    campaign_match = re.fullmatch(r"/api/campaigns/([^/]+)", path)
    if method == "GET" and campaign_match:
        try:
            handler._json({"ok": True, "campaign": repositories["campaign"]().getCampaign(campaign_match.group(1))})
        except (RuntimeError, ValueError) as exc:
            handler._repository_error(exc)
        return True

    if method == "POST" and path == "/api/products":
        payload = request["get_payload"]()
        try:
            product = repositories["product"]().createProduct(payload)
            handler._json({"ok": True, "product": product}, status=201)
        except ValueError as exc:
            handler._repository_error(exc)
        return True

    if method == "POST" and path == "/api/campaigns":
        payload = request["get_payload"]()
        try:
            campaign = repositories["campaign"]().createCampaign(payload)
            handler._json({"ok": True, "campaign": campaign}, status=201)
        except ValueError as exc:
            handler._repository_error(exc)
        return True

    if method == "POST" and campaign_creators_match:
        payload = request["get_payload"]()
        campaign_id = campaign_creators_match.group(1)
        supplied_campaign_id = str(payload.get("campaign_id") or "").strip()
        if supplied_campaign_id and supplied_campaign_id != campaign_id:
            handler._error("请求路径与数据中的 Campaign ID 不一致。")
            return True
        try:
            record = repositories["campaign_creator"]().createCampaignCreator(
                {**payload, "campaign_id": campaign_id}
            )
            handler._json({"ok": True, "campaign_creator": record}, status=201)
        except ValueError as exc:
            handler._repository_error(exc)
        return True

    if method == "PATCH" and product_match:
        payload = request["get_payload"]()
        try:
            repository = repositories["product"]()
            if "archived_at" in payload:
                product = repository.setProductArchivedAt(product_match.group(1), payload.get("archived_at"))
            elif payload.get("archived") is True:
                product = repository.archiveProduct(product_match.group(1))
            else:
                product = repository.updateProduct(product_match.group(1), payload)
            handler._json({"ok": True, "product": product})
        except ValueError as exc:
            handler._repository_error(exc)
        return True

    if method == "PATCH" and campaign_match:
        payload = request["get_payload"]()
        try:
            repository = repositories["campaign"]()
            if "archived_at" in payload:
                campaign = repository.setCampaignArchivedAt(campaign_match.group(1), payload.get("archived_at"))
            elif payload.get("archived") is True:
                campaign = repository.archiveCampaign(campaign_match.group(1))
            else:
                campaign = repository.updateCampaign(campaign_match.group(1), payload)
            handler._json({"ok": True, "campaign": campaign})
        except ValueError as exc:
            handler._repository_error(exc)
        return True

    campaign_creator_match = re.fullmatch(r"/api/campaign-creators/([^/]+)", path)
    if method == "PATCH" and campaign_creator_match:
        payload = request["get_payload"]()
        try:
            repository = repositories["campaign_creator"]()
            record = (
                repository.archiveCampaignCreator(campaign_creator_match.group(1))
                if payload.get("archived") is True
                else repository.updateCampaignCreator(campaign_creator_match.group(1), payload)
            )
            handler._json({"ok": True, "campaign_creator": record})
        except ValueError as exc:
            handler._repository_error(exc)
        return True

    if method == "DELETE" and campaign_creator_match:
        try:
            result = repositories["campaign_creator"]().remove_creator_from_campaign(
                campaign_creator_match.group(1)
            )
            handler._ok(**result)
        except ValueError as exc:
            handler._repository_error(exc)
        return True

    if method == "DELETE" and campaign_match:
        try:
            result = repositories["campaign"]().delete_campaign(campaign_match.group(1))
            handler._ok(**result)
        except ValueError as exc:
            handler._repository_error(exc)
        return True

    return False
