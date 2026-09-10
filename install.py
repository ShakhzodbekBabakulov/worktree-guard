#!/usr/bin/env python3
"""Install the shared workflow using native Claude Code and Codex hooks/skills."""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

SOURCE = Path(__file__).resolve().parent
COMMANDS = ('work', 'push', 'ship', 'done')


def digest(content):
    return hashlib.sha256(content).hexdigest()


def read_json(path):
    value = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(value, dict):
        raise ValueError(str(path) + ' must contain a JSON object')
    return value


def config_groups(data):
    hooks = data.setdefault('hooks', {})
    if not isinstance(hooks, dict):
        raise ValueError('hooks must be an object')
    groups = hooks.setdefault('PreToolUse', [])
    if not isinstance(groups, list):
        raise ValueError('hooks.PreToolUse must be a list')
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get('hooks'), list):
            raise ValueError('Each PreToolUse group must have a hooks list')
        if any(not isinstance(h, dict) for h in group['hooks']):
            raise ValueError('Each hook handler must be an object')
    return groups


def encoded(value):
    return (json.dumps(value, indent=2) + '\n').encode()


def atomic(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, staging = tempfile.mkstemp(dir=path.parent, prefix='.worktree-guard-')
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(content)
        os.chmod(staging, mode)
        os.replace(staging, path)
    finally:
        if os.path.exists(staging):
            os.unlink(staging)


def safe_path(base, relative):
    path = base / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('Invalid manifest path: ' + relative)
    if not path.resolve().is_relative_to(base.resolve()):
        raise ValueError('Refusing a path outside install scope: ' + str(path))
    # Do not write through symlinked settings, skills or hook directories.
    if any(p.is_symlink() for p in [path] + list(path.parents) if p != base.parent):
        raise ValueError('Refusing symlinked install target: ' + str(path))
    return path


def strip_owned(data, entry):
    if not entry:
        return
    kept = []
    for group in config_groups(data):
        if group.get('matcher') != entry['matcher']:
            kept.append(group)
            continue
        handlers = [h for h in group['hooks'] if h != entry['hooks'][0]]
        if handlers:
            kept.append(dict(group, hooks=handlers))
    data['hooks']['PreToolUse'] = kept


def migrate_legacy(data, root, scope):
    """Recognize only exact old entrypoint argv, never substring matches."""
    names = ('codex-guard.py', 'claude-guard.py', 'worktree-guard.sh', 'ship-guard.sh')
    paths = {str(root / 'hooks' / name) for name in names}
    if scope == 'project' and root.name == '.claude':
        paths.update('$CLAUDE_PROJECT_DIR/.claude/hooks/' + name for name in names)
    if scope == 'user':
        paths.update('$HOME/' + root.name + '/hooks/' + name for name in names)
    def recognized(handler):
        if handler.get('type', 'command') != 'command':
            return False
        try:
            words = shlex.split(handler.get('command', ''))
        except (ValueError, TypeError):
            return False
        if len(words) == 1:
            return words[0] in paths
        return (len(words) == 2 and words[1] in paths and
                (Path(words[0]).name in ('python', 'python3', 'bash', 'sh') or
                 Path(words[0]).name.startswith('python3.')))
    kept, removed = [], []
    for group in config_groups(data):
        legacy = [h for h in group['hooks'] if recognized(h)]
        remaining = [h for h in group['hooks'] if not recognized(h)]
        if legacy:
            removed.append(dict(group, hooks=legacy))
        if remaining or not legacy:
            kept.append(dict(group, hooks=remaining))
    data['hooks']['PreToolUse'] = kept
    return removed


def restore_legacy(data, originals):
    groups = config_groups(data)
    for original in originals:
        metadata = {k: v for k, v in original.items() if k != 'hooks'}
        group = next((g for g in groups if {k: v for k, v in g.items() if k != 'hooks'} == metadata), None)
        if group is None:
            group = dict(metadata, hooks=[])
            groups.append(group)
        for handler in original['hooks']:
            if handler not in group['hooks']:
                group['hooks'].append(handler)


def prepare(opts, host, base):
    root = base / ('.claude' if host == 'claude' else '.codex')
    safe_path(base, str((root / 'worktree-guard-backups').relative_to(base)))
    manifest_path = root / 'worktree-guard-manifest.json'
    safe_path(base, str(manifest_path.relative_to(base)))
    manifest = read_json(manifest_path)
    if manifest and (manifest.get('version') != 1 or manifest.get('host') != host):
        raise ValueError('Unrecognized install manifest: ' + str(manifest_path))
    for relative, record in manifest.get('files', {}).items():
        safe_path(base, relative)
        if record.get('original'):
            original = safe_path(base, record['original'])
            if not original.is_file():
                raise ValueError('Original backup is missing: ' + str(original))
            if not original.is_relative_to(root / 'worktree-guard-backups'):
                raise ValueError('Backup path is outside the backup directory')
    config = root / ('settings.json' if host == 'claude' else 'hooks.json')
    safe_path(base, str(config.relative_to(base)))
    data = read_json(config)
    config_groups(data)
    helper_dir = root / 'hooks'
    helper_ref = shlex.quote(str(helper_dir))
    if opts.scope == 'project':
        # Resolve the current checkout first, then the registered primary checkout.
        # Git's NUL-delimited output preserves spaces and newlines in paths.
        resolver = ("import pathlib,subprocess; "
                    "run=lambda *a:subprocess.check_output(['git',*a]); "
                    "current=pathlib.Path(run('rev-parse','--show-toplevel').decode().rstrip('\\n')); "
                    "records=run('worktree','list','--porcelain','-z').split(b'\\0'); "
                    "primary=pathlib.Path(next(x[9:].decode() for x in records if x.startswith(b'worktree '))); "
                    "suffix=" + repr(root.name + '/hooks') + "; "
                    "candidates=[current/suffix,primary/suffix]; "
                    "print(next(p for p in candidates if (p/" + repr(host + '-guard.py') + ").is_file()))")
        helper_ref = '"$(python3 -c ' + shlex.quote(resolver) + ')"'
    entry = {'matcher': 'Edit|Write|NotebookEdit|Bash' if host == 'claude' else '^(apply_patch|Edit|Write|NotebookEdit|Bash)$',
             'hooks': [{'type': 'command', 'command': 'python3 ' + helper_ref + '/' + host + '-guard.py',
                        'timeout': 50, 'statusMessage': 'Checking worktree branch and merge safety'}]}
    planned = {}
    migrated = []
    if not opts.uninstall and not opts.check:
        for path in sorted((SOURCE / 'hook').iterdir()):
            if path.is_file() and (path.suffix in ('', '.py', '.sh')):
                planned[helper_dir / path.name] = path.read_bytes()
        if helper_dir / (host + '-guard.py') not in planned:
            raise ValueError('Source is incomplete: missing ' + host + '-guard.py')
        skill_root = base / ('.claude/skills' if host == 'claude' else '.agents/skills')
        for name in COMMANDS:
            source_dir = SOURCE / 'skills' / name
            if not (source_dir / 'SKILL.md').is_file():
                raise ValueError('Source is incomplete: missing skill ' + name)
            for path in sorted(source_dir.rglob('*')):
                if path.is_file() and '__pycache__' not in path.parts:
                    content = path.read_text().replace('{{WG_HELPERS}}', helper_ref).replace('{{WG_HOST}}', host)
                    planned[skill_root / name / path.relative_to(source_dir)] = content.encode()
            if host == 'claude':
                legacy = root / 'commands' / (name + '.md')
                if legacy.exists():
                    planned[legacy] = None
        for path, content in planned.items():
            relative = str(path.relative_to(base))
            safe_path(base, relative)
            old = manifest.get('files', {}).get(relative)
            if path.exists():
                current = path.read_bytes()
                owned = (old is not None and old.get('sha256') == digest(current) and
                         (old.get('mode') is None or old['mode'] == path.stat().st_mode & 0o777))
                if not owned and not opts.replace_commands:
                    raise ValueError('Existing or modified file needs --replace-commands: ' + str(path))
        strip_owned(data, manifest.get('hook'))
        migrated = migrate_legacy(data, root, opts.scope)
        config_groups(data).append(entry)
    return {'host': host, 'base': base, 'root': root, 'manifest_path': manifest_path,
            'manifest': manifest, 'config': config, 'data': data, 'entry': entry, 'planned': planned, 'migrated': migrated}


def check(state):
    manifest = state['manifest']
    issues = []
    if not manifest:
        issues.append('No installation manifest')
    for relative, record in manifest.get('files', {}).items():
        path = state['base'] / relative
        expected = record['sha256']
        if expected is None:
            if path.exists():
                issues.append('Recreated conflicting command: ' + relative)
        elif not path.is_file() or digest(path.read_bytes()) != expected:
            issues.append('Missing or modified file: ' + relative)
        elif record.get('mode') is not None and path.stat().st_mode & 0o777 != record['mode']:
            issues.append('Modified permissions: ' + relative)
    hook = manifest.get('hook')
    if not hook:
        issues.append('No owned configured hook')
    if hook and not any(g.get('matcher') == hook['matcher'] and hook['hooks'][0] in g['hooks']
                        for g in config_groups(state['data'])):
        issues.append('Configured hook is missing or modified')
    for issue in issues:
        print(state['host'] + ': ' + issue)
    if not issues:
        print(state['host'] + ': installed files intact and hook configured; host activation is not verified.')
    return not issues


def install(state):
    base, root, config = state['base'], state['root'], state['config']
    manifest = copy.deepcopy(state['manifest']) or {'version': 1, 'host': state['host'], 'files': {}}
    planned = state['planned']
    changed = {p: c for p, c in planned.items() if (p.exists() if c is None else
               not p.exists() or p.read_bytes() != c or
               p.stat().st_mode & 0o777 != (0o755 if p.parent == root / 'hooks' else 0o644))}
    # Identical bytes do not imply ownership: adoption must retain the user's original.
    adopted = [p for p in planned if str(p.relative_to(base)) not in manifest['files']]
    config_content = encoded(state['data'])
    config_changed = not config.exists() or config.read_bytes() != config_content
    if not changed and not adopted and not config_changed and manifest.get('hook') == state['entry']:
        print(state['host'] + ': already up to date (configured, host activation not verified).')
        return
    backup = root / 'worktree-guard-backups' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    safe_path(base, str(backup.relative_to(base)))
    backup.mkdir(parents=True)
    # Snapshot every overwritten file before the first write, including settings.
    snapshots = {}
    for path in dict.fromkeys(list(changed) + adopted + ([config] if config_changed else []) + [state['manifest_path']]):
        if path.exists():
            dest = backup / path.relative_to(base)
            atomic(dest, path.read_bytes(), path.stat().st_mode & 0o777)
            snapshots[str(path.relative_to(base))] = str(dest.relative_to(base))
    atomic(backup / 'manifest.json', encoded(snapshots))
    for path, content in planned.items():
        relative = str(path.relative_to(base))
        record = manifest['files'].get(relative, {'original': snapshots.get(relative),
                                               'original_mode': path.stat().st_mode & 0o777 if path.exists() else None})
        record['sha256'] = digest(content) if content is not None else None
        record['mode'] = 0o755 if path.parent == root / 'hooks' else 0o644
        manifest['files'][relative] = record
        if path in changed:
            if content is None:
                path.unlink()
            else:
                atomic(path, content, 0o755 if path.parent == root / 'hooks' else 0o644)
    if config_changed:
        atomic(config, config_content, config.stat().st_mode & 0o777 if config.exists() else 0o644)
    manifest['hook'] = state['entry']
    manifest.setdefault('migrated_hooks', []).extend(state['migrated'])
    atomic(state['manifest_path'], encoded(manifest))
    print(state['host'] + ': installed /work, /push, /ship, /done and configured guards.')
    print('Backup: ' + str(backup))
    print('Review native hook trust prompts and restart/reload the host. Activation is not verified.')


def uninstall(state):
    manifest = state['manifest']
    if not manifest:
        print(state['host'] + ': no owned installation to remove.')
        return
    remaining = {}
    for relative, record in manifest['files'].items():
        path = state['base'] / relative
        unchanged = (not path.exists()) if record['sha256'] is None else path.is_file() and digest(path.read_bytes()) == record['sha256']
        if unchanged and path.exists() and record.get('mode') is not None:
            unchanged = path.stat().st_mode & 0o777 == record['mode']
        if not unchanged:
            remaining[relative] = record
            print('Preserved missing/modified target: ' + relative)
            continue
        if record.get('original'):
            atomic(path, (state['base'] / record['original']).read_bytes(), record.get('original_mode') or 0o644)
        elif path.exists():
            path.unlink()
    old_data = copy.deepcopy(state['data'])
    strip_owned(state['data'], manifest.get('hook'))
    restore_legacy(state['data'], manifest.get('migrated_hooks', []))
    manifest.pop('migrated_hooks', None)
    # A deleted settings file is an external edit; leave it absent.
    if state['config'].exists() and state['data'] != old_data:
        atomic(state['config'], encoded(state['data']), state['config'].stat().st_mode & 0o777)
    if remaining:
        manifest['files'] = remaining
        manifest.pop('hook', None)
        atomic(state['manifest_path'], encoded(manifest))
    else:
        state['manifest_path'].unlink()
    print(state['host'] + ': removed unmodified owned files and hook; backups retained.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', choices=('claude', 'codex', 'both'), default='claude')
    parser.add_argument('--scope', choices=('user', 'project'), default='user')
    parser.add_argument('--home', type=Path, default=Path.home())
    parser.add_argument('--project', type=Path)
    parser.add_argument('--replace-commands', action='store_true', help='Back up and replace conflicting/modified installed files')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--check', action='store_true', help='Read-only check; does not prove host activation')
    modes.add_argument('--uninstall', action='store_true')
    opts = parser.parse_args(argv)
    if sys.version_info < (3, 9):
        raise RuntimeError('Python 3.9 or later is required')
    for binary in ('git', 'python3'):
        if not shutil.which(binary):
            raise RuntimeError('Required executable is unavailable: ' + binary)
    if opts.scope == 'project':
        if opts.project is None:
            parser.error('--scope project requires --project PATH')
        base = opts.project.expanduser().resolve()
        result = subprocess.run(['git', '-C', str(base), 'rev-parse', '--show-toplevel'], text=True, capture_output=True)
        if result.returncode or Path(result.stdout.strip()).resolve() != base:
            raise ValueError('--project must name the Git repository root')
    else:
        if opts.project:
            parser.error('--project requires --scope project')
        base = opts.home.expanduser().resolve()
    hosts = ('claude', 'codex') if opts.host == 'both' else (opts.host,)
    # Validate all hosts and conflicts before writing any install targets.
    states = [prepare(opts, host, base) for host in hosts]
    if opts.check:
        return 0 if all([check(state) for state in states]) else 1
    for state in states:
        (uninstall if opts.uninstall else install)(state)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, TypeError, KeyError) as exc:
        print('Install stopped: ' + str(exc), file=sys.stderr)
        sys.exit(1)
