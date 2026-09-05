#!/usr/bin/env bash
# worktree-guard installer — https://github.com/ShakhzodbekBabakulov/worktree-guard
#
# Asks three questions, writes the hook, merges it into your Claude Code
# settings.json (without eating your existing hooks), then proves the guard
# actually fires before telling you it worked.
#
# Works both as a local `./install.sh` and piped: `curl -fsSL ... | bash`.
# The piped case is why every prompt reads from /dev/tty and not stdin —
# when a script is piped into bash, stdin IS the script, so a plain `read`
# would silently swallow the script's own bytes instead of waiting for you.

set -euo pipefail

REPO="https://github.com/ShakhzodbekBabakulov/worktree-guard"
# Overridable so forks — and this repo's own tests — can point at another source.
RAW_BASE="${WG_HOOK_BASE_URL:-https://raw.githubusercontent.com/ShakhzodbekBabakulov/worktree-guard/main/hook}"

bold=""; dim=""; red=""; green=""; reset=""
if [ -t 1 ]; then
  bold=$'\033[1m'; dim=$'\033[2m'; red=$'\033[31m'; green=$'\033[32m'; reset=$'\033[0m'
fi

die() { printf '\n%serror:%s %s\n' "$red" "$reset" "$1" >&2; exit 1; }

# ─── prerequisites ──────────────────────────────────────────────────────────
command -v git >/dev/null 2>&1 || die "git is required but not on PATH."
command -v python3 >/dev/null 2>&1 || die \
"python3 is required but not on PATH.
  The hook uses it to read Claude Code's JSON payload, and the installer uses
  it to merge settings.json without clobbering your existing hooks.
  macOS: xcode-select --install     Debian/Ubuntu: sudo apt install python3"

# We need a real terminal to ask questions. Under `curl | bash` stdin is the
# pipe, so /dev/tty is the only way to reach the human.
TTY="/dev/tty"
[ -r "$TTY" ] && [ -w "$TTY" ] || die \
"no terminal available, so I can't ask you anything.
  This installer is interactive. Run it from a terminal, or clone the repo
  and edit hook/worktree-guard.sh by hand: $REPO"

# Answer lands in $ANSWER rather than being echoed for $(...) to capture.
# Deliberate: `die` inside a command substitution runs in a subshell and would
# only kill the subshell, letting the installer carry on with a bogus value.
#
# EOF is NOT the same as pressing Enter. Pressing Enter means "use the default";
# EOF means there is nobody there, and silently installing defaults on behalf of
# nobody is how you end up guarding a branch named "1".
ANSWER=""
ask() {
  local prompt="$1" default="$2" reply=""
  printf '%s' "$prompt" >"$TTY"
  if ! IFS= read -r reply <"$TTY"; then
    printf '\n' >"$TTY"
    die "reached end of input while waiting for an answer.
  This installer is interactive and needs a real terminal."
  fi
  ANSWER="${reply:-$default}"
}

say() { printf '%s\n' "$1" >"$TTY"; }

# ─── banner ─────────────────────────────────────────────────────────────────
say ""
say "  ${bold}worktree-guard${reset} — keep coding agents off your main branch"
say "  ${dim}${REPO}${reset}"
say ""

# ─── 1. scope ───────────────────────────────────────────────────────────────
in_repo=0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 && in_repo=1
repo_root=""
[ "$in_repo" = "1" ] && repo_root="$(git rev-parse --show-toplevel)"

say "  ${bold}Where should this apply?${reset}"
say ""
if [ "$in_repo" = "1" ]; then
  say "    1) This project only   ${dim}$repo_root/.claude/${reset}"
  say "       ${dim}commit it and your whole team gets the guard${reset}"
else
  say "    1) This project only   ${dim}(unavailable — you're not inside a git repo)${reset}"
fi
say "    2) Every project        ${dim}~/.claude/${reset}"
say "       ${dim}just you, all repos. Note: Claude Code on the web ignores this${reset}"
say "       ${dim}one — cloud sessions only read a repo's own .claude/ folder.${reset}"
say ""

scope=""
while [ -z "$scope" ]; do
  ask "  Choose [1]: " "1"; choice="$ANSWER"
  case "$choice" in
    1) if [ "$in_repo" = "1" ]; then scope="project"; else
         say "  ${red}Not inside a git repo — can't do a project install here.${reset}"
       fi ;;
    2) scope="global" ;;
    *) say "  ${red}Enter 1 or 2.${reset}" ;;
  esac
done

if [ "$scope" = "project" ]; then
  claude_dir="$repo_root/.claude"
  hook_dir_ref='$CLAUDE_PROJECT_DIR/.claude/hooks'
else
  claude_dir="$HOME/.claude"
  hook_dir_ref='$HOME/.claude/hooks'
