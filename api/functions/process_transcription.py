"""
Process Transcription Function
Orchestrates the transcription and health analysis pipeline
"""
import azure.functions as func
import logging
import json
import time
from datetime import datetime

from api.shared import AzureConfig, JobStatus, CosmosDBClient, BlobStorageClient
from api.services import TranscriptionService, HealthAnalyticsService

logger = logging.getLogger(__name__)

bp = func.Blueprint()


@bp.route(route="process/{job_id}", methods=["POST"])
async def process_transcription(req: func.HttpRequest) -> func.HttpResponse:
    """
    Process a transcription job
    
    1. Download audio from blob storage
    2. Transcribe using Azure Speech Services
    3. Analyze with Text Analytics for Health
    4. Store results in Cosmos DB
    """
    job_id = req.route_params.get('job_id')
    
    if not job_id:
        return func.HttpResponse(
            json.dumps({"error": "Job ID is required"}),
            status_code=400,
            mimetype="application/json"
        )
    
    try:
        logger.info(f"Processing job: {job_id}")
        start_time = time.time()
        
        # Initialize services
        config = AzureConfig.from_environment()
        cosmos_client = CosmosDBClient(config)
        storage_client = BlobStorageClient(config)
        transcription_service = TranscriptionService(config)
        health_service = HealthAnalyticsService(config)
        
        # Get job from database
        job = cosmos_client.get_job(job_id)
        if not job:
            return func.HttpResponse(
                json.dumps({"error": f"Job not found: {job_id}"}),
                status_code=404,
                mimetype="application/json"
            )
        
        # Update status to processing
        job.status = JobStatus.TRANSCRIBING
        job.updated_at = datetime.utcnow().isoformat() + "Z"
        cosmos_client.update_job(job)
        
        # Download audio file
        logger.info(f"Downloading audio for job: {job_id}")
        audio_bytes = storage_client.download_audio(job_id, job.filename)
        if not audio_bytes:
            job.status = JobStatus.FAILED
            job.error_message = "Failed to download audio file"
            cosmos_client.update_job(job)
            return func.HttpResponse(
                json.dumps({"error": "Failed to download audio file"}),
                status_code=500,
                mimetype="application/json"
            )
        
        # Transcribe audio
        logger.info(f"Transcribing audio for job: {job_id}")
        ext = job.filename.split('.')[-1] if '.' in job.filename else 'wav'
        success, transcription_text, metadata = transcription_service.transcribe_audio_bytes(
            audio_bytes, 
            audio_format=ext
        )
        
        if not success:
            job.status = JobStatus.FAILED
            job.error_message = f"Transcription failed: {transcription_text}"
            cosmos_client.update_job(job)
            return func.HttpResponse(
                json.dumps({"error": f"Transcription failed: {transcription_text}"}),
                status_code=500,
                mimetype="application/json"
            )
        
        job.transcription_text = transcription_text
        job.status = JobStatus.ANALYZING
        job.updated_at = datetime.utcnow().isoformat() + "Z"
        cosmos_client.update_job(job)
        
        # Analyze with Text Analytics for Health
        logger.info(f"Analyzing health entities for job: {job_id}")
        health_results = health_service.analyze_health_text(transcription_text)
        
        # Update job with results
        job.medical_entities = {
            "entities": health_results.get("entities", []),
            "entities_by_category": health_results.get("entities_by_category", {}),
            "relations": health_results.get("relations", []),
            "summary": health_results.get("summary", {})
        }
        job.fhir_bundle = health_results.get("fhir_bundle")
        job.status = JobStatus.COMPLETED
        job.processing_time_seconds = time.time() - start_time
        job.updated_at = datetime.utcnow().isoformat() + "Z"
        cosmos_client.update_job(job)
        
        logger.info(f"Job {job_id} completed in {job.processing_time_seconds:.2f}s")
        
        return func.HttpResponse(
            json.dumps({
                "job_id": job_id,
                "status": JobStatus.COMPLETED,
                "processing_time_seconds": job.processing_time_seconds,
                "summary": {
                    "transcription_length": len(transcription_text),
                    "word_count": len(transcription_text.split()) if transcription_text else 0,
                    "entities_found": len(health_results.get("entities", [])),
                    "relations_found": len(health_results.get("relations", [])),
                    "categories": list(health_results.get("entities_by_category", {}).keys())
                },
                "links": {
                    "results": f"/api/results/{job_id}",
                    "status": f"/api/status/{job_id}"
                }
            }),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        logger.error(f"Processing failed for job {job_id}: {e}")
        
        # Try to update job status to failed
        try:
            config = AzureConfig.from_environment()
            cosmos_client = CosmosDBClient(config)
            job = cosmos_client.get_job(job_id)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(e)
                job.updated_at = datetime.utcnow().isoformat() + "Z"
                cosmos_client.update_job(job)
        except:
            pass
        
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
