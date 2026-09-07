# ServerChan Notifier

本仓库既是插件 marketplace，也是两个插件共用的插件根。**两个插件相互隔离**，各有自己的清单和 hook
文件，共用同一份实现和同一份配置：

| 插件 | 服务对象 | Hook 文件 | 事件 |
| --- | --- | --- | --- |
| `serverchan-notifier` | Codex | `codex-hooks.json` | `Stop`、`PermissionRequest`、`SessionEnd` |
| `serverchan-notifier-claude` | Claude Code | `claude-hooks.json` | `Stop`、`StopFailure`、`PermissionRequest`、`Notification`、`SessionEnd` |

通知标题为 `项目目录 | <agent> 当前操作`，最长 32 字符。两个插件都读取
`%USERPROFILE%\.codex\serverchan-notifier.env` 里的同一个 SendKey。

## 从零安装（Windows）

### 1. 准备依赖

- Codex 侧：`codex plugin --help` 能正常输出帮助。
- Claude Code 侧：`/plugin` 可用。
- 已安装 Python 3，且 `python --version` 能正常输出版本。两个插件的 Windows Hook 命令名都是
  `python`（本机 `python3` 指向 Microsoft Store 占位程序，不可用）。
- 已从 ServerChan 取得 SendKey。

```powershell
codex plugin --help
python --version
```

### 2. 清理旧版安装（仅从 0.2.x 升级时需要）

0.3.0 改成了 marketplace 形态，旧的"个人 marketplace 里写死 `{"source":"url"}`"的装法已经作废。

```powershell
codex plugin remove serverchan-notifier@personal
```

然后编辑 `%USERPROFILE%\.agents\plugins\marketplace.json`，删除其中指向本仓库的
`serverchan-notifier` 条目（其他插件条目保留）。如果该文件只有这一个插件，可以整个删掉。

### 3. 安装 Codex 插件

仓库自带 `.agents/plugins/marketplace.json`，直接把仓库注册成 marketplace：

```powershell
codex plugin marketplace add https://github.com/InvisibleQAQ/serverchan_notifier.git
codex plugin add serverchan-notifier@serverchan
codex plugin list
```

`codex plugin list` 中应出现 `serverchan-notifier@serverchan`，状态为 `installed, enabled`。

> 不要给 `marketplace add` 加 `--sparse`。插件根就是仓库根，稀疏检出会让 Hook 找不到 `scripts/`。

### 4. 安装 Claude Code 插件

在 Claude Code 会话中执行：

```
/plugin marketplace add InvisibleQAQ/serverchan_notifier
/plugin install serverchan-notifier-claude@serverchan
```

命令行等价形式，可用来确认 hook 是否真的被加载：

```powershell
claude plugin details serverchan-notifier-claude@serverchan
```

输出的 `Component inventory` 里应显示
`Hooks (5)  PermissionRequest, Stop, StopFailure, Notification, SessionEnd`。

### 5. 配置 SendKey

创建固定的用户配置文件 `%USERPROFILE%\.codex\serverchan-notifier.env`，填入 ServerChan SendKey：

```dotenv
SERVERCHAN_SENDKEY=YOUR_SERVERCHAN_SENDKEY
```

两个插件都只读取此文件，不读取当前工作目录、插件安装目录或其他环境变量。路径在 `.codex` 目录下只是
历史原因，不代表它只服务 Codex。配置位于版本化插件缓存之外，因此升级或重装插件不会删除它。该文件含
密钥，禁止提交到 Git。

Codex 插件只使用 `codex-hooks.json` 中的 lifecycle hooks，不使用旧版 `config.toml` `notify` 回调。
若用户配置仍有指向本通知器的 `notify`，应删除该项，避免重复发送。

### 6. 信任 Hook

Codex：安装后关闭当前会话，启动新会话并运行 `/hooks`，审核并信任插件的三个 Hook。插件 Hook 属于
非托管 Hook，安装或启用插件不会自动授予信任，**未信任等同于没装**——Codex 会静默跳过。Codex 按
`<插件 ID>:<Hook 文件相对路径>:<事件>:<i>:<j>` 记录每条 Hook 的定义哈希；升级后只要 Hook 文件名或
命令有任何改动，旧记录即失配，必须重新审核。

Claude Code：安装插件时按提示确认插件 Hook，之后可用 `/hooks` 复核已生效的配置。

### 7. 验证通知

在新会话中发送一条普通消息，回复结束后应收到 `输出完成` 通知。触发需要确认的工具操作时应收到
`等待确认` 通知；退出主会话时应收到 `会话结束` 通知。

若没有收到通知，先检查：

- 插件是否为 `installed, enabled`。
- `%USERPROFILE%\.codex\serverchan-notifier.env` 是否只定义了一次 `SERVERCHAN_SENDKEY`。
- `/hooks` 中的 Hook 是否已信任。**这是升级后通知消失的首要原因**：未信任的 Hook 被静默跳过，
  插件仍显示 `installed, enabled`，日志里也不会留下任何痕迹。