fi
hook_command="\"$hook_dir_ref/worktree-guard.sh\""
ship_command="\"$hook_dir_ref/ship-guard.sh\""
hook_path="$claude_dir/hooks/worktree-guard.sh"
ship_path="$claude_dir/hooks/ship-guard.sh"
checker_path="$claude_dir/hooks/session-conflict-check"
settings_path="$claude_dir/settings.json"

# ─── 2. protected branches ──────────────────────────────────────────────────
say ""
default_branch="main"
if [ "$in_repo" = "1" ]; then
  cur="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  case "$cur" in main|master) default_branch="$cur" ;; esac
fi
say "  ${bold}Which branches are protected?${reset} ${dim}(space-separated)${reset}"
branches=""
while [ -z "$branches" ]; do
  ask "  Branches [$default_branch]: " "$default_branch"; reply="$ANSWER"
  ok=1
  for b in $reply; do
    if ! printf '%s' "$b" | grep -Eq '^[A-Za-z0-9._/-]+$'; then
      say "  ${red}'$b' has characters I won't put in a shell script. Letters, digits, . _ / - only.${reset}"
      ok=0
    fi
  done
  [ "$ok" = "1" ] && branches="$reply"
done

# ─── 3. what counts as code ─────────────────────────────────────────────────
say ""
say "  ${bold}What counts as \"code\"?${reset}"
say ""
say "    1) Sensible defaults   ${dim}.ts .tsx .py .swift .kt .go .rs .rb .java .sh .sql .css …${reset}"
say "       ${dim}markdown, JSON, YAML and everything else stay editable${reset}"
say "    2) Everything except   ${dim}markdown, text, JSON, YAML, TOML, config, images${reset}"
say "       ${dim}stricter — also guards Makefile, Dockerfile, and other${reset}"
say "       ${dim}extension-less files${reset}"
say ""
mode=""
while [ -z "$mode" ]; do
  ask "  Choose [1]: " "1"; choice="$ANSWER"
  case "$choice" in
    1) mode="listed" ;;
    2) mode="all-but-safe" ;;
    *) say "  ${red}Enter 1 or 2.${reset}" ;;
  esac
done

# ─── 4. the merge gate ──────────────────────────────────────────────────────
# Only worth offering if `gh` is around: the gate reads open pull requests, and
# the command it guards is itself a gh command.
want_ship="no"
if command -v gh >/dev/null 2>&1; then
  say ""
  say "  ${bold}Also stop parallel sessions merging over each other?${reset}"
  say ""
  say "    ${dim}When two agents work at once, whichever merges second merges onto${reset}"
  say "    ${dim}a main branch it never saw — and nothing tells you. ship-guard${reset}"
  say "    ${dim}refuses a \`gh pr merge\` while another OPEN pull request changes${reset}"
  say "    ${dim}the same files. It runs only on merges, so it costs nothing${reset}"
  say "    ${dim}the rest of the time.${reset}"
  say ""
  while :; do
    ask "  Install it? [Y/n]: " "y"; choice="$ANSWER"
    case "$choice" in
      y|Y|yes|Yes) want_ship="yes"; break ;;
      n|N|no|No)   want_ship="no";  break ;;
      *) say "  ${red}Enter y or n.${reset}" ;;
    esac
  done
fi

# ─── fetch the hook template ────────────────────────────────────────────────
# Running from a clone? Use the local file. Piped through bash? BASH_SOURCE
# isn't a real path, so fall back to downloading it.
src_dir=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

# Answer lands in $FETCHED, for the same subshell reason `ask` uses $ANSWER:
# `die` inside $(...) would only kill the subshell.
FETCHED=""
fetch_hook() {
  local name="$1"
  if [ -n "$src_dir" ] && [ -f "$src_dir/hook/$name" ]; then
    FETCHED="$(cat "$src_dir/hook/$name")"
  else
    command -v curl >/dev/null 2>&1 || die \
      "need curl to download $name (or run this from a clone)."
    FETCHED="$(curl -fsSL "$RAW_BASE/$name")" || die \
      "couldn't download $name from $RAW_BASE/$name"
  fi
  [ -n "$FETCHED" ] || die "$name came back empty."
}

fetch_hook worktree-guard.sh
template="$FETCHED"

# ─── write the hook, with the answers baked in ──────────────────────────────
mkdir -p "$claude_dir/hooks"

# Substitute in python, not sed: branch names may contain '/', which turns sed
# delimiters into a guessing game.
printf '%s' "$template" | python3 -c '
import re, sys
branches, mode = sys.argv[1], sys.argv[2]
src = sys.stdin.read()
src, n1 = re.subn(r"^PROTECTED_BRANCHES=.*$", "PROTECTED_BRANCHES=\"%s\"" % branches, src, count=1, flags=re.M)
src, n2 = re.subn(r"^GUARD_MODE=.*$", "GUARD_MODE=\"%s\"" % mode, src, count=1, flags=re.M)
if not (n1 and n2):
    sys.stderr.write("template did not contain the expected config lines\n")
    sys.exit(1)
