// Azure Bicep deployment template for Healthcare Transcription Services
// Deploy with: az deployment group create --resource-group <rg-name> --template-file main.bicep

@description('The location for all resources')
param location string = resourceGroup().location

@description('Base name for all resources')
param baseName string = 'healthtranscription'

@description('Environment (dev, staging, prod)')
@allowed(['dev', 'staging', 'prod'])
param environment string = 'dev'

// Generate unique suffix for globally unique names
var uniqueSuffix = uniqueString(resourceGroup().id)
var resourceBaseName = '${baseName}${environment}'

// ============================================================================
// Storage Account - For audio files and function app
// ============================================================================
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: toLower('${take(resourceBaseName, 14)}${take(uniqueSuffix, 8)}')
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    encryption: {
      services: {
        blob: {
          enabled: true
        }
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
    enableAutomaticFailover: false
    enableMultipleWriteLocations: false
    capabilities: [
      {
        name: 'EnableServerless'
      }
    ]
  }
}

resource cosmosDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2023-11-15' = {
  parent: cosmosAccount
  name: 'transcription-db'
  properties: {
    resource: {
      id: 'transcription-db'
    }
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
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [
          {
            path: '/*'
          }
        ]
      }
    }
  }
}

// ============================================================================
// Cognitive Services - Speech Services
// ============================================================================
resource speechService 'Microsoft.CognitiveServices/accounts@2023-10-01-preview' = {
  name: '${resourceBaseName}-speech-${take(uniqueSuffix, 6)}'
  location: location
  kind: 'SpeechServices'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: '${resourceBaseName}-speech-${take(uniqueSuffix, 6)}'
    publicNetworkAccess: 'Enabled'
  }
}

// ============================================================================
// Cognitive Services - Language Service (Text Analytics for Health)
// ============================================================================
resource languageService 'Microsoft.CognitiveServices/accounts@2023-10-01-preview' = {
  name: '${resourceBaseName}-language-${take(uniqueSuffix, 6)}'
  location: location
  kind: 'TextAnalytics'
  sku: {
    name: 'S'
  }
  properties: {
    customSubDomainName: '${resourceBaseName}-language-${take(uniqueSuffix, 6)}'
    publicNetworkAccess: 'Enabled'
  }
}

// ============================================================================
// App Service Plan - For Azure Functions
// ============================================================================
resource appServicePlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: '${resourceBaseName}-plan'
  location: location
  sku: {
    name: 'Y1'
    tier: 'Dynamic'
  }
  properties: {
    reserved: true // Linux
  }
}

// ============================================================================
// Application Insights - For monitoring
// ============================================================================
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${resourceBaseName}-insights'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    Request_Source: 'rest'
  }
}

// ============================================================================
// Function App - Backend API
// ============================================================================
resource functionApp 'Microsoft.Web/sites@2023-01-01' = {
  name: '${resourceBaseName}-func-${take(uniqueSuffix, 6)}'
  location: location
  kind: 'functionapp,linux'
  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      pythonVersion: '3.11'
      linuxFxVersion: 'Python|3.11'
      cors: {
        allowedOrigins: ['*']
      }
      appSettings: [
        {
          name: 'AzureWebJobsStorage'
          value: 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};EndpointSuffix=${az.environment().suffixes.storage};AccountKey=${storageAccount.listKeys().keys[0].value}'
        }
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'python'
        }
        {
          name: 'APPINSIGHTS_INSTRUMENTATIONKEY'
          value: appInsights.properties.InstrumentationKey
        }
        {
          name: 'AZURE_SPEECH_KEY'
          value: speechService.listKeys().key1
        }
        {
          name: 'AZURE_SPEECH_REGION'
          value: location
        }
        {
          name: 'AZURE_LANGUAGE_KEY'
          value: languageService.listKeys().key1
        }
        {
          name: 'AZURE_LANGUAGE_ENDPOINT'
          value: languageService.properties.endpoint
        }
        {
          name: 'COSMOS_CONNECTION_STRING'
          value: cosmosAccount.listConnectionStrings().connectionStrings[0].connectionString
        }
        {
          name: 'COSMOS_DATABASE_NAME'
          value: cosmosDatabase.name
        }
        {
          name: 'COSMOS_CONTAINER_NAME'
          value: cosmosContainer.name
        }
        {
          name: 'STORAGE_CONNECTION_STRING'
          value: 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};EndpointSuffix=${az.environment().suffixes.storage};AccountKey=${storageAccount.listKeys().keys[0].value}'
        }
        {
          name: 'STORAGE_CONTAINER_NAME'
          value: 'audio-files'
        }
      ]
    }
    httpsOnly: true
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
    repositoryUrl: ''
    branch: ''
    buildProperties: {
      appLocation: '/frontend'
      outputLocation: '/frontend'
    }
  }
}

// ============================================================================
// Outputs
// ============================================================================
output functionAppName string = functionApp.name
output functionAppUrl string = 'https://${functionApp.properties.defaultHostName}'
output staticWebAppName string = staticWebApp.name
output staticWebAppUrl string = 'https://${staticWebApp.properties.defaultHostname}'
output speechServiceEndpoint string = speechService.properties.endpoint
output languageServiceEndpoint string = languageService.properties.endpoint
output cosmosAccountEndpoint string = cosmosAccount.properties.documentEndpoint
output storageAccountName string = storageAccount.name

// Instructions output
output deploymentInstructions string = '''
Deployment Complete!

Next Steps:
1. Deploy the Function App code:
   func azure functionapp publish ${functionAppName}

2. Configure the Static Web App:
   - Link to your GitHub repository, or
   - Deploy manually using SWA CLI

3. Update the frontend API_BASE_URL to point to:
   ${functionAppUrl}/api

4. For HIPAA compliance:
   - Enable Azure Monitor diagnostic settings
   - Configure managed identities
   - Set up VNet integration for production
'''
