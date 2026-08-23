# serverchan-notifier

## Purpose

Send privacy-minimal ServerChan reminders for Codex root-turn completion and approval requests.

## Layout

- `hooks/hooks.json`: binds `Stop` and `PermissionRequest` without changing their decisions.
- `scripts/serverchan_notifier.py`: validates hook/config input, builds messages, and sends GET requests.
- `scripts/test_serverchan_notifier.py`: title, config, and HTTP contract tests.
- `.env.example`: documents the plugin-local `SERVERCHAN_SENDKEY` schema; `.env` holds the ignored local value.
- `CONTEXT.md`: stable notification terminology and invariants.

## Invariants

- Never store a SendKey in tracked plugin source, tests, or docs; keep the local value only in ignored `.env`.
- Notification failure must never block or approve a Codex operation.
- Do not send commands, tool arguments, or assistant output to ServerChan.
- Keep ServerChan `title` at 32 characters or fewer and `desp` at 32 KiB or fewer.

Update this file and `README.md` when behavior or file ownership changes.
