/**
 * Azure Healthcare Transcription Services - Frontend Application
 */

// API Configuration
// The API URL can be configured in multiple ways:
// 1. Set FUNCTION_APP_URL in staticwebapp.config.json for production
// 2. Uses /api for local development (Azure Functions Core Tools)
// 3. Falls back to window.API_BASE_URL if set globally
const API_BASE_URL = (() => {
    // Check for global override (can be set in staticwebapp.config.json)
    if (window.FUNCTION_APP_URL) {
        return window.FUNCTION_APP_URL;
    }
    // Local development
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        return '/api';
    }
    // Production - use linked backend or configured URL
    // Update this URL after deploying your Function App, or use staticwebapp.config.json
    return 'https://healthtranscript-func-si35ec.azurewebsites.net/api';
})();

// State
let currentJobId = null;
let selectedFile = null;
let pollInterval = null;
let audioDurationMinutes = 0;

// DOM Elements
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const selectedFileDiv = document.getElementById('selectedFile');
const fileName = document.getElementById('fileName');
const fileSize = document.getElementById('fileSize');
const removeFileBtn = document.getElementById('removeFile');
const uploadBtn = document.getElementById('uploadBtn');
const statusSection = document.getElementById('statusSection');
const statusMessage = document.getElementById('statusMessage');
const resultsSection = document.getElementById('resultsSection');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initializeUpload();
    initializeTabs();
});

/**
 * Initialize upload functionality
 */
function initializeUpload() {
    // Click to upload
    dropZone.addEventListener('click', () => fileInput.click());
    
    // File selection
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            selectFile(e.target.files[0]);
        }
    });
    
    // Drag and drop
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });
    
    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });
    
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            selectFile(e.dataTransfer.files[0]);
        }
    });
    
    // Remove file
    removeFileBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        clearFile();
    });
    
    // Upload button
    uploadBtn.addEventListener('click', uploadAndProcess);
}

/**
 * Select a file for upload
 */
function selectFile(file) {
    const supportedFormats = ['.wav', '.mp3', '.ogg', '.flac', '.m4a', '.wma'];
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    
    if (!supportedFormats.includes(ext)) {
        alert(`Unsupported format. Please use: ${supportedFormats.join(', ')}`);
        return;
    }
    
    selectedFile = file;
    fileName.textContent = file.name;
    fileSize.textContent = formatFileSize(file.size);
    selectedFileDiv.style.display = 'flex';
    uploadBtn.disabled = false;
    
    // Get audio duration
    getAudioDuration(file);
}

/**
 * Get audio file duration
 */
function getAudioDuration(file) {
    const audio = new Audio();
    const objectUrl = URL.createObjectURL(file);
    
    audio.addEventListener('loadedmetadata', () => {
        audioDurationMinutes = audio.duration / 60;
        URL.revokeObjectURL(objectUrl);
        
        // Update file info with duration
        const durationStr = formatDuration(audio.duration);
        fileSize.textContent = `${formatFileSize(file.size)} • ${durationStr}`;
    });
    
    audio.addEventListener('error', () => {
        // If we can't get duration, estimate from file size (rough estimate)
        // Assume ~1MB per minute for compressed audio
        audioDurationMinutes = file.size / (1024 * 1024);
        URL.revokeObjectURL(objectUrl);
    });
    
    audio.src = objectUrl;
}

/**
 * Format duration in seconds to mm:ss
 */
