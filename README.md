# Azure Healthcare Transcription Services Demo

A demo application demonstrating Azure Speech Services for audio transcription with Text Analytics for Health for medical entity extraction and analysis.

## Overview

This application provides an automated pipeline for:
- **Audio Transcription**: Convert recorded interviews/conversations to text using Azure Speech Services
- **Medical Text Analytics**: Extract medical entities, relationships, and FHIR-structured data using Text Analytics for Health
- **HIPAA-Compliant Storage**: Secure storage in Azure Cosmos DB with full audit capabilities

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│   Audio Upload  │ →  │ Azure Functions  │ →  │ Speech to Text API  │
│ (Blob Storage)  │    │  (Orchestrator)  │    │ (Transcription)     │
└─────────────────┘    └──────────────────┘    └─────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     Text Analytics for Health                       │
│           (Medical Entity Extraction & Analysis)                    │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│   Results API   │ ←  │   Cosmos DB      │ ←  │    JSON Processing  │
│  (Web/Mobile)   │    │ (HIPAA Storage)  │    │ (Structured Data)   │
└─────────────────┘    └──────────────────┘    └─────────────────────┘
```

## Project Structure

```
transcription-services-demo/
├── api/                          # Azure Functions backend
│   ├── upload_audio/             # Audio file upload handler
│   ├── process_transcription/    # Speech-to-text processing
│   ├── analyze_health/           # Text Analytics for Health
│   ├── get_results/              # Retrieve processed results
│   └── shared/                   # Shared utilities
├── frontend/                     # Web interface
│   ├── index.html                # Main upload interface
│   ├── styles.css                # Application styles
│   └── app.js                    # Frontend JavaScript
├── infra/                        # Infrastructure as Code
│   └── main.bicep                # Azure Bicep deployment
├── samples/                      # Sample audio and transcripts
│   └── sample_health_dialog.txt  # Sample healthcare conversation
├── requirements.txt              # Python dependencies
├── host.json                     # Azure Functions host config
├── local.settings.json           # Local development settings
└── README.md
```

## Prerequisites

- Python 3.9+
- Azure Subscription with the following services:
  - Azure Speech Services
  - Azure Language Service (Text Analytics for Health)
  - Azure Cosmos DB
  - Azure Blob Storage
  - Azure Functions

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `local.settings.example.json` to `local.settings.json` and update with your Azure credentials:

```json
{
  "Values": {
    "AZURE_SPEECH_KEY": "your-speech-key",
    "AZURE_SPEECH_REGION": "your-region",
    "AZURE_LANGUAGE_KEY": "your-language-key",
    "AZURE_LANGUAGE_ENDPOINT": "your-endpoint",
    "COSMOS_CONNECTION_STRING": "your-cosmos-connection",
    "STORAGE_CONNECTION_STRING": "your-storage-connection"
  }
}
```

### 3. Run Locally

```bash
func start
```

### 4. Deploy to Azure

```bash
az deployment group create --resource-group your-rg --template-file infra/main.bicep
func azure functionapp publish your-function-app
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/upload` | POST | Upload audio file for processing |
| `/api/status/{id}` | GET | Get processing status |
| `/api/results/{id}` | GET | Get transcription and analysis results |
| `/api/health` | GET | Health check endpoint |

## Cost Comparison

| Service | Azure Cost | TranscribeMe | Savings |
|---------|------------|--------------|---------|
| Batch Transcription | $0.003/min | $0.79/min | 99.6% |
| Real-time | $0.017/min | $0.79/min | 97.8% |

## HIPAA Compliance

This demo is designed for HIPAA-eligible deployments:
- All data encrypted in transit and at rest.
- Azure services configured with BAA support.
- Audit logging enabled.
- Data residency in approved US regions.

## Documentation

- [Azure Speech to Text](https://learn.microsoft.com/azure/ai-services/speech-service/speech-to-text)
- [Batch Transcription](https://learn.microsoft.com/azure/ai-services/speech-service/batch-transcription)
- [Text Analytics for Health](https://learn.microsoft.com/azure/ai-services/language-service/text-analytics-for-health/overview)
- [FHIR Integration](https://learn.microsoft.com/azure/ai-services/language-service/text-analytics-for-health/fhir)

## License

MIT License - See LICENSE file for details
