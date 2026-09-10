"""Validate direct gh pr merge calls against the actual target review."""
import os
import re
import shlex
from workflow_conflicts import report
from worktree_common import Stop


def guard_merge(data):
    command = (data.get('tool_input') or {}).get('command', '')
    if not isinstance(command, str):
        return
    command = command.strip()
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars='();<>|&\n')
        lexer.whitespace = ' \t\r'
        lexer.whitespace_split = True
        parts = list(lexer)
    except ValueError:
        if re.search(r'(?:^|[;\n&|])\s*gh\s+pr\s+merge\b', command):
            raise Stop('Cannot parse the merge command. Run a direct gh pr merge command.')
        return
    matches = [i for i in range(len(parts) - 2) if parts[i:i + 3] == ['gh', 'pr', 'merge']]
    # Only command positions count. A quoted example in echo/Python/heredoc
    # content is not a merge invocation. Wrappers/aliases remain outside this
    # direct-command tripwire, as documented.
    boundaries = set('&;|\n()')
    matches = [i for i in matches if i == 0 or set(parts[i - 1]) <= boundaries]
    if not matches:
        return
    if matches != [0] or '\n' in command.strip() or any(p in {'&&', ';', '|', '||', '&', '>', '>>', '<', '(', ')'} for p in parts):
        raise Stop('Run gh pr merge as a separate command with its repository set as the tool working directory.')
    # gh accepts its positional selector before or after flags. Skip values so
    # a subject/body cannot accidentally become the review being checked.
    selectors, expected_heads = [], []
    value_flags = {'--author-email', '-A', '--body', '-b', '--body-file', '-F',
                   '--match-head-commit', '--subject', '-t'}
    switches = {'--admin', '--auto', '--delete-branch', '-d', '--disable-auto',
                '--merge', '-m', '--rebase', '-r', '--squash', '-s', '--help', '-h'}
    help_requested = False
    index = 3
    while index < len(parts):
        word = parts[index]
        flag, equal, value = word.partition('=')
        if flag in {'--repo', '-R'} or word.startswith('-R'):
            raise Stop('Run the merge in the target repository working directory, without a repository override.')
        if flag in value_flags:
            if not equal:
                index += 1
                if index >= len(parts) or parts[index].startswith('-'):
                    raise Stop('Missing value for ' + flag)
                value = parts[index]
            if not value:
                raise Stop('Missing value for ' + flag)
            if flag == '--match-head-commit':
                expected_heads.append(value)
        elif word in switches:
            help_requested = help_requested or word in {'--help', '-h'}
        elif word.startswith('-'):
            raise Stop('Unsupported merge option layout: ' + word + '. Use separate documented flags and values.')
        else:
            selectors.append(word)
        index += 1
    if help_requested:
        return
    if len(selectors) > 1:
        raise Stop('Use a single review number or branch from the current repository.')
    selector = selectors[0] if selectors else None
    if selector and '://' in selector:
        raise Stop('Use a review number or branch from the current repository.')
    result = report(data.get('cwd') or os.getcwd(), selector)
    if not result['gh_ok']:
        raise Stop('Merge check is incomplete: ' + '; '.join(result['warnings']))
    if not result.get('number'):
        raise Stop('No open review was found for the selected branch.')
    if any(expected != result.get('head') for expected in expected_heads):
        raise Stop('The pull request changed after verification; refresh and retest before merging.')
    blockers = [c for c in result['conflicts'] if c['blocking']]
    if blockers:
        descriptions = [('#' + str(c['number']) if c['kind'] == 'pr' else c['branch']) +
                        ': ' + ', '.join(c['files'][:5]) for c in blockers]
        raise Stop('Overlapping unfinished work: ' + '; '.join(descriptions) +
                   '. Older reviews land first; local sessions need attention. Refresh and retest afterwards.')
