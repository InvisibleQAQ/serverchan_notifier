# Context

## Glossary

- **Completion notification**: a reminder emitted after the main Codex thread finishes one response.
- **Approval notification**: a reminder emitted when Codex is waiting for the user to approve a tool operation.
- **Project name**: the final directory component of the session working directory.
- **Current operation**: `输出完成` for completion, or `等待确认:<operation type>` for approval.

## Invariants

- Subagent completion is not project completion.
- A notification reports state; it never decides an approval or continues a turn.
- Notification content identifies the project and operation without exporting task payloads.
