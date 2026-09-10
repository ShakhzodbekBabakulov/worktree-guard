---
name: push
description: Review, test, save and upload this task's feature branch, then open or update its pull request. Never merges. Use on the user's /push request.
disable-model-invocation: true
---

# /push — prepare review

Host: {{WG_HOST}}. An explicit `/push` authorizes this task's commit, feature push and review request; project instructions and host permissions still apply.

Read and execute [the preparation checklist](references/prepare-review.md) in full. It is bundled with this workflow and requires no external review toolkit. Stop at the pull request and preview report. Do not merge or clean up.

Report what changed, actual check results and limitations, the pull request URL, and a verified preview URL with its coverage (or why none exists). Next: review the result, then `/ship`.
