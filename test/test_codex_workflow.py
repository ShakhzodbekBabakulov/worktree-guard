import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / 'hook'


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='guard tests ')
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name).resolve()
        self.main = self.dir / 'main repo'
        self.remote = self.dir / 'remote.git'
        self.bin = self.dir / 'bin'
        self.bin.mkdir()
        self.fixture = self.dir / 'github.json'
        self.fixture.write_text('{}')
        gh = self.bin / 'gh'
        gh.write_text('''#!/usr/bin/env python3
import json, os, sys
d = json.load(open(os.environ['GH_FIXTURE']))
a = sys.argv[1:]
key = ' '.join(a[:2])
if key == 'repo view': value = {'nameWithOwner': 'owner/repo'}
elif key == 'pr view': value = d.get('views', {}).get(a[2], d.get('view'))
elif key == 'pr list': value = d.get('list', [])
elif a and a[0] == 'api': value = d.get(a[1])
else: value = None
if value is None: sys.exit('GitHub unavailable or unknown request: ' + repr(a))
print(json.dumps(value))
''')
        gh.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        GH_FIXTURE=str(self.fixture), GIT_CONFIG_NOSYSTEM='1',
                        GIT_CONFIG_GLOBAL='/dev/null', GIT_TERMINAL_PROMPT='0')
        self.run_cmd(['git', 'init', '--bare', '-b', 'main', str(self.remote)], self.dir)
        self.run_cmd(['git', 'init', '-b', 'main', str(self.main)], self.dir)
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Test')
        (self.main / 'app.py').write_text('base\n')
        self.git('add', '.')
        self.git('commit', '-m', 'base')
        self.git('remote', 'add', 'origin', str(self.remote))
        self.git('push', '-u', 'origin', 'main')
        self.git('remote', 'set-head', 'origin', '-a')

    def run_cmd(self, args, cwd=None, check=True, payload=None):
        p = subprocess.run(args, cwd=cwd or self.main, env=self.env, text=True,
                           input=payload, capture_output=True, timeout=30)
        if check:
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p

    def git(self, *args, cwd=None, check=True):
        return self.run_cmd(['git', *args], cwd, check).stdout.strip()

    def feature(self, name='feature/topic'):
        self.branch = name
        self.tree = self.dir / 'feature tree'
        self.git('worktree', 'add', '-b', name, str(self.tree))
        (self.tree / 'app.py').write_text('feature\n')
        self.git('add', '.', cwd=self.tree)
        self.git('commit', '-m', 'feature', cwd=self.tree)
        self.tip = self.git('rev-parse', 'HEAD', cwd=self.tree)
        self.git('push', '-u', 'origin', name, cwd=self.tree)

    def merge(self, squash=False):
        self.git('merge', '--squash' if squash else '--ff-only', self.branch)
        if squash:
            self.git('commit', '-m', 'squashed feature')
        self.git('push', 'origin', 'main')
        self.fixture.write_text(json.dumps({'view': {
            'state': 'MERGED', 'headRefOid': self.tip, 'headRefName': self.branch,
            'baseRefName': 'main', 'number': 12, 'mergeCommit': {'oid': self.git('rev-parse', 'HEAD')},
            'isCrossRepository': False, 'url': 'https://github.com/owner/repo/pull/12'}}))

    def cleanup(self, *args, cwd=None):
        self.assertTrue((HOOK / 'worktree-cleanup').exists(), 'cleanup helper must be installed from source')
        return self.run_cmd(['python3', str(HOOK / 'worktree-cleanup'), *args], cwd, False)

    def assert_preserved(self):
        self.assertTrue(self.tree.exists())
        self.assertEqual(self.git('rev-parse', self.branch), self.git('rev-parse', 'HEAD', cwd=self.tree))
        self.assertTrue(self.git('ls-remote', '--heads', 'origin', self.branch))

    def test_cleanup_removes_merged_worktree_and_both_branches(self):
        self.feature(); self.merge()
        p = self.cleanup('--worktree', str(self.tree))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse(self.tree.exists())
        self.assertEqual(self.git('branch', '--list', self.branch), '')
        self.assertEqual(self.git('ls-remote', '--heads', 'origin', self.branch), '')
        self.assertTrue((self.main / 'app.py').exists())

    def test_cleanup_supports_squash_merge_exact_tip(self):
        self.feature(); self.merge(squash=True)
        p = self.cleanup('--worktree', str(self.tree))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse(self.tree.exists())

    def test_cleanup_preserves_commits_added_after_squash_merge(self):
        self.feature(); self.merge(squash=True)
        (self.tree / 'extra.py').write_text('new work')
        self.git('add', '.', cwd=self.tree); self.git('commit', '-m', 'later', cwd=self.tree)
        p = self.cleanup('--worktree', str(self.tree))
        self.assertNotEqual(p.returncode, 0)
        self.assert_preserved()

    def test_cleanup_dry_run_has_no_ref_or_worktree_changes(self):
        self.feature(); self.merge()
        before = self.git('show-ref')
        p = self.cleanup('--worktree', str(self.tree), '--dry-run')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(before, self.git('show-ref')); self.assert_preserved()

    def test_cleanup_preserves_unsaved_untracked_and_ignored_files(self):
        self.feature(); self.merge()
        for name in ['app.py', 'notes.txt', 'private.env']:
            with self.subTest(name=name):
                if name == 'private.env':
                    self.git('config', 'core.excludesFile', str(self.dir / 'ignore'))
                    (self.dir / 'ignore').write_text('private.env\n')
                path = self.tree / name
                previous = path.read_bytes() if path.exists() else None
                path.write_text('must survive')
                self.assertNotEqual(self.cleanup('--worktree', str(self.tree)).returncode, 0)
                self.assertEqual(path.read_text(), 'must survive'); self.assert_preserved()
                if previous is None: path.unlink()
                else: path.write_bytes(previous)

    def test_cleanup_refuses_main_and_locked_worktree(self):
        self.assertNotEqual(self.cleanup().returncode, 0)
        self.feature(); self.merge(); self.git('worktree', 'lock', str(self.tree))
        self.assertNotEqual(self.cleanup('--worktree', str(self.tree)).returncode, 0)
        self.assert_preserved()

    def test_cleanup_leftover_branch_without_worktree(self):
        self.feature(); self.merge(); self.git('worktree', 'remove', str(self.tree))
        p = self.cleanup('--branch', self.branch)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.git('branch', '--list', self.branch), '')

    def test_cleanup_in_place_feature_keeps_primary_folder(self):
        self.feature(); self.merge(); self.git('worktree', 'remove', str(self.tree))
        self.git('switch', self.branch)
        p = self.cleanup()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(self.main.exists())
        self.assertEqual(self.git('branch', '--show-current'), 'main')

    def guard(self, patch, cwd=None):
        script = HOOK / 'codex-guard.py'
        # Before the repair, exercise the installed guard to reproduce its native-input bug.
        command = ['python3', str(script)] if script.exists() else ['bash', str(HOOK / 'worktree-guard.sh')]
        payload = {'tool_name': 'apply_patch', 'cwd': str(cwd or self.main), 'tool_input': {'command': patch}}
        return self.run_cmd(command, self.dir, False, json.dumps(payload))

    def test_native_patch_blocks_main_and_allows_feature(self):
        patch = '*** Begin Patch\n*** Add File: sub/app.py\n+pass\n*** End Patch'
        self.assertEqual(self.guard(patch).returncode, 2)
        self.feature()
        self.assertEqual(self.guard(patch, self.tree).returncode, 0)

    def test_native_patch_checks_move_destination_and_every_file(self):
        self.feature()
        patch = ('*** Begin Patch\n*** Add File: README.md\n+safe\n'
                 '*** Update File: app.py\n*** Move to: ' + str(self.main / 'moved.py') +
                 '\n@@\n-feature\n+changed\n*** End Patch')
        self.assertEqual(self.guard(patch, self.tree).returncode, 2)

    def test_native_patch_allows_docs_and_outside_repo(self):
        self.assertEqual(self.guard('*** Begin Patch\n*** Add File: README.md\n+x\n*** End Patch').returncode, 0)
        self.assertEqual(self.guard('*** Begin Patch\n*** Add File: loose.py\n+x\n*** End Patch', self.dir).returncode, 0)

    def test_start_creates_feature_from_remote_base_without_switching_main(self):
        script = HOOK / 'worktree-start'
        self.assertTrue(script.exists(), 'start helper is missing')
        dest = self.dir / 'new work'
        self.git('symbolic-ref', '--delete', 'refs/remotes/origin/HEAD')
        p = self.run_cmd(['python3', str(script), 'feature/new', '--path', str(dest)], check=False)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.git('branch', '--show-current', cwd=dest), 'feature/new')
        self.assertEqual(self.git('branch', '--show-current'), 'main')
        self.assertEqual(self.git('rev-parse', 'HEAD', cwd=dest), self.git('rev-parse', 'origin/main'))
        self.assertEqual(self.guard('*** Begin Patch\n*** Add File: new.py\n+pass\n*** End Patch', dest).returncode, 0)

    def report(self, *args):
        script = HOOK / 'codex-session-conflict-check'
        self.assertTrue(script.exists(), 'conflict checker is missing')
        return self.run_cmd(['python3', str(script), *args], check=False)

    def prs(self, own_number=12, other_number=7):
        own = {'number': own_number, 'headRefName': 'feature/topic', 'baseRefName': 'main',
               'state': 'OPEN', 'changedFiles': 1, 'headRefOid': self.tip, 'isCrossRepository': False,
               'url': 'https://github.com/owner/repo/pull/' + str(own_number)}
        other = dict(own, number=other_number, headRefName='feature/other')
        self.fixture.write_text(json.dumps({'view': own, 'list': [own, other],
            'repos/owner/repo/pulls/%s/files' % own_number: [[{'filename': 'app.py'}]],
            'repos/owner/repo/pulls/%s/files' % other_number: [[{'filename': 'app.py'}]]}))

    def test_conflicts_explicit_pr_from_main_and_older_first(self):
        self.feature(); self.prs()
        p = self.report('--pr', '12')
        self.assertEqual(p.returncode, 0, p.stderr)
        d = json.loads(p.stdout)
        self.assertTrue(d['gh_ok'])
        self.assertEqual([c['number'] for c in d['conflicts'] if c['blocking']], [7])
        self.prs(own_number=7, other_number=12)
        d = json.loads(self.report('--pr', '7').stdout)
        self.assertFalse(any(c['blocking'] for c in d['conflicts']))

    def test_conflicts_partial_api_failure_is_not_all_clear(self):
        self.feature(); self.prs()
        d = json.loads(self.fixture.read_text()); del d['repos/owner/repo/pulls/7/files']
        self.fixture.write_text(json.dumps(d))
        report = json.loads(self.report('--pr', '12').stdout)
        self.assertFalse(report['gh_ok']); self.assertTrue(report['warnings'])

    def shell_guard(self, command):
        self.assertTrue((HOOK / 'codex-guard.py').exists())
        return self.run_cmd(['python3', str(HOOK / 'codex-guard.py')], self.dir, False,
                            json.dumps({'tool_name': 'Bash', 'cwd': str(self.main),
                                        'tool_input': {'command': command}}))

    def test_merge_guard_blocks_overlap_and_unknown_but_allows_reads(self):
        self.feature(); self.prs()
        self.assertEqual(self.shell_guard('gh pr merge 12 --squash').returncode, 2)
        self.prs(own_number=7, other_number=12)
        self.assertEqual(self.shell_guard('gh pr merge 7 --squash').returncode, 0)
        self.fixture.write_text('{}')
        self.assertEqual(self.shell_guard('gh pr merge 12 --squash').returncode, 2)
        self.assertEqual(self.shell_guard('git status --short').returncode, 0)

    def test_merge_guard_rejects_ambiguous_repository_switches(self):
        self.feature(); self.prs(own_number=7, other_number=12)
        for cmd in ['cd elsewhere && gh pr merge 7', 'gh pr merge 7 --repo other/repo']:
            self.assertEqual(self.shell_guard(cmd).returncode, 2)

    def test_cleanup_follows_differently_named_upstream(self):
        self.feature(); self.merge()
        self.git('branch', '-m', self.branch, 'feature/local-name', cwd=self.tree)
        p = self.cleanup('--worktree', str(self.tree))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.git('ls-remote', '--heads', 'origin', 'feature/topic'), '')

    def test_cleanup_preserves_new_remote_commits_and_dirty_main(self):
        self.feature(); self.merge()
        (self.main / 'app.py').write_text('unsaved base work')
        self.assertNotEqual(self.cleanup('--worktree', str(self.tree)).returncode, 0)
        self.assert_preserved()
        self.git('restore', 'app.py')
        self.git('push', 'origin', 'main:refs/heads/safe-copy')
        (self.main / 'extra.py').write_text('later remote commit')
        self.git('add', '.'); self.git('commit', '-m', 'new')
        self.git('push', 'origin', 'main:refs/heads/' + self.branch)
        self.assertNotEqual(self.cleanup('--worktree', str(self.tree)).returncode, 0)
        self.assertTrue(self.tree.exists())

    def test_install_preserves_other_hooks_and_is_repeatable(self):
        installer = ROOT / 'install-codex.py'
        self.assertTrue(installer.exists(), 'Codex installer is missing')
        home = self.dir / 'home'
        codex = home / '.codex'; codex.mkdir(parents=True)
        unrelated = {'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': 'keep-this-hook'}]}
        old_guard = {'matcher': 'Edit|Write', 'hooks': [
            {'type': 'command', 'command': str(codex / 'hooks/worktree-guard.sh')},
            {'type': 'command', 'command': 'keep-this-too'}]}
        (codex / 'hooks.json').write_text(json.dumps({'custom': 'preserve', 'hooks': {
            'PreToolUse': [unrelated, old_guard], 'Stop': [{'hooks': [{'type': 'command', 'command': 'finish'}]}]}}))
        original = (codex / 'hooks.json').read_bytes()
        p = self.run_cmd(['python3', str(installer), '--home', str(home)])
        installed = (codex / 'hooks.json').read_bytes()
        self.run_cmd(['python3', str(installer), '--home', str(home)])
        self.assertEqual(installed, (codex / 'hooks.json').read_bytes())
        data = json.loads(installed)
        self.assertIn(unrelated, data['hooks']['PreToolUse'])
        self.assertEqual(data['custom'], 'preserve'); self.assertIn('Stop', data['hooks'])
        handlers = [h for group in data['hooks']['PreToolUse'] for h in group['hooks']]
        self.assertTrue(any(h['command'] == 'keep-this-too' for h in handlers))
        self.assertEqual(sum('codex-guard.py' in h['command'] for h in handlers), 1)
        backups = list((codex / 'worktree-guard-backups').glob('*/.codex/hooks.json'))
        self.assertTrue(any(p.read_bytes() == original for p in backups))
        for name in ['work', 'push', 'ship', 'done']:
            self.assertTrue((home / '.agents/skills' / name / 'SKILL.md').exists())
        for name in ['worktree-start', 'worktree-cleanup', 'codex-session-conflict-check']:
            self.run_cmd([str(codex / 'hooks' / name), '--help'])

    def test_detached_linked_worktree_allowed_but_primary_detached_denied(self):
        patch = '*** Begin Patch\n*** Add File: app.py\n+x\n*** End Patch'
        tree = self.dir / 'native worktree'
        self.git('worktree', 'add', '--detach', str(tree), 'HEAD')
        self.assertEqual(self.guard(patch, tree).returncode, 0)
        self.git('checkout', '--detach')
        self.assertEqual(self.guard(patch).returncode, 2)

    def test_claude_adapter_uses_event_directory_and_same_rules(self):
        script = HOOK / 'claude-guard.py'
        payload = {'tool_name': 'Write', 'cwd': str(self.main),
                   'tool_input': {'file_path': 'nested/new.py', 'content': 'pass'}}
        p = self.run_cmd(['python3', str(script)], self.dir, False, json.dumps(payload))
        self.assertEqual(p.returncode, 2, p.stderr)
        self.feature()
        payload['cwd'] = str(self.tree)
        p = self.run_cmd(['python3', str(script)], self.dir, False, json.dumps(payload))
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_start_resumes_dirty_worktree_without_creating_duplicate(self):
        self.feature()
        (self.tree / 'notes.txt').write_text('preserve')
        before = self.git('worktree', 'list', '--porcelain')
        p = self.run_cmd(['python3', str(HOOK / 'worktree-start'), self.branch], check=False)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(str(self.tree), p.stdout)
        self.assertEqual(before, self.git('worktree', 'list', '--porcelain'))
        self.assertEqual((self.tree / 'notes.txt').read_text(), 'preserve')

    def test_start_uses_existing_local_and_remote_branch(self):
        self.feature()
        tip = self.tip
        self.git('worktree', 'remove', str(self.tree))
        dest = self.dir / 'resumed'
        p = self.run_cmd(['python3', str(HOOK / 'worktree-start'), self.branch, '--path', str(dest)], check=False)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.git('rev-parse', 'HEAD', cwd=dest), tip)
        self.git('worktree', 'remove', str(dest))
        self.git('branch', '-D', self.branch)
        p = self.run_cmd(['python3', str(HOOK / 'worktree-start'), self.branch, '--path', str(dest)], check=False)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.git('rev-parse', 'HEAD', cwd=dest), tip)

    def test_submitted_worktree_unsaved_overlap_is_not_hidden(self):
        self.feature(); self.prs(own_number=7, other_number=12)
        other = self.dir / 'other tree'
        self.git('worktree', 'add', '-b', 'feature/other', str(other))
        (other / 'app.py').write_text('unsubmitted later edit')
        d = json.loads(self.report('--pr', '7').stdout)
        self.assertTrue(d['gh_ok'], d)
        self.assertTrue(any(c['kind'] == 'worktree' and c['blocking'] for c in d['conflicts']), d)

    def test_status_detects_missing_review_dirty_and_unpushed_work(self):
        self.feature()
        script = HOOK / 'workflow-status'
        p = self.run_cmd(['python3', str(script)], self.tree, False)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(json.loads(p.stdout)['needs_push'])
        self.prs()
        p = self.run_cmd(['python3', str(script)], self.tree)
        self.assertFalse(json.loads(p.stdout)['needs_push'])
        (self.tree / 'new.py').write_text('new')
        self.assertTrue(json.loads(self.run_cmd(['python3', str(script)], self.tree).stdout)['needs_push'])
        self.git('add', '.', cwd=self.tree); self.git('commit', '-m', 'new', cwd=self.tree)
        self.assertTrue(json.loads(self.run_cmd(['python3', str(script)], self.tree).stdout)['needs_push'])

    def test_prepare_names_detached_worktree_without_losing_changes(self):
        tree = self.dir / 'native'
        self.git('worktree', 'add', '--detach', str(tree), 'HEAD')
        (tree / 'app.py').write_text('native changes')
        p = self.run_cmd(['python3', str(HOOK / 'worktree-start'), 'feature/native', '--adopt'], tree, False)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.git('branch', '--show-current', cwd=tree), 'feature/native')
        self.assertEqual((tree / 'app.py').read_text(), 'native changes')
        self.assertEqual(self.git('branch', '--show-current'), 'main')

    def test_merge_examples_in_read_or_documentation_commands_are_allowed(self):
        for command in ["echo gh pr merge 12", "rg 'gh pr merge' README.md",
                        "python3 - <<'PY'\ntext = '''\ngh pr merge <number> --squash\n'''\nprint(text)\nPY"]:
            self.assertEqual(self.shell_guard(command).returncode, 0, command)

    def test_merge_guard_refuses_changed_exact_head(self):
        self.feature(); self.prs(own_number=7, other_number=12)
        self.assertEqual(self.shell_guard('gh pr merge 7 --match-head-commit ' + '0' * 40).returncode, 2)
        self.assertEqual(self.shell_guard('gh pr merge 7 --match-head-commit ' + self.tip).returncode, 0)

    def test_closed_and_merged_reviews_never_trigger_automatic_push(self):
        self.feature(); self.prs()
        for state in ('CLOSED', 'MERGED'):
            data = json.loads(self.fixture.read_text())
            data['list'][0]['state'] = state
            self.fixture.write_text(json.dumps(data))
            result = json.loads(self.run_cmd(['python3', str(HOOK / 'workflow-status')], self.tree).stdout)
            self.assertEqual(result['state'], state)
            self.assertFalse(result['needs_push'])



    def test_merge_option_order_checks_actual_target(self):
        self.feature(); self.prs(own_number=7, other_number=12)
        self.git('switch', '-c', 'invoker')
        d = json.loads(self.fixture.read_text())
        d['views'] = {'7': d['list'][0], '12': d['list'][1]}
        self.fixture.write_text(json.dumps(d))
        for cmd in ['gh pr merge --squash 12',
                    'gh pr merge --body "release notes" --squash 12',
                    'gh pr merge --subject=release 12 --squash']:
            self.assertEqual(self.shell_guard(cmd).returncode, 2, cmd)
        self.assertEqual(self.shell_guard('gh pr merge --squash 7').returncode, 0)

    def test_merge_from_dirty_base_detects_invoking_workspace(self):
        self.feature(); self.prs(own_number=7, other_number=12)
        (self.main / 'app.py').write_text('unfinished base work')
        d = json.loads(self.report('--pr', '7').stdout)
        self.assertTrue(d['gh_ok'], d)
        self.assertTrue(any(c.get('path') == str(self.main) and c['blocking'] for c in d['conflicts']), d)
        self.assertEqual(self.shell_guard('gh pr merge 7 --squash').returncode, 2)

    def test_merge_newline_compound_is_refused_and_help_needs_no_github(self):
        self.feature(); self.prs()
        for separator in ('\n', '\n\n', ';\n', ' &&\n'):
            self.assertEqual(self.shell_guard('git status' + separator + 'gh pr merge 12 --squash').returncode, 2)
        self.prs(own_number=7, other_number=12)
        self.assertEqual(self.shell_guard('\ngh pr merge 7 --squash\n').returncode, 0)
        self.fixture.write_text('{}')
        self.assertEqual(self.shell_guard('gh pr merge --help').returncode, 0)
        self.assertEqual(self.shell_guard('gh pr merge -h').returncode, 0)

    def test_unknown_remote_default_cannot_allow_source_edits(self):
        self.git('branch', '-m', 'main', 'develop')
        self.git('push', 'origin', 'develop')
        self.git('symbolic-ref', 'HEAD', 'refs/heads/develop', cwd=self.remote)
        self.git('symbolic-ref', '--delete', 'refs/remotes/origin/HEAD')
        patch = '*** Begin Patch\n*** Add File: app.py\n+x\n*** End Patch'
        self.assertEqual(self.guard(patch).returncode, 2)
        self.git('remote', 'set-head', 'origin', '-a')
        self.assertEqual(self.guard(patch).returncode, 2)
        self.git('switch', '-c', 'feature/safe')
        self.assertEqual(self.guard(patch).returncode, 0)

    def test_cleanup_preserves_ignored_collision_in_surviving_main(self):
        self.feature()
        (self.tree / 'private.env').write_text('published example')
        self.git('add', '.', cwd=self.tree); self.git('commit', '-m', 'track example', cwd=self.tree)
        self.tip = self.git('rev-parse', 'HEAD', cwd=self.tree)
        self.git('push', 'origin', self.branch, cwd=self.tree)
        self.git('push', 'origin', self.branch + ':main', cwd=self.tree)
        ignore = self.dir / 'ignore'
        ignore.write_text('private.env\n')
        self.git('config', 'core.excludesFile', str(ignore))
        private = self.main / 'private.env'; private.write_text('private local data')
        p = self.cleanup('--worktree', str(self.tree))
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(private.read_text(), 'private local data')
        self.assert_preserved()


if __name__ == '__main__':
    unittest.main()
