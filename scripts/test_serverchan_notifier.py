from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlparse


SCRIPT_PATH = Path(__file__).with_name("serverchan_notifier.py")
REPO_ROOT = SCRIPT_PATH.parent.parent
# Both agents install the repository root as the plugin root, so one script serves both.
AGENTS = ("codex", "claude")
HOOKS_PATHS = {agent: REPO_ROOT / f"{agent}-hooks.json" for agent in AGENTS}
MANIFEST_PATHS = {
    "codex": REPO_ROOT / ".codex-plugin" / "plugin.json",
    "claude": REPO_ROOT / ".claude-plugin" / "plugin.json",
}
MARKETPLACE_PATHS = {
    "codex": REPO_ROOT / ".agents" / "plugins" / "marketplace.json",
    "claude": REPO_ROOT / ".claude-plugin" / "marketplace.json",
}
# The plugin root holds the implementation directly; nothing outside it is materialised.
SHARED_SCRIPT_SUFFIX = "scripts/serverchan_notifier.py"

SPEC = importlib.util.spec_from_file_location("serverchan_notifier", SCRIPT_PATH)
assert SPEC and SPEC.loader
notifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(notifier)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def hook_entries(agent: str):
    """Yield (event, matcher, handler) for every declared hook of one plugin."""
    config = load_json(HOOKS_PATHS[agent])
    for event, groups in config["hooks"].items():
        for group in groups:
            for handler in group["hooks"]:
                yield event, group.get("matcher"), handler


def commands_of(handler):
    """Every shell command a handler can run, POSIX form plus the optional Windows form."""
    commands = [handler["command"]]
    if "commandWindows" in handler:
        commands.append(handler["commandWindows"])
    return commands


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, _limit):
        return b'{"code": 0, "message": "SUCCESS"}'


class ConfigurationTests(unittest.TestCase):
    def test_default_env_path_is_outside_plugin_installation(self):
        self.assertEqual(
            notifier.DEFAULT_ENV_PATH,
            Path.home() / ".codex" / "serverchan-notifier.env",
        )

    def test_both_plugins_read_the_same_notification_configuration(self):
        # The shared implementation is the only place the SendKey path is defined.
        self.assertEqual(set(notifier.AGENT_EVENTS), {"codex", "claude"})
        self.assertEqual(set(notifier.AGENT_LABELS), set(notifier.AGENT_EVENTS))

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

    def test_agent_flag_is_required_and_validated(self):
        self.assertEqual(notifier.parse_agent(["--agent", "claude"]), "claude")
        with io.StringIO() as noise, contextlib.redirect_stderr(noise):
            for argv in ([], ["--agent", "cursor"]):
                with self.subTest(argv=argv), self.assertRaises(SystemExit):
                    notifier.parse_agent(argv)


class TitleTests(unittest.TestCase):
    def test_codex_titles_match_the_documented_operations(self):
        cases = {
            "Stop": ".codex | Codex 输出完成",
            "SessionEnd": ".codex | Codex 会话结束",
        }
        for event, expected in cases.items():
            with self.subTest(event=event):
                title, _desp = notifier.build_notification(
                    "codex", {"hook_event_name": event, "cwd": r"C:\Users\18368\.codex"}
                )
                self.assertEqual(title, expected)

    def test_claude_titles_cover_every_declared_event(self):
        cases = {
            "Stop": ("sample | Claude 输出完成", {}),
            "SessionEnd": ("sample | Claude 会话结束", {}),
            "PermissionRequest": ("sample | Claude 等待确认:命令", {"tool_name": "Bash"}),
            "StopFailure": ("sample | Claude 运行失败:触发限流", {"error": "rate_limit"}),
            "Notification": (
                "sample | Claude 等待输入",
                {"notification_type": "idle_prompt"},
            ),
        }
        self.assertEqual(set(cases), set(notifier.AGENT_EVENTS["claude"]))
        for event, (expected, extra) in cases.items():
            with self.subTest(event=event):
                title, _desp = notifier.build_notification(
                    "claude",
                    {"hook_event_name": event, "cwd": r"C:\work\sample", **extra},
                )
                self.assertEqual(title, expected)
                self.assertLessEqual(len(title), notifier.TITLE_LIMIT)

    def test_long_action_yields_room_instead_of_erasing_the_project(self):
        title, _desp = notifier.build_notification(
            "claude",
            {
                "hook_event_name": "PermissionRequest",
                "cwd": "C:\\work\\" + "p" * 40,
                "tool_name": "mcp__vendor__" + "t" * 40,
            },
        )

        project, _separator, action = title.partition(" | ")
        self.assertLessEqual(len(title), notifier.TITLE_LIMIT)
        self.assertGreaterEqual(len(project), notifier.PROJECT_FLOOR)
        self.assertTrue(action.startswith("Claude 等待确认:"))

    def test_long_project_name_keeps_the_full_action(self):
        title, _desp = notifier.build_notification(
            "codex", {"hook_event_name": "Stop", "cwd": "C:\\work\\" + "x" * 80}
        )

        self.assertLessEqual(len(title), notifier.TITLE_LIMIT)
        self.assertTrue(title.endswith(" | Codex 输出完成"))

    def test_desp_names_the_agent_and_omits_payload_bodies(self):
        _title, desp = notifier.build_notification(
            "claude",
            {
                "hook_event_name": "StopFailure",
                "cwd": r"C:\work\sample",
                "error": "overloaded",
                "error_details": "SECRET DETAIL",
                "last_assistant_message": "SECRET MESSAGE",
            },
        )

        self.assertIn("## Claude Code 运行失败", desp)
        self.assertIn("- 失败原因: `服务过载`", desp)
        self.assertNotIn("SECRET DETAIL", desp)
        self.assertNotIn("SECRET MESSAGE", desp)

    def test_unknown_error_enum_falls_back_without_crashing(self):
        self.assertEqual(notifier.error_label(None), "未知错误")
        self.assertEqual(notifier.error_label("brand_new_code"), "brand_new_code")
        self.assertEqual(notifier.error_label("billing_error"), "计费错误")


