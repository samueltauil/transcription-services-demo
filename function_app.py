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
    """Generate a comprehensive FHIR R4 bundle from extracted medical entities"""
    if not medical_entities:
        return {"resourceType": "Bundle", "type": "collection", "total": 0, "entry": []}
    
    entities = medical_entities.get("entities", [])
    relations = medical_entities.get("relations", [])
    summary = medical_entities.get("summary", {})
    diarization = medical_entities.get("diarization", {})
    fhir_resources = []
    
    # Map all Text Analytics for Health categories to FHIR resource types
    category_to_fhir = {
        "BodyStructure": "BodyStructure",
        "Age": "Observation", "Ethnicity": "Observation", "Gender": "Patient",
        "ExaminationName": "DiagnosticReport",
        "Allergen": "AllergyIntolerance",
        "Course": "Observation", "Date": "Observation", "Direction": "Observation",
        "Frequency": "Observation", "Time": "Observation", "MeasurementUnit": "Observation",
        "MeasurementValue": "Observation", "RelationalOperator": "Observation",
        "Variant": "Observation", "GeneOrProtein": "Observation",
        "MutationType": "Observation", "Expression": "Observation",
        "AdministrativeEvent": "Encounter", "CareEnvironment": "Location",
        "HealthcareProfession": "Practitioner",
        "Diagnosis": "Condition", "SymptomOrSign": "Observation",
        "ConditionQualifier": "Observation", "ConditionScale": "Observation",
        "MedicationClass": "Medication", "MedicationName": "MedicationStatement",
        "Dosage": "MedicationStatement", "MedicationForm": "Medication",
        "MedicationRoute": "MedicationStatement",
        "FamilyRelation": "FamilyMemberHistory",
        "Employment": "Observation", "LivingStatus": "Observation",
        "SubstanceUse": "Observation", "SubstanceUseAmount": "Observation",
        "TreatmentName": "Procedure",
    }
    
    # Map certainty values to FHIR verification status
    # Reference: https://learn.microsoft.com/en-us/azure/ai-services/language-service/text-analytics-for-health/concepts/assertion-detection
    certainty_to_status = {
        "positive": "confirmed",
        "positive_possible": "provisional",
        "negative": "refuted",
        "negative_possible": "refuted",
        "neutral_possible": "unconfirmed"
    }
    
    for idx, entity in enumerate(entities, 1):
        category = entity.get("category", "")
        fhir_type = category_to_fhir.get(category, "Observation")
        assertion = entity.get("assertion", {})
        links = entity.get("links", [])
        
        # Build coding array from entity links
        coding = []
        for link in links:
            data_source = link.get("dataSource", "")
            code_id = link.get("id", "")
            # Map data sources to FHIR system URIs
            system_map = {
                "UMLS": "http://terminology.hl7.org/CodeSystem/umls",
                "SNOMEDCT_US": "http://snomed.info/sct",
                "ICD10CM": "http://hl7.org/fhir/sid/icd-10-cm",
                "ICD9CM": "http://hl7.org/fhir/sid/icd-9-cm",
                "RXNORM": "http://www.nlm.nih.gov/research/umls/rxnorm",
                "MSH": "http://id.nlm.nih.gov/mesh",
                "NCI": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
                "HPO": "http://purl.obolibrary.org/obo/hp.owl"
            }
            if data_source in system_map:
                coding.append({
                    "system": system_map[data_source],
                    "code": code_id,
                    "display": entity.get("text", "")
                })
        
        resource = {
            "resourceType": fhir_type,
            "id": f"entity-{idx}",
            "meta": {
                "profile": [f"http://hl7.org/fhir/StructureDefinition/{fhir_type}"],
                "source": "azure-text-analytics-for-health",
                "tag": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ObservationValue", "code": "SUBSETTED"}]
            },
            "text": {
                "status": "generated",
                "div": f"<div xmlns=\"http://www.w3.org/1999/xhtml\"><p><b>{category}</b>: {entity.get('text', '')}</p></div>"
            },
            "code": {
                "text": entity.get("text", ""),
                "coding": coding if coding else None
            },
            "extension": []
        }
        
        # Add confidence score extension
        resource["extension"].append({
            "url": "http://hl7.org/fhir/StructureDefinition/confidence",
            "valueDecimal": round(entity.get("confidence_score", 0), 4)
        })
        
        # Add category extension
        resource["extension"].append({
            "url": "http://hl7.org/fhir/StructureDefinition/text-analytics-category",
            "valueString": category
        })
        
        # Add text position extension
        resource["extension"].append({
            "url": "http://hl7.org/fhir/StructureDefinition/text-offset",
            "valueInteger": entity.get("offset", 0)
        })
        
        # Add assertion extensions with proper FHIR structure
        # Reference: https://learn.microsoft.com/en-us/azure/ai-services/language-service/text-analytics-for-health/concepts/assertion-detection
        if assertion:
            certainty = assertion.get("certainty")
            conditionality = assertion.get("conditionality")
            association = assertion.get("association")
            temporal = assertion.get("temporal")
            
            # CERTAINTY: positive (default), negative, positive_possible, negative_possible, neutral_possible
            if certainty:
                certainty_display = {
                    "positive": "Confirmed - concept exists",
                    "negative": "Negated - concept does not exist",
                    "positive_possible": "Likely Present - probably exists but uncertain",
                    "negative_possible": "Possibly Absent - unlikely but uncertain",
                    "neutral_possible": "Uncertain - may or may not exist"
                }
                resource["extension"].append({
                    "url": "http://hl7.org/fhir/StructureDefinition/condition-assertedCertainty",
                    "valueCodeableConcept": {
                        "coding": [{
                            "system": "http://terminology.hl7.org/CodeSystem/certainty-type",
                            "code": certainty,
                            "display": certainty_display.get(certainty, certainty)
                        }],
                        "text": certainty
                    }
                })
            
            # CONDITIONALITY: none (default), hypothetical, conditional
            if conditionality:
                conditionality_display = {
                    "hypothetical": "Hypothetical - may develop in future",
                    "conditional": "Conditional - exists only under certain conditions"
                }
                resource["extension"].append({
                    "url": "http://hl7.org/fhir/StructureDefinition/condition-conditionality",
                    "valueCodeableConcept": {
                        "coding": [{
                            "system": "http://terminology.hl7.org/CodeSystem/conditionality-type",
                            "code": conditionality,
                            "display": conditionality_display.get(conditionality, conditionality)
                        }],
                        "text": conditionality
                    }
                })
            
            # ASSOCIATION: subject (default), other
            if association:
                association_display = {
                    "subject": "Subject - associated with the patient",
                    "other": "Other - associated with family member or other person"
                }
                resource["extension"].append({
                    "url": "http://hl7.org/fhir/StructureDefinition/condition-association",
                    "valueCodeableConcept": {
                        "coding": [{
                            "system": "http://terminology.hl7.org/CodeSystem/association-type",
                            "code": association,
                            "display": association_display.get(association, association)
                        }],
                        "text": association
                    }
                })
            
            # TEMPORAL: current (default), past, future
            if temporal:
                temporal_display = {
                    "current": "Current - related to current encounter",
                    "past": "Past - prior to current encounter",
                    "future": "Future - planned or scheduled"
                }
                resource["extension"].append({
                    "url": "http://hl7.org/fhir/StructureDefinition/condition-temporal",
                    "valueCodeableConcept": {
                        "coding": [{
                            "system": "http://terminology.hl7.org/CodeSystem/temporal-type",
                            "code": temporal,
                            "display": temporal_display.get(temporal, temporal)
                        }],
                        "text": temporal
                    }
                })
            
            # Set verification status for Condition resources
            if fhir_type == "Condition" and certainty:
                resource["verificationStatus"] = {
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                        "code": certainty_to_status.get(certainty, "unconfirmed")
                    }]
                }
        
        # Remove empty extensions
        if not resource["extension"]:
            del resource["extension"]
        # Remove empty coding
        if resource["code"]["coding"] is None:
            del resource["code"]["coding"]
        
        fhir_resources.append({
            "fullUrl": f"urn:uuid:entity-{idx}",
            "resource": resource
        })
    
    # Add relations as Observation resources with references
    for rel_idx, relation in enumerate(relations, 1):
        rel_type = relation.get("relationType", "Unknown")
        source = relation.get("source", {})
        target = relation.get("target", {})
        
        relation_resource = {
            "resourceType": "Observation",
            "id": f"relation-{rel_idx}",
            "meta": {
                "profile": ["http://hl7.org/fhir/StructureDefinition/Observation"],
                "source": "azure-text-analytics-for-health"
            },
            "status": "final",
            "category": [{
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                    "code": "clinical-relationship",
                    "display": "Clinical Relationship"
                }]
            }],
            "code": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/relation-type",
                    "code": rel_type,
                    "display": rel_type.replace("Of", " of ").replace("For", " for ")
                }],
                "text": f"{rel_type}: {source.get('text', '')} → {target.get('text', '')}"
            },
            "component": [
                {
                    "code": {"text": "source"},
                    "valueString": source.get("text", "")
                },
                {
                    "code": {"text": "target"},
                    "valueString": target.get("text", "")
                }
            ],
            "extension": [{
                "url": "http://hl7.org/fhir/StructureDefinition/confidence",
                "valueDecimal": round(relation.get("confidence_score", 0), 4)
            }]
        }
        
        fhir_resources.append({
            "fullUrl": f"urn:uuid:relation-{rel_idx}",
            "resource": relation_resource
        })
    
    # Add summary as DocumentReference
    if summary:
        summary_resource = {
            "resourceType": "DocumentReference",
            "id": "analysis-summary",
            "meta": {"source": "azure-text-analytics-for-health"},
            "status": "current",
            "type": {"text": "Healthcare Transcription Analysis Summary"},
            "description": "Summary of medical entity extraction from transcribed audio",
            "content": [{
                "attachment": {
                    "contentType": "application/json",
                    "data": None
                }
            }],
            "extension": [
                {"url": "total-entities", "valueInteger": summary.get("total_entities", 0)},
                {"url": "total-relations", "valueInteger": summary.get("total_relations", 0)},
                {"url": "speaker-count", "valueInteger": summary.get("speaker_count", 0)},
                {"url": "linked-entities", "valueInteger": summary.get("linked_entities", 0)},
                {"url": "categories", "valueString": ", ".join(summary.get("categories", []))}
            ]
        }
        if summary.get("assertions"):
            for key, val in summary["assertions"].items():
                summary_resource["extension"].append({
                    "url": f"assertion-{key}",
                    "valueInteger": val
                })
        fhir_resources.append({
            "fullUrl": "urn:uuid:analysis-summary",
            "resource": summary_resource
        })
    
    return {
        "resourceType": "Bundle",
        "id": f"transcription-analysis-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "meta": {
            "lastUpdated": datetime.utcnow().isoformat() + "Z",
            "source": "azure-healthcare-transcription-service"
        },
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