sys.stdout.write(src)
' "$branches" "$mode" > "$hook_path.tmp" || die "failed to configure the hook template."
mv "$hook_path.tmp" "$hook_path"
chmod +x "$hook_path"

# ─── merge into settings.json ───────────────────────────────────────────────
MERGE_PY='
import json, os, shutil, sys

path, command, MATCHER, MARKER, IF_FILTER = sys.argv[1:6]

data = {}
backed_up = ""
if os.path.exists(path):
    with open(path, encoding="utf-8") as f:
        raw = f.read().strip()
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            sys.stderr.write(
                "%s is not valid JSON (%s).\n"
                "I will not touch it — fix it, or add the hook by hand.\n" % (path, e))
            sys.exit(1)
        backed_up = path + ".worktree-guard-backup"
        # Only the first time. A second merge in the same run must not overwrite
        # the backup with a copy of the half-merged file - that is the one state
        # nobody wants to roll back to.
        if not os.path.exists(backed_up):
            shutil.copy2(path, backed_up)

if not isinstance(data, dict):
    sys.stderr.write("%s does not contain a JSON object at the top level.\n" % path)
    sys.exit(1)

hooks = data.setdefault("hooks", {})
if not isinstance(hooks, dict):
    sys.stderr.write("The \"hooks\" key in %s is not an object. Refusing to guess.\n" % path)
    sys.exit(1)

pre = hooks.setdefault("PreToolUse", [])
if not isinstance(pre, list):
    sys.stderr.write("hooks.PreToolUse in %s is not a list. Refusing to guess.\n" % path)
    sys.exit(1)

hook_obj = {"type": "command", "command": command}
if IF_FILTER:
    # Narrow the hook to the one command it guards, so it costs nothing on the
    # thousands of shell calls it has no opinion about.
    hook_obj["if"] = IF_FILTER
    hook_obj["timeout"] = 120
    hook_obj["statusMessage"] = "Checking for conflicting sessions"
entry = {"matcher": MATCHER, "hooks": [hook_obj]}

def is_ours(e):
    if not isinstance(e, dict):
        return False
    for h in e.get("hooks", []) or []:
        if isinstance(h, dict) and MARKER in str(h.get("command", "")):
            return True
    return False

replaced = False
for i, e in enumerate(pre):
    if is_ours(e):
        pre[i] = entry
        replaced = True
        break
if not replaced:
    pre.append(entry)

# Count what we are keeping, so the installer can prove it kept it.
kept = sum(len(e.get("hooks", []) or []) for e in pre
           if isinstance(e, dict) and not is_ours(e))
for event, entries in hooks.items():
    if event == "PreToolUse" or not isinstance(entries, list):
        continue
    kept += sum(len(e.get("hooks", []) or []) for e in entries if isinstance(e, dict))

# Write via a temp file + rename so a crash cannot leave a truncated settings.json.
tmp = path + ".worktree-guard-tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
os.replace(tmp, path)

print("%s\t%d\t%s" % ("updated" if replaced else "added", kept, backed_up))
'

merge_result="$(python3 -c "$MERGE_PY" \
  "$settings_path" "$hook_command" "Edit|Write|NotebookEdit" "worktree-guard" "")" \
  || die "couldn't merge into $settings_path — nothing was changed."

merge_action="$(printf '%s' "$merge_result" | cut -f1)"
merge_kept="$(printf '%s' "$merge_result" | cut -f2)"
merge_backup="$(printf '%s' "$merge_result" | cut -f3)"

# ─── the merge gate, if it was wanted ───────────────────────────────────────
# Two files: the hook Claude Code calls, and the checker it leans on. The
# checker is also useful on its own — run it any time to see who else is
# touching your files — so it is installed as a normal executable, not hidden.
if [ "$want_ship" = "yes" ]; then
  fetch_hook ship-guard.sh
  printf '%s' "$FETCHED" > "$ship_path.tmp" && mv "$ship_path.tmp" "$ship_path"
  chmod +x "$ship_path"

  fetch_hook session-conflict-check
  printf '%s' "$FETCHED" > "$checker_path.tmp" && mv "$checker_path.tmp" "$checker_path"
  chmod +x "$checker_path"

  python3 -c "$MERGE_PY" \
    "$settings_path" "$ship_command" "Bash" "ship-guard" "Bash(gh pr merge*)" \
    >/dev/null || die "couldn't add the merge gate to $settings_path."
fi

