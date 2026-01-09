# Sample Health Dialog

This file contains a sample healthcare conversation between a doctor and patient for testing the transcription and Text Analytics for Health services.

## Expected Medical Entities

When analyzed by Text Analytics for Health, the sample dialog should identify:

### Symptoms/Signs
- Persistent headaches
- Pressure (head/eyes)
- Fatigue
- Blurry vision
- Light sensitivity

### Medications
- Lisinopril 10mg (blood pressure medication)
- Lisinopril 20mg (increased dose)
- Ibuprofen 400mg (NSAID/pain relief)
- Acetaminophen 500mg (recommended alternative)

### Dosages
- 10 milligrams
- 20 milligrams
- 400 milligrams
- 500 milligrams

### Conditions/Diagnoses
- Hypertension (high blood pressure)
- Tension headaches (suspected)
- Rebound headaches (mentioned as risk)

### Body Structures
- Head
- Eyes
- Front of head

### Measurements
- Blood pressure: 145/95
- Blood pressure: 148/92
- Pain scale: 5-6 (sometimes 8)
- Duration: 2 weeks

### Examinations/Tests
- Blood pressure check
- Neurological exam
- Complete metabolic panel
- Eye exam

### Treatment/Recommendations
- Medication adjustment
- Lifestyle modifications
- Sodium reduction
- Regular exercise (30 min walking, 5 days/week)
- Stress management
- Follow-up in 2 weeks

## Usage

1. Upload the sample audio version of this dialog to the demo application
2. View the transcription output
3. Review extracted medical entities organized by category
4. Export the FHIR-compliant bundle

## Creating Audio Samples

To create an audio file from this transcript:

1. Use text-to-speech services (e.g., Azure TTS)
2. Record actors reading the dialog
3. Use existing audio recordings (ensure HIPAA compliance)

Supported formats: WAV, MP3, OGG, FLAC, M4A, WMA