function formatDuration(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Clear selected file
 */
function clearFile() {
    selectedFile = null;
    audioDurationMinutes = 0;
    fileInput.value = '';
    selectedFileDiv.style.display = 'none';
    uploadBtn.disabled = true;
}

/**
 * Format file size
 */
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

/**
 * Upload and process file
 */
async function uploadAndProcess() {
    if (!selectedFile) return;
    
    // Update UI
    uploadBtn.disabled = true;
    uploadBtn.querySelector('.btn-text').style.display = 'none';
    uploadBtn.querySelector('.btn-loading').style.display = 'inline';
    statusSection.style.display = 'block';
    resultsSection.style.display = 'none';
    
    resetStatus();
    updateStatus('upload', 'active');
    statusMessage.textContent = 'Uploading audio file...';
    
    try {
        // Upload file
        const formData = new FormData();
        formData.append('file', selectedFile);
        
        const uploadResponse = await fetch(`${API_BASE_URL}/upload`, {
            method: 'POST',
            body: formData
        });
        
        if (!uploadResponse.ok) {
            throw new Error('Upload failed');
        }
        
        const uploadData = await uploadResponse.json();
        currentJobId = uploadData.job_id;
        
        updateStatus('upload', 'completed');
        updateStatus('transcribe', 'active');
        statusMessage.textContent = 'Starting transcription...';
        
        // Start processing
        const processResponse = await fetch(`${API_BASE_URL}/process/${currentJobId}`, {
            method: 'POST'
        });
        
        if (!processResponse.ok) {
            throw new Error('Processing failed');
        }
        
        // Poll for results
        startPolling();
        
    } catch (error) {
        console.error('Error:', error);
        statusMessage.textContent = `Error: ${error.message}`;
        updateCurrentStepToError();
        resetUploadButton();
    }
}

/**
 * Start polling for job status
 */
function startPolling() {
    pollInterval = setInterval(checkStatus, 2000);
}

/**
 * Stop polling
 */
function stopPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

/**
 * Check job status
 */
async function checkStatus() {
    if (!currentJobId) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/status/${currentJobId}`);
        const data = await response.json();
        
        switch (data.status) {
            case 'transcribing':
                updateStatus('transcribe', 'active');
                statusMessage.textContent = 'Transcribing audio...';
                break;
                
            case 'analyzing':
                updateStatus('transcribe', 'completed');
                updateStatus('analyze', 'active');
                statusMessage.textContent = 'Analyzing medical entities...';
                break;
                
            case 'completed':
                stopPolling();
                updateStatus('transcribe', 'completed');
                updateStatus('analyze', 'completed');
                updateStatus('complete', 'completed');
                statusMessage.textContent = 'Processing complete!';
                await loadResults();
                resetUploadButton();
                break;
                
            case 'failed':
                stopPolling();
                updateCurrentStepToError();
                statusMessage.textContent = `Error: ${data.error_message || 'Processing failed'}`;
                resetUploadButton();
                break;
        }
    } catch (error) {
        console.error('Status check error:', error);
    }
}

/**
 * Update status step
 */
function updateStatus(step, state) {
    const stepEl = document.querySelector(`.status-step[data-step="${step}"]`);
    if (stepEl) {
        stepEl.classList.remove('active', 'completed', 'error');
        stepEl.classList.add(state);
    }
}

/**
 * Reset all status steps
 */
function resetStatus() {
    document.querySelectorAll('.status-step').forEach(step => {
        step.classList.remove('active', 'completed', 'error');
    });
}

/**
 * Mark current active step as error
 */
function updateCurrentStepToError() {
    const activeStep = document.querySelector('.status-step.active');
    if (activeStep) {
        activeStep.classList.remove('active');
        activeStep.classList.add('error');
    }
}

/**
 * Reset upload button
 */
function resetUploadButton() {
    uploadBtn.disabled = false;
    uploadBtn.querySelector('.btn-text').style.display = 'inline';
    uploadBtn.querySelector('.btn-loading').style.display = 'none';
}

/**
 * Load and display results
 */
async function loadResults() {
    try {
        const response = await fetch(`${API_BASE_URL}/results/${currentJobId}`);
        const data = await response.json();
        
        resultsSection.style.display = 'block';
        
        // Calculate and display cost savings based on audio duration
        updateCostSavings();
        
        // Update summary cards
        document.getElementById('processingTime').textContent = 
            data.processing_time_seconds ? `${data.processing_time_seconds.toFixed(1)}s` : '-';
        document.getElementById('wordCount').textContent = 
            data.transcription?.word_count || '-';
        document.getElementById('entityCount').textContent = 
            data.medical_analysis?.summary?.total_entities || '-';
        document.getElementById('relationCount').textContent = 
            data.medical_analysis?.summary?.total_relations || '-';
        
        // Update speaker count if available
        const speakerCountEl = document.getElementById('speakerCount');
        if (speakerCountEl) {
            speakerCountEl.textContent = data.medical_analysis?.summary?.speaker_count || '-';
        }
        
        // Update assertion stats if available
        const assertionStats = data.medical_analysis?.summary?.assertions;
        if (assertionStats) {
            const negatedEl = document.getElementById('negatedCount');
            const linkedEl = document.getElementById('linkedCount');
            if (negatedEl) negatedEl.textContent = assertionStats.negated || '0';
            if (linkedEl) linkedEl.textContent = data.medical_analysis?.summary?.linked_entities || '0';
        }
        
        // Display transcription with optional diarization
        const diarization = data.medical_analysis?.diarization;
        if (diarization && diarization.phrases && diarization.phrases.length > 0 && diarization.speaker_count > 1) {
            displayDiarizedTranscription(diarization.phrases, data.transcription?.text);
        } else {
            document.getElementById('transcriptionText').innerHTML = 
                `<p>${data.transcription?.text || 'No transcription available'}</p>`;
        }
        
        // Display entities
        displayEntities(data.medical_analysis?.entities_by_category || {});
        
        // Display relations
        displayRelations(data.medical_analysis?.relations || []);
        
        // Display FHIR
        document.getElementById('fhirOutput').textContent = 
            JSON.stringify(data.fhir_bundle, null, 2);
        
        // Setup FHIR download - capture job ID in closure
        const jobId = currentJobId || `export-${Date.now()}`;
        document.getElementById('downloadFhir').onclick = () => {
            downloadJson(data.fhir_bundle, `fhir-bundle-${jobId}.json`);
        };
        
        // Setup FHIR toggle
        const fhirContainer = document.getElementById('fhirContainer');
        const toggleBtn = document.getElementById('toggleFhirView');
        const toggleText = document.getElementById('toggleFhirText');
        fhirContainer.classList.add('collapsed');
        toggleText.textContent = 'Show FHIR JSON';
        toggleBtn.onclick = () => {
            const isCollapsed = fhirContainer.classList.toggle('collapsed');
            toggleText.textContent = isCollapsed ? 'Show FHIR JSON' : 'Hide FHIR JSON';
        };
        
    } catch (error) {
        console.error('Failed to load results:', error);
    }
}

/**
 * Update cost savings banner based on audio duration
 */
function updateCostSavings() {
    const TRANSCRIBEME_RATE = 0.79; // per minute
    const AZURE_RATE = 0.003; // per minute (real-time STT)
    
    const minutes = audioDurationMinutes || 1;
    const transcribemeCost = minutes * TRANSCRIBEME_RATE;
    const azureCost = minutes * AZURE_RATE;
    const savings = transcribemeCost - azureCost;
    
    document.getElementById('transcribemeCostActual').textContent = `$${transcribemeCost.toFixed(2)}`;
    document.getElementById('azureCostActual').textContent = `$${azureCost.toFixed(3)}`;
    document.getElementById('actualSavings').textContent = `$${savings.toFixed(2)}`;
    document.getElementById('savingsDetails').textContent = `(${minutes.toFixed(1)} min audio)`;
}

/**
 * Display medical entities by category with assertions and entity links
 */
function displayEntities(entitiesByCategory) {
    const container = document.getElementById('entitiesContainer');
    container.innerHTML = '';
    
    const categories = Object.keys(entitiesByCategory);
    
    if (categories.length === 0) {
        container.innerHTML = '<p class="placeholder">No medical entities found</p>';
        return;
    }
    
    categories.forEach(category => {
        const entities = entitiesByCategory[category];
        const categoryDiv = document.createElement('div');
        categoryDiv.className = 'entity-category';
        
        const header = document.createElement('h3');
        header.textContent = formatCategoryName(category) + ` (${entities.length})`;
        categoryDiv.appendChild(header);
        
        const list = document.createElement('div');
        list.className = 'entity-list';
        
        entities.forEach(entity => {
            const tag = document.createElement('span');
            tag.className = 'entity-tag';
            
            // Build assertion badges
            let assertionHtml = '';
            if (entity.assertion) {
                const certainty = entity.assertion.certainty;
                const conditionality = entity.assertion.conditionality;
                
                if (certainty === 'negative' || certainty === 'negativePossible') {
                    assertionHtml += '<span class="assertion-badge negated">Negated</span>';
                } else if (certainty === 'positive') {
                    assertionHtml += '<span class="assertion-badge affirmed">Affirmed</span>';
                }
                
                if (conditionality === 'hypothetical') {
                    assertionHtml += '<span class="assertion-badge hypothetical">Hypothetical</span>';
                } else if (conditionality === 'conditional') {
                    assertionHtml += '<span class="assertion-badge conditional">Conditional</span>';
                }
                
                if (entity.assertion.association === 'other') {
                    assertionHtml += '<span class="assertion-badge other-subject">Other Subject</span>';
                }
            }
            
            // Build entity links to medical ontologies
            let linksHtml = '';
            if (entity.links && entity.links.length > 0) {
                const linkItems = entity.links.slice(0, 2).map(link => {
                    const url = getOntologyUrl(link.dataSource, link.id);
                    if (url) {
                        return `<a href="${url}" target="_blank" class="entity-link" title="${link.dataSource}: ${link.id}">${link.dataSource}</a>`;
                    }
                    return `<span class="entity-link-text" title="${link.id}">${link.dataSource}</span>`;
                });
                linksHtml = `<span class="entity-links">${linkItems.join(' ')}</span>`;
            }
            
            tag.innerHTML = `
                <span class="entity-text">${entity.text}</span>
                ${assertionHtml}
                <span class="confidence">${Math.round(entity.confidence_score * 100)}%</span>
                ${linksHtml}
            `;
            list.appendChild(tag);
        });
        
        categoryDiv.appendChild(list);
        container.appendChild(categoryDiv);
    });
}

/**
 * Get URL for medical ontology lookup
 */
function getOntologyUrl(dataSource, id) {
    const ontologyUrls = {
        'UMLS': `https://uts.nlm.nih.gov/uts/umls/concept/${id}`,
        'SNOMED CT': `https://browser.ihtsdotools.org/?perspective=full&conceptId1=${id}`,
        'ICD-10-CM': `https://icd.who.int/browse10/2019/en#/${id}`,
        'ICD-9-CM': `https://icd.who.int/browse10/2019/en#/${id}`,
        'RxNorm': `https://mor.nlm.nih.gov/RxNav/search?searchBy=RXCUI&searchTerm=${id}`,
        'MeSH': `https://meshb.nlm.nih.gov/record/ui?ui=${id}`,
        'CPT': null,  // No public URL
        'NDC': `https://ndclist.com/?s=${id}`,
        'NCI': `https://ncit.nci.nih.gov/ncitbrowser/ConceptReport.jsp?dictionary=NCI_Thesaurus&code=${id}`
    };
    return ontologyUrls[dataSource] || null;
}

