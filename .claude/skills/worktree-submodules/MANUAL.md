# Worktree + Submodules — Manual Fallback

The steps below mirror what `scripts/create-worktree.sh` does — use these only when you need to deviate (carry an existing feature branch,
migrate foreign dirty state, etc.). For the default path and when-to-use, see `SKILL.md`; run the script with `--help` for its flag
reference.

## 1. Pick a path and branch name

Worktrees live in a dedicated `<repo>-worktrees/` directory **alongside the repo** (sibling of the repo root, not inside it). In-tree paths — even
`.claude/worktrees/` — get walked by formatters, indexers, and skill scanners, causing duplicate work and cache pollution.

```bash
repo_root="$(git rev-parse --show-toplevel)"
repo_parent="$(dirname "$repo_root")"
worktrees_root="${repo_parent}/$(basename "$repo_root")-worktrees"
mkdir -p "$worktrees_root"

slug="<short-task-name>"   # derive from the task; e.g. Linear identifier + short descriptor
worktree_path="${worktrees_root}/${slug}-$(date +%Y%m%d-%H%M%S)"
branch="${slug}-$(date +%Y%m%d-%H%M%S)"
```

Always append the timestamp to **both** `worktree_path` and `branch` — agents launched seconds apart with the same slug collide otherwise.

## 2. Create the worktree off the latest base

The bundled script does this by default: it fetches `origin/main` and refuses to fall back to a stale local `main`.

```bash
git -C "$repo_root" fetch origin
git -C "$repo_root" worktree add -b "$branch" "$worktree_path" origin/main
```

### Variant: carry an existing feature branch into the worktree

If you're isolating because of foreign dirty state but already have your own feature branch with committed work, carry the same commits into
the worktree — starting fresh from `origin/main` loses your existing work and points PR creation at the wrong head. Branch off the same
commit instead of sharing the ref; sharing requires `-f` which silently bypasses Git's same-branch safety check and can drop files between
cross-session commits.

```bash
existing_branch="$(git -C "$repo_root" branch --show-current)"
# Refuse on detached HEAD — caller must pass the branch name explicitly.
if [ -z "$existing_branch" ]; then
  echo "main clone is on detached HEAD; pass the branch name explicitly" >&2
  exit 1
fi
isolation_branch="${existing_branch}-iso-$(date +%Y%m%d-%H%M%S)"
git -C "$repo_root" worktree add -b "$isolation_branch" "$worktree_path" "$existing_branch"
```

Merge / cherry-pick / open the iso branch as its own PR when the isolation session finishes.

### Foreign dirty state: migrate only your own paths

If the existing branch carries uncommitted work that needs to come along, do **not** commit broadly in the main clone to "make room" — that
risks capturing foreign dirty paths. Create the worktree first, then re-apply only your own paths via a path-scoped patch (ordering
rationale below). `--binary` on both sides is required so tracked binary edits survive the round-trip.

```bash
repo_root="$(git -C . rev-parse --show-toplevel)"   # run from the main clone
worktree_path=/absolute/path/to/sibling/worktree    # the `${worktrees_root}/${slug}-<ts>` from above

git -C "$repo_root" diff --binary --cached -- <your-paths> | git -C "$worktree_path" apply --binary --index
# then unstaged on top (skip if no unstaged edits):
git -C "$repo_root" diff --binary -- <your-paths> | git -C "$worktree_path" apply --binary
# for untracked files of yours, copy explicitly: cp -- <src> "$worktree_path/<dst>"
```

**Ordering rationale:** `--cached` (staged) MUST go before the plain diff (unstaged). The unstaged patch is generated against the staged
content, so applying unstaged first against a clean destination fails with `patch does not apply` (or silently drops hunks) on any path with
both staged and unstaged edits. `--index` (not `--cached`) on the staged step updates both index AND worktree — `--cached` alone leaves
worktree files at HEAD, so the unstaged patch has the wrong base.

After migrating, revert only the paths you yourself dirtied from the shared checkout (`git checkout -- <path>` per file you touched, `rm`
for files you yourself created) so the shared tree returns to the exact state you found it in.

**WARNING: superproject `git diff` does NOT carry submodule file edits.** It records only the submodule pointer (often as a `-dirty`
marker); the actual file hunks live in each submodule's own working tree. For dirty submodule paths, run the same diff/apply **inside each
submodule** after step 3:

