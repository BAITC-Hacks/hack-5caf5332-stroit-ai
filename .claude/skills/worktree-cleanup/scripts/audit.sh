#!/usr/bin/env bash
# audit.sh — emit TSV rows describing each non-main worktree of a git repo.
#
# Columns: PATH BRANCH STATE AGE ACTIVE SUPER_DIRTY SUB_DIRTY MERGED LOCKED PR_URL PR_STATE NOTES
#
# - AGE: last-COMMIT age (`git log -1`), NOT session activity — a worktree parked at
#   origin/main shows main's last-commit age even if it was created two minutes ago.
# - ACTIVE: y when any file outside .git/node_modules was modified in the last
#   30 minutes — the live-concurrent-session signal. Judge activity by this, never AGE.
# - SUPER_DIRTY / SUB_DIRTY: porcelain lines minus "gitlink-only" dirt. A ` M <name>`
#   line at the top level of `status --porcelain` is the per-worktree submodule pointer
#   diverging from the recorded gitlink — not a real edit. Same filter recursively.
# - MERGED: y/n vs origin/<base>. Default base=main; override with --base.
# - PR_URL/PR_STATE: a PR containing this exact HEAD commit. PR_STATE distinguishes `open`,
#   `merged`, and `closed-unmerged`; branch lookup is used only to find candidate PRs, then
#   the PR commit list proves the exact commit. Pass --also-check <owner/repo> only when the
#   same commit can exist in that repository.
#
# Usage:
#   ./audit.sh [--main-root <path>] [--base main] [--no-fetch] \
#              [--also-check owner/repo ...] [--header]

set -euo pipefail

main_root=""
base="main"
fetch=1
emit_header=0
also_check=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --main-root)  main_root="$2"; shift 2 ;;
    --base)       base="$2"; shift 2 ;;
    --no-fetch)   fetch=0; shift ;;
    --header)     emit_header=1; shift ;;
    --also-check) also_check+=("$2"); shift 2 ;;
    -h|--help)    sed -n '2,18p' "$0"; exit 0 ;;
    *)            echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$main_root" ]]; then
  main_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  [[ -z "$main_root" ]] && { echo "not in a git repo; pass --main-root" >&2; exit 2; }
fi

origin_url="$(git -C "$main_root" remote get-url origin 2>/dev/null || true)"
primary_repo=""
if [[ "$origin_url" =~ github\.com[:/]([^/]+)/([^/.]+)(\.git)?$ ]]; then
  primary_repo="${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
fi

[[ $fetch -eq 1 ]] && git -C "$main_root" fetch -q origin "$base" 2>/dev/null || true

# `-newer <ref-file>` instead of -newermt: stock macOS find and bfs disagree on
# every timestamp string format, but both take a reference file.
active_ref="$(mktemp "${TMPDIR:-/tmp/claude}/wt-audit-active-ref.XXXXXX")"
trap 'rm -f "$active_ref"' EXIT
touch -t "$(date -v-30M +%Y%m%d%H%M.%S 2>/dev/null || date -d '30 minutes ago' +%Y%m%d%H%M.%S)" "$active_ref"

recently_touched() {
  local root="$1"
  [[ -n "$(find "$root" \( -name .git -o -name node_modules \) -prune -o -type f -newer "$active_ref" -print -quit 2>/dev/null)" ]] \
    && echo y || echo n
}

# Count porcelain lines that are not gitlink dirt or generated build artifacts.
# Drops top-level gitlink divergence, `node_modules`, and LLVM `.profraw` profiles.
count_real_dirty() {
  local raw="$1"
  [[ -z "$raw" ]] && { echo 0; return; }
  printf '%s\n' "$raw" | \
    grep -vE '^.M [^ /]+$|^\?\? (.+/)?node_modules/?$|^\?\? .*\.profraw$' | \
    grep -cE '\S' || true
}

branch_pr_lookup() {
  local repo="$1" commit="$2" branch="$3" owner candidates number url state merged_at shas

  [[ -n "$branch" ]] || return 0
  owner="${repo%%/*}"
  candidates="$("${WORKTREE_CLEANUP_GH:-gh}" api -H 'Accept: application/vnd.github+json' \
    "repos/$repo/pulls?head=$owner:$branch&state=all&per_page=100" \
    --jq 'sort_by(if .merged_at != null then 0 elif .state == "open" then 1 else 2 end) | .[] | [.number, .html_url, .state, (.merged_at // "")] | @tsv' \
    2>/dev/null || true)"

  while IFS=$'\t' read -r number url state merged_at; do
    [[ -n "$number" ]] || continue
    shas="$("${WORKTREE_CLEANUP_GH:-gh}" api --paginate -H 'Accept: application/vnd.github+json' \
      "repos/$repo/pulls/$number/commits" --jq '.[].sha' 2>/dev/null || true)"
    if grep -Fqx "$commit" <<< "$shas"; then
      printf '%s\t%s\t%s' "$url" "$state" "$merged_at"
      return 0
    fi
  done <<< "$candidates"
}

