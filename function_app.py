"""
Azure Functions entry point
Healthcare Transcription Services Demo
Simplified version using REST APIs instead of heavy SDKs
"""
import azure.functions as func
import logging
import json
import uuid
import os
import time
import requests
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the main function app
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# ============================================================================
# Configuration
# ============================================================================

@dataclass
class AzureConfig:
    """Configuration for Azure services"""
    speech_key: str
    speech_region: str
    speech_endpoint: str  # Custom endpoint for managed identity
    language_key: str
    language_endpoint: str
    cosmos_connection_string: str
    cosmos_endpoint: str  # For managed identity
    cosmos_database_name: str
    cosmos_container_name: str
    storage_connection_string: str
    storage_container_name: str
    storage_account_name: str  # For managed identity
    
    @classmethod
    def from_environment(cls) -> "AzureConfig":
        return cls(
            speech_key=os.environ.get("AZURE_SPEECH_KEY", ""),
            speech_region=os.environ.get("AZURE_SPEECH_REGION", ""),
            speech_endpoint=os.environ.get("AZURE_SPEECH_ENDPOINT", ""),
            language_key=os.environ.get("AZURE_LANGUAGE_KEY", ""),
            language_endpoint=os.environ.get("AZURE_LANGUAGE_ENDPOINT", ""),
            cosmos_connection_string=os.environ.get("COSMOS_CONNECTION_STRING", ""),
            cosmos_endpoint=os.environ.get("COSMOS_ENDPOINT", ""),
            cosmos_database_name=os.environ.get("COSMOS_DATABASE_NAME", "transcription-db"),
            cosmos_container_name=os.environ.get("COSMOS_CONTAINER_NAME", "transcriptions"),
            storage_connection_string=os.environ.get("STORAGE_CONNECTION_STRING", ""),
            storage_container_name=os.environ.get("STORAGE_CONTAINER_NAME", "audio-files"),
            storage_account_name=os.environ.get("STORAGE_ACCOUNT_NAME", os.environ.get("AzureWebJobsStorage__accountName", "")),
        )
    
    def validate(self) -> bool:
        # Either connection string or endpoint (for managed identity)
        has_storage = bool(self.storage_connection_string) or bool(self.storage_account_name)
        has_cosmos = bool(self.cosmos_connection_string) or bool(self.cosmos_endpoint)
        # Speech: either API key or endpoint (for managed identity)
        has_speech = bool(self.speech_key) or bool(self.speech_endpoint)
        # Language: either API key or endpoint (for managed identity)  
        has_language = bool(self.language_key) or bool(self.language_endpoint)
        
        return all([
            has_speech,
            self.speech_region,
            has_language,
            has_cosmos,
            has_storage,
        ])


class JobStatus:
    PENDING = "pending"
    TRANSCRIBING = "transcribing"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TranscriptionJob:
    id: str
    filename: str
    status: str
    created_at: str
    updated_at: str
    blob_url: Optional[str] = None
    transcription_text: Optional[str] = None
    medical_entities: Optional[dict] = None
    error_message: Optional[str] = None
    processing_time_seconds: Optional[float] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id, "filename": self.filename, "status": self.status,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "blob_url": self.blob_url, "transcription_text": self.transcription_text,
            "medical_entities": self.medical_entities,
            "error_message": self.error_message, "processing_time_seconds": self.processing_time_seconds,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "TranscriptionJob":
        return cls(
            id=data.get("id", ""), filename=data.get("filename", ""),
            status=data.get("status", "pending"), created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""), blob_url=data.get("blob_url"),
            transcription_text=data.get("transcription_text"),
            medical_entities=data.get("medical_entities"),
            error_message=data.get("error_message"), processing_time_seconds=data.get("processing_time_seconds"),
        )


# ============================================================================
# Service Clients (lazy initialization)
# ============================================================================

