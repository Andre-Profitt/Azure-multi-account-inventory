param principalId string
param principalTenantId string
param roleDefinitionId string
param definitionName string = 'InventoryDelegation'
param description string = 'Delegate subscription access for the inventory service'

resource regDef 'Microsoft.ManagedServices/registrationDefinitions@2022-10-01-preview' = {
  name: guid(definitionName, subscription().id)
  properties: {
    registrationDefinitionName: definitionName
    description: description
    authorizations: [
      {
        principalId: principalId
        principalIdDisplayName: 'InventoryServicePrincipal'
        roleDefinitionId: roleDefinitionId
      }
    ]
  }
}

resource regAssign 'Microsoft.ManagedServices/registrationAssignments@2022-10-01-preview' = {
  name: guid(definitionName, principalId)
  properties: {
    registrationDefinitionId: regDef.id
  }
}

output registrationDefinitionId string = regDef.id
