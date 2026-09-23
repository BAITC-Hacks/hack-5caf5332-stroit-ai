#!/usr/bin/env bash
# Machine-local atomic slot-claim primitive — meant to be SOURCED, not executed.
#
# The "claim one of N slots on this machine, reaping stale holders" loop used by
# ship-ui-feature/scripts/capture-lock.sh (bounded-concurrency capture semaphore).
#
# Usage — source this file, then call:
#
#   file_age <path>
#     Echo seconds since <path> was last modified, or a large number if it's gone.
#
#   claim_slot <claims_dir> <owner> <stale_fn> <candidate>...
#     Walk the candidate keys in order. For an existing claim file, call
#     `stale_fn <claim_file>` (return 0 == reapable): a live holder is left alone,
#     a stale one is reaped (rm). Then attempt an atomic noclobber claim writing
#     <owner> into <claims_dir>/<candidate>. On the first successful claim, echo
#     that candidate key and return 0. Return 1 if none could be claimed — every
#     candidate is either held by a live owner or lost the race to a concurrent claimer.
#
# The caller supplies the staleness policy (`stale_fn`) and the candidate set, and
# owns everything unique to it (wait/retry loop, post-claim rechecks, release model).

# Seconds since a file was last modified, or a large number if it's gone.
file_age() {
  local f="$1" now mtime
  now="$(date +%s)"
  mtime="$(stat -f %m "$f" 2>/dev/null || stat -c %Y "$f" 2>/dev/null || echo 0)"
  echo $(( now - mtime ))
}

claim_slot() {
  local claims_dir="$1" owner="$2" stale_fn="$3"
  shift 3
  mkdir -p "$claims_dir"
  local candidate claim
  for candidate in "$@"; do
    claim="$claims_dir/$candidate"
    if [ -e "$claim" ]; then
      if ! "$stale_fn" "$claim"; then
        continue          # live holder — leave it alone
      fi
      rm -f "$claim"      # stale — reap so we can reclaim it
    fi
    # noclobber makes the claim atomic across concurrent claimers.
    if ( set -C; printf '%s\n' "$owner" > "$claim" ) 2>/dev/null; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}
