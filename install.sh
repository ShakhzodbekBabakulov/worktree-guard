#!/usr/bin/env bash
# Compatibility entrypoint; run from a complete clone of worktree-guard.
set -euo pipefail
source_dir=""
if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
  source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
if [[ -z "$source_dir" || ! -f "$source_dir/install.py" || ! -d "$source_dir/hook" || ! -d "$source_dir/skills" ]]; then
  printf '%s\n' 'Please clone https://github.com/ShakhzodbekBabakulov/worktree-guard and run ./install.sh from that clone. A standalone download cannot safely install a matching runtime.' >&2
  exit 1
fi
command -v python3 >/dev/null 2>&1 || { printf '%s\n' 'Python 3.9 or later is required.' >&2; exit 1; }
exec python3 "$source_dir/install.py" "$@"
