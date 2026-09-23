#!/usr/bin/env bash
# create-worktree.sh — create a sibling worktree, initializing only requested submodules.
#
# Usage:
#   ./create-worktree.sh <slug> [--ticket <ID>] [--base <branch>] [--submodule <path> ...] [--all]
#                        [--no-default-submodules] [--install-dependencies]
#                        [--depth <n>] [--jobs <n>] [--submodule-branch <submodule>:<remote-branch> ...]
#                        [--verbose]
#
# Examples:
#   ./create-worktree.sh my-feature --submodule go
#   ./create-worktree.sh add-rate-limiting --ticket S-128641 --submodule go
#   ./create-worktree.sh feed-fix --submodule scheduled/feeds --submodule-branch scheduled:main
#   ./create-worktree.sh mitm-proxy --base feat/extraction-agent --submodule-branch go:feat/stateless-extraction-agent
#   ./create-worktree.sh everything --all
#   ./create-worktree.sh quick-fix   # origin/main base, no submodules initialized
#   ./create-worktree.sh fast --all  # --jobs defaults to 8; pass --jobs 1 to serialize

# --ticket <ID> prepends the lowercased Linear identifier to the branch (and
# feat/<slug> submodule branches), so the branch is named <id>-<slug>, e.g.
# `s-128641-add-rate-limiting`. Linear's GitHub integration links and carries a
# ticket's status (In Progress on push → Done on merge) off the *branch name* —
# a PR-body mention alone links weakly and does not reliably carry status. When
# the work traces to a ticket, always pass --ticket so the branch carries the ID.
# No-op prefix if the slug already begins with the identifier.
#
# The worktree is created at ../<repo>-worktrees/<branch-slug>-<timestamp>/ alongside the
# main checkout, branched off freshly fetched origin/main by default.
# If --base is passed, a matching remote branch is fetched and used when it exists.
# DEFAULT_SUBMODULES (empty for now) are always initialized unless
# --no-default-submodules. Beyond those, only submodules named via --submodule (or
# implied by --submodule-branch) are initialized; nested paths like a/b init their
# parent chain automatically. --all inits everything. --jobs (8 by default)
# parallelizes the single-invocation --all init across submodules; the
# targeted --submodule path inits one path per `git submodule update` call, so
# --jobs only helps there if a single named path expands to several nested
# submodules. The bottleneck is per-submodule working-tree materialization,
# not the shared gitdir; pass --jobs 1 to serialize.
# Submodules are cloned shallow (last 100 commits by default; --depth <n>
# overrides, 0 = full history). If --submodule-branch is given, those
# submodules get a named branch created off the specified remote branch
# (instead of staying on detached HEAD).
#
# Full policy: .claude/skills/worktree-submodules/SKILL.md. Edge cases: MANUAL.md.
#
# Exit codes:
#   0  worktree created
#   1  error
#   2  bad args

set -euo pipefail

slug=""
ticket=""
base=""
DEFAULT_BASE="main"
jobs=8
init_all=false
depth=100
verbose=0
no_defaults=false
install_dependencies=false
# Submodules always initialized (on top of any --submodule flags). Keep this to small,
# broadly-relevant submodules. Opt out with --no-default-submodules.
declare -a DEFAULT_SUBMODULES=()
declare -a sm_init=()
declare -a sm_branches=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base)              [[ $# -ge 2 ]] || { echo "$1 requires a value" >&2; exit 2; }; base="$2"; shift 2 ;;
    --ticket)            [[ $# -ge 2 ]] || { echo "$1 requires a value" >&2; exit 2; }; ticket="$2"; shift 2 ;;
    --submodule)         [[ $# -ge 2 ]] || { echo "$1 requires a value" >&2; exit 2; }; sm_init+=("$2"); shift 2 ;;
    --all)               init_all=true; shift ;;
    --no-default-submodules) no_defaults=true; shift ;;
    --depth)             [[ $# -ge 2 ]] || { echo "$1 requires a value" >&2; exit 2; }; depth="$2"; shift 2 ;;
    --jobs)              [[ $# -ge 2 ]] || { echo "$1 requires a value" >&2; exit 2; }; jobs="$2"; shift 2 ;;
    --submodule-branch)  [[ $# -ge 2 ]] || { echo "$1 requires a value" >&2; exit 2; }; sm_branches+=("$2"); shift 2 ;;
    --verbose)           verbose=1; shift ;;
    --install-dependencies) install_dependencies=true; shift ;;
    -h|--help)           sed -n '2,/^$/p' "$0" | sed '$d'; exit 0 ;;
    -*)                  echo "unknown flag: $1" >&2; exit 2 ;;
    *)
      if [[ -z "$slug" ]]; then slug="$1"; shift
      else echo "extra positional arg: $1" >&2; exit 2; fi ;;
  esac
