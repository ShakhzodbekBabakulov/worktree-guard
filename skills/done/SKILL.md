---
name: done
description: Safely remove this task's proven-merged workspace and local/remote feature branches on the user's /done request. Never cleans other tasks.
disable-model-invocation: true
---

# /done — clean up finished work

Host: {{WG_HOST}}. The user's `/done` authorizes cleanup of this task only. Respect project instructions and host permissions.

1. Inspect Git status, registered worktrees and the task's review. Identify the exact finished branch/workspace. Ask only if several targets are plausible. Never sweep all workspaces or infer completion from an old PR alone.
2. Move the host task away from a directory that will be deleted, using native handoff/exit-worktree controls where available, and verify its new location. If this task cannot move itself, explain the native UI step and wait. A shell `cd` alone does not relocate a desktop task. Terminal-only hosts must run cleanup from the surviving primary checkout.
3. Preview the selected operation:

   ```sh
   {{WG_HELPERS}}/worktree-cleanup --worktree <finished-path> --dry-run
   ```

   For a leftover branch without a workspace use `--branch <exact-branch>`. Preview does not fetch/change refs. If remote evidence is stale, fetch origin from the surviving checkout and repeat.
4. Run the same command without `--dry-run` after the preview confirms the target. The helper proves the latest exact commit landed (normal or squash), refuses newer remote commits/default divergence, preserves ignored/private and unsaved files, and never removes the primary folder. Never bypass refusals with force or manual deletion.
5. If cleanup stops, preserve remaining work and report each completed step accurately: a later failure does not undo earlier progress. Coordinate app-managed directory removal through supported host controls; never leave the task pointing into a deleted folder or archive unrelated tasks.
6. Verify workspace registrations, local branches and exact remote branch absence from the surviving checkout. Report what disappeared and what remains. Next: `/work` for the next feature.
