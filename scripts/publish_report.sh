#!/usr/bin/env bash
# Build the report and publish ./site to the gh-pages branch (GitHub Pages).
#
# One-time setup on github.com:
#   Settings → Pages → Build and deployment → Source: "Deploy from a branch",
#   Branch: gh-pages / (root).
#
# After the first publish, the report lives at:
#   https://<user>.github.io/<repo>/<slug>/
# where <slug> is the value in config/report.local.yaml (gitignored).
#
# Usage: scripts/publish_report.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SITE_DIR="$PROJECT_ROOT/site"
WORKTREE_DIR="$PROJECT_ROOT/.ghpages"

cd "$PROJECT_ROOT"

# 1. Generate the report.
"$SCRIPT_DIR/build_report.sh"

# 2. Attach a worktree pinned to gh-pages (create the branch if it doesn't exist).
git worktree remove --force "$WORKTREE_DIR" 2>/dev/null || true
if git show-ref --verify --quiet refs/heads/gh-pages; then
  git worktree add --force "$WORKTREE_DIR" gh-pages
elif git ls-remote --exit-code --heads origin gh-pages >/dev/null 2>&1; then
  git fetch origin gh-pages
  git worktree add --force "$WORKTREE_DIR" -B gh-pages origin/gh-pages
else
  git worktree add --force "$WORKTREE_DIR" --orphan gh-pages
fi

# 3. Sync the freshly built site into the worktree (replace previous contents).
find "$WORKTREE_DIR" -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +
cp -R "$SITE_DIR"/. "$WORKTREE_DIR"/

# 4. Commit + push.
cd "$WORKTREE_DIR"
git add -A
if git diff --cached --quiet; then
  echo "변경 사항 없음 — 게시 생략."
else
  git commit -m "report: publish $(date -u +%Y-%m-%dT%H:%MZ)"
  git push origin gh-pages
  echo "게시 완료. config/report.local.yaml의 슬러그 경로로 접속하세요."
fi

cd "$PROJECT_ROOT"
git worktree remove --force "$WORKTREE_DIR" 2>/dev/null || true
