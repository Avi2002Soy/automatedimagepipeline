#!/usr/bin/env bash
# One-shot Azure provisioning + deployment. Requires: az CLI (logged in), Azure Functions Core Tools.
set -euo pipefail

SUFFIX="${SUFFIX:-$RANDOM}"
RG="${RG:-rg-image-pipeline}"
LOC="${LOC:-eastus}"                       # pick a region where Vision captions are supported
STORAGE="stimgpipe${SUFFIX}"
COSMOS="cosmos-imgpipe-${SUFFIX}"
VISION="vision-imgpipe-${SUFFIX}"
APP="func-imgpipe-${SUFFIX}"
TOPIC="evgt-imgpipe-${SUFFIX}"

az group create -n "$RG" -l "$LOC"

# Storage + containers
az storage account create -n "$STORAGE" -g "$RG" -l "$LOC" --sku Standard_LRS
STORAGE_CONN=$(az storage account show-connection-string -n "$STORAGE" -g "$RG" -o tsv)
for c in raw-images processed-images; do
  az storage container create --name "$c" --connection-string "$STORAGE_CONN"
done

# Cosmos DB (serverless) — partition key /id
az cosmosdb create -n "$COSMOS" -g "$RG" --capabilities EnableServerless --locations regionName="$LOC"
az cosmosdb sql database create -a "$COSMOS" -g "$RG" -n imagedb
az cosmosdb sql container create -a "$COSMOS" -g "$RG" -d imagedb -n metadata --partition-key-path "/id"
COSMOS_ENDPOINT=$(az cosmosdb show -n "$COSMOS" -g "$RG" --query documentEndpoint -o tsv)
COSMOS_KEY=$(az cosmosdb keys list -n "$COSMOS" -g "$RG" --query primaryMasterKey -o tsv)

# Azure AI Vision
az cognitiveservices account create -n "$VISION" -g "$RG" -l "$LOC" --kind ComputerVision --sku S1 --yes
VISION_ENDPOINT=$(az cognitiveservices account show -n "$VISION" -g "$RG" --query properties.endpoint -o tsv)
VISION_KEY=$(az cognitiveservices account keys list -n "$VISION" -g "$RG" --query key1 -o tsv)

# Function App (Linux, Python 3.11, Consumption)
az functionapp create -n "$APP" -g "$RG" --storage-account "$STORAGE" \
  --consumption-plan-location "$LOC" --runtime python --runtime-version 3.11 \
  --functions-version 4 --os-type Linux
az functionapp config appsettings set -n "$APP" -g "$RG" --settings \
  STORAGE_CONNECTION="$STORAGE_CONN" RAW_CONTAINER=raw-images PROCESSED_CONTAINER=processed-images \
  VISION_ENDPOINT="$VISION_ENDPOINT" VISION_KEY="$VISION_KEY" \
  COSMOS_ENDPOINT="$COSMOS_ENDPOINT" COSMOS_KEY="$COSMOS_KEY" \
  COSMOS_DATABASE=imagedb COSMOS_CONTAINER=metadata

# Deploy code FIRST (Event Grid validates the endpoint when the subscription is created)
func azure functionapp publish "$APP" --python

# Event Grid: BlobCreated in raw-images -> blob trigger webhook
BLOBS_KEY=$(az functionapp keys list -n "$APP" -g "$RG" --query systemKeys.blobs_extension -o tsv)
STORAGE_ID=$(az storage account show -n "$STORAGE" -g "$RG" --query id -o tsv)
az eventgrid system-topic create -n "$TOPIC" -g "$RG" -l "$LOC" \
  --source "$STORAGE_ID" --topic-type microsoft.storage.storageaccounts
az eventgrid system-topic event-subscription create -n blob-created-to-func \
  --system-topic-name "$TOPIC" -g "$RG" \
  --endpoint-type webhook \
  --endpoint "https://${APP}.azurewebsites.net/runtime/webhooks/blobs?functionName=Host.Functions.process_image&code=${BLOBS_KEY}" \
  --included-event-types Microsoft.Storage.BlobCreated \
  --subject-begins-with /blobServices/default/containers/raw-images/

echo "Done. Upload an image to the 'raw-images' container to trigger the pipeline."
