"""
Upload Audio Function
Handles audio file uploads and initiates transcription processing
"""
import azure.functions as func
import logging
import json
import uuid
from datetime import datetime

from api.shared import AzureConfig, TranscriptionJob, JobStatus, CosmosDBClient, BlobStorageClient

logger = logging.getLogger(__name__)

bp = func.Blueprint()


@bp.route(route="upload", methods=["POST"])
async def upload_audio(req: func.HttpRequest) -> func.HttpResponse:
    """
    Upload an audio file for transcription and health analysis
    
    Accepts multipart/form-data with 'file' field
    Returns job ID for tracking progress
    """
    try:
        logger.info("Received upload request")
        
        # Initialize configuration
        config = AzureConfig.from_environment()
        if not config.validate():
            return func.HttpResponse(
                json.dumps({"error": "Server configuration error"}),
                status_code=500,
                mimetype="application/json"
            )
        
        # Get uploaded file
        file = req.files.get('file')
        if not file:
            return func.HttpResponse(
                json.dumps({"error": "No file provided. Use 'file' field in multipart/form-data"}),
                status_code=400,
                mimetype="application/json"
            )
        
        filename = file.filename
        content = file.read()
        
        logger.info(f"Processing file: {filename}, size: {len(content)} bytes")
        
        # Validate file format
        storage_client = BlobStorageClient(config)
        if not storage_client.is_supported_format(filename):
            return func.HttpResponse(
                json.dumps({
                    "error": f"Unsupported file format. Supported formats: {list(storage_client.SUPPORTED_FORMATS.keys())}"
                }),
                status_code=400,
                mimetype="application/json"
            )
        
        # Generate job ID
        job_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat() + "Z"
        
        # Upload to blob storage
        blob_url = storage_client.upload_audio(job_id, filename, content)
        
        # Create job record
        job = TranscriptionJob(
            id=job_id,
            filename=filename,
            status=JobStatus.PENDING,
            created_at=now,
            updated_at=now,
            blob_url=blob_url
        )
        
        # Save to Cosmos DB
        cosmos_client = CosmosDBClient(config)
        cosmos_client.create_job(job)
        
        logger.info(f"Created transcription job: {job_id}")
        
        return func.HttpResponse(
            json.dumps({
                "job_id": job_id,
                "filename": filename,
                "status": JobStatus.PENDING,
                "message": "File uploaded successfully. Use /api/process/{job_id} to start processing.",
                "links": {
                    "status": f"/api/status/{job_id}",
                    "process": f"/api/process/{job_id}",
                    "results": f"/api/results/{job_id}"
                }
            }),
            status_code=201,
            mimetype="application/json"
        )
        
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
