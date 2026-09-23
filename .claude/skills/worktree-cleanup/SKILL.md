---
name: worktree-cleanup
description: "Audit and remove stale git worktrees of this repo (and their per-worktree submodule branches), driving each to a terminal state — its work is on the remote as a PR, or it has no diff vs main — before deleting the local copy. Use when the user wants to list, prune, or clean up worktrees, or right after opening a PR from a worktree."
effort: low
mutation: mutating
worktree: false
lock: none
---

# Worktree Cleanup

Companion to `worktree-submodules`. First step: `git worktree list` — only the main worktree listed and `../<repo>-worktrees/` empty or absent → nothing to do, exit.

## Goal

Every worktree ends in one of two terminal states before its local copy is removed:

1. **Has a PR** (open, merged, or closed) — the work lives on the remote.
2. **No diff vs `origin/main`** — nothing to preserve.

Anything else has uncaptured work. Default: land a PR first, then remove. Never silently discard. Surface clearly-stale ones (very old, huge dirty count, user-abandoned) to the user case-by-case.

## Scripts

Run from the main checkout with repo-relative paths. Never operate on the worktree you're currently in.

### `audit.sh` — read-only inventory

```bash
.claude/skills/worktree-cleanup/scripts/audit.sh --header | column -t -s $'\t'
```

Columns: `PATH BRANCH STATE AGE ACTIVE SUPER_DIRTY SUB_DIRTY MERGED LOCKED PR_URL PR_STATE NOTES`

- `AGE` is last-**commit** age, not session activity — never use it to judge liveness.
- `ACTIVE=y` — a file changed in the last 30 min: a live session owns it.
- `SUPER_DIRTY` / `SUB_DIRTY` already drop gitlink-pointer noise; `0` = truly clean.
- `MERGED` is vs `origin/main` after a fetch (`--no-fetch` to skip; `--base` to change).

| Bucket | Filter | Action |
|---|---|---|
| live — hands off | `ACTIVE=y` (overrides all) | Surface only; don't touch. |
| locked | `LOCKED=y` | Confirm no session holds it first. |
| safe to remove | dirty `0/0` AND (`MERGED=y` OR `PR_URL` set) | Remove directly. |
| no-op branch | no PR AND no diff vs main | Remove directly. |
| land PR first | no PR AND has diff | Commit, push, `gh pr create`, then remove. |

Diff vs main check for "no PR" rows:

```bash
git -C "$wt" log --oneline origin/main..HEAD
git -C "$wt" status --porcelain | grep -vE '^.M [^ /]+$'
git -C "$wt" submodule foreach --recursive --quiet 'git status --porcelain'
```

All empty → no diff.

### `remove-worktree.sh` — one-shot removal

```bash
.claude/skills/worktree-cleanup/scripts/remove-worktree.sh <worktree-path> [--superseded|--preserved|--force-discard]
```

Unlocks → removes (with `--force` fallback on the submodule refusal) → `rm -rf` orphan dir → prune → deletes the branch in the superproject and each submodule (skipping branches used by another worktree).

- **Refuses** (exit 3) on real uncommitted work or local-only submodule commits.
- `--superseded` / `--preserved` — let `check-superseded.sh` verify current main or a remote PR already holds every change, then remove.
- `--force-discard` — irreversible; only after showing the user the diff and getting an explicit go-ahead.
- Refuses to remove the main worktree or the one you're `cd`'d into.

Exit codes: `0` removed, `2` bad args / not a registered worktree, `3` refused, `4` removal failed (dir survived sandbox — re-run unsandboxed).

## Orphan sweep

After the registered pass, list `../<repo>-worktrees/` and subtract `git worktree list` paths. Leftovers are orphans (sandbox blocked an unlink, or a stray clone). Skip any with a file modified in the last 30 min; check a leftover `.git` dir for unpushed commits before deleting; otherwise `rm -rf` it.

## Tests

`scripts/*.test.sh` — run after editing any script.
