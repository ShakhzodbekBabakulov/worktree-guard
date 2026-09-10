#!/usr/bin/env python3
"""End-to-end compatibility checks: real wrappers/Git and simulated GitHub."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

HOOK = Path(__file__).resolve().parents[1] / 'hook'
GIT = shutil.which('git')


class LegacyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.hook = self.home / 'hook'
        shutil.copytree(HOOK, self.hook, ignore=shutil.ignore_patterns('__pycache__'))
        self.repo = self.home / 'repo'
        self.repo.mkdir()
        self.env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null')
        self.git('init', '-q', '--initial-branch=main')
        self.git('config', 'user.email', 'test@example.com')
        self.git('config', 'user.name', 'Test')
        (self.repo / 'a.ts').write_text('base\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'base')
        self.git('remote', 'add', 'origin', 'https://github.invalid/owner/repo.git')
        self.git('update-ref', 'refs/remotes/origin/main', 'HEAD')
        self.git('symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/main')
        self.bin = self.home / 'bin'
        self.bin.mkdir()
        self.state = self.home / 'gh.json'
        self.log = self.home / 'calls.log'
        self.env.update(PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        LEGACY_GH_STATE=str(self.state), LEGACY_CALL_LOG=str(self.log),
                        LEGACY_REAL_GIT=GIT)
        self.executable('git', '''#!/usr/bin/env python3
import os, sys
with open(os.environ['LEGACY_CALL_LOG'], 'a') as f: f.write('git ' + repr(sys.argv[1:]) + '\\n')
if 'fetch' in sys.argv[1:]: sys.exit(89)
os.execv(os.environ['LEGACY_REAL_GIT'], ['git'] + sys.argv[1:])
''')
        self.executable('gh', '''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ['LEGACY_CALL_LOG'], 'a') as f: f.write('gh ' + repr(args) + '\\n')
s = json.load(open(os.environ['LEGACY_GH_STATE']))
if s.get('broken'): print('unavailable', file=sys.stderr); sys.exit(1)
if args[:2] == ['repo', 'view']: result = {'nameWithOwner': 'owner/repo'}
elif args[:2] == ['pr', 'list']: result = s['prs']
elif args[:2] == ['pr', 'view']: result = next(p for p in s['prs'] if str(p['number']) == args[2] or p['headRefName'] == args[2])
elif args[0] == 'api': result = [s['files'][args[1].split('/')[-2]]]
else: print('unexpected fake gh call', args, file=sys.stderr); sys.exit(99)
print(json.dumps(result))
''')
        self.state.write_text(json.dumps({'prs': [], 'files': {}}))

    def executable(self, name, content):
        path = self.bin / name
        path.write_text(content)
        path.chmod(0o755)

    def git(self, *args, cwd=None):
        return subprocess.check_output([GIT, *args], cwd=cwd or self.repo,
                                       env=self.env, stderr=subprocess.PIPE, text=True).strip()

    def call(self, script, data=None, args=(), cwd=None):
        command = [str(self.hook / script), *args]
        return subprocess.run(command, input=json.dumps(data) if isinstance(data, dict) else data,
                              cwd=cwd or self.repo, env=self.env, capture_output=True, text=True)

    def edit(self, path, expected, **extra):
        event = dict(tool_input={'file_path': str(path)}, **extra)
        result = self.call('worktree-guard.sh', event)
        self.assertEqual(result.returncode, expected, result.stderr)
        return result

    def configure(self, **values):
        path = self.hook / 'worktree-guard.sh'
        source = path.read_text()
        for name, value in values.items():
            source, count = re.subn(r'^' + name + r'=.*$', name + '="' + value + '"', source, flags=re.M)
            self.assertEqual(count, 1)
        path.write_text(source)

    def test_protected_sources_and_planning_documents(self):
        for name in ['app.ts', 'src/deep/new.py', 'App.TS']:
            with self.subTest(name=name): self.edit(self.repo / name, 2)
        for name in ['README.md', 'settings.json', 'Makefile']:
            with self.subTest(name=name): self.edit(self.repo / name, 0)
        denial = self.edit(self.repo / 'app.ts', 2).stderr
        self.assertIn('main', denial)
        self.assertIn('/work', denial)

    def test_feature_branches_and_outside_repository(self):
        for name in ['feature-x', 'wip/some-thing']:
            self.git('checkout', '-qb', name)
            self.edit(self.repo / 'app.ts', 0)
        self.edit(self.home / 'loose.ts', 0)

    def test_primary_detached_denied_but_linked_detached_allowed(self):
        self.git('checkout', '-q', '--detach')
        self.edit(self.repo / 'app.ts', 2)
        linked = self.home / 'linked'
        self.git('worktree', 'add', '--detach', str(linked), 'HEAD')
        self.edit(linked / 'app.ts', 0)

    def test_malformed_guarded_edit_denied(self):
        for event in [{}, 'not json at all', {'tool_input': {}}, {'tool_input': {'file_path': 42}}]:
            with self.subTest(event=event):
                self.assertEqual(self.call('worktree-guard.sh', event).returncode, 2)

    def test_multiple_protected_branches(self):
        self.configure(PROTECTED_BRANCHES='main develop release')
        for branch, expected in [('develop', 2), ('release', 2), ('topic', 0)]:
            self.git('checkout', '-qb', branch)
            self.edit(self.repo / 'app.ts', expected)

    def test_all_but_safe_and_custom_extensions(self):
        self.configure(GUARD_MODE='all-but-safe')
        for name in ['Makefile', 'weird.xyz']: self.edit(self.repo / name, 2)
        for name in ['README.md', 'config.yaml', 'logo.png']: self.edit(self.repo / name, 0)
        self.configure(GUARD_MODE='listed', CODE_EXTENSIONS='xyz')
        self.edit(self.repo / 'app.XYZ', 2)
        self.edit(self.repo / 'app.ts', 0)
        self.configure(GUARD_MODE='invalid')
        self.edit(self.repo / 'app.ts', 2)

    def test_event_cwd_and_notebook_paths(self):
        self.edit('app.ts', 2, cwd=str(self.repo))
        self.configure(CODE_EXTENSIONS='ipynb')
        result = self.call('worktree-guard.sh', {'tool_name': 'NotebookEdit',
                                               'tool_input': {'notebook_path': str(self.repo / 'n.ipynb')}})
        self.assertEqual(result.returncode, 2, result.stderr)

    def reviews(self, other=None):
        self.git('checkout', '-qb', 'codex/mine')
        (self.repo / 'a.ts').write_text('mine\n')
        self.git('commit', '-qam', 'mine')
        head = self.git('rev-parse', 'HEAD')
        def pr(number, branch):
            return dict(number=number, headRefName=branch, baseRefName='main', state='OPEN',
                        changedFiles=1, headRefOid=head, isCrossRepository=False,
                        url='https://github.invalid/owner/repo/pull/' + str(number))
        prs = [pr(7, 'codex/mine')]
        files = {'7': [{'filename': 'a.ts'}]}
        if other:
            number, filename = other
            prs.append(pr(number, 'codex/other'))
            files[str(number)] = [{'filename': filename}]
        self.state.write_text(json.dumps(dict(prs=prs, files=files)))

    def merge(self, expected, command='gh pr merge 7 --squash'):
        result = self.call('ship-guard.sh', dict(tool_input={'command': command}, cwd=str(self.repo)))
        self.assertEqual(result.returncode, expected, result.stderr)
        return result

    def test_merge_clean_and_ordinary_commands(self):
        self.reviews()
        self.merge(0)
        for command in ['ls -la', 'git log --oneline', "echo 'gh pr merge 7'"]:
            self.merge(0, command)

    def test_merge_older_overlap_blocks_with_useful_reason(self):
        self.reviews((6, 'a.ts'))
        result = self.merge(2)
        self.assertIn('#6', result.stderr)
        self.assertIn('a.ts', result.stderr)

    def test_merge_younger_overlap_does_not_jump_queue(self):
        self.reviews((8, 'a.ts'))
        self.merge(0)

    def test_merge_incomplete_evidence_and_retired_checker_cannot_allow(self):
        self.reviews()
        self.state.write_text(json.dumps({'broken': True}))
        self.env['SHIP_GUARD_CHECKER'] = str(self.home / 'missing-checker')
        self.merge(2)
        self.state.write_text('not json')
        self.merge(2)

    def test_local_overlap_blocks_and_preserves_full_branch_name(self):
        self.reviews()
        linked = self.home / 'other'
        self.git('worktree', 'add', '-b', 'codex/unfinished/session', str(linked), 'main')
        (linked / 'a.ts').write_text('unfinished\n')
        result = self.merge(2)
        self.assertIn('codex/unfinished/session', result.stderr)
        report = json.loads(self.call('session-conflict-check').stdout)
        self.assertTrue(report['gh_ok'], report)
        self.assertIn('codex/unfinished/session', [c['branch'] for c in report['conflicts']])

    def test_checker_read_only_and_legacy_flags(self):
        self.reviews()
        before = self.git('show-ref')
        for args in [(), ('--no-fetch',)]:
            result = self.call('session-conflict-check', args=args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)['gh_ok'])
        self.assertEqual(before, self.git('show-ref'))
        self.assertNotIn("'fetch'", self.log.read_text())
        rejected = json.loads(self.call('session-conflict-check', args=('--base', 'main')).stdout)
        self.assertFalse(rejected['gh_ok'])
        self.assertIn('base', rejected['warnings'][0])

    def test_checker_incomplete_outside_repo_is_json(self):
        result = self.call('session-conflict-check', cwd=self.home)
        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertFalse(report['gh_ok'])
        self.assertTrue(report['warnings'])


if __name__ == '__main__':
    unittest.main()