```bash
# Substitute the bracketed placeholder before running: set `sm_paths` to YOUR own edited
# paths within this submodule (space-separated, relative to the submodule root), e.g.
#   sm_paths="scripts/src/foo/bar.info.ts scripts/src/foo/bar.ts"
# Keep the `-- $sm_paths` limiter — path scoping is the whole point of this flow: it migrates
# only this session's edits and leaves a concurrent session's foreign dirt in the submodule
# untouched. Do NOT drop the limiter to "capture everything" — that re-introduces the data-loss
# this flow exists to avoid.
# `git submodule foreach` exposes `$displaypath` as a documented var; `$sm_path` expands to empty
# and would silently skip dirty submodules.
git -C "$repo_root" submodule foreach --quiet 'echo "$displaypath"' | while read -r sm; do
  if [ -n "$(git -C "$repo_root/$sm" status --porcelain)" ]; then
    git -C "$repo_root/$sm" diff --binary --cached -- $sm_paths \
      | git -C "$worktree_path/$sm" apply --binary --index
    git -C "$repo_root/$sm" diff --binary -- $sm_paths \
      | git -C "$worktree_path/$sm" apply --binary
    # plus explicit `cp` for untracked files inside the submodule
  fi
done
```

Never `git stash` the foreign dirty state to "make room" — that's the destructive move this flow exists to avoid.

## 3. Initialize submodules inside the new worktree

Only when the repo has submodules. Easy to forget — without it, every submodule directory is empty. (The bundled script initializes
the submodules passed via `--submodule`/`--all`; in the manual flow, scope the same way or init everything.)

```bash
git -C "$worktree_path" submodule update --init --recursive --single-branch
```

Each submodule lands at the recorded gitlink commit in detached HEAD. If the main checkout has uncommitted submodule bumps, the worktree
lands at the _recorded_ (older) gitlink — reset the affected submodule (`git -C "$worktree_path/<submodule>" reset --hard origin/main`)
before branching if you need the newer state.

## 4. Create per-worktree branches in submodules the agent will edit

Submodules share their gitdir (`.git/modules/<name>`) across worktrees, so two agents on the same submodule branch will fight over the ref.
Create a unique branch in each submodule the agent will modify:

```bash
# Targeted (preferred — only the submodule(s) actually being edited):
git -C "$worktree_path/<submodule>" switch -c "$branch"

# Or, blanket across every submodule:
git -C "$worktree_path" submodule foreach "git switch -c \"$branch\""
```

Skip this step for submodules that will remain untouched — extra branches just clutter the remote later.

## 5. Hand off to the agent

The agent should `cd "$worktree_path"` (or use `git -C "$worktree_path" ...`). It now has:

- Its own superproject branch
- Its own branch inside each submodule it will edit
- A working tree fully independent from other parallel worktrees

### Background subagent fan-out

Create every sibling worktree before spawning code-writing subagents and pass each absolute path in its prompt. Tell each subagent to stop
and report if setup looks broken; it must not repair worktrees, branches, the main checkout, or sibling worktrees. Keep each worktree and PR
to one independent concern.

## 6. Pushing work back

Push only repositories changed by the task. A submodule change ships through that submodule's own PR; leave its superproject gitlink
unstaged. Pin advancement happens after merge in a dedicated sync PR.

When a task has independently changed both a submodule and superproject-owned files, push the submodule branch first, then the superproject
branch:

```bash
git submodule foreach --recursive '
  current="$(git rev-parse --abbrev-ref HEAD)"
  if [ "$current" != "HEAD" ]; then
    git push --set-upstream origin "$current"
  fi
'
git push --set-upstream origin "$(git branch --show-current)"
```

Do not use this blanket push for the default path; push each changed repository directly. It remains here only as a manual fallback for a
task that intentionally changed several initialized repositories.

## 7. Teardown

As soon as the PR is opened, the worktree is no longer load-bearing — the branch and any submodule branches are mirrored on the remote.
**Tear down right after the PR opens**; don't wait for merge. The same applies when work
is abandoned.

```bash
git worktree remove "$worktree_path"
git worktree prune
git branch -D "$branch"  # delete the superproject branch if no longer needed

# For each submodule that had a per-worktree branch:
git -C "$repo_root/<submodule>" branch -D "$branch"
```

If `git worktree remove` complains about modified/untracked files, commit or discard them first — `--force` silently drops uncommitted work.

## Common pitfalls

- **Forgetting step 3.** Builds and tests fail because submodule directories are empty. In a script-built worktree, an empty submodule dir
  means it wasn't passed via `--submodule` — re-run `git -C "$worktree_path" submodule update --init --single-branch <path>` for the missing
  one.
- **Trusting the recorded gitlink when the main checkout has uncommitted submodule bumps.** The worktree lands at the older recorded commit
  — files added in newer submodule commits won't be present. Reset the submodule to the right ref (see step 3 note).
- **Skipping step 4 when two agents edit the same submodule.** They overwrite each other's HEAD in `.git/modules/<name>`.
- **Pushing the superproject before its submodule branches.** The remote rejects unreachable gitlinks. Push submodules first.
- **Running from inside another worktree.** Submodule paths resolve relative to the superproject; run from the main clone.
