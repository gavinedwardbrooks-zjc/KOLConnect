from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "app" / "server.py"


class M89RuntimeStorageBootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = ast.parse(SERVER.read_text(encoding="utf-8-sig"))

    def _function(self, name: str) -> ast.FunctionDef:
        return next(
            node
            for node in self.module.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        )

    def test_server_bootstraps_storage_before_accepting_requests(self) -> None:
        function = self._function("run")
        bootstrap_index = next(
            index
            for index, statement in enumerate(function.body)
            if isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
            and statement.value.func.id == "_new_repository_factory"
        )
        server_index = next(
            index
            for index, statement in enumerate(function.body)
            if isinstance(statement, ast.Assign)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
            and statement.value.func.id == "KOLConnectHTTPServer"
        )
        call = function.body[bootstrap_index].value

        self.assertLess(bootstrap_index, server_index)
        self.assertTrue(
            any(
                keyword.arg == "bootstrap_new_install"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in call.keywords
            )
        )

    def test_request_factory_defaults_to_non_bootstrap_resolution(self) -> None:
        function = self._function("_new_repository_factory")
        bootstrap_default = next(
            default
            for argument, default in zip(function.args.kwonlyargs, function.args.kw_defaults)
            if argument.arg == "bootstrap_new_install"
        )
        factory_call = next(
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "for_runtime"
        )

        self.assertIsInstance(bootstrap_default, ast.Constant)
        self.assertIs(bootstrap_default.value, False)
        self.assertTrue(any(keyword.arg == "storage_paths" for keyword in factory_call.keywords))
        self.assertTrue(
            any(
                keyword.arg == "bootstrap_new_install"
                and isinstance(keyword.value, ast.Name)
                and keyword.value.id == "bootstrap_new_install"
                for keyword in factory_call.keywords
            )
        )


if __name__ == "__main__":
    unittest.main()
