#!/usr/bin/env python3
"""Native claude hook entry point for the shared workflow policy."""
from workflow_guard import main

if __name__ == "__main__":
    raise SystemExit(main("claude"))
