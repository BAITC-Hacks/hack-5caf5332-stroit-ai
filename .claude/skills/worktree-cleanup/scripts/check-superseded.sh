#!/usr/bin/env bash
# check-superseded.sh — classify whether a stale worktree's tracked changes already
# exist on origin/<base>.
#
# Usage:
#   ./check-superseded.sh <worktree-path> [--base main] [--no-fetch]
#
# Output: STATUS<TAB>DETAIL, where STATUS is one of:
#   superseded      every tracked source change is already present on origin/<base>
#   preserved       every remaining source commit has exact remote-PR provenance
#   not-superseded  at least one source or untracked change still needs preserving
#   no-diff         no source or untracked changes exist relative to origin/<base>

set -euo pipefail

wt=""
base="main"
fetch=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base) base="$2"; shift 2 ;;
    --no-fetch) fetch=0; shift ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    -*) echo "unknown flag: $1" >&2; exit 2 ;;
    *)
      if [[ -z "$wt" ]]; then wt="$1"; shift
      else echo "extra positional arg: $1" >&2; exit 2; fi ;;
  esac
done

[[ -n "$wt" ]] || { echo "usage: $0 <worktree-path> [--base main] [--no-fetch]" >&2; exit 2; }
wt="$(cd "$wt" 2>/dev/null && pwd -P)" || { echo "not a directory: $wt" >&2; exit 2; }
git -C "$wt" rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo "not a git worktree: $wt" >&2
  exit 2
}

tmp_paths=""
cleanup() {
  local path
  while IFS= read -r path; do
    [[ -n "$path" ]] && rm -f "$path" "${path}.lock"
  done <<< "$tmp_paths"
  return 0
}
trap cleanup EXIT

new_tmp_path=""
new_tmp() {
  new_tmp_path="$(mktemp "${TMPDIR:-/tmp}/worktree-supersession.XXXXXX")"
  tmp_paths+="$new_tmp_path"$'\n'
}

reason=""
has_changes=0
has_preserved_changes=0

untracked_source_paths() {
  git -C "$1" ls-files --others --exclude-standard | \
    awk '$0 !~ /(^|\/)node_modules(\/|$)/ && $0 !~ /\.profraw$/'
}

real_diff_paths() {
  local repo="$1" compare_ref="$2" path old_mode new_mode

  while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    old_mode="$(git -C "$repo" ls-tree "$compare_ref" -- "$path" | awk 'NR==1 {print $1}')"
    new_mode="$(git -C "$repo" ls-files --stage -- "$path" | awk 'NR==1 {print $1}')"
    [[ "$old_mode" == "160000" || "$new_mode" == "160000" ]] && continue
    printf '%s\n' "$path"
  done < <(git -C "$repo" diff --name-only "$compare_ref")
}

has_uncommitted_source_changes() {
  [[ -n "$(real_diff_paths "$1" HEAD)" ]]
}

commit_has_source_changes() {
  local repo="$1" commit="$2" parent

  parent="$(git -C "$repo" rev-parse --verify --quiet "$commit^1" 2>/dev/null || true)"
  [[ -n "$parent" ]] || return 1
  git -C "$repo" diff --raw "$parent" "$commit" | \
    awk '$2 != "160000" && $3 != "160000" { found=1 } END { exit !found }'
}

github_repository() {
  local repo="$1" origin_url

  if [[ -n "${WORKTREE_CLEANUP_GITHUB_REPO:-}" ]]; then
    printf '%s' "$WORKTREE_CLEANUP_GITHUB_REPO"
    return 0
  fi

  origin_url="$(git -C "$repo" remote get-url origin 2>/dev/null || true)"
  if [[ "$origin_url" =~ github\.com[:/]([^/]+)/([^/.]+)(\.git)?$ ]]; then
    printf '%s/%s' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
  fi
}

branch_pr_for_commit() {
  local repo="$1" github_repo="$2" branch="$3" commit="$4" owner candidates candidate_status
  local number url state merged_at commit_shas commit_status

  [[ -n "$branch" ]] || return 1
  owner="${github_repo%%/*}"
  candidate_status=0
  candidates="$("${WORKTREE_CLEANUP_GH:-gh}" api \
    -H 'Accept: application/vnd.github+json' \
    "repos/$github_repo/pulls?head=$owner:$branch&state=all&per_page=100" \
    --jq 'sort_by(if .merged_at != null then 0 elif .state == "open" then 1 else 2 end) | .[] | [.number, .html_url, .state, (.merged_at // "")] | @tsv' \
    2>/dev/null)" || candidate_status=$?
  [[ "$candidate_status" -eq 0 ]] || return 2

  while IFS=$'\t' read -r number url state merged_at; do
    [[ -n "$number" ]] || continue
    commit_status=0
    commit_shas="$("${WORKTREE_CLEANUP_GH:-gh}" api --paginate \
      -H 'Accept: application/vnd.github+json' \
      "repos/$github_repo/pulls/$number/commits" --jq '.[].sha' 2>/dev/null)" || commit_status=$?
    [[ "$commit_status" -eq 0 ]] || return 2
    if grep -Fqx "$commit" <<< "$commit_shas"; then
      printf '%s\t%s' "$url" "$state"
      return 0
    fi
  done <<< "$candidates"

  return 1
}

