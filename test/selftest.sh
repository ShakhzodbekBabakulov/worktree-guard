#!/usr/bin/env bash
# Exercise installed-style legacy wrappers against disposable repos and fake gh.
# No live GitHub calls or destructive remote actions occur in this suite.
set -euo pipefail
exec python3 "$(dirname "$0")/test_legacy.py" -v
