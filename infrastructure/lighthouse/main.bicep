param principalId string
param principalTenantId string

module role 'customRole.bicep' = {
  name: 'customRole'
}

module delegation 'delegation.bicep' = {
  name: 'delegation'
  params: {
    principalId: principalId
    principalTenantId: principalTenantId
    roleDefinitionId: role.outputs.roleDefinitionId
  }
}

output registrationDefinitionId string = delegation.outputs.registrationDefinitionId
output roleDefinitionId string = role.outputs.roleDefinitionId
