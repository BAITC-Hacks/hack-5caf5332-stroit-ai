#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$here/remove-worktree.sh"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/remove-worktree-test.XXXXXX")"
main=""
remaining=""

cleanup() {
  if [[ -n "$main" && -e "$main/.git" && -n "$remaining" && -d "$remaining" ]]; then
    git -C "$main" worktree remove --force "$remaining" >/dev/null 2>&1 || true
  fi
  rm -rf "$tmp"
}
trap cleanup EXIT

commit() {
  git -C "$1" -c commit.gpgSign=false add .
  git -C "$1" -c commit.gpgSign=false commit -qm "$2"
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
printf '%s\n' '#!/usr/bin/env bash' 'printf "https://github.com/durable-alpha/test/pull/1\\tclosed\\t2026-07-21T00:00:00Z\\n"' >"$fake_gh"
chmod +x "$fake_gh"

main="$tmp/main"
git clone -q "$remote" "$main"
git -C "$main" config user.email test@example.com
git -C "$main" config user.name test

superseded="$tmp/superseded"
git -C "$main" worktree add -qb stale "$superseded"
superseded="$(cd "$superseded" && pwd -P)"
git -C "$superseded" config user.email test@example.com
git -C "$superseded" config user.name test
printf 'feature\n' >"$superseded/message.txt"

current="$tmp/current"
git clone -q "$remote" "$current"
git -C "$current" config user.email test@example.com
git -C "$current" config user.name test
printf 'feature\n' >"$current/message.txt"
commit "$current" "independent feature"
git -C "$current" push -q origin main

"$script" "$superseded" --main-root "$main" --superseded >/dev/null
[[ ! -d "$superseded" ]] || { echo "superseded worktree was not removed" >&2; exit 1; }
git -C "$main" show-ref --verify --quiet refs/heads/stale && {
  echo "superseded branch was not removed" >&2
  exit 1
}

generated="$tmp/generated"
git -C "$main" worktree add -qb generated "$generated"
generated="$(cd "$generated" && pwd -P)"
mkdir -p "$generated/node_modules"
touch "$generated/default.profraw"
"$script" "$generated" --main-root "$main" >/dev/null
[[ ! -d "$generated" ]] || { echo "generated-only worktree was not removed" >&2; exit 1; }

preserved="$tmp/preserved"
git -C "$main" worktree add -qb pr-backed "$preserved"
preserved="$(cd "$preserved" && pwd -P)"
git -C "$preserved" config user.email test@example.com
git -C "$preserved" config user.name test
printf 'kept by remote PR\n' >"$preserved/message.txt"
commit "$preserved" "remote PR feature"

WORKTREE_CLEANUP_GH="$fake_gh" WORKTREE_CLEANUP_GITHUB_REPO=durable-alpha/test \
  "$script" "$preserved" --main-root "$main" --preserved >/dev/null
[[ ! -d "$preserved" ]] || { echo "PR-backed worktree was not removed" >&2; exit 1; }
git -C "$main" show-ref --verify --quiet refs/heads/pr-backed && {
  echo "PR-backed branch was not removed" >&2
  exit 1
}

remaining="$tmp/remaining"
git -C "$main" worktree add -qb remaining "$remaining"
remaining="$(cd "$remaining" && pwd -P)"
git -C "$remaining" config user.email test@example.com
git -C "$remaining" config user.name test
printf 'still needed\n' >"$remaining/message.txt"

if "$script" "$remaining" --main-root "$main" --superseded >/dev/null 2>&1; then
  echo "non-superseded worktree was removed" >&2
  exit 1
fi
[[ -d "$remaining" ]] || { echo "non-superseded worktree disappeared" >&2; exit 1; }

# create-worktree.sh materializes submodules with --single-branch, so a submodule tip parked on a
# live topic branch is invisible to a configured fetch and must not read as local-only.
# git blocks the file transport for submodule clones by default; env-config reaches the children it
# spawns, which repo-local config does not.
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=protocol.file.allow GIT_CONFIG_VALUE_0=always
sm_remote="$tmp/sub.git"
git init --bare -q "$sm_remote"
sm_seed="$tmp/sub-seed"
git clone -q "$sm_remote" "$sm_seed"
git -C "$sm_seed" config user.email test@example.com
git -C "$sm_seed" config user.name test
printf 'sub base\n' >"$sm_seed/sub.txt"
commit "$sm_seed" "sub base"
git -C "$sm_seed" branch -M main
git -C "$sm_seed" push -qu origin main
git -C "$sm_remote" symbolic-ref HEAD refs/heads/main
git -C "$sm_seed" checkout -q -b topic
printf 'sub topic\n' >>"$sm_seed/sub.txt"
commit "$sm_seed" "sub topic"
git -C "$sm_seed" push -q origin topic
sm_topic_oid="$(git -C "$sm_seed" rev-parse HEAD)"

super_remote="$tmp/super.git"
git init --bare -q "$super_remote"
super_seed="$tmp/super-seed"
git clone -q "$super_remote" "$super_seed"
git -C "$super_seed" config user.email test@example.com
git -C "$super_seed" config user.name test
printf 'super\n' >"$super_seed/readme.txt"
commit "$super_seed" "super base"
git -C "$super_seed" branch -M main
git -C "$super_seed" submodule add -q "$sm_remote" sub
git -C "$super_seed/sub" fetch -q origin topic
git -C "$super_seed/sub" checkout -q "$sm_topic_oid"
commit "$super_seed" "pin sub to topic tip"
git -C "$super_seed" push -qu origin main
git -C "$super_remote" symbolic-ref HEAD refs/heads/main

sm_main="$tmp/super-main"
git clone -q "$super_remote" "$sm_main"
git -C "$sm_main" config user.email test@example.com
git -C "$sm_main" config user.name test

sm_wt="$tmp/super-wt"
git -C "$sm_main" worktree add -q -b sub-guard "$sm_wt"
sm_wt="$(cd "$sm_wt" && pwd -P)"
git -C "$sm_wt" submodule update --init --single-branch --quiet
[[ "$(git -C "$sm_wt/sub" rev-parse HEAD)" == "$sm_topic_oid" ]] || {
  echo "fixture: submodule did not land on the topic tip" >&2
  exit 1
}
git -C "$sm_wt/sub" branch -r --contains "$sm_topic_oid" 2>/dev/null | grep -q . && {
  echo "fixture: single-branch clone unexpectedly already tracks the topic branch" >&2
  exit 1
}

if ! "$script" "$sm_wt" --main-root "$sm_main" >/dev/null 2>&1; then
  echo "submodule tip on a live remote topic branch was wrongly refused as local-only" >&2
  exit 1
fi
[[ ! -d "$sm_wt" ]] || { echo "remote-backed submodule worktree was not removed" >&2; exit 1; }

# The widened probe must not soften the guard: a tip the remote has never seen still blocks teardown.
local_wt="$tmp/super-wt-local"
git -C "$sm_main" worktree add -q -b sub-local "$local_wt"
local_wt="$(cd "$local_wt" && pwd -P)"
git -C "$local_wt" submodule update --init --single-branch --quiet
git -C "$local_wt/sub" config user.email test@example.com
git -C "$local_wt/sub" config user.name test
git -C "$local_wt/sub" checkout -q -b local-work
printf 'never pushed\n' >>"$local_wt/sub/sub.txt"
commit "$local_wt/sub" "local-only submodule work"

if "$script" "$local_wt" --main-root "$sm_main" >/dev/null 2>&1; then
  echo "local-only submodule commit was wrongly torn down" >&2
  exit 1
fi
[[ -d "$local_wt" ]] || { echo "local-only submodule worktree disappeared" >&2; exit 1; }
git -C "$sm_main" worktree remove --force "$local_wt" >/dev/null 2>&1 || true

echo "remove-worktree supersession tests passed"
