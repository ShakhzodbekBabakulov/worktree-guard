#!/usr/bin/env bash
# Regression suite for hook/worktree-guard.sh.  Run: ./test/selftest.sh
#
# Every test asserts BOTH directions. A suite that only checks "does it block?"
# passes cleanly on a hook that blocks absolutely everything, which is worse
# than no hook at all. So for each axis we prove the block AND the pass-through.

set -uo pipefail   # deliberately not -e: we want every test to run, then a tally

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_SRC="$here/../hook/worktree-guard.sh"
[ -f "$HOOK_SRC" ] || { echo "can't find $HOOK_SRC"; exit 1; }

bold=""; red=""; green=""; dim=""; reset=""
if [ -t 1 ]; then
  bold=$'\033[1m'; red=$'\033[31m'; green=$'\033[32m'; dim=$'\033[2m'; reset=$'\033[0m'
fi

pass=0; fail=0
work="$(mktemp -d)"
# If this fails, $work is empty, every path below becomes "/something", the
# writes fail, and several assertions still come back green because the guard
# fails open on a missing stub. A suite that can report success while its own
# scratch space does not exist is proving nothing. Stop instead.
[ -n "$work" ] && [ -d "$work" ] || {
  echo "could not create a temporary directory - refusing to run a suite that" >&2
  echo "would report passes it did not earn." >&2
  exit 1
}
trap 'rm -rf "$work"' EXIT

# configure <branches> <mode> -> echoes path to a hook built with that config
configure() {
  local out="$work/hook-$3.sh"
  python3 - "$HOOK_SRC" "$1" "$2" > "$out" <<'PY'
import re, sys
src = open(sys.argv[1]).read()
src, a = re.subn(r'^PROTECTED_BRANCHES=.*$', 'PROTECTED_BRANCHES="%s"' % sys.argv[2], src, count=1, flags=re.M)
src, b = re.subn(r'^GUARD_MODE=.*$', 'GUARD_MODE="%s"' % sys.argv[3], src, count=1, flags=re.M)
assert a and b, "config lines not found in template"
sys.stdout.write(src)
PY
  chmod +x "$out"
  printf '%s' "$out"
}

# mkrepo <branch> -> echoes path to a fresh repo genuinely sitting on <branch>
mkrepo() {
  local d; d="$(mktemp -d -p "$work" 2>/dev/null || mktemp -d "$work/r.XXXXXX")"
  git -C "$d" init -q
  git -C "$d" symbolic-ref HEAD "refs/heads/$1"
  git -C "$d" -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m init
  # Prove we're where we claim to be. A repo that silently landed on some other
  # branch would make every downstream assertion meaningless-but-green.
  local got; got="$(git -C "$d" branch --show-current)"
  [ "$got" = "$1" ] || { echo "mkrepo: wanted branch '$1', got '$got'"; exit 1; }
  printf '%s' "$d"
}

probe() {  # probe <hook> <path> -> exit code
  local rc=0
  printf '{"tool_input":{"file_path":"%s"}}' "$2" | "$1" >/dev/null 2>&1 || rc=$?
  printf '%s' "$rc"
}

check() {  # check <description> <expected> <actual>
  if [ "$2" = "$3" ]; then
    pass=$((pass + 1)); printf '  %s✓%s %s\n' "$green" "$reset" "$1"
  else
    fail=$((fail + 1)); printf '  %s✗%s %s %s(wanted %s, got %s)%s\n' \
      "$red" "$reset" "$1" "$dim" "$2" "$3" "$reset"
  fi
}

BLOCK=2; ALLOW=0

printf '\n%sworktree-guard selftest%s\n\n' "$bold" "$reset"

# ── default config: guard "main", listed extensions ─────────────────────────
h="$(configure "main" "listed" default)"
r="$(mkrepo main)"

printf '%son the protected branch%s\n' "$bold" "$reset"
check "blocks app.ts"                          "$BLOCK" "$(probe "$h" "$r/app.ts")"
check "blocks src/deep/new.py (dir not yet created)" "$BLOCK" "$(probe "$h" "$r/src/deep/new.py")"
check "blocks App.TS (extension match is case-insensitive)" "$BLOCK" "$(probe "$h" "$r/App.TS")"
check "allows README.md"                       "$ALLOW" "$(probe "$h" "$r/README.md")"
check "allows settings.json"                   "$ALLOW" "$(probe "$h" "$r/settings.json")"
check "allows Makefile (no extension, listed mode)" "$ALLOW" "$(probe "$h" "$r/Makefile")"

printf '\n%soff the protected branch%s\n' "$bold" "$reset"
rf="$(mkrepo feature-x)"
check "allows app.ts on feature-x"             "$ALLOW" "$(probe "$h" "$rf/app.ts")"
rw="$(mkrepo wip/some-thing)"
check "allows app.ts on wip/some-thing"        "$ALLOW" "$(probe "$h" "$rw/app.ts")"

printf '\n%snot a branch to protect%s\n' "$bold" "$reset"
outside="$(mktemp -d)"
check "allows a file in no repo at all"        "$ALLOW" "$(probe "$h" "$outside/loose.ts")"
rd="$(mkrepo main)"; git -C "$rd" checkout -q --detach
check "allows on a detached HEAD"              "$ALLOW" "$(probe "$h" "$rd/app.ts")"
rm -rf "$outside"

