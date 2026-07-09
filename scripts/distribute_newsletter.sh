#!/usr/bin/env bash
#
# Distribute the next JCVB newsletter, then publish the site.
#
# Usage:
#   scripts/distribute_newsletter.sh          # real send + build/deploy site
#   scripts/distribute_newsletter.sh --test   # dry run: test recipient only, no deploy
#
# Real run:
#   1. Send Next-Newsletter.md to the distribution list (SendGrid). This also
#      files the newsletter into site/content/newsletters/ and commits it.
#   2. Build + deploy the site so the newsletter shows up publicly.
#
# Test run (--test):
#   - Sends only to the test recipient, does NOT file/commit the newsletter,
#     and skips the build/deploy. Use to preview before the real send.
#
# Credentials (SendGrid + Azure) are loaded from .env by the underlying
# tools; see src/jcvb/newsletter.py and scripts/deploy.sh.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

TEST_MODE=""
for arg in "$@"; do
  case "$arg" in
    --test) TEST_MODE="--test" ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [[ -n "$TEST_MODE" ]]; then
  echo "==> distributing newsletter (TEST — test recipient only)..."
  uv run python -m jcvb.newsletter --test
  echo "==> done. test newsletter sent; site NOT deployed."
  exit 0
fi

echo "==> distributing newsletter..."
uv run python -m jcvb.newsletter

echo "==> building + deploying site..."
sh scripts/deploy.sh

echo "==> done. newsletter sent and site published."