done

[[ -z "$slug" ]] && { echo "usage: $0 <slug> [--ticket <ID>] [--base <branch>] [--submodule <path> ...] [--all] [--no-default-submodules] [--install-dependencies] [--depth <n>] [--jobs <n>] [--submodule-branch <submodule>:<remote-branch> ...]" >&2; exit 2; }
# The slug is interpolated straight into the worktree path and branch name, so a `/`
# or `..` would let it escape the sibling worktrees dir (back into the repo) — keep it
# to a plain path segment.
[[ "$slug" =~ ^[A-Za-z0-9._-]+$ && "$slug" != "." && "$slug" != ".." ]] || { echo "slug must be a plain segment matching [A-Za-z0-9._-]+ (no slashes/spaces, not . or ..): $slug" >&2; exit 2; }

# --ticket prepends the lowercased Linear identifier to the slug so the branch is
# <id>-<slug> and Linear links/carries status off the branch name. branch_slug is
# the effective slug used for the worktree dir and every branch below; it equals
# slug when no ticket is given (backward compatible).
branch_slug="$slug"
if [[ -n "$ticket" ]]; then
  # Linear identifiers are <TEAM-KEY>-<number>, e.g. S-128641 / ENG-42.
  [[ "$ticket" =~ ^[A-Za-z][A-Za-z0-9]*-[0-9]+$ ]] || { echo "--ticket must be a Linear identifier like S-128641 or ENG-42, got: $ticket" >&2; exit 2; }
  ticket_lc="$(printf '%s' "$ticket" | tr '[:upper:]' '[:lower:]')"
  # No-op if the slug already leads with the identifier, so passing both an
  # id-prefixed slug and --ticket doesn't double it up.
  if [[ "$branch_slug" != "$ticket_lc" && "$branch_slug" != "$ticket_lc"-* ]]; then
    branch_slug="${ticket_lc}-${slug}"
  fi
fi

