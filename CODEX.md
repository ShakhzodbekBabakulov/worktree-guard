# Codex integration

Use the [unified installer and workflow guide](README.md) for either host or both.

```sh
python3 install.py --host codex --scope user
python3 install.py --host codex --scope user --check
```

For one repository add `--scope project --project "/path/to/project"` instead.
The compatible `python3 install-codex.py` entry point uses Codex user scope.
Skills live in `.agents/skills`; the native configuration is `.codex/hooks.json`.
Helpers are in `.codex/hooks`. Unrelated configuration is preserved.

## Native workspace behavior

Codex normally starts a native worktree without a named branch. This is valid:
the guard verifies that Git registered it as a linked isolated worktree.
`/push` names it before upload without discarding local changes. A detached
primary checkout remains protected.

`/work` prefers native creation/resumption. The task must verify the actual app
workspace after a native transition. If the active task cannot move itself,
it explains the required native handoff and waits; it must not claim that a
different shell working directory moved the app. `/done` likewise requires
the task to leave the workspace before removing it.

## Hook activation

Review and approve the installed hook in Codex's native controls (`/hooks` in
the CLI), then reload/restart as needed. The installer configures but never
self-approves hooks. A green installer check is not proof of activation.

The adapter receives native `apply_patch` paths from `tool_input.command` and
resolves them relative to the event's `cwd`. It checks additions, updates,
deletions and move destinations. Shell/exec events use the official Bash matcher
for the direct merge guard. Arbitrary scripts and other file tools are outside
edit interception.

Run both deny-on-default and allow-in-isolation smoke tests through Codex itself.
See [recorded verification](docs/verification.md) for tested script behavior and
the separate native-host gate. No result there implies a live user installation
has been changed or activated.

Official references: [worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees),
[hooks](https://learn.chatgpt.com/docs/hooks),
[skills](https://learn.chatgpt.com/docs/build-skills).
