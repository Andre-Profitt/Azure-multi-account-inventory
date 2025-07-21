param roleName string = 'ResourceGraphCostReader'
param description string = 'Allows read access to Resource Graph and Cost Management APIs'
param assignableScopes array = [ subscription().id ]

resource customRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(subscription().id, roleName)
  properties: {
    roleName: roleName
    description: description
    assignableScopes: assignableScopes
    permissions: [
      {
        actions: [
          'Microsoft.ResourceGraph/*/read'
          'Microsoft.CostManagement/*/read'
        ]
        notActions: []
      }
    ]
  }
}

output roleDefinitionId string = customRole.id
