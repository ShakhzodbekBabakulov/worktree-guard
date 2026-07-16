#!/usr/bin/env bash
# worktree-guard — keep coding agents off your main branch.
# https://github.com/ShakhzodbekBabakulov/worktree-guard
#
# Refuses Claude Code's Edit/Write/NotebookEdit tools on source files while
# you're sitting on a protected branch, pushing code onto a feature branch
# (ideally a git worktree) instead. Markdown, JSON and config stay editable
# on purpose — planning on main is fine, coding on main is not.
#
# Wired as a PreToolUse hook in settings.json. Claude Code sends the tool call
# as JSON on stdin. Exit 2 denies the call, and whatever this prints to stderr
# is handed back to the agent as the reason.
#
# THIS IS A TRIPWIRE, NOT A SANDBOX. It guards the edit tools. It does not
# guard Bash — `sed -i`, `echo > f.ts` and `git apply` all sail past it. It
# catches the thing that actually happens (an agent absent-mindedly editing
# main), not a determined attempt to get around it.

set -euo pipefail

# ─── config ─────────────────────────────────────────────────────────────────
# Re-run the installer to change these, or just edit them here.

# Branches on which source edits are refused. Space-separated.
PROTECTED_BRANCHES="main"

# How to decide what counts as source:
#   listed       → guard only the extensions in CODE_EXTENSIONS
#   all-but-safe → guard everything except the extensions in SAFE_EXTENSIONS
GUARD_MODE="listed"

# Space-separated, no leading dots.
CODE_EXTENSIONS="bash c cc cjs cpp cs css go h hpp java js jsx kt kts lua m mjs php py rb rs scss sh sql svelte swift ts tsx vue zsh"

# Only consulted when GUARD_MODE=all-but-safe.
SAFE_EXTENSIONS="md markdown mdx txt json jsonc yaml yml toml ini cfg conf env lock csv svg png jpg jpeg gif webp ico"
# ────────────────────────────────────────────────────────────────────────────

# ─── read the tool call ─────────────────────────────────────────────────────
input="$(cat)"

# Pull out the target path. If anything goes wrong here we fail OPEN (allow the
# edit) rather than closed. A guard that breaks should cost you a missed catch,
# not the ability to work at all. The installer checks python3 exists and the
# self-test proves the guard fires, so a silent no-op shouldn't survive install.
file_path="$(printf '%s' "$input" | python3 -c \
  'import sys, json; print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))' \
  2>/dev/null || true)"

[ -n "$file_path" ] || exit 0

# ─── is this a source file? ─────────────────────────────────────────────────
base="${file_path##*/}"
case "$base" in
  *.*) ext="${base##*.}" ;;
  *)   ext="" ;;
esac
ext="$(printf '%s' "$ext" | tr '[:upper:]' '[:lower:]')"

if [ "$GUARD_MODE" = "all-but-safe" ]; then
  # Everything is code until proven otherwise. A file with no extension
  # (Makefile, Dockerfile) counts as code in this mode, on purpose.
  is_code=1
  for e in $SAFE_EXTENSIONS; do
    if [ "$ext" = "$e" ]; then is_code=0; break; fi
  done
else
  is_code=0
  for e in $CODE_EXTENSIONS; do
    if [ "$ext" = "$e" ]; then is_code=1; break; fi
  done
fi

[ "$is_code" = "1" ] || exit 0

# ─── which branch does this file actually live on? ──────────────────────────
# Resolve from the file's own directory, not the current one, so a worktree
# reports its feature branch instead of the main checkout's. For a new file in
# a directory that doesn't exist yet, walk up to the nearest real ancestor.
# dirname, not ${var%/*} — the latter leaves a bare "foo" unchanged and spins
# this loop forever. dirname("foo") is "." and dirname("/") is "/", so it lands.
dir="$(dirname "$file_path")"
while [ "$dir" != "/" ] && [ "$dir" != "." ] && [ ! -d "$dir" ]; do
  dir="$(dirname "$dir")"
done
[ -d "$dir" ] || dir="."

branch="$(git -C "$dir" branch --show-current 2>/dev/null || true)"

# Ask the file's own repo and nothing else. Deliberately NO fallback to the
# current working directory: if the file isn't in a repo, the honest answer is
# "nothing to protect" — not "let me go ask whatever repo my shell happens to
# be sitting in", which blocks unrelated files based on an unrelated branch.
#
# Empty here also covers a detached HEAD, which has no branch to protect.
[ -n "$branch" ] || exit 0

# ─── the rule ───────────────────────────────────────────────────────────────
for b in $PROTECTED_BRANCHES; do
  if [ "$branch" = "$b" ]; then
    {
      echo "BLOCKED by worktree-guard: '$base' is source, and you're on protected branch '$branch'."
      echo
      echo "Code belongs on a feature branch — ideally an isolated worktree:"
      echo "    git worktree add ../wt-<name> -b <name>     # separate folder + branch"
      echo "    git checkout -b <name>                      # or just a branch, in place"
      echo "(If you have the EnterWorktree tool, that does the same in one step.)"
      echo
      echo "Markdown, JSON and config are still editable here — plan freely on '$branch'."
      echo "Protected: $PROTECTED_BRANCHES  ·  configure: $0"
    } >&2
    exit 2
  fi
done

exit 0
