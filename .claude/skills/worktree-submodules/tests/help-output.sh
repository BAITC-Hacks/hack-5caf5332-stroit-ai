#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
help_output="$("$script_dir/../scripts/create-worktree.sh" --help)"
word_count="$(printf '%s\n' "$help_output" | wc -w | tr -d ' ')"

[[ "$help_output" == *"# Usage:"* ]]
[[ "$help_output" == *"--submodule-branch"* ]]
[[ "$help_output" == *"# Examples:"* ]]

if ((word_count > 150)); then
  echo "help output is too verbose: $word_count words (limit 150)" >&2
  exit 1
fi
