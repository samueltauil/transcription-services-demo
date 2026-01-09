/**
 * Azure Healthcare Transcription Services - Frontend Application
 */

// API Configuration
// Use relative path when running locally or when API is linked to Static Web App
// Use absolute URL when API is hosted separately on Azure Functions
const API_BASE_URL = window.location.hostname === 'localhost' 
    ? '/api' 
    : 'https://healthtranscriptiondev-func-si35ec.azurewebsites.net/api';

// State
let currentJobId = null;
let selectedFile = null;
let pollInterval = null;

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
    initializeCostCalculator();
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
}

/**
 * Clear selected file
 */
function clearFile() {
    selectedFile = null;
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
        
        // Display FHIR
        document.getElementById('fhirOutput').textContent = 
            JSON.stringify(data.fhir_bundle, null, 2);
        
        // Setup FHIR download
        document.getElementById('downloadFhir').onclick = () => {
            downloadJson(data.fhir_bundle, `fhir-bundle-${currentJobId}.json`);
        };
        
    } catch (error) {
        console.error('Failed to load results:', error);
    }
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

/**
 * Initialize cost calculator
 */
function initializeCostCalculator() {
    const minutesInput = document.getElementById('minutesInput');
    
    function updateCosts() {
        const minutes = parseFloat(minutesInput.value) || 0;
        const transcribemeCost = minutes * 0.79;
        const azureCost = minutes * 0.003;
        const savings = transcribemeCost - azureCost;
        const savingsPercent = transcribemeCost > 0 ? (savings / transcribemeCost) * 100 : 0;
        
        document.getElementById('transcribemeCost').textContent = `$${transcribemeCost.toFixed(2)}`;
        document.getElementById('azureCost').textContent = `$${azureCost.toFixed(2)}`;
        document.getElementById('savingsAmount').textContent = `$${savings.toFixed(2)}`;
        document.getElementById('savingsPercent').textContent = `${savingsPercent.toFixed(1)}%`;
    }
    
    minutesInput.addEventListener('input', updateCosts);
    updateCosts();
}
