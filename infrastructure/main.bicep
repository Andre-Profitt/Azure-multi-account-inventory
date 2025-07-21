param location string = resourceGroup().location
param storageAccountName string = 'inv${uniqueString(resourceGroup().id)}'
param reportsStorageName string = 'invrep${uniqueString(resourceGroup().id)}'
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

resource inventoryTable 'Microsoft.Storage/storageAccounts/tableServices/tables@2022-09-01' = {
  name: '${storageAccount.name}/default/inventory'
}

resource reportsStorage 'Microsoft.Storage/storageAccounts@2022-09-01' = {
  name: reportsStorageName
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
          name: 'TABLE_STORAGE'
          value: storageAccount.name
        }
        {
          name: 'REPORTS_STORAGE'
          value: reportsStorage.name
        }
      ]
    }
  }
}

resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${functionAppName}-insights'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
  }
}

resource errorAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'FunctionErrorAlert'
  location: location
  properties: {
    description: 'Alert on function errors'
    severity: 2
    enabled: true
    scopes: [functionApp.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    criteria: {
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          metricName: 'FunctionsErrors'
          metricNamespace: 'microsoft.web/sites'
          operator: 'GreaterThan'
          threshold: 1
          timeAggregation: 'Total'
        }
      ]
    }
  }
}

resource collectorFunction 'Microsoft.Web/sites/functions@2022-09-01' = {
  name: '${functionApp.name}/Collector'
  properties: {
    config: {
      bindings: [
        {
          name: 'timer'
          direction: 'in'
          type: 'timerTrigger'
          schedule: '0 0 * * * *'
        }
      ]
      scriptFile: 'azure_function_main.py'
    }
  }
}

resource queryFunction 'Microsoft.Web/sites/functions@2022-09-01' = {
  name: '${functionApp.name}/Query'
  properties: {
    config: {
      bindings: [
        {
          authLevel: 'function'
          type: 'httpTrigger'
          direction: 'in'
          name: 'req'
          methods: ['get']
        }
        {
          type: 'http'
          direction: 'out'
          name: 'res'
        }
      ]
      scriptFile: 'query/enhanced_inventory_query.py'
    }
  }
}

output functionAppName string = functionApp.name
output storageAccountName string = storageAccount.name
output reportsStorageName string = reportsStorage.name
