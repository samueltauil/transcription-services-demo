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
    initializeTheme();
    initializeUpload();
    initializeTabs();
});

/**
 * Initialize theme toggle functionality
 */
function initializeTheme() {
    const themeToggle = document.getElementById('themeToggle');
    
    // Check for saved theme preference or system preference
    const savedTheme = localStorage.getItem('theme');
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    if (savedTheme) {
        document.documentElement.setAttribute('data-theme', savedTheme);
    } else if (systemPrefersDark) {
        document.documentElement.setAttribute('data-theme', 'dark');
    }
    
    // Toggle theme on button click
    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
        });
    }
    
    // Listen for system theme changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        if (!localStorage.getItem('theme')) {
            document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
        }
    });
}

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
        summaryLoaded = false; // Reset summary state for new job
        
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
                // Hide spinner on completion
                const spinner = document.getElementById('statusSpinner');
                if (spinner) spinner.classList.add('hidden');
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
 * Update status step and progress bar
 */
function updateStatus(step, state) {
    const stepEl = document.querySelector(`.status-step[data-step="${step}"]`);
    if (stepEl) {
        stepEl.classList.remove('active', 'completed', 'error');
        stepEl.classList.add(state);
    }
    
    // Update progress bar and badge
    updateProgressBar();
    updateStatusBadge(state);
}

/**
 * Update the progress bar based on completed steps
 */
function updateProgressBar() {
    const steps = ['upload', 'transcribe', 'analyze', 'complete'];
    const progressFill = document.getElementById('statusProgressFill');
    const progressText = document.getElementById('statusProgressText');
    
    if (!progressFill || !progressText) return;
    
    let completedCount = 0;
    let hasActive = false;
    
    steps.forEach((step, index) => {
        const stepEl = document.querySelector(`.status-step[data-step="${step}"]`);
        if (stepEl) {
            if (stepEl.classList.contains('completed')) {
                completedCount = index + 1;
            } else if (stepEl.classList.contains('active')) {
                hasActive = true;
                completedCount = index + 0.5; // Halfway through current step
            }
        }
    });
    
    const percentage = Math.round((completedCount / steps.length) * 100);
    progressFill.style.width = `${percentage}%`;
    progressText.textContent = `${percentage}%`;
}

/**
 * Update the status badge
 */
function updateStatusBadge(state) {
    const badge = document.getElementById('statusBadge');
    if (!badge) return;
    
    badge.classList.remove('completed', 'error');
    
    if (state === 'completed') {
        // Check if all steps are completed
        const allCompleted = Array.from(document.querySelectorAll('.status-step'))
            .every(step => step.classList.contains('completed'));
        if (allCompleted) {
            badge.textContent = 'Completed';
            badge.classList.add('completed');
        }
    } else if (state === 'error') {
        badge.textContent = 'Error';
        badge.classList.add('error');
    } else {
        badge.textContent = 'In Progress';
    }
}

/**
 * Reset all status steps
 */