printf '\n%smalformed input fails open, never closed%s\n' "$bold" "$reset"
check "allows on empty JSON object"  "$ALLOW" "$(printf '{}' | "$h" >/dev/null 2>&1; echo $?)"
check "allows on unparseable garbage" "$ALLOW" "$(printf 'not json at all' | "$h" >/dev/null 2>&1; echo $?)"
check "allows when file_path is absent" "$ALLOW" "$(printf '{"tool_input":{}}' | "$h" >/dev/null 2>&1; echo $?)"

printf '\n%smultiple protected branches%s\n' "$bold" "$reset"
h2="$(configure "main develop release" "listed" multi)"
rdev="$(mkrepo develop)"; rrel="$(mkrepo release)"; rok="$(mkrepo topic)"
check "blocks on develop"                      "$BLOCK" "$(probe "$h2" "$rdev/app.ts")"
check "blocks on release"                      "$BLOCK" "$(probe "$h2" "$rrel/app.ts")"
check "allows on topic"                        "$ALLOW" "$(probe "$h2" "$rok/app.ts")"

printf '\n%sall-but-safe mode%s\n' "$bold" "$reset"
h3="$(configure "main" "all-but-safe" strict)"
rs="$(mkrepo main)"
check "blocks Makefile (no extension is code here)" "$BLOCK" "$(probe "$h3" "$rs/Makefile")"
check "blocks weird.xyz (unknown extension)"   "$BLOCK" "$(probe "$h3" "$rs/weird.xyz")"
check "still allows README.md"                 "$ALLOW" "$(probe "$h3" "$rs/README.md")"
check "still allows config.yaml"               "$ALLOW" "$(probe "$h3" "$rs/config.yaml")"
check "still allows logo.png"                  "$ALLOW" "$(probe "$h3" "$rs/logo.png")"

printf '\n%sship-guard: the merge gate%s\n' "$bold" "$reset"
SHIP_SRC="$here/../hook/ship-guard.sh"
if [ ! -f "$SHIP_SRC" ]; then
  check "hook/ship-guard.sh exists" ok missing
else
  # Stub checkers stand in for the real one: no network, no pull requests. What
  # is under test is the guard's decision, not the checker's arithmetic.
  stub() { printf '#!/bin/sh\ncat <<'\''J'\''\n%s\nJ\n' "$2" > "$1"; chmod +x "$1"; }
  stub "$work/stub-hit"    '{"conflicts":[{"kind":"pr","number":7,"branch":"other","url":"http://x/7","files":["a.ts","b.py"]}]}'
  stub "$work/stub-clean"  '{"conflicts":[]}'
  stub "$work/stub-wt"     '{"conflicts":[{"kind":"worktree","path":"/tmp/w","branch":"o","files":["a.ts"]}]}'
  stub "$work/stub-broken" 'not json at all'

  sprobe() {  # sprobe <checker> <command> -> exit code
    local rc=0
    printf '{"tool_input":{"command":"%s"},"cwd":"%s"}' "$2" "$work" \
      | SHIP_GUARD_CHECKER="$1" "$SHIP_SRC" >/dev/null 2>&1 || rc=$?
    printf '%s' "$rc"
  }

  check "blocks a merge that overlaps an open request" \
    "$BLOCK" "$(sprobe "$work/stub-hit" "gh pr merge 7 --squash")"
  check "allows a merge with nothing in its way" \
    "$ALLOW" "$(sprobe "$work/stub-clean" "gh pr merge 7 --squash")"
  check "ignores ordinary commands entirely" \
    "$ALLOW" "$(sprobe "$work/stub-hit" "ls -la")"
  check "ignores a command that only reads history" \
    "$ALLOW" "$(sprobe "$work/stub-hit" "git log --oneline")"
  # A merge cannot race work nobody has pushed, so there is nothing to wait for.
  check "allows when only an unsubmitted worktree overlaps" \
    "$ALLOW" "$(sprobe "$work/stub-wt" "gh pr merge 7 --squash")"
  # Fails open deliberately: the merge being guarded is itself a gh call, so a
  # broken checker cannot wave a bad merge through - there would be no merge.
  check "fails open when the checker is broken" \
    "$ALLOW" "$(sprobe "$work/stub-broken" "gh pr merge 7 --squash")"
  check "fails open when the checker is missing" \
    "$ALLOW" "$(sprobe "$work/no-such-checker" "gh pr merge 7 --squash")"

  smsg="$(printf '{"tool_input":{"command":"gh pr merge 7"},"cwd":"%s"}' "$work" \
    | SHIP_GUARD_CHECKER="$work/stub-hit" "$SHIP_SRC" 2>&1 >/dev/null)"
  case "$smsg" in *"#7"*) check "names the blocking request" ok ok ;;
                  *) check "names the blocking request" ok missing ;; esac
  case "$smsg" in *"a.ts"*) check "names a shared file" ok ok ;;
                  *) check "names a shared file" ok missing ;; esac
fi

printf '\n%sthe denial message is actually useful%s\n' "$bold" "$reset"
msg="$(printf '{"tool_input":{"file_path":"%s"}}' "$r/app.ts" | "$h" 2>&1 >/dev/null)"
case "$msg" in *"worktree"*) check "mentions worktrees" ok ok ;; *) check "mentions worktrees" ok missing ;; esac
case "$msg" in *"main"*) check "names the branch" ok ok ;; *) check "names the branch" ok missing ;; esac

printf '\n'
if [ "$fail" -eq 0 ]; then
  printf '%s%s✓ all %d passed%s\n\n' "$green" "$bold" "$pass" "$reset"; exit 0
else
  printf '%s%s✗ %d failed%s, %d passed\n\n' "$red" "$bold" "$fail" "$reset" "$pass"; exit 1
fi
