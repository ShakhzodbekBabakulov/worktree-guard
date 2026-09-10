#!/usr/bin/env python3
"""Compatibility entrypoint for the unified installer (Codex, user scope)."""
from pathlib import Path
import runpy
import sys

if __name__ == '__main__':
    sys.argv[1:1] = ['--host', 'codex', '--scope', 'user']
    runpy.run_path(str(Path(__file__).resolve().with_name('install.py')), run_name='__main__')
