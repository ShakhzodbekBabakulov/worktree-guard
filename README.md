# worktree-guard

One workflow for Claude Code and Codex: **`/work` → `/push` → `/ship` → `/done`**.
The four commands share Python helpers and a built-in review checklist. No other
workflow package or personal configuration is required.

## Workflow

| Command | Behavior |
| --- | --- |
| `/work <name>` | Resume a matching workspace or branch first; otherwise start isolated work from the remote default branch. Prefer native app transitions, verify the actual working location, preserve unsaved work, and follow project setup instructions. |
| `/push` | Review requirements and code, run project checks, save intended work, update from the review base/default branch, retest, push the feature branch, and create/update its pull request. Return an evidenced preview when available. Never merge. |
| `/ship` | Perform the push stage automatically for missing reviews or unsaved/unuploaded work. Check overlap, update and retest, merge the exact tested head, then verify configured deployments against the released commit. Leave cleanup to `/done`. |
| `/done` | Prove the latest feature tip was merged, safely update the default checkout, and remove only the selected finished workspace and local/remote feature branches. Report each completed step. |

Commands are explicit, user-invoked skills. Project instructions and host
permissions still apply. The shared push-stage reference lets `/ship` prepare
work without depending on another automatically invoked command.

## Install

Supports macOS and Linux. Requires **Git and Python 3.9+** on the host's PATH.
Publishing and merging additionally require authenticated GitHub CLI (`gh`).
No third-party Python packages are needed.

Clone this repository and run the installer from the checkout:

```sh
git clone https://github.com/ShakhzodbekBabakulov/worktree-guard.git
cd worktree-guard
python3 install.py --host both --scope user
```

Choose `--host claude`, `--host codex`, or `--host both`. Default: Claude, user
scope. For only one project, provide its existing Git repository root:

```sh
python3 install.py --host both --scope project --project "/path/to/project"
```

| Host | Skills relative to scope root | Hook configuration | Helpers |
| --- | --- | --- | --- |
| Claude Code | `.claude/skills/{work,push,ship,done}/` | `.claude/settings.json` | `.claude/hooks/` |
| Codex | `.agents/skills/{work,push,ship,done}/` | `.codex/hooks.json` | `.codex/hooks/` |

User scope means your home folder; project scope means the selected repository.
For project distribution, review and commit the generated settings, helpers and
skills so new worktrees/clones contain them. An uncommitted project installation
does not appear automatically in another checkout; install there separately or
use user scope. Backups and ownership manifests are local installation records,
not required team runtime files.

Use a single scope for these command names to avoid competing definitions from
user and project installations. The installer checks conflicts in the selected
scope; it does not remove definitions in another scope or another plugin.

Replaced files are backed up under the selected host's
`worktree-guard-backups/`. Unrelated settings and hook handlers are preserved.
An existing unrelated command or modified owned file stops installation. Review
the reported collision before explicitly choosing replacement:

```sh
python3 install.py --host both --scope user --replace-commands
```

This choice backs up replaced commands, including legacy Claude command files.
`install.sh` remains a wrapper for this installer; `install-codex.py` defaults to
Codex user scope. Downloading a lone installer script is no longer supported:
the complete checkout supplies the matching helpers and skills.

### Configured is different from active

The installer writes configuration; it cannot prove that an app has loaded it.
Restart/reload the host and inspect its native hook controls. In Codex, review
and approve the hook through the native trust flow (`/hooks` in the CLI).
Changed hook definitions can require approval again. This installer never writes
trust hashes or bypasses host approval.

Run a disposable real-host test: attempt a source edit on the protected default
branch (must be denied), then the same edit in an isolated feature workspace
(must be allowed). Codex should also allow an unnamed, linked native worktree.
Record the actual hook event and result; calling the script directly is a
separate test. See [verification evidence and remaining checks](docs/verification.md).