class EventSurfaceTests(unittest.TestCase):
    def test_codex_rejects_events_it_cannot_emit(self):
        for event in ("StopFailure", "Notification"):
            with self.subTest(event=event):
                with self.assertRaises(notifier.NotificationError):
                    notifier.build_notification(
                        "codex", {"hook_event_name": event, "cwd": r"C:\work\sample"}
                    )

    def test_unknown_agent_and_event_are_rejected(self):
        with self.assertRaises(notifier.NotificationError):
            notifier.build_notification("cursor", {"hook_event_name": "Stop"})
        with self.assertRaises(notifier.NotificationError):
            notifier.build_notification("claude", {"hook_event_name": "SubagentStop"})

    def test_only_idle_notifications_are_reported(self):
        for kind in ("permission_prompt", "auth_success", None):
            with self.subTest(kind=kind):
                with self.assertRaises(notifier.NotificationError):
                    notifier.build_notification(
                        "claude",
                        {"hook_event_name": "Notification", "notification_type": kind},
                    )


class HookContractTests(unittest.TestCase):
    def test_each_plugin_declares_exactly_its_supported_events(self):
        for agent, expected in notifier.AGENT_EVENTS.items():
            with self.subTest(agent=agent):
                config = load_json(HOOKS_PATHS[agent])
                self.assertEqual(set(config["hooks"]), set(expected))

    def test_every_hook_passes_its_own_agent_flag(self):
        for agent in AGENTS:
            for event, _matcher, handler in hook_entries(agent):
                with self.subTest(agent=agent, event=event):
                    for command in commands_of(handler):
                        self.assertIn(f"--agent {agent}", command)

    def test_both_hook_files_point_at_the_single_shared_implementation(self):
        self.assertTrue((REPO_ROOT / SHARED_SCRIPT_SUFFIX).is_file())
        for agent in AGENTS:
            for event, _matcher, handler in hook_entries(agent):
                with self.subTest(agent=agent, event=event):
                    for command in commands_of(handler):
                        # The script sits inside the plugin root: no parent traversal.
                        self.assertIn("serverchan_notifier.py", command)
                        self.assertNotIn("..", command)
                    self.assertIn(SHARED_SCRIPT_SUFFIX, handler["command"])

    def test_each_plugin_manifest_declares_its_own_hook_file(self):
        # Neither agent may rely on hooks/hooks.json, so the manifest must name the file.
        for agent in AGENTS:
            with self.subTest(agent=agent):
                manifest = load_json(MANIFEST_PATHS[agent])
                self.assertEqual(manifest["hooks"], f"./{agent}-hooks.json")
                self.assertTrue((REPO_ROOT / manifest["hooks"].lstrip("./")).is_file())

    def test_session_end_is_synchronous_and_bounded_for_both_plugins(self):
        for agent in AGENTS:
            with self.subTest(agent=agent):
                handler = load_json(HOOKS_PATHS[agent])["hooks"]["SessionEnd"][0]["hooks"][0]
                self.assertNotIn("async", handler)
                self.assertLessEqual(handler["timeout"], 3)
                self.assertLess(notifier.SESSION_END_REQUEST_TIMEOUT, handler["timeout"])

    def test_non_blocking_events_run_async(self):
        for agent in AGENTS:
            for event, _matcher, handler in hook_entries(agent):
                if event == "SessionEnd":
                    continue
                with self.subTest(agent=agent, event=event):
                    self.assertTrue(handler["async"])

    def test_codex_hook_uses_powershell_plugin_root(self):
        commands = {
            handler["commandWindows"] for _event, _matcher, handler in hook_entries("codex")
        }

        self.assertEqual(len(commands), 1)
        command = commands.pop()
        self.assertNotIn("%PLUGIN_ROOT%", command)
        self.assertIn("$env:PLUGIN_ROOT", command)

    def test_claude_hook_uses_the_claude_placeholder_only(self):
        for event, _matcher, handler in hook_entries("claude"):
            with self.subTest(event=event):
                # Claude Code has no commandWindows key and substitutes the placeholder itself.
                self.assertNotIn("commandWindows", handler)
                self.assertIn("${CLAUDE_PLUGIN_ROOT}", handler["command"])
                self.assertNotIn("${PLUGIN_ROOT}", handler["command"])
                self.assertNotIn("$env:", handler["command"])

    def test_claude_matchers_filter_idle_and_real_session_ends(self):
        matchers = {
            event: matcher for event, matcher, _handler in hook_entries("claude")
        }

        self.assertEqual(matchers["Notification"], "^idle_prompt$")
        # /clear and resume are not session ends, so they must not notify.
        self.assertEqual(matchers["SessionEnd"], "^(logout|prompt_input_exit|other)$")
        for reason in ("clear", "resume"):
            self.assertNotIn(reason, matchers["SessionEnd"])

    @unittest.skipUnless(os.name == "nt", "Windows shell regression test")
    def test_hook_commands_run_from_powershell(self):
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        self.assertIsNotNone(powershell)

        for agent in AGENTS:
            handler = load_json(HOOKS_PATHS[agent])["hooks"]["Stop"][0]["hooks"][0]
            with self.subTest(agent=agent), TemporaryDirectory() as temp_dir:
                plugin_root = Path(temp_dir) / "plugin root"
                (plugin_root / "scripts").mkdir(parents=True)
                marker = plugin_root / "hook-ran.txt"
                (plugin_root / "scripts" / "serverchan_notifier.py").write_text(
                    "import os, sys\n"
                    "from pathlib import Path\n"
                    "assert sys.argv[1:] == ['--agent', os.environ['HOOK_TEST_AGENT']], sys.argv\n"
                    "Path(os.environ['HOOK_TEST_MARKER']).write_text("
                    "'hook-ran', encoding='utf-8')\n",
                    encoding="utf-8",
                )
                env = os.environ.copy()
                env["PLUGIN_ROOT"] = str(plugin_root)
                env["HOOK_TEST_MARKER"] = str(marker)
                env["HOOK_TEST_AGENT"] = agent
                # Claude Code substitutes its placeholders before the shell sees the command.
                command = handler.get("commandWindows") or handler["command"].replace(
                    "${CLAUDE_PLUGIN_ROOT}", str(plugin_root)
                )

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