function resetStatus() {
    document.querySelectorAll('.status-step').forEach(step => {
        step.classList.remove('active', 'completed', 'error');
    });
    
    // Reset progress bar
    const progressFill = document.getElementById('statusProgressFill');
    const progressText = document.getElementById('statusProgressText');
    const badge = document.getElementById('statusBadge');
    const spinner = document.getElementById('statusSpinner');
    
    if (progressFill) progressFill.style.width = '0%';
    if (progressText) progressText.textContent = '0%';
    if (badge) {
        badge.textContent = 'In Progress';
        badge.classList.remove('completed', 'error');
    }
    if (spinner) spinner.classList.remove('hidden');
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
    updateStatusBadge('error');
    
    // Hide spinner on error
    const spinner = document.getElementById('statusSpinner');
    if (spinner) spinner.classList.add('hidden');
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
        
        console.log('Results loaded:', data);
        
        resultsSection.style.display = 'block';
        
        // Calculate and display cost savings based on audio duration
        updateCostSavings();
        
        // Update summary cards
        document.getElementById('processingTime').textContent = 
            data.processing_time_seconds ? `${data.processing_time_seconds.toFixed(1)}s` : '-';
        document.getElementById('speakerCount').textContent = 
            data.medical_analysis?.summary?.speaker_count || data.medical_analysis?.diarization?.speaker_count || '1';
        document.getElementById('entityCount').textContent = 
            data.medical_analysis?.summary?.total_entities || '-';
        document.getElementById('relationCount').textContent = 
            data.medical_analysis?.summary?.total_relations || '-';
        document.getElementById('linkedCount').textContent = 
            data.medical_analysis?.summary?.linked_entities || '0';
        
        // Update assertion detection chips
        const assertionStats = data.medical_analysis?.summary?.assertions;
        updateAssertionChips(assertionStats);
        
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
        
        // Display relations with entity assertion correlation
        displayRelations(data.medical_analysis?.relations || [], data.medical_analysis?.entities || []);
        
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
 * Update assertion detection chips based on analysis results
 */
function updateAssertionChips(assertionStats) {
    const summaryBar = document.getElementById('assertionSummaryBar');
    
    if (!assertionStats) {
        summaryBar.style.display = 'none';
        return;
    }
    
    // Check if any assertions exist
    const hasAssertions = Object.values(assertionStats).some(v => v > 0);
    
    if (!hasAssertions) {
        summaryBar.style.display = 'none';
        return;
    }
    
    summaryBar.style.display = 'flex';
    
    // Update each chip - show only if count > 0
    const chipConfigs = [
        { id: 'chipNegated', countId: 'negatedCount', key: 'negated' },
        { id: 'chipHypothetical', countId: 'hypotheticalCount', key: 'hypothetical' },
        { id: 'chipConditional', countId: 'conditionalCount', key: 'conditional' },
        { id: 'chipOtherSubject', countId: 'otherSubjectCount', key: 'other_subject' },
        { id: 'chipTemporalPast', countId: 'temporalPastCount', key: 'temporal_past' },
        { id: 'chipTemporalFuture', countId: 'temporalFutureCount', key: 'temporal_future' },
        { id: 'chipUncertain', countId: 'uncertainCount', key: 'uncertain' }
    ];
    
    chipConfigs.forEach(config => {
        const chip = document.getElementById(config.id);
        const countEl = document.getElementById(config.countId);
        const count = assertionStats[config.key] || 0;
        
        if (count > 0) {
            chip.style.display = 'flex';
            countEl.textContent = count;
        } else {
            chip.style.display = 'none';
        }
    });
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
            
            // Build assertion badges based on Microsoft Text Analytics for Health
            // Reference: https://learn.microsoft.com/en-us/azure/ai-services/language-service/text-analytics-for-health/concepts/assertion-detection
            let assertionHtml = '';
            if (entity.assertion) {
                const certainty = entity.assertion.certainty;
                const conditionality = entity.assertion.conditionality;
                const association = entity.assertion.association;
                const temporal = entity.assertion.temporal;
                
                // CERTAINTY - presence/absence of the concept
                // Values: positive (default), negative, positive_possible, negative_possible, neutral_possible
                if (certainty === 'negative') {
                    assertionHtml += '<span class="assertion-badge negated" title="Certainty: Negative - concept does not exist">Negated</span>';
                } else if (certainty === 'negative_possible' || certainty === 'negativePossible') {
                    assertionHtml += '<span class="assertion-badge negated-possible" title="Certainty: Negative Possible - unlikely but uncertain">Possibly Absent</span>';
                } else if (certainty === 'positive_possible' || certainty === 'positivePossible') {
                    assertionHtml += '<span class="assertion-badge affirmed-possible" title="Certainty: Positive Possible - likely exists but uncertain">Likely Present</span>';
                } else if (certainty === 'neutral_possible' || certainty === 'neutralPossible') {
                    assertionHtml += '<span class="assertion-badge uncertain" title="Certainty: Neutral Possible - may or may not exist">Uncertain</span>';
                }
                // Note: positive is default, no badge needed
                
                // CONDITIONALITY - whether existence depends on conditions
                // Values: none (default), hypothetical, conditional
                if (conditionality === 'hypothetical') {
                    assertionHtml += '<span class="assertion-badge hypothetical" title="Conditionality: Hypothetical - may develop in future">Hypothetical</span>';
                } else if (conditionality === 'conditional') {
                    assertionHtml += '<span class="assertion-badge conditional" title="Conditionality: Conditional - exists only under certain conditions">Conditional</span>';
                }
                
                // ASSOCIATION - who the concept is associated with
                // Values: subject (default), other
                if (association === 'other') {
                    assertionHtml += '<span class="assertion-badge other-subject" title="Association: Other - associated with family member or other person">Family/Other</span>';
                }
                
                // TEMPORAL - when the concept occurred
                // Values: current (default), past, future
                if (temporal === 'past') {
                    assertionHtml += '<span class="assertion-badge temporal-past" title="Temporal: Past - prior to current encounter">Past</span>';
                } else if (temporal === 'future') {
                    assertionHtml += '<span class="assertion-badge temporal-future" title="Temporal: Future - planned/scheduled">Future</span>';
                }
            }
            
            // Extract UMLS code if available - use public NLM browser URL
            let umlsCode = '';
            let umlsUrl = '';
            if (entity.links && entity.links.length > 0) {
                const umlsLink = entity.links.find(l => l.dataSource === 'UMLS');
                if (umlsLink) {
                    umlsCode = umlsLink.id;
                    // Use NLM's public concept report page (no login required)
                    umlsUrl = `https://ncim.nci.nih.gov/ncimbrowser/ConceptReport.jsp?dictionary=NCI%20Metathesaurus&code=${umlsLink.id}`;
                }
            }
            
            // Build UMLS code display (removed other ontology links like AOD, CCC)
            const umlsHtml = umlsCode 
                ? `<a href="${umlsUrl}" target="_blank" class="umls-code" title="View ${umlsCode} in NCI Metathesaurus">${umlsCode}</a>` 
                : '';
            
            tag.innerHTML = `
                <span class="entity-text">${entity.text}</span>
                ${umlsHtml}
                ${assertionHtml}
                <span class="confidence">${Math.round(entity.confidence_score * 100)}%</span>
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
        const speaker = phrase.speaker || 1;
        // Azure Speech API uses 1-based speaker IDs, convert to 0-based for array indexing
        const speakerIndex = speaker - 1;
        const colorIdx = Math.max(0, speakerIndex) % speakerColors.length;
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
            // Use speaker number directly (already 1-based from API)
            labelSpan.textContent = `Speaker ${speaker}`;
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
 * @param {Array} relations - The relations array from API
 * @param {Array} allEntities - All entities for assertion lookup correlation
 */
function displayRelations(relations, allEntities = []) {
    const container = document.getElementById('relationsContainer');
    container.innerHTML = '';
    
    if (!relations || relations.length === 0) {
        container.innerHTML = '<p class="placeholder">No relationships found between medical entities</p>';
        return;
    }
    
    // Build lookup map for assertions by offset (entities in relations don't include assertions)
    const assertionsByOffset = {};
    allEntities.forEach(entity => {
        if (entity.assertion && entity.offset !== undefined) {
            assertionsByOffset[entity.offset] = entity.assertion;
        }
    });
    
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
            
            // Build entity cards with more detail and assertion lookup
            const entityCards = entities.map((e, idx) => {
                // Handle confidence - API returns 0-1, convert to percentage
                let confidencePercent = null;
                if (e.confidenceScore !== undefined && e.confidenceScore !== null) {
                    // If value is > 1, it's already a percentage; otherwise multiply by 100
                    confidencePercent = e.confidenceScore > 1 ? Math.round(e.confidenceScore) : Math.round(e.confidenceScore * 100);
                }
                const confidenceClass = confidencePercent >= 90 ? 'high' : confidencePercent >= 70 ? 'medium' : 'low';
                
                // Look up assertion from correlated entity by offset
                const assertion = assertionsByOffset[e.offset];
                let assertionHtml = '';
                
                if (assertion) {
                    const certainty = assertion.certainty || assertion.Certainty;
                    const conditionality = assertion.conditionality || assertion.Conditionality;
                    const association = assertion.association || assertion.Association;
                    const temporal = assertion.temporal || assertion.Temporal;
                    
                    // CERTAINTY badges
                    if (certainty === 'negative') {
                        assertionHtml += '<span class="assertion-badge-sm negated" title="Negated - entity is explicitly denied">✗ Negated</span>';
                    } else if (certainty === 'negative_possible' || certainty === 'negativePossible') {
                        assertionHtml += '<span class="assertion-badge-sm negated-possible" title="Possibly absent">? Possibly Absent</span>';
                    } else if (certainty === 'positive_possible' || certainty === 'positivePossible') {
                        assertionHtml += '<span class="assertion-badge-sm affirmed-possible" title="Likely present">~ Likely</span>';
                    } else if (certainty === 'neutral_possible' || certainty === 'neutralPossible') {
                        assertionHtml += '<span class="assertion-badge-sm uncertain" title="Uncertain">? Uncertain</span>';
                    }
                    
                    // CONDITIONALITY badges
                    if (conditionality === 'hypothetical') {
                        assertionHtml += '<span class="assertion-badge-sm hypothetical" title="Hypothetical condition">⚡ Hypothetical</span>';
                    } else if (conditionality === 'conditional') {
                        assertionHtml += '<span class="assertion-badge-sm conditional" title="Conditional">↔ Conditional</span>';
                    }
                    
                    // ASSOCIATION badges
                    if (association === 'other') {
                        assertionHtml += '<span class="assertion-badge-sm other-subject" title="Related to family/other">👤 Other Person</span>';
                    }
                    
                    // TEMPORAL badges
                    if (temporal === 'past') {
                        assertionHtml += '<span class="assertion-badge-sm temporal-past" title="Past occurrence">◄ Past</span>';
                    } else if (temporal === 'future') {
                        assertionHtml += '<span class="assertion-badge-sm temporal-future" title="Future/planned">► Future</span>';
                    }
                }
                
                return `
                    <div class="relation-entity-card${assertion ? ' has-assertion' : ''}">
                        <div class="entity-role">${e.role || 'Entity'}</div>
                        <div class="entity-text">${e.text || 'Unknown'}</div>
                        ${assertionHtml ? `<div class="entity-assertions">${assertionHtml}</div>` : ''}
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
    
    // Count assertions in relations for summary
    let relationsWithAssertions = 0;
    let negatedInRelations = 0;
    let conditionalInRelations = 0;
    
    relations.forEach(relation => {
        const entities = relation.entities || [];
        let hasAssertion = false;
        entities.forEach(e => {
            const assertion = assertionsByOffset[e.offset];
            if (assertion) {
                hasAssertion = true;
                if (assertion.certainty === 'negative' || assertion.certainty === 'negative_possible') {
                    negatedInRelations++;
                }
                if (assertion.conditionality) {
                    conditionalInRelations++;
                }
            }
        });
        if (hasAssertion) relationsWithAssertions++;
    });
    
    // Add summary at the top
    const summaryDiv = document.createElement('div');
    summaryDiv.className = 'relations-summary';
    
    let assertionSummaryHtml = '';
    if (relationsWithAssertions > 0) {
        assertionSummaryHtml = `
            <div class="summary-stat assertion-stat">
                <span class="stat-value">${relationsWithAssertions}</span>
                <span class="stat-label">With Assertions</span>
            </div>
        `;
        if (negatedInRelations > 0) {
            assertionSummaryHtml += `
                <div class="summary-stat negated-stat">
                    <span class="stat-value">${negatedInRelations}</span>
                    <span class="stat-label">Negated Entities</span>
                </div>
            `;
        }
    }
    
    summaryDiv.innerHTML = `
        <div class="summary-stat">
            <span class="stat-value">${relations.length}</span>
            <span class="stat-label">Total Relationships</span>
        </div>
        <div class="summary-stat">
            <span class="stat-value">${Object.keys(groupedRelations).length}</span>
            <span class="stat-label">Relationship Types</span>
        </div>
        ${assertionSummaryHtml}
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

// ============================================================================
// AI Summary Functions
// ============================================================================

// Summary state
let summaryLoaded = false;
let regenerateCooldownTimer = null;
let cooldownRemaining = 0;

/**
 * Load AI-generated clinical summary
 * @param {boolean} regenerate - Force regeneration of cached summary
 */
async function loadSummary(regenerate = false) {
    if (!currentJobId) {
        console.warn('No job ID available for summary');
        return;
    }
    
    const loadingEl = document.getElementById('summaryLoading');
    const contentEl = document.getElementById('summaryContent');
    const errorEl = document.getElementById('summaryError');
    const footerEl = document.getElementById('summaryFooter');
    const regenerateBtn = document.getElementById('regenerateSummary');
    
    // Show loading state
    loadingEl.style.display = 'flex';
    contentEl.innerHTML = '';
    errorEl.style.display = 'none';
    
    // Disable regenerate button during loading
    if (regenerateBtn) {
        regenerateBtn.disabled = true;
    }
    
    try {
        const url = regenerate 
            ? `${API_BASE_URL}/summary/${currentJobId}?regenerate=true`
            : `${API_BASE_URL}/summary/${currentJobId}`;
            
        const response = await fetch(url);
        const data = await response.json();
        
        // Hide loading
        loadingEl.style.display = 'none';
        
        if (!response.ok) {
            // Handle cooldown error
            if (response.status === 429 && data.cooldown_remaining_seconds) {
                startCooldownTimer(data.cooldown_remaining_seconds);
                // Show cached summary if available
                if (data.summary_text) {
                    displaySummary(data);
                    footerEl.style.display = 'flex';
                }
                return;
            }
            
            throw new Error(data.error || `HTTP ${response.status}`);
        }
        
        // Display the summary
        displaySummary(data);
        summaryLoaded = true;
        
        // Show footer with metadata
        footerEl.style.display = 'flex';
        
        // Enable regenerate button
        if (regenerateBtn) {
            regenerateBtn.disabled = false;
        }
        
    } catch (error) {
        console.error('Failed to load summary:', error);
        loadingEl.style.display = 'none';
        errorEl.style.display = 'flex';
        document.getElementById('summaryErrorText').textContent = error.message;
        footerEl.style.display = 'none';
        
        // Enable regenerate button even on error
        if (regenerateBtn) {
            regenerateBtn.disabled = false;
        }
    }
}

/**
 * Display the AI summary content
 */
function displaySummary(data) {
    const contentEl = document.getElementById('summaryContent');
    const errorEl = document.getElementById('summaryError');
    const pdfBtn = document.getElementById('downloadPdf');
    
    errorEl.style.display = 'none';
    
    if (!data.summary_text) {
        contentEl.innerHTML = '<p class="placeholder">No summary available. Click "Regenerate" to generate one.</p>';
        if (pdfBtn) pdfBtn.disabled = true;
        return;
    }
    
    // Parse and format the markdown-style summary
    const formattedSummary = formatSummaryText(data.summary_text);
    contentEl.innerHTML = formattedSummary;
    
    // Enable PDF download button
    if (pdfBtn) pdfBtn.disabled = false;
    
    // Update metadata
    const cachedBadge = document.getElementById('cachedBadge');
    if (data.cached) {
        cachedBadge.style.display = 'inline-flex';
    } else {
        cachedBadge.style.display = 'none';
    }
    
    // Update generated timestamp
    if (data.generated_at) {
        const date = new Date(data.generated_at);
        document.getElementById('generatedAt').textContent = `Generated: ${date.toLocaleString()}`;
    }
    
    // Update model info
    if (data.model) {
        document.getElementById('summaryModel').textContent = `Model: ${data.model}`;
    }
    
    // Update token usage
    if (data.token_usage) {
        document.getElementById('promptTokens').textContent = `Prompt: ${data.token_usage.prompt_tokens?.toLocaleString() || '-'}`;
        document.getElementById('completionTokens').textContent = `Completion: ${data.token_usage.completion_tokens?.toLocaleString() || '-'}`;
        document.getElementById('totalTokens').textContent = `Total: ${data.token_usage.total_tokens?.toLocaleString() || '-'}`;
        
        if (data.token_usage.estimated_cost_usd !== undefined) {
            const cost = data.token_usage.estimated_cost_usd;
            document.getElementById('estimatedCost').textContent = `Est. Cost: $${cost < 0.01 ? cost.toFixed(6) : cost.toFixed(4)}`;
        }
    }
}

/**
 * Format the summary text using marked.js for proper markdown rendering
 */
function formatSummaryText(text) {
    // Check if marked is available
    if (typeof marked === 'undefined') {
        console.warn('marked.js not loaded, falling back to basic formatting');
        return `<div class="markdown-body"><pre>${text}</pre></div>`;
    }
    
    // Configure marked for clinical content
    marked.setOptions({
        breaks: true,        // Convert \n to <br>
        gfm: true,           // GitHub Flavored Markdown
        headerIds: false,    // Don't add IDs to headers
        mangle: false,       // Don't escape autolinks
        sanitize: false      // Allow HTML (we trust OpenAI output)
    });
    
    // Parse markdown to HTML
    let html = marked.parse(text);
    
    // Wrap in styled container
    return `<div class="markdown-body">${html}</div>`;
}

/**
 * Start the regenerate cooldown timer
 */
function startCooldownTimer(seconds) {
    const regenerateBtn = document.getElementById('regenerateSummary');
    const btnText = regenerateBtn?.querySelector('.btn-text');
    const cooldownText = regenerateBtn?.querySelector('.cooldown-text');
    const timerSpan = document.getElementById('cooldownTimer');
    
    if (!regenerateBtn) return;
    
    cooldownRemaining = Math.ceil(seconds);
    regenerateBtn.disabled = true;
    regenerateBtn.classList.add('cooldown');
    
    if (btnText) btnText.style.display = 'none';
    if (cooldownText) cooldownText.style.display = 'inline';
    
    // Clear any existing timer
    if (regenerateCooldownTimer) {
        clearInterval(regenerateCooldownTimer);
    }
    
    // Update timer display
    if (timerSpan) timerSpan.textContent = cooldownRemaining;
    
    regenerateCooldownTimer = setInterval(() => {
        cooldownRemaining--;
        if (timerSpan) timerSpan.textContent = cooldownRemaining;
        
        if (cooldownRemaining <= 0) {
            clearInterval(regenerateCooldownTimer);
            regenerateCooldownTimer = null;
            regenerateBtn.disabled = false;
            regenerateBtn.classList.remove('cooldown');
            if (btnText) btnText.style.display = 'inline';
            if (cooldownText) cooldownText.style.display = 'none';
        }
    }, 1000);
}

/**
 * Handle regenerate button click
 */
function handleRegenerateClick() {
    loadSummary(true);
}

/**
 * Download summary as PDF
 */
async function downloadSummaryPdf() {
    if (!currentJobId) {
        console.warn('No job ID available for PDF download');
        return;
    }
    
    const pdfBtn = document.getElementById('downloadPdf');
    const pdfToast = document.getElementById('pdfToast');
    
    // Disable button during download
    if (pdfBtn) {
        pdfBtn.disabled = true;
        pdfBtn.querySelector('.btn-text').textContent = 'Generating...';
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/summary/${currentJobId}/pdf`);
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }
        
        // Get the PDF blob
        const blob = await response.blob();
        
        // Extract filename from Content-Disposition header or use default
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = `clinical-summary-${currentJobId}.pdf`;
        if (contentDisposition) {
            const match = contentDisposition.match(/filename="(.+?)"/);
            if (match) filename = match[1];
        }
        
        // Trigger download
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        console.log('PDF downloaded successfully');
        
    } catch (error) {
        console.error('PDF download failed:', error);
        
        // Show error toast with fallback option
        if (pdfToast) {
            document.getElementById('pdfToastMessage').textContent = error.message || 'PDF generation failed';
            pdfToast.style.display = 'flex';
        }
    } finally {
        // Re-enable button
        if (pdfBtn) {
            pdfBtn.disabled = false;
            pdfBtn.querySelector('.btn-text').textContent = 'Download PDF';
        }
    }
}

