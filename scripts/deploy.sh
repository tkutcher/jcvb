#!/usr/bin/env bash
#
# Deploy the built JCVB site to Azure Blob Storage (Anvilor Sites).
# The `jcvb` container is served at https://sites.anvilor.com/jcvb, so the
# CONTENTS of build/jcvb/ are uploaded to the container root.
#
# Usage: sh scripts/deploy.sh [prod|staging] [--dry-run]
#   prod     -> container `jcvb`         https://sites.anvilor.com/jcvb/
#   staging  -> container `jcvb-staging` https://sites.anvilor.com/jcvb-staging/
# Staging is the same build under a different base path, so every link is
# rewritten — a staging deploy can never link back into prod by accident.
# --dry-run builds and reports what would happen, and touches nothing remote.
#
# Auth: a service principal whose creds live in .env (never committed):
#   JCVB_SITE_MGR_SP_TENANT_ID, JCVB_SITE_MGR_SP_CLIENT_ID, JCVB_SITE_MGR_SP_PASSWORD
# The SP needs the "Storage Blob Data Contributor" role on the account/container.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# --- Config ---
ACCOUNT_NAME="stwanvlsitesprod001"

TARGET="prod"
DRY_RUN="no"
for arg in "$@"; do
  case "$arg" in
    prod|production) TARGET="prod" ;;
    staging|stage)   TARGET="staging" ;;
    --dry-run)       DRY_RUN="yes" ;;
    *) echo "usage: sh scripts/deploy.sh [prod|staging] [--dry-run]" >&2; exit 2 ;;
  esac
done

if [[ "$TARGET" == "staging" ]]; then
  CONTAINER="jcvb-staging"
else
  CONTAINER="jcvb"
fi
export JCVB_BASE_PATH="/${CONTAINER}"
export JCVB_CANONICAL_URL="https://sites.anvilor.com/${CONTAINER}"
SRC_DIR="build/${CONTAINER}"   # container root == /<container>, so upload its contents

echo "target: ${TARGET} → container ${CONTAINER}"

# --- Load service-principal credentials from .env ---
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
: "${JCVB_SITE_MGR_SP_TENANT_ID:?missing in .env}"
: "${JCVB_SITE_MGR_SP_CLIENT_ID:?missing in .env}"
: "${JCVB_SITE_MGR_SP_PASSWORD:?missing in .env}"

# --- Build fresh ---
echo "building site..."
sh scripts/build.sh
[[ -d "$SRC_DIR" ]] || { echo "error: $SRC_DIR not found (build failed?)" >&2; exit 1; }

if [[ "$DRY_RUN" == "yes" ]]; then
  echo "dry run — would sync $(find "$SRC_DIR" -type f | wc -l | tr -d ' ') files"
  echo "  to container ${CONTAINER} on ${ACCOUNT_NAME}"
  echo "  → https://sites.anvilor.com/${CONTAINER}/"
  exit 0
fi

# --- Sign in the service principal (data-plane auth via Azure AD) ---
echo "signing in service principal..."
az login --service-principal \
  --username "${JCVB_SITE_MGR_SP_CLIENT_ID}" \
  --password "${JCVB_SITE_MGR_SP_PASSWORD}" \
  --tenant "${JCVB_SITE_MGR_SP_TENANT_ID}" \
  --output none
trap 'az logout --output none 2>/dev/null || true' EXIT

AUTH=(--auth-mode login)

if ! az storage blob list --account-name "${ACCOUNT_NAME}" "${AUTH[@]}" \
     --container-name "${CONTAINER}" --num-results 1 --output none 2>/dev/null; then
  echo "error: container '${CONTAINER}' is not reachable on ${ACCOUNT_NAME}." >&2
  if [[ "$TARGET" == "staging" ]]; then
    echo "Create it once with:" >&2
    echo "  az storage container create --account-name ${ACCOUNT_NAME} \\" >&2
    echo "    --auth-mode login --name ${CONTAINER} --public-access blob" >&2
    echo "Anvilor Sites also has to route /${CONTAINER} to it." >&2
  fi
  exit 1
fi

echo "removing old contents..."
az storage blob delete-batch \
  --account-name "${ACCOUNT_NAME}" \
  "${AUTH[@]}" \
  --source "${CONTAINER}" \
  --pattern "*"

echo "uploading new contents..."
az storage blob upload-batch \
  --account-name "${ACCOUNT_NAME}" \
  "${AUTH[@]}" \
  --source "${SRC_DIR}" \
  --destination "${CONTAINER}" \
  --overwrite true

echo "done. → https://sites.anvilor.com/${CONTAINER}/"
