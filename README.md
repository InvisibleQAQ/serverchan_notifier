# ServerChan Notifier

Codex 插件：主线程本轮输出完成时发送 `Stop` 通知；Codex 请求工具授权时发送
`PermissionRequest` 通知；主会话结束时发送 `SessionEnd` 通知。通知标题为
`项目目录 | 当前操作`，最长 32 字符。

## 从零安装（Windows）

### 1. 准备依赖

需要满足以下条件：

- 已安装支持插件的 Codex CLI；`codex plugin --help` 能正常输出帮助。
- 已安装 Python 3，并且 `python --version` 能正常输出版本。Windows Hook 使用的命令名
  是 `python`。
- 已从 ServerChan 取得 SendKey。

```powershell
codex plugin --help
python --version
```

### 2. 注册个人 marketplace

Codex 会自动发现 `%USERPROFILE%\.agents\plugins\marketplace.json`，因此默认个人
marketplace 不需要运行 `codex plugin marketplace add`。

如果该文件不存在，创建它并写入：

```json
{
  "name": "personal",
  "interface": {
    "displayName": "Personal"
  },
  "plugins": [
    {
      "name": "serverchan-notifier",
      "source": {
        "source": "url",
        "url": "https://github.com/InvisibleQAQ/serverchan_notifier.git"
      },
      "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL"
      },
      "category": "Productivity"
    }
  ]
}
```

可以先用 PowerShell 创建父目录，再用文本编辑器创建该 JSON 文件：

```powershell
$marketplaceDirectory = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.agents\plugins'
New-Item -ItemType Directory -Force -Path $marketplaceDirectory
notepad (Join-Path $marketplaceDirectory 'marketplace.json')
```

如果 `marketplace.json` 已存在，不要覆盖它；只把上面 `plugins` 数组中的
`serverchan-notifier` 对象追加到现有 `plugins` 数组，并保留其他插件条目。

### 3. 安装插件

```powershell
codex plugin add serverchan-notifier@personal
codex plugin list
```

`codex plugin list` 中应出现 `serverchan-notifier@personal`，状态为
`installed, enabled`。

### 4. 配置 SendKey

创建固定的用户配置文件 `%USERPROFILE%\.codex\serverchan-notifier.env`，填入
ServerChan SendKey：

```dotenv
SERVERCHAN_SENDKEY=YOUR_SERVERCHAN_SENDKEY
```

插件只读取此文件，不读取当前工作目录、插件安装目录或其他环境变量。配置位于版本化插件
缓存之外，因此升级或重装插件不会删除它。该文件含密钥，禁止提交到 Git。

插件只使用 `hooks/hooks.json` 中的 lifecycle hooks，不使用旧版 `config.toml` `notify`
回调。若用户配置仍有指向本通知器的 `notify`，应删除该项，避免重复发送。

### 5. 信任 Hook

安装后关闭当前 Codex 会话，再启动一个新会话并运行 `/hooks`。审核并信任插件的
`Stop`、`PermissionRequest` 和 `SessionEnd` 三个 Hook。插件 Hook 属于非托管 Hook，
安装或启用插件不会自动授予信任。

Codex 会记录 Hook 定义哈希；升级到 Hook 配置发生变化的新版本后，需要在 `/hooks`
中重新审核。

### 6. 验证通知

在新会话中发送一条普通消息，回复结束后应收到 `输出完成` 通知。触发需要确认的工具
操作时应收到 `等待确认` 通知；关闭主会话时应收到 `会话结束` 通知。

若没有收到通知，先检查：

- `codex plugin list` 中插件是否为 `installed, enabled`。
- `%USERPROFILE%\.codex\serverchan-notifier.env` 是否只定义了一次
  `SERVERCHAN_SENDKEY`。
- `/hooks` 中三个 Hook 是否已信任。
- 插件数据目录中的 `serverchan-notifier.log`；无法取得插件数据目录时，日志位于
  `%USERPROFILE%\.codex\serverchan-notifier.log`。

## 行为

- `Stop`：标题示例 `.codex | 输出完成`。
- `PermissionRequest`：标题示例 `.codex | 等待确认:命令`。
- `SessionEnd`：标题示例 `.codex | 会话结束`。它表示会话关闭，不表示单轮输出完成。
- Windows Hook 使用 PowerShell 的 `$env:PLUGIN_ROOT` 定位插件缓存中的通知脚本，避免
  将 CMD 语法 `%PLUGIN_ROOT%` 当成字面目录。
- 请求采用 GET，`title` 与 `desp` 使用 URL 编码。
- `Stop` 与 `PermissionRequest` 异步执行；`SessionEnd` 按 Codex 契约同步执行，Hook
  超时为 3 秒，网络请求超时为 2 秒。
- 网络错误只写日志，不改变 Codex 的审批、续跑或结束决策。
- 为减少第三方数据暴露，通知不发送命令正文、工具参数或 AI 回复正文。

错误写入插件数据目录下的 `serverchan-notifier.log`；无法取得插件数据目录时，回退到
`%USERPROFILE%\.codex\serverchan-notifier.log`。

## 开发验证

```powershell
python scripts/test_serverchan_notifier.py -v
```
