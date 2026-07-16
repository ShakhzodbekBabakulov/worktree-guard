# worktree-guard

**Keep coding agents off your main branch.**

Claude Code will edit `main` without a second thought. You asked a question, it
answered by changing three files, and now your main branch has uncommitted work
in it that you didn't plan and can't cleanly review.

`worktree-guard` refuses those edits. Source files on a protected branch are
blocked; the agent is told to go make a worktree. Markdown, JSON and config stay
editable — because thinking, planning and note-taking on `main` are fine. It's
the *coding* that belongs on a branch.

```
BLOCKED by worktree-guard: 'app.ts' is source, and you're on protected branch 'main'.

Code belongs on a feature branch — ideally an isolated worktree:
    git worktree add ../wt-<name> -b <name>     # separate folder + branch
    git checkout -b <name>                      # or just a branch, in place
(If you have the EnterWorktree tool, that does the same in one step.)

Markdown, JSON and config are still editable here — plan freely on 'main'.
```

The agent reads that and starts a worktree. Usually without asking you.

---

## Install

The installer asks three questions, merges itself into your `settings.json`
without disturbing hooks you already have, and **proves the guard actually fires
before it claims success.**

```sh
git clone https://github.com/ShakhzodbekBabakulov/worktree-guard
cd worktree-guard
./install.sh
```

Prefer not to clone? Download it, read it, then run it:

```sh
curl -fsSL https://raw.githubusercontent.com/ShakhzodbekBabakulov/worktree-guard/main/install.sh -o wg-install.sh
less wg-install.sh     # ~320 lines of shell. Worth the five minutes.
bash wg-install.sh
```

There is a `curl … | bash` one-liner and it works, but this is a tool whose whole
job is to stop software from doing things you didn't sanction. Piping it
unexamined into your shell would be a funny way to start.

---

## What it does **not** guard

**This is a tripwire, not a sandbox.** Read this part before you rely on it.

It hooks Claude Code's `Edit`, `Write` and `NotebookEdit` tools. It does **not**
hook `Bash`. An agent that runs `sed -i`, `echo > app.ts`, `git apply`, or a
script that writes files will go straight through it — and no hook can reliably
prevent that, because deciding what an arbitrary shell command will write is not
a solvable problem.

So it does not stop a determined agent, and it is not a security boundary.

What it stops is the thing that actually happens fifty times a week: an agent
absent-mindedly editing `main` because nothing told it not to. That's a real
problem, and this really does solve it.

Other limits, stated plainly:

- **macOS and Linux.** It's a bash script. Windows needs Git Bash or WSL.
- **Claude Code only.** Cursor, Codex and Copilot have entirely different hook
  contracts. Nothing here ports to them.
- **It reads `file_path` only.** A tool call that writes somewhere else isn't seen.
- **It fails open.** If the payload can't be parsed, the edit is allowed. A broken
  guard should cost you a missed catch, not your ability to work. The installer
  checks its dependencies and self-tests precisely so a silently-dead hook
  doesn't survive installation.

---

## Where it applies

| Scope | Lives in | Covers | Notes |
|---|---|---|---|
| **This project** | `<repo>/.claude/` | this repo | commit it and your whole team gets the guard |
| **Every project** | `~/.claude/` | all your repos | just you |

Both work identically across the Claude Code CLI, the desktop app, and the IDE
extensions — [they all read the same settings files][docs-desktop]. There's no
separate desktop install.

**One caveat worth knowing:** [Claude Code on the web][docs-web] clones your repo,
so it runs a project-scoped guard but **not** a global one — `~/.claude/` lives on
your machine and never reaches the cloud session. If you want web coverage,
install into the project.

[docs-desktop]: https://code.claude.com/docs/en/desktop
[docs-web]: https://code.claude.com/docs/en/claude-code-on-the-web

---

## Configuration

Re-run `install.sh` any time, or edit the config block at the top of the
installed `worktree-guard.sh`:

```sh
# Branches on which source edits are refused. Space-separated.
PROTECTED_BRANCHES="main"

# listed       → guard only the extensions in CODE_EXTENSIONS
# all-but-safe → guard everything except the extensions in SAFE_EXTENSIONS
GUARD_MODE="listed"

CODE_EXTENSIONS="bash c cc cjs cpp cs css go h hpp java js jsx kt kts lua m mjs php py rb rs scss sh sql svelte swift ts tsx vue zsh"
SAFE_EXTENSIONS="md markdown mdx txt json jsonc yaml yml toml ini cfg conf env lock csv svg png jpg jpeg gif webp ico"
```

`all-but-safe` is stricter: anything not on the safe list is code, including
extension-less files like `Makefile` and `Dockerfile`.

---

## Requirements

- `git`
- `python3` — the hook uses it to read Claude Code's JSON payload, and the
  installer uses it to merge `settings.json` safely.
  On macOS it ships with the Xcode command line tools, which `git` already needs;
  if you have git, you have it. (`jq` would be the obvious alternative, but it
  carries no such guarantee.)
- `bash`

---

## Uninstall

```sh
rm ~/.claude/hooks/worktree-guard.sh          # or <repo>/.claude/hooks/…
```

Then drop the `worktree-guard` entry from `hooks.PreToolUse` in the matching
`settings.json`. The installer leaves a `settings.json.worktree-guard-backup`
from its first run if you'd rather roll back wholesale.

---

## How it works

Claude Code sends every tool call to a `PreToolUse` hook as JSON on stdin. This
one pulls out `tool_input.file_path`, decides whether it's source, asks **that
file's own repository** which branch it's on, and exits `2` if that branch is
protected. Exit `2` is Claude Code's "deny" signal, and whatever the hook writes
to stderr is handed back to the agent as the reason — which is why the message
above reads like instructions rather than an error.

Asking the *file's* repo rather than the current directory is the important bit.
It means a worktree correctly reports its own feature branch, and a file outside
any repo is correctly left alone instead of being judged by whatever repo your
terminal happens to be sitting in.

---

## Tests

```sh
./test/selftest.sh
```

23 assertions, and every axis is tested in **both** directions — that it blocks
what it should, and that it allows what it should. A suite that only checked
"does it block?" would pass with flying colours on a hook that blocks
everything, which is worse than having no hook at all.

---

## License

MIT — see [LICENSE](LICENSE).
