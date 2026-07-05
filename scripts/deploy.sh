#!/usr/bin/env bash
#
# Deploy the built JCVB site to Azure Blob Storage (Anvilor Sites).
# The `jcvb` container is served at https://sites.anvilor.com/jcvb, so the
# CONTENTS of build/jcvb/ are uploaded to the container root.
#
# Auth: a service principal whose creds live in .env (never committed):
#   JCVB_SITE_MGR_SP_TENANT_ID, JCVB_SITE_MGR_SP_CLIENT_ID, JCVB_SITE_MGR_SP_PASSWORD
# The SP needs the "Storage Blob Data Contributor" role on the account/container.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# --- Config ---
ACCOUNT_NAME="stwanvlsitesprod001"
CONTAINER="jcvb"
SRC_DIR="build/${CONTAINER}"   # container root == /jcvb, so upload build/jcvb/*

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

# --- Sign in the service principal (data-plane auth via Azure AD) ---
echo "signing in service principal..."
az login --service-principal \
  --username "${JCVB_SITE_MGR_SP_CLIENT_ID}" \
  --password "${JCVB_SITE_MGR_SP_PASSWORD}" \
  --tenant "${JCVB_SITE_MGR_SP_TENANT_ID}" \
  --output none
trap 'az logout --output none 2>/dev/null || true' EXIT

AUTH=(--auth-mode login)

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
