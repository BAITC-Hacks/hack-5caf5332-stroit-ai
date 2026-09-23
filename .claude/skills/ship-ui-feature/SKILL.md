---
name: ship-ui-feature
description: "Capture real browser evidence (Playwright screenshots + video) for a web UI change and attach it to the PR description. Use whenever a rendered web UI in this repo is being shipped, verified, screenshotted, or PR'd and there is a dev-server route to exercise."
effort: medium
mutation: mutating
worktree: false
lock: pr:<repo>#<n>
---

# Ship UI Feature — visual capture & PR evidence

After a UI change is implemented, prove it works against the **real running app**: start the dev server, navigate to the changed route, do the minimum interaction that shows it working, capture, post to the PR, exit. Happy path; optimize for speed.

**Precondition:** the diff touches rendered web UI and the app has a dev command (`package.json` `dev` script or equivalent). No web UI in the diff → exit; this skill doesn't apply.

## TL;DR

```bash
skill=.claude/skills/ship-ui-feature                    # relative to the repo/worktree root
wt="$(git rev-parse --show-toplevel)"
out=/tmp/claude/ui-capture/$(basename "$wt")            # per-worktree → parallel runs don't collide
port=3000                                               # bump if taken; reuse below
route=/                                                 # the route the change lives on

# 0. Preflight capture tooling (no-op once installed; exits 2 when missing)
"$skill/scripts/ensure-playwright.sh"
# exit 2 → ask the user, then (unsandboxed): "$skill/scripts/ensure-playwright.sh" --install

# 1. Dev server — run_in_background + dangerouslyDisableSandbox (sandbox blocks listen())
(cd "$wt/<app-dir>" && PORT=$port bun run dev)          # or npm run dev / the app's dev command

# 2. Capture — unsandboxed (chromium can't launch sandboxed)
CAPTURE_OUT="$out" CAPTURE_BASE_URL="http://localhost:$port" CAPTURE_ROUTE="$route" \
  CAPTURE_STEPS="$out/steps.mjs" "$skill/scripts/ensure-playwright.sh" -- playwright test --config "$skill/playwright.config.ts"

# 3. PR must exist first. Post evidence from inside the checkout (gh resolves repo/PR there) — unsandboxed (network)
bun "$skill/scripts/post-to-pr.ts" --evidence "$out" --route "$route" [--pr <n>]
```

Prereqs: `node`, `npm`, `bun`, `gh` on PATH. Tooling (`@playwright/test`, `sharp`, Chromium) is pinned in `package-lock.json` and cached outside the repo (`~/Library/Caches/stroit-ai/ship-ui-feature`; override with `PLAYWRIGHT_TOOL_HOME` / `PLAYWRIGHT_BROWSERS_PATH`), so later runs reuse it.

## 1. Dev server

- Reuse a server already running for this checkout instead of starting a second one (Next refuses two `next dev` in one dir).
- Install deps in the worktree first if `node_modules` is missing; never symlink `node_modules` from the main checkout (Turbopack rejects out-of-root symlinks).
- A first `curl` can 404 while the route compiles — re-probe before concluding the route is missing.
- A route that 500s is usually missing backend env/services, not the capture — read the dev-server log.

## 2. Auth (only if routes are gated)

If a `storageState.json` exists at `~/.claude/stroit-ai-auth/storageState.json` (override: `CAPTURE_STORAGE_STATE`), capture loads it. To create one: `"$skill/scripts/ensure-playwright.sh" -- playwright open --save-storage="$HOME/.claude/stroit-ai-auth/storageState.json" http://localhost:$port`, log in, close the window gracefully. Capture fails loudly if it lands on `/sign-in` or `/login`; set `CAPTURE_ALLOW_SIGN_IN=1` only when the sign-in page is the UI under test.

## 3. Steps (optional)

Change visible on load → skip `CAPTURE_STEPS`; the spec screenshots the route as `final`. Otherwise write a throwaway plain-JS module at `$out/steps.mjs`:

```js
/** @type {import("<abs path to skill>/scripts/capture").CaptureSteps} */
const steps = async (page, screenshot) => {
  await page.getByRole("tab", { name: "History" }).click();
  await screenshot("history-tab");        // any number of named screenshots
};
export default steps;
```

Minimum interaction only — enough to show the feature working, not an e2e suite.

## 4. Capture output

Under `$CAPTURE_OUT`: `media/<run-id>/NN-<name>.png` (full-page, capped at `CAPTURE_MAX_PX`=2000, palette-quantized at `CAPTURE_PNG_QUALITY`=80) and `test-results/**/video.webm` (`CAPTURE_VIDEO_WIDTH`×`CAPTURE_VIDEO_HEIGHT`, default 960×600). Files older than a week are swept each run.

- Capture fails on HTTP ≥400, a Next error overlay, or a sign-in landing — fix and re-run; never post partial evidence.
- `bootstrap_check_in … Permission denied (1100)` / `mach_port_rendezvous` → chromium ran sandboxed; rerun with `dangerouslyDisableSandbox: true`.
- At most `MAX_CONCURRENT_CAPTURES` (default 2) captures run machine-wide; the rest queue (`scripts/capture-lock.sh`).
- Concurrent captures need distinct `CAPTURE_OUT` dirs.

## 5. Land it on the PR

`post-to-pr.ts` uploads screenshots + video as assets on a prerelease tagged `ui-evidence-pr-<n>-<run-id>` (no git objects added), verifies each asset landed, then writes embeds into the PR **description** between `<!-- ui-evidence:start -->` / `<!-- ui-evidence:end -->` markers (reruns replace in place). Pass `--signature "<line>"` to append a line to the block.

Old evidence releases: `bun "$skill/scripts/prune-evidence-releases.ts" --repo=BAITC-Hacks/hack-5caf5332-stroit-ai [--days=30] [--dry-run]`.

Then exit: kill the dev server you started; leave `$out`.

## 6. Fallback — capture genuinely impossible

Only after an honest run of §1–§3. Write a prominent note in the PR body: evidence was **not** captured, the **specific** technical block, and what was verified instead. Never ship a silent evidence-free UI PR.
