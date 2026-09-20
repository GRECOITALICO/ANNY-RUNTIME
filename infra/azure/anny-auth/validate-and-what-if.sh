#!/usr/bin/env bash
set -euo pipefail

# DESIGN/DRY-RUN ONLY.
# This script validates Bicep and executes ARM what-if.
# It MUST NOT deploy, create, update, delete, assign roles, or write secrets.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$ROOT/main.bicep"
PARAMS="${PARAMS_FILE:-$ROOT/parameters.local.json}"

command -v az >/dev/null 2>&1 || {
  echo "BLOCKED: Azure CLI (az) is unavailable."
  exit 20
}

test -f "$TEMPLATE" || {
  echo "BLOCKED: Bicep template not found: $TEMPLATE"
  exit 21
}

test -f "$PARAMS" || {
  echo "BLOCKED: parameter file not found: $PARAMS"
  exit 22
}

az account show >/dev/null || {
  echo "BLOCKED: authenticated Azure session unavailable."
  exit 23
}

SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-conrrad-cn-az-001}"

echo "AZURE_SUBSCRIPTION=$SUBSCRIPTION_ID"
echo "RESOURCE_GROUP=$RESOURCE_GROUP"
echo "MODE=VALIDATION_AND_WHAT_IF_ONLY"

echo
echo "== BICEP VALIDATION =="
az bicep build --file "$TEMPLATE" --stdout >/dev/null
echo "BICEP_VALIDATION=PASS"

echo
echo "== WHAT-IF =="
az deployment group what-if   --resource-group "$RESOURCE_GROUP"   --template-file "$TEMPLATE"   --parameters @"$PARAMS"   --result-format FullResourcePayloads

echo
echo "WHAT_IF_COMPLETED=TRUE"
echo "NO_DEPLOYMENT_PERFORMED=TRUE"
