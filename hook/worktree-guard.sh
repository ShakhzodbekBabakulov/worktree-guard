#!/usr/bin/env bash
# Legacy Claude entrypoint. Source decisions use the shared native policy.
set -euo pipefail

# Preserved for existing installations that customize these assignments.
PROTECTED_BRANCHES="main"
GUARD_MODE="listed"
CODE_EXTENSIONS="bash bsl c cc cjs cpp cs css go h hpp java js jsx kt kts lua m mjs php py rb rs scss sh sql svelte swift ts tsx vue zsh"
SAFE_EXTENSIONS="md markdown mdx txt json jsonc yaml yml toml ini cfg conf env lock csv svg png jpg jpeg gif webp ico"

exec python3 "$(dirname "$0")/legacy_adapter.py" edit \
  "$PROTECTED_BRANCHES" "$GUARD_MODE" "$CODE_EXTENSIONS" "$SAFE_EXTENSIONS"
