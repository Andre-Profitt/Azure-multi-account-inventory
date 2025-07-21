// Copyright 2024
// Licensed under the Apache License, Version 2.0
param location string = resourceGroup().location
param storageAccountName string = 'inv${uniqueString(resourceGroup().id)}'
param functionAppName string = 'inventory${uniqueString(resourceGroup().id)}'
param cosmosAccountName string = 'invcosmos${uniqueString(resourceGroup().id)}'

resource storageAccount 'Microsoft.Storage/storageAccounts@2022-09-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2022-11-15' = {
  name: cosmosAccountName
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    locations: [
      {
        failoverPriority: 0
        locationName: location
      }
    ]
    databaseAccountOfferType: 'Standard'
  }
}

resource functionApp 'Microsoft.Web/sites@2022-09-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp'
  properties: {
    serverFarmId: appPlan.id
    siteConfig: {
      appSettings: [
        {
          name: 'AzureWebJobsStorage'
          value: listKeys(storageAccount.id, '2022-09-01').keys[0].value
        }
        {
          name: 'COSMOS_URL'
          value: cosmos.properties.documentEndpoint
        }
        {
          name: 'AZURE_CONFIG'
          value: 'config/azure_subscriptions.json'
        }
      ]
    }
  }
  identity: {
    type: 'SystemAssigned'
  }
}

resource appPlan 'Microsoft.Web/serverfarms@2022-09-01' = {
  name: '${functionAppName}-plan'
  location: location
  sku: {
    name: 'Y1'
    tier: 'Dynamic'
  }
}

resource timer 'Microsoft.Web/sites/functions@2022-09-01' = {
  name: '${functionApp.name}/azure_function_main'
  properties: {
    config: {
      bindings: [
        {
          name: 'timer'
          direction: 'in'
          type: 'timerTrigger'
          schedule: '0 0 */6 * * *'
        }
      ]
      scriptFile: 'azure_function_main.py'
    }
  }
}