def transcribe_audio_rest(audio_bytes: bytes, config: AzureConfig, enable_diarization: bool = True) -> dict:
    """Transcribe audio using Speech Fast Transcription API with optional diarization"""
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
        return {"text": f"Authentication failed: {str(e)}", "phrases": [], "speakers": []}
    
    # Build definition with optional diarization
    definition = {
        "locales": ["en-US"],
        "profanityFilterMode": "Masked"
    }
    
    # Enable diarization for speaker identification
    if enable_diarization:
        definition["diarization"] = {
            "maxSpeakers": 10,
            "enabled": True
        }
    
    # Fast Transcription API uses multipart/form-data
    import io
    files = {
        'audio': ('audio.wav', io.BytesIO(audio_bytes), 'audio/wav')
    }
    data = {
        'definition': json.dumps(definition)
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    
    response = requests.post(url, headers=headers, files=files, data=data, timeout=180)
    
    if response.status_code == 200:
        result = response.json()
        
        # Extract combined text
        combined_text = ""
        combined = result.get("combinedPhrases", [])
        if combined:
            combined_text = combined[0].get("text", "")
        else:
            # Fallback to phrases
            phrases = result.get("phrases", [])
            if phrases:
                combined_text = " ".join([p.get("text", "") for p in phrases])
        
        # Extract diarized phrases with speaker information
        diarized_phrases = []
        speakers_found = set()
        for phrase in result.get("phrases", []):
            speaker = phrase.get("speaker", 0)
            speakers_found.add(speaker)
            diarized_phrases.append({
                "text": phrase.get("text", ""),
                "speaker": speaker,
                "offset": phrase.get("offset", ""),
                "duration": phrase.get("duration", ""),
                "confidence": phrase.get("confidence", 0)
            })
        
        return {
            "text": combined_text or "No transcription result",
            "phrases": diarized_phrases,
            "speakers": list(speakers_found),
            "speaker_count": len(speakers_found)
        }
    else:
        logger.error(f"Speech API error: {response.status_code} - {response.text}")
        return {"text": f"Transcription failed: {response.status_code}", "phrases": [], "speakers": []}


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
                                # Extract assertion information (negation, conditionality, etc.)
                                assertion_data = entity.get("assertion", {})
                                assertion = None
                                if assertion_data:
                                    assertion = {
                                        "certainty": assertion_data.get("certainty"),  # positive, negativePossible, negative, neutral
                                        "conditionality": assertion_data.get("conditionality"),  # hypothetical, conditional
                                        "association": assertion_data.get("association")  # subject, other
                                    }
                                
                                # Extract entity links to medical ontologies (UMLS, SNOMED, ICD-10, etc.)
                                links = []
                                for link in entity.get("links", []):
                                    links.append({
                                        "dataSource": link.get("dataSource"),  # UMLS, SNOMED CT, ICD-10-CM, etc.
                                        "id": link.get("id")  # Code like C0027361 for UMLS
                                    })
                                
                                entities.append({
                                    "text": entity.get("text"),
                                    "category": entity.get("category"),
                                    "subcategory": entity.get("subcategory"),
                                    "confidence_score": entity.get("confidenceScore", 0),
                                    "offset": entity.get("offset", 0),
                                    "length": entity.get("length", 0),
                                    "assertion": assertion,
                                    "links": links if links else None
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
        
        # Transcribe using REST API with diarization
        transcription_result = transcribe_audio_rest(audio_bytes, config, enable_diarization=True)
        transcription_text = transcription_result.get("text", "")
        diarized_phrases = transcription_result.get("phrases", [])
        speaker_count = transcription_result.get("speaker_count", 0)
        
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
        
        # Count assertions and linked entities
        assertion_counts = {"negated": 0, "conditional": 0, "hypothetical": 0, "affirmed": 0}
        linked_entities_count = 0
        for entity in health_results.get("entities", []):
            if entity.get("links"):
                linked_entities_count += 1
            assertion = entity.get("assertion")
            if assertion:
                certainty = assertion.get("certainty", "")
                if certainty in ("negative", "negativePossible"):
                    assertion_counts["negated"] += 1
                elif certainty == "positive":
                    assertion_counts["affirmed"] += 1
                conditionality = assertion.get("conditionality", "")
                if conditionality == "hypothetical":
                    assertion_counts["hypothetical"] += 1
                elif conditionality == "conditional":
                    assertion_counts["conditional"] += 1
        
        # Calculate summary
        total_entities = len(health_results.get("entities", []))
        total_relations = len(health_results.get("relations", []))
        
        job.medical_entities = {
            "entities": health_results.get("entities", []),
            "entities_by_category": entities_by_category,
            "relations": health_results.get("relations", []),
            "diarization": {
                "phrases": diarized_phrases,
                "speaker_count": speaker_count
            },
            "summary": {
                "total_entities": total_entities,
                "total_relations": total_relations,
                "categories": list(entities_by_category.keys()),
                "speaker_count": speaker_count,
                "linked_entities": linked_entities_count,
                "assertions": assertion_counts
            }
        }
        job.status = JobStatus.COMPLETED
        job.processing_time_seconds = time.time() - start_time
        job.updated_at = datetime.utcnow().isoformat() + "Z"
        container.upsert_item(body=job.to_dict())
        
        logger.info(f"Job {job_id} completed in {job.processing_time_seconds:.2f}s with {speaker_count} speakers")
        return func.HttpResponse(
            json.dumps({"job_id": job_id, "status": JobStatus.COMPLETED, "processing_time": job.processing_time_seconds,
                       "transcription_preview": transcription_text[:500] if transcription_text else "",
                       "entities_found": total_entities, "speakers_detected": speaker_count}),
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
