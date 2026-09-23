#!/usr/bin/env bash
# remove-worktree.sh — fully clean up one worktree in a single call.
#
# Encapsulates the full dance: unlock-if-locked → worktree remove → --force fallback
# (the "submodules cannot be moved" refusal is a structural git limit, not dirty state)
# → rm orphan dir if sandbox blocked git's unlink → worktree prune → branch -D in
# superproject → branch -D in every submodule that has the same branch (skipping any
# branch in use by another worktree).
#
# Refuses to touch a worktree with real uncommitted work unless --force-discard,
# --superseded, or --preserved. The verified modes prove current main or a remote PR
# already retains every source change.
# "Real" = porcelain lines minus top-level gitlink-pointer dirt.
# Also refuses when a submodule carries LOCAL-ONLY commits (no PR) that teardown would drop;
# the guard below documents which tips are at risk and why a super gitlink bump doesn't preserve.
#
# Usage:
#   ./remove-worktree.sh <worktree-path> [--main-root <path>] [--superseded|--preserved|--force-discard]
#
# Exit codes:
#   0  removed cleanly
#   2  bad args / not a known worktree
#   3  refused due to uncommitted work, unpushed submodule commits, or failed supersession verification
#   4  removal failed (orphan dir survived sandbox; manual cleanup needed)

set -euo pipefail

wt=""
main_root=""
force_discard=0
superseded=0
preserved=0
verified=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --main-root)     main_root="$2"; shift 2 ;;
    --force-discard) force_discard=1; shift ;;
    --superseded)    superseded=1; shift ;;
    --preserved)     preserved=1; shift ;;
    -h|--help)       sed -n '2,21p' "$0"; exit 0 ;;
    -*)              echo "unknown flag: $1" >&2; exit 2 ;;
    *)
      if [[ -z "$wt" ]]; then wt="$1"; shift
      else echo "extra positional arg: $1" >&2; exit 2; fi ;;
  esac
done

[[ -z "$wt" ]] && { echo "usage: $0 <worktree-path> [--main-root <path>] [--superseded|--preserved|--force-discard]" >&2; exit 2; }
[[ $((force_discard + superseded + preserved)) -le 1 ]] || {
  echo "choose at most one of --superseded, --preserved, or --force-discard" >&2
  exit 2
}
wt="${wt%/}"  # strip trailing slash

# Infer main_root from the worktree if not given.
if [[ -z "$main_root" ]]; then
  if [[ -d "$wt" ]]; then
    # WHY buffer before awk: an early-exit awk downstream of git SIGPIPEs it under pipefail,
    # and set -e then kills the whole script (observed as exit 141 mid-run).
    wt_porcelain="$(git -C "$wt" worktree list --porcelain)"
    main_root="$(awk '/^worktree / {print $2; exit}' <<< "$wt_porcelain")"
  fi
  [[ -z "$main_root" ]] && { echo "could not infer --main-root; pass explicitly" >&2; exit 2; }
fi

# Refuse to operate on the main worktree itself.
if [[ "$wt" == "$main_root" ]]; then
  echo "refusing to remove the main worktree: $wt" >&2
  exit 2
fi

