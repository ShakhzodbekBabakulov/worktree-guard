"""Native event adapters share one file/merge policy. No writes in a hook."""
import json
import os
from pathlib import Path
import re
import signal
import sys
from worktree_common import Stop, is_linked, protected_branches, run

CODE = set('bash bsl c cc cjs cpp cs css go h hpp ipynb java js jsx kt kts lua m mjs php py rb rs scss sh sql svelte swift ts tsx vue zsh'.split())
SAFE = set('md markdown mdx txt json jsonc yaml yml toml ini cfg conf env lock csv svg png jpg jpeg gif webp ico'.split())


def policy(override=None):
    path = Path(__file__).with_name('worktree-guard-config.json')
    config = json.loads(path.read_text()) if path.exists() else {}
    if override is not None:
        if not isinstance(override, dict) or not isinstance(config, dict):
            raise Stop('Guard configuration must be a JSON object.')
        config.update(override)
    if not isinstance(config, dict):
        raise Stop('Guard configuration must be a JSON object.')
    for key in ('protected_branches', 'code_extensions', 'safe_extensions'):
        if key in config and (not isinstance(config[key], list) or
                              not all(isinstance(v, str) for v in config[key])):
            raise Stop('Invalid guard configuration: ' + key)
    if config.get('mode', 'listed') not in ('listed', 'all-but-safe'):
        raise Stop('Guard mode must be listed or all-but-safe.')
    return config


def patch_guard(data, host, config=None):
    inputs = data.get('tool_input')
    if not isinstance(inputs, dict):
        raise Stop('Unreadable edit event; no file paths were checked.')
    tool = data.get('tool_name', '')
    paths = []
    if tool == 'apply_patch':
        patch = inputs.get('command')
        if not isinstance(patch, str):
            raise Stop('Unreadable patch event.')
        paths = re.findall(r'^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$', patch, re.M)
    else:
        paths = [inputs[key] for key in ('file_path', 'notebook_path') if inputs.get(key)]
    if not paths or not all(isinstance(p, str) and p for p in paths):
        raise Stop('The edit paths could not be read; inspect the event before retrying.')
    config = policy(config)
    code = set(config.get('code_extensions', CODE))
    safe = set(config.get('safe_extensions', SAFE))
    cwd = Path(data.get('cwd') or os.getcwd())
    for filename in paths:
        path = Path(filename)
        if not path.is_absolute():
            path = cwd / path
        path = path.resolve()
        ext = path.suffix.lower().lstrip('.')
        is_code = ext not in safe if config.get('mode') == 'all-but-safe' else ext in code
        if not is_code:
            continue
        directory = path.parent
        while not directory.is_dir() and directory != directory.parent:
            directory = directory.parent
        p = run(['git', 'rev-parse', '--is-inside-work-tree'], directory, False)
        if p.returncode or p.stdout.strip() != 'true':
            continue
        branch = run(['git', 'branch', '--show-current'], directory).stdout.strip()
        protected = (protected_branches(directory) if branch else set()) | set(config.get('protected_branches', []))
        if branch in protected or (not branch and not is_linked(directory)):
            raise Stop('%s is source on %s. Run /work to create or resume an isolated workspace.' %
                       (path.name, branch or 'the detached primary checkout'))


def main(host, config=None):
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise Stop('Unreadable hook event.')
        tool = data.get('tool_name', '')
        if tool == 'Bash':
            def timed_out(signum, frame):
                raise Stop('Merge verification timed out; no all-clear was established.')
            signal.signal(signal.SIGALRM, timed_out)
            signal.alarm(40)
            from workflow_merge_guard import guard_merge
            guard_merge(data)
        elif tool in {'apply_patch', 'Edit', 'Write', 'NotebookEdit'}:
            patch_guard(data, host, config)
        else:
            raise Stop('Unknown guarded tool: ' + str(tool))
    except Exception as exc:
        print('BLOCKED by worktree-guard: ' + str(exc), file=sys.stderr)
        return 2
    finally:
        signal.alarm(0)
    return 0
