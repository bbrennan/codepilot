---
name: resolve-merge-conflicts
description: Resolve git merge or rebase conflicts by understanding the intent of both sides. Use when files contain conflict markers or the user is mid-merge/rebase.
---
# Resolve merge conflicts

1. `git status` to list conflicted files and whether this is a merge, rebase, or cherry-pick.
2. For each conflicted file, understand both sides before editing:
   - `git log --oneline --merge -- <file>` and `git show <commit> -- <file>` for the commits involved
   - read the conflict hunks with enough surrounding context
   - state each side's intent in one line ("ours renames X", "theirs adds a retry")
3. Combine the intents; don't just pick a side. If they truly conflict, ask the user which behaviour wins.
4. Propose the resolved hunks with `propose_edit` (no conflict markers left; search for `<<<<<<<`, `=======`,
   `>>>>>>>` afterwards).
5. Run the tests touching those files. Tell the user the git commands to finish (`git add`, then
   `git merge --continue` / `git rebase --continue`); codepilot never commits for them.
