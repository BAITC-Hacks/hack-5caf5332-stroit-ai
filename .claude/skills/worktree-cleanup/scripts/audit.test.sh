#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$here/audit.sh"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/worktree-audit-test.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

remote="$tmp/remote.git"
main="$tmp/main"
candidate="$tmp/candidate"
fake_bin="$tmp/bin"
mkdir -p "$fake_bin"

git init --bare -q "$remote"
git clone -q "$remote" "$main"
git -C "$main" config user.email test@example.com
git -C "$main" config user.name test
printf 'base\n' >"$main/message.txt"
git -C "$main" -c commit.gpgSign=false add message.txt
git -C "$main" -c commit.gpgSign=false commit -qm base
git -C "$main" branch -M main
git -C "$main" push -qu origin main
git -C "$remote" symbolic-ref HEAD refs/heads/main
git -C "$main" remote set-url origin https://github.com/durable-alpha/test.git
git -C "$main" worktree add -qb candidate "$candidate"
mkdir -p "$candidate/node_modules"
touch "$candidate/default.profraw"

fake_gh="$fake_bin/gh"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -euo pipefail' \
  'args="$*"' \
  'filter=""' \
  'while [[ $# -gt 0 ]]; do' \
  '  if [[ "$1" == "--jq" ]]; then filter="$2"; shift 2; else shift; fi' \
  'done' \
  'case "$args" in' \
  '  */commits/*/pulls*) response="${WORKTREE_CLEANUP_FAKE_DIRECT_RESPONSE:-[]}" ;;' \
  '  *pulls\?head=*) response="${WORKTREE_CLEANUP_FAKE_BRANCH_RESPONSE:-[]}" ;;' \
  '  */pulls/*/commits*) response="${WORKTREE_CLEANUP_FAKE_PR_COMMITS:-[]}" ;;' \
  '  *) response="[]" ;;' \
  'esac' \
  'printf "%s\\n" "$response" | jq -r "$filter"' >"$fake_gh"
chmod +x "$fake_gh"

assert_pr_state() {
  local expected="$1" response="$2" result actual dirty
  result="$(PATH="$fake_bin:$PATH" WORKTREE_CLEANUP_FAKE_DIRECT_RESPONSE="$response" \
    "$script" --main-root "$main" --no-fetch)"
  actual="$(awk -F $'\t' '$2 == "candidate" { print $11 }' <<< "$result")"
  if [[ "$actual" != "$expected" ]]; then
    echo "expected PR state $expected, got: $result" >&2
    exit 1
  fi
  dirty="$(awk -F $'\t' '$2 == "candidate" { print $6 ":" $7 }' <<< "$result")"
  if [[ "$dirty" != "0:0" ]]; then
    echo "expected generated artifacts to be clean, got: $result" >&2
    exit 1
  fi
}

assert_branch_pr_state() {
  local expected="$1" head="$2" result actual
  result="$(PATH="$fake_bin:$PATH" \
    WORKTREE_CLEANUP_FAKE_BRANCH_RESPONSE='[{"number":4,"html_url":"https://github.com/durable-alpha/test/pull/4","state":"open","merged_at":null}]' \
    WORKTREE_CLEANUP_FAKE_PR_COMMITS="[{\"sha\":\"$head\"}]" \
    "$script" --main-root "$main" --no-fetch)"
  actual="$(awk -F $'\t' '$2 == "candidate" { print $11 }' <<< "$result")"
  if [[ "$actual" != "$expected" ]]; then
    echo "expected branch PR state $expected, got: $result" >&2
    exit 1
  fi
}

assert_pr_state merged '[{"html_url":"https://github.com/durable-alpha/test/pull/1","state":"closed","merged_at":"2026-07-21T00:00:00Z"}]'
assert_pr_state closed-unmerged '[{"html_url":"https://github.com/durable-alpha/test/pull/2","state":"closed","merged_at":null}]'
assert_pr_state open '[{"html_url":"https://github.com/durable-alpha/test/pull/3","state":"open","merged_at":null}]'
assert_branch_pr_state open "$(git -C "$candidate" rev-parse HEAD)"

echo "audit tests passed"
