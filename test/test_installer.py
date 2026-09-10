"""Isolated installer checks; these do not claim native host hook activation."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='wg-installer-')
        self.base = Path(self.tmp.name).resolve()
        self.home = self.base / "home with 'quotes'"
        self.source = self.base / 'source'
        self.source.mkdir()
        for name in ('install.py', 'install.sh', 'install-codex.py'):
            shutil.copy2(ROOT / name, self.source / name)
        (self.source / 'hook').mkdir()
        # Tiny executable fixture isolates installer behavior from core helper changes.
        for name in ('claude-guard.py', 'codex-guard.py', 'worktree-start', 'support.py'):
            (self.source / 'hook' / name).write_text('#!/usr/bin/env python3\nprint("fixture-runtime")\n')
        cache = self.source / 'hook/__pycache__'
        cache.mkdir()
        (cache / 'ignored.pyc').write_bytes(b'ignored')
        for name in ('work', 'push', 'ship', 'done'):
            folder = self.source / 'skills' / name
            folder.mkdir(parents=True)
            (folder / 'SKILL.md').write_text('{{WG_HELPERS}}/worktree-start\nhost={{WG_HOST}}\n')
            (folder / 'reference.md').write_text('Shared {{WG_HOST}} reference.\n')

    def tearDown(self):
        self.tmp.cleanup()

    def run_install(self, *args, expected=0, entry='install.py'):
        result = subprocess.run([sys.executable, str(self.source / entry), '--home', str(self.home), *args],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def config(self, host):
        return self.home / ('.claude/settings.json' if host == 'claude' else '.codex/hooks.json')

    def test_both_hosts_fresh_repeat_and_check(self):
        self.run_install('--host', 'both')
        for host, skills in [('claude', '.claude/skills'), ('codex', '.agents/skills')]:
            config = json.loads(self.config(host).read_text())
            entry = config['hooks']['PreToolUse'][0]
            self.assertIn('Bash', entry['matcher'])
            command = entry['hooks'][0]['command']
            result = subprocess.run(command, shell=True, text=True, capture_output=True)
            self.assertEqual(result.stdout.strip(), 'fixture-runtime', result.stderr)
            self.assertFalse((self.home / ('.' + host) / 'hooks/__pycache__').exists())
            for name in ('work', 'push', 'ship', 'done'):
                body = (self.home / skills / name / 'SKILL.md').read_text()
                self.assertNotIn('{{WG_', body)
                self.assertIn('host=' + host, body)
                self.assertEqual(shlex.split(body.splitlines()[0])[0], str(self.home / ('.' + host) / 'hooks/worktree-start'))
                self.assertTrue((self.home / skills / name / 'reference.md').exists())
        before = {p: p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        self.run_install('--host', 'both')
        self.run_install('--host', 'both', '--check')
        self.assertEqual(before, {p: p.read_bytes() for p in self.home.rglob('*') if p.is_file()})

    def test_config_and_mixed_handlers_preserved_on_uninstall(self):
        path = self.config('codex')
        path.parent.mkdir(parents=True)
        custom = {'custom': 42, 'hooks': {'Stop': [{'hooks': [{'command': 'finish'}]}],
                  'PreToolUse': [{'matcher': 'Bash', 'hooks': [{'command': 'unrelated'}]}]}}
        path.write_text(json.dumps(custom))
        self.run_install('--host', 'codex')
        data = json.loads(path.read_text())
        data['hooks']['PreToolUse'][-1]['hooks'].append({'type': 'command', 'command': 'keep-in-same-group'})
        data['later-user-edit'] = True
        path.write_text(json.dumps(data))
        self.run_install('--host', 'codex', '--uninstall')
        remaining = json.loads(path.read_text())
        self.assertEqual(remaining['custom'], 42)
        self.assertTrue(remaining['later-user-edit'])
        self.assertEqual(remaining['hooks']['Stop'], custom['hooks']['Stop'])
        commands = [h['command'] for g in remaining['hooks']['PreToolUse'] for h in g['hooks']]
        self.assertEqual(commands, ['unrelated', 'keep-in-same-group'])
        self.assertFalse((self.home / '.agents/skills/work/SKILL.md').exists())

    def test_legacy_native_handlers_migrate_and_restore(self):
        for host in ('claude', 'codex'):
            with self.subTest(host=host):
                path = self.config(host)
                path.parent.mkdir(parents=True)
                legacy = {'type': 'command', 'command': shlex.quote(str(path.parent / 'hooks/worktree-guard.sh'))}
                unrelated = {'type': 'command', 'command': 'echo worktree-guard.sh'}
                original = {'matcher': 'Edit|Write', 'hooks': [legacy, unrelated]}
                path.write_text(json.dumps({'hooks': {'PreToolUse': [original]}}))
                self.run_install('--host', host)
                self.run_install('--host', host)
                handlers = [h for g in json.loads(path.read_text())['hooks']['PreToolUse'] for h in g['hooks']]
                self.assertNotIn(legacy, handlers)
                self.assertIn(unrelated, handlers)
                self.assertEqual(sum(host + '-guard.py' in h['command'] for h in handlers), 1)
                self.run_install('--host', host, '--uninstall')
                handlers = [h for g in json.loads(path.read_text())['hooks']['PreToolUse'] for h in g['hooks']]
                self.assertIn(legacy, handlers)
                self.assertIn(unrelated, handlers)

    def test_check_ignores_source_runtime(self):
        self.run_install('--host', 'codex')
        shutil.rmtree(self.source / 'hook')
        shutil.rmtree(self.source / 'skills')
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()}
        self.run_install('--host', 'codex', '--check')
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()})

    def test_collision_preflight_and_replacement_restoration(self):
        target = self.home / '.agents/skills/work/SKILL.md'
        target.parent.mkdir(parents=True)
        target.write_text('original user command')
        self.run_install('--host', 'both', expected=1)
        self.assertFalse((self.home / '.claude').exists())
        self.run_install('--host', 'both', '--replace-commands')
        self.run_install('--host', 'both')
        self.run_install('--host', 'both', '--uninstall')
        self.assertEqual(target.read_text(), 'original user command')

    def test_identical_preexisting_command_is_restored_on_uninstall(self):
        target = self.home / '.agents/skills/work/SKILL.md'
        target.parent.mkdir(parents=True)
        original = (self.source / 'skills/work/SKILL.md').read_text().replace(
            '{{WG_HELPERS}}', shlex.quote(str(self.home / '.codex/hooks'))).replace('{{WG_HOST}}', 'codex')
        target.write_text(original)
        target.chmod(0o644)
        self.run_install('--host', 'codex', '--replace-commands')
        manifest = json.loads((self.home / '.codex/worktree-guard-manifest.json').read_text())
        self.assertIsNotNone(manifest['files']['.agents/skills/work/SKILL.md']['original'])
        self.run_install('--host', 'codex')
        self.run_install('--host', 'codex', '--uninstall')
        self.assertEqual(target.read_text(), original)
        self.assertEqual(target.stat().st_mode & 0o777, 0o644)

    def test_actual_source_skills_and_references_install(self):
        args = [sys.executable, str(ROOT / 'install.py'), '--home', str(self.home), '--host', 'both']
        for extra in ([], ['--check']):
            result = subprocess.run(args + extra, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for host, destination in [('claude', '.claude/skills'), ('codex', '.agents/skills')]:
            for command in ('work', 'push', 'ship', 'done'):
                for source in (ROOT / 'skills' / command).rglob('*'):
                    if source.is_file() and '__pycache__' not in source.parts:
                        installed = self.home / destination / command / source.relative_to(ROOT / 'skills' / command)
                        expected = source.read_text().replace('{{WG_HELPERS}}', shlex.quote(str(self.home / ('.' + host) / 'hooks'))).replace('{{WG_HOST}}', host)
                        self.assertEqual(installed.read_text(), expected)
        result = subprocess.run(args + ['--uninstall'], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_legacy_claude_command_restored(self):
        target = self.home / '.claude/commands/work.md'
        target.parent.mkdir(parents=True)
        target.write_text('legacy command')
        self.run_install(expected=1)
        self.run_install('--replace-commands')
        self.assertFalse(target.exists())
        self.run_install('--uninstall')
        self.assertEqual(target.read_text(), 'legacy command')

    def test_modified_owned_files_preserved_and_reported(self):
        self.run_install('--host', 'codex')
        target = self.home / '.agents/skills/work/SKILL.md'
        target.write_text('user modification')
        self.run_install('--host', 'codex', expected=1)
        self.run_install('--host', 'codex', '--check', expected=1)
        self.run_install('--host', 'codex', '--uninstall')
        self.assertEqual(target.read_text(), 'user modification')
        self.assertTrue((self.home / '.codex/worktree-guard-manifest.json').exists())

    def test_upgrade_is_owned_and_snapshots_each_change(self):
        self.run_install('--host', 'codex')
        target = self.home / '.codex/hooks/support.py'
        old = target.read_bytes()
        (self.source / 'hook/support.py').write_text('# changed version\n')
        self.run_install('--host', 'codex')
        self.assertEqual(target.read_text(), '# changed version\n')
        backups = list((self.home / '.codex/worktree-guard-backups').glob('*/.codex/hooks/support.py'))
        self.assertTrue(any(p.read_bytes() == old for p in backups))

    def test_malformed_settings_no_partial_install(self):
        for invalid in ('{broken', '[]', '{"hooks": []}', '{"hooks":{"PreToolUse":{}}}'):
            with self.subTest(invalid=invalid):
                path = self.config('codex')
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(invalid)
                self.run_install('--host', 'both', expected=1)
                self.assertEqual(path.read_text(), invalid)
                self.assertFalse((self.home / '.claude').exists())

    def test_check_missing_is_readonly(self):
        self.run_install('--host', 'both', '--check', expected=1)
        self.assertFalse(self.home.exists())

    def test_compatibility_entrypoint_defaults_codex(self):
        self.run_install(entry='install-codex.py')
        self.assertTrue(self.config('codex').exists())
        self.assertFalse(self.config('claude').exists())

    def test_project_install_from_linked_checkout_before_commit(self):
        project = self.base / 'primary project'
        project.mkdir()
        def git(*args):
            return subprocess.run(['git', '-C', str(project), *args], check=True, capture_output=True)
        git('init', '-q')
        git('-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '--allow-empty', '-qm', 'init')
        linked = self.base / 'linked tree'
        git('worktree', 'add', '--detach', str(linked))
        self.run_install('--host', 'both', '--scope', 'project', '--project', str(project))
        self.assertFalse(self.home.exists())
        for host, filename in [('claude', 'settings.json'), ('codex', 'hooks.json')]:
            config = json.loads((project / ('.' + host) / filename).read_text())
            command = config['hooks']['PreToolUse'][0]['hooks'][0]['command']
            self.assertNotIn(str(project), command)
            result = subprocess.run(command, shell=True, cwd=linked, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'fixture-runtime')
        self.run_install('--host', 'both', '--scope', 'project', '--project', str(project), '--check')

    def test_config_permissions_preserved_and_helper_mode_checked(self):
        path = self.config('codex')
        path.parent.mkdir(parents=True)
        path.write_text('{}')
        path.chmod(0o600)
        self.run_install('--host', 'codex')
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        helper = self.home / '.codex/hooks/worktree-start'
        helper.chmod(0o644)
        self.run_install('--host', 'codex', '--check', expected=1)
        self.run_install('--host', 'codex', '--uninstall')
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_symlink_target_refused(self):
        outside = self.base / 'external'
        outside.mkdir()
        self.home.mkdir()
        (self.home / '.codex').symlink_to(outside)
        self.run_install('--host', 'codex', expected=1)
        self.assertEqual(list(outside.iterdir()), [])

    def test_backup_directory_symlink_refused_before_writes(self):
        outside = self.base / 'external-backups'
        outside.mkdir()
        sentinel = outside / 'sentinel'
        sentinel.write_text('keep me')
        root = self.home / '.codex'
        root.mkdir(parents=True)
        (root / 'worktree-guard-backups').symlink_to(outside)
        self.run_install('--host', 'both', expected=1)
        self.assertEqual(list(outside.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_text(), 'keep me')
        self.assertFalse((self.home / '.claude').exists())
        self.assertFalse((root / 'hooks').exists())

    def test_uninstall_missing_config_with_migrated_hooks(self):
        path = self.config('codex')
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'hooks': {'PreToolUse': [{'matcher': 'Bash', 'hooks': [{
            'type': 'command', 'command': shlex.quote(str(path.parent / 'hooks/worktree-guard.sh'))}]}]}}))
        self.run_install('--host', 'codex')
        path.unlink()
        self.run_install('--host', 'codex', '--uninstall')
        self.assertFalse(path.exists())
        self.assertFalse((self.home / '.codex/hooks/codex-guard.py').exists())
        self.assertFalse((self.home / '.codex/worktree-guard-manifest.json').exists())

    def test_modified_hook_refuses_uninstall_before_changing_either_host(self):
        self.run_install('--host', 'both')
        path = self.config('codex')
        original = path.read_text()
        for change in ('timeout', 'matcher', 'group_metadata', 'event', 'append_arguments', 'prepend_wrapper'):
            with self.subTest(change=change):
                data = json.loads(original)
                group = data['hooks']['PreToolUse'][0]
                group['hooks'].append({'type': 'command', 'command': 'keep-unrelated-handler'})
                if change == 'timeout':
                    group['hooks'][0]['timeout'] = 60
                elif change == 'matcher':
                    group['matcher'] = 'Bash'
                elif change == 'group_metadata':
                    group['customMetadata'] = 'user edit'
                elif change == 'append_arguments':
                    group['hooks'][0]['command'] += ' --custom-option'
                elif change == 'prepend_wrapper':
                    group['hooks'][0]['command'] = 'env MY_SETTING=1 ' + group['hooks'][0]['command']
                else:
                    data['hooks']['PostToolUse'] = data['hooks'].pop('PreToolUse')
                path.write_text(json.dumps(data))
                before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()}
                result = self.run_install('--host', 'both', '--uninstall', expected=1)
                self.assertIn('guard hook was modified', result.stderr)
                after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob('*') if p.is_file()}
                self.assertEqual(before, after)

    def test_missing_original_backup_stops_uninstall_before_removal(self):
        target = self.home / '.agents/skills/work/SKILL.md'
        target.parent.mkdir(parents=True)
        target.write_text('previous command')
        self.run_install('--host', 'codex', '--replace-commands')
        manifest = json.loads((self.home / '.codex/worktree-guard-manifest.json').read_text())
        (self.home / manifest['files']['.agents/skills/work/SKILL.md']['original']).unlink()
        helper = self.home / '.codex/hooks/codex-guard.py'
        content = helper.read_bytes()
        self.run_install('--host', 'codex', '--uninstall', expected=1)
        self.assertEqual(helper.read_bytes(), content)
        self.assertTrue(self.config('codex').exists())

    def test_shell_standalone_download_fails_helpfully(self):
        result = subprocess.run(['bash'], input=(self.source / 'install.sh').read_text(), text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Please clone', result.stderr)


if __name__ == '__main__':
    unittest.main()