- 插件数据目录中的 `serverchan-notifier.log`；无法取得插件数据目录时，日志位于
  `%USERPROFILE%\.codex\serverchan-notifier.log`。

## 行为

### 标题示例

| 事件 | Codex | Claude Code |
| --- | --- | --- |
| `Stop` | `.codex \| Codex 输出完成` | `.codex \| Claude 输出完成` |
| `PermissionRequest` | `.codex \| Codex 等待确认:命令` | `.codex \| Claude 等待确认:命令` |
| `SessionEnd` | `.codex \| Codex 会话结束` | `.codex \| Claude 会话结束` |
| `StopFailure` | 不支持 | `.codex \| Claude 运行失败:触发限流` |
| `Notification` | 不支持 | `.codex \| Claude 等待输入` |

`StopFailure` 的失败原因来自 Claude Code 的有界枚举，映射为 `鉴权失败`、`组织限制`、`账号冻结`、
`计费错误`、`触发限流`、`服务过载`、`请求无效`、`模型缺失`、`服务端错误`、`输出超长`、`未知错误`。

### 共同约定

- `SessionEnd` 表示会话关闭，不表示单轮输出完成。
- 标题超过 32 字符时优先截断操作细节，保留项目名 —— 项目名才是推送列表里的有效标识。
- 请求采用 GET，`title` 与 `desp` 使用 URL 编码。
- 除 `SessionEnd` 外的事件异步执行；`SessionEnd` 同步执行，Hook 超时 3 秒，网络请求超时 2.8 秒。
  3 秒不是可调参数：Codex 会把 `SessionEnd` 的 Hook 超时硬钳到 3 秒（超过时打印 `clamping SessionEnd
  hook timeout to 3s`）。ServerChan 实测往返：错误 Key 被拒约 2.5 秒，真实发送约 3.5 秒；解释器启动
  约 0.1 秒。因此请求超时必须吃满剩余预算——早期的 2 秒低于任何一种延迟，会让每一条会话结束通知都
  静默超时。即便吃满，**Codex 下的会话结束通知仍是尽力而为**：真实发送耗时本就超过 3 秒的天花板。
  `Stop` 与 `PermissionRequest` 不受影响，它们异步执行且有 15 秒预算。
- 网络错误只写日志，不改变 agent 的审批、续跑或结束决策。脚本始终先输出 `{}` 并以 0 退出。
- 为减少第三方数据暴露，通知不发送命令正文、工具参数或 AI 回复正文。`StopFailure` 只发送错误枚举，
  不发送 `error_details` 与 `last_assistant_message`。
- Hook 命令通过 `--agent codex|claude` 显式声明来源，不嗅探环境变量（Codex 也会替换
  `CLAUDE_PLUGIN_ROOT`，嗅探不可靠）。

### Claude Code 专有行为

- `Notification` 只匹配 `^idle_prompt$`。Claude Code 的空闲阈值默认 60 秒
  （`messageIdleNotifThresholdMs`），且弹窗在屏或回合运行中不触发。因此**同一个等待状态会先收到
  `输出完成`、60 秒后再收到 `等待输入`**。这是刻意保留的第二次提醒，不是 bug。
- `SessionEnd` 只匹配 `^(logout|prompt_input_exit|other)$`。`/clear` 和 resume 不是会话结束，
  不发通知。
- Claude Code 不支持 `commandWindows`，Windows 下用 PowerShell 执行 `command`；
  `${CLAUDE_PLUGIN_ROOT}` 由 Claude Code 自己替换成绝对路径，不依赖 shell 展开。

## Hook 加载与信任

两项行为已在 codex-cli 0.153.4 上实测确认。

**Codex 读取 `plugin.json` 的 `hooks` 路径。** 一个只有 `"hooks": "./alt-hooks.json"`、没有
`hooks/hooks.json` 的探针插件，其 Hook 被正常加载，`sourcePath` 就是清单指定的那个文件。所以
`codex-hooks.json` 这个命名是有效的，不需要退回默认路径。

**未信任的 Hook 会被 Codex 静默跳过。** 不报错、不提示、不写日志——表现就是通知凭空消失。信任记录
存在 `%USERPROFILE%\.codex\config.toml` 的 `[hooks.state]` 下，键是
`<插件 ID>:<Hook 文件相对路径>:<事件>:<i>:<j>`，值是该 Hook 定义的 sha256。**Hook 文件改名或命令改动
都会让旧记录失配**，等同于回到未信任状态，必须重新审核（第 6 步）。0.3.0 同时改了文件名
（`hooks/hooks.json` → `codex-hooks.json`）和命令（新增 `--agent codex`），因此从 0.2.x 升级后
三条 Hook 全部需要重新信任。

## 开发验证

```powershell
python scripts/test_serverchan_notifier.py -v
```

测试覆盖两个插件的事件集、`--agent` 传参、标题预算、marketplace 清单指向、`hooks/hooks.json` 不存在，
以及两条 Hook 命令的真实 PowerShell 启动。
