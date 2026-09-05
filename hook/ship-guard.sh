#!/usr/bin/env bash
# ship-guard - keep parallel agent sessions from merging over each other.
# https://github.com/ShakhzodbekBabakulov/worktree-guard
#
# Sibling of worktree-guard. That one keeps an agent off your main branch;
# this one keeps two agents from landing conflicting work on it.
#
# Refuses a `gh pr merge` while another OPEN pull request changes a file this
# branch also changes. The other request was submitted first, so it will land;
# merging now means merging onto a main branch you have never seen, and the
# loser of that race finds out afterwards.
#
# Wired as a PreToolUse hook on Bash in settings.json, narrowed with
#   "if": "Bash(gh pr merge*)"
# so it costs nothing on ordinary commands. Exit 2 denies the call, and
# whatever this prints to stderr is handed back to the agent as the reason.
#
# WHY IT FAILS OPEN. If the conflict check cannot reach GitHub it allows the
# merge. That is safe here for a specific reason, not out of optimism: the
# merge being guarded is itself a `gh` command against the same API. No GitHub
# means no merge either way, so refusing would block nothing and only cost you
# a confusing error. Everything else about a broken check is reported loudly.

set -euo pipefail

# ─── config ─────────────────────────────────────────────────────────────────
# Which collision kinds block a merge. "pr" is an open request that overlaps.
# "worktree" is an unsubmitted local session that overlaps - reported by the
# checker, but not blocked here, because merging cannot race something that
# has not been pushed. Add it if you want the stricter behaviour.
BLOCKING_KINDS="pr"

# The checker. Installed beside this file.
CHECKER="${SHIP_GUARD_CHECKER:-$(dirname "$0")/session-conflict-check}"
# ────────────────────────────────────────────────────────────────────────────

input="$(cat)"

# Pull out the command and the directory it runs in. Fail OPEN on anything
# unreadable, for the same reason worktree-guard does.
command_text="$(printf '%s' "$input" | python3 -c \
  'import sys, json; print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))' \
  2>/dev/null || true)"

[ -n "$command_text" ] || exit 0

# Only guard an actual merge. The settings "if" filter should have done this
# already; repeating it means the hook is still correct if it is ever wired
# without the filter, or invoked by hand.
case "$command_text" in
  *"gh pr merge"*) ;;
  *) exit 0 ;;
esac

work_dir="$(printf '%s' "$input" | python3 -c \
  'import sys, json; print(json.load(sys.stdin).get("cwd", ""))' \
  2>/dev/null || true)"
[ -n "$work_dir" ] && [ -d "$work_dir" ] || work_dir="$PWD"

[ -x "$CHECKER" ] || exit 0

report="$(cd "$work_dir" && "$CHECKER" 2>/dev/null || true)"
[ -n "$report" ] || exit 0

# Ask the report whether anything blocking overlaps. Prints the human-readable
# reason on stdout, or nothing at all when the merge is fine.
blockers="$(printf '%s' "$report" | BLOCKING_KINDS="$BLOCKING_KINDS" python3 -c '
import json, os, sys

try:
    data = json.load(sys.stdin)
except ValueError:
    sys.exit(0)                       # unreadable report -> allow

kinds = set(os.environ.get("BLOCKING_KINDS", "pr").split())
hits = [c for c in data.get("conflicts", []) if c.get("kind") in kinds]
if not hits:
    sys.exit(0)

for c in hits:
    where = "pull request #%s (%s)" % (c.get("number"), c.get("branch", "?"))
    print("  %s" % where)
    if c.get("url"):
        print("    %s" % c["url"])
    for f in c.get("files", [])[:10]:
        print("    also changes %s" % f)
    extra = len(c.get("files", [])) - 10
    if extra > 0:
        print("    ...and %d more shared file(s)" % extra)
' 2>/dev/null || true)"

[ -n "$blockers" ] || exit 0

cat >&2 <<EOF
BLOCKED by ship-guard: another open pull request changes the same files.

$blockers

It was submitted before yours, so it lands first. Merging now would merge onto
a main branch you have not seen, and nothing would tell you afterwards.

What to do:
  1. Wait for that request to merge (the /ship workflow does this for you).
  2. Then pull it in:  git fetch origin && git merge origin/main
  3. Re-run your checks - your code changed when theirs landed.
  4. Merge.

To see the full picture yourself:
  $CHECKER
EOF
exit 2