Official integration contracts: [Codex hooks](https://learn.chatgpt.com/docs/hooks),
[Codex skills](https://learn.chatgpt.com/docs/build-skills),
[Claude hooks](https://code.claude.com/docs/en/hooks), and
[Claude skills](https://code.claude.com/docs/en/skills).

## Guards and boundaries

**Branch guard:** Claude `Edit`, `Write`, and `NotebookEdit`, plus Codex native
`apply_patch` events, use one policy. Each affected file is checked against its
own repository, including rename destinations. Source edits on main, master,
and the recorded remote default branch are refused; planning documents remain
editable. A detached primary checkout is refused. A registered linked detached
worktree is allowed, matching [Codex's native model](https://learn.chatgpt.com/docs/environments/git-worktrees).
If origin exists but its default branch is not recorded locally, named-branch
source edits stop until `git remote set-head origin --auto` records it. Refresh
that reference if the repository's default branch changes.

**Merge guard:** supported direct `gh pr merge` calls are checked against their
actual PR number or branch, including selectors after flags. Use a standalone
command with the tool working directory set to the target repository. Compound
merge commands, repository overrides and ambiguous option layouts are refused;
read-only merge help is allowed. Malformed supported events and incomplete
GitHub evidence stop guarded actions.

Older overlapping PRs against the same base go first, ordered by PR number.
`/ship` waits at most 30 minutes, checking every 60 seconds. Overlapping
unsubmitted local changes stop shipping and identify their workspace; later
local changes behind a submitted PR are included. Newer submitted PRs remain
visible but do not block the older one. The checker caps its scan at 99 open
PRs and verifies complete file lists. Unknown results never mean all-clear.

The read-only checker is also available as `session-conflict-check` or
`codex-session-conflict-check`, with `--pr NUMBER`. Read `gh_ok`, `warnings`, and
each conflict's `blocking` field; exit status alone is not an all-clear signal.

This is an agent-workflow tripwire, not a security sandbox. Arbitrary shell file
writes, other file-writing tools, wrapped/aliased merge commands, direct pushes,
and web/API merges are outside interception. Unpublished work on other computers
is invisible. File overlap is conservative and cannot prove semantic conflicts.
Branch permissions and required GitHub checks remain useful independent controls.

## Cleanup and deployment evidence

Cleanup requires current remote-base evidence and the exact latest feature tip.
Ordinary merge ancestry is sufficient; squash cleanup additionally requires a
matching merged PR head and its merge commit on the remote base. Unknown proof,
new commits, locked workspaces, or unsaved/untracked/ignored files in a folder to
be deleted stop removal. This includes generated dependency folders: resolve
them deliberately before retrying. Ignored files in the surviving checkout are
protected from incoming tracked-file collisions using Git's native options.

Only the selected workspace and branches are removed. The primary folder stays.
Remote deletion is conditional on the inspected tip; local deletion also checks
the expected tip. Cleanup can partially succeed, so each completed step is
printed and later failures preserve what remains. Concurrent filesystem changes
cannot be made fully atomic with this workflow. `/done` must move the actual
task away before removal; changing a shell directory is not an app handoff.

Failed required checks stop publishing/merging. Missing checks are disclosed.
Deployment success needs provider/check evidence identifying the released
commit plus the project's documented application check. A responding old page
is insufficient. Projects without deployments report that explicitly. Version
changes and release notes follow each project's own conventions.

## Configuration and upgrades

Optional `worktree-guard-config.json` beside the installed helpers customizes
the policy. It is user-owned and is not replaced by installation:

```json
{
  "protected_branches": ["release"],
  "mode": "listed",
  "code_extensions": ["py", "js", "ts", "tsx", "swift"],
  "safe_extensions": ["md", "txt", "json", "yaml", "toml"]
}
```

Omit extension lists to retain defaults. `listed` guards only source extensions;
`all-but-safe` guards everything outside the safe list, including extensionless
files. Built-in protected branches are additive. Malformed configuration blocks
supported edits instead of silently disabling protection.

The old Claude `worktree-guard.sh` and `ship-guard.sh` entry points remain wrappers
around the shared policy. Existing shell extension/mode/branch settings remain
available in the former wrapper. The legacy checker accepts `--no-fetch` but
never fetches. Its old `--base` override now reports an unsupported/unknown result.
`SHIP_GUARD_CHECKER` and `BLOCKING_KINDS` overrides are retired: unknown GitHub
results and local overlap must not silently bypass the shared merge policy.

To upgrade, update this checkout and rerun the same host/scope install command.
Owned unchanged files update safely; local modifications require an explicit
replacement choice. Check file integrity afterwards:

```sh
python3 install.py --host both --scope user --check
```

`--check` is read-only and does not claim real-host activation. Use the same
project arguments for project installations, and repeat native smoke tests.

## Uninstall

```sh
python3 install.py --host both --scope user --uninstall
```

Use the original scope/project arguments. Uninstall removes unchanged owned
files/hooks, restores backed-up originals and migrated hook handlers, and
preserves unrelated settings and modified files. Backups are retained. If an
owned file was edited or deleted independently, the report identifies it for
manual inspection; nothing is blindly overwritten. Reload the host afterwards.

## Tests

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s test -p 'test_*.py' -v
bash test/selftest.sh
```

Tests use disposable repositories, local bare remotes, temporary installation
folders, and simulated GitHub responses. They never merge a live PR or delete
a live remote branch. The shell entry point runs the legacy compatibility tests,
which are also included in discovery. Real-host evidence is tracked separately.

MIT — see [LICENSE](LICENSE).
