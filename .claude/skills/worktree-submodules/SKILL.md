---
name: worktree-submodules
description: "Create an isolated sibling git worktree (branched off fresh origin/main) through the bundled script, initializing only needed submodules. Use before any write to this repo — code, docs, or skill changes — when foreign dirty state exists, or when parallel agents need independent branches. Skip for read-only work."
effort: low
mutation: mutating
worktree: false
lock: none
---

# Worktree + Submodules

Use the bundled script to create isolated sibling worktrees. A plain `git worktree add` skips the fresh-base fetch, the sibling-path guard, and the timestamped branch.

## Before writing

- Run `git status --short --branch` in the intended repo.
- Reuse a session-created sibling worktree only when it has the needed submodules and branches.
- Otherwise run the creation script from the main clone before editing.
- Leave foreign dirty state untouched; never stash, restore, reset, clean, stage, or commit it. If this session already edited the shared checkout, read `MANUAL.md` §2 and migrate only those paths.

Read-only inspection can stay in the main checkout.

## Create the worktree

```bash
.claude/skills/worktree-submodules/scripts/create-worktree.sh <slug> \
  [--ticket <ID>] [--base <branch>] [--install-dependencies] [--submodule <path> ...] \
  [--submodule-branch <submodule>:<remote-branch> ...]
```

The script creates `../<repo>-worktrees/<slug>-<timestamp>/` on a same-named branch from fresh `origin/main` and prints the absolute path. Use:

- `--ticket <ID>` when a Linear ticket exists so the branch carries the ticket ID (`s-123-<slug>`).
- `--submodule <path>` for a submodule that will only be read or tested.
- `--submodule-branch <path>:<remote-branch>` for a submodule that will be edited; this also initializes it.
- `--all` only when every submodule is needed.
- `--install-dependencies` for bounded JS setup: requires root `package.json` + `bun.lock` on the base, then runs only `bun install --frozen-lockfile --ignore-scripts` in the root and initialized submodules that have both files.

Run the script with `--help` for the remaining flags; use `--verbose` only when diagnosing creation.

Never use raw `git worktree add`, an in-tree worktree, or built-in agent worktree isolation. For an existing feature branch, manual migration, unusual base, or subagent fan-out, read the relevant section of `MANUAL.md` before acting.

## Deliver and clean up

Commit and push each changed repository promptly so cleanup can distinguish active work from an empty worktree. A submodule change ships through that submodule's own PR; never stage its superproject gitlink in the same PR. Never use a blanket push across initialized repositories.

After every required PR opens, remove the worktree from the main clone via the `worktree-cleanup` skill:

```bash
.claude/skills/worktree-cleanup/scripts/remove-worktree.sh <worktree-path>
```

Remove only artifacts created by this session and confirm the shared checkout has no new dirt attributable to the task. `MANUAL.md` §§6–7 contain manual push and teardown details.
