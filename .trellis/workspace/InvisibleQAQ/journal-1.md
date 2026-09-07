# Journal - InvisibleQAQ (Part 1)

> AI development session journal
> Started: 2026-08-23

---

## Session 1: Adopt Codex lifecycle hooks

**Date**: 2026-08-23
**Task**: Adopt Codex lifecycle hooks
**Branch**: `main`

### Summary

Added PermissionRequest, Stop, and SessionEnd ServerChan lifecycle notifications; documented legacy notify removal and verified tests and plugin validation.

### Main Changes

- Added `SessionEnd` alongside `PermissionRequest` and `Stop` in the plugin lifecycle hooks.
- Added a distinct session-end notification with a 3-second hook budget and 2-second HTTP timeout.
- Updated plugin metadata, domain terminology, and user documentation to reject legacy `notify` callbacks.
- Added lifecycle event and timeout contract tests.

### Git Commits

| Hash | Message |
|------|---------|
| `fa3a84c` | `feat(hooks): use Codex lifecycle notifications` |

### Testing

- [OK] `python scripts\test_serverchan_notifier.py -v` (9 tests)
- [OK] `python -m py_compile scripts\serverchan_notifier.py scripts\test_serverchan_notifier.py`
- [OK] Plugin structure validation

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 2: 修复 Codex 插件失效：hook 信任失配与 session-end 预算

**Date**: 2026-09-07
**Task**: 修复 Codex 插件失效：hook 信任失配与 session-end 预算
**Branch**: `main`

### Summary

d8fa453 同时改了 Codex hook 文件名（hooks/hooks.json -> codex-hooks.json）和命令（新增 --agent codex），令 config.toml 中三条 [hooks.state] 信任记录全部失配；Codex 对未信任 hook 静默跳过，通知消失。用一次性探针插件 + app-server hooks/list RPC 双向验证：未信任 hook 不执行，写入 trusted_hash 后同一条立即执行。已为用户写入三条信任记录并实测送达。同批探针证伪了 CLAUDE.md 里的 [UNKNOWN]：Codex 确实读取 plugin.json#hooks 路径，无需退回默认路径或复制脚本。顺带修复 SESSION_END_REQUEST_TIMEOUT=2.0 低于端点延迟导致每条会话结束通知必然超时的问题（ServerChan 实测拒绝 2.5s / 真实发送 3.5s，Codex 把 SessionEnd hook 硬钳 3s，故仍是尽力而为）。

### Main Changes

- `scripts/serverchan_notifier.py`：`SESSION_END_REQUEST_TIMEOUT` 2.0 -> 2.8，注释记录实测延迟来源。
- `scripts/test_serverchan_notifier.py`：新增回归断言，请求预算不得远低于 hook 预算。
- `CLAUDE.md`：`Known unverified behaviour` 段替换为 `Verified Codex hook behaviour`；新增 hook 信任失配不变量。
- `CONTEXT.md`：新增术语 **Hook trust** 及两条不变量。
- `README.md`：`已知未验证项` 替换为 `Hook 加载与信任`；排障清单点明未信任 hook 被静默跳过。

### Git Commits

| Hash | Message |
|------|---------|
| `5bd95af` | fix(hooks): resolve Codex hook trust and the session-end request budget |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
