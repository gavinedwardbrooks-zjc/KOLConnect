"""Product, Campaign, and CampaignCreator HTTP endpoints."""

import re


CAMPAIGN_NOT_FOUND = "CAMPAIGN_NOT_FOUND"


def _campaign_repository_error(handler, exc: Exception) -> None:
    if isinstance(exc, ValueError) and "Campaign 不存在" in str(exc):
        handler._json({"ok": False, "error": CAMPAIGN_NOT_FOUND}, status=404)
        return
    handler._repository_error(exc)


def handle(handler, request: dict, context: dict) -> bool:
    method = request["method"]
    path = request["path"]
    query = request["query"]
    repositories = context["repositories"]
    invalidate_dashboard = context.get("services", {}).get(
        "invalidate_dashboard_response_cache", lambda: None
    )
    campaign_creator_service = context.get("services", {}).get("campaign_creator")

    # GET /api/products → {"ok": true, "products": [...]}
    if method == "GET" and path == "/api/products":
        include_archived = str((query.get("include_archived") or [""])[0]).lower() == "true"
        try:
            products = repositories["product"]().getProducts(include_archived=include_archived)
            handler._json({"ok": True, "products": products})
        except (RuntimeError, ValueError) as exc:
            handler._repository_error(exc)
        return True

    product_match = re.fullmatch(r"/api/products/([^/]+)", path)
    # GET /api/products/{product_id} → {"ok": true, "product": {...}}
    if method == "GET" and product_match:
        try:
            handler._json({"ok": True, "product": repositories["product"]().getProduct(product_match.group(1))})
        except (RuntimeError, ValueError) as exc:
            handler._repository_error(exc)
        return True

    # GET /api/campaigns → {"ok": true, "campaigns": [...]}
    if method == "GET" and path == "/api/campaigns":
        try:
            campaigns = repositories["campaign"]().getCampaigns(
                product_id=(query.get("product_id") or [""])[0],
                status=(query.get("status") or [""])[0],
                creator_id=(query.get("creator_id") or [""])[0],
                start_date_from=(query.get("start_date_from") or [""])[0],
                start_date_to=(query.get("start_date_to") or [""])[0],
                include_archived=str((query.get("include_archived") or [""])[0]).lower() == "true",
            )
            handler._json({"ok": True, "campaigns": campaigns if isinstance(campaigns, list) else []})
        except (RuntimeError, ValueError) as exc:
            handler._repository_error(exc)
        return True

    campaign_creators_match = re.fullmatch(r"/api/campaigns/([^/]+)/creators", path)
    campaign_creators_batch_match = re.fullmatch(
        r"/api/campaigns/([^/]+)/creators/batch", path
    )
    campaign_publications_refresh_match = re.fullmatch(
        r"/api/campaigns/([^/]+)/publications/refresh", path
    )
    campaign_performance_match = re.fullmatch(r"/api/campaigns/([^/]+)/performance", path)
    # GET /api/campaigns/{campaign_id}/creators → {"ok": true, "campaign_creators": [...]}
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
            _campaign_repository_error(handler, exc)
        return True

    campaign_match = re.fullmatch(r"/api/campaigns/([^/]+)", path)
    # GET /api/campaigns/{campaign_id} → {"ok": true, "campaign": {...}}
    if method == "GET" and campaign_match:
        try:
            handler._json({"ok": True, "campaign": repositories["campaign"]().getCampaign(campaign_match.group(1))})
        except (RuntimeError, ValueError) as exc:
            _campaign_repository_error(handler, exc)
        return True

    # POST /api/products → {"ok": true, "product": {...}}
    if method == "POST" and path == "/api/products":
        payload = request["get_payload"]()
        try:
            product = repositories["product"]().createProduct(payload)
            handler._json({"ok": True, "product": product}, status=201)
        except ValueError as exc:
            handler._repository_error(exc)
        return True

    # POST /api/campaigns → {"ok": true, "campaign": {...}}
    if method == "POST" and path == "/api/campaigns":
        payload = request["get_payload"]()
        try:
            campaign = repositories["campaign"]().createCampaign(payload)
            handler._json({"ok": True, "campaign": campaign}, status=201)
        except ValueError as exc:
            handler._repository_error(exc)
        return True

    # POST /api/campaigns/{campaign_id}/creators → {"ok": true, "campaign_creator": {...}}
    if method == "POST" and campaign_creators_match:
        payload = request["get_payload"]()
        campaign_id = campaign_creators_match.group(1)
        supplied_campaign_id = str(payload.get("campaign_id") or "").strip()
        if supplied_campaign_id and supplied_campaign_id != campaign_id:
            handler._error("请求路径与数据中的 Campaign ID 不一致。")
            return True
        try:
            record = (
                campaign_creator_service.create_campaign_creator(
                    {**payload, "campaign_id": campaign_id}
                )
                if campaign_creator_service is not None
                else repositories["campaign_creator"]().createCampaignCreator(
                    {**payload, "campaign_id": campaign_id}
                )
            )
            invalidate_dashboard()
            handler._json({"ok": True, "campaign_creator": record}, status=201)
        except ValueError as exc:
            handler._repository_error(exc)
        return True

    # POST /api/campaigns/{campaign_id}/creators/batch → per-Creator results.
    if method == "POST" and campaign_creators_batch_match:
        payload = request["get_payload"]()
        try:
            result = context["services"]["campaign_creator"].batch_add_creators(
                campaign_creators_batch_match.group(1), payload.get("creator_ids")
            )
            handler._json({"ok": True, **result})
        except ValueError as exc:
            handler._repository_error(exc)
        return True

    if method == "POST" and campaign_publications_refresh_match:
        payload = request["get_payload"]()
        try:
            result = context["services"]["publication_tracking"].refresh_campaign(
                campaign_publications_refresh_match.group(1),
                refresh_operation_id=payload.get("refresh_operation_id", ""),
            )
            handler._json({"ok": True, **result})
        except (RuntimeError, ValueError) as exc:
            _campaign_repository_error(handler, exc)
        return True

    if method == "GET" and campaign_performance_match:
        try:
            repositories["campaign"]().getCampaign(campaign_performance_match.group(1))
            result = context["services"]["analytics"].get_campaign_performance(
                campaign_performance_match.group(1)
            )
            handler._json({"ok": True, **result})
        except (RuntimeError, ValueError) as exc:
            _campaign_repository_error(handler, exc)
        return True

    # PATCH /api/products/{product_id} → {"ok": true, "product": {...}}
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

    # PATCH /api/campaigns/{campaign_id} → {"ok": true, "campaign": {...}}
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
            if (
                "archived_at" in payload
                or payload.get("archived") is True
                or "name" in payload
            ):
                invalidate_dashboard()
            handler._json({"ok": True, "campaign": campaign})
        except ValueError as exc:
            handler._repository_error(exc)
        return True

    campaign_creator_publications_match = re.fullmatch(
        r"/api/campaign-creators/([^/]+)/publications", path
    )
    campaign_creator_publication_match = re.fullmatch(
        r"/api/campaign-creators/([^/]+)/publications/([^/]+)", path
    )
    campaign_creator_publication_refresh_match = re.fullmatch(
        r"/api/campaign-creators/([^/]+)/publications/([^/]+)/refresh", path
    )
    campaign_creator_publication_latest_match = re.fullmatch(
        r"/api/campaign-creators/([^/]+)/publications/([^/]+)/performance/latest", path
    )
    campaign_creator_publication_history_match = re.fullmatch(
        r"/api/campaign-creators/([^/]+)/publications/([^/]+)/performance/history", path
    )
    campaign_creator_publication_performance_match = re.fullmatch(
        r"/api/campaign-creators/([^/]+)/publications/([^/]+)/performance", path
    )
    campaign_creator_match = re.fullmatch(r"/api/campaign-creators/([^/]+)", path)

    # Actual publications belong to an existing CampaignCreator relation.
    if method == "GET" and campaign_creator_publications_match:
        try:
            if campaign_creator_service is None:
                raise RuntimeError("实际发布内容服务未配置。")
            handler._json(
                {
                    "ok": True,
                    "publications": campaign_creator_service.list_publications(
                        campaign_creator_publications_match.group(1)
                    ),
                }
            )
        except (RuntimeError, ValueError) as exc:
            handler._repository_error(exc)
        return True

    if method == "POST" and campaign_creator_publications_match:
        payload = request["get_payload"]()
        try:
            if campaign_creator_service is None:
                raise RuntimeError("实际发布内容服务未配置。")
            record = campaign_creator_service.add_publication(
                campaign_creator_publications_match.group(1), payload
            )
            handler._json({"ok": True, "campaign_creator": record}, status=201)
        except (RuntimeError, ValueError) as exc:
            handler._repository_error(exc)
        return True

    if method == "POST" and campaign_creator_publication_refresh_match:
        payload = request["get_payload"]()
        try:
            result = context["services"]["publication_tracking"].refresh_publication(
                campaign_creator_publication_refresh_match.group(1),
                campaign_creator_publication_refresh_match.group(2),
                refresh_operation_id=payload.get("refresh_operation_id", ""),
            )
            handler._json({"ok": True, **result})
        except (RuntimeError, ValueError) as exc:
            handler._repository_error(exc)
        return True

    if method == "GET" and campaign_creator_publication_latest_match:
        try:
            observation = context["services"]["publication_tracking"].latest(
                campaign_creator_publication_latest_match.group(1),
                campaign_creator_publication_latest_match.group(2),
            )
            handler._json({"ok": True, "observation": observation})
        except (RuntimeError, ValueError) as exc:
            handler._repository_error(exc)
        return True

    if method == "GET" and campaign_creator_publication_history_match:
        try:
            observations = context["services"]["publication_tracking"].history(
                campaign_creator_publication_history_match.group(1),
                campaign_creator_publication_history_match.group(2),
            )
            handler._json({"ok": True, "observations": observations})
        except (RuntimeError, ValueError) as exc:
            handler._repository_error(exc)
        return True

    if method == "GET" and campaign_creator_publication_performance_match:
        try:
            result = context["services"]["analytics"].get_publication_performance(
                campaign_creator_publication_performance_match.group(1),
                campaign_creator_publication_performance_match.group(2),
            )
            handler._json({"ok": True, **result})
        except (RuntimeError, ValueError) as exc:
            handler._repository_error(exc)
        return True

    if method == "DELETE" and campaign_creator_publication_match:
        try:
            if campaign_creator_service is None:
                raise RuntimeError("实际发布内容服务未配置。")
            result = campaign_creator_service.delete_publication(
                campaign_creator_publication_match.group(1),
                campaign_creator_publication_match.group(2),
            )
            handler._ok(**result)
        except (RuntimeError, ValueError) as exc:
            handler._repository_error(exc)
        return True

    # PATCH /api/campaign-creators/{id} → {"ok": true, "campaign_creator": {...}}
    if method == "PATCH" and campaign_creator_match:
        payload = request["get_payload"]()
        try:
            repository = repositories["campaign_creator"]()
            record = (
                repository.archiveCampaignCreator(campaign_creator_match.group(1))
                if payload.get("archived") is True
                else (
                    campaign_creator_service.update_campaign_creator(
                        campaign_creator_match.group(1), payload
                    )
                    if campaign_creator_service is not None and "publications" in payload
                    else repository.updateCampaignCreator(campaign_creator_match.group(1), payload)
                )
            )
            if payload.get("archived") is True or set(payload).intersection(
                {
                    "stage",
                    "cost",
                    "cost_currency",
                    "views",
                    "roi",
                    "performance_note",
                    "campaign_id",
                    "creator_id",
                    "account_id",
                    "publish_date",
                }
            ):
                invalidate_dashboard()
            handler._json({"ok": True, "campaign_creator": record})
        except ValueError as exc:
            handler._repository_error(exc)
        return True

    # DELETE /api/campaign-creators/{id} → {"ok": true, "campaign_creator_id": "...", "campaign_id": "...", "creator_id": "...", "deleted": true}
    if method == "DELETE" and campaign_creator_match:
        try:
            result = repositories["campaign_creator"]().remove_creator_from_campaign(
                campaign_creator_match.group(1)
            )
            invalidate_dashboard()
            handler._ok(**result)
        except ValueError as exc:
            handler._repository_error(exc)
        return True

    # DELETE /api/campaigns/{campaign_id} → {"ok": true, "campaign_id": "...", "deleted": true, "removed_campaign_creators": 0}
    if method == "DELETE" and campaign_match:
        try:
            result = repositories["campaign"]().delete_campaign(campaign_match.group(1))
            invalidate_dashboard()
            handler._ok(**result)
        except ValueError as exc:
            handler._repository_error(exc)
        return True

    return False
