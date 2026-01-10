"""
Azure Functions entry point
Healthcare Transcription Services Demo
Single-file approach for reliable deployment
"""
import azure.functions as func
import logging
import json
import uuid
import os
import time
import tempfile
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Tuple

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
        )
    
    def validate(self) -> bool:
        return all([
            self.speech_key, self.speech_region, self.language_key,
            self.language_endpoint, self.cosmos_connection_string,
            self.storage_connection_string,
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
    fhir_bundle: Optional[dict] = None
    error_message: Optional[str] = None
    processing_time_seconds: Optional[float] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id, "filename": self.filename, "status": self.status,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "blob_url": self.blob_url, "transcription_text": self.transcription_text,
            "medical_entities": self.medical_entities, "fhir_bundle": self.fhir_bundle,
            "error_message": self.error_message, "processing_time_seconds": self.processing_time_seconds,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "TranscriptionJob":
        return cls(
            id=data.get("id", ""), filename=data.get("filename", ""),
            status=data.get("status", "pending"), created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""), blob_url=data.get("blob_url"),
            transcription_text=data.get("transcription_text"),
            medical_entities=data.get("medical_entities"), fhir_bundle=data.get("fhir_bundle"),
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
    """Get Blob Storage client"""
    from azure.storage.blob import BlobServiceClient
    service_client = BlobServiceClient.from_connection_string(config.storage_connection_string)
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
    """Process a transcription job"""
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
        
        # Transcribe
        import azure.cognitiveservices.speech as speechsdk
        speech_config = speechsdk.SpeechConfig(subscription=config.speech_key, region=config.speech_region)
        speech_config.speech_recognition_language = "en-US"
        
        ext = job.filename.split('.')[-1] if '.' in job.filename else 'wav'
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp_file:
            tmp_file.write(audio_bytes)
            tmp_path = tmp_file.name
        
        try:
            audio_config = speechsdk.AudioConfig(filename=tmp_path)
            recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
            
            all_results = []
            done = False
            
            def recognized_cb(evt):
                if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                    all_results.append(evt.result.text)
            
            def session_stopped_cb(evt):
                nonlocal done
                done = True
            
            recognizer.recognized.connect(recognized_cb)
            recognizer.session_stopped.connect(session_stopped_cb)
            recognizer.canceled.connect(session_stopped_cb)
            
            recognizer.start_continuous_recognition()
            while not done:
                time.sleep(0.5)
            recognizer.stop_continuous_recognition()
            
            transcription_text = " ".join(all_results)
        finally:
            os.remove(tmp_path)
        
        job.transcription_text = transcription_text
        job.status = JobStatus.ANALYZING
        job.updated_at = datetime.utcnow().isoformat() + "Z"
        container.upsert_item(body=job.to_dict())
        
        # Analyze with Text Analytics for Health
        from azure.ai.textanalytics import TextAnalyticsClient
        from azure.core.credentials import AzureKeyCredential
        
        text_client = TextAnalyticsClient(endpoint=config.language_endpoint, credential=AzureKeyCredential(config.language_key))
        
        # Split into chunks if needed (5120 char limit)
        chunks = [transcription_text[i:i+5000] for i in range(0, len(transcription_text), 5000)] if transcription_text else [""]
        
        all_entities = []
        for chunk in chunks:
            if chunk.strip():
                poller = text_client.begin_analyze_healthcare_entities([chunk])
                results = list(poller.result())
                for doc in results:
                    if not doc.is_error:
                        for entity in doc.entities:
                            all_entities.append({
                                "text": entity.text,
                                "category": entity.category,
                                "confidence_score": entity.confidence_score,
                                "offset": entity.offset,
                                "length": entity.length
                            })
        
        # Group by category
        entities_by_category = {}
        for e in all_entities:
            cat = e["category"]
            if cat not in entities_by_category:
                entities_by_category[cat] = []
            entities_by_category[cat].append(e)
        
        job.medical_entities = {"entities": all_entities, "entities_by_category": entities_by_category}
        job.status = JobStatus.COMPLETED
        job.processing_time_seconds = time.time() - start_time
        job.updated_at = datetime.utcnow().isoformat() + "Z"
        container.upsert_item(body=job.to_dict())
        
        logger.info(f"Job {job_id} completed in {job.processing_time_seconds:.2f}s")
        return func.HttpResponse(
            json.dumps({"job_id": job_id, "status": JobStatus.COMPLETED, "processing_time": job.processing_time_seconds,
                       "transcription_preview": transcription_text[:500] if transcription_text else "",
                       "entities_found": len(all_entities)}),
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
