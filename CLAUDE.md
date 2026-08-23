# serverchan-notifier

## Purpose

Send privacy-minimal ServerChan reminders for Codex root-turn completion, approval requests, and main-session end.

## Layout

- `hooks/hooks.json`: binds `Stop`, `PermissionRequest`, and `SessionEnd` without changing Codex decisions.
- `scripts/serverchan_notifier.py`: validates hook/config input, builds messages, and sends GET requests.
- `scripts/test_serverchan_notifier.py`: title, config, and HTTP contract tests.
- `.env.example`: documents the user-level `SERVERCHAN_SENDKEY` file at `~/.codex/serverchan-notifier.env`.
- `CONTEXT.md`: stable notification terminology and invariants.

## Invariants

- Never store a SendKey in tracked plugin source, tests, or docs; keep it only in `~/.codex/serverchan-notifier.env`.
- Plugin installation and upgrades must not replace notification configuration.
- Notification failure must never block or approve a Codex operation.
- Use lifecycle hooks exclusively; do not add the legacy `notify` callback.
- Do not send commands, tool arguments, or assistant output to ServerChan.
- Keep ServerChan `title` at 32 characters or fewer and `desp` at 32 KiB or fewer.
- Keep `SessionEnd` synchronous with a hook timeout no greater than 3 seconds.

Update this file and `README.md` when behavior or file ownership changes.