[[ "$depth" =~ ^[0-9]+$ ]] || { echo "--depth must be a non-negative integer, got: $depth" >&2; exit 2; }
[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || { echo "--jobs must be a positive integer, got: $jobs" >&2; exit 2; }

# Main checkout root — the parent of the shared git dir, so running from inside
# another worktree still branches off the main clone.
find_repo_root() {
  local common
  common="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" \
    || { echo "cannot find repo root" >&2; return 1; }
  dirname "$common"
}

run_quietly() {
  local cmd=("$@")
  local output_dir="${TMPDIR:-/tmp/claude}"
  local output
  mkdir -p "$output_dir"
  output="$(mktemp "$output_dir/create-worktree-output.XXXXXX")"
  if ! "${cmd[@]}" >"$output" 2>&1; then
    cat "$output" >&2
    rm -f "$output"
    return 1
  fi
  rm -f "$output"
}

run_cmd() {
  if [[ "$verbose" == "1" ]]; then
    "$@"
  else
    run_quietly "$@"
  fi
}

repo_root="$(find_repo_root)"

# macOS ships bash 3.2 (no declare -A), so dedupe by linear scan.
array_contains() {
  local needle="$1"; shift
  local x
  for x in "$@"; do [[ "$x" == "$needle" ]] && return 0; done
  return 1
}

# A submodule named in --submodule-branch must be checked out for the branch
# step to work, so it's implied into the init set.
for entry in "${sm_branches[@]+"${sm_branches[@]}"}"; do
  sm_init+=("${entry%%:*}")
done

# Always-on defaults: init these regardless of --submodule flags so every worktree
# discovers their contents. --all already inits everything; --no-default-submodules
# opts out. Prepend so they lead the (deduped) init order.
if ! $init_all && ! $no_defaults; then
  sm_init=("${DEFAULT_SUBMODULES[@]+"${DEFAULT_SUBMODULES[@]}"}" "${sm_init[@]+"${sm_init[@]}"}")
fi

# Dedupe while preserving order.
declare -a init_paths=()
for p in "${sm_init[@]+"${sm_init[@]}"}"; do
  array_contains "$p" "${init_paths[@]+"${init_paths[@]}"}" || init_paths+=("$p")
done

# Resolve a (possibly nested) submodule path into init steps of the form
# "<parent-rel>|<sm-path>", longest .gitmodules match first so e.g.
# docs/knowledge resolves as one step while scheduled/feeds becomes two.
resolve_chain() {
  local root="$repo_root" parent_rel="." rel="$1"
  while [[ -n "$rel" ]]; do
    if [[ ! -f "$root/.gitmodules" ]]; then
      echo "no .gitmodules under '$parent_rel' (parent submodule not checked out in main clone?)" >&2
      return 1
    fi
    local match=""
    while IFS= read -r p; do
      if [[ "$rel" == "$p" || "$rel" == "$p"/* ]]; then
        [[ ${#p} -gt ${#match} ]] && match="$p"
      fi
    done < <(git config -f "$root/.gitmodules" --get-regexp 'submodule\..*\.path' | awk '{print $2}')
    if [[ -z "$match" ]]; then
      echo "'$rel' is not a submodule under '$parent_rel'" >&2
      return 1
    fi
    echo "${parent_rel}|${match}"
    if [[ "$rel" == "$match" ]]; then
      rel=""
    else
      rel="${rel#"$match"/}"
    fi
    root="$root/$match"
    if [[ "$parent_rel" == "." ]]; then parent_rel="$match"; else parent_rel="$parent_rel/$match"; fi
  done
}

# Validate every requested path before touching the worktree so a typo
# doesn't leave a half-built tree behind.
declare -a init_steps=()
for p in "${init_paths[@]+"${init_paths[@]}"}"; do
  chain="$(resolve_chain "$p")" || { echo "invalid --submodule path: $p" >&2; exit 2; }
  while IFS= read -r step; do
    array_contains "$step" "${init_steps[@]+"${init_steps[@]}"}" || init_steps+=("$step")
  done <<< "$chain"
done

worktrees_root="$(dirname "$repo_root")/$(basename "$repo_root")-worktrees"

# Defense in depth: the worktrees root must sit beside the repo, never inside it —
# in-tree worktrees get walked by formatters/indexers/skill scanners. This guards
# against an unexpected root resolution; the path is a sibling by construction.
repo_root_real="$(cd "$repo_root" && pwd -P)"
worktrees_root_real="$(cd "$(dirname "$repo_root")" && pwd -P)/$(basename "$repo_root")-worktrees"
case "$worktrees_root_real/" in
  "$repo_root_real"/*) echo "refusing: worktrees root resolved inside the repo: $worktrees_root_real" >&2; exit 1 ;;
esac

ts="$(date +%Y%m%d-%H%M%S)"
wt_path="${worktrees_root}/${branch_slug}-${ts}"
branch="${branch_slug}-${ts}"

[[ -z "$base" ]] && base="$DEFAULT_BASE"

resolve_base_ref() {
  local requested="$1"
  local remote_branch="$requested"

  if [[ "$requested" == origin/* ]]; then
    remote_branch="${requested#origin/}"
    git -C "$repo_root" fetch origin "$remote_branch" 2>/dev/null || {
      echo "failed to fetch origin/$remote_branch" >&2
      return 1
    }
    echo "origin/$remote_branch"
    return
  fi

  if git -C "$repo_root" fetch origin "$requested" 2>/dev/null; then
    echo "origin/$requested"
    return
  fi

  if [[ "$requested" == "$DEFAULT_BASE" ]]; then
    echo "failed to fetch origin/$DEFAULT_BASE; refusing to fall back to local $DEFAULT_BASE" >&2
    return 1
  fi

  echo "$requested"
}

base_ref="$(resolve_base_ref "$base")" || exit 1

if $install_dependencies; then
  command -v bun >/dev/null 2>&1 || { echo "bun is required for --install-dependencies" >&2; exit 1; }
  git -C "$repo_root" cat-file -e "${base_ref}:package.json" 2>/dev/null || { echo "package.json is missing from $base_ref" >&2; exit 1; }
  git -C "$repo_root" cat-file -e "${base_ref}:bun.lock" 2>/dev/null || { echo "bun.lock is missing from $base_ref" >&2; exit 1; }
fi

if [[ "$verbose" == "1" ]]; then
  echo "repo root:   $repo_root"
  echo "worktree:    $wt_path"
  echo "branch:      $branch"
  echo "base:        $base_ref"
  echo "jobs:        $jobs"
fi

mkdir -p "$worktrees_root"

# --no-track keeps `worktree add` from writing branch upstream config. The agent sandbox
# masks .git/config with /dev/null, so that write fails the whole command; nothing here
# needs the upstream anyway, since pushes name their refspec explicitly.
run_cmd git -C "$repo_root" worktree add --no-track -b "$branch" "$wt_path" "$base_ref"

if [[ "$verbose" != "1" ]]; then
  echo "worktree ready at: $wt_path"
fi

declare -a depth_args=()
[[ "$depth" -gt 0 ]] && depth_args=(--depth "$depth")
depth_summary="$depth"
[[ "$depth" == "0" ]] && depth_summary="full"
submodule_summary="none"
if $init_all; then
  submodule_summary="all"
elif [[ ${#init_paths[@]} -gt 0 ]]; then
  submodule_summary="$(IFS=,; echo "${init_paths[*]}")"
fi

if [[ "$verbose" == "1" ]]; then
  echo ""
  echo "=== initializing submodules ==="
fi
declare -a initialized_paths=()
if $init_all; then
  run_cmd git -C "$wt_path" submodule update --init --recursive --single-branch --jobs "$jobs" "${depth_args[@]+"${depth_args[@]}"}"
  while IFS= read -r initialized_path; do
    if [[ -n "$initialized_path" ]]; then
      array_contains "$initialized_path" "${initialized_paths[@]+"${initialized_paths[@]}"}" || initialized_paths+=("$initialized_path")
    fi
  done < <(git -C "$wt_path" submodule foreach --recursive --quiet 'printf "%s\n" "$displaypath"')
elif [[ ${#init_steps[@]} -eq 0 ]]; then
  if [[ "$verbose" == "1" ]]; then
    echo "no submodules requested — pass --submodule <path> or --all to initialize any"
  fi
else
  for step in "${init_steps[@]}"; do
    parent_rel="${step%%|*}"
    sm="${step#*|}"
    if [[ "$verbose" == "1" ]]; then
      echo "--- $([[ "$parent_rel" == "." ]] || printf '%s/' "$parent_rel")$sm"
    fi
    run_cmd git -C "$wt_path/$parent_rel" submodule update --init --single-branch --jobs "$jobs" "${depth_args[@]+"${depth_args[@]}"}" "$sm"
    initialized_path="$sm"
    [[ "$parent_rel" == "." ]] || initialized_path="$parent_rel/$sm"
    array_contains "$initialized_path" "${initialized_paths[@]+"${initialized_paths[@]}"}" || initialized_paths+=("$initialized_path")
  done
fi

for entry in "${sm_branches[@]+"${sm_branches[@]}"}"; do
  sm="${entry%%:*}"
  remote_branch="${entry#*:}"
  sm_path="$wt_path/$sm"

  if [[ ! -d "$sm_path" ]]; then
    echo "warning: submodule '$sm' not found at $sm_path, skipping" >&2
    continue
  fi
  if [[ "$verbose" == "1" ]]; then
    echo ""
    echo "=== $sm: creating branch feat/${branch_slug} off origin/${remote_branch} ==="
  fi
  run_cmd git -C "$sm_path" fetch "${depth_args[@]+"${depth_args[@]}"}" origin "$remote_branch"
  run_cmd git -C "$sm_path" switch -c "feat/${branch_slug}" "origin/${remote_branch}"
done

dependencies_summary="skipped"
if $install_dependencies; then
  declare -a dependency_paths=(".")
  for initialized_path in "${initialized_paths[@]+"${initialized_paths[@]}"}"; do
    checkout="$wt_path/$initialized_path"
    if [[ -f "$checkout/package.json" && -f "$checkout/bun.lock" ]]; then
      dependency_paths+=("$initialized_path")
    fi
  done

  for dependency_path in "${dependency_paths[@]}"; do
    checkout="$wt_path"
    [[ "$dependency_path" == "." ]] || checkout="$wt_path/$dependency_path"
    if [[ "$verbose" == "1" ]]; then
      echo ""
      echo "=== installing dependencies: $dependency_path ==="
    else
      echo "installing dependencies: $dependency_path"
    fi
    run_cmd bun install --cwd "$checkout" --frozen-lockfile --ignore-scripts
  done
  dependencies_summary="$(IFS=,; echo "${dependency_paths[*]}")"
fi

if [[ "$verbose" == "1" ]]; then
  echo ""
  echo "=== done ==="
  echo "worktree ready at: $wt_path"
  echo ""
  echo "to clean up later:"
  echo "  .claude/skills/worktree-cleanup/scripts/remove-worktree.sh $wt_path"
else
  echo "initialized with jobs=$jobs depth=$depth_summary submodules=$submodule_summary dependencies=$dependencies_summary"
fi
