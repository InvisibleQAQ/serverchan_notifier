#!/usr/bin/env python3
"""Send privacy-minimal Codex lifecycle notifications through ServerChan."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


TITLE_LIMIT = 32
DESP_BYTE_LIMIT = 32 * 1024
SENDKEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
ENV_KEY = "SERVERCHAN_SENDKEY"
DEFAULT_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
SERVERCHAN_ENDPOINT = "https://sctapi.ftqq.com/{sendkey}.send"


class NotificationError(RuntimeError):
    """Raised when notification input or delivery is invalid."""


def load_sendkey(path: Path | None = None) -> str:
    source = path or DEFAULT_ENV_PATH
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise NotificationError(f"Environment file not found: {source}") from exc
    except OSError as exc:
        raise NotificationError(f"Cannot read environment file: {source}") from exc

    values = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, raw_value = stripped.partition("=")
        if separator and key.strip() == ENV_KEY:
            value = raw_value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values.append(value)

    if len(values) != 1:
        raise NotificationError(f"Environment file must define {ENV_KEY} exactly once")
    sendkey = values[0]
    if not SENDKEY_PATTERN.fullmatch(sendkey):
        raise NotificationError(f"Environment variable {ENV_KEY} is invalid")
    return sendkey


def project_name(cwd: str) -> str:
    name = Path(cwd).name
    return name or cwd or "[UNKNOWN]"


def tool_label(tool_name: object) -> str:
    if not isinstance(tool_name, str) or not tool_name:
        return "操作"
    labels = {
        "Bash": "命令",
        "apply_patch": "文件修改",
        "Agent": "子代理",
    }
    return labels.get(tool_name, tool_name.rsplit("__", 1)[-1])


def fit_title(project: str, action: str) -> str:
    separator = " | "
    action = action[: TITLE_LIMIT - len(separator) - 1]
    available = TITLE_LIMIT - len(separator) - len(action)
    if len(project) > available:
        project = project[: max(available - 1, 0)] + "…"
    return f"{project}{separator}{action}"[:TITLE_LIMIT]


def markdown_value(value: str) -> str:
    return value.replace("`", "&#96;").replace("\r", " ").replace("\n", " ")


def truncate_utf8(value: str, byte_limit: int) -> str:
    raw = value.encode("utf-8")
    if len(raw) <= byte_limit:
        return value
    return raw[:byte_limit].decode("utf-8", errors="ignore")


def build_notification(payload: dict[str, Any]) -> tuple[str, str]:
    event = payload.get("hook_event_name")
    cwd_value = payload.get("cwd")
    cwd = cwd_value if isinstance(cwd_value, str) and cwd_value else os.getcwd()
    project = project_name(cwd)

    if event == "PermissionRequest":
        tool = tool_label(payload.get("tool_name"))
        action = f"等待确认:{tool}"
        details = [
            "## Codex 等待确认",
            "",
            f"- 项目: `{markdown_value(project)}`",
            f"- 工作目录: `{markdown_value(cwd)}`",
            f"- 操作类型: `{markdown_value(tool)}`",
        ]
    elif event == "Stop":
        action = "输出完成"
        details = [
            "## Codex 输出完成",
            "",
            f"- 项目: `{markdown_value(project)}`",
            f"- 工作目录: `{markdown_value(cwd)}`",
        ]
    else:
        raise NotificationError(f"Unsupported hook event: {event!r}")

    details.append(f"- 时间: `{datetime.now().astimezone().isoformat(timespec='seconds')}`")
    return fit_title(project, action), truncate_utf8("\n".join(details), DESP_BYTE_LIMIT)


def send_notification(
    sendkey: str,
    title: str,
    desp: str,
    *,
    open_url: Callable[..., Any] = urlopen,
) -> None:
    query = urlencode({"title": title, "desp": desp})
    endpoint = SERVERCHAN_ENDPOINT.format(sendkey=quote(sendkey, safe=""))
    request = Request(
        f"{endpoint}?{query}",
        headers={"User-Agent": "codex-serverchan-notifier/0.1"},
        method="GET",
    )

    try:
        with open_url(request, timeout=10) as response:
            status = getattr(response, "status", 200)
            body = response.read(64 * 1024)
    except OSError as exc:
        raise NotificationError("ServerChan request failed") from exc

    if not 200 <= status < 300:
        raise NotificationError(f"ServerChan returned HTTP {status}")

    try:
        result = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NotificationError("ServerChan returned an invalid JSON response") from exc

    if isinstance(result, dict) and result.get("code") not in (None, 0, "0"):
        raise NotificationError(f"ServerChan rejected the request (code={result.get('code')!r})")


def error_log_path() -> Path:
    plugin_data = os.environ.get("PLUGIN_DATA") or os.environ.get("CLAUDE_PLUGIN_DATA")
    if plugin_data:
        return Path(plugin_data) / "serverchan-notifier.log"
    return Path.home() / ".codex" / "serverchan-notifier.log"


def log_error(exc: BaseException) -> None:
    line = (
        f"{datetime.now().astimezone().isoformat(timespec='seconds')} "
        f"{type(exc).__name__}: {exc}\n"
    )
    try:
        path = error_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError:
        pass


def read_hook_payload() -> dict[str, Any]:
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise NotificationError("Hook input must be a JSON object")
    return payload


def main() -> int:
    # Stop hooks require JSON output. An empty object leaves Codex behavior unchanged.
    print("{}")
    try:
        payload = read_hook_payload()
        title, desp = build_notification(payload)
        send_notification(load_sendkey(), title, desp)
    except (NotificationError, OSError, json.JSONDecodeError) as exc:
        log_error(exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
