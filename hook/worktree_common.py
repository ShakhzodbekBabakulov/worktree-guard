"""Shared operations for Claude and Codex worktree workflows. No shell interpolation."""
import json
import os
from pathlib import Path
import subprocess
import sys


class Stop(Exception):
    pass


def run(args, cwd=None, check=True):
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=45)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Stop(str(exc)) from exc
    if check and p.returncode:
        raise Stop('%s failed: %s' % (' '.join(args[:3]), (p.stderr or p.stdout).strip()))
    return p


def git(cwd, *args):
    return run(['git', *args], cwd).stdout.strip()


def root(cwd):
    return Path(git(cwd, 'rev-parse', '--show-toplevel')).resolve()


def ref(cwd, name):
    return git(cwd, 'rev-parse', '--verify', name + '^{commit}')


def ancestor(cwd, older, newer):
    p = run(['git', 'merge-base', '--is-ancestor', older, newer], cwd, False)
    if p.returncode not in (0, 1):
        raise Stop(p.stderr.strip())
    return p.returncode == 0


def base_branch(cwd):
    p = run(['git', 'symbolic-ref', '--quiet', 'refs/remotes/origin/HEAD'], cwd, False)
    if p.returncode == 0:
        return p.stdout.strip().removeprefix('refs/remotes/origin/')
    # Ask Git rather than assuming that every repository uses main.
    out = git(cwd, 'ls-remote', '--symref', 'origin', 'HEAD')
    for line in out.splitlines():
        if line.startswith('ref: refs/heads/'):
            return line.split('\t')[0].removeprefix('ref: refs/heads/')
    raise Stop('Cannot determine the default branch from origin.')


def trees(cwd):
    out = run(['git', 'worktree', 'list', '--porcelain', '-z'], cwd).stdout
    result, item = [], {}
    for field in out.split('\0'):
        if not field:
            if item:
                result.append(item); item = {}
        else:
            key, _, value = field.partition(' ')
            item[key] = value
    return result


def clean(cwd, ignored=False):
    args = ['status', '--porcelain', '--untracked-files=all']
    if ignored:
        args.append('--ignored')
    dirty = git(cwd, *args)
    if dirty:
        raise Stop('Unsaved or untracked%s files in %s:\n%s' %
                   ('/ignored' if ignored else '', cwd, dirty))


def remote_tip(cwd, branch):
    out = git(cwd, 'ls-remote', '--heads', 'origin', 'refs/heads/' + branch)
    rows = [line.split() for line in out.splitlines() if line]
    return next((r[0] for r in rows if r[1] == 'refs/heads/' + branch), None)


def gh_json(cwd, *args):
    try:
        return json.loads(run(['gh', *args], cwd).stdout)
    except ValueError as exc:
        raise Stop('GitHub returned unreadable data.') from exc


def entry(main):
    try:
        main()
    except (Stop, ValueError, KeyError, TypeError, OSError) as exc:
        print('Stopped: ' + str(exc), file=sys.stderr)
        sys.exit(1)


def is_linked(cwd):
    """Verify isolation from Git metadata, not a directory-name convention."""
    here = root(cwd)
    gitdir = Path(git(here, 'rev-parse', '--absolute-git-dir')).resolve()
    common = Path(git(here, 'rev-parse', '--git-common-dir'))
    if not common.is_absolute():
        common = here / common
    return gitdir != common.resolve() and any(
        Path(t['worktree']).resolve() == here and 'prunable' not in t for t in trees(here))


def protected_branches(cwd):
    protected = {'main', 'master'}
    remote = run(['git', 'symbolic-ref', '--quiet', 'refs/remotes/origin/HEAD'], cwd, False)
    if remote.returncode == 0:
        protected.add(remote.stdout.strip().removeprefix('refs/remotes/origin/'))
    elif run(['git', 'remote', 'get-url', 'origin'], cwd, False).returncode == 0:
        raise Stop('The remote default branch is not recorded locally. Run git remote set-head origin --auto, then retry the edit.')
    return protected