/**
 * Download summary as plain text (fallback)
 */
async function downloadSummaryTxt() {
    if (!currentJobId) {
        console.warn('No job ID available for text download');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/summary/${currentJobId}/txt`);
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }
        
        const text = await response.text();
        
        // Extract filename from Content-Disposition header or use default
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = `clinical-summary-${currentJobId}.txt`;
        if (contentDisposition) {
            const match = contentDisposition.match(/filename="(.+?)"/);
            if (match) filename = match[1];
        }
        
        // Trigger download
        const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        // Hide toast
        const pdfToast = document.getElementById('pdfToast');
        if (pdfToast) pdfToast.style.display = 'none';
        
        console.log('Text file downloaded successfully');
        
    } catch (error) {
        console.error('Text download failed:', error);
        alert('Failed to download text file: ' + error.message);
    }
}

/**
 * Dismiss PDF error toast
 */
function dismissPdfToast() {
    const pdfToast = document.getElementById('pdfToast');
    if (pdfToast) pdfToast.style.display = 'none';
}

/**
 * Initialize summary tab functionality
 */
function initializeSummary() {
    const regenerateBtn = document.getElementById('regenerateSummary');
    const pdfBtn = document.getElementById('downloadPdf');
    const txtFallbackBtn = document.getElementById('downloadTxtFallback');
    const dismissToastBtn = document.getElementById('dismissToast');
    
    if (regenerateBtn) {
        regenerateBtn.addEventListener('click', handleRegenerateClick);
    }
    
    if (pdfBtn) {
        pdfBtn.addEventListener('click', downloadSummaryPdf);
    }
    
    if (txtFallbackBtn) {
        txtFallbackBtn.addEventListener('click', downloadSummaryTxt);
    }
    
    if (dismissToastBtn) {
        dismissToastBtn.addEventListener('click', dismissPdfToast);
    }
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
            
            // Load summary on-demand when tab is clicked
            if (target === 'summary' && !summaryLoaded && currentJobId) {
                loadSummary();
            }
        });
    });
    
    // Initialize summary functionality
    initializeSummary();
}