# Refuse if we're currently inside the target.
cwd="$(pwd -P)"
case "$cwd" in
  "$wt"|"$wt"/*)
    echo "refusing: current dir ($cwd) is inside the target worktree; cd elsewhere first" >&2
    exit 2 ;;
esac

# Confirm the path is actually registered as a worktree (so we don't rm random dirs).
# Buffered for the same SIGPIPE reason as above (the branch/locked awk below exits early).
main_porcelain="$(git -C "$main_root" worktree list --porcelain)"
if ! awk -v p="$wt" '$1=="worktree" && $2==p {f=1} END {exit !f}' <<< "$main_porcelain"; then
  echo "not a registered worktree of $main_root: $wt" >&2
  exit 2
fi

# Pull branch + locked state from porcelain.
read -r branch locked <<< "$(
  awk -v p="$wt" -v RS='' '
    {
      if (index($0, "worktree " p "\n") || $0 ~ ("worktree " p "$")) {
        br=""; lk=0
        n = split($0, lines, "\n")
        for (i=1; i<=n; i++) {
          if (lines[i] ~ /^branch /)         { sub(/^branch refs\/heads\//, "", lines[i]); br=lines[i] }
          else if (lines[i] ~ /^locked/)     { lk=1 }
        }
        print br, lk
        exit
      }
    }
  ' <<< "$main_porcelain"
)"
locked="${locked:-0}"

if [[ $superseded -eq 1 || $preserved -eq 1 ]]; then
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  checker="$script_dir/check-superseded.sh"
  [[ -x "$checker" ]] || {
    echo "missing supersession checker: $checker" >&2
    exit 3
  }

  check_output=""
  check_exit=0
  check_output="$("$checker" "$wt")" || check_exit=$?
  if [[ $check_exit -ne 0 ]]; then
    echo "refusing: could not verify supersession for $wt" >&2
    exit 3
  fi
  check_status="${check_output%%$'\t'*}"
  if [[ $superseded -eq 1 && "$check_status" != "superseded" && "$check_status" != "no-diff" ]]; then
    echo "refusing: $wt is not superseded ($check_output)" >&2
    exit 3
  fi
  if [[ $preserved -eq 1 && "$check_status" != "preserved" && "$check_status" != "superseded" && "$check_status" != "no-diff" ]]; then
    echo "refusing: $wt is not remotely preserved ($check_output)" >&2
    exit 3
  fi

  verified=1
fi

# Safety: re-check clean state unless --force-discard.
count_real_dirty() {
  local raw="$1"
  [[ -z "$raw" ]] && { echo 0; return; }
  printf '%s\n' "$raw" | \
    grep -vE '^.M [^ /]+$|^\?\? (.+/)?node_modules/?$|^\?\? .*\.profraw$' | \
    grep -cE '\S' || true
}

if [[ $force_discard -eq 0 && $verified -eq 0 ]]; then
  super_raw="$(git -C "$wt" status --porcelain --ignore-submodules=dirty 2>/dev/null || true)"
  sub_raw="$(git -C "$wt" submodule foreach --recursive --quiet 'git status --porcelain' 2>/dev/null || true)"
  super_dirty="$(count_real_dirty "$super_raw")"
  sub_dirty="$(count_real_dirty "$sub_raw")"
  if [[ "$super_dirty" -gt 0 || "$sub_dirty" -gt 0 ]]; then
    echo "refusing: $wt has uncommitted work (super=$super_dirty sub=$sub_dirty). Pass --superseded or --preserved to verify it is retained remotely, or --force-discard to override." >&2
    [[ "$super_dirty" -gt 0 ]] && { echo "--- super status ---" >&2; printf '%s\n' "$super_raw" | grep -vE '^.M [^ /]+$' >&2; }
    [[ "$sub_dirty" -gt 0 ]]   && { echo "--- sub status ---"   >&2; printf '%s\n' "$sub_raw"   | grep -vE '^.M [^ /]+$' >&2; }
    exit 3
  fi

fi

if [[ $force_discard -eq 0 ]]; then
  # Refuse if a submodule holds committed local-only work (no PR) that teardown drops, unless the
  # tip is on a submodule remote. WHY a super gitlink bump doesn't preserve: it records a pointer,
  # not the object, and pushing the super never pushes submodule objects.
  #
  # At-risk = EVERY local ref the teardown drops, weighed independently against the live remote:
  #   self → all refs/heads/* (+ detached HEAD) in $wt/$sm, destroyed by `git worktree remove --force`.
  #   main → refs/heads/$branch in $main_root/$sm, deleted by the branch -D loop below.
  #
  # WHY enumerate from $wt, not $main_root: `git submodule foreach` skips submodules not checked
  # out at its root, but create-worktree.sh --submodule can leave a path deinitialized in main yet
  # initialized in $wt — so list gitlinks (mode 160000, present regardless of init) from $wt.
  list_submodule_paths() {
    git -C "$1" ls-files --stage 2>/dev/null | awk '$1=="160000" {print $4}'
  }
  enumerate_submodules() {
    local root="$1" prefix="${2:-}" sub
    while IFS= read -r sub; do
      if [[ -z "$sub" ]]; then continue; fi
      local disp="${prefix:+$prefix/}$sub"
      echo "$disp"
      if [[ -d "$root/$sub/.git" || -f "$root/$sub/.git" ]]; then
        enumerate_submodules "$root/$sub" "$disp"
      fi
    done <<< "$(list_submodule_paths "$root")"
    return 0
  }
  sm_paths="$(enumerate_submodules "$wt")" || true
  if [[ -z "$sm_paths" ]]; then sm_paths="$(enumerate_submodules "$main_root")" || true; fi

  # Fetch each physical gitdir at most once: self+main refs share linked per-worktree gitdirs,
  # so one fetch updates the refs/remotes both see (0=unreachable, 1=fetched).
  # macOS ships bash 3.2 (no associative arrays), so emulate the path→status cache with a
  # newline-delimited "key<TAB>status" string. Worktree paths never contain tabs/newlines —
  # the same assumption the tab-delimited `refs` here-string below already relies on.
  fetched_roots=""
  fetched_get() {  # echo cached status for key $1, empty if unset
    [[ -z "$fetched_roots" ]] && return 0  # skip the dummy empty-line read on an empty cache
    local k v
    while IFS=$'\t' read -r k v; do
      [[ "$k" == "$1" ]] && { printf '%s' "$v"; return 0; }
    done <<< "$fetched_roots"
    return 0
  }
  fetched_set() { fetched_roots+="$1"$'\t'"$2"$'\n'; }
  sm_ahead=""
  while IFS= read -r sm; do
    if [[ -z "$sm" ]]; then continue; fi

    # Enumerate EVERY local ref the teardown drops (entry = "root<TAB>origin<TAB>ref"); a single
    # inferred tip misses a non-HEAD unpushed branch the gitdir deletion also takes.
    #   self → ALL refs/heads/* (+ detached HEAD) in $wt/$sm, killed by `worktree remove --force`.
    #   main → refs/heads/$branch in $main_root/$sm (deleted by branch -D; sibling-holder skip applies).
    refs=""
    wt_sm="$wt/$sm"
    if [[ -d "$wt_sm/.git" || -f "$wt_sm/.git" ]]; then
      while IFS= read -r wt_ref; do
        if [[ -n "$wt_ref" ]]; then refs+="$wt_sm	self	$wt_ref"$'\n'; fi
      done <<< "$(git -C "$wt_sm" for-each-ref --format='%(refname:short)' refs/heads/ 2>/dev/null)"
      # A detached HEAD has no refs/heads entry but its tip still dies with the gitdir; carry the OID.
      if ! git -C "$wt_sm" symbolic-ref --quiet HEAD >/dev/null 2>&1; then
        wt_oid="$(git -C "$wt_sm" rev-parse --verify --quiet HEAD 2>/dev/null || true)"
        if [[ -n "$wt_oid" ]]; then refs+="$wt_sm	self	$wt_oid"$'\n'; fi
      fi
    fi
    main_sm="$main_root/$sm"
    if [[ -n "$branch" && "$main_sm" != "$wt_sm" && ( -d "$main_sm/.git" || -f "$main_sm/.git" ) ]] \
       && git -C "$main_sm" show-ref --verify --quiet "refs/heads/$branch" 2>/dev/null; then
      refs+="$main_sm	main	$branch"$'\n'
    fi

    while IFS=$'\t' read -r cand_root cand_origin cand_ref; do
      [[ -z "$cand_root" ]] && continue
      # A sibling worktree holding the main ref preserves it (branch -D fails closed, copy survives).
      # WHY main-only / canonicalize: %(worktreepath) is meaningful only for the main submodule's
      # ref, and git resolves it physically (/tmp→/private/tmp on macOS), so compare resolved paths.
      if [[ "$cand_origin" == "main" ]]; then
        holder="$(git -C "$cand_root" for-each-ref --format='%(worktreepath)' "refs/heads/$cand_ref" 2>/dev/null || true)"
        if [[ -n "$holder" ]]; then
          holder_real="$(cd "$holder" 2>/dev/null && pwd -P || echo "$holder")"
          target_real="$(cd "$wt/$sm" 2>/dev/null && pwd -P || echo "$wt/$sm")"
          [[ "$holder_real" != "$target_real" ]] && continue
        fi
      fi
      # Fetch the LIVE remote BEFORE judging reachability: a stale origin/main can make a local-only
      # tip look already-on-remote. Unreachable fetch ⇒ fail closed (at-risk), never trust stale refs.
      # WHY the explicit refspec instead of the configured one: create-worktree.sh materializes
      # submodules with --single-branch, so remote.origin.fetch is scoped to main and a configured
      # fetch never lands the topic branch that actually holds the tip.
      cand_root_real="$(cd "$cand_root" 2>/dev/null && pwd -P || echo "$cand_root")"
      if [[ -z "$(fetched_get "$cand_root_real")" ]]; then
        if git -C "$cand_root" fetch --prune --quiet origin '+refs/heads/*:refs/remotes/origin/*' 2>/dev/null; then
          fetched_set "$cand_root_real" 1
        else
          fetched_set "$cand_root_real" 0
        fi
      fi
      [[ "$(fetched_get "$cand_root_real")" == "1" ]] || { sm_ahead+="$sm "; break; }
      # Preserved iff the exact tip is reachable from a live remote-tracking ref post-fetch. Drops
      # the origin/main-range heuristic entirely: any ref a real remote ref contains is recoverable.
      [[ -n "$(git -C "$cand_root" branch -r --contains "$cand_ref" 2>/dev/null)" ]] && continue
      # A squash-merged PR whose branch was deleted keeps its tip alive under the forge's
      # refs/pull/*/head, which no refspec over refs/heads/* can see. Ask the remote whether it will
      # still serve the exact object; a tip the remote can hand back is not lost with the worktree.
      cand_oid="$(git -C "$cand_root" rev-parse --verify --quiet "$cand_ref^{commit}" 2>/dev/null || true)"
      if [[ -n "$cand_oid" ]] \
         && git -C "$cand_root" fetch --dry-run --depth 1 --quiet origin "$cand_oid" >/dev/null 2>&1; then
        continue
      fi
      sm_ahead+="$sm "
      break
    done <<< "$refs"
  done <<< "$sm_paths"
  if [[ -n "$sm_ahead" ]]; then
    echo "refusing: $wt has local-only submodule commits ahead of origin/main (${sm_ahead%% }) — not on any submodule remote (a pushed super gitlink bump does not preserve the submodule object)." >&2
    echo "Push the submodule branch (open its PR) first, pass --superseded or --preserved to verify it is retained remotely, or use --force-discard to drop the local branch." >&2
    exit 3
  fi
fi

# Unlock if locked.
if [[ "$locked" == "1" ]]; then
  echo "unlocking $wt"
  git -C "$main_root" worktree unlock "$wt" || true
fi

# Try non-forced remove first; fall back to --force on the submodule-structural refusal.
echo "removing $wt"
_wt_tmp="${TMPDIR:-/tmp}/wt-remove.$$"
if ! git -C "$main_root" worktree remove "$wt" 2>"$_wt_tmp"; then
  if grep -qE 'working trees containing submodules|contains modified or untracked' "$_wt_tmp"; then
    echo "  → retrying with --force"
    git -C "$main_root" worktree remove --force "$wt" 2>&1 || true
  else
    cat "$_wt_tmp" >&2
    rm -f "$_wt_tmp"
    exit 4
  fi
fi
rm -f "$_wt_tmp"

# Sandbox orphan: git updated its admin records but couldn't unlink the dir.
if [[ -d "$wt" ]]; then
  echo "  → dir survived (sandbox?); rm -rf"
  rm -rf "$wt" 2>/dev/null || {
    echo "rm failed; manual cleanup needed for $wt" >&2
    git -C "$main_root" worktree prune
    exit 4
  }
fi

git -C "$main_root" worktree prune

# Branch cleanup: super, then each submodule (recursive). Skip branches in use elsewhere.
if [[ -n "$branch" ]]; then
  echo "deleting branch $branch in superproject"
  git -C "$main_root" branch -D "$branch" 2>&1 | sed 's/^/  /' || true

  # Iterate submodules recursively. We list paths relative to $main_root and prefix.
  # Wrapped in `|| true` so a non-superproject $main_root (e.g. a submodule worktree's
  # main_root is the .git/modules path, where `submodule foreach` exits non-zero) doesn't
  # trip pipefail and abort the script after the main work already succeeded.
  # shellcheck disable=SC2016 # $displaypath is evaluated by each submodule shell.
  sm_list="$(git -C "$main_root" submodule --quiet foreach --recursive 'echo "$displaypath"' 2>/dev/null || true)"
  while IFS= read -r sm; do
    [[ -z "$sm" ]] && continue
    sm_path="$main_root/$sm"
    [[ -d "$sm_path/.git" || -f "$sm_path/.git" ]] || continue
    if git -C "$sm_path" show-ref --verify --quiet "refs/heads/$branch" 2>/dev/null; then
      out="$(git -C "$sm_path" branch -D "$branch" 2>&1 || true)"
      if [[ "$out" == *"used by worktree"* ]]; then
        echo "  $sm: branch kept (in use by another worktree)"
      else
        echo "  $sm: $out"
      fi
    fi
  done <<< "$sm_list"
fi

echo "done."
