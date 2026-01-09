"""
Shared configuration and utilities for Azure Transcription Services Demo
"""
import os
import logging
from dataclasses import dataclass
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AzureConfig:
    """Configuration for Azure services"""
    # Speech Services
    speech_key: str
    speech_region: str
    
    # Language Services (Text Analytics for Health)
    language_key: str
    language_endpoint: str
    
    # Cosmos DB
    cosmos_connection_string: str
    cosmos_database_name: str
    cosmos_container_name: str
    
    # Blob Storage
    storage_connection_string: str
    storage_container_name: str
    
    @classmethod
    def from_environment(cls) -> "AzureConfig":
        """Load configuration from environment variables"""
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
        """Validate that all required configuration is present"""
        required_fields = [
            self.speech_key,
            self.speech_region,
            self.language_key,
            self.language_endpoint,
            self.cosmos_connection_string,
            self.storage_connection_string,
        ]
        return all(required_fields)


@dataclass
class TranscriptionJob:
    """Model for a transcription job"""
    id: str
    filename: str
    status: str  # pending, processing, transcribing, analyzing, completed, failed
    created_at: str
    updated_at: str
    blob_url: Optional[str] = None
    transcription_text: Optional[str] = None
    medical_entities: Optional[dict] = None
    fhir_bundle: Optional[dict] = None
    error_message: Optional[str] = None
    processing_time_seconds: Optional[float] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for Cosmos DB storage"""
        return {
            "id": self.id,
            "filename": self.filename,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "blob_url": self.blob_url,
            "transcription_text": self.transcription_text,
            "medical_entities": self.medical_entities,
            "fhir_bundle": self.fhir_bundle,
            "error_message": self.error_message,
            "processing_time_seconds": self.processing_time_seconds,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "TranscriptionJob":
        """Create from dictionary"""
        return cls(
            id=data.get("id", ""),
            filename=data.get("filename", ""),
            status=data.get("status", "pending"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            blob_url=data.get("blob_url"),
            transcription_text=data.get("transcription_text"),
            medical_entities=data.get("medical_entities"),
            fhir_bundle=data.get("fhir_bundle"),
            error_message=data.get("error_message"),
            processing_time_seconds=data.get("processing_time_seconds"),
        )


# Status constants
class JobStatus:
    PENDING = "pending"
    UPLOADING = "uploading"
    TRANSCRIBING = "transcribing"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"
