// Azure Bicep deployment template for Healthcare Transcription Services
// Deploy with: az deployment group create --resource-group <rg-name> --template-file main.bicep
// 
// This template uses managed identity authentication for all services
// to comply with enterprise security policies (disableLocalAuth: true)

@description('The location for all resources')
param location string = resourceGroup().location

@description('Base name for all resources')
param baseName string = 'healthtranscript'

@description('Environment (dev, staging, prod)')
@allowed(['dev', 'staging', 'prod'])
param environment string = 'dev'

// Generate unique suffix for globally unique names
var uniqueSuffix = uniqueString(resourceGroup().id)
var resourceBaseName = '${baseName}-${environment}'

// Role definition IDs for RBAC
var storageBlobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
var storageQueueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var cognitiveServicesUserRoleId = 'a97b65f3-24c7-4388-baec-2e87135dc908'
var cosmosDbDataContributorRoleId = '00000000-0000-0000-0000-000000000002' // Cosmos DB Built-in Data Contributor

// ============================================================================
// Storage Account - For audio files and function app
// ============================================================================
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: toLower('${take(baseName, 10)}${take(uniqueSuffix, 8)}st')
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowSharedKeyAccess: true // Required for AzureWebJobsStorage
    encryption: {
      services: {
        blob: { enabled: true }
        queue: { enabled: true }
      }
      keySource: 'Microsoft.Storage'
    }
  }
}

// Blob container for audio files
resource audioContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  name: '${storageAccount.name}/default/audio-files'
  properties: {
    publicAccess: 'None'
  }
}

// ============================================================================
// Cosmos DB - For storing transcription jobs and results
// ============================================================================
resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2023-11-15' = {
  name: '${resourceBaseName}-cosmos-${take(uniqueSuffix, 6)}'
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    disableLocalAuth: true // Enforce managed identity auth
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    capabilities: [
      { name: 'EnableServerless' }
    ]
  }
}

resource cosmosDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2023-11-15' = {
  parent: cosmosAccount
  name: 'transcription-db'
  properties: {
    resource: { id: 'transcription-db' }
  }
}

resource cosmosContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2023-11-15' = {
  parent: cosmosDatabase
  name: 'transcriptions'
  properties: {
    resource: {
      id: 'transcriptions'
      partitionKey: {
        paths: ['/id']
        kind: 'Hash'
      }
    }
  }
}

// ============================================================================
// Cognitive Services - Speech Services (with managed identity)
// ============================================================================
resource speechService 'Microsoft.CognitiveServices/accounts@2023-10-01-preview' = {
  name: '${resourceBaseName}-speech-${take(uniqueSuffix, 6)}'
  location: location
  kind: 'SpeechServices'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: '${resourceBaseName}-speech-${take(uniqueSuffix, 6)}'
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true // Enforce managed identity auth
  }
}

// ============================================================================
// Cognitive Services - Language Service (Text Analytics for Health)
// ============================================================================
resource languageService 'Microsoft.CognitiveServices/accounts@2023-10-01-preview' = {
  name: '${resourceBaseName}-lang-${take(uniqueSuffix, 6)}'
  location: location
  kind: 'TextAnalytics'
  sku: { name: 'S' } // Standard tier for Text Analytics for Health
  properties: {
    customSubDomainName: '${resourceBaseName}-lang-${take(uniqueSuffix, 6)}'
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true // Enforce managed identity auth
  }
}

// ============================================================================
// App Service Plan - Elastic Premium for managed identity storage binding
// ============================================================================
resource appServicePlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: '${resourceBaseName}-plan-${take(uniqueSuffix, 6)}'
  location: location
  sku: {
    name: 'EP1'
    tier: 'ElasticPremium'
    family: 'EP'
  }
  kind: 'elastic'
  properties: {
    reserved: true // Linux
    maximumElasticWorkerCount: 20
  }
}

// ============================================================================
// Application Insights - For monitoring
// ============================================================================
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${resourceBaseName}-insights-${take(uniqueSuffix, 6)}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    Request_Source: 'rest'
  }
}

