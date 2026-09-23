#!/usr/bin/env bash
# Validate a skill's frontmatter against the authoring norms.
# Hard-checks: name/description/effort present; the mutation/worktree/lock trio
# present AND internally consistent. Opt-in per skill (run by create-skill on the
# skill it just made) — NOT run repo-wide; existing skills predate the trio.
#
# Usage: validate-skill.sh <skill-dir | path/to/SKILL.md>
set -euo pipefail

target="${1:-}"
if [ -z "$target" ]; then
  echo "usage: validate-skill.sh <skill-dir | path/to/SKILL.md>" >&2
  exit 2
fi

file="$target"
[ -d "$target" ] && file="$target/SKILL.md"
if [ ! -f "$file" ]; then
  echo "FAIL: no SKILL.md at '$file'" >&2
  exit 2
fi

# Pull a top-level scalar out of the first YAML frontmatter block (lines between
# the opening and closing `---`). Strips trailing `# comment` and surrounding
# space. Only strips a *matched* surrounding quote pair; a lone opening or
# closing quote (e.g. `name: "new-skill`) is left intact so the unbalanced-quote
# check below rejects the malformed scalar instead of silently accepting it.
get_val() {
  awk -v k="$1" '
    NR==1 && $0 !~ /^---[[:space:]]*$/ { exit }      # no frontmatter at all
    /^---[[:space:]]*$/ { c++; next }
    c==1 && $0 ~ "^"k"[[:space:]]*:" {
      sub("^"k"[[:space:]]*:[[:space:]]*", "")
      sub(/[[:space:]]*#.*$/, "")
      gsub(/^[[:space:]]+|[[:space:]]+$/, "")
      if ($0 ~ /^".*"$/ || $0 ~ /^'\''.*'\''$/) { $0 = substr($0, 2, length($0) - 2) }
      print
      exit
    }
    c>=2 { exit }
  ' "$file"
}

has_key() {
  awk -v k="$1" '
    NR==1 && $0 !~ /^---[[:space:]]*$/ { exit }
    /^---[[:space:]]*$/ { c++; next }
    c==1 && $0 ~ "^"k"[[:space:]]*:" { found=1; exit }
    c>=2 { exit }
    END { exit found ? 0 : 1 }
  ' "$file"
}

# True when the raw scalar carries an unbalanced surrounding quote — a leading
# quote with no matching trailing one (or vice versa). get_val leaves these
# intact, so a lone quote survives into the value and trips this check.
has_unbalanced_quote() {
  case "$1" in
    \"*\"|\'*\') return 1 ;;          # matched pair → balanced
    \"*|*\"|\'*|*\') return 0 ;;      # lone leading or trailing quote
    *) return 1 ;;
  esac
}

# YAML plain scalars cannot contain `: `, an unquoted ` #` starts a comment, and a completed flow
# collection cannot have trailing prose. The lightweight field reader above would otherwise accept
# these forms even though discovery clients using a real YAML parser reject or truncate them.
has_invalid_plain_scalar() {
  awk -v k="$1" '
    NR==1 && $0 !~ /^---[[:space:]]*$/ { exit }
    /^---[[:space:]]*$/ { c++; next }
    c==1 && $0 ~ "^"k"[[:space:]]*:" {
      sub("^"k"[[:space:]]*:[[:space:]]*", "")
      value=$0
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
      first=substr(value, 1, 1)
      if (value == "" || first == "\"" || first == "'\''" || first == ">" || first == "|") exit
      if (value ~ /:[[:space:]]/ || value ~ /[[:space:]]#/ || value ~ /^\[[^]]+\][[:space:]]+./) found=1
      exit
    }
    c>=2 { exit }
    END { exit found ? 0 : 1 }
  ' "$file"
}

# Frontmatter must be a complete block: opening `---` on line 1 and a matching
# closing `---`. An unterminated block (no closing delimiter) would let get_val
# scan the whole file and silently collect keys, accepting a malformed skill.
frontmatter_state="$(awk '
  NR==1 && $0 !~ /^---[[:space:]]*$/ { print "none"; exit }
  /^---[[:space:]]*$/ { c++; if (c==2) { print "closed"; exit } next }
  END { if (c<2) print (c==1 ? "open" : "none") }
' "$file")"
case "$frontmatter_state" in
  none) echo "FAIL: no YAML frontmatter block (file must start with '---')" >&2; echo "✗ $file is not a valid skill" >&2; exit 1;;
  open) echo "FAIL: unterminated YAML frontmatter (missing closing '---')" >&2; echo "✗ $file is not a valid skill" >&2; exit 1;;
