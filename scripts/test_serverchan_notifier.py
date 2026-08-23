from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlparse


SCRIPT_PATH = Path(__file__).with_name("serverchan_notifier.py")
HOOKS_PATH = SCRIPT_PATH.parent.parent / "hooks" / "hooks.json"
SPEC = importlib.util.spec_from_file_location("serverchan_notifier", SCRIPT_PATH)
assert SPEC and SPEC.loader
notifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(notifier)


def load_hook_config():
    return json.loads(HOOKS_PATH.read_text(encoding="utf-8"))


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

    def test_session_end_title_is_distinct_from_turn_completion(self):
        title, desp = notifier.build_notification(
            {"hook_event_name": "SessionEnd", "cwd": r"C:\Users\18368\.codex"}
        )

        self.assertEqual(title, ".codex | 会话结束")
        self.assertIn("## Codex 会话结束", desp)

    def test_plugin_declares_only_supported_notification_lifecycle_hooks(self):
        config = load_hook_config()

        self.assertEqual(
            set(config["hooks"]),
            {"PermissionRequest", "Stop", "SessionEnd"},
        )
        session_end_handler = config["hooks"]["SessionEnd"][0]["hooks"][0]
        self.assertNotIn("async", session_end_handler)
        self.assertLessEqual(session_end_handler["timeout"], 3)
        self.assertLess(
            notifier.SESSION_END_REQUEST_TIMEOUT,
            session_end_handler["timeout"],
        )

    def test_windows_hook_command_uses_powershell_plugin_root(self):
        config = load_hook_config()
        commands = {
            group["hooks"][0]["commandWindows"]
            for groups in config["hooks"].values()
            for group in groups
        }

        self.assertEqual(len(commands), 1)
        command = commands.pop()
        self.assertNotIn("%PLUGIN_ROOT%", command)
        self.assertIn("$env:PLUGIN_ROOT", command)

    @unittest.skipUnless(os.name == "nt", "Windows shell regression test")
    def test_windows_hook_command_runs_from_powershell(self):
        config = load_hook_config()
        command = config["hooks"]["Stop"][0]["hooks"][0]["commandWindows"]
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        self.assertIsNotNone(powershell)

        with TemporaryDirectory() as temp_dir:
            plugin_root = Path(temp_dir) / "plugin root"
            script_dir = plugin_root / "scripts"
            script_dir.mkdir(parents=True)
            marker = plugin_root / "hook-ran.txt"
            (script_dir / "serverchan_notifier.py").write_text(
                "import os\n"
                "from pathlib import Path\n"
                "Path(os.environ['HOOK_TEST_MARKER']).write_text("
                "'hook-ran', encoding='utf-8')\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["PLUGIN_ROOT"] = str(plugin_root)
            env["HOOK_TEST_MARKER"] = str(marker)

            result = subprocess.run(
                [str(powershell), "-NoProfile", "-Command", command],
                input="{}",
                text=True,
                capture_output=True,
                cwd=plugin_root,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(
                marker.is_file(),
                f"stdout={result.stdout!r} stderr={result.stderr!r}",
            )
            self.assertEqual(marker.read_text(encoding="utf-8"), "hook-ran")

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
