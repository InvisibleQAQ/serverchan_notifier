#!/usr/bin/env python3
"""Send privacy-minimal Codex and Claude Code lifecycle notifications through ServerChan."""

from __future__ import annotations

import argparse
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
PROJECT_FLOOR = 8
DESP_BYTE_LIMIT = 32 * 1024
SENDKEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
ENV_KEY = "SERVERCHAN_SENDKEY"
DEFAULT_ENV_PATH = Path.home() / ".codex" / "serverchan-notifier.env"
SERVERCHAN_ENDPOINT = "https://sctapi.ftqq.com/{sendkey}.send"
DEFAULT_REQUEST_TIMEOUT = 10.0
# Codex clamps SessionEnd hooks to 3s, so the whole run — interpreter start (~0.1s) plus the
# request — has to fit there; the request therefore gets the rest of that budget. Measured
# ServerChan latency is ~2.5s for a rejected key and ~3.5s for a real send, so session-end
# delivery stays best-effort under Codex. Stop and PermissionRequest are async with 15s.
SESSION_END_REQUEST_TIMEOUT = 2.8

# Each agent exposes a different lifecycle surface. Codex has no turn-failure event.
AGENT_LABELS = {"codex": ("Codex", "Codex"), "claude": ("Claude", "Claude Code")}
AGENT_EVENTS = {
    "codex": ("PermissionRequest", "Stop", "SessionEnd"),
    "claude": ("PermissionRequest", "Stop", "StopFailure", "Notification", "SessionEnd"),
}
EVENT_ACTIONS = {
    "PermissionRequest": "等待确认",
    "Stop": "输出完成",
    "StopFailure": "运行失败",
    "Notification": "等待输入",
    "SessionEnd": "会话结束",
}
TOOL_LABELS = {
    "Bash": "命令",
    "PowerShell": "命令",
    "apply_patch": "文件修改",
    "Edit": "文件修改",
    "Write": "文件写入",
    "NotebookEdit": "笔记本修改",
    "Read": "文件读取",
    "Agent": "子代理",
    "Task": "子代理",
    "WebFetch": "网页抓取",
    "WebSearch": "联网搜索",
}
# StopFailure carries a bounded enum, so the reason is safe to send and short to label.
ERROR_LABELS = {
    "authentication_failed": "鉴权失败",
    "oauth_org_not_allowed": "组织限制",
    "account_on_hold": "账号冻结",
    "billing_error": "计费错误",
    "rate_limit": "触发限流",
    "overloaded": "服务过载",
    "invalid_request": "请求无效",
    "model_not_found": "模型缺失",
    "server_error": "服务端错误",
    "max_output_tokens": "输出超长",
    "unknown": "未知错误",
}
IDLE_NOTIFICATION_TYPE = "idle_prompt"


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
    return TOOL_LABELS.get(tool_name, tool_name.rsplit("__", 1)[-1])


def error_label(error: object) -> str:
    if not isinstance(error, str) or not error:
        return ERROR_LABELS["unknown"]
    return ERROR_LABELS.get(error, error)


def ellipsize(value: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def fit_title(project: str, action: str) -> str:
    """Keep the project identifiable first; long action detail yields room, not the project."""
    separator = " | "
    budget = TITLE_LIMIT - len(separator)
    project = ellipsize(project, max(budget - len(action), min(len(project), PROJECT_FLOOR)))
    return f"{project}{separator}{ellipsize(action, budget - len(project))}"


def markdown_value(value: str) -> str:
    return value.replace("`", "&#96;").replace("\r", " ").replace("\n", " ")


def truncate_utf8(value: str, byte_limit: int) -> str:
    raw = value.encode("utf-8")
    if len(raw) <= byte_limit:
        return value
    return raw[:byte_limit].decode("utf-8", errors="ignore")


def event_detail(event: str, payload: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
    """Return the action suffix and the event-specific desp rows."""
    if event == "PermissionRequest":
        tool = tool_label(payload.get("tool_name"))
        return tool, [("操作类型", tool)]
    if event == "StopFailure":
        reason = error_label(payload.get("error"))
        return reason, [("失败原因", reason)]
    if event == "Notification":
        kind = payload.get("notification_type")
        if kind != IDLE_NOTIFICATION_TYPE:
            raise NotificationError(f"Unsupported notification type: {kind!r}")
    return "", []


def build_notification(agent: str, payload: dict[str, Any]) -> tuple[str, str]:
    if agent not in AGENT_EVENTS:
        raise NotificationError(f"Unsupported agent: {agent!r}")
    event = payload.get("hook_event_name")
    if event not in AGENT_EVENTS[agent]:
        raise NotificationError(f"Unsupported {agent} hook event: {event!r}")

    cwd_value = payload.get("cwd")
    cwd = cwd_value if isinstance(cwd_value, str) and cwd_value else os.getcwd()
    project = project_name(cwd)
    short_name, long_name = AGENT_LABELS[agent]
    suffix, extra_rows = event_detail(event, payload)

    action = EVENT_ACTIONS[event]
    if suffix:
        action = f"{action}:{suffix}"

    rows = [("项目", project), ("工作目录", cwd)]
    rows.extend(extra_rows)
    rows.append(("时间", datetime.now().astimezone().isoformat(timespec="seconds")))
    details = [f"## {long_name} {EVENT_ACTIONS[event]}", ""]
    details.extend(f"- {label}: `{markdown_value(value)}`" for label, value in rows)

    return (
        fit_title(project, f"{short_name} {action}"),
        truncate_utf8("\n".join(details), DESP_BYTE_LIMIT),
    )


def send_notification(
    sendkey: str,
    title: str,
    desp: str,
    *,
    timeout: float = DEFAULT_REQUEST_TIMEOUT,
    open_url: Callable[..., Any] = urlopen,
) -> None:
    query = urlencode({"title": title, "desp": desp})
    endpoint = SERVERCHAN_ENDPOINT.format(sendkey=quote(sendkey, safe=""))
    request = Request(
        f"{endpoint}?{query}",
        headers={"User-Agent": "serverchan-notifier/0.3"},
        method="GET",
    )

    try:
        with open_url(request, timeout=timeout) as response:
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


def parse_agent(argv: list[str]) -> str:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--agent", required=True, choices=sorted(AGENT_EVENTS))
    return parser.parse_args(argv).agent


def read_hook_payload() -> dict[str, Any]:
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise NotificationError("Hook input must be a JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    # Stop hooks require JSON output. An empty object leaves the agent's decisions unchanged.
    print("{}")
    try:
        agent = parse_agent(sys.argv[1:] if argv is None else argv)
        payload = read_hook_payload()
        title, desp = build_notification(agent, payload)
        timeout = (
            SESSION_END_REQUEST_TIMEOUT
            if payload.get("hook_event_name") == "SessionEnd"
            else DEFAULT_REQUEST_TIMEOUT
        )
        send_notification(load_sendkey(), title, desp, timeout=timeout)
    except (NotificationError, OSError, json.JSONDecodeError, SystemExit) as exc:
        log_error(exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
