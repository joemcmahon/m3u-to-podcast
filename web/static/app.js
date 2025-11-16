// DOM Elements
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('fileInput');
const uploadSection = document.getElementById('upload-section');
const processingSection = document.getElementById('processing-section');
const completeSection = document.getElementById('complete-section');
const errorSection = document.getElementById('error-section');

const playlistName = document.getElementById('playlistName');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const statusMessage = document.getElementById('statusMessage');
const completeName = document.getElementById('completeName');
const errorMessage = document.getElementById('errorMessage');

// Buttons
const downloadMp3 = document.getElementById('downloadMp3');
const downloadChapters = document.getElementById('downloadChapters');
const convertAnother = document.getElementById('convertAnother');
const tryAgain = document.getElementById('tryAgain');

// State
let currentJobId = null;
let statusInterval = null;

// Drag and drop
dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
});

dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('dragover');
});

dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFile(files[0]);
    }
});

// File input
fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handleFile(e.target.files[0]);
    }
});

dropzone.addEventListener('click', () => {
    fileInput.click();
});

// File handling
function handleFile(file) {
    if (!file.name.toLowerCase().endsWith('.m3u')) {
        showError('Please select a valid .m3u file');
        return;
    }

    uploadFile(file);
}

// Upload file
async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Upload failed');
        }

        const data = await response.json();
        currentJobId = data.job_id;

        // Show processing section
        uploadSection.style.display = 'none';
        processingSection.style.display = 'block';
        completeSection.style.display = 'none';
        errorSection.style.display = 'none';

        playlistName.textContent = data.filename;

        // Start polling for status
        startStatusPolling();
    } catch (error) {
        showError(`Upload failed: ${error.message}`);
    }
}

// Poll for status updates
function startStatusPolling() {
    if (statusInterval) clearInterval(statusInterval);

    statusInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/status/${currentJobId}`);
            if (!response.ok) throw new Error('Status check failed');

            const status = await response.json();
            updateUI(status);

            if (status.status === 'complete') {
                clearInterval(statusInterval);
                showComplete(status);
            } else if (status.status === 'error') {
                clearInterval(statusInterval);
                showError(status.message);
            }
        } catch (error) {
            console.error('Status check error:', error);
        }
    }, 500);
}

// Update UI with status
function updateUI(status) {
    const progress = status.progress || 0;
    progressFill.style.width = progress + '%';
    progressText.textContent = progress + '%';
    statusMessage.textContent = status.message || 'Processing...';

    // Update steps
    updateStep('parsing', status.message);
    updateStep('concat', status.message);
    updateStep('chapters', status.message);
    updateStep('merging', status.message);
}

// Update individual step
function updateStep(stepName, message) {
    const step = document.getElementById(`step-${stepName}`);
    if (!step) return;

    const stepTexts = {
        'parsing': 'Parsing playlist',
        'concat': 'Preparing audio files',
        'chapters': 'Computing chapters',
        'merging': 'Merging audio'
    };

    const currentText = stepTexts[stepName];
    const messageToCheck = (message || '').toLowerCase();

    if (messageToCheck.includes('parsing')) {
        setStepStatus('parsing', 'active');
        setStepStatus('concat', 'pending');
        setStepStatus('chapters', 'pending');
        setStepStatus('merging', 'pending');
    } else if (messageToCheck.includes('concat') || messageToCheck.includes('preparing')) {
        setStepStatus('parsing', 'complete');
        setStepStatus('concat', 'active');
        setStepStatus('chapters', 'pending');
        setStepStatus('merging', 'pending');
    } else if (messageToCheck.includes('chapter') || messageToCheck.includes('computing')) {
        setStepStatus('parsing', 'complete');
        setStepStatus('concat', 'complete');
        setStepStatus('chapters', 'active');
        setStepStatus('merging', 'pending');
    } else if (messageToCheck.includes('merging')) {
        setStepStatus('parsing', 'complete');
        setStepStatus('concat', 'complete');
        setStepStatus('chapters', 'complete');
        setStepStatus('merging', 'active');
    }
}

// Set step status
function setStepStatus(stepName, status) {
    const step = document.getElementById(`step-${stepName}`);
    if (!step) return;

    step.classList.remove('active', 'complete', 'pending');
    step.classList.add(status);

    const icon = step.querySelector('.step-icon');
    if (status === 'complete') {
        icon.textContent = '✓';
    } else if (status === 'active') {
        icon.textContent = '●';
    } else {
        icon.textContent = '○';
    }
}

// Show complete section
function showComplete(status) {
    processingSection.style.display = 'none';
    completeSection.style.display = 'block';
    completeName.textContent = playlistName.textContent;

    // Set up download buttons
    downloadMp3.onclick = () => downloadFileByType('mp3');
    downloadChapters.onclick = () => downloadFileByType('chapters');
}

// Download file
async function downloadFileByType(fileType) {
    const url = `/api/download/${currentJobId}/${fileType}`;
    const response = await fetch(url);
    const blob = await response.blob();
    const urlObj = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = urlObj;

    // Determine filename
    const baseName = playlistName.textContent.replace('.m3u', '');
    if (fileType === 'mp3') {
        a.download = `${baseName}.mp3`;
    } else {
        a.download = `${baseName}_chapters.txt`;
    }

    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(urlObj);
}

// Show error
function showError(message) {
    uploadSection.style.display = 'none';
    processingSection.style.display = 'none';
    completeSection.style.display = 'none';
    errorSection.style.display = 'block';
    errorMessage.textContent = message;

    if (statusInterval) clearInterval(statusInterval);
}

// Reset UI
function resetUI() {
    uploadSection.style.display = 'block';
    processingSection.style.display = 'none';
    completeSection.style.display = 'none';
    errorSection.style.display = 'none';
    fileInput.value = '';
    currentJobId = null;

    // Reset progress
    progressFill.style.width = '0%';
    progressText.textContent = '0%';
    statusMessage.textContent = 'Starting conversion...';

    // Reset steps
    setStepStatus('parsing', 'pending');
    setStepStatus('concat', 'pending');
    setStepStatus('chapters', 'pending');
    setStepStatus('merging', 'pending');
}

// Event listeners
convertAnother.addEventListener('click', resetUI);
tryAgain.addEventListener('click', resetUI);
