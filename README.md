# ServerChan Notifier

Codex 插件：主线程本轮输出完成时发送 `Stop` 通知；Codex 请求工具授权时发送
`PermissionRequest` 通知。通知标题为 `项目目录 | 当前操作`，最长 32 字符。

## 配置

创建固定的用户配置文件 `%USERPROFILE%\.codex\serverchan-notifier.env`，填入
ServerChan SendKey：

```dotenv
SERVERCHAN_SENDKEY=YOUR_SERVERCHAN_SENDKEY
```

插件只读取此文件，不读取当前工作目录、插件安装目录或其他环境变量。配置位于版本化插件
缓存之外，因此升级或重装插件不会删除它。该文件含密钥，禁止提交到 Git。

## 行为

- `Stop`：标题示例 `.codex | 输出完成`。
- `PermissionRequest`：标题示例 `.codex | 等待确认:命令`。
- 请求采用 GET，`title` 与 `desp` 使用 URL 编码。
- Hook 异步执行；网络错误不会阻断 Codex。
- 为减少第三方数据暴露，通知不发送命令正文、工具参数或 AI 回复正文。

错误写入插件数据目录下的 `serverchan-notifier.log`；无法取得插件数据目录时，回退到
`%USERPROFILE%\.codex\serverchan-notifier.log`。

## 启用

从个人 marketplace 安装插件后，启动新会话并运行 `/hooks`，审核并信任插件的两个 Hook。
Codex 会记录 Hook 定义哈希；脚本或 Hook 配置变化后需要重新审核。

## 验证

```powershell
python scripts/test_serverchan_notifier.py -v
```