class MarketplaceTests(unittest.TestCase):
    def test_codex_marketplace_installs_the_repository_root(self):
        manifest = load_json(MARKETPLACE_PATHS["codex"])
        entries = manifest["plugins"]

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["source"], {"source": "local", "path": "./"})
        self.assertEqual(entries[0]["name"], load_json(MANIFEST_PATHS["codex"])["name"])

    def test_claude_marketplace_installs_the_repository_root(self):
        manifest = load_json(MARKETPLACE_PATHS["claude"])
        entries = manifest["plugins"]

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["source"], "./")
        self.assertEqual(entries[0]["name"], load_json(MANIFEST_PATHS["claude"])["name"])

    def test_plugin_names_stay_distinct_across_the_two_manifests(self):
        names = {agent: load_json(path)["name"] for agent, path in MANIFEST_PATHS.items()}
        self.assertEqual(len(set(names.values())), 2, names)

    def test_no_default_hook_file_exists_anywhere(self):
        # Claude Code auto-loads hooks/hooks.json inside a plugin root regardless of the
        # manifest. Both plugin roots are the repository root, so such a file would fire
        # one agent's hooks under the other.
        self.assertFalse((REPO_ROOT / "hooks" / "hooks.json").exists())
        self.assertEqual(list(REPO_ROOT.glob("**/hooks/hooks.json")), [])


class TransportTests(unittest.TestCase):
    def test_request_is_get_and_parameters_are_urlencoded(self):
        captured = {}

        def open_url(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse()

        notifier.send_notification(
            "SCT1234567890",
            ".codex | Codex 输出完成",
            "目录含空格: C:\\my project",
            open_url=open_url,
        )

        request = captured["request"]
        parsed = urlparse(request.full_url)
        params = parse_qs(parsed.query)
        self.assertEqual(request.method, "GET")
        self.assertEqual(captured["timeout"], 10)
        self.assertEqual(params["title"], [".codex | Codex 输出完成"])
        self.assertEqual(params["desp"], ["目录含空格: C:\\my project"])
        self.assertTrue(parsed.path.endswith("/SCT1234567890.send"))


if __name__ == "__main__":
    unittest.main()
