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
    language_key: str
    language_endpoint: str
    cosmos_connection_string: str
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
            language_key=os.environ.get("AZURE_LANGUAGE_KEY", ""),
            language_endpoint=os.environ.get("AZURE_LANGUAGE_ENDPOINT", ""),
            cosmos_connection_string=os.environ.get("COSMOS_CONNECTION_STRING", ""),
            cosmos_database_name=os.environ.get("COSMOS_DATABASE_NAME", "transcription-db"),
            cosmos_container_name=os.environ.get("COSMOS_CONTAINER_NAME", "transcriptions"),
            storage_connection_string=os.environ.get("STORAGE_CONNECTION_STRING", ""),
            storage_container_name=os.environ.get("STORAGE_CONTAINER_NAME", "audio-files"),
            storage_account_name=os.environ.get("STORAGE_ACCOUNT_NAME", os.environ.get("AzureWebJobsStorage__accountName", "")),
        )
    
    def validate(self) -> bool:
        # Either connection string or account name (for managed identity)
        has_storage = bool(self.storage_connection_string) or bool(self.storage_account_name)
        return all([
            self.speech_key, self.speech_region, self.language_key,
            self.language_endpoint, self.cosmos_connection_string,
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
    """Get Cosmos DB client"""
    from azure.cosmos import CosmosClient, PartitionKey
    client = CosmosClient.from_connection_string(config.cosmos_connection_string)
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
# Speech REST API (no SDK needed)
# ============================================================================

def transcribe_audio_rest(audio_bytes: bytes, config: AzureConfig) -> str:
    """Transcribe audio using Speech REST API (for short audio < 60 seconds)"""
    url = f"https://{config.speech_region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1"
    
    headers = {
        "Ocp-Apim-Subscription-Key": config.speech_key,
        "Content-Type": "audio/wav",
        "Accept": "application/json"
    }
    
    params = {
        "language": "en-US",
        "format": "detailed"
    }
    
    response = requests.post(url, headers=headers, params=params, data=audio_bytes, timeout=60)
    
    if response.status_code == 200:
        result = response.json()
        if result.get("RecognitionStatus") == "Success":
            return result.get("DisplayText", "")
        else:
            return f"Recognition status: {result.get('RecognitionStatus', 'Unknown')}"
    else:
        logger.error(f"Speech API error: {response.status_code} - {response.text}")
        return f"Transcription failed: {response.status_code}"


# ============================================================================
# Text Analytics REST API
# ============================================================================

def analyze_health_text_rest(text: str, config: AzureConfig) -> dict:
    """Analyze text for health entities using REST API"""
    url = f"{config.language_endpoint}/language/analyze-text/jobs?api-version=2023-04-01"
    
    headers = {
        "Ocp-Apim-Subscription-Key": config.language_key,
        "Content-Type": "application/json"
    }
    
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
        result_response = requests.get(operation_location, headers={"Ocp-Apim-Subscription-Key": config.language_key})
        
        if result_response.status_code == 200:
            result = result_response.json()
            status = result.get("status", "")
            
            if status == "succeeded":
                entities = []
                try:
                    tasks = result.get("tasks", {}).get("items", [])
                    for task in tasks:
                        docs = task.get("results", {}).get("documents", [])
                        for doc in docs:
                            for entity in doc.get("entities", []):
                                entities.append({
                                    "text": entity.get("text"),
                                    "category": entity.get("category"),
                                    "confidence_score": entity.get("confidenceScore", 0)
                                })
                except Exception as e:
                    logger.error(f"Error parsing health results: {e}")
                
                return {"entities": entities}
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
        
        job.medical_entities = {
            "entities": health_results.get("entities", []),
            "entities_by_category": entities_by_category
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
        
        result = {
            "job_id": job.id, "filename": job.filename, "status": job.status,
            "created_at": job.created_at, "updated_at": job.updated_at,
            "processing_time_seconds": job.processing_time_seconds,
            "transcription": {"text": job.transcription_text, "word_count": len(job.transcription_text.split()) if job.transcription_text else 0},
            "medical_analysis": job.medical_entities,
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
