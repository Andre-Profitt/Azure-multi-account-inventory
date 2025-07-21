// Copyright 2024
// Licensed under the Apache License, Version 2.0
param mspTenantId string
param functionPrincipalId string
param principalTenantId string

resource customRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(subscription().id, 'InventoryReaderRole')
  properties: {
    roleName: 'InventoryReaderRole'
    description: 'Allow Function app to query Resource Graph and Cost Management'
    permissions: [
      {
        actions: [
          'Microsoft.ResourceGraph/*/read',
          'Microsoft.CostManagement/query/action',
          'Microsoft.Resources/subscriptions/resourceGroups/read'
        ]
        notActions: []
      }
    ]
    assignableScopes: [ subscription().id ]
  }
}

resource registrationDef 'Microsoft.ManagedServices/registrationDefinitions@2022-10-01' = {
  name: guid(subscription().id, 'inventoryDelegation')
  properties: {
    registrationDefinitionName: 'Inventory Delegation'
    description: 'Delegation for MSP inventory function'
    managedByTenantId: mspTenantId
      authorizations: [
        {
          principalId: functionPrincipalId
          principalTenantId: principalTenantId
          roleDefinitionId: customRole.id
        }
      ]
  }
}

resource assignment 'Microsoft.ManagedServices/registrationAssignments@2022-10-01' = {
  name: guid(subscription().id, 'inventoryDelegation')
  properties: {
    registrationDefinitionId: registrationDef.id
  }
}
