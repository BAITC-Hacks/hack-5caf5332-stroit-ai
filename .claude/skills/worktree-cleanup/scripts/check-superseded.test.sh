#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$here/check-superseded.sh"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/check-superseded-test.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

commit() {
  git -C "$1" -c commit.gpgSign=false add .
  git -C "$1" -c commit.gpgSign=false commit -qm "$2"
}

assert_status() {
  local expected="$1" repo="$2" result status
  result="$("$script" "$repo")"
  status="${result%%$'\t'*}"
  if [[ "$status" != "$expected" ]]; then
    echo "expected $expected for $repo, got: $result" >&2
    exit 1
  fi
}

assert_pr_backed_status() {
  local expected="$1" repo="$2" result status
  result="$(WORKTREE_CLEANUP_GH="$fake_gh" WORKTREE_CLEANUP_GITHUB_REPO=durable-alpha/test \
    WORKTREE_CLEANUP_FAKE_DIRECT_PR=$'https://github.com/durable-alpha/test/pull/1\tclosed' \
    "$script" "$repo")"
  status="${result%%$'\t'*}"
  if [[ "$status" != "$expected" ]]; then
    echo "expected $expected for $repo, got: $result" >&2
    exit 1
  fi
}

assert_branch_pr_status() {
  local expected="$1" repo="$2" pr_commits="$3" result status
  result="$(WORKTREE_CLEANUP_GH="$fake_gh" WORKTREE_CLEANUP_GITHUB_REPO=durable-alpha/test \
    WORKTREE_CLEANUP_FAKE_BRANCH_PR=$'42\thttps://github.com/durable-alpha/test/pull/42\topen\t' \
    WORKTREE_CLEANUP_FAKE_PR_COMMITS="$pr_commits" \
    "$script" "$repo")"
  status="${result%%$'\t'*}"
  if [[ "$status" != "$expected" ]]; then
    echo "expected $expected for $repo, got: $result" >&2
    exit 1
  fi
}

remote="$tmp/remote.git"
seed="$tmp/seed"
git init --bare -q "$remote"
git clone -q "$remote" "$seed"
git -C "$seed" config user.email test@example.com
git -C "$seed" config user.name test
printf 'base\n' >"$seed/message.txt"
commit "$seed" "base"
git -C "$seed" branch -M main
git -C "$seed" push -qu origin main
git -C "$remote" symbolic-ref HEAD refs/heads/main

fake_gh="$tmp/gh"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -euo pipefail' \
  'case "$*" in' \
  '  */commits/*/pulls*) printf "%s\\n" "${WORKTREE_CLEANUP_FAKE_DIRECT_PR:-}" ;;' \
  '  *pulls\?head=*) printf "%s\\n" "${WORKTREE_CLEANUP_FAKE_BRANCH_PR:-}" ;;' \
  '  */pulls/*/commits*) printf "%s\\n" "${WORKTREE_CLEANUP_FAKE_PR_COMMITS:-}" ;;' \
  'esac' >"$fake_gh"
chmod +x "$fake_gh"

stale="$tmp/stale"
git clone -q "$remote" "$stale"
git -C "$stale" config user.email test@example.com
git -C "$stale" config user.name test
git -C "$stale" checkout -qb stale
printf 'feature\n' >"$stale/message.txt"
commit "$stale" "stale feature"

current="$tmp/current"
git clone -q "$remote" "$current"
git -C "$current" config user.email test@example.com
git -C "$current" config user.name test
printf 'feature\n' >"$current/message.txt"
commit "$current" "independent feature"
git -C "$current" push -q origin main

assert_status superseded "$stale"

needs_pr="$tmp/needs-pr"
git clone -q "$remote" "$needs_pr"
git -C "$needs_pr" config user.email test@example.com
git -C "$needs_pr" config user.name test
git -C "$needs_pr" checkout -qb needs-pr
printf 'different\n' >"$needs_pr/message.txt"
commit "$needs_pr" "different feature"
assert_status not-superseded "$needs_pr"

pr_backed="$tmp/pr-backed"
git clone -q "$remote" "$pr_backed"
git -C "$pr_backed" config user.email test@example.com
git -C "$pr_backed" config user.name test
git -C "$pr_backed" checkout -qb pr-backed
printf 'remote-pr\n' >"$pr_backed/message.txt"
commit "$pr_backed" "remote PR feature"
assert_pr_backed_status preserved "$pr_backed"

branch_pr_backed="$tmp/branch-pr-backed"
git clone -q "$remote" "$branch_pr_backed"
git -C "$branch_pr_backed" config user.email test@example.com
git -C "$branch_pr_backed" config user.name test
git -C "$branch_pr_backed" checkout -qb branch-pr-backed
printf 'branch remote-pr\n' >"$branch_pr_backed/message.txt"
commit "$branch_pr_backed" "branch PR feature"
branch_pr_commit="$(git -C "$branch_pr_backed" rev-parse HEAD)"
assert_branch_pr_status preserved "$branch_pr_backed" "$branch_pr_commit"
assert_branch_pr_status not-superseded "$branch_pr_backed" deadbeef

dirty="$tmp/dirty"
git clone -q "$remote" "$dirty"
printf 'unsaved\n' >"$dirty/message.txt"
assert_status not-superseded "$dirty"

untracked="$tmp/untracked"
git clone -q "$remote" "$untracked"
printf 'left behind\n' >"$untracked/leftover.txt"
assert_status not-superseded "$untracked"

generated="$tmp/generated"
git clone -q "$remote" "$generated"
mkdir -p "$generated/node_modules"
touch "$generated/default.profraw"
assert_status no-diff "$generated"

no_diff="$tmp/no-diff"
git clone -q "$remote" "$no_diff"
assert_status no-diff "$no_diff"

gitlink_only="$tmp/gitlink-only"
git clone -q "$remote" "$gitlink_only"
git -C "$gitlink_only" config user.email test@example.com
git -C "$gitlink_only" config user.name test
git -C "$gitlink_only" checkout -qb gitlink-only
gitlink_oid="$(git -C "$gitlink_only" rev-parse HEAD)"
git -C "$gitlink_only" update-index --add --cacheinfo "160000,$gitlink_oid,nested"
git -C "$gitlink_only" -c commit.gpgSign=false commit -qm "gitlink only"
assert_status no-diff "$gitlink_only"

echo "check-superseded tests passed"
