#!/usr/bin/env bash
set -euo pipefail

test_root="$(mktemp -d)"
trap 'rm -rf "$test_root"' EXIT

remote="$test_root/remote.git"
repo="$test_root/repo"
landing_remote="$test_root/landing-remote.git"
landing_repo="$test_root/landing"
bun_log="$test_root/bun.log"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

git init --bare "$remote" >/dev/null
git init --bare "$landing_remote" >/dev/null
git init -b main "$repo" >/dev/null
git -C "$repo" config user.name "Worktree install test"
git -C "$repo" config user.email "worktree-install-test@example.com"

mkdir -p "$repo/.claude/skills/worktree-submodules/scripts" "$test_root/bin"
cp "$script_dir/../scripts/create-worktree.sh" "$repo/.claude/skills/worktree-submodules/scripts/create-worktree.sh"
printf '{"name":"worktree-install-test"}\n' >"$repo/package.json"
printf '' >"$repo/bun.lock"

git init -b main "$landing_repo" >/dev/null
git -C "$landing_repo" config user.name "Landing install test"
git -C "$landing_repo" config user.email "landing-install-test@example.com"
printf '{"name":"landing-install-test"}\n' >"$landing_repo/package.json"
printf '' >"$landing_repo/bun.lock"
git -C "$landing_repo" add bun.lock package.json
git -C "$landing_repo" commit -m "Landing fixture" >/dev/null
git -C "$landing_repo" remote add origin "$landing_remote"
git -C "$landing_repo" push -u origin main >/dev/null
git -C "$landing_remote" symbolic-ref HEAD refs/heads/main
git -c protocol.file.allow=always -C "$repo" submodule add "$landing_remote" landing >/dev/null

printf '%s\n' \
  '#!/usr/bin/env bash' \
  'printf '\''%s\n'\'' "$*" >>"$BUN_LOG"' \
  >"$test_root/bin/bun"
chmod +x "$repo/.claude/skills/worktree-submodules/scripts/create-worktree.sh" "$test_root/bin/bun"

git -C "$repo" add .gitmodules bun.lock landing package.json .claude
git -C "$repo" commit -m "Fixture" >/dev/null
git -C "$repo" remote add origin "$remote"
git -C "$repo" push -u origin main >/dev/null

GIT_ALLOW_PROTOCOL=file PATH="$test_root/bin:$PATH" BUN_LOG="$bun_log" \
  "$repo/.claude/skills/worktree-submodules/scripts/create-worktree.sh" skipped >/dev/null
test ! -e "$bun_log"

output="$(
  GIT_ALLOW_PROTOCOL=file PATH="$test_root/bin:$PATH" BUN_LOG="$bun_log" \
    "$repo/.claude/skills/worktree-submodules/scripts/create-worktree.sh" installed \
      --install-dependencies --submodule landing
)"
worktree_path="$(printf '%s\n' "$output" | sed -n 's/^worktree ready at: //p')"

test -d "$worktree_path"
grep -Fqx "install --cwd $worktree_path --frozen-lockfile --ignore-scripts" "$bun_log"
grep -Fqx "install --cwd $worktree_path/landing --frozen-lockfile --ignore-scripts" "$bun_log"
test "$(wc -l <"$bun_log")" -eq 2
printf '%s\n' "$output" | grep -Fq 'dependencies=.,landing'

help="$($repo/.claude/skills/worktree-submodules/scripts/create-worktree.sh --help)"
printf '%s\n' "$help" | grep -Fq -- '--install-dependencies'
