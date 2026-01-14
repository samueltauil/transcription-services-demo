# Screenshot Guide

The README.md references the following screenshots that need to be captured from the live application:

## Required Screenshots

### 1. dashboard.png
**Location:** Main application view after page load
**What to capture:** Full page view showing HealthTranscribe logo, upload section, and overall layout
**Viewport:** 1920x1080 (desktop)

### 2. upload-interface.png
**Location:** Focus on the upload section
**What to capture:** 
- Upload header with microphone icon
- Feature tags (Speech-to-Text, Medical NER, FHIR Export)
- Drop zone with animated icon
- Format badges (WAV, MP3, FLAC, etc.)
**Viewport:** 1920x1080 (desktop)

### 3. medical-entities.png
**Location:** Results section after processing a sample medical file
**What to capture:** 
- Medical Entities table showing categories
- Entity types (Medications, Conditions, Procedures, etc.)
- Sample extracted entities
**Viewport:** 1920x1080 (desktop)

### 4. relationships.png
**Location:** Relationship mapping section in results
**What to capture:**
- Entity relationship pairs
- Connection types (Drug→Dosage, Condition→Body Structure, etc.)
**Viewport:** 1920x1080 (desktop)

### 5. fhir-export.png
**Location:** FHIR export section showing JSON bundle
**What to capture:**
- FHIR R4 Bundle structure
- Resource types (Observation, Condition, etc.)
- JSON formatted output
**Viewport:** 1920x1080 (desktop)

### 6. dark-mode.png
**Location:** Application in dark mode
**What to capture:**
- Toggle theme button in header (moon/sun icon)
- Dark background with teal accents
- Overall dark mode aesthetic
**Viewport:** 1920x1080 (desktop)

## How to Capture

### Using VS Code Simple Browser

1. Open Simple Browser: `Ctrl+Shift+P` → "Simple Browser: Show"
2. Navigate to: https://lemon-meadow-03ec82310.4.azurestaticapps.net/
3. For each screenshot:
   - Set up the view as described above
   - Use Windows Snipping Tool (`Win + Shift + S`)
   - Save to `docs/` folder with the exact filename
   - Crop to remove browser chrome if needed

### Using Browser DevTools

1. Open application in Chrome/Edge
2. Press `F12` to open DevTools
3. Press `Ctrl+Shift+P` (in DevTools)
4. Type "screenshot" and select "Capture full size screenshot"
5. Save to `docs/` folder with the exact filename

## Screenshot Checklist

- [ ] dashboard.png - Overall application view
- [ ] upload-interface.png - Upload section detail
- [ ] medical-entities.png - Entity extraction results
- [ ] relationships.png - Relationship mapping
- [ ] fhir-export.png - FHIR JSON bundle
- [ ] dark-mode.png - Dark mode UI

## Notes

- All screenshots should be at least 1920x1080 resolution
- PNG format preferred for sharp UI elements
- Compress images to keep repository size manageable (use TinyPNG or similar)
- Ensure no sensitive data is visible in screenshots
- Use sample medical transcription data for demo purposes
