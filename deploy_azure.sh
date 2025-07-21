#!/bin/bash
# Simple deployment script for Azure resources
set -e

LOCATION=${LOCATION:-eastus}
TEMPLATE_FILE="infrastructure/main.bicep"

if ! command -v az >/dev/null; then
  echo "Azure CLI not found" >&2
  exit 1
fi

echo "Deploying resources to $LOCATION using $TEMPLATE_FILE"
az deployment sub create --location "$LOCATION" --template-file "$TEMPLATE_FILE"
