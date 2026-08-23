# ServerChan Notifier

Codex 插件：主线程本轮输出完成时发送 `Stop` 通知；Codex 请求工具授权时发送
`PermissionRequest` 通知；主会话结束时发送 `SessionEnd` 通知。通知标题为
`项目目录 | 当前操作`，最长 32 字符。

## 配置

创建固定的用户配置文件 `%USERPROFILE%\.codex\serverchan-notifier.env`，填入
ServerChan SendKey：

```dotenv
SERVERCHAN_SENDKEY=YOUR_SERVERCHAN_SENDKEY
```

插件只读取此文件，不读取当前工作目录、插件安装目录或其他环境变量。配置位于版本化插件
缓存之外，因此升级或重装插件不会删除它。该文件含密钥，禁止提交到 Git。

插件只使用 `hooks/hooks.json` 中的 lifecycle hooks，不使用旧版 `config.toml` `notify`
回调。若用户配置仍有指向本通知器的 `notify`，应删除该项，避免重复发送。

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

## 启用

从个人 marketplace 安装插件后，启动新会话并运行 `/hooks`，审核并信任插件的三个 Hook。
Codex 会记录 Hook 定义哈希；升级到 `0.2.1` 后 Hook 配置已变化，需要重新审核。

## 验证

```powershell
python scripts/test_serverchan_notifier.py -v
```
