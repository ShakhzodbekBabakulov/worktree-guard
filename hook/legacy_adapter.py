#!/usr/bin/env python3
"""Keep the original Claude entrypoints on the shared native guard policy."""
import io
import json
import sys
from workflow_guard import main


def legacy():
    try:
        kind = sys.argv[1]
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError('Unreadable hook event.')
        data.setdefault('tool_name', 'Write' if kind == 'edit' else 'Bash')
        config = None
        if kind == 'edit':
            branches, mode, code, safe = sys.argv[2:]
            config = dict(protected_branches=branches.split(), mode=mode,
                          code_extensions=code.split(), safe_extensions=safe.split())
        sys.stdin = io.StringIO(json.dumps(data))
        return main('claude', config=config)
    except Exception as exc:
        print('BLOCKED by worktree-guard: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(legacy())
