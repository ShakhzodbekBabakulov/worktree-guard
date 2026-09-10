"""Read-only PR and local-worktree overlap reporting for Claude and Codex."""
from pathlib import Path
from worktree_common import Stop, base_branch, gh_json, git, root, run, trees

FIELDS = 'number,headRefName,baseRefName,state,changedFiles,headRefOid,isCrossRepository,url'


def files_for_pr(cwd, repo, pr):
    pages = gh_json(cwd, 'api', 'repos/%s/pulls/%s/files' % (repo, pr['number']),
                    '--paginate', '--slurp')
    records = [item for page in pages for item in page]
    if len(records) != pr['changedFiles']:
        raise Stop('Incomplete file list for pull request #%s.' % pr['number'])
    files = {item['filename'] for item in records}
    files.update(item['previous_filename'] for item in records if item.get('previous_filename'))
    return files


def local_files(cwd, base):
    mb = git(cwd, 'merge-base', 'HEAD', 'refs/remotes/origin/' + base)
    files = set()
    for args in [
        ['diff', '--name-only', '--no-renames', '-z', mb, 'HEAD'],
        ['diff', '--name-only', '--no-renames', '-z', 'HEAD'],
        ['ls-files', '--others', '--exclude-standard', '-z'],
    ]:
        files.update(x for x in run(['git', *args], cwd).stdout.split('\0') if x)
    return files


def report(cwd, selector=None):
    result = {'gh_ok': False, 'warnings': [], 'conflicts': []}
    try:
        here = root(cwd)
        origin = git(here, 'remote', 'get-url', 'origin')
        repo = gh_json(here, 'repo', 'view', origin, '--json', 'nameWithOwner')['nameWithOwner']
        base = base_branch(here)
        branch = git(here, 'branch', '--show-current')
        prs = gh_json(here, 'pr', 'list', '--repo', repo, '--state', 'open', '--limit', '100',
                      '--json', FIELDS)
        if len(prs) >= 100:
            raise Stop('At least 100 open requests; this bounded checker cannot establish a complete list.')
        own = gh_json(here, 'pr', 'view', str(selector), '--repo', repo, '--json', FIELDS) if selector else next(
            (p for p in prs if p['headRefName'] == branch and not p['isCrossRepository']), None)
        if own and own.get('isCrossRepository') is not False:
            raise Stop('Cross-repository pull requests need manual review.')
        if own and own['state'] != 'OPEN':
            raise Stop('The selected pull request is not open.')
        if own:
            base = own['baseRefName']
        mine = files_for_pr(here, repo, own) if own else local_files(here, base)
        result.update(branch=own['headRefName'] if own else branch, base=base,
                      number=own['number'] if own else None, head=own['headRefOid'] if own else None, changed_file_count=len(mine))
        submitted = {p['headRefName']: p for p in prs if not p['isCrossRepository']}
        for other in prs:
            if (own and other['number'] == own['number']) or other['baseRefName'] != base:
                continue
            shared = sorted(mine & files_for_pr(here, repo, other))
            if shared:
                result['conflicts'].append(dict(kind='pr', number=other['number'], branch=other['headRefName'],
                    url=other['url'], files=shared, blocking=not own or other['number'] < own['number']))
        for tree in trees(here):
            path = Path(tree['worktree']).resolve()
            name = tree.get('branch', '').removeprefix('refs/heads/')
            if (not own and path == here) or (own and name == own['headRefName']):
                continue
            if 'prunable' in tree or not path.is_dir():
                raise Stop('A registered worktree cannot be inspected: ' + str(path))
            if name == base or name in submitted:
                # Submitted commits are covered by the PR check, but subsequent
                # local edits/commits are not. Do not hide them behind its name.
                baseline = submitted[name]['headRefOid'] if name in submitted else 'refs/remotes/origin/' + base
                pending = set(x for x in run(['git', 'diff', '--name-only', '--no-renames', '-z', baseline], path).stdout.split('\0') if x)
                pending.update(x for x in run(['git', 'ls-files', '--others', '--exclude-standard', '-z'], path).stdout.split('\0') if x)
            else:
                pending = local_files(path, base)
            shared = sorted(mine & pending)
            if shared:
                result['conflicts'].append(dict(kind='worktree', branch=name, path=str(path),
                                               files=shared, blocking=True))
        result['gh_ok'] = True
    except (Stop, ValueError, KeyError, TypeError, OSError) as exc:
        result['warnings'].append(str(exc))
    return result
