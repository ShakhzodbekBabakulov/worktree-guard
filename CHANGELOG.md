# Changelog

## Unreleased

- Provide the same `/work`, `/push`, `/ship`, and `/done` workflow for Claude Code and Codex without an external review-workflow dependency.
- Add shared Git, overlap, native edit/merge guard, status, and exact-tip cleanup helpers; preserve legacy Claude entry points.
- Resume existing workspaces/branches and support Codex's linked unnamed worktrees.
- Include the push stage automatically when shipping work that has no current uploaded review.
- Refuse unknown merge evidence, older overlapping reviews, and overlapping unfinished local work; preserve ignored files and changed branch tips during cleanup.
- Add one installer for either/both hosts and user/project scope, explicit conflict replacement, backups, integrity checks, and conservative uninstall.
- Document native hook trust, workspace handoff, integration boundaries, and separate real-host verification evidence.

## v0.2.0

**Adds a second guard: `ship-guard`, the merge gate.**

`worktree-guard` keeps one agent off your main branch. This one keeps two agents
out of each other's way.

When several agent sessions run at once, whichever merges second merges onto a
main branch it never saw, and nothing says so. `ship-guard` refuses a
`gh pr merge` while another **open** pull request changes the same files, and
tells the agent to wait for it and pull it in first.

- **`hook/ship-guard.sh`** — the gate. Wired as a `PreToolUse` hook on `Bash`,
  narrowed with `"if": "Bash(gh pr merge*)"` so it runs only on an actual merge
  and costs nothing on every other command.
- **`hook/session-conflict-check`** — the checker underneath it, and useful on
  its own: run it any time to see who else is in your files. Read-only, always
  exits 0, prints JSON. Reports two kinds of collision, because they need
  opposite responses — an **open pull request** you can wait for, an
  **unsubmitted local worktree** you cannot.
- **`install.sh`** — asks a fourth question, installs both files, wires the
  second hook entry, and self-tests it in both directions before claiming
  success. Only offered when `gh` is present. The settings merge is now reusable
  rather than one-shot, and no longer overwrites its own backup on the second
  pass.
- **`test/selftest.sh`** — 23 assertions became 32. The suite also now refuses
  to run at all if it cannot create its own scratch directory: without that
  check, several assertions came back green while the temp directory did not
  exist, because a missing stub makes the guard fail open. A suite that can
  report passes it did not earn is worse than no suite.

**Fails open, on purpose.** If the checker cannot reach GitHub, the merge is
allowed. That is safe for a specific reason rather than optimism: the merge
being guarded is itself a `gh` call against the same API, so no GitHub means no
merge either way. Refusing would block nothing and only produce a confusing
error.

**Still a tripwire, not a sandbox.** Neither guard stops a determined agent, and
neither hooks arbitrary shell. They catch the things that actually happen.

## v0.1.0

First release. `worktree-guard`: refuses Claude Code's Edit/Write/NotebookEdit
tools on source files while you are sitting on a protected branch, and tells the
agent to go make a worktree. Markdown, JSON and config stay editable, because
planning on main is fine and coding on main is not.

Three fixes made while extracting it from the project it grew up in:

1. Dropped the fallback that judged a file by the current directory's branch. It
   blocked files in no repository at all, according to whatever repo the
   terminal happened to be sitting in. The original's own comment said never to
   do this; the next line did it.
2. Used `dirname` rather than `${var%/*}` when walking up to find an existing
   ancestor directory — the latter leaves a bare `foo` unchanged and loops
   forever.
3. Made the protected branches and the definition of "code" configurable instead
   of hardcoded.