esac

name="$(get_val name)"
description="$(get_val description)"
overview="$(get_val overview)"
listing="$(get_val listing)"
disable_model_invocation="$(get_val disable-model-invocation)"
effort="$(get_val effort)"
mutation="$(get_val mutation)"
worktree="$(get_val worktree)"
lock="$(get_val lock)"

fail=0
err() { echo "FAIL: $1" >&2; fail=1; }

# Required scalars
[ -n "$name" ]        || err "missing 'name:'"
has_key description    || err "missing 'description:'"
[ -n "$effort" ]      || err "missing 'effort:' (low|medium|high|xhigh|max)"
[ -n "$mutation" ]    || err "missing 'mutation:' (read-only|mutating)"
[ -n "$worktree" ]    || err "missing 'worktree:' (true|false)"
[ -n "$lock" ]        || err "missing 'lock:' (<coordination-key-template>|none)"

if [ -z "$description" ]; then
  err "description must be non-empty; use '.' for name-only skills with overview"
elif [ "$description" = "." ]; then
  [ "$listing" = "name-only" ] || err "placeholder description requires listing:name-only"
  [ -n "$overview" ]           || err "placeholder description requires overview:"
elif [ "$listing" = "name-only" ]; then
  err "listing:name-only requires description: '.' and overview:"
fi

# Unbalanced quotes — a lone opening/closing quote means the frontmatter is not
# valid YAML and skill discovery would mis-parse it; reject loudly.
for kv in "name:$name" "description:$description" "overview:$overview" "effort:$effort" \
          "mutation:$mutation" "worktree:$worktree" "lock:$lock"; do
  key="${kv%%:*}"; val="${kv#*:}"
  has_unbalanced_quote "$val" && err "$key has an unbalanced quote: $val"
done

for key in name description overview listing disable-model-invocation effort mutation worktree lock; do
  has_invalid_plain_scalar "$key" && err "$key is not a valid YAML plain scalar; quote it or use a block scalar"
done

# Enums
case "$mutation" in read-only|mutating|"") ;; *) err "mutation must be read-only|mutating, got '$mutation'";; esac
case "$worktree" in true|false|"") ;; *) err "worktree must be true|false, got '$worktree'";; esac
case "$effort" in low|medium|high|xhigh|max|"") ;; *) err "effort must be low|medium|high|xhigh|max, got '$effort'";; esac
case "$listing" in name-only|"") ;; *) err "listing must be name-only or omitted, got '$listing'";; esac
case "$disable_model_invocation" in true|false|"") ;; *) err "disable-model-invocation must be true|false, got '$disable_model_invocation'";; esac

agent_metadata="$(dirname "$file")/agents/openai.yaml"
codex_implicit_disabled=false
if [ -f "$agent_metadata" ] && grep -Eq '^[[:space:]]*allow_implicit_invocation:[[:space:]]*false[[:space:]]*$' "$agent_metadata"; then
  codex_implicit_disabled=true
fi

if [ "$disable_model_invocation" = "true" ]; then
  [ "$listing" = "name-only" ] || err "user-only skill requires listing:name-only"
  [ "$description" = "." ] || err "user-only skill requires description: '.' with routing text in overview:"
  [ "$codex_implicit_disabled" = "true" ] || err "user-only skill requires agents/openai.yaml policy.allow_implicit_invocation:false"
elif [ "$codex_implicit_disabled" = "true" ]; then
  err "Codex implicit invocation is disabled but SKILL.md lacks disable-model-invocation:true"
fi

# Consistency — the precondition contract
if [ "$mutation" = "read-only" ]; then
  [ "$worktree" = "false" ] || err "read-only ⇒ worktree must be false (got '$worktree')"
  [ "$lock" = "none" ]      || err "read-only ⇒ lock must be none (got '$lock')"
fi
if [ "$worktree" = "true" ] && [ "$mutation" != "mutating" ]; then
  err "worktree:true ⇒ mutation must be mutating (got '$mutation')"
fi
if [ -n "$lock" ] && [ "$lock" != "none" ] && [ "$mutation" != "mutating" ]; then
  err "lock '$lock' set ⇒ mutation must be mutating (got '$mutation')"
fi

if [ "$fail" -ne 0 ]; then
  echo "✗ $file is not a valid skill" >&2
  exit 1
fi

echo "✓ $name — mutation:$mutation worktree:$worktree lock:$lock effort:$effort"