/**
 * Display diarized transcription with speaker identification
 */
function displayDiarizedTranscription(phrases, fullText) {
    const container = document.getElementById('transcriptionText');
    container.innerHTML = '';
    
    // Speaker colors for visual distinction
    const speakerColors = [
        { bg: '#e3f2fd', border: '#1976d2', label: '#1976d2' },  // Blue - Doctor
        { bg: '#f3e5f5', border: '#7b1fa2', label: '#7b1fa2' },  // Purple - Patient
        { bg: '#e8f5e9', border: '#388e3c', label: '#388e3c' },  // Green
        { bg: '#fff3e0', border: '#f57c00', label: '#f57c00' },  // Orange
        { bg: '#fce4ec', border: '#c2185b', label: '#c2185b' },  // Pink
        { bg: '#e0f7fa', border: '#00838f', label: '#00838f' },  // Cyan
    ];
    
    // Speaker labels (common healthcare scenario)
    const speakerLabels = ['Speaker 1', 'Speaker 2', 'Speaker 3', 'Speaker 4', 'Speaker 5', 'Speaker 6'];
    
    // Add toggle for diarization view
    const toggleDiv = document.createElement('div');
    toggleDiv.className = 'diarization-toggle';
    toggleDiv.innerHTML = `
        <button class="toggle-btn active" data-view="diarized">Speaker View</button>
        <button class="toggle-btn" data-view="plain">Plain Text</button>
    `;
    container.appendChild(toggleDiv);
    
    // Create diarized view
    const diarizedView = document.createElement('div');
    diarizedView.className = 'diarized-view';
    diarizedView.id = 'diarizedView';
    
    let currentSpeaker = null;
    let currentGroup = null;
    
    phrases.forEach(phrase => {
        const speaker = phrase.speaker || 0;
        const colorIdx = speaker % speakerColors.length;
        const colors = speakerColors[colorIdx];
        
        // Group consecutive phrases by same speaker
        if (speaker !== currentSpeaker) {
            if (currentGroup) {
                diarizedView.appendChild(currentGroup);
            }
            
            currentGroup = document.createElement('div');
            currentGroup.className = 'speaker-group';
            currentGroup.style.borderLeftColor = colors.border;
            currentGroup.style.backgroundColor = colors.bg;
            
            const labelSpan = document.createElement('span');
            labelSpan.className = 'speaker-label';
            labelSpan.style.backgroundColor = colors.label;
            labelSpan.textContent = speakerLabels[speaker] || `Speaker ${speaker + 1}`;
            currentGroup.appendChild(labelSpan);
            
            const textDiv = document.createElement('div');
            textDiv.className = 'speaker-text';
            currentGroup.appendChild(textDiv);
            
            currentSpeaker = speaker;
        }
        
        const textSpan = document.createElement('span');
        textSpan.textContent = phrase.text + ' ';
        currentGroup.querySelector('.speaker-text').appendChild(textSpan);
    });
    
    if (currentGroup) {
        diarizedView.appendChild(currentGroup);
    }
    
    container.appendChild(diarizedView);
    
    // Create plain text view (hidden by default)
    const plainView = document.createElement('div');
    plainView.className = 'plain-view';
    plainView.id = 'plainView';
    plainView.style.display = 'none';
    plainView.innerHTML = `<p>${fullText}</p>`;
    container.appendChild(plainView);
    
    // Add toggle functionality
    toggleDiv.querySelectorAll('.toggle-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            toggleDiv.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            const view = btn.dataset.view;
            document.getElementById('diarizedView').style.display = view === 'diarized' ? 'block' : 'none';
            document.getElementById('plainView').style.display = view === 'plain' ? 'block' : 'none';
        });
    });
}

