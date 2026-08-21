"""Static contract tests for M2.6 S6 composition-provider reclassification."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "app" / "server.py"


class S6ProviderReclassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SERVER_PATH.read_text(encoding="utf-8-sig")
        cls.tree = ast.parse(cls.source)
        cls.functions = {
            node.name: node
            for node in cls.tree.body
            if isinstance(node, ast.FunctionDef)
        }

    def _function_source(self, name: str) -> str:
        node = self.functions[name]
        return ast.get_source_segment(self.source, node) or ""

    def test_dead_agency_port_forwarder_is_removed(self) -> None:
        self.assertNotIn("get_agency_port", self.functions)
        self.assertNotIn("get_agency_port", self.source)

    def test_repository_providers_resolve_the_active_request_factory(self) -> None:
        providers = {
            "get_creator_repository": "creator",
            "get_agency_repository": "agency",
            "get_product_repository": "product",
            "get_campaign_repository": "campaign",
            "get_campaign_creator_repository": "campaign_creator",
        }
        for provider, factory_method in providers.items():
            with self.subTest(provider=provider):
                source = self._function_source(provider)
                self.assertIn("get_active_repository_factory() or _new_repository_factory()", source)
                self.assertIn(f"factory.{factory_method}()", source)

    def test_service_providers_remain_explicit_composition_seams(self) -> None:
        expected = {
            "get_agency_service": "AgencyService(",
            "get_creator_service": "CreatorService(",
            "get_task_service": "TaskService(",
            "get_campaign_creator_service": "CampaignCreatorService(",
        }
        for provider, constructor in expected.items():
            with self.subTest(provider=provider):
                self.assertIn(constructor, self._function_source(provider))

        task_service = self._function_source("get_task_service")
        self.assertIn("get_task_port", task_service)
        self.assertIn("get_creator_port", task_service)


if __name__ == "__main__":
    unittest.main()
