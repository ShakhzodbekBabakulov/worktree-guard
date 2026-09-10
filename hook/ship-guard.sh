#!/usr/bin/env bash
# Legacy Claude entrypoint. All direct merges use the shared fail-closed gate.
# SHIP_GUARD_CHECKER and BLOCKING_KINDS are retired: an alternate report must
# never bypass incomplete-evidence or unfinished-local-work checks.
set -euo pipefail
exec python3 "$(dirname "$0")/legacy_adapter.py" merge
