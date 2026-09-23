#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
validator="$here/validate-skill.sh"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

write_skill() {
  local name="$1" frontmatter="$2"
  mkdir -p "$scratch/$name"
  printf '%s\n' '---' "$frontmatter" '---' '# Test' >"$scratch/$name/SKILL.md"
}

expect_pass() {
  "$validator" "$scratch/$1" >/dev/null
}

expect_fail() {
  if "$validator" "$scratch/$1" >/dev/null 2>&1; then
    echo "expected validation failure: $1" >&2
    exit 1
  fi
}

write_skill normal $'name: normal\ndescription: A precise visible workflow.\neffort: low\nmutation: read-only\nworktree: false\nlock: none'
expect_pass normal

write_skill helper $'name: helper\ndescription: "."\noverview: Internal helper selected by a visible caller.\nlisting: name-only\neffort: low\nmutation: read-only\nworktree: false\nlock: none'
expect_pass helper

write_skill explicit $'name: explicit\ndescription: "."\noverview: Run only when the user explicitly invokes it.\nlisting: name-only\ndisable-model-invocation: true\neffort: low\nmutation: read-only\nworktree: false\nlock: none'
mkdir -p "$scratch/explicit/agents"
printf '%s\n' 'policy:' '  allow_implicit_invocation: false' >"$scratch/explicit/agents/openai.yaml"
expect_pass explicit

write_skill missing_codex_guard $'name: missing-codex-guard\ndescription: "."\noverview: Explicit only.\nlisting: name-only\ndisable-model-invocation: true\neffort: low\nmutation: read-only\nworktree: false\nlock: none'
expect_fail missing_codex_guard

write_skill hidden_description $'name: hidden-description\ndescription: This should be visible.\nlisting: name-only\neffort: low\nmutation: read-only\nworktree: false\nlock: none'
expect_fail hidden_description

write_skill codex_only $'name: codex-only\ndescription: A visible workflow with a contradictory Codex guard.\neffort: low\nmutation: read-only\nworktree: false\nlock: none'
mkdir -p "$scratch/codex_only/agents"
printf '%s\n' 'policy:' '  allow_implicit_invocation: false' >"$scratch/codex_only/agents/openai.yaml"
expect_fail codex_only

write_skill invalid_plain_scalar $'name: invalid-plain-scalar\ndescription: Route requests: search or send.\neffort: low\nmutation: read-only\nworktree: false\nlock: none'
expect_fail invalid_plain_scalar

write_skill folded_scalar $'name: folded-scalar\ndescription: >-\n  Route requests: search or send.\neffort: low\nmutation: read-only\nworktree: false\nlock: none'
expect_pass folded_scalar

write_skill truncated_plain_scalar $'name: truncated-plain-scalar\ndescription: Post to #operations when requested.\neffort: low\nmutation: read-only\nworktree: false\nlock: none'
expect_fail truncated_plain_scalar

echo "validate-skill invocation taxonomy tests passed"