pr_for_commit() {
  local repo="$1" commit="$2" github_repo branch output direct_status branch_status

  github_repo="$(github_repository "$repo")"
  [[ -n "$github_repo" ]] || return 1
  direct_status=0
  output="$("${WORKTREE_CLEANUP_GH:-gh}" api \
    -H 'Accept: application/vnd.github+json' \
    "repos/$github_repo/commits/$commit/pulls" \
    --jq '.[0] | select(.) | [.html_url, .state] | @tsv' 2>/dev/null)" || direct_status=$?
  [[ "$direct_status" -eq 0 ]] || return 2
  if [[ -n "$output" ]]; then
    printf '%s' "$output"
    return 0
  fi

  branch="$(git -C "$repo" branch --show-current 2>/dev/null || true)"
  branch_status=0
  output="$(branch_pr_for_commit "$repo" "$github_repo" "$branch" "$commit")" || branch_status=$?
  [[ "$branch_status" -eq 0 ]] || return "$branch_status"
  printf '%s' "$output"
}

commits_are_pr_backed() {
  local repo="$1" target_ref="$2" label="$3" commit pr_output pr_status source_commits=0

  while IFS= read -r commit; do
    [[ -z "$commit" ]] && continue
    commit_has_source_changes "$repo" "$commit" || continue
    source_commits=1
    pr_status=0
    pr_output="$(pr_for_commit "$repo" "$commit")" || pr_status=$?
    case "$pr_status" in
      0) ;;
      1)
        reason="$label commit ${commit:0:8} has source changes absent from $target_ref and no associated remote PR"
        return 1
        ;;
      *)
        reason="could not verify GitHub PR provenance for $label commit ${commit:0:8}"
        return 2
        ;;
    esac
  done <<< "$(git -C "$repo" rev-list "$target_ref..HEAD")"

  if [[ "$source_commits" -eq 0 ]]; then
    reason="$label has source changes absent from $target_ref without a source commit to verify"
    return 1
  fi

  has_preserved_changes=1
}

check_repo() {
  local repo="$1" label="$2" target_ref merge_base patch index real_paths path pr_status

  if [[ -n "$(untracked_source_paths "$repo")" ]]; then
    reason="$label has untracked files"
    return 1
  fi

  target_ref="origin/$base"
  if [[ $fetch -eq 1 ]] && ! git -C "$repo" fetch --quiet origin "$base"; then
    reason="could not fetch $target_ref for $label"
    return 2
  fi
  if ! git -C "$repo" rev-parse --verify --quiet "${target_ref}^{commit}" >/dev/null; then
    reason="$label has no $target_ref"
    return 2
  fi
  if ! merge_base="$(git -C "$repo" merge-base "$target_ref" HEAD)"; then
    reason="$label and $target_ref have no merge base"
    return 1
  fi

  real_paths="$(real_diff_paths "$repo" "$merge_base")"
  [[ -n "$real_paths" ]] || return 0

  local -a paths=()
  while IFS= read -r path; do
    [[ -n "$path" ]] && paths+=("$path")
  done <<< "$real_paths"

  new_tmp
  patch="$new_tmp_path"
  git -C "$repo" diff --binary --full-index --no-ext-diff --no-renames "$merge_base" -- "${paths[@]}" >"$patch"
  [[ -s "$patch" ]] || return 0
  has_changes=1

  new_tmp
  index="$new_tmp_path"
  rm -f "$index"
  if ! GIT_INDEX_FILE="$index" git -C "$repo" read-tree "$target_ref"; then
    reason="could not read $target_ref for $label"
    return 2
  fi

  # A reverse application against a temporary index proves current main already
  # contains every hunk, without changing the candidate worktree.
  if GIT_INDEX_FILE="$index" git -C "$repo" apply --cached --reverse --check "$patch" >/dev/null 2>&1; then
    return 0
  fi

  if has_uncommitted_source_changes "$repo"; then
    reason="$label has uncommitted source changes absent from $target_ref"
    return 1
  fi

  pr_status=0
  commits_are_pr_backed "$repo" "$target_ref" "$label" || pr_status=$?
  return "$pr_status"
}

repo_paths="$wt"
# shellcheck disable=SC2016 # $displaypath is evaluated by each submodule shell.
sub_paths="$(git -C "$wt" submodule foreach --recursive --quiet 'printf "%s\n" "$displaypath"' 2>/dev/null || true)"
while IFS= read -r sub_path; do
  [[ -n "$sub_path" ]] && repo_paths+=$'\n'"$wt/$sub_path"
done <<< "$sub_paths"

while IFS= read -r repo; do
  [[ -n "$repo" ]] || continue
  label="${repo#"$wt"/}"
  [[ "$label" == "$repo" ]] && label="superproject"

  check_status=0
  check_repo "$repo" "$label" || check_status=$?
  case "$check_status" in
    0) ;;
    1) printf 'not-superseded\t%s\n' "$reason"; exit 0 ;;
    *) echo "$reason" >&2; exit 2 ;;
  esac
done <<< "$repo_paths"

if [[ $has_changes -eq 0 ]]; then
  printf 'no-diff\tno source or untracked changes relative to origin/%s\n' "$base"
elif [[ $has_preserved_changes -eq 1 ]]; then
  printf 'preserved\tevery remaining source commit has exact remote-PR provenance\n'
else
  printf 'superseded\tevery tracked source change is already present on origin/%s\n' "$base"
fi