def get_cosmos_client(config: AzureConfig):
    """Get Cosmos DB client - supports both connection string and managed identity"""
    from azure.cosmos import CosmosClient, PartitionKey
    
    if config.cosmos_connection_string:
        client = CosmosClient.from_connection_string(config.cosmos_connection_string)
    else:
        # Use managed identity
        from azure.identity import DefaultAzureCredential
        client = CosmosClient(config.cosmos_endpoint, credential=DefaultAzureCredential())
    
    database = client.create_database_if_not_exists(id=config.cosmos_database_name)
    container = database.create_container_if_not_exists(
        id=config.cosmos_container_name,
        partition_key=PartitionKey(path="/id"),
        offer_throughput=400
    )
    return container


def get_blob_client(config: AzureConfig, blob_name: str):
    """Get Blob Storage client - supports both connection string and managed identity"""
    from azure.storage.blob import BlobServiceClient
    
    if config.storage_connection_string:
        # Use connection string if available
        service_client = BlobServiceClient.from_connection_string(config.storage_connection_string)
    else:
        # Use managed identity with account name
        from azure.identity import DefaultAzureCredential
        account_url = f"https://{config.storage_account_name}.blob.core.windows.net"
        service_client = BlobServiceClient(account_url, credential=DefaultAzureCredential())
    
    container_client = service_client.get_container_client(config.storage_container_name)
    try:
        container_client.create_container()
    except Exception:
        pass  # Container already exists
    return container_client.get_blob_client(blob_name)


SUPPORTED_FORMATS = {'.wav', '.mp3', '.m4a', '.ogg', '.flac', '.wma', '.aac'}


def is_supported_format(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in SUPPORTED_FORMATS


# ============================================================================
# FHIR Bundle Generator
# ============================================================================

def generate_fhir_bundle(medical_entities: dict) -> dict:
    """Generate a FHIR-compatible bundle from extracted medical entities"""
    if not medical_entities:
        return {"resourceType": "Bundle", "type": "collection", "total": 0, "entry": []}
    
    entities = medical_entities.get("entities", [])
    fhir_resources = []
    
    # Map all Text Analytics for Health categories to FHIR resource types
    # Reference: https://learn.microsoft.com/azure/ai-services/language-service/text-analytics-for-health/concepts/health-entity-categories
    category_to_fhir = {
        # Anatomy
        "BodyStructure": "BodyStructure",
        
        # Demographics
        "Age": "Observation",
        "Ethnicity": "Observation",
        "Gender": "Patient",
        
        # Examinations
        "ExaminationName": "Procedure",
        
        # External Influence
        "Allergen": "AllergyIntolerance",
        
        # General Attributes
        "Course": "Observation",
        "Date": "Observation",
        "Direction": "Observation",
        "Frequency": "Observation",
        "Time": "Observation",
        "MeasurementUnit": "Observation",
        "MeasurementValue": "Observation",
        "RelationalOperator": "Observation",
        
        # Genomics
        "Variant": "Observation",
        "GeneOrProtein": "Observation",
        "MutationType": "Observation",
        "Expression": "Observation",
        
        # Healthcare
        "AdministrativeEvent": "Encounter",
        "CareEnvironment": "Location",
        "HealthcareProfession": "Practitioner",
        
        # Medical Condition
        "Diagnosis": "Condition",
        "SymptomOrSign": "Observation",
        "ConditionQualifier": "Observation",
        "ConditionScale": "Observation",
        
        # Medication
        "MedicationClass": "Medication",
        "MedicationName": "Medication",
        "Dosage": "MedicationStatement",
        "MedicationForm": "Medication",
        "MedicationRoute": "MedicationStatement",
        
        # Social
        "FamilyRelation": "FamilyMemberHistory",
        "Employment": "Observation",
        "LivingStatus": "Observation",
        "SubstanceUse": "Observation",
        "SubstanceUseAmount": "Observation",
        
        # Treatment
        "TreatmentName": "Procedure",
    }
    
    for idx, entity in enumerate(entities, 1):
        category = entity.get("category", "")
        fhir_type = category_to_fhir.get(category, "Observation")
        
        resource = {
            "resourceType": fhir_type,
            "id": f"resource-{idx}",
            "text": {
                "status": "generated",
                "div": f"<div xmlns=\"http://www.w3.org/1999/xhtml\">{entity.get('text', '')}</div>"
            },
            "code": {
                "text": entity.get("text", ""),
                "coding": []
            },
            "meta": {
                "source": "text-analytics-for-health",
                "confidence": entity.get("confidence_score", 0)
            }
        }
        
        # Add data source codes if available
        for ds in entity.get("data_sources", []):
            resource["code"]["coding"].append({
                "system": ds.get("name", ""),
                "code": ds.get("entity_id", "")
            })
        
        # Add assertion information
        if entity.get("assertion"):
            resource["extension"] = [{
                "url": "http://hl7.org/fhir/StructureDefinition/assertion",
                "valueString": str(entity["assertion"])
            }]
        
        fhir_resources.append({
            "fullUrl": f"urn:uuid:resource-{idx}",
            "resource": resource
        })
    
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "total": len(fhir_resources),
        "entry": fhir_resources
    }


