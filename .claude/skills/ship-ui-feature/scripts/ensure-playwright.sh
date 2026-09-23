#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
skill_dir="$(cd -- "$script_dir/.." && pwd)"

if [ -z "${HOME:-}" ]; then
  echo "HOME is required to locate the persistent Playwright cache." >&2
  exit 1
fi

case "$(uname -s)" in
  Darwin) cache_root="${XDG_CACHE_HOME:-$HOME/Library/Caches}" ;;
  *) cache_root="${XDG_CACHE_HOME:-$HOME/.cache}" ;;
esac

tool_home="${PLAYWRIGHT_TOOL_HOME:-$cache_root/stroit-ai/ship-ui-feature}"
browser_home="${PLAYWRIGHT_BROWSERS_PATH:-$tool_home/browsers}"
playwright="$tool_home/node_modules/.bin/playwright"
install=false

usage() {
  cat >&2 <<EOF
Usage: $(basename "$0") [--install] [-- (playwright <arguments> | node <script> [arguments...])]

Checks the shared Playwright package and Chromium cache. Use --install only
after approval to install any missing or stale capture tooling.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --install)
      install=true
      shift
      ;;
    --)
      shift
      break
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage
      exit 1
      ;;
  esac
done

package_ready() {
  test -x "$playwright" &&
    cmp -s "$skill_dir/package.json" "$tool_home/package.json" &&
    cmp -s "$skill_dir/package-lock.json" "$tool_home/package-lock.json" &&
    (
      cd "$tool_home"
      npm ls --depth=0 >/dev/null 2>&1 &&
        node -e 'require("sharp");require("@playwright/test")' >/dev/null 2>&1
    )
}

install_package() {
  command -v npm >/dev/null 2>&1 || {
    echo "npm is required to install the Playwright capture package." >&2
    exit 1
  }
  mkdir -p "$tool_home"
  cp "$skill_dir/package.json" "$skill_dir/package-lock.json" "$tool_home/"
  (
    cd "$tool_home"
    # --include=dev: @playwright/test, sharp, and the CLI live in devDependencies,
    # so a caller with NODE_ENV=production (or npm omit=dev) would otherwise skip
    # them and leave $tool_home/node_modules/.bin/playwright missing.
    npm ci --include=dev >&2
  )
}

browser_paths() {
  PLAYWRIGHT_BROWSERS_PATH="$browser_home" "$playwright" install --dry-run chromium |
    sed -n 's/^[[:space:]]*Install location:[[:space:]]*//p'
}

browser_ready() {
  local paths
  local browser_path

  paths="$(browser_paths)"
  test -n "$paths" || return 1
  while IFS= read -r browser_path; do
    test -n "$browser_path" || continue
    test -f "$browser_path/INSTALLATION_COMPLETE" || return 1
  done <<EOF
$paths
EOF
}

if ! package_ready; then
  if [ "$install" = false ]; then
    echo "Playwright capture package is missing or stale in $tool_home." >&2
    echo "Run $(basename "$0") --install after approving the install." >&2
    exit 2
  fi
  install_package
fi

if ! browser_ready; then
  if [ "$install" = false ]; then
    echo "Chromium is missing or incomplete in $browser_home." >&2
    echo "Run $(basename "$0") --install after approving the install." >&2
    exit 2
  fi
  mkdir -p "$browser_home"
  PLAYWRIGHT_BROWSERS_PATH="$browser_home" "$playwright" install chromium >&2
  browser_ready || {
    echo "Chromium installation did not complete in $browser_home." >&2
    exit 1
  }
fi

if [ "$#" -gt 0 ]; then
  if [ "$1" = "playwright" ]; then
    shift
  fi
  if [ "${1:-}" = "node" ]; then
    shift
    exec env PLAYWRIGHT_TOOL_HOME="$tool_home" PLAYWRIGHT_BROWSERS_PATH="$browser_home" node "$@"
  fi
  # `playwright test` is the heavy headless-Chromium capture; gate it through the
  # machine-local concurrency semaphore so parallel fan-out can't overload the box
  # (default 2, MAX_CONCURRENT_CAPTURES to override). Other playwright subcommands
  # (e.g. --version) and the node seed-auth login above stay ungated.
  if [ "${1:-}" = "test" ]; then
    exec "$script_dir/capture-lock.sh" -- env PLAYWRIGHT_TOOL_HOME="$tool_home" PLAYWRIGHT_BROWSERS_PATH="$browser_home" "$playwright" "$@"
  fi
  exec env PLAYWRIGHT_TOOL_HOME="$tool_home" PLAYWRIGHT_BROWSERS_PATH="$browser_home" "$playwright" "$@"
fi

printf 'Playwright capture tooling is ready in %s (Chromium cache: %s).\n' "$tool_home" "$browser_home"
