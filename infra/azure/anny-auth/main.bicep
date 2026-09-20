targetScope = 'resourceGroup'

@description('Existing Azure Container Apps environment hosting the isolated ANNY Auth service.')
param containerAppsEnvironmentName string = 'cae-cnaz001'

@description('New isolated Container App for ANNY hosted authorization.')
param authContainerAppName string = 'ca-anny-auth'

@description('Existing Azure Container Registry name.')
param containerRegistryName string = 'cnaz001acrvwee7dlf'

@description('Existing Key Vault name.')
param keyVaultName string = 'kvconrradcp001'

@description('Container image repository/name.')
param imageRepository string = 'anny-auth'

@description('Synthetic tag used only for read-only what-if. Replace with an immutable reviewed tag/digest before deployment.')
param imageTag string = 'what-if-only'

@description('Synthetic hostname used only for read-only what-if. Replace with the approved public hostname before deployment.')
param authHostname string = 'auth.what-if.invalid'

@description('GitHub App secret name in Key Vault. The secret value is never stored here.')
param githubAppClientSecretName string = 'github-app-client-secret'

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: containerAppsEnvironmentName
}

resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = {
  name: containerRegistryName
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource authIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'mi-anny-auth'
  location: resourceGroup().location
}

resource authAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, authIdentity.id, 'AcrPull')
  scope: registry
  properties: {
    principalId: authIdentity.properties.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
    principalType: 'ServicePrincipal'
  }
}

resource authKeyVaultSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, authIdentity.id, 'KeyVaultSecretsUser')
  scope: keyVault
  properties: {
    principalId: authIdentity.properties.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
    principalType: 'ServicePrincipal'
  }
}

resource authApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: authContainerAppName
  location: resourceGroup().location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      ${authIdentity.id}: {}
    }
  }
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: authIdentity.id
        }
      ]
      secrets: [
        {
          name: githubAppClientSecretName
          keyVaultUrl: ${keyVault.properties.vaultUri}secrets/${githubAppClientSecretName}
          identity: authIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'anny-auth'
          image: ${registry.properties.loginServer}/${imageRepository}:${imageTag}
          env: [
            { name: 'ANNY_AUTH_ISSUER', value: https://${authHostname} }
            { name: 'ANNY_AUTH_AUDIENCE', value: 'anny-runtime' }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/health', port: 8000 }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 8000 }
              initialDelaySeconds: 5
              periodSeconds: 10
            }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 2
      }
    }
  }
}

output authIdentityId string = authIdentity.id
output authContainerAppId string = authApp.id
output authFqdn string = authApp.properties.configuration.ingress.fqdn
