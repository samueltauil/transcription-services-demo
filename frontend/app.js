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
        
        // Display transcription
        document.getElementById('transcriptionText').textContent = 
            data.transcription?.text || 'No transcription available';
        
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
 * Display medical entities by category
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
            tag.innerHTML = `
                ${entity.text}
                <span class="confidence">${Math.round(entity.confidence_score * 100)}%</span>
            `;
            list.appendChild(tag);
        });
        
        categoryDiv.appendChild(list);
        container.appendChild(categoryDiv);
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
