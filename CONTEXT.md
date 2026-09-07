# ServerChan Notifier

Defines the user-visible notification language and the configuration boundary that survives plugin upgrades.

## Language

**Notifying agent**:
The coding agent whose lifecycle produces a notification. Exactly two exist: Codex and Claude Code.
Each has its own manifest and its own hook file; they share one plugin root, one implementation, and
one configuration.

**Completion notification**:
A reminder emitted after the main thread of a **Notifying agent** finishes one response.
It is also the input-required signal: the turn ended, so the next move is the user's.

**Approval notification**:
A reminder emitted when a **Notifying agent** is waiting for the user to approve a tool operation.

**Failure notification**:
A reminder emitted when a turn ends because of an API error, carrying a bounded failure reason.
Claude Code only — Codex exposes no turn-failure event.

**Idle notification**:
A reminder emitted when Claude Code has been waiting for user input past its idle threshold.
Claude Code only.

**Session-end notification**:
A reminder emitted when the main session of a **Notifying agent** ends. It is not a turn-completion signal.

**Project name**:
The final directory component of the session working directory.

**Current operation**:
`<agent> 输出完成` for completion, `<agent> 等待确认:<operation type>` for approval,
`<agent> 运行失败:<failure reason>` for failure, `<agent> 等待输入` for idle,
or `<agent> 会话结束` for session end.

**Failure reason**:
A label for one member of Claude Code's closed turn-failure enum, such as `触发限流` or `鉴权失败`.
_Avoid_: raw error details, assistant output

**Notification configuration**:
The user-owned `~/.codex/serverchan-notifier.env` file containing the ServerChan SendKey.
_Avoid_: Plugin `.env`, cache configuration, per-agent configuration

## Relationships

- Every notification type identifies one **Notifying agent**, one **Project name**, and one **Current operation**.
- A **Failure notification** additionally identifies one **Failure reason**.
- Both **Notifying agent**s read the same **Notification configuration**.
- The two plugins share one implementation; only the hook file and the manifest differ per agent.
- Each agent materialises the plugin root as an isolated copy, so anything a hook needs must live
  inside that root. Nothing above it survives installation.

## Example dialogue

> **Dev:** "Does a plugin upgrade replace the **Notification configuration**?"
> **Maintainer:** "No. It belongs to the user and stays outside both plugin caches."

> **Dev:** "Claude Code sent a **Completion notification** and then an **Idle notification** for the same turn."
> **Maintainer:** "That is the agreed behaviour, not a defect. The idle reminder is a deliberate second nudge."

## Invariants

- Subagent completion is not project completion.
- Turn completion is not session end.
- Clearing or resuming a session is not session end; only a real exit or logout notifies.
- A notification reports state; it never decides an approval or continues a turn.
- Notification content identifies the project and operation without exporting task payloads.
- **Project name** outranks operation detail: when the title runs out of room, the operation detail is
  truncated first so the project stays identifiable.
- The **Idle notification** repeats the **Completion notification** for the same waiting state by design.
- Lifecycle hooks are the only notification trigger; legacy `notify` configuration is not used.
- The **Notifying agent** is declared explicitly by the hook command, never inferred from the environment.
- No `hooks/hooks.json` may exist anywhere. Claude Code auto-loads that path inside a plugin root
  regardless of what the manifest declares, so each plugin names its own hook file in its manifest.

## Flagged ambiguities

- `.env` previously meant a file inside the plugin installation; resolved as the user-owned **Notification configuration**.
- `permission_required` / `input_required` / `run_completed` / `run_failed` are not hook event names in
  either agent; they are resolved to **Approval**, **Completion**, **Completion**, and **Failure notification**.
- The **Notification configuration** lives under `~/.codex/` even for Claude Code. Kept deliberately so
  one file serves both agents; the path name is historical, not a scope.
