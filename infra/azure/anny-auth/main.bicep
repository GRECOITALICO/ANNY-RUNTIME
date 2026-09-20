targetScope = 'resourceGroup'

@description('Existing Azure Container Apps environment hosting the isolated ANNY Auth service.')
param containerAppsEnvironmentName string = 'cae-cnaz001'

@description('New isolated Container App for ANNY hosted authorization.')
param authContainerAppName string = 'ca-anny-auth'

@description('Existing Azure Container Registry.')
param containerRegistryName string = 'cnaz001acrvwee7dlf'

@description('Existing Key Vault. No secret values are embedded here.')
param keyVaultName string = 'kvconrradcp001'

@description('Container image repository/name.')
param imageRepository string = 'anny-auth'

@description('Immutable image tag or digest. Must not remain DESIGN_ONLY for deployment.')
param imageTag string = 'DESIGN_ONLY'

@description('Future public hostname for authorization. DNS ownership must be verified before deployment.')
param authHostname string = 'auth.REPLACE_ME'

@description('Resource ID of dedicated user-assigned managed identity.')
param authManagedIdentityResourceId string = 'REPLACE_ME'

@description('Key Vault secret URI for the GitHub App client secret.')
param githubAppClientSecretUri string = 'REPLACE_ME'

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: containerAppsEnvironmentName
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01' existing = {
  name: containerRegistryName
}

resource authApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: authContainerAppName
  location: resourceGroup().location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${authManagedIdentityResourceId}': {}
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
          identity: authManagedIdentityResourceId
        }
      ]
      secrets: [
        {
          name: 'github-app-client-secret'
          keyVaultUrl: githubAppClientSecretUri
          identity: authManagedIdentityResourceId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'anny-auth'
          image: '${registry.properties.loginServer}/${imageRepository}:${imageTag}'
          env: [
            { name: 'ANNY_AUTH_ISSUER', value: 'https://${authHostname}' }
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

output authContainerAppId string = authApp.id
output authFqdn string = authApp.properties.configuration.ingress.fqdn