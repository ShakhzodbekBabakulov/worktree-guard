---
name: work
description: Start or resume an isolated coding workspace on the user's /work request.
disable-model-invocation: true
---

# /work — start or resume

Host: {{WG_HOST}}. Workflow: `/work` → `/push` → `/ship` → `/done`.
Respect repository instructions, task scope, and normal host permissions.

1. Inspect instructions, Git status, registered worktrees, current branch and remote default. Use the user's branch name; otherwise derive a short task name, prefixed `codex/` for Codex or `worktree-` for Claude. Ask only if the task is unclear.
2. Resume an exact matching workspace or existing branch before creating anything. Reuse an already suitable isolated workspace, including an unnamed native Codex worktree. Preserve edits; never stash, reset, discard, or relocate unrelated work automatically. Do not use substring matches to choose among branches.
3. Prefer native workspace tools: Claude EnterWorktree; Codex Worktree/Handoff. Never nest another worktree or create a separate Codex task unless requested. If the host has native UI controls but cannot move this task itself, explain the required handoff and wait.
4. Only when no native workspace facility exists, use the terminal fallback:

   ```sh
   {{WG_HELPERS}}/worktree-start <exact-branch-name>
   ```

   `--path <directory>` selects a new location. This resumes exact existing work, checks out an existing branch, or creates fresh work from the fetched remote default. Do not override refusals with force.
5. Verify the host task's actual working directory and Git workspace. A shell `cd` does not move a desktop task. If a native transition is unavailable, stop with the UI instruction instead of silently pointing tools elsewhere. In a terminal-only host, enter the printed workspace explicitly.
6. Follow documented project dependency/setup instructions there. Do not copy secrets or share dependency folders automatically. Report missing local configuration.
7. Report the workspace and branch (or isolated unnamed native worktree), then continue the authorized task. Next: `/push` for review, or `/ship` to prepare and merge.
