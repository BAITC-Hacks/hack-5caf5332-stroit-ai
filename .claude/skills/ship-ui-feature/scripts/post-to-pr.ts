#!/usr/bin/env bun
// Land capture evidence on a PR: upload media as assets on a per-PR GitHub
// release (GitHub has no API for native comment attachments, and release assets
// are the only API-writable store that adds no git objects), then write
// thumbnail embeds + artifact links into the PR description via gh
// (marker-delimited so reruns replace the block instead of stacking).
//
// Run from inside the checkout whose PR gets the evidence (the worktree root):
//   bun <skill>/scripts/post-to-pr.ts --evidence /tmp/claude/ui-capture/<wt> [--pr <n>] [--route /feeds/x] [--signature "<line>"]

import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdtempSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const run = (cmd: string, args: string[], cwd?: string): string =>
  execFileSync(cmd, args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "inherit"] }).trim();

const runOptional = (cmd: string, args: string[]): string | null => {
  try {
    return execFileSync(cmd, args, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return null;
  }
};

const parseArgs = (argv: string[]): Map<string, string> => {
  const args = new Map<string, string>();
  for (let i = 0; i < argv.length; i += 2) {
    if (!argv[i].startsWith("--") || argv[i + 1] === undefined) throw new Error(`bad args near ${argv[i]}`);
    args.set(argv[i].slice(2), argv[i + 1]);
  }
  return args;
};

const args = parseArgs(process.argv.slice(2));
const evidenceDir = args.get("evidence");
if (!evidenceDir || !existsSync(evidenceDir)) throw new Error("--evidence <dir> must exist");

const repo = run("gh", ["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"]);
const prNumber = args.get("pr") ?? run("gh", ["pr", "view", "--json", "number", "-q", ".number"]);

const filesUnder = (dir: string): string[] =>
  existsSync(dir)
    ? readdirSync(dir, { recursive: true, encoding: "utf8" })
        .map((f) => path.join(dir, f))
        .sort()
    : [];

// capture.ts isolates each run under media/<runId>/ and records the current one
// in media/.latest-run — publish only that run so stale siblings never leak.
const mediaRoot = path.join(evidenceDir, "media");
const latestRunFile = path.join(mediaRoot, ".latest-run");
if (!existsSync(latestRunFile)) throw new Error(`no ${latestRunFile} — did the capture run?`);
const runId = readFileSync(latestRunFile, "utf8").trim();
if (!runId) throw new Error(`${latestRunFile} is empty`);
const runMediaDir = path.join(mediaRoot, runId);
const releaseTag = `ui-evidence-pr-${prNumber}-${runId}`;

const screenshots = filesUnder(runMediaDir).filter((f) => f.endsWith(".png"));
const resultFiles = filesUnder(path.join(evidenceDir, "test-results"));
const videos = resultFiles.filter((f) => f.endsWith(".webm"));
if (screenshots.length === 0) throw new Error(`no screenshots under ${runMediaDir} — did the capture run?`);

const stage = mkdtempSync(path.join(tmpdir(), "pr-evidence-"));
screenshots.forEach((f) => cpSync(f, path.join(stage, path.basename(f))));
videos.forEach((f, i) => cpSync(f, path.join(stage, `video-${i + 1}.webm`)));

const staged = readdirSync(stage).sort();

// Evidence goes to a per-capture release, not into git. Release assets live in GitHub's blob
// storage and create no git objects, so a clone never pays for them; the previous shared
// `pr-evidence` branch put every PR's media in every clone of the repo, permanently
// (838MB in portal, 97% of its object store). Deleting the release deletes the assets,
// which is the retention handle a shared append-only branch could never offer.
//
// Passing assets to `gh release create` makes the CLI upload them while the release is a
// draft, then publish it. Published assets can be immutable, so each capture uses its run id.
const ensureRelease = (): void => {
  const existingJson = runOptional("gh", ["release", "view", releaseTag, "--json", "assets,isDraft"]);
  if (existingJson) {
    const existing = JSON.parse(existingJson) as { assets: Array<{ name: string }>; isDraft: boolean };
    const existingNames = existing.assets.map((asset) => asset.name).sort();
    if (!existing.isDraft && JSON.stringify(existingNames) === JSON.stringify(staged)) return;
    if (!existing.isDraft) throw new Error(`published release ${releaseTag} does not match the current capture`);

    existingNames
      .filter((name) => !staged.includes(name))
      .forEach((name) => run("gh", ["release", "delete-asset", releaseTag, name, "--yes"]));
    run("gh", ["release", "upload", releaseTag, ...staged.map((file) => path.join(stage, file)), "--clobber"]);
    run("gh", ["release", "edit", releaseTag, "--draft=false", "--prerelease"]);
    return;
  }

  // Tag the default branch, never the PR's own head: a tag pins its commit forever, so
  // tagging the feature branch would keep that branch's objects alive past the squash-merge
  // and reintroduce exactly the unbounded retention this change removes.
  const defaultBranch = run("gh", ["repo", "view", "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"]);
  run("gh", [
    "release",
    "create",
    releaseTag,
    ...staged.map((file) => path.join(stage, file)),
    "--target",
    defaultBranch,
    "--prerelease",
    "--title",
    `UI capture evidence for PR #${prNumber}`,
    "--notes",
    `Playwright capture evidence for #${prNumber}. Deleted when the PR is closed or by the retention sweep.`
  ]);
};

ensureRelease();

const assetUrl = (file: string) => `https://github.com/${repo}/releases/download/${releaseTag}/${file}`;

// Confirm the media actually landed before embedding URLs that would otherwise 404 — a
// silently-empty upload is exactly the "evidence didn't upload" failure to catch loudly.
const uploaded = run("gh", ["release", "view", releaseTag, "--json", "assets", "-q", ".assets[].name"]).split("\n").filter(Boolean);
const missing = staged.filter((f) => !uploaded.includes(f));
if (missing.length > 0) {
  throw new Error(`evidence not found on release ${releaseTag} after upload (${missing.join(", ")}) — upload did not land`);
}
const signatureLine = args.get("signature");

const body = [
  "## 📸 UI capture evidence",
  ...(args.has("route") ? [`Route: \`${args.get("route")}\``] : []),
  "",
  "### Screenshots",
  ...staged.filter((f) => f.endsWith(".png")).map((f) => `![${f}](${assetUrl(f)})`),
  "",
  "### Artifacts",
  ...staged.filter((f) => f.endsWith(".webm")).map((f) => `- 🎬 [${f}](${assetUrl(f)}) — interaction recording`),
  ...(signatureLine ? ["", signatureLine] : [])
].join("\n");

// Land the evidence in the PR *description*, not a comment, so it sits with the change
// itself rather than scrolling away in the thread. Reruns replace the marker-delimited
// block in place instead of stacking duplicate evidence sections.
const START = "<!-- ui-evidence:start -->";
const END = "<!-- ui-evidence:end -->";
const currentBody = run("gh", ["pr", "view", prNumber, "--json", "body", "-q", ".body"]);
const stripped = currentBody.replace(new RegExp(`${START}[\\s\\S]*?${END}`, "g"), "").trimEnd();
const nextBody = `${stripped}\n\n${START}\n${body}\n${END}\n`;
const bodyFile = path.join(mkdtempSync(path.join(tmpdir(), "pr-evidence-body-")), "body.md");
writeFileSync(bodyFile, nextBody);
run("gh", ["pr", "edit", prNumber, "--body-file", bodyFile]);
console.log(`updated PR #${prNumber} description with capture evidence`);
