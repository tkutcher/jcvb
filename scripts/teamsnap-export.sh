#!/usr/bin/env bash
#
# Refresh the TeamSnap import CSVs from the published JCVB calendar.
# Cron-safe wrapper: resolves the repo itself so it works from any cwd.
#
# Writes three CSVs (games / practices / other events) to .outputs/teamsnap/
# unless a destination is given as $1. Any argument after that is passed
# through to the module, e.g.:
#
#   scripts/teamsnap-export.sh ~/Desktop --from 2026-08-01
#
# The importer skips duplicate events, so re-importing a refreshed file only
# adds what's new — but the export itself is the safe part; nothing is sent to
# TeamSnap here. Uploading stays a manual step.
#
# Weekly via cron (uv must be on cron's PATH — use its absolute path if not):
#   0 7 * * 1 /Users/tkutcher/TK/github/jcvb/scripts/teamsnap-export.sh >> /tmp/jcvb-teamsnap.log 2>&1
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${1:-$REPO_ROOT/.outputs/teamsnap}"
[ $# -gt 0 ] && shift

cd "$REPO_ROOT"
exec uv run python -m jcvb.teamsnap_calendar --out-dir "$OUT_DIR" "$@"
