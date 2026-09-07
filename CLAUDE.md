# serverchan-notifier

## Purpose

Send privacy-minimal ServerChan reminders for Codex and Claude Code lifecycle events:
turn completion, approval requests, turn failure, idle waiting, and session end.

## Layout

The repository is simultaneously a plugin marketplace and the plugin root for both agents. Each agent
installs the repository root (`source` path `./`) as an isolated copy, so the implementation must live
inside the root — a parent-relative path does not survive installation.

- `.agents/plugins/marketplace.json`: Codex marketplace manifest; declares `serverchan-notifier` with
  `{"source":"local","path":"./"}`.
- `.claude-plugin/marketplace.json`: Claude Code marketplace manifest; declares
  `serverchan-notifier-claude` with `"source": "./"`. Both manifests name the marketplace `serverchan`.
- `.codex-plugin/plugin.json`: Codex plugin manifest; `"hooks": "./codex-hooks.json"`.
- `.claude-plugin/plugin.json`: Claude Code plugin manifest; `"hooks": "./claude-hooks.json"`.
- `codex-hooks.json`: binds `Stop`, `PermissionRequest`, `SessionEnd`.
- `claude-hooks.json`: binds `Stop`, `StopFailure`, `PermissionRequest`, `Notification`
  (matcher `^idle_prompt$`), `SessionEnd` (matcher excludes `clear` and `resume`).
- `scripts/serverchan_notifier.py`: the only implementation; `AGENT_EVENTS` is the source of truth for
  which events each agent may emit.
- `scripts/test_serverchan_notifier.py`: message, hook-contract, marketplace, and HTTP tests, plus a real
  PowerShell launch test for each agent's command.
- `.env.example`: documents the user-level `SERVERCHAN_SENDKEY` file at `~/.codex/serverchan-notifier.env`.
- `CONTEXT.md`: stable notification terminology and invariants.

## Invariants

- Never store a SendKey in tracked plugin source, tests, or docs; keep it only in
  `~/.codex/serverchan-notifier.env`. Both plugins read that one file.
- Plugin installation and upgrades must not replace notification configuration.
- Notification failure must never block, approve, or continue an agent operation. The script always exits
  0, prints `{}` first, and logs errors instead of raising.
- Use lifecycle hooks exclusively; do not add the legacy Codex `notify` callback.
- Do not send commands, tool arguments, or assistant output to ServerChan. `StopFailure` may report its
  bounded `error` enum but never `error_details` or `last_assistant_message`.
- Keep ServerChan `title` at 32 characters or fewer and `desp` at 32 KiB or fewer. When the title runs
  out of room, truncate the operation detail before the project name.
- Keep `SessionEnd` synchronous with a hook timeout no greater than 3 seconds in both hook files.
- The notifying agent is passed explicitly as `--agent codex|claude`. Never infer it from environment
  variables: Codex also substitutes `CLAUDE_PLUGIN_ROOT`, so sniffing is unreliable.
- Never create `hooks/hooks.json`. Claude Code auto-loads that path inside a plugin root regardless of
  the manifest, and both plugin roots are the repository root, so such a file would fire one agent's
  hooks under the other. Each plugin's hook file is named by its own manifest instead.
- Every hook command must reference the script inside the plugin root (`scripts/…`), never through `..`.
- Resolve Codex Windows plugin paths with PowerShell's `$env:PLUGIN_ROOT` syntax; Claude Code has no
  `commandWindows` key and substitutes `${CLAUDE_PLUGIN_ROOT}` itself before the shell runs. Cover both
  commands with a real PowerShell launch test.
- Adding an event to one agent does not add it to the other. `AGENT_EVENTS` is the single source of
  truth and each hook file must declare exactly its own set.
- `.agents/` is ignored except for `.agents/plugins/marketplace.json`; the `.gitignore` re-includes the
  directory itself first because a global ignore of `.agents/` would stop git from descending.

## Known unverified behaviour

`[UNKNOWN]` Codex reading `plugin.json#hooks`. Its binary carries the doc snippet
`"hooks": "./hooks.json",` and the provenance label `plugin.json#hooks[`, and `codex plugin add`
succeeds, but Codex parses no hook file at install time (even malformed JSON at the default path is
silent), so the field cannot be proven without a trusted interactive session. If Codex turns out to
ignore it, the failure is silent absence of notifications — not duplicates or errors — and the fallback
is to give Codex its own plugin root with a copied script, kept honest by an identity test.

Update this file, `CONTEXT.md`, and `README.md` when behavior or file ownership changes.
