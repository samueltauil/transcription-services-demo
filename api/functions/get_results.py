"""
Get Results Function
Retrieve transcription and analysis results
"""
import azure.functions as func
import logging
import json

from api.shared import AzureConfig, CosmosDBClient

logger = logging.getLogger(__name__)

bp = func.Blueprint()


@bp.route(route="status/{job_id}", methods=["GET"])
async def get_status(req: func.HttpRequest) -> func.HttpResponse:
    """Get the status of a transcription job"""
    job_id = req.route_params.get('job_id')
    
    if not job_id:
        return func.HttpResponse(
            json.dumps({"error": "Job ID is required"}),
            status_code=400,
            mimetype="application/json"
        )
    
    try:
        config = AzureConfig.from_environment()
        cosmos_client = CosmosDBClient(config)
        
        job = cosmos_client.get_job(job_id)
        if not job:
            return func.HttpResponse(
                json.dumps({"error": f"Job not found: {job_id}"}),
                status_code=404,
                mimetype="application/json"
            )
        
        return func.HttpResponse(
            json.dumps({
                "job_id": job.id,
                "filename": job.filename,
                "status": job.status,
                "created_at": job.created_at,
                "updated_at": job.updated_at,
                "processing_time_seconds": job.processing_time_seconds,
                "error_message": job.error_message
            }),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        logger.error(f"Failed to get status for job {job_id}: {e}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )


@bp.route(route="results/{job_id}", methods=["GET"])
async def get_results(req: func.HttpRequest) -> func.HttpResponse:
    """Get full results of a completed transcription job"""
    job_id = req.route_params.get('job_id')
    
    if not job_id:
        return func.HttpResponse(
            json.dumps({"error": "Job ID is required"}),
            status_code=400,
            mimetype="application/json"
        )
    
    try:
        config = AzureConfig.from_environment()
        cosmos_client = CosmosDBClient(config)
        
        job = cosmos_client.get_job(job_id)
        if not job:
            return func.HttpResponse(
                json.dumps({"error": f"Job not found: {job_id}"}),
                status_code=404,
                mimetype="application/json"
            )
        
        # Check query parameters for filtering
        include_fhir = req.params.get('include_fhir', 'true').lower() == 'true'
        include_entities = req.params.get('include_entities', 'true').lower() == 'true'
        
        result = {
            "job_id": job.id,
            "filename": job.filename,
            "status": job.status,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "processing_time_seconds": job.processing_time_seconds,
            "transcription": {
                "text": job.transcription_text,
                "word_count": len(job.transcription_text.split()) if job.transcription_text else 0,
                "character_count": len(job.transcription_text) if job.transcription_text else 0
            }
        }
        
        if include_entities and job.medical_entities:
            result["medical_analysis"] = job.medical_entities
        
        if include_fhir and job.fhir_bundle:
            result["fhir_bundle"] = job.fhir_bundle
        
        if job.error_message:
            result["error_message"] = job.error_message
        
        return func.HttpResponse(
            json.dumps(result, indent=2),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        logger.error(f"Failed to get results for job {job_id}: {e}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )


@bp.route(route="jobs", methods=["GET"])
async def list_jobs(req: func.HttpRequest) -> func.HttpResponse:
    """List recent transcription jobs"""
    try:
        config = AzureConfig.from_environment()
        cosmos_client = CosmosDBClient(config)
        
        limit = int(req.params.get('limit', 50))
        jobs = cosmos_client.list_jobs(limit=limit)
        
        return func.HttpResponse(
            json.dumps({
                "jobs": [
                    {
                        "job_id": job.id,
                        "filename": job.filename,
                        "status": job.status,
                        "created_at": job.created_at,
                        "processing_time_seconds": job.processing_time_seconds
                    }
                    for job in jobs
                ],
                "count": len(jobs)
            }),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )


@bp.route(route="health", methods=["GET"])
async def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint"""
    return func.HttpResponse(
        json.dumps({
            "status": "healthy",
            "service": "Azure Healthcare Transcription Services",
            "version": "1.0.0"
        }),
        status_code=200,
        mimetype="application/json"
    )