/**
 * Display relationships between medical entities with enhanced visualization
 */
function displayRelations(relations) {
    const container = document.getElementById('relationsContainer');
    container.innerHTML = '';
    
    if (!relations || relations.length === 0) {
        container.innerHTML = '<p class="placeholder">No relationships found between medical entities</p>';
        return;
    }
    
    // Group relations by type
    const groupedRelations = {};
    relations.forEach((relation, index) => {
        const type = relation.relationType || 'Unknown';
        if (!groupedRelations[type]) {
            groupedRelations[type] = [];
        }
        groupedRelations[type].push({ ...relation, originalIndex: index });
    });
    
    // Create relation type descriptions
    const relationDescriptions = {
        'DosageOfMedication': 'Links medication to its prescribed dosage',
        'RouteOfMedication': 'How medication is administered (oral, IV, etc.)',
        'FormOfMedication': 'Physical form of medication (tablet, liquid, etc.)',
        'FrequencyOfMedication': 'How often medication is taken',
        'TimeOfMedication': 'When medication is administered',
        'CourseOfMedication': 'Changes in medication over time',
        'BodySiteOfCondition': 'Where in the body a condition occurs',
        'TimeOfCondition': 'When a condition occurred or was observed',
        'QualifierOfCondition': 'Descriptive attributes of a condition',
        'FrequencyOfCondition': 'How often a condition occurs',
        'CourseOfCondition': 'How a condition progresses over time',
        'ScaleOfCondition': 'Severity or measurement scale of condition',
        'DirectionOfCondition': 'Directional location of condition',
        'DirectionOfBodyStructure': 'Directional location of body part',
        'DirectionOfExamination': 'Direction during examination',
        'DirectionOfTreatment': 'Direction of treatment application',
        'BodySiteOfTreatment': 'Where treatment is applied',
        'TimeOfTreatment': 'When treatment is administered',
        'FrequencyOfTreatment': 'How often treatment is given',
        'CourseOfTreatment': 'How treatment changes over time',
        'TimeOfExamination': 'When examination was performed',
        'RelationOfExamination': 'What examination relates to',
        'CourseOfExamination': 'Changes in examination results',
        'UnitOfCondition': 'Measurement unit for condition',
        'ValueOfCondition': 'Measured value for condition',
        'UnitOfExamination': 'Measurement unit for examination',
        'ValueOfExamination': 'Measured value from examination',
        'ExaminationFindsCondition': 'Examination that detected a condition',
        'Abbreviation': 'Abbreviation and its full form',
        'AmountOfSubstanceUse': 'Quantity of substance used',
        'FrequencyOfSubstanceUse': 'How often substance is used',
        'ExpressionOfGene': 'Gene expression level',
        'ExpressionOfVariant': 'Variant expression',
        'MutationTypeOfGene': 'Type of gene mutation',
        'MutationTypeOfVariant': 'Type of variant mutation',
        'VariantOfGene': 'Genetic variant of a gene'
    };
    
    // Render grouped relations
    Object.keys(groupedRelations).sort().forEach(relationType => {
        const typeRelations = groupedRelations[relationType];
        const formattedType = formatCategoryName(relationType);
        const description = relationDescriptions[relationType] || '';
        
        const groupDiv = document.createElement('div');
        groupDiv.className = 'relation-group';
        
        groupDiv.innerHTML = `
            <div class="relation-group-header">
                <div class="relation-group-title">
                    <span class="relation-type-badge">${formattedType}</span>
                    <span class="relation-count">${typeRelations.length} relationship${typeRelations.length > 1 ? 's' : ''}</span>
                </div>
                ${description ? `<div class="relation-description">${description}</div>` : ''}
            </div>
            <div class="relation-group-items"></div>
        `;
        
        const itemsContainer = groupDiv.querySelector('.relation-group-items');
        
        typeRelations.forEach((relation) => {
            const entities = relation.entities || [];
            const confidence = relation.confidenceScore;
            
            const relationDiv = document.createElement('div');
            relationDiv.className = 'relation-item';
            
            // Build entity cards with more detail
            const entityCards = entities.map((e, idx) => {
                // Handle confidence - API returns 0-1, convert to percentage
                let confidencePercent = null;
                if (e.confidenceScore !== undefined && e.confidenceScore !== null) {
                    // If value is > 1, it's already a percentage; otherwise multiply by 100
                    confidencePercent = e.confidenceScore > 1 ? Math.round(e.confidenceScore) : Math.round(e.confidenceScore * 100);
                }
                const confidenceClass = confidencePercent >= 90 ? 'high' : confidencePercent >= 70 ? 'medium' : 'low';
                
                return `
                    <div class="relation-entity-card">
                        <div class="entity-role">${e.role || 'Entity'}</div>
                        <div class="entity-text">${e.text || 'Unknown'}</div>
                        <div class="entity-meta">
                            <span class="entity-category-tag">${formatCategoryName(e.category || '')}</span>
                            ${confidencePercent !== null && confidencePercent > 0 ? `<span class="entity-confidence ${confidenceClass}">${confidencePercent}%</span>` : ''}
                        </div>
                    </div>
                `;
            }).join(`<div class="relation-connector"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg></div>`);
            
            // Confidence indicator for the relation itself
            let relationConfidencePercent = null;
            if (confidence !== undefined && confidence !== null) {
                relationConfidencePercent = confidence > 1 ? Math.round(confidence) : Math.round(confidence * 100);
            }
            const relationConfidenceHtml = relationConfidencePercent !== null && relationConfidencePercent > 0 ? 
                `<div class="relation-confidence-bar"><span>${relationConfidencePercent}% confidence</span><div class="confidence-fill" style="width: ${relationConfidencePercent}%"></div></div>` : '';
            
            relationDiv.innerHTML = `
                <div class="relation-entities-flow">${entityCards}</div>
                ${relationConfidenceHtml}
            `;
            
            itemsContainer.appendChild(relationDiv);
        });
        
        container.appendChild(groupDiv);
    });
    
    // Add summary at the top
    const summaryDiv = document.createElement('div');
    summaryDiv.className = 'relations-summary';
    summaryDiv.innerHTML = `
        <div class="summary-stat">
            <span class="stat-value">${relations.length}</span>
            <span class="stat-label">Total Relationships</span>
        </div>
        <div class="summary-stat">
            <span class="stat-value">${Object.keys(groupedRelations).length}</span>
            <span class="stat-label">Relationship Types</span>
        </div>
    `;
    container.insertBefore(summaryDiv, container.firstChild);
}

/**
 * Format category name for display
 */
function formatCategoryName(category) {
    return category
        .replace(/([A-Z])/g, ' $1')
        .replace(/^./, str => str.toUpperCase())
        .trim();
}

/**
 * Download JSON file
 */
function downloadJson(data, filename) {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}

/**
 * Initialize tabs
 */
function initializeTabs() {
    const tabs = document.querySelectorAll('.tab');
    const panes = document.querySelectorAll('.tab-pane');
    
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const target = tab.dataset.tab;
            
            tabs.forEach(t => t.classList.remove('active'));
            panes.forEach(p => p.classList.remove('active'));
            
            tab.classList.add('active');
            document.getElementById(`${target}Tab`).classList.add('active');
        });
    });
}
