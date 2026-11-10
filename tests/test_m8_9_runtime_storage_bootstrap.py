from __future__ import annotations

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import sys


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "app" / "server.py"
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import server  # noqa: E402


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
            if isinstance(statement, ast.Assign)
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

    def test_packaged_windows_legacy_authority_does_not_make_startup_fatal(self) -> None:
        """Legacy users may start the app, but Mail facts never receive Excel authority."""
        legacy_factory = SimpleNamespace(
            store=SimpleNamespace(is_sqlite_authority=False)
        )
        http_server = SimpleNamespace(
            serve_forever=mock.Mock(),
            shutdown=mock.Mock(),
            server_close=mock.Mock(),
        )
        chat_transport = SimpleNamespace(start=mock.Mock(), close=mock.Mock())
        recovery_thread = SimpleNamespace(start=mock.Mock())

        with (
            mock.patch.object(server.sys, "platform", "win32"),
            mock.patch.object(server.sys, "frozen", True, create=True),
            mock.patch.object(
                server, "_new_repository_factory", return_value=legacy_factory
            ) as create_factory,
            mock.patch.object(server, "get_mail_send_service") as mail_send,
            mock.patch.object(server, "KOLConnectHTTPServer", return_value=http_server),
            mock.patch.object(
                server, "get_feishu_chat_transport", return_value=chat_transport
            ),
            mock.patch.object(server.threading, "Thread", return_value=recovery_thread),
            mock.patch.object(server, "log_event") as log_event,
            mock.patch.dict(server.STATE, {"feishu": {"chat_enabled": False}}, clear=False),
        ):
            server.run()

        create_factory.assert_called_once_with(bootstrap_new_install=True)
        mail_send.assert_not_called()
        http_server.serve_forever.assert_called_once_with()
        http_server.server_close.assert_called_once_with()
        self.assertTrue(
            any(
                call.args
                and call.args[0] == "MailSend"
                and "SQLite authority" in call.args[1]
                for call in log_event.call_args_list
            )
        )

    def test_sqlite_authority_still_recovers_interrupted_mail_attempts(self) -> None:
        sqlite_factory = SimpleNamespace(
            store=SimpleNamespace(is_sqlite_authority=True)
        )
        mail_send = SimpleNamespace(
            recover_interrupted_attempts=mock.Mock(return_value=2)
        )
        with mock.patch.object(server, "get_mail_send_service", return_value=mail_send):
            recovered = server._recover_mail_send_state_on_startup(sqlite_factory)

        self.assertEqual(2, recovered)
        mail_send.recover_interrupted_attempts.assert_called_once_with()

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
