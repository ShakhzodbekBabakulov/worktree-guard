---
name: ship
description: Prepare unpublished work when needed, merge the tested pull request safely, and verify configured deployments. Use on the user's /ship request. Cleanup is /done.
disable-model-invocation: true
---

# /ship — prepare if needed, merge, verify

Host: {{WG_HOST}}. `/ship` includes the push stage when needed. Respect project instructions and host permissions; do not publish or merge without the user's request.

1. Inspect the task workspace and branch. Name an isolated unnamed native worktree as described in [the shared push stage](../push/references/prepare-review.md). Stop on the protected default branch. Run `{{WG_HELPERS}}/workflow-status`. Stop on errors or CLOSED. On MERGED, report whether newer work remains; suggest `/done` only for finished work.
2. If `needs_push: true` (missing PR, unsaved/unuploaded work, or a different review head), execute [the shared push stage](../push/references/prepare-review.md) fully and then continue shipping. Do not stop at the preview link. Re-read status afterwards. Never recurse from `/push` into `/ship`.
3. Fetch origin. Run `{{WG_HELPERS}}/codex-session-conflict-check --pr <number>` (a compatibility name shared by both hosts). Read `gh_ok`, warnings and each `blocking` field. Unknown is not all-clear. Overlapping unsubmitted local work, including later edits behind an existing PR, stops shipping and identifies the workspace. Older overlapping PRs go first; newer submitted PRs do not block this one.
4. Wait for older blocking PRs at 60-second intervals for at most 30 minutes. Remain responsive and report meaningful changes/elapsed time. Do not schedule recurring automations, message others, or wait indefinitely. If still blocked, report and stop. Fetch and check again after waiting.
5. Merge the current remote review base into this feature branch. Stop for nontrivial unresolved conflicts. Run documented fast checks (lint, type checks, unit tests) if code changed. Reuse prior evidence only when recorded for the exact unchanged head; otherwise check now. Failures stop merging. Push updated feature work explicitly. Confirm local HEAD, remote feature tip and PR head match; recheck if work changes.
6. Inspect hosted checks. Failed, pending or unknown results stop merging. If no hosted checks exist, disclose that and rely on verified project checks. Run the conflict checker again immediately before merging.
7. Run this standalone command with the tool working directory set to the target repository (no `cd &&` prefix or repository override):

   ```sh
   gh pr merge <number> --squash --match-head-commit <tested-commit>
   ```

   Follow the project's merge method if different. Do not use `--delete-branch`; cleanup belongs to `/done`. If blocked, re-evaluate the blocker. If queued, verify actual MERGED state before claiming success.
8. Verify MERGED state and resulting base commit. For affected configured deployments, use provider/check evidence tied to that commit plus the documented application check. An old page responding is not deployment proof. Report failed/pending/unavailable deployment checks separately from a successful merge. If no deployment is configured, say so.
9. Report review URL, checks, merge commit, deployment evidence/limitations and waiting. Next: `/done`. Do not remove branches/workspaces here.
