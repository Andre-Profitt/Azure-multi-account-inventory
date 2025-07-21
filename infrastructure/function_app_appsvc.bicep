param location string = resourceGroup().location
param functionAppName string = 'inventory${uniqueString(resourceGroup().id)}'
param storageAccountName string = 'invapp${uniqueString(resourceGroup().id)}'
param keyVaultName string
param subscriptionIdSecretName string = 'azure-subscription-id'
param tableStorageSecretName string = 'table-storage-conn'

resource keyVault 'Microsoft.KeyVault/vaults@2022-07-01' existing = {
  name: keyVaultName
}

var subscriptionIdSecretUri = 'https://${keyVault.name}.vault.azure.net/secrets/${subscriptionIdSecretName}'
var tableStorageSecretUri = 'https://${keyVault.name}.vault.azure.net/secrets/${tableStorageSecretName}'

resource storageAccount 'Microsoft.Storage/storageAccounts@2022-09-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
}

resource appPlan 'Microsoft.Web/serverfarms@2022-09-01' = {
  name: '${functionAppName}-plan'
  location: location
  sku: {
    name: 'Y1'
    tier: 'Dynamic'
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
          value: storageAccount.properties.primaryEndpoints.blob
        }
        {
          name: 'AZURE_SUBSCRIPTION_ID'
          value: '@Microsoft.KeyVault(SecretUri=${subscriptionIdSecretUri})'
        }
        {
          name: 'TABLE_STORAGE'
          value: '@Microsoft.KeyVault(SecretUri=${tableStorageSecretUri})'
        }
      ]
    }
  }
}

resource timerFunction 'Microsoft.Web/sites/functions@2022-09-01' = {
  name: '${functionApp.name}/InventoryTimer'
  properties: {
    config: {
      bindings: [
        {
          name: 'myTimer'
          direction: 'in'
          type: 'timerTrigger'
          schedule: '0 0 */6 * * *'
        }
      ]
      scriptFile: 'azure_function_main.py'
    }
  }
}

output functionAppName string = functionApp.name
