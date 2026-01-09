"""
Cosmos DB client for storing transcription jobs and results
"""
import logging
from typing import Optional, List
from azure.cosmos import CosmosClient, PartitionKey, exceptions
from .config import AzureConfig, TranscriptionJob

logger = logging.getLogger(__name__)


class CosmosDBClient:
    """Client for Cosmos DB operations"""
    
    def __init__(self, config: AzureConfig):
        self.config = config
        self.client = CosmosClient.from_connection_string(config.cosmos_connection_string)
        self.database = None
        self.container = None
        self._initialize()
    
    def _initialize(self):
        """Initialize database and container"""
        try:
            # Create database if not exists
            self.database = self.client.create_database_if_not_exists(
                id=self.config.cosmos_database_name
            )
            
            # Create container if not exists with partition key on id
            self.container = self.database.create_container_if_not_exists(
                id=self.config.cosmos_container_name,
                partition_key=PartitionKey(path="/id"),
                offer_throughput=400  # Minimum RU/s for cost efficiency
            )
            logger.info(f"Initialized Cosmos DB: {self.config.cosmos_database_name}/{self.config.cosmos_container_name}")
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Failed to initialize Cosmos DB: {e}")
            raise
    
    def create_job(self, job: TranscriptionJob) -> TranscriptionJob:
        """Create a new transcription job"""
        try:
            self.container.create_item(body=job.to_dict())
            logger.info(f"Created job: {job.id}")
            return job
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Failed to create job {job.id}: {e}")
            raise
    
    def update_job(self, job: TranscriptionJob) -> TranscriptionJob:
        """Update an existing transcription job"""
        try:
            self.container.upsert_item(body=job.to_dict())
            logger.info(f"Updated job: {job.id}")
            return job
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Failed to update job {job.id}: {e}")
            raise
    
    def get_job(self, job_id: str) -> Optional[TranscriptionJob]:
        """Get a transcription job by ID"""
        try:
            item = self.container.read_item(item=job_id, partition_key=job_id)
            return TranscriptionJob.from_dict(item)
        except exceptions.CosmosResourceNotFoundError:
            logger.warning(f"Job not found: {job_id}")
            return None
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Failed to get job {job_id}: {e}")
            raise
    
    def list_jobs(self, limit: int = 50) -> List[TranscriptionJob]:
        """List recent transcription jobs"""
        try:
            query = "SELECT * FROM c ORDER BY c.created_at DESC OFFSET 0 LIMIT @limit"
            items = self.container.query_items(
                query=query,
                parameters=[{"name": "@limit", "value": limit}],
                enable_cross_partition_query=True
            )
            return [TranscriptionJob.from_dict(item) for item in items]
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Failed to list jobs: {e}")
            raise
    
    def delete_job(self, job_id: str) -> bool:
        """Delete a transcription job"""
        try:
            self.container.delete_item(item=job_id, partition_key=job_id)
            logger.info(f"Deleted job: {job_id}")
            return True
        except exceptions.CosmosResourceNotFoundError:
            logger.warning(f"Job not found for deletion: {job_id}")
            return False
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Failed to delete job {job_id}: {e}")
            raise
