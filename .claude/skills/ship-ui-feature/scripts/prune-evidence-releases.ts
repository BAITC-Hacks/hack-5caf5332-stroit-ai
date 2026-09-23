#!/usr/bin/env bun
// Delete UI-evidence releases once their PR is closed, or once they age out.
//
// Release assets have no native expiry (unlike Actions artifacts), so without this the
// per-PR releases accumulate the same way the old shared `pr-evidence` branch did — just
// outside git instead of inside it. Closing the PR is the real signal; the age cutoff only
// catches releases whose PR was deleted or never existed.
//
//   bun <skill>/scripts/prune-evidence-releases.ts --repo=BAITC-Hacks/hack-5caf5332-stroit-ai [--days=30] [--dry-run]

import { execFileSync } from "node:child_process";

const run = (cmd: string, args: string[]): string =>
  execFileSync(cmd, args, { encoding: "utf8", stdio: ["ignore", "pipe", "inherit"] }).trim();

const args = new Map<string, string>();
const flags = new Set<string>();
for (const arg of process.argv.slice(2)) {
  if (!arg.startsWith("--")) throw new Error(`bad arg: ${arg}`);
  const [key, value] = arg.slice(2).split("=", 2);
  if (value === undefined) flags.add(key);
  else args.set(key, value);
}

const repo = args.get("repo") ?? run("gh", ["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"]);
const days = Number(args.get("days") ?? 30);
if (!Number.isFinite(days) || days < 0) throw new Error("--days must be a non-negative number");
const dryRun = flags.has("dry-run");

const EVIDENCE_TAG = /^ui-evidence-pr-(\d+)(?:-.+)?$/;
const cutoff = Date.now() - days * 24 * 60 * 60 * 1000;

type Release = { tagName: string; createdAt: string };
const releases: Release[] = JSON.parse(run("gh", ["release", "list", "--repo", repo, "--limit", "500", "--json", "tagName,createdAt"]));

// A PR that no longer exists (deleted, or a tag that never matched one) reads as closed:
// there is nothing left for the evidence to support either way.
const prIsOpen = (pr: string): boolean => {
  try {
    return run("gh", ["pr", "view", pr, "--repo", repo, "--json", "state", "-q", ".state"]) === "OPEN";
  } catch {
    return false;
  }
};

let deleted = 0;
for (const release of releases) {
  const match = EVIDENCE_TAG.exec(release.tagName);
  if (!match) continue;

  const aged = Date.parse(release.createdAt) < cutoff;
  const open = prIsOpen(match[1]);
  if (open && !aged) continue;

  const why = open ? `aged out (>${days}d)` : "PR closed";
  if (dryRun) {
    console.log(`would delete ${release.tagName} — ${why}`);
  } else {
    // --cleanup-tag removes the git tag too; leaving it behind would keep the tagged
    // commit reachable forever, which is the retention leak this whole change removes.
    run("gh", ["release", "delete", release.tagName, "--repo", repo, "--yes", "--cleanup-tag"]);
    console.log(`deleted ${release.tagName} — ${why}`);
  }
  deleted++;
}

console.log(`${dryRun ? "would delete" : "deleted"} ${deleted} evidence release(s) in ${repo}`);
