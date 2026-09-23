---
name: create-skill
description: "Scaffold a new Claude Code skill under .claude/skills/ that follows this repo's authoring norms — a deterministic precondition gate and the mutation/worktree/lock frontmatter — and validate it. Use when the user wants to create/add/define a new skill or scaffold a SKILL.md."
effort: medium
mutation: mutating
worktree: true
lock: none
---

# Create Skill

Scaffold a new skill at `.claude/skills/<name>/SKILL.md`. Keep `SKILL.md` lean; push detail into `references/` loaded on demand.

## Precondition gate (do this first)
Before writing anything, confirm the skill is worth existing and nail its **deterministic relevance**:
1. **Is it actually a skill?** A skill earns its place when it carries non-obvious procedural knowledge, a multi-step workflow, or bundled scripts the model would otherwise re-derive. One-off prose belongs in a doc (`CLAUDE.md`, `docs/`), not a skill.
2. **Choose the invocation class.**
   - **normal** (default) — real `description:`; Claude auto-invokes when the description matches.
   - **name-only** — `description: "."` + `listing: name-only` + `overview:`; Claude won't auto-pick it, a visible caller (another skill) names it.
   - **user-only** — name-only plus `disable-model-invocation: true` (and `agents/openai.yaml` `policy.allow_implicit_invocation: false` for Codex); only `/<name>` runs it.
3. **State the checkable precondition.** One line answering "how does the model *know* this skill applies, without guessing?" It goes in `description` (or `overview`); its check becomes the body's first step. Can't make it observable → sharpen the scope first.
4. **Set up an isolated worktree** via the `worktree-submodules` skill.

Every skill must be safe to **not** run. The body's **first step confirms the precondition deterministically** and **exits early** when it doesn't hold. No side effects before that check passes.

## Process
1. **Pick a name** — lowercase, hyphenated, verb-led (`ship-ui-feature`, not `ui_shipper`). Folder: `.claude/skills/<name>/`.
2. **Decide invocation class and effect class** (frontmatter trio below) — independent axes.
3. **Write `SKILL.md`** — frontmatter first, then a lean body whose first step is the precondition check.
4. **Add resources only if reused** — `scripts/` for deterministic/repeated operations, `references/` for on-demand detail. No `README.md`/`CHANGELOG.md` in the folder. Reference scripts by repo-relative path: `.claude/skills/<name>/scripts/...`.
5. **Validate:** `.claude/skills/create-skill/scripts/validate-skill.sh .claude/skills/<name>` — fix every `FAIL`.
6. **Ship** — commit on the worktree branch, push, open a PR with `gh pr create`, then clean up via the `worktree-cleanup` skill.

## The pre-execution frontmatter (required)
```yaml
mutation: read-only | mutating        # does running it change shared state?
worktree: true | false                # set up a sibling worktree before any tracked-file edit
lock: <coordination-key-template> | none   # key for a unit concurrent sessions could both grab
```
- **`mutation`** — `read-only` if it only reads/reports. `mutating` if it writes files, opens/edits a PR, changes a branch/deploy/DB, or sends an external message.
- **`worktree`** — `true` only when it edits **tracked files** that ship via a PR. `false` for external-only mutations and all read-only skills.
- **`lock`** — a stable key template like `pr:<repo>#<n>`, `branch:<name>`, `skill:<name>` for mutating skills on a contended unit; `none` otherwise.

Validator enforces: `read-only ⇒ worktree:false & lock:none`; `worktree:true ⇒ mutating`; `lock != none ⇒ mutating`; name-only uses `description: "."` plus `overview`; user-only additionally requires `disable-model-invocation: true` and the Codex guard. Also required: `name`, non-empty `description`, `effort` (`low|medium|high|xhigh|max`). Add `model:` only to override the session model. Quote any scalar containing `: ` or ` #`.

## Frontmatter examples
```yaml
# read-only lookup
mutation: read-only
worktree: false
lock: none
```
```yaml
# edits tracked code and opens a PR
mutation: mutating
worktree: true
lock: pr:<repo>#<n>
```
```yaml
# mutates external state only (e.g. posts to Slack)
mutation: mutating
worktree: false
lock: none
```

## Authoring norms
- **Cross-skill references are one-line pointers.** "X routes through the `<skill>` skill" — never restate the target's flags or mechanics.
- **Push toward autonomy.** Safety in an autonomous loop is stopping conditions + worktree isolation, not per-step user prompts — though destructive actions still require human confirmation.
- **Code work runs on the strongest model.** A cheap-model read/triage skill that moves to writing code should spawn a subagent with an explicit `model:`.
