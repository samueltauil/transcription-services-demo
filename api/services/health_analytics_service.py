"""
Text Analytics for Health service
Extracts medical entities, relationships, and FHIR-structured data from transcribed text
"""
import logging
from typing import Optional, Dict, List, Any
from azure.ai.textanalytics import TextAnalyticsClient, HealthcareEntityRelation
from azure.core.credentials import AzureKeyCredential
from api.shared.config import AzureConfig

logger = logging.getLogger(__name__)


class HealthAnalyticsService:
    """Service for Text Analytics for Health operations"""
    
    def __init__(self, config: AzureConfig):
        self.config = config
        self.client = TextAnalyticsClient(
            endpoint=config.language_endpoint,
            credential=AzureKeyCredential(config.language_key)
        )
    
    def analyze_health_text(self, text: str) -> Dict[str, Any]:
        """
        Analyze text for medical entities and relationships
        
        Args:
            text: Transcribed text to analyze
            
        Returns:
            Dictionary containing entities, relationships, and FHIR bundle
        """
        try:
            logger.info(f"Analyzing health text ({len(text)} characters)")
            
            # Split text into chunks if needed (max 5120 characters per document)
            chunks = self._split_text(text, max_length=5000)
            
            all_entities = []
            all_relations = []
            
            # Process each chunk
            for i, chunk in enumerate(chunks):
                logger.debug(f"Processing chunk {i+1}/{len(chunks)}")
                
                # Start the health analysis
                poller = self.client.begin_analyze_healthcare_entities([chunk])
                result = poller.result()
                
                # Process results
                for doc in result:
                    if doc.is_error:
                        logger.error(f"Error in document analysis: {doc.error}")
                        continue
                    
                    # Extract entities
                    for entity in doc.entities:
                        entity_dict = self._entity_to_dict(entity)
                        all_entities.append(entity_dict)
                    
                    # Extract relationships
                    for relation in doc.entity_relations:
                        relation_dict = self._relation_to_dict(relation)
                        all_relations.append(relation_dict)
            
            # Group entities by category
            entities_by_category = self._group_entities_by_category(all_entities)
            
            # Generate FHIR bundle
            fhir_bundle = self._generate_fhir_bundle(all_entities, all_relations)
            
            result = {
                "entities": all_entities,
                "entities_by_category": entities_by_category,
                "relations": all_relations,
                "fhir_bundle": fhir_bundle,
                "summary": {
                    "total_entities": len(all_entities),
                    "total_relations": len(all_relations),
                    "categories_found": list(entities_by_category.keys()),
                    "text_length": len(text)
                }
            }
            
            logger.info(f"Health analysis complete: {len(all_entities)} entities, {len(all_relations)} relations")
            return result
            
        except Exception as e:
            logger.error(f"Health text analysis failed: {e}")
            return {
                "error": str(e),
                "entities": [],
                "relations": [],
                "fhir_bundle": None,
                "summary": {"error": str(e)}
            }
    
    def _entity_to_dict(self, entity) -> Dict[str, Any]:
        """Convert health entity to dictionary"""
        return {
            "text": entity.text,
            "category": entity.category,
            "subcategory": entity.subcategory,
            "confidence_score": entity.confidence_score,
            "offset": entity.offset,
            "length": entity.length,
            "normalized_text": getattr(entity, 'normalized_text', None),
            "data_sources": [
                {"name": ds.name, "entity_id": ds.entity_id}
                for ds in (entity.data_sources or [])
            ],
            "assertion": {
                "conditionality": getattr(entity.assertion, 'conditionality', None) if entity.assertion else None,
                "certainty": getattr(entity.assertion, 'certainty', None) if entity.assertion else None,
                "association": getattr(entity.assertion, 'association', None) if entity.assertion else None,
            } if entity.assertion else None
        }
    
    def _relation_to_dict(self, relation: HealthcareEntityRelation) -> Dict[str, Any]:
        """Convert health entity relation to dictionary"""
        return {
            "relation_type": relation.relation_type.value if hasattr(relation.relation_type, 'value') else str(relation.relation_type),
            "roles": [
                {
                    "name": role.name,
                    "entity_text": role.entity.text,
                    "entity_category": role.entity.category
                }
                for role in relation.roles
            ],
            "confidence_score": getattr(relation, 'confidence_score', None)
        }
    
    def _group_entities_by_category(self, entities: List[Dict]) -> Dict[str, List[Dict]]:
        """Group entities by their category"""
        grouped = {}
        for entity in entities:
            category = entity.get("category", "Unknown")
            if category not in grouped:
                grouped[category] = []
            grouped[category].append(entity)
        return grouped
    
    def _generate_fhir_bundle(self, entities: List[Dict], relations: List[Dict]) -> Dict[str, Any]:
        """
        Generate a FHIR-compatible bundle from extracted entities
        This is a simplified FHIR R4 bundle structure
        """
        fhir_resources = []
        
        # Map categories to FHIR resource types
        category_to_fhir = {
            "MedicationName": "Medication",
            "Diagnosis": "Condition",
            "SymptomOrSign": "Observation",
            "BodyStructure": "BodyStructure",
            "TreatmentName": "Procedure",
            "ExaminationName": "Procedure",
            "Dosage": "MedicationStatement",
            "MedicationForm": "Medication",
            "MedicationRoute": "MedicationStatement",
            "FamilyRelation": "FamilyMemberHistory",
            "Age": "Observation",
            "Gender": "Patient",
            "Time": "Observation",
            "Date": "Observation",
        }
        
        resource_id = 1
        for entity in entities:
            category = entity.get("category", "")
            fhir_type = category_to_fhir.get(category, "Observation")
            
            resource = {
                "resourceType": fhir_type,
                "id": f"resource-{resource_id}",
                "text": {
                    "status": "generated",
                    "div": f"<div>{entity.get('text', '')}</div>"
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
                    "url": "assertion",
                    "valueString": str(entity["assertion"])
                }]
            
            fhir_resources.append({
                "fullUrl": f"urn:uuid:resource-{resource_id}",
                "resource": resource
            })
            resource_id += 1
        
        # Create FHIR Bundle
        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "total": len(fhir_resources),
            "entry": fhir_resources
        }
        
        return bundle
    
    def _split_text(self, text: str, max_length: int = 5000) -> List[str]:
        """Split text into chunks that fit within API limits"""
        if len(text) <= max_length:
            return [text]
        
        chunks = []
        sentences = text.replace('\n', ' ').split('. ')
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 2 <= max_length:
                current_chunk += sentence + ". "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def get_entity_categories(self) -> List[str]:
        """Return list of supported entity categories"""
        return [
            "MedicationName",
            "Dosage", 
            "MedicationForm",
            "MedicationRoute",
            "Diagnosis",
            "SymptomOrSign",
            "BodyStructure",
            "TreatmentName",
            "ExaminationName",
            "FamilyRelation",
            "Age",
            "Gender",
            "AdministrativeEvent",
            "CareEnvironment",
            "HealthcareProfession",
            "Allergen",
            "GeneOrProtein",
            "Variant",
            "MutationType",
            "Expression",
            "Direction",
            "RelationalOperator",
            "Time",
            "Date",
            "Course",
            "ConditionQualifier",
            "MeasurementUnit",
            "MeasurementValue"
        ]