# ─── prove it actually works ────────────────────────────────────────────────
# An installer that says "done" without testing is indistinguishable from one
# that silently did nothing. Test BOTH directions: a guard that blocks
# everything would sail through a blocks-on-main check alone.
first_branch="${branches%% *}"
t="$(mktemp -d)"
trap 'rm -rf "$t"' EXIT
git -C "$t" init -q -b "$first_branch" 2>/dev/null || {
  git -C "$t" init -q
  git -C "$t" symbolic-ref HEAD "refs/heads/$first_branch"
}
git -C "$t" -c user.email=wg@example.com -c user.name=worktree-guard \
  commit -q --allow-empty -m init

probe() {
  local rc=0
  printf '{"tool_input":{"file_path":"%s"}}' "$1" | "$hook_path" >/dev/null 2>&1 || rc=$?
  printf '%s' "$rc"
}

fails=""
[ "$(probe "$t/app.ts")" = "2" ] || fails="$fails\n    - did NOT block app.ts on '$first_branch'"
[ "$(probe "$t/notes.md")" = "0" ] || fails="$fails\n    - wrongly blocked notes.md (docs must stay editable)"
git -C "$t" checkout -q -b wg-selftest-branch
[ "$(probe "$t/app.ts")" = "0" ] || fails="$fails\n    - wrongly blocked app.ts on a feature branch"

# Same rule for the merge gate: prove it refuses AND prove it lets things
# through. Stub checkers stand in for the real one so the test needs no network
# and no pull requests of its own.
if [ "$want_ship" = "yes" ]; then
  printf '#!/bin/sh\necho %s\n' \
    "'{\"conflicts\":[{\"kind\":\"pr\",\"number\":1,\"branch\":\"other\",\"files\":[\"a.ts\"]}]}'" \
    > "$t/stub-hit"
  printf '#!/bin/sh\necho %s\n' "'{\"conflicts\":[]}'" > "$t/stub-clean"
  chmod +x "$t/stub-hit" "$t/stub-clean"

  ship_probe() {
    local checker="$1" cmd="$2" rc=0
    printf '{"tool_input":{"command":"%s"},"cwd":"%s"}' "$cmd" "$t" \
      | SHIP_GUARD_CHECKER="$checker" "$ship_path" >/dev/null 2>&1 || rc=$?
    printf '%s' "$rc"
  }

  [ "$(ship_probe "$t/stub-hit" "gh pr merge 1 --squash")" = "2" ] \
    || fails="$fails\n    - did NOT block a merge that overlaps an open request"
  [ "$(ship_probe "$t/stub-clean" "gh pr merge 1 --squash")" = "0" ] \
    || fails="$fails\n    - wrongly blocked a merge with nothing in its way"
  [ "$(ship_probe "$t/stub-hit" "ls -la")" = "0" ] \
    || fails="$fails\n    - interfered with an ordinary command"
fi

if [ -n "$fails" ]; then
  say ""
  say "  ${red}${bold}Self-test FAILED.${reset} The hook is installed but is not behaving:"
  # shellcheck disable=SC2059
  printf "$fails\n" >"$TTY"
  say ""
  say "  Please open an issue with this output: $REPO/issues"
  exit 1
fi

# ─── report ─────────────────────────────────────────────────────────────────
say ""
say "  ${green}✓${reset} wrote  ${dim}$hook_path${reset}"
if [ "$merge_action" = "updated" ]; then
  say "  ${green}✓${reset} updated the existing worktree-guard entry in ${dim}$settings_path${reset}"
else
  say "  ${green}✓${reset} added to ${dim}$settings_path${reset}"
fi
if [ "$merge_kept" -gt 0 ]; then
  say "  ${green}✓${reset} kept your $merge_kept other hook(s) untouched"
fi
[ -n "$merge_backup" ] && say "  ${green}✓${reset} backup  ${dim}$merge_backup${reset}"
say "  ${green}✓${reset} self-test: blocks code on ${bold}$first_branch${reset}, allows it on a branch, leaves docs alone"
if [ "$want_ship" = "yes" ]; then
  say "  ${green}✓${reset} wrote  ${dim}$ship_path${reset}"
  say "  ${green}✓${reset} wrote  ${dim}$checker_path${reset}"
  say "  ${green}✓${reset} self-test: refuses a merge that overlaps an open request, allows one that doesn't"
fi
say ""
say "  ${bold}Protected:${reset} $branches"
if [ "$want_ship" = "yes" ]; then
  say "  ${bold}Merge gate:${reset} on — see who else is in your files any time with"
  say "  ${dim}  $checker_path${reset}"
fi
if [ "$scope" = "project" ]; then
  say "  ${dim}Commit .claude/ to share the guard with your team.${reset}"
fi
say "  ${dim}Reconfigure any time: re-run this, or edit the config block at the${reset}"
say "  ${dim}top of the hook. Uninstall: delete the hook + its settings.json entry.${reset}"
say ""
say "  Restart Claude Code to arm it."
say ""
