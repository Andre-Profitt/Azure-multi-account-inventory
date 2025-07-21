#!/bin/bash
set -euo pipefail

# Azure deployment script for the multi-account inventory

BLUE='\033[0;34m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
    exit 1
}

check_az_cli() {
    log "Validating Azure CLI..."
    if ! command -v az >/dev/null; then
        error "Azure CLI not found. Install from https://learn.microsoft.com/cli/azure/install-azure-cli"
    fi
    if ! az account show >/dev/null 2>&1; then
        error "Azure CLI not logged in. Run 'az login' first."
    fi
    log "Azure CLI is available"
}

package_function() {
    log "Packaging function code for Azure Functions..."
    WORK_DIR=$(mktemp -d)
    cp -r src/* "$WORK_DIR/"
    cp -r config "$WORK_DIR/" 2>/dev/null || true
    (cd "$WORK_DIR" && zip -r function.zip . -x '*.pyc' '*__pycache__*' >/dev/null)
    FUNCTION_PACKAGE="$WORK_DIR/function.zip"
    log "Function package created: $FUNCTION_PACKAGE"
}

deploy_bicep() {
    log "Deploying Bicep templates..."
    RESOURCE_GROUP="${RESOURCE_GROUP:-inventory-rg}"
    LOCATION="${LOCATION:-eastus}"
    az group create -n "$RESOURCE_GROUP" -l "$LOCATION" >/dev/null
    az deployment group create \
        --resource-group "$RESOURCE_GROUP" \
        --template-file infrastructure/main.bicep \
        --parameters functionPackage=@"$FUNCTION_PACKAGE" >/dev/null
    log "Bicep deployment completed"
}

setup_identity() {
    log "Setting up service principal..."
    APP_NAME="${APP_NAME:-inventory-sp}"
    if ! az ad sp list --display-name "$APP_NAME" --query [].appId -o tsv | grep -q .; then
        az ad sp create-for-rbac -n "$APP_NAME" \
            --role contributor \
            --scopes "/subscriptions/$(az account show --query id -o tsv)" \
            > sp.json
        log "Service principal credentials saved to sp.json"
    else
        log "Service principal $APP_NAME already exists"
    fi
}

trigger_initial_run() {
    log "Triggering initial collection run..."
    FUNCTION_APP=$(az deployment group list --resource-group "$RESOURCE_GROUP" --query '[0].properties.outputs.functionAppName.value' -o tsv 2>/dev/null || echo "")
    if [ -n "$FUNCTION_APP" ]; then
        KEY=$(az functionapp function keys list --function-name CollectInventory --name "$FUNCTION_APP" --resource-group "$RESOURCE_GROUP" --query default -o tsv)
        curl -s -X POST "https://${FUNCTION_APP}.azurewebsites.net/api/CollectInventory?code=${KEY}" >/dev/null || true
        log "Initial collection triggered"
    else
        log "Function app name not found. Trigger manually via the Azure Portal"
    fi
}

main() {
    check_az_cli
    package_function
    deploy_bicep
    setup_identity
    trigger_initial_run
    log "Azure deployment complete"
}

main "$@"
