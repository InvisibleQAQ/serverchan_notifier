# ServerChan Notifier

Defines the user-visible notification language and the configuration boundary that survives plugin upgrades.

## Language

**Completion notification**:
A reminder emitted after the main Codex thread finishes one response.

**Approval notification**:
A reminder emitted when Codex is waiting for the user to approve a tool operation.

**Project name**:
The final directory component of the session working directory.

**Current operation**:
`输出完成` for completion, or `等待确认:<operation type>` for approval.

**Notification configuration**:
The user-owned `~/.codex/serverchan-notifier.env` file containing the ServerChan SendKey.
_Avoid_: Plugin `.env`, cache configuration

## Relationships

- A **Completion notification** identifies one **Project name** and one **Current operation**.
- An **Approval notification** identifies one **Project name** and one **Current operation**.
- Both notification types read the same **Notification configuration**.

## Example dialogue

> **Dev:** "Does a plugin upgrade replace the **Notification configuration**?"
> **Maintainer:** "No. It belongs to the user and stays outside the plugin cache."

## Invariants

- Subagent completion is not project completion.
- A notification reports state; it never decides an approval or continues a turn.
- Notification content identifies the project and operation without exporting task payloads.

## Flagged ambiguities

- `.env` previously meant a file inside the plugin installation; resolved as the user-owned **Notification configuration**.
