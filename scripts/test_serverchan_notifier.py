from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlparse


SCRIPT_PATH = Path(__file__).with_name("serverchan_notifier.py")
SPEC = importlib.util.spec_from_file_location("serverchan_notifier", SCRIPT_PATH)
assert SPEC and SPEC.loader
notifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(notifier)


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, _limit):
        return b'{"code": 0, "message": "SUCCESS"}'


class ServerChanNotifierTests(unittest.TestCase):
    def test_default_env_path_is_outside_plugin_installation(self):
        self.assertEqual(
            notifier.DEFAULT_ENV_PATH,
            Path.home() / ".codex" / "serverchan-notifier.env",
        )

    def test_completion_title_contains_project_and_action(self):
        title, desp = notifier.build_notification(
            {"hook_event_name": "Stop", "cwd": r"C:\Users\18368\.codex"}
        )

        self.assertEqual(title, ".codex | 输出完成")
        self.assertIn("`.codex`", desp)
        self.assertLessEqual(len(title), 32)

    def test_approval_title_contains_project_and_operation(self):
        title, _desp = notifier.build_notification(
            {
                "hook_event_name": "PermissionRequest",
                "cwd": r"C:\work\sample",
                "tool_name": "Bash",
            }
        )

        self.assertEqual(title, "sample | 等待确认:命令")

    def test_long_project_name_preserves_action_and_title_limit(self):
        title, _desp = notifier.build_notification(
            {"hook_event_name": "Stop", "cwd": "C:\\work\\" + "x" * 80}
        )

        self.assertLessEqual(len(title), 32)
        self.assertTrue(title.endswith(" | 输出完成"))

    def test_load_sendkey_validates_env_file(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "serverchan-notifier.env"
            path.write_text(
                "# ServerChan credentials\nSERVERCHAN_SENDKEY='SCT1234567890'\n",
                encoding="utf-8",
            )
            self.assertEqual(notifier.load_sendkey(path), "SCT1234567890")

            path.write_text("SERVERCHAN_SENDKEY=bad/key\n", encoding="utf-8")
            with self.assertRaises(notifier.NotificationError):
                notifier.load_sendkey(path)

    def test_load_sendkey_rejects_missing_or_duplicate_values(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "serverchan-notifier.env"
            path.write_text("OTHER_VALUE=ignored\n", encoding="utf-8")
            with self.assertRaises(notifier.NotificationError):
                notifier.load_sendkey(path)

            path.write_text(
                "SERVERCHAN_SENDKEY=SCT1234567890\n"
                "SERVERCHAN_SENDKEY=SCT0987654321\n",
                encoding="utf-8",
            )
            with self.assertRaises(notifier.NotificationError):
                notifier.load_sendkey(path)

    def test_request_is_get_and_parameters_are_urlencoded(self):
        captured = {}

        def open_url(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse()

        notifier.send_notification(
            "SCT1234567890",
            ".codex | 输出完成",
            "目录含空格: C:\\my project",
            open_url=open_url,
        )

        request = captured["request"]
        parsed = urlparse(request.full_url)
        params = parse_qs(parsed.query)
        self.assertEqual(request.method, "GET")
        self.assertEqual(captured["timeout"], 10)
        self.assertEqual(params["title"], [".codex | 输出完成"])
        self.assertEqual(params["desp"], ["目录含空格: C:\\my project"])
        self.assertTrue(parsed.path.endswith("/SCT1234567890.send"))


if __name__ == "__main__":
    unittest.main()
