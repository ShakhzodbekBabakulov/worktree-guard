# One worktree workflow for Claude and Codex

## Approved goal
Provide /work → /push → /ship → /done for Claude Code and Codex, without gstack or personal-project dependencies. Preserve existing unfinished work. After implementation and verification, follow the authorized /push and /ship delivery stages; required unresolved checks still block release.

## Commands
- /work <name>: resume a matching worktree or existing branch first; otherwise create isolated work from the current remote default. Prefer native host workspace transitions and verify actual cwd. Preserve unsaved work and follow project dependency setup.
- /push: update from default, inspect bugs and requirements, run documented project checks, save only task changes, push explicit feature branch, create/update PR, return verified preview if available. Never merge. Name isolated detached work before uploading.
- /ship: run push stage when missing PR, unsaved work, or unpushed changes; check overlap; older PRs first, maximum 30-minute wait; local unsubmitted overlap or incomplete GitHub evidence stops merge. Refresh, retest changed code, require hosted checks, merge exact tested head, verify configured deployment by commit. No cleanup.
- /done: prove exact latest work merged (normal or squash), update base safely, remove only selected workspace and local/remote branches. Preserve unsaved, ignored/private files, newer commits and unrelated work. Report partial cleanup honestly.
- Failed required checks stop publishing/merging. Missing checks are disclosed. Version/release notes follow project conventions. Host permissions and project instructions apply.

## Implementation
1. Shared Python Git/conflict/cleanup helpers and native Claude/Codex event adapters. Keep existing Claude entrypoints compatible.
2. Branch guard blocks supported source edits on protected branches, allows feature branches and verified linked detached worktrees, allows planning documents. Shell writes are outside this tripwire.
3. Merge guard resolves actual target and refuses overlapping/unverifiable direct GitHub merges.
4. Native workspace tools first; never claim an app moved merely because shell cwd changed. If self-handoff unavailable, give the native handoff step. Leave workspace before cleanup.
5. One installer: --host claude|codex|both, --scope user|project; Git/Python 3.9+, gh authentication before publishing/merging; preserve unrelated settings, backups, repeatability, collision confirmation, check/upgrade/uninstall. Never change hook trust hashes.
6. macOS/Linux; distinguish configured from proven active. Documentation includes native trust and limitations.

## Files / ownership
- Core: hook/worktree_common.py, hook/worktree-start, hook/worktree-cleanup, hook/workflow_guard.py, hook/codex-guard.py, hook/claude-guard.py, hook/workflow_conflicts.py, hook/workflow_merge_guard.py; existing compatibility entrypoints; core tests.
- Installer: install.py, install-codex.py, install.sh, test/test_installer.py.
- Commands/docs: skills/{work,push,ship,done}/SKILL.md plus shared references, README.md, CODEX.md, CHANGELOG.md, docs/verification.md.

## Verification
- Preserve baseline evidence: 19 Codex workflow tests and 32 legacy Claude assertions passed before this change.
- Disposable repos/temp homes: create/resume/existing branches/spaces/detached worktrees; fresh installs/upgrades/repeat installs/both hosts/unrelated settings/collisions; shared adapters block/allow correctly.
- Simulate GitHub destructive scenarios: failed/missing checks, partial API, overlap/order/local unsaved work, changed head, normal/squash cleanup and partial failure.
- Real Claude and Codex host smoke tests separate from direct-script tests. Never claim actual hook activation from unit tests alone. Record unavailable host checks explicitly.
- Deliver review-ready changes; publishing follows /push and /ship separately.

## Progress
- Approved plan saved; original repair notes preserved in docs/prior-codex-repair.md.

- Shared helpers, four commands, unified installer, compatibility wrappers and documentation implemented. Review findings received regression tests and fixes.
- Real-host smoke checks attempted separately; activation/account limitations are recorded in docs/verification.md.

- 68 automated cases pass; Codex native protected, named-feature and linked-unnamed edit smoke checks pass. Claude native delivery remains blocked by account access. Publishing is pending this required check; shipping additionally identifies an existing unsaved primary-checkout plan overlap. Existing plans/workspaces remain preserved.