# ============================================================================
# Speech REST API (no SDK needed)
# ============================================================================

def get_speech_token(config: AzureConfig) -> str:
    """Get access token for Speech API using managed identity"""
    try:
        from azure.identity import DefaultAzureCredential
        credential = DefaultAzureCredential()
        token = credential.get_token("https://cognitiveservices.azure.com/.default")
        return token.token
    except Exception as e:
        logger.error(f"Failed to get Speech token via managed identity: {e}")
        raise

def transcribe_audio_rest(audio_bytes: bytes, config: AzureConfig) -> str:
    """Transcribe audio using Speech Fast Transcription API (supports Azure AD auth)"""
    # Use Fast Transcription API which supports Azure AD/managed identity
    if config.speech_endpoint:
        base_endpoint = config.speech_endpoint.rstrip('/')
        url = f"{base_endpoint}/speechtotext/transcriptions:transcribe?api-version=2024-11-15"
    else:
        url = f"https://{config.speech_region}.api.cognitive.microsoft.com/speechtotext/transcriptions:transcribe?api-version=2024-11-15"
    
    # Use managed identity token
    try:
        token = get_speech_token(config)
        logger.info(f"Using Fast Transcription API: {url}")
    except Exception as e:
        logger.error(f"Failed to authenticate for Speech API: {e}")
        return f"Authentication failed: {str(e)}"
    
    # Fast Transcription API uses multipart/form-data
    import io
    files = {
        'audio': ('audio.wav', io.BytesIO(audio_bytes), 'audio/wav')
    }
    data = {
        'definition': '{"locales": ["en-US"]}'
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    
    response = requests.post(url, headers=headers, files=files, data=data, timeout=120)
    
    if response.status_code == 200:
        result = response.json()
        # Fast Transcription API returns combinedPhrases with display text
        combined = result.get("combinedPhrases", [])
        if combined:
            return combined[0].get("text", "")
        # Fallback to phrases
        phrases = result.get("phrases", [])
        if phrases:
            return " ".join([p.get("text", "") for p in phrases])
        return "No transcription result"
    else:
        logger.error(f"Speech API error: {response.status_code} - {response.text}")
        return f"Transcription failed: {response.status_code}"


# ============================================================================
# Text Analytics REST API
# ============================================================================

def get_language_token() -> str:
    """Get access token for Language API using managed identity"""
    try:
        from azure.identity import DefaultAzureCredential
        credential = DefaultAzureCredential()
        token = credential.get_token("https://cognitiveservices.azure.com/.default")
        return token.token
    except Exception as e:
        logger.error(f"Failed to get Language token via managed identity: {e}")
        raise

def analyze_health_text_rest(text: str, config: AzureConfig) -> dict:
    """Analyze text for health entities using REST API"""
    url = f"{config.language_endpoint}/language/analyze-text/jobs?api-version=2023-04-01"
    
    # Use managed identity token instead of API key
    try:
        token = get_language_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    except Exception as e:
        logger.error(f"Failed to authenticate for Language API: {e}")
        return {"entities": [], "error": f"Authentication failed: {str(e)}"}
    
    payload = {
        "displayName": "Health Analysis",
        "analysisInput": {
            "documents": [{"id": "1", "language": "en", "text": text[:5000]}]  # Limit text
        },
        "tasks": [
            {"kind": "Healthcare", "parameters": {"modelVersion": "latest"}}
        ]
    }
    
    # Start the job
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    
    if response.status_code != 202:
        logger.error(f"Health API error: {response.status_code} - {response.text}")
        return {"entities": [], "error": f"API error: {response.status_code}"}
    
    # Get operation location
    operation_location = response.headers.get("Operation-Location")
    if not operation_location:
        return {"entities": [], "error": "No operation location"}
    
    # Poll for results
    for _ in range(30):  # Max 30 attempts
        time.sleep(2)
        result_response = requests.get(operation_location, headers={"Authorization": f"Bearer {token}"})
        
        if result_response.status_code == 200:
            result = result_response.json()
            status = result.get("status", "")
            
            if status == "succeeded":
                entities = []
                relations = []
                try:
                    tasks = result.get("tasks", {}).get("items", [])
                    for task in tasks:
                        docs = task.get("results", {}).get("documents", [])
                        for doc in docs:
                            # Build entity lookup by index
                            doc_entities = doc.get("entities", [])
                            entity_by_index = {}
                            for idx, entity in enumerate(doc_entities):
                                entities.append({
                                    "text": entity.get("text"),
                                    "category": entity.get("category"),
                                    "confidence_score": entity.get("confidenceScore", 0)
                                })
                                # Store by index for relation lookup (API uses #/documents/0/entities/N format)
                                entity_by_index[idx] = entity
                            
                            # Process relations with proper entity text lookup
                            for relation in doc.get("relations", []):
                                relation_entities = []
                                for rel_entity in relation.get("entities", []):
                                    # Get the referenced entity - ref format is like "#/documents/0/entities/5"
                                    ref = rel_entity.get("ref", "")
                                    entity_data = {}
                                    if "/entities/" in ref:
                                        try:
                                            entity_idx = int(ref.split("/entities/")[-1])
                                            entity_data = entity_by_index.get(entity_idx, {})
                                        except (ValueError, IndexError):
                                            pass
                                    relation_entities.append({
                                        "text": entity_data.get("text", "Unknown"),
                                        "role": rel_entity.get("role", ""),
                                        "category": entity_data.get("category", ""),
                                        "confidenceScore": entity_data.get("confidenceScore", 0),
                                        "offset": entity_data.get("offset", 0),
                                        "length": entity_data.get("length", 0)
                                    })
                                relations.append({
                                    "relationType": relation.get("relationType"),
                                    "confidenceScore": relation.get("confidenceScore", 0),
                                    "entities": relation_entities
                                })
                except Exception as e:
                    logger.error(f"Error parsing health results: {e}")
                
                return {"entities": entities, "relations": relations}
            elif status == "failed":
                return {"entities": [], "error": "Analysis failed"}
    
    return {"entities": [], "error": "Timeout waiting for results"}


# ============================================================================
# HTTP Functions
# ============================================================================

@app.route(route="health", methods=["GET"])
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint"""
    return func.HttpResponse(
        json.dumps({"status": "healthy", "service": "transcription-api", "timestamp": datetime.utcnow().isoformat()}),
        status_code=200,
        mimetype="application/json"
    )


@app.route(route="upload", methods=["POST"])
def upload_audio(req: func.HttpRequest) -> func.HttpResponse:
    """Upload an audio file for transcription"""
    try:
        logger.info("Received upload request")
        config = AzureConfig.from_environment()
        
        if not config.validate():
            return func.HttpResponse(json.dumps({"error": "Server configuration error"}), status_code=500, mimetype="application/json")
        
        file = req.files.get('file')
        if not file:
            return func.HttpResponse(json.dumps({"error": "No file provided"}), status_code=400, mimetype="application/json")
        
        filename = file.filename
        if not is_supported_format(filename):
            return func.HttpResponse(json.dumps({"error": f"Unsupported format. Supported: {SUPPORTED_FORMATS}"}), status_code=400, mimetype="application/json")
        
        content = file.read()
        job_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat() + "Z"
        
        # Upload to blob
        blob_name = f"{job_id}/{filename}"
        blob_client = get_blob_client(config, blob_name)
        blob_client.upload_blob(content, overwrite=True)
        
        # Create job
        job = TranscriptionJob(id=job_id, filename=filename, status=JobStatus.PENDING, created_at=now, updated_at=now, blob_url=blob_client.url)
        
        # Save to Cosmos
        container = get_cosmos_client(config)
        container.create_item(body=job.to_dict())
        
        logger.info(f"Created job: {job_id}")
        return func.HttpResponse(
            json.dumps({"job_id": job_id, "filename": filename, "status": JobStatus.PENDING,
                       "links": {"status": f"/api/status/{job_id}", "process": f"/api/process/{job_id}", "results": f"/api/results/{job_id}"}}),
            status_code=201,
            mimetype="application/json"
        )
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")


@app.route(route="process/{job_id}", methods=["POST"])
def process_transcription(req: func.HttpRequest) -> func.HttpResponse:
    """Process a transcription job using REST APIs"""
    job_id = req.route_params.get('job_id')
    if not job_id:
        return func.HttpResponse(json.dumps({"error": "Job ID required"}), status_code=400, mimetype="application/json")
    
    try:
        config = AzureConfig.from_environment()
        container = get_cosmos_client(config)
        start_time = time.time()
        
        # Get job
        try:
            job_data = container.read_item(item=job_id, partition_key=job_id)
            job = TranscriptionJob.from_dict(job_data)
        except Exception:
            return func.HttpResponse(json.dumps({"error": f"Job not found: {job_id}"}), status_code=404, mimetype="application/json")
        
        # Update status
        job.status = JobStatus.TRANSCRIBING
        job.updated_at = datetime.utcnow().isoformat() + "Z"
        container.upsert_item(body=job.to_dict())
        
        # Download audio
        blob_name = f"{job_id}/{job.filename}"
        blob_client = get_blob_client(config, blob_name)
        audio_bytes = blob_client.download_blob().readall()
        
        # Transcribe using REST API
        transcription_text = transcribe_audio_rest(audio_bytes, config)
        
        job.transcription_text = transcription_text
        job.status = JobStatus.ANALYZING
        job.updated_at = datetime.utcnow().isoformat() + "Z"
        container.upsert_item(body=job.to_dict())
        
        # Analyze health entities using REST API
        health_results = analyze_health_text_rest(transcription_text, config)
        
        # Group entities by category
        entities_by_category = {}
        for e in health_results.get("entities", []):
            cat = e.get("category", "Unknown")
            if cat not in entities_by_category:
                entities_by_category[cat] = []
            entities_by_category[cat].append(e)
        
        # Calculate summary
        total_entities = len(health_results.get("entities", []))
        total_relations = len(health_results.get("relations", []))
        
        job.medical_entities = {
            "entities": health_results.get("entities", []),
            "entities_by_category": entities_by_category,
            "relations": health_results.get("relations", []),
            "summary": {
                "total_entities": total_entities,
                "total_relations": total_relations,
                "categories": list(entities_by_category.keys())
            }
        }
        job.status = JobStatus.COMPLETED
        job.processing_time_seconds = time.time() - start_time
        job.updated_at = datetime.utcnow().isoformat() + "Z"
        container.upsert_item(body=job.to_dict())
        
        logger.info(f"Job {job_id} completed in {job.processing_time_seconds:.2f}s")
        return func.HttpResponse(
            json.dumps({"job_id": job_id, "status": JobStatus.COMPLETED, "processing_time": job.processing_time_seconds,
                       "transcription_preview": transcription_text[:500] if transcription_text else "",
                       "entities_found": len(health_results.get("entities", []))}),
            status_code=200, mimetype="application/json"
        )
        
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        try:
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            container.upsert_item(body=job.to_dict())
        except:
            pass
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")


@app.route(route="status/{job_id}", methods=["GET"])
def get_status(req: func.HttpRequest) -> func.HttpResponse:
    """Get job status"""
    job_id = req.route_params.get('job_id')
    if not job_id:
        return func.HttpResponse(json.dumps({"error": "Job ID required"}), status_code=400, mimetype="application/json")
    
    try:
        config = AzureConfig.from_environment()
        container = get_cosmos_client(config)
        job_data = container.read_item(item=job_id, partition_key=job_id)
        job = TranscriptionJob.from_dict(job_data)
        
        return func.HttpResponse(
            json.dumps({"job_id": job.id, "filename": job.filename, "status": job.status,
                       "created_at": job.created_at, "updated_at": job.updated_at,
                       "processing_time_seconds": job.processing_time_seconds, "error_message": job.error_message}),
            status_code=200, mimetype="application/json"
        )
    except Exception as e:
        return func.HttpResponse(json.dumps({"error": f"Job not found: {job_id}"}), status_code=404, mimetype="application/json")


@app.route(route="results/{job_id}", methods=["GET"])
def get_results(req: func.HttpRequest) -> func.HttpResponse:
    """Get full results"""
    job_id = req.route_params.get('job_id')
    if not job_id:
        return func.HttpResponse(json.dumps({"error": "Job ID required"}), status_code=400, mimetype="application/json")
    
    try:
        config = AzureConfig.from_environment()
        container = get_cosmos_client(config)
        job_data = container.read_item(item=job_id, partition_key=job_id)
        job = TranscriptionJob.from_dict(job_data)
        
        # Generate FHIR bundle from entities
        fhir_bundle = generate_fhir_bundle(job.medical_entities) if job.medical_entities else None
        
        result = {
            "job_id": job.id, "filename": job.filename, "status": job.status,
            "created_at": job.created_at, "updated_at": job.updated_at,
            "processing_time_seconds": job.processing_time_seconds,
            "transcription": {"text": job.transcription_text, "word_count": len(job.transcription_text.split()) if job.transcription_text else 0},
            "medical_analysis": job.medical_entities,
            "fhir_bundle": fhir_bundle,
            "error_message": job.error_message
        }
        return func.HttpResponse(json.dumps(result, indent=2), status_code=200, mimetype="application/json")
    except Exception as e:
        return func.HttpResponse(json.dumps({"error": f"Job not found: {job_id}"}), status_code=404, mimetype="application/json")


@app.route(route="jobs", methods=["GET"])
def list_jobs(req: func.HttpRequest) -> func.HttpResponse:
    """List recent jobs"""
    try:
        config = AzureConfig.from_environment()
        container = get_cosmos_client(config)
        
        limit = int(req.params.get('limit', 50))
        query = "SELECT * FROM c ORDER BY c.created_at DESC OFFSET 0 LIMIT @limit"
        items = list(container.query_items(query=query, parameters=[{"name": "@limit", "value": limit}], enable_cross_partition_query=True))
        
        jobs = [{"job_id": j["id"], "filename": j["filename"], "status": j["status"], "created_at": j["created_at"]} for j in items]
        return func.HttpResponse(json.dumps({"jobs": jobs, "total": len(jobs)}), status_code=200, mimetype="application/json")
    except Exception as e:
        logger.error(f"List jobs failed: {e}")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")
