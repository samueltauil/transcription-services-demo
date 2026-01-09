"""
Azure Blob Storage client for audio file management
"""
import logging
from typing import Optional, Tuple
from azure.storage.blob import BlobServiceClient, BlobClient, ContentSettings
from .config import AzureConfig

logger = logging.getLogger(__name__)


class BlobStorageClient:
    """Client for Azure Blob Storage operations"""
    
    # Supported audio formats for Azure Speech Services
    SUPPORTED_FORMATS = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".m4a": "audio/mp4",
        ".wma": "audio/x-ms-wma",
    }
    
    def __init__(self, config: AzureConfig):
        self.config = config
        self.blob_service_client = BlobServiceClient.from_connection_string(
            config.storage_connection_string
        )
        self.container_client = None
        self._initialize()
    
    def _initialize(self):
        """Initialize storage container"""
        try:
            self.container_client = self.blob_service_client.get_container_client(
                self.config.storage_container_name
            )
            # Create container if not exists
            if not self.container_client.exists():
                self.container_client.create_container()
                logger.info(f"Created storage container: {self.config.storage_container_name}")
            else:
                logger.info(f"Using existing storage container: {self.config.storage_container_name}")
        except Exception as e:
            logger.error(f"Failed to initialize storage container: {e}")
            raise
    
    def upload_audio(self, job_id: str, filename: str, content: bytes) -> str:
        """
        Upload audio file to blob storage
        
        Args:
            job_id: Unique job identifier
            filename: Original filename
            content: File content as bytes
            
        Returns:
            Blob URL
        """
        try:
            # Determine content type from extension
            ext = self._get_extension(filename)
            content_type = self.SUPPORTED_FORMATS.get(ext, "application/octet-stream")
            
            # Create blob name with job ID prefix for organization
            blob_name = f"{job_id}/{filename}"
            
            # Upload blob
            blob_client = self.container_client.get_blob_client(blob_name)
            blob_client.upload_blob(
                content,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type)
            )
            
            logger.info(f"Uploaded audio file: {blob_name}")
            return blob_client.url
            
        except Exception as e:
            logger.error(f"Failed to upload audio file {filename}: {e}")
            raise
    
    def get_audio_url(self, job_id: str, filename: str) -> Optional[str]:
        """Get the URL for an uploaded audio file"""
        blob_name = f"{job_id}/{filename}"
        blob_client = self.container_client.get_blob_client(blob_name)
        
        if blob_client.exists():
            return blob_client.url
        return None
    
    def download_audio(self, job_id: str, filename: str) -> Optional[bytes]:
        """Download audio file content"""
        try:
            blob_name = f"{job_id}/{filename}"
            blob_client = self.container_client.get_blob_client(blob_name)
            
            if blob_client.exists():
                return blob_client.download_blob().readall()
            return None
            
        except Exception as e:
            logger.error(f"Failed to download audio file: {e}")
            return None
    
    def delete_audio(self, job_id: str, filename: str) -> bool:
        """Delete audio file from storage"""
        try:
            blob_name = f"{job_id}/{filename}"
            blob_client = self.container_client.get_blob_client(blob_name)
            blob_client.delete_blob()
            logger.info(f"Deleted audio file: {blob_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete audio file: {e}")
            return False
    
    def is_supported_format(self, filename: str) -> bool:
        """Check if the file format is supported"""
        ext = self._get_extension(filename)
        return ext in self.SUPPORTED_FORMATS
    
    def _get_extension(self, filename: str) -> str:
        """Get lowercase file extension"""
        import os
        return os.path.splitext(filename)[1].lower()
