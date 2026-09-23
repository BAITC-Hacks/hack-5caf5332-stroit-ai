#!/usr/bin/env bash
set -euo pipefail

# Machine-local capture concurrency semaphore.
#
# Wraps a command, holding one of N slots for its lifetime so that parallel UI
# captures (headless Chromium via `playwright test`) can't overload the machine.
# ship-ui-feature routes every capture through here (see ensure-playwright.sh);
# the seed-auth login path is intentionally NOT gated.
#
# Usage: capture-lock.sh -- <command> [args...]
#
# Env:
#   MAX_CONCURRENT_CAPTURES   slots (default 2; set 1 for fully serial)
#   CAPTURE_LOCK_WAIT         max seconds to wait for a free slot (default 1800)
#   CAPTURE_LOCK_STALE_SECS   age after which a slot file is reaped even if its
#                             PID looks alive — survives PID reuse (default 1800)
#
# Slot files live at /tmp/claude/ui-capture-slots/slot-<i>, content = holder PID.
# The atomic claim + stale-reap loop is shared with allocate-port.sh via slot-claim.sh.

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./slot-claim.sh
. "$here/slot-claim.sh"

if [ "${1:-}" = "--" ]; then
  shift
fi
if [ "$#" -eq 0 ]; then
  echo "usage: capture-lock.sh -- <command> [args...]" >&2
  exit 2
fi

slots="${MAX_CONCURRENT_CAPTURES:-2}"
case "$slots" in
  '' | *[!0-9]*) echo "capture-lock: MAX_CONCURRENT_CAPTURES must be a positive integer (got '$slots')" >&2; exit 2 ;;
esac
[ "$slots" -ge 1 ] || { echo "capture-lock: MAX_CONCURRENT_CAPTURES must be >= 1" >&2; exit 2; }

wait_budget="${CAPTURE_LOCK_WAIT:-1800}"
stale_secs="${CAPTURE_LOCK_STALE_SECS:-1800}"
slots_dir=/tmp/claude/ui-capture-slots

# A capture slot is reapable unless its holder PID is still alive AND the claim is
# younger than the age backstop (the backstop survives PID reuse).
slot_stale() {
  local claim="$1" holder
  holder="$(cat "$claim" 2>/dev/null || true)"
  if [ -n "$holder" ] && kill -0 "$holder" 2>/dev/null && [ "$(file_age "$claim")" -lt "$stale_secs" ]; then
    return 1
  fi
  return 0
}

# Slot keys are slot-0 … slot-(N-1); claim files are $slots_dir/slot-<i>.
candidates=()
for i in $(seq 0 $(( slots - 1 ))); do
  candidates+=("slot-$i")
done

slot=""
deadline=$(( $(date +%s) + wait_budget ))
warned=false

while :; do
  if key="$(claim_slot "$slots_dir" "$$" slot_stale "${candidates[@]}")"; then
    slot="$slots_dir/$key"
    break
  fi

  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "capture-lock: timed out after ${wait_budget}s waiting for a free capture slot (all $slots busy)" >&2
    exit 1
  fi
  if [ "$warned" = false ]; then
    echo "capture-lock: all $slots capture slots busy — waiting…" >&2
    warned=true
  fi
  sleep 1
done

trap 'rm -f "$slot"' EXIT
# Forward termination to the wrapped capture so a kill releases the slot too.
trap 'kill -TERM "$child" 2>/dev/null || true' INT TERM

# Run as a child (not exec) so the EXIT trap fires and releases the slot afterward.
"$@" &
child=$!
rc=0
wait "$child" || rc=$?   # don't let set -e abort before the slot is released
exit "$rc"
