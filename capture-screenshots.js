const { chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

(async () => {
  console.log('Launching browser...');
  const browser = await chromium.launch({ 
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const context = await browser.newContext({
    viewport: { width: 2560, height: 1440 },
    deviceScaleFactor: 2  // Retina/HiDPI for sharper images
  });
  const page = await context.newPage();

  const url = 'https://lemon-meadow-03ec82310.4.azurestaticapps.net/';
  console.log(`Navigating to ${url}...`);
  await page.goto(url, { waitUntil: 'networkidle' });
  
  // Wait a bit for animations to settle
  await page.waitForTimeout(2000);

  // 1. Dashboard screenshot (light mode)
  console.log('Capturing dashboard.png...');
  await page.screenshot({ 
    path: path.join(__dirname, 'docs', 'dashboard.png'),
    fullPage: false
  });

  // 2. Upload interface close-up
  console.log('Capturing upload-interface.png...');
  const uploadSection = await page.locator('.upload-section').first();
  if (await uploadSection.isVisible()) {
    await uploadSection.screenshot({ 
      path: path.join(__dirname, 'docs', 'upload-interface.png')
    });
  }

  // 3. Upload sample file if it exists
  const sampleFile = path.join(__dirname, 'samples', 'sample-clinical.mp3');
  if (fs.existsSync(sampleFile)) {
    console.log('\nUploading sample file...');
    
    // Find and click the file input
    const fileInput = await page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(sampleFile);
    await page.waitForTimeout(1000);

    // Click the process button
    const processBtn = await page.locator('.primary-btn, button:has-text("Process")').first();
    if (await processBtn.isVisible() && !await processBtn.isDisabled()) {
      await processBtn.click();
      console.log('Processing started...');
      
      // Wait for processing to complete (check for status changes)
      await page.waitForTimeout(5000);
      
      // Try to wait for completion (max 2 minutes)
      try {
        await page.waitForSelector('.status-badge:has-text("Completed")', { 
          timeout: 120000 
        });
        console.log('Processing completed!');
        
        // Wait for results to render
        await page.waitForTimeout(2000);
        
        // 4. Capture medical entities - full section with scroll
        console.log('Capturing medical-entities.png...');
        const entitiesSection = await page.locator('#medicalEntities, .entities-section, .card:has-text("Medical Entities")').first();
        if (await entitiesSection.isVisible()) {
          // Scroll the section into view and wait
          await entitiesSection.scrollIntoViewIfNeeded();
          await page.waitForTimeout(500);
          await entitiesSection.screenshot({ 
            path: path.join(__dirname, 'docs', 'medical-entities.png'),
            type: 'png'
          });
        }
        
        // 5. Capture relationships - full section
        console.log('Capturing relationships.png...');
        const relationshipsSection = await page.locator('#relationships, .relationships-section, .card:has-text("Relationships")').first();
        if (await relationshipsSection.isVisible()) {
          await relationshipsSection.scrollIntoViewIfNeeded();
          await page.waitForTimeout(500);
          await relationshipsSection.screenshot({ 
            path: path.join(__dirname, 'docs', 'relationships.png'),
            type: 'png'
          });
        }
        
        // 6. Capture FHIR export - with more context
        console.log('Capturing fhir-export.png...');
        const fhirSection = await page.locator('#fhirBundle, .fhir-section, .card:has-text("FHIR")').first();
        if (await fhirSection.isVisible()) {
          await fhirSection.scrollIntoViewIfNeeded();
          await page.waitForTimeout(500);
          await fhirSection.screenshot({ 
            path: path.join(__dirname, 'docs', 'fhir-export.png'),
            type: 'png'
          });
        }
        
      } catch (error) {
        console.log('⚠️  Processing timeout or error:', error.message);
        console.log('   Will capture remaining screenshots manually');
      }
    }
  }

  // 7. Switch to dark mode
  console.log('\nSwitching to dark mode...');
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  
  const themeToggle = await page.locator('#themeToggle, .theme-toggle, button[aria-label*="theme"], button:has-text("🌙"), button:has-text("☀️")').first();
  if (await themeToggle.isVisible()) {
    await themeToggle.click();
    await page.waitForTimeout(500);
  }
  
  console.log('Capturing dark-mode.png...');
  await page.screenshot({ 
    path: path.join(__dirname, 'docs', 'dark-mode.png'),
    fullPage: false
  });

  await browser.close();
  
  // Check which screenshots were created
  const screenshots = [
    'dashboard.png',
    'upload-interface.png',
    'dark-mode.png',
    'medical-entities.png',
    'relationships.png',
    'fhir-export.png'
  ];
  
  console.log('\n✅ Screenshot capture complete!');
  console.log('\nCaptured screenshots:');
  screenshots.forEach(filename => {
    const filepath = path.join(__dirname, 'docs', filename);
    if (fs.existsSync(filepath)) {
      const stats = fs.statSync(filepath);
      console.log(`   ✓ ${filename} (${(stats.size / 1024).toFixed(1)} KB)`);
    } else {
      console.log(`   ✗ ${filename} (not captured)`);
    }
  });
})();