// ============================================================================
// Function App - Backend API with System Assigned Managed Identity
// ============================================================================
resource functionApp 'Microsoft.Web/sites@2023-01-01' = {
  name: '${resourceBaseName}-func-${take(uniqueSuffix, 6)}'
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    siteConfig: {
      pythonVersion: '3.11'
      linuxFxVersion: 'Python|3.11'
      cors: {
        allowedOrigins: ['*']
      }
      appSettings: [
        // Storage - Managed Identity binding
        { name: 'AzureWebJobsStorage__accountName', value: storageAccount.name }
        // Functions runtime
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
        // Application Insights
        { name: 'APPINSIGHTS_INSTRUMENTATIONKEY', value: appInsights.properties.InstrumentationKey }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
        // Speech Service - Managed Identity (no keys)
        { name: 'AZURE_SPEECH_ENDPOINT', value: speechService.properties.endpoint }
        { name: 'AZURE_SPEECH_REGION', value: location }
        // Language Service - Managed Identity (no keys)
        { name: 'AZURE_LANGUAGE_ENDPOINT', value: languageService.properties.endpoint }
        // Cosmos DB - Managed Identity (no connection string)
        { name: 'COSMOS_ENDPOINT', value: cosmosAccount.properties.documentEndpoint }
        { name: 'COSMOS_DATABASE_NAME', value: cosmosDatabase.name }
        { name: 'COSMOS_CONTAINER_NAME', value: cosmosContainer.name }
        // Storage for blob operations
        { name: 'STORAGE_ACCOUNT_NAME', value: storageAccount.name }
        { name: 'STORAGE_CONTAINER_NAME', value: 'audio-files' }
        // Build settings
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
        { name: 'ENABLE_ORYX_BUILD', value: 'true' }
      ]
    }
  }
}

// Enable SCM basic auth for deployment (required for GitHub Actions)
resource functionAppScmBasicAuth 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2023-01-01' = {
  parent: functionApp
  name: 'scm'
  properties: { allow: true }
}

resource functionAppFtpBasicAuth 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2023-01-01' = {
  parent: functionApp
  name: 'ftp'
  properties: { allow: true }
}

// ============================================================================
// RBAC - Storage Blob Data Owner (for blob operations)
// ============================================================================
resource storageBlobDataOwnerRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, functionApp.id, storageBlobDataOwnerRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataOwnerRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================================
// RBAC - Storage Queue Data Contributor (for function triggers)
// ============================================================================
resource storageQueueDataContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, functionApp.id, storageQueueDataContributorRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageQueueDataContributorRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================================
// RBAC - Cognitive Services User for Speech Service
// ============================================================================
resource speechServiceRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(speechService.id, functionApp.id, cognitiveServicesUserRoleId)
  scope: speechService
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================================
// RBAC - Cognitive Services User for Language Service
// ============================================================================
resource languageServiceRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(languageService.id, functionApp.id, cognitiveServicesUserRoleId)
  scope: languageService
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================================
// RBAC - Cosmos DB Data Contributor
// ============================================================================
resource cosmosDbRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2023-11-15' = {
  parent: cosmosAccount
  name: guid(cosmosAccount.id, functionApp.id, cosmosDbDataContributorRoleId)
  properties: {
    roleDefinitionId: '${cosmosAccount.id}/sqlRoleDefinitions/${cosmosDbDataContributorRoleId}'
    principalId: functionApp.identity.principalId
    scope: cosmosAccount.id
  }
}

// ============================================================================
// Static Web App - Frontend hosting
// ============================================================================
resource staticWebApp 'Microsoft.Web/staticSites@2023-01-01' = {
  name: '${resourceBaseName}-web-${take(uniqueSuffix, 6)}'
  location: 'centralus' // Static Web Apps have limited region availability
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {
    buildProperties: {
      appLocation: '/frontend'
      outputLocation: '/frontend'
    }
  }
}

// ============================================================================
// Outputs - Used by GitHub Actions for deployment
// ============================================================================
output functionAppName string = functionApp.name
output functionAppUrl string = 'https://${functionApp.properties.defaultHostName}'
output staticWebAppName string = staticWebApp.name
output staticWebAppUrl string = 'https://${staticWebApp.properties.defaultHostname}'
output speechServiceEndpoint string = speechService.properties.endpoint
output languageServiceEndpoint string = languageService.properties.endpoint
output cosmosAccountEndpoint string = cosmosAccount.properties.documentEndpoint
output storageAccountName string = storageAccount.name
output resourceGroup string = resourceGroup().name
