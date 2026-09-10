# Verification record

Date: 2026-09-10. Environment: macOS, Git 2.50.1, Python 3.14.5,
Claude Code 2.1.263, Codex CLI 0.153.4.

## Automated behavior

`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s test -p 'test_*.py' -q`
passed **72 tests**. The 14 legacy compatibility cases are included in this
count and also run through `bash test/selftest.sh`. The suite includes 37 core, 21 installer and 14 legacy cases.

Coverage includes temporary user/project installs for either/both hosts,
repeat installations and upgrades, legacy command collisions, unrelated
settings, backup originals, symlink rejection, modified/missing uninstall
targets, native adapter input shapes, paths with spaces, default/feature and
linked detached edits, workspace resumption, existing local/remote branches,
and naming detached work without discarding changes.

Simulated GitHub responses exercise actual PR selector order, older-first
overlap, unsaved work in other and invoking checkouts, incomplete responses,
changed expected heads, missing/open/closed/merged status decisions, exact-tip
ordinary/squash cleanup, ignored-file collisions, later commits, dirty main,
and preservation of unrelated workspace data. Merge-command compound layouts,
read-only help, and quoted documentation examples have regression coverage.

Code review found and fixed ignored-file overwrites, actual-target selection,
invoking-workspace overlap, newline parsing, unknown-default protection and
help-command false denials. The shipping review additionally fixed staged-index
overlap omissions, workspace identity changes during cleanup, and uninstall
leaving modified hooks behind after removing their runtime. Regression cases
cover all three, including failure after remote-branch deletion. Installer review fixes cover preservation of
identical preexisting files, backup symlink safety and deleted settings during
uninstall.

Python 3.9 grammar parsing passed for all 19 Python source/helper/test files;
shell syntax and `git diff --check` passed. This is syntax compatibility,
not a Python 3.9 runtime or Linux execution claim. No live merge or branch
deletion is performed by automated tests.

The command instructions were reviewed for `/push` stopping before merge,
`/ship` executing the shared push stage when needed, required-check failures,
bounded waits, exact tested-head merging, and deployment evidence. Status
decisions are executable tests; full AI-driven command runs through publication
and deployment have not been proven by those tests.

## Real Codex host evidence

Installed both adapters in a disposable project. Installer integrity checks
passed. An initial headless session correctly reported the hook configured
but untrusted; it did not attempt an edit. This was not counted as activation.

The native `/hooks` interface then showed the project PreToolUse hook as new.
It was reviewed and trusted through that interface. No trust hashes were
written by the installer or edited manually. The existing user-wide guard
remained enabled, and everyday installation files were not replaced.

- Protected main: a native `apply_patch` attempt to create `smoke.ipynb` was
  denied with the new project's exact message: `smoke.ipynb is source on main.
  Run /work to create or resume an isolated workspace.` The file remained absent.
- Feature branch: the corresponding native `apply_patch` succeeded and the
  on-disk notebook matched the requested content.
- A separate initial `.py` denial came from the older user-wide guard, so it
  is deliberately not used as evidence for the replacement.
- Linked unnamed worktree: after installing the project files into that
  checkout, the native hook inventory showed the trusted project guard active.
  The native notebook patch succeeded, the file matched its requested content,
  and Git still reported no named branch. No branch was created for the test.

Local raw traces are retained in the disposable smoke-test folder under
`/private/tmp/worktree-guard-host-smoke-g6cy4u8s/`: `codex-notebook-main.jsonl`
, `codex-notebook-feature.jsonl` and `codex-notebook-detached.jsonl`. These are machine-local evidence, not
distributed runtime paths or prerequisites. Native UI trust was observed
separately through the terminal interface.

The empty linked checkout did not inherit an uncommitted project hook from
the primary checkout. The native hook inventory showed only the user hook.
Project installation files must be present in the checkout (normally by
committing the reviewed configuration/helpers/skills); this is documented.

## Real Claude host evidence

The disposable project contained the native Claude configuration and adapter.
Ran Claude with project settings, Read/Write tools, an approved single-write
test, verbose stream output and hook events. Authentication status was logged
in, but the model request failed before a Write event with HTTP 403,
`oauth_org_not_allowed`: the organization has disabled subscription access to
Claude Code. No source file was created.

**Not passed; user-owned follow-up:** actual Claude deny/allow delivery still
needs an account permitted to run Claude Code. The user explicitly chose to
install and validate Claude themselves and authorized publishing and cleanup
without waiting for that host test. Direct adapter and legacy-wrapper tests
do not prove Claude activation. No credentials belong in this repository.

## Verification limits

Before claiming both-host verification, the user must complete real Claude
protected/isolated edit tests with permitted access. This remains an unverified
host claim, not a publication blocker after the user’s explicit scope change.
Native desktop workspace handoff and cleanup,
full command publication scenarios, Linux execution, and Python 3.9 runtime
coverage remain explicit unverified areas. No application deployment is
configured in this repository, and no deployment success is claimed.

## Delivery status

The real repository status helper reported a missing pull request and
`needs_push: true`, as expected for unpublished work. GitHub access is available.
The real conflict checker returned `gh_ok: true` and identified an overlapping
untracked `PLAN.md` in the primary main checkout. That older planning document
was moved into a local archive under the surviving primary repository’s Git
metadata and verified byte for byte. The original repair notes will be archived
there before removing their workspace. This resolves the planning-document
overlap without discarding it; shipping still performs a fresh conflict check.

Implementation is saved in the existing repair workspace. The user authorized
publishing, merging, finished-work cleanup and removal of other proven-stale
branches/worktrees. Claude installation and live validation are user-owned.
Publication and cleanup are pending in this record; their eventual results
must be verified independently. No release, tag, deployment or completed
cleanup is claimed by these documentation changes.