pr_lookup() {
  local repo="$1" commit="$2" branch="$3" raw
  [[ -z "$repo" || -z "$commit" ]] && return 0
  raw="$("${WORKTREE_CLEANUP_GH:-gh}" api -H 'Accept: application/vnd.github+json' \
    "repos/$repo/commits/$commit/pulls" \
    --jq 'sort_by(if .merged_at != null then 0 elif .state == "open" then 1 else 2 end) | .[0] | select(.) | [.html_url, .state, (.merged_at // "")] | @tsv' \
    2>/dev/null || true)"
  [[ -n "$raw" ]] && { printf '%s' "$raw"; return 0; }
  branch_pr_lookup "$repo" "$commit" "$branch"
}

[[ $emit_header -eq 1 ]] && \
  printf 'PATH\tBRANCH\tSTATE\tAGE\tACTIVE\tSUPER_DIRTY\tSUB_DIRTY\tMERGED\tLOCKED\tPR_URL\tPR_STATE\tNOTES\n'

# Parse `worktree list --porcelain`. Records are separated by blank lines; the FIRST
# record is the main worktree, which we skip.
porcelain="$(git -C "$main_root" worktree list --porcelain)"

# Split into blocks via awk (RS=''); print one block per line with fields tab-joined.
# Then iterate with `read -r` so each iteration is one worktree block.
echo "$porcelain" | awk -v RS='' -v ORS='\n' '{gsub(/\n/, "\t"); print}' | \
while IFS= read -r block; do
  [[ -z "$block" ]] && continue

  wt="";       head_sha=""; branch=""; detached=0; locked=0
  IFS=$'\t' read -ra fields <<< "$block"
  for f in "${fields[@]}"; do
    case "$f" in
      worktree\ *) wt="${f#worktree }" ;;
      HEAD\ *)     head_sha="${f#HEAD }" ;;
      branch\ *)   branch="${f#branch }" ;;
      detached)    detached=1 ;;
      locked|locked\ *) locked=1 ;;
    esac
  done

  # First block is the main worktree — skip.
  if [[ "$wt" == "$main_root" ]]; then continue; fi

  branch="${branch#refs/heads/}"
  if [[ $detached -eq 1 ]]; then
    state="detached"
    br_label="(detached:${head_sha:0:8})"
  else
    state="branch"
    br_label="$branch"
  fi

  super_raw="$(git -C "$wt" status --porcelain --ignore-submodules=dirty 2>/dev/null || true)"
  super_dirty="$(count_real_dirty "$super_raw")"

  sub_raw="$(git -C "$wt" submodule foreach --recursive --quiet 'git status --porcelain' 2>/dev/null || true)"
  sub_dirty="$(count_real_dirty "$sub_raw")"

  age="$(git -C "$wt" log -1 --format='%cr' 2>/dev/null || echo unknown)"
  active="$(recently_touched "$wt")"

  merged="n"
  git -C "$wt" merge-base --is-ancestor HEAD "origin/$base" 2>/dev/null && merged="y"

  pr_url=""; pr_state=""
  if [[ "$state" == "branch" ]]; then
    line="$(pr_lookup "$primary_repo" "$head_sha" "$branch")"
    if [[ -z "$line" ]]; then
      for repo in "${also_check[@]:-}"; do
        line="$(pr_lookup "$repo" "$head_sha" "$branch")"
        [[ -n "$line" ]] && break
      done
    fi
    if [[ -n "$line" ]]; then
      pr_url="${line%%	*}"
      pr_metadata="${line#*	}"
      raw_pr_state="${pr_metadata%%	*}"
      merged_at="${pr_metadata#*	}"
      if [[ "$raw_pr_state" == "closed" && -n "$merged_at" && "$merged_at" != "$pr_metadata" ]]; then
        pr_state="merged"
      elif [[ "$raw_pr_state" == "closed" ]]; then
        pr_state="closed-unmerged"
      else
        pr_state="$raw_pr_state"
      fi
    fi
  fi

  notes=""
  [[ $locked -eq 1 ]] && notes="locked"

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$wt" "$br_label" "$state" "$age" "$active" \
    "$super_dirty" "$sub_dirty" "$merged" \
    "$([[ $locked -eq 1 ]] && echo y || echo n)" \
    "$pr_url" "$pr_state" "$notes"
done
